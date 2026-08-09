#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古超级写作助手
=============================================
基于 PyQt5 + Selenium 的本地小说创作辅助软件
- 挂载真实 Chrome / Edge,自动操作 DeepSeek / 豆包 / Gemini / 元宝 等 AI 网页
- 三种启动模式:attach(连接已开调试 Chrome,最稳)/ standalone / temp
- 内置盘古超级系统(禁用词过滤 + 感官铁律 + 压爆震 + 黄金三章公式)
- 章节列表 / 项目存档(JSON) / 一键保存所有章节
- 角色与世界全部库自动同步(角色/关系/伏笔/承诺/弧线/信息/剧情树等)/ 30 项质检 + AI 自动修复 / 章节元信息面板

运行依赖:
    pip install PyQt5 selenium
    (selenium 4.6+ 自动管理 driver,无需单独装 chromedriver)
"""

# ── 版本号(改这里就行,会同步到窗口标题/状态栏/关于框) ──
APP_VERSION = "v2.23.5"
# 版本号规则(用户铁律):格式 vX.YZ,小改动末位+1(v1.01→v1.02),
# 大改动十位+1末位归零(v1.02→v1.10),v1.99 满 → v2.00 主版本进位。
# 详见 项目对接记忆.md "版本号铁律" 段。
APP_NAME    = "盘古超级写作助手"
APP_FULL    = f"{APP_NAME} {APP_VERSION}"

# ──────────────────────────────────────────────────────────────────
# v2.10:DEFENSE_FINGERPRINTS — 二道闸巡查指纹字典
# 给 housekeeper.verify_defenses() 用。每个 BUG 配一组代码模式,
# 任何指纹缺失意味着该 BUG 修复点被回退(工程级回归)。
#
# 编码原则:
#   - 每个 pattern 必须是"很难因为 lint/重构而消失但能因为误删而消失"的字符串
#   - 优先选**独特的方法名/变量名/常量名**(grep 唯一性高),避免普通词
#   - 多个 pattern AND 关系:全在 = 防御完好,任一缺失 = 防御消失
#
# 添加新条目流程(给下一代 Claude):
#   1. 修完一个真正棘手的 BUG 后,在这里加 "BUG-XXX": [模式列表]
#   2. 模式选 1-3 个,用最具特征的标识符 / 注释关键词
#   3. 不要选常见词(如"chapter""def"),容易在重构后被替换
#   4. 测试:故意删一个模式跑 hk.verify_defenses(),应该报警
# ──────────────────────────────────────────────────────────────────
DEFENSE_FINGERPRINTS = {
    # BUG-028:章节指纹防串(防止已生成章节因 race 被覆盖)
    "BUG-028": ["_chapter_fingerprint"],
    # BUG-065:关键后处理任务失败 → 重试 + 本地降级(摘要丢失止血)
    "BUG-065": ["CRITICAL_TARGETS", "_build_degraded_content"],
    # BUG-066:章节锁定机制(locked 字段拦截 delete/rename/save/切走时写回)
    "BUG-066": ["_toggle_chapter_lock", '"locked"'],
    # BUG-067:角色 last_ch 字段 + 同名不同姓检查
    "BUG-067": ["_find_duplicate_names", '"last_ch"'],
    # BUG-068:下一章选项按钮对比度修复(深棕 WCAG AAA)
    "BUG-068": ["#3a2a10"],
    # BUG-069:字数判定三档(超长 ⚠ 但不扣健康度)
    "BUG-069": ["word_count_long"],
    # BUG-071:_pending_task_targets 字典治本(race 修复)
    "BUG-071": ["_pending_task_targets"],
    # BUG-073:QSettings None 兜底(Linux 无存档时 isinstance 检测)
    # 注:模式选 `or []` + `isinstance` 联合(更难因重构消失)
    "BUG-073": ["s.value(", "or []"],
}

# ──────────────────────────────────────────────────────────────────
# v2.21.4 双 AI 分工:可路由到副 AI 的"数据/分析型"任务
# ──────────────────────────────────────────────────────────────────
# 主 AI (DeepSeek):写正文/优化/创意/对话/取名 — 需要叙事力
# 副 AI (Qwen):    抽取/稽核/数据 — 需要结构化输出能力
#
# 列在这里的 target 在用户启用"副 AI"时会自动路由到副 AI URL,
# 走另一个浏览器标签页。其他 target(写作类)继续走主 AI。
# ──────────────────────────────────────────────────────────────────
SECONDARY_AI_TARGETS = {
    # —— 抽取类 ——
    "canon_extract", "canon_audit",
    "character_extract", "long_term_extract",
    "chapter_summary",
    "chapter_to_plot_node",
    "import_extract", "book_chapter_analysis",
    # —— 稽核/打分类 ——
    "critique_rhythm", "critique_character", "critique_mru",
    "critique_mismatch", "critique_pov_lock", "style_audit",
    "arc_advance_check", "relation_change_check",
    "foreshadow_check", "foreshadow_reeval",
    "promise_check", "promise_reeval",
    "info_check", "info_disclose_check",
    # —— 简单分析 ——
    "dialogue_critic", "laodao_critique",
    "pangu_qcheck", "pangu_mode",
    "skill_run",
}

import sys
import os
import re
import json
try:
    import project_io
    PROJECT_IO_AVAILABLE = True
except ImportError:
    PROJECT_IO_AVAILABLE = False
try:
    import dialogue_critic
    DIALOGUE_CRITIC_AVAILABLE = True
except ImportError:
    DIALOGUE_CRITIC_AVAILABLE = False
try:
    import book_splitter
    BOOK_SPLITTER_AVAILABLE = True
except ImportError:
    BOOK_SPLITTER_AVAILABLE = False
try:
    import import_continuation
    IMPORT_CONTINUATION_AVAILABLE = True
except ImportError:
    IMPORT_CONTINUATION_AVAILABLE = False
try:
    import relation_graph
    RELATION_GRAPH_AVAILABLE = True
except ImportError:
    RELATION_GRAPH_AVAILABLE = False
try:
    import housekeeper as _housekeeper_mod
    HOUSEKEEPER_AVAILABLE = True
except ImportError:
    HOUSEKEEPER_AVAILABLE = False
import time
import random
import socket
import subprocess
import threading
import queue
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QTextBrowser, QDialogButtonBox, QListWidgetItem,
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QPlainTextEdit, QTabWidget,
    QListWidget, QListWidgetItem, QRadioButton, QCheckBox, QButtonGroup,
    QGroupBox, QSplitter, QFileDialog, QMessageBox, QInputDialog,
    QSpinBox, QFrame, QScrollArea, QGridLayout, QAction, QStatusBar,
    QSlider, QComboBox,
)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QObject, QThread, QSize
from PyQt5.QtGui import QFont, QIcon, QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor

# core/ 子包(v2.00 P1 拆分:UI/数据常量 + 全局 QSS)
# 用 `import *` 把 9 个顶层常量注入本模块命名空间,保持所有现有引用零修改
from core.constants import (
    AI_URLS, GENRES, PLATFORMS, ENDINGS, GOLDEN_FINGERS,
    PERSONAS, ERAS, STYLE_DIMENSIONS,
)
from core.stylesheet import STYLESHEET
from core.prompts import PROMPTS  # v2.00 P2:584 行 / 29 keys 移出
from core.site_profiles import SITE_PROFILES, _profile_for_url  # v2.02 P3 + v2.03 P4

# v2.02 P3:5 个完全自包含的 UI 类移出(共 590 行)
from ui.highlighters import _PanguForbiddenHighlighter
from ui.threads import _TTSSynthThread
from ui.theme import ThemeManager
from ui.conversation_switcher import ConversationSwitcher
from ui.story_outline import StoryOutline
from ui.debug_panel import DebugPanel
from ui.emotion_curve import EmotionCurvePanel
from ui.plot_timeline import show_plot_timeline
from ui.ab_compare import ABCompareDialog

# v2.03 P4:DEFAULT_SKILLS 数据 + 8 个 Tab 类(共 3325 行)
from core.default_skills import DEFAULT_SKILLS
from ui.tabs.project_home import ProjectHomeTab
from ui.tabs.book_splitter import BookSplitterTab
from ui.tabs.chapter_editor import ChapterEditor
from ui.tabs.creation_settings import CreationSettings
from ui.tabs.dialog_memory import DialogMemory
from ui.tabs.canon_guard import CanonGuard
from ui.tabs.skill_library import SkillLibrary
from ui.tabs.generation_control import GenerationControl

# v2.04 P5:CharacterLibrary(3860 行,80 方法,P5 单文件最大)
from ui.tabs.character_library import CharacterLibrary

# v2.05 P6:BrowserWorker(2475 行,33 方法,Selenium 自动化 worker)
from ui.browser_worker import BrowserWorker

# Selenium(可选,装了就启用真浏览器自动化)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    try:
        from selenium.webdriver.edge.options import Options as EdgeOptions
    except ImportError:  # 老版 selenium 没有 Edge
        EdgeOptions = None
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    EdgeOptions = None

# QtWebEngine(已不再使用,仅保留作为兜底状态查看,避免老代码引用报错)
WEB_ENGINE_AVAILABLE = False

# ---- 模块化生成流水线(v7 新增,可选) ----
try:
    from workflow_pipeline import (
        GenerationWorkflow, StepRegistry, _patch_main_window
    )
    WORKFLOW_AVAILABLE = True
except ImportError:
    WORKFLOW_AVAILABLE = False

# ---- 流程强化学习(自学习哪种等待/重试策略最优) ----
try:
    from flow_rl import FlowRL, REWARDS as RL_REWARDS
    FLOW_RL_AVAILABLE = True
except ImportError:
    FLOW_RL_AVAILABLE = False
    RL_REWARDS = {}

# ---- 工作流可视化面板(新增) ----
try:
    from workflow_panel import WorkflowPanel
    WORKFLOW_PANEL_AVAILABLE = True
except ImportError:
    WORKFLOW_PANEL_AVAILABLE = False

# ---- 寿元台账 + 长期伏笔检查(新增) ----
try:
    from lifespan_loops_steps import LifespanLoopsExtension
    from lifespan_loops_panel import LifespanLoopsPanel
    LIFESPAN_LOOPS_AVAILABLE = True
except ImportError:
    LIFESPAN_LOOPS_AVAILABLE = False

# ---- 研究报告出厂技能(新增) ----
try:
    from research_report_skills import install_into as _install_research_skills
    RESEARCH_SKILLS_AVAILABLE = True
except ImportError:
    RESEARCH_SKILLS_AVAILABLE = False


# =====================================================================
# 一、内置提示词模板 PROMPTS(29 keys)
#    v2.00 P2 已外迁到 core/prompts.py(原 584 行字典整体搬出)
#    依然通过顶部 `from core.prompts import PROMPTS` 进入本模块 globals(),
#    pangu_patch.install_pangu(globals()) 的就地修改机制完全保留。
# =====================================================================

# ---- 盘古超级系统(零侵入集成,新增) ----
try:
    from pangu_patch import install_pangu
    install_pangu(globals())  # 就地把 PROMPTS 字典套上盘古铁律
    PANGU_AVAILABLE = True
except ImportError:
    PANGU_AVAILABLE = False



# =====================================================================
# 三、章节编辑器(+ 盘古禁用词实时高亮器)
# =====================================================================










# =====================================================================
# 四、创作设置页
# =====================================================================


# =====================================================================
# 五、故事大纲页
# =====================================================================


# =====================================================================
# 六、对话记忆系统
# =====================================================================





# =====================================================================
# B / C / D 新增模块:Canon 设定守护 + 多维自鞭策 + 技能库
# =====================================================================

# 内置出厂技能(用户可在 UI 里增删)




# ═══════════════════════════════════════════════════════════════════
# 角色库 + 关系图谱 + 时间线 + 物品/法器库 + 伏笔追踪
# ═══════════════════════════════════════════════════════════════════







# 各 AI 网站的选择器档案
# 每家 DOM 不同,这里只列经验上比较稳的,跑不通时可微调





# =====================================================================
# 对话槽管理器(E 模块:随时换对话,自动同步记忆)
# =====================================================================





# =====================================================================
# 七、(原封面生成页已删除 — 用户不需要,2026-05-16 第十三批)
# =====================================================================


# =====================================================================
# 八、主窗口
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_FULL)
        self._project_title = ""  # 当前项目名,用于窗口标题
        self.resize(1280, 820)
        # 按 font_scale 把全局样式表里的 font-size: Npx 全部按倍率放大
        # 这是修 BUG-016 的关键 — 不然 app.setFont() 被这里的 13px 死压
        _scale = 1.0
        try:
            from PyQt5.QtWidgets import QApplication as _QA
            _scale = float(_QA.instance().property("_novelai_dpi_scale") or 1.0)
        except Exception:
            pass
        if _scale > 1.0:
            import re as _re
            # 用主题系统代替硬编码 STYLESHEET；旧 light 自动升级到 dark
            _cur_theme = ThemeManager.current()
            if _cur_theme == "light":
                from PyQt5.QtCore import QSettings as _QS2
                _QS2("NovelAI", "UI").setValue("theme", "dark")
                _cur_theme = "dark"
            ThemeManager.apply(_QA.instance(), _cur_theme)
            # 再做 font-size 缩放
            _cur_qss = _QA.instance().styleSheet()
            def _sz(m):
                n = int(m.group(1))
                return f"font-size: {int(round(n * _scale))}px"
            scaled_qss = _re.sub(r'font-size:\s*(\d+)px', _sz, _cur_qss)
            _QA.instance().setStyleSheet(scaled_qss)
        else:
            # 启动时恢复用户上次选择的主题；light 是旧默认值，自动升级到 dark
            _cur_theme = ThemeManager.current()
            if _cur_theme == "light":
                from PyQt5.QtCore import QSettings as _QS2
                _QS2("NovelAI", "UI").setValue("theme", "dark")
                _cur_theme = "dark"
            ThemeManager.apply(_QA.instance(), _cur_theme)

        # 恢复上次窗口大小和位置
        from PyQt5.QtCore import QSettings
        _s = QSettings("NovelAI", "MainWindow")
        _geo = _s.value("geometry")
        if _geo:
            self.restoreGeometry(_geo)

        self.chapters = []
        self.current_chapter_index = -1
        self.project_dir = Path.home() / "NovelAI_Projects"
        self.project_dir.mkdir(exist_ok=True)
        self.current_project_file = None

        # 浏览器自动化 worker
        self.worker = BrowserWorker()

        # 流程强化学习(自学习最优等待/重试策略)
        if FLOW_RL_AVAILABLE:
            from PyQt5.QtCore import QSettings as _QS_rl
            try:
                self.flow_rl = FlowRL(
                    epsilon=0.15,
                    persist_settings=_QS_rl("NovelAI", "FlowRL"))
                # 把 RL 实例挂给 worker(让 worker 在关键决策点查询/反馈)
                self.worker.flow_rl = self.flow_rl
                print(f"[FlowRL] ✓ 已启用,worker.flow_rl 设置成功 "
                      f"(已加载 {len(self.flow_rl.history)} 条历史 / "
                      f"{len(self.flow_rl.q_table)} 个 state)")
            except Exception as _e_rl:
                print(f"[FlowRL] ✗ 初始化失败:{_e_rl}")
                import traceback; traceback.print_exc()
                self.flow_rl = None
        else:
            print("[FlowRL] ✗ flow_rl.py 没找到, RL 未启用")
            self.flow_rl = None

        # 批量生成状态
        self._batch_remaining = 0
        self._batch_paused = False
        # v1.97 BUG-071 治本:把单变量 _pending_task_target 改成字典映射 task_id -> meta
        # 旧字段保留为 None 做兼容兜底(任何外部代码若残留访问,拿到 None 不会崩)
        # 字典 key 是 worker 的 task_id(== _send_to_ai 的 label),value 是 meta dict
        # 例如 {"摘要-第7章": {"target": "chapter_summary", "ch_num": 7, ...}, ...}
        self._pending_task_targets = {}
        self._pending_task_target = None  # deprecated,仅做兼容兜底
        # 一键生成对话记忆的流水线状态
        # 列表元素:(step_name, arg)  step_name ∈ "summary"|"character"|"long_term"
        self._full_memory_pipeline = []
        self._full_memory_total = 0  # 总步数(用于显示进度)
        self._full_memory_running = False

        self._build_menu()
        self._build_ui()
        self._build_statusbar()
        self._connect_signals()
        self._connect_worker()
        self._init_demo_chapters()

        # ---- v7:模块化生成流水线 ----
        if WORKFLOW_AVAILABLE:
            _patch_main_window(self.__class__)       # 注入 _send_to_ai_with_callback
            self.workflow = GenerationWorkflow(self)
            self.workflow.setup_default_steps()
        else:
            self.workflow = None

        # ---- 寿元台账 + 长期伏笔(新增) ----
        if LIFESPAN_LOOPS_AVAILABLE:
            LifespanLoopsExtension.install(self)
            # Phase C-3:盘古 ↔ lifespan_loops 联动桥
            try:
                self._install_pangu_lifespan_bridge()
            except Exception as e:
                print(f"[warn] 盘古-lifespan 联动安装失败: {e}")
            if self.tab_lifespan is not None:
                self.tab_lifespan.sync_from_mw()
            # 伏笔检查Tab同步
            if hasattr(self, 'tab_foreshadow'):
                self.tab_foreshadow.sync_from_mw()
                self.tab_lifespan.request_save.connect(self.save_project)
                self.tab_lifespan.request_log.connect(
                    lambda m, lv: self.tab_generation.log(m, lv))

        # ---- 研究报告出厂技能(新增) ----
        if RESEARCH_SKILLS_AVAILABLE:
            try:
                n_added = _install_research_skills(self.tab_skills)
                if n_added:
                    self.tab_generation.log(
                        f"📚 已加载研究报告出厂技能 {n_added} 条", "info")
            except Exception as e:
                self.tab_generation.log(
                    f"⚠ 研究报告技能装载失败:{e}", "warn")

        # ---- 工作流可视化(加入生成引擎组) ----
        if WORKFLOW_PANEL_AVAILABLE and self.workflow is not None:
            self.tab_workflow = WorkflowPanel(mw=self)
            self.tab_workflow.request_log.connect(
                lambda m, lv: self.tab_generation.log(m, lv))
            self._tab_engine.addTab(self.tab_workflow, "工作流")

        # 恢复上次设置和项目数据
        # 先加载项目数据，再加载设置（QSettings优先级更高，覆盖项目文件中的旧设置）
        self._autoload()
        # 自动启动浏览器(直接读 QSettings,不依赖 checkbox 加载时序)
        try:
            from PyQt5.QtCore import QSettings as _QS_auto
            _auto = _QS_auto("NovelAI", "GenerationControl").value(
                "browser.auto_start", False, type=bool)
            if _auto:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(2000, self._auto_start_browser)
        except Exception:
            pass
        # 启动后默认显示创作设置 Tab
        try:
            self.tabs.setCurrentIndex(0)
        except Exception:
            pass
        self.tab_settings.load_settings()
        # 第 3/5/6 项:恢复用户保存过的自定义题材/金手指/人设条目
        try:
            self.tab_settings._load_custom_checks()
        except Exception:
            pass
        # 第 1 项:加载完之后再装自动保存钩子(避免 load 过程被当作 dirty)
        self.tab_settings.enable_auto_save()
        # 加载用户为站点存的选择器覆盖(BUG-018:DOM 不稳定的解决)
        try:
            self._load_site_profile_overrides()
        except Exception:
            pass
        # 第 7 项:把题材/时代/金手指/人设串成折叠链
        try:
            self.tab_settings._install_collapsible_chain()
        except Exception:
            pass

        # Phase C-2:启动时加载用户自定义风格库(覆盖内置)
        try:
            from PyQt5.QtCore import QSettings as _QS2
            _ps_settings = _QS2("NovelAI", "PanguStyleLib")
            _custom_styles = _ps_settings.value("custom_mapping", None)
            if _custom_styles and isinstance(_custom_styles, list) and _custom_styles:
                from pangu_system import STYLE_MAPPING as _SM
                _SM.clear()
                _SM.extend(_custom_styles)
        except Exception:
            pass

        # ───── 第 9 项:60 秒定时 autosave(防止崩溃丢失对话记忆) ─────
        try:
            from PyQt5.QtCore import QTimer as _AsT
            self._periodic_autosave_timer = _AsT(self)
            self._periodic_autosave_timer.setInterval(60_000)  # 60 秒
            self._periodic_autosave_timer.timeout.connect(self._periodic_autosave_fire)
            self._periodic_autosave_timer.start()
        except Exception:
            pass

        # BUG-016 配套:遍历所有子 widget 把局部 setStyleSheet 里的 font-size 也按倍率放大
        # (全文 26 处 setStyleSheet 写死 font-size,只改全局 STYLESHEET 还不够)
        if _scale > 1.0:
            try:
                import re as _re2
                def _scale_qss_str(s):
                    return _re2.sub(r'font-size:\s*(\d+)px',
                        lambda m: f"font-size: {int(round(int(m.group(1)) * _scale))}px", s)
                for w in self.findChildren(QWidget):
                    ss = w.styleSheet()
                    if ss and "font-size" in ss:
                        w.setStyleSheet(_scale_qss_str(ss))
            except Exception:
                pass

        # ───── 启动时按当前 AI 站点联动 3 checkbox 默认值 ─────
        # 用户原话:'除了镜像站和GPT 其他都不勾选'
        try:
            _cur_btn = self.tab_settings.ai_group.checkedButton()
            if _cur_btn is not None:
                _ai = _cur_btn.text()
                if _ai in ("ChatGPT", "ChatGPT镜像"):
                    self.tab_generation.auto_save.setChecked(True)
                    self.tab_generation.auto_grab.setChecked(True)
                    self.tab_generation.use_attachment.setChecked(True)
                elif _ai != "自定义":
                    self.tab_generation.auto_save.setChecked(False)
                    self.tab_generation.auto_grab.setChecked(False)
                    self.tab_generation.use_attachment.setChecked(False)
        except Exception:
            pass

        # ───── 首次启动盘古介绍 banner(Phase A,真位置) ─────
        try:
            from PyQt5.QtCore import QSettings as _QS, QTimer as _QT
            _s = _QS("NovelAI", "Pangu")
            if not _s.value("first_seen", False, type=bool):
                try:
                    from pangu_system import get_default_engine as _pe
                    _banner = _pe().get_first_activation_banner()
                except Exception:
                    _banner = None
                if _banner:
                    # 延迟 500ms,等主窗口完全显示后再弹
                    def _show_banner():
                        # 生命周期守卫:singleShot 捕获了 self,若 500ms 内
                        # 窗口已销毁(测试环境/秒关应用),在死对象上弹模态
                        # 会段错误;窗口不可见(离屏测试)时弹模态则无人可点,
                        # 事件循环一转就永久挂死
                        try:
                            _visible = self.isVisible()
                        except RuntimeError:
                            return  # C++ 对象已销毁
                        if not _visible:
                            _s.setValue("first_seen", True)
                            return
                        QMessageBox.information(
                            self, "🛕 欢迎使用【盘古超级系统】", _banner)
                        _s.setValue("first_seen", True)
                    _QT.singleShot(500, _show_banner)
                else:
                    _s.setValue("first_seen", True)
        except Exception:
            pass

        # ───── v2.10:管家 P3-#10 RL 反馈联动(注册健康度回调) ─────
        try:
            if HOUSEKEEPER_AVAILABLE:
                _housekeeper_mod.get_housekeeper().set_rl_reward_callback(
                    self._on_hk_health_to_rl)
        except Exception:
            pass

    def _connect_worker(self):
        self.worker.log_signal.connect(self.tab_generation.log_signal.emit)
        self.worker.status_signal.connect(self.update_browser_status)
        self.worker.response_received.connect(self._on_response_received)
        self.worker.started.connect(self._on_browser_started)
        # v2.25.0 镜像登录:worker 截图帧 → 转发给打开中的镜像对话框
        if hasattr(self.worker, "mirror_frame"):
            self.worker.mirror_frame.connect(self._on_mirror_frame)
        # v2.22.2 BUG-083: 任务进度 → 主进程,给"卡死提醒"判定用
        # (旧逻辑:90 秒任务没完成就弹窗。新逻辑:90 秒任务字符数还是 0 才弹)
        try:
            self.worker.task_progress.connect(self._on_task_progress)
        except Exception:
            pass

        # v2.22.3 BUG-085: 任务"思考中"状态 → 主进程,给"卡死提醒"加思考期闸门
        # (Qwen 思考阶段 0 字节 0-90 秒是合法的,不该弹窗。worker 检测到
        # thinking_indicator 命中时 emit True,主进程 _check_timeout 看到
        # thinking=True 就延期 60 秒再查)
        try:
            self.worker.task_thinking.connect(self._on_task_thinking)
        except Exception:
            pass

        # v2.23.0 BUG-086: 番茄榜单扫描完成 → 主进程拼增强 prompt 发 AI
        try:
            self.worker.rank_scraped.connect(self._on_fanqie_rank_scraped)
        except Exception:
            pass

        # v2.23.1: 番茄全榜扫描进度 + 完成信号
        try:
            self.worker.rank_progress.connect(self._on_v231_rank_progress)
            self.worker.rank_all_scraped.connect(self._on_v231_all_ranks_scraped)
        except Exception:
            pass

        # v2.23.3: 详情抓取信号 + 启动 30 秒后自动后台扫
        try:
            self.worker.detail_progress.connect(self._on_v233_detail_progress)
            self.worker.detail_batch_done.connect(self._on_v233_detail_batch_done)
        except Exception:
            pass

        # v2.23.4: 番茄榜单 Tab 实时更新(转发 worker 信号到 Tab)
        try:
            self.worker.rank_progress.connect(self._fanqie_tab_on_rank_progress)
            self.worker.rank_all_scraped.connect(self._fanqie_tab_on_rank_done)
            self.worker.detail_progress.connect(self._fanqie_tab_on_detail_progress)
            self.worker.detail_batch_done.connect(self._fanqie_tab_on_detail_done)
        except Exception:
            pass
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(30000, self._v233_bg_auto_scrape)  # 30s 后启动后台抓
        except Exception:
            pass

    def _on_task_progress(self, task_id, char_count):
        """
        v2.22.2 BUG-083:worker 在 polling 抓到内容时 emit 进度,主进程
        跟踪每个 task 的最新字符数。`_check_timeout` 用这个判断"是否真卡死":
          - 90 秒到了 + 字符数 == 0 → 真卡了,弹窗 + TTS 报警
          - 90 秒到了 + 字符数 > 0  → AI 正在写(Qwen 章节常态),静默不打扰
        """
        if not hasattr(self, "_task_char_progress"):
            self._task_char_progress = {}
        self._task_char_progress[task_id] = int(char_count or 0)

    def _on_task_thinking(self, task_id, is_thinking):
        """
        v2.22.3 BUG-085:worker 在 polling 检测到 Qwen "思考中"动画状态变化时
        emit。主进程跟踪每个 task 的 thinking 状态。`_check_timeout` 用这个
        判断"0 字节卡死"是不是误报:
          - thinking=True  → Qwen 在思考(合法 0 字节),延期 60 秒再查
          - thinking=False → 不在思考期,正常按 0 字节判定卡死
        """
        if not hasattr(self, "_task_thinking_state"):
            self._task_thinking_state = {}
        self._task_thinking_state[task_id] = bool(is_thinking)

    def update_browser_status(self, status):
        """浏览器状态变化时由 BrowserWorker 信号调用 — 把状态显示在状态栏右侧 + 控制 close 按钮"""
        colors = {
            "idle":     ("#28a745", "空闲(就绪)"),
            "busy":     ("#ff9500", "繁忙(执行任务中)"),
            "starting": ("#666",    "启动中..."),
            "stopped":  ("#999",    "已停止"),
            "error":    ("#cc3333", "出错"),
        }
        color, text = colors.get(status, ("#666", str(status)))
        # 生成控制 Tab 顶部状态条
        self.tab_generation.status_label.setText(f"状态:{text}")
        self.tab_generation.status_label.setStyleSheet(
            f"padding: 4px 10px; background: {color}; color: white;"
            f"border-radius: 3px; font-weight: bold;")
        # 主窗口状态栏右侧显示
        if hasattr(self, "_status_indicator"):
            self._status_indicator.setText(f"● {text}")
            self._status_indicator.setStyleSheet(
                f"color: {color}; font-weight: bold; padding: 2px 8px;")
        # 启动 / 关闭 按钮状态切换
        if status == "idle":
            self.tab_generation.btn_launch.setEnabled(False)
            self.tab_generation.btn_close.setEnabled(True)
        elif status in ("stopped", "error"):
            self.tab_generation.btn_launch.setEnabled(True)
            self.tab_generation.btn_close.setEnabled(False)

    # ---- 菜单 ----
    def _build_menu(self):
        m = self.menuBar()
        fm = m.addMenu("文件(&F)")
        for txt, slot, sc in [
            ("新建项目", self.new_project, ""),
            ("打开项目", self.open_project, "Ctrl+O"),
            ("📥 导入外部小说续写...", self.import_continuation, ""),
            ("🕐 最近项目", "__RECENT__", ""),   # v1.41 标记,下面动态填充
            ("保存项目", self.save_project, "Ctrl+S"),
            ("📝 项目重命名", self.rename_project, ""),
            ("🕓 恢复历史版本(最近 10 次)", self.restore_project_backup, ""),
            (None, None, ""),
            ("退出", self.close, ""),
        ]:
            if txt is None:
                fm.addSeparator(); continue
            if slot == "__RECENT__":
                # v1.41: 动态最近项目子菜单
                self.recent_menu = fm.addMenu(txt)
                self._refresh_recent_menu()
                continue
            a = QAction(txt, self)
            if sc: a.setShortcut(sc)
            a.triggered.connect(slot)
            fm.addAction(a)

        sm = m.addMenu("设置(&S)")
        a_font = QAction("🔍 界面字体大小...", self)
        a_font.triggered.connect(self.show_font_scale_dialog)
        sm.addAction(a_font)
        sm.addSeparator()
        a = QAction("关于", self); a.triggered.connect(self.show_about)
        sm.addAction(a)

        # 工具菜单(诊断 / 现场拾取 / 清理)
        tm = m.addMenu("工具(&T)")
        a_diag = QAction("🔬 诊断当前 AI 网页 DOM(看选择器命中)", self)
        a_diag.triggered.connect(self.show_dom_diagnostics)
        tm.addAction(a_diag)
        # v1.50: 老 .json 导入(罕用,从 open_project 主流程剥离)
        a_import_json = QAction("📦 导入旧 .json 项目(v1.29 及之前)", self)
        a_import_json.triggered.connect(self._import_legacy_json)
        tm.addAction(a_import_json)
        a_pick = QAction("🎯 现场拾取选择器(点页面元素自动生成)", self)
        a_pick.triggered.connect(self.start_dom_picker)
        tm.addAction(a_pick)
        tm.addSeparator()
        a_override = QAction("📝 手动编辑当前站点选择器...", self)
        a_override.triggered.connect(self.edit_site_profile_override)
        tm.addAction(a_override)
        tm.addSeparator()
        a_emotion = QAction("📊 查看情绪曲线", self)
        a_emotion.triggered.connect(self._show_emotion_curve)
        tm.addAction(a_emotion)
        a_plotmap = QAction("🗺️ 剧情线地图", self)
        a_plotmap.triggered.connect(self._show_plot_timeline)
        tm.addAction(a_plotmap)
        a_readers = QAction("👥 模拟读者评审", self)
        a_readers.triggered.connect(self._run_reader_panel)
        a_readers.setToolTip("让AI模拟3种读者(追爽/追感情/挑BUG)对当前章节评论")
        tm.addAction(a_readers)
        a_script = QAction("🎬 转短剧剧本", self)
        a_script.triggered.connect(self._convert_to_script)
        a_script.setToolTip("把当前章节改编成竖屏短剧剧本格式")
        tm.addAction(a_script)
        a_ab = QAction("🤖 A/B 对比(重新生成)", self)
        a_ab.triggered.connect(self._start_ab_compare)
        a_ab.setToolTip("对当前章节重新生成一个版本,左右对比选更好的")
        tm.addAction(a_ab)
        tm.addSeparator()
        a_naming = QAction("🎭 AI 智能取名(全文替换)", self)
        a_naming.triggered.connect(self._open_ai_naming)
        a_naming.setToolTip("AI生成10个角色名,选中后全文替换")
        tm.addAction(a_naming)
        tm.addAction(a_override)
        tm.addSeparator()
        a_clean_meta = QAction("🧹 扫描清理所有章节尾部元信息(本章完/钩子/选项)", self)
        a_clean_meta.triggered.connect(self.batch_clean_chapter_meta)
        tm.addAction(a_clean_meta)
        tm.addSeparator()
        a_rl_show = QAction("🤖 流程 RL 学习状态(看自学习成果)", self)
        a_rl_show.triggered.connect(self.show_flow_rl_status)
        tm.addAction(a_rl_show)
        a_rl_reset = QAction("🔄 重置 RL 学习数据(慎用)", self)
        a_rl_reset.triggered.connect(self.reset_flow_rl)
        tm.addAction(a_rl_reset)
        tm.addSeparator()
        a_hk_show = QAction("📋 管家日报(本次会话章节健康汇总)", self)
        a_hk_show.triggered.connect(self.show_housekeeper_summary)
        tm.addAction(a_hk_show)

    def show_housekeeper_summary(self):
        """📋 管家日报弹窗(P1 — 章末聚合 / pipeline 健康度 / 跨章累计)"""
        if not HOUSEKEEPER_AVAILABLE:
            QMessageBox.information(
                self, "管家未启用",
                "管家模块未启用(housekeeper.py 可能没找到)。\n"
                "确认仓库根目录有 housekeeper.py 文件。")
            return
        try:
            hk = _housekeeper_mod.get_housekeeper()
            summary = hk.render_session_summary()
            recent_lines = []
            for r in hk.history[-5:]:
                recent_lines.append("  " + r.render_oneliner())
            if recent_lines:
                summary += "\n\n— 最近 {} 章详情 —\n".format(len(recent_lines))
                summary += "\n".join(recent_lines)
            QMessageBox.information(self, "📋 管家日报", summary)
        except Exception as e:
            QMessageBox.warning(self, "管家日报查询失败", str(e))

    def _on_hk_health_to_rl(self, health_score: float, report: dict):
        """v2.10:管家 finalize_chapter 末尾的健康度反馈回调(P3-#10 集成)

        被 housekeeper.set_rl_reward_callback 注册,每次 finalize 自动调用。

        ─── MVP 实现:仅记录,不真喂 flow_rl ───
        理由(给下一代 Claude 或想接入的用户):
          - flow_rl 的 state/action 是浏览器决策粒度(send_button 状态 / 重试策略等)
            跟"章节级整体健康度"不直接对应,强行注入会留孤儿 Q 表条目
          - 没有 choose_action 配对的 reward 调用,history 也无法回填
          - 健康度的"赋分公式"(score → reward value)是产品决策,不该由代码默认设
          - MVP 阶段:打印日志,让用户观察健康度趋势,后续再决定如何接入 RL

        想接入 flow_rl 的话,在此方法体内补:
            if self.flow_rl:
                state = ("chapter_meta_health", report.get("chapter_num"))
                action = {"type": "chapter_complete"}
                reward_value = (health_score - 0.5) * 40   # -20 ~ +20
                self.flow_rl.reward(state, action, reward_value,
                                    reason=f"章末健康度 {health_score:.2f}")

        失败容错:任何异常吞掉,不影响 housekeeper 的 finalize_chapter 返回
        """
        try:
            ch_num = report.get("chapter_num", "?")
            mark = ("🟢" if health_score >= 0.85 else
                    "🟡" if health_score >= 0.65 else "🔴")
            if hasattr(self, "tab_generation"):
                self.tab_generation.log(
                    f"  · 第{ch_num}章健康度→RL 反馈通道:{mark}{int(health_score * 100)}%"
                    f"(MVP 仅记录,实际接入 flow_rl 留待后续)", "info")
        except Exception:
            pass

    def show_flow_rl_status(self):
        """显示流程 RL 学习状态"""
        if not self.flow_rl:
            QMessageBox.information(
                self, "RL 未启用",
                "流程强化学习未启用(flow_rl.py 可能没找到)。\n"
                "确认仓库根目录有 flow_rl.py 文件。")
            return
        try:
            text = self.flow_rl.summary()
            QMessageBox.information(self, "🤖 流程 RL 学习状态", text)
        except Exception as e:
            QMessageBox.warning(self, "RL 状态查询失败", str(e))

    def reset_flow_rl(self):
        """重置 RL 学习数据"""
        if not self.flow_rl:
            return
        ret = QMessageBox.question(
            self, "确认重置",
            "确定要清空所有 RL 学习数据吗?\n"
            "(重置后程序从头学习,之前的经验丢失)")
        if ret == QMessageBox.Yes:
            self.flow_rl.reset()
            QMessageBox.information(self, "已重置", "RL 学习数据已清空")

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        ml = QHBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(0)

        # ──── 左侧导航栏 (v2.23.4 — 无硬编码颜色,跟随主题) ────
        left = QFrame()
        left.setFixedWidth(220)
        left.setObjectName("nav_sidebar")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 16, 14, 10)
        ll.setSpacing(6)

        # ── 项目操作按钮 ──
        btn_new_proj = QPushButton("＋  新建项目")
        btn_new_proj.setCursor(Qt.PointingHandCursor)
        btn_new_proj.setObjectName("nav_primary_btn")
        btn_new_proj.clicked.connect(self.new_project)
        ll.addWidget(btn_new_proj)

        for text, slot in [
            ("📂  打开项目", lambda: self._on_nav_open_project()),
            ("⏩  继续上次", lambda: None),
        ]:
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("nav_side_btn")
            btn.setStyleSheet("text-align: left; border: none;")
            if slot:
                btn.clicked.connect(slot)
            ll.addWidget(btn)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        ll.addWidget(sep1)

        # ── 创作流程 ──
        flow_lbl = QLabel("→  创作流程")
        flow_lbl.setStyleSheet("font-size:11px; font-weight:bold; padding:4px 0;")
        ll.addWidget(flow_lbl)

        self._nav_steps = []
        steps = [
            ("1", "基础设定", "题材/风格/设定", "创作设置"),
            ("2", "世界构建", "世界观/势力/地图", "世界构建"),
            ("3", "角色设定", "角色/关系/命运线", "角色系统"),
            ("4", "大纲规划", "故事线/主线/支线", "世界构建"),
            ("5", "章节创作", "章节/内容/写作", "生成引擎"),
            ("6", "AI 工具箱", "AI 修改/质检/工具", "AI 工具箱"),
        ]
        for num, name, desc, tab_keyword in steps:
            step_btn = QPushButton(f"  {num}   {name}")
            step_btn.setToolTip(desc)
            step_btn.setCursor(Qt.PointingHandCursor)
            step_btn.setObjectName("nav_step_btn")
            step_btn.setStyleSheet("text-align: left; border: none;")
            _kw = tab_keyword
            step_btn.clicked.connect(lambda checked, k=_kw: self._on_nav_step_by_name(k))
            ll.addWidget(step_btn)
            self._nav_steps.append(step_btn)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        ll.addWidget(sep2)

        # ── 章节列表 ──
        self.lbl_chapter_count = QLabel("📄 章节列表")
        self.lbl_chapter_count.setStyleSheet(
            "font-weight:bold; font-size:11px; padding:2px 0;")
        ll.addWidget(self.lbl_chapter_count)

        self.chapter_list = QListWidget()
        self.chapter_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.chapter_list.setDragDropMode(QListWidget.InternalMove)
        self.chapter_list.model().rowsMoved.connect(self._on_chapters_reordered)
        self.chapter_list.itemClicked.connect(self._on_chapter_clicked)
        self.chapter_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chapter_list.customContextMenuRequested.connect(self._on_chapter_list_context_menu)
        self.chapter_list.setStyleSheet("font-size: 11px;")
        ll.addWidget(self.chapter_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_add = QPushButton("＋")
        btn_add.setFixedSize(32, 28)
        btn_add.setToolTip("新增章节")
        btn_add.clicked.connect(self.add_chapter)
        btn_del = QPushButton("－")
        btn_del.setFixedSize(32, 28)
        btn_del.setToolTip("删除章节")
        btn_del.setObjectName("nav_danger_btn")
        btn_del.clicked.connect(self.delete_chapter)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        hint = QLabel("右键更多")
        hint.setStyleSheet("font-size:10px;")
        btn_row.addWidget(hint)
        ll.addLayout(btn_row)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine)
        ll.addWidget(sep3)

        self._recent_list = QListWidget()
        self._recent_list.setMaximumHeight(120)
        self._recent_list.setStyleSheet("border: none; background: transparent; font-size: 10px;")
        self._recent_list.itemDoubleClicked.connect(self._on_recent_project_clicked)
        ll.addWidget(self._recent_list)

        more_lbl = QLabel("更多项目...")
        more_lbl.setStyleSheet("font-size:10px; padding:2px 0;")
        ll.addWidget(more_lbl)

        ml.addWidget(left)

        # ---- 右侧 Tab ----
        self.tabs = QTabWidget()
        # v1.20:Tab 右上角加 ☀️/🌙 主题切换按钮
        from PyQt5.QtCore import QSettings as _QS_theme
        _theme_name = _QS_theme("NovelAI", "UI").value("theme", "light", type=str)
        # 主题切换按钮已在工具栏(差异化旁边),不再放Tab角落
        self.tab_settings = CreationSettings()
        self.tab_outline = StoryOutline()
        self.tab_memory = DialogMemory()
        self.tab_canon = CanonGuard()
        self.tab_charlib = CharacterLibrary()  # 新增: 角色库+关系+时间线+物品+伏笔
        # 寿元/伏笔(可选模块)
        if LIFESPAN_LOOPS_AVAILABLE:
            self.tab_lifespan = LifespanLoopsPanel(mw=self)
        else:
            self.tab_lifespan = None
        self.tab_skills = SkillLibrary()
        self.tab_generation = GenerationControl()
        self.tab_editor = ChapterEditor()
        # 工作流可视化(可选模块,放最后实例化,因为依赖 self.workflow 已就绪)
        # 这里先占位 None,真正的 WorkflowPanel 在 __init__ 末尾装配
        self.tab_workflow = None

        # Tab 列表(项目主页已移到启动器,不再需要)
        tab_list = [
            (self.tab_settings, "创作设置"),
        ]

        # ── 📝 世界构建(子Tab: 故事大纲 + 对话记忆 + Canon) ──
        from PyQt5.QtWidgets import QTabWidget as _SubTW
        self._tab_world = _SubTW()
        self._tab_world.addTab(self.tab_outline, "故事大纲")
        self._tab_world.addTab(self.tab_memory, "对话记忆")
        self._tab_world.addTab(self.tab_canon, "Canon 设定")
        tab_list.append((self._tab_world, "📝 世界构建"))

        # ── 🎭 角色系统(子Tab: 角色与世界 + 技能库 + 伏笔检查) ──
        self._tab_chars = _SubTW()
        self._tab_chars.addTab(self.tab_charlib, "角色与世界")
        self._tab_chars.addTab(self.tab_skills, "技能库")
        # v2.23.4: 伏笔检查从独立 Tab 移入角色系统
        from ui.foreshadow_tab import ForeshadowTab
        self.tab_foreshadow = ForeshadowTab(mw=self)
        self._tab_chars.addTab(self.tab_foreshadow, "🪤 伏笔检查")
        tab_list.append((self._tab_chars, "🎭 角色系统"))

        if self.tab_lifespan is not None:
            tab_list.append((self.tab_lifespan, "寿元台账"))

        # ── ⚙️ 生成引擎(子Tab: 生成控制 + 工作流) ──
        self._tab_engine = _SubTW()
        self._tab_engine.addTab(self.tab_generation, "生成控制")
        # 工作流面板加入生成引擎组
        self.tab_book_splitter = BookSplitterTab()
        tab_list += [
            (self._tab_engine, "⚙️ 生成引擎"),
            (self.tab_editor, "章节编辑器"),
            (self.tab_book_splitter, "📚 拆书学习"),
        ]

        # ── 🛠 AI 工具箱(v2.23.4: 直接用 AI 修改章节) ──
        from ui.ai_toolbox_tab import AIToolboxTab
        self.tab_ai_toolbox = AIToolboxTab(mw=self)
        self.tab_ai_toolbox.request_ai_modify.connect(
            self._on_ai_toolbox_modify)
        tab_list.append((self.tab_ai_toolbox, "🛠 AI 工具箱"))

        # ── 📊 番茄榜单(v2.23.4) ──
        from ui.fanqie_rank_tab import FanqieRankTab
        self.tab_fanqie_rank = FanqieRankTab(mw=self)
        self.tab_fanqie_rank.request_rescan.connect(
            self._on_fanqie_rank_rescan)
        self.tab_fanqie_rank.request_retry_details.connect(
            self._on_fanqie_retry_details)
        tab_list.append((self.tab_fanqie_rank, "📊 番茄榜单"))

        # DEBUG 面板(最后一个 Tab)
        self.tab_debug = DebugPanel()
        tab_list.append((self.tab_debug, "🔧 DEBUG"))
        for w, n in tab_list:
            self.tabs.addTab(w, n)
        ml.addWidget(self.tabs, 1)

    def _build_statusbar(self):
        sb = QStatusBar();
        # ───── Phase B:盘古手册 + 批量巡检 顶部工具栏 ─────
        _tb_pangu = self.addToolBar("盘古工具")
        _tb_pangu.setMovable(False)
        _act_manual = QAction("❓ 盘古手册", self)
        _act_manual.triggered.connect(self._on_pangu_show_manual)
        _tb_pangu.addAction(_act_manual)
        _act_batch = QAction("🛡️ 全书巡检", self)
        _act_batch.triggered.connect(self._on_pangu_batch_scan)
        _tb_pangu.addAction(_act_batch)
        # Phase C-2:风格库编辑器
        _act_style_edit = QAction("🎨 风格库", self)
        _act_style_edit.setToolTip("打开盘古风格库可视化编辑器")
        _act_style_edit.triggered.connect(self._on_pangu_style_editor)
        _tb_pangu.addAction(_act_style_edit)
        # Phase C-1:差异化状态查看
        _act_diff_info = QAction("🎲 差异化", self)
        _act_diff_info.setToolTip("查看章节差异化(防 AI 套路)当前状态和下一章预览参数")
        _act_diff_info.triggered.connect(self._on_pangu_diff_info)
        _tb_pangu.addAction(_act_diff_info)
        # 主题切换(左键循环,右键选择)
        from PyQt5.QtWidgets import QToolButton
        self.btn_theme_toggle = QToolButton()
        self.btn_theme_toggle.setText("🎨 主题切换")
        self.btn_theme_toggle.setToolTip("左键循环 / 右键选主题\n☀️浅色→🌙暗黑→🌿护眼绿→🌅暖黄→⚡盘古黑金")
        self.btn_theme_toggle.clicked.connect(self._on_toggle_theme)
        self.btn_theme_toggle.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_theme_toggle.customContextMenuRequested.connect(
            lambda p: self._show_theme_menu())
        _tb_pangu.addWidget(self.btn_theme_toggle)
        # AI 智能取名(放工具栏,方便访问)
        _act_naming = QAction("🎭 智能换名", self)
        _act_naming.setToolTip("AI生成角色名,选中后全文替换(正文+大纲+角色库)")
        _act_naming.triggered.connect(self._open_ai_naming)
        _tb_pangu.addAction(_act_naming)
        self.setStatusBar(sb)
        sb.addWidget(QLabel(f"© 2026 {APP_NAME} {APP_VERSION}"))
        self._status_stats = QLabel("0章 · 0字")
        self._status_stats.setStyleSheet("padding:2px 10px; color:#7a7a7a;")
        sb.addPermanentWidget(self._status_stats)
        # 任务计时器(中间)
        self._status_task = QLabel("")
        self._status_task.setStyleSheet(
            "padding:2px 12px; color:#1a73e8; font-weight:bold;")
        sb.addPermanentWidget(self._status_task)
        self._task_start_time = None
        self._task_current_name = ""
        self._task_timer = QTimer(self)
        self._task_timer.timeout.connect(self._tick_task_timer)
        self._task_timer.setInterval(1000)
        # 状态指示器(右侧)
        self._status_indicator = QLabel("● 空闲")
        self._status_indicator.setStyleSheet(
            "color: #7a7a7a; font-weight: bold; padding: 2px 8px;")
        sb.addPermanentWidget(self._status_indicator)

    def _connect_signals(self):
        # 常用快捷键
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(
            lambda: self._switch_to_tab(self.tab_generation))
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(
            lambda: self._switch_to_tab(self.tab_editor))
        QShortcut(QKeySequence("F5"), self).activated.connect(
            self._refresh_chapter_list)

        # 创作设置
        self.tab_settings.btn_gen_insp.clicked.connect(self.gen_inspiration)
        self.tab_settings.btn_regen_insp.clicked.connect(self.gen_inspiration)
        self.tab_settings.btn_gen_title.clicked.connect(self.gen_title)
        self.tab_settings.btn_regen_title.clicked.connect(self.gen_title)
        self.tab_settings.btn_import_txt.clicked.connect(
            lambda: self._import_to(self.tab_settings.inspiration_edit))
        self.tab_settings.btn_prelogin.clicked.connect(self.prelogin_ai)
        self.tab_settings.ai_group.buttonClicked.connect(self._on_ai_changed)
        # v1.63:上下文设置变化 → 重算字数预估
        try:
            self.tab_generation.ctx_settings_changed.connect(
                self._update_ctx_estimate)
        except Exception:
            pass

        # 大纲
        self.tab_outline.btn_gen_all.clicked.connect(self.gen_outline_all)
        self.tab_outline.btn_regen_all.clicked.connect(self.gen_outline_all)
        self.tab_outline.btn_gen_seed.clicked.connect(lambda: self.gen_outline_part("故事种子"))
        self.tab_outline.btn_gen_wv.clicked.connect(lambda: self.gen_outline_part("世界观"))
        self.tab_outline.btn_gen_lo.clicked.connect(lambda: self.gen_outline_part("LO世界观层"))
        self.tab_outline.btn_gen_struct.clicked.connect(lambda: self.gen_outline_part("故事结构"))
        self.tab_outline.btn_gen_ch.clicked.connect(lambda: self.gen_outline_part("章节大纲"))
        self.tab_outline.btn_rename.clicked.connect(self.open_rename_dialog)
        self.tab_outline.btn_extract_intro.clicked.connect(self.extract_intro)
        self.tab_outline.btn_import_special.clicked.connect(
            lambda: self._import_to(self.tab_outline.special_edit))

        # 生成控制 - 浏览器
        self.tab_generation.btn_launch.clicked.connect(self.launch_browser)
        self.tab_generation.btn_close.clicked.connect(self.close_browser)
        self.tab_generation.btn_new_chat.clicked.connect(self._manual_new_chat)
        if hasattr(self.tab_generation, "btn_mirror_login"):
            self.tab_generation.btn_mirror_login.clicked.connect(
                self._open_login_mirror)
        self.tab_generation.btn_go.clicked.connect(self._goto_url)
        self.tab_generation.btn_grab.clicked.connect(self.grab_response)
        # v2.21.5:登录副 AI 按钮
        if hasattr(self.tab_generation, "btn_open_aux"):
            self.tab_generation.btn_open_aux.clicked.connect(self._open_aux_for_login)

        # 创作设置 ai_group(单选) ↔ 生成控制 site_combo(下拉) 双向同步
        def _ai_radio_to_combo(btn):
            name = btn.text()
            if name in AI_URLS:
                cur = self.tab_generation.site_combo.currentText()
                if cur != name:
                    self.tab_generation.site_combo.blockSignals(True)
                    self.tab_generation.site_combo.setCurrentText(name)
                    self.tab_generation.site_combo.blockSignals(False)
                    self.tab_generation.url_input.setText(AI_URLS[name])
            elif name == "自定义":
                u = self.tab_settings.custom_url.text().strip()
                if u:
                    self.tab_generation.url_input.setText(u)
        self.tab_settings.ai_group.buttonClicked.connect(_ai_radio_to_combo)

        def _ai_combo_to_radio(name):
            for btn in self.tab_settings.ai_group.buttons():
                if btn.text() == name and not btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                    break
        self.tab_generation.site_combo.currentTextChanged.connect(_ai_combo_to_radio)

        # 生成控制 - 任务
        self.tab_generation.btn_start.clicked.connect(self.start_generation)
        self.tab_generation.btn_pause.clicked.connect(self.pause_generation)
        self.tab_generation.btn_gen_one.clicked.connect(self.gen_first_chapter)
        self.tab_generation.btn_gen_three.clicked.connect(self.gen_golden_three)
        self.tab_generation.btn_regen_three.clicked.connect(self.gen_golden_three)
        self.tab_generation.btn_gen_next.clicked.connect(self.gen_next_chapter_single)

        # 章节编辑
        self.tab_editor.save_requested.connect(self.save_current_chapter)
        self.tab_editor.optimize_requested.connect(self.optimize_chapter)
        self.tab_editor.save_all_requested.connect(self.save_all_chapters)

        # 对话记忆
        self.tab_memory.btn_gen_full_memory.clicked.connect(self.gen_full_memory)
        self.tab_memory.btn_stop_full_memory.clicked.connect(self.stop_full_memory)
        self.tab_memory.btn_extract_chars.clicked.connect(self.extract_characters)
        self.tab_memory.btn_clear_chars.clicked.connect(
            lambda: self.tab_memory.chars_edit.clear())
        self.tab_memory.btn_gen_all_sum.clicked.connect(self.gen_all_missing_summaries)
        self.tab_memory.btn_gen_cur_sum.clicked.connect(self.gen_current_summary)
        self.tab_memory.btn_clear_sum.clicked.connect(
            lambda: self.tab_memory.summaries_edit.clear())
        self.tab_memory.btn_extract_lt.clicked.connect(self.extract_long_term)
        self.tab_memory.btn_clear_lt.clicked.connect(
            lambda: self.tab_memory.long_term_edit.clear())
        self.tab_memory.btn_preview.clicked.connect(self._refresh_memory_preview)

        # Canon Tab
        self.tab_canon.btn_extract_now.clicked.connect(self._canon_extract_all_chapters)

        # 角色与世界 Tab
        self.tab_charlib.btn_extract_from_chapters.clicked.connect(self._charlib_extract_from_chapters)
        # v1.02:✨ 勾上时,如果检测到"已有章节但 6 库还空" → 主动询问要不要立刻补抽
        self.tab_charlib.chk_auto_extract.stateChanged.connect(
            self._on_chk_auto_extract_toggled)
        # v1.76 BUG-056:伏笔追踪 Tab 的 AI 重评估按钮
        if hasattr(self.tab_charlib, "btn_reeval_fore"):
            self.tab_charlib.btn_reeval_fore.clicked.connect(self._reeval_zero_pay_at)
        # v1.77 BUG-057:威胁承诺 Tab 的 AI 重评估按钮
        if hasattr(self.tab_charlib, "btn_reeval_promise"):
            self.tab_charlib.btn_reeval_promise.clicked.connect(
                self._reeval_zero_deadline_promise)

        # 章节编辑器: 风格检测 + 备选版本
        self.tab_editor.btn_style_check.clicked.connect(self._on_style_check)
        self.tab_editor.btn_regen_alt.clicked.connect(self._on_regen_alt)

        # ChapterEditor 盘古超级系统按钮(本地词扫已在 ChapterEditor 内消化)
        self.tab_editor.pangu_qcheck_requested.connect(self._on_pangu_qcheck)
        self.tab_editor.laodao_critique_requested.connect(self._on_laodao_critique)
        self.tab_editor.pangu_spiral_requested.connect(self._on_pangu_spiral)
        self.tab_editor.pangu_preview_prompt_requested.connect(self._on_pangu_preview_prompt)
        # BUG-014:用户在元信息面板点了"下一章选项"按钮 → 记到 _user_picked_next_option,
        # _send_next_chapter 会把它当作开局指引注入 prompt
        self.tab_editor.next_option_picked.connect(self._on_pangu_next_option_picked)
        # v1.10:TTS 朗读
        self.tab_editor.tts_play_requested.connect(self._on_tts_play)
        self.tab_editor.tts_pause_requested.connect(self._on_tts_pause)
        self.tab_editor.tts_stop_requested.connect(self._on_tts_stop)
        self.tab_editor.tts_speed_changed.connect(self._on_tts_speed_changed)
        # v1.32:13 法对话诊断
        self.tab_editor.dialogue_critic_requested.connect(self._on_dialogue_critic)
        # v1.38: 拆书章节 AI 分析
        self.tab_book_splitter.request_chapter_analysis.connect(
            self._on_book_chapter_analyze)
        # 项目主页已移到启动器(tab_home 不再存在)
        self._init_tts()
        # v1.21:加 视图 菜单 + Ctrl+Shift+D 快捷键(corner widget click bug 的兜底入口)
        try:
            self._setup_view_menu()
        except Exception as _e:
            print(f"[Theme] 视图菜单创建失败: {_e}", flush=True)
        self.tab_settings.btn_pangu_wl_apply.clicked.connect(self._on_pangu_apply_whitelist)
        # CreationSettings 盘古快捷工具
        self.tab_settings.btn_pangu_style.clicked.connect(self._on_pangu_style_match)
        self.tab_settings.btn_pangu_arch.clicked.connect(
            lambda: self._on_pangu_mode("architect"))
        self.tab_settings.btn_pangu_dream.clicked.connect(
            lambda: self._on_pangu_mode("dreamweaver"))
        self.tab_settings.btn_pangu_alch.clicked.connect(
            lambda: self._on_pangu_mode("alchemist"))
        self.tab_settings.btn_pangu_sculpt.clicked.connect(
            lambda: self._on_pangu_mode("sculptor"))
        # 盘古开关 → 运行时切换
        self.tab_settings.pangu_check.toggled.connect(self._on_pangu_toggle)

        # Skill Tab
        self.tab_skills.btn_test.clicked.connect(self._skill_test_run)

        # ChapterEditor 右键菜单(应用技能)
        self.tab_editor.content_edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_editor.content_edit.customContextMenuRequested.connect(
            self._show_chapter_editor_menu)

        # E 模块:对话槽管理
        sw = self.tab_generation.conv_switcher
        sw.btn_save_slot.clicked.connect(self._conv_save_current_slot)
        sw.btn_switch.clicked.connect(self._conv_switch_selected)
        sw.btn_new_slot.clicked.connect(self._conv_open_new_dialog)

    # ---- 浏览器控制 ----
    def launch_browser(self):
        if not SELENIUM_AVAILABLE:
            QMessageBox.critical(
                self, "缺少依赖",
                "未安装 Selenium,无法挂载真实浏览器。\n\n"
                "请在终端运行:\n"
                "  pip install -U selenium\n\n"
                "(selenium 4.6+ 自动管理 chromedriver,无需单独装。\n"
                "两种内核模式:\n"
                "  • Chrome 调试 — attach 已开调试 Chrome,程序与浏览器解耦,最稳\n"
                "  • 系统 Edge — standalone Edge)")
            return
        ch = self.tab_generation.selected_kernel_channel()
        self.tab_generation.btn_launch.setEnabled(False)
        self.tab_generation.btn_close.setEnabled(True)
        mode_label = {
            "chrome": "Chrome attach 调试模式",
            "msedge": "Edge standalone",
        }.get(ch, "Chrome standalone")
        self.tab_generation.log(f"准备启动浏览器({mode_label})...", "info")
        # 传递隐藏浏览器标记
        self.worker._hide_browser = (
            hasattr(self.tab_generation, 'chk_hide_browser') and
            self.tab_generation.chk_hide_browser.isChecked())
        self.worker.start(channel=ch)

    # ============ v2.25.0 扫码镜像登录(防提示词露屏) ============
    def _open_login_mirror(self):
        """浏览器保持隐藏,弹出登录页镜像:worker 截图流 + 点击转发。
        用户在镜像里扫码/点击完成登录,浏览器窗口全程不露面。"""
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "浏览器未就绪",
                "请先点「🚀 启动浏览器」(建议勾选 🫥 隐藏浏览器),\n"
                "浏览器就绪后再打开镜像登录。")
            return
        if getattr(self, "_mirror_dlg", None):
            self._mirror_dlg.raise_()
            return
        from ui.login_mirror import LoginMirrorDialog
        dlg = LoginMirrorDialog(self)
        dlg.click_requested.connect(
            lambda x, y: self.worker.submit(
                {"action": "mirror_click", "x": x, "y": y}))
        dlg.finished.connect(self._close_login_mirror)
        self._mirror_dlg = dlg
        self._mirror_timer = QTimer(self)
        self._mirror_timer.setInterval(1500)
        self._mirror_timer.timeout.connect(
            lambda: self.worker.submit({"action": "mirror_shot"}))
        self._mirror_timer.start()
        self.worker.submit({"action": "mirror_shot"})   # 立即出第一帧
        dlg.show()

    def _on_mirror_frame(self, png_bytes, css_w, css_h):
        dlg = getattr(self, "_mirror_dlg", None)
        if dlg:
            dlg.update_frame(png_bytes, css_w, css_h)

    def _close_login_mirror(self, *_):
        t = getattr(self, "_mirror_timer", None)
        if t:
            t.stop()
        self._mirror_timer = None
        self._mirror_dlg = None

    def _auto_start_browser(self):
        """启动时自动连接浏览器+导航到上次AI站点"""
        if not SELENIUM_AVAILABLE:
            return
        self.tab_generation.log("🚀 自动启动浏览器(上次设置)...", "info")
        self.launch_browser()

    def _tts_alert(self, text):
        """语音报警(简单的一句话提醒,不走TTS队列)"""
        import threading
        def _speak():
            try:
                # 优先用 edge-tts
                import asyncio
                import edge_tts
                import tempfile, os
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    tmp = f.name
                async def _gen():
                    comm = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                    await comm.save(tmp)
                asyncio.run(_gen())
                # 播放
                try:
                    import pygame
                    if not pygame.mixer.get_init():
                        pygame.mixer.init()
                    pygame.mixer.music.load(tmp)
                    pygame.mixer.music.play()
                    import time
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.1)
                except Exception:
                    pass
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            except ImportError:
                # 没有 edge-tts,用系统蜂鸣
                try:
                    import winsound
                    winsound.Beep(800, 500)
                    winsound.Beep(600, 500)
                    winsound.Beep(800, 500)
                except Exception:
                    pass
        threading.Thread(target=_speak, daemon=True).start()

    def _on_browser_started(self):
        # 浏览器就绪后,自动跳到当前选定的 AI 网站
        url = self.tab_generation.url_input.text().strip()
        if url:
            self.worker.submit({"action": "navigate", "url": url})

    def close_browser(self):
        self.worker.stop()
        self.tab_generation.btn_launch.setEnabled(True)
        self.tab_generation.btn_close.setEnabled(False)

    def _manual_new_chat(self):
        """手动开启新对话"""
        if not self.worker.is_ready():
            QMessageBox.warning(self, "提示", "请先启动浏览器")
            return
        url = self.tab_generation.url_input.text().strip()
        self.worker.submit({"action": "new_chat", "url": url})
        self.tab_generation.log("🔄 手动新建对话 — AI上下文已清空", "success")

    def _check_auto_shutdown(self):
        """批量生成完毕后自动保存+关机(不弹窗)"""
        if not hasattr(self.tab_generation, 'chk_shutdown'):
            return
        if not self.tab_generation.chk_shutdown.isChecked():
            return
        self.tab_generation.log("🔌 批量生成完毕,保存项目后关机...", "success")
        try:
            self.save_project()
            self.tab_generation.log("✅ 项目已保存,30秒后关机", "success")
        except Exception as e:
            self.tab_generation.log(f"⚠ 保存失败: {e},仍然关机", "warn")
        import subprocess, sys
        if sys.platform == "win32":
            subprocess.Popen("shutdown /s /t 30", shell=True)
        else:
            subprocess.Popen("shutdown -h +1", shell=True)

    def _goto_url(self):
        if not self.worker.is_ready():
            QMessageBox.warning(self, "提示", "请先点『启动浏览器』")
            return
        url = self.tab_generation.url_input.text().strip()
        if not url:
            return
        if not url.startswith("http"):
            url = "https://" + url
            self.tab_generation.url_input.setText(url)
        self.worker.submit({"action": "navigate", "url": url})

    def _open_aux_for_login(self):
        """v2.21.5:打开副 AI 网站让用户登录(首次使用必须)。
        登录后 Chrome 用户数据目录会记 cookie,以后自动用。"""
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "提示",
                "请先点『🚀 启动浏览器』启动主浏览器,然后再登录副 AI。")
            return
        if not hasattr(self.tab_generation, "aux_url_input"):
            return
        aux_url = self.tab_generation.aux_url_input.text().strip()
        if not aux_url:
            QMessageBox.warning(self, "提示", "副 AI URL 为空")
            return
        if not aux_url.startswith("http"):
            aux_url = "https://" + aux_url
            self.tab_generation.aux_url_input.setText(aux_url)
        aux_site = self.tab_generation.aux_site_combo.currentText()
        self.tab_generation.log(
            f"🔓 打开 {aux_site} 副 AI 标签,请在浏览器里完成登录。", "info")
        # navigate 走 _goto,会自动开新标签或复用已有标签
        self.worker.submit({"action": "navigate", "url": aux_url})
        # 提示用户
        QMessageBox.information(
            self, "登录副 AI",
            f"已在浏览器打开 {aux_site}({aux_url})。\n\n"
            f"请在浏览器里完成登录。\n"
            f"登录一次,Chrome 永久记住(用户数据目录:NovelAI_Browser_Data)。\n\n"
            f"登录完不需要关闭这个标签 — 它会留着,让主程序自动切换使用。")

    def _on_ai_changed(self, button):
        ai = button.text()
        url = AI_URLS.get(ai)
        if not url and ai == "自定义":
            url = self.tab_settings.custom_url.text().strip()
        if url:
            self.tab_generation.url_input.setText(url)
            self.tab_generation.site_combo.setCurrentText(ai if ai in AI_URLS else "DeepSeek")
            self.tab_generation.log(f"已切换到 {ai}: {url}", "info")
            if self.worker.is_ready():
                self.worker.submit({"action": "navigate", "url": url})
        # AI 站点联动:ChatGPT/镜像站 → 3 checkbox 全开;其他 AI → 全关
        # 用户原话:"除了镜像站和GPT 其他都不勾选"
        # 注意:radio text 是 "ChatGPT"(不是 AI_URLS 里的 "ChatGPT镜像")
        try:
            tg = self.tab_generation
            if ai in ("ChatGPT", "ChatGPT镜像"):
                tg.auto_save.setChecked(True)
                tg.auto_grab.setChecked(True)
                tg.use_attachment.setChecked(True)
                tg.log(f"已切到 {ai} → 自动保存TXT/自动抓取/附件模式 全部打开", "info")
            elif ai == "自定义":
                pass  # 不动用户当前选择
            else:
                tg.auto_save.setChecked(False)
                tg.auto_grab.setChecked(False)
                tg.use_attachment.setChecked(False)
                tg.log(f"已切到 {ai} → 自动保存TXT/自动抓取/附件模式 全部关闭(此站无审核,直发更快)", "info")
        except Exception:
            pass

    def _init_demo_chapters(self):
        # 不再预填示例章节,启动时章节列表为空
        # 用户通过「新增章节」或「新建空白创作」按钮自行添加
        self._refresh_chapter_list()

    def _refresh_chapter_list(self):
        self.chapter_list.clear()
        for i, ch in enumerate(self.chapters):
            _title = ch.get("title", "")
            _content = ch.get("content", "")
            _wc = len(_content.replace(" ", "").replace("\n", ""))

            # 前缀标记
            prefix = ""
            if ch.get("locked"):
                prefix = "🔒 "
            # 字数后缀
            if _wc > 0:
                _display = f"{prefix}{_title} ({_wc}字)"
            else:
                _display = f"{prefix}{_title}"

            _item = QListWidgetItem(_display)

            # 颜色标记
            if ch.get("locked"):
                _item.setForeground(QColor("#999"))
                _item.setToolTip("已锁定 — 右键解锁")
            elif _wc > 0 and _wc < 1000:
                _item.setForeground(QColor("#e74c3c"))
                _item.setToolTip(f"⚠ 字数偏少({_wc}字)")
            elif ch.get("emotion_scores"):
                emo = ch["emotion_scores"]
                t = emo.get("tension", 5)
                s = emo.get("satisfaction", 5)
                if t + s >= 14:
                    _item.setForeground(QColor("#e67e22"))
                    _item.setToolTip(f"🔥 高燃章(紧张{t}+爽感{s})")

            self.chapter_list.addItem(_item)
        if 0 <= self.current_chapter_index < len(self.chapters):
            self.chapter_list.setCurrentRow(self.current_chapter_index)
        n = len(self.chapters)
        total_wc = sum(len(ch.get("content", "").replace(" ", "").replace("\n", ""))
                       for ch in self.chapters)
        if hasattr(self, "lbl_chapter_count"):
            if n == 0:
                self.lbl_chapter_count.setText("章节列表 (空)")
            else:
                self.lbl_chapter_count.setText(
                    f"章节列表 (共 {n} 章 · {total_wc:,}字 · Ctrl多选 · 可拖拽排序)")
        # 状态栏 + 窗口标题同步
        if hasattr(self, "_status_stats"):
            avg = total_wc // n if n > 0 else 0
            target = 300  # 默认目标章数
            try:
                target = self.tab_settings.get_chapter_count() or 300
            except Exception:
                pass
            pct = min(100, int(n / target * 100)) if target > 0 else 0
            self._status_stats.setText(
                f"{n}章 · {total_wc:,}字 · 均{avg:,}字/章 · 进度{n}/{target}({pct}%)")
        self._update_window_title()
        # v1.63: 章节数变了 → 重算上下文注入字数预估
        try:
            self._update_ctx_estimate()
        except Exception:
            pass
        # v2.23.4: 同步 AI 工具箱章节下拉
        try:
            if hasattr(self, "tab_ai_toolbox"):
                self.tab_ai_toolbox.refresh_chapters()
        except Exception:
            pass

    def _update_task_monitor(self, task_id, status, retry=0):
        """更新任务监控状态"""
        from datetime import datetime
        if not hasattr(self, "_task_monitor"):
            self._task_monitor = {}
        self._task_monitor[task_id] = {
            "status": status, "time": datetime.now(), "retry": retry}
        # 显示在状态栏
        if hasattr(self, "_status_indicator"):
            self._status_indicator.setText(f"● {task_id}: {status}")
            if "❌" in status:
                self._status_indicator.setStyleSheet(
                    "color:#e74c3c; font-weight:bold; padding:2px 8px;")
            elif "✅" in status:
                self._status_indicator.setStyleSheet(
                    "color:#1f8b4d; font-weight:bold; padding:2px 8px;")
            elif "🔄" in status:
                self._status_indicator.setStyleSheet(
                    "color:#b8651b; font-weight:bold; padding:2px 8px;")
            else:
                self._status_indicator.setStyleSheet(
                    "color:#1a73e8; font-weight:bold; padding:2px 8px;")
        # 也输出到日志
        self.tab_generation.log(f"[监控] {task_id}: {status}", "info")
        # 启动/停止计时器
        if "📤" in status:
            # 任务开始
            self._task_current_name = task_id
            self._task_start_time = datetime.now()
            self._task_timer.start()
            self._tick_task_timer()
        elif "✅" in status or "❌" in status:
            # 任务完成/失败
            elapsed = ""
            if self._task_start_time:
                secs = int((datetime.now() - self._task_start_time).total_seconds())
                elapsed = f" ({secs}秒)"
            self._status_task.setText(f"{task_id}: {status}{elapsed}")
            self._task_timer.stop()
            self._task_start_time = None

    def _tick_task_timer(self):
        """每秒更新任务计时"""
        if self._task_start_time:
            from datetime import datetime
            secs = int((datetime.now() - self._task_start_time).total_seconds())
            mins = secs // 60
            s = secs % 60
            time_str = f"{mins}:{s:02d}" if mins > 0 else f"{s}秒"
            self._status_task.setText(
                f"⏱ {self._task_current_name}  {time_str}")
            # 超时变色
            if secs > 60:
                self._status_task.setStyleSheet(
                    "padding:2px 12px; color:#e74c3c; font-weight:bold;")
            elif secs > 30:
                self._status_task.setStyleSheet(
                    "padding:2px 12px; color:#b8651b; font-weight:bold;")
            else:
                self._status_task.setStyleSheet(
                    "padding:2px 12px; color:#1a73e8; font-weight:bold;")

    def _switch_to_tab(self, widget):
        """智能切Tab:支持嵌套子Tab"""
        idx = self.tabs.indexOf(widget)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
            return
        for group in [getattr(self, '_tab_world', None),
                      getattr(self, '_tab_chars', None),
                      getattr(self, '_tab_engine', None)]:
            if group is None:
                continue
            sub_idx = group.indexOf(widget)
            if sub_idx >= 0:
                parent_idx = self.tabs.indexOf(group)
                if parent_idx >= 0:
                    self.tabs.setCurrentIndex(parent_idx)
                group.setCurrentIndex(sub_idx)
                return

    def _update_window_title(self, suffix=""):
        """更新窗口标题: APP名 — 项目名 [状态]"""
        parts = [APP_FULL]
        proj = getattr(self, "_project_title", "") or ""
        if not proj and getattr(self, "current_project_file", None):
            proj = Path(self.current_project_file).stem
        if proj:
            parts.append(proj)
        if suffix:
            parts.append(suffix)
        self.setWindowTitle(" — ".join(parts))

    # ──── v2.23.4: 左侧导航栏辅助方法 ────

    def _on_nav_step_by_name(self, keyword):
        """创作流程步骤点击 → 按 Tab 名称关键词匹配切换"""
        try:
            for i in range(self.tabs.count()):
                if keyword in self.tabs.tabText(i):
                    self.tabs.setCurrentIndex(i)
                    return
        except Exception:
            pass

    def _on_nav_step(self, tab_idx):
        """创作流程步骤点击 → 切到对应 Tab(兼容旧索引方式)"""
        try:
            if 0 <= tab_idx < self.tabs.count():
                self.tabs.setCurrentIndex(tab_idx)
        except Exception:
            pass

    def _on_nav_open_project(self):
        """左栏"打开项目"按钮"""
        try:
            path = QFileDialog.getExistingDirectory(
                self, "选择项目文件夹", str(self.project_dir))
            if path:
                self._open_project_by_path(path)
        except Exception:
            pass

    def _on_recent_project_clicked(self, item):
        """最近项目列表双击"""
        path = item.data(Qt.UserRole)
        if path:
            try:
                from pathlib import Path as _P
                if _P(path).exists():
                    self._open_project_by_path(path)
            except Exception:
                pass

    def _load_recent_to_sidebar(self):
        """刷新左栏最近项目列表"""
        try:
            rl = getattr(self, "_recent_list", None)
            if not rl:
                return
            rl.clear()
            from PyQt5.QtCore import QSettings
            recent = QSettings("NovelAI", "UI").value(
                "recent_projects", [], type=list) or []
            from pathlib import Path as _P
            from datetime import datetime
            for path in recent[:8]:
                p = _P(path)
                if not p.exists():
                    continue
                try:
                    mtime = datetime.fromtimestamp(p.stat().st_mtime)
                    time_str = mtime.strftime("%m-%d %H:%M")
                except Exception:
                    time_str = ""
                label = f"{p.name}\n{time_str}" if time_str else p.name
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, str(p))
                item.setSizeHint(QSize(0, 36))
                rl.addItem(item)
        except Exception:
            pass

    def _on_chapter_clicked(self, item):
        idx = self.chapter_list.row(item)
        if not (0 <= idx < len(self.chapters)): return
        # 自动保存当前章
        if 0 <= self.current_chapter_index < len(self.chapters):
            _cur = self.chapters[self.current_chapter_index]
            # v1.92 BUG-066:已锁定章节切走时跳过写回,保护"已确认内容"
            if _cur.get("locked"):
                _ch_no = self.current_chapter_index + 1
                try:
                    self.tab_generation.log(
                        f"⚠ 第{_ch_no}章已锁定,切走时跳过编辑器写回(改动未保存)。"
                        f"如需修改请先右键解锁本章。", "warn")
                except Exception:
                    pass
            else:
                _cur["title"] = self.tab_editor.title_input.text()
                _cur["content"] = self.tab_editor.content_edit.toPlainText()
        self.current_chapter_index = idx
        ch = self.chapters[idx]
        self.tab_editor.show_chapter(ch, idx)  # 记录索引,供风格检测/备选版本使用
        self._switch_to_tab(self.tab_editor)

    # ---- 章节管理 ----
    def _on_chapter_list_context_menu(self, pos):
        """章节列表右键菜单 — 全部操作"""
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self.chapter_list)
        item = self.chapter_list.itemAt(pos)
        idx = self.chapter_list.row(item) if item else -1

        # ── 章节操作(有选中时) ──
        if item and 0 <= idx < len(self.chapters):
            ch = self.chapters[idx]
            menu.addAction("✏️ 重命名", self.rename_chapter)
            menu.addAction("🗑️ 删除选中", self.delete_chapter)
            menu.addSeparator()
            if ch.get("locked"):
                menu.addAction("🔓 解锁本章",
                    lambda: self._toggle_chapter_lock(idx, False))
            else:
                menu.addAction("🔒 锁定本章",
                    lambda: self._toggle_chapter_lock(idx, True))
            menu.addSeparator()

        # ── 通用操作(始终可用) ──
        menu.addAction("➕ 新增章节", self.add_chapter)
        menu.addSeparator()
        menu.addAction("📂 导入存档", self.open_project)
        menu.addAction("📁 新建空白创作", self.new_project)
        menu.addAction("📝 项目重命名", self.rename_project)
        menu.addAction("📁 新建目录", self.new_directory)
        menu.addAction("⬆️ 返回上级目录", self.back_directory)

        menu.exec_(self.chapter_list.viewport().mapToGlobal(pos))

    def _toggle_chapter_lock(self, idx, locked):
        """v1.92 BUG-066:切换章节锁定状态。
        locked=True 后:save/delete/rename/切走写回全部跳过,
        UI 章节标题前显示 🔒 标记。
        """
        if not (0 <= idx < len(self.chapters)):
            return
        ch = self.chapters[idx]
        # 锁定前如果有未保存的编辑器改动且当前正是这一章 → 先 flush 到 dict
        if locked and idx == self.current_chapter_index:
            try:
                ch["title"] = self.tab_editor.title_input.text() or ch.get("title", "")
                ch["content"] = self.tab_editor.content_edit.toPlainText()
            except Exception:
                pass
        ch["locked"] = bool(locked)
        self._refresh_chapter_list()
        # 锁定后重新选中,保持高亮
        try:
            self.chapter_list.setCurrentRow(idx)
        except Exception:
            pass
        _ch_no = idx + 1
        _ch_title = ch.get("title", "")
        if locked:
            msg = f"🔒 第{_ch_no}章『{_ch_title}』已锁定 — save/重命名/删除/写回均拦截"
        else:
            msg = f"🔓 第{_ch_no}章『{_ch_title}』已解锁"
        try:
            self.tab_generation.log(msg, "info")
            self.statusBar().showMessage(msg, 4000)
        except Exception:
            pass

    def add_chapter(self):
        n = len(self.chapters) + 1
        title, ok = QInputDialog.getText(self, "新增章节", "章节标题:", text=f"第{n}章 ")
        if ok and title:
            self.chapters.append({"title": title, "content": "", "locked": False})
            self.current_chapter_index = len(self.chapters) - 1
            self._refresh_chapter_list()
            self.tab_editor.load_chapter(title, "")
            self._switch_to_tab(self.tab_editor)

    def delete_chapter(self):
        selected = self.chapter_list.selectedItems()
        if not selected:
            return
        indices = sorted({self.chapter_list.row(item) for item in selected}, reverse=True)

        # 检查锁定
        locked = [self.chapters[i]["title"] for i in indices
                  if i < len(self.chapters) and self.chapters[i].get("locked")]
        if locked:
            QMessageBox.warning(self, "已锁定",
                f"以下章节已锁定,无法删除:\n{'、'.join(locked)}\n\n请先右键解锁。")
            return

        # 确认
        if len(indices) == 1:
            msg = f"删除『{self.chapters[indices[0]]['title']}』?"
        else:
            msg = f"删除选中的 {len(indices)} 章?"
        if QMessageBox.question(self, "确认", msg) == QMessageBox.Yes:
            for idx in indices:  # 从后往前删
                if idx < len(self.chapters):
                    self.chapters.pop(idx)
            self.current_chapter_index = -1
            self.tab_editor.load_chapter("", "")
            self._refresh_chapter_list()

    def _on_chapters_reordered(self):
        """拖拽排序后同步 self.chapters 顺序"""
        new_order = []
        for i in range(self.chapter_list.count()):
            item_text = self.chapter_list.item(i).text()
            # 从 item 文本反查原章节(去掉字数后缀和锁定前缀)
            for ch in self.chapters:
                title = ch.get("title", "")
                if title in item_text and ch not in new_order:
                    new_order.append(ch)
                    break
        if len(new_order) == len(self.chapters):
            self.chapters[:] = new_order
            self._refresh_chapter_list()
            self.tab_generation.log(f"📋 章节顺序已更新(拖拽排序)", "info")

    def rename_chapter(self):
        idx = self.chapter_list.currentRow()
        if idx < 0: return
        # v1.92 BUG-066:已锁定章节拒绝重命名
        if self.chapters[idx].get("locked"):
            QMessageBox.warning(
                self, "已锁定",
                f"『{self.chapters[idx]['title']}』已锁定,无法重命名。\n\n"
                f"请先右键解锁本章后再操作。")
            return
        title, ok = QInputDialog.getText(
            self, "重命名", "新标题:", text=self.chapters[idx]["title"])
        if ok and title:
            self.chapters[idx]["title"] = title
            self._refresh_chapter_list()

    def save_current_chapter(self, title, content):
        # 盘古超级系统:保存前自动本地词扫(0 token,只在日志提示)
        try:
            if getattr(self.tab_settings, "pangu_check", None) and self.tab_settings.pangu_check.isChecked():
                from pangu_system import get_default_engine as _pg_engine
                _content = self.tab_editor.content_edit.toPlainText()
                if _content.strip():
                    _r = _pg_engine().quick_chapter_lint(_content)
                    if not _r.get("pass"):
                        _msg = f"WARN 盘古词扫 {_r.get('score', 0)}分 - " + "; ".join(_r.get("issues", [])[:3])
                        if hasattr(self, "tab_generation"):
                            self.tab_generation.log(_msg, "warn")
        except Exception:
            pass
        if self.current_chapter_index < 0:
            QMessageBox.warning(self, "提示", "请先新增或选择章节")
            return
        # v1.92 BUG-066:已锁定章节拒绝写回
        if self.chapters[self.current_chapter_index].get("locked"):
            _ch_no = self.current_chapter_index + 1
            QMessageBox.warning(
                self, "已锁定",
                f"第{_ch_no}章『{self.chapters[self.current_chapter_index]['title']}』已锁定,无法保存修改。\n\n"
                f"如需修改请先右键解锁本章。")
            return
        self.chapters[self.current_chapter_index]["title"] = title
        self.chapters[self.current_chapter_index]["content"] = content
        self._refresh_chapter_list()
        self._save_chapter_to_disk(self.chapters[self.current_chapter_index])
        self.statusBar().showMessage(f"已保存:{title}", 3000)

    def _save_chapter_to_disk(self, chapter):
        title = self.tab_settings.get_title()
        proj = self.project_dir / re.sub(r'[\\/:*?"<>|]', '_', title)
        proj.mkdir(exist_ok=True)
        safe = re.sub(r'[\\/:*?"<>|]', '_', chapter["title"])
        path = proj / f"{safe}.txt"
        path.write_text(chapter["content"], encoding="utf-8")
        self.tab_generation.log(f"章节已保存到: {path}", "success")

    def save_all_chapters(self):
        if 0 <= self.current_chapter_index < len(self.chapters):
            self.chapters[self.current_chapter_index]["title"] = self.tab_editor.title_input.text()
            self.chapters[self.current_chapter_index]["content"] = self.tab_editor.content_edit.toPlainText()
        for ch in self.chapters:
            self._save_chapter_to_disk(ch)
        QMessageBox.information(self, "完成", f"已保存 {len(self.chapters)} 章到\n{self.project_dir}")

    # ---- AI 调用入口 ----
    def _send_to_ai(self, prompt, label="提示词", target=None, **extra):
        """
        统一的发送入口。
        target: 用于自动回填到 UI 的目标标识。可选:
            'inspiration' / 'title' / 'outline_full' / 'outline_part:<name>'
            / 'intro' / 'chapter' / 'golden_three' / 'optimize'
            None 表示只显示日志,弹窗手动选择。
        """
        # ── 防重复发送:同一个label正在等待中,不再发 ──
        if label in self._pending_task_targets:
            existing = self._pending_task_targets[label]
            # 工作流内部重试(retry)允许覆盖,普通任务不允许
            if existing.get("target") == target and "_retry" not in label.lower():
                self.tab_generation.log(
                    f"⚠ 「{label}」已在等待中,跳过重复发送", "warn")
                return
        if not SELENIUM_AVAILABLE:
            QMessageBox.critical(
                self, "缺少依赖",
                "未安装 Selenium,无法自动发送/抓取。\n\n"
                "请运行:\n"
                "  pip install -U selenium")
            return
        if not self.worker.is_ready():
            self._switch_to_tab(self.tab_generation)
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』,完成 AI 网站登录后再生成。")
            return
        # 同步 UI 设置到 worker(每次发送前都同步,允许用户中途切换)
        # ★ 智能开关:深度思考只对"长正文创作"任务有用,JSON 评分稽核反而会触发 R1 思考超时
        #   → 把短输出 / JSON 任务里的深度思考自动关掉(章节正文/优化/老刀点评/30 项质检 才开)
        try:
            # 自动判断当前任务是否适合深度思考
            _deep_targets = {
                "chapter", "golden_three", "optimize",
                "laodao_critique", "laodao_autofix",
                "pangu_qcheck", "pangu_autofix", "pangu_spiral",
            }
            user_wants_deep = (
                self.tab_settings.chk_deep_think.isChecked()
                if hasattr(self.tab_settings, "chk_deep_think") else False)
            # 章节正文 / 创作类 → 听用户的;JSON 短评分类 → 强制关
            if target in _deep_targets:
                self.worker._deep_think_enabled = user_wants_deep
            else:
                # canon_audit / rhythm_check / character_check / 抽取 / 摘要等 → 强制关
                self.worker._deep_think_enabled = False
                if user_wants_deep:
                    self.tab_generation.log(
                        f"  ↳ {label} 是 JSON/短输出任务,自动关闭深度思考(避免 R1 思考超时)",
                        "info")
        except Exception:
            self.worker._deep_think_enabled = False
        # 不再自动跳转到生成引擎(用户反馈:打断工作流)
        self.tab_generation.log(f"准备发送:{label} ({len(prompt)} 字符)", "info")
        # 记录这次任务的目标位置(由 _on_response_received 处理回填)
        # v1.97 BUG-071:字典写入 — key=label(== worker 侧 task_id),避免并发任务串台
        self._pending_task_targets[label] = {
            "target": target, "label": label,
            "_original_prompt": prompt, **extra}
        # 任务监控
        self._update_task_monitor(label, "📤 已发送")
        # 应用人类延迟
        type_delay = 30 if self.tab_settings.delay_check.isChecked() else 5
        # 投递任务
        # v2.21.4 双 AI 分工:数据任务路由到副 AI URL(走另一个浏览器标签页)
        url = self.tab_generation.url_input.text().strip()  # 默认走主 AI
        try:
            aux_enabled = (hasattr(self.tab_generation, "chk_aux_ai")
                           and self.tab_generation.chk_aux_ai.isChecked())
            if aux_enabled and target in SECONDARY_AI_TARGETS:
                aux_url = self.tab_generation.aux_url_input.text().strip()
                if aux_url:
                    url = aux_url
                    aux_site = self.tab_generation.aux_site_combo.currentText()
                    self.tab_generation.log(
                        f"  🤝 路由到副 AI: {aux_site} ({label})", "info")
                    # 状态指示变蓝
                    try:
                        self.tab_generation.aux_status_label.setStyleSheet(
                            "color:#1976d2; font-size:14px;")
                        self.tab_generation.aux_status_label.setToolTip(
                            f"● 副 AI 工作中: {label}")
                    except Exception:
                        pass
        except Exception as _e_aux:
            print(f"[副 AI 路由] 失败,降级到主 AI: {_e_aux}", flush=True)
        # 读取附件模式开关
        allow_att = self.tab_generation.use_attachment.isChecked() if hasattr(self.tab_generation, 'use_attachment') else True
        self.worker.submit({
            "action": "send_prompt",
            "prompt": prompt,
            "task_id": label,
            "url": url,
            "type_delay_ms": type_delay,
            "allow_attachment": allow_att,
            # ★ 给 RL 决策用的上下文
            "label": label,
            "target": target,
            "retry_used": extra.get("retry_used", 0),
            # v1.91 BUG-065:把 worker 侧降级要用的 meta 字段透传
            # (只透传 _xxx 前缀的"内部 meta"字段,跨线程安全的标量/字符串)
            **{k: v for k, v in extra.items()
               if k.startswith("_") and isinstance(v, (str, int, float, bool, type(None)))},
        })
        # v2.22.2 BUG-083:超时报警从"纯时间触发"改为"0字节卡 90 秒才报警"。
        # 旧逻辑:90 秒任务没完成就弹窗 — Qwen 写章节本来就要 4-5 分钟,每次都误报。
        # 新逻辑:90 秒到了去查 worker 报上来的最新字符数,字符数 > 0 → AI 在写字,
        # 静默不打扰;字符数 == 0 → 真卡了 → 弹窗 + TTS。
        # task_id == label(BUG-071 注释:key=label(== worker 侧 task_id))
        _task_label = label
        def _check_timeout():
            if _task_label not in self._pending_task_targets:
                return  # 任务早就完成了
            # v2.22.2 BUG-083:查 worker 报上来的最新字符进度(task_id == label)
            char_progress = 0
            if hasattr(self, "_task_char_progress"):
                char_progress = self._task_char_progress.get(_task_label, 0)
            if char_progress > 0:
                # AI 正在写字(Qwen 章节常态),静默不打扰
                return
            # v2.22.3 BUG-085: 思考期闸门
            # 实战(21:44:11):Canon抽取-第1章实际 17 秒后成功 985 字,但 90 秒
            # 时已被误报"0 字节无回复" — Qwen 思考阶段就是合法的 0 字节 0-90 秒。
            # worker 检测到 thinking_indicator 命中时 emit True。看到 True 就
            # 延期 60 秒再查,不报警。
            is_thinking = False
            if hasattr(self, "_task_thinking_state"):
                is_thinking = self._task_thinking_state.get(_task_label, False)
            if is_thinking:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(60000, _check_timeout)
                return
            # 真的 0 字节卡了 90 秒(且不在思考期) → 报警
            self.tab_generation.log(
                f"⏰ 「{_task_label}」已等待 90 秒,0 字节无回复(可能真卡住了)!",
                "warn")
            # TTS 语音报警
            try:
                self._tts_alert("注意,任务 90 秒没有任何回复,可能卡住了,请检查浏览器")
            except Exception:
                pass
            # 弹窗
            QMessageBox.warning(
                self, "⏰ 任务超时",
                f"「{_task_label}」已等待 90 秒,且 0 字节无任何回复。\n\n"
                f"可能原因:\n"
                f"  • 页面卡住了(刷新浏览器)\n"
                f"  • 网络断了(检查网络)\n"
                f"  • AI 服务异常(等会儿再试)\n\n"
                f"如果 AI 正在写字,这条不会弹 — 只有 0 字节才报警。\n\n"
                f"你可以:\n"
                f"  1. 继续等待\n"
                f"  2. 切到浏览器手动刷新\n"
                f"  3. 重新点击生成")
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(90000, _check_timeout)

    def _on_response_received(self, task_id, content):
        """worker 回调:某次提示词的 AI 回复已抓取完毕"""
        # v2.22.2 BUG-083:任务完成时清掉进度跟踪(防止字典无限增长)
        if hasattr(self, "_task_char_progress"):
            self._task_char_progress.pop(task_id, None)
        # v2.22.3 BUG-085:任务完成时清掉思考状态跟踪
        if hasattr(self, "_task_thinking_state"):
            self._task_thinking_state.pop(task_id, None)
        # ── 0字节/空内容自动重试 ──
        if not content or not content.strip():
            meta = self._pending_task_targets.get(task_id, {})
            _retry_0b = meta.get("_retry_0byte", 0)
            if _retry_0b < 3:
                meta["_retry_0byte"] = _retry_0b + 1
                self.tab_generation.log(
                    f"⚠ 「{task_id}」返回空内容(0字节),自动重试"
                    f"({_retry_0b+1}/3)...", "warn")
                # 更新任务监控
                self._update_task_monitor(task_id, "🔄 空内容重试", _retry_0b+1)
                # 重新发送(用原始prompt)
                prompt = meta.get("_original_prompt", "")
                if prompt:
                    self.worker.submit({
                        "action": "send_prompt",
                        "prompt": prompt,
                        "task_id": task_id,
                        "url": self.tab_generation.url_input.text().strip(),
                    })
                    return
            self.tab_generation.log(
                f"❌ 「{task_id}」连续3次返回空内容,放弃", "warn")
            self._update_task_monitor(task_id, "❌ 空内容放弃")
            self._pending_task_targets.pop(task_id, None)
            return

        # 任务监控:标记完成
        self._update_task_monitor(task_id, f"✅ 收到{len(content)}字")
        # v2.21.4:副 AI 状态指示恢复绿色(从工作中蓝色)
        try:
            if (hasattr(self.tab_generation, "chk_aux_ai")
                and self.tab_generation.chk_aux_ai.isChecked()):
                self.tab_generation.aux_status_label.setStyleSheet(
                    "color:#1f8b4d; font-size:14px;")
                self.tab_generation.aux_status_label.setToolTip(
                    f"● 副 AI 已启用 ({self.tab_generation.aux_site_combo.currentText()})")
        except Exception:
            pass
        # 从 pending 超时计时器中移除
        self._pending_task_targets.get(task_id, {}).pop("_retry_0byte", None)
        # ── BUG-077 直接回调(备用路径,根因已在 workflow_pipeline.py 修复) ──
        _crit_cb = getattr(self, "_critique_audit_callback", None)
        if _crit_cb and ("稽核" in (task_id or "") or "critique" in (task_id or "").lower()):
            kind, ch_num = _crit_cb
            self._critique_audit_callback = None
            self._pending_task_targets.pop(task_id, None)
            if content and content.strip():
                self.tab_generation.log(
                    f"任务『{task_id}』抓取成功,{len(content)} 字符", "success")
            self._on_critique_score_response(content, kind, ch_num)
            return
        # v1.97 BUG-071:从字典按 task_id 取本任务的 meta,避免并发任务串台
        # (task_id 由 worker 端从 submit 时的 task_id 字段透传回来,等于 _send_to_ai 的 label)
        # Phase B:盘古质检结果路由(优先级最高,不走原回填逻辑)
        try:
            tgt = self._pending_task_targets.get(task_id, {}).get("target", "")
            if tgt == "pangu_qcheck":
                # 拿当前章节原文做段落映射
                _cur_idx = self.tab_editor.current_index if hasattr(self.tab_editor, "current_index") else 0
                _orig = ""
                if self.chapters and isinstance(_cur_idx, int) and 0 <= _cur_idx < len(self.chapters):
                    _orig = self.chapters[_cur_idx].get("content", "")
                self._on_pangu_qcheck_response(content, _orig)
                self._pending_task_targets.pop(task_id, None)
                return
            if tgt == "pangu_spiral":
                QMessageBox.information(self, "🌀 盘古 P1-P7 螺旋诊断", content[:3000])
                self._pending_task_targets.pop(task_id, None)
                return
            if tgt == "pangu_mode":
                self.tab_generation.log(f"✓ 盘古模式切换完成:\n{content[:200]}", "info")
                self._pending_task_targets.pop(task_id, None)
                return
            if tgt == "pangu_autofix":
                # AI 修复完成 → 把内容回填当前章节
                meta = self._pending_task_targets.get(task_id, {})
                ch_idx = meta.get("ch_idx", -1)
                orig = meta.get("original_chapter", "")
                self._on_pangu_autofix_response(content, ch_idx, orig)
                self._pending_task_targets.pop(task_id, None)
                return
            if tgt == "laodao_critique":
                # 老刀毒舌点评返回 → 弹窗展示
                meta = self._pending_task_targets.get(task_id, {})
                self._on_laodao_critique_response(content, meta)
                self._pending_task_targets.pop(task_id, None)
                return
            if tgt == "laodao_autofix":
                # 老刀按建议重写返回 → 回填章节
                meta = self._pending_task_targets.get(task_id, {})
                ch_idx = meta.get("ch_idx", -1)
                orig = meta.get("original_chapter", "")
                self._on_laodao_autofix_response(content, ch_idx, orig)
                self._pending_task_targets.pop(task_id, None)
                return
        except Exception as _e_dispatch:
            # ★ BUG-031 治本:不再静默吞 dispatch 异常,且若 target 是已被路由的
            #   系列(pangu_* / laodao_*),即使 handler 抛了也绝不落到主 dispatch
            #   兜底(否则用户辛苦修出的内容被复制到剪贴板就算完)
            import traceback
            _tb = traceback.format_exc()
            try:
                self.tab_generation.log(
                    f"⚠ 回填 dispatch 抛异常(原本会被吞,现已暴露):{_e_dispatch}",
                    "error")
                for _ln in _tb.strip().splitlines()[-8:]:
                    self.tab_generation.log(f"  {_ln}", "error")
            except Exception:
                pass
            print("=" * 60, flush=True)
            print(f"[_on_response_received dispatch 异常] task={task_id!r}", flush=True)
            print(_tb, flush=True)
            print("=" * 60, flush=True)
            # 命中已知系列 → 不走主 dispatch 兜底,避免内容被复制到剪贴板就算完
            _ROUTED_TARGETS = {
                "pangu_qcheck", "pangu_spiral", "pangu_mode",
                "pangu_autofix", "laodao_critique", "laodao_autofix",
            }
            try:
                _tgt = self._pending_task_targets.get(task_id, {}).get("target", "")
            except Exception:
                _tgt = ""
            if _tgt in _ROUTED_TARGETS:
                self._pending_task_targets.pop(task_id, None)
                return
        if not content or not content.strip():
            self.tab_generation.log(f"任务『{task_id}』未抓到内容(选择器需调整)", "warn")
            content = ""
        else:
            self.tab_generation.log(
                f"任务『{task_id}』抓取成功,{len(content)} 字符", "success")

        # v1.97 BUG-071:主 dispatch 也按 task_id 取 meta,跟 pangu/laodao 路由一致
        meta = self._pending_task_targets.get(task_id, {})
        target = meta.get("target")
        # DEBUG: 响应路由追踪(自动出现在 DEBUG 面板)
        print(f"[dispatch] task={task_id!r} target={target!r} "
              f"keys={list(self._pending_task_targets.keys())}", flush=True)
        # BUG-077 根治:有活跃审计链时,按 task_id 名字无条件覆写 target
        # (三次实战确认:target 要么丢失要么值错误,根因未知)
        _ast_active = getattr(self, "_audit_state", None)
        if _ast_active:
            _tid = task_id or ""
            if "节奏稽核" in _tid or "rhythm" in _tid.lower():
                if target != "critique_rhythm":
                    print(f"[BUG-077] 覆写 target: {target!r} → critique_rhythm (task={_tid!r})", flush=True)
                target = "critique_rhythm"
                if not meta.get("ch_num"):
                    meta = {"target": target, "ch_num": _ast_active.get("meta", {}).get("ch_num", 0)}
            elif "人设稽核" in _tid or "character" in _tid.lower():
                if target != "critique_character":
                    print(f"[BUG-077] 覆写 target: {target!r} → critique_character (task={_tid!r})", flush=True)
                target = "critique_character"
                if not meta.get("ch_num"):
                    meta = {"target": target, "ch_num": _ast_active.get("meta", {}).get("ch_num", 0)}
            elif "代入感稽核" in _tid or "mru" in _tid.lower():
                if target != "critique_mru":
                    print(f"[BUG-077] 覆写 target: {target!r} → critique_mru (task={_tid!r})", flush=True)
                target = "critique_mru"
                if not meta.get("ch_num"):
                    meta = {"target": target, "ch_num": _ast_active.get("meta", {}).get("ch_num", 0)}
            elif "错位稽核" in _tid or "mismatch" in _tid.lower():
                if target != "critique_mismatch":
                    print(f"[BUG-077] 覆写 target: {target!r} → critique_mismatch (task={_tid!r})", flush=True)
                target = "critique_mismatch"
                if not meta.get("ch_num"):
                    meta = {"target": target, "ch_num": _ast_active.get("meta", {}).get("ch_num", 0)}
            elif "视角稽核" in _tid or "pov_lock" in _tid.lower():
                if target != "critique_pov_lock":
                    print(f"[BUG-077] 覆写 target: {target!r} → critique_pov_lock (task={_tid!r})", flush=True)
                target = "critique_pov_lock"
                if not meta.get("ch_num"):
                    meta = {"target": target, "ch_num": _ast_active.get("meta", {}).get("ch_num", 0)}
            elif "Canon稽核" in _tid:
                if target != "canon_audit":
                    print(f"[BUG-077] 覆写 target: {target!r} → canon_audit (task={_tid!r})", flush=True)
                target = "canon_audit"
        # BUG-077 追踪(仅异常时打印)
        if not target:
            print(f"[BUG-077] task_id={task_id!r} target=None "
                  f"dict_keys={list(self._pending_task_targets.keys())}", flush=True)
        # ★ 关键:先 pop pending,handler 才能在内部重新设置(链式任务依赖此)
        self._pending_task_targets.pop(task_id, None)

        # 根据目标自动回填
        if target == "inspiration":
            self._show_inspiration_picker(content)
        elif target == "reader_panel":
            self._on_reader_panel_response(content)
        elif target == "novel_to_script":
            self._on_script_response(content)
        elif target == "ab_compare":
            self._on_ab_compare_response(content)
        elif target == "ai_naming":
            self._on_ai_naming_response(content)
        elif target == "ai_toolbox":
            # v2.23.4: AI 工具箱修改结果回传
            try:
                self.tab_ai_toolbox.on_ai_result(content)
            except Exception:
                pass
        elif target == "conv_restore":
            # 记忆恢复确认回复 — 只记日志
            self.tab_generation.log(
                f"✓ 新对话已确认上下文({len(content)} 字符回复):"
                f" {content[:80].replace(chr(10),' ')}…", "success")
            self.tab_generation.log(
                "🟢 对话槽切换完成,可以继续生成章节。", "success")
        elif target == "title":
            # 提取第一行非空文本作为书名
            t = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
            t = re.sub(r'^[「《【\s"\']+|[」》】\s"\']+$', '', t)[:30]
            if t: self.tab_settings.title_input.setText(t)
            self._switch_to_tab(self.tab_settings)
        elif target == "outline_full":
            # 整段内容始终填入章节大纲框
            self.tab_outline.chapter_outline_edit.setPlainText(content)
            # 同时尝试按标题拆分回填各分项框
            self._auto_fill_outline(content)
            self._switch_to_tab(self.tab_outline)
        elif target and target.startswith("outline_part:"):
            part = target.split(":", 1)[1]
            mp = {
                "故事种子": self.tab_outline.seed_edit,
                "世界观": self.tab_outline.worldview_edit,
                "LO世界观层": self.tab_outline.lo_edit,
                "故事结构": self.tab_outline.structure_edit,
                "章节大纲": self.tab_outline.chapter_outline_edit,
            }
            if part in mp:
                mp[part].setPlainText(content)
            self._switch_to_tab(self.tab_outline)
        elif target == "intro":
            self.tab_outline.intro_edit.setPlainText(content)
            self._switch_to_tab(self.tab_outline)
        elif target in ("chapter", "golden_three"):
            if self.workflow and meta.get("_workflow_ctx") and target == "chapter":
                # ★ 新路径:由 workflow.start() 发起的章节(含 _workflow_ctx)
                print(f"[dispatch] → workflow.on_ai_content (workflow 路径)", flush=True)
                self.workflow.on_ai_content(content, meta)
            else:
                print(f"[dispatch] → _handle_chapter_response (旧路径)", flush=True)
                self._handle_chapter_response(content, meta)
        elif target and target.startswith("_cb_"):
            # workflow_pipeline 一次性 callback(AI 稽核步骤回调)
            cb = getattr(self, "_one_shot_callbacks", {}).pop(target, None)
            print(f"[dispatch] _cb_ 回调: target={target!r} found={cb is not None}", flush=True)
            if cb:
                cb(content)
        elif target == "optimize":
            self.tab_editor.content_edit.setPlainText(content)
            self._switch_to_tab(self.tab_editor)
        elif target == "dialogue_critic":
            # v1.32:13 法对话诊断 AI 返回
            try:
                self._on_dialogue_critic_received(content, meta)
            except Exception as _e:
                import traceback
                print(f"[dialogue_critic] 处理失败: {_e}\n{traceback.format_exc()}", flush=True)
                QMessageBox.warning(
                    self, "诊断处理失败",
                    f"AI 返回处理失败:{_e}\n\n原始返回前 500 字:\n{content[:500]}")
            return
        elif target == "import_extract":
            # v1.51: 导入续写 — AI 提取设定返回
            try:
                self._on_import_extract_received(content, meta)
            except Exception as _e:
                import traceback
                print(f"[import_extract] dispatch 失败: {_e}\n{traceback.format_exc()}",
                      flush=True)
            return
        elif target == "book_chapter_analysis":
            # v1.38: 拆书章节 AI 分析返回
            try:
                self._on_book_chapter_analysis_received(content, meta)
            except Exception as _e:
                import traceback
                print(f"[book_analyze] dispatch 失败: {_e}\n"
                      f"{traceback.format_exc()}", flush=True)
            return
        elif target == "dialogue_critic_autofix":
            # v1.34: 13 法重写返回
            try:
                ch_idx = meta.get("ch_idx", -1)
                orig = meta.get("original_chapter", "")
                self._on_dialogue_critic_autofix_response(content, ch_idx, orig)
            except Exception as _e:
                import traceback
                print(f"[dc_autofix] 处理失败: {_e}\n{traceback.format_exc()}", flush=True)
                QMessageBox.warning(
                    self, "重写处理失败",
                    f"AI 返回处理失败:{_e}\n\n原始返回前 500 字:\n{content[:500]}")
            return
        elif target == "chapter_summary":
            # 章节摘要回填到记忆系统
            ch_num = meta.get("ch_num")
            if ch_num and content:
                ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
                summary = content.strip().replace('\n', ' ')
                # 截断超长摘要
                max_len = self.tab_memory.summary_len.value()
                if len(summary) > max_len * 1.5:
                    summary = summary[:max_len] + "..."
                if ch:
                    ch["summary"] = summary
                    self.tab_memory.append_summary(ch_num, ch["title"], summary)
                self.tab_generation.log(f"✓ 第 {ch_num} 章摘要已记入对话记忆", "success")
                # 第 9 项:摘要进盘 → 立即 autosave,保证不丢
                # 尊重 auto_save_project 开关(用户可关掉)
                if getattr(self.tab_generation, "auto_save_project", None) is None \
                        or self.tab_generation.auto_save_project.isChecked():
                    try:
                        self._autosave()
                        self.tab_generation.log("  · 已自动保存到项目文件", "info")
                    except Exception:
                        pass
            # 链式触发:正在跑后置流水线 → 推进
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
            # 链式触发:批量生成中且摘要是为下一章准备的(老路径,无后置流水线时)
            elif meta.get("chain_to_next") and self._batch_remaining > 0 and not self._batch_paused:
                QTimer.singleShot(1000, self._send_next_chapter)
            elif meta.get("chain_to_next") and (self._batch_remaining > 0 or self._batch_paused):
                # v1.96 BUG-070:真批量场景才打"批量已结束"
                # — 单章模式 _batch_remaining=0 走这里说明 chain_to_next 被错误设置了
                # (典型成因:_pending_task_target 单变量在多任务并发提交时被覆盖,
                #  Canon 抽取响应错误地路由到 chapter_summary handler 用了摘要任务的 meta)
                self.tab_generation.log("批量生成已结束", "info")
                self._check_auto_shutdown()
            elif meta.get("chain_to_next"):
                # v1.96 BUG-070:防御诊断 — chain_to_next=True 但 _batch_remaining=0 + 未暂停
                # 说明 meta 来源诡异(_pending_task_target 串台?),不打"批量已结束"避免误导
                # 单章模式没有"批量"概念,这条 log 让下次实战能定位是不是真的串台
                self.tab_generation.log(
                    f"⚠ chain_to_next=True 但 _batch_remaining=0,可能是 "
                    f"_pending_task_target 串台(BUG-070 防御)。task: {meta.get('label', '?')}",
                    "warn")
            # 链式触发:一键生成对话记忆流水线推进
            if meta.get("chain_full_memory"):
                QTimer.singleShot(800, self._run_next_full_memory_step)
            # workflow_pipeline 回调
            done_cb = meta.get("_done_cb")
            if done_cb:
                QTimer.singleShot(100, done_cb)
        elif target == "character_extract":
            # 角色档案提取
            if content.strip():
                self.tab_memory.chars_edit.setPlainText(content.strip())
                self.tab_generation.log("✓ 角色档案已更新", "success")
            self._switch_to_tab(self.tab_memory)
            if meta.get("chain_full_memory"):
                QTimer.singleShot(800, self._run_next_full_memory_step)
        elif target == "world_extract":
            # 角色库结构化提取
            self._on_world_extract_received(content, meta.get("ch_num", 0))
        elif target == "style_audit":
            # 风格检测结果 - 弹窗显示
            ch_idx = meta.get("ch_idx", 0)
            if content.strip():
                QMessageBox.information(
                    self, f"风格检测结果 - 第{ch_idx+1}章",
                    content.strip())
            else:
                QMessageBox.warning(self, "失败", "AI 未返回检测结果")
        elif target == "alt_version":
            # 备选版本 - 弹窗让用户选择保留
            ch_idx = meta.get("ch_idx", 0)
            if not content.strip():
                QMessageBox.warning(self, "失败", "AI 未返回新版本")
                return
            ret = QMessageBox.question(
                self, f"备选版本 - 第{ch_idx+1}章",
                f"AI 已生成备选版本({len(content)} 字)。\n\n"
                f"前 200 字预览:\n{content[:200]}...\n\n"
                "是否用此版本替换原章节内容?\n"
                "(选「否」则只显示在编辑器供你比对,不替换)",
                QMessageBox.Yes | QMessageBox.No)
            if ret == QMessageBox.Yes:
                if 0 <= ch_idx < len(self.chapters):
                    self.chapters[ch_idx]["content"] = content.strip()
                    self.tab_editor.show_chapter(self.chapters[ch_idx], ch_idx)
                    self.tab_generation.log(
                        f"✓ 第{ch_idx+1}章已替换为备选版本", "success")
            else:
                # 仅显示在编辑器
                self.tab_editor.content_edit.setPlainText(content.strip())
                self._switch_to_tab(self.tab_editor)
        elif target == "long_term_extract":
            # 长期记忆提取 - 追加到现有内容
            if content.strip() and content.strip() != "无":
                cur = self.tab_memory.long_term_edit.toPlainText().strip()
                merged = (cur + "\n" + content.strip()) if cur else content.strip()
                self.tab_memory.long_term_edit.setPlainText(merged)
                self.tab_generation.log("✓ 长期记忆已追加", "success")
            else:
                self.tab_generation.log("本章无新增长期记忆", "info")
            self._switch_to_tab(self.tab_memory)
            if meta.get("chain_full_memory"):
                QTimer.singleShot(800, self._run_next_full_memory_step)

        # ============ B / C / D 新增 target 分发 ============
        elif target == "canon_audit":
            self._on_canon_audit_response(content)
        elif target == "canon_extract":
            self._on_canon_extract_response(content, meta)
            # 后置流水线下一步(单章生成完后的链)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
            # 批量抽取流水线下一步(用户点「从已有章节抽取」)
            if getattr(self, "_canon_batch_active", False):
                self._canon_batch_active = False
                QTimer.singleShot(800, self._run_next_canon_extract)
        elif target == "foreshadow_check":
            # v1.76 BUG-056:章末伏笔回收自动检查
            self._on_foreshadow_check_response(content, meta)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif target == "foreshadow_reeval":
            # v1.76 BUG-056:plan_pay_at=0 批量重评估(按钮触发,不挂 pipeline)
            self._on_foreshadow_reeval_response(content, meta)
        elif target == "promise_check":
            # v1.77 BUG-057:章末承诺兑现自动检查
            self._on_promise_check_response(content, meta)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif target == "promise_reeval":
            # v1.77 BUG-057:deadline=0 批量重评估(按钮触发)
            self._on_promise_reeval_response(content, meta)
        elif target == "arc_advance_check":
            # v1.78 BUG-058:章末弧线推进自动评估
            self._on_arc_advance_check_response(content, meta)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif target == "relation_change_check":
            # v1.78 BUG-058:章末关系值变化自动评估
            self._on_relation_change_check_response(content, meta)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif target == "info_disclose_check":
            # v1.79 BUG-059:章末信息披露追踪
            self._on_info_disclose_check_response(content, meta)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif target == "info_check":
            # v1.79 BUG-059:章末知识穿帮检查(标红警告,不自动修)
            self._on_info_check_response(content, meta)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif target == "chapter_to_plot_node":
            # v1.85 BUG-062:章末写作回流(把章号挂到剧情树节点第 5 列)
            self._on_chapter_to_plot_node_response(content, meta)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif target == "critique_rhythm":
            ch_num = meta.get("ch_num", 0)
            self._on_critique_score_response(content, "rhythm", ch_num)
        elif target == "critique_character":
            ch_num = meta.get("ch_num", 0)
            self._on_critique_score_response(content, "character", ch_num)
        elif target == "critique_mru":
            ch_num = meta.get("ch_num", 0)
            self._on_critique_score_response(content, "mru", ch_num)
        elif target == "critique_mismatch":
            ch_num = meta.get("ch_num", 0)
            self._on_critique_score_response(content, "mismatch", ch_num)
        elif target == "critique_pov_lock":
            ch_num = meta.get("ch_num", 0)
            self._on_critique_score_response(content, "pov_lock", ch_num)
        elif target == "skill_run":
            self._on_skill_response(content, meta)

        else:
            # ── BUG-077 安全网:如果当前有活跃的审计链(_audit_state),
            #    说明响应路由丢失了,把响应喂回审计链而不是丢到剪贴板 ──
            _ast = getattr(self, "_audit_state", None)
            if _ast and _ast.get("remaining") is not None:
                self.tab_generation.log(
                    f"⚠ BUG-077 安全网触发:task={task_id!r} target={target!r} "
                    f"落到兜底,但有活跃审计链 → 尝试喂回 _continue_ai_audit_chain",
                    "warn")
                # 尝试解析为评分响应(节奏/人设),喂回审计链
                try:
                    self._on_critique_score_response(
                        content,
                        "rhythm" if "节奏" in (task_id or "") else "character",
                        _ast["meta"].get("ch_num", 0))
                except Exception as _e77:
                    self.tab_generation.log(
                        f"  BUG-077 喂回失败:{_e77},强制推进审计链", "warn")
                    self._continue_ai_audit_chain()
            # ── 也检查后置流水线是否卡住 ──
            elif getattr(self, "_post_chapter_pipeline", None):
                self.tab_generation.log(
                    f"⚠ BUG-077 安全网:task={task_id!r} 落到兜底,"
                    f"但有活跃后置流水线 → 推进下一步", "warn")
                QTimer.singleShot(500, self._run_next_post_chapter_step)
            else:
                # 真的没指定目标,复制到剪贴板
                self._popup_choose_target(content)

    def _handle_chapter_response(self, content, meta):
        """处理章节生成回复 → 多维校验 → 死磕重写 / 入库 + 后置链"""
        if not content:
            self._batch_remaining = 0
            return
        target_words = meta.get("target_words", 3000)
        min_words = meta.get("min_words", int(target_words * 0.85))

        # ★ BUG-027 防御:DeepSeek 串行任务有时回复抓取错位 → 抓到的不是章节,
        #   是上一轮 JSON 稽核的残留 / 短回复。如果章节正文 < 500 字 且 retry_left > 0,
        #   认定是 AI 没听懂指令的废话回复,直接重发原指令,不算章节
        ck_content_len = len(content.strip()) if content else 0
        if (ck_content_len < 500 and meta.get("retry_left", 0) > 0
                and meta.get("target") != "golden_three"):
            self.tab_generation.log(
                f"⚠ 收到异常短的'章节回复'({ck_content_len} 字),疑似抓取错位/AI 误解指令,"
                f"重发(剩余 {meta.get('retry_left', 0)} 次)",
                "warn")
            # 简单粗暴 — 重发死磕 prompt(不抓 JSON 校验)
            new_meta = dict(meta)
            new_meta["_held_content"] = ""  # 不存
            self._retry_chapter_with_reasons(
                new_meta, ["内容明显异常(疑似抓取错位),重发"])
            return

        # ---- 即时校验(无 AI 调用)----
        instant_issues, need_ai_audit = self._check_chapter_quality(
            content, target_words, min_words)

        cfg = self.tab_generation.critique_config()

        # ---- 是否需要 AI 稽核(Canon / 节奏 / 人设)----
        if need_ai_audit and meta.get("target") != "golden_three":
            # 启动 AI 稽核串联流水线
            self._start_ai_audit_chain(content, meta, instant_issues)
            return

        # 没有 AI 稽核需求,直接根据即时问题决定
        if instant_issues:
            new_meta = dict(meta)
            new_meta["_held_content"] = content
            self._retry_chapter_with_reasons(new_meta, instant_issues)
            return

        self._accept_chapter_and_continue(content, meta)

    def _start_ai_audit_chain(self, content, meta, instant_issues):
        """串行 AI 稽核:Canon → 节奏 → 人设,把所有 issues 汇总后决定是否死磕"""
        cfg = self.tab_generation.critique_config()
        # 留存 content 在 meta 里供 callback 使用
        audit_state = {
            "content": content,
            "meta": dict(meta),
            "issues": list(instant_issues),
            "remaining": [],
        }
        if cfg.get("canon"):
            audit_state["remaining"].append("canon")
        if cfg.get("rhythm"):
            audit_state["remaining"].append("rhythm")
        if cfg.get("character"):
            audit_state["remaining"].append("character")
        if cfg.get("mru"):
            audit_state["remaining"].append("mru")
        if cfg.get("mismatch"):
            audit_state["remaining"].append("mismatch")
        if cfg.get("pov_lock"):
            audit_state["remaining"].append("pov_lock")
        self._audit_state = audit_state
        self._continue_ai_audit_chain()

    def _continue_ai_audit_chain(self):
        """推进 AI 稽核流水线,完成时统一决定 retry / accept"""
        st = getattr(self, "_audit_state", None)
        if st is None:
            return
        if not st["remaining"]:
            # 全部稽核完成 → 决定走向
            content = st["content"]
            meta = st["meta"]
            issues = st["issues"]
            self._audit_state = None
            if issues:
                meta["_held_content"] = content
                self._retry_chapter_with_reasons(meta, issues)
            else:
                self._accept_chapter_and_continue(content, meta)
            return

        next_kind = st["remaining"].pop(0)
        ch_num = st["meta"].get("ch_num", len(self.chapters) + 1)
        content = st["content"]
        if next_kind == "canon":
            def on_canon_done(violations):
                # 仅 high 严重度才作为重写理由(mid/low 只记录不死磕)
                for v in violations:
                    if v.get("severity") == "high":
                        st["issues"].append(
                            "Canon 违反(严重):" + v.get("desc", "")[:120])
                self._continue_ai_audit_chain()
            self._run_canon_audit(content, ch_num, on_canon_done)
        elif next_kind == "rhythm":
            _label_rhythm = f"节奏稽核-第{ch_num}章"
            # BUG-077 终极修复:注册直接回调,完全绕过 dispatch 路由
            self._critique_audit_callback = ("rhythm", ch_num)
            prompt = PROMPTS["critique_rhythm"].format(content=content[:6000])
            self._send_to_ai(prompt, _label_rhythm,
                             target="critique_rhythm", ch_num=ch_num)
        elif next_kind == "character":
            chars = self.get_unified_chars_summary() or "(暂无)"
            prompt = PROMPTS["critique_character"].format(
                characters=chars, content=content[:6000])
            _label_char = f"人设稽核-第{ch_num}章"
            # BUG-077 终极修复:同上
            self._critique_audit_callback = ("character", ch_num)
            self._send_to_ai(prompt, _label_char,
                             target="critique_character", ch_num=ch_num)
        elif next_kind == "mru":
            # v2.24.0 代入感(MRU)稽核:刺激→感受→反应 顺序检查
            _label_mru = f"代入感稽核-第{ch_num}章"
            # BUG-077 终极修复:同上
            self._critique_audit_callback = ("mru", ch_num)
            prompt = PROMPTS["critique_mru"].format(content=content[:6000])
            self._send_to_ai(prompt, _label_mru,
                             target="critique_mru", ch_num=ch_num)
        elif next_kind == "mismatch":
            # v2.24.1 角色三层错位稽核:说/想/做 不能全程一致
            _label_mm = f"错位稽核-第{ch_num}章"
            # BUG-077 终极修复:同上
            self._critique_audit_callback = ("mismatch", ch_num)
            prompt = PROMPTS["critique_mismatch"].format(content=content[:6000])
            self._send_to_ai(prompt, _label_mm,
                             target="critique_mismatch", ch_num=ch_num)
        elif next_kind == "pov_lock":
            # v2.24.1 情境视角锁定稽核:场景内不切视角
            _label_pov = f"视角稽核-第{ch_num}章"
            # BUG-077 终极修复:同上
            self._critique_audit_callback = ("pov_lock", ch_num)
            prompt = PROMPTS["critique_pov_lock"].format(content=content[:6000])
            self._send_to_ai(prompt, _label_pov,
                             target="critique_pov_lock", ch_num=ch_num)

    def _on_critique_score_response(self, content, kind, ch_num):
        """处理节奏 / 人设打分回复"""
        st = getattr(self, "_audit_state", None)
        if st is None:
            return
        threshold = 6 if kind == "rhythm" else 7
        try:
            text = self._extract_json_blob(content)
            data = json.loads(text)
            score = int(data.get("score", 10))
            reason = (data.get("reason", "") or "")[:120]
            label = {"rhythm": "节奏", "character": "人设",
                     "mru": "代入感", "mismatch": "三层错位",
                     "pov_lock": "视角锁定"}[kind]
            self.tab_generation.log(
                f"  {label}打分:{score}/10 — {reason}", "info")
            if score < threshold:
                st["issues"].append(f"{label}评分不足({score}<{threshold}):{reason}")
        except Exception as e:
            self.tab_generation.log(f"  {kind} 打分解析失败:{e}", "warn")
        self._continue_ai_audit_chain()

    # ===================================================================
    # 技能库(D 模块):手动调用 + 章末自动调用
    # ===================================================================
    def _run_skill_on_chapter(self, skill, ch_num, chain_post=False,
                              body_override=None, _done_cb=None):
        """在某一章上运行技能。chain_post=True 时回复后会推进 post-chapter 流水线"""
        if 0 < ch_num <= len(self.chapters):
            ch = self.chapters[ch_num - 1]
            content = body_override if body_override is not None else (ch.get("content") or "")
        else:
            content = body_override or ""
        if not content:
            self.tab_generation.log(f"技能「{skill['name']}」: 无可用文本", "warn")
            if chain_post:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
            if _done_cb:
                QTimer.singleShot(100, _done_cb)
            return
        try:
            prompt = skill["prompt"].format(content=content[:8000])
        except Exception:
            prompt = skill["prompt"] + "\n\n" + content[:8000]
        self._send_to_ai(
            prompt, f"技能-{skill['name']}",
            target="skill_run",
            ch_num=ch_num,
            skill_name=skill["name"],
            skill_target=skill.get("target", "log_only"),
            chain_post=chain_post,
            _done_cb=_done_cb,          # workflow_pipeline 回调
        )

    def _on_skill_response(self, content, meta):
        skill_name = meta.get("skill_name", "?")
        skill_target = meta.get("skill_target", "log_only")
        ch_num = meta.get("ch_num", 0)
        if not content.strip():
            self.tab_generation.log(f"技能「{skill_name}」未抓到内容", "warn")
        elif skill_target == "current_chapter":
            if 0 < ch_num <= len(self.chapters):
                self.chapters[ch_num - 1]["content"] = content
                self.tab_editor.content_edit.setPlainText(content)
                self.tab_generation.log(
                    f"✓ 技能「{skill_name}」已替换第 {ch_num} 章正文", "success")
        elif skill_target == "selected_text":
            cur = self.tab_editor.content_edit.textCursor()
            if cur.hasSelection():
                cur.insertText(content)
            else:
                self.tab_editor.content_edit.setPlainText(content)
            self.tab_generation.log(
                f"✓ 技能「{skill_name}」已应用到选区", "success")
        elif skill_target == "append_to_canon":
            # 简单追加为 evolving 演化项
            try:
                cur = self.tab_canon.canon_edit.toPlainText()
                self.tab_canon.canon_edit.setPlainText(
                    (cur + "\n" if cur else "") + f"# 技能「{skill_name}」于 ch{ch_num} 追加\n"
                    + "\n".join(
                        f"[E][M] 技能.{skill_name}.{i} = {ln.strip()} (ch{ch_num})"
                        for i, ln in enumerate(content.splitlines()[:20])
                        if ln.strip())
                )
                self.tab_generation.log(
                    f"✓ 技能「{skill_name}」结果已追加到 Canon", "success")
            except Exception as e:
                self.tab_generation.log(f"追加 Canon 失败:{e}", "warn")
        else:  # log_only
            self.tab_generation.log(
                f"📝 技能「{skill_name}」结果(ch{ch_num}):", "info")
            for line in content.splitlines()[:10]:
                if line.strip():
                    self.tab_generation.log(f"   {line.strip()[:200]}", "info")

        # 链式推进
        if meta.get("chain_post"):
            QTimer.singleShot(500, self._run_next_post_chapter_step)
        elif getattr(self, "_post_chapter_pipeline", None):
            # BUG-077 加固:meta 丢失时通过 pipeline 直接推进
            QTimer.singleShot(500, self._run_next_post_chapter_step)
        # workflow_pipeline 回调
        done_cb = meta.get("_done_cb")
        if done_cb:
            QTimer.singleShot(500, done_cb)

    # ─────────────── 风格一致性检测 ───────────────
    def _on_style_check(self):
        """检测当前章节风格与参考章节的一致性"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节")
            return
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』再使用风格检测。")
            return
        cur_idx = self.tab_editor.current_index
        if cur_idx is None or cur_idx < 0 or cur_idx >= len(self.chapters):
            QMessageBox.information(self, "提示", "请先在编辑器选中一个章节")
            return
        if cur_idx == 0:
            QMessageBox.information(
                self, "提示",
                "第 1 章是基准章,无需检测。请打开第 2 章及以后的章节进行风格检测。")
            return
        cur_ch = self.chapters[cur_idx]
        # 用第 1 章作为风格基准
        ref_ch = self.chapters[0]
        prompt = PROMPTS["style_audit"].format(
            reference=ref_ch.get("content", "")[:3000],
            content=cur_ch.get("content", "")[:3000],
        )
        self._send_to_ai(
            prompt, f"风格检测-第{cur_idx+1}章",
            target="style_audit",
            ch_idx=cur_idx,
        )

    # ─────────────── 多版本备选生成 ───────────────
    def _on_regen_alt(self):
        """为当前章节生成备选版本(同样的提示词,让 AI 给不同写法)"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节")
            return
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先点『启动浏览器』")
            return
        cur_idx = self.tab_editor.current_index
        if cur_idx is None or cur_idx < 0 or cur_idx >= len(self.chapters):
            QMessageBox.information(self, "提示", "请先选中要重生成的章节")
            return
        ch_num = cur_idx + 1
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        outline = (self.tab_outline.worldview_edit.toPlainText() + "\n"
                   + self.tab_outline.structure_edit.toPlainText())[:1500]
        target = self.tab_settings.get_words_per_chapter()
        offset = self.tab_settings.get_prompt_offset()
        target_with_offset = max(500, target + offset)
        min_words = max(300, int(target_with_offset * 0.85))
        full = self.tab_settings.get_full_settings_block()
        # v1.22:备选版本也用 prev_context 保持一致性
        prev_context = self._build_prev_context(ch_num)
        prompt = PROMPTS["chapter"].format(
            chapter_num=ch_num,
            title=self.tab_settings.get_title(),
            genre="/".join(self.tab_settings.get_selected_genres() or ["言情"]),
            outline=outline,
            chapter_outline=co[:2500],
            prev_context=prev_context,
            min_words=min_words, target_words=target_with_offset,
        )
        prompt += (
            f"\n\n【完整设定参考】\n{full}"
            "\n\n【备选版本要求】\n"
            "请用与上一版【截然不同】的写法重写本章。可以:\n"
            "  · 改变开场切入点(从对话开场/从动作开场/从内心独白开场)\n"
            "  · 调整节奏(放慢或加快)\n"
            "  · 用不同视角或描写偏重\n"
            "保持核心情节不变,但表达完全不同。"
        )
        self._send_to_ai(
            prompt, f"备选版本-第{ch_num}章",
            target="alt_version",
            ch_idx=cur_idx,
        )

    # ─────────────── 角色库自动提取 ───────────────
    # ─────────────── 盘古超级系统:新功能入口 ───────────────
    def _on_pangu_toggle(self, checked):
        # 运行时根据 GUI 勾选状态切换盘古的 PROMPTS 包裹
        try:
            from pangu_patch import install_pangu, uninstall_pangu, is_installed
        except ImportError:
            return
        g = globals()
        cur = is_installed(g)
        if checked and not cur:
            install_pangu(g)
            self.tab_generation.log("✓ 盘古超级系统已启用(PROMPTS 已包裹)", "info")
        elif not checked and cur:
            uninstall_pangu(g)
            self.tab_generation.log("⊘ 盘古超级系统已停用(PROMPTS 已还原)", "info")

    def _on_pangu_style_match(self):
        # 基于创意灵感关键词匹配盘古风格库,弹结果
        kw = self.tab_settings.inspiration_edit.toPlainText().strip()
        if not kw:
            QMessageBox.information(
                self, "提示",
                "先在【创意灵感】输入框填几个关键词(如 '退婚 战神 都市 神豪')")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        report = get_default_engine().build_style_report(kw)
        dlg = QMessageBox(self)
        dlg.setWindowTitle("🎯 盘古风格匹配")
        dlg.setText("基于你的关键词,推荐 Top 3 风格组合:")
        dlg.setDetailedText(report)
        dlg.exec_()

    def _on_pangu_mode(self, mode_key):
        # 切换盘古四模式(发个 mode-switch prompt 给当前 AI)
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』Tab 启动浏览器并完成 AI 网站登录。")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        prompt = get_default_engine().build_mode_switch_prompt(mode_key)
        names = {"architect": "建筑师", "dreamweaver": "造梦师",
                 "alchemist": "炼金术士", "sculptor": "雕刻家"}
        self._send_to_ai(
            prompt, f"盘古模式切换-{names.get(mode_key, mode_key)}",
            target="pangu_mode")

    def _on_book_chapter_analyze(self, ch_idx, content):
        """v1.38: 拆书 — 用户点'AI 分析本章'触发"""
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』点『🚀 启动浏览器』并完成 AI 网站登录")
            self.tab_book_splitter.btn_analyze.setEnabled(True)
            return
        if not content or not content.strip():
            QMessageBox.warning(self, "提示", "这一章正文为空")
            self.tab_book_splitter.btn_analyze.setEnabled(True)
            return
        # 构造分析 prompt:综合 13 法 + 八大坑 + 钩子 + 爽点
        prompt = (
            "你是网文章节诊断专家。请深度分析下面这一章,从【其他作者的章节学习】"
            "角度给出全面评分。\n\n"
            "【评分维度】\n"
            "1. 13 法对话铁律(动作卡位/神态神韵/情境穿插/语义衔接/标点替代等)\n"
            "2. 八大坑(K1 视角统一 / K2 对话有效 / K3 爽点付费 / K4 主角主动 / "
            "K5 反派合理 / K6 无毒点 / K7 节奏紧凑 / K8 市场意识)\n"
            "3. 章末钩子强度(0-10):悬念 / 倒计时 / 关键对话 / 反转\n"
            "4. 爽点统计:本章用了哪几种爽点(打脸/捡漏/暧昧/突破/反转/碾压/夺宝/收服/揭秘/共鸣)\n"
            "5. 章节结构总评(开篇 3 段抓人吗 / 中段节奏 / 结尾钩子)\n\n"
            "【输出格式】用 markdown 表格 + 简短点评,400-800 字。\n"
            "不要重述章节内容,只给评分和点评。\n\n"
            "【待分析章节】\n"
            + content[:8000]
        )
        self.tab_generation.log(
            f"▶ 拆书 AI 分析第 {ch_idx+1} 章...", "info")
        self._send_to_ai(
            prompt, f"拆书分析-第{ch_idx+1}章",
            target="book_chapter_analysis",
            book_ch_idx=ch_idx,
        )

    def _on_book_chapter_analysis_received(self, content, meta):
        """v1.38: AI 分析返回 → 写回拆书 Tab"""
        ch_idx = meta.get("book_ch_idx", -1)
        if ch_idx < 0:
            return
        try:
            self.tab_book_splitter.receive_analysis_result(
                ch_idx, content)
            self.tab_generation.log(
                f"✓ 拆书第 {ch_idx+1} 章 AI 分析完成", "success")
        except Exception as e:
            print(f"[book_analyze] 写回失败: {e}", flush=True)

    def _on_dialogue_critic(self):
        """v1.32:13 法对话诊断 — 静态扫描 + 可选 AI 深度评分"""
        if not DIALOGUE_CRITIC_AVAILABLE:
            QMessageBox.warning(
                self, "诊断器不可用",
                "dialogue_critic.py 没找到。\n请确认文件存在于程序目录。")
            return

        content = self.tab_editor.content_edit.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "对话诊断", "本章为空,无内容可诊断")
            return

        critic = dialogue_critic.DialogueCritic(content)

        # Step 1: 静态扫描(本地,瞬出)
        static = critic.static_scan()
        static_msg = static.summary()

        # 询问是否跑 AI 深度评分
        ret = QMessageBox.question(
            self, "🔬 对话诊断 - 静态扫描完成",
            f"{static_msg}\n\n──────────\n"
            f"是否继续 AI 深度评分?\n"
            f"  ✓ 是 → 发 AI,13 法逐条评分 + 改写建议(消耗 token)\n"
            f"  ✗ 否 → 只看静态扫描结果",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            # 把静态结果显示到对话框
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle("🔬 13 法对话诊断 (静态)")
            dlg.resize(700, 500)
            lay = QVBoxLayout(dlg)
            te = QPlainTextEdit(static_msg)
            te.setReadOnly(True)
            lay.addWidget(te)
            bb = QDialogButtonBox(QDialogButtonBox.Close)
            bb.rejected.connect(dlg.reject)
            bb.accepted.connect(dlg.accept)
            lay.addWidget(bb)
            dlg.exec_()
            return

        # Step 2: 发 AI(用现有 _send_to_ai 通道)
        # 读老刀开关
        from PyQt5.QtCore import QSettings
        laodao = QSettings("NovelAI", "DialogueCritic").value(
            "laodao_style", False, type=bool)
        prompt = critic.build_ai_prompt(deep=True, laodao=laodao)
        self._dialogue_critic_static = static    # 暂存静态结果供 received 用
        self._send_to_ai(
            prompt,
            f"13 法对话诊断{'(老刀风格)' if laodao else ''}",
            target="dialogue_critic")
        self.tab_generation.log(
            "🔬 13 法对话诊断已发送 AI(深度评分 + 改写建议)", "info")

    def _on_dialogue_critic_received(self, content, meta):
        """AI 返回诊断结果 + 提供按建议重写"""
        ai_data = dialogue_critic.parse_ai_response(content)
        static = getattr(self, "_dialogue_critic_static", None)
        if static is None:
            QMessageBox.warning(self, "诊断错误", "找不到静态扫描缓存")
            return
        report = dialogue_critic.format_report(static, ai_data)
        # 用大对话框显示 + 加"按建议重写"按钮
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton)
        dlg = QDialog(self)
        dlg.setWindowTitle("🔬 13 法对话诊断 - AI 深度结果")
        dlg.resize(800, 650)
        lay = QVBoxLayout(dlg)
        te = QPlainTextEdit(report)
        te.setReadOnly(True)
        from PyQt5.QtGui import QFont
        f = QFont("Consolas", 10)
        te.setFont(f)
        lay.addWidget(te)

        # v1.34: 按钮区 — 一键 AI 按建议重写
        btn_row = QHBoxLayout()
        btn_autofix = QPushButton("🔧 按 13 法建议重写本章")
        btn_autofix.setStyleSheet(
            "QPushButton { background:#8e44ad; color:white; padding:8px 16px; "
            "border-radius:3px; font-weight:bold; font-size:14px; } "
            "QPushButton:hover { background:#6c3483; }")
        btn_autofix.setToolTip(
            "把章节正文 + 13 法各项弱点 + 改写建议发给 AI,让它按 13 法重写本章。\n"
            "完成后修复版本会自动覆盖当前章节(原版本通过项目备份找回)。")
        btn_close = QPushButton("先关掉(我手动改)")
        btn_close.setStyleSheet("QPushButton { background:#888; color:white; padding:8px 16px; }")

        # 整体分数不太差(>=85)或没拿到 AI 数据 → 不强推
        overall = (ai_data or {}).get("overall_score", 0)
        try:
            overall_int = int(overall) if overall else 0
        except (ValueError, TypeError):
            overall_int = 0
        if not ai_data:
            btn_autofix.setEnabled(False)
            btn_autofix.setText("⚠ AI 评分未解析,无法重写")
        elif overall_int >= 90:
            btn_autofix.setText("✓ 整体已达 90+,无需重写(仍可点)")
            btn_autofix.setStyleSheet(
                "QPushButton { background:#1f8b4d; color:white; padding:8px 16px; "
                "border-radius:3px; font-weight:bold; }")

        def _on_dc_autofix():
            dlg.accept()
            self._on_dialogue_critic_autofix_request(ai_data)

        btn_autofix.clicked.connect(_on_dc_autofix)
        btn_close.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_autofix, 2)
        btn_row.addWidget(btn_close, 1)
        lay.addLayout(btn_row)

        dlg.exec_()
        self.tab_generation.log("🔬 13 法对话诊断完成", "success")

    def _on_dialogue_critic_autofix_request(self, ai_data):
        """v1.34: 让 AI 按 13 法 advice 重写本章"""
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』点『🚀 启动浏览器』并完成 AI 网站登录")
            return
        original_chapter = self.tab_editor.content_edit.toPlainText().strip()
        if not original_chapter:
            QMessageBox.warning(self, "提示", "原章节内容为空,无法重写")
            return
        ch_idx = getattr(self.tab_editor, "current_index", -1)
        if ch_idx < 0 or ch_idx >= len(self.chapters):
            QMessageBox.warning(
                self, "提示",
                "请先在左侧章节列表里选中要重写的章节")
            return

        # 构造 prompt — 从 ai_data 抽出 13 法弱点和建议
        LAW_NAMES = {
            "L1": "动作卡位", "L2": "神态神韵", "L3": "情境穿插",
            "L4": "语感辨识", "L5": "语义衔接", "L6": "标点替代",
            "L7": "内心独白回切", "L8": "群体反应衬托",
            "L9": "重复词锚定", "L10": "空格断句", "L11": "通感法",
            "L12": "信息差技巧", "L13": "节奏开关",
        }
        weak_laws = []
        worst_3 = ai_data.get("worst_3", [])
        for key in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8",
                    "L9", "L10", "L11", "L12", "L13"):
            item = ai_data.get(key)
            if not isinstance(item, dict):
                continue
            score = item.get("score", 10)
            try:
                score_int = int(score)
            except (ValueError, TypeError):
                score_int = 10
            advice = item.get("advice", "").strip()
            # 弱点定义: 分数 <= 5 或在 worst_3 里
            if score_int <= 5 or key in worst_3:
                weak_laws.append(
                    f"  · {key} {LAW_NAMES.get(key, key)} ({score_int}/10): {advice}")

        weak_section = "\n".join(weak_laws) if weak_laws else "  · (AI 未指出具体弱点)"
        verdict = ai_data.get("verdict", "(无)")
        overall = ai_data.get("overall_score", "?")

        prompt = (
            "你是网文对话风格修复师。下面是一篇章节,以及 13 法对话铁律的诊断结果。\n"
            "请按诊断指出的弱点,重写这一章,**只改对话写法,情节/人设/世界观完全不动**。\n\n"
            f"【整体评分】{overall}/100\n"
            f"【AI 评价】{verdict}\n\n"
            "【主要弱点(必须改)】\n"
            f"{weak_section}\n\n"
            "【13 法对话铁律(强制遵守)】\n"
            "  L1 动作卡位: 用动作替代「X 说」\n"
            "  L2 神态神韵: 专属微动作前置\n"
            "  L3 情境穿插: 对话间插环境/物\n"
            "  L4 语感辨识: 角色专属语气/口头禅\n"
            "  L5 语义衔接: 对话直接回应前句\n"
            "  L6 标点替代: 短促交锋换行+标点\n"
            "  L7 内心独白回切: 对话后接主角预判\n"
            "  L8 群体反应衬托: 用反应反推说话人\n"
            "  L9 重复词锚定: 角色刻意重复词\n"
            "  L10 空格断句: 对话顶格+空行\n"
            "  L11 通感法: 一种感官写另一种\n"
            "  L12 信息差: 读者/角色不对称张力\n"
            "  L13 节奏开关: 急慢脉冲\n\n"
            "**红线**: 「说/道」次数 ≤ 章节字数/600 (约每 600 字一次)。\n"
            "禁套词: 怒吼道/喃喃道/喝道/低声道/淡淡道/缓缓道。\n"
            "禁修饰: 生气地说/担心地问 等。\n\n"
            "【输出】**只输出重写后的完整章节正文**,不要解释、不要 markdown、"
            "不要前言后语。直接从章节第一句开始写到最后一句。\n\n"
            "【章节原文】\n"
            f"{original_chapter[:8000]}\n"
        )

        self.tab_generation.log(
            f"▶ 让 AI 按 13 法重写第 {ch_idx+1} 章(弱点 {len(weak_laws)} 项)...",
            "info")
        self._send_to_ai(
            prompt,
            f"13法重写-第{ch_idx+1}章",
            target="dialogue_critic_autofix",
            ch_idx=ch_idx,
            original_chapter=original_chapter,
        )

    def _on_pangu_qcheck(self, content):
        # 让 AI 按盘古 30 项质检规范深度审稿
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        prompt = get_default_engine().build_quality_check_prompt(content)
        self._send_to_ai(prompt, "盘古30项质检", target="pangu_qcheck")


    @staticmethod
    def _parse_laodao_quit_rate(critique_text):
        """从老刀点评里解析弃书率，返回 int 或 None。
        兼容多种 AI 输出格式。"""
        import re as _re
        # 按优先级尝试多种匹配模式
        patterns = [
            # 精确匹配"三章弃书率预估：XX%"（中文冒号或英文冒号）
            r'三章弃书率预估\s*[：:]\s*(\d{1,3})\s*%',
            # "当前版本三章弃书率预估：XX%"
            r'当前版本三章弃书率预估\s*[：:]\s*(\d{1,3})\s*%',
            # "弃书率预估：XX%"
            r'弃书率预估\s*[：:]\s*(\d{1,3})\s*%',
            # "弃书率：XX%"
            r'弃书率\s*[：:]\s*(\d{1,3})\s*%',
            # "弃书率约XX%" 或 "弃书率大约XX%"
            r'弃书率[约大概预估]{0,4}\s*(\d{1,3})\s*%',
            # "XX%的弃书率"
            r'(\d{1,3})\s*%\s*的弃书率',
            # 宽松：附近有"弃书"两字的百分数
            r'弃书.{0,20}?(\d{1,3})\s*%',
        ]
        for pat in patterns:
            m = _re.search(pat, critique_text)
            if m:
                val = int(m.group(1))
                if 0 <= val <= 100:   # 合理范围
                    return val
        return None

    def _on_laodao_critique(self, content, retry_round=1,
                             autofix_round=0, max_rounds=3, target_rate=35):
        """🔪 老刀毒舌点评:让 AI 扮老刀给当前章节开刀。
        retry_round: 格式重试轮次(最多3次)
        autofix_round: 自动重写循环计数(0=未进入循环)"""
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器并完成登录")
            return
        # 安全截断:老刀 prompt 本身就 ~1.5k,加章节正文要控制总长
        snippet = content[:6000] if len(content) > 6000 else content
        prompt = PROMPTS["critique_laodao"].format(content=snippet)
        loop_info = f" [自动循环第{autofix_round}轮]" if autofix_round > 0 else ""
        self.tab_generation.log(
            f"▶ 召唤老刀 (第 {retry_round} 轮){loop_info},约 1 分钟回填...", "info")
        self._send_to_ai(
            prompt, f"老刀毒舌点评-第{retry_round}轮",
            target="laodao_critique",
            retry_round=retry_round,
            original_content=content,
            autofix_round=autofix_round,
            max_rounds=max_rounds,
            target_rate=target_rate,
        )

    def _on_laodao_critique_response(self, content, meta):
        """老刀点评返回 → 解析弃书率 → 自动重写循环 → 弹窗展示"""
        retry_round   = meta.get("retry_round", 1)
        original_content = meta.get("original_content", "")
        autofix_round = meta.get("autofix_round", 0)   # 已重写几轮
        from PyQt5.QtCore import QSettings as _QS_ld
        target_rate = _QS_ld("NovelAI", "Laodao").value("target_quit_rate", 35, type=int)
        max_rounds  = _QS_ld("NovelAI", "Laodao").value("max_autofix_rounds", 3, type=int)
        # 简单的"成功"判定:老刀回复要包含【逐条开刀】或❌或【综合诊断】才算成功格式
        success_markers = ("逐条开刀", "综合诊断", "❌", "🔪", "存活概率", "致命伤")
        is_valid = any(m in content for m in success_markers)
        # 内容太短(<200 字)也算失败
        if len(content) < 200:
            is_valid = False
        if not is_valid:
            if retry_round < 3:
                self.tab_generation.log(
                    f"✗ 老刀点评第 {retry_round} 轮返回格式不对 (字数 {len(content)}),自动重试...",
                    "warn")
                # 自动再跑(原章节再点评一次)
                self._on_laodao_critique(original_content, retry_round=retry_round + 1)
                return
            else:
                self.tab_generation.log(
                    f"✗ 老刀点评 3 轮都不通过,放弃。最后一次返回:\n{content[:500]}",
                    "warn")
                QMessageBox.warning(
                    self, "老刀点评失败",
                    f"3 轮都没拿到合格点评。最后返回(前 500 字):\n\n{content[:500]}")
                return
        # ── 弃书率解析 + 自动重写循环 ──
        quit_rate = self._parse_laodao_quit_rate(content)
        if quit_rate is not None:
            self.tab_generation.log(
                f"📊 老刀弃书率: {quit_rate}%  目标: ≤{target_rate}%"
                f"  (已重写: {autofix_round}/{max_rounds}轮)", "info")
        if (quit_rate is not None
                and quit_rate > target_rate
                and autofix_round < max_rounds):
            self.tab_generation.log(
                f"🔄 弃书率 {quit_rate}% 超目标 {target_rate}%，"
                f"触发第 {autofix_round + 1} 轮自动重写...", "warn")
            self._on_laodao_autofix_request(
                content, original_content,
                autofix_round=autofix_round + 1,
                max_rounds=max_rounds,
                target_rate=target_rate,
            )
            return
        if quit_rate is not None and autofix_round > 0:
            if quit_rate <= target_rate:
                self.tab_generation.log(
                    f"✅ 弃书率达标! {quit_rate}% ≤ {target_rate}%，共重写 {autofix_round} 轮", "success")
            else:
                self.tab_generation.log(
                    f"⚠ 已达最大轮数 {max_rounds}，最终弃书率 {quit_rate}%，停止", "warn")

        # 弹窗展示
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🔪 老刀点评(第 {retry_round} 轮)")
        dlg.resize(900, 700)
        lay = QVBoxLayout(dlg)
        _rate_html = (f"  弃书率: <b style='color:#f04c5a'>{quit_rate}%</b>"
                      f" (目标≤{target_rate}%)" if quit_rate is not None else "")
        top = QLabel(
            f"<h3 style='color:#c0392b'>🔪 老刀的开刀报告</h3>"
            f"<p>第 {retry_round} 轮 · {len(content)} 字 · "
            f"基于 {len(original_content)} 字的章节正文{_rate_html}</p>")
        top.setTextFormat(Qt.RichText)
        lay.addWidget(top)
        txt = QPlainTextEdit()
        txt.setPlainText(content)
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "font-family: 'Microsoft YaHei', sans-serif; font-size: 13px; "
            "line-height: 1.6; background: #fff9f9; color:#3a3f47; padding: 10px;")
        lay.addWidget(txt, 1)
        # 按钮区
        btn_row = QHBoxLayout()
        btn_autofix = QPushButton("🔧 按老刀建议重写本章")
        btn_autofix.setStyleSheet(
            "background:#b8651b;color:white;padding:8px 16px;border-radius:3px;"
            "font-weight:bold;font-size:14px;")
        btn_autofix.setToolTip(
            "把老刀的整段点评 + 章节原文发给 AI,让它按老刀的批评和改法直接重写本章。\n"
            "完成后修复版本自动覆盖当前章节(原版本通过 .backups 备份,菜单 → 🕓 恢复历史版本 找回)。")
        btn_autofix.clicked.connect(
            lambda: (dlg.accept(),
                     self._on_laodao_autofix_request(content, original_content)))
        btn_recheck = QPushButton("🔁 再来一刀(让老刀再点评一次)")
        btn_recheck.setStyleSheet(
            "background:#c0392b;color:white;padding:6px 14px;border-radius:3px;")
        btn_recheck.clicked.connect(
            lambda: (dlg.accept(), self._on_laodao_critique(original_content, 1)))
        btn_copy = QPushButton("📋 复制全部")
        btn_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(content))
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_autofix, 2)
        btn_row.addWidget(btn_recheck, 1)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)
        self.tab_generation.log(
            f"✓ 老刀第 {retry_round} 轮点评完成,{len(content)} 字", "success")
        dlg.exec_()

    def _on_laodao_autofix_request(self, critique_text, original_chapter,
                                    autofix_round=0, max_rounds=3, target_rate=35):
        """🔧 按老刀建议重写 — 把点评 + 原文发 AI,让它按建议改
        autofix_round: 当前是第几轮自动重写(0=手动触发)"""
        if not original_chapter or not original_chapter.strip():
            QMessageBox.warning(self, "提示", "原章节内容为空,无法修复")
            return
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录")
            return
        ch_idx = getattr(self.tab_editor, "current_index", -1)
        if ch_idx < 0 or ch_idx >= len(self.chapters):
            QMessageBox.warning(
                self, "提示",
                "请先在左侧章节列表里选中要修复的章节")
            return
        # 截断 — 老刀点评 + 原文都可能很长
        critique_snip = critique_text[:5000] if len(critique_text) > 5000 else critique_text
        content_snip = original_chapter[:8000] if len(original_chapter) > 8000 else original_chapter
        prompt = PROMPTS["laodao_autofix"].format(
            critique=critique_snip,
            content=content_snip,
        )
        loop_info = f" (自动第{autofix_round}轮)" if autofix_round > 0 else ""
        self.tab_generation.log(
            f"▶ AI 按老刀建议重写第 {ch_idx+1} 章{loop_info},约 1-2 分钟回填...", "info")
        self._send_to_ai(
            prompt, f"老刀修复-第{ch_idx+1}章",
            target="laodao_autofix",
            ch_idx=ch_idx,
            original_chapter=original_chapter,
            autofix_round=autofix_round,
            max_rounds=max_rounds,
            target_rate=target_rate,
        )

    def _on_laodao_autofix_response(self, content, ch_idx, original_chapter,
                                     autofix_round=0, max_rounds=3, target_rate=35):
        """老刀修复返回 → 回填当前章节(原版本自动备份到 .backups)
        如 autofix_round>0 且未达最大轮，回填后自动再跑老刀点评"""
        if not content or not content.strip():
            QMessageBox.warning(
                self, "老刀修复失败",
                "AI 没返回任何内容。可能 AI 没听懂指令,请重试或先关掉浏览器/网络问题。")
            return
        fixed = content.strip()
        # 容错:去掉可能的元信息块
        try:
            from pangu_system import strip_chapter_meta
            fixed = strip_chapter_meta(fixed)
        except Exception:
            pass
        orig_len = len(original_chapter)
        new_len = len(fixed)
        ratio = new_len / orig_len if orig_len > 0 else 1.0
        if ratio < 0.5 or ratio > 1.8:
            ret = QMessageBox.question(
                self, "⚠️ 修复结果异常",
                f"AI 返回内容长度跟原章节差太多:\n"
                f"  原章节:{orig_len} 字  →  AI 返回:{new_len} 字"
                f"(变化 {(ratio-1)*100:+.1f}%)\n\n"
                f"前 300 字预览:\n{fixed[:300]}...\n\n"
                f"还要回填吗?\n"
                f"  ✓ 是 → 覆盖当前章节(原内容已通过 .backups 备份)\n"
                f"  ✗ 否 → 放弃这次修复",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                self.tab_generation.log("已放弃 AI 修复结果(长度异常)", "warn")
                return
        # BUG-031 加固:核心回填 ① 绝对不被后续 UI/IO 失败连累
        if 0 <= ch_idx < len(self.chapters):
            # ① 核心:写进 chapter dict
            self.chapters[ch_idx]["content"] = fixed
            # ② 以下每步独立 try
            try:
                if self.tab_editor.current_index == ch_idx:
                    self.tab_editor.content_edit.setPlainText(fixed)
            except Exception as _e_ed:
                self.tab_generation.log(
                    f"⚠ 编辑器 setPlainText 失败(内容已入章节 dict):{_e_ed}", "warn")
            try:
                self.save_project()
            except Exception:
                try:
                    self._autosave()
                except Exception as _e_sv:
                    self.tab_generation.log(
                        f"⚠ 保存失败但内容已回填,可手动保存:{_e_sv}", "warn")
            try:
                self.tab_generation.log(
                    f"✓ 老刀重写完成第 {ch_idx+1} 章:{orig_len}→{new_len} 字。"
                    f"原版本可通过菜单 → 🕓 恢复历史版本 找回",
                    "success")
            except Exception:
                pass
            # ── 自动循环：重写完立即再跑老刀点评检查弃书率 ──
            if autofix_round > 0:
                # 在循环中(包括最后一轮)：一律再跑点评，让用户看到最终弃书率
                round_info = (f"第 {autofix_round}/{max_rounds} 轮"
                              if autofix_round <= max_rounds
                              else f"第 {autofix_round} 轮(已超最大)")
                self.tab_generation.log(
                    f"🔄 {round_info} 重写完成，自动再跑老刀点评检查弃书率...", "info")
                self._on_laodao_critique(fixed, retry_round=1,
                                         autofix_round=autofix_round,
                                         max_rounds=max_rounds,
                                         target_rate=target_rate)
                return   # 不弹完成弹窗，等点评回来判断是否继续
            # 纯手动触发(autofix_round=0)：弹完成弹窗
            try:
                msg = (f"第 {ch_idx+1} 章已按老刀建议重写 + 回填 + 保存。\n\n"
                       f"字数变化:{orig_len} → {new_len}\n"
                       f"想要旧版本?菜单 → 文件 → 🕓 恢复历史版本(最近 10 次)\n\n"
                       f"建议:再点一次「🔪 老刀毒舌点评」看新版评价 / 「📊 30项质检」看新得分。")
                QMessageBox.information(self, "✓ 老刀修复完成", msg)
            except Exception:
                pass
        else:
            # ch_idx 不合法 — 兜底剪贴板 + 告知
            try:
                QApplication.clipboard().setText(fixed)
            except Exception:
                pass
            self.tab_generation.log(
                f"⚠ 老刀修复回填失败:ch_idx={ch_idx} 超出章节范围(共 {len(self.chapters)} 章)。"
                f"已抓到 {new_len} 字,复制到剪贴板。",
                "error")
            QMessageBox.warning(
                self, "回填失败",
                f"无法把老刀修复结果写入章节:ch_idx={ch_idx} 不在 0~{len(self.chapters)-1} 范围内。\n"
                f"内容({new_len} 字)已复制到剪贴板,可手动粘贴。")

    def _on_pangu_spiral(self, content):
        # 让 AI 诊断当前章节处于 P1-P7 哪个螺旋阶段
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        prompt = get_default_engine().build_spiral_diagnose_prompt(content)
        self._send_to_ai(prompt, "盘古P1-P7螺旋诊断", target="pangu_spiral")

    # ───── Phase A:Prompt 预览 + 白名单应用 ─────
    def _on_pangu_preview_prompt(self):
        # 预览章节生成时实际发给 AI 的 prompt
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节,无法预览。请先生成一章。")
            return
        cur_idx = self.tab_editor.current_index
        if cur_idx is None or cur_idx < 0:
            cur_idx = 0
        try:
            ch = self.chapters[cur_idx] if cur_idx < len(self.chapters) else self.chapters[0]
        except Exception:
            ch = {}
        # 用当前已生成最后一章作为"上下文",预览下一章 prompt
        s = self.tab_settings
        # BUG #3 修复:从真实大纲控件读取(原 self._outline_text 不存在)
        try:
            _outline_real = (
                self.tab_outline.worldview_edit.toPlainText() + "\n"
                + self.tab_outline.structure_edit.toPlainText()
            ).strip() or "(尚未填写世界观和结构大纲)"
        except Exception:
            _outline_real = "(无法读取大纲)"
        try:
            _ch_outline = self.tab_outline.chapter_outline_edit.toPlainText().strip() or "(无章节大纲)"
        except Exception:
            _ch_outline = "(无章节大纲)"
        try:
            # v1.22:预览也要传 prev_context,避免 KeyError
            try:
                _prev_ctx = self._build_prev_context(cur_idx + 2)
            except Exception:
                _prev_ctx = ""
            preview_prompt = PROMPTS["chapter"].format(
                title=s.get_title(),
                chapter_num=cur_idx + 2,
                genre="/".join(s.get_selected_genres()) or "通用",
                outline=_outline_real[:1500],
                chapter_outline=_ch_outline[:2500],
                prev_context=_prev_ctx,
                min_words=int(s.get_words_per_chapter() * 0.9),
                target_words=s.get_words_per_chapter(),
            )
            # v1.23 BUG-041:补齐 _send_next_chapter 实际会 append 的所有内容
            # 让用户能看到真实发给 AI 的完整 prompt
            try:
                _full = s.get_full_settings_block()
                preview_prompt += f"\n\n【完整设定参考】\n{_full}"
            except Exception:
                pass
            # 对话记忆
            try:
                if hasattr(self, "tab_memory") and \
                        getattr(self.tab_memory, "auto_inject", None) and \
                        self.tab_memory.auto_inject.isChecked():
                    _mem = self._build_memory_block()
                    if _mem:
                        preview_prompt += f"\n\n{_mem}"
            except Exception:
                pass
            # Canon 设定
            try:
                if hasattr(self, "tab_canon") and \
                        getattr(self.tab_canon, "chk_inject", None) and \
                        self.tab_canon.chk_inject.isChecked():
                    _can = self._build_canon_block()
                    if _can:
                        preview_prompt += f"\n\n{_can}"
            except Exception:
                pass
            # 角色与世界 6 库
            try:
                if hasattr(self, "tab_charlib"):
                    _cl = self.tab_charlib.build_inject_block(
                        current_chapter=cur_idx + 2)
                    if _cl:
                        preview_prompt += _cl
            except Exception:
                pass
        except Exception as e:
            preview_prompt = f"[预览失败] PROMPTS['chapter'].format 报错: {e}"

        dlg = QDialog(self)
        dlg.setWindowTitle(f"👁️ 预览发送给 AI 的 Prompt(已含盘古铁律,共 {len(preview_prompt)} 字符)")
        dlg.resize(900, 700)
        lay = QVBoxLayout(dlg)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setStyleSheet("font-family:'Consolas','Microsoft YaHei';font-size:12px;background:#fafafa; color:#3a3f47;")
        viewer.setPlainText(preview_prompt)
        lay.addWidget(viewer)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec_()

    def _on_pangu_apply_whitelist(self):
        # 应用白名单到 PanguEngine + 刷新高亮
        try:
            from pangu_system import PanguEngine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        text = self.tab_settings.pangu_whitelist_edit.toPlainText()
        PanguEngine.set_whitelist(text)
        wl = PanguEngine.get_whitelist()
        # 刷新章节编辑器高亮
        if hasattr(self.tab_editor, "pangu_highlighter") and self.tab_editor.pangu_highlighter:
            self.tab_editor.pangu_highlighter.refresh_words()
        QMessageBox.information(
            self, "白名单已应用",
            f"已设置 {len(wl)} 个允许词。\n这些词不会再被高亮 / 计入词扫:\n{', '.join(wl) if wl else '(空)'}")

    def _on_pangu_next_option_picked(self, option_text):
        """用户在元信息面板点了某条【下一章选项】 → 记录,下次 _send_next_chapter 注入"""
        self._user_picked_next_option = option_text
        QMessageBox.information(
            self, "✓ 已设定下章开局",
            f"已记录你选的下一章开局走向:\n\n{option_text}\n\n"
            f"下次生成下一章时,会自动把这条作为开局指引注入到 AI 提示词里。\n"
            f"(单次有效,生成后自动清空)")
        try:
            self.tab_generation.log(
                f"📌 用户指定下章开局:「{option_text[:40]}」", "info")
        except Exception:
            pass

    # ───── Phase B:30 项质检 JSON 解析 + 段落标注 ─────
    def _on_pangu_qcheck_response(self, content_response, original_chapter):
        # 解析 AI 返回的 JSON,把失败项映射到段落,然后让 highlighter 标黄
        import json as _json
        try:
            # 提取 JSON(可能包在 markdown code block 里)
            m = re.search(r"\{[\s\S]*\}", content_response)
            if not m:
                raise ValueError("没找到 JSON")
            data = _json.loads(m.group(0))
        except Exception as e:
            QMessageBox.warning(
                self, "盘古质检 JSON 解析失败",
                f"AI 返回不是合法 JSON,无法标注。\n错误:{e}\n\n原始返回前 500 字:\n{content_response[:500]}")
            return
        score = data.get("score", "?")
        failed = data.get("failed_items", [])
        advice = data.get("advice", "")
        # 在章节文本里找 advice 提到的关键词所在段落
        block_ids = set()
        if advice and original_chapter:
            for kw in re.findall(r"[\u4e00-\u9fa5]{2,10}", advice)[:20]:
                idx = original_chapter.find(kw)
                if idx >= 0:
                    block_no = original_chapter.count("\n", 0, idx)
                    block_ids.add(block_no)
        if hasattr(self.tab_editor, "pangu_highlighter") and self.tab_editor.pangu_highlighter:
            self.tab_editor.pangu_highlighter.set_qcheck_blocks(block_ids)

        # 弹结果对话框(改成 QDialog,加"AI 自动修复"按钮)
        dlg = QDialog(self)
        dlg.setWindowTitle("📊 智能质检结果 - 38 项")
        dlg.setMinimumWidth(600)
        lay = QVBoxLayout(dlg)

        # 顶部得分行
        score_lab = QLabel(f"<h2>得分:{score}/100</h2><b>失败项:</b>{failed}")
        score_lab.setStyleSheet("color:#2a6dcd; padding:6px;")
        lay.addWidget(score_lab)

        # 建议(可滚动)
        advice_lab = QLabel(f"<b>建议:</b><br>{advice}")
        advice_lab.setWordWrap(True)
        advice_lab.setStyleSheet("padding:8px; background:#f7f7f7; color:#3a3f47; border:1px solid #ddd;")
        advice_scroll = QScrollArea()
        advice_scroll.setWidget(advice_lab)
        advice_scroll.setWidgetResizable(True)
        advice_scroll.setMinimumHeight(150)
        lay.addWidget(advice_scroll, 1)

        if block_ids:
            seg_lab = QLabel(
                f"<i>相关段落已在编辑器里浅黄高亮(段号:{sorted(block_ids)[:10]})</i>")
            seg_lab.setStyleSheet("color:#888; padding:4px;")
            lay.addWidget(seg_lab)

        # v1.33:八大坑 K_scores 展示
        k_scores = data.get("K_scores", {})
        if k_scores:
            K_NAMES = {
                "K1": "视角统一", "K2": "对话有效", "K3": "爽点付费",
                "K4": "主角主动", "K5": "反派合理", "K6": "无毒点",
                "K7": "节奏紧凑", "K8": "市场意识",
            }
            k_lines = ["<b>🔥 八大坑专项评分:</b><table cellpadding='3'>"]
            for key in ("K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8"):
                sc = k_scores.get(key, "?")
                name = K_NAMES.get(key, key)
                # 进度条 0-10
                try:
                    sc_int = int(sc)
                    bar_fill = "█" * sc_int + "░" * (10 - sc_int)
                    color = ("#27ae60" if sc_int >= 8 else
                             "#f39c12" if sc_int >= 5 else "#e74c3c")
                except (ValueError, TypeError):
                    bar_fill, color = "?" * 10, "#888"
                k_lines.append(
                    f"<tr><td><b>{key} {name}</b></td>"
                    f"<td><span style='color:{color};font-family:monospace'>{bar_fill}</span></td>"
                    f"<td style='color:{color}'><b>{sc}/10</b></td></tr>")
            k_lines.append("</table>")
            k_worst = data.get("K_worst", [])
            if k_worst:
                k_lines.append(
                    f"<br><b>⚠ 最弱:</b>"
                    f"<span style='color:#e74c3c'>{', '.join(k_worst)}</span>")
            k_verdict = data.get("K_verdict", "")
            if k_verdict:
                k_lines.append(f"<br><i>{k_verdict}</i>")
            k_lab = QLabel("".join(k_lines))
            k_lab.setWordWrap(True)
            k_lab.setStyleSheet(
                "padding:8px; background:#fffbe6; color:#3a3f47; border:1px solid #f0c36d;")
            lay.addWidget(k_lab)

        # 按钮区
        btn_row = QHBoxLayout()
        btn_autofix = QPushButton("🔧 让 AI 自动修复这些问题")
        btn_autofix.setStyleSheet(
            "QPushButton { background:#b8651b; color:white; padding:8px 16px; "
            "border-radius:3px; font-weight:bold; font-size:14px; } "
            "QPushButton:hover { background:#9a4a12; }")
        btn_autofix.setToolTip(
            "把章节正文 + 失败项 + 建议发给 AI,让它直接重写有问题的部分。\n"
            "完成后修复版本会自动覆盖当前章节内容(原版本通过项目备份找回:菜单 → 🕓 恢复历史版本)。")
        btn_close = QPushButton("先关掉(我手动改)")
        btn_close.setStyleSheet("QPushButton { background:#888; color:white; padding:8px 16px; }")

        # 失败项太少时不必修复
        if not failed:
            btn_autofix.setEnabled(False)
            btn_autofix.setText("✓ 已无失败项,无需修复")
            btn_autofix.setStyleSheet(
                "QPushButton { background:#1f8b4d; color:white; padding:8px 16px; "
                "border-radius:3px; font-weight:bold; }")

        def _on_autofix():
            dlg.accept()
            self._on_pangu_autofix_request(score, failed, advice, original_chapter)

        btn_autofix.clicked.connect(_on_autofix)
        btn_close.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_autofix, 2)
        btn_row.addWidget(btn_close, 1)
        lay.addLayout(btn_row)

        dlg.exec_()

    def _on_pangu_autofix_request(self, score, failed, advice, original_chapter):
        """触发 AI 自动修复 — 把 issues + content 发给 AI 让它重写问题段落"""
        if not original_chapter or not original_chapter.strip():
            QMessageBox.warning(self, "提示", "原章节内容为空,无法修复")
            return
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录")
            return
        # 记下当前章节 idx,用于回填(用户可能中途切章节)
        ch_idx = getattr(self.tab_editor, "current_index", -1)
        if ch_idx < 0 or ch_idx >= len(self.chapters):
            QMessageBox.warning(
                self, "提示",
                "请先在左侧章节列表里选中要修复的章节(_current_index 无效)")
            return
        prompt = PROMPTS["pangu_autofix"].format(
            score=score,
            failed=failed if failed else "[]",
            advice=advice or "(无具体建议,请按盘古铁律检查并修复)",
            content=original_chapter[:8000],   # 安全截断
        )
        self.tab_generation.log(
            f"▶ 让 AI 修复第 {ch_idx+1} 章(失败项 {failed}),约 1 分钟回填……",
            "info")
        self._send_to_ai(
            prompt, f"AI 修复-第{ch_idx+1}章",
            target="pangu_autofix",
            ch_idx=ch_idx,
            original_chapter=original_chapter,
        )

    def _on_dialogue_critic_autofix_response(self, content, ch_idx, original_chapter):
        """v1.34: 13 法重写返回 → 回填章节(同 pangu_autofix 范式)"""
        if not content or not content.strip():
            QMessageBox.warning(
                self, "13 法重写失败", "AI 没返回任何内容,请重试或先检查浏览器/网络。")
            return
        fixed = content.strip()
        # 去除可能的元信息块
        try:
            from pangu_system import strip_chapter_meta
            fixed = strip_chapter_meta(fixed)
        except Exception:
            pass
        # 比较长度,异常时给提示
        orig_len = len(original_chapter)
        new_len = len(fixed)
        ratio = new_len / orig_len if orig_len > 0 else 1.0
        if ratio < 0.5 or ratio > 1.8:
            ret = QMessageBox.question(
                self, "⚠️ 重写结果异常",
                f"AI 返回内容长度跟原章节差太多:\n"
                f"  原长度: {orig_len} 字\n"
                f"  新长度: {new_len} 字 ({ratio*100:.0f}%)\n\n"
                f"是否仍然回填?\n"
                f"  是 → 用 AI 返回的内容覆盖章节\n"
                f"  否 → 丢弃 AI 返回",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if ret != QMessageBox.Yes:
                self.tab_generation.log(
                    "✗ 13 法重写结果被用户拒绝(长度异常)", "warn")
                # 给用户看看 AI 返回的内容
                from PyQt5.QtWidgets import (
                    QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox)
                d = QDialog(self)
                d.setWindowTitle("⚠️ 已丢弃的 AI 返回内容(供查看)")
                d.resize(700, 500)
                la = QVBoxLayout(d)
                te = QPlainTextEdit(fixed)
                te.setReadOnly(True)
                la.addWidget(te)
                bb = QDialogButtonBox(QDialogButtonBox.Close)
                bb.rejected.connect(d.reject)
                la.addWidget(bb)
                d.exec_()
                return
        # 安全检查通过 → 回填章节
        if 0 <= ch_idx < len(self.chapters):
            self.chapters[ch_idx]["content"] = fixed
            # 如果当前显示的是这一章,更新 UI
            if self.tab_editor.current_index == ch_idx:
                self.tab_editor.content_edit.setPlainText(fixed)
            self.tab_generation.log(
                f"✓ 第 {ch_idx+1} 章 13 法重写完成 ({orig_len} → {new_len} 字)",
                "success")
            # 触发 autosave 保险
            try:
                self.save_project()
            except Exception as _e:
                self.tab_generation.log(f"⚠ 自动保存失败:{_e}", "warn")
            # 弹完成提示
            QMessageBox.information(
                self, "✅ 13 法重写完成",
                f"第 {ch_idx+1} 章已用 AI 重写版本覆盖。\n"
                f"原长 {orig_len} 字 → 新长 {new_len} 字\n\n"
                f"原版本通过项目备份找回:\n"
                f"  菜单 → 文件 → 🕓 恢复历史版本")
        else:
            QMessageBox.warning(
                self, "回填失败", f"章节索引 {ch_idx} 无效")

    def _on_pangu_autofix_response(self, content, ch_idx, original_chapter):
        """AI 修复返回 → 回填当前章节(原内容已通过 save_project 的 .backups 备份)"""
        if not content or not content.strip():
            QMessageBox.warning(
                self, "AI 修复失败", "AI 没返回任何内容,请重试或先检查浏览器/网络。")
            return
        # 容错:去掉可能的 markdown 包裹 / 元信息块(用 pangu_system.strip_chapter_meta)
        fixed = content.strip()
        try:
            from pangu_system import strip_chapter_meta
            fixed = strip_chapter_meta(fixed)
        except Exception:
            pass
        # 比较长度,异常时给提示
        orig_len = len(original_chapter)
        new_len = len(fixed)
        ratio = new_len / orig_len if orig_len > 0 else 1.0
        if ratio < 0.5 or ratio > 1.8:
            ret = QMessageBox.question(
                self, "⚠️ 修复结果异常",
                f"AI 返回内容长度跟原章节差太多:\n"
                f"  原章节:{orig_len} 字  →  AI 返回:{new_len} 字(变化 {(ratio-1)*100:+.1f}%)\n\n"
                f"前 300 字预览:\n{fixed[:300]}...\n\n"
                f"还要回填吗?\n"
                f"  ✓ 是 → 覆盖当前章节(原内容已通过 .backups 备份)\n"
                f"  ✗ 否 → 放弃这次修复",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                self.tab_generation.log("已放弃 AI 修复结果(长度异常)", "warn")
                return
        # ─── 回填 ─── BUG-031 加固:核心动作 ① 绝对不被后续 UI/IO 失败连累
        if 0 <= ch_idx < len(self.chapters):
            # ① 核心:把内容写进 chapter dict — 一旦这步成功,回填这件事就完成了
            self.chapters[ch_idx]["content"] = fixed
            # ② 以下每一步独立 try,任何一步抛都不影响"内容已入章节"这个事实
            try:
                if self.tab_editor.current_index == ch_idx:
                    self.tab_editor.content_edit.setPlainText(fixed)
            except Exception as _e_ed:
                self.tab_generation.log(
                    f"⚠ 编辑器 setPlainText 失败(内容已入章节 dict):{_e_ed}", "warn")
            try:
                if hasattr(self.tab_editor, "pangu_highlighter") and self.tab_editor.pangu_highlighter:
                    self.tab_editor.pangu_highlighter.set_qcheck_blocks(set())
            except Exception:
                pass
            # 立即 autosave + 备份(失败也无所谓,内容已入 dict 下次手动保存即可)
            try:
                self.save_project()
            except Exception:
                try:
                    self._autosave()
                except Exception as _e_sv:
                    self.tab_generation.log(
                        f"⚠ 保存失败但内容已回填,可手动保存:{_e_sv}", "warn")
            try:
                self.tab_generation.log(
                    f"✓ AI 修复完成第 {ch_idx+1} 章:{orig_len}→{new_len} 字。"
                    f"原版本可通过菜单 → 🕓 恢复历史版本 找回",
                    "success")
            except Exception:
                pass
            try:
                QMessageBox.information(
                    self, "✓ AI 修复完成",
                    f"第 {ch_idx+1} 章已自动修复 + 回填 + 保存。\n\n"
                    f"字数变化:{orig_len} → {new_len}\n"
                    f"想要旧版本?菜单 → 文件 → 🕓 恢复历史版本(最近 10 次)\n\n"
                    f"建议:再点一次「📊 30项质检」看新得分。")
            except Exception:
                pass
        else:
            # ch_idx 不合法 — 不能静默,把内容塞剪贴板兜底 + 告知用户
            try:
                QApplication.clipboard().setText(fixed)
            except Exception:
                pass
            self.tab_generation.log(
                f"⚠ AI 修复回填失败:ch_idx={ch_idx} 超出章节范围(共 {len(self.chapters)} 章)。"
                f"已抓到 {new_len} 字,复制到剪贴板。",
                "error")
            QMessageBox.warning(
                self, "回填失败",
                f"无法把修复结果写入章节:ch_idx={ch_idx} 不在 0~{len(self.chapters)-1} 范围内。\n"
                f"内容({new_len} 字)已复制到剪贴板,可手动粘贴。")

    # ───── Phase B:盘古帮助查询面板 ─────
    def _on_pangu_show_manual(self):
        # 弹独立窗口展示盘古完整 spec,带搜索
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        full = get_default_engine().get_full_spec() if hasattr(get_default_engine(), "get_full_spec") else None
        if not full:
            try:
                with open("pangu_full_spec.md", "r", encoding="utf-8") as f:
                    full = f.read()
            except Exception:
                full = "(无法加载 pangu_full_spec.md)"
        dlg = QDialog(self)
        dlg.setWindowTitle("❓ 盘古超级系统 · 完整手册")
        dlg.resize(1100, 800)
        lay = QVBoxLayout(dlg)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("🔍 搜索:"))
        search_input = QLineEdit()
        search_input.setPlaceholderText("输入关键词回车跳转")
        srow.addWidget(search_input, 1)
        btn_next = QPushButton("下一个")
        srow.addWidget(btn_next)
        lay.addLayout(srow)
        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(True)
        viewer.setStyleSheet("font-family:'Microsoft YaHei';font-size:13px;line-height:1.6;")
        viewer.setMarkdown(full)
        lay.addWidget(viewer, 1)

        def do_search():
            kw = search_input.text().strip()
            if not kw:
                return
            cursor = viewer.document().find(kw, viewer.textCursor())
            if cursor.isNull():
                cursor = viewer.document().find(kw)
            if not cursor.isNull():
                viewer.setTextCursor(cursor)
                viewer.ensureCursorVisible()
        search_input.returnPressed.connect(do_search)
        btn_next.clicked.connect(do_search)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec_()

    # ───── Phase B:批量扫描整本书 ─────
    def _on_pangu_batch_scan(self):
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节")
            return
        try:
            from pangu_system import get_default_engine, PanguEngine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        engine = get_default_engine()
        results = []
        all_forbidden_count = {}
        for i, ch in enumerate(self.chapters):
            content = ch.get("content", "")
            if not content.strip():
                continue
            r = engine.quick_chapter_lint(content)
            results.append({
                "idx": i + 1,
                "title": ch.get("title", f"第{i+1}章"),
                "score": r.get("score", 0),
                "pass": r.get("pass", False),
                "issues": r.get("issues", []),
            })
            for w, c in PanguEngine.detect_forbidden_words(content):
                all_forbidden_count[w] = all_forbidden_count.get(w, 0) + c
        if not results:
            QMessageBox.information(self, "提示", "所有章节内容为空")
            return
        # 出报告
        avg = sum(r["score"] for r in results) / len(results)
        passed = sum(1 for r in results if r["pass"])
        top_words = sorted(all_forbidden_count.items(), key=lambda x: -x[1])[:10]
        lines = [
            f"# 盘古全书巡检报告",
            "",
            f"- 章节总数:**{len(results)}**",
            f"- 通过率:**{passed}/{len(results)}** ({passed * 100 // len(results)}%)",
            f"- 平均分:**{avg:.1f} / 100**",
            "",
            "## TOP 10 禁用词(全书累计)",
            "",
        ]
        for w, c in top_words:
            lines.append(f"- `{w}` × {c}")
        lines.extend([
            "",
            "## 各章详情",
            "",
            "| # | 标题 | 得分 | 通过 | 主要问题 |",
            "|---|---|---|---|---|",
        ])
        for r in results:
            ok = "✓" if r["pass"] else "✗"
            issues_s = " / ".join(r["issues"][:2]) if r["issues"] else "-"
            issues_s = issues_s.replace("|", "/")
            lines.append(f"| {r['idx']} | {r['title']} | {r['score']} | {ok} | {issues_s} |")
        report_md = "\n".join(lines)
        # 展示 + 提供保存按钮
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🛡️ 盘古全书巡检报告(共扫描 {len(results)} 章)")
        dlg.resize(1000, 720)
        lay = QVBoxLayout(dlg)
        viewer = QTextBrowser()
        viewer.setMarkdown(report_md)
        viewer.setStyleSheet("font-family:'Microsoft YaHei';font-size:13px;")
        lay.addWidget(viewer, 1)
        brow = QHBoxLayout()
        btn_save_md = QPushButton("💾 保存为 Markdown")
        btn_save_html = QPushButton("🌐 保存为 HTML")
        brow.addStretch()
        brow.addWidget(btn_save_md)
        brow.addWidget(btn_save_html)
        lay.addLayout(brow)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)

        def do_save_md():
            fn, _ = QFileDialog.getSaveFileName(
                dlg, "保存巡检报告", "盘古巡检报告.md", "Markdown (*.md)")
            if fn:
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(report_md)
                QMessageBox.information(dlg, "已保存", fn)

        def do_save_html():
            fn, _ = QFileDialog.getSaveFileName(
                dlg, "保存巡检报告", "盘古巡检报告.html", "HTML (*.html)")
            if fn:
                html_body = viewer.toHtml()
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(html_body)
                QMessageBox.information(dlg, "已保存", fn)

        btn_save_md.clicked.connect(do_save_md)
        btn_save_html.clicked.connect(do_save_html)
        dlg.exec_()

    # ───── Phase C-1:差异化说明弹窗 ─────
    def _on_pangu_diff_info(self):
        # 显示当前差异化状态 + 预览下一章会用什么参数
        try:
            from pangu_system import get_default_engine as _pg
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        enabled = (getattr(self.tab_settings, "pangu_check", None)
                   and self.tab_settings.pangu_check.isChecked())
        next_ch = len(self.chapters) + 1
        engine = _pg()
        recent = [c.get("content", "") for c in self.chapters[-3:]] if self.chapters else []
        preview = engine.build_seed_variation_block(next_ch, recent)
        jitter = engine.get_word_count_jitter(next_ch)
        status = "✅ 已启用" if enabled else "⊘ 已停用(盘古总开关关闭)"
        msg = (
            f"章节差异化:{status}\n\n"
            "原理:每章用不同的 RNG 种子,锁定到不同的开篇/节奏/感官组合,\n"
            "防止 AI 反复用同一套套路写章节。\n\n"
            f"下一章(第 {next_ch} 章)预览参数:\n{preview}\n\n"
            f"字数浮动:×{jitter:.2f}"
        )
        QMessageBox.information(self, "🎲 章节差异化(防套路)", msg)

    # ───── Phase C-3:盘古 ↔ lifespan_loops 联动 ─────
    def _install_pangu_lifespan_bridge(self):
        # 在 workflow post_write 加一个低优先级步骤:
        # 寿元/伏笔 audit 完后,自动跑盘古词扫,有问题就在日志提示用户做 30 项质检
        if not (getattr(self, "workflow", None) and self.workflow):
            return
        if not getattr(self.workflow, "_registry", None):
            return
        try:
            from workflow_pipeline import PipelineStep
        except ImportError:
            return

        mw = self

        class _PanguLifespanBridgeStep(PipelineStep):
            name = "pangu_lifespan_bridge"

            @property
            def enabled(self_step):
                pangu_on = (getattr(mw.tab_settings, "pangu_check", None)
                            and mw.tab_settings.pangu_check.isChecked())
                lifespan_on = bool(getattr(mw, "lifespan_ledger", {}).get("enabled"))
                return pangu_on and lifespan_on

            def run(self_step, ctx, done):
                content = getattr(ctx, "content", "")
                if not content:
                    done()
                    return
                try:
                    from pangu_system import get_default_engine
                    e = get_default_engine()
                    r = e.quick_chapter_lint(content)
                    if not r.get("pass") and hasattr(mw, "tab_generation"):
                        score = r.get("score", 0)
                        issues_cnt = len(r.get("issues", []))
                        level = "warn" if score < 70 else "info"
                        mw.tab_generation.log(
                            f"🌀 盘古-lifespan 联动:本章盘古词扫 {score}/100 ({issues_cnt} 处问题)。"
                            f"建议在章节编辑器点 📊 30项质检 做深度审稿。",
                            level
                        )
                except Exception:
                    pass
                done()

        self.workflow._registry.register(
            "post_write", _PanguLifespanBridgeStep(),
            priority=45  # 在 lifespan audit (35) / open_loops (40) 之后
        )

    # ───── Phase C-2:盘古风格库可视化编辑器 ─────
    def _on_pangu_style_editor(self):
        try:
            from pangu_system import STYLE_MAPPING, PanguEngine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        from PyQt5.QtCore import QSettings as _QS
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        _s = _QS("NovelAI", "PanguStyleLib")

        dlg = QDialog(self)
        dlg.setWindowTitle("🎨 盘古风格库编辑器")
        dlg.resize(1200, 700)
        lay = QVBoxLayout(dlg)
        info = QLabel(
            "在此编辑/添加/删除风格映射规则。每行一组:\n"
            "  · 关键词(用 | 分隔)\n"
            "  · 主风格 / 辅风格 / 点缀风格\n"
            "  · 女角色基调 / 适合平台\n"
            "保存后会持久化到本机,覆盖内置规则。点【恢复内置】可还原。"
        )
        info.setStyleSheet("color:#7a7a7a;padding:6px;background:#f5f5f5;border-radius:4px;")
        lay.addWidget(info)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["关键词(|分隔)", "主风格", "辅风格", "点缀", "女基调 / 平台"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        saved = _s.value("custom_mapping", None)
        if saved and isinstance(saved, list) and saved:
            rules = saved
        else:
            rules = [dict(r) for r in STYLE_MAPPING]

        def load_table(rs):
            table.setRowCount(len(rs))
            for i, r in enumerate(rs):
                table.setItem(i, 0, QTableWidgetItem(r.get("kw", "")))
                table.setItem(i, 1, QTableWidgetItem(r.get("main", "")))
                table.setItem(i, 2, QTableWidgetItem(r.get("sub", "")))
                table.setItem(i, 3, QTableWidgetItem(r.get("accent", "")))
                table.setItem(i, 4, QTableWidgetItem(
                    f"{r.get('female', '')} / {r.get('platform', '')}"))

        load_table(rules)
        lay.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ 添加")
        btn_del = QPushButton("🗑️ 删除选中")
        btn_save = QPushButton("💾 保存(覆盖内置)")
        btn_save.setStyleSheet("background:#16a085;color:white;padding:6px 14px;border-radius:3px;")
        btn_reset = QPushButton("🔄 恢复内置")
        btn_export = QPushButton("📤 导出")
        btn_close = QPushButton("关闭")
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        btn_row.addWidget(btn_export)
        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        def do_add():
            r = table.rowCount()
            table.insertRow(r)
            for col in range(5):
                table.setItem(r, col, QTableWidgetItem(""))

        def do_del():
            rows = sorted({i.row() for i in table.selectedIndexes()}, reverse=True)
            for r in rows:
                table.removeRow(r)

        def serialize_table():
            out = []
            for i in range(table.rowCount()):
                kw = table.item(i, 0).text().strip() if table.item(i, 0) else ""
                if not kw:
                    continue
                main = table.item(i, 1).text().strip() if table.item(i, 1) else ""
                sub = table.item(i, 2).text().strip() if table.item(i, 2) else ""
                accent = table.item(i, 3).text().strip() if table.item(i, 3) else ""
                fp = table.item(i, 4).text().strip() if table.item(i, 4) else ""
                if "/" in fp:
                    female, platform = [s.strip() for s in fp.split("/", 1)]
                else:
                    female, platform = fp, ""
                out.append({
                    "kw": kw, "main": main, "sub": sub,
                    "accent": accent, "female": female, "platform": platform,
                })
            return out

        def do_save():
            data = serialize_table()
            if not data:
                QMessageBox.warning(dlg, "保存失败", "至少需要 1 条规则")
                return
            _s.setValue("custom_mapping", data)
            from pangu_system import STYLE_MAPPING as _SM
            _SM.clear()
            _SM.extend(data)
            QMessageBox.information(dlg, "已保存",
                f"已保存 {len(data)} 条规则到本机,并立即生效。\n下次启动会自动加载。")

        def do_reset():
            if QMessageBox.question(
                dlg, "确认", "恢复成内置规则?会丢失你的自定义编辑。"
            ) != QMessageBox.Yes:
                return
            _s.remove("custom_mapping")
            import importlib
            import pangu_system as _ps
            importlib.reload(_ps)
            load_table(list(_ps.STYLE_MAPPING))

        def do_export():
            data = serialize_table()
            fn, _ = QFileDialog.getSaveFileName(
                dlg, "导出风格库", "盘古风格库.json", "JSON (*.json)")
            if fn:
                import json as _json
                Path(fn).write_text(_json.dumps(data, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
                QMessageBox.information(dlg, "已导出", fn)

        btn_add.clicked.connect(do_add)
        btn_del.clicked.connect(do_del)
        btn_save.clicked.connect(do_save)
        btn_reset.clicked.connect(do_reset)
        btn_export.clicked.connect(do_export)
        btn_close.clicked.connect(dlg.reject)
        dlg.exec_()


    def _on_chk_auto_extract_toggled(self, state):
        """v1.02 BUG-032:✨ 勾选时如果已有章节但 6 库空 → 问要不要立刻补抽
        防止用户勾上以为生效,实际 6 库永远是空的(只对未来章节起效)"""
        from PyQt5.QtCore import Qt
        if state != Qt.Checked:
            return  # 取消勾选不打扰
        # 检测:有章节内容吗?
        if not getattr(self, "chapters", None):
            return
        n_chapters = sum(1 for c in self.chapters if (c.get("content") or "").strip())
        if n_chapters == 0:
            return
        # 检测:6 库是不是全空?
        cl = self.tab_charlib
        total_rows = (
            cl.tbl_chars.rowCount() + cl.tbl_relations.rowCount()
            + cl.tbl_timeline.rowCount() + cl.tbl_items.rowCount()
            + cl.tbl_fore.rowCount())
        if total_rows > 0:
            return  # 已有数据,不打扰
        # 弹问 — 用 QTimer 延后避免 stateChanged 信号正在处理时打开 modal
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._ask_backfill_charlib(n_chapters))

    def _ask_backfill_charlib(self, n_chapters):
        """实际的弹问 + 触发补抽"""
        ret = QMessageBox.question(
            self, "💡 库还是空的",
            f"你已经写了 {n_chapters} 章,但角色/关系/伏笔等库还是空的。\n\n"
            f"勾选「✨ 每章生成后自动抽取」只对【未来章节】生效。\n"
            f"要立刻给已有的 {n_chapters} 章一次性抽一遍吗?\n\n"
            f"  ✓ 是 → 现在就抽(每章约 30 秒,共需约 {n_chapters * 30 // 60 + 1} 分钟)\n"
            f"  ✗ 否 → 不抽,你可以稍后点「🔄 立即从所有章节提取」按钮",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes)
        if ret == QMessageBox.Yes:
            self._charlib_extract_from_chapters()

    def _charlib_extract_from_chapters(self):
        """从已写章节用 AI 一键提取角色/关系/物品/事件/伏笔"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节,无法提取")
            return
        if not self.worker.is_ready():
            self._switch_to_tab(self.tab_generation)
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』,完成 AI 网站登录后再提取。")
            return
        # 让用户选范围
        from PyQt5.QtWidgets import QInputDialog
        max_ch = len(self.chapters)
        text, ok = QInputDialog.getText(
            self, "提取范围",
            f"请输入要提取的章节范围(共 {max_ch} 章)\n"
            f"格式:'all' 或 '1-5' 或 '3' (单章)\n"
            f"建议:每次 3-5 章一批,避免提示词过长",
            text=f"1-{min(5, max_ch)}")
        if not ok or not text.strip():
            return
        # 解析范围
        nums = []
        try:
            t = text.strip().lower()
            if t == "all":
                nums = list(range(1, max_ch + 1))
            elif "-" in t:
                a, b = t.split("-")
                nums = list(range(int(a), int(b) + 1))
            else:
                nums = [int(t)]
        except Exception:
            QMessageBox.warning(self, "格式错误", "请按照 '1-5' 或 '3' 格式输入")
            return
        nums = [n for n in nums if 1 <= n <= max_ch]
        if not nums:
            return

        self._charlib_batch_queue = nums
        self.tab_generation.log(
            f"▶ 开始批量提取角色库,共 {len(nums)} 章: {nums}", "info")
        self._run_next_charlib_extract()

    def _run_next_charlib_extract(self):
        """处理 charlib 提取队列里下一个章节"""
        queue = getattr(self, "_charlib_batch_queue", None)
        if not queue:
            self.tab_generation.log("✅ 角色库批量提取完成", "success")
            # 如果是 _post_chapter_chain 触发的,推进链
            if getattr(self, "_charlib_chain_post", False):
                self._charlib_chain_post = False
                QTimer.singleShot(500, self._run_next_post_chapter_step)
            else:
                self._switch_to_tab(self.tab_charlib)
            return
        ch_num = queue.pop(0)
        ch = self.chapters[ch_num - 1]
        content = ch.get("content", "")
        if not content.strip():
            QTimer.singleShot(100, self._run_next_charlib_extract)
            return
        # 现有数据摘要(避免重复提取)
        existing = self.tab_charlib.serialize()
        existing_brief = json.dumps({
            "characters": [r[0] for r in existing.get("characters", []) if r[0]],
            "items":      [r[0] for r in existing.get("items", []) if r[0]],
        }, ensure_ascii=False)[:600]

        prompt = PROMPTS["world_extract"].format(
            ch_num=ch_num,
            existing=existing_brief,
            content=content[:5000],
        )
        # v1.02:让用户看到 6 库抽取真的发出去了
        self.tab_generation.log(
            f"🎭 第 {ch_num} 章 库抽取启动 → 发送 world_extract({len(prompt)} 字)",
            "info")
        self._send_to_ai(
            prompt,
            f"提取角色库-第{ch_num}章",
            target="world_extract",
            ch_num=ch_num,
        )

    def _on_world_extract_received(self, content, ch_num):
        """world_extract 回调:解析 JSON 并合并到 charlib"""
        if not content.strip():
            self.tab_generation.log(f"第{ch_num}章提取为空", "warn")
            QTimer.singleShot(500, self._run_next_charlib_extract)
            return
        # 容错:抠出 JSON 部分(去掉可能的 markdown 包裹)
        text = content.strip()
        if "```" in text:
            import re as _re
            m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.S)
            if m:
                text = m.group(1)
        # 找第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end+1]
        try:
            data = json.loads(text)
        except Exception as e:
            # v1.02 BUG-032:JSON 解析失败 → 重试 1 次(BUG-027 风格防抓取串)
            retry_n = getattr(self, "_world_extract_retry", {}).get(ch_num, 0)
            if retry_n < 1:
                self._world_extract_retry = getattr(self, "_world_extract_retry", {})
                self._world_extract_retry[ch_num] = retry_n + 1
                self.tab_generation.log(
                    f"⚠ 第{ch_num}章 库抽取 JSON 解析失败({e}),"
                    f"疑似抓取串了,等 2s 后重试(第 {retry_n + 1}/1 次)",
                    "warn")
                self.tab_generation.log(f"  原始前 200 字: {content[:200]}", "warn")
                # 重新塞回队列
                if not hasattr(self, "_charlib_batch_queue"):
                    self._charlib_batch_queue = []
                self._charlib_batch_queue.insert(0, ch_num)
                QTimer.singleShot(2000, self._run_next_charlib_extract)
                return
            self.tab_generation.log(
                f"⚠ 第{ch_num}章 库抽取 JSON 解析最终失败({e}),跳过此章",
                "error")
            self.tab_generation.log(f"  原始前 300 字: {content[:300]}", "warn")
            QTimer.singleShot(500, self._run_next_charlib_extract)
            return

        # v1.02:检测"AI 返回了合法 JSON 但全部数组全空" — 也算抓取串/AI 没识别
        # v1.74:加上 power_levels(战力体系)一起算
        # v1.77:加上 promises(威胁承诺)一起算
        # v1.78:加上 arcs / relations_value / goals(剧情进度)一起算
        # v1.79:加上 infos / info_disclosures(信息隔离)一起算
        # v1.80:加上 plot_branches(剧情树)一起算
        all_empty = not any(
            (data.get(k) or []) for k in
            ("characters", "relations", "items", "events", "foreshadows",
             "power_levels", "promises",
             "arcs", "relations_value", "goals",
             "infos", "info_disclosures",
             "plot_branches")
        )
        if all_empty:
            retry_n = getattr(self, "_world_extract_retry", {}).get(ch_num, 0)
            if retry_n < 1:
                self._world_extract_retry = getattr(self, "_world_extract_retry", {})
                self._world_extract_retry[ch_num] = retry_n + 1
                self.tab_generation.log(
                    f"⚠ 第{ch_num}章 库抽取 AI 返回全部分类皆空,疑似抓取串/AI 误解,"
                    f"等 2s 后重试(第 {retry_n + 1}/1 次)",
                    "warn")
                if not hasattr(self, "_charlib_batch_queue"):
                    self._charlib_batch_queue = []
                self._charlib_batch_queue.insert(0, ch_num)
                QTimer.singleShot(2000, self._run_next_charlib_extract)
                return

        added = self._merge_into_charlib(data)
        hero_n = added.get("hero", 0)
        pw_n = added.get("pw", 0)
        pr_n = added.get("pr", 0)
        arc_n = added.get("arc", 0)   # v1.78
        rv_n = added.get("rv", 0)     # v1.78
        gl_n = added.get("gl", 0)     # v1.78
        info_n = added.get("info", 0) # v1.79
        kb_n = added.get("kb", 0)     # v1.79
        pt_n = added.get("pt", 0)     # v1.80
        self.tab_generation.log(
            f"✓ 第{ch_num}章 库提取完成: 角色+{added['ch']} 关系+{added['rel']} "
            f"物品+{added['it']} 时间线+{added['ev']} 伏笔+{added['fo']}"
            + (f" 战力+{pw_n}" if pw_n else "")
            + (f" 承诺+{pr_n}" if pr_n else "")
            + (f" 弧线+{arc_n}" if arc_n else "")
            + (f" 关系值+{rv_n}" if rv_n else "")
            + (f" 目标+{gl_n}" if gl_n else "")
            + (f" 信息+{info_n}" if info_n else "")
            + (f" 知情+{kb_n}" if kb_n else "")
            + (f" 树节点+{pt_n}" if pt_n else "")
            + (f" 主角状态+{hero_n}" if hero_n else ""),
            "success")
        # 触发下一章
        QTimer.singleShot(800, self._run_next_charlib_extract)

    def _merge_into_charlib(self, data):
        """把提取的数据合并进 charlib UI 表格(去重)"""
        from PyQt5.QtWidgets import QTableWidgetItem
        cl = self.tab_charlib
        added = {"ch": 0, "rel": 0, "it": 0, "ev": 0, "fo": 0, "pw": 0, "pr": 0,
                 "arc": 0, "rv": 0, "gl": 0,                # v1.78
                 "info": 0, "kb": 0,                         # v1.79
                 "pt": 0,                                    # v1.80 plot tree
                 "hero": 0}

        def existing_names(tbl, col=0):
            return set((tbl.item(r, col).text() if tbl.item(r, col) else "")
                       for r in range(tbl.rowCount()))

        # 角色
        ex_chars = existing_names(cl.tbl_chars)
        for c in (data.get("characters") or []):
            name = c.get("name", "").strip()
            if not name or name in ex_chars:
                continue
            row = cl.tbl_chars.rowCount()
            cl.tbl_chars.insertRow(row)
            vals = [
                name, c.get("role", "配角"), c.get("appearance", ""),
                c.get("personality", ""), c.get("mark", ""),
                c.get("ability", ""), c.get("state", ""),
                str(c.get("first_ch", "")),
            ]
            for col, v in enumerate(vals):
                cl.tbl_chars.setItem(row, col, QTableWidgetItem(str(v)))
            added["ch"] += 1
            ex_chars.add(name)

        # 关系(去重 key=a+type+b)
        ex_rels = set()
        for r in range(cl.tbl_relations.rowCount()):
            a = cl.tbl_relations.item(r, 0).text() if cl.tbl_relations.item(r, 0) else ""
            t = cl.tbl_relations.item(r, 1).text() if cl.tbl_relations.item(r, 1) else ""
            b = cl.tbl_relations.item(r, 2).text() if cl.tbl_relations.item(r, 2) else ""
            ex_rels.add(f"{a}|{t}|{b}")
        for rel in (data.get("relations") or []):
            a = rel.get("a", "").strip()
            t = rel.get("type", "").strip()
            b = rel.get("b", "").strip()
            if not (a and t and b):
                continue
            k = f"{a}|{t}|{b}"
            if k in ex_rels:
                continue
            row = cl.tbl_relations.rowCount()
            cl.tbl_relations.insertRow(row)
            for col, v in enumerate([a, t, b, rel.get("note", "")]):
                cl.tbl_relations.setItem(row, col, QTableWidgetItem(v))
            added["rel"] += 1
            ex_rels.add(k)

        # 物品
        ex_items = existing_names(cl.tbl_items)
        for it in (data.get("items") or []):
            name = it.get("name", "").strip()
            if not name or name in ex_items:
                continue
            row = cl.tbl_items.rowCount()
            cl.tbl_items.insertRow(row)
            vals = [name, it.get("type", "法器"), it.get("owner", ""),
                    str(it.get("source_ch", "")), it.get("ability", "")]
            for col, v in enumerate(vals):
                cl.tbl_items.setItem(row, col, QTableWidgetItem(str(v)))
            added["it"] += 1
            ex_items.add(name)

        # 事件
        ex_evs = set()
        for r in range(cl.tbl_timeline.rowCount()):
            ch = cl.tbl_timeline.item(r, 0).text() if cl.tbl_timeline.item(r, 0) else ""
            ev = cl.tbl_timeline.item(r, 1).text() if cl.tbl_timeline.item(r, 1) else ""
            ex_evs.add(f"{ch}|{ev[:20]}")
        for ev in (data.get("events") or []):
            ch = str(ev.get("ch", ""))
            evt = ev.get("event", "").strip()
            if not evt:
                continue
            k = f"{ch}|{evt[:20]}"
            if k in ex_evs:
                continue
            row = cl.tbl_timeline.rowCount()
            cl.tbl_timeline.insertRow(row)
            for col, v in enumerate([ch, evt, ev.get("state_change", "")]):
                cl.tbl_timeline.setItem(row, col, QTableWidgetItem(v))
            added["ev"] += 1
            ex_evs.add(k)

        # 伏笔
        ex_fos = set()
        for r in range(cl.tbl_fore.rowCount()):
            ch = cl.tbl_fore.item(r, 0).text() if cl.tbl_fore.item(r, 0) else ""
            ct = cl.tbl_fore.item(r, 1).text() if cl.tbl_fore.item(r, 1) else ""
            ex_fos.add(f"{ch}|{ct[:30]}")
        for fo in (data.get("foreshadows") or []):
            ch = str(fo.get("ch", ""))
            ct = fo.get("content", "").strip()
            if not ct:
                continue
            k = f"{ch}|{ct[:30]}"
            if k in ex_fos:
                continue
            row = cl.tbl_fore.rowCount()
            cl.tbl_fore.insertRow(row)
            vals = [ch, ct, str(fo.get("plan_pay_at", "0")), "否", ""]
            for col, v in enumerate(vals):
                cl.tbl_fore.setItem(row, col, QTableWidgetItem(v))
            added["fo"] += 1
            ex_fos.add(k)
        
        # v1.74:战力体系 power_levels(去重 key=realm+level)
        ex_pws = set()
        for r in range(cl.tbl_power.rowCount()):
            rl = cl.tbl_power.item(r, 0).text() if cl.tbl_power.item(r, 0) else ""
            lv = cl.tbl_power.item(r, 1).text() if cl.tbl_power.item(r, 1) else ""
            ex_pws.add(f"{rl}|{lv}")
        for pw in (data.get("power_levels") or []):
            rl = str(pw.get("realm", "")).strip()
            lv = str(pw.get("level", "")).strip()
            if not rl:  # 至少要有大段
                continue
            k = f"{rl}|{lv}"
            if k in ex_pws:
                continue
            row = cl.tbl_power.rowCount()
            cl.tbl_power.insertRow(row)
            vals = [rl, lv, pw.get("power", ""), pw.get("note", "")]
            for col, v in enumerate(vals):
                cl.tbl_power.setItem(row, col, QTableWidgetItem(str(v)))
            added["pw"] += 1
            ex_pws.add(k)
        
        # v1.77:威胁承诺 promises(去重 key=ch + from + to + content[:30])
        if hasattr(cl, "tbl_promises"):
            ex_prs = set()
            for r in range(cl.tbl_promises.rowCount()):
                ch = cl.tbl_promises.item(r, 0).text() if cl.tbl_promises.item(r, 0) else ""
                fr = cl.tbl_promises.item(r, 2).text() if cl.tbl_promises.item(r, 2) else ""
                to = cl.tbl_promises.item(r, 3).text() if cl.tbl_promises.item(r, 3) else ""
                ct = cl.tbl_promises.item(r, 4).text() if cl.tbl_promises.item(r, 4) else ""
                ex_prs.add(f"{ch}|{fr}|{to}|{ct[:30]}")
            for pr in (data.get("promises") or []):
                if not isinstance(pr, dict):
                    continue
                ch = str(pr.get("ch", "")).strip()
                kind = str(pr.get("kind", "承诺")).strip() or "承诺"
                fr = str(pr.get("from", "")).strip()
                to = str(pr.get("to", "")).strip()
                ct = str(pr.get("content", "")).strip()
                if not ct:
                    continue
                k = f"{ch}|{fr}|{to}|{ct[:30]}"
                if k in ex_prs:
                    continue
                row = cl.tbl_promises.rowCount()
                cl.tbl_promises.insertRow(row)
                vals = [ch, kind, fr, to, ct,
                        str(pr.get("deadline", "0")), "否"]
                for col, v in enumerate(vals):
                    cl.tbl_promises.setItem(row, col, QTableWidgetItem(str(v)))
                added["pr"] = added.get("pr", 0) + 1
                ex_prs.add(k)

        # v1.78:故事弧线 arcs(去重 key=name;progress 取较大值,phase 用新值)
        if hasattr(cl, "tbl_arcs"):
            ex_arcs = {}  # name -> row idx
            for r in range(cl.tbl_arcs.rowCount()):
                nm = cl.tbl_arcs.item(r, 0).text() if cl.tbl_arcs.item(r, 0) else ""
                if nm:
                    ex_arcs[nm] = r
            for arc in (data.get("arcs") or []):
                if not isinstance(arc, dict):
                    continue
                nm = str(arc.get("name", "")).strip()
                if not nm:
                    continue
                try:
                    new_prog = max(0, min(100, int(arc.get("progress", 0) or 0)))
                except (TypeError, ValueError):
                    new_prog = 0
                phase = str(arc.get("phase", "开端")).strip() or "开端"
                if nm in ex_arcs:
                    r = ex_arcs[nm]
                    try:
                        old_prog = int(cl.tbl_arcs.item(r, 1).text()
                                       if cl.tbl_arcs.item(r, 1) else "0")
                    except (TypeError, ValueError):
                        old_prog = 0
                    if new_prog > old_prog:
                        cl.tbl_arcs.setItem(r, 1, QTableWidgetItem(str(new_prog)))
                    cl.tbl_arcs.setItem(r, 2, QTableWidgetItem(phase))
                    continue
                row = cl.tbl_arcs.rowCount()
                cl.tbl_arcs.insertRow(row)
                for col, v in enumerate([nm, str(new_prog), phase]):
                    cl.tbl_arcs.setItem(row, col, QTableWidgetItem(v))
                added["arc"] = added.get("arc", 0) + 1
                ex_arcs[nm] = row

        # v1.78:关系值矩阵 relations_value(去重 key=a|b;value 用新值)
        if hasattr(cl, "tbl_rel_values"):
            ex_rvs = {}
            for r in range(cl.tbl_rel_values.rowCount()):
                a = cl.tbl_rel_values.item(r, 0).text() if cl.tbl_rel_values.item(r, 0) else ""
                b = cl.tbl_rel_values.item(r, 1).text() if cl.tbl_rel_values.item(r, 1) else ""
                if a and b:
                    ex_rvs[f"{a}|{b}"] = r
            for rv in (data.get("relations_value") or []):
                if not isinstance(rv, dict):
                    continue
                a = str(rv.get("a", "")).strip()
                b = str(rv.get("b", "")).strip()
                if not (a and b):
                    continue
                try:
                    val = max(-100, min(100, int(rv.get("value", 0) or 0)))
                except (TypeError, ValueError):
                    val = 0
                ch = str(rv.get("ch", "1")).strip() or "1"
                k = f"{a}|{b}"
                if k in ex_rvs:
                    r = ex_rvs[k]
                    cl.tbl_rel_values.setItem(r, 2, QTableWidgetItem(str(val)))
                    cl.tbl_rel_values.setItem(r, 3, QTableWidgetItem(ch))
                    continue
                row = cl.tbl_rel_values.rowCount()
                cl.tbl_rel_values.insertRow(row)
                for col, v in enumerate([a, b, str(val), ch]):
                    cl.tbl_rel_values.setItem(row, col, QTableWidgetItem(v))
                added["rv"] = added.get("rv", 0) + 1
                ex_rvs[k] = row

        # v1.78:当前目标 goals(去重 key=name;status 用新值)
        if hasattr(cl, "tbl_goals"):
            ex_gls = {}
            for r in range(cl.tbl_goals.rowCount()):
                nm = cl.tbl_goals.item(r, 0).text() if cl.tbl_goals.item(r, 0) else ""
                if nm:
                    ex_gls[nm] = r
            for gl in (data.get("goals") or []):
                if not isinstance(gl, dict):
                    continue
                nm = str(gl.get("name", "")).strip()
                if not nm:
                    continue
                priority = str(gl.get("priority", "主线")).strip() or "主线"
                status = str(gl.get("status", "进行中")).strip() or "进行中"
                set_ch = str(gl.get("set_ch", "1")).strip() or "1"
                if nm in ex_gls:
                    r = ex_gls[nm]
                    cl.tbl_goals.setItem(r, 2, QTableWidgetItem(status))
                    continue
                row = cl.tbl_goals.rowCount()
                cl.tbl_goals.insertRow(row)
                for col, v in enumerate([nm, priority, status, set_ch]):
                    cl.tbl_goals.setItem(row, col, QTableWidgetItem(v))
                added["gl"] = added.get("gl", 0) + 1
                ex_gls[nm] = row

        # v1.79:关键信息条目 infos(content 去重 + id 自动续号 + remap 表)
        id_remap = {}
        if hasattr(cl, "tbl_infos"):
            ex_infos_by_content = {}
            used_ids = set()
            for r in range(cl.tbl_infos.rowCount()):
                ct_it = cl.tbl_infos.item(r, 1)
                id_it = cl.tbl_infos.item(r, 0)
                if ct_it and ct_it.text().strip():
                    ex_infos_by_content[ct_it.text().strip()] = r
                if id_it and id_it.text().strip():
                    used_ids.add(id_it.text().strip())

            def _next_info_id():
                n = 1
                while f"INFO-{n:03d}" in used_ids:
                    n += 1
                used_ids.add(f"INFO-{n:03d}")
                return f"INFO-{n:03d}"

            for info in (data.get("infos") or []):
                if not isinstance(info, dict):
                    continue
                content = str(info.get("content", "")).strip()
                if not content:
                    continue
                raw_id = str(info.get("id", "")).strip()
                if content in ex_infos_by_content:
                    r = ex_infos_by_content[content]
                    existing_id = cl.tbl_infos.item(r, 0).text() if cl.tbl_infos.item(r, 0) else ""
                    if raw_id:
                        id_remap[raw_id] = existing_id
                    continue
                final_id = raw_id if (raw_id and raw_id not in used_ids
                                       and re.match(r"^INFO-\d{3}$", raw_id)) else _next_info_id()
                if raw_id and final_id != raw_id:
                    id_remap[raw_id] = final_id
                used_ids.add(final_id)
                src_ch = str(info.get("source_ch", "1")).strip() or "1"
                src_type = str(info.get("source_type", "设定")).strip() or "设定"
                row = cl.tbl_infos.rowCount()
                cl.tbl_infos.insertRow(row)
                for col, v in enumerate([final_id, content, src_ch, src_type]):
                    cl.tbl_infos.setItem(row, col, QTableWidgetItem(v))
                added["info"] = added.get("info", 0) + 1
                ex_infos_by_content[content] = row

        # v1.79:知情人 known_by(同时接受 known_by + info_disclosures,悬挂引用过滤)
        if hasattr(cl, "tbl_known_by"):
            ex_kbs = set()
            for r in range(cl.tbl_known_by.rowCount()):
                info_it = cl.tbl_known_by.item(r, 0)
                ch_it = cl.tbl_known_by.item(r, 1)
                if info_it and ch_it and info_it.text().strip() and ch_it.text().strip():
                    ex_kbs.add(f"{info_it.text().strip()}|{ch_it.text().strip()}")

            kb_records = []
            for kb in (data.get("known_by") or []):
                if isinstance(kb, dict):
                    kb_records.append({
                        "info_id": str(kb.get("info_id", "")).strip(),
                        "character": str(kb.get("character", "")).strip(),
                        "via": str(kb.get("via", "")).strip(),
                    })
            for dc in (data.get("info_disclosures") or []):
                if isinstance(dc, dict):
                    kb_records.append({
                        "info_id": str(dc.get("info_id", "")).strip(),
                        "character": str(dc.get("to", "") or dc.get("character", "")).strip(),
                        "via": str(dc.get("via", "")).strip(),
                    })

            # 收集有效 info_ids 以过滤悬挂引用
            valid_ids = set()
            if hasattr(cl, "tbl_infos"):
                for r in range(cl.tbl_infos.rowCount()):
                    it = cl.tbl_infos.item(r, 0)
                    if it and it.text().strip():
                        valid_ids.add(it.text().strip())

            for rec in kb_records:
                info_id = id_remap.get(rec["info_id"], rec["info_id"])
                character = rec["character"]
                via = rec["via"]
                if not (info_id and character):
                    continue
                if info_id not in valid_ids:
                    continue  # 悬挂引用过滤
                k = f"{info_id}|{character}"
                if k in ex_kbs:
                    continue
                row = cl.tbl_known_by.rowCount()
                cl.tbl_known_by.insertRow(row)
                for col, v in enumerate([info_id, character, via or "未知途径"]):
                    cl.tbl_known_by.setItem(row, col, QTableWidgetItem(v))
                added["kb"] = added.get("kb", 0) + 1
                ex_kbs.add(k)

        # v1.80:剧情树 plot_branches(直接委托 CharacterLibrary.merge_dicts 的逻辑)
        # 因为 plot_branches 的合并比其他更复杂(扁平 list 重建树 + node_id remap),
        # 不重复实现,只把 plot_branches 字段切出来调一次 cl.merge_dicts
        if hasattr(cl, "tree_plot") and (data.get("plot_branches") or []):
            sub_added = cl.merge_dicts({"plot_branches": data.get("plot_branches", [])})
            added["pt"] = added.get("pt", 0) + sub_added.get("pt", 0)

        # v1.64+v1.74:hero_state 字段(B 方案 — AI 写完每章后自动同步主角状态)
        # 由 QSettings 开关控制,默认开启
        # v1.74:prompt 已改成快照模式(每次都输出完整状态),根因修复;
        #         同时 n_filled=0 时也更新 label 表示"已同步但本章无变化"
        try:
            from PyQt5.QtCore import QSettings
            auto_sync = QSettings("NovelAI", "CreationSettings").value(
                "auto_sync_hero_state", True, type=bool)
        except Exception:
            auto_sync = True
        
        if auto_sync:
            hs = data.get("hero_state") or {}
            # 诊断日志:打印 AI 实际返回的 hero_state(关键 5 字段),便于排查
            try:
                hs_repr = {k: hs.get(k, "") for k in
                           ("age", "realm", "location", "faction", "mood")}
                print(f"[hero_state v1.74] ch={data.get('_ch', '?')} AI 返回: {hs_repr}",
                      flush=True)
            except Exception:
                pass
            if isinstance(hs, dict) and hs:
                try:
                    n = cl.apply_hero_state_dict(hs)
                    added["hero"] = n
                    # 即使 n=0 也更新 label,表示"AI 已同步但本章无变化"
                    try:
                        if n > 0:
                            cl.lbl_hero_source.setText(
                                f"📌 数据来源:AI 自动同步({n}/5 字段更新)")
                            cl.lbl_hero_source.setStyleSheet(
                                "color: #2a6dcd; font-size: 11px; "
                                "padding: 2px 4px; font-weight:bold;")
                        else:
                            # AI 返回了 hero_state 字典但 5 字段全空 → 仍算同步过
                            cl.lbl_hero_source.setText(
                                "📌 数据来源:AI 已同步(本章主角状态无变化)")
                            cl.lbl_hero_source.setStyleSheet(
                                "color: #7a7a7a; font-size: 11px; "
                                "padding: 2px 4px;")
                    except Exception:
                        pass
                except Exception as _e:
                    print(f"[hero_state] apply 失败: {_e}", flush=True)
            else:
                # AI 完全没返回 hero_state 字段 — 这是 prompt 没生效或 AI 输出格式不对
                # 不跳过:用空字典也调一次同步(避免永远不更新)
                hs = {}
                print(f"[hero_state v1.74] AI 没返回 hero_state 字段,用空字典尝试同步",
                      flush=True)

        return added

    def _canon_extract_all_chapters(self):
        """从所有已生成章节自动抽取 Canon"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节,无法抽取")
            return
        if not self.worker.is_ready():
            self._switch_to_tab(self.tab_generation)
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』,完成 AI 网站登录后再抽取。")
            return
        ret = QMessageBox.question(
            self, "确认",
            f"将对 {len(self.chapters)} 章逐一发送 AI 抽取设定,大约需要 "
            f"{len(self.chapters) * 30} 秒。是否继续?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self._canon_batch_pipeline = list(range(1, len(self.chapters) + 1))
        self._run_next_canon_extract()

    def _run_next_canon_extract(self):
        if not getattr(self, "_canon_batch_pipeline", None):
            self.tab_generation.log("✓ Canon 批量抽取完成", "success")
            return
        ch_num = self._canon_batch_pipeline.pop(0)
        ch = self.chapters[ch_num - 1]
        if not ch.get("content"):
            QTimer.singleShot(100, self._run_next_canon_extract)
            return
        # 复用现有 _run_canon_extract 但要在响应里推进队列
        self._canon_batch_active = True
        self._run_canon_extract(ch["content"], ch_num)

    def _skill_test_run(self):
        """技能 Tab 里点「测试运行」时,在当前编辑器选中章节上跑该技能"""
        idx = self.tab_skills._current_idx
        if idx < 0 or idx >= len(self.tab_skills.skills):
            QMessageBox.information(self, "提示", "请先在左侧选中一个技能")
            return
        skill = self.tab_skills.skills[idx]
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器", "请先到『生成控制』启动浏览器")
            return
        ch_idx = self.chapter_list.currentRow()
        if ch_idx < 0 or ch_idx >= len(self.chapters):
            QMessageBox.information(self, "提示", "请先在左侧选中一章")
            return
        # 使用编辑器当前文本(用户可能改过未保存)
        body = self.tab_editor.content_edit.toPlainText()
        self._run_skill_on_chapter(skill, ch_idx + 1, body_override=body)

    def _show_chapter_editor_menu(self, pos):
        """章节编辑器右键菜单 - 应用技能"""
        menu = self.tab_editor.content_edit.createStandardContextMenu()
        manual_skills = self.tab_skills.get_manual_skills()
        if manual_skills:
            menu.addSeparator()
            sk_menu = menu.addMenu("⚡ 应用技能")
            for s in manual_skills:
                act = sk_menu.addAction(s["name"])
                act.triggered.connect(
                    lambda _, sk=s: self._apply_manual_skill_to_editor(sk))
        menu.exec_(self.tab_editor.content_edit.mapToGlobal(pos))

    def _apply_manual_skill_to_editor(self, skill):
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器", "请先到『生成控制』启动浏览器")
            return
        ch_idx = self.chapter_list.currentRow()
        ch_num = ch_idx + 1 if ch_idx >= 0 else 0

        # selected_text 模式:取选中文本;否则取全文
        target = skill.get("target", "current_chapter")
        if target == "selected_text":
            cur = self.tab_editor.content_edit.textCursor()
            if not cur.hasSelection():
                QMessageBox.information(
                    self, "提示",
                    f"技能「{skill['name']}」目标是选中文本,但你没有选中任何内容。\n"
                    f"请先选中一段再调用,或改技能 target 为 current_chapter")
                return
            body = cur.selectedText().replace('\u2029', '\n')
        else:
            body = self.tab_editor.content_edit.toPlainText()

        self._run_skill_on_chapter(skill, ch_num, body_override=body)
    def _submit_summary_task(self, ch_num, chain_to_next=False,
                             chain_full_memory=False, _done_cb=None):
        """提交一个『生成本章摘要』的任务给浏览器自动化"""
        if not (0 < ch_num <= len(self.chapters)):
            return
        ch = self.chapters[ch_num - 1]
        max_len = self.tab_memory.summary_len.value()
        prompt = PROMPTS["chapter_summary"].format(
            max_len=max_len,
            title=ch.get("title", f"第{ch_num}章"),
            content=ch.get("content", "")[:5000],
        )
        self._send_to_ai(
            prompt, f"摘要-第{ch_num}章",
            target="chapter_summary",
            ch_num=ch_num,
            chain_to_next=chain_to_next,
            chain_full_memory=chain_full_memory,
            _done_cb=_done_cb,          # workflow_pipeline 回调
            # v1.91 BUG-065:把章节正文/标题塞进 meta,供 worker 降级时使用
            _ch_content=ch.get("content", ""),
            _ch_title=ch.get("title", f"第{ch_num}章"),
        )

    def _split_and_save_golden_three(self, content):
        """把黄金三章按 ===第N章=== 拆分入库"""
        chunks = re.split(r'={2,}\s*第\s*[一二三123]\s*章[^\n=]*={2,}', content)
        chunks = [c.strip() for c in chunks if c.strip()]
        if len(chunks) < 3:
            # 退化:整体作为一章
            self.chapters.append({"title": "黄金三章合订", "content": content})
        else:
            titles = re.findall(r'={2,}\s*(第\s*[一二三123]\s*章[^=\n]*?)={2,}', content)
            for i, body in enumerate(chunks[:3]):
                t = titles[i].strip() if i < len(titles) else f"第{i+1}章"
                self.chapters.append({"title": t, "content": body})
        self._refresh_chapter_list()
        if self.tab_generation.auto_save.isChecked():
            for ch in self.chapters[-3:]:
                self._save_chapter_to_disk(ch)
        self.tab_generation.log("✓ 黄金三章已生成并保存", "success")

    def _extract_chapter_title(self, content):
        """从生成内容里尝试提取章节标题
        支持格式:
          第 1 章 觉醒之夜
          第一章 觉醒之夜
          第1章：觉醒之夜
          【第 1 章】觉醒之夜
        """
        for line in content.splitlines()[:5]:
            line = line.strip()
            if not line:
                continue
            # 匹配各种章节标题格式
            m = re.match(
                r'^[【\[]?\s*第\s*[一二三四五六七八九十百千零\d]+\s*章[】\]]?\s*[：:、\s]*\s*(.*)$',
                line
            )
            if m:
                # 整行作为完整标题(包含"第N章 xxx")
                # 限制长度,避免把正文也算进来
                if len(line) <= 50:
                    return line
                # 太长说明是正文,不是标题
                continue
        return None

    def _strip_chapter_title(self, content):
        """如果首行是章节标题就移除 + 最终防线剥离任何残留元信息"""
        # ── 最终防线:强制再 strip 一次元信息(双保险,不管上游有没有剥过)
        try:
            from pangu_system import strip_chapter_meta
            content = strip_chapter_meta(content)
        except Exception:
            pass

        lines = content.splitlines()
        if not lines:
            return content
        first = lines[0].strip()
        if re.match(r'^[【\[]?\s*第\s*[一二三四五六七八九十百千零\d]+\s*章', first) and len(first) <= 50:
            # 移除标题行 + 可能的空行
            i = 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            return "\n".join(lines[i:])
        return content

    def _check_foreshadow_alert(self, ch_num):
        """检查即将到期的伏笔,如有则弹窗提醒"""
        if not hasattr(self, "tab_charlib"):
            return
        cl = self.tab_charlib
        urgent = []  # 0~3章后该回收
        overdue = []  # 已超期
        for r in range(cl.tbl_fore.rowCount()):
            ch_set = cl.tbl_fore.item(r, 0).text() if cl.tbl_fore.item(r, 0) else "0"
            content = cl.tbl_fore.item(r, 1).text() if cl.tbl_fore.item(r, 1) else ""
            ch_pay = cl.tbl_fore.item(r, 2).text() if cl.tbl_fore.item(r, 2) else "0"
            paid = cl.tbl_fore.item(r, 3).text() if cl.tbl_fore.item(r, 3) else "否"
            if paid == "是" or not content:
                continue
            try:
                ch_pay_int = int(ch_pay)
            except ValueError:
                continue
            # v1.76 BUG-056:ch_pay=0 是 AI 评估失败的占位,不算超期(应该走重评估按钮)
            if ch_pay_int == 0:
                continue
            distance = ch_pay_int - ch_num
            if distance < 0:
                overdue.append((ch_set, content, ch_pay, abs(distance)))
            elif distance <= 3:
                urgent.append((ch_set, content, ch_pay, distance))
        if not urgent and not overdue:
            return
        # 弹窗
        msg_lines = [f"🔔 第 {ch_num} 章生成前伏笔提醒:\n"]
        if overdue:
            msg_lines.append(f"⚠️ 已超期未回收的伏笔 ({len(overdue)} 个):")
            for cs, ct, cp, d in overdue[:5]:
                msg_lines.append(f"  · 第{cs}章埋: {ct[:50]}")
                msg_lines.append(f"    应在第{cp}章回收,已超 {d} 章")
        if urgent:
            msg_lines.append(f"\n🎯 即将回收的伏笔 ({len(urgent)} 个):")
            for cs, ct, cp, d in urgent[:5]:
                flag = "本章可回收!" if d == 0 else f"还有 {d} 章"
                msg_lines.append(f"  · 第{cs}章埋: {ct[:50]} [{flag}]")
        msg_lines.append("\n是否继续生成? (这些信息已自动注入到提示词中提醒AI)")
        ret = QMessageBox.question(
            self, "伏笔提醒", "\n".join(msg_lines),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret == QMessageBox.No:
            self._batch_paused = True
            self._batch_remaining = 0
            self.tab_generation.log("用户取消,批量生成已停止", "warn")

    def _build_prev_context(self, ch_num):
        """v1.22 BUG-040 / v1.63 多章注入:构造【前情提要】块,注入到 chapter prompt

        组成(按用户配置):
          1. 早期章节摘要(第 1 章到第 ch_num-N-1 章,如有 summary 字段)
             — 仅当 use_summaries=True 才注入
          2. 最近 N 章正文(N = chapters_n 设置,默认 1)
             每章超过 tail_chars 字时截尾

        若没有上一章 / 第 1 章 → 返回空字符串(prompt 模板 {prev_context} 不显示)
        """
        if not self.chapters or ch_num <= 1:
            return ""
        
        # 读取配置(找 CreationSettings,失败用默认值)
        try:
            cfg = self.tab_generation.get_ctx_config()
        except Exception:
            from PyQt5.QtCore import QSettings
            qs = QSettings("NovelAI", "CreationSettings")
            cfg = {
                "chapters_n":    qs.value("prev_chapters_n", 1, type=int),
                "tail_chars":    qs.value("prev_chapter_tail_chars", 2500, type=int),
                "use_summaries": qs.value("prev_use_summaries", True, type=bool),
            }
        
        # 边界 clamp
        n_full = max(1, min(10, cfg["chapters_n"]))
        tail_n = max(500, min(8000, cfg["tail_chars"]))
        use_summaries = bool(cfg["use_summaries"])
        
        # 实际能拿到的章数 = min(配置, 已有章数)
        # 第 ch_num 章未生成时,self.chapters 含 ch_num-1 章
        avail = len(self.chapters)  # 已有章数
        n_full = min(n_full, avail)
        
        sections = []
        injected_summary_n = 0
        injected_full_n = 0
        total_chars = 0
        
        # 1. 早期章节摘要(第 1 章 ~ 第 avail-n_full 章)
        if use_summaries:
            summary_end = avail - n_full   # exclusive
            if summary_end > 0:
                early_summaries = []
                for i in range(summary_end):
                    c = self.chapters[i]
                    s = (c.get("summary") or "").strip()
                    if s:
                        snippet = s[:200]
                        early_summaries.append(f"  · 第 {i+1} 章:{snippet}")
                        injected_summary_n += 1
                        total_chars += len(snippet)
                if early_summaries:
                    sections.append(
                        "▼ 早期章节摘要(主线脉络)\n"
                        + "\n".join(early_summaries))
        
        # 2. 最近 N 章完整正文(每章超 tail_chars 截尾)
        full_chapters_block_lines = []
        # 倒数 n_full 章 = chapters[avail-n_full : avail]
        for offset in range(n_full):
            idx = avail - n_full + offset   # 0-based
            ch = self.chapters[idx]
            content = (ch.get("content") or "").strip()
            if not content:
                continue
            
            # 截尾
            if len(content) > tail_n:
                content_block = content[-tail_n:]
                truncated = True
            else:
                content_block = content
                truncated = False
            
            title = (ch.get("title") or "").strip() or f"第 {idx+1} 章"
            
            # 多章时:加章节分隔标记;单章时:保持原 v1.22 格式不变
            if n_full == 1:
                header = "▼ 上一章正文末尾(直接承接,语气/动作/情节请连续)"
                header += f"\n  上一章标题:《{title}》"
                if truncated:
                    header += f"(全文 {len(content)} 字,只取末尾 {tail_n} 字)"
                full_chapters_block_lines.append(f"{header}\n\n{content_block}")
            else:
                marker = "末尾" if truncated else "完整"
                full_chapters_block_lines.append(
                    f"━━━━ 第 {idx+1} 章《{title}》({marker} {len(content_block)} 字)━━━━\n"
                    f"{content_block}")
            
            injected_full_n += 1
            total_chars += len(content_block)
        
        if full_chapters_block_lines:
            if n_full == 1:
                sections.extend(full_chapters_block_lines)
            else:
                # 多章 — 加个总标题
                sections.append(
                    "▼ 最近 {n} 章正文(直接承接,语气/动作/情节请连续)\n\n".format(
                        n=injected_full_n)
                    + "\n\n".join(full_chapters_block_lines))
        
        # 诊断 log
        try:
            self.tab_generation.log(
                f"📖 已注入前情:{injected_full_n} 章正文"
                + (f" + {injected_summary_n} 章摘要" if injected_summary_n else "")
                + f"({total_chars} 字)",
                "info")
        except Exception:
            pass
        
        if not sections:
            return ""
        
        return (
            "【前情提要 — 保持一致性的关键】\n"
            + "\n\n".join(sections)
            + "\n\n"
        )
    
    def _update_ctx_estimate(self):
        """v1.63:根据当前 chapters + ctx 设置,实时算预估注入字数并显示。
        
        触发点:
          · CreationSettings 三个控件变化(信号)
          · 章节列表变更(可在 update_chapter_list 末尾调一次)
        """
        try:
            cfg = self.tab_generation.get_ctx_config()
        except Exception:
            return
        
        lbl = getattr(self.tab_generation, "prev_ctx_estimate", None)
        if lbl is None:
            return
        
        chapters = self.chapters or []
        n_full_req = cfg["chapters_n"]
        tail_n = cfg["tail_chars"]
        use_summaries = cfg["use_summaries"]
        avail = len(chapters)
        
        # 没有任何章节
        if avail == 0:
            lbl.setText(
                f"📊 预估注入字数:0(还没有章节,生成第 1 章时不注入前情)\n"
                f"   配置:最近 {n_full_req} 章 × 最多 {tail_n} 字/章" +
                (" + 早期摘要" if use_summaries else ""))
            return
        
        # 实际注入章数 = min(配置, 已有)
        n_full = min(n_full_req, avail)
        
        # 完整正文字数
        full_chars = 0
        for offset in range(n_full):
            idx = avail - n_full + offset
            content = (chapters[idx].get("content") or "").strip()
            full_chars += min(len(content), tail_n)
        
        # 摘要字数(每章 ≤200 字)
        summary_chars = 0
        summary_count = 0
        if use_summaries:
            for i in range(avail - n_full):
                s = (chapters[i].get("summary") or "").strip()
                if s:
                    summary_chars += min(len(s), 200)
                    summary_count += 1
        
        total = full_chars + summary_chars
        
        # 警示色:>15000 字开始警示,>30000 字爆红
        if total > 30000:
            color = "#cc3333"
            warning = "  ⚠ 偏大,小心 AI 上下文溢出"
        elif total > 15000:
            color = "#cc8800"
            warning = "  ⚠ 较多,留意 token 消耗"
        else:
            color = "#1a4480"
            warning = ""
        
        next_ch = avail + 1
        msg = (
            f"📊 写第 {next_ch} 章时预估注入:<b>{total:,}</b> 字{warning}\n"
            f"   ├ 最近 {n_full} 章正文:{full_chars:,} 字"
            + (f"(配置要 {n_full_req} 章,但只有 {avail} 章)"
               if n_full < n_full_req else "")
            + (f"\n   └ 早期 {summary_count} 章摘要:{summary_chars:,} 字"
               if use_summaries and summary_count else "")
        )
        lbl.setText(msg)
        lbl.setStyleSheet(
            f"color: {color}; font-weight: bold; "
            "padding: 4px 8px; background: #eef4fb; border-radius: 3px;")

    def _send_next_chapter(self):
        """批量生成里发下一章(自动注入对话记忆+伏笔提醒)"""
        if self._batch_paused or self._batch_remaining <= 0:
            # 批量结束,清 silent 标记(下次单章生成或重启批量恢复正常)
            if getattr(self, "_batch_silent", False):
                self._batch_silent = False
            return
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        ch_num = len(self.chapters) + 1

        # ★ 伏笔到期提醒(只在第1章和达到回收期的章节弹一次,且仅手动模式)
        if hasattr(self, "tab_charlib") and not getattr(self, "_batch_silent", False):
            self._check_foreshadow_alert(ch_num)

        outline = (self.tab_outline.worldview_edit.toPlainText() + "\n"
                   + self.tab_outline.structure_edit.toPlainText())[:1500]
        target = self.tab_settings.get_words_per_chapter()
        offset = self.tab_settings.get_prompt_offset()
        target_with_offset = max(500, target + offset)
        # Phase C-1:盘古章节差异化(随盘古总开关启用)
        _diff_block = ""
        try:
            if (getattr(self.tab_settings, "pangu_check", None)
                    and self.tab_settings.pangu_check.isChecked()):
                from pangu_system import get_default_engine as _pg_get
                _recent = [c.get("content", "") for c in self.chapters[-3:]] if self.chapters else []
                _diff_block = _pg_get().build_seed_variation_block(ch_num, _recent)
                # 字数浮动 ±10%(章节确定性,同章重试拿同样结果)
                _jitter = _pg_get().get_word_count_jitter(ch_num)
                target_with_offset = max(500, int(target_with_offset * _jitter))
        except Exception:
            pass
        min_words = max(300, int(target_with_offset * 0.85))
        full = self.tab_settings.get_full_settings_block()
        prev_context = self._build_prev_context(ch_num)
        prompt = PROMPTS["chapter"].format(
            chapter_num=ch_num,
            title=self.tab_settings.get_title(),
            genre="/".join(self.tab_settings.get_selected_genres() or ["言情"]),
            outline=outline,
            chapter_outline=co[:2500],
            prev_context=prev_context,
            min_words=min_words, target_words=target_with_offset,
        ) + f"\n\n【完整设定参考】\n{full}"
        if _diff_block:
            prompt += f"\n\n{_diff_block}"

        # BUG-014:如果用户在上一章元信息面板点了"下一章选项",
        # 把它作为本章开局指引注入(prompt 末尾,优先级高)
        picked_opt = getattr(self, "_user_picked_next_option", None)
        if picked_opt:
            prompt += (
                f"\n\n【本章开局指引(用户从上一章【下一章选项】中指定)】\n"
                f"本章必须从以下情境展开:{picked_opt}\n"
                f"严格按这条线索写,不要换到其他选项。"
            )
            self.tab_generation.log(
                f"已注入用户指定的下章开局:{picked_opt[:30]}...", "info")
            # 用完即清,避免影响后续章节
            self._user_picked_next_option = None
        else:
            # 用户没点选项 → 自动用上一章的元信息引导
            # (钩子 / 待解决悬念 / 备选下一章方向)
            if self.chapters and len(self.chapters) >= 1:
                prev_ch = self.chapters[-1]
                hook = prev_ch.get("hook") or {}
                cool = prev_ch.get("cool_points") or []
                opts = prev_ch.get("next_options") or []
                bridge_lines = []
                if hook and hook.get("content"):
                    htype = hook.get("type", "")
                    bridge_lines.append(
                        f"上一章悬念(类型:{htype}):{hook['content']}")
                if opts:
                    bridge_lines.append(
                        f"上一章列出的可能走向(任选其一展开,或合并几条):\n  "
                        + "\n  ".join(f"- {o}" for o in opts[:5]))
                if cool:
                    bridge_lines.append(
                        f"上一章已用爽点(避免重复):{', '.join(c[:30] for c in cool[:3])}")
                if bridge_lines:
                    prompt += (
                        "\n\n【本章承接(自动从上一章元信息提取)】\n"
                        + "\n".join(bridge_lines)
                        + "\n要求:本章开篇直接承接上面的悬念,把它推进到下一个高潮。"
                    )
                    self.tab_generation.log(
                        f"已自动注入上一章承接信息({len(bridge_lines)} 条)",
                        "info")

                # 防重复:扫最近 3 章钩子类型 + 爽点类型,如有连用同种,提示 AI 换花样
                recent_3 = self.chapters[-3:]
                hook_types = [
                    (c.get("hook") or {}).get("type", "")
                    for c in recent_3
                    if c.get("hook")
                ]
                cool_types = []
                for c in recent_3:
                    for cp in (c.get("cool_points") or []):
                        # 取 "类型:内容" 的类型部分
                        m = re.match(r'^\s*([^::]{1,8})\s*[::]', cp)
                        if m:
                            cool_types.append(m.group(1).strip())
                # 找连用同种(2 次及以上)
                from collections import Counter
                hook_cnt = Counter(hook_types)
                cool_cnt = Counter(cool_types)
                avoid_lines = []
                for t, n in hook_cnt.items():
                    if t and n >= 2:
                        avoid_lines.append(
                            f"- 钩子类型【{t}】最近{n}章已用,本章换其他类型"
                            f"(对话没说完/人物出现/秘密暴露/倒计时/关键动作)")
                for t, n in cool_cnt.items():
                    if t and n >= 2:
                        avoid_lines.append(
                            f"- 爽点类型【{t}】最近{n}章已用,本章换其他类型"
                            f"(打脸/反转/碾压/揭秘/救场/装逼/复仇)")
                if avoid_lines:
                    prompt += (
                        "\n\n【避免审美疲劳(最近章节统计)】\n"
                        + "\n".join(avoid_lines))
                    self.tab_generation.log(
                        f"已注入防重复提示({len(avoid_lines)} 条):避免连用同类型钩子/爽点",
                        "info")

        # ★ 注入对话记忆(旧路径兜底:仅在 workflow 不可用时执行)
        if not self.workflow:
            if self.tab_memory.auto_inject.isChecked():
                mem_block = self._build_memory_block()
                if mem_block:
                    prompt += f"\n\n{mem_block}"
                    self.tab_generation.log(
                        f"已注入对话记忆({len(mem_block)} 字符)到第 {ch_num} 章提示词", "info")

            # ★ B 模块:注入 Canon 设定约束
            if self.tab_canon.chk_inject.isChecked():
                canon_block = self._build_canon_block()
                if canon_block:
                    prompt += f"\n\n{canon_block}"
                    self.tab_generation.log(
                        f"已注入 Canon 约束({len(canon_block)} 字符)到第 {ch_num} 章提示词", "info")

            # ★ 角色库 + 关系 + 时间线 + 物品 + 伏笔 一键注入
            if hasattr(self, "tab_charlib"):
                charlib_block = self.tab_charlib.build_inject_block(current_chapter=ch_num)
                if charlib_block:
                    prompt += charlib_block
                    self.tab_generation.log(
                        f"已注入角色与世界状态({len(charlib_block)} 字符)到第 {ch_num} 章提示词", "info")

        if self.workflow:
            # ★ 新路径:PRE_WRITE 阶段负责注入,workflow 接管完整生命周期
            self.workflow.start(
                prompt=prompt,
                ch_num=ch_num,
                target_words=target_with_offset,
                min_words=min_words,
                retry_left=self.tab_generation.retry_count.value(),
            )
        else:
            # 旧路径兜底
            self._send_to_ai(
                prompt, f"第 {ch_num} 章",
                target="chapter", ch_num=ch_num,
                target_words=target_with_offset, min_words=min_words,
                retry_left=self.tab_generation.retry_count.value(),
                original_prompt=prompt,
            )

    # ===================================================================
    # 对话记忆系统
    # ===================================================================
    # ===================================================================
    # E 模块:对话槽管理(随时换对话 + 自动同步记忆)
    # ===================================================================

    def _conv_save_current_slot(self):
        """保存当前 URL 为命名槽"""
        url = self.tab_generation.url_input.text().strip()
        if not url:
            QMessageBox.information(self, "提示", "URL 框为空,请先填入对话地址")
            return
        ch_num = len(self.chapters)
        # 生成默认名:AI站点 + 当前章数
        site = self.tab_generation.site_combo.currentText()
        from datetime import datetime as _dt
        default_name = f"{site}-ch{ch_num}-{_dt.now().strftime('%H%M')}"
        name, ok = QInputDialog.getText(
            self, "保存对话槽", "槽名称:", text=default_name)
        if not ok or not name.strip():
            return
        sw = self.tab_generation.conv_switcher
        idx = sw.add_slot(name.strip(), url, ai_site=site, chapter_at=ch_num)
        sw.set_active(idx)
        self.tab_generation.log(f"📌 已保存对话槽「{name.strip()}」(ch{ch_num})", "success")

    def _conv_switch_selected(self):
        """切换到列表中选中的槽"""
        sw = self.tab_generation.conv_switcher
        slot = sw.get_selected_slot()
        if not slot:
            QMessageBox.information(self, "提示", "请先在列表中选中一个对话槽")
            return
        url = slot.get("url", "").strip()
        if not url:
            QMessageBox.warning(self, "槽 URL 为空", f"槽「{slot['name']}」没有保存有效 URL")
            return
        sync = sw.chk_sync.isChecked()

        # 1. 切换 URL
        self.tab_generation.url_input.setText(url)
        row = sw.slot_list.currentRow()
        sw.set_active(row)
        self.tab_generation.log(
            f"🔄 切换到对话槽「{slot['name']}」(url={url[:60]}...)", "info")

        # 2. 导航到新 URL
        if self.worker.is_ready():
            self.worker.submit({
                "action": "goto",
                "url": url,
                "task_id": f"切换对话槽-{slot['name']}",
            })
        else:
            self.tab_generation.log(
                "⚠ 浏览器未就绪,已更新 URL 框,待启动后可手动访问", "warn")

        # 3. 同步记忆(可选)
        if sync:
            # 用 QTimer 错开,让 goto 先完成
            QTimer.singleShot(3500, self._conv_send_restore_prompt)
        else:
            self.tab_generation.log(
                "ℹ 未开启「切换时同步记忆」,跳过上下文恢复", "info")

    def _conv_open_new_dialog(self):
        """在浏览器中打开新对话页,然后引导用户保存"""
        site = self.tab_generation.site_combo.currentText()
        url = AI_URLS.get(site, "https://chat.deepseek.com/")
        if self.worker.is_ready():
            self.worker.submit({
                "action": "goto",
                "url": url,
                "task_id": "新建对话槽",
            })
            QMessageBox.information(
                self, "新建对话",
                f"已导航到 {site} 主页。\n\n"
                "请在浏览器里开启一个新对话,\n"
                "然后把新对话的完整 URL 复制到「URL」框,\n"
                "再点「📌 保存当前」绑定为槽。")
        else:
            QMessageBox.information(
                self, "提示",
                "请先启动浏览器,再点「新建槽」。")

    def _build_context_restore_prompt(self) -> str:
        """
        构建「记忆恢复」提示词:把书名/进度/角色/摘要/长期记忆/Canon
        打包成一条完整的上下文恢复消息,发给新对话窗口。
        AI 读完后确认,之后就能像老对话一样继续写。
        """
        title = self.tab_settings.get_title() or "未命名小说"
        genre = "/".join(self.tab_settings.get_selected_genres() or ["—"])
        ch_count = len(self.chapters)
        next_ch = ch_count + 1

        parts = [
            f"你是我的网文写作助手,正在辅助创作《{title}》。\n"
            f"以下是目前的全部写作进度,请仔细阅读后回复确认。\n",

            f"【基本信息】\n"
            f"书名:《{title}》  题材:{genre}  "
            f"当前进度:已完成第 {ch_count} 章,下一章将写第 {next_ch} 章\n",
        ]

        # 角色档案
        chars = self.tab_memory.chars_edit.toPlainText().strip()
        if chars:
            parts.append(f"【角色档案(人设/状态/关系,必须保持一致)】\n{chars}\n")

        # 章节摘要
        sums = self.tab_memory.parse_summaries()
        if sums:
            lines = [f"第{n}章:{s}" for n, s in sorted(sums.items())]
            parts.append("【已完成章节摘要(按顺序,了解剧情脉络)】\n" + "\n".join(lines) + "\n")

        # 最近 N 章详细
        recent_n = self.tab_memory.recent_n.value()
        if recent_n > 0 and self.chapters:
            start = max(0, ch_count - recent_n)
            detail = []
            for ch in self.chapters[start:]:
                body = (ch.get("content") or "").strip()
                tail = ("..." + body[-500:]) if len(body) > 500 else body
                s = f"——{ch.get('title','')}——"
                if ch.get("summary"):
                    s += f"\n[核心] {ch['summary']}"
                s += f"\n[末尾片段]\n{tail}"
                detail.append(s)
            if detail:
                parts.append(
                    f"【最近 {len(detail)} 章详细内容(衔接关键)】\n\n"
                    + "\n\n".join(detail) + "\n")

        # 长期记忆
        lt = self.tab_memory.long_term_edit.toPlainText().strip()
        if lt:
            parts.append(
                f"【长期记忆 / 重要伏笔(不可遗忘,不可矛盾)】\n{lt}\n")

        # Canon 约束
        canon_block = self._build_canon_block()
        if canon_block:
            parts.append(canon_block + "\n")

        # 世界观/大纲片段
        wv = self.tab_outline.worldview_edit.toPlainText().strip()[:600]
        if wv:
            parts.append(f"【世界观/设定(节选)】\n{wv}\n")

        parts.append(
            f"以上就是全部进度。\n"
            f"请回复:「已了解,当前进度:第 {ch_count} 章已完成,"
            f"下一章将写第 {next_ch} 章,随时可以继续。」"
        )

        return "\n\n".join(parts)

    def _conv_send_restore_prompt(self):
        """向当前 URL(新对话)发送一次完整的记忆恢复提示词"""
        if not self.worker.is_ready():
            self.tab_generation.log(
                "⚠ 浏览器未就绪,无法发送记忆恢复提示词", "warn")
            return
        prompt = self._build_context_restore_prompt()
        self.tab_generation.log(
            f"📨 发送记忆恢复提示词({len(prompt)} 字符)…", "info")
        self._send_to_ai(
            prompt,
            label="记忆恢复·上下文同步",
            target="conv_restore",
        )

    def get_unified_chars_summary(self):
        """v1.23 BUG-041:统一的角色档案数据接口

        合并两个数据源(避免 critique_character 永远 (暂无)):
        1. tab_charlib(6 库自动抽取的结构化数据)— 优先
        2. tab_memory.chars_edit(对话记忆 prose 文本)— 兜底

        如果两个都空返回 "" — 调用方自己决定显示 "(暂无)" 还是跳过整段
        """
        lines = []
        # 优先 1:6 库角色表
        try:
            if hasattr(self, "tab_charlib") and hasattr(self.tab_charlib, "tbl_chars"):
                cl = self.tab_charlib
                rows = []
                for r in range(cl.tbl_chars.rowCount()):
                    cells = [
                        cl.tbl_chars.item(r, c).text() if cl.tbl_chars.item(r, c) else ""
                        for c in range(8)
                    ]
                    name, role, look, pers, mark, ability, state, _ = cells
                    if not name.strip():
                        continue
                    bits = []
                    if role:    bits.append(f"定位-{role}")
                    if look:    bits.append(f"外貌-{look}")
                    if pers:    bits.append(f"性格-{pers}")
                    if mark:    bits.append(f"标志-{mark}")
                    if ability: bits.append(f"能力-{ability}")
                    if state:   bits.append(f"状态-{state}")
                    rows.append(f"  · {name}:" + "; ".join(bits))
                if rows:
                    lines.append("[来源:角色与世界库,共 {} 人]".format(len(rows)))
                    lines.extend(rows[:10])   # 最多 10 人,避免过长
        except Exception:
            pass
        # 兜底 2:对话记忆 prose
        try:
            prose = self.tab_memory.chars_edit.toPlainText().strip()
            if prose:
                if lines:
                    lines.append("\n[来源:对话记忆 prose 补充]")
                lines.append(prose)
        except Exception:
            pass
        return "\n".join(lines)

    def _build_memory_block(self):
        """
        组装记忆块:角色档案 + 早期章节摘要 + 最近 N 章详细尾段 + 长期伏笔
        返回完整的 【对话记忆】 段落,可直接拼到提示词末尾
        """
        parts = []
        m = self.tab_memory

        # 1. 角色档案
        chars = m.chars_edit.toPlainText().strip()
        if chars:
            parts.append(f"【角色档案(必须保持人设一致)】\n{chars}")

        # 2. 章节摘要 + 最近 N 章详细
        recent_n = m.recent_n.value()
        cur_ch_count = len(self.chapters)
        sums = m.parse_summaries()
        if cur_ch_count > 0:
            sum_lines = []
            # 早期章节(只用摘要)
            early_end = max(0, cur_ch_count - recent_n)
            for n in range(1, early_end + 1):
                if n in sums:
                    sum_lines.append(f"第{n}章:{sums[n]}")
            if sum_lines:
                parts.append("【已发生剧情概要(早期章节)】\n" + "\n".join(sum_lines))

            # 最近 N 章详细尾段
            if recent_n > 0:
                start = max(0, cur_ch_count - recent_n)
                detail_chunks = []
                for ch in self.chapters[start:]:
                    body = (ch.get("content") or "").strip()
                    # 取尾段 + 摘要
                    tail = body[-400:] if len(body) > 400 else body
                    block = f"——{ch.get('title', '')}——"
                    if ch.get("summary"):
                        block += f"\n[本章核心] {ch['summary']}"
                    if tail:
                        block += f"\n[本章末尾片段]\n...{tail}"
                    detail_chunks.append(block)
                if detail_chunks:
                    parts.append(
                        f"【最近 {len(detail_chunks)} 章详细回顾(请基于这些细节衔接)】\n"
                        + "\n\n".join(detail_chunks))

        # 3. 长期记忆
        lt = m.long_term_edit.toPlainText().strip()
        if lt:
            parts.append(f"【长期记忆 - 重要伏笔/物品/关系(不要遗忘、不要矛盾)】\n{lt}")

        if not parts:
            return ""
        return "【对话记忆 - AI 必读 ↓】\n" + "\n\n".join(parts)

    def _refresh_memory_preview(self):
        """更新对话记忆预览面板"""
        block = self._build_memory_block()
        if not block:
            self.tab_memory.preview_edit.setPlainText(
                "(暂无记忆内容。请先生成章节,或手动填写角色/长期记忆)")
        else:
            self.tab_memory.preview_edit.setPlainText(block)
        self.tab_generation.log(
            f"记忆预览已刷新,共 {len(block)} 字符", "info")

    # ===================================================================
    # Canon 设定守护(B 模块)
    # ===================================================================
    def _build_canon_block(self):
        """组装 Canon 约束块,注入到下一章提示词末尾"""
        if not hasattr(self, "tab_canon"):
            return ""
        locked = self.tab_canon.serialize_locked()
        evolving = self.tab_canon.serialize_evolving()
        if locked == "(暂无锁定项)" and evolving == "(暂无演化项)":
            return ""
        return (
            "【★ Canon 核心设定 - 绝对不可违反 ★】\n"
            "以下是必须遵守的核心设定,任何与之冲突的内容都视为这章作废。\n\n"
            "[锁定项 - 严格遵守]\n" + locked + "\n\n"
            "[演化项 - 可推进但不可凭空打脸]\n" + evolving)

    def _run_canon_audit(self, content, ch_num, on_done):
        """对一章正文跑 Canon 稽核 prompt(含反重复检测)。
        on_done(violations: list) 在 AI 回复后被调用。"""
        if not hasattr(self, "tab_canon"):
            on_done([])
            return
        locked = self.tab_canon.serialize_locked()
        evolving = self.tab_canon.serialize_evolving()
        if locked == "(暂无锁定项)" and evolving == "(暂无演化项)":
            on_done([])
            return

        # 收集前面章节的关键事件(用于反重复检测)
        prev_events = []
        for i, ch in enumerate(self.chapters):
            if i >= ch_num - 1:
                break  # 只看前面的章节
            summary = ch.get("summary", "")
            ch_content = ch.get("content", "")
            if summary:
                prev_events.append(f"第{i+1}章: {summary[:150]}")
            elif ch_content:
                # 没有摘要就用正文前200字
                prev_events.append(f"第{i+1}章: {ch_content[:200]}...")
        prev_events_text = "\n".join(prev_events) if prev_events else "(这是第1章,无前章)"

        prompt = PROMPTS["canon_audit"].format(
            canon_locked=locked, canon_evolving=evolving,
            prev_events=prev_events_text, content=content[:6000])
        # 暂存 callback,_on_response_received 里特殊处理
        self._canon_audit_callback = (on_done, ch_num)
        self._send_to_ai(prompt, f"Canon稽核-第{ch_num}章", target="canon_audit")

    def _on_canon_audit_response(self, content):
        """处理 Canon 稽核 AI 回复"""
        cb_tuple = getattr(self, "_canon_audit_callback", None)
        if not cb_tuple:
            return
        on_done, ch_num = cb_tuple
        self._canon_audit_callback = None

        violations = []
        try:
            text = self._extract_json_blob(content)
            data = json.loads(text)
            if data.get("violated") and data.get("items"):
                violations = data["items"]
                for it in violations:
                    self.tab_canon.add_audit_log(
                        ch_num, it.get("severity", "mid"), it.get("desc", ""))
        except Exception as e:
            self.tab_generation.log(f"Canon 稽核解析失败:{e}(原文已忽略)", "warn")
        on_done(violations)

    def _run_canon_extract(self, content, ch_num):
        """从一章正文提取新 Canon,异步追加到设定档"""
        existing = self.tab_canon.canon_edit.toPlainText()[:2000]
        prompt = PROMPTS["canon_extract"].format(
            existing=existing or "(空)",
            ch_num=ch_num, content=content[:6000])
        # v1.75:发送诊断 — 让用户看到 prompt 真的发出去了
        print(f"[canon-extract v1.75] ch={ch_num} 发送 prompt({len(prompt)} 字)",
              flush=True)
        self.tab_generation.log(
            f"🛡️ Canon 抽取-第{ch_num}章 → AI({len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"Canon抽取-第{ch_num}章",
                         target="canon_extract", ch_num=ch_num)

    def _on_canon_extract_response(self, content, meta):
        """处理 Canon 抽取 AI 回复
        既写 Canon Tab(单值条目),也按前缀分发到 🎭 角色与世界 6 库"""
        from datetime import datetime as _dt
        ch_num = meta.get("ch_num", 0)
        # v1.75:全链路诊断 — 打印 AI 原始回复前 200 字,方便排障
        print(f"[canon-extract v1.75] ch={ch_num} AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            # v1.75:防 list-vs-dict — prompt 要求是数组,但 AI 可能输出对象
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ Canon 抽取:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略。原始前 200 字:{(content or '')[:200]}",
                    "warn")
                # 更新 label 让用户看见
                try:
                    self.tab_canon.lbl_last_extract.setText(
                        f"⚠ 最近抽取:第{ch_num}章 AI 输出格式错误(非数组) "
                        f"@ {_dt.now().strftime('%H:%M:%S')}")
                    self.tab_canon.lbl_last_extract.setStyleSheet(
                        "color: #c00; font-size: 11px; padding: 4px 6px; "
                        "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
                except Exception:
                    pass
                return
            count = 0
            # 用于按前缀分发到 charlib 的结构化 dict
            charlib_data = {
                "characters": [],
                "relations": [],
                "items": [],
                "events": [],   # 时间线
                "foreshadows": [],
            }
            # 角色聚合:同一角色多字段合并到一行
            chars_acc = {}      # name -> {role, appearance, personality, ability, state, first_ch}
            items_acc = {}      # name -> {owner, source, status, ability}

            for it in arr:
                # v1.75:防 list-of-string — AI 可能塞字符串而不是 dict 到数组里
                if not isinstance(it, dict):
                    continue
                key = it.get("key", "").strip()
                value = it.get("value", "").strip()
                mode = it.get("mode", "evolving")
                ch = it.get("ch", ch_num)
                if not key or not value:
                    continue

                # 1) 写 Canon Tab (保留全字段路径,任意 key 都能录)
                self.tab_canon.add_item(
                    key, value, mode=mode,
                    severity="high" if mode == "locked" else "mid",
                    ch=ch)
                count += 1

                # 2) 按前缀分发到 charlib 的结构化 dict
                #    格式: <类别>.<主键>.<字段>  (例如 角色.林远.身份)
                parts = key.split(".", 2)  # 最多分 3 段
                if len(parts) < 2:
                    continue
                category = parts[0]
                main_key = parts[1] if len(parts) >= 2 else ""
                field = parts[2] if len(parts) >= 3 else "info"

                if category == "角色":
                    if main_key not in chars_acc:
                        chars_acc[main_key] = {"name": main_key, "first_ch": ch}
                    # 字段映射到 charlib 8 列
                    fmap = {
                        "身份": "role", "角色": "role",
                        "外貌": "appearance", "样貌": "appearance",
                        "性格": "personality", "人设": "personality",
                        "标志": "mark", "标记": "mark", "独有称号": "mark",
                        "能力": "ability", "技能": "ability", "战力": "ability",
                        "状态": "state", "当前状态": "state",
                    }
                    col_key = fmap.get(field, "personality")  # 未知字段塞 personality
                    # 合并 value(同字段多次提取 → 用 / 拼接)
                    cur = chars_acc[main_key].get(col_key, "")
                    chars_acc[main_key][col_key] = (cur + " / " + value) if cur else value
                elif category == "关系":
                    # main_key = "X-Y" 或 "X与Y"
                    m = re.match(r'^(.+?)\s*[-与]\s*(.+)$', main_key)
                    if m:
                        a, b = m.group(1).strip(), m.group(2).strip()
                        charlib_data["relations"].append({
                            "a": a, "type": field, "b": b, "note": value,
                        })
                elif category == "时间线":
                    # main_key = 第N章 (或 三年前 / 十八岁 等),作为时间锚
                    charlib_data["events"].append({
                        "time": main_key, "event": value, "ch": ch,
                    })
                elif category == "物品":
                    if main_key not in items_acc:
                        items_acc[main_key] = {"name": main_key}
                    fmap_it = {
                        "持有人": "owner", "拥有者": "owner",
                        "来源": "source",
                        "状态": "status", "当前状态": "status",
                        "能力": "ability", "效果": "ability", "功效": "ability",
                    }
                    col_key = fmap_it.get(field, "source")
                    cur = items_acc[main_key].get(col_key, "")
                    items_acc[main_key][col_key] = (cur + " / " + value) if cur else value
                elif category == "战力":
                    # 战力体系归到角色 ability 或单独物品行(看用户偏好)
                    # 这里塞到 items_acc 以"<体系名>"作 name,字段 ability 存所有细节
                    if main_key not in items_acc:
                        items_acc[main_key] = {"name": main_key, "source": "(战力体系)"}
                    cur = items_acc[main_key].get("ability", "")
                    items_acc[main_key]["ability"] = \
                        (cur + " / " + f"{field}:{value}") if cur else f"{field}:{value}"
                elif category == "伏笔":
                    charlib_data["foreshadows"].append({
                        "content": main_key + ("|" + value if main_key != value else ""),
                        "ch": ch,
                        "plan_pay_at": 0,
                    })

            # 合并累积的 chars / items
            charlib_data["characters"] = list(chars_acc.values())
            charlib_data["items"] = list(items_acc.values())

            # 同步到 🎭 角色与世界
            added = {}
            try:
                added = self._merge_into_charlib(charlib_data)
            except Exception as _me:
                self.tab_generation.log(f"同步库失败:{_me}", "warn")

            self.tab_generation.log(
                f"✓ Canon 抽取完成:Canon Tab +{count} 条 / "
                f"🎭 角色与世界 角色+{added.get('ch',0)} 关系+{added.get('rel',0)} "
                f"物品+{added.get('it',0)} 时间线+{added.get('ev',0)} 伏笔+{added.get('fo',0)}",
                "success")
            
            # v1.75:永远更新 Canon Tab 顶部 label,无论 count 是否为 0
            try:
                ts = _dt.now().strftime('%H:%M:%S')
                if count > 0:
                    self.tab_canon.lbl_last_extract.setText(
                        f"✅ 最近抽取:第{ch_num}章 +{count} 条新设定 @ {ts}")
                    self.tab_canon.lbl_last_extract.setStyleSheet(
                        "color: #2a6dcd; font-size: 11px; padding: 4px 6px; "
                        "background: #e8f0fe; border: 1px solid #88aaff; "
                        "border-radius: 3px; font-weight:bold;")
                else:
                    # AI 跑了但没抽到东西 — 不是错误,但要让用户看见
                    self.tab_canon.lbl_last_extract.setText(
                        f"📭 最近抽取:第{ch_num}章 AI 返回空数组(本章无新设定) @ {ts}")
                    self.tab_canon.lbl_last_extract.setStyleSheet(
                        "color: #7a7a7a; font-size: 11px; padding: 4px 6px; "
                        "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
            except Exception:
                pass
        except Exception as e:
            self.tab_generation.log(f"⚠️ Canon 抽取解析失败:{e}", "warn")
            # v1.75:解析失败也要让用户看见,不能静默
            try:
                ts = _dt.now().strftime('%H:%M:%S')
                self.tab_canon.lbl_last_extract.setText(
                    f"⚠ 最近抽取:第{ch_num}章 JSON 解析失败({e}) @ {ts}")
                self.tab_canon.lbl_last_extract.setStyleSheet(
                    "color: #c00; font-size: 11px; padding: 4px 6px; "
                    "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
            except Exception:
                pass
            # 诊断打印 AI 原始回复前 500 字
            print(f"[canon-extract v1.75] ch={ch_num} 解析失败,原始 500 字: "
                  f"{(content or '')[:500]!r}", flush=True)

    @staticmethod
    def _extract_json_blob(text):
        """从 AI 回复里提取 JSON 字符串(去掉 ```json 包裹、前后说明文字)"""
        if not text:
            return "{}"
        # 去 markdown 代码块
        m = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', text, re.DOTALL)
        if m:
            return m.group(1)
        # 找首个 { 或 [,谁先出现就用谁(避免数组里的内层 {} 被先匹配)
        i_obj = text.find('{')
        i_arr = text.find('[')
        candidates = [(i, o, c) for i, o, c in
                      [(i_obj, '{', '}'), (i_arr, '[', ']')] if i >= 0]
        if not candidates:
            return "{}"
        candidates.sort()  # 按位置升序,先出现的优先
        i, ch_open, ch_close = candidates[0]
        depth = 0
        for j in range(i, len(text)):
            if text[j] == ch_open:
                depth += 1
            elif text[j] == ch_close:
                depth -= 1
                if depth == 0:
                    return text[i:j+1]
        return "{}"

    # ===================================================================
    # 多维自鞭策(C 模块)
    # ===================================================================
    def _extract_hook_intensity_from_text(self, content):
        """
        v2.23.0 BUG-086 helper:从章节正文末尾的【断章钩子】元信息块解析强度

        AI 输出的元信息块格式示例:
            【断章钩子】
            类型:倒计时
            强度:★★★★★
            内容:还有 7 天系统就要重启

        返回 0-5(★ 数量),解析失败或没声明就返回 0。

        实现要点:
        - 只看末尾 ~2000 字(章节末尾才有元信息块),避免误抓正文里的"★"
        - 用 re 匹配"强度"行,统计连续 ★ 字符
        """
        if not content:
            return 0
        import re as _re
        tail = content[-2000:] if len(content) > 2000 else content
        # 找 "【断章钩子】" 块
        m_block = _re.search(r'【断章钩子】(.*?)(?:【|$)', tail, _re.DOTALL)
        if not m_block:
            return 0
        block = m_block.group(1)
        # 找"强度"行的 ★ 数量(支持中英文冒号 + 容错空格)
        m_int = _re.search(r'强度[\s::]+([★☆⭐\s]+)', block)
        if not m_int:
            return 0
        star_seq = m_int.group(1).strip()
        # 数有几个 ★ / ⭐(☆ 视为半颗,不计)
        count = star_seq.count('★') + star_seq.count('⭐')
        return min(count, 5)

    def _check_chapter_quality(self, content, target_words, min_words):
        """对章节做即时校验(无 AI 调用部分)。
        返回 (issues:list[str], need_ai_audit:bool)"""
        issues = []
        cfg = self.tab_generation.critique_config()

        # 显眼日志:让用户看见检查在跑(用户多次问"质量到底有没有检查")
        self.tab_generation.log(
            f"🔍 章节质量校验启动 (字数{len(content)} 目标{target_words} 阈值{self.tab_generation.quality_threshold.value()}分)...",
            "info")
        ran_checks = []

        # 1. 字数
        actual = len(re.sub(r'\s', '', content))
        if cfg.get("word_count"):
            ran_checks.append("字数")
            if actual < min_words:
                issues.append(
                    f"字数不达标:目标 {target_words} 字,实际 {actual} 字"
                    f"(差 {min_words - actual} 字)")

        # 2. 章末钩子(v1.73:扩 80+ 关键词 + 看末段,源头在 pangu_system.HOOK_MARKERS)
        if cfg.get("hook"):
            ran_checks.append("钩子")
            try:
                from pangu_system import PanguEngine as _PE
                has_hook = _PE.check_chapter_has_hook(content)
            except Exception:
                has_hook = True  # 兜底:pangu 不可用就放行,不要硬崩
            # v2.23.0 BUG-086 钩子检测松绑:
            # 实战(第 1 章死磕 10 次全失败):AI 元信息块里声明了"钩子类型=倒计时
            # / 强度★★★★★ / 内容=...",但正文末段没有 HOOK_MARKERS 任一关键词
            # (倒计时类钩子 "还有 7 天" 不在 80+ 关键词列表里)。导致钩子入库成功
            # 但写后校验失败,死磕 10 次浪费 ~7 分钟 + 大量 token。
            #
            # 修法:HOOK_MARKERS 检测失败时,解析 【断章钩子】 元信息块,如果 AI
            # 声明了 intensity ≥ ★★★★(4 星以上),视为"AI 自己说写了强钩子"
            # → 放行,不再要求关键词必须命中。代价:AI 可能虚标强度,但实战
            # 4 星以上虚标的概率远低于关键词列表不全的概率。日志说明放行原因
            # 让用户能审。
            if not has_hook:
                hook_meta_intensity = self._extract_hook_intensity_from_text(content)
                if hook_meta_intensity >= 4:
                    self.tab_generation.log(
                        f"  · [BUG-086] 关键词未命中但元信息声明强度 ★{'★'*hook_meta_intensity} "
                        f"→ 放行(信任 AI 元信息;关键词列表跟不上创意)", "info")
                    has_hook = True
            if not has_hook:
                issues.append(
                    "章末缺少钩子:末段无悬念/转折/留白/反差元素,"
                    "读者追更欲不足。请在结尾留一个新悬念、决断、神秘人或场景切换")

        # 3. 禁用词扫描(高严重度 → 直接触发死磕重写)
        # 阈值:总命中次数 >5 或 单词命中 >2 都算违反
        ran_checks.append("禁用词")
        try:
            from pangu_system import PanguEngine as _PE
            hits = _PE.detect_forbidden_words(content)
            total_count = sum(c for _, c in hits)
            heavy_words = [(w, c) for w, c in hits if c >= 2]
            if total_count > 5 or heavy_words:
                top_str = ", ".join(f"{w}×{c}" for w, c in hits[:8])
                issues.append(
                    f"禁用词违规(累计 {total_count} 次,触发铁律):{top_str}。"
                    f"必须全部删除或换说法,这是盘古铁律第 15 条"
                )
            else:
                self.tab_generation.log(
                    f"  · 禁用词扫描通过(累计 {total_count} 次,未超阈值)", "info")
        except Exception:
            pass

        # 4. 盘古综合评分门(分数低于阈值 → 死磕)
        # v1.81 BUG-061:改用 lint_with_locations,记录精确定位给死磕用
        ran_checks.append("盘古综合评分")
        score_locations_summary = ""  # 存定位给死磕注入
        try:
            threshold = self.tab_generation.quality_threshold.value()
            if threshold > 0:
                from pangu_system import get_default_engine
                eng = get_default_engine()
                # v1.81:用 lint_with_locations 拿精确定位
                lint = eng.lint_with_locations(content)
                score = lint.get("score", 0)
                if score < threshold:
                    score_locations_summary = lint.get("summary", "")
                    issues.append(
                        f"评分不达标:盘古综合评分 {score}/100 < 阈值 {threshold}。"
                        f"差 {threshold - score} 分。"
                        f"具体违规已记录(下次重写时会附带定位)"
                    )
                else:
                    self.tab_generation.log(
                        f"  · 盘古综合评分 {score}/100 ≥ 阈值 {threshold} ✓", "info")
            else:
                self.tab_generation.log(
                    f"  · 评分门已关闭(阈值=0,跳过)", "info")
        except Exception as _se:
            self.tab_generation.log(f"评分门跑失败(忽略):{_se}", "warn")

        # 把定位信息暂存到 self(下面会被 retry 函数读)
        self._last_lint_locations = score_locations_summary

        # 汇总
        if issues:
            self.tab_generation.log(
                f"🔍 即时校验完成:跑了 [{', '.join(ran_checks)}] {len(ran_checks)} 项 → "
                f"发现 {len(issues)} 个问题 → 触发死磕", "warn")
        else:
            self.tab_generation.log(
                f"🔍 即时校验完成:跑了 [{', '.join(ran_checks)}] {len(ran_checks)} 项 → "
                f"全部通过 ✓", "success")

        return issues, (cfg.get("canon") or cfg.get("rhythm") or cfg.get("character"))

    def _retry_chapter_with_reasons(self, meta, reasons):
        """字数 / 钩子 / Canon / 节奏 / 人设 任一不达标 → 拼强化 prompt 重发"""
        retry = meta.get("retry_left", 0)
        if retry <= 0:
            self.tab_generation.log(
                "✗ 死磕次数用尽,接受这章(质量不达标)", "warn")
            self._accept_chapter_and_continue(
                meta.get("_held_content", ""), meta)
            return

        # ★ RL 反馈:死磕一次 = 扣分
        try:
            if self.flow_rl:
                retry_used = meta.get("retry_used", 0)
                state = ("chapter", "deepseek", retry_used)
                action = meta.get("_rl_action", {"send_wait": 3.0,
                                                 "stable_threshold": 1.5,
                                                 "post_emit_wait": 3,
                                                 "use_strategy_b": False})
                reward_val = RL_REWARDS["retry_needed"]
                # 章节字数严重不足 → 额外扣分
                content = meta.get("_held_content", "")
                if content and len(content) < 500:
                    reward_val += RL_REWARDS["chapter_word_count_short"]
                self.flow_rl.reward(
                    state, action, reward_val,
                    f"死磕重写({len(reasons)} 个问题)")
        except Exception:
            pass

        new_meta = dict(meta)
        new_meta["retry_left"] = retry - 1
        new_meta["retry_used"] = meta.get("retry_used", 0) + 1  # 记录用了几次
        new_meta.pop("_held_content", None)
        reason_block = "\n".join(f"  · {r}" for r in reasons)
        # 如果违规里有禁用词,加超强力指令
        has_forbidden = any("禁用词违规" in r for r in reasons)
        forbidden_extra = ""
        if has_forbidden:
            forbidden_extra = (
                "\n\n🚨【最高优先级:禁用词清零】🚨\n"
                "上次本章用了禁用词,这是盘古铁律不可违反的死规。\n"
                "重写本章时,每写一句都问自己:这句有禁用词吗?\n"
                "替换策略:\n"
                "- 副词类(顿时/连忙/显然/似乎/可能/几乎...)→ 直接删除,不加任何替代\n"
                "- 心理动词(知道/觉得/想/认为)→ 换成具体动作或对话\n"
                "  错例:他知道这不对   正例:他咬了咬牙\n"
                "  错例:她觉得很冷    正例:她搓了搓手臂,起了一层鸡皮疙瘩\n"
                "- 套话(嘴角勾起/眼中闪过/心下了然)→ 整句重写\n"
                "- 比喻词(仿佛/如同/像)→ 改成直接断言\n"
                "  错例:他仿佛被雷劈了    正例:他僵在原地\n"
                "重写完后自查一遍,如果还有任何禁用词,继续删继续换,直到清零。\n"
            )

        # v1.81 BUG-061:把上次校验的精确定位 summary 注入 retry prompt
        # 这是关键修复 — 旧版只告诉 AI"用了 3 次想",新版告诉 AI"第 11 段『林远想站直』
        # 这里要改",让 AI 能精准修而不是再瞎写一次
        locations_block = ""
        loc_summary = getattr(self, "_last_lint_locations", "")
        if loc_summary and loc_summary != "无具体违规":
            locations_block = (
                "\n\n🎯【上次违规的精确定位(必须逐条修复)】\n"
                + loc_summary
                + "\n\n重写时,请逐条对照上面的【段号 / 原文片段 / 修复建议】,"
                "把对应位置改掉。不要换一批别的禁用词,要让分数真正上升。\n"
            )

        # v1.81:分数进度提示(让 AI 知道目标 vs 现状的 gap)
        score_progress_block = ""
        try:
            threshold = self.tab_generation.quality_threshold.value()
            # 从 reasons 里抽取上次分数
            for r in reasons:
                m_score = re.search(r"评分不达标[::]\s*盘古综合评分\s*(\d+)/100", r)
                if m_score:
                    last_score = int(m_score.group(1))
                    gap = threshold - last_score
                    score_progress_block = (
                        f"\n\n📊【分数进度】上次 {last_score}/100,"
                        f"目标 ≥ {threshold},缺 {gap} 分。\n"
                        f"重写时优先修扣分最重的项(通常是禁用词数量)。\n"
                    )
                    break
        except Exception:
            pass

        stronger = (meta.get("original_prompt", "")
                    + "\n\n【上次问题清单(必须修正)】\n" + reason_block
                    + forbidden_extra
                    + locations_block          # v1.81 新增
                    + score_progress_block     # v1.81 新增
                    + "\n\n请重写本章,严格规避以上所有问题。")
        # v1.97 BUG-071:字典写入 key=label,死磕重写跟其他任务并发不串台
        self._pending_task_targets[new_meta.get("label", "章节")] = new_meta
        self.tab_generation.log(
            f"⚠ 章节质量未达标 ({len(reasons)} 个问题),死磕重写中... "
            f"(本次第 {meta.get('retry_count_used', 0) + 1} 轮,上限 {meta.get('retry_left', retry)} 次)",
            "warn")
        for r in reasons:
            self.tab_generation.log(f"  · {r}", "warn")
        # 重试时也走附件模式(镜像站审核严,文本会被拒绝)
        # _clear_existing_attachments 会自动清掉旧附件,不会堆积
        self.worker.submit({
            "action": "send_prompt",
            "prompt": stronger,
            "task_id": meta.get("label", "章节"),
            "url": self.tab_generation.url_input.text().strip(),
            "type_delay_ms": 5,
            "allow_attachment": True,  # 镜像站需要附件绕审核
        })

    def _accept_chapter_and_continue(self, content, meta):
        """章节通过校验或死磕用尽 → 入库并触发后续链"""
        # 📋 管家:章节流程开始(P1 — 章末日报)
        try:
            if HOUSEKEEPER_AVAILABLE:
                _hk = _housekeeper_mod.get_housekeeper()
                _hk_ch = meta.get("ch_num", len(self.chapters) + 1)
                _hk.start_chapter(_hk_ch, path_tag="main")
        except Exception:
            pass

        # ★ RL 反馈:章节成功 → 加分(根据死磕次数决定加多少)
        try:
            if self.flow_rl and meta.get("target") not in ("golden_three",):
                retry_used = meta.get("retry_used", 0)
                reward_val = (
                    RL_REWARDS["chapter_success_first_try"]
                    if retry_used == 0
                    else RL_REWARDS["chapter_success_after_retry"]
                )
                content_len = len(content or "")
                if content_len >= 2000:
                    reward_val += RL_REWARDS["chapter_word_count_ok"]
                state = ("chapter", "deepseek", retry_used)
                action = meta.get("_rl_action", {"send_wait": 3.0,
                                                 "stable_threshold": 1.5,
                                                 "post_emit_wait": 3,
                                                 "use_strategy_b": False})
                self.flow_rl.reward(
                    state, action, reward_val,
                    f"章节成功(retry={retry_used}, 长度={content_len})")
                self.tab_generation.log(
                    f"🎯 RL 奖励: {reward_val:+d} ({state[0]}, 死磕{retry_used} 次)",
                    "info")
        except Exception as _e_rl:
            pass

        if meta.get("target") == "golden_three":
            self._split_and_save_golden_three(content)
            last_ch_num = len(self.chapters)
        else:
            ch_num = meta.get("ch_num", len(self.chapters) + 1)
            # ── 解析并剥离盘古章节尾部元信息(【断章钩子】【本章爽点】
            #     【伏笔状态】【下一章选项】),只把正文写入 chapter['content']
            pangu_meta = None
            body_clean = content
            try:
                from pangu_system import parse_chapter_meta as _pangu_parse
                pangu_meta = _pangu_parse(content)
                body_clean = pangu_meta.get("body") or content
                # 📋 管家:记录内容长度 + 元信息
                try:
                    if HOUSEKEEPER_AVAILABLE:
                        _hk = _housekeeper_mod.get_housekeeper()
                        _hk.record_content(content, body_clean)
                        _hk.record_pangu_meta(pangu_meta)
                except Exception:
                    pass
                # 诊断日志:让用户能看到是否真的剥离了元信息
                _stripped = len(content) - len(body_clean)
                if _stripped > 0:
                    self.tab_generation.log(
                        f"✓ 已剥离章节尾部元信息 {_stripped} 字 → 切到【章节编辑器】Tab,"
                        f"字数下方📌米色面板可看钩子/爽点/伏笔/下一章选项",
                        "info")
                elif "本章完" in content or "【断章钩子】" in content \
                        or "断章钩子" in content or "下一章选项" in content:
                    # 元信息标记还在正文里 → 剥离失败,打 warn
                    self.tab_generation.log(
                        "⚠️ 检测到元信息标记但剥离失败(parse_chapter_meta 没匹配)。"
                        "请把这段章节末尾 30 行复制发给开发者,以便加新匹配规则",
                        "warn")
                    # 📋 管家:剥离失败告警
                    try:
                        if HOUSEKEEPER_AVAILABLE:
                            _housekeeper_mod.get_housekeeper().warn("元信息剥离失败")
                    except Exception:
                        pass
            except ImportError:
                pass
            except Exception as _pm_e:
                self.tab_generation.log(f"盘古元信息解析失败(降级保留原文):{_pm_e}", "warn")
                # 📋 管家:记录解析失败
                try:
                    if HOUSEKEEPER_AVAILABLE:
                        _housekeeper_mod.get_housekeeper().record_pangu_meta_failed(str(_pm_e))
                except Exception:
                    pass

            ch_title = self._extract_chapter_title(body_clean) or f"第{ch_num}章"
            ch_body = self._strip_chapter_title(body_clean)
            # v1.92 BUG-066:章节默认 locked=False(章节级中稿/终稿锁定字段)
            chapter = {"title": ch_title, "content": ch_body, "summary": "", "locked": False}

            # ── 元信息存进 chapter dict,供 UI/工作流后续用
            if pangu_meta:
                if pangu_meta.get("hook"):
                    chapter["hook"] = pangu_meta["hook"]
                if pangu_meta.get("cool_points"):
                    chapter["cool_points"] = pangu_meta["cool_points"]
                if pangu_meta.get("next_options"):
                    chapter["next_options"] = pangu_meta["next_options"]
                # 伏笔摘要(给 GUI 用,方便看"埋 X 收 Y";真正入库走 _sync 函数)
                _sp = len(pangu_meta.get("seeds_planted", []))
                _pd = len(pangu_meta.get("seeds_paid", []))
                if _sp or _pd:
                    parts = []
                    if _sp: parts.append(f"埋雷 {_sp} 条")
                    if _pd: parts.append(f"收雷 {_pd} 条")
                    chapter["_pangu_seeds_summary"] = " / ".join(parts)

            self.chapters.append(chapter)

            # 自动朗读(如果开启)
            if self.tab_generation.chk_auto_tts.isChecked():
                self._tts_auto_enqueue(ch_num, content)

            # ── 把【伏笔状态】同步到 lifespan_loops 伏笔库
            if pangu_meta:
                self._sync_pangu_seeds_to_lifespan(pangu_meta, ch_num)
                # ── 钩子 + 爽点 自动写入 🎭 角色与世界 → 🎣 钩子编年 / 🎯 爽点编年
                self._sync_hook_and_cool_to_charlib(pangu_meta, ch_num)
                # 📋 管家:两个 sync 跑完
                try:
                    if HOUSEKEEPER_AVAILABLE:
                        _hk = _housekeeper_mod.get_housekeeper()
                        _hk.record_step("seeds_sync_lifespan", True)
                        _hk.record_step("hook_cool_sync", True)
                except Exception:
                    pass

            self._refresh_chapter_list()
            if self.tab_generation.auto_save.isChecked():
                self._save_chapter_to_disk(self.chapters[-1])
                # 📋 管家:auto_save 跑了
                try:
                    if HOUSEKEEPER_AVAILABLE:
                        _housekeeper_mod.get_housekeeper().record_step("auto_save", True)
                except Exception:
                    pass
            actual = len(re.sub(r'\s', '', ch_body))
            # 📋 管家:字数门记录
            try:
                if HOUSEKEEPER_AVAILABLE:
                    _hk = _housekeeper_mod.get_housekeeper()
                    _target = meta.get("target_words") or \
                        getattr(self, "_batch_target_words", 0) or 0
                    _hk.record_word_count(int(_target or 0), actual)
            except Exception:
                pass
            self.tab_generation.log(
                f"✓ 第 {ch_num} 章生成成功!字数:{actual} 字", "success")
            if pangu_meta and (pangu_meta.get("hook") or pangu_meta.get("cool_points")
                               or pangu_meta.get("seeds_planted") or pangu_meta.get("next_options")):
                bits = []
                if pangu_meta.get("hook"):          bits.append("钩子")
                if pangu_meta.get("cool_points"):   bits.append(f"爽点×{len(pangu_meta['cool_points'])}")
                if pangu_meta.get("seeds_planted"): bits.append(f"埋雷×{len(pangu_meta['seeds_planted'])}")
                if pangu_meta.get("seeds_paid"):    bits.append(f"收雷×{len(pangu_meta['seeds_paid'])}")
                if pangu_meta.get("next_options"):  bits.append(f"下章选项×{len(pangu_meta['next_options'])}")
                self.tab_generation.log("  · 盘古元信息已剥离并归档:" + " / ".join(bits), "info")
            last_ch_num = ch_num

        self._batch_remaining -= 1
        print(f"[batch] 章节入库完成 batch_remaining={self._batch_remaining} "
              f"paused={self._batch_paused}", flush=True)
        if self._batch_remaining > 0:
            self._update_window_title(f"⏳ 剩余{self._batch_remaining}章")
        else:
            self._update_window_title("✅ 生成完成")

        # v1.32:✨ 自动 13 法静态扫描(如果开了开关)
        try:
            if DIALOGUE_CRITIC_AVAILABLE:
                from PyQt5.QtCore import QSettings
                auto_dc = QSettings("NovelAI", "DialogueCritic").value(
                    "auto_static", False, type=bool)
                if auto_dc and content:
                    critic = dialogue_critic.DialogueCritic(content)
                    static = critic.static_scan()
                    reds = [i for i in static.issues if i.severity == "red"]
                    if reds:
                        self.tab_generation.log(
                            f"🔬 13法静态扫描: 发现 {len(reds)} 处红线违反(说/道 "
                            f"{static.say_count}/{static.say_allowed})— "
                            f"点 🔬 13法诊断 看详情",
                            "warn")
                    else:
                        self.tab_generation.log(
                            f"🔬 13法静态扫描: ✓ 通过(说/道 {static.say_count}/"
                            f"{static.say_allowed})",
                            "success")
                    # 📋 管家:记录 13 法扫描结果
                    try:
                        if HOUSEKEEPER_AVAILABLE:
                            _housekeeper_mod.get_housekeeper().record_dialogue_critic(
                                reds=len(reds),
                                say_count=static.say_count,
                                say_allowed=static.say_allowed)
                    except Exception:
                        pass
        except Exception as _e:
            print(f"[auto dc] 失败: {_e}", flush=True)

        # 后置链:Canon 抽取 → 摘要 → after_chapter 技能 → 下一章
        # (用 QTimer 错开,避免一窝蜂砸到 worker)
        self._post_chapter_chain(last_ch_num)

        # 📋 管家:章节流程结束,生成日报
        try:
            if HOUSEKEEPER_AVAILABLE:
                _hk = _housekeeper_mod.get_housekeeper()
                _hk.record_step("post_chapter_chain", True)

                # ── v2.10:P2-#6 Canon locked 字段一致性巡检(finalize 前) ──
                # 高严重度 locked 项的 value 必须在章节正文里出现,
                # 否则提醒"AI 可能改/删了这个锁定字段"。MVP 仅检测 high。
                try:
                    if hasattr(self, "tab_canon") and hasattr(self.tab_canon, "parse"):
                        _content_str = str(content or "")
                        for _it in self.tab_canon.parse():
                            if (_it.get("mode") == "locked"
                                    and _it.get("severity") == "high"):
                                _val = str(_it.get("value", "")).strip()
                                _key = _it.get("key", "?")
                                if _val and (_val not in _content_str):
                                    _hk.record_canon_locked_mismatch(
                                        _key, _val, "(本章正文未提及)")
                except Exception:
                    pass

                # ── v2.10:P3-#12 二道闸巡查(每 10 章触发,跨多文件扫描) ──
                # 检查关键历史 BUG 修复点是否被新代码意外回退。
                try:
                    _ch_now = meta.get("ch_num", len(self.chapters))
                    if _ch_now > 0 and _ch_now % 10 == 0:
                        # 扫主程序 + ui 子包(P3~P6 模块化拆分后,代码散在多处)
                        import glob as _glob
                        _scan_paths = (
                            ["novel_ai.py"]
                            + _glob.glob("ui/*.py")
                            + _glob.glob("ui/tabs/*.py")
                            + _glob.glob("core/*.py")
                        )
                        _hk.verify_defenses(DEFENSE_FINGERPRINTS, _scan_paths)
                except Exception:
                    pass

                # ── finalize:生成日报 ──
                _final = _hk.finalize_chapter()
                if _final:
                    _score = _final.health_score
                    _oneliner = _final.render_oneliner()
                    # 醒目分级输出
                    if _score >= 0.8:
                        _emoji, _level = "🟢", "success"
                    elif _score >= 0.5:
                        _emoji, _level = "🟡", "warn"
                    else:
                        _emoji, _level = "🔴", "error"
                    _pct = int(_score * 100)
                    self.tab_generation.log(
                        f"{'─' * 50}", "info")
                    self.tab_generation.log(
                        f"📋 管家日报 {_emoji} 健康度 {_pct}% │ {_oneliner}",
                        _level)
                    # 如果有告警,逐条显示
                    if _final.warnings:
                        for _w in _final.warnings[:3]:
                            self.tab_generation.log(f"  ⚠ {_w}", "warn")
                    # 如果有防御消失,醒目警告
                    if _final.missing_defenses:
                        self.tab_generation.log(
                            f"  🛡️ 防御消失:{', '.join(_final.missing_defenses)}",
                            "error")
                    self.tab_generation.log(
                        f"{'─' * 50}", "info")

                # ── v2.10:P2-#7 跨章节奏雷达(每 5 章触发,看历史 5 章) ──
                # 必须 finalize 之后调,因为 check_pacing_window 用 self.history
                # (finalize 把 current_report 归档到 history)
                try:
                    _ch_now = meta.get("ch_num", len(self.chapters))
                    if _ch_now >= 5 and _ch_now % 5 == 0:
                        _pacing = _hk.check_pacing_window(n=5)
                        if _pacing and _pacing.get("msg"):
                            # 雷达检测到疲软,把消息打到日志(housekeeper 已经 warn 到 history)
                            self.tab_generation.log(
                                f"📡 节奏雷达:{_pacing['msg']}",
                                "warn")
                except Exception:
                    pass
        except Exception:
            pass

    def _sync_hook_and_cool_to_charlib(self, pangu_meta: dict, ch_num: int):
        """把【断章钩子】+【本章爽点】写入 🎭 角色与世界 → 🎣 钩子编年 / 🎯 爽点编年
        每章一行。如同章重复触发(死磕重写),会按章号去重,只保留最新。"""
        if not hasattr(self, "tab_charlib"):
            return
        from PyQt5.QtWidgets import QTableWidgetItem
        cl = self.tab_charlib

        # 钩子
        hook = pangu_meta.get("hook") or {}
        if hook and hook.get("content"):
            # 先去掉同章号旧行(死磕重写时)
            for r in range(cl.tbl_hooks.rowCount() - 1, -1, -1):
                if cl.tbl_hooks.item(r, 0) and cl.tbl_hooks.item(r, 0).text() == str(ch_num):
                    cl.tbl_hooks.removeRow(r)
            r = cl.tbl_hooks.rowCount()
            cl.tbl_hooks.insertRow(r)
            vals = [
                str(ch_num),
                hook.get("type", ""),
                hook.get("intensity", ""),
                hook.get("content", ""),
            ]
            for c, v in enumerate(vals):
                cl.tbl_hooks.setItem(r, c, QTableWidgetItem(str(v)))
            try:
                self.tab_generation.log(
                    f"  · 钩子已入库:第{ch_num}章 / {hook.get('type','')} "
                    f"/ 强度{hook.get('intensity','')}", "info")
            except Exception:
                pass

        # 爽点(可能多条,每条一行;同样按章号去重)
        cool_list = pangu_meta.get("cool_points") or []
        if cool_list:
            # 先去掉同章号旧行
            for r in range(cl.tbl_cool.rowCount() - 1, -1, -1):
                if cl.tbl_cool.item(r, 0) and cl.tbl_cool.item(r, 0).text() == str(ch_num):
                    cl.tbl_cool.removeRow(r)
            for cool_str in cool_list:
                # 格式可能是 "类型:内容" 或纯内容
                cool_type = ""
                cool_content = cool_str
                if ":" in cool_str or ":" in cool_str:
                    parts = re.split(r'[::]', cool_str, 1)
                    if len(parts) == 2:
                        cool_type = parts[0].strip()
                        cool_content = parts[1].strip()
                r = cl.tbl_cool.rowCount()
                cl.tbl_cool.insertRow(r)
                vals = [str(ch_num), cool_type, cool_content]
                for c, v in enumerate(vals):
                    cl.tbl_cool.setItem(r, c, QTableWidgetItem(str(v)))
            try:
                self.tab_generation.log(
                    f"  · 爽点已入库:第{ch_num}章 / {len(cool_list)} 条", "info")
            except Exception:
                pass

    def _sync_pangu_seeds_to_lifespan(self, pangu_meta: dict, ch_num: int):
        """把盘古【伏笔状态】的埋雷/收雷自动写入 lifespan_loops 的伏笔库。
        如果 lifespan_loops 未加载或未初始化 open_loops,静默跳过。"""
        try:
            from lifespan_loops_steps import LifespanLoopsExtension
        except ImportError:
            return
        # 收雷:遍历现有 open_loops,desc 子串匹配则 close
        for paid in pangu_meta.get("seeds_paid", []):
            desc = paid.get("desc", "")
            if not desc:
                continue
            loops = (getattr(self, "open_loops", None) or {}).get("loops", []) if hasattr(self, "open_loops") else []
            matched = None
            for loop in loops:
                if loop.get("status") == "closed":
                    continue
                ld = loop.get("desc", "")
                # 双向子串匹配(短的在长的里 或 反过来),避免 AI 措辞微差就匹配不上
                if (ld and (ld in desc or desc in ld)):
                    matched = loop
                    break
            if matched:
                LifespanLoopsExtension.close_loop(self, matched["id"], ch_num)
                try:
                    self.tab_generation.log(
                        f"  · 伏笔自动闭环:「{matched.get('desc','')[:30]}」 @第{ch_num}章", "info")
                except Exception:
                    pass
        # 埋雷:每条新加一条伏笔
        existing_ids = set(
            l.get("id") for l in (getattr(self, "open_loops", None) or {}).get("loops", [])
            if hasattr(self, "open_loops")
        )
        for i, seed in enumerate(pangu_meta.get("seeds_planted", [])):
            desc = seed.get("desc", "")
            if not desc:
                continue
            # 生成 unique id
            loop_id = f"pangu_ch{ch_num}_seed{i+1}"
            while loop_id in existing_ids:
                i += 1
                loop_id = f"pangu_ch{ch_num}_seed{i+1}"
            existing_ids.add(loop_id)
            # 关键词:取 desc 前 6 个字作为粗略关键词(用于章节文本扫描自动刷新 last_seen_ch)
            keyword = desc[:6] if len(desc) >= 6 else desc
            LifespanLoopsExtension.add_loop(
                self,
                loop_id=loop_id,
                desc=desc,
                added_ch=ch_num,
                keyword=keyword,
            )
            try:
                self.tab_generation.log(
                    f"  · 伏笔自动入库:「{desc[:30]}」 @第{ch_num}章 "
                    + (f"(计划第{seed['plan_pay_at']}章收)" if seed.get("plan_pay_at") else ""),
                    "info")
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────
    # v1.76 BUG-056:全自动伏笔闭环
    # ──────────────────────────────────────────────────────────
    def _run_foreshadow_check(self, content, ch_num):
        """章节生成后,把未回收伏笔交给 AI 检查本章回收了哪些"""
        if not hasattr(self.tab_charlib, "tbl_fore"):
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        pending = []
        for r in range(self.tab_charlib.tbl_fore.rowCount()):
            ch_set = self.tab_charlib.tbl_fore.item(r, 0).text() if self.tab_charlib.tbl_fore.item(r, 0) else "0"
            ct = self.tab_charlib.tbl_fore.item(r, 1).text() if self.tab_charlib.tbl_fore.item(r, 1) else ""
            ch_pay = self.tab_charlib.tbl_fore.item(r, 2).text() if self.tab_charlib.tbl_fore.item(r, 2) else "0"
            paid = self.tab_charlib.tbl_fore.item(r, 3).text() if self.tab_charlib.tbl_fore.item(r, 3) else "否"
            if paid == "是" or not ct:
                continue
            pending.append({
                "id": r, "ch_set": ch_set, "content": ct[:120],
                "plan_pay_at": ch_pay,
            })
        if not pending:
            # 无可检查 — 跳过这一步,推进 pipeline
            print(f"[foreshadow-check v1.76] ch={ch_num} 无未回收伏笔,跳过", flush=True)
            self.tab_generation.log(
                f"🪤 第{ch_num}章伏笔回收检查:无未回收伏笔,跳过", "info")
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        fl = json.dumps(pending, ensure_ascii=False)
        prompt = PROMPTS["foreshadow_check"].format(
            foreshadow_list=fl, ch_num=ch_num, content=content[:6000])
        print(f"[foreshadow-check v1.76] ch={ch_num} 检查 {len(pending)} 条伏笔, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"🪤 伏笔回收检查-第{ch_num}章 → AI({len(pending)} 条未回收, {len(prompt)} 字 prompt)",
            "info")
        self._send_to_ai(prompt, f"伏笔回收检查-第{ch_num}章",
                         target="foreshadow_check", ch_num=ch_num)

    def _on_foreshadow_check_response(self, content, meta):
        """AI 检查回复 → 把命中的伏笔在 tbl_fore 里标记已回收"""
        from datetime import datetime as _dt
        ch_num = meta.get("ch_num", 0)
        print(f"[foreshadow-check v1.76] ch={ch_num} AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        from PyQt5.QtWidgets import QTableWidgetItem
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 伏笔回收检查:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略。原始前 200 字:{(content or '')[:200]}", "warn")
                try:
                    self.tab_charlib.lbl_last_check.setText(
                        f"⚠ 最近检查:第{ch_num}章 AI 输出格式错误(非数组) "
                        f"@ {_dt.now().strftime('%H:%M:%S')}")
                    self.tab_charlib.lbl_last_check.setStyleSheet(
                        "color: #c00; font-size: 11px; padding: 4px 6px; "
                        "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
                except Exception:
                    pass
                return
            count = 0
            for it in arr:
                if not isinstance(it, dict):
                    continue
                try:
                    rid = int(it.get("id", -1))
                except (TypeError, ValueError):
                    continue
                if not (0 <= rid < self.tab_charlib.tbl_fore.rowCount()):
                    continue
                # 已经标记过的不重复(防 AI 重复回收)
                paid_now = self.tab_charlib.tbl_fore.item(rid, 3)
                if paid_now and paid_now.text() == "是":
                    continue
                self.tab_charlib.tbl_fore.setItem(rid, 3, QTableWidgetItem("是"))
                self.tab_charlib.tbl_fore.setItem(rid, 4, QTableWidgetItem(str(ch_num)))
                how = str(it.get("how", ""))[:50]
                self.tab_generation.log(
                    f"  ✓ 伏笔回收:[{rid}] @第{ch_num}章 — {how}", "info")
                count += 1
            ts = _dt.now().strftime("%H:%M:%S")
            try:
                if count > 0:
                    self.tab_charlib.lbl_last_check.setText(
                        f"✅ 最近检查:第{ch_num}章 +{count} 条伏笔已回收 @ {ts}")
                    self.tab_charlib.lbl_last_check.setStyleSheet(
                        "color: #06f; font-weight: bold; font-size: 11px; "
                        "padding: 4px 6px; background: #eef6ff; "
                        "border: 1px solid #aac; border-radius: 3px;")
                else:
                    self.tab_charlib.lbl_last_check.setText(
                        f"📭 最近检查:第{ch_num}章 本章未回收任何伏笔 @ {ts}")
                    self.tab_charlib.lbl_last_check.setStyleSheet(
                        "color: #777; font-size: 11px; padding: 4px 6px; "
                        "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
            except Exception:
                pass
            self.tab_generation.log(
                f"✓ 伏笔回收检查完成:第{ch_num}章 共 {count} 条回收", "info")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 伏笔回收检查解析失败:{e}", "warn")
            try:
                self.tab_charlib.lbl_last_check.setText(
                    f"⚠ 最近检查:第{ch_num}章 JSON 解析失败({e}) "
                    f"@ {_dt.now().strftime('%H:%M:%S')}")
                self.tab_charlib.lbl_last_check.setStyleSheet(
                    "color: #c00; font-size: 11px; padding: 4px 6px; "
                    "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
            except Exception:
                pass

    def _reeval_zero_pay_at(self):
        """🤖 AI 重评估 plan_pay_at=0(或空)的伏笔 — 由按钮触发"""
        if not hasattr(self.tab_charlib, "tbl_fore"):
            return
        items = []
        for r in range(self.tab_charlib.tbl_fore.rowCount()):
            ch_set = self.tab_charlib.tbl_fore.item(r, 0).text() if self.tab_charlib.tbl_fore.item(r, 0) else "0"
            ct = self.tab_charlib.tbl_fore.item(r, 1).text() if self.tab_charlib.tbl_fore.item(r, 1) else ""
            ch_pay = self.tab_charlib.tbl_fore.item(r, 2).text() if self.tab_charlib.tbl_fore.item(r, 2) else "0"
            paid = self.tab_charlib.tbl_fore.item(r, 3).text() if self.tab_charlib.tbl_fore.item(r, 3) else "否"
            if paid == "是" or not ct:
                continue
            try:
                if int(ch_pay) != 0:
                    continue
            except ValueError:
                continue
            items.append({"id": r, "ch_set": ch_set, "content": ct[:120]})
        if not items:
            QMessageBox.information(
                self, "AI 重评估",
                "没有需要重评估的伏笔(所有未回收伏笔的 plan_pay_at 都非 0)")
            return
        current_ch = len(self.chapters) if hasattr(self, "chapters") else 1
        ret = QMessageBox.question(
            self, "AI 重评估确认",
            f"将把 {len(items)} 条 plan_pay_at=0 的伏笔交给 AI 评估合理回收章节(基于当前已写到第 {current_ch} 章)。\n\n"
            f"继续吗?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            return
        fl = json.dumps(items, ensure_ascii=False)
        prompt = PROMPTS["foreshadow_reeval"].format(
            current_ch=current_ch, foreshadow_list=fl)
        print(f"[foreshadow-reeval v1.76] 评估 {len(items)} 条, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"🤖 AI 重评估伏笔 → 发送 {len(items)} 条({len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"伏笔重评估-{len(items)}条",
                         target="foreshadow_reeval", count=len(items))

    def _on_foreshadow_reeval_response(self, content, meta):
        """AI 重评估回复 → 把 plan_pay_at 回填到 tbl_fore"""
        from datetime import datetime as _dt
        from PyQt5.QtWidgets import QTableWidgetItem
        count_req = meta.get("count", 0)
        print(f"[foreshadow-reeval v1.76] AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 伏笔重评估:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略", "warn")
                QMessageBox.warning(self, "AI 重评估失败",
                                    f"AI 输出不是 JSON 数组,本次未更新。\n原始前 200 字:\n{(content or '')[:200]}")
                return
            count = 0
            current_ch = len(self.chapters) if hasattr(self, "chapters") else 1
            for it in arr:
                if not isinstance(it, dict):
                    continue
                try:
                    rid = int(it.get("id", -1))
                    new_pay = int(it.get("plan_pay_at", 0))
                except (TypeError, ValueError):
                    continue
                if not (0 <= rid < self.tab_charlib.tbl_fore.rowCount()):
                    continue
                # v1.76:守 — 必须 > current_ch,绝不允许 0 或过去章节
                if new_pay <= current_ch:
                    new_pay = current_ch + 30  # 保守 fallback
                self.tab_charlib.tbl_fore.setItem(rid, 2, QTableWidgetItem(str(new_pay)))
                reason = str(it.get("reason", ""))[:30]
                self.tab_generation.log(
                    f"  ✓ 伏笔重评估:[{rid}] plan_pay_at → 第{new_pay}章 ({reason})", "info")
                count += 1
            ts = _dt.now().strftime("%H:%M:%S")
            self.tab_generation.log(
                f"✓ AI 重评估完成:更新 {count}/{count_req} 条伏笔", "info")
            QMessageBox.information(
                self, "AI 重评估完成",
                f"AI 评估完成,已自动回填 {count}/{count_req} 条伏笔的 plan_pay_at。\n\n"
                f"完成时间:{ts}")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 伏笔重评估解析失败:{e}", "warn")
            QMessageBox.warning(
                self, "AI 重评估失败",
                f"JSON 解析失败:{e}\n原始前 300 字:\n{(content or '')[:300]}")

    # ──────────────────────────────────────────────────────────
    # v1.77 BUG-057:威胁承诺自动闭环(与 v1.76 伏笔闭环同模式)
    # ──────────────────────────────────────────────────────────
    def _run_promise_check(self, content, ch_num):
        """章节生成后,把未兑现承诺/威胁/约定交给 AI 检查本章兑现了哪些"""
        if not hasattr(self.tab_charlib, "tbl_promises"):
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        pending = []
        tbl = self.tab_charlib.tbl_promises
        for r in range(tbl.rowCount()):
            ch_set = tbl.item(r, 0).text() if tbl.item(r, 0) else "0"
            kind = tbl.item(r, 1).text() if tbl.item(r, 1) else "承诺"
            fr = tbl.item(r, 2).text() if tbl.item(r, 2) else ""
            to = tbl.item(r, 3).text() if tbl.item(r, 3) else ""
            ct = tbl.item(r, 4).text() if tbl.item(r, 4) else ""
            dl = tbl.item(r, 5).text() if tbl.item(r, 5) else "0"
            fulfilled = tbl.item(r, 6).text() if tbl.item(r, 6) else "否"
            if fulfilled == "是" or not ct:
                continue
            pending.append({
                "id": r, "ch_set": ch_set, "kind": kind,
                "from": fr, "to": to,
                "content": ct[:120], "deadline": dl,
            })
        if not pending:
            print(f"[promise-check v1.77] ch={ch_num} 无未兑现承诺,跳过", flush=True)
            self.tab_generation.log(
                f"⚡ 第{ch_num}章承诺兑现检查:无未兑现承诺,跳过", "info")
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        pl = json.dumps(pending, ensure_ascii=False)
        prompt = PROMPTS["promise_check"].format(
            promise_list=pl, ch_num=ch_num, content=content[:6000])
        print(f"[promise-check v1.77] ch={ch_num} 检查 {len(pending)} 条承诺, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"⚡ 承诺兑现检查-第{ch_num}章 → AI({len(pending)} 条未兑现, "
            f"{len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"承诺兑现检查-第{ch_num}章",
                         target="promise_check", ch_num=ch_num)

    def _on_promise_check_response(self, content, meta):
        """AI 检查回复 → 把命中的承诺在 tbl_promises 标记已兑现"""
        from datetime import datetime as _dt
        from PyQt5.QtWidgets import QTableWidgetItem
        ch_num = meta.get("ch_num", 0)
        print(f"[promise-check v1.77] ch={ch_num} AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 承诺兑现检查:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略。原始前 200 字:{(content or '')[:200]}", "warn")
                try:
                    self.tab_charlib.lbl_last_promise_check.setText(
                        f"⚠ 最近检查:第{ch_num}章 AI 输出格式错误(非数组) "
                        f"@ {_dt.now().strftime('%H:%M:%S')}")
                    self.tab_charlib.lbl_last_promise_check.setStyleSheet(
                        "color: #c00; font-size: 11px; padding: 4px 6px; "
                        "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
                except Exception:
                    pass
                return
            count = 0
            tbl = self.tab_charlib.tbl_promises
            for it in arr:
                if not isinstance(it, dict):
                    continue
                try:
                    rid = int(it.get("id", -1))
                except (TypeError, ValueError):
                    continue
                if not (0 <= rid < tbl.rowCount()):
                    continue
                paid_now = tbl.item(rid, 6)
                if paid_now and paid_now.text() == "是":
                    continue
                tbl.setItem(rid, 6, QTableWidgetItem("是"))
                outcome = str(it.get("outcome", ""))[:20]
                how = str(it.get("how", ""))[:50]
                self.tab_generation.log(
                    f"  ✓ 承诺兑现:[{rid}] @第{ch_num}章 {outcome} — {how}", "info")
                count += 1
            ts = _dt.now().strftime("%H:%M:%S")
            try:
                if count > 0:
                    self.tab_charlib.lbl_last_promise_check.setText(
                        f"✅ 最近检查:第{ch_num}章 +{count} 条承诺已兑现 @ {ts}")
                    self.tab_charlib.lbl_last_promise_check.setStyleSheet(
                        "color: #06f; font-weight: bold; font-size: 11px; "
                        "padding: 4px 6px; background: #eef6ff; "
                        "border: 1px solid #aac; border-radius: 3px;")
                else:
                    self.tab_charlib.lbl_last_promise_check.setText(
                        f"📭 最近检查:第{ch_num}章 本章未兑现任何承诺 @ {ts}")
                    self.tab_charlib.lbl_last_promise_check.setStyleSheet(
                        "color: #777; font-size: 11px; padding: 4px 6px; "
                        "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
            except Exception:
                pass
            self.tab_generation.log(
                f"✓ 承诺兑现检查完成:第{ch_num}章 共 {count} 条兑现", "info")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 承诺兑现检查解析失败:{e}", "warn")
            try:
                self.tab_charlib.lbl_last_promise_check.setText(
                    f"⚠ 最近检查:第{ch_num}章 JSON 解析失败({e}) "
                    f"@ {_dt.now().strftime('%H:%M:%S')}")
                self.tab_charlib.lbl_last_promise_check.setStyleSheet(
                    "color: #c00; font-size: 11px; padding: 4px 6px; "
                    "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
            except Exception:
                pass

    def _reeval_zero_deadline_promise(self):
        """🤖 AI 重评估 deadline=0 的承诺 — 由按钮触发"""
        if not hasattr(self.tab_charlib, "tbl_promises"):
            return
        items = []
        tbl = self.tab_charlib.tbl_promises
        for r in range(tbl.rowCount()):
            ch_set = tbl.item(r, 0).text() if tbl.item(r, 0) else "0"
            kind = tbl.item(r, 1).text() if tbl.item(r, 1) else "承诺"
            fr = tbl.item(r, 2).text() if tbl.item(r, 2) else ""
            to = tbl.item(r, 3).text() if tbl.item(r, 3) else ""
            ct = tbl.item(r, 4).text() if tbl.item(r, 4) else ""
            dl = tbl.item(r, 5).text() if tbl.item(r, 5) else "0"
            fulfilled = tbl.item(r, 6).text() if tbl.item(r, 6) else "否"
            if fulfilled == "是" or not ct:
                continue
            try:
                if int(dl) != 0:
                    continue
            except ValueError:
                continue
            items.append({"id": r, "ch_set": ch_set, "kind": kind,
                          "from": fr, "to": to, "content": ct[:120]})
        if not items:
            QMessageBox.information(
                self, "AI 重评估",
                "没有需要重评估的承诺(所有未兑现条目的 deadline 都非 0)")
            return
        current_ch = len(self.chapters) if hasattr(self, "chapters") else 1
        ret = QMessageBox.question(
            self, "AI 重评估确认",
            f"将把 {len(items)} 条 deadline=0 的承诺/威胁/约定交给 AI 评估合理截止章节"
            f"(基于当前已写到第 {current_ch} 章)。\n\n继续吗?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            return
        pl = json.dumps(items, ensure_ascii=False)
        prompt = PROMPTS["promise_reeval"].format(
            current_ch=current_ch, promise_list=pl)
        print(f"[promise-reeval v1.77] 评估 {len(items)} 条, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"🤖 AI 重评估承诺 → 发送 {len(items)} 条({len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"承诺重评估-{len(items)}条",
                         target="promise_reeval", count=len(items))

    def _on_promise_reeval_response(self, content, meta):
        """AI 重评估回复 → 把 deadline 回填到 tbl_promises"""
        from datetime import datetime as _dt
        from PyQt5.QtWidgets import QTableWidgetItem
        count_req = meta.get("count", 0)
        print(f"[promise-reeval v1.77] AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 承诺重评估:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略", "warn")
                QMessageBox.warning(self, "AI 重评估失败",
                                    f"AI 输出不是 JSON 数组,本次未更新。\n原始前 200 字:\n"
                                    f"{(content or '')[:200]}")
                return
            count = 0
            current_ch = len(self.chapters) if hasattr(self, "chapters") else 1
            tbl = self.tab_charlib.tbl_promises
            for it in arr:
                if not isinstance(it, dict):
                    continue
                try:
                    rid = int(it.get("id", -1))
                    new_dl = int(it.get("deadline", 0))
                except (TypeError, ValueError):
                    continue
                if not (0 <= rid < tbl.rowCount()):
                    continue
                # 守:AI 又返回 0 或过去章节时强制 +15 fallback
                if new_dl <= current_ch:
                    new_dl = current_ch + 15
                tbl.setItem(rid, 5, QTableWidgetItem(str(new_dl)))
                reason = str(it.get("reason", ""))[:30]
                self.tab_generation.log(
                    f"  ✓ 承诺重评估:[{rid}] deadline → 第{new_dl}章 ({reason})", "info")
                count += 1
            ts = _dt.now().strftime("%H:%M:%S")
            self.tab_generation.log(
                f"✓ AI 重评估完成:更新 {count}/{count_req} 条承诺", "info")
            QMessageBox.information(
                self, "AI 重评估完成",
                f"AI 评估完成,已自动回填 {count}/{count_req} 条承诺的 deadline。\n\n"
                f"完成时间:{ts}")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 承诺重评估解析失败:{e}", "warn")
            QMessageBox.warning(
                self, "AI 重评估失败",
                f"JSON 解析失败:{e}\n原始前 300 字:\n{(content or '')[:300]}")

    # ──────────────────────────────────────────────────────────
    # v1.78 BUG-058:剧情进度自动更新(弧线推进 / 关系值变化)
    # ─────────────────────────────────────────────────────────
    # 与 v1.77 不同点:不是"标记已兑现"(布尔),而是"加 delta"(数值累积)。
    # 弧线 progress 封顶 100,关系值封顶 ±100。
    # 不要"重评估"按钮 — 因为 progress/value 是 0~100/-100~100 的连续值,
    # 没有"deadline=0 失败"这种二元状态,直接 AI 章末更新即可。

    def _run_arc_advance_check(self, content, ch_num):
        """章末让 AI 评估本章对哪几条弧线推进了多少 progress"""
        if not hasattr(self.tab_charlib, "tbl_arcs"):
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        tbl = self.tab_charlib.tbl_arcs
        arcs = []
        for r in range(tbl.rowCount()):
            nm = tbl.item(r, 0).text() if tbl.item(r, 0) else ""
            pg = tbl.item(r, 1).text() if tbl.item(r, 1) else "0"
            ph = tbl.item(r, 2).text() if tbl.item(r, 2) else "开端"
            if not nm:
                continue
            try:
                pg_int = max(0, min(100, int(pg)))
            except (TypeError, ValueError):
                pg_int = 0
            # 已收束(progress=100)的弧线不再让 AI 推进
            if pg_int >= 100:
                continue
            arcs.append({"id": r, "name": nm, "progress": pg_int, "phase": ph})
        if not arcs:
            print(f"[arc-check v1.78] ch={ch_num} 无可推进弧线,跳过", flush=True)
            self.tab_generation.log(
                f"📈 第{ch_num}章弧线推进检查:无可推进弧线,跳过", "info")
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        al = json.dumps(arcs, ensure_ascii=False)
        prompt = PROMPTS["arc_advance_check"].format(
            arc_list=al, ch_num=ch_num, content=content[:6000])
        print(f"[arc-check v1.78] ch={ch_num} 评估 {len(arcs)} 条弧线, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"📈 弧线推进检查-第{ch_num}章 → AI({len(arcs)} 条, "
            f"{len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"弧线推进检查-第{ch_num}章",
                         target="arc_advance_check", ch_num=ch_num)

    def _on_arc_advance_check_response(self, content, meta):
        """AI 回复 → 把 delta 累加到对应 arc 的 progress(封顶 100)"""
        from datetime import datetime as _dt
        from PyQt5.QtWidgets import QTableWidgetItem
        ch_num = meta.get("ch_num", 0)
        print(f"[arc-check v1.78] ch={ch_num} AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 弧线推进检查:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略。原始前 200 字:{(content or '')[:200]}", "warn")
                try:
                    self.tab_charlib.lbl_last_arc_check.setText(
                        f"⚠ 最近评估:第{ch_num}章 AI 输出格式错误(非数组) "
                        f"@ {_dt.now().strftime('%H:%M:%S')}")
                    self.tab_charlib.lbl_last_arc_check.setStyleSheet(
                        "color: #c00; font-size: 11px; padding: 4px 6px; "
                        "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
                except Exception:
                    pass
                return
            count = 0
            tbl = self.tab_charlib.tbl_arcs
            for it in arr:
                if not isinstance(it, dict):
                    continue
                try:
                    rid = int(it.get("id", -1))
                    delta = int(it.get("delta", 0))
                except (TypeError, ValueError):
                    continue
                if not (0 <= rid < tbl.rowCount()):
                    continue
                # 守:delta 限定 0~15(AI 越界时 clamp)
                delta = max(0, min(15, delta))
                if delta == 0:
                    continue
                old_item = tbl.item(rid, 1)
                try:
                    old = int(old_item.text() if old_item else "0")
                except (TypeError, ValueError):
                    old = 0
                new_prog = max(0, min(100, old + delta))
                tbl.setItem(rid, 1, QTableWidgetItem(str(new_prog)))
                # 自动推进 phase(可选,基于 progress 区间)
                try:
                    if new_prog >= 90:
                        ph = "收束"
                    elif new_prog >= 70:
                        ph = "高潮"
                    elif new_prog >= 50:
                        ph = "转折"
                    elif new_prog >= 20:
                        ph = "铺垫"
                    else:
                        ph = "开端"
                    cur_ph = tbl.item(rid, 2).text() if tbl.item(rid, 2) else ""
                    # 不回退 phase(已"高潮"不会因下章推进 5% 回到"转折")
                    _PHASE_RANK = {"开端": 0, "铺垫": 1, "转折": 2, "高潮": 3, "收束": 4}
                    if _PHASE_RANK.get(ph, 0) > _PHASE_RANK.get(cur_ph, 0):
                        tbl.setItem(rid, 2, QTableWidgetItem(ph))
                except Exception:
                    pass
                name = tbl.item(rid, 0).text() if tbl.item(rid, 0) else f"#{rid}"
                reason = str(it.get("reason", ""))[:50]
                self.tab_generation.log(
                    f"  ✓ 弧线推进:[{name}] {old}% → {new_prog}% (+{delta}) — {reason}",
                    "info")
                count += 1
            ts = _dt.now().strftime("%H:%M:%S")
            try:
                if count > 0:
                    self.tab_charlib.lbl_last_arc_check.setText(
                        f"✅ 最近评估:第{ch_num}章 {count} 条弧线推进 @ {ts}")
                    self.tab_charlib.lbl_last_arc_check.setStyleSheet(
                        "color: #06f; font-weight: bold; font-size: 11px; "
                        "padding: 4px 6px; background: #eef6ff; "
                        "border: 1px solid #aac; border-radius: 3px;")
                else:
                    self.tab_charlib.lbl_last_arc_check.setText(
                        f"📭 最近评估:第{ch_num}章 本章未实质推进任何弧线 @ {ts}")
                    self.tab_charlib.lbl_last_arc_check.setStyleSheet(
                        "color: #777; font-size: 11px; padding: 4px 6px; "
                        "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
            except Exception:
                pass
            self.tab_generation.log(
                f"✓ 弧线推进检查完成:第{ch_num}章 共 {count} 条弧线推进", "info")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 弧线推进检查解析失败:{e}", "warn")
            try:
                self.tab_charlib.lbl_last_arc_check.setText(
                    f"⚠ 最近评估:第{ch_num}章 JSON 解析失败({e}) "
                    f"@ {_dt.now().strftime('%H:%M:%S')}")
                self.tab_charlib.lbl_last_arc_check.setStyleSheet(
                    "color: #c00; font-size: 11px; padding: 4px 6px; "
                    "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
            except Exception:
                pass

    def _run_relation_change_check(self, content, ch_num):
        """章末让 AI 评估本章哪些关系值发生变化"""
        if not hasattr(self.tab_charlib, "tbl_rel_values"):
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        tbl = self.tab_charlib.tbl_rel_values
        rels = []
        for r in range(tbl.rowCount()):
            a = tbl.item(r, 0).text() if tbl.item(r, 0) else ""
            b = tbl.item(r, 1).text() if tbl.item(r, 1) else ""
            v = tbl.item(r, 2).text() if tbl.item(r, 2) else "0"
            if not (a and b):
                continue
            try:
                val = int(v)
            except (TypeError, ValueError):
                val = 0
            rels.append({"id": r, "a": a, "b": b, "value": val})
        # 注意:即使 rels 为空,也要发 AI — 因为本章可能新建关系(id=-1)
        rl = json.dumps(rels, ensure_ascii=False)
        prompt = PROMPTS["relation_change_check"].format(
            relation_list=rl, ch_num=ch_num, content=content[:6000])
        print(f"[rel-check v1.78] ch={ch_num} 评估 {len(rels)} 条已有关系, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"💞 关系值变化检查-第{ch_num}章 → AI({len(rels)} 条已有, "
            f"{len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"关系值变化检查-第{ch_num}章",
                         target="relation_change_check", ch_num=ch_num)

    def _on_relation_change_check_response(self, content, meta):
        """AI 回复 → 把 delta 累加 / 新建关系对(封顶 ±100)"""
        from datetime import datetime as _dt
        from PyQt5.QtWidgets import QTableWidgetItem
        ch_num = meta.get("ch_num", 0)
        print(f"[rel-check v1.78] ch={ch_num} AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 关系值变化检查:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略。原始前 200 字:{(content or '')[:200]}", "warn")
                return
            count_upd = 0
            count_new = 0
            tbl = self.tab_charlib.tbl_rel_values
            for it in arr:
                if not isinstance(it, dict):
                    continue
                try:
                    rid = int(it.get("id", -1))
                    delta = int(it.get("delta", 0))
                except (TypeError, ValueError):
                    continue
                # 守:delta 限定 ±50
                delta = max(-50, min(50, delta))
                if delta == 0:
                    continue
                if 0 <= rid < tbl.rowCount():
                    # 已有关系对累加
                    old_item = tbl.item(rid, 2)
                    try:
                        old = int(old_item.text() if old_item else "0")
                    except (TypeError, ValueError):
                        old = 0
                    new_val = max(-100, min(100, old + delta))
                    tbl.setItem(rid, 2, QTableWidgetItem(str(new_val)))
                    tbl.setItem(rid, 3, QTableWidgetItem(str(ch_num)))
                    a = tbl.item(rid, 0).text() if tbl.item(rid, 0) else ""
                    b = tbl.item(rid, 1).text() if tbl.item(rid, 1) else ""
                    reason = str(it.get("reason", ""))[:50]
                    self.tab_generation.log(
                        f"  ✓ 关系变化:[{a}→{b}] {old:+d} → {new_val:+d} "
                        f"({delta:+d}) — {reason}", "info")
                    count_upd += 1
                elif rid == -1:
                    # 新关系对
                    a = str(it.get("a", "")).strip()
                    b = str(it.get("b", "")).strip()
                    if not (a and b):
                        continue
                    new_val = max(-100, min(100, delta))
                    row = tbl.rowCount()
                    tbl.insertRow(row)
                    for col, v in enumerate([a, b, str(new_val), str(ch_num)]):
                        tbl.setItem(row, col, QTableWidgetItem(v))
                    reason = str(it.get("reason", ""))[:50]
                    self.tab_generation.log(
                        f"  ✓ 新关系建立:[{a}→{b}] {new_val:+d} — {reason}", "info")
                    count_new += 1
            ts = _dt.now().strftime("%H:%M:%S")
            self.tab_generation.log(
                f"✓ 关系值变化检查完成:第{ch_num}章 更新 {count_upd} 条 + 新建 {count_new} 条",
                "info")
            # 注:关系值变化不单独更新 label — arc_advance 已经更新过了
        except Exception as e:
            self.tab_generation.log(f"⚠️ 关系值变化检查解析失败:{e}", "warn")

    # ──────────────────────────────────────────────────────────
    # v1.79 BUG-059:信息隔离自动检查(知识穿帮 + 披露追踪)
    # ──────────────────────────────────────────────────────────
    # 与 v1.77/v1.78 的关键差异:info_check 是【侦测违规】而非【状态推进】 —
    # AI 返回的不是"哪些条更新",而是"哪些角色穿帮了"。
    # 命中违规时,系统不会自动修复正文(那需要重写),只标红警告给用户看。
    # 用户判断是 AI 抽错了(可去 known_by 表里加补)还是 AI 写错了(需要重写章节)。

    def _build_known_table_snapshot(self):
        """构造发给 AI 的【已知信息边界】权威表(JSON 字符串)"""
        if not (hasattr(self.tab_charlib, "tbl_infos")
                and hasattr(self.tab_charlib, "tbl_known_by")):
            return "[]"
        # 1. 收集 info_id → content 索引
        info_map = {}
        for r in range(self.tab_charlib.tbl_infos.rowCount()):
            iid = self.tab_charlib.tbl_infos.item(r, 0)
            ct = self.tab_charlib.tbl_infos.item(r, 1)
            if iid and ct and iid.text().strip() and ct.text().strip():
                info_map[iid.text().strip()] = ct.text().strip()
        # 2. 按 info_id 聚合知情人
        by_info = {}
        for r in range(self.tab_charlib.tbl_known_by.rowCount()):
            iid_it = self.tab_charlib.tbl_known_by.item(r, 0)
            ch_it = self.tab_charlib.tbl_known_by.item(r, 1)
            if not (iid_it and ch_it):
                continue
            iid = iid_it.text().strip()
            ch = ch_it.text().strip()
            if not (iid and ch) or iid not in info_map:
                continue
            by_info.setdefault(iid, []).append(ch)
        # 3. 序列化:[{info_id, content, knowers: [角色...]}, ...]
        out = []
        for iid, content in info_map.items():
            out.append({
                "info_id": iid,
                "content": content,
                "knowers": sorted(by_info.get(iid, [])),
            })
        return json.dumps(out, ensure_ascii=False)

    def _run_info_check(self, content, ch_num):
        """章末让 AI 扫描穿帮 — 某角色用了他不该知道的信息"""
        if not (hasattr(self.tab_charlib, "tbl_infos")
                and hasattr(self.tab_charlib, "tbl_known_by")):
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        if self.tab_charlib.tbl_infos.rowCount() == 0:
            print(f"[info-check v1.79] ch={ch_num} 库里没 info,跳过", flush=True)
            self.tab_generation.log(
                f"🔒 第{ch_num}章 知识穿帮检查:库里没 info,跳过", "info")
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        kt = self._build_known_table_snapshot()
        prompt = PROMPTS["info_check"].format(
            known_table=kt, ch_num=ch_num, content=content[:6000])
        print(f"[info-check v1.79] ch={ch_num} 检查 {self.tab_charlib.tbl_infos.rowCount()} 条 info, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"🔒 知识穿帮检查-第{ch_num}章 → AI({self.tab_charlib.tbl_infos.rowCount()} 条 info, "
            f"{len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"知识穿帮检查-第{ch_num}章",
                         target="info_check", ch_num=ch_num)

    def _on_info_check_response(self, content, meta):
        """AI 回复穿帮违规清单 → 标红警告(不自动修)"""
        from datetime import datetime as _dt
        ch_num = meta.get("ch_num", 0)
        print(f"[info-check v1.79] ch={ch_num} AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 知识穿帮检查:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略。原始前 200 字:{(content or '')[:200]}", "warn")
                try:
                    self.tab_charlib.lbl_last_info_check.setText(
                        f"⚠ 最近检查:第{ch_num}章 AI 输出格式错误(非数组) "
                        f"@ {_dt.now().strftime('%H:%M:%S')}")
                    self.tab_charlib.lbl_last_info_check.setStyleSheet(
                        "color: #c00; font-size: 11px; padding: 4px 6px; "
                        "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
                except Exception:
                    pass
                return
            violations = []
            for it in arr:
                if not isinstance(it, dict):
                    continue
                info_id = str(it.get("info_id", "")).strip()
                character = str(it.get("character", "")).strip()
                evidence = str(it.get("evidence", "")).strip()
                why = str(it.get("why_should_not_know", "")).strip()
                if not (info_id and character):
                    continue
                violations.append((info_id, character, evidence, why))
            ts = _dt.now().strftime("%H:%M:%S")
            try:
                if violations:
                    self.tab_charlib.lbl_last_info_check.setText(
                        f"🚨 最近检查:第{ch_num}章 发现 {len(violations)} 处知识穿帮 — 请人工核查"
                        f" @ {ts}")
                    self.tab_charlib.lbl_last_info_check.setStyleSheet(
                        "color: #fff; font-weight: bold; font-size: 11px; "
                        "padding: 4px 6px; background: #c00; "
                        "border: 1px solid #800; border-radius: 3px;")
                    for info_id, character, evidence, why in violations:
                        self.tab_generation.log(
                            f"  🚨 穿帮:[{info_id}] {character} — 证据『{evidence[:30]}』,原因『{why[:30]}』",
                            "warn")
                else:
                    self.tab_charlib.lbl_last_info_check.setText(
                        f"✅ 最近检查:第{ch_num}章 无知识穿帮 @ {ts}")
                    self.tab_charlib.lbl_last_info_check.setStyleSheet(
                        "color: #060; font-weight: bold; font-size: 11px; "
                        "padding: 4px 6px; background: #eeffee; "
                        "border: 1px solid #aca; border-radius: 3px;")
            except Exception:
                pass
            self.tab_generation.log(
                f"✓ 知识穿帮检查完成:第{ch_num}章 {len(violations)} 处违规", "info")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 知识穿帮检查解析失败:{e}", "warn")
            try:
                self.tab_charlib.lbl_last_info_check.setText(
                    f"⚠ 最近检查:第{ch_num}章 JSON 解析失败({e}) "
                    f"@ {_dt.now().strftime('%H:%M:%S')}")
                self.tab_charlib.lbl_last_info_check.setStyleSheet(
                    "color: #c00; font-size: 11px; padding: 4px 6px; "
                    "background: #fff5f5; border: 1px solid #fcc; border-radius: 3px;")
            except Exception:
                pass

    def _run_info_disclose_check(self, content, ch_num):
        """章末让 AI 扫描新披露事件 — 谁本章新知道了什么"""
        if not (hasattr(self.tab_charlib, "tbl_infos")
                and hasattr(self.tab_charlib, "tbl_known_by")):
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        if self.tab_charlib.tbl_infos.rowCount() == 0:
            print(f"[info-disclose v1.79] ch={ch_num} 库里没 info,跳过", flush=True)
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        # info 表
        info_tbl_list = []
        for r in range(self.tab_charlib.tbl_infos.rowCount()):
            iid = self.tab_charlib.tbl_infos.item(r, 0)
            ct = self.tab_charlib.tbl_infos.item(r, 1)
            if iid and ct and iid.text().strip():
                info_tbl_list.append({
                    "info_id": iid.text().strip(),
                    "content": ct.text().strip()})
        kt = self._build_known_table_snapshot()
        prompt = PROMPTS["info_disclose_check"].format(
            info_table=json.dumps(info_tbl_list, ensure_ascii=False),
            known_table=kt, ch_num=ch_num, content=content[:6000])
        print(f"[info-disclose v1.79] ch={ch_num} 扫描披露事件, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"🔒 信息披露追踪-第{ch_num}章 → AI({len(prompt)} 字 prompt)", "info")
        self._send_to_ai(prompt, f"信息披露追踪-第{ch_num}章",
                         target="info_disclose_check", ch_num=ch_num)

    def _on_info_disclose_check_response(self, content, meta):
        """AI 回复新披露事件 → 自动入库到 known_by"""
        from PyQt5.QtWidgets import QTableWidgetItem
        ch_num = meta.get("ch_num", 0)
        print(f"[info-disclose v1.79] ch={ch_num} AI 原始回复({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 信息披露追踪:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略。原始前 200 字:{(content or '')[:200]}", "warn")
                return
            # 现有 known_by 索引(防去重)
            ex_kbs = set()
            tbl = self.tab_charlib.tbl_known_by
            for r in range(tbl.rowCount()):
                iid_it = tbl.item(r, 0)
                ch_it = tbl.item(r, 1)
                if iid_it and ch_it and iid_it.text().strip() and ch_it.text().strip():
                    ex_kbs.add(f"{iid_it.text().strip()}|{ch_it.text().strip()}")
            # 有效 info_ids 集合(过滤悬挂引用)
            valid_ids = set()
            for r in range(self.tab_charlib.tbl_infos.rowCount()):
                it = self.tab_charlib.tbl_infos.item(r, 0)
                if it and it.text().strip():
                    valid_ids.add(it.text().strip())
            count = 0
            for it in arr:
                if not isinstance(it, dict):
                    continue
                info_id = str(it.get("info_id", "")).strip()
                to = str(it.get("to", "")).strip()
                via = str(it.get("via", "")).strip()
                if not (info_id and to):
                    continue
                if info_id not in valid_ids:
                    self.tab_generation.log(
                        f"  ⚠️ 跳过悬挂引用:[{info_id}] 不在 infos 表里", "warn")
                    continue
                k = f"{info_id}|{to}"
                if k in ex_kbs:
                    continue
                row = tbl.rowCount()
                tbl.insertRow(row)
                for col, v in enumerate([info_id, to, via or f"第{ch_num}章新披露"]):
                    tbl.setItem(row, col, QTableWidgetItem(v))
                count += 1
                ex_kbs.add(k)
                self.tab_generation.log(
                    f"  ✓ 新披露:[{info_id}] → {to} 通过『{via[:30]}』", "info")
            self.tab_generation.log(
                f"✓ 信息披露追踪完成:第{ch_num}章 新入库 {count} 条 known_by", "info")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 信息披露追踪解析失败:{e}", "warn")

    # ──────────────────────────────────────────────────────────
    # v1.85 BUG-062:写作模式回流(章末把章号反向挂到剧情树节点)
    # ──────────────────────────────────────────────────────────
    # 与 v1.79 info_check 对照:都是【侦测式】检查 — AI 返回的不是新建数据,
    # 而是【本章对应哪些已存在节点】。命中后改 tree_plot 第 5 列(append 章号,
    # 不覆盖,同节点可被多章命中),同时去重(同章号不重复挂)。
    # 与 v1.80 注入逻辑的对照:v1.80 是"按章号找节点"(读),v1.85 是"按内容找节点"(写)。

    def _run_chapter_to_plot_node(self, content, ch_num):
        """章末让 AI 反查本章对应剧情树哪些节点"""
        if not hasattr(self.tab_charlib, "tree_plot"):
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        nodes = self.tab_charlib._tree_to_list()
        if not nodes:
            print(f"[plot-reflow v1.85] ch={ch_num} 剧情树空,跳过", flush=True)
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        # 给 AI 一个精简版表(id + kind + name + ch_range)— 不含 chapter_links 避免循环
        simplified = []
        for n in nodes:
            if not n["node_id"] or not n["name"]:
                continue
            simplified.append({
                "node_id": n["node_id"],
                "kind": n["kind"],
                "name": n["name"],
                "ch_range": n.get("ch_range", ""),
            })
        if not simplified:
            print(f"[plot-reflow v1.85] ch={ch_num} 剧情树全是无名节点,跳过", flush=True)
            QTimer.singleShot(100, self._run_next_post_chapter_step)
            return
        prompt = PROMPTS["chapter_to_plot_node"].format(
            plot_tree=json.dumps(simplified, ensure_ascii=False),
            ch_num=ch_num,
            content=content[:6000])
        print(f"[plot-reflow v1.85] ch={ch_num} 反查 {len(simplified)} 个剧情节点, "
              f"prompt {len(prompt)} 字", flush=True)
        self.tab_generation.log(
            f"🌳 写作回流-第{ch_num}章 → AI({len(simplified)} 节点, {len(prompt)} 字)",
            "info")
        self._send_to_ai(prompt, f"写作回流-第{ch_num}章",
                         target="chapter_to_plot_node", ch_num=ch_num)

    def _on_chapter_to_plot_node_response(self, content, meta):
        """AI 反查结果 → 章号 append 到对应节点的 chapter_links 列(第 5 列)"""
        from PyQt5.QtCore import Qt
        ch_num = meta.get("ch_num", 0)
        print(f"[plot-reflow v1.85] ch={ch_num} AI 原始({len(content or '')} 字) "
              f"前 200: {(content or '')[:200]!r}", flush=True)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            if not isinstance(arr, list):
                self.tab_generation.log(
                    f"⚠️ 写作回流:AI 返回的不是 JSON 数组(是 {type(arr).__name__}),"
                    f"已忽略", "warn")
                return
            # 建 node_id → QTreeWidgetItem 索引(扫全树)
            id_to_item = {}
            tree = self.tab_charlib.tree_plot
            def _scan(item):
                nid = item.data(0, Qt.UserRole)
                if nid:
                    id_to_item[str(nid)] = item
                for i in range(item.childCount()):
                    _scan(item.child(i))
            for i in range(tree.topLevelItemCount()):
                _scan(tree.topLevelItem(i))

            count = 0
            for it in arr:
                if not isinstance(it, dict):
                    continue
                node_id = str(it.get("node_id", "")).strip()
                reason = str(it.get("reason", "")).strip()
                if not node_id:
                    continue
                if node_id not in id_to_item:
                    self.tab_generation.log(
                        f"  ⚠️ 跳过悬挂节点 id:{node_id}(不在剧情树里)", "warn")
                    continue
                # 追加章号到第 5 列(逗号分隔,去重)
                item = id_to_item[node_id]
                cur = (item.text(4) or "").strip()
                existing = set(c.strip() for c in cur.split(",") if c.strip())
                ch_str = str(ch_num)
                if ch_str in existing:
                    continue  # 已挂过,跳
                existing.add(ch_str)
                # 排序后写回 — 章号按数字升序
                try:
                    sorted_chs = sorted(existing, key=lambda x: int(x))
                except ValueError:
                    sorted_chs = sorted(existing)
                item.setText(4, ", ".join(sorted_chs))
                count += 1
                self.tab_generation.log(
                    f"  ✓ 第{ch_num}章 → 节点[{node_id}]『{item.text(0)}』"
                    f"{('(' + reason[:25] + ')') if reason else ''}",
                    "info")
            self.tab_generation.log(
                f"✓ 写作回流完成:第{ch_num}章 挂到 {count} 个剧情节点", "info")
        except Exception as e:
            self.tab_generation.log(f"⚠️ 写作回流解析失败:{e}", "warn")

    def _post_chapter_chain(self, ch_num):
        """章节通过后的链式处理:Canon 抽取 → 6库抽取 → 章末技能 → 摘要 → 下一章"""
        if ch_num <= 0:
            return
        # v1.75:全链路诊断 — 让用户能看出'Canon 自动抽取没生效'到底卡在哪
        canon_on = bool(self.tab_canon.chk_extract.isChecked())
        charlib_on = bool(hasattr(self.tab_charlib, "chk_auto_extract") and
                          self.tab_charlib.chk_auto_extract.isChecked())
        print(f"[post-chain v1.75] ch={ch_num} canon_extract={canon_on} "
              f"charlib_extract={charlib_on}", flush=True)
        self.tab_generation.log(
            f"📋 第 {ch_num} 章后置链准备启动 "
            f"(Canon抽取={'✓' if canon_on else '✗'} / "
            f"6库抽取={'✓' if charlib_on else '✗'})",
            "info")
        
        pipeline = []
        if self.tab_canon.chk_extract.isChecked():
            pipeline.append(("canon_extract", ch_num))

        # BUG-014:6 库自动抽取(角色/关系/时间线/物品/战力/伏笔)
        if hasattr(self.tab_charlib, "chk_auto_extract") and \
                self.tab_charlib.chk_auto_extract.isChecked():
            pipeline.append(("charlib_extract", ch_num))

        # v1.76 BUG-056:伏笔自动回收检查(只有当库里有未回收伏笔时才发 AI)
        # 注意:放在 charlib_extract 后面 — 让新抽的伏笔先入库,再统一检查回收
        if hasattr(self.tab_charlib, "tbl_fore"):
            # 检查是否有未回收伏笔,有才挂(节省 AI 调用)
            _has_pending = False
            for r in range(self.tab_charlib.tbl_fore.rowCount()):
                paid = self.tab_charlib.tbl_fore.item(r, 3)
                ct = self.tab_charlib.tbl_fore.item(r, 1)
                if ct and ct.text().strip() and (not paid or paid.text() != "是"):
                    _has_pending = True
                    break
            if _has_pending:
                pipeline.append(("foreshadow_check", ch_num))

        # v1.77 BUG-057:承诺/威胁/约定自动兑现检查(只有库里有未兑现条目时才挂)
        # 注意:在 foreshadow_check 之后 — 同样让新抽的承诺先入库
        if hasattr(self.tab_charlib, "tbl_promises"):
            _has_pending_pr = False
            for r in range(self.tab_charlib.tbl_promises.rowCount()):
                ful = self.tab_charlib.tbl_promises.item(r, 6)
                ct = self.tab_charlib.tbl_promises.item(r, 4)
                if ct and ct.text().strip() and (not ful or ful.text() != "是"):
                    _has_pending_pr = True
                    break
            if _has_pending_pr:
                pipeline.append(("promise_check", ch_num))

        # v1.78 BUG-058:剧情进度更新(弧线推进 + 关系值变化)— 都挂在 promise_check 之后
        # 顺序:arc_advance_check → relation_change_check(独立 AI 调用,各管各的)
        # 同 v1.76/v1.77 模式 — 只有库里有"可推进"或"可变化"的对象时才挂
        if hasattr(self.tab_charlib, "tbl_arcs"):
            # 弧线检查:只要有未完成弧线(progress < 100)就挂
            _has_open_arc = False
            for r in range(self.tab_charlib.tbl_arcs.rowCount()):
                nm_it = self.tab_charlib.tbl_arcs.item(r, 0)
                pg_it = self.tab_charlib.tbl_arcs.item(r, 1)
                if not (nm_it and nm_it.text().strip()):
                    continue
                try:
                    pg = int(pg_it.text()) if pg_it else 0
                except (TypeError, ValueError):
                    pg = 0
                if pg < 100:
                    _has_open_arc = True
                    break
            if _has_open_arc:
                pipeline.append(("arc_advance_check", ch_num))

        if hasattr(self.tab_charlib, "tbl_rel_values"):
            # 关系值检查:库里有任何关系对 / 或者哪怕没关系对也允许 AI 新建
            # 但若全库为空且本章可能没角色互动,跳过 — 这里保守:库里有 ≥1 行就挂,
            # 没行就先等 world_extract 抽出来再说,本章不查变化
            _has_rel = False
            for r in range(self.tab_charlib.tbl_rel_values.rowCount()):
                a_it = self.tab_charlib.tbl_rel_values.item(r, 0)
                b_it = self.tab_charlib.tbl_rel_values.item(r, 1)
                if a_it and b_it and a_it.text().strip() and b_it.text().strip():
                    _has_rel = True
                    break
            if _has_rel:
                pipeline.append(("relation_change_check", ch_num))

        # v1.79 BUG-059:信息隔离检查 — 两阶段
        # 1) info_disclose_check:扫描本章新披露事件,自动入库到 known_by
        # 2) info_check:扫描穿帮违规(某角色用了他不该知道的信息)— 标红警告,不自动修
        # 顺序很重要:disclose 必须在 check 之前 — 因为 check 用的 known_by 表里
        # 应包含本章新披露的人,否则会把"刚听完就用上的合法对话"误判为穿帮
        if hasattr(self.tab_charlib, "tbl_infos"):
            _has_info = self.tab_charlib.tbl_infos.rowCount() > 0
            if _has_info:
                pipeline.append(("info_disclose_check", ch_num))
                pipeline.append(("info_check", ch_num))

        # v1.85 BUG-062:写作模式回流 — AI 反查本章对应剧情树哪些节点
        # 必须挂在所有结构化抽取/检查之后(因为它依赖前面所有数据稳定后再跑)
        # 是【侦测式】检查 — 只把章号挂到节点(第 5 列),不改剧情树结构
        if hasattr(self.tab_charlib, "tree_plot"):
            if self.tab_charlib.tree_plot.topLevelItemCount() > 0:
                pipeline.append(("chapter_to_plot_node", ch_num))

        # after_chapter_generation 技能(固定自动触发)
        for s in self.tab_skills.get_after_chapter_skills():
            pipeline.append(("skill_after", ch_num, s))

        # auto_match 技能(根据章节内容正则匹配触发)
        ch_content = (self.chapters[ch_num - 1].get("content", "")
                      if 0 < ch_num <= len(self.chapters) else "")
        for s in self.tab_skills.get_auto_match_skills(ch_content):
            self.tab_generation.log(
                f"🎯 auto_match 技能「{s['name']}」命中(第{ch_num}章)", "info")
            pipeline.append(("skill_after", ch_num, s))

        if self.tab_memory.auto_summarize.isChecked():
            need_more = self._batch_remaining > 0 and not self._batch_paused
            pipeline.append(("summary", ch_num, need_more))
        else:
            need_more = self._batch_remaining > 0 and not self._batch_paused
            if need_more:
                pipeline.append(("next_chapter",))
            else:
                pipeline.append(("end_batch",))

        # v1.02:让用户能看到 pipeline 真的启动了
        if pipeline:
            _step_names = [s[0] for s in pipeline]
            self.tab_generation.log(
                f"🔗 第 {ch_num} 章后置链启动: {' → '.join(_step_names)}", "info")
        self._post_chapter_pipeline = pipeline
        QTimer.singleShot(800, self._run_next_post_chapter_step)

    def _run_next_post_chapter_step(self):
        """后置流水线推进"""
        if not getattr(self, "_post_chapter_pipeline", None):
            return
        step = self._post_chapter_pipeline.pop(0)
        if step[0] == "canon_extract":
            ch = self.chapters[step[1] - 1] if step[1] <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_canon_extract(ch["content"], step[1])
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "charlib_extract":
            # BUG-014:批量抽取 6 库(角色/关系/时间线/物品/战力/伏笔)
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                # 复用 _charlib_extract_from_chapters 的单章逻辑
                self._charlib_batch_queue = [ch_num]
                # 设置 flag,让 _on_world_extract_received 完成后回 post_chapter 链
                self._charlib_chain_post = True
                self._run_next_charlib_extract()
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "foreshadow_check":
            # v1.76 BUG-056:伏笔自动回收检查
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_foreshadow_check(ch["content"], ch_num)
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "promise_check":
            # v1.77 BUG-057:承诺/威胁/约定自动兑现检查
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_promise_check(ch["content"], ch_num)
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "arc_advance_check":
            # v1.78 BUG-058:弧线推进自动评估
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_arc_advance_check(ch["content"], ch_num)
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "relation_change_check":
            # v1.78 BUG-058:关系值变化自动评估
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_relation_change_check(ch["content"], ch_num)
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "info_disclose_check":
            # v1.79 BUG-059:扫描新披露事件
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_info_disclose_check(ch["content"], ch_num)
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "info_check":
            # v1.79 BUG-059:扫描穿帮违规(标红警告,不自动修)
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_info_check(ch["content"], ch_num)
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "chapter_to_plot_node":
            # v1.85 BUG-062:写作模式回流 — 反查本章对应剧情树节点
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_chapter_to_plot_node(ch["content"], ch_num)
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "skill_after":
            ch_num, skill = step[1], step[2]
            self._run_skill_on_chapter(skill, ch_num, chain_post=True)
        elif step[0] == "summary":
            ch_num, need_more = step[1], step[2]
            self._submit_summary_task(ch_num, chain_to_next=need_more)
        elif step[0] == "next_chapter":
            QTimer.singleShot(800, self._send_next_chapter)
        elif step[0] == "end_batch":
            self.tab_generation.log("批量生成已结束", "info")
            self._check_auto_shutdown()

    def gen_current_summary(self):
        """生成当前选中章节的摘要"""
        idx = self.chapter_list.currentRow()
        if idx < 0:
            QMessageBox.information(self, "提示", "请先在左侧选中一章")
            return
        # 同步当前编辑器内容到 chapters
        if self.current_chapter_index == idx:
            self.chapters[idx]["title"] = self.tab_editor.title_input.text()
            self.chapters[idx]["content"] = self.tab_editor.content_edit.toPlainText()
        if not self.chapters[idx].get("content", "").strip():
            QMessageBox.warning(self, "提示", "本章正文为空,无法生成摘要")
            return
        self._submit_summary_task(idx + 1, chain_to_next=False)

    def gen_all_missing_summaries(self):
        """补齐所有缺失的章节摘要"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "还没有章节内容")
            return
        sums = self.tab_memory.parse_summaries()
        missing = []
        for i, ch in enumerate(self.chapters):
            n = i + 1
            if n not in sums and ch.get("content", "").strip():
                missing.append(n)
        if not missing:
            QMessageBox.information(self, "提示", "所有章节都已有摘要")
            return
        self.tab_generation.log(
            f"准备补齐 {len(missing)} 章摘要(将依次发到浏览器队列)", "info")
        # 依次提交,worker 会按顺序处理
        for n in missing:
            self._submit_summary_task(n, chain_to_next=False)

    def extract_characters(self, chain_full_memory=False):
        """从最新章节提取/更新角色档案"""
        if not self.chapters:
            if not chain_full_memory:
                QMessageBox.information(self, "提示", "还没有章节内容")
            return False
        # 流水线模式:扫描更多章节(最多 5 章)以获得更全面的角色档案
        recent = self.chapters[-5:] if chain_full_memory else self.chapters[-3:]
        content = "\n\n".join(
            f"{ch.get('title', '')}\n{ch.get('content', '')[:2500]}" for ch in recent)
        existing = self.tab_memory.chars_edit.toPlainText().strip()
        existing_block = (
            f"已有的角色档案(请在此基础上更新/补充):\n{existing}\n\n"
            if existing else "")
        prompt = PROMPTS["character_extract"].format(
            existing=existing_block, content=content[:8000])
        self._send_to_ai(
            prompt, "角色提取",
            target="character_extract",
            chain_full_memory=chain_full_memory,
        )
        return True

    def extract_long_term(self, chain_full_memory=False):
        """从最新章节提取长期记忆"""
        if not self.chapters:
            if not chain_full_memory:
                QMessageBox.information(self, "提示", "还没有章节内容")
            return False
        ch = self.chapters[-1]
        if not ch.get("content", "").strip():
            if not chain_full_memory:
                QMessageBox.warning(self, "提示", "最新章节正文为空")
            return False
        content = f"{ch.get('title', '')}\n{ch.get('content', '')[:5000]}"
        prompt = PROMPTS["long_term_extract"].format(content=content)
        self._send_to_ai(
            prompt, f"长期记忆-{ch.get('title', '')}",
            target="long_term_extract",
            chain_full_memory=chain_full_memory,
        )
        return True

    # ===================================================================
    # 一键生成对话记忆 - 流水线
    # ===================================================================
    def gen_full_memory(self):
        """一键生成完整对话记忆: 补齐摘要 → 提取角色 → 提取长期记忆"""
        if not self.chapters:
            QMessageBox.warning(self, "提示", "还没有章节内容,无法生成对话记忆")
            return
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录。")
            return
        if self._full_memory_running:
            QMessageBox.information(self, "提示", "当前一键生成正在进行中,请等待或点中止")
            return

        # 构造流水线:[(step, arg), ...]
        pipeline = []
        # 第 1 阶段:补齐所有缺失的摘要
        sums = self.tab_memory.parse_summaries()
        missing = []
        for i, ch in enumerate(self.chapters):
            n = i + 1
            if n not in sums and ch.get("content", "").strip():
                missing.append(n)
                pipeline.append(("summary", n))
        # 第 2 阶段:提取角色档案(只一次)
        pipeline.append(("character", None))
        # 第 3 阶段:提取长期记忆(只一次)
        pipeline.append(("long_term", None))

        self._full_memory_pipeline = pipeline
        self._full_memory_total = len(pipeline)
        self._full_memory_running = True

        # UI 反馈
        self.tab_memory.btn_gen_full_memory.setEnabled(False)
        self.tab_memory.btn_stop_full_memory.setEnabled(True)
        steps_desc = (
            f"{len(missing)} 个缺失摘要 + 角色档案 + 长期记忆"
            if missing else "角色档案 + 长期记忆(摘要已齐全)")
        self.tab_memory.update_progress(
            f"启动:共 {self._full_memory_total} 步({steps_desc})", "running")
        self.tab_generation.log(
            f"▶ 一键生成对话记忆启动,共 {self._full_memory_total} 步:{steps_desc}",
            "info")
        self._switch_to_tab(self.tab_memory)

        self._run_next_full_memory_step()

    def _run_next_full_memory_step(self):
        """流水线推进一步"""
        if not self._full_memory_running:
            return
        if not self._full_memory_pipeline:
            # 全部完成
            self._full_memory_running = False
            self.tab_memory.btn_gen_full_memory.setEnabled(True)
            self.tab_memory.btn_stop_full_memory.setEnabled(False)
            self.tab_memory.update_progress("✓ 对话记忆生成完成!", "success")
            self.tab_generation.log("✓ 一键生成对话记忆全部完成", "success")
            # 自动刷新预览
            self._refresh_memory_preview()
            return

        step, arg = self._full_memory_pipeline.pop(0)
        done = self._full_memory_total - len(self._full_memory_pipeline)
        progress_prefix = f"[{done}/{self._full_memory_total}]"

        if step == "summary":
            self.tab_memory.update_progress(
                f"{progress_prefix} 正在生成第 {arg} 章摘要...", "running")
            self._submit_summary_task(arg, chain_full_memory=True)
        elif step == "character":
            self.tab_memory.update_progress(
                f"{progress_prefix} 正在提取角色档案...", "running")
            ok = self.extract_characters(chain_full_memory=True)
            if not ok:
                # 跳过本步
                self._run_next_full_memory_step()
        elif step == "long_term":
            self.tab_memory.update_progress(
                f"{progress_prefix} 正在提取长期记忆...", "running")
            ok = self.extract_long_term(chain_full_memory=True)
            if not ok:
                self._run_next_full_memory_step()

    def stop_full_memory(self):
        """中止一键生成"""
        if not self._full_memory_running:
            return
        self._full_memory_running = False
        self._full_memory_pipeline = []
        self.tab_memory.btn_gen_full_memory.setEnabled(True)
        self.tab_memory.btn_stop_full_memory.setEnabled(False)
        self.tab_memory.update_progress("已中止", "error")
        self.tab_generation.log("一键生成对话记忆已中止", "warn")

    def _popup_choose_target(self, content):
        """没指定 target 时:直接复制到剪贴板,不弹窗打扰"""
        if not content.strip():
            return
        QApplication.clipboard().setText(content)
        self.tab_generation.log(
            f"✓ 已抓取 {len(content)} 字符,内容已复制到剪贴板", "success")

    # ════════════════════════════════════════════════
    # v1.10 TTS 朗读 — Index-TTS / EdgeTTS 后端
    # ════════════════════════════════════════════════
    def _refresh_recent_menu(self):
        """v1.41: 刷新文件菜单 → 最近项目 子菜单(每次 open/save 后调用)"""
        if not hasattr(self, "recent_menu") or not self.recent_menu:
            return
        self.recent_menu.clear()
        from PyQt5.QtCore import QSettings
        from pathlib import Path as _P
        recent = QSettings("NovelAI", "UI").value(
            "recent_projects", [], type=list) or []
        if not recent:
            a = self.recent_menu.addAction("(空 — 打开项目后会出现)")
            a.setEnabled(False)
            return
        # 显示最多 10 个,带快捷键 1-9
        added = 0
        for path in recent[:10]:
            p = _P(path)
            if not p.exists():
                continue
            added += 1
            label = f"&{added}  {p.name}" if added <= 9 else f"   {p.name}"
            a = self.recent_menu.addAction(label)
            # 闭包陷阱:用 lambda 默认参数固定 path
            a.triggered.connect(lambda checked=False, _p=str(p): self._open_project_by_path(_p))
        if added == 0:
            a = self.recent_menu.addAction("(列表已清空 — 项目可能被移动)")
            a.setEnabled(False)
        else:
            self.recent_menu.addSeparator()
            a_clear = self.recent_menu.addAction("✕ 清空最近项目列表")
            a_clear.triggered.connect(self._clear_recent_projects)

        # v2.23.4: 同步刷新左栏最近项目列表
        try:
            self._load_recent_to_sidebar()
        except Exception:
            pass

    def _open_project_by_path(self, path):
        """v1.41: 通过路径直接打开项目(跳过 open_project 的对话框)"""
        from pathlib import Path as _P
        from PyQt5.QtWidgets import QMessageBox
        target = _P(path)
        if not target.exists() or not target.is_dir():
            QMessageBox.warning(
                self, "项目不存在",
                f"项目文件夹不存在或已被移动:\n{target}\n\n"
                "将从最近项目列表移除。")
            self._remove_from_recent(path)
            self._refresh_recent_menu()
            return
        if not PROJECT_IO_AVAILABLE:
            QMessageBox.warning(self, "缺少 project_io 模块", "无法打开文件夹格式项目")
            return
        try:
            d = project_io.load_project_folder(target)
            self.current_project_file = str(target.resolve())
            self._load_payload_into_ui(d)
            self._push_to_recent(self.current_project_file)
            # 存 last_project_path
            from PyQt5.QtCore import QSettings
            QSettings("NovelAI", "UI").setValue(
                "last_project_path", self.current_project_file)
            self.tab_generation.log(f"📂 已打开: {target.name}", "success")
            self._project_title = target.name
            self._update_window_title()
            # v2.23.4: 番茄榜单 Tab 同步项目根目录 + 加载磁盘缓存
            self._sync_fanqie_rank_tab()
            # 刷新项目主页
            if hasattr(self, "tab_home"):
                self.tab_home.refresh(self)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"加载项目失败:\n{e}")

    def import_continuation(self):
        """v1.51: 导入外部小说续写 — 三阶段:
        阶段 1: 选 .txt 文件 → book_splitter 拆章
        阶段 2: ImportContinuationDialog 让用户选模式(当前项目/新项目 + AI 提取?)
        阶段 3: 执行导入(可能含 AI 调用)
        """
        if not BOOK_SPLITTER_AVAILABLE or not IMPORT_CONTINUATION_AVAILABLE:
            QMessageBox.warning(
                self, "模块缺失",
                "需要 book_splitter.py 和 import_continuation.py")
            return

        # 阶段 1: 选文件 + 拆章
        path, _ = QFileDialog.getOpenFileName(
            self, "选择外部小说 TXT 文件",
            str(self.project_dir), "TXT 文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            book_meta = book_splitter.load_and_split(path)
        except Exception as e:
            QMessageBox.critical(self, "拆章失败", f"无法读取或拆分文件:\n{e}")
            return
        if book_meta.chapter_count == 0:
            QMessageBox.warning(
                self, "未识别章节",
                "没有从这个文件识别出任何章节(可能没有「第 X 章」标记)。\n\n"
                "如果想整本当一章导入,先重命名为「第一章 xxx.txt」之类。")
            return

        # 阶段 2: 配置对话框
        dlg = import_continuation.ImportContinuationDialog(
            parent=self, book_meta=book_meta)
        if dlg.exec_() != QDialog.Accepted:
            return
        cfg = dlg.get_result()

        # 阶段 3: 浏览器在线检查(只在勾选 AI 时)
        if cfg["ai_extract"]:
            if not self.worker.is_ready():
                ret = QMessageBox.question(
                    self, "浏览器未启动",
                    "你勾了「让 AI 提取设定」,但浏览器还没启动。\n\n"
                    "  是 → 现在去启动浏览器(请先到「生成控制」点 🚀 启动)\n"
                    "  否 → 跳过 AI 提取,只导入章节(以后手动补设定)",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if ret == QMessageBox.Yes:
                    # 跳到生成控制 Tab,让用户去启动浏览器
                    try:
                        for i in range(self.tabs.count()):
                            if "生成控制" in self.tabs.tabText(i):
                                self.tabs.setCurrentIndex(i)
                                break
                    except Exception:
                        pass
                    return   # 用户启动后重新走这个流程
                else:
                    cfg["ai_extract"] = False   # 用户选跳过

        # 执行导入
        self._do_import_continuation(book_meta, cfg, source_path=path)

    def _do_import_continuation(self, book_meta, cfg, source_path=""):
        """阶段 3: 执行实际的导入操作"""
        from pathlib import Path as _P

        # ─ 模式 B: 新建项目 ─
        if cfg["mode"] == "new":
            # 如果有未保存内容,提示
            if self.chapters and not QMessageBox.question(
                self, "新建项目?",
                "当前已有打开的项目。新建会切换到新项目(当前会先自动保存)。\n\n"
                "继续吗?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            ) == QMessageBox.Yes:
                return
            # 先保存当前
            try:
                if self.current_project_file:
                    self.save_project()
            except Exception:
                pass
            # 清空状态
            self.chapters = []
            self.current_chapter_index = -1
            self.current_project_file = None
            # 设书名
            self.tab_settings.title_input.setText(book_meta.title)

        # ─ 把章节追加到 self.chapters ─
        start_idx = len(self.chapters)
        for ch in book_meta.chapters:
            chapter_dict = {
                "title": ch.title_clean or ch.title,
                "content": ch.content,
            }
            if cfg["mark_imported"] and source_path:
                chapter_dict["imported_from"] = _P(source_path).name
                chapter_dict["is_imported"] = True
            self.chapters.append(chapter_dict)

        # 刷新章节列表 + UI
        self._refresh_chapter_list()
        try:
            if hasattr(self, "tab_home"):
                self.tab_home.refresh(self)
        except Exception:
            pass

        self.tab_generation.log(
            f"✓ 已导入 {book_meta.chapter_count} 章到{'当前项目' if cfg['mode']=='current' else '新项目'},"
            f"现在共 {len(self.chapters)} 章",
            "success")

        # ─ 走 AI 提取(如果勾了) ─
        if cfg["ai_extract"]:
            extract_n = min(cfg["extract_n"], book_meta.chapter_count)
            chapters_to_extract = book_meta.chapters[:extract_n]
            prompt = import_continuation.build_extract_prompt(
                chapters_to_extract, max_chars=30000)
            self.tab_generation.log(
                f"▶ 让 AI 读前 {extract_n} 章提取设定,约 1-2 分钟...", "info")
            self._send_to_ai(
                prompt, f"导入续写-AI 提取设定(前{extract_n}章)",
                target="import_extract",
                import_source=_P(source_path).name if source_path else "",
            )
        else:
            # 不提取 → 直接弹完成提示
            QMessageBox.information(
                self, "✓ 导入完成",
                f"已导入 {book_meta.chapter_count} 章。\n\n"
                "下一步:\n"
                "  · 到「创作设置」/「故事大纲」补一下世界观/主角设定\n"
                "  · 到「章节编辑器」检查导入的章节内容\n"
                "  · 点「📖 生成下一章」开始续写")
            # 保存
            try:
                self.save_project()
            except Exception:
                pass

    def _on_import_extract_received(self, content, meta):
        """v1.51: AI 提取设定返回 → 填充对应字段"""
        data = import_continuation.parse_extract_response(content)
        if not data:
            QMessageBox.warning(
                self, "AI 提取失败",
                f"AI 返回的 JSON 无法解析。\n\n"
                f"原始返回(前 500 字):\n{(content or '')[:500]}\n\n"
                f"章节已正常导入,但设定字段需要手动补。")
            try:
                self.save_project()
            except Exception:
                pass
            return

        # ── 填充字段 ──
        filled = []

        # 1. 角色 → 6 库
        chars = data.get("characters", []) or []
        if chars and hasattr(self, "tab_charlib") and hasattr(self.tab_charlib, "tbl_chars"):
            try:
                tbl = self.tab_charlib.tbl_chars
                for ch in chars[:20]:   # 最多 20 个,避免炸表
                    row = tbl.rowCount()
                    tbl.insertRow(row)
                    cells = [
                        ch.get("name", ""), ch.get("role", ""),
                        ch.get("appearance", ""), ch.get("personality", ""),
                        "",   # 标志/口头禅
                        ch.get("ability", ""), ch.get("state", ""), "",
                    ]
                    from PyQt5.QtWidgets import QTableWidgetItem
                    for c, v in enumerate(cells):
                        tbl.setItem(row, c, QTableWidgetItem(str(v)))
                filled.append(f"角色 {len(chars)} 个 → 角色库")
            except Exception as e:
                print(f"[import] 填充角色失败: {e}", flush=True)

        # 2. 世界观 → 故事大纲
        wv = data.get("worldview", "").strip()
        if wv:
            try:
                current = self.tab_outline.worldview_edit.toPlainText().strip()
                # 追加,不覆盖
                merged = (current + "\n\n──── AI 提取 ────\n" + wv) if current else wv
                self.tab_outline.worldview_edit.setPlainText(merged)
                filled.append(f"世界观({len(wv)} 字)→ 故事大纲")
            except Exception as e:
                print(f"[import] 填充世界观失败: {e}", flush=True)

        # 3. 故事种子 → 大纲 seed
        seed = data.get("seed", "").strip()
        if seed:
            try:
                current = self.tab_outline.seed_edit.toPlainText().strip()
                merged = (current + "\n\n──── AI 提取 ────\n" + seed) if current else seed
                self.tab_outline.seed_edit.setPlainText(merged)
                filled.append(f"故事种子 → 大纲")
            except Exception as e:
                print(f"[import] 填充种子失败: {e}", flush=True)

        # 4. 伏笔 → Canon
        forshadows = data.get("foreshadows", []) or []
        if forshadows and hasattr(self, "tab_canon"):
            try:
                for f in forshadows[:20]:
                    # 简化:把伏笔追加到 canon 的"演化项"
                    ch_num = f.get("chapter", "?")
                    content_text = f.get("content", "").strip()
                    if content_text:
                        item_text = f"[第{ch_num}章 伏笔] {content_text}"
                        # 复用 tab_canon 的接口(如果有的话)
                        if hasattr(self.tab_canon, "add_evolving"):
                            self.tab_canon.add_evolving(item_text)
                filled.append(f"伏笔 {len(forshadows)} 条 → Canon")
            except Exception as e:
                print(f"[import] 填充伏笔失败: {e}", flush=True)

        # 5. 后续大纲建议 → 章节大纲(追加在末尾)
        next_outline = data.get("outline_next", []) or []
        if next_outline:
            try:
                current = self.tab_outline.chapter_outline_edit.toPlainText().strip()
                addition = "\n\n──── AI 续写建议(导入时生成) ────\n"
                addition += "\n".join(f"  · {x}" for x in next_outline)
                merged = (current + addition) if current else addition.lstrip("\n")
                self.tab_outline.chapter_outline_edit.setPlainText(merged)
                filled.append(f"后续大纲 {len(next_outline)} 条 → 章节大纲")
            except Exception as e:
                print(f"[import] 填充后续大纲失败: {e}", flush=True)

        # 总结
        summary = "\n".join(f"  ✓ {x}" for x in filled) if filled else "  (无可用字段)"
        QMessageBox.information(
            self, "✓ 导入完成 + AI 提取完成",
            f"已成功导入章节并提取设定:\n\n{summary}\n\n"
            f"建议:\n"
            f"  · 到「🎭 角色与世界」检查角色档案是否准确\n"
            f"  · 到「故事大纲」检查世界观/种子\n"
            f"  · 到「Canon 设定」检查伏笔\n"
            f"  · 这些都是 AI 提取的,可能不完美,请按需调整")

        # 保存
        try:
            self.save_project()
        except Exception as e:
            self.tab_generation.log(f"⚠ 保存失败:{e}", "warn")

    def _import_legacy_json(self):
        """v1.50: 导入老 .json 项目(罕用,从工具菜单触发)
        会自动升级为文件夹格式,原 .json 保留为 .legacy-original.json"""
        if not PROJECT_IO_AVAILABLE:
            QMessageBox.warning(self, "缺少模块", "需要 project_io.py")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择旧版 .json 项目文件",
            str(self.project_dir), "项目 (*.json)")
        if not path:
            return
        try:
            fmt = project_io.detect_format(path)
            if fmt != "legacy_json":
                QMessageBox.warning(
                    self, "不是旧 .json 格式",
                    f"这个文件不是旧版项目 .json:\n{path}")
                return
            # 自动升级到同名文件夹
            json_p = Path(path)
            target = json_p.parent / json_p.stem
            if target.exists() and target.is_dir():
                target = json_p.parent / (json_p.stem + "_migrated")
            ret = QMessageBox.question(
                self, "升级旧项目?",
                f"将把旧 .json 升级为文件夹结构:\n  {target}\n\n"
                f"原 .json 会保留为 .legacy-original.json 作为备份。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ret != QMessageBox.Yes:
                return
            project_io.migrate_legacy_json(json_p, target)
            d = project_io.load_project_folder(target)
            self.current_project_file = str(target.resolve())
            self._load_payload_into_ui(d)
            self._push_to_recent(self.current_project_file)
            try:
                from PyQt5.QtCore import QSettings
                QSettings("NovelAI", "UI").setValue(
                    "last_project_path", self.current_project_file)
            except Exception:
                pass
            QMessageBox.information(
                self, "✓ 升级完成",
                f"已升级到文件夹结构:\n{target}")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"加载旧 .json 失败:\n{e}")

    def _push_to_recent(self, path):
        """把项目路径推到最近项目列表头部(去重,保留最近 10 个)"""
        if not path:
            return
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "UI")
        recent = s.value("recent_projects", [], type=list) or []
        # 去重
        recent = [p for p in recent if p != path]
        recent.insert(0, path)
        recent = recent[:10]
        s.setValue("recent_projects", recent)
        self._refresh_recent_menu()
        if hasattr(self, "tab_home"):
            self.tab_home.refresh_recent_list()

    def _remove_from_recent(self, path):
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "UI")
        recent = s.value("recent_projects", [], type=list) or []
        recent = [p for p in recent if p != path]
        s.setValue("recent_projects", recent)

    def _clear_recent_projects(self):
        from PyQt5.QtWidgets import QMessageBox
        if QMessageBox.question(
            self, "清空最近项目?",
            "确定清空最近项目列表吗?(不会删除项目文件)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        from PyQt5.QtCore import QSettings
        QSettings("NovelAI", "UI").setValue("recent_projects", [])
        self._refresh_recent_menu()
        if hasattr(self, "tab_home"):
            self.tab_home.refresh_recent_list()

    def _setup_view_menu(self):
        """v1.21:加 视图 菜单 + Ctrl+Shift+D 快捷键,作为 corner widget 按钮的兜底入口"""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        # 1. 主菜单栏加 视图(V) → 🌙 切换黑夜/白天
        menubar = self.menuBar()
        view_menu = menubar.addMenu("视图(&V)")
        toggle_action = view_menu.addAction("🌙 切换 白天 / 黑夜 主题")
        toggle_action.setShortcut("Ctrl+Shift+D")
        toggle_action.triggered.connect(self._on_toggle_theme)
        # 2. 全局快捷键 Ctrl+Shift+D(即使菜单被某些情况隐藏也能用)
        sc = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        sc.activated.connect(self._on_toggle_theme)
        print("[Theme] 视图菜单 + Ctrl+Shift+D 快捷键已注册", flush=True)

    def _on_toggle_theme(self):
        """循环切换主题"""
        themes = list(ThemeManager.THEMES.keys())
        cur = ThemeManager.current()
        idx = themes.index(cur) if cur in themes else 0
        new_name = themes[(idx + 1) % len(themes)]
        self._apply_theme(new_name)

    def _show_theme_menu(self):
        """右键选择主题"""
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        cur = ThemeManager.current()
        for key, theme in ThemeManager.THEMES.items():
            label = theme.get("label", key)
            act = menu.addAction(f"{'✓ ' if key == cur else '   '}{label}")
            act.triggered.connect(lambda checked, k=key: self._apply_theme(k))
        menu.exec_(self.btn_theme_toggle.mapToGlobal(
            self.btn_theme_toggle.rect().bottomLeft()))

    def _apply_theme(self, name):
        """应用指定主题 — 保留字体大小,显示切换进度"""
        from PyQt5.QtWidgets import QApplication
        import re as _re
        app = QApplication.instance()
        if app is None:
            return

        # 保存当前字体(切换后恢复)
        saved_font = app.font()

        # 状态提示
        self.statusBar().showMessage("🎨 正在切换主题...", 3000)
        app.processEvents()

        ThemeManager.apply(app, name)

        # 智能清除:只清颜色相关属性,完全跳过只有font的控件
        _accent_colors = {"#e65100", "#1a73e8", "#27ae60", "#8e44ad",
                          "#e67e22", "#3498db", "#2ecc71", "#cc3333",
                          "#e74c3c", "#0f3460", "#1557b0", "#bf360c",
                          "#c0392b", "#d35400", "#2980b9", "#6c3483",
                          "#5d6d7e", "#b8860b", "#ffd700"}
        children = self.findChildren(QWidget)
        for i, w in enumerate(children):
            ss = w.styleSheet()
            if not ss:
                continue
            if any(c in ss.lower() for c in _accent_colors):
                continue
            if hasattr(self, 'tab_debug') and w is getattr(self.tab_debug, 'log_edit', None):
                continue
            # 只有颜色没有字体 → 直接清空
            has_color = bool(_re.search(r'(?:background|color)\s*:', ss))
            has_font = bool(_re.search(r'font', ss))
            if not has_color:
                continue  # 没有颜色属性,不需要清
            if has_font:
                # 有字体+有颜色:只保留font行
                font_lines = _re.findall(r'[^;{]*font[^;]*;', ss)
                w.setStyleSheet(" ".join(font_lines))
            else:
                w.setStyleSheet("")

        qss = ThemeManager.THEMES.get(name, {}).get("qss", "")
        self.setStyleSheet(qss)

        # 恢复字体(防止主题QSS改变字体大小)
        app.setFont(saved_font)

        # 快速刷新(不逐个polish,减少卡顿)
        app.processEvents()
        self.update()

        try:
            self.tab_editor._apply_editor_colors()
        except Exception:
            pass

        label = ThemeManager.THEMES.get(name, {}).get("label", name)
        icon = ThemeManager.THEMES.get(name, {}).get("icon", "🎨")
        self.btn_theme_toggle.setText(f"{icon} 主题切换")
        self.tab_generation.log(f"🎨 主题 → {label}", "info")

    def _init_tts(self):
        """启动时初始化 TTS:QMediaPlayer + 状态"""
        try:
            from PyQt5.QtMultimedia import QMediaPlayer
            self._tts_player = QMediaPlayer(self)
            self._tts_player.mediaStatusChanged.connect(self._on_tts_player_status)
        except Exception as e:
            print(f"[TTS] QMediaPlayer 初始化失败: {e}", flush=True)
            self._tts_player = None
        self._tts_queue = []         # 待播放音频文件路径
        self._tts_chunks_total = 0
        self._tts_chunks_done = 0
        self._tts_worker = None
        self._tts_speed = 1.0
        self._tts_temp_dir = None
        self._tts_auto_queue = []    # 自动朗读队列: [(ch_num, text), ...]
        self._tts_auto_playing = False

    def _tts_backend_config(self):
        """读取当前 TTS 配置 → (backend_name, kwargs, voice_or_ref)"""
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "TTS")
        backend = s.value("backend", "edge_tts", type=str)
        if backend == "index_tts":
            url = s.value("index_url", "http://127.0.0.1:7862/", type=str)
            ref = s.value("index_ref_audio", "", type=str)
            api_name = s.value("index_api_name", "", type=str) or None
            return "index_tts", {"url": url, "ref_audio": ref, "api_name": api_name}, ref
        if backend == "edge_tts":
            voice = s.value("edge_voice", "zh-CN-XiaoxiaoNeural", type=str)
            return "edge_tts", {}, voice
        return "disabled", {}, None

    def _on_tts_play(self):
        """开始朗读当前章节"""
        # 取当前章节文本
        text = ""
        try:
            text = self.tab_editor.content_edit.toPlainText().strip()
        except Exception:
            pass
        if not text:
            QMessageBox.information(self, "TTS", "当前章节为空,无东西可读")
            return
        # 已在播放 → 暂停/继续
        if self._tts_worker is not None and self._tts_worker.isRunning():
            self._on_tts_pause()
            return
        # 配置
        backend_name, kwargs, voice = self._tts_backend_config()
        if backend_name == "disabled":
            QMessageBox.information(
                self, "TTS",
                "TTS 已关闭。\n请在 创作设置 → 🔊 TTS 朗读 里选一个后端(EdgeTTS 或 Index-TTS)。")
            return
        try:
            import tts_backend as _tb
        except ImportError as e:
            QMessageBox.warning(self, "TTS",
                f"tts_backend.py 加载失败:{e}")
            return
        backend = _tb.get_backend(backend_name, **kwargs)
        if not backend.is_available():
            tip_install = (
                "pip install edge-tts" if backend_name == "edge_tts"
                else "pip install gradio_client")
            QMessageBox.warning(
                self, f"TTS({backend.display})不可用",
                f"后端 {backend.name} 当前不可用。\n\n"
                f"修复办法:在命令行运行  {tip_install}\n"
                f"然后重启程序。")
            return
        # 切段
        chunks = _tb.split_text_for_tts(text, max_chars=300)
        if not chunks:
            return
        # 准备 temp 目录
        import tempfile
        if self._tts_temp_dir is None or not Path(self._tts_temp_dir).exists():
            self._tts_temp_dir = tempfile.mkdtemp(prefix="novelai_tts_")
        # 启动后台 worker
        self._tts_queue.clear()
        self._tts_chunks_total = len(chunks)
        self._tts_chunks_done = 0
        self.tab_editor.btn_tts_play.setText("⏸ 暂停")
        self.tab_editor.btn_tts_stop.setEnabled(True)
        self.tab_editor.lbl_tts_status.setText(f"合成中 0/{len(chunks)}")
        self.tab_generation.log(
            f"🔊 TTS 启动:{backend.display},章节 {len(text)} 字 → {len(chunks)} 段",
            "info")
        self._tts_worker = _TTSSynthThread(
            backend=backend, chunks=chunks, voice=voice,
            speed=self._tts_speed, temp_dir=self._tts_temp_dir, parent=self)
        self._tts_worker.chunk_ready.connect(self._on_tts_chunk_ready)
        self._tts_worker.chunk_failed.connect(self._on_tts_chunk_failed)
        self._tts_worker.finished_all.connect(self._on_tts_synth_done)
        self._tts_worker.start()

    def _on_tts_chunk_ready(self, idx, total, audio_path):
        """一段合成好了 → 进队列"""
        self._tts_chunks_done = max(self._tts_chunks_done, idx + 1)
        self.tab_editor.lbl_tts_status.setText(f"合成中 {self._tts_chunks_done}/{total}")
        self._tts_queue.append(audio_path)
        # 如果播放器空闲,启动播放(必须检查所有后端)
        if not self._is_tts_playing():
            self._play_next_chunk()

    def _is_tts_playing(self):
        """检查当前是否有音频在播放(兼容 pygame / winsound / QMediaPlayer)"""
        # pygame 优先检查
        if getattr(self, "_tts_currently_pygame", False):
            try:
                import pygame
                if pygame.mixer.music.get_busy():
                    return True
            except Exception:
                pass
        # winsound 无法检测,用 flag
        if getattr(self, "_tts_currently_winsound", False):
            return True
        # QMediaPlayer
        try:
            from PyQt5.QtMultimedia import QMediaPlayer
            if self._tts_player is not None and self._tts_player.state() == QMediaPlayer.PlayingState:
                return True
        except Exception:
            pass
        return False

    def _on_tts_chunk_failed(self, idx, total, err):
        self.tab_generation.log(
            f"⚠ TTS 第 {idx+1}/{total} 段合成失败:{err}", "warn")

    def _on_tts_synth_done(self):
        self.tab_generation.log("🔊 TTS 全部段落合成完成,继续播放剩余队列", "info")

    def _play_next_chunk(self):
        """v1.16:pygame 优先 → winsound → QMediaPlayer。
        pygame 有 get_busy() 可轮询,winsound 没'播完信号'用 wave duration 调度。"""
        if not self._tts_queue:
            return
        path = self._tts_queue.pop(0)
        import sys, os
        ext = os.path.splitext(path)[1].lower()

        # 路径 0:pygame.mixer — SDL2 后端,最稳
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            self._tts_currently_winsound = False
            self._tts_currently_pygame = True
            # 用 QTimer 轮询 pygame.mixer.music.get_busy()
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(200, self._pygame_check_done)
            return
        except ImportError:
            pass
        except Exception as _e:
            self.tab_generation.log(f"⚠ pygame 播放失败({_e}),退到 winsound", "warn")

        # 路径 1:Windows + WAV → winsound
        if sys.platform == "win32" and ext == ".wav":
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                self._tts_currently_winsound = True
                # 算 duration → 安排下一段
                duration_ms = self._get_wav_duration_ms(path)
                # 不要紧贴着调度,留 80ms 让 SND_ASYNC 真启动 + 收尾衔接
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(
                    max(200, duration_ms + 80),
                    self._on_winsound_chunk_done)
                return
            except Exception as e:
                self.tab_generation.log(
                    f"⚠ winsound 播放失败({e}),退回 QMediaPlayer", "warn")
        # 路径 2:QMediaPlayer
        try:
            from PyQt5.QtCore import QUrl
            from PyQt5.QtMultimedia import QMediaContent
            if self._tts_player is None:
                return
            self._tts_currently_winsound = False
            self._tts_player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self._tts_player.play()
        except Exception as e:
            self.tab_generation.log(f"⚠ TTS 播放失败:{e}", "warn")

    def _pygame_check_done(self):
        """v1.16:轮询 pygame.mixer 是否播完,完了接下一段"""
        try:
            import pygame
            if pygame.mixer.music.get_busy():
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(200, self._pygame_check_done)
                return
        except Exception:
            pass
        # 播完了
        self._tts_currently_pygame = False
        if self._tts_queue:
            self._play_next_chunk()
            return
        if self._tts_worker is not None and self._tts_worker.isRunning():
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(1000, self._pygame_check_done)
            return
        # 全完
        self.tab_editor.btn_tts_play.setText("🔊 朗读本章")
        self.tab_editor.btn_tts_stop.setEnabled(False)
        self.tab_editor.lbl_tts_status.setText("✓ 播放完成")
        # 自动朗读队列:播下一章
        if self._tts_auto_queue:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(500, self._tts_auto_play_next)
        else:
            self._tts_auto_playing = False

    def _get_wav_duration_ms(self, path):
        """读 WAV header 算时长(毫秒)。失败时给个保守默认 5 秒。"""
        try:
            import wave
            with wave.open(path, "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                if rate > 0:
                    return int(frames * 1000 / rate)
        except Exception:
            pass
        return 5000

    def _on_winsound_chunk_done(self):
        """winsound 一段播完(由 QTimer 触发)— 接下一段或者收尾"""
        # 如果队列还有,继续播
        if self._tts_queue:
            self._play_next_chunk()
            return
        # 队列空了 → 检查合成线程是否还在跑(还在跑的话继续等)
        if self._tts_worker is not None and self._tts_worker.isRunning():
            # 1 秒后再检查
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(1000, self._on_winsound_chunk_done)
            return
        # 全完了
        self.tab_editor.btn_tts_play.setText("🔊 朗读本章")
        self.tab_editor.btn_tts_stop.setEnabled(False)
        self.tab_editor.lbl_tts_status.setText("✓ 播放完成")

    def _on_tts_player_status(self, status):
        """QMediaPlayer 状态变化 — 一段播完了自动播下一段"""
        try:
            from PyQt5.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.EndOfMedia:
                if self._tts_queue:
                    self._play_next_chunk()
                elif (self._tts_worker is None or not self._tts_worker.isRunning()):
                    # 本章全部播完
                    self.tab_editor.btn_tts_play.setText("🔊 朗读本章")
                    self.tab_editor.btn_tts_stop.setEnabled(False)
                    self.tab_editor.lbl_tts_status.setText("✓ 播放完成")
                    # 自动朗读队列:播下一章
                    if self._tts_auto_queue:
                        from PyQt5.QtCore import QTimer
                        QTimer.singleShot(500, self._tts_auto_play_next)
                    else:
                        self._tts_auto_playing = False
        except Exception:
            pass

    def _on_tts_pause(self):
        """暂停 / 继续。pygame 真暂停;winsound 不支持;QMediaPlayer 标准 pause/play"""
        # pygame 真暂停
        if getattr(self, "_tts_currently_pygame", False):
            try:
                import pygame
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.pause()
                    self.tab_editor.btn_tts_play.setText("▶ 继续")
                else:
                    pygame.mixer.music.unpause()
                    self.tab_editor.btn_tts_play.setText("⏸ 暂停")
            except Exception:
                pass
            return
        if getattr(self, "_tts_currently_winsound", False):
            self.tab_generation.log(
                "ℹ winsound 不支持真暂停,只能停。要继续请重点 🔊 朗读本章", "info")
            return
        try:
            from PyQt5.QtMultimedia import QMediaPlayer
            if self._tts_player is None:
                return
            st = self._tts_player.state()
            if st == QMediaPlayer.PlayingState:
                self._tts_player.pause()
                self.tab_editor.btn_tts_play.setText("▶ 继续")
            else:
                self._tts_player.play()
                self.tab_editor.btn_tts_play.setText("⏸ 暂停")
        except Exception:
            pass

    def _on_tts_stop(self):
        """停止播放 + 清队列 + 终止合成"""
        # 停 pygame
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        # 停 winsound(如果正在用)
        try:
            import sys
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        try:
            if self._tts_player is not None:
                self._tts_player.stop()
        except Exception:
            pass
        self._tts_queue.clear()
        if self._tts_worker is not None:
            try:
                self._tts_worker.requestInterruption()
            except Exception:
                pass
        self.tab_editor.btn_tts_play.setText("🔊 朗读本章")
        self.tab_editor.btn_tts_stop.setEnabled(False)
        self.tab_editor.lbl_tts_status.setText("已停止")
        self._tts_auto_queue.clear()
        self._tts_auto_playing = False
        self.tab_generation.log("🔊 TTS 已停止", "info")

    # ── 自动朗读队列(批量生成时按顺序读) ──

    def _tts_auto_enqueue(self, ch_num, text):
        """将章节加入自动朗读队列"""
        if not text or not text.strip():
            return
        self._tts_auto_queue.append((ch_num, text.strip()))
        self.tab_generation.log(
            f"🔊 第{ch_num}章已加入朗读队列(队列{len(self._tts_auto_queue)}章)",
            "info")
        if not self._tts_auto_playing:
            self._tts_auto_play_next()

    def _tts_auto_play_next(self):
        """从自动队列取下一章开始朗读"""
        if not self._tts_auto_queue:
            self._tts_auto_playing = False
            self.tab_generation.log("🔊 自动朗读队列播放完毕", "info")
            return
        ch_num, text = self._tts_auto_queue.pop(0)
        self._tts_auto_playing = True
        self.tab_generation.log(
            f"🔊 自动朗读第{ch_num}章({len(text)}字)", "info")
        self._tts_play_text(text)

    def _tts_play_text(self, text):
        """直接朗读指定文本(不依赖编辑器当前内容)"""
        backend_name, kwargs, voice = self._tts_backend_config()
        if backend_name == "disabled":
            self._tts_auto_queue.clear()
            self._tts_auto_playing = False
            return
        try:
            import tts_backend as _tb
        except ImportError:
            self._tts_auto_playing = False
            return
        backend = _tb.get_backend(backend_name, **kwargs)
        if not backend.is_available():
            self._tts_auto_playing = False
            return
        chunks = _tb.split_text_for_tts(text, max_chars=300)
        if not chunks:
            # 空文本,跳到下一章
            if self._tts_auto_queue:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(100, self._tts_auto_play_next)
            else:
                self._tts_auto_playing = False
            return
        import tempfile
        if self._tts_temp_dir is None or not Path(self._tts_temp_dir).exists():
            self._tts_temp_dir = tempfile.mkdtemp(prefix="novelai_tts_")
        self._tts_queue.clear()
        self._tts_chunks_total = len(chunks)
        self._tts_chunks_done = 0
        self.tab_editor.btn_tts_play.setText("⏸ 暂停")
        self.tab_editor.btn_tts_stop.setEnabled(True)
        from ui.threads import _TTSSynthThread
        self._tts_worker = _TTSSynthThread(
            backend, chunks, self._tts_temp_dir, self._tts_speed, voice)
        self._tts_worker.chunk_ready.connect(self._on_tts_chunk_ready)
        self._tts_worker.all_done.connect(self._on_tts_all_done)
        self._tts_worker.error.connect(self._on_tts_error)
        self._tts_worker.start()

    def _on_tts_speed_changed(self, speed):
        """速度滑块调整 — 只影响下一次合成,当前已合成的段保持原速"""
        self._tts_speed = float(speed)

    def gen_inspiration(self):
        genres = self.tab_settings.get_selected_genres()
        if not genres:
            QMessageBox.warning(self, "提示", "请至少选一个题材"); return
        platform = self.tab_settings.get_platform()
        # v2.23.1: 三层灵感增强(优先全榜 → 单榜 → 通用)
        # 1. 番茄 + 浏览器就绪 → 优先用 v2.23.1 全榜扫描(74 榜矩阵)
        # 2. 全榜失败 / 不可用 → fallback 到 v2.23.0 单榜扫描
        # 3. 单榜也失败 → fallback 到旧通用 prompt
        # 全榜缓存命中(24h)直接复用,不再扫
        if platform == "番茄小说" and self.worker.is_ready():
            if self._gen_inspiration_try_v231_full_scrape(genres, platform):
                return
            if self._gen_inspiration_try_scrape(genres, platform):
                return
        self._gen_inspiration_send_fallback(genres, platform)

    def _gen_inspiration_try_v231_full_scrape(self, genres, platform):
        """
        v2.23.1: 尝试全榜扫描(74 榜矩阵)

        返回 True 表示已触发扫榜任务 / 缓存命中已发 AI;False 表示不可用,让上层 fallback。
        """
        try:
            from core.fanqie_rank_scraper import (
                build_v231_full_rank_prompt, V231_CACHE_TTL_SEC)
        except Exception as e:
            self.tab_generation.log(
                f"⚠ v2.23.1 全榜模块导入失败:{e},尝试 v2.23.0 单榜", "warn")
            return False

        # v2.23.1 stats 缓存(挂 self 上)
        if not hasattr(self, "_v231_rank_stats_cache"):
            self._v231_rank_stats_cache = {"stats": None, "scraped_at": 0.0}

        import time as _time
        cache_entry = self._v231_rank_stats_cache
        age = _time.time() - cache_entry.get("scraped_at", 0)
        if cache_entry.get("stats") and age < V231_CACHE_TTL_SEC:
            stats = cache_entry["stats"]
            self.tab_generation.log(
                f"💡 v2.23.1 全榜缓存命中({stats.get('total_books', 0)} 本,"
                f"{int(age // 60)} 分钟前扫的),直接用", "info")
            self._gen_inspiration_send_with_v231_stats(stats, genres, platform)
            return True

        self.tab_generation.log(
            f"💡 v2.23.1 准备扫描番茄全榜(74 个榜单 × Top10,预计 2-3 分钟)...", "info")

        self._pending_v231_inspiration_ctx = {
            "genres": list(genres),
            "platform": platform,
        }

        self.worker.reset_scan_cancel()
        self._show_v231_scan_progress_dialog()
        self._fanqie_scanning = True  # v2.23.4: 锁
        self.worker.submit({
            "action": "scrape_fanqie_all_ranks",
            "task_id": "fanqie_all_ranks_scrape",
        })
        return True

    def _show_v231_scan_progress_dialog(self):
        """
        v2.23.1: 弹一个非模态进度对话框,显示当前扫描进度

        包含:进度条(0-74)/ 当前榜单标签 + 抓到多少本 /
        "用部分数据生成"按钮 → 调 worker.cancel_scan() 提前结束 /
        "取消"按钮 → 调 worker.cancel_scan() + 设标志让回调走 fallback
        """
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel,
                                      QProgressBar, QPushButton, QHBoxLayout)

        dlg = QDialog(self)
        dlg.setWindowTitle("番茄全榜扫描中")
        dlg.resize(440, 180)
        dlg.setModal(False)

        v = QVBoxLayout(dlg)
        title = QLabel("正在扫描番茄小说全部 74 个分类榜单...")
        v.addWidget(title)

        bar = QProgressBar()
        bar.setRange(0, 74)
        bar.setValue(0)
        v.addWidget(bar)

        status = QLabel("准备开始...")
        status.setWordWrap(True)
        v.addWidget(status)

        hint = QLabel("提示:全部扫完需 2-3 分钟。点'用部分数据生成'可提前结束。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        v.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_partial = QPushButton("用部分数据生成")
        btn_cancel = QPushButton("取消")
        btn_row.addWidget(btn_partial)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        v.addLayout(btn_row)

        def on_partial():
            self.worker.cancel_scan()
            self.tab_generation.log("💡 用户选择用部分数据生成", "info")
            btn_partial.setEnabled(False)
            btn_partial.setText("提前结束中...")

        def on_cancel():
            self.worker.cancel_scan()
            self._v231_scan_cancelled_full = True
            self.tab_generation.log("💡 用户取消了全榜扫描", "info")
            dlg.close()

        btn_partial.clicked.connect(on_partial)
        btn_cancel.clicked.connect(on_cancel)

        self._v231_scan_dialog = dlg
        self._v231_scan_dialog_widgets = {
            "bar": bar, "status": status,
            "btn_partial": btn_partial, "btn_cancel": btn_cancel,
        }
        self._v231_scan_cancelled_full = False
        dlg.show()

    def _on_v231_rank_progress(self, task_id, cur, total, label, n_books):
        """v2.23.1: worker emit rank_progress 时更新对话框"""
        if task_id != "fanqie_all_ranks_scrape":
            return
        dlg = getattr(self, "_v231_scan_dialog", None)
        if not dlg or not dlg.isVisible():
            return
        widgets = getattr(self, "_v231_scan_dialog_widgets", {})
        bar = widgets.get("bar")
        status = widgets.get("status")
        if bar:
            bar.setValue(cur)
        if status:
            status.setText(f"扫描 {cur}/{total}:{label} → 抓到 {n_books} 本")

    def _on_v231_all_ranks_scraped(self, task_id, stats):
        """
        v2.23.1: worker 全榜扫完回调

        - stats 为空 / total_books=0 → fallback 到 v2.23.0 单榜 / 通用
        - stats 正常 → 缓存 + 拼 prompt 发 AI
        - 用户取消(_v231_scan_cancelled_full=True)→ 走通用 fallback
        """
        if task_id != "fanqie_all_ranks_scrape":
            return

        self._fanqie_scanning = False  # v2.23.4: 解锁

        dlg = getattr(self, "_v231_scan_dialog", None)
        if dlg:
            try:
                dlg.close()
            except Exception:
                pass
        self._v231_scan_dialog = None

        ctx = getattr(self, "_pending_v231_inspiration_ctx", None)
        # v2.23.3: ctx 为 None = 后台自动扫(_v233_bg_auto_scrape),不发 AI 但保存数据
        is_bg_mode = ctx is None
        self._pending_v231_inspiration_ctx = None
        genres = ctx.get("genres", []) if ctx else []
        platform = ctx.get("platform", "番茄小说") if ctx else "番茄小说"

        if getattr(self, "_v231_scan_cancelled_full", False):
            self._v231_scan_cancelled_full = False
            if not is_bg_mode:
                self.tab_generation.log("💡 全榜扫描取消,fallback 通用 prompt", "warn")
                self._gen_inspiration_send_fallback(genres, platform)
            return

        if not stats or stats.get("total_books", 0) == 0:
            if is_bg_mode:
                self.tab_generation.log(
                    "⚠ v2.23.3 后台扫榜结果为空,跳过", "warn")
                return
            self.tab_generation.log(
                "⚠ v2.23.1 全榜扫描结果为空,fallback 到 v2.23.0 单榜", "warn")
            if self._gen_inspiration_try_scrape(genres, platform):
                return
            self._gen_inspiration_send_fallback(genres, platform)
            return

        # 扫成功,缓存
        import time as _time
        self._v231_rank_stats_cache = {
            "stats": stats,
            "scraped_at": _time.time(),
        }

        # v2.23.3: 保存扫榜快照到磁盘 + 触发后台详情抓取
        scraped_raw = stats.get("_scraped_raw", [])
        self._v233_save_snapshot_and_trigger_details(stats, scraped_raw)

        # v2.23.3: 后台模式只保存数据,不发 AI
        if is_bg_mode:
            self.tab_generation.log(
                f"📚 v2.23.3 后台扫榜完成:{stats.get('total_books', 0)} 本 "
                f"(去重 {stats.get('unique_books', 0)} 本)→ 详情抓取已自动启动",
                "info")
            return

        self.tab_generation.log(
            f"💡 v2.23.1 全榜扫描成功:{stats.get('total_books', 0)} 本 "
            f"(去重 {stats.get('unique_books', 0)} 本) → 拼增强 prompt", "info")
        self._gen_inspiration_send_with_v231_stats(stats, genres, platform)

    def _gen_inspiration_send_with_v231_stats(self, stats, genres, platform):
        """v2.23.1: 用 stats 拼 prompt 发 AI。v2.23.3 升级:有详情数据就加进 prompt"""
        # v2.23.3: 优先用增强 prompt(含详情爆款样本)
        try:
            from core.fanqie_rank_scraper import build_v233_enriched_prompt
            base_prompt = PROMPTS["creative_inspiration"].format(
                genre="/".join(genres), platform=platform)
            project_root = self._v233_get_project_root()
            prompt = build_v233_enriched_prompt(
                stats, genres, project_root, base_prompt)
            if prompt:
                self._send_to_ai(prompt, "创意灵感", target="inspiration")
                return
        except Exception:
            pass

        # Fallback 到 v2.23.1 纯统计 prompt
        try:
            from core.fanqie_rank_scraper import build_v231_full_rank_prompt
        except Exception:
            self._gen_inspiration_send_fallback(genres, platform)
            return
        base_prompt = PROMPTS["creative_inspiration"].format(
            genre="/".join(genres), platform=platform)
        prompt = build_v231_full_rank_prompt(stats, genres, base_prompt)
        if not prompt:
            self._gen_inspiration_send_fallback(genres, platform)
            return
        self._send_to_ai(prompt, "创意灵感", target="inspiration")

    # ===========================================================
    # v2.23.3: 详情抓取相关方法
    # ===========================================================

    def _v233_get_project_root(self):
        """
        v2.23.3: 返回当前项目根目录(.fanqie_cache 放在这里)

        优先用 self.current_project 路径,fallback 到 cwd
        """
        try:
            proj = getattr(self, "current_project", None)
            if proj and getattr(proj, "path", None):
                return str(proj.path)
        except Exception:
            pass
        try:
            proj_dir = getattr(self, "project_dir", None)
            if proj_dir:
                return str(proj_dir)
        except Exception:
            pass
        import os
        return os.getcwd()

    def _v233_save_snapshot_and_trigger_details(self, stats, scraped_raw):
        """
        v2.23.3: 扫完榜后:
          1. 保存快照到磁盘
          2. 写一次 INDEX.md
          3. 提取 Top5 book_id 列表,提交后台详情抓取任务
        """
        if not stats or not scraped_raw:
            return
        try:
            from core.fanqie_rank_scraper import (
                save_rank_snapshot, write_index_md,
                get_t5_book_ids_from_scraped, ensure_cache_dirs,
                list_cached_book_ids,
            )
        except Exception as e:
            self.tab_generation.log(f"⚠ v2.23.3 模块导入失败:{e}", "warn")
            return

        project_root = self._v233_get_project_root()
        try:
            ensure_cache_dirs(project_root)
            save_rank_snapshot(project_root, scraped_raw, stats)
        except Exception:
            pass

        # 提取 Top5 × 74 = 370 个 book_id(去重后约 200-300)
        book_ids = get_t5_book_ids_from_scraped(scraped_raw)
        # 排除已缓存的(7 天 TTL 内的复用)
        cached = list_cached_book_ids(project_root)
        pending = [(bid, lbl, cat) for (bid, lbl, cat) in book_ids
                    if bid not in cached]

        # 写初始 INDEX.md
        try:
            write_index_md(project_root, stats, scraped_raw,
                            (len(cached), len(book_ids)))
        except Exception:
            pass

        if not pending:
            self.tab_generation.log(
                f"📚 v2.23.3 详情已全在缓存({len(cached)} 本),不需要抓", "info")
            return

        self.tab_generation.log(
            f"📚 v2.23.3 启动后台详情抓取:待抓 {len(pending)} 本"
            f"(已缓存 {len(cached)} 本)→ 缓存目录 {project_root}/.fanqie_cache/",
            "info")

        # 提交后台抓取任务(worker 会自行礼让 AI 任务)
        self.worker.submit({
            "action": "scrape_book_details_batch",
            "task_id": "fanqie_detail_batch",
            "book_ids": pending,
            "project_root": project_root,
            "stats": stats,
        })

    def _v233_bg_auto_scrape(self, force=False):
        """
        v2.23.3: 程序启动 30 秒后自动触发(QTimer.singleShot 30s 调过来)

        force=True: 用户手动触发,跳过自动扫榜开关检查
        """
        try:
            # v2.23.4: 防重复扫榜锁
            if getattr(self, "_fanqie_scanning", False):
                self.tab_generation.log(
                    "📚 已有扫榜任务在跑,跳过重复触发", "info")
                return

            # v2.23.4: 用户关闭了自动扫榜(手动触发不受影响)
            if not force:
                try:
                    from ui.fanqie_rank_tab import FanqieRankTab
                    if not FanqieRankTab.is_auto_scan_enabled():
                        return
                except Exception:
                    pass

            if not self.worker.is_ready():
                self.tab_generation.log(
                    "📚 v2.23.3 启动 30s 后台抓取:浏览器未就绪,跳过", "info")
                return
            # 浏览器忙(用户已在生成章节)→ 跳过这次
            if self.worker.task_queue.qsize() > 0:
                self.tab_generation.log(
                    "📚 v2.23.3 后台抓取:浏览器有任务排队,本次跳过", "info")
                return

            # 检查 v2.23.1 stats 缓存
            from core.fanqie_rank_scraper import V231_CACHE_TTL_SEC
            import time as _time
            cache = getattr(self, "_v231_rank_stats_cache", None)
            age = _time.time() - (cache.get("scraped_at", 0) if cache else 0)
            if cache and cache.get("stats") and age < V231_CACHE_TTL_SEC:
                # 缓存还在,只需要检查详情有没有抓
                self.tab_generation.log(
                    f"📚 v2.23.3 v2.23.1 缓存命中(扫过 {int(age//60)} 分钟前),"
                    f"只补抓详情", "info")
                stats = cache["stats"]
                scraped = stats.get("_scraped_raw", [])
                self._v233_save_snapshot_and_trigger_details(stats, scraped)
                return

            # 没缓存,后台静默扫(不弹进度对话框)
            self.tab_generation.log(
                "📚 v2.23.3 启动 30s 自动后台扫榜:74 榜 × Top10", "info")
            self._pending_v231_inspiration_ctx = None  # 后台模式不发 AI
            self.worker.reset_scan_cancel()
            self._v231_scan_dialog = None
            self._v231_scan_cancelled_full = False
            self._fanqie_scanning = True  # v2.23.4: 锁
            self.worker.submit({
                "action": "scrape_fanqie_all_ranks",
                "task_id": "fanqie_all_ranks_scrape",
            })
        except Exception as e:
            try:
                self.tab_generation.log(
                    f"⚠ v2.23.3 后台启动抓取失败:{e}", "warn")
            except Exception:
                pass

    def _on_v233_detail_progress(self, task_id, cur, total, book_id):
        """v2.23.3: 详情抓取进度(每抓完 1 本)— 静默,只在每 10 本打日志"""
        # 每 20 本打一次,worker 已经每 10 打了,这里更稀疏
        if cur % 20 == 0:
            try:
                self.tab_generation.log(
                    f"📚 v2.23.3 详情后台 {cur}/{total}", "info")
            except Exception:
                pass

    def _on_v233_detail_batch_done(self, task_id, success, fail):
        """v2.23.3: 详情批抓完成"""
        try:
            self.tab_generation.log(
                f"📚 v2.23.3 详情抓取批次完成:成功 {success} / 失败 {fail}。"
                f"下一次点'生成灵感'就会用上这些样本。", "info")
        except Exception:
            pass

    # ─── v2.23.4: 番茄榜单 Tab 转发方法 ───

    def _fanqie_tab_on_rank_progress(self, task_id, cur, total, label, n_books):
        """转发扫榜进度到 Tab"""
        try:
            self.tab_fanqie_rank.update_scan_progress(cur, total, label, n_books)
            self.tab_fanqie_rank.btn_rescan.setEnabled(False)
            self.tab_fanqie_rank.btn_rescan.setText("扫描中...")
        except Exception:
            pass

    def _fanqie_tab_on_rank_done(self, task_id, stats):
        """扫榜完成 → 更新 Tab 热度表"""
        try:
            import time as _t
            self.tab_fanqie_rank.update_stats(stats, _t.time())
            self.tab_fanqie_rank.load_details_from_disk()
            self.tab_fanqie_rank.btn_rescan.setEnabled(True)
            self.tab_fanqie_rank.btn_rescan.setText("🔄 刷新扫榜")
        except Exception:
            pass

    def _fanqie_tab_on_detail_progress(self, task_id, cur, total, book_id):
        """转发详情进度到 Tab"""
        try:
            self.tab_fanqie_rank.update_detail_progress(cur, total, book_id)
        except Exception:
            pass

    def _fanqie_tab_on_detail_done(self, task_id, success, fail):
        """详情完成 → 刷新 Tab 详情表"""
        try:
            self.tab_fanqie_rank.on_detail_batch_done(success, fail)
        except Exception:
            pass

    def _on_fanqie_rank_rescan(self):
        """用户在番茄榜单 Tab 点了'刷新扫榜'"""
        try:
            # v2.23.4: 防重复
            if getattr(self, "_fanqie_scanning", False):
                self.tab_generation.log(
                    "📊 已有扫榜任务在跑,等完成后再刷新", "info")
                return
            self.tab_generation.log(
                "📊 用户手动触发番茄全榜刷新扫描...", "info")
            # 手动触发时清掉 24h 缓存(强制重扫)
            self._v231_rank_stats_cache = {"stats": None, "scraped_at": 0.0}
            self._v233_bg_auto_scrape(force=True)  # 手动触发,跳过自动开关检查
        except Exception as e:
            self.tab_generation.log(
                f"⚠ 手动扫榜触发失败:{e}", "warn")

    def _sync_fanqie_rank_tab(self):
        """
        v2.23.4: 项目打开后同步番茄榜单 Tab

        1. 设置项目根目录(让 Tab 知道磁盘缓存在哪)
        2. 从磁盘加载上次扫榜快照(热度表立刻有数据)
        3. 从磁盘加载已有详情(详情表立刻有数据)
        """
        try:
            tab = getattr(self, "tab_fanqie_rank", None)
            if not tab:
                return
            root = self._v233_get_project_root()
            if root:
                tab.set_project_root(root)
                tab.load_snapshot_from_disk()
                tab.load_details_from_disk()
        except Exception:
            pass

    def _on_ai_toolbox_modify(self, ch_idx, prompt):
        """
        v2.23.4: AI 工具箱请求修改章节

        ch_idx: 章节索引
        prompt: 完整 prompt(含原文 + 指令)
        """
        try:
            self.tab_generation.log(
                f"🛠 AI 工具箱:发送第 {ch_idx+1} 章到 AI 修改...", "info")
            # 用 _send_to_ai 发送,target 设为 "ai_toolbox" 以便回调区分
            self._send_to_ai(
                prompt, f"AI工具箱修改第{ch_idx+1}章",
                target="ai_toolbox")
        except Exception as e:
            self.tab_generation.log(
                f"⚠ AI 工具箱发送失败:{e}", "warn")
            try:
                self.tab_ai_toolbox.on_ai_result("")
            except Exception:
                pass

    def _on_fanqie_retry_details(self, failed_list):
        """
        用户在番茄榜单 Tab 点了'补抓失败详情'

        failed_list: [(book_id, source_label, source_category), ...]
        """
        try:
            if not failed_list:
                return
            project_root = self._v233_get_project_root()
            if not project_root:
                self.tab_generation.log(
                    "⚠ 补抓详情:无法确定项目根目录", "warn")
                return

            self.tab_generation.log(
                f"📚 用户手动补抓 {len(failed_list)} 本失败详情...", "info")

            # 获取最近的 stats(给 INDEX.md 用)
            cache = getattr(self, "_v231_rank_stats_cache", None)
            stats = cache.get("stats", {}) if cache else {}

            self.worker.submit({
                "action": "scrape_book_details_batch",
                "task_id": "fanqie_detail_retry",
                "book_ids": failed_list,
                "project_root": project_root,
                "stats": stats,
            })
        except Exception as e:
            self.tab_generation.log(
                f"⚠ 补抓详情触发失败:{e}", "warn")

    def _gen_inspiration_send_fallback(self, genres, platform):
        """v2.23.0 BUG-086: fallback 路径 — 走旧通用 prompt"""
        prompt = PROMPTS["creative_inspiration"].format(
            genre="/".join(genres), platform=platform)
        self.tab_generation.log(
            f"💡 正在根据{platform}{'/'.join(genres)}类热榜生成创意...", "info")
        self._send_to_ai(prompt, "创意灵感", target="inspiration")

    def _gen_inspiration_try_scrape(self, genres, platform):
        """
        v2.23.0 BUG-086:尝试扫榜,返回 True 表示扫榜任务已触发 / 缓存命中已发 AI
        返回 False 表示扫榜不可用,让上层走 fallback。
        """
        try:
            from core.fanqie_rank_scraper import (
                FanqieRankCache, filter_by_genres,
                build_enhanced_inspiration_prompt, Book)
        except Exception as e:
            self.tab_generation.log(
                f"⚠ 扫榜模块导入失败:{e},fallback 到通用 prompt", "warn")
            return False

        # 单例缓存,挂在 self 上
        if not hasattr(self, "_fanqie_rank_cache"):
            self._fanqie_rank_cache = FanqieRankCache()

        cached = self._fanqie_rank_cache.get(platform, genres)
        if cached:
            self.tab_generation.log(
                f"💡 番茄榜单缓存命中({len(cached)} 本),直接用", "info")
            self._gen_inspiration_with_books(cached, genres, platform)
            return True

        # 触发扫榜任务
        self.tab_generation.log(
            f"💡 准备扫描番茄榜单(用户选 {'/'.join(genres)} 类)...", "info")
        # 暂存上下文,扫榜回调时用
        self._pending_inspiration_ctx = {
            "genres": list(genres),
            "platform": platform,
        }
        self.worker.submit({
            "action": "scrape_fanqie_rank",
            "task_id": "fanqie_rank_scrape",
        })
        return True

    def _on_fanqie_rank_scraped(self, task_id, books_data):
        """
        v2.23.0 BUG-086:worker 扫榜完成回调,books_data 是 list[dict]

        - 扫到 0 条 → fallback 到旧通用 prompt
        - 扫到正常 → filter by genres → build_enhanced_prompt → 发 AI
        """
        ctx = getattr(self, "_pending_inspiration_ctx", None)
        if not ctx:
            # 不是 gen_inspiration 触发的扫榜?不该发生,稳妥起见忽略
            return
        # 用完即清
        self._pending_inspiration_ctx = None
        genres = ctx.get("genres", [])
        platform = ctx.get("platform", "番茄小说")
        try:
            from core.fanqie_rank_scraper import (
                Book, parse_scraped_books)
        except Exception:
            self._gen_inspiration_send_fallback(genres, platform)
            return
        # books_data 是 dict 列表(信号传递),转回 Book 对象
        books = parse_scraped_books(books_data) if books_data else []
        if not books:
            self.tab_generation.log(
                "⚠ 扫榜返回 0 条,fallback 到通用 prompt", "warn")
            self._gen_inspiration_send_fallback(genres, platform)
            return
        # 缓存
        if hasattr(self, "_fanqie_rank_cache"):
            self._fanqie_rank_cache.put(platform, genres, books)
        self._gen_inspiration_with_books(books, genres, platform)

    def _gen_inspiration_with_books(self, books, genres, platform):
        """
        v2.23.0 BUG-086:扫到的真实榜单 → filter by genres → build enhanced prompt → 发 AI
        """
        try:
            from core.fanqie_rank_scraper import (
                filter_by_genres, build_enhanced_inspiration_prompt)
        except Exception:
            self._gen_inspiration_send_fallback(genres, platform)
            return
        filtered, hard_n, relax_n = filter_by_genres(books, genres)
        if not filtered:
            self.tab_generation.log(
                f"⚠ 扫到 {len(books)} 本但题材匹配 0 条,fallback 到通用 prompt", "warn")
            self._gen_inspiration_send_fallback(genres, platform)
            return
        match_summary = (
            f"题材严格匹配 {hard_n} 本" +
            (f" + 题材相近补充 {relax_n} 本" if relax_n > 0 else "")
        )
        self.tab_generation.log(
            f"💡 榜单过滤后共 {len(filtered)} 本({match_summary})→ 拼增强 prompt", "info")
        prompt = build_enhanced_inspiration_prompt(filtered, genres, platform)
        if not prompt:
            self.tab_generation.log(
                "⚠ 增强 prompt 构造失败,fallback 到通用 prompt", "warn")
            self._gen_inspiration_send_fallback(genres, platform)
            return
        self._send_to_ai(prompt, "创意灵感", target="inspiration")

    def _show_inspiration_picker(self, content):
        """弹出灵感选择窗口 — 点击选一个"""
        import re as _re
        # 解析: "1. 【xxx】yyy" 或 "1. xxx" 格式
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        options = []
        for ln in lines:
            # 去掉序号前缀 "1. " "2、" etc
            cleaned = _re.sub(r'^\d+[.、)\]]\s*', '', ln).strip()
            if cleaned and len(cleaned) > 5:
                options.append(cleaned)
        if not options:
            # 解析失败,直接填入
            self.tab_settings.inspiration_edit.setPlainText(content)
            self._switch_to_tab(self.tab_settings)
            return

        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
        dlg = QDialog(self)
        dlg.setWindowTitle("💡 选择一个创意灵感")
        dlg.resize(650, 400)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("点击你最喜欢的一个:"))

        selected = [None]
        for i, opt in enumerate(options[:8]):
            # 提取【】里的卖点做按钮标题
            match = _re.search(r'【(.+?)】', opt)
            title = match.group(1) if match else opt[:20]
            detail = _re.sub(r'【.+?】', '', opt).strip()

            btn = QPushButton(f"{i+1}. {title}")
            btn.setToolTip(detail or opt)
            btn.setStyleSheet(
                "QPushButton { text-align:left; padding:10px 14px;"
                "font-size:13px; border:2px solid #ccc; border-radius:6px;"
                "margin:2px; } "
                "QPushButton:hover { border-color:#1a73e8; background:#e8f0fe; color:#3a3f47; }")
            btn.clicked.connect(
                lambda _, o=opt, d=dlg: (
                    selected.__setitem__(0, o), d.accept()))
            lay.addWidget(btn)

        # 底部按钮
        bottom = QHBoxLayout()
        btn_regen = QPushButton("🎲 不喜欢?重新生成")
        btn_regen.clicked.connect(lambda: (dlg.reject(), self.gen_inspiration()))
        bottom.addWidget(btn_regen)
        bottom.addStretch()
        btn_all = QPushButton("📋 全部填入")
        btn_all.setToolTip("把5个全填进去,自己改")
        btn_all.clicked.connect(
            lambda: (selected.__setitem__(0, content), dlg.accept()))
        bottom.addWidget(btn_all)
        lay.addLayout(bottom)

        if dlg.exec_() == QDialog.Accepted and selected[0]:
            self.tab_settings.inspiration_edit.setPlainText(selected[0])
            self._switch_to_tab(self.tab_settings)
            self.tab_generation.log("💡 已选择创意灵感", "success")

    def gen_title(self):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        insp = self.tab_settings.get_inspiration()
        if not insp.strip():
            QMessageBox.warning(self, "提示", "请先填写创意灵感"); return
        prompt = PROMPTS["title"].format(
            genre="/".join(genres), inspiration=insp,
            platform=self.tab_settings.get_platform())
        self.tab_generation.log("🏷️ 正在生成书名,请等待...", "info")
        self._send_to_ai(prompt, "AI生成书名", target="title")

    # ---- 补丁3：大纲自动回填 ----
    def _auto_fill_outline(self, text: str):
        """
        把 AI 返回的大纲文本按常见标题拆分，自动回填到 StoryOutline 各输入框。
        支持三种格式：
          1. 中文方括号: 【故事种子】、【世界观】、【章节大纲】
          2. Markdown 标题: ### 世界观设定、## 章节大纲、#### 第一卷
          3. 普通段落标题: 世界观设定、主角设定 等
        """
        outline = getattr(self, 'tab_outline', None)
        if outline is None:
            self.tab_generation.log("⚠️  找不到 tab_outline 控件，无法回填", "warn")
            return

        def extract_block(keywords, text, is_chapter=False):
            """
            提取以 keywords 中任意一个为标题的段落内容。
            支持 【xxx】、## xxx、xxx: 等多种格式。
            
            参数:
              is_chapter: 章节大纲特殊处理 - 匹配到文末（因为下面通常嵌套子标题如 #### 第一卷）
            """
            kw_pattern = '|'.join(re.escape(k) for k in keywords)
            # 标题行模式：可能带 【】 或 # 标记，关键词后允许有括号备注等
            title_pattern = (
                r'(?:^|\n)\s*'                          # 行首
                r'(?:【\s*)?'                             # 可选 【
                r'(?:#{1,6}\s*|\*+\s*)?'                # 可选 # 或 *
                r'(?:' + kw_pattern + r')'                # 关键词
                r'[^\n【]*'                               # 允许标题后任意非换行非【内容（如"章节大纲（300章）"）
                r'(?:】|[:：])?'                           # 可选结尾标点
                r'\s*\n+'                                # 换行
            )
            
            if is_chapter:
                # 章节大纲：匹配到下一个【】块或文末（不被 #### 子标题截断）
                pattern = title_pattern + r'(.*?)(?=\n\s*【|\Z)'
            else:
                # 其他模块：匹配到下一个标题（任何 # 级或【】）
                pattern = title_pattern + r'(.*?)(?=\n\s*(?:【|#{1,6}\s)|\Z)'
            
            m = re.search(pattern, text, re.S | re.M)
            return m.group(1).strip() if m else ""

        # 各模块的关键词（同义词组）
        seed_kws       = ["故事种子", "故事核心", "核心设定", "故事概要"]
        worldview_kws  = ["世界观", "世界观设定", "世界设定", "背景设定"]
        lo_kws         = ["LO层", "LO世界观", "底层逻辑", "世界规则"]
        structure_kws  = ["故事结构", "故事架构", "结构设定", "整体结构"]
        chapter_kws    = ["章节大纲", "分章大纲", "章节梗概", "章节列表"]
        intro_kws      = ["简介", "作品简介", "故事简介"]

        def extract_kv(keywords, text):
            """兜底：匹配 **关键词**：内容 / 关键词：内容 这种键值对（单行）"""
            kw_pattern = '|'.join(re.escape(k) for k in keywords)
            pattern = (
                r'(?:\*\*\s*)?'                 # 可选 **
                r'(?:' + kw_pattern + r')'         # 关键词
                r'(?:\s*\*\*)?'                 # 可选 **
                r'\s*[:：]\s*'                   # 冒号
                r'(.+?)'                           # 内容
                r'(?=\n|\Z)'                     # 行尾或文末
            )
            m = re.search(pattern, text)
            return m.group(1).strip() if m else ""

        # 先尝试段落标题，再降级到键值对
        seed       = extract_block(seed_kws, text)       or extract_kv(seed_kws + ["题材", "故事题材"], text)
        worldview  = extract_block(worldview_kws, text)  or extract_kv(worldview_kws, text)
        lo_layer   = extract_block(lo_kws, text)         or extract_kv(lo_kws, text)
        structure  = extract_block(structure_kws, text)  or extract_kv(structure_kws + ["节奏", "升级逻辑"], text)
        ch_outline = extract_block(chapter_kws, text, is_chapter=True)
        intro      = extract_block(intro_kws, text)      or extract_kv(intro_kws, text)

        # 兜底：如果章节大纲没识别到，但文本里有大量 "1." "2." "第X章" 这种列表
        # 就把列表部分作为章节大纲
        if not ch_outline:
            # 找到第一个章节列表的开始位置
            list_match = re.search(r'(?:^|\n)\s*(?:1[\.\、]|第[一二三四五六七八九十1-9][章卷])', text, re.M)
            if list_match:
                # 从这里到文末作为章节大纲
                ch_outline = text[list_match.start():].strip()

        filled = []
        if seed       and hasattr(outline, 'seed_edit'):
            outline.seed_edit.setPlainText(seed);            filled.append("故事种子")
        if worldview  and hasattr(outline, 'worldview_edit'):
            outline.worldview_edit.setPlainText(worldview);  filled.append("世界观")
        if lo_layer   and hasattr(outline, 'lo_edit'):
            outline.lo_edit.setPlainText(lo_layer);          filled.append("LO层")
        if structure  and hasattr(outline, 'structure_edit'):
            outline.structure_edit.setPlainText(structure);  filled.append("结构")
        if ch_outline and hasattr(outline, 'chapter_outline_edit'):
            outline.chapter_outline_edit.setPlainText(ch_outline); filled.append("章节大纲")
        if intro      and hasattr(outline, 'intro_edit'):
            outline.intro_edit.setPlainText(intro);          filled.append("简介")

        if filled:
            self.tab_generation.log(f"✅ 大纲已自动回填：{' / '.join(filled)}", "success")
        else:
            self.tab_generation.log("✅ 大纲整体已回填（未检测到分块标题）", "success")

    def gen_outline_all(self):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        insp = self.tab_settings.get_inspiration()
        if not insp.strip():
            QMessageBox.warning(self, "提示", "请先填写创意灵感"); return
        cc = self.tab_settings.get_chapter_count()
        self.tab_outline.chapter_count.setValue(cc)
        special = self.tab_outline.special_edit.toPlainText()
        full_settings = self.tab_settings.get_full_settings_block()
        extra_parts = [f"\n\n【完整设定】\n{full_settings}"]
        if special.strip():
            extra_parts.append(f"\n【特殊需求/外部资料】\n{special}")
        detail = self.tab_settings.get_outline_detail()
        extra_parts.append(
            f"\n【大纲详细度】{detail}"
            f"({'每章一句话' if detail == '简洁' else '每章 50-80 字' if detail == '标准' else '每章 100-200 字,含主要情节、冲突、转折'})")
        extra = "".join(extra_parts)
        prompt = PROMPTS["outline_full"].format(
            genre="/".join(genres), inspiration=insp,
            chapter_count=cc, extra=extra)
        self._send_to_ai(prompt, "完整大纲", target="outline_full")

    def gen_outline_part(self, part_name):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        insp = self.tab_settings.get_inspiration()
        extra = f"\n【完整设定参考】\n{self.tab_settings.get_full_settings_block()}"
        if part_name == "章节大纲":
            extra += f"\n总章节数:{self.tab_settings.get_chapter_count()} 章。"
        prompt = PROMPTS["outline_part"].format(
            part_name=part_name, genre="/".join(genres),
            inspiration=insp, extra=extra)
        self._send_to_ai(prompt, part_name, target=f"outline_part:{part_name}")

    def extract_intro(self):
        seed = self.tab_outline.seed_edit.toPlainText()
        wv = self.tab_outline.worldview_edit.toPlainText()
        st = self.tab_outline.structure_edit.toPlainText()
        if not (seed or wv or st):
            QMessageBox.warning(self, "提示", "请先填写大纲内容"); return
        prompt = PROMPTS["intro"].format(seed=seed, worldview=wv, structure=st)
        self._send_to_ai(prompt, "作品简介", target="intro")

    def open_rename_dialog(self):
        """🔄 改名工具:多对应一次替换大纲全部文本(也可选择是否覆盖章节正文)
        例如:林远→苏白 + 林悦→苏雨 + 天剑宗→玄霄宗,一次提交。"""
        # 收集所有要扫描的目标(QPlainTextEdit + chapter content)
        # 用 _get_widget 容错:某个字段在重构后改名/删了,不会整个崩
        def _get_widget(obj, attr):
            return getattr(obj, attr, None) if obj is not None else None

        raw_targets = [
            ("特殊需求", _get_widget(self.tab_outline, "special_edit")),
            ("简介", _get_widget(self.tab_outline, "intro_edit")),
            ("故事种子", _get_widget(self.tab_outline, "seed_edit")),
            ("世界观", _get_widget(self.tab_outline, "worldview_edit")),
            ("LO世界观层", _get_widget(self.tab_outline, "lo_edit")),
            ("故事结构", _get_widget(self.tab_outline, "structure_edit")),
            ("章节大纲", _get_widget(self.tab_outline, "chapter_outline_edit")),
            ("角色档案", _get_widget(self.tab_memory, "chars_edit")),
        ]
        # 过滤掉 None(不存在的 widget),日志记下缺失项
        targets = [(label, w) for label, w in raw_targets if w is not None]
        missing = [label for label, w in raw_targets if w is None]
        if missing:
            self.tab_generation.log(
                f"改名工具:以下字段没找到 widget,跳过 → {missing}", "warn")

        dlg = QDialog(self)
        dlg.setWindowTitle("🔄 改名工具(批量替换大纲/章节中的角色/地名/门派)")
        dlg.setMinimumWidth(700)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "<b>使用方法:</b>每行一个对应关系,<b>旧名 + 空格 + 新名</b><br>"
            "例如:<br>"
            "&nbsp;&nbsp;<code>林远 林麟</code>(中间一个空格就行)<br>"
            "&nbsp;&nbsp;<code>林悦 林雨</code><br>"
            "&nbsp;&nbsp;<code>天剑宗 玄霄宗</code><br>"
            "<i>(箭头 → / = / 制表符 也支持,如果你想打)</i>"))
        rename_text = QPlainTextEdit()
        rename_text.setPlaceholderText("林远 林麟\n林悦 林雨\n天剑宗 玄霄宗")
        rename_text.setMinimumHeight(150)
        rename_text.setStyleSheet("font-family:monospace;font-size:13px;")
        lay.addWidget(rename_text)

        # 范围 checkbox
        cb_outline = QCheckBox("替换大纲全部文本(简介/种子/世界观/LO/结构/章节大纲/特殊需求/角色设定)")
        cb_outline.setChecked(True)
        cb_chapters = QCheckBox(f"同时替换已生成章节正文({len(self.chapters)} 章)")
        cb_chapters.setChecked(False)  # 默认不动章节,只动大纲(更安全)
        cb_charlib = QCheckBox("同时替换 🎭 角色与世界 库的所有表(角色名/关系/物品持有人等)")
        cb_charlib.setChecked(True)
        for cb in (cb_outline, cb_chapters, cb_charlib):
            lay.addWidget(cb)

        # 按钮
        btn_row = QHBoxLayout()
        btn_preview = QPushButton("👁 预览替换数(不写盘)")
        btn_preview.setStyleSheet("background:#3498db;color:white;padding:6px 14px;border-radius:3px;")
        btn_apply = QPushButton("✓ 应用替换(写盘 + 自动保存)")
        btn_apply.setStyleSheet(
            "background:#1f8b4d;color:white;padding:6px 14px;border-radius:3px;font-weight:bold;")
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)

        def parse_pairs():
            """从文本解析"旧名 新名"映射。
            优先用箭头/等号分隔(更精确);没有就用空白拆 2 段(任意空白,包括单空格)。"""
            pairs = []
            for line in rename_text.toPlainText().splitlines():
                line = line.strip()
                if not line:
                    continue
                # 1) 优先看有没有显式分隔符 → / -> / => / =
                m = re.split(r'\s*(?:→|->|=>|=)\s*', line, 1)
                if len(m) == 2 and m[0].strip() and m[1].strip():
                    pairs.append((m[0].strip(), m[1].strip()))
                    continue
                # 2) 没有显式分隔符 → 按任意空白(含单空格/制表符)拆成两段
                #    .split(None, 1) 是 Python 推荐的"按任意空白拆"
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    pairs.append((parts[0].strip(), parts[1].strip()))
            return pairs

        def do_scan_and_apply(write):
            pairs = parse_pairs()
            if not pairs:
                QMessageBox.warning(dlg, "提示",
                    "没解析出有效对应关系。\n格式:旧名 → 新名,每行一个")
                return
            # 验证没重名
            old_set = set()
            for old, new in pairs:
                if old in old_set:
                    QMessageBox.warning(dlg, "重复",
                        f"旧名 '{old}' 出现多次,只能定义一次。")
                    return
                old_set.add(old)

            # 统计 & 替换
            stats = []
            total = 0
            # 1) 大纲编辑器
            if cb_outline.isChecked():
                for label, widget in targets:
                    txt = widget.toPlainText()
                    n_changes = 0
                    new_txt = txt
                    for old, new in pairs:
                        cnt = new_txt.count(old)
                        if cnt > 0:
                            new_txt = new_txt.replace(old, new)
                            n_changes += cnt
                    if n_changes > 0:
                        stats.append(f"{label}: {n_changes} 处")
                        total += n_changes
                        if write:
                            widget.setPlainText(new_txt)

            # 2) 章节正文
            if cb_chapters.isChecked() and self.chapters:
                ch_changes = 0
                for ch in self.chapters:
                    c = ch.get("content", "")
                    new_c = c
                    for old, new in pairs:
                        cnt = new_c.count(old)
                        if cnt > 0:
                            new_c = new_c.replace(old, new)
                            ch_changes += cnt
                    if write and new_c != c:
                        ch["content"] = new_c
                    # 章节标题也换
                    t = ch.get("title", "")
                    new_t = t
                    for old, new in pairs:
                        new_t = new_t.replace(old, new)
                    if write and new_t != t:
                        ch["title"] = new_t
                if ch_changes > 0:
                    stats.append(f"章节正文: {ch_changes} 处")
                    total += ch_changes

            # 3) 🎭 角色与世界库 — 遍历每张表的每个单元格
            if cb_charlib.isChecked() and hasattr(self, "tab_charlib"):
                cl = self.tab_charlib
                tables = [
                    ("角色档案", cl.tbl_chars),
                    ("关系图谱", cl.tbl_relations),
                    ("时间线", cl.tbl_timeline),
                    ("物品法器", cl.tbl_items),
                    ("战力等级", cl.tbl_power),
                    ("伏笔追踪", cl.tbl_fore),
                ]
                # 钩子/爽点子页如果存在(用户已升级到 bf9f713 之后)
                if hasattr(cl, "tbl_hooks"):
                    tables.append(("钩子编年", cl.tbl_hooks))
                if hasattr(cl, "tbl_cool"):
                    tables.append(("爽点编年", cl.tbl_cool))
                for tname, tbl in tables:
                    t_changes = 0
                    for r in range(tbl.rowCount()):
                        for c in range(tbl.columnCount()):
                            item = tbl.item(r, c)
                            if not item:
                                continue
                            v = item.text()
                            new_v = v
                            for old, new in pairs:
                                cnt = new_v.count(old)
                                if cnt > 0:
                                    new_v = new_v.replace(old, new)
                                    t_changes += cnt
                            if write and new_v != v:
                                from PyQt5.QtWidgets import QTableWidgetItem
                                tbl.setItem(r, c, QTableWidgetItem(new_v))
                    if t_changes > 0:
                        stats.append(f"{tname}: {t_changes} 处")
                        total += t_changes

            # 输出报告
            if total == 0:
                QMessageBox.information(dlg, "结果",
                    f"扫描完成,没有匹配的内容。\n请检查旧名拼写是否正确。")
                return

            msg = (f"共 {len(pairs)} 个对应关系,"
                   f"{'已替换' if write else '将替换'} {total} 处:\n\n"
                   + "\n".join(f"  · {s}" for s in stats))
            if write:
                # 自动保存
                try:
                    self.save_project()
                except Exception:
                    try:
                        self._autosave()
                    except Exception:
                        pass
                # 刷新当前章节编辑器
                try:
                    ci = self.tab_editor.current_index
                    if 0 <= ci < len(self.chapters):
                        self.tab_editor.show_chapter(self.chapters[ci], ci)
                except Exception:
                    pass
                self.tab_generation.log(f"🔄 改名应用:{total} 处替换,已自动保存", "success")
                msg += "\n\n✓ 已自动保存项目(.backups 保留原版本,可菜单 → 🕓 恢复)"
                QMessageBox.information(dlg, "✓ 完成", msg)
                dlg.accept()
            else:
                QMessageBox.information(dlg, "👁 预览(未写盘)", msg)

        btn_preview.clicked.connect(lambda: do_scan_and_apply(write=False))
        btn_apply.clicked.connect(lambda: do_scan_and_apply(write=True))
        btn_row.addWidget(btn_preview)
        btn_row.addWidget(btn_apply)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        dlg.exec_()

    def gen_first_chapter(self):
        """单独生成第一章（要求已有章节大纲）"""
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        if not co.strip():
            QMessageBox.warning(self, "提示", "请先生成或填写章节大纲")
            return
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录。")
            return
        # 重置章节列表（如果用户想重新从第一章开始）
        if self.chapters:
            reply = QMessageBox.question(
                self, "确认", 
                f"已有 {len(self.chapters)} 章，是否清空后从第 1 章开始？\n（选「否」则继续生成下一章）",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.chapters.clear()
                self.tab_generation.log("已清空已生成章节，准备生成第 1 章", "info")
        # 设置批量参数(单章生成: remaining=1)
        self._batch_remaining = 1
        self._batch_paused = False
        self.tab_generation.log("▶ 开始生成第 1 章...", "info")
        self._send_next_chapter()

    def gen_golden_three(self):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        full = self.tab_settings.get_full_settings_block()
        # 角色库 + 时间线 + 伏笔 一键注入
        charlib_block = ""
        if hasattr(self, "tab_charlib"):
            charlib_block = self.tab_charlib.build_inject_block(current_chapter=1)
        prompt = PROMPTS["golden_three"].format(
            title=self.tab_settings.get_title(),
            genre="/".join(genres),
            inspiration=self.tab_settings.get_inspiration(),
            ch_outline=self.tab_outline.chapter_outline_edit.toPlainText()[:3000]
        ) + f"\n\n【完整设定】\n{full}"
        if charlib_block:
            prompt += charlib_block
            self.tab_generation.log(
                f"已注入角色与世界状态({len(charlib_block)} 字符)到黄金三章", "info")
        self._send_to_ai(prompt, "黄金三章", target="golden_three")

    def gen_next_chapter_single(self):
        """▶ 写下一章(单章生成,不进入批量模式)
        跟批量生成共享 _send_next_chapter,但 _batch_remaining=1 + _batch_silent=False
        (单章模式下伏笔到期提醒会弹出来,让用户主动处理)"""
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录。")
            return
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        if not co.strip():
            QMessageBox.warning(self, "提示", "请先生成或填写章节大纲"); return
        if not self.chapters:
            QMessageBox.warning(
                self, "提示",
                "目前没有任何章节。\n"
                "首次生成请点【📖 生成第一章】或【生成黄金三章】。\n"
                "「写下一章」是在已有章节基础上续写。")
            return
        next_ch_num = len(self.chapters) + 1
        # 启动单章模式
        self._batch_remaining = 1
        self._batch_paused = False
        self._batch_silent = False  # 单章模式 → 伏笔到期弹提醒
        target = self.tab_settings.get_words_per_chapter()
        offset = self.tab_settings.get_prompt_offset()
        target_with_offset = max(500, target + offset)
        self.tab_generation.log(
            f"▶ 单章模式:写第 {next_ch_num} 章,目标 {target_with_offset} 字"
            f"(基础 {target} {offset:+d}),死磕 {self.tab_generation.retry_count.value()} 次上限",
            "info")
        self._send_next_chapter()

    def start_generation(self):
        """开始批量自动生成 - 真自动:发送→等回复→抓取→存章节→发下一章"""
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录。")
            return
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        if not co.strip():
            QMessageBox.warning(self, "提示", "请先生成或填写章节大纲"); return
        # 启动批量
        self._batch_remaining = self.tab_generation.batch_count.value()
        self._batch_paused = False
        # BUG #8 修复:批量生成时静默伏笔提醒,避免阻塞自动化流程
        # 伏笔信息仍会注入到 prompt,只是不弹 modal
        self._batch_silent = True
        target = self.tab_settings.get_words_per_chapter()
        offset = self.tab_settings.get_prompt_offset()
        target_with_offset = max(500, target + offset)
        self.tab_generation.log(
            f"▶ 批量启动:{self._batch_remaining} 章,目标 {target_with_offset} 字"
            f"(基础 {target} {offset:+d}),死磕 {self.tab_generation.retry_count.value()} 次", "info")
        self._update_window_title(f"⏳ 生成中({self._batch_remaining}章)")
        self._send_next_chapter()

    def batch_count_value(self):
        return self.tab_generation.batch_count.value()

    def pause_generation(self):
        self._batch_paused = True
        self._batch_remaining = 0
        self._batch_silent = False  # 退出批量,恢复伏笔提醒
        self.tab_generation.log("⏸ 已请求停止批量(等待当前任务结束)", "warn")

    def grab_response(self):
        """手动触发抓取最后一条 AI 回复"""
        if not self.worker.is_ready():
            QMessageBox.warning(self, "提示", "请先启动浏览器"); return
        # target=None,弹窗让用户选回填位置
        # v1.97 BUG-071:字典写入 key="手动抓取"(== worker submit 的 task_id)
        self._pending_task_targets["手动抓取"] = {"target": None, "label": "手动抓取"}
        self.worker.submit({"action": "just_grab", "task_id": "手动抓取"})

    def optimize_chapter(self, content):
        prompt = PROMPTS["ai_optimize"].format(content=content[:6000])
        self._send_to_ai(prompt, "AI润色", target="optimize")

    # ---- 其他 ----
    def _import_to(self, target_edit):
        path, _ = QFileDialog.getOpenFileName(self, "导入TXT", "", "文本 (*.txt)")
        if path:
            try:
                txt = Path(path).read_text(encoding="utf-8", errors="ignore")
                target_edit.setPlainText(txt)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取失败:{e}")

    def prelogin_ai(self):
        ai = self.tab_settings.get_selected_ai()
        url = AI_URLS.get(ai) or self.tab_settings.custom_url.text().strip()
        if not url:
            return
        self.tab_generation.url_input.setText(url)
        if ai in AI_URLS:
            self.tab_generation.site_combo.setCurrentText(ai)
        if not self.worker.is_ready():
            self.tab_generation.log(f"启动浏览器以登录 {ai}...", "info")
            self.launch_browser()
        else:
            self.worker.submit({"action": "navigate", "url": url})
            self.tab_generation.log(f"请在浏览器中完成 {ai} 的登录", "info")

    def closeEvent(self, event):
        """关闭主窗口时停止浏览器线程,清理临时文件"""
        from PyQt5.QtCore import QSettings
        QSettings("NovelAI", "MainWindow").setValue("geometry", self.saveGeometry())
        self.tab_settings.save_settings()
        self._autosave()
        try:
            self.worker.stop()
        except Exception:
            pass
        # 清理所有 novel_ai 临时文件
        try:
            import os, tempfile, glob
            tmp_dir = tempfile.gettempdir()
            for f in glob.glob(os.path.join(tmp_dir, "novel_ai_prompt_*.txt")):
                try:
                    os.remove(f)
                except Exception:
                    pass
        except Exception:
            pass
        event.accept()

    def _periodic_autosave_fire(self):
        """第 9 项配套:60 秒定时 autosave,只在有项目文件且内容有变化时跑,
        避免无意义的写盘和日志噪音"""
        try:
            # 尊重用户开关:auto_save_project 关掉就不跑定时
            cb = getattr(self.tab_generation, "auto_save_project", None)
            if cb is not None and not cb.isChecked():
                return
            # 没打开任何项目,跳过
            if not self.current_project_file:
                return
            # 章节为空且记忆为空 → 跳过
            if not self.chapters and not self.tab_memory.summaries_edit.toPlainText().strip():
                return
            self._autosave()
            # v1.32 dev: 用户说自动保存别显示,只在 console 留痕便于事后追溯
            print("[autosave] ⏱ 60s 定时 autosave 已执行", flush=True)
        except Exception:
            pass

    def _autosave(self):
        """自动保存到当前项目文件，若无则保存到 autosave.json"""
        try:
            if 0 <= self.current_chapter_index < len(self.chapters):
                self.chapters[self.current_chapter_index]["title"] = self.tab_editor.title_input.text()
                self.chapters[self.current_chapter_index]["content"] = self.tab_editor.content_edit.toPlainText()
            # v2.21.4 BUG-080:保存前先把伏笔 Tab 的 UI 同步到 mw.open_loops
            try:
                if hasattr(self, "tab_foreshadow") and hasattr(self.tab_foreshadow, "sync_to_mw"):
                    self.tab_foreshadow.sync_to_mw()
            except Exception:
                pass
            # v1.30:autosave 默认也走文件夹格式(autosave/ 子文件夹)
            save_path = self.current_project_file or str(self.project_dir / "autosave")
            s = self.tab_settings
            d = {
                "title": s.get_title(),
                "inspiration": s.get_inspiration(),
                "seed": self.tab_outline.seed_edit.toPlainText(),
                "worldview": self.tab_outline.worldview_edit.toPlainText(),
                "lo": self.tab_outline.lo_edit.toPlainText(),
                "structure": self.tab_outline.structure_edit.toPlainText(),
                "chapter_outline": self.tab_outline.chapter_outline_edit.toPlainText(),
                "intro": self.tab_outline.intro_edit.toPlainText(),
                "chapters": self.chapters,
                "memory": {
                    "characters": self.tab_memory.chars_edit.toPlainText(),
                    "summaries": self.tab_memory.summaries_edit.toPlainText(),
                    "long_term": self.tab_memory.long_term_edit.toPlainText(),
                    "auto_summarize": self.tab_memory.auto_summarize.isChecked(),
                    "auto_inject": self.tab_memory.auto_inject.isChecked(),
                    "recent_n": self.tab_memory.recent_n.value(),
                    "summary_len": self.tab_memory.summary_len.value(),
                },
                "canon": self.tab_canon.serialize_for_save(),
                "charlib": self.tab_charlib.serialize() if hasattr(self, "tab_charlib") else {},
                "skills": self.tab_skills.serialize_for_save(),
                "critique": self.tab_generation.critique_config(),
                "conv_slots": self.tab_generation.conv_switcher.serialize_for_save(),
                "lifespan_loops": (
                    self.tab_lifespan.serialize_for_save()
                    if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None)
                    else {}
                ),
                # v2.21.4 BUG-080:伏笔 Tab 数据要保存(之前完全没存,重启就丢)
                "open_loops": (
                    getattr(self, "open_loops", {}) or {}
                ),
                "advanced": {
                    "genres": s.get_selected_genres(),
                    "platform": s.get_platform(),
                    "audience": s.get_audience(),
                    "density": s.get_density(),
                    "growth": s.get_growth(),
                    "conflict": s.get_conflict(),
                    "era": s.get_era(),
                    "chapter_count": s.get_chapter_count(),
                    "words_per_chapter": s.get_words_per_chapter(),
                    "outline_detail": s.get_outline_detail(),
                    "style_weights": s.get_style_weights(),
                    "rhythm": s.get_rhythm(),
                    "endings": s.get_endings(),
                    "creation_mode": s.get_creation_mode(),
                    "prompt_offset": s.get_prompt_offset(),
                    "golden_fingers": s.get_golden_fingers(),
                    "personas": s.get_personas(),
                    "ai": s.get_selected_ai(),
                },
                "saved_at": datetime.now().isoformat(),
                "gen_url": self.tab_generation.url_input.text(),
                "gen_site": self.tab_generation.site_combo.currentText(),
            }
            # v1.31 BUG-043:autosave 也走 project_io 文件夹格式
            # 之前只改了 save_project 没改这个,导致文件夹路径被当文件写,Permission denied
            target = Path(save_path)
            # v2.23.7 脏哈希短路:payload(除易变的 saved_at)与上次保存
            # 完全一致且目标已存在 → 跳过。60s 定时器在用户静止时零 IO,
            # 不再每分钟全量重写整个项目。
            import hashlib as _hl
            _dh = _hl.md5(json.dumps(
                {k: v for k, v in d.items() if k != "saved_at"},
                ensure_ascii=False, sort_keys=True, default=str
            ).encode("utf-8")).hexdigest()
            if (_dh == getattr(self, "_last_autosave_hash", None)
                    and target.exists()):
                print("[autosave] 内容未变,跳过", flush=True)
                return
            if PROJECT_IO_AVAILABLE and (
                    not target.suffix or target.is_dir() or
                    (not target.exists() and not save_path.endswith(".json"))):
                # 走文件夹格式
                project_io.save_project_folder(target, d)
                # autosave 不打 status bar(太频繁),只在 console
                print(f"[autosave] 已写文件夹: {target}", flush=True)
            else:
                # 旧 .json 路径 — v2.23.7 改原子写:此前 write_text 截断写,
                # 写一半崩溃 = 新旧数据两空
                target.parent.mkdir(parents=True, exist_ok=True)
                _payload_text = json.dumps(d, ensure_ascii=False, indent=2)
                import tempfile as _tf
                _fd, _tmp = _tf.mkstemp(prefix=target.name + ".",
                                        dir=str(target.parent))
                try:
                    with os.fdopen(_fd, "w", encoding="utf-8") as _fh:
                        _fh.write(_payload_text)
                    os.replace(_tmp, target)
                except Exception:
                    try:
                        os.unlink(_tmp)
                    except OSError:
                        pass
                    raise
                print(f"[autosave] 已写 .json: {target}", flush=True)
            self._last_autosave_hash = _dh
        except Exception as e:
            import traceback
            self.statusBar().showMessage(f"自动保存失败:{e}", 5000)
            print(f"[autosave] 失败: {e}\n{traceback.format_exc()}", flush=True)

    def _autoload(self):
        """启动时自动加载上次的项目
        v1.36 BUG-049:加载顺序
          1. 上次主动保存的项目(QSettings 'UI/last_project_path')
          2. autosave 文件夹(v1.30+ 格式)
          3. autosave.json(老格式兜底)
        """
        d = None
        loaded_path = None
        # 1. 上次主动保存的项目路径(QSettings 持久化)
        try:
            from PyQt5.QtCore import QSettings
            last_path = QSettings("NovelAI", "UI").value("last_project_path", "", type=str)
            if last_path and PROJECT_IO_AVAILABLE:
                from pathlib import Path as _P
                lp = _P(last_path)
                if lp.is_dir() and (lp / "project.json").exists():
                    d = project_io.load_project_folder(lp)
                    loaded_path = str(lp)
                    self.current_project_file = loaded_path
                    print(f"[autoload] ✓ 加载上次项目文件夹: {lp}", flush=True)
                    self._project_title = Path(lp).name
                    self._update_window_title()
                    # v1.41: 推到最近项目列表(确保 last 也在 recent 顶端)
                    try:
                        self._push_to_recent(loaded_path)
                    except Exception:
                        pass
        except Exception as _e:
            print(f"[autoload] last_project_path 加载失败: {_e}", flush=True)
        # 2. autosave 文件夹(v1.30+ 格式)
        if d is None:
            autosave_dir = self.project_dir / "autosave"
            if autosave_dir.is_dir() and (autosave_dir / "project.json").exists() and PROJECT_IO_AVAILABLE:
                try:
                    d = project_io.load_project_folder(autosave_dir)
                    loaded_path = str(autosave_dir)
                    print(f"[autoload] ✓ 加载 autosave 文件夹: {autosave_dir}", flush=True)
                except Exception as _e:
                    print(f"[autoload] autosave 文件夹加载失败: {_e}", flush=True)
        # 3. autosave.json(老格式兜底)
        if d is None:
            autosave_json = self.project_dir / "autosave.json"
            if autosave_json.exists():
                try:
                    d = json.loads(autosave_json.read_text(encoding="utf-8"))
                    print(f"[autoload] ✓ 加载老 autosave.json (兜底)", flush=True)
                except Exception as _e:
                    print(f"[autoload] autosave.json 加载失败: {_e}", flush=True)
        if d is None:
            return
        try:
            self.chapters = d.get("chapters", [])
            # v1.92 BUG-066:旧存档无 locked 字段 → 兜底 False(向后兼容)
            for _ch in self.chapters:
                if isinstance(_ch, dict):
                    _ch.setdefault("locked", False)
            self.tab_settings.title_input.setText(d.get("title", ""))
            self.tab_settings.inspiration_edit.setPlainText(d.get("inspiration", ""))
            self.tab_outline.seed_edit.setPlainText(d.get("seed", ""))
            self.tab_outline.worldview_edit.setPlainText(d.get("worldview", ""))
            self.tab_outline.lo_edit.setPlainText(d.get("lo", ""))
            self.tab_outline.structure_edit.setPlainText(d.get("structure", ""))
            self.tab_outline.chapter_outline_edit.setPlainText(d.get("chapter_outline", ""))
            self.tab_outline.intro_edit.setPlainText(d.get("intro", ""))
            adv = d.get("advanced", {})
            if adv:
                self._apply_advanced(adv)
            mem = d.get("memory", {})
            if mem:
                self.tab_memory.chars_edit.setPlainText(mem.get("characters", ""))
                self.tab_memory.summaries_edit.setPlainText(mem.get("summaries", ""))
                self.tab_memory.long_term_edit.setPlainText(mem.get("long_term", ""))
                self.tab_memory.auto_summarize.setChecked(mem.get("auto_summarize", True))
                self.tab_memory.auto_inject.setChecked(mem.get("auto_inject", True))
                self.tab_memory.recent_n.setValue(int(mem.get("recent_n", 3)))
                self.tab_memory.summary_len.setValue(int(mem.get("summary_len", 80)))
            if d.get("canon"):
                self.tab_canon.load_from_dict(d["canon"])
            if d.get("charlib") and hasattr(self, "tab_charlib"):
                self.tab_charlib.load(d["charlib"])
            if d.get("skills"):
                self.tab_skills.load_from_dict(d["skills"])
            crit = d.get("critique", {})
            if crit:
                self.tab_generation.chk_crit_words.setChecked(crit.get("word_count", True))
                self.tab_generation.chk_crit_hook.setChecked(crit.get("hook", True))
                self.tab_generation.chk_crit_canon.setChecked(crit.get("canon", True))
                self.tab_generation.chk_crit_rhythm.setChecked(crit.get("rhythm", False))
                self.tab_generation.chk_crit_char.setChecked(crit.get("character", False))
            if d.get("conv_slots"):
                self.tab_generation.conv_switcher.load_from_dict(d["conv_slots"])
            if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None and d.get("lifespan_loops")):
                self.tab_lifespan.load_from_dict(d["lifespan_loops"])
            # 恢复生成控制 URL
            if d.get("gen_url"):
                self.tab_generation.url_input.setText(d["gen_url"])
            if d.get("gen_site"):
                self.tab_generation.site_combo.setCurrentText(d["gen_site"])
            self._refresh_chapter_list()
            # v1.41: 刷新项目主页
            try:
                if hasattr(self, "tab_home"):
                    self.tab_home.refresh(self)
            except Exception:
                pass
            # v2.23.4: 番茄榜单 Tab 同步项目根目录 + 加载磁盘缓存
            self._sync_fanqie_rank_tab()
            self.statusBar().showMessage("已恢复上次自动保存的项目", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"自动加载失败:{e}", 5000)

    def new_project(self):
        # 先取名
        title, ok = QInputDialog.getText(
            self, "新建项目", "请给小说取个名字:",
            text="我的新小说")
        if not ok or not title.strip():
            return
        title = title.strip()
        if QMessageBox.question(
            self, "新建项目",
            f"新建「{title}」将清空当前所有数据,继续?"
        ) != QMessageBox.Yes:
            return
        self._reset_ui_state()
        # 创建项目文件夹
        import re as _re
        safe_title = _re.sub(r'[\\/:*?"<>|]', '_', title)
        proj_path = self.project_dir / safe_title
        proj_path.mkdir(parents=True, exist_ok=True)
        self.current_project_file = str(proj_path)
        self._project_title = title
        self._update_window_title()
        # 保存路径到 QSettings
        try:
            from PyQt5.QtCore import QSettings
            QSettings("NovelAI", "UI").setValue(
                "last_project_path", self.current_project_file)
        except Exception:
            pass
        try:
            if hasattr(self, "tab_home"):
                self.tab_home.refresh(self)
        except Exception:
            pass
        self.tab_generation.log(f"📁 新建项目:「{title}」", "success")
        self.statusBar().showMessage(f"新项目「{title}」已创建", 3000)

    def rename_project(self):
        """重命名当前项目"""
        if not self.current_project_file:
            QMessageBox.information(self, "提示", "没有打开的项目")
            return
        old_path = Path(self.current_project_file)
        old_name = old_path.name
        new_name, ok = QInputDialog.getText(
            self, "项目重命名", "新名字:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        import re as _re
        safe_name = _re.sub(r'[\\/:*?"<>|]', '_', new_name)
        new_path = old_path.parent / safe_name
        if new_path.exists():
            QMessageBox.warning(self, "重命名", f"「{safe_name}」已存在")
            return
        try:
            old_path.rename(new_path)
            self.current_project_file = str(new_path)
            self._project_title = new_name
            self._update_window_title()
            from PyQt5.QtCore import QSettings
            QSettings("NovelAI", "UI").setValue(
                "last_project_path", self.current_project_file)
            self._push_to_recent(self.current_project_file)
            self.tab_generation.log(
                f"📁 项目重命名:「{old_name}」→「{new_name}」", "success")
        except Exception as e:
            QMessageBox.warning(self, "重命名失败", str(e))

    def open_project(self):
        """v1.50:直接弹文件夹选择器,去掉 v1.30 迁移期的二选一弹窗
        老 .json 入口移到 工具菜单 → '导入旧 .json 项目'(罕用)"""
        path = QFileDialog.getExistingDirectory(
            self, "选择项目文件夹", str(self.project_dir))
        if not path:
            return

        # 用 project_io 加载(优先,兼容文件夹格式)
        if PROJECT_IO_AVAILABLE:
            try:
                fmt = project_io.detect_format(path)
                if fmt == "folder":
                    d = project_io.load_project_folder(path)
                    self.current_project_file = str(Path(path).resolve())
                    # v1.36 BUG-049:存到 QSettings 让下次启动能自动加载
                    try:
                        from PyQt5.QtCore import QSettings
                        QSettings("NovelAI", "UI").setValue(
                            "last_project_path", self.current_project_file)
                    except Exception:
                        pass
                    # v1.41: 推到最近项目列表
                    self._push_to_recent(self.current_project_file)
                    self.tab_generation.log(
                        f"📂 已打开项目文件夹: {path}", "success")
                elif fmt == "legacy_json":
                    # 旧 .json → 询问升级
                    ret = QMessageBox.question(
                        self, "检测到旧版项目",
                        f"这是旧版单 .json 项目文件:\n  {path}\n\n"
                        f"v1.30 改用文件夹格式存档(章节/大纲/设置分开),\n"
                        f"现在升级吗?\n\n"
                        f"  ✓ 是 → 自动转成文件夹结构(原 .json 备份保留)\n"
                        f"  ✗ 否 → 直接读旧格式(以后保存还会写文件夹)",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                    if ret == QMessageBox.Yes:
                        # 升级到新文件夹
                        json_p = Path(path)
                        target = json_p.parent / json_p.stem
                        # 如果同名文件夹已存在,追加 _migrated
                        if target.exists() and target.is_dir():
                            target = json_p.parent / (json_p.stem + "_migrated")
                        project_io.migrate_legacy_json(json_p, target)
                        d = project_io.load_project_folder(target)
                        self.current_project_file = str(target.resolve())
                        try:
                            from PyQt5.QtCore import QSettings
                            QSettings("NovelAI", "UI").setValue(
                                "last_project_path", self.current_project_file)
                        except Exception:
                            pass
                        # v1.41: 推到最近项目列表
                        self._push_to_recent(self.current_project_file)
                        self.tab_generation.log(
                            f"📂 旧 .json 已升级为文件夹: {target}", "success")
                        QMessageBox.information(
                            self, "升级完成",
                            f"已升级到文件夹结构:\n  {target}\n\n"
                            f"原 .json 保留在:\n  {target/'.legacy-original.json'}")
                    else:
                        # 不升级,直接读
                        d = json.loads(Path(path).read_text(encoding="utf-8"))
                        self.current_project_file = path
                else:
                    QMessageBox.warning(
                        self, "格式无法识别",
                        f"路径不是项目文件夹也不是 .json:\n{path}")
                    return
            except Exception as e:
                QMessageBox.critical(
                    self, "打开失败",
                    f"加载项目失败:{e}\n\n路径: {path}")
                return
            self._load_payload_into_ui(d)
            return

        # 兜底:project_io 不可用(理论上不会),走老路径
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            self.current_project_file = path
            self._load_payload_into_ui(d)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开失败:{e}")

    def _reset_ui_state(self):
        """v1.60 BUG-050: 切项目/新建项目前显式清空所有 UI 状态
        各 tab 的 load 方法多有 'if 空则不动' 的早返回逻辑,
        所以必须在这里直接清,不能依赖 load_from_dict({})。
        """
        # 1. 章节列表 + 编辑器
        self.chapters = []
        self.current_chapter_index = -1
        try:
            self.tab_editor.load_chapter("", "")
        except Exception:
            pass

        # 2. 创作设置 — title + inspiration + 所有高级选项
        try:
            self.tab_settings.title_input.clear()
            self.tab_settings.inspiration_edit.clear()
            # 重置高级选项到默认值(题材/平台/章节数等)
            # 用 _apply_advanced 传空 dict 触发默认值,但要确保 _apply_advanced 处理空 dict
            self._apply_advanced({})
        except Exception as _e:
            print(f"[_reset] settings 清空异常: {_e}", flush=True)

        # 3. 大纲 — 6 个文本框 + intro + special
        try:
            for w in (
                self.tab_outline.seed_edit,
                self.tab_outline.worldview_edit,
                self.tab_outline.lo_edit,
                self.tab_outline.structure_edit,
                self.tab_outline.chapter_outline_edit,
                self.tab_outline.intro_edit,
                self.tab_outline.special_edit,
            ):
                w.clear()
        except Exception as _e:
            print(f"[_reset] outline 清空异常: {_e}", flush=True)

        # 4. 对话记忆 — 3 个文本框 + 4 个开关
        try:
            self.tab_memory.chars_edit.clear()
            self.tab_memory.summaries_edit.clear()
            self.tab_memory.long_term_edit.clear()
            if hasattr(self.tab_memory, "preview_edit"):
                self.tab_memory.preview_edit.clear()
            self.tab_memory.auto_summarize.setChecked(True)
            self.tab_memory.auto_inject.setChecked(True)
            self.tab_memory.recent_n.setValue(3)
            self.tab_memory.summary_len.setValue(80)
        except Exception as _e:
            print(f"[_reset] memory 清空异常: {_e}", flush=True)

        # 5. Canon — 文本 + 3 个开关
        try:
            if hasattr(self.tab_canon, "canon_edit"):
                self.tab_canon.canon_edit.clear()
            if hasattr(self.tab_canon, "chk_inject"):
                self.tab_canon.chk_inject.setChecked(True)
                self.tab_canon.chk_audit.setChecked(True)
                self.tab_canon.chk_extract.setChecked(True)
        except Exception as _e:
            print(f"[_reset] canon 清空异常: {_e}", flush=True)

        # 6. 全部库(charlib) — v2.21.3 BUG-078:旧版只清 5 个表且两个名字写错(tbl_rel/tbl_foreshadows 不存在,
        # 应是 tbl_relations/tbl_fore),导致新建项目时关系/伏笔/承诺等 10+ 个表都还留着老数据,
        # AI 写新章节时 build_inject_block 注入了老角色,出现"新项目串老剧情"
        try:
            if hasattr(self, "tab_charlib"):
                _cl = self.tab_charlib
                # 全部 13 个表全清(对齐 serialize 的列表)
                for tbl_attr in (
                    "tbl_chars", "tbl_relations", "tbl_timeline",
                    "tbl_items", "tbl_power", "tbl_fore",
                    "tbl_promises", "tbl_arcs", "tbl_rel_values",
                    "tbl_goals", "tbl_infos", "tbl_known_by",
                    "tbl_hooks", "tbl_cool",
                ):
                    tbl = getattr(_cl, tbl_attr, None)
                    if tbl is not None:
                        tbl.setRowCount(0)
                # 主角当前状态 5 个字段也要清(否则老项目的"傅恬恬·18岁·练气期"会被注入新项目)
                if hasattr(_cl, "hero_age"):
                    _cl.hero_age.setText("18")
                if hasattr(_cl, "hero_realm"):
                    _cl.hero_realm.setText("")
                if hasattr(_cl, "hero_location"):
                    _cl.hero_location.setText("")
                if hasattr(_cl, "hero_faction"):
                    _cl.hero_faction.setText("")
                if hasattr(_cl, "hero_mood"):
                    _cl.hero_mood.setText("")
                # POV 模式回到默认值(角色 POV 的角色名也清)
                if hasattr(_cl, "cb_pov_mode"):
                    _cl.cb_pov_mode.setCurrentText("全知视角")
                if hasattr(_cl, "le_pov_character"):
                    _cl.le_pov_character.clear()
                # 剧情树 (QTreeWidget,不是 QTableWidget)
                if hasattr(_cl, "tree_plot"):
                    _cl.tree_plot.clear()
        except Exception as _e:
            print(f"[_reset] charlib 清空异常: {_e}", flush=True)

        # 7. 技能库
        try:
            if hasattr(self.tab_skills, "skills"):
                self.tab_skills.skills = []
            if hasattr(self.tab_skills, "_refresh_list"):
                self.tab_skills._refresh_list()
        except Exception as _e:
            print(f"[_reset] skills 清空异常: {_e}", flush=True)

        # 8. 章节质量校验配置(critique) — 5 个 checkbox 默认值
        try:
            self.tab_generation.chk_crit_words.setChecked(True)
            self.tab_generation.chk_crit_hook.setChecked(True)
            self.tab_generation.chk_crit_canon.setChecked(True)
            self.tab_generation.chk_crit_rhythm.setChecked(False)
            self.tab_generation.chk_crit_char.setChecked(False)
        except Exception as _e:
            print(f"[_reset] critique 清空异常: {_e}", flush=True)

        # 9. 对话槽(conv_slots)
        try:
            cs = self.tab_generation.conv_switcher
            cs.slots = []
            cs._active_slot_idx = -1
            if hasattr(cs, "active_label"):
                cs.active_label.setText("(未绑定槽)")
            if hasattr(cs, "_refresh_list"):
                cs._refresh_list()
        except Exception as _e:
            print(f"[_reset] conv_slots 清空异常: {_e}", flush=True)

        # 10. 寿元/伏笔
        try:
            if LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None:
                if hasattr(self.tab_lifespan, "load_from_dict"):
                    # lifespan 的 load 应该能处理空 dict
                    self.tab_lifespan.load_from_dict({})
        except Exception as _e:
            print(f"[_reset] lifespan 清空异常: {_e}", flush=True)

        # 10.5 v2.21.4 BUG-080:伏笔 Tab(独立 Tab) — mw.open_loops + UI
        try:
            self.open_loops = {}
            if hasattr(self, "tab_foreshadow"):
                _ft = self.tab_foreshadow
                if hasattr(_ft, "table"):
                    _ft.table.setRowCount(0)
                if hasattr(_ft, "chk_enabled"):
                    _ft.chk_enabled.setChecked(False)
                if hasattr(_ft, "spin_warn"):
                    _ft.spin_warn.setValue(80)
                if hasattr(_ft, "spin_critical"):
                    _ft.spin_critical.setValue(150)
        except Exception as _e:
            print(f"[_reset] open_loops 清空异常: {_e}", flush=True)

        # 11. 刷新章节列表 UI
        try:
            self._refresh_chapter_list()
        except Exception:
            pass

        print("[_reset] ✓ UI 状态已全部清空", flush=True)

    def _load_payload_into_ui(self, d: dict):
        """v1.30:从 payload(可能来自文件夹或旧 .json)还原所有 UI 状态
        抽出来作为统一接口,文件夹路径和老路径都能复用
        v1.60 BUG-050: 加载前先清空 UI 防止旧项目状态残留
        """
        self._reset_ui_state()
        self.chapters = d.get("chapters", [])
        # v1.92 BUG-066:旧存档无 locked 字段 → 兜底 False(向后兼容)
        for _ch in self.chapters:
            if isinstance(_ch, dict):
                _ch.setdefault("locked", False)
        self.tab_settings.title_input.setText(d.get("title", ""))
        self.tab_settings.inspiration_edit.setPlainText(d.get("inspiration", ""))
        self.tab_outline.seed_edit.setPlainText(d.get("seed", ""))
        self.tab_outline.worldview_edit.setPlainText(d.get("worldview", ""))
        self.tab_outline.lo_edit.setPlainText(d.get("lo", ""))
        self.tab_outline.structure_edit.setPlainText(d.get("structure", ""))
        self.tab_outline.chapter_outline_edit.setPlainText(d.get("chapter_outline", ""))
        self.tab_outline.intro_edit.setPlainText(d.get("intro", ""))
        # 还原高级设定
        adv = d.get("advanced", {})
        if adv:
            self._apply_advanced(adv)
        # 还原对话记忆
        mem = d.get("memory", {})
        if mem:
            self.tab_memory.chars_edit.setPlainText(mem.get("characters", ""))
            self.tab_memory.summaries_edit.setPlainText(mem.get("summaries", ""))
            self.tab_memory.long_term_edit.setPlainText(mem.get("long_term", ""))
            self.tab_memory.auto_summarize.setChecked(mem.get("auto_summarize", True))
            self.tab_memory.auto_inject.setChecked(mem.get("auto_inject", True))
            self.tab_memory.recent_n.setValue(int(mem.get("recent_n", 3)))
            self.tab_memory.summary_len.setValue(int(mem.get("summary_len", 80)))
        # 还原 Canon
        if d.get("canon"):
            self.tab_canon.load_from_dict(d["canon"])
        # 还原 6 库(charlib)
        if d.get("charlib") and hasattr(self, "tab_charlib"):
            try:
                self.tab_charlib.load(d["charlib"])
            except Exception as _e:
                print(f"[加载] charlib 还原失败: {_e}", flush=True)
        # 还原技能库
        if d.get("skills"):
            self.tab_skills.load_from_dict(d["skills"])
        # 还原章节质量校验配置
        crit = d.get("critique", {})
        if crit:
            self.tab_generation.chk_crit_words.setChecked(crit.get("word_count", True))
            self.tab_generation.chk_crit_hook.setChecked(crit.get("hook", True))
            self.tab_generation.chk_crit_canon.setChecked(crit.get("canon", True))
            self.tab_generation.chk_crit_rhythm.setChecked(crit.get("rhythm", False))
            self.tab_generation.chk_crit_char.setChecked(crit.get("character", False))
        # 还原对话槽
        if d.get("conv_slots"):
            self.tab_generation.conv_switcher.load_from_dict(d["conv_slots"])
        # 寿元/伏笔
        if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None
                and d.get("lifespan_loops")):
            self.tab_lifespan.load_from_dict(d["lifespan_loops"])
        # v2.21.4 BUG-080:还原伏笔 Tab 数据(之前完全没读,导致重启丢失)
        try:
            ol = d.get("open_loops")
            if ol:
                self.open_loops = ol
                if hasattr(self, "tab_foreshadow") and hasattr(self.tab_foreshadow, "sync_from_mw"):
                    self.tab_foreshadow.sync_from_mw()
        except Exception as _e:
            print(f"[加载] open_loops 还原失败: {_e}", flush=True)
        self.current_chapter_index = -1
        self._refresh_chapter_list()
        # v1.41: 刷新项目主页
        try:
            if hasattr(self, "tab_home"):
                self.tab_home.refresh(self)
        except Exception:
            pass
        self.statusBar().showMessage(
            f"已打开:{self.current_project_file}", 3000)

    def _apply_advanced(self, adv):
        """根据存档还原创作设置中的高级选项"""
        s = self.tab_settings
        # 题材
        for n, cb in s.genre_checks.items():
            cb.setChecked(n in adv.get("genres", []))
        # 单选项
        def _set_radio(group, value):
            for b in group.buttons():
                if b.text() == value:
                    b.setChecked(True); return
        _set_radio(s.platform_group, adv.get("platform", "番茄小说"))
        _set_radio(s.audience_group, adv.get("audience", "成人"))
        _set_radio(s.density_group, adv.get("density", "极致爽"))
        _set_radio(s.growth_group, adv.get("growth", "爆发型"))
        _set_radio(s.conflict_group, adv.get("conflict", "极端"))
        _set_radio(s.detail_group, adv.get("outline_detail", "详细"))
        _set_radio(s.rhythm_group, adv.get("rhythm", "适中"))
        _set_radio(s.mode_group, adv.get("creation_mode", "创造版"))
        # 数值
        s.era_custom.setText(adv.get("era", "古代王朝"))
        s.chapter_custom.setValue(int(adv.get("chapter_count", 300)))
        s.words_custom.setValue(int(adv.get("words_per_chapter", 3000)))
        s.prompt_offset.setValue(int(adv.get("prompt_offset", -200)))
        # 风格滑块
        for n, v in adv.get("style_weights", {}).items():
            if n in s.style_sliders:
                s.style_sliders[n].setValue(int(v))
        # 多选
        for n, cb in s.ending_checks.items():
            cb.setChecked(n in adv.get("endings", []))
        for n, cb in s.golden_checks.items():
            cb.setChecked(n in adv.get("golden_fingers", []))
        for n, cb in s.persona_checks.items():
            cb.setChecked(n in adv.get("personas", []))


    def save_project(self):
        """v1.30 新存档:保存到文件夹结构(by project_io)
        如果当前是旧 .json 路径 → 保存时升级到文件夹
        """
        if 0 <= self.current_chapter_index < len(self.chapters):
            self.chapters[self.current_chapter_index]["title"] = self.tab_editor.title_input.text()
            self.chapters[self.current_chapter_index]["content"] = self.tab_editor.content_edit.toPlainText()
        # v2.21.4 BUG-080:保存前先把伏笔 Tab 的 UI 同步到 mw.open_loops
        try:
            if hasattr(self, "tab_foreshadow") and hasattr(self.tab_foreshadow, "sync_to_mw"):
                self.tab_foreshadow.sync_to_mw()
        except Exception:
            pass
        if not self.current_project_file:
            # 用户没指定路径 → 默认 <project_dir>/<书名>/(文件夹)
            title = self.tab_settings.get_title() or "未命名项目"
            import re as _re
            safe = _re.sub(r'[\\/:*?"<>|]', '_', title).strip() or "untitled"
            default_folder = self.project_dir / safe
            # 询问用户:用默认还是自己选
            path = QFileDialog.getExistingDirectory(
                self, "选择保存位置(选项目文件夹,不存在会自动创建)",
                str(default_folder))
            if not path:
                # 用户取消 → fallback 默认位置
                if QMessageBox.question(
                    self, "保存到默认位置?",
                    f"未选择路径,要保存到默认位置吗?\n\n{default_folder}",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes) != QMessageBox.Yes:
                    return
                path = str(default_folder)
            self.current_project_file = path
        s = self.tab_settings
        d = {
            "title": s.get_title(),
            "inspiration": s.get_inspiration(),
            "seed": self.tab_outline.seed_edit.toPlainText(),
            "worldview": self.tab_outline.worldview_edit.toPlainText(),
            "lo": self.tab_outline.lo_edit.toPlainText(),
            "structure": self.tab_outline.structure_edit.toPlainText(),
            "chapter_outline": self.tab_outline.chapter_outline_edit.toPlainText(),
            "intro": self.tab_outline.intro_edit.toPlainText(),
            "chapters": self.chapters,
            # 对话记忆
            "memory": {
                "characters": self.tab_memory.chars_edit.toPlainText(),
                "summaries": self.tab_memory.summaries_edit.toPlainText(),
                "long_term": self.tab_memory.long_term_edit.toPlainText(),
                "auto_summarize": self.tab_memory.auto_summarize.isChecked(),
                "auto_inject": self.tab_memory.auto_inject.isChecked(),
                "recent_n": self.tab_memory.recent_n.value(),
                "summary_len": self.tab_memory.summary_len.value(),
            },
            # B 模块:Canon 设定档
            "canon": self.tab_canon.serialize_for_save(),
            # 🎭 角色库 + 关系 + 时间线 + 物品 + 伏笔
            "charlib": self.tab_charlib.serialize() if hasattr(self, "tab_charlib") else {},
            # D 模块:技能库
            "skills": self.tab_skills.serialize_for_save(),
            # C 模块:章节质量校验配置
            "critique": self.tab_generation.critique_config(),
            # E 模块:对话槽
            "conv_slots": self.tab_generation.conv_switcher.serialize_for_save(),
            # 寿元/伏笔(可选模块)
            "lifespan_loops": (
                self.tab_lifespan.serialize_for_save()
                if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None)
                else {}
            ),
            # v2.21.4 BUG-080:伏笔 Tab 数据(之前完全没存,重启就丢)
            "open_loops": (
                getattr(self, "open_loops", {}) or {}
            ),
            # 高级设定
            "advanced": {
                "genres": s.get_selected_genres(),
                "platform": s.get_platform(),
                "audience": s.get_audience(),
                "density": s.get_density(),
                "growth": s.get_growth(),
                "conflict": s.get_conflict(),
                "era": s.get_era(),
                "chapter_count": s.get_chapter_count(),
                "words_per_chapter": s.get_words_per_chapter(),
                "outline_detail": s.get_outline_detail(),
                "style_weights": s.get_style_weights(),
                "rhythm": s.get_rhythm(),
                "endings": s.get_endings(),
                "creation_mode": s.get_creation_mode(),
                "prompt_offset": s.get_prompt_offset(),
                "golden_fingers": s.get_golden_fingers(),
                "personas": s.get_personas(),
                "ai": s.get_selected_ai(),
            },
            "saved_at": datetime.now().isoformat(),
        }
        try:
            target = Path(self.current_project_file)
            # 路径判断:文件夹 vs .json
            if PROJECT_IO_AVAILABLE and (
                    not target.suffix or target.is_dir() or not target.exists()):
                # 走新文件夹格式
                # 先做整体 zip 备份(如果文件夹已存在)
                if target.is_dir():
                    try:
                        project_io.make_backup_zip(target, keep=10)
                    except Exception as _be:
                        print(f"[backup] zip 失败: {_be}", flush=True)
                project_io.save_project_folder(target, d)
                # v1.36 BUG-049: 保存成功后把路径存 QSettings
                try:
                    from PyQt5.QtCore import QSettings
                    QSettings("NovelAI", "UI").setValue(
                        "last_project_path", str(target.resolve()))
                except Exception:
                    pass
                # v1.41: 推到最近项目列表
                self._push_to_recent(str(target.resolve()))
                self.statusBar().showMessage(
                    f"已保存(文件夹):{target}", 3000)
                self.tab_generation.log(
                    f"💾 项目已保存到文件夹: {target}", "success")
            else:
                # 旧路径:单 .json 文件
                self._rotate_project_backups(self.current_project_file)
                Path(self.current_project_file).write_text(
                    json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                self.statusBar().showMessage(
                    f"已保存(.json):{self.current_project_file}", 3000)
        except Exception as e:
            import traceback
            QMessageBox.critical(
                self, "保存失败",
                f"无法写入项目:\n{self.current_project_file}\n\n错误:{e}\n\n"
                "请检查:1) 路径是否可写  2) 磁盘是否已满  3) 文件名是否合法")
            self.tab_generation.log(
                f"✗ 保存项目失败:{e}\n{traceback.format_exc()}", "error")

    def _rotate_project_backups(self, project_path: str, keep: int = 10):
        """第 2 项:在 .backups/ 子目录里保留最近 N 次保存的快照。
        命名:<项目名>.YYYYMMDD-HHMMSS.json  超过 keep 个的最老备份删除。"""
        try:
            p = Path(project_path)
            if not p.exists():
                return  # 第一次保存没旧文件可备份
            backup_dir = p.parent / ".backups"
            backup_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = backup_dir / f"{p.stem}.{ts}{p.suffix}"
            backup_path.write_bytes(p.read_bytes())
            # 清理超过 keep 个的旧备份(只清同名前缀的)
            siblings = sorted(
                backup_dir.glob(f"{p.stem}.*{p.suffix}"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            for old in siblings[keep:]:
                try:
                    old.unlink()
                except Exception:
                    pass
        except Exception:
            pass  # 备份失败不影响主保存

    def restore_project_backup(self):
        """从 .backups/ 里挑一个 zip 版本恢复"""
        if not self.current_project_file:
            QMessageBox.information(self, "提示", "当前没有打开的项目")
            return
        p = Path(self.current_project_file)
        # 新格式: 项目文件夹/.backups/backup-*.zip
        backup_dir = p / ".backups"
        if not backup_dir.exists():
            # 兼容: 也试父目录
            backup_dir = p.parent / ".backups"
        if not backup_dir.exists():
            QMessageBox.information(self, "提示",
                f"备份目录不存在:\n{p / '.backups'}\n\n"
                f"备份在每次保存时自动创建(最多保留10个)。\n"
                f"请先保存一次项目。")
            return
        backups = sorted(
            backup_dir.glob("backup-*.zip"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if not backups:
            QMessageBox.information(self, "提示",
                f"备份目录存在但没有 zip 文件:\n{backup_dir}")
            return
        from datetime import datetime
        items = [f"{i+1}. {b.name}  ({datetime.fromtimestamp(b.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')})"
                 for i, b in enumerate(backups)]
        choice, ok = QInputDialog.getItem(
            self, "选择恢复版本",
            f"从最近 {len(backups)} 个备份里选:",
            items, 0, False)
        if not ok or not choice:
            return
        idx = items.index(choice)
        chosen = backups[idx]
        ret = QMessageBox.question(
            self, "确认恢复",
            f"将用以下备份覆盖当前项目:\n\n{chosen.name}\n\n"
            f"当前项目会先备份。继续?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        try:
            import zipfile, shutil
            # 先备份当前版本
            if PROJECT_IO_AVAILABLE:
                project_io.make_backup_zip(p, keep=15)
            # 解压恢复
            with zipfile.ZipFile(chosen, 'r') as z:
                # 清空项目文件夹(保留.backups)
                for item in p.iterdir():
                    if item.name == ".backups":
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                z.extractall(p)
            self.tab_generation.log(
                f"✅ 已恢复备份: {chosen.name}", "success")
            # 重新加载
            if PROJECT_IO_AVAILABLE:
                d = project_io.load_project_folder(p)
                self._load_payload_into_ui(d)
                self._refresh_chapter_list()
            QMessageBox.information(self, "恢复完成",
                f"已恢复: {chosen.name}\n项目数据已重新加载。")
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

    def new_directory(self):
        name, ok = QInputDialog.getText(self, "新建目录", "目录名:")
        if ok and name:
            (self.project_dir / name).mkdir(exist_ok=True)
            QMessageBox.information(self, "完成", f"目录已创建:{self.project_dir / name}")

    def back_directory(self):
        QMessageBox.information(self, "项目目录", str(self.project_dir))

    def toggle_lock(self):
        ro = self.tab_editor.content_edit.isReadOnly()
        self.tab_editor.content_edit.setReadOnly(not ro)
        self.tab_editor.title_input.setReadOnly(not ro)
        self.statusBar().showMessage("已解锁,可以编辑" if ro else "已锁定,只读模式", 3000)

    def show_font_scale_dialog(self):
        """界面字体大小对话框 — 从顶部菜单'设置 → 🔍 界面字体大小...' 弹出"""
        from PyQt5.QtCore import QSettings
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
            QDialogButtonBox, QApplication as _QA)
        dlg = QDialog(self)
        dlg.setWindowTitle("🔍 界面字体大小")
        dlg.setMinimumWidth(500)
        lay = QVBoxLayout(dlg)

        tip = QLabel(
            "调字体倍数 — 4K 屏 / 老花眼 / 看不清都用这个。\n"
            "拖滑块到你舒服的位置,点确定,**关闭程序重新打开**生效。\n"
            "(Qt 字体只能在启动时设,运行中没法即时变)")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#7a7a7a; padding:6px; background:#f4f4f4; border-radius:3px;")
        lay.addWidget(tip)

        # 读当前值
        s = QSettings("NovelAI", "CreationSettings")
        cur = s.value("font_scale", 0.0, type=float) or 0.0
        if cur < 0.5:
            cur = float(_QA.instance().property("_novelai_dpi_scale") or 1.0)

        row = QHBoxLayout()
        row.addWidget(QLabel("字体倍数:"))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(80, 220)         # ×0.80 ~ ×2.20
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(20)
        slider.setValue(int(round(cur * 100)))
        row.addWidget(slider, 1)
        lab = QLabel(f"×{cur:.2f}")
        lab.setMinimumWidth(60)
        lab.setStyleSheet("font-weight:bold; font-size:14px; color:#977242;")
        row.addWidget(lab)
        lay.addLayout(row)

        # 实时更新标签
        slider.valueChanged.connect(lambda v: lab.setText(f"×{v/100:.2f}"))

        # 常用预设
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("快速预设:"))
        for label, val in [("1.0(默认)", 100), ("1.25", 125),
                            ("1.5(推荐 4K)", 150), ("1.75", 175), ("2.0", 200)]:
            btn = QPushButton(label)
            btn.setMaximumWidth(110)
            btn.clicked.connect(lambda _, v=val: slider.setValue(v))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)

        if dlg.exec_() == QDialog.Accepted:
            v = slider.value() / 100.0
            s.setValue("font_scale", float(v))
            QMessageBox.information(
                self, "已保存",
                f"字体倍数 ×{v:.2f} 已保存。\n\n"
                f"请关闭程序后重新打开生效。")

    # ==================== DOM 诊断 / 拾取工具(BUG-018 配套) ====================
    def _show_plot_timeline(self):
        """🗺️ 剧情线地图"""
        canon_items = []
        try:
            import json as _json
            raw = self.tab_canon.canon_edit.toPlainText().strip()
            if raw:
                items = _json.loads(raw)
                if isinstance(items, list):
                    canon_items = items
        except Exception:
            pass
        show_plot_timeline(self, self.chapters, canon_items)

    def _run_reader_panel(self):
        """👥 模拟读者评审 — 选择读者类型,动态构建提示词"""
        text = ""
        try:
            text = self.tab_editor.content_edit.toPlainText().strip()
        except Exception:
            pass
        if not text:
            QMessageBox.information(self, "读者评审", "当前章节为空")
            return
        from ui.reader_panel import ReaderSelectDialog, build_reader_prompt
        dlg = ReaderSelectDialog(self)
        if dlg.exec_() != dlg.Accepted:
            return
        self._reader_panel_keys = dlg.selected
        prompt = build_reader_prompt(dlg.selected, text)
        count = len(dlg.selected)
        self.tab_generation.log(f"👥 正在模拟 {count} 种读者评审...", "info")
        self._send_to_ai(prompt, "读者评审", target="reader_panel")

    def _on_reader_panel_response(self, content):
        """处理读者评审结果"""
        from ui.reader_panel import parse_reader_response
        keys = getattr(self, "_reader_panel_keys", ["shuang", "love", "logic"])
        result = parse_reader_response(content, keys)
        QMessageBox.information(self, "👥 读者评审团", result)

    def _convert_to_script(self):
        """🎬 把当前章节转为短剧剧本"""
        text = ""
        try:
            text = self.tab_editor.content_edit.toPlainText().strip()
        except Exception:
            pass
        if not text:
            QMessageBox.information(self, "转剧本", "当前章节为空")
            return
        ch_idx = getattr(self.tab_editor, "current_index", 0)
        ch_title = self.chapters[ch_idx]["title"] if ch_idx < len(self.chapters) else "未知"
        word_count = len(text)
        content = text[:12000] if len(text) > 12000 else text
        self.tab_generation.log(
            f"🎬 正在把「{ch_title}」({word_count}字)转为 AI 分镜脚本...", "info")
        prompt = PROMPTS["novel_to_script"].format(
            content=content, word_count=word_count)
        self._send_to_ai(prompt, f"AI分镜-{ch_title}", target="novel_to_script")

    def _on_script_response(self, content):
        """处理剧本转换结果"""
        if not content or not content.strip():
            QMessageBox.warning(self, "转剧本", "AI 未返回剧本内容")
            return
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("🎬 AI 分镜脚本")
        dlg.resize(1100, 750)
        lay = QVBoxLayout(dlg)
        # 顶部提示
        from PyQt5.QtWidgets import QLabel
        tip = QLabel("✅ 分镜脚本生成完成。场景 JSON 可直接用于 AI 生图，视频提示词可用于可灵/Sora/Runway。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#4e79cd; font-size:12px; padding:4px;")
        lay.addWidget(tip)
        edit = QPlainTextEdit()
        edit.setPlainText(content.strip())
        edit.setReadOnly(False)
        edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', 'Microsoft YaHei'; font-size: 12px;")
        lay.addWidget(edit)
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("📋 复制全部")
        btn_copy.clicked.connect(lambda: (
            QApplication.clipboard().setText(edit.toPlainText()),
            self.tab_generation.log("📋 分镜脚本已复制", "info")))
        btn_save = QPushButton("💾 保存为 .txt")
        def _save_script():
            import os
            from PyQt5.QtWidgets import QFileDialog
            ch_idx_ = getattr(self.tab_editor, "current_index", 0)
            default_name = f"分镜脚本_{self.chapters[ch_idx_].get('title','第X章') if ch_idx_ < len(self.chapters) else '未命名'}.txt"
            path, _ = QFileDialog.getSaveFileName(
                dlg, "保存分镜脚本", default_name, "文本文件 (*.txt);;所有文件 (*)")
            if path:
                with open(path, "w", encoding="utf-8") as f_:
                    f_.write(edit.toPlainText())
                self.tab_generation.log(f"💾 分镜脚本已保存: {path}", "success")
        btn_save.clicked.connect(_save_script)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)
        self.tab_generation.log(
            f"🎬 AI 分镜脚本生成完成({len(content)} 字符，含场景 JSON + 分镜表格)", "success")
        dlg.exec_()

    # ── A/B 对比 ──

    def _start_ab_compare(self):
        """🤖 对当前章节重新生成一版，与现有版本对比"""
        ch_idx = getattr(self.tab_editor, "current_index", -1)
        if ch_idx < 0 or ch_idx >= len(self.chapters):
            QMessageBox.information(self, "A/B 对比", "请先选择一个章节")
            return
        current_text = self.chapters[ch_idx].get("content", "")
        if not current_text.strip():
            QMessageBox.information(self, "A/B 对比", "当前章节为空")
            return

        # 保存当前版本
        self._ab_compare_data = {
            "ch_idx": ch_idx,
            "version_a": current_text,
            "ch_num": ch_idx + 1,
        }

        ch_num = ch_idx + 1
        self.tab_generation.log(f"🤖 A/B 对比:正在为第{ch_num}章生成 B 版本...", "info")

        # 用"重写"提示词生成另一版本
        prompt = PROMPTS["ab_rewrite"].format(content=current_text[:8000])
        self._send_to_ai(prompt, f"A/B对比-第{ch_num}章", target="ab_compare")

    def _on_ab_compare_response(self, content):
        """B 版本生成完毕,弹出对比窗口"""
        data = getattr(self, "_ab_compare_data", None)
        if not data:
            return
        ch_num = data["ch_num"]
        ch_idx = data["ch_idx"]
        version_a = data["version_a"]
        version_b = (content or "").strip()

        if not version_b:
            QMessageBox.warning(self, "A/B 对比", "B 版本生成失败")
            return

        self.tab_generation.log(
            f"🤖 A/B 对比:B 版本生成完成({len(version_b)}字符)", "success")

        dlg = ABCompareDialog(
            f"A 版(当前) — 第{ch_num}章",
            version_a,
            f"B 版(新生成) — 第{ch_num}章",
            version_b,
            parent=self,
        )
        dlg.exec_()

        if dlg.picked == ABCompareDialog.PICK_B:
            # 用 B 版替换
            self.chapters[ch_idx]["content"] = version_b
            self.tab_editor.content_edit.setPlainText(version_b)
            self.tab_generation.log(
                f"✅ 已用 B 版替换第{ch_num}章", "success")
        elif dlg.picked == ABCompareDialog.PICK_A:
            self.tab_generation.log(
                f"✅ 保留 A 版(第{ch_num}章不变)", "info")
        else:
            self.tab_generation.log("取消对比", "info")

        self._ab_compare_data = None

    def _show_emotion_curve(self):
        """📊 查看全书情绪曲线"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("📊 情绪曲线")
        dlg.resize(900, 400)
        lay = QVBoxLayout(dlg)
        panel = EmotionCurvePanel()
        panel.load_from_chapters(self.chapters)
        warning = panel.load_from_chapters(self.chapters)
        lay.addWidget(panel)
        if warning:
            self.tab_generation.log(warning, "warn")
        # 统计
        scored = sum(1 for ch in self.chapters if ch.get("emotion_scores"))
        total = len(self.chapters)
        if scored == 0:
            from PyQt5.QtWidgets import QLabel
            hint = QLabel(f"暂无情绪数据(0/{total}章)。连续生成新章节后自动评分。")
            hint.setStyleSheet("color:#7a7a7a; padding:20px;")
            lay.addWidget(hint)
        dlg.exec_()

    # ── AI 智能取名 ──

    def _open_ai_naming(self):
        """打开 AI 取名对话框 — 从角色库+大纲+正文识别所有角色"""
        from ui.ai_naming import AINamingDialog
        import re as _re
        from collections import Counter

        char_set = {}  # name → role
        auto_name = ""

        # 1. 角色库(最可靠)
        try:
            tbl = self.tab_charlib.tbl_chars
            for r in range(tbl.rowCount()):
                name = (tbl.item(r, 0).text() if tbl.item(r, 0) else "").strip()
                role = (tbl.item(r, 1).text() if tbl.item(r, 1) else "").strip()
                if name:
                    char_set[name] = role or "配角"
                    if not auto_name and ("主角" in role or "男主" in role or "女主" in role):
                        auto_name = name
        except Exception:
            pass

        # 2. 大纲文本提取(找高频中文人名)
        outline_text = ""
        try:
            for edit in [
                self.tab_outline.seed_edit,
                self.tab_outline.worldview_edit,
                self.tab_outline.structure_edit,
                self.tab_outline.chapter_outline_edit,
            ]:
                outline_text += edit.toPlainText() + "\n"
        except Exception:
            pass

        # 3. 正文前5章也扫一遍
        for ch in self.chapters[:5]:
            outline_text += (ch.get("content") or "") + "\n"

        # 提取高频中文人名(出现≥3次)
        if outline_text:
            # 第一步: 提取2字人名(最可靠: 姓+名)
            candidates_2 = _re.findall(r'[\u4e00-\u9fff]{2}', outline_text)
            # 第二步: 提取3字人名(姓+名名,过滤掉姓名+动词)
            candidates_3 = _re.findall(r'[\u4e00-\u9fff]{3}', outline_text)
            freq = Counter(candidates_2 + candidates_3)
            # 常用词停用表
            _stop = {"但是", "因为", "所以", "如果", "可以", "已经", "什么", "没有",
                     "这个", "那个", "他们", "我们", "自己", "不是", "就是", "还是",
                     "一个", "出来", "进去", "时候", "知道", "觉得", "开始", "然后",
                     "现在", "这样", "那样", "怎么", "为什么", "突然", "终于", "于是",
                     "心里", "眼中", "手中", "身上", "面前", "身边", "之间", "之中",
                     "目光", "声音", "表情", "动作", "世界", "地方", "问题", "事情"}
            # 3字名末字不能是常见动词/副词/助词/介词
            _not_name_tail = set("的了在是不也都要会到把被给让跟"
                                 "说做看去来吃喝打拿走跑站坐骑飞"
                                 "想能用有过着得和对从向往比跟把"
                                 "很太更最还又再已才刚就只都没别"
                                 "吧吗呢啊哦呀嘛啦嗯哈哟呵嘿哼"
                                 "上下里外前后中内间旁边底顶头尾"
                                 "开关进出回起落举放收送拉推拖拽"
                                 "学教帮找买卖带领换穿脱洗切煮炒"
                                 "听问答叫喊笑哭骂踢拉拒扔抢偷")
            _surnames = set("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张"
                            "孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎"
                            "鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤"
                            "滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄穆"
                            "萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒"
                            "屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭林")
            for word, cnt in freq.most_common(80):
                if cnt >= 3 and word not in _stop and word not in char_set:
                    if word[0] not in _surnames:
                        continue
                    # 3字名: 末字不能是动词/助词
                    if len(word) == 3 and word[2] in _not_name_tail:
                        continue
                    char_set[word] = "大纲提取"

        char_list = [(name, role) for name, role in char_set.items()]
        # 角色库的排前面
        char_list.sort(key=lambda x: (0 if x[1] not in ("大纲提取",) else 1, x[0]))

        dlg = AINamingDialog(
            old_name=auto_name, char_list=char_list, parent=self)
        self._naming_dlg = dlg
        dlg.finished.connect(self._on_naming_dlg_closed)
        dlg.show()

    def _on_naming_dlg_closed(self, result_code):
        """取名对话框关闭 → 如果选了名字就全文替换"""
        dlg = getattr(self, "_naming_dlg", None)
        if not dlg:
            return
        if result_code == QDialog.Accepted:
            result = dlg.get_result()
            if result:
                self._do_global_rename(result)
        self._naming_dlg = None

    def _on_ai_naming_response(self, content):
        """AI 返回名字列表 → 更新对话框"""
        dlg = getattr(self, "_naming_dlg", None)
        if dlg and dlg.isVisible():
            dlg.on_names_received(content)

    def _do_global_rename(self, result):
        """全文替换角色名 — 带预览确认"""
        if not result:
            return
        old_name, new_name = result

        # ── 收集所有出现位置 ──
        occurrences = []  # [(source_label, context_text, index_in_source), ...]

        # 章节
        for i, ch in enumerate(self.chapters):
            for key in list(ch.keys()):
                val = ch[key]
                if isinstance(val, str) and old_name in val:
                    for m in __import__('re').finditer(__import__('re').escape(old_name), val):
                        start = max(0, m.start() - 15)
                        end = min(len(val), m.end() + 15)
                        ctx = val[start:end].replace('\n', ' ')
                        occurrences.append((
                            f"第{i+1}章.{key}", ctx, m.start()))

        # 大纲
        outline_edits = []
        try:
            outline_edits = [
                ("简介", self.tab_outline.intro_edit),
                ("故事种子", self.tab_outline.seed_edit),
                ("世界观", self.tab_outline.worldview_edit),
                ("LO层", self.tab_outline.lo_edit),
                ("故事结构", self.tab_outline.structure_edit),
                ("章节大纲", self.tab_outline.chapter_outline_edit),
                ("特殊需求", self.tab_outline.special_edit),
            ]
        except Exception:
            pass
        for label, edit in outline_edits:
            text = edit.toPlainText()
            if old_name in text:
                for m in __import__('re').finditer(
                        __import__('re').escape(old_name), text):
                    start = max(0, m.start() - 15)
                    end = min(len(text), m.end() + 15)
                    ctx = text[start:end].replace('\n', ' ')
                    occurrences.append((f"大纲.{label}", ctx, m.start()))

        if not occurrences:
            QMessageBox.information(self, "替换",
                f"没有找到「{old_name}」")
            return

        # ── 弹出预览对话框 ──
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
            QCheckBox, QScrollArea, QWidget, QPushButton, QLabel)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🔍 预览替换: 「{old_name}」→「{new_name}」")
        dlg.resize(700, 500)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"找到 {len(occurrences)} 处「{old_name}」,取消勾选不想替换的:"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        clayout = QVBoxLayout(container)
        checks = []
        for src, ctx, pos in occurrences:
            highlighted = ctx.replace(
                old_name, f"【{old_name}→{new_name}】")
            chk = QCheckBox(f"[{src}] ...{highlighted}...")
            chk.setChecked(True)
            chk.setStyleSheet("font-size:12px; padding:2px;")
            clayout.addWidget(chk)
            checks.append(chk)
        clayout.addStretch()
        scroll.setWidget(container)
        lay.addWidget(scroll)

        # 按钮
        btn_row = QHBoxLayout()
        btn_all = QPushButton(f"全选({len(checks)})")
        btn_all.clicked.connect(lambda: [c.setChecked(True) for c in checks])
        btn_row.addWidget(btn_all)
        btn_none = QPushButton("全不选")
        btn_none.clicked.connect(lambda: [c.setChecked(False) for c in checks])
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        btn_ok = QPushButton(f"✅ 替换勾选的")
        btn_ok.setStyleSheet(
            "QPushButton { background:#1f8b4d; color:white; padding:8px 16px;"
            "font-weight:bold; border-radius:4px; }")
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        if dlg.exec_() != QDialog.Accepted:
            return

        # ── 按勾选执行替换(从后往前,避免偏移) ──
        # 按 source 分组
        to_replace = {}
        for i, (src, ctx, pos) in enumerate(occurrences):
            if checks[i].isChecked():
                to_replace.setdefault(src, []).append(pos)

        count = 0
        # 章节替换
        for i, ch in enumerate(self.chapters):
            for key in list(ch.keys()):
                val = ch[key]
                if not isinstance(val, str):
                    continue
                positions = to_replace.get(f"第{i+1}章.{key}", [])
                if not positions:
                    continue
                # 从后往前替换
                for pos in sorted(positions, reverse=True):
                    val = val[:pos] + new_name + val[pos+len(old_name):]
                ch[key] = val
                count += 1

        # 大纲替换
        for label, edit in outline_edits:
            positions = to_replace.get(f"大纲.{label}", [])
            if not positions:
                continue
            text = edit.toPlainText()
            for pos in sorted(positions, reverse=True):
                text = text[:pos] + new_name + text[pos+len(old_name):]
            edit.setPlainText(text)
            count += 1

        # 角色库/记忆/Canon — 这些全量替换(没有同名冲突风险)
        try:
            tbl = self.tab_charlib.tbl_chars
            for r in range(tbl.rowCount()):
                for c in range(tbl.columnCount()):
                    item = tbl.item(r, c)
                    if item and old_name in item.text():
                        item.setText(item.text().replace(old_name, new_name))
        except Exception:
            pass
        try:
            mem = self.tab_memory.memory_edit.toPlainText()
            if old_name in mem:
                self.tab_memory.memory_edit.setPlainText(
                    mem.replace(old_name, new_name))
        except Exception:
            pass
        try:
            canon = self.tab_canon.canon_edit.toPlainText()
            if old_name in canon:
                self.tab_canon.canon_edit.setPlainText(
                    canon.replace(old_name, new_name))
        except Exception:
            pass

        selected = sum(1 for c in checks if c.isChecked())
        self._refresh_chapter_list()
        if 0 <= self.current_chapter_index < len(self.chapters):
            ch = self.chapters[self.current_chapter_index]
            self.tab_editor.load_chapter(
                ch.get("title", ""), ch.get("content", ""))
        self.tab_generation.log(
            f"🎭 精准替换:「{old_name}」→「{new_name}」"
            f"({selected}/{len(occurrences)}处)", "success")

    def show_dom_diagnostics(self):
        """🔬 诊断当前 AI 网页 DOM:看每个选择器在当前页命中了多少元素"""
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并打开 AI 网站")
            return
        # 在 worker 线程跑(driver 必须在 worker 线程访问)
        # 用一个简单的 deferred:postEvent / Queue 都行,这里用 invokeMethod
        from PyQt5.QtCore import QMetaObject, Qt, Q_RETURN_ARG
        # 简单点:同步走 — DOM 诊断很快,worker 当前如果不忙,直接调
        try:
            result = self.worker.run_dom_diagnostics()
        except Exception as e:
            QMessageBox.critical(self, "诊断失败", str(e))
            return
        # 渲染结果对话框
        dlg = QDialog(self)
        dlg.setWindowTitle("🔬 DOM 诊断结果")
        dlg.resize(800, 600)
        lay = QVBoxLayout(dlg)
        if "__error__" in result:
            lay.addWidget(QLabel(f"<b>诊断失败:</b>{result['__error__']}"))
        else:
            ov = result.get("__overview__", {})
            top = QLabel(
                f"<h3>页面概况</h3>"
                f"<p><b>URL:</b>{ov.get('url', '?')}</p>"
                f"<p><b>标题:</b>{ov.get('title', '?')}</p>"
                f"<p><b>页面统计:</b>textarea×{ov.get('total_textareas', 0)},"
                f"contenteditable×{ov.get('total_contenteditable', 0)},"
                f"button×{ov.get('total_buttons', 0)}"
                f"<br>DeepSeek 特有:ds-markdown×{ov.get('ds_markdown_count', 0)},"
                f"ds-assistant-message-main-content×{ov.get('ds_assistant_count', 0)}</p>")
            top.setTextFormat(Qt.RichText)
            top.setWordWrap(True)
            lay.addWidget(top)
            # 详细结果
            txt = QPlainTextEdit()
            txt.setReadOnly(True)
            txt.setStyleSheet("font-family:monospace; font-size:12px;")
            lines = ["<选择器诊断>\n" + "=" * 60]
            for name, info in result.items():
                if name == "__overview__":
                    continue
                sel = info.get("selector", "")
                cnt = info.get("count", 0)
                err = info.get("error", "")
                flag = "✓" if cnt > 0 else ("✗" if not err else "⚠")
                lines.append(f"\n[{flag}] {name}")
                lines.append(f"  选择器: {sel}")
                if err:
                    lines.append(f"  错误: {err}")
                else:
                    lines.append(f"  命中: {cnt} 个")
                    for j, s in enumerate(info.get("samples", [])):
                        vis = "可见" if s.get("visible") else "隐藏"
                        lines.append(f"    [{j}] <{s['tag']}.{s['class']}> [{vis}] '{s['text']}'")
            txt.setPlainText("\n".join(lines))
            lay.addWidget(txt, 1)
        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_pick = QPushButton("🎯 改用现场拾取")
        btn_pick.clicked.connect(lambda: (dlg.accept(), self.start_dom_picker()))
        btn_pick.setStyleSheet(
            "QPushButton { background:#b8651b; color:white; padding:6px 14px; "
            "border-radius:3px; font-weight:bold; }")
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_pick)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)
        dlg.exec_()

    def start_dom_picker(self):
        """🎯 现场拾取:在浏览器开 picker,用户 hover/点击,Python 端轮询读结果"""
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器并打开 AI 网页")
            return
        ok = self.worker.install_dom_picker()
        if not ok:
            QMessageBox.warning(self, "安装失败", "JS 注入失败,请确认浏览器已挂载到 AI 网页")
            return
        # 弹引导对话框,用户每点一次 "采集刚才点的",就读一次 picked
        dlg = QDialog(self)
        dlg.setWindowTitle("🎯 现场拾取选择器")
        dlg.setMinimumWidth(700)
        lay = QVBoxLayout(dlg)
        guide = QLabel(
            "<h3>用法</h3>"
            "<ol>"
            "<li>切到浏览器(挂载的 AI 网页)</li>"
            "<li>鼠标 hover 各元素,左上角蓝条会显示建议的选择器</li>"
            "<li>点击 <b>输入框</b> / <b>发送按钮</b> / <b>AI 回复区</b> 任一</li>"
            "<li>回到这里,点下方对应的[采集...为...]按钮,把刚点的选择器存到对应字段</li>"
            "<li>采集完点【💾 保存覆盖】生效</li>"
            "<li>浏览器里按 ESC 退出拾取模式</li>"
            "</ol>")
        guide.setWordWrap(True)
        guide.setStyleSheet("background:#f5f5f5; color:#3a3f47; padding:10px; border-radius:3px;")
        lay.addWidget(guide)

        # 当前已采集的字段
        url = self.tab_generation.url_input.text() or "?"
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        lay.addWidget(QLabel(f"<b>目标站点:</b>{host}"))

        # 三个字段的"采集到此"
        fields = {}
        for key, label in [("input", "输入框"), ("send_btn", "发送按钮"), ("response", "AI 回复区"),
                            ("stop_btn", "停止按钮(可选)")]:
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText(f"<未采集 {label} 的选择器>")
            row.addWidget(QLabel(f"{label}:"))
            row.addWidget(edit, 1)
            btn = QPushButton(f"📥 用刚点击的元素填入")
            btn.setStyleSheet("QPushButton { background:#3498db; color:white; padding:4px 8px; }")
            def make_cap(e=edit, k=key, l=label):
                def _cap():
                    p = self.worker.get_picked_selector()
                    if p:
                        e.setText(p.get("selector", ""))
                        QMessageBox.information(
                            dlg, "✓ 已采集",
                            f"{l} 选择器:\n{p.get('selector')}\n命中 {p.get('count')} 个元素")
                    else:
                        QMessageBox.warning(
                            dlg, "没采到",
                            f"还没在浏览器里点元素,请先去浏览器 hover + 点{l}")
                return _cap
            btn.clicked.connect(make_cap())
            row.addWidget(btn)
            fields[key] = edit
            lay.addLayout(row)

        # 保存按钮
        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 保存覆盖到 QSettings(立即生效)")
        btn_save.setStyleSheet(
            "QPushButton { background:#1f8b4d; color:white; padding:8px 16px; "
            "border-radius:3px; font-weight:bold; }")
        def _save():
            overrides = {k: e.text().strip() for k, e in fields.items() if e.text().strip()}
            if not overrides:
                QMessageBox.warning(dlg, "提示", "至少要填一个选择器")
                return
            self._apply_site_profile_override(host, overrides)
            QMessageBox.information(
                dlg, "✓ 已保存",
                f"{host} 选择器覆盖已保存。\n"
                f"立即生效,下次发消息会用新选择器。\n"
                f"覆盖项:{list(overrides.keys())}")
            dlg.accept()
        btn_save.clicked.connect(_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        dlg.exec_()

    def _apply_site_profile_override(self, host, overrides):
        """把用户拾取的选择器覆盖到运行时 SITE_PROFILES + 持久化到 QSettings"""
        global SITE_PROFILES
        # 找最匹配的 host key
        match_key = None
        for hk in SITE_PROFILES:
            if hk in host or host.endswith(hk):
                match_key = hk
                break
        if not match_key:
            # 新建一份(复制 _default 当底)
            match_key = host
            base = dict(SITE_PROFILES.get("_default", {}))
            base["name"] = host
            SITE_PROFILES[match_key] = base
        # 应用覆盖
        for k, v in overrides.items():
            SITE_PROFILES[match_key][k] = v
        # 持久化
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "SiteProfiles")
        for k, v in overrides.items():
            s.setValue(f"{match_key}/{k}", v)
        self.tab_generation.log(
            f"✓ 已更新 {match_key} 选择器:{list(overrides.keys())}", "success")

    def _load_site_profile_overrides(self):
        """启动时加载用户在 QSettings 里存的选择器覆盖"""
        global SITE_PROFILES
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "SiteProfiles")
        for host in list(SITE_PROFILES.keys()) + ['__custom__']:
            s.beginGroup(host)
            for k in s.childKeys():
                v = s.value(k)
                if v:
                    if host not in SITE_PROFILES:
                        SITE_PROFILES[host] = dict(SITE_PROFILES.get("_default", {}))
                    SITE_PROFILES[host][k] = v
            s.endGroup()

    def edit_site_profile_override(self):
        """📝 手动编辑当前站点选择器(高级用户)"""
        url = self.tab_generation.url_input.text() or ""
        from urllib.parse import urlparse
        host = urlparse(url).netloc or "chat.deepseek.com"
        match_key = None
        for hk in SITE_PROFILES:
            if hk in host or host.endswith(hk):
                match_key = hk
                break
        if not match_key:
            match_key = "_default"
        cur = SITE_PROFILES.get(match_key, {})

        dlg = QDialog(self)
        dlg.setWindowTitle(f"📝 编辑 {match_key} 选择器")
        dlg.setMinimumWidth(700)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"<b>当前站点:</b>{host}<br>"
            f"<b>使用 profile:</b>{match_key}<br>"
            f"<i>修改后立即生效,持久化到 QSettings。</i>"))
        fields = {}
        for key, label in [("input", "输入框 input"),
                            ("send_btn", "发送按钮 send_btn"),
                            ("response", "AI 回复区 response"),
                            ("stop_btn", "停止按钮 stop_btn")]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}:"))
            edit = QLineEdit(cur.get(key, ""))
            edit.setMinimumWidth(450)
            row.addWidget(edit, 1)
            fields[key] = edit
            lay.addLayout(row)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("💾 保存覆盖")
        btn_ok.setStyleSheet("QPushButton { background:#1f8b4d; color:white; padding:6px 14px; }")
        def _ok():
            overrides = {k: e.text().strip() for k, e in fields.items() if e.text().strip()}
            if overrides:
                self._apply_site_profile_override(host, overrides)
            dlg.accept()
        btn_ok.clicked.connect(_ok)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)
        dlg.exec_()

    def batch_clean_chapter_meta(self):
        """🧹 扫描所有章节,把残留的元信息(本章完/钩子/爽点/选项)剥到 dict 字段
        用于清理'旧章节'(之前没有 strip 逻辑时生成的脏数据)"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "当前没有章节可清理")
            return
        try:
            from pangu_system import parse_chapter_meta as _pangu_parse
        except ImportError:
            QMessageBox.warning(self, "无法清理", "找不到 pangu_system 模块")
            return

        # 先扫一遍看有几章需要清
        dirty_idxs = []
        for i, ch in enumerate(self.chapters):
            c = ch.get("content", "")
            if not c:
                continue
            # 含元信息标记之一就算 dirty
            if "本章完" in c or "【断章钩子】" in c or "【下一章选项】" in c \
                    or "【本章爽点】" in c or "【伏笔状态】" in c:
                dirty_idxs.append(i)

        if not dirty_idxs:
            QMessageBox.information(
                self, "✓ 不用清理",
                f"扫描 {len(self.chapters)} 章,**没有发现**残留元信息。\n"
                f"如果你看到章节正文里还有'本章完'等,可能是:\n"
                f"  · 拉的代码不是最新(git log 看 HEAD 是不是 cdcbfde 或更新)\n"
                f"  · 章节内容是 AI 加了变体格式,可以把章节末尾发我加规则")
            return

        ret = QMessageBox.question(
            self, "🧹 一键清理章节尾部元信息",
            f"扫描 {len(self.chapters)} 章,**发现 {len(dirty_idxs)} 章**含残留元信息:\n"
            f"  章节号:{[i+1 for i in dirty_idxs[:10]]}{'...' if len(dirty_idxs) > 10 else ''}\n\n"
            f"清理后:\n"
            f"  ✓ 章节正文剥离'本章完 / 【断章钩子】/ 【本章爽点】/ ...'\n"
            f"  ✓ 元信息存进 chapter dict 的 hook/cool_points/next_options 字段\n"
            f"  ✓ 自动保存项目(会触发 .backups 备份原版本)\n\n"
            f"继续吗?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return

        cleaned = 0
        total_stripped = 0
        for i in dirty_idxs:
            ch = self.chapters[i]
            orig = ch.get("content", "")
            if not orig:
                continue
            try:
                meta = _pangu_parse(orig)
                new_body = meta.get("body") or orig
                if len(new_body) == len(orig):
                    continue  # 没真的剥到
                stripped = len(orig) - len(new_body)
                total_stripped += stripped
                cleaned += 1
                ch["content"] = new_body
                # 存元信息到 dict 字段
                if meta.get("hook"): ch["hook"] = meta["hook"]
                if meta.get("cool_points"): ch["cool_points"] = meta["cool_points"]
                if meta.get("next_options"): ch["next_options"] = meta["next_options"]
                _sp = len(meta.get("seeds_planted", []))
                _pd = len(meta.get("seeds_paid", []))
                if _sp or _pd:
                    parts = []
                    if _sp: parts.append(f"埋雷 {_sp} 条")
                    if _pd: parts.append(f"收雷 {_pd} 条")
                    ch["_pangu_seeds_summary"] = " / ".join(parts)
                self.tab_generation.log(
                    f"  · 第 {i+1} 章 剥离 {stripped} 字 + 元信息入档",
                    "info")
            except Exception as e:
                self.tab_generation.log(f"  ✗ 第 {i+1} 章 剥离失败:{e}", "warn")

        # 刷新 UI
        try:
            cur_idx = self.tab_editor.current_index
            if 0 <= cur_idx < len(self.chapters):
                self.tab_editor.show_chapter(self.chapters[cur_idx], cur_idx)
        except Exception:
            pass
        # 保存
        try:
            self.save_project()
        except Exception:
            self._autosave()

        QMessageBox.information(
            self, "✓ 清理完成",
            f"清理 {cleaned} 章,共剥离 {total_stripped} 字元信息。\n\n"
            f"已自动保存项目(原版本可通过菜单 → 🕓 恢复历史版本 找回)。\n"
            f"切到章节编辑器看『📌 本章元信息』面板,钩子/爽点/选项已就位。")

    def show_about(self):
        QMessageBox.about(
            self, f"关于 {APP_NAME}",
            f"<h2>{APP_NAME}</h2>"
            f"<p><b>版本:</b>{APP_VERSION}</p>"
            "<p><b>技术栈:</b>Python 3 + PyQt5 + Selenium</p>"
            "<p><b>核心特性:</b></p>"
            "<ul>"
            "<li>挂载真实 Chrome / Edge,自动驱动 DeepSeek/豆包/Gemini/元宝/小米AI/ChatGPT 镜像</li>"
            "<li>盘古超级系统:禁用词过滤 + 感官铁律 + 压爆震 + 黄金三章公式</li>"
            "<li>角色与世界库自动同步(角色/关系/时间线/物品/战力/伏笔/威胁承诺/剧情进度/信息隔离/剧情树)</li>"
            "<li>30 项质检 + 🔧 AI 自动修复</li>"
            "<li>章节元信息面板(钩子/爽点/伏笔/下一章选项,点选项自动指引下章)</li>"
            "<li>项目自动保存(每章+60s+章后立即)+ 最近 10 次版本备份</li>"
            "<li>自定义题材/时代/金手指/主角人设 + 折叠链</li>"
            "<li>设置菜单 → 🔍 界面字体大小(支持 4K HiDPI 手动放大)</li>"
            "</ul>"
        )


def main():
    # ── 屏蔽无害的 Qt 警告(stylesheet / DirectWrite) ──
    from PyQt5.QtCore import qInstallMessageHandler, QtWarningMsg
    _original_handler = None
    def _qt_message_filter(mode, context, message):
        if mode == QtWarningMsg:
            if "Could not parse stylesheet" in message:
                return
            if "DirectWrite" in message:
                return
        if _original_handler:
            _original_handler(mode, context, message)
        elif message:
            print(message)
    qInstallMessageHandler(_qt_message_filter)

    # ── 第 8 项: 4K HiDPI 自动缩放 ──────────────────────
    # 必须在 QApplication 创建 *之前* 设置这两个属性
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ── 应用图标 ──
    import os
    _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
    _ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
    if os.path.exists(_ico_path):
        app.setWindowIcon(QIcon(_ico_path))
    elif os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    # ── 启动闪屏(透明背景 + 文字在金色框内) ──
    from PyQt5.QtWidgets import QSplashScreen
    from PyQt5.QtGui import QPixmap, QFont as _QFont, QPainter, QPen
    _splash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "assets", "splash.png")
    if not os.path.exists(_splash_path):
        _splash_path = _icon_path
    splash = None
    _splash_modules = [
        "盘古核心引擎", "禁用词系统", "风格权重", "对话记忆",
        "Canon守卫", "角色管理", "技能库", "情绪分析",
        "章节编辑器", "生成控制", "故事大纲", "世界观构建",
        "伏笔追踪", "节奏稽核", "人物弧光", "关系图谱",
        "TTS语音", "流程引擎", "差异化系统", "AI文风检测",
        "剧情地图", "读者评审", "A/B对比", "短剧转换",
        "智能取名", "项目管理", "主题系统", "浏览器引擎",
        "自动保存",
    ]

    class _PanguSplash(QSplashScreen):
        """自定义闪屏:透明背景 + 文字画在金色框区域"""
        def __init__(self, pixmap):
            super().__init__(pixmap)
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self._msg = ""
            self._color = QColor("#FFD700")

        def set_progress(self, msg, color=None):
            self._msg = msg
            if color:
                self._color = color
            self.repaint()

        def drawContents(self, painter):
            painter.save()
            painter.setFont(_QFont("Microsoft YaHei", 13, _QFont.Bold))
            painter.setPen(QPen(self._color))
            # 文字画在底部金色框内(约 88%-95% 高度区域)
            h = self.pixmap().height()
            w = self.pixmap().width()
            text_y = int(h * 0.83)
            text_h = int(h * 0.09)
            from PyQt5.QtCore import QRect
            rect = QRect(int(w * 0.08), text_y, int(w * 0.84), text_h)
            painter.drawText(rect,
                Qt.AlignVCenter | Qt.AlignHCenter, self._msg)
            painter.restore()

    if os.path.exists(_splash_path):
        _pix = QPixmap(_splash_path).scaled(
            520, 520, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if not _pix.isNull():
            splash = _PanguSplash(_pix)
            splash.show()
            for i, mod in enumerate(_splash_modules):
                pct = int((i + 1) / len(_splash_modules) * 100)
                splash.set_progress(
                    f"正在加载核心模块 ({i+1}/{len(_splash_modules)}) · "
                    f"{mod}  {pct}%")
                app.processEvents()
                import time; time.sleep(0.03)

    # v1.20:启动时应用上次保存的主题(light/dark)
    try:
        ThemeManager.apply(app, ThemeManager.current())
    except Exception as _e:
        print(f"[Theme] 启动应用主题失败: {_e}", flush=True)

    # 字体倍数:只读用户手动设置(QSettings.font_scale),不再做自动检测
    # 原因:多屏 / 高分屏 Windows 缩放各种组合下自动检测不靠谱,
    #      手动滑块(创作设置最底)最稳。默认 ×1.0,用户拖了再生效。
    try:
        from PyQt5.QtCore import QSettings as _QSf
        _manual = _QSf("NovelAI", "CreationSettings").value(
            "font_scale", 0.0, type=float) or 0.0
        _scale = _manual if _manual >= 0.5 else 1.0
        if _scale > 1.0:
            from PyQt5.QtGui import QFont
            _font = app.font()
            _base = _font.pointSizeF() if _font.pointSizeF() > 0 else 9.0
            _font.setPointSizeF(_base * _scale)
            app.setFont(_font)
        app.setProperty("_novelai_dpi_scale", _scale)
    except Exception:
        pass

    # ── 授权验证 ──────────────────────────
    from license_guard import LicenseGuard
    guard = LicenseGuard(app)
    if not guard.check():
        sys.exit(0)

    try:
        if splash:
            splash.set_progress("正在初始化...")
            app.processEvents()

        # ── 项目启动器(闪屏后第一个界面) ──
        from ui.project_launcher import ProjectLauncher
        from pathlib import Path as _Path
        _proj_dir = _Path.home() / "NovelAI_Projects"
        _proj_dir.mkdir(exist_ok=True)

        if splash:
            splash.set_progress("✓ 加载完成!", QColor("#00FF00"))
            app.processEvents()
            import time; time.sleep(0.3)

        launcher = ProjectLauncher(str(_proj_dir))
        if os.path.exists(_ico_path):
            launcher.setWindowIcon(QIcon(_ico_path))
        if splash:
            splash.finish(launcher)
        result = launcher.exec_()
        selected_project = launcher.selected_path

        if result != QDialog.Accepted or not selected_project:
            sys.exit(0)

        # ── 加载主窗口 ──
        win = MainWindow()
        if os.path.exists(_ico_path):
            win.setWindowIcon(QIcon(_ico_path))
        elif os.path.exists(_icon_path):
            win.setWindowIcon(QIcon(_icon_path))

        # 加载选中的项目
        if PROJECT_IO_AVAILABLE:
            try:
                from pathlib import Path as _P2
                target = _P2(selected_project)
                d = project_io.load_project_folder(target)
                win.current_project_file = str(target.resolve())
                win._load_payload_into_ui(d)
                win._project_title = target.name
                win._update_window_title()
                win._push_to_recent(win.current_project_file)
                from PyQt5.QtCore import QSettings as _QSL
                _QSL("NovelAI", "UI").setValue(
                    "last_project_path", win.current_project_file)
                win.tab_generation.log(f"📂 已打开: {target.name}", "success")
            except Exception as _e:
                win.current_project_file = selected_project
                win._project_title = _Path(selected_project).name
                win._update_window_title()
                print(f"[launcher] 加载项目: {_e}", flush=True)

        # 自动识别 1K/2K/4K 分辨率(v2.23.4: 读窗口所在屏幕,不是默认屏)
        dpi = app.primaryScreen().logicalDotsPerInch() if hasattr(app, 'primaryScreen') else 96
        try:
            # 先 showMaximized 让窗口到它该去的屏幕上
            win.showMaximized()
            app.processEvents()
            # 然后读窗口所在屏幕的几何
            _win_screen = win.screen() if hasattr(win, 'screen') else None
            if _win_screen:
                _geo = _win_screen.geometry()
                sw, sh = _geo.width(), _geo.height()
                dpi = _win_screen.logicalDotsPerInch()
            else:
                from PyQt5.QtWidgets import QDesktopWidget
                _geo = QDesktopWidget().screenGeometry()
                sw, sh = _geo.width(), _geo.height()
        except Exception:
            from PyQt5.QtWidgets import QDesktopWidget
            _geo = QDesktopWidget().screenGeometry()
            sw, sh = _geo.width(), _geo.height()
        win.setMinimumSize(800, 600)

        # v2.23.4: 用 max(sw,sh) 判断分辨率(支持竖屏如 1080×1920)
        _max_dim = max(sw, sh)
        if _max_dim >= 3840:
            _res = "4K"
            _font_scale = 1.5
        elif _max_dim >= 2560:
            _res = "2K"
            _font_scale = 1.2
        else:
            _res = "1K"
            _font_scale = 1.0

        # 应用字体缩放(如果用户没手动设过)
        from PyQt5.QtCore import QSettings as _QSr
        _manual = _QSr("NovelAI", "CreationSettings").value(
            "font_scale", 0.0, type=float) or 0.0
        if _manual < 0.5 and _font_scale > 1.0:
            from PyQt5.QtGui import QFont as _QFr
            _f = app.font()
            _base = _f.pointSizeF() if _f.pointSizeF() > 0 else 9.0
            _f.setPointSizeF(_base * _font_scale)
            app.setFont(_f)
            app.setProperty("_novelai_dpi_scale", _font_scale)

        win.showMaximized()
        win.tab_generation.log(
            f"🖥 屏幕: {sw}×{sh} ({_res}) · DPI:{dpi:.0f} · "
            f"字体缩放:×{_font_scale}", "info")
        # v1.20:应用编辑器自定义颜色(如果之前调过)
        try:
            win.tab_editor._apply_editor_colors()
        except Exception:
            pass
        # 字体倍数启动日志(只在 >1.0 时打,简洁)
        try:
            _sc = app.property("_novelai_dpi_scale") or 1.0
            if _sc > 1.0:
                win.tab_generation.log(
                    f"字体倍数 ×{_sc:.2f} 已应用(创作设置 → 底部 🔍 界面字体大小)",
                    "info")
        except Exception:
            pass
    except Exception as e:
        import traceback
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "启动错误", traceback.format_exc())
        sys.exit(1)

    # 启动后台心跳
    guard.start_heartbeat(win)
    app.aboutToQuit.connect(guard.stop_heartbeat)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
