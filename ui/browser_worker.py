"""
BrowserWorker — Selenium 浏览器自动化 worker(独立线程跑 Selenium)。

v2.05 P6 模块化拆分:从主程序 novel_ai.py 外迁(原 2475 行)。

设计要点:
- 三种启动模式(chrome attach / standalone Edge / standalone Chrome)
- selenium 子模块按需局部 import(性能 + 容错)
- SELENIUM_AVAILABLE 各文件独立 try/except(避免循环 import)
"""

import os
import sys
import time
import json
import glob
import queue
import socket
import threading
import tempfile
import traceback
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, pyqtSignal

# selenium 顶层 try/except(独立重定义,避免循环 import)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    try:
        from selenium.webdriver.edge.options import Options as EdgeOptions
    except ImportError:
        EdgeOptions = None
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    webdriver = None
    ChromeOptions = None
    EdgeOptions = None

# selenium 子模块(常用的顶层引入,方法内局部 import 也照旧保留)
try:
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import WebDriverException
except ImportError:
    ActionChains = None
    By = None
    Keys = None
    WebDriverException = Exception

# v2.11 BUG-076 修复:P6 拆分时 AST 抽取漏了这个 module-level 函数。
# BrowserWorker 在 _dispatch_send / _send_prompt / _build_send_xpath 等 4 处用到,
# 静态测试没触发(只在真实派发 prompt 时进入这些路径),实战立刻 NameError。
# 跟 BUG-074 同根因(P3~P6 拆分留下的隐藏地雷)。
from core.site_profiles import _profile_for_url


class BrowserWorker(QObject):
    """
    在独立线程里跑 Selenium,挂载真实 Chrome/Edge 浏览器。
    主线程通过 submit() 投递任务,通过信号接收日志/回复/状态变化。

    三种启动模式(由 channel 参数选择):
      - "chrome"  → attach 模式:自动启动调试 Chrome(--remote-debugging-port=9222)再 attach。
                    最稳:与浏览器解耦,Chrome 崩了 driver 不会一起死。
      - "msedge"  → standalone Edge,自带 profile。
      - 其它(None / "chromium") → standalone Chrome,自带 profile。
    """
    log_signal = pyqtSignal(str, str)            # message, level
    response_received = pyqtSignal(str, str)     # task_id, content
    status_signal = pyqtSignal(str)              # idle / busy / starting / stopped / error
    started = pyqtSignal()                       # 浏览器就绪
    # v2.22.2 BUG-083:任务进度信号(给主进程的"卡死提醒"判定用)
    # 主进程的 90 秒"卡死"弹窗以前是纯时间触发,Qwen 写章节本来就要 4-5 分钟,
    # 每次都误报。现在 worker 在 polling 抓到内容时 emit (task_id, char_count),
    # 主进程跟踪每个 task 的最新字符数,只在"该任务 0 字节卡了 90 秒"时才弹窗。
    task_progress = pyqtSignal(str, int)         # task_id, current_char_count
    # v2.22.3 BUG-085: Qwen 思考期 _check_timeout 误报"卡住"修复
    # 实战日志(21:44:11):任务实际 17 秒后成功 985 字,但 90 秒时已弹
    # "0 字节无回复(可能真卡住了)" — 因为 Qwen 思考阶段就是合法的
    # 0 字节 0-90 秒。worker polling 检测 thinking_indicator 状态变化时
    # emit (task_id, is_thinking)。主进程 _check_timeout 看到 thinking=True
    # 时延期 60 秒再查,不弹窗。
    task_thinking = pyqtSignal(str, bool)        # task_id, is_thinking
    # v2.23.0 BUG-086: 番茄榜单扫描完成信号
    # gen_inspiration 流程会先扫榜,scrape_fanqie_rank 任务完成时 emit
    # (task_id, list[dict]) — books 列表(已解析,可直接传给 core.fanqie_rank_scraper)
    # books 为空 = 扫榜失败 / 扫到 0 条,主进程要 fallback 到旧通用 prompt
    rank_scraped = pyqtSignal(str, list)          # task_id, books_list
    # v2.23.1: 番茄全榜扫描信号
    # rank_progress: 每扫完一个榜单 emit (task_id, current, total, label, books_count)
    #   主进程用来更新进度对话框,用户看见"扫描 5/74:男频阅读榜·西方奇幻 → 10 本"
    # rank_all_scraped: 全部扫完后 emit (task_id, stats_dict)
    #   stats_dict 是 aggregate_v231_stats 输出,包含整个榜单矩阵的聚合统计
    #   stats_dict["total_books"] == 0 → 扫榜全失败,主进程 fallback
    rank_progress = pyqtSignal(str, int, int, str, int)   # task_id, cur, total, label, n_books
    rank_all_scraped = pyqtSignal(str, dict)              # task_id, stats_dict
    # v2.23.3: 详情抓取相关信号
    # detail_progress: 每抓完一本 emit (task_id, current, total, book_id)
    #   主进程更新 INDEX.md 或状态栏
    # detail_batch_done: 整批详情抓完 emit (task_id, success_count, fail_count)
    detail_progress = pyqtSignal(str, int, int, str)      # task_id, cur, total, book_id
    detail_batch_done = pyqtSignal(str, int, int)         # task_id, success, fail

    DEBUG_PORT = 9222

    def __init__(self):
        super().__init__()
        self.task_queue = queue.Queue()
        self.thread = None
        self._stop = threading.Event()
        self._browser_ready = threading.Event()
        self.user_data_dir = str(Path.home() / "NovelAI_Browser_Data")
        Path(self.user_data_dir).mkdir(exist_ok=True)
        self.channel = None
        self.driver = None
        # 用于"内容稳定即视为回复完成"的等待窗口(秒)
        self.stable_wait = 4
        self.max_wait = 240  # 单次最长等待 4 分钟
        # DeepSeek 深度思考模式(主线程根据 UI 设置)
        self._deep_think_enabled = False
        # v2.23.1: 扫榜取消事件,用户在进度对话框点"用部分数据生成"时 set,
        # _scrape_fanqie_all_ranks 循环里每榜检查,触发就提前 emit 结果退出
        self._scan_cancel = threading.Event()

    # ============ 主线程调用接口 ============
    def start(self, channel=None):
        if self.thread and self.thread.is_alive():
            self.log_signal.emit("浏览器已在运行", "warn")
            return
        if not SELENIUM_AVAILABLE:
            self.log_signal.emit(
                "未安装 Selenium。请运行:\n"
                "  pip install -U selenium\n"
                "(selenium 4.6+ 自动管理 chromedriver,无需单独装)", "error")
            return
        self.channel = channel
        self._stop.clear()
        self._browser_ready.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.status_signal.emit("starting")

    def stop(self):
        self._stop.set()
        # 投空任务唤醒队列
        self.task_queue.put({"action": "_quit"})

    def submit(self, task):
        """提交任务。task: {'action': 'navigate'|'send_prompt'|'just_grab', ...}"""
        self.task_queue.put(task)

    def is_ready(self):
        return self._browser_ready.is_set()

    def cancel_scan(self):
        """v2.23.1: 主进程调用,触发扫榜循环提前退出(用户点'用部分数据生成')

        线程安全:_scan_cancel 是 threading.Event,_scrape_fanqie_all_ranks 在
        循环里轮询 .is_set()。调用此方法后,扫榜循环会在下一榜开始前退出,
        并 emit 当前已扫到的数据(不是空)。
        """
        self._scan_cancel.set()

    def reset_scan_cancel(self):
        """v2.23.1: 主进程调用,在开始新扫榜前清掉取消标志"""
        self._scan_cancel.clear()

    # ============ Chrome 探测与启动辅助 ============
    @staticmethod
    def _find_chrome_exe():
        """探测 Chrome 可执行文件路径(Windows / macOS / Linux)"""
        candidates = []
        if sys.platform == "win32":
            for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                       os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                       os.environ.get("LocalAppData", "")):
                if pf:
                    candidates.append(Path(pf) / "Google/Chrome/Application/chrome.exe")
        elif sys.platform == "darwin":
            candidates.append(Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        else:
            # 先用 shutil.which() 探测 PATH，兼容 Flatpak/AppImage/自定义安装
            import shutil
            for name in ("google-chrome", "google-chrome-stable",
                         "chromium-browser", "chromium", "chrome"):
                found = shutil.which(name)
                if found:
                    return found
            # 再兜底硬编码路径（snap 等不在 PATH 里的场景）
            for p in ("/usr/bin/google-chrome", "/usr/bin/chromium-browser",
                      "/usr/bin/chromium", "/snap/bin/chromium",
                      "/var/lib/flatpak/exports/bin/com.google.Chrome"):
                candidates.append(Path(p))
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    @staticmethod
    def _find_edge_exe():
        candidates = []
        if sys.platform == "win32":
            for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                       os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
                candidates.append(Path(pf) / "Microsoft/Edge/Application/msedge.exe")
        elif sys.platform == "darwin":
            candidates.append(Path(
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))
        else:
            import shutil
            for name in ("microsoft-edge", "microsoft-edge-stable", "msedge"):
                found = shutil.which(name)
                if found:
                    return found
            candidates.append(Path("/usr/bin/microsoft-edge"))
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    @staticmethod
    def _port_in_use(port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            return s.connect_ex(("127.0.0.1", int(port))) == 0
        finally:
            s.close()

    @staticmethod
    def _profile_locked(profile_dir):
        """检测 user-data-dir 是否被另一个 Chrome 占用"""
        p = Path(profile_dir)
        if not p.exists():
            return False
        for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            f = p / lock
            if f.exists() or f.is_symlink():
                return True
        return False

    def _launch_debug_chrome(self, port, user_data_dir):
        """
        启动一个带远程调试端口的 Chrome 子进程。
        与本程序解耦,即使 driver 挂了 Chrome 还在,反之亦然。
        """
        if self._port_in_use(port):
            self.log_signal.emit(
                f"端口 {port} 已被占用 —— 直接 attach 现有调试 Chrome", "info")
            return  # 已有调试 Chrome,直接 attach 即可

        chrome_path = self._find_chrome_exe()
        if not chrome_path:
            raise RuntimeError(
                "找不到 Chrome 可执行文件。\n"
                "请确认已安装 Google Chrome,或改用「Chromium 自带」(standalone)模式。")

        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        if self._profile_locked(user_data_dir):
            raise RuntimeError(
                f"Profile 目录被锁定:{user_data_dir}\n"
                f"请关闭所有使用该 profile 的 Chrome,或删除目录里的 Singleton* 文件。")

        cmd = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        # 隐藏浏览器:移到屏幕外
        if getattr(self, '_hide_browser', False):
            cmd += ["--window-position=-2400,-2400", "--window-size=800,600"]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
        subprocess.Popen(cmd, **kwargs)
        self.log_signal.emit(f"已派发调试 Chrome 子进程,端口 {port}", "info")

        # 最长等 5 秒,等端口监听起来
        for _ in range(10):
            time.sleep(0.5)
            if self._port_in_use(port):
                return
        raise RuntimeError(
            f"调试 Chrome 启动后端口 {port} 5 秒内未监听 —— 可能被防火墙挡了或参数被忽略")

    @staticmethod
    def _diagnose(msg):
        m = (msg or "").lower()
        if "unable to obtain driver" in m or "selenium manager" in m or "could not start" in m:
            return ("【诊断】Selenium 自动下载 chromedriver 失败!常见原因:\n"
                    "  1. 网络/防火墙拦截了 Selenium Manager(无法访问 googleapis.com)\n"
                    "  2. 公司机器禁止下载可执行文件\n"
                    "  3. Chrome 版本太新,driver 还没匹配\n"
                    "✅ 解决方案(任选一):\n"
                    "  方案 A: pip install webdriver-manager(自动用中国镜像下载,推荐)\n"
                    "  方案 B: 开一次梯子让程序下载 chromedriver,之后本地缓存会自动复用\n"
                    "  方案 C: 手动下载 chromedriver → "
                    "https://googlechromelabs.github.io/chrome-for-testing/ "
                    "→ 解压到 PATH 路径(如 C:\\Windows\\)\n"
                    "  方案 D: 切换内核到「系统 Edge」(Windows 10+ 内置不用下 driver)")
        if "session not created" in m and "chrome" in m:
            return ("【诊断】Chrome 启动后立刻退出。常见原因:\n"
                    "  1. 同 profile 已有 Chrome 运行 → 关掉所有 Chrome 重试\n"
                    "  2. ChromeDriver 与 Chrome 版本不匹配 → pip install -U selenium\n"
                    "  3. profile 目录被锁 → 删除 ~/NovelAI_Browser_Data 里的 Singleton* 文件\n"
                    "✅ 推荐:把内核切成「系统 Chrome」(自动起调试 Chrome 后 attach,最稳)")
        if "chrome not reachable" in m:
            return "【诊断】无法连接 Chrome(端口不对或浏览器已关)"
        if "chromedriver" in m and ("version" in m or "mismatch" in m):
            return ("【诊断】ChromeDriver 版本不匹配。\n"
                    "  方案 A: pip install -U selenium\n"
                    "  方案 B: pip install -U webdriver-manager(自动管理版本)")
        if "no such file" in m or "not found" in m or "cannot find" in m:
            return "【诊断】找不到浏览器可执行文件,请确认 Chrome / Edge 已安装"
        return ("【诊断】未知错误。\n"
                "  · 先试:关闭所有 Chrome 窗口后重试\n"
                "  · 再试:切换内核到「系统 Edge」(最稳兜底)\n"
                "  · 最后:pip install -U selenium webdriver-manager")

    @staticmethod
    def _resolve_chrome_driver_service():
        """四层兜底获取 chromedriver Service(优先本地缓存,避免翻墙):
        1) Selenium Manager 缓存目录(~/.cache/selenium/ 或 ~/AppData/Local/selenium/)
        2) webdriver-manager 缓存目录(~/.wdm/)
        3) PATH 里的 chromedriver
        4) webdriver-manager 在线下载(尝试中国镜像)
        返回 Service 对象或 None"""
        try:
            from selenium.webdriver.chrome.service import Service as _CS
            import shutil as _shu

            # ── 层 1:扫 Selenium Manager 本地缓存 ──
            cache_roots = []
            if sys.platform == "win32":
                local_app = os.environ.get("LOCALAPPDATA", "")
                if local_app:
                    cache_roots.append(Path(local_app) / "selenium" / "chromedriver")
            else:
                cache_roots.append(Path.home() / ".cache" / "selenium" / "chromedriver")
            for root in cache_roots:
                if root.exists():
                    # 找最新版的 chromedriver 可执行文件
                    exes = sorted(root.rglob("chromedriver*"), key=lambda p: p.stat().st_mtime, reverse=True)
                    for exe in exes:
                        if exe.is_file() and exe.stat().st_size > 1_000_000:  # >1MB = 真 binary
                            return _CS(str(exe))

            # ── 层 2:扫 webdriver-manager 本地缓存 ──
            wdm_root = Path.home() / ".wdm" / "drivers" / "chromedriver"
            if wdm_root.exists():
                exes = sorted(wdm_root.rglob("chromedriver*"), key=lambda p: p.stat().st_mtime, reverse=True)
                for exe in exes:
                    if exe.is_file() and exe.stat().st_size > 1_000_000:
                        return _CS(str(exe))

            # ── 层 3:PATH 里的 chromedriver ──
            cd_path = _shu.which("chromedriver") or _shu.which("chromedriver.exe")
            if cd_path:
                return _CS(cd_path)

            # ── 层 4:webdriver-manager 在线下载(尝试中国镜像)──
            try:
                from webdriver_manager.chrome import ChromeDriverManager as _CDM
                # 优先用 npmmirror 中国镜像,不需要翻墙
                os.environ.setdefault(
                    "WDM_URL", "https://registry.npmmirror.com/-/binary/chromedriver")
                return _CS(_CDM().install())
            except (ImportError, Exception):
                pass

        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_edge_driver_service():
        """同 Chrome 版本,Edge 本地缓存优先"""
        try:
            from selenium.webdriver.edge.service import Service as _ES
            import shutil as _shu

            # 层 1:Selenium Manager 本地缓存
            cache_roots = []
            if sys.platform == "win32":
                local_app = os.environ.get("LOCALAPPDATA", "")
                if local_app:
                    cache_roots.append(Path(local_app) / "selenium" / "msedgedriver")
            else:
                cache_roots.append(Path.home() / ".cache" / "selenium" / "msedgedriver")
            for root in cache_roots:
                if root.exists():
                    exes = sorted(root.rglob("msedgedriver*"), key=lambda p: p.stat().st_mtime, reverse=True)
                    for exe in exes:
                        if exe.is_file() and exe.stat().st_size > 1_000_000:
                            return _ES(str(exe))

            # 层 2:PATH
            ed_path = _shu.which("msedgedriver") or _shu.which("msedgedriver.exe")
            if ed_path:
                return _ES(ed_path)

            # 层 3:webdriver-manager 在线
            try:
                from webdriver_manager.microsoft import EdgeChromiumDriverManager as _EDM
                return _ES(_EDM().install())
            except (ImportError, Exception):
                pass
        except Exception:
            pass
        return None

    # ============ Worker 后台主循环 ============
    def _run(self):
        try:
            self._launch_driver()
            self._browser_ready.set()
            self.started.emit()
            self.log_signal.emit(
                f"真实浏览器已就绪 (channel={self.channel or 'chromium'}),"
                f"用户数据目录:{self.user_data_dir}", "success")
            self.status_signal.emit("idle")

            while not self._stop.is_set():
                try:
                    task = self.task_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if task.get("action") == "_quit":
                    break
                self._handle(task)
        except Exception as e:
            self.log_signal.emit(f"浏览器异常:{e}", "error")
            self.status_signal.emit("error")
        finally:
            self._teardown_driver()
            self.status_signal.emit("stopped")
            self.log_signal.emit("浏览器已关闭", "info")

    def _launch_driver(self):
        """根据 channel 选择启动方式"""
        ch = self.channel
        if ch == "msedge":
            if EdgeOptions is None:
                raise RuntimeError("当前 selenium 不支持 Edge,请升级:pip install -U selenium")
            opts = EdgeOptions()
            edge_path = self._find_edge_exe()
            if edge_path:
                opts.binary_location = edge_path
            opts.add_argument(f"--user-data-dir={self.user_data_dir}_edge")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            self.log_signal.emit("→ Edge standalone 模式", "info")
            # v2.12.2:优先本地缓存
            svc = self._resolve_edge_driver_service()
            try:
                if svc:
                    self.log_signal.emit("使用本地缓存的 msedgedriver(无需联网)", "info")
                    self.driver = webdriver.Edge(options=opts, service=svc)
                else:
                    self.driver = webdriver.Edge(options=opts)
            except Exception as e:
                if svc:
                    self.log_signal.emit("本地 msedgedriver 版本不匹配,尝试 Selenium Manager", "warn")
                    try:
                        self.driver = webdriver.Edge(options=opts)
                    except Exception as e2:
                        raise RuntimeError(f"{e2}\n\n{self._diagnose(str(e2))}")
                else:
                    raise RuntimeError(f"{e}\n\n{self._diagnose(str(e))}")

        elif ch == "chrome":
            # attach 模式 + 自动起调试 Chrome
            self.log_signal.emit("→ Chrome attach 模式(先起调试 Chrome 再 attach)", "info")
            self._launch_debug_chrome(self.DEBUG_PORT, self.user_data_dir)
            opts = ChromeOptions()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.DEBUG_PORT}")
            # v2.12.2:优先本地缓存的 chromedriver,避免每次联网(国内 googleapis 被墙)
            svc = self._resolve_chrome_driver_service()
            try:
                if svc:
                    self.log_signal.emit("使用本地缓存的 chromedriver(无需联网)", "info")
                    self.driver = webdriver.Chrome(options=opts, service=svc)
                else:
                    self.driver = webdriver.Chrome(options=opts)
            except Exception as e:
                # 本地缓存失败(版本不匹配等),回退到 Selenium Manager
                if svc:
                    self.log_signal.emit("本地 chromedriver 版本不匹配,尝试 Selenium Manager", "warn")
                    try:
                        self.driver = webdriver.Chrome(options=opts)
                    except Exception as e2:
                        raise RuntimeError(f"{e2}\n\n{self._diagnose(str(e2))}")
                else:
                    raise RuntimeError(f"{e}\n\n{self._diagnose(str(e))}")

        else:
            # standalone Chromium
            opts = ChromeOptions()
            chrome_path = self._find_chrome_exe()
            if chrome_path:
                opts.binary_location = chrome_path
            if self._profile_locked(self.user_data_dir):
                raise RuntimeError(
                    f"Profile 已被另一个 Chrome 占用:{self.user_data_dir}\n"
                    "请关闭所有 Chrome 窗口,或换成「系统 Chrome」(attach 模式)")
            opts.add_argument(f"--user-data-dir={self.user_data_dir}")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            self.log_signal.emit("→ Chromium standalone 模式", "info")
            # v2.12.2:优先本地缓存的 chromedriver
            svc = self._resolve_chrome_driver_service()
            try:
                if svc:
                    self.log_signal.emit("使用本地缓存的 chromedriver(无需联网)", "info")
                    self.driver = webdriver.Chrome(options=opts, service=svc)
                else:
                    self.driver = webdriver.Chrome(options=opts)
            except Exception as e:
                if svc:
                    self.log_signal.emit("本地 chromedriver 版本不匹配,尝试 Selenium Manager", "warn")
                    try:
                        self.driver = webdriver.Chrome(options=opts)
                    except Exception as e2:
                        raise RuntimeError(f"{e2}\n\n{self._diagnose(str(e2))}")
                else:
                    raise RuntimeError(f"{e}\n\n{self._diagnose(str(e))}")

        # 反爬:抹掉 navigator.webdriver
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            })
        except Exception:
            pass

    def _teardown_driver(self):
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _is_alive(self):
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    # ============ 任务派发 ============
    def _handle(self, task):
        action = task.get("action")
        try:
            self.status_signal.emit("busy")
            if action == "navigate":
                self._goto(task["url"])
            elif action == "goto":
                self._goto(task["url"])
                self.log_signal.emit(
                    f"已导航到:{task['url'][:80]}", "info")
            elif action == "new_chat":
                self._start_new_chat(task.get("url", ""))
            elif action == "send_prompt":
                self._send_prompt(task)
            elif action == "just_grab":
                prof = _profile_for_url(self._current_url())
                self.response_received.emit(
                    task.get("task_id", ""), self._grab_last_response(prof))
            elif action == "scrape_fanqie_rank":
                # v2.23.0 BUG-086: 番茄单榜扫描(保留兼容)
                # 流程:navigate → 等懒加载 → 多重 selector 抓取 → emit rank_scraped
                # 失败兜底:任何异常 → emit 空列表,主进程会 fallback 到旧 prompt
                self._scrape_fanqie_rank(task)
            elif action == "scrape_fanqie_all_ranks":
                # v2.23.1: 番茄全榜矩阵扫描(74 榜单 × Top10)
                # 流程:循环 74 个分类榜单 URL → 每榜 navigate + 正则抓 book_id +
                #       emit rank_progress → 全部完成 emit rank_all_scraped(stats)
                # 取消:用户点"用部分数据生成"→ 主进程 cancel_scan() →
                #       循环检测 _scan_cancel,提前退出 emit 部分结果
                # 失败兜底:任何榜失败跳过继续下一榜,全失败 emit empty stats
                self._scrape_fanqie_all_ranks(task)
            elif action == "scrape_book_details_batch":
                # v2.23.3: 详情页深度抓取(后台任务)
                # 流程:接收 task["book_ids"] (list of (bid, label, category)),
                #       逐个 navigate /page/{book_id} → 抓 page_source meta →
                #       parse_detail_page_html → save_book_detail 写磁盘
                # 礼让:每抓完一本检查 task_queue.qsize(),有任务就让位
                # 主进程通过 task["project_root"] 告诉 worker 缓存目录
                self._scrape_book_details_batch(task)
            self.status_signal.emit("idle")
        except Exception as e:
            self.log_signal.emit(f"任务执行失败:{e}", "error")
            self.status_signal.emit("idle")

    def _current_url(self):
        try:
            return self.driver.current_url or ""
        except Exception:
            return ""

    def _scrape_fanqie_rank(self, task):
        """
        v2.23.0 BUG-086: 扫描番茄小说榜单页面

        流程:
          1. navigate 到榜单 URL(默认 https://fanqienovel.com/rank?enter_from=menu)
          2. 等页面加载 + 滚动让懒加载内容出现
          3. 用 JS 多重 selector 尝试抓 book 卡片
          4. 解析每张卡的 title/category/abstract/read_count
          5. emit rank_scraped 信号给主进程

        失败兜底:任何异常 → emit 空列表,主进程会 fallback 到旧通用 prompt。
        """
        task_id = task.get("task_id", "fanqie_rank")
        try:
            from core.fanqie_rank_scraper import FANQIE_SCRAPER_PROFILE
        except Exception as e:
            self.log_signal.emit(
                f"⚠ 扫榜模块导入失败:{e},fallback 到旧灵感 prompt", "warn")
            self.rank_scraped.emit(task_id, [])
            return

        prof = FANQIE_SCRAPER_PROFILE
        rank_url = task.get("url") or prof.get("rank_url", "")
        if not rank_url:
            self.log_signal.emit("⚠ 扫榜 URL 为空", "warn")
            self.rank_scraped.emit(task_id, [])
            return

        if not self._is_alive():
            self.log_signal.emit("⚠ 浏览器未就绪,无法扫榜", "warn")
            self.rank_scraped.emit(task_id, [])
            return

        try:
            self.log_signal.emit(f"📊 扫描番茄榜单:{rank_url}", "info")
            self._goto(rank_url)
            wait_sec = float(prof.get("wait_after_load_sec", 3.5))
            time.sleep(wait_sec)

            # 滚动让懒加载内容出现
            scroll_steps = int(prof.get("scroll_steps", 3))
            scroll_pause = float(prof.get("scroll_pause_sec", 0.6))
            for i in range(scroll_steps):
                try:
                    self.driver.execute_script(
                        "window.scrollBy(0, window.innerHeight * 0.8);")
                except Exception:
                    pass
                time.sleep(scroll_pause)

            # 多重 selector 尝试抓取
            card_sels = prof.get("book_card_selectors", [])
            title_sels = prof.get("title_selectors", [])
            cat_sels = prof.get("category_selectors", [])
            abs_sels = prof.get("abstract_selectors", [])
            read_sels = prof.get("read_count_selectors", [])

            # 用 JS 一次抓回所有卡片字段(避免 selenium 单元素查询的慢)
            js = """
            const cardSels = arguments[0];
            const titleSels = arguments[1];
            const catSels = arguments[2];
            const absSels = arguments[3];
            const readSels = arguments[4];
            function findFirst(root, sels) {
                for (const s of sels) {
                    try {
                        const el = root.querySelector(s);
                        if (el && el.textContent) return el.textContent.trim();
                    } catch(e) {}
                }
                return "";
            }
            let cards = [];
            for (const cs of cardSels) {
                try {
                    const nodes = document.querySelectorAll(cs);
                    if (nodes && nodes.length > 0) {
                        cards = Array.from(nodes);
                        break;
                    }
                } catch(e) {}
            }
            // 兜底:如果没有任何 selector 命中,尝试用通用启发式
            // (页面里"看起来像书卡片"的元素 — 有 a 标签 + 文本)
            if (cards.length === 0) {
                try {
                    const allAs = document.querySelectorAll('a[href*="/page/"], a[href*="/book/"]');
                    const seen = new Set();
                    for (const a of allAs) {
                        let p = a.closest('div, li');
                        if (p && !seen.has(p)) { seen.add(p); cards.push(p); }
                        if (cards.length >= 50) break;
                    }
                } catch(e) {}
            }
            const out = [];
            for (const card of cards.slice(0, 50)) {
                const title = findFirst(card, titleSels) || (card.textContent || '').slice(0, 30);
                const category = findFirst(card, catSels);
                const abstract = findFirst(card, absSels);
                const read_count = findFirst(card, readSels);
                if (title || category) {
                    out.push({title, category, abstract, read_count});
                }
            }
            return out;
            """
            raw_data = self.driver.execute_script(
                js, card_sels, title_sels, cat_sels, abs_sels, read_sels) or []

            # 解析 + 去重
            from core.fanqie_rank_scraper import parse_scraped_books
            books = parse_scraped_books(raw_data)
            self.log_signal.emit(
                f"📊 扫榜完成:抓到 {len(raw_data)} 张卡片,有效 {len(books)} 本", "info")
            # emit dict 列表(信号跨进程,Book 对象不能直接传)
            self.rank_scraped.emit(task_id, [b.to_dict() for b in books])
        except Exception as e:
            self.log_signal.emit(
                f"⚠ 扫榜异常:{e},fallback 到旧灵感 prompt", "warn")
            self.rank_scraped.emit(task_id, [])

    def _scrape_fanqie_all_ranks(self, task):
        """
        v2.23.1: 番茄全榜矩阵扫描(74 榜单 × Top10)

        流程:
          1. 加载 74 个分类榜单 URL 列表(从 fanqie_rank_scraper.get_all_rank_urls())
          2. 循环每个 URL:
             a. 检查 _scan_cancel,触发就提前退出(早退机制)
             b. navigate 到该榜单
             c. 等加载 + 滚动让懒加载内容出现
             d. 抓 page_source HTML,调 parse_rank_page_minimal 解析
             e. emit rank_progress(cur, total, label, n_books)
          3. 全部扫完后调 aggregate_v231_stats 聚合
          4. emit rank_all_scraped(stats_dict)

        失败兜底:任何单榜失败 → 该榜 books=[] 但继续下一榜。全失败 → stats 为空。

        重要:用 self.driver.page_source 拿 HTML(不是 execute_script),
        因为榜单页有字体反爬,parse_rank_page_minimal 用正则只抽
        book_id + 在读数,这两个字段在 HTML 里是干净的(book_id 在 URL 里,数字也是)。
        """
        task_id = task.get("task_id", "fanqie_all_ranks")

        try:
            from core.fanqie_rank_scraper import (
                get_all_rank_urls, parse_rank_page_minimal, aggregate_v231_stats,
            )
        except Exception as e:
            self.log_signal.emit(
                f"⚠ 全榜扫榜模块导入失败:{e},fallback 到旧灵感 prompt", "warn")
            self.rank_all_scraped.emit(task_id, {})
            return

        if not self._is_alive():
            self.log_signal.emit("⚠ 浏览器未就绪,无法扫全榜", "warn")
            self.rank_all_scraped.emit(task_id, {})
            return

        all_urls = get_all_rank_urls()
        total = len(all_urls)
        self.log_signal.emit(
            f"📊 v2.23.1 全榜扫描开始:共 {total} 个分类榜单 × Top10 = "
            f"{total * 10} 本预期", "info")

        scraped = []
        scanned_ok = 0
        scanned_fail = 0

        # v2.23.4 BUG-B: 开独立标签扫榜(不覆盖 DeepSeek/Qwen)
        _orig_handle = None
        _scan_handle = None
        try:
            _orig_handle = self.driver.current_window_handle
            _before = set(self.driver.window_handles)
            self.driver.execute_script("window.open('about:blank','_blank');")
            time.sleep(0.3)
            _after = set(self.driver.window_handles)
            _new = _after - _before
            if _new:
                _scan_handle = _new.pop()
                self.driver.switch_to.window(_scan_handle)
            else:
                _scan_handle = _orig_handle
        except Exception:
            _scan_handle = _orig_handle

        for i, board in enumerate(all_urls, 1):
            # 取消检查:用户在进度对话框点了"用部分数据生成"
            if self._scan_cancel.is_set():
                self.log_signal.emit(
                    f"📊 扫榜已被用户取消(进度 {i - 1}/{total}),"
                    f"用部分数据(已扫 {len(scraped)} 榜)", "info")
                break

            url = board["url"]
            label = board["label"]
            books = []
            try:
                # v2.23.2 BUG-087: 不能用 self._goto() — 它有"同 host 跳过 navigate"优化
                # (双 AI 切换时复用标签),导致 74 次循环里浏览器从来没真正切换 URL,
                # 一直停在第一个 fanqienovel.com 标签的原始页面(可能是详情页),
                # 每次抓 page_source 都是同一本书的详情页 → 全部 0 本。
                # 修法:直接 driver.get(url) 强制每次都真 navigate。
                try:
                    self.driver.get(url)
                except Exception as ge:
                    raise RuntimeError(f"navigate 失败: {ge}")

                # 等 React 渲染完(番茄是 SPA,JS 渲染需要时间)
                time.sleep(2.5)

                # 滚动让懒加载内容出现
                try:
                    self.driver.execute_script(
                        "window.scrollBy(0, window.innerHeight * 0.8);")
                except Exception:
                    pass
                time.sleep(0.5)

                # v2.23.2 BUG-087: 用 JS DOM 查询而不是 page_source 正则。
                # page_source 在 React 应用里可能是渲染前的 #root 空 div,
                # 而 querySelectorAll 拿到的是渲染后的真实 DOM。
                # 抓:所有指向 /page/{book_id} 的 a 标签 + 同 row 里的"在读 XX万"文本
                # 字体反爬只影响显示文本,DOM href 和数字+万的文本是干净的
                try:
                    raw_books = self.driver.execute_script("""
                        const links = document.querySelectorAll('a[href*="/page/"]');
                        const seen = new Set();
                        const out = [];
                        for (const a of links) {
                            const href = a.getAttribute('href') || '';
                            const m = href.match(/\\/page\\/(\\d{10,})/);
                            if (!m) continue;
                            const bid = m[1];
                            if (seen.has(bid)) continue;
                            seen.add(bid);
                            // 找最近的 row 容器(向上 4 层找)
                            let row = a;
                            for (let i = 0; i < 6; i++) {
                                if (!row.parentElement) break;
                                row = row.parentElement;
                                // 看这层有没有"万"字(在读数),有就停
                                if (row.textContent && /\\d+(?:\\.\\d+)?\\s*万/.test(row.textContent)) {
                                    break;
                                }
                            }
                            const rowText = row.textContent || '';
                            const readMatch = rowText.match(/(\\d+(?:\\.\\d+)?)\\s*万/);
                            out.push({
                                book_id: bid,
                                read_count_raw: readMatch ? readMatch[0] : '',
                                read_count_num: readMatch ? Math.round(parseFloat(readMatch[1]) * 10000) : 0,
                            });
                            if (out.length >= 10) break;
                        }
                        return out;
                    """) or []
                    books = list(raw_books) if raw_books else []
                except Exception as js_err:
                    self.log_signal.emit(
                        f"⚠ 扫榜 [{label}] JS 抓取失败({js_err}),"
                        f"fallback 到 page_source 正则", "warn")
                    # JS fallback 到 page_source 正则(v2.23.1 老路径)
                    try:
                        html = self.driver.page_source or ""
                    except Exception:
                        html = ""
                    books = parse_rank_page_minimal(html, max_books=10)

                if books:
                    scanned_ok += 1
                else:
                    scanned_fail += 1

                # v2.23.2 BUG-087: 第一榜 + 失败榜各打一条 DEBUG,方便诊断
                if i == 1 or (not books and scanned_fail <= 3):
                    try:
                        cur_url = self.driver.current_url
                    except Exception:
                        cur_url = "?"
                    self.log_signal.emit(
                        f"  [DEBUG] {label}: 当前 URL={cur_url[-60:]}, "
                        f"抓到 {len(books)} 本", "info")

            except Exception as e:
                scanned_fail += 1
                self.log_signal.emit(
                    f"⚠ 扫榜 [{label}] 失败({e}),跳过", "warn")
                books = []

            scraped.append({
                "label": label,
                "gender": board["gender"],
                "type": board["type"],
                "category": board["category"],
                "cat_id": board["cat_id"],
                "books": books,
            })

            self.rank_progress.emit(task_id, i, total, label, len(books))

            # 每 10 个榜单打一条进度日志(避免刷屏)
            if i % 10 == 0 or i == total:
                self.log_signal.emit(
                    f"📊 扫榜进度 {i}/{total}(成功 {scanned_ok}, 失败 {scanned_fail})", "info")

        # 聚合统计
        stats = aggregate_v231_stats(scraped) if scraped else {}
        if stats:
            stats["scanned_ok"] = scanned_ok
            stats["scanned_fail"] = scanned_fail
            stats["cancelled"] = self._scan_cancel.is_set()
            # v2.23.3: 嵌入 scraped 列表本身,主进程能取 Top5 book_id 做详情抓取
            stats["_scraped_raw"] = scraped

        self.log_signal.emit(
            f"📊 全榜扫描完成:共扫 {len(scraped)} 榜(成功 {scanned_ok}/失败 {scanned_fail}),"
            f"得到 {stats.get('total_books', 0)} 本(去重后 {stats.get('unique_books', 0)} 本)",
            "info")

        # v2.23.4 BUG-B: 关掉扫榜标签,切回原标签
        try:
            if _scan_handle and _scan_handle != _orig_handle:
                self.driver.switch_to.window(_scan_handle)
                self.driver.close()
                self.driver.switch_to.window(_orig_handle)
        except Exception:
            pass

        self.rank_all_scraped.emit(task_id, stats)

    def _scrape_book_details_batch(self, task):
        """
        v2.23.3: 详情页深度抓取(后台批任务)

        task 格式:
          {
            "action": "scrape_book_details_batch",
            "task_id": "fanqie_detail_batch",
            "book_ids": [(book_id, source_label, source_category), ...],
            "project_root": "<项目根目录,用于磁盘缓存>",
          }

        流程:
          for (bid, label, category) in book_ids:
            - 如果磁盘已有该 book_id 缓存且没过期 → 跳过
            - 如果 _scan_cancel 触发 → break(用户取消)
            - 如果 task_queue.qsize() > 0 → sleep 让位 AI 任务(礼让)
            - driver.get("/page/{book_id}")
            - 等 1.5 秒
            - page_source → parse_detail_page_html → save_book_detail
            - emit detail_progress
          - 写 INDEX.md
          - emit detail_batch_done

        礼让:每抓完一本检查 task_queue,有任务就 sleep 直到队列空。
        """
        task_id = task.get("task_id", "fanqie_detail_batch")
        book_ids = task.get("book_ids") or []
        project_root = task.get("project_root", "")

        try:
            from core.fanqie_rank_scraper import (
                parse_detail_page_html, save_book_detail,
                load_book_detail, write_index_md, ensure_cache_dirs,
            )
        except Exception as e:
            self.log_signal.emit(
                f"⚠ 详情抓取模块导入失败:{e}", "warn")
            self.detail_batch_done.emit(task_id, 0, 0)
            return

        if not self._is_alive():
            self.log_signal.emit("⚠ 浏览器未就绪,无法抓详情", "warn")
            self.detail_batch_done.emit(task_id, 0, 0)
            return

        if not book_ids:
            self.detail_batch_done.emit(task_id, 0, 0)
            return

        ensure_cache_dirs(project_root)

        total = len(book_ids)
        success = 0
        fail = 0
        skipped = 0
        stats_for_index = task.get("stats", {})

        self.log_signal.emit(
            f"📚 v2.23.3 后台开始抓详情:{total} 本(磁盘缓存 7 天)", "info")

        # v2.23.4: 开新标签抓详情,不覆盖 DeepSeek/Qwen 标签
        _original_handle = None
        _detail_handle = None
        try:
            _original_handle = self.driver.current_window_handle
            _handles_before = set(self.driver.window_handles)
            self.driver.execute_script("window.open('about:blank','_blank');")
            time.sleep(0.3)
            _handles_after = set(self.driver.window_handles)
            _new = _handles_after - _handles_before
            if _new:
                _detail_handle = _new.pop()
                self.driver.switch_to.window(_detail_handle)
                self.log_signal.emit(
                    "📚 已开独立标签抓详情(不影响 AI 标签)", "info")
            else:
                _detail_handle = _original_handle
        except Exception:
            _detail_handle = _original_handle

        for i, (bid, label, category) in enumerate(book_ids, 1):
            # 取消检查
            if self._scan_cancel.is_set():
                self.log_signal.emit(
                    f"📚 详情抓取被取消(已抓 {success} 本)", "info")
                break

            # 缓存命中检查(跳过已抓)
            if load_book_detail(project_root, bid):
                skipped += 1
                self.detail_progress.emit(task_id, i, total, bid)
                continue

            # 礼让:有 AI 任务排队就让位(每 0.5 秒检查一次,最多等 60 秒)
            wait_count = 0
            while self.task_queue.qsize() > 0 and wait_count < 120:
                time.sleep(0.5)
                wait_count += 1
                if self._scan_cancel.is_set():
                    break

            if self._scan_cancel.is_set():
                break

            # 抓详情
            url = f"https://fanqienovel.com/page/{bid}"
            try:
                self.driver.get(url)
                time.sleep(1.5)  # 详情页静态多,1.5 秒够

                html = ""
                try:
                    html = self.driver.page_source or ""
                except Exception:
                    html = ""

                detail = parse_detail_page_html(html)
                if detail and detail.get("title"):
                    save_book_detail(project_root, bid, detail, label, category)
                    success += 1
                else:
                    fail += 1

            except Exception as e:
                fail += 1
                self.log_signal.emit(
                    f"⚠ 详情抓取 [{bid}] 失败:{e}", "warn")

            self.detail_progress.emit(task_id, i, total, bid)

            # 每 10 本打一条进度
            if i % 10 == 0 or i == total:
                self.log_signal.emit(
                    f"📚 详情抓取进度 {i}/{total}"
                    f"(成功 {success}, 跳过 {skipped}, 失败 {fail})", "info")

            # 实时更新 INDEX.md(每 5 本)
            if i % 5 == 0 and stats_for_index:
                try:
                    write_index_md(project_root, stats_for_index,
                                    [], (success + skipped, total))
                except Exception:
                    pass

        # 最终写一次 INDEX.md
        if stats_for_index:
            try:
                write_index_md(project_root, stats_for_index,
                                [], (success + skipped, total))
            except Exception:
                pass

        self.log_signal.emit(
            f"📚 详情抓取完成:总 {total}(成功 {success} / 跳过 {skipped} / 失败 {fail})",
            "info")

        # v2.23.4: 关掉详情标签,切回原标签
        try:
            if _detail_handle and _detail_handle != _original_handle:
                self.driver.switch_to.window(_detail_handle)
                self.driver.close()
                self.driver.switch_to.window(_original_handle)
                self.log_signal.emit(
                    "📚 详情标签已关闭,切回 AI 标签", "info")
        except Exception:
            pass

        # v2.23.4: 检查 DeepSeek 标签是否还在,不在就恢复
        try:
            self._ensure_ai_tab_alive()
        except Exception:
            pass

        self.detail_batch_done.emit(task_id, success, fail)

    def _ensure_ai_tab_alive(self):
        """
        v2.23.4: 检查 AI 标签(DeepSeek / Qwen)是否还在打开状态。
        如果被详情抓取覆盖或关闭了,自动重新打开。
        """
        if not self._is_alive():
            return
        try:
            _saved_handle = self.driver.current_window_handle
            ai_hosts = ["chat.deepseek.com", "chat.qwen.ai"]
            found_ai = False
            ai_handle = None
            for handle in self.driver.window_handles:
                try:
                    self.driver.switch_to.window(handle)
                    url = self.driver.current_url or ""
                    for host in ai_hosts:
                        if host in url:
                            found_ai = True
                            ai_handle = handle
                            break
                except Exception:
                    continue
                if found_ai:
                    break

            if not found_ai:
                # DeepSeek 标签不在了,重新打开
                self.log_signal.emit(
                    "⚠ AI 标签(DeepSeek)不见了,自动重新打开...", "warn")
                self.driver.execute_script(
                    "window.open('https://chat.deepseek.com/','_blank');")
                time.sleep(2)
                self.log_signal.emit(
                    "✓ 已自动恢复 DeepSeek 标签", "info")
            else:
                # 切回调用前的标签(不破坏调用者的上下文)
                try:
                    self.driver.switch_to.window(_saved_handle)
                except Exception:
                    # _saved_handle 可能已被关闭,切到 AI 标签
                    if ai_handle:
                        self.driver.switch_to.window(ai_handle)
        except Exception:
            pass

    def _goto(self, url):
        if not self._is_alive():
            return
        if not url:
            return
        cur = self._current_url()
        # v2.21.5:双 AI 分工要求频繁主↔副切换,旧逻辑每次开新标签会堆积。
        # 新策略:
        #   ① 当前 URL 已在目标 host 上 → 啥也不做(避免每次切都打开 deepseek.com/?)
        #   ② 已有打开的标签匹配目标 host → 切过去复用(不开新)
        #   ③ 都没有 → attach 模式开新标签,直连模式直接 get
        from urllib.parse import urlparse
        try:
            target_host = urlparse(url).hostname or ""
        except Exception:
            target_host = ""
        cur_host = ""
        try:
            cur_host = urlparse(cur).hostname or "" if cur else ""
        except Exception:
            pass

        # ① 当前标签已在目标 host
        if target_host and cur_host and target_host == cur_host:
            return

        # ② attach 模式:在已有标签里找匹配 host 的,切过去复用
        if self.channel == "chrome" and target_host:
            try:
                cur_handle = None
                try:
                    cur_handle = self.driver.current_window_handle
                except Exception:
                    pass
                for h in self.driver.window_handles:
                    if h == cur_handle:
                        continue
                    try:
                        self.driver.switch_to.window(h)
                        h_url = self._current_url() or ""
                        h_host = urlparse(h_url).hostname or ""
                        if h_host == target_host:
                            self.log_signal.emit(
                                f"🔁 切到已有标签:{target_host}", "info")
                            return
                    except Exception:
                        continue
                # 没找到 → 切回原标签再开新
                if cur_handle:
                    try:
                        self.driver.switch_to.window(cur_handle)
                    except Exception:
                        pass
            except Exception:
                pass

        # ③ attach 模式异站点开新标签;否则直接 get
        if (self.channel == "chrome" and cur and url
                and url.split("?")[0] != cur.split("?")[0]
                and target_host and cur_host
                and target_host != cur_host):
            try:
                self.driver.execute_script(f"window.open({json.dumps(url)},'_blank');")
                handles = self.driver.window_handles
                self.driver.switch_to.window(handles[-1])
                self.log_signal.emit(f"已在新标签打开:{url}", "info")
                return
            except Exception:
                pass
        self.driver.get(url)
        self.log_signal.emit(f"已访问:{url}", "info")

    def _start_new_chat(self, url=""):
        """开启新对话:点击新对话按钮或刷新页面"""
        if not self._is_alive():
            return
        self.log_signal.emit("🔄 正在开启新对话...", "info")
        try:
            # 方法1: 尝试用JS点击新对话按钮(各站点通用选择器)
            clicked = self.driver.execute_script(r"""
                // DeepSeek: 新对话按钮(圆圈+加号图标)
                // 通过SVG path内容精确识别
                const allBtns = document.querySelectorAll('div[role="button"]');
                for (const btn of allBtns) {
                    if (btn.offsetParent === null) continue;
                    const paths = btn.querySelectorAll('svg path');
                    for (const p of paths) {
                        const d = p.getAttribute('d') || '';
                        // DeepSeek新对话按钮的"+"号SVG特征
                        if (d.includes('4.93945') && d.includes('11.0605')) {
                            btn.click();
                            return 'clicked:deepseek-new-chat';
                        }
                    }
                }
                // 通用兜底: 找class含new-chat的元素
                const selectors = [
                    'div[class*="new-chat"]',
                    'button[class*="new-chat"]',
                    'a[class*="new-chat"]',
                    'button[aria-label*="New"]',
                    'button[aria-label*="新"]',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) {
                        el.click();
                        return 'clicked:' + sel;
                    }
                }
                return null;
            """)
            if clicked:
                self.log_signal.emit(f"✓ 新对话已开启({clicked})", "success")
                import time; time.sleep(2)
                return
        except Exception:
            pass
        # 方法2: 刷新页面(最可靠的兜底)
        try:
            cur_url = self._current_url() or url
            if cur_url:
                # 去掉路径中的对话ID,只保留域名
                from urllib.parse import urlparse
                parsed = urlparse(cur_url)
                base = f"{parsed.scheme}://{parsed.netloc}/"
                self.driver.get(base)
                self.log_signal.emit(f"✓ 已导航到首页开启新对话: {base}", "success")
                import time; time.sleep(2)
        except Exception as e:
            self.log_signal.emit(f"⚠ 开启新对话失败: {e}", "warn")

    def run_dom_diagnostics(self):
        """诊断:对当前页跑所有候选选择器,返回命中情况
        给主线程调,通过 future 同步返回结果"""
        try:
            from selenium.common.exceptions import WebDriverException
            url = self._current_url()
            prof = _profile_for_url(url)
            # 收集要测的选择器
            test_selectors = {
                "input(输入框)": prof.get("input", ""),
                "send_btn(发送按钮)": prof.get("send_btn", ""),
                "response(回复区)": prof.get("response", ""),
                "stop_btn(停止按钮)": prof.get("stop_btn", ""),
            }
            fb = prof.get("_response_fallback", [])
            for i, s in enumerate(fb):
                test_selectors[f"_response_fallback[{i}]"] = s

            # 浏览器里跑诊断
            js = r"""
            const sels = arguments[0];
            const result = {};
            for (const [name, sel] of Object.entries(sels)) {
                if (!sel) { result[name] = {selector: sel, count: 0, samples: []}; continue; }
                try {
                    const els = document.querySelectorAll(sel);
                    const samples = [];
                    for (let i = 0; i < Math.min(els.length, 3); i++) {
                        const el = els[i];
                        const visible = el.offsetParent !== null;
                        const text = (el.innerText || el.value || '').slice(0, 80).replace(/\n/g, '⏎');
                        samples.push({
                            tag: el.tagName.toLowerCase(),
                            class: (el.className || '').toString().slice(0, 60),
                            visible: visible,
                            text: text
                        });
                    }
                    result[name] = {selector: sel, count: els.length, samples: samples};
                } catch (e) {
                    result[name] = {selector: sel, error: e.message};
                }
            }
            // 额外:统计页面 DOM 概况
            result['__overview__'] = {
                title: document.title,
                url: location.href,
                total_textareas: document.querySelectorAll('textarea').length,
                total_contenteditable: document.querySelectorAll('[contenteditable="true"]').length,
                total_buttons: document.querySelectorAll('button, [role="button"]').length,
                ds_markdown_count: document.querySelectorAll('div.ds-markdown').length,
                ds_assistant_count: document.querySelectorAll('div.ds-markdown.ds-assistant-message-main-content').length,
            };
            return result;
            """
            return self.driver.execute_script(js, test_selectors)
        except WebDriverException as e:
            return {"__error__": str(e)}
        except Exception as e:
            return {"__error__": f"诊断失败:{e}"}

    def install_dom_picker(self):
        """在页面上安装现场拾取助手:
        - 鼠标 hover 时高亮元素并显示选择器建议
        - 点击时把选择器写入 window.__novelai_picked
        - 按 ESC 退出
        Python 端可以轮询 window.__novelai_picked 拿到用户选的"""
        try:
            self.driver.execute_script(r"""
            if (window.__novelai_picker_active) return;
            window.__novelai_picker_active = true;
            window.__novelai_picked = null;

            // 建议选择器:优先 id,其次 [data-testid],其次 class chain,最次 tagName
            function suggestSelector(el) {
                if (!el) return null;
                if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) {
                    return '#' + el.id;
                }
                const tid = el.getAttribute('data-testid');
                if (tid) return `[data-testid="${tid}"]`;
                const aria = el.getAttribute('aria-label');
                if (aria) return `${el.tagName.toLowerCase()}[aria-label*="${aria.slice(0,20)}"]`;
                // 优先用稳定 class(过滤 hash 形式)
                const cls = (el.className || '').toString().split(/\s+/)
                    .filter(c => c && c.length > 2 && !/^_[a-f0-9]/.test(c) && !/^[a-f0-9]{6,}$/.test(c))
                    .slice(0, 2);
                if (cls.length > 0) {
                    return el.tagName.toLowerCase() + '.' + cls.join('.');
                }
                // 兜底:tagName + nth-child
                const parent = el.parentElement;
                if (parent) {
                    const idx = Array.from(parent.children).indexOf(el);
                    return parent.tagName.toLowerCase() + ' > ' +
                           el.tagName.toLowerCase() + ':nth-child(' + (idx+1) + ')';
                }
                return el.tagName.toLowerCase();
            }

            // 浮动提示框
            let tip = document.createElement('div');
            tip.style.cssText = `
                position:fixed; z-index:999999; padding:8px 12px;
                background:#1a4480; color:white; font:13px/1.4 monospace;
                border-radius:4px; pointer-events:none;
                box-shadow:0 4px 12px rgba(0,0,0,0.3);
                max-width:600px; word-break:break-all;
            `;
            tip.innerHTML = '🎯 拾取模式 — hover 看选择器, 点击采集, ESC 退出';
            tip.style.top = '10px';
            tip.style.left = '10px';
            document.body.appendChild(tip);

            let lastHover = null;
            function onHover(e) {
                if (lastHover) lastHover.style.outline = '';
                lastHover = e.target;
                lastHover.style.outline = '3px solid red';
                const sel = suggestSelector(e.target);
                const cnt = document.querySelectorAll(sel).length;
                const txt = (e.target.innerText || e.target.value || '').slice(0, 50).replace(/\n/g, '⏎');
                tip.innerHTML = `🎯 选择器: <b>${sel}</b><br>命中 ${cnt} 个 | tag=${e.target.tagName.toLowerCase()} | text="${txt}"`;
            }
            function onClick(e) {
                e.preventDefault(); e.stopPropagation();
                const sel = suggestSelector(e.target);
                const cnt = document.querySelectorAll(sel).length;
                window.__novelai_picked = {selector: sel, count: cnt, tag: e.target.tagName.toLowerCase()};
                tip.innerHTML = `✅ 已拾取: <b>${sel}</b><br>命中 ${cnt} 个。回 PyQt 程序点用即可,或继续 hover 拾取其他。`;
                tip.style.background = '#2ecc71';
                setTimeout(() => { tip.style.background = '#1a4480'; }, 1500);
                return false;
            }
            function onKey(e) {
                if (e.key === 'Escape') {
                    if (lastHover) lastHover.style.outline = '';
                    tip.remove();
                    document.removeEventListener('mouseover', onHover, true);
                    document.removeEventListener('click', onClick, true);
                    document.removeEventListener('keydown', onKey, true);
                    window.__novelai_picker_active = false;
                }
            }
            document.addEventListener('mouseover', onHover, true);
            document.addEventListener('click', onClick, true);
            document.addEventListener('keydown', onKey, true);
            """)
            return True
        except Exception:
            return False

    def get_picked_selector(self):
        """轮询读取拾取结果"""
        try:
            return self.driver.execute_script(r"""
                const p = window.__novelai_picked;
                if (p) { window.__novelai_picked = null; return p; }
                return null;
            """)
        except Exception:
            return None

    def _inject_kbd_guard(self):
        """注入 DeepSeek 搜索 modal 三重防护(BUG-013 + 用户报告的搜索 modal 弹窗):
        1. Ctrl+K / Cmd+K 键盘拦截(capture 阶段)
        2. 直接隐藏顶部搜索按钮(用户不用 DeepSeek 自带搜索)
        3. MutationObserver 兜底:搜索 modal 一出现就关掉,防止 Selenium 误点
        用 window.__novelai_search_guard 做 flag,重复调用不会重复绑定。"""
        try:
            self.driver.execute_script(r"""
                if (window.__novelai_search_guard) return 'already';
                window.__novelai_search_guard = true;

                // ─── 1. Ctrl+K / Cmd+K 拦截(capture 阶段) ───
                window.addEventListener('keydown', function(e) {
                    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
                        e.preventDefault();
                        e.stopImmediatePropagation();
                        console.log('[novelai] Ctrl+K blocked');
                        return false;
                    }
                }, true);

                // ─── 2. 隐藏顶部搜索按钮 ───
                // 搜索按钮的 SVG 是放大镜:path d 以 "M11.894845 6.647401" 开头
                function hideSearchButtons() {
                    document.querySelectorAll('div[role="button"]').forEach(btn => {
                        if (btn.dataset.naiHidden === '1') return;
                        const path = btn.querySelector('svg path');
                        if (path) {
                            const d = path.getAttribute('d') || '';
                            // 放大镜 svg 的 d 起始
                            if (d.startsWith('M11.894845') || d.indexOf('M11.894845 6.647401') >= 0) {
                                btn.style.display = 'none';
                                btn.dataset.naiHidden = '1';
                                console.log('[novelai] 搜索按钮已隐藏');
                            }
                        }
                    });
                }
                hideSearchButtons();
                // 周期性扫(SPA 切页面后按钮会重生)
                setInterval(hideSearchButtons, 1500);

                // ─── 3. 搜索 modal 兜底:出现就关闭 ───
                // 简化版:不依赖 input placeholder,直接按 X 按钮 SVG 特征找
                // X 按钮 SVG path d 含 14.187(用户提供的稳定特征)
                function dismissSearchModal() {
                    // 找页面上所有可能的 X 按钮(svg path d 含 14.187)
                    const paths = document.querySelectorAll('svg path');
                    let closedCount = 0;
                    for (const p of paths) {
                        const d = p.getAttribute('d') || '';
                        if (d.indexOf('14.187') < 0) continue;
                        const btn = p.closest('[role="button"]');
                        if (!btn || btn.dataset.naiClosed === '1') continue;
                        // 检查 X 按钮是否在 modal/dialog 容器里(避免误关其他 X)
                        const modal = btn.closest('[role="dialog"]') ||
                                      btn.closest('.ds-modal-content') ||
                                      btn.closest('[class*="modal"]');
                        if (modal && modal.offsetParent !== null) {
                            btn.dataset.naiClosed = '1';  // 防同帧重复点
                            btn.click();
                            closedCount++;
                            console.log('[novelai] 搜索 modal X 按钮已点关闭');
                            // 0.5 秒后清掉标记,允许下次新 modal 再关
                            setTimeout(() => { delete btn.dataset.naiClosed; }, 500);
                        }
                    }
                    return closedCount;
                }
                // 立即扫一次 + MutationObserver 持续盯 + 每 800ms 周期扫(双保险)
                dismissSearchModal();
                setInterval(dismissSearchModal, 800);
                const obs = new MutationObserver(function() {
                    dismissSearchModal();
                });
                obs.observe(document.body, {childList: true, subtree: true});

                // 暴露给外部供 Python 主动调用
                window.__novelai_dismiss_modal = dismissSearchModal;

                return 'OK';
            """)
        except Exception:
            pass  # 注入失败不影响正常发送

    # ============ 核心:发送提示词 + 等回复 ============
    def _send_prompt(self, task):
        prompt = task["prompt"]
        task_id = task.get("task_id", "")
        target_url = task.get("url")

        # ── 智能冷却:防止发送过于频繁被限流 ──
        _min_gap = 5.0  # 最小发送间隔(秒)
        _now = time.time()
        _last = getattr(self, "_last_send_time", 0)
        _gap = _now - _last
        if _gap < _min_gap:
            _wait = _min_gap - _gap
            self.log_signal.emit(
                f"⏳ 冷却 {_wait:.1f}秒(防限流)...", "info")
            time.sleep(_wait)
        self._last_send_time = time.time()

        # v2.21.5:统一调用 _goto,由 _goto 内部判断是否需要切换
        # (旧逻辑用字符串包含判断有 bug:"https://chat.qwen.ai/" in "https://chat.qwen.ai/c/abc"
        #  在切到 Qwen 后会一直为 True,导致切回主 AI 时不切换)
        if target_url:
            from urllib.parse import urlparse
            try:
                target_host = urlparse(target_url).hostname or ""
                cur_host = urlparse(self._current_url() or "").hostname or ""
            except Exception:
                target_host = cur_host = ""
            if target_host and target_host != cur_host:
                self._goto(target_url)
                time.sleep(1.5)

        prof = _profile_for_url(self._current_url())
        self.log_signal.emit(f"使用档案:{prof['name']}", "info")

        # ★★★ RL 决策点:根据当前任务类型查 Q 表选最优参数
        #   state = (任务类型, AI 供应商, 死磕次数)
        #   action = {send_wait, stable_threshold, post_emit_wait, use_strategy_b}
        self._rl_current_action = None
        self._rl_current_state = None
        try:
            _rl_obj = getattr(self, "flow_rl", None)
            if _rl_obj is None:
                self.log_signal.emit(
                    "⚠ worker 端 self.flow_rl 为 None,RL 决策跳过", "warn")
            else:
                # 推断任务类型
                _label = task.get("label", "") or task.get("target", "")
                if "章" in _label or task.get("target") == "chapter":
                    _task_type = "chapter"
                elif "稽核" in _label or "评分" in _label or "json" in _label.lower():
                    _task_type = "json_short"
                elif task.get("target") == "golden_three":
                    _task_type = "golden_three"
                else:
                    _task_type = "other"
                # AI 供应商(从 URL 推断)
                _provider = (prof.get("name", "") or "unknown").lower().split()[0]
                # 死磕次数(主线程在 task meta 里传)
                _retry_used = task.get("retry_used", 0)
                state = (_task_type, _provider, _retry_used)
                action = _rl_obj.choose_action(state, task_label=_label)
                self._rl_current_state = state
                self._rl_current_action = action
                # 把 action 回传给主线程(供 reward 时使用)
                task["_rl_action"] = action
                self.log_signal.emit(
                    f"🤖 RL 决策 [{_task_type}/{_provider}/retry={_retry_used}] "
                    f"→ send_wait={action.get('send_wait')}s "
                    f"stable={action.get('stable_threshold')}s "
                    f"idle×{action.get('post_emit_wait')} "
                    f"stratB={action.get('use_strategy_b')}",
                    "info")
        except Exception as _e_rl_d:
            self.log_signal.emit(f"⚠ RL 决策异常(用默认):{_e_rl_d}", "warn")
            import traceback
            self.log_signal.emit(traceback.format_exc()[-500:], "warn")

        # BUG-013 + 搜索 modal 兜底:注入三重防护(Ctrl+K 拦截 + 隐藏搜索按钮 + 自动关 modal)
        # 用 idempotent 的全局 flag 防重复绑定
        self._inject_kbd_guard()

        # 发消息前再强制关一次搜索 modal(如果用户之前手动触发或 selenium 误触发还残留)
        # 反复关 3 次,每次间隔 200ms,防 modal 关闭动画期间又重生
        try:
            for _i in range(3):
                closed = self.driver.execute_script(r"""
                    if (typeof window.__novelai_dismiss_modal === 'function') {
                        return window.__novelai_dismiss_modal();
                    }
                    return 0;
                """) or 0
                if closed > 0:
                    self.log_signal.emit(
                        f"发消息前关闭了 {closed} 个搜索 modal", "info")
                    time.sleep(0.2)
                else:
                    break  # 没 modal 了,无需再扫
        except Exception:
            pass

        # ★★★ BUG-029 第二道防线:发送前确认 AI 真空闲
        #   防止上一任务的"完成判定"过早,这一轮发送进入到 AI 还在写的状态
        try:
            idle_deadline = time.time() + 10
            while time.time() < idle_deadline:
                is_idle = self.driver.execute_script(r"""
                    const ta = document.querySelector('textarea');
                    if (!ta) return true;  // 没 textarea 就跳过
                    let c = ta.parentElement;
                    for (let i = 0; i < 5 && c; i++) {
                        const stop1 = c.querySelector('div[role="button"]:has(svg rect)');
                        if (stop1 && stop1.offsetParent !== null) return false;
                        const stop2 = c.querySelector(
                            'div[role="button"][aria-label*="停止"], button[aria-label*="停止"]');
                        if (stop2 && stop2.offsetParent !== null) return false;
                        c = c.parentElement;
                    }
                    return !ta.disabled;
                """)
                if is_idle:
                    break
                self.log_signal.emit(
                    "⏳ 等待 AI 完成上一轮(stop 按钮仍可见)...", "info")
                time.sleep(0.5)
            else:
                self.log_signal.emit(
                    "⚠ 等 AI 空闲超时 10s,强制开始本次任务(可能 DeepSeek 卡住)", "warn")
        except Exception:
            pass

        # 1) 等输入框出现(最长 15s)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._stop.is_set(): return
            try:
                found = self.driver.execute_script(
                    f"return !!document.querySelector({json.dumps(prof['input'])});")
                if found:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            self.log_signal.emit("等待输入框超时,请确认网页已加载且已登录", "error")
            self.response_received.emit(task_id, "")
            return

        prev_count = self._count_responses(prof)

        # 发送前快照 textarea 附近 icon 按钮的 SVG 形状,
        # 这样 AI 写完后可以对比"按钮 SVG 是不是变回发送前的样子"判定完成
        try:
            self._btn_snapshot_before = self.driver.execute_script(r"""
                const ta = document.querySelector('textarea');
                if (!ta) return null;
                let container = ta.parentElement;
                for (let i = 0; i < 5 && container; i++) {
                    const btns = container.querySelectorAll('div[role="button"]');
                    if (btns.length > 0) {
                        // 把按钮们的 SVG path/rect d 属性拼成指纹
                        const fp = [];
                        for (const b of btns) {
                            if (b.offsetParent === null) continue;
                            const paths = b.querySelectorAll('svg path, svg rect');
                            const dlist = [];
                            for (const p of paths) {
                                dlist.push((p.getAttribute('d') || '') +
                                           '|' + (p.getAttribute('width') || ''));
                            }
                            fp.push(dlist.join(';'));
                        }
                        return fp.join('||');
                    }
                    container = container.parentElement;
                }
                return null;
            """)
        except Exception:
            self._btn_snapshot_before = None

        # 发送前清除 TamperMonkey bridge 旧数据,防止读到上一轮回复
        if prof.get("tm_bridge"):
            try:
                self.driver.execute_script(
                    "localStorage.removeItem('__novelai_reply');")
            except Exception:
                pass

        # ★★★ BUG-028 回归修复 v1.89:指纹必须在 prompt 发送前抓
        #     原代码把 prev_response_fingerprint 抓在 _dispatch_send 之后(line 9180+),
        #     此时 DeepSeek 已经在 DOM 里插了空 assistant 占位槽,
        #     _grab_last_response 抓到 "|0",后续 wait 循环里抓到的章节残留
        #     与 "|0" 永远不等 → 防串失效。
        #     修法:挪到 _inject_prompt 前抓,确保指纹是真正的上一轮回复。
        prev_response_fingerprint = ""
        try:
            _prev_text = self._grab_last_response(prof) or ""
            prev_response_fingerprint = f"{_prev_text[:100]}|{len(_prev_text)}"
        except Exception:
            pass

        # 2.0) 长文本附件模式:超过 1500 字符时转成 txt 文件上传
        # 优势：绕过审核（附件不进入文本审核）+ 避免输入框卡顿
        upload_threshold = task.get("upload_threshold", 0)  # 0 = 全部走附件,绕过审核
        use_attachment = (
            prof.get("name", "").startswith("ChatGPT")  # 仅 ChatGPT 系列支持
            and len(prompt) >= upload_threshold
            and task.get("allow_attachment", True)
        )
        
        if use_attachment:
            self.log_signal.emit(
                f"⚡ 长文本({len(prompt)}字)启用附件上传模式", "info")
            uploaded = self._upload_prompt_as_file(prof, prompt)
            if uploaded:
                # 引导语 - 用追加方式注入,不清空(避免附件丢失)
                short_guide = (
                    "请仔细阅读附件内容，按其要求生成完整结果。"
                    "直接输出，不要复述、不要省略、注意字数要求。"
                )
                # 用 execCommand insertText 直接追加,不 selectAll
                inject_ok = self.driver.execute_script(f"""
                    const sel = '#prompt-textarea, div.ProseMirror[contenteditable="true"], div[contenteditable="true"]';
                    const box = document.querySelector(sel);
                    if (!box) return 'NO_BOX';
                    box.focus();
                    // 移动光标到末尾(不用 selectAll, 避免删除附件块)
                    const range = document.createRange();
                    range.selectNodeContents(box);
                    range.collapse(false);
                    const s = window.getSelection();
                    s.removeAllRanges();
                    s.addRange(range);
                    // 直接 insertText 追加
                    document.execCommand('insertText', false, {json.dumps(short_guide)});
                    box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true, inputType:'insertText'}}));
                    box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                    return 'OK';
                """)
                self.log_signal.emit(f"引导语注入: {inject_ok}", "info")
                import time as _ti; _ti.sleep(0.5)
                self.log_signal.emit("✓ 准备发送(附件+引导语)", "info")
            else:
                self.log_signal.emit("⚠️ 附件上传失败，降级为直接发送文本", "warn")
                if not self._inject_prompt(prof["input"], prompt):
                    self.log_signal.emit("文本注入失败", "error")
                    self.response_received.emit(task_id, "")
                    return
        else:
            # 短文本：直接注入
            if not self._inject_prompt(prof["input"], prompt):
                self.log_signal.emit("文本注入失败", "error")
                self.response_received.emit(task_id, "")
                return

        # 模拟人类停顿(给 React 一点时间 setState)
        time.sleep(0.3)

        # 3) 点发送(优先 Enter,失败再点按钮 + 兜底 forced click)
        # v1.91 BUG-065:关键后处理任务(摘要/Canon抽取等)失败 → 重试 2 次 + 本地降级
        #   普通任务维持原"放弃"语义
        CRITICAL_TARGETS = {
            "chapter_summary", "canon_extract",
            "character_extract", "world_extract", "long_term_extract",
        }
        _task_target = task.get("target", "")
        _is_critical = _task_target in CRITICAL_TARGETS
        
        _send_ok = self._dispatch_send(prof["send_btn"])
        if not _send_ok and _is_critical:
            _max_retry = 2
            for _attempt in range(1, _max_retry + 1):
                self.log_signal.emit(
                    f"🔁 关键任务[{_task_target}]发送失败,重试 {_attempt}/{_max_retry} "
                    f"(按钮态预检={self._get_send_button_state().get('state')})",
                    "warn")
                time.sleep(1.5)  # 给页面状态稳定
                # 重新注入 textarea(_inject_prompt 内部会 selectAll+delete 再 insert)
                if not self._inject_prompt(prof["input"], prompt):
                    self.log_signal.emit(f"  ↳ 重试 {_attempt} 注入失败,继续", "warn")
                    continue
                time.sleep(0.4)
                # 发送前预检按钮态 — 灰就再等等
                _pre_state = self._get_send_button_state().get('state')
                if _pre_state == 'disabled':
                    self.log_signal.emit(
                        f"  ↳ 重试 {_attempt} 注入后按钮仍 disabled,再等 1s",
                        "warn")
                    time.sleep(1.0)
                elif _pre_state == 'stop':
                    self.log_signal.emit(
                        f"  ↳ 重试 {_attempt} 检测到 stop 按钮(AI 写未结束),等 3s",
                        "warn")
                    time.sleep(3.0)
                if self._dispatch_send(prof["send_btn"]):
                    self.log_signal.emit(
                        f"✓ 关键任务[{_task_target}]重试 {_attempt} 发送成功", "success")
                    _send_ok = True
                    break
            if not _send_ok:
                # 重试用尽 → 本地降级兜底,不让关键数据丢
                _degraded = self._build_degraded_content(task)
                if _degraded:
                    self.log_signal.emit(
                        f"⚠ 关键任务[{_task_target}]重试 {_max_retry} 次仍失败,"
                        f"启用本地降级({len(_degraded)} 字),避免数据丢失",
                        "warn")
                    self.response_received.emit(task_id, _degraded)
                else:
                    self.log_signal.emit(
                        f"⚠ 关键任务[{_task_target}]重试 {_max_retry} 次仍失败,"
                        f"且无降级路径,只能放弃(本次数据丢失)",
                        "error")
                    self.response_received.emit(task_id, "")
                return
        elif not _send_ok:
            # 普通任务:维持原放弃语义
            self.log_signal.emit("回车与发送按钮均失败,放弃本次任务", "error")
            self.response_received.emit(task_id, "")
            return

        self.log_signal.emit(
            f"提示词已发送 ({len(prompt)} 字符),等待 AI 回复...", "info")

        # 4) 等新回复出现(对话条数 +1 OR 抓到内容)
        # 因 DeepSeek 计数策略 prev/cur 在短回复时容易失灵,加内容兜底
        # 提速:30s deadline → 15s,轮询 0.5s → 0.2s
        # ★ 指纹防串:prev_response_fingerprint 已在 line 9102 (发送前) 捕获
        #   抓到内容时必须确认指纹变化,否则是上一轮残留 → 继续等

        time.sleep(1.5)  # 给 DOM 渲染新回复块的最短时间(原 3s)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._stop.is_set(): return
            cur_cnt = self._count_responses(prof)
            # 计数增加 OR 已经能抓到回复内容(> 30 字)就认为开始了
            if cur_cnt > prev_count:
                break
            try:
                early_text = self._grab_last_response(prof)
                if early_text and len(early_text) > 30:
                    # ★ 防串:检查是不是新回复(指纹必须变化)
                    cur_fp = f"{early_text[:100]}|{len(early_text)}"
                    if cur_fp == prev_response_fingerprint:
                        # 还是上一轮的输出,继续等
                        time.sleep(0.2)
                        continue
                    # 可能 prev_count 算错了,但实际已有新内容
                    self.log_signal.emit(
                        f"检测到回复内容(已抓 {len(early_text)} 字符),进入稳定等待",
                        "info")
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            self.log_signal.emit(
                "未检测到新回复条目,可能选择器需调整(到 SITE_PROFILES 微调)", "warn")

        # 5) 等内容稳定 N 秒 / stop 按钮消失 / 完成后按钮出现 任一条件
        # 提速:轮询间隔 0.3s(原 1s), stable_wait 内部 1.5s(原 4s), stop 按钮检测加强
        last_text = ""
        last_change = time.time()
        start = time.time()
        # 智能稳定阈值:根据内容长度分档
        # 短回复(JSON/评分/摘要 <300 字)→ 0.9s 稳定即完成(超快)
        # 中等回复(<1000 字)→ 1.5s
        # 长章节(>=1000 字)→ 用 self.stable_wait(默认 4s)防 AI 卡顿误判
        ultrafast_stable_wait = 0.9
        fast_stable_wait = 1.5
        # RL 接管"长章节稳定阈值"(>= 1000 字时用,默认 4s 防卡顿误判)
        try:
            if getattr(self, "_rl_current_action", None):
                normal_stable_wait = float(
                    self._rl_current_action.get("stable_threshold", self.stable_wait))
            else:
                normal_stable_wait = self.stable_wait
        except Exception:
            normal_stable_wait = self.stable_wait
        no_change_streak = 0  # 连续无变化的轮数
        # 0字符超时:如果90秒都是0字符,放弃等待(触发上层自动重试)
        _zero_char_start = time.time()
        _ZERO_CHAR_TIMEOUT = 90  # 秒
        # v2.22.1 BUG-082: 站点专属"完成判定下限"(给 Qwen 这类流式输出慢的站点用)
        # Qwen 思考 80s 后才开始逐字流出 JSON,字符间隔 > 0.9s 会被 polling
        # 误判"内容稳定 → 完成",抓到的只是 `[{"key":"角色.苏棠.体质` 这种半句。
        # 修法分三层(C 主防御 + A/B 兜底):
        #   C. thinking_indicator:DOM 里这个 selector 命中 → Qwen 还在思考,
        #      直接跳过完成判定。**确定性信号**,优先级最高。
        #   A. stable_wait_min:稳定等待时间下限(秒),C 失效时兜底
        #   B. min_complete_chars:最小完成字符数,A 失效时兜底
        # profile 里如果设了对应字段,任何完成路径(按钮快照恢复 / 内容稳定 /
        # RL 学习态)都要先过这三道关。
        _site_thinking_sel = str(prof.get("thinking_indicator", "") or "")
        _site_stable_min = float(prof.get("stable_wait_min", 0.0) or 0.0)
        _site_min_chars = int(prof.get("min_complete_chars", 0) or 0)
        _b082_min_chars_warned = False  # 防刷屏:同一任务内只告警一次
        _b082_thinking_warned = False  # 同上,thinking 守卫只告警一次
        # v2.22.3 BUG-084: BUG-082 守卫死循环修复
        # 实战(21:45:27→21:49:01,3 分 35 秒,200+圈紧循环):BUG-082 守卫触发后
        # Qwen 67 字思考预览顶按钮恢复 + cur 不变,polling 陷"按钮快照已恢复 → 0.8s
        # → recheck 还是 67 字 → BUG-082 拒绝 → continue → 回顶 → 按钮快照已恢复" 死循环。
        # 修法三条:1) 守卫累计 90s 超时则放弃接受当前内容 2) sleep 3s 避免紧循环
        # 3) "⏳ 按钮快照已恢复" 日志加抑制(否则 200+ 行刷屏)
        _b082_guard_first_at = None  # 守卫第一次触发的时间(None = 还没触发)
        _B082_GUARD_MAX = 90.0  # 守卫累计超时(秒),超过则放弃守卫
        _b082_guard_sleep = 3.0  # 守卫触发后 continue 前的强制 sleep
        _b082_button_resume_log_silenced = False  # "⏳ 按钮快照已恢复" 日志抑制
        _b082_guard_giveup_logged = False  # 守卫超时放弃日志只打一次
        # v2.22.3 BUG-085: Qwen 思考期 _check_timeout 误报"卡住"修复
        # polling 每圈检测 thinking 状态变化就 emit task_thinking 信号给主进程。
        # 主进程 _check_timeout 看到 thinking=True 时延期 60 秒再查,不弹窗。
        _last_thinking_emitted = None  # 上次 emit 的 thinking 状态,变化才 emit
        # 继续生成防死循环计数:连续点击但 AI 没响应 → 3 次后放弃
        cg_attempts = 0
        cg_max_attempts = 3
        while time.time() - start < self.max_wait:
            if self._stop.is_set(): return
            cur = self._grab_last_response(prof)
            # v2.22.3 BUG-085: 每圈检测 thinking 状态,变化时 emit
            # 主进程 _check_timeout 用这个判断"0 字节卡死"是不是误报
            if _site_thinking_sel:
                try:
                    _curr_thinking = self._site_is_thinking(_site_thinking_sel)
                    if _curr_thinking != _last_thinking_emitted:
                        self.task_thinking.emit(task_id, bool(_curr_thinking))
                        _last_thinking_emitted = _curr_thinking
                except Exception:
                    pass
            # ★ 防串:如果抓到的内容跟发送前指纹一致 → 这是上一轮残留,不是新回复
            #   假装 cur 为空,让循环继续等,直到 DeepSeek 真出新回复
            if cur and prev_response_fingerprint:
                cur_fp = f"{cur[:100]}|{len(cur)}"
                if cur_fp == prev_response_fingerprint:
                    cur = ""  # 阻止把上一轮的输出当成本轮的

            # ── 0字符超时检测:90秒无任何内容 → 放弃,触发上层自动重试 ──
            if cur and len(cur.strip()) > 0:
                _zero_char_start = time.time()  # 有内容了,重置计时
            elif time.time() - _zero_char_start > _ZERO_CHAR_TIMEOUT:
                self.log_signal.emit(
                    f"⚠ 连续 {_ZERO_CHAR_TIMEOUT}秒 无任何回复内容(0字符),"
                    f"放弃本次等待,触发自动重试", "warn")
                last_text = ""  # 返回空 → 触发0字节重试
                break

            # ★ 优先级最高:扫"继续生成"按钮,每轮 0.3s 都跑(不依赖 stopping/cur 状态)
            #   DeepSeek 显示"继续生成"时 stop 按钮可能还在,所以不能等 stopping=False 才检测
            try:
                # 先找到元素 + 坐标 — 失败原因 1:JS click 在 DeepSeek 上无效,要用真实鼠标
                cg_target = self.driver.execute_script(r"""
                    // 1) 严格匹配优先(性能最好)
                    const btns = document.querySelectorAll(
                        'button, div[role="button"], span[role="button"]');
                    for (const b of btns) {
                        if (b.offsetParent === null) continue;
                        const t = (b.innerText || b.textContent || '').trim();
                        if (t === '继续生成' || t === '继续' ||
                            (t.length <= 10 && t.includes('继续生成'))) {
                            const r = b.getBoundingClientRect();
                            // 标记元素 + 返回坐标
                            b.setAttribute('data-novelai-cg-target', '1');
                            return {x: r.left + r.width/2, y: r.top + r.height/2,
                                    way: 'TEXT:' + t.slice(0, 20)};
                        }
                    }
                    // 2) 兜底:span 反查祖先
                    const spans = document.querySelectorAll('span');
                    for (const s of spans) {
                        if (s.offsetParent === null) continue;
                        const txt = (s.textContent || '').trim();
                        if (txt === '继续生成') {
                            let el = s.parentElement;
                            for (let i = 0; i < 5 && el; i++) {
                                if (el.tagName === 'BUTTON' ||
                                    el.getAttribute('role') === 'button') {
                                    const r = el.getBoundingClientRect();
                                    el.setAttribute('data-novelai-cg-target', '1');
                                    return {x: r.left + r.width/2, y: r.top + r.height/2,
                                            way: 'SPAN'};
                                }
                                el = el.parentElement;
                            }
                        }
                    }
                    return null;
                """)
                if cg_target:
                    cg_attempts += 1
                    if cg_attempts > cg_max_attempts:
                        # 连续点击 3 次都没效果 → 放弃,直接走完成判定
                        self.log_signal.emit(
                            f"⚠ 「继续生成」按钮连续点击 {cg_max_attempts} 次都无效,"
                            f"放弃续写,以当前内容收尾({len(cur or '')} 字符)", "warn")
                        # ★ RL 反馈:死循环 -30 分(避免下次重复)
                        try:
                            if getattr(self, "flow_rl", None) and self._rl_current_state:
                                from flow_rl import REWARDS as _R
                                self.flow_rl.reward(
                                    self._rl_current_state, self._rl_current_action,
                                    _R["continue_gen_failed"], "继续生成连点 3 次无效")
                        except Exception:
                            pass
                        # 清除标记
                        try:
                            self.driver.execute_script(
                                "document.querySelectorAll('[data-novelai-cg-target]').forEach"
                                "(e => e.removeAttribute('data-novelai-cg-target'));")
                        except Exception:
                            pass
                        break  # 跳出循环,以当前内容完成
                    # 用 Selenium ActionChains 模拟真实鼠标点击
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        from selenium.webdriver.common.by import By
                        target_el = self.driver.find_element(
                            By.CSS_SELECTOR, '[data-novelai-cg-target="1"]')
                        ActionChains(self.driver).move_to_element(target_el).pause(0.1).click().perform()
                        self.log_signal.emit(
                            f"⚙ 检测到「继续生成」→ ActionChains 点击 (第 {cg_attempts}/{cg_max_attempts} 次,"
                            f"{cg_target.get('way','')}),重置等待...", "info")
                    except Exception as _e_ac:
                        # 退化到 JS dispatchEvent 三重(虽然可能没用,但留个保底)
                        try:
                            self.driver.execute_script(r"""
                                const el = document.querySelector('[data-novelai-cg-target="1"]');
                                if (!el) return;
                                const opts = {bubbles: true, cancelable: true, view: window};
                                el.dispatchEvent(new MouseEvent('pointerdown', opts));
                                el.dispatchEvent(new MouseEvent('mousedown', opts));
                                el.dispatchEvent(new MouseEvent('pointerup', opts));
                                el.dispatchEvent(new MouseEvent('mouseup', opts));
                                el.dispatchEvent(new MouseEvent('click', opts));
                            """)
                        except Exception:
                            pass
                        self.log_signal.emit(
                            f"⚙ ActionChains 失败 ({_e_ac}),降级 JS 点击 (第 {cg_attempts}/{cg_max_attempts} 次)",
                            "warn")
                    # 清标记
                    try:
                        self.driver.execute_script(
                            "document.querySelectorAll('[data-novelai-cg-target]').forEach"
                            "(e => e.removeAttribute('data-novelai-cg-target'));")
                    except Exception:
                        pass
                    last_change = time.time()
                    last_text = ""
                    no_change_streak = 0
                    time.sleep(2.5)  # 给 DeepSeek 更多处理时间
                    continue
                else:
                    # 这轮没看到"继续生成"按钮 → 重置 attempts(AI 可能恢复正常生成了)
                    cg_attempts = 0
            except Exception as _e_cg:
                pass

            # 完成信号 1: 按钮快照恢复(AI 写完后,textarea 旁边按钮 SVG 变回发送前的样子)
            # 这是最稳的完成信号:不依赖任何 class/aria-label,只看按钮 SVG 形状指纹
            # AI 在写时,纸飞机(发送)→ 方块(停止),所以指纹会变;
            # 写完后停止按钮消失/变回纸飞机 → 指纹恢复成发送前的样子
            stopping = False
            try:
                cur_snapshot = self.driver.execute_script(r"""
                    const ta = document.querySelector('textarea');
                    if (!ta) return null;
                    let container = ta.parentElement;
                    for (let i = 0; i < 5 && container; i++) {
                        const btns = container.querySelectorAll('div[role="button"]');
                        if (btns.length > 0) {
                            const fp = [];
                            for (const b of btns) {
                                if (b.offsetParent === null) continue;
                                const paths = b.querySelectorAll('svg path, svg rect');
                                const dlist = [];
                                for (const p of paths) {
                                    dlist.push((p.getAttribute('d') || '') +
                                               '|' + (p.getAttribute('width') || ''));
                                }
                                fp.push(dlist.join(';'));
                            }
                            return fp.join('||');
                        }
                        container = container.parentElement;
                    }
                    return null;
                """)
                # 快照变化中 → 还在写;快照跟"发送前"一致 → 写完了
                snap_before = getattr(self, "_btn_snapshot_before", None)
                if snap_before and cur_snapshot is not None:
                    # 快照不一致 = 现在有"停止按钮"在 → AI 还在写
                    # 快照一致 = 按钮 SVG 变回发送前样子 → AI 写完了
                    if cur_snapshot != snap_before:
                        stopping = True
                else:
                    # 快照不可用,退化到原 selector 检测
                    stopping = self.driver.execute_script(r"""
                        let s = document.querySelector('div[role="button"][aria-label*="停止"]') ||
                                document.querySelector('button[aria-label*="停止"]') ||
                                document.querySelector('button[aria-label*="Stop" i]') ||
                                document.querySelector('button[data-testid*="stop"]');
                        if (s && s.offsetParent !== null) return true;
                        const ta = document.querySelector('textarea');
                        if (ta) {
                            let c = ta.parentElement;
                            for (let i = 0; i < 5 && c; i++) {
                                const b = c.querySelectorAll('div[role="button"]:has(svg rect)');
                                for (const x of b) if (x.offsetParent !== null) return true;
                                c = c.parentElement;
                            }
                        }
                        return false;
                    """) or False
            except Exception:
                pass

            # stop 不可见(按钮恢复) + 抓到内容 + 内容跟上次相同 → 判定可能完成
            # ★★ 但要 0.8s 保险确认按钮快照没"延迟恢复"
            if not stopping and cur and len(cur) > 30 and cur == last_text:
                # ★★ 保险减速:写完后再等 0.8s,确认按钮快照没"延迟恢复"
                # v2.22.3 BUG-084: 日志抑制 — 死循环时这条会刷 200+ 次
                if not _b082_button_resume_log_silenced:
                    self.log_signal.emit(
                        f"⏳ 按钮快照已恢复(可能写完),0.8s 保险确认...", "info")
                time.sleep(0.8)
                recheck = self._grab_last_response(prof)
                if recheck and recheck != cur:
                    # 还在写 → 内容继续增加,接着循环
                    self.log_signal.emit(
                        f"  (假警:0.8s 后内容从 {len(cur)} 涨到 {len(recheck)} 字符,接着等)",
                        "info")
                    last_text = recheck
                    last_change = time.time()
                    # v2.22.3 BUG-084: 字符真涨 → 重置守卫计时 + 解除日志抑制
                    _b082_guard_first_at = None
                    _b082_button_resume_log_silenced = False
                    continue
                # v2.22.1 BUG-082 (C 主防御): 站点说"还在思考" → 不结束
                if _site_thinking_sel and self._site_is_thinking(_site_thinking_sel):
                    if not _b082_thinking_warned:
                        self.log_signal.emit(
                            f"  · [BUG-082] 按钮恢复但 Qwen 还显示\"思考中\"动画 → "
                            f"继续等真正完成...",
                            "info")
                        _b082_thinking_warned = True
                    # v2.22.3 BUG-084: 守卫累计超时检查
                    if _b082_guard_first_at is None:
                        _b082_guard_first_at = time.time()
                    elif time.time() - _b082_guard_first_at > _B082_GUARD_MAX:
                        if not _b082_guard_giveup_logged:
                            self.log_signal.emit(
                                f"  · [BUG-084] BUG-082 守卫累计 {_B082_GUARD_MAX:.0f}s "
                                f"仍在拒绝完成 → 放弃守卫接受当前 {len(cur)} 字",
                                "warn")
                            _b082_guard_giveup_logged = True
                        break
                    last_text = cur
                    last_change = time.time()
                    _b082_button_resume_log_silenced = True
                    time.sleep(_b082_guard_sleep)
                    continue
                # v2.22.1 BUG-082 (B 兜底): 按钮虽恢复但字符数不够站点下限
                if _site_min_chars and len(cur) < _site_min_chars:
                    if not _b082_min_chars_warned:
                        self.log_signal.emit(
                            f"  · [BUG-082] 按钮恢复但 {len(cur)} 字 < 站点下限"
                            f" {_site_min_chars} → 继续等 Qwen 流式输出...",
                            "info")
                        _b082_min_chars_warned = True
                    # v2.22.3 BUG-084: 守卫累计超时检查
                    if _b082_guard_first_at is None:
                        _b082_guard_first_at = time.time()
                    elif time.time() - _b082_guard_first_at > _B082_GUARD_MAX:
                        if not _b082_guard_giveup_logged:
                            self.log_signal.emit(
                                f"  · [BUG-084] BUG-082 守卫累计 {_B082_GUARD_MAX:.0f}s "
                                f"仍在拒绝完成 → 放弃守卫接受当前 {len(cur)} 字",
                                "warn")
                            _b082_guard_giveup_logged = True
                        break
                    last_text = cur
                    last_change = time.time()
                    _b082_button_resume_log_silenced = True
                    time.sleep(_b082_guard_sleep)
                    continue
                self.log_signal.emit(
                    f"✓ 按钮快照已恢复(AI 写完)+ 内容稳定 → 完成 ({len(cur)} 字符)", "info")
                break

            if cur and cur == last_text:
                no_change_streak += 1
                # 智能三档稳定阈值:
                #   <300 字 (JSON/评分/摘要) → 0.9s 即可
                #   <1000 字 → 1.5s
                #   >=1000 字 (长章节) → self.stable_wait (默认 4s,防 AI 卡顿误判)
                clen = len(cur)
                if clen < 300:
                    wait_threshold = ultrafast_stable_wait
                elif clen < 1000:
                    wait_threshold = fast_stable_wait
                else:
                    wait_threshold = normal_stable_wait
                # v2.22.1 BUG-082: 站点级稳定等待下限(Qwen 8s,DeepSeek 不设)
                if _site_stable_min:
                    wait_threshold = max(wait_threshold, _site_stable_min)
                if time.time() - last_change >= wait_threshold:
                    # v2.22.1 BUG-082 (C 主防御): 站点说"还在思考" → 不结束
                    if _site_thinking_sel and self._site_is_thinking(_site_thinking_sel):
                        if not _b082_thinking_warned:
                            self.log_signal.emit(
                                f"  · [BUG-082] 内容稳定 {wait_threshold:.1f}s 但 "
                                f"Qwen 还显示\"思考中\"动画 → 继续等真正完成...",
                                "info")
                            _b082_thinking_warned = True
                        # v2.22.3 BUG-084: 守卫累计超时检查
                        if _b082_guard_first_at is None:
                            _b082_guard_first_at = time.time()
                        elif time.time() - _b082_guard_first_at > _B082_GUARD_MAX:
                            if not _b082_guard_giveup_logged:
                                self.log_signal.emit(
                                    f"  · [BUG-084] BUG-082 守卫累计 {_B082_GUARD_MAX:.0f}s "
                                    f"仍在拒绝完成 → 放弃守卫接受当前 {clen} 字",
                                    "warn")
                                _b082_guard_giveup_logged = True
                            break
                    # v2.22.1 BUG-082 (B 兜底): 字符数不够站点下限
                    elif _site_min_chars and clen < _site_min_chars:
                        if not _b082_min_chars_warned:
                            self.log_signal.emit(
                                f"  · [BUG-082] 内容稳定 {wait_threshold:.1f}s 但 "
                                f"{clen} 字 < 站点下限 {_site_min_chars} → "
                                f"继续等(Qwen 等结构化输出补齐)...",
                                "info")
                            _b082_min_chars_warned = True
                        # v2.22.3 BUG-084: 守卫累计超时检查
                        if _b082_guard_first_at is None:
                            _b082_guard_first_at = time.time()
                        elif time.time() - _b082_guard_first_at > _B082_GUARD_MAX:
                            if not _b082_guard_giveup_logged:
                                self.log_signal.emit(
                                    f"  · [BUG-084] BUG-082 守卫累计 {_B082_GUARD_MAX:.0f}s "
                                    f"仍在拒绝完成 → 放弃守卫接受当前 {clen} 字",
                                    "warn")
                                _b082_guard_giveup_logged = True
                            break
                    else:
                        self.log_signal.emit(
                            f"✓ 内容稳定 {wait_threshold:.1f}s → 完成 ({clen} 字符)", "info")
                        break
            else:
                last_text = cur
                last_change = time.time()
                no_change_streak = 0
                # v2.22.3 BUG-084: 字符真涨 → 重置守卫计时 + 解除日志抑制
                _b082_guard_first_at = None
                _b082_button_resume_log_silenced = False
                # v2.22.2 BUG-083: 内容刚变化 → 立刻通知主进程"这个任务在写字"
                try:
                    self.task_progress.emit(task_id, len(cur or ""))
                except Exception:
                    pass
            elapsed = int(time.time() - start)
            if elapsed and elapsed % 5 == 0 and no_change_streak == 0:
                self.log_signal.emit(
                    f"AI 生成中...已 {elapsed}s,当前 {len(cur or '')} 字符", "info")
                # v2.22.2 BUG-083: 每 5 秒也同步一次进度(防内容稳定时主进程
                # 拿不到最新字符数)
                try:
                    self.task_progress.emit(task_id, len(cur or ""))
                except Exception:
                    pass
            time.sleep(0.3)  # 提速:1s → 0.3s,响应快 3 倍

        if last_text:
            self.log_signal.emit(f"回复完成,共 {len(last_text)} 字符", "success")
        else:
            self.log_signal.emit(
                "回复抓取为空,可能选择器需调整(到 SITE_PROFILES 微调)", "warn")

        # ★★★ BUG-029 关键修复:emit 前必须等 AI 真正空闲
        #   用户原话"上一个任务还没结束,下一个任务就已经开始了"
        #   完成判定可能过早,emit 后主线程立即发下一个任务,
        #   导致 textarea 注入到 DeepSeek 还没回复完的状态 → 抓串
        try:
            stable_idle_start = time.time()
            consec_idle = 0
            while time.time() - stable_idle_start < 5.0:
                # 检测两个信号都满足才算真空闲:
                # 1. 没有 stop 按钮 (AI 不在写)
                # 2. textarea 可输入 (没被禁用)
                is_idle = self.driver.execute_script(r"""
                    // 1) 没 stop 按钮
                    const ta = document.querySelector('textarea');
                    if (!ta) return false;
                    let c = ta.parentElement;
                    for (let i = 0; i < 5 && c; i++) {
                        const stop1 = c.querySelector('div[role="button"]:has(svg rect)');
                        if (stop1 && stop1.offsetParent !== null) return false;
                        const stop2 = c.querySelector(
                            'div[role="button"][aria-label*="停止"], button[aria-label*="停止"]');
                        if (stop2 && stop2.offsetParent !== null) return false;
                        c = c.parentElement;
                    }
                    // 2) textarea 可用
                    if (ta.disabled) return false;
                    return true;
                """)
                if is_idle:
                    consec_idle += 1
                    # 用 RL 推荐的连续次数(默认 3,= 0.6s)
                    _rl_post_wait = 3
                    try:
                        if getattr(self, "_rl_current_action", None):
                            _rl_post_wait = int(
                                self._rl_current_action.get("post_emit_wait", 3))
                    except Exception:
                        pass
                    if consec_idle >= _rl_post_wait:
                        break
                else:
                    consec_idle = 0
                time.sleep(0.2)
            else:
                # 5s 都没等到,记日志但还是继续(防卡死)
                self.log_signal.emit(
                    "⚠ AI 空闲确认超时(5s),继续下一任务(可能 DeepSeek 卡住)", "warn")
        except Exception as _e_idle:
            self.log_signal.emit(f"AI 空闲检测异常:{_e_idle}", "warn")

        # v2.22.3 BUG-085: polling 退出前 emit thinking=False
        # 避免任务真完成后,主进程 _check_timeout 还误以为在思考期
        try:
            if _last_thinking_emitted is True:
                self.task_thinking.emit(task_id, False)
        except Exception:
            pass

        self.response_received.emit(task_id, last_text)

    # ---------- 附件上传：把长文本 prompt 转 txt 上传 ----------
    def _clear_existing_attachments(self):
        """清空 composer 输入区的待发送附件
        实测镜像站删除按钮 aria-label='移除文件1：xxx.txt'
        """
        try:
            # 多轮清除（点一个删除按钮后 React 重渲染，需要再扫一遍）
            for round_idx in range(5):
                removed = self.driver.execute_script(r"""
                    let count = 0;
                    
                    // 找页面上所有按钮（不限定在 composer 内，因为附件有时挂在 composer 外）
                    const btns = document.querySelectorAll('button');
                    btns.forEach(btn => {
                        const aria = btn.getAttribute('aria-label') || '';
                        
                        // 排除发送/侧边栏等无关按钮
                        if (aria.includes('发送') || aria.includes('Send') ||
                            aria.includes('边栏') || aria.includes('sidebar') ||
                            aria.includes('Stop') || aria.includes('停止')) {
                            return;
                        }
                        
                        // 精确匹配镜像站附件删除按钮
                        // 实测格式: "移除文件1：xxx.txt"  或  "Remove file 1: xxx.txt"
                        const isAttClose = (
                            aria.match(/移除文件\s*\d*[：:]/) ||
                            aria.match(/^移除[\s文件]*\d*$/) ||
                            aria.match(/Remove\s+file\s*\d*[：:]/i) ||
                            aria.match(/^Remove\s+attachment/i) ||
                            aria.match(/^Delete\s+file/i)
                        );
                        
                        if (isAttClose) {
                            try { btn.click(); count++; } catch(e) {}
                        }
                    });
                    
                    return count;
                """) or 0
                
                if removed == 0:
                    if round_idx == 0:
                        # 首轮就没找到删除按钮,正常情况(无附件)
                        print(f"[_clear_attachments] 首轮无删除按钮(无残留附件),正常", flush=True)
                    break
                
                self.log_signal.emit(f"✓ 第{round_idx+1}轮清除 {removed} 个残留附件", "info")
                print(f"[_clear_attachments] 第{round_idx+1}轮: 移除 {removed} 个", flush=True)
                import time as _t; _t.sleep(0.5)  # 等 React 重渲染
            
            # 重置所有 file input 的 value
            self.driver.execute_script("""
                document.querySelectorAll('input[type="file"]').forEach(el => {
                    try { el.value = ''; } catch(e) {}
                });
            """)
        except Exception as e:
            self.log_signal.emit(f"清除附件异常: {e}", "warn")

    def _upload_prompt_as_file(self, prof, text):
        """
        把 prompt 写成临时 txt 文件，通过 ChatGPT 的文件上传 input 注入。
        ChatGPT 系列(包括镜像站)有隐藏的 <input type="file" />，
        Selenium 直接 send_keys(filepath) 即可上传，无需点开文件选择对话框。
        """
        import os, tempfile, time as _t, glob
        # 0) 先清除已存在的附件，避免堆积
        self._clear_existing_attachments()
        # 0.5) 删除磁盘上残留的旧临时文件(保留最近 3 个,以防发送中)
        try:
            tmp_dir = tempfile.gettempdir()
            old_files = sorted(
                glob.glob(os.path.join(tmp_dir, "novel_ai_prompt_*.txt")),
                key=os.path.getmtime
            )
            # 保留最近 3 个,删掉更老的
            for old_f in old_files[:-3]:
                try:
                    os.remove(old_f)
                except Exception:
                    pass
            if len(old_files) > 3:
                self.log_signal.emit(f"已清理 {len(old_files)-3} 个旧临时文件", "info")
        except Exception:
            pass
        # 1) 写临时文件
        try:
            tmp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(tmp_dir, f"novel_ai_prompt_{int(_t.time())}.txt")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            # 记录到实例,方便后续清理
            if not hasattr(self, "_temp_files"):
                self._temp_files = []
            self._temp_files.append(tmp_path)
            # 实例只保留最近 3 个引用
            if len(self._temp_files) > 3:
                old_path = self._temp_files.pop(0)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
            self.log_signal.emit(f"已创建临时附件: {os.path.basename(tmp_path)} ({len(text)}字)", "info")
        except Exception as e:
            self.log_signal.emit(f"写入临时文件失败: {e}", "error")
            return False

        # 2) 找到隐藏的 <input type="file"> 元素
        # ChatGPT/镜像站通常有这个隐藏控件用于文件上传
        try:
            # 等待 input[type=file] 出现（页面可能延迟渲染）
            file_input = None
            for _ in range(10):
                file_inputs = self.driver.execute_script("""
                    return Array.from(document.querySelectorAll('input[type="file"]'))
                        .map(el => ({
                            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                            accept: el.accept || '',
                            multiple: el.multiple
                        }));
                """)
                if file_inputs:
                    self.log_signal.emit(
                        f"找到 {len(file_inputs)} 个 input[type=file]", "info")
                    break
                _t.sleep(0.3)
            else:
                self.log_signal.emit("页面未找到 input[type=file]，无法上传附件", "warn")
                return False

            # 3) 用 Selenium 的 send_keys 注入文件路径
            from selenium.webdriver.common.by import By
            inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if not inputs:
                return False

            # 强制让 input 可见（Selenium 不能给隐藏元素 send_keys）
            self.driver.execute_script("""
                document.querySelectorAll('input[type="file"]').forEach(el => {
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.opacity = '1';
                    el.style.position = 'fixed';
                    el.style.left = '0';
                    el.style.top = '0';
                    el.style.width = '1px';
                    el.style.height = '1px';
                    el.removeAttribute('hidden');
                });
            """)
            _t.sleep(0.3)

            # 关键: send_keys 前先重置 input 的 value,避免追加上次的文件
            self.driver.execute_script("""
                document.querySelectorAll('input[type="file"]').forEach(el => {
                    try { el.value = ''; } catch(e) {}
                });
            """)
            _t.sleep(0.2)
            
            # 选第一个 input（通常就是聊天框的附件上传）
            inputs[0].send_keys(tmp_path)
            self.log_signal.emit("文件路径已 send_keys 到 input", "info")

            # 4) 等待上传完成 - 多策略检测
            fname = os.path.basename(tmp_path)
            uploaded = False
            for i in range(40):  # 最多等20秒
                state = self.driver.execute_script(f"""
                    const fname = {json.dumps(fname)};
                    // 检查方式1: 整个页面文字含文件名
                    const hasName = document.body.innerText.includes(fname);
                    // 检查方式2: 有 attachment 类名元素出现
                    const attEls = document.querySelectorAll(
                        '[class*="attachment" i], [class*="file-preview" i], ' +
                        '[class*="file-card" i], [data-testid*="attachment" i], ' +
                        '[class*="composer-file" i], [aria-label*="附件" i]'
                    );
                    // 检查方式3: input 框附近有 .txt 字样
                    const composer = document.querySelector('form, [class*="composer" i]');
                    const composerText = composer ? composer.innerText : '';
                    const hasTxt = composerText.includes('.txt');
                    return {{ hasName, attCount: attEls.length, hasTxt }};
                """) or {{}}
                # 任何一种检测到就认为上传完成
                if state.get('hasName') or state.get('attCount', 0) > 0 or state.get('hasTxt'):
                    self.log_signal.emit(
                        f"✓ 附件已就位 ({(i+1)*0.5}s) [name={state.get('hasName')} att={state.get('attCount')} txt={state.get('hasTxt')}]",
                        "info")
                    _t.sleep(2.5)  # 让后端完整接收附件
                    uploaded = True
                    break
                _t.sleep(0.5)

            if not uploaded:
                self.log_signal.emit("⚠ 等待附件上传超时(20s)", "warn")
                # 即使没检测到也试试,可能是镜像站DOM结构特殊
                _t.sleep(1.5)
                return True

            # ★ v1.32 dev: 发送前最后一道防线 — 验证附件 chip 真在 composer 里 ★
            # 镜像站审核管道可能延迟,附件"上传完成"≠服务端"接受完成"
            # 通过检测 composer 区域内可见的删除按钮数(应该 >= 1 且 = 1)来验证
            _t.sleep(1.5)   # 多等 1.5s 让镜像站审核流程跑完
            try:
                chip_state = self.driver.execute_script(r"""
                    const fname = arguments[0];
                    const composer = document.querySelector('form, [class*="composer" i]');
                    if (!composer) return {chips: 0, hasFile: false};
                    // 数 composer 里可见的"移除文件"按钮
                    const removeBtns = composer.querySelectorAll('button[aria-label*="移除文件"], button[aria-label*="Remove file"]');
                    const visibleChips = Array.from(removeBtns).filter(b => {
                        const r = b.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    // 找文件名是否在 composer 文本里
                    const hasFile = composer.innerText.includes(fname);
                    return {chips: visibleChips.length, hasFile, names: visibleChips.map(b => b.getAttribute('aria-label'))};
                """, fname) or {}
                chip_n = chip_state.get('chips', 0)
                has_file = chip_state.get('hasFile', False)
                names = chip_state.get('names', [])
                print(f"[upload chip 验证] chips={chip_n} hasFile={has_file} names={names}", flush=True)
                if chip_n == 0 or not has_file:
                    self.log_signal.emit(
                        f"⚠ 附件 chip 验证失败(chips={chip_n}/has_file={has_file}),"
                        f"镜像站可能正在审核,再等 3s",
                        "warn")
                    _t.sleep(3)
                    # 再验一次
                    chip_n2 = self.driver.execute_script("""
                        const composer = document.querySelector('form, [class*="composer" i]');
                        if (!composer) return 0;
                        return composer.querySelectorAll('button[aria-label*="移除文件"], button[aria-label*="Remove file"]').length;
                    """) or 0
                    if chip_n2 == 0:
                        self.log_signal.emit(
                            "⚠ 附件 chip 仍未出现,镜像站审核可能拒绝了附件,后续若发送失败请重启浏览器",
                            "warn")
                elif chip_n > 1:
                    # 残留多个附件 — 严重 BUG-B 场景
                    self.log_signal.emit(
                        f"⚠ composer 检测到 {chip_n} 个附件 chip,有残留!尝试清理多余...",
                        "warn")
                    print(f"[upload chip 验证] 异常多 chip: {names}", flush=True)
                    # 多余的从后往前删(保留第一个 = 当前任务的)
                    self.driver.execute_script(r"""
                        const composer = document.querySelector('form, [class*="composer" i]');
                        if (!composer) return;
                        const btns = Array.from(composer.querySelectorAll('button[aria-label*="移除文件"], button[aria-label*="Remove file"]'));
                        // 保留第一个,删除剩下的
                        for (let i = 1; i < btns.length; i++) {
                            try { btns[i].click(); } catch(e) {}
                        }
                    """)
                    _t.sleep(1)
                else:
                    self.log_signal.emit(
                        f"✓ 附件 chip 验证通过(1 个 chip 已挂载)",
                        "info")
            except Exception as _ce:
                print(f"[upload chip 验证] 异常: {_ce}", flush=True)

            return True

        except Exception as e:
            self.log_signal.emit(f"附件上传异常: {e}", "warn")
            return False

    # ---------- 文本注入(借鉴 GPTWebController 的 execCommand 路径)----------
    def _inject_prompt(self, input_selector, text):
        """
        注入策略(按优先级依次尝试,成功即返回 True):
          A0. Clipboard API  ── 写 text 到剪贴板 → Ctrl+V(对镜像站/ProseMirror 最稳)
          A1. CDP Input.insertText ── focus+清空后用 DevTools Protocol 打字
          B.  React native setter ── textarea/input 的 value setter + input event
          C.  execCommand ── 通用兜底,React 可能不响应但总有机会触发
        """
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        import time as _t_inj

        # 长文本注入需要更长的脚本超时
        try:
            self.driver.set_script_timeout(90)
        except Exception:
            pass

        sel = json.dumps(input_selector)
        text_js = json.dumps(text)

        # ── 0. textarea 专属注入(DeepSeek 等用 textarea, 不是 contenteditable)
        # React 把 value 控制锁住, 直接 .value=... 不触发 setState
        # 必须用 React 的内部 setter 才能让 state 更新
        try:
            # ★ DeepSeek 深度思考模式:发送前检查并启用 R1 按钮
            #   (这里没 prof 参数,通过当前 URL 重算)
            try:
                _cur_prof = _profile_for_url(self._current_url())
            except Exception:
                _cur_prof = {"name": ""}
            if (_cur_prof.get("name", "").lower().startswith("deepseek")
                    and getattr(self, "_deep_think_enabled", False)):
                try:
                    dt_state = self.driver.execute_script(r"""
                        // DeepSeek "深度思考" 按钮特征: 含 "深度思考" 文本
                        const all = document.querySelectorAll(
                            'div[role="button"], button, span[role="button"]');
                        for (const b of all) {
                            if (b.offsetParent === null) continue;
                            const t = (b.innerText || b.textContent || '').trim();
                            if (t === '深度思考' || t === '深度思考 (R1)' ||
                                t.startsWith('深度思考')) {
                                // 检查是否已激活 (含 aria-pressed 或样式高亮)
                                const pressed = b.getAttribute('aria-pressed');
                                const cls = b.className || '';
                                // 启用条件:背景色变化 或 aria-pressed=true
                                const isActive = (pressed === 'true') ||
                                    cls.includes('active') ||
                                    cls.includes('selected') ||
                                    cls.includes('checked');
                                if (!isActive) {
                                    b.click();
                                    return 'ACTIVATED';
                                }
                                return 'ALREADY_ON';
                            }
                        }
                        return 'NOT_FOUND';
                    """)
                    if dt_state == 'ACTIVATED':
                        self.log_signal.emit("🧠 已启用 DeepSeek 深度思考(R1)", "info")
                        _t_inj.sleep(0.5)
                    elif dt_state == 'NOT_FOUND':
                        self.log_signal.emit(
                            "🧠 深度思考按钮没找到(DeepSeek UI 可能改了),跳过", "warn")
                except Exception as _e_dt:
                    self.log_signal.emit(f"深度思考检测异常(忽略):{_e_dt}", "warn")

            result = self.driver.execute_script(f"""
                const ta = document.querySelector('textarea');
                if (!ta) return 'NO_TA';
                ta.focus();
                // 用 React 内部 setter 设 value (绕过 React 的 controlled lock)
                const proto = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value');
                if (proto && proto.set) {{
                    proto.set.call(ta, {text_js});
                }} else {{
                    ta.value = {text_js};
                }}
                // 触发 React 合成事件
                ta.dispatchEvent(new Event('input',  {{bubbles:true}}));
                ta.dispatchEvent(new Event('change', {{bubbles:true}}));
                return (ta.value && ta.value.length > 10) ? 'OK_TA' : 'EMPTY_TA';
            """)
            self.log_signal.emit(f"textarea 注入: {result}", "info")
            if result == 'OK_TA':
                _t_inj.sleep(0.3)
                # 等发送按钮 enabled
                return True
        except Exception as _e:
            self.log_signal.emit(f"textarea 注入异常(降级):{_e}", "warn")

        # ── 快速路径: ProseMirror / #prompt-textarea
        # 实测最有效: focus → selectAll → delete → execCommand insertText → 触发 React 事件
        # 优先用 #prompt-textarea，不依赖可能含特殊字符的多选择器字符串
        _pm_sel = json.dumps('#prompt-textarea, div.ProseMirror[contenteditable="true"], div[contenteditable="true"]')
        try:
            result = self.driver.execute_script(f"""
                const box = document.querySelector({_pm_sel});
                if (!box || !box.isContentEditable) return 'SKIP';
                box.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                const ok = document.execCommand('insertText', false, {text_js});
                // 触发 React 合成事件让发送按钮解锁
                box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true, inputType:'insertText'}}));
                box.dispatchEvent(new Event('change', {{bubbles:true}}));
                box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                const content = (box.innerText || box.textContent || '').trim();
                return content ? 'OK' : 'EMPTY';
            """)
            self.log_signal.emit(f"注入结果: {result}", "info")
            if result == 'OK':
                # 等待发送按钮出现（输入框为空时按钮不在DOM，有内容后才渲染）
                _btn_sel = json.dumps(
                    'button.composer-submit-btn, [data-testid="send-button"], '
                    'button[aria-label*="Send" i], button[aria-label*="发送"]'
                )
                for _wi in range(20):
                    _btn_ok = self.driver.execute_script(f"""
                        return !!document.querySelector({_btn_sel});
                    """)
                    if _btn_ok:
                        break
                    _t_inj.sleep(0.15)
                else:
                    self.log_signal.emit("⚠️ 注入成功但发送按钮未出现，仍尝试发送", "warn")
                _t_inj.sleep(0.2)
                self.log_signal.emit("✓ insertText 注入成功，发送按钮已就绪", "info")
                return True
            elif result in ('EMPTY', 'SKIP'):
                self.log_signal.emit(f"insertText 结果={result}，尝试 CDP 注入", "warn")
                # CDP Input.insertText — Selenium attach模式下最可靠
                try:
                    self.driver.execute_script(f"""
                        const box = document.querySelector({_pm_sel});
                        if (box) {{ box.focus(); document.execCommand('selectAll'); document.execCommand('delete'); }}
                    """)
                    _t_inj.sleep(0.1)
                    self.driver.execute_cdp_cmd('Input.insertText', {'text': text})
                    _t_inj.sleep(0.3)
                    # 触发 React 事件
                    cdp_ok = self.driver.execute_script(f"""
                        const box = document.querySelector({_pm_sel});
                        if (!box) return false;
                        box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true}}));
                        box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                        return (box.innerText || box.textContent || '').trim().length > 0;
                    """)
                    if cdp_ok:
                        self.log_signal.emit("✓ CDP insertText 注入成功", "info")
                        # 等发送按钮出现
                        _btn_sel2 = json.dumps('button.composer-submit-btn, [data-testid="send-button"]')
                        for _wi2 in range(20):
                            if self.driver.execute_script(f"return !!document.querySelector({_btn_sel2});"):
                                break
                            _t_inj.sleep(0.15)
                        _t_inj.sleep(0.2)
                        return True
                    self.log_signal.emit("CDP 注入后内容仍为空", "warn")
                except Exception as _cdp_e:
                    self.log_signal.emit(f"CDP 注入失败: {_cdp_e}", "warn")
        except Exception as e:
            self.log_signal.emit(f"快速注入异常: {e}，降级处理", "warn")

        # 判断元素类型
        try:
            tag_info = self.driver.execute_script(f"""
                const box = document.querySelector({sel});
                if (!box) return null;
                return {{
                    tag: (box.tagName || '').toUpperCase(),
                    ce:  box.isContentEditable,
                    pm:  box.classList.contains('ProseMirror') || box.id === 'prompt-textarea',
                    vis: !!(box.offsetWidth || box.offsetHeight)
                }};
            """)
        except Exception:
            tag_info = None

        if tag_info is None:
            self.log_signal.emit("找不到输入框元素", "warn")
            return False

        is_pm  = tag_info.get("pm", False)
        is_ce  = tag_info.get("ce", False)
        tag    = tag_info.get("tag", "")
        is_div = (tag == "DIV") or is_pm or is_ce

        # ── A0. Clipboard API + Ctrl+V (最可靠,对所有 React contenteditable 站点)
        if is_div:
            try:
                # 1) 把文本写进剪贴板(navigator.clipboard 需要 https,所以用 execCommand copy)
                copy_ok = self.driver.execute_script(f"""
                    const ta = document.createElement('textarea');
                    ta.value = {text_js};
                    ta.style.position = 'fixed';
                    ta.style.opacity  = '0';
                    document.body.appendChild(ta);
                    ta.focus(); ta.select();
                    const ok = document.execCommand('copy');
                    document.body.removeChild(ta);
                    return ok;
                """)
                if copy_ok:
                    # 2) focus 编辑器 + 全选删除旧内容
                    self.driver.execute_script(f"""
                        const box = document.querySelector({sel});
                        box.focus();
                        const s = window.getSelection();
                        s.selectAllChildren(box);
                        s.deleteFromDocument();
                        box.focus();
                    """)
                    import time as _t; _t.sleep(0.1)
                    # 3) Ctrl+V 粘贴
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    import time as _t2; _t2.sleep(0.3)
                    # 4) 验证
                    injected = self.driver.execute_script(f"""
                        const box = document.querySelector({sel});
                        return !!(box && (box.innerText || box.textContent || '').trim());
                    """)
                    if injected:
                        # 补触发 React 合成事件，让发送按钮从 disabled 变可用
                        self.driver.execute_script(f"""
                            const box = document.querySelector({sel});
                            if (!box) return;
                            // 触发 React 可识别的 input 事件
                            box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true}}));
                            box.dispatchEvent(new Event('change', {{bubbles:true}}));
                            // ChatGPT/镜像站专用：触发 compositionend 解锁发送按钮
                            box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                        """)
                        import time as _tw; _tw.sleep(0.2)
                        self.log_signal.emit("✓ 剪贴板+Ctrl+V 注入成功", "info")
                        return True
                    self.log_signal.emit("剪贴板注入后内容为空,尝试CDP", "warn")
            except Exception as e:
                self.log_signal.emit(f"剪贴板注入异常:{e},尝试CDP", "warn")

        # ── A1. ProseMirror —— JS清空 + CDP Input.insertText
        if is_div:
            try:
                import time as _time
                # 1. 用JS清空编辑器(不用Ctrl+A避免触发浏览器快捷键)
                self.driver.execute_script(f"""
                    const box = document.querySelector({sel});
                    if (!box) return;
                    box.focus();
                    // 清空ProseMirror内容
                    const sel2 = window.getSelection();
                    sel2.selectAllChildren(box);
                    sel2.deleteFromDocument();
                    // 确保光标在编辑器内
                    box.focus();
                """)
                _time.sleep(0.15)
                # 2. CDP Input.insertText 直接注入文本
                self.driver.execute_cdp_cmd('Input.insertText', {'text': text})
                _time.sleep(0.3)
                # 3. 验证注入是否成功
                injected = self.driver.execute_script(f"""
                    const box = document.querySelector({sel});
                    return !!(box && (box.innerText || box.textContent || '').trim());
                """)
                if injected:
                    # 补触发 React 合成事件
                    self.driver.execute_script(f"""
                        const box = document.querySelector({sel});
                        if (!box) return;
                        box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true}}));
                        box.dispatchEvent(new Event('change', {{bubbles:true}}));
                        box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                    """)
                    import time as _tw2; _tw2.sleep(0.2)
                    return True
                self.log_signal.emit("CDP注入后内容为空，尝试JS兜底", "warn")
            except Exception as e:
                self.log_signal.emit(f"CDP注入失败:{e}，尝试JS兜底", "warn")
        # B. textarea/input —— React native setter
        if tag in ("TEXTAREA", "INPUT"):
            try:
                js = f"""
                const box = document.querySelector({sel});
                box.focus();
                const proto = ('{tag}' === 'TEXTAREA')
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(box, {text_js});
                box.dispatchEvent(new Event('input', {{bubbles:true}}));
                box.dispatchEvent(new Event('change', {{bubbles:true}}));
                return 'OK_TEXTAREA';
                """
                r = self.driver.execute_script(js)
                if r == 'OK_TEXTAREA':
                    return True
            except Exception:
                pass

        # C. execCommand 兜底
        try:
            js = f"""
            const box = document.querySelector({sel});
            if (!box) return 'NO_BOX';
            box.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            if (document.execCommand('insertText', false, {text_js})) return 'OK_EXEC';
            box.innerHTML = '';
            const p = document.createElement('p');
            p.textContent = {text_js};
            box.appendChild(p);
            box.dispatchEvent(new InputEvent('input',
                {{bubbles:true, data:{text_js}, inputType:'insertText'}}));
            return 'OK_FALLBACK';
            """
            r = self.driver.execute_script(js)
            if r == "NO_BOX":
                return False
            if r == "OK_FALLBACK":
                self.log_signal.emit("退回innerHTML注入(React可能不响应)", "warn")
            return True
        except Exception as e:
            self.log_signal.emit(f"注入异常:{e}", "warn")
            return False

    # ---------- 发送按钮状态机(v1.91 BUG-065)----------
    def _site_is_thinking(self, selector):
        """
        v2.22.1 BUG-082 (C 主防御):查询 DOM 是否存在某个 "AI 正在思考" 元素。

        给 Qwen 这类有显式"思考状态"UI 的站点用。Qwen 思考中页面会有
        `.qwen-chat-status-card-title-animate` 这个带 -animate 后缀的 div
        (例:"梳理情节脉络,提炼核心要素")。思考完后这个动画类消失,
        父容器换成 `.qwen-chat-thinking-status-card-completed` + 文本
        "已经完成思考"。

        polling 看到这个 selector 命中 → Qwen 还在思考 → 跳过完成判定。

        参数 selector:CSS selector,从 profile 的 thinking_indicator 字段读
        返回 True = 还在思考,False = 已完成或没这种 UI / 查询失败
        """
        if not selector:
            return False
        try:
            return bool(self.driver.execute_script(
                "return !!document.querySelector(arguments[0]);", selector
            ))
        except Exception:
            return False

    def _get_send_button_state(self):
        """
        统一查"发送按钮当前态",返回 dict:
          state ∈ {'enabled', 'disabled', 'stop', 'loading', 'none'}
          detail: 文字说明,用于日志
        
        语义:
          enabled  — 按钮亮,可点击发送(textarea 有内容)
          disabled — 按钮灰(textarea 空 / 上传中 / 锁定)
          stop     — 当前是 stop 按钮(AI 正在写,千万别点)
          loading  — 发送瞬间 / spinner 状态
          none     — 按钮不在 DOM(可能正在重渲染)
        
        v1.91 新增。原 _dispatch_send 只在失败后看"事后症状"
        (消息计数 / textarea 清空 / AI 写迹象),漏掉"按钮当前态"
        这个最直接的信号,导致 BUG-065 中摘要任务发送失败时
        诊断不清根因(灰?还是焦点丢?)。

        v2.22.0 BUG-081 修复:在 JS 内的通用 selector 之前,先用当前站点
        profile 的 send_btn 作为最高优先级 — 否则 Qwen 的 button.send-button
        既不被 composer-submit-btn / [data-testid=send-button] / aria-label
        命中,也不被 DeepSeek 风格的 textarea 邻近 div[role=button] 命中,
        会一路掉到 no_btn_in_dom,实战日志里看到的就是这个症状。
        """
        # BUG-081: 取当前 URL 对应站点 profile 的 send_btn,作为 JS 内最高优先 selector
        try:
            _prof = _profile_for_url(self._current_url())
            _site_send_sel = _prof.get("send_btn", "") if _prof else ""
        except Exception:
            _site_send_sel = ""
        try:
            return self.driver.execute_script(r"""
                const siteSel = arguments[0] || '';
                // 0) BUG-081: site profile 优先 — 命中 Qwen 这类自定义按钮
                let btn = null;
                if (siteSel) {
                    try {
                        const c = document.querySelector(siteSel);
                        if (c && c.offsetParent !== null) btn = c;
                    } catch (_) {}
                }
                // 1) 通用发送按钮(ChatGPT/Claude/镜像站)
                if (!btn) btn = document.querySelector('button.composer-submit-btn')
                       || document.querySelector('[data-testid="send-button"]')
                       || document.querySelector('button[aria-label*="发送"]')
                       || document.querySelector('button[aria-label*="Send" i]');
                
                // 2) 没找到通用 → 找 textarea 旁边的 [role=button](DeepSeek)
                let isDsCandidate = false;
                if (!btn) {
                    const ta = document.querySelector('textarea');
                    if (ta) {
                        let c = ta.parentElement;
                        const taRect = ta.getBoundingClientRect();
                        let best = null;
                        let bestX = -Infinity;
                        for (let i = 0; i < 5 && c; i++) {
                            const cands = c.querySelectorAll('div[role="button"]:has(svg)');
                            for (const cand of cands) {
                                if (cand.offsetParent === null) continue;
                                const r = cand.getBoundingClientRect();
                                if (r.top >= taRect.top - 10 && r.left >= taRect.left
                                        && r.right > bestX) {
                                    best = cand;
                                    bestX = r.right;
                                }
                            }
                            if (best) break;
                            c = c.parentElement;
                        }
                        btn = best;
                        isDsCandidate = !!best;
                    }
                }
                
                if (!btn) return {state: 'none', detail: 'no_btn_in_dom'};
                
                // 3) 判 stop(发送按钮在 AI 写期间会变成 stop)
                const hasRect = btn.querySelector('svg rect') !== null;
                const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                const isStop = hasRect || ariaLabel.includes('停止')
                                       || ariaLabel.includes('stop');
                if (isStop) return {state: 'stop', detail: 'aria=' + ariaLabel + ',rect=' + hasRect};
                
                // 4) 判 loading(spinner / animate-spin)
                const hasSpinner = btn.querySelector(
                    'svg[class*="animate-spin" i], svg[class*="spinner" i], [class*="loading" i]'
                ) !== null;
                if (hasSpinner) return {state: 'loading', detail: 'spinner_visible'};
                
                // 5) 判 disabled
                const ariaDis = (btn.getAttribute('aria-disabled') || '').toLowerCase();
                const isDisabled = btn.disabled || ariaDis === 'true';
                if (isDisabled) {
                    // 取 textarea 内容长度辅助判断
                    const ta = document.querySelector('textarea');
                    const taLen = ta ? (ta.value || '').length : -1;
                    return {state: 'disabled', detail: 'aria-dis=' + ariaDis 
                            + ',btn.disabled=' + btn.disabled + ',ta_len=' + taLen};
                }
                
                // 6) 默认 enabled
                let _src = 'common_selector';
                if (siteSel && btn === document.querySelector(siteSel)) _src = 'site_profile';
                else if (isDsCandidate) _src = 'ds_nearby';
                return {state: 'enabled', detail: _src};
            """, _site_send_sel) or {'state': 'none', 'detail': 'js_returned_null'}
        except Exception as e:
            return {'state': 'none', 'detail': f'exception:{e}'}

    # ---------- 发送派发(Enter / 按钮 / 兜底强点)----------
    def _dispatch_send(self, send_btn_selector):
        """
        优先级:
          1. 模拟在输入框按 Enter
          2. 等待发送按钮变可点(最多 10s),点它
          3. 兜底:无明显上传指示就强制 click(对付 React state 卡住)
        """
        # 用通用的回复数计数(DeepSeek/豆包/Gemini 各种都覆盖到)
        _count_js = """
            return (
                document.querySelectorAll('div.ds-markdown.ds-assistant-message-main-content').length ||
                Math.floor(document.querySelectorAll('p.ds-markdown-paragraph').length / 1) ||
                document.querySelectorAll('div.markdown,[data-message-author-role="assistant"]').length
            );
        """
        # 1) Enter —— ProseMirror编辑器跳过(会换行),其他走Enter
        try:
            is_pm = self.driver.execute_script("""
                const el = document.activeElement;
                return el && (el.classList.contains('ProseMirror') ||
                              el.id === 'prompt-textarea');
            """)
            if not is_pm:
                self.driver.execute_script("""
                    const ev = new KeyboardEvent('keydown',
                        {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true});
                    const box = document.activeElement || document.body;
                    box.dispatchEvent(ev);
                """)
        except Exception:
            pass

        # 1.5) 镜像站/ChatGPT 专用: 多策略发送
        _before_cnt = 0
        try:
            _before_cnt = self.driver.execute_script(_count_js) or 0
        except Exception:
            pass

        # 策略A: focus 输入框 + Enter (实测最稳定的方式,DeepSeek 也支持)
        try:
            from selenium.webdriver.common.action_chains import ActionChains as _AC
            from selenium.webdriver.common.keys import Keys as _K
            self.driver.execute_script("""
                const box = document.querySelector('textarea')
                         || document.querySelector('#prompt-textarea')
                         || document.querySelector('div[contenteditable="true"]');
                if (box) box.focus();
            """)
            time.sleep(0.2)
            _AC(self.driver).send_keys(_K.RETURN).perform()
            self.log_signal.emit("已按 Enter 发送，等待响应...", "info")
            # v1.32 dev: console 诊断 — 看 Enter 后 1 秒内 composer 文本是否清空
            print(f"[dispatch_send] Enter 后 1s, _before_cnt={_before_cnt}", flush=True)
            # ★ 关键修复:Enter 后给 DeepSeek 更长时间响应(尤其是冷启动 / 长 prompt)
            #   分阶段等待 — 1.5s / 3s / 5s 各检查一次,任一通过就 return
            # RL 推荐的 send_wait(总时长),拆分为 3 段
            _rl_total_wait = 5.0  # 默认 5s 分 1.5+1.5+2
            try:
                if getattr(self, "_rl_current_action", None):
                    _rl_total_wait = float(
                        self._rl_current_action.get("send_wait", 3.0))
            except Exception:
                pass
            # 把总时长拆成 3 段,前两段各 30%,最后一段 40%
            _step1 = _rl_total_wait * 0.3
            _step2 = _rl_total_wait * 0.3
            _step3 = _rl_total_wait * 0.4
            for wait_step in (_step1, _step2, _step3):
                time.sleep(wait_step)
                _after_cnt = self.driver.execute_script(_count_js) or 0
                # 检测 1:消息计数增加(最稳)
                if _after_cnt > _before_cnt:
                    self.log_signal.emit(
                        f"✓ 发送成功(消息数 {_before_cnt}→{_after_cnt})", "info")
                    return True
                # 检测 2:AI 正在写(stop 按钮 / 新内容出现)
                try:
                    ai_writing = self.driver.execute_script(r"""
                        const ta = document.querySelector('textarea');
                        if (!ta) return false;
                        let c = ta.parentElement;
                        for (let i = 0; i < 5 && c; i++) {
                            const stopByRect = c.querySelector('div[role="button"]:has(svg rect)');
                            if (stopByRect && stopByRect.offsetParent !== null) return true;
                            const stopByLabel = c.querySelector(
                                'div[role="button"][aria-label*="停止"], button[aria-label*="停止"]');
                            if (stopByLabel && stopByLabel.offsetParent !== null) return true;
                            c = c.parentElement;
                        }
                        return false;
                    """)
                    if ai_writing:
                        self.log_signal.emit(
                            f"✓ Enter 已发送(检测到 AI 正在写,计数器假警 {_before_cnt}→{_after_cnt})",
                            "info")
                        return True
                except Exception:
                    pass
                # 检测 3:textarea 是否被清空(发送后 DeepSeek 会清空输入)
                try:
                    ta_empty = self.driver.execute_script(r"""
                        const ta = document.querySelector('textarea');
                        return ta && ta.value.trim() === '';
                    """)
                    if ta_empty:
                        self.log_signal.emit(
                            f"✓ Enter 已发送(textarea 已清空,确认发送)", "info")
                        return True
                except Exception:
                    pass
                # 检测 4(v1.91 BUG-065 新增):按钮态作为旁证
                #   stop/loading → AI 已开始处理(等于发送成功的强证据)
                #   none → 按钮 DOM 重渲染中,谨慎处理(不立即判定成功)
                try:
                    _btn = self._get_send_button_state()
                    _bs = _btn.get('state')
                    if _bs in ('stop', 'loading'):
                        self.log_signal.emit(
                            f"✓ Enter 已发送(按钮态={_bs},AI 正在处理)", "info")
                        return True
                except Exception:
                    pass
            # 全部检测都失败 → 真的没发出去,日志告警 + 走策略 B
            # v1.91 BUG-065:加按钮态诊断,补"事后症状全阴性"时的根因盲区
            _btn_state_now = self._get_send_button_state()
            self.log_signal.emit(
                f"Enter 后 5s 仍未确认发送({_before_cnt}→{_after_cnt} / textarea 未清空 / 无 AI 写迹象 / 按钮态={_btn_state_now.get('state')}:{_btn_state_now.get('detail','')})，尝试按钮",
                "warn")
        except Exception as e:
            self.log_signal.emit(f"Enter发送异常: {e}", "warn")

        # ★ RL 控制:如果 RL 学到"这个 state 不该走策略 B" → 直接 return False
        try:
            if (getattr(self, "_rl_current_action", None)
                    and self._rl_current_action.get("use_strategy_b") is False):
                self.log_signal.emit(
                    "🤖 RL 建议跳过策略 B(避免误点 stop),return False", "info")
                return False
        except Exception:
            pass

        # 策略B: 强制点击按钮(DeepSeek + ChatGPT 通用,加 textarea 邻近按钮策略)
        # BUG-081: 同步在 JS 内最先尝试当前站点 profile 的 send_btn,解决 Qwen
        #          button.send-button 不被通用 selector 命中导致返回 'no-btn'
        try:
            _prof_b = _profile_for_url(self._current_url())
            _site_send_sel_b = _prof_b.get("send_btn", "") if _prof_b else ""
        except Exception:
            _site_send_sel_b = ""
        try:
            clicked = self.driver.execute_script(r"""
                const siteSel = arguments[0] || '';
                // 0) BUG-081: 当前站点 profile 优先 — 命中 Qwen 等自定义按钮
                if (siteSel) {
                    try {
                        const sb = document.querySelector(siteSel);
                        if (sb && sb.offsetParent !== null) {
                            // 排除 stop 状态(AI 写时按钮会切到停止图标)
                            const _hasRect = sb.querySelector('svg rect') !== null;
                            const _al = (sb.getAttribute('aria-label') || '').toLowerCase();
                            const _isStop = _hasRect || _al.includes('停止')
                                                     || _al.includes('stop');
                            if (!_isStop) {
                                sb.removeAttribute('disabled');
                                sb.removeAttribute('aria-disabled');
                                sb.click();
                                return 'site-profile-btn';
                            }
                        }
                    } catch (_) {}
                }
                // 1) 通用按钮选择器(ChatGPT/Claude 镜像站)
                let btn = document.querySelector('button.composer-submit-btn')
                       || document.querySelector('[data-testid="send-button"]')
                       || document.querySelector('button[aria-label*="发送"]')
                       || document.querySelector('button[aria-label*="Send" i]');
                if (btn) {
                    btn.removeAttribute('disabled');
                    btn.removeAttribute('aria-disabled');
                    btn.click();
                    return 'compat-btn';
                }
                // 2) DeepSeek: textarea 旁边的最右下角带 svg 的 [role=button]
                //    (textarea 的祖父级 form/div 里, 选 m 尺寸或 sizing-container)
                const ta = document.querySelector('textarea');
                if (ta) {
                    // 找 textarea 共同祖先(往上找 form/div 容器)
                    let container = ta.parentElement;
                    for (let i = 0; i < 5 && container; i++) {
                        const candidates = container.querySelectorAll(
                            'div[role="button"]:has(svg)');
                        // 候选里选可见 + 右下位置的(taX > textarea.x 且 visible)
                        const taRect = ta.getBoundingClientRect();
                        let best = null;
                        let bestX = -Infinity;
                        for (const c of candidates) {
                            if (c.offsetParent === null) continue;
                            // ★★ 关键修复:排除 stop 按钮(防止 AI 写时把停止按钮当发送按钮)
                            // 停止按钮特征:SVG 含 rect 元素(方块图标),或 aria-label 含"停止"
                            const hasRect = c.querySelector('svg rect') !== null;
                            const ariaLabel = (c.getAttribute('aria-label') || '').toLowerCase();
                            const isStopBtn = hasRect || ariaLabel.includes('停止')
                                || ariaLabel.includes('stop');
                            if (isStopBtn) continue;
                            // 排除"深度思考""智能搜索"等带文字的按钮
                            const txt = (c.innerText || c.textContent || '').trim();
                            if (txt && txt.length > 0 && txt.length < 10) continue;
                            const r = c.getBoundingClientRect();
                            // 选 textarea 右下方的, 优先最靠右
                            if (r.top >= taRect.top - 10 && r.left >= taRect.left
                                    && r.right > bestX) {
                                best = c;
                                bestX = r.right;
                            }
                        }
                        if (best) {
                            best.click();
                            return 'deepseek-nearby-btn:' + (best.className || '').slice(0, 50);
                        }
                        container = container.parentElement;
                    }
                }
                return 'no-btn';
            """, _site_send_sel_b)
            self.log_signal.emit(f"点击发送按钮策略B: {clicked}", "info")
            time.sleep(1.5)
            _after_cnt2 = self.driver.execute_script(_count_js) or 0
            if _after_cnt2 > _before_cnt:
                self.log_signal.emit(f"✓ 按钮点击成功(消息数 {_before_cnt}→{_after_cnt2})", "info")
                return True
        except Exception as e:
            self.log_signal.emit(f"按钮发送异常: {e}", "warn")

        # 策略C: 走原来的旧逻辑(fallback)
        self.log_signal.emit("策略 A/B 都未确认发送, 退到旧 selector 兜底", "warn")

        # 2) 等按钮可点(每 0.25s 轮询,最多 10s)
        sel = json.dumps(send_btn_selector)
        deadline = time.time() + 10
        while time.time() < deadline:
            if self._stop.is_set(): return False
            clicked = self.driver.execute_script(f"""
                const btn = document.querySelector('button.composer-submit-btn')
                         || document.querySelector({sel})
                         || document.querySelector('[data-testid="send-button"]')
                         || document.querySelector('button[aria-label*="发送" i]')
                         || document.querySelector('button[aria-label*="Send" i]')
                         || document.querySelector('form button[type="submit"]');
                if (!btn) return false;
                const ariaDis = (btn.getAttribute('aria-disabled') || '').toLowerCase();
                // 只检查 disabled 属性和 aria-disabled，不检查 className（避免误判）
                const dis = btn.disabled || ariaDis === 'true';
                if (!dis) {{ btn.click(); return true; }}
                // 即使 disabled 也强点
                btn.removeAttribute('disabled');
                btn.removeAttribute('aria-disabled');
                btn.click();
                return true;
            """)
            if clicked:
                return True
            time.sleep(0.25)

        # 3) 兜底强点(无上传中就信任视觉)
        forced = self.driver.execute_script(f"""
            const upScopes = document.querySelectorAll(
                'div[class*="attachment" i], div[class*="file-preview" i], ' +
                'form [class*="upload" i]'
            );
            let uploading = 0;
            upScopes.forEach(s => {{
                uploading += s.querySelectorAll(
                    'svg[class*="animate-spin" i], svg[class*="spinner" i], ' +
                    '[role="progressbar"], [class*="loading" i]'
                ).length;
            }});
            if (uploading > 0) return {{ok:false, reason:'uploading'}};
            const btn = document.querySelector({sel})
                     || document.querySelector('[data-testid="send-button"]')
                     || document.querySelector('button[aria-label*="发送" i]')
                     || document.querySelector('button[aria-label*="Send" i]')
                     || document.querySelector('form button[type="submit"]');
            if (!btn) return {{ok:false, reason:'no_btn'}};
            try {{ btn.click(); return {{ok:true, reason:'forced'}}; }}
            catch (e) {{ return {{ok:false, reason:'exc', err:String(e)}}; }}
        """) or {}
        if forced.get("ok"):
            self.log_signal.emit("⚡ 兜底:按钮 disabled 但无上传中,已强制点击", "warn")
            return True
        return False

    # ---------- 关键任务降级兜底(v1.91 BUG-065)----------
    def _build_degraded_content(self, task):
        """
        关键任务发送失败 + 重试用尽时,构造"本地降级内容"作为伪 AI 响应,
        让上层 handler 走正常 success 路径,避免数据丢失/流水线卡住。
        
        只对 chapter_summary 做实质降级(章节正文头/尾拼接);
        其他关键 target 返回带标签的占位字符串,handler 自行决定是否采用。
        所有降级内容都带 [降级:vN.NN BUG-065] 前缀,便于事后人工识别 + 重生成。
        """
        target = task.get("target", "")
        ch_num = task.get("ch_num", 0)
        
        if target == "chapter_summary":
            # 章节摘要降级:头 300 + 尾 300 + 标签
            #   _ch_content/_ch_title 由 _submit_summary_task 在 meta 里塞进来
            ch_content = (task.get("_ch_content") or "").strip()
            ch_title = task.get("_ch_title") or f"第{ch_num}章"
            if not ch_content:
                return (f"[降级:v1.91 BUG-065 摘要任务发送失败且无章节正文兜底,"
                        f"建议手动重新生成第 {ch_num} 章摘要]")
            head = ch_content[:300].strip().replace('\n', ' ')
            tail_zone = ch_content[-300:].strip().replace('\n', ' ') \
                if len(ch_content) > 700 else ""
            parts = [f"【{ch_title} - 降级摘要】"]
            parts.append(f"开头:{head}")
            if tail_zone and tail_zone != head:
                parts.append(f"结尾:{tail_zone}")
            parts.append(
                f"[降级:v1.91 BUG-065 本次摘要 AI 任务发送失败,"
                f"本地从章节正文截取头尾拼接,信息密度低于正常摘要,"
                f"建议有空时手动到对话记忆 Tab 点'本章重生成摘要']")
            return " | ".join(parts)
        
        elif target == "canon_extract":
            # Canon 抽取降级:返回空 JSON 让 handler 走"无新增"分支
            #   handler 收到空字符串/空 JSON 时通常会跳过,不破坏现有 KB
            return ""
        
        elif target in ("character_extract", "world_extract", "long_term_extract"):
            # 这三个用户多为手动触发,降级返回空让 handler 不破坏现有数据
            #   (handler 通常会判 content.strip() 为空 → log 一句"AI 无返回")
            return ""
        
        return ""

    # ---------- 抓取/计数(用 querySelectorAll,跳过 selenium 的 CSS 解析)----------
    def _count_responses(self, prof):
        # DeepSeek 专属:用"p.ds-markdown-paragraph 的父分组数"做计数
        # 这样新版 / 旧版都能用一致计数
        if prof.get("_grab_strategy") == "deepseek_paragraphs":
            try:
                n = int(self.driver.execute_script(r"""
                    let n1 = document.querySelectorAll(
                        'div.ds-markdown.ds-assistant-message-main-content').length;
                    if (n1 > 0) return n1;
                    // 退路:数 p.ds-markdown-paragraph 的"父分组数"
                    const paragraphs = document.querySelectorAll('p.ds-markdown-paragraph');
                    if (!paragraphs.length) return 0;
                    let groups = 0;
                    let curParent = null;
                    for (const p of paragraphs) {
                        if (p.parentElement !== curParent) {
                            groups++;
                            curParent = p.parentElement;
                        }
                    }
                    return groups;
                """) or 0)
                if n > 0:
                    return n
            except Exception:
                pass  # 降级到通用流程

        # 依次尝试 response 主选择器 + fallback，返回第一个有结果的数量
        selectors = []
        primary = prof.get('response', '')
        if primary:
            selectors.append(primary)
        selectors.extend(prof.get('_response_fallback', []))
        if not selectors:
            selectors = ['div.markdown', '[data-message-author-role="assistant"]']
        for sel in selectors:
            try:
                cnt = int(self.driver.execute_script(
                    f"return document.querySelectorAll({json.dumps(sel)}).length;"
                ) or 0)
                if cnt > 0:
                    return cnt
            except Exception:
                continue
        return 0

    def _grab_last_response(self, prof):
        """
        抓取最新 AI 回复文本。
        优先级:
          1. TamperMonkey bridge —— 如果档案有 tm_bridge=True,
             先读 localStorage.__novelai_reply(由 TM 脚本写入),
             有内容且时间戳在 60s 内就直接用,跳过 DOM 选择器。
          2. DOM 选择器(profile 主选择器 → _response_fallback → 通用兜底)
        """
        # ── 1. TamperMonkey bridge
        if prof.get("tm_bridge"):
            try:
                bridge = self.driver.execute_script("""
                    try {
                        const raw = localStorage.getItem('__novelai_reply');
                        if (!raw) return null;
                        const obj = JSON.parse(raw);
                        if (!obj || !obj.text) return null;
                        // 60 秒内的数据才算有效
                        if (Date.now() - (obj.ts || 0) > 60000) return null;
                        return obj.text;
                    } catch(e) { return null; }
                """)
                if bridge and bridge.strip():
                    return bridge.strip()
            except Exception:
                pass  # bridge 不可用则降级到 DOM 选择器

        # ── 1.5. DeepSeek 专属策略:把"最近一组 p.ds-markdown-paragraph"拼成完整回复
        # 用户报告 DeepSeek DOM 变化:
        #   div.ds-markdown.ds-assistant-message-main-content 是外层容器
        #   p.ds-markdown-paragraph 是段落,但新版可能拿不到外层 div,只有 p
        # 策略:扫所有 p.ds-markdown-paragraph,按 DOM 顺序找最后一组连续的(共同父亲)
        if prof.get("_grab_strategy") == "deepseek_paragraphs":
            try:
                ds_text = self.driver.execute_script(r"""
                    // 1) 优先用外层 div.ds-markdown.ds-assistant-message-main-content
                    let containers = document.querySelectorAll(
                        'div.ds-markdown.ds-assistant-message-main-content');
                    if (containers.length > 0) {
                        const last = containers[containers.length - 1];
                        return (last.innerText || last.textContent || '').trim();
                    }
                    // 2) 退路:扫所有 p.ds-markdown-paragraph,按"父节点分组"取最后一组
                    const paragraphs = document.querySelectorAll('p.ds-markdown-paragraph');
                    if (!paragraphs.length) return '';
                    // 按 immediate parent 分组(同一回复的 p 共父亲)
                    const groups = [];
                    let curParent = null;
                    let curGroup = [];
                    for (const p of paragraphs) {
                        if (p.parentElement !== curParent) {
                            if (curGroup.length) groups.push(curGroup);
                            curParent = p.parentElement;
                            curGroup = [p];
                        } else {
                            curGroup.push(p);
                        }
                    }
                    if (curGroup.length) groups.push(curGroup);
                    if (!groups.length) return '';
                    // 用最后一组
                    const lastGroup = groups[groups.length - 1];
                    return lastGroup.map(p => (p.innerText || p.textContent || '').trim())
                                    .filter(t => t).join('\n\n');
                """) or ""
                if ds_text and len(ds_text.strip()) > 10:
                    return ds_text.strip()
            except Exception:
                pass  # 降级到通用 selector 流程

        # ── 2. DOM 选择器(优先抓 assistant role 的最后一条)
        # 顺序: assistant 容器内的 markdown > assistant 容器 > 任意 markdown
        _fallback_defaults = [
            '[data-message-author-role="assistant"] div.markdown',
            '[data-message-author-role="assistant"] .prose',
            '[data-message-author-role="assistant"]',
            'div.markdown',  # 兜底:可能是用户消息,但有内容总比没有强
            'div.prose',
        ]
        selectors = []
        primary = prof.get('response', '')
        # 主选择器先用 assistant 限定的版本
        if primary == 'div.markdown':
            selectors.append('[data-message-author-role="assistant"] div.markdown')
        if primary:
            selectors.append(primary)
        selectors.extend(prof.get('_response_fallback', []))
        selectors.extend(_fallback_defaults)
        # 去重保序
        seen = set()
        selectors = [s for s in selectors if s and not (s in seen or seen.add(s))]

        for sel in selectors:
            try:
                text = self.driver.execute_script(f"""
                    const ns = document.querySelectorAll({json.dumps(sel)});
                    if (!ns.length) return '';
                    const last = ns[ns.length - 1];
                    return (last.innerText || last.textContent || '').trim();
                """) or ""
                if len(text.strip()) > 10:
                    return text.strip()
            except Exception:
                continue
        return ""
