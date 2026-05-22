# -*- coding: utf-8 -*-
"""ui/tabs/generation_control.py - 生成控制 Tab(338 行)

v2.03 P4 拆分:从 novel_ai.py 第 9562-9899 行整体搬运,内容零修改。
"""
from datetime import datetime

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from core.constants import AI_URLS
from core.site_profiles import _profile_for_url
from ui.conversation_switcher import ConversationSwitcher

# Selenium 可用性 flag - 各文件独立判断,避免循环 import
try:
    import selenium  # noqa: F401
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class GenerationControl(QWidget):
    """生成控制页(Selenium 模式 - 挂载真实浏览器)"""
    log_signal = pyqtSignal(str, str)
    ctx_settings_changed = pyqtSignal()  # v2.12: 从 CreationSettings 迁入

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("生成控制 — 挂载真实浏览器(Selenium 自动化)")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a4480;")
        layout.addWidget(title)

        # ---- 浏览器内核挂载(完整面板,日常工作的主入口)----
        bbox = QGroupBox("浏览器内核挂载")
        blay = QVBoxLayout(bbox)

        # 第 1 行:内核选择 + 启动 / 关闭
        b1 = QHBoxLayout()
        b1.addWidget(QLabel("内核:"))
        self.kernel_group = QButtonGroup(self)
        # 内核 0: standalone Chrome,自有 profile(简单,但同 profile 不能再开 Chrome)
        # 内核 1: attach 模式,自动起调试 Chrome 后 attach(最稳)
        # 内核 2: standalone Edge
        rb_chrome = QRadioButton("Chrome 调试(attach,推荐)"); rb_chrome.setChecked(True)
        rb_edge = QRadioButton("系统 Edge")
        self.kernel_group.addButton(rb_chrome, 1)
        self.kernel_group.addButton(rb_edge, 2)
        for rb in (rb_chrome, rb_edge):
            b1.addWidget(rb)
        b1.addStretch()
        self.btn_launch = QPushButton("🚀 启动浏览器(首次请登录)")
        self.btn_launch.setStyleSheet(
            "background:#1a73e8;color:white;padding:6px 14px;"
            "font-weight:bold;border-radius:3px;")
        self.btn_close = QPushButton("⛔ 关闭浏览器")
        self.btn_close.setEnabled(False)
        b1.addWidget(self.btn_launch); b1.addWidget(self.btn_close)
        blay.addLayout(b1)

        # 第 2 行:AI 网站 + URL + 访问 + 抓取
        b2 = QHBoxLayout()
        b2.addWidget(QLabel("AI 网站:"))
        self.site_combo = QComboBox()
        self.site_combo.addItems(list(AI_URLS.keys()))
        self.site_combo.setCurrentText("ChatGPT镜像")
        b2.addWidget(self.site_combo)
        b2.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit("https://gpt.aimonkey.plus/")
        b2.addWidget(self.url_input, 1)
        self.btn_go = QPushButton("访问")
        self.btn_grab = QPushButton("📋 抓取最后一条回复")
        b2.addWidget(self.btn_go); b2.addWidget(self.btn_grab)
        blay.addLayout(b2)

        # 第 3 行:状态指示
        self.status_label = QLabel("状态:未启动")
        self.status_label.setStyleSheet(
            "padding: 4px 10px; background: #eee; border-radius: 3px; color: #666;")
        blay.addWidget(self.status_label)

        layout.addWidget(bbox)

        # 联动:站点切换更新 URL + 加载站点偏好(BUG-044 v1.32)
        self.site_combo.currentTextChanged.connect(self._on_site_changed)

        # ---- 生成参数 ----
        gbox = QGroupBox("批量生成参数")
        glay = QVBoxLayout(gbox)
        crow = QHBoxLayout()
        self.btn_gen_one = QPushButton("📖 生成第一章")
        self.btn_gen_one.setStyleSheet(
            "background:#27ae60;color:white;padding:6px 14px;font-weight:bold;border-radius:3px;")
        self.btn_gen_three = QPushButton("生成黄金三章")
        self.btn_regen_three = QPushButton("不想要,重生成黄金三章")
        self.btn_gen_next = QPushButton("▶ 写下一章")
        self.btn_gen_next.setStyleSheet(
            "background:#3498db;color:white;padding:6px 14px;font-weight:bold;border-radius:3px;")
        self.btn_gen_next.setToolTip(
            "单独生成下一章(不进入批量连续生成模式)。\n"
            "当前已有 N 章 → 点这个写第 N+1 章。\n"
            "适用于:想一章一章手动确认 / 黄金三章后慢慢往下写。")
        crow.addWidget(self.btn_gen_one)
        crow.addWidget(self.btn_gen_three)
        crow.addWidget(self.btn_regen_three)
        crow.addWidget(self.btn_gen_next)

        crow.addWidget(QLabel("连续生成:"))
        self.batch_count = QSpinBox()
        self.batch_count.setRange(1, 999); self.batch_count.setValue(15)
        crow.addWidget(self.batch_count)
        crow.addWidget(QLabel("章"))

        crow.addWidget(QLabel("字数死磕:"))
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 50); self.retry_count.setValue(10)  # 上限提到 50,默认 10
        self.retry_count.setToolTip(
            "死磕次数上限(防死循环用,不是必然次数)。\n"
            "实际重写次数 = 直到达标或用尽次数。\n"
            "如果质量阈值高、模型差,可能用满。建议留 10 次以上。")
        crow.addWidget(self.retry_count)
        crow.addWidget(QLabel("次上限"))

        crow.addWidget(QLabel("|质量阈值≥"))
        self.quality_threshold = QSpinBox()
        self.quality_threshold.setRange(0, 100); self.quality_threshold.setValue(75)
        self.quality_threshold.setSuffix(" 分")
        self.quality_threshold.setToolTip(
            "盘古质量评分阈值(0-100)。v1.81 已校准评分曲线。\n"
            "评分低于此值 → 触发死磕重写(死磕时会注入上次的精确定位)。\n"
            "设 0 = 关闭分数门(只看字数/钩子/禁用词)。\n"
            "设 75 = 宽松(几乎一次过),设 85 = 中等(推荐),设 95 = 严苛。\n"
            "v1.81 校准:质量良好的章节通常 90+ 分,设 95 分门可达但仍需 AI 努力。")
        crow.addWidget(self.quality_threshold)

        self.btn_start = QPushButton("▶ 开始连续生成")
        self.btn_pause = QPushButton("⏸ 暂停/停止")
        crow.addWidget(self.btn_start); crow.addWidget(self.btn_pause)
        crow.addStretch()
        glay.addLayout(crow)

        crow2 = QHBoxLayout()
        self.auto_save_project = QCheckBox("💾 自动保存项目(每章后立即写盘)")
        self.auto_save_project.setChecked(True)
        self.auto_save_project.setToolTip(
            "勾选后,每生成完一章会立即把项目保存到当前 .json 文件\n"
            "+ 摘要写完后再自动保存一次\n"
            "+ 每 60 秒额外定时保存一次\n"
            "防止意外关机/崩溃丢章节,强烈推荐保留。")
        self.auto_save_project.setStyleSheet("QCheckBox { color: #2ecc71; font-weight: bold; }")
        crow2.addWidget(self.auto_save_project)
        self.auto_save = QCheckBox("自动保存到 TXT")
        self.auto_save.setChecked(True)
        self.auto_save.setToolTip("生成完后另存一份独立 TXT 到项目目录(章节标题做文件名)")
        crow2.addWidget(self.auto_save)
        self.auto_grab = QCheckBox("自动抓取并回填(生成完即写入章节)")
        self.auto_grab.setChecked(True)
        crow2.addWidget(self.auto_grab)
        self.use_attachment = QCheckBox("📎 全部任务走附件(绕过镜像站审核-推荐)")
        self.use_attachment.setChecked(True)  # 默认开启
        self.use_attachment.setToolTip(
            "勾选后,所有任务(包括短任务)都通过 txt 附件发送给 AI\n"
            "✅ 推荐: 镜像站对短文本也可能触发审核,统一走附件最稳\n"
            "⚠️ 不勾: 直接发文本,可能被 flagged_by_moderation 拦截\n"
            "── DeepSeek 等无审核站默认会关掉这个 + 自动抓取 + 自动 TXT")
        crow2.addWidget(self.use_attachment)
        crow2.addStretch()
        self.btn_clear = QPushButton("清除日志")
        self.btn_clear.clicked.connect(self.clear_log)
        crow2.addWidget(self.btn_clear)
        glay.addLayout(crow2)

        # ---- C 模块:多维自鞭策 ----
        crit_box = QGroupBox("章节质量校验(写完后自动跑,任一不达标 → 触发死磕重写)")
        crit_lay = QHBoxLayout(crit_box)
        crit_lay.addWidget(QLabel("启用维度:"))
        self.chk_crit_words = QCheckBox("字数(默认开)")
        self.chk_crit_words.setChecked(True)
        self.chk_crit_hook = QCheckBox("章末钩子(瞬时,无 AI 调用)")
        self.chk_crit_hook.setChecked(True)
        self.chk_crit_canon = QCheckBox("Canon 稽核(1 次 AI 调用)")
        self.chk_crit_canon.setChecked(True)
        self.chk_crit_rhythm = QCheckBox("节奏分(1 次 AI 调用)")
        self.chk_crit_rhythm.setChecked(False)
        self.chk_crit_char = QCheckBox("人设分(1 次 AI 调用)")
        self.chk_crit_char.setChecked(False)
        for w in (self.chk_crit_words, self.chk_crit_hook,
                  self.chk_crit_canon, self.chk_crit_rhythm, self.chk_crit_char):
            crit_lay.addWidget(w)
        crit_lay.addStretch()
        glay.addWidget(crit_box)
        layout.addWidget(gbox)

        # ── v2.12:📖 一致性上下文(从 CreationSettings 迁入,更贴合"生成控制"语义)──
        from PyQt5.QtCore import QSettings as _QS_ctx
        _qs_ctx = _QS_ctx("NovelAI", "CreationSettings")

        ctx_box = QGroupBox("📖 一致性上下文(注入到下章 prompt)")
        ctx_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        ctx_lay = QVBoxLayout(ctx_box)

        # 行 1:完整正文注入章数
        ctx_r0 = QHBoxLayout()
        ctx_r0.addWidget(QLabel("完整正文注入【最近几章】:"))
        self.prev_chapters_n = QSpinBox()
        self.prev_chapters_n.setRange(1, 10)
        self.prev_chapters_n.setSingleStep(1)
        self.prev_chapters_n.setValue(
            max(1, min(10, _qs_ctx.value("prev_chapters_n", 1, type=int))))
        self.prev_chapters_n.setToolTip(
            "生成下一章时,把倒数最近【N 章】的正文塞进 prompt。\n"
            "默认 1 章(只塞上一章)。\n\n"
            "推荐值:\n"
            "  · 短篇 / 内存小:1 章\n"
            "  · 一般网文:1~2 章\n"
            "  · 多线索 / 复杂剧情:3~5 章\n"
            "  · 注意:章数 × 每章字数太大会爆 AI 上下文")
        ctx_r0.addWidget(self.prev_chapters_n)
        ctx_r0.addWidget(QLabel("章"))
        ctx_r0.addStretch()
        ctx_lay.addLayout(ctx_r0)

        # 行 2:单章末尾字数
        ctx_r1 = QHBoxLayout()
        ctx_r1.addWidget(QLabel("每章最多保留末尾:"))
        self.prev_tail_chars = QSpinBox()
        self.prev_tail_chars.setRange(500, 8000)
        self.prev_tail_chars.setSingleStep(500)
        _saved = _qs_ctx.value("prev_chapter_tail_chars", 2500, type=int)
        self.prev_tail_chars.setValue(max(500, min(8000, _saved)))
        self.prev_tail_chars.setToolTip(
            "每章注入时,若超过这么多字则只保留末尾 N 字(节省 token)。\n"
            "让 AI 看到人物语气 / 动作惯性 / 情节细节,保持一致性。\n\n"
            "推荐值:2500 字(主流大模型 context 够用,内容也够)\n"
            "字数越大 → 一致性越好 / token 消耗越多")
        self.prev_tail_chars.valueChanged.connect(
            lambda v: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_chapter_tail_chars", v))
        ctx_r1.addWidget(self.prev_tail_chars)
        ctx_r1.addWidget(QLabel("字 / 章"))
        ctx_r1.addStretch()
        ctx_lay.addLayout(ctx_r1)

        # 行 3:再往前用摘要开关
        ctx_r2 = QHBoxLayout()
        self.prev_use_summaries = QCheckBox(
            "再往前的章节用【摘要】注入(每章 ≤200 字,有摘要才注入)")
        self.prev_use_summaries.setChecked(
            _qs_ctx.value("prev_use_summaries", True, type=bool))
        self.prev_use_summaries.setToolTip(
            "✓ 勾选:N 章之前的所有章节,各取 summary 字段前 200 字注入,串起主线脉络\n"
            "✗ 取消:N 章之前完全不注入(节省 token,但容易忘早期设定)\n\n"
            "提示:章节没有 summary 字段也不会注入,可在编辑器里手动加 / AI 生成。")
        self.prev_use_summaries.stateChanged.connect(
            lambda s: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_use_summaries", bool(s)))
        ctx_r2.addWidget(self.prev_use_summaries)
        ctx_r2.addStretch()
        ctx_lay.addLayout(ctx_r2)

        # 字数预估 label(实时随 spin 变化)
        self.prev_ctx_estimate = QLabel("📊 预估注入字数:—(写完第 1 章后实时显示)")
        self.prev_ctx_estimate.setStyleSheet(
            "color: #1a4480; font-weight: bold; "
            "padding: 4px 8px; background: #eef4fb; border-radius: 3px;")
        self.prev_ctx_estimate.setWordWrap(True)
        ctx_lay.addWidget(self.prev_ctx_estimate)

        # 联动:控件变化 → 持久化 + 触发预估更新(信号上抛 MainWindow)
        self.prev_chapters_n.valueChanged.connect(
            lambda v: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_chapters_n", v))
        self.prev_chapters_n.valueChanged.connect(self._emit_ctx_changed)
        self.prev_tail_chars.valueChanged.connect(self._emit_ctx_changed)
        self.prev_use_summaries.stateChanged.connect(self._emit_ctx_changed)

        _hint = QLabel(
            "ℹ 默认配置:最近 1 章完整 + 每章 2500 字上限 + 早期摘要。\n"
            "  · 衔接不上 / 语气漂移 → 加大『最近几章』或『字数上限』\n"
            "  · AI 报错 token 溢出 / 章节质量下降 → 减小这两项")
        _hint.setStyleSheet("color: #888; font-size: 11px;")
        _hint.setWordWrap(True)
        ctx_lay.addWidget(_hint)
        layout.addWidget(ctx_box)

        # ---- E 模块:对话槽管理 ----
        self.conv_switcher = ConversationSwitcher()
        # 保存当前按钮 & 切换按钮由 MainWindow 接管(需要访问 url_input / worker)
        layout.addWidget(self.conv_switcher)

        # ---- 日志区 ----
        log_box = QGroupBox("生成进度 / 自动化日志")
        ll = QVBoxLayout(log_box)
        self.log_edit = QPlainTextEdit(); self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 12px; background: #fafafa;")
        ll.addWidget(self.log_edit)
        layout.addWidget(log_box, 1)

        # 联动:站点切换更新 URL —— 已移到「创作设置」AI配置 区域内自带处理

        if not SELENIUM_AVAILABLE:
            self._append_log(
                "⚠ 未检测到 Selenium,无法挂载真实浏览器。\n"
                "请运行:  pip install -U selenium\n"
                "(selenium 4.6+ 自动管理 chromedriver)\n"
                "安装后重启本软件。", "error")

        self.log_signal.connect(self._append_log)

        # ─── 全部 UI 偏好持久化(QSettings 实时写入,不再等关程序)──
        self._install_persistence()

    def _install_persistence(self):
        """把本 Tab 所有需要持久化的控件注册到 QSettings 实时写入。
        启动时自动恢复 + 任何变更立即保存(防止程序异常退出丢设置)。"""
        from PyQt5.QtCore import QSettings as _QS
        s = _QS("NovelAI", "GenerationControl")

        # 格式:(key, widget, getter_method, setter_method, signal_name, default)
        items = [
            # CheckBox 类
            ("batch.batch_count", self.batch_count, "value", "setValue", "valueChanged", 15),
            ("batch.retry_count", self.retry_count, "value", "setValue", "valueChanged", 10),
            ("batch.quality_threshold", self.quality_threshold, "value", "setValue", "valueChanged", 75),
            ("crit.words", self.chk_crit_words, "isChecked", "setChecked", "stateChanged", True),
            ("crit.hook", self.chk_crit_hook, "isChecked", "setChecked", "stateChanged", True),
            ("crit.canon", self.chk_crit_canon, "isChecked", "setChecked", "stateChanged", True),
            ("crit.rhythm", self.chk_crit_rhythm, "isChecked", "setChecked", "stateChanged", False),
            ("crit.char", self.chk_crit_char, "isChecked", "setChecked", "stateChanged", False),
        ]
        # 自动保存相关 checkbox(如果存在)
        for attr in ("chk_autosave_proj", "chk_autosave_txt", "chk_auto_grab"):
            if hasattr(self, attr):
                w = getattr(self, attr)
                items.append((f"save.{attr}", w, "isChecked", "setChecked", "stateChanged", True))

        for key, widget, getter, setter, sig_name, default in items:
            try:
                # 1) 启动恢复
                stored = s.value(key, default,
                                 type=int if isinstance(default, int) else bool)
                getattr(widget, setter)(stored)
                # 2) 注册变更监听 → 实时写入
                signal = getattr(widget, sig_name)
                signal.connect(
                    lambda _v=None, k=key, w=widget, g=getter:
                    _QS("NovelAI", "GenerationControl").setValue(k, getattr(w, g)()))
            except Exception as _e:
                # 哪个控件不存在就跳过,不影响其他
                pass

    def selected_kernel_channel(self):
        """1=Chrome 调试 attach / 2=系统 Edge (standalone 已移除)"""
        idx = self.kernel_group.checkedId()
        if idx == 2:
            return "msedge"
        return "chrome"  # 默认 attach

    # ───────── v1.32 BUG-044: 站点偏好绑定 ─────────
    SITE_PREFERENCES = {
        # 站点名 → (auto_save, auto_grab, use_attachment)
        # 只对镜像站做特殊处理(因为有审核,需要走附件)
        # 其他站点不在表里 → 保持当前 UI 状态不动
        "ChatGPT镜像": {
            "auto_save": False,           # 镜像站不需要自动 TXT(用户用得少)
            "auto_grab": True,            # 自动回填到章节
            "use_attachment": True,       # 关键:必须走附件绕过审核
        },
        # 未来可加:
        # "DeepSeek": {...},
        # "ChatGPT 官方": {...},
    }

    def _on_site_changed(self, name):
        """v1.32:切换站点时 — 1. 更新 URL  2. 应用站点偏好(如果有)"""
        # 1. 更新 URL
        if name in AI_URLS:
            self.url_input.setText(AI_URLS[name])

        # 2. 应用站点偏好(只对表里有定义的站)
        pref = self.SITE_PREFERENCES.get(name)
        if not pref:
            # 表里没有 → 保持当前 UI 状态不动,但 console 留痕
            print(f"[site] 切换到 '{name}',无专属偏好,保持当前 UI 状态", flush=True)
            return

        # 3. 应用三个 checkbox
        applied = []
        for attr, expected in pref.items():
            w = getattr(self, attr, None)
            if w is None:
                continue
            if w.isChecked() != expected:
                w.setChecked(expected)
                applied.append(f"{attr}={'开' if expected else '关'}")
            else:
                # 已经是期望值,不重复应用,但 summary 还是记录(给状态栏看)
                pass

        # 4. 预报即将使用的选择器档案
        # _profile_for_url 是按 URL host 匹配的,提示用户切换后将命中哪个档案
        target_url = AI_URLS.get(name, "")
        try:
            prof = _profile_for_url(target_url)
            prof_name = prof.get("name", "通用")
        except Exception:
            prof_name = "?"

        # 5. 状态栏提示 3 秒(向 MainWindow 发信号让它显示)
        summary = ", ".join(
            f"{k}={'✓' if v else '✗'}" for k, v in pref.items())
        msg = (f"📌 [{name}] 偏好已加载: {summary} "
               f"| 选择器档案将匹配: {prof_name}")
        print(f"[site] {msg}", flush=True)

        # 通过 MainWindow.statusBar() 显示
        # GenerationControl 是 tab 不是 MainWindow,要往上找
        w = self
        while w and not hasattr(w, "statusBar"):
            w = w.parent()
        if w and hasattr(w, "statusBar"):
            try:
                w.statusBar().showMessage(msg, 5000)   # 5 秒,内容比之前多
            except Exception:
                pass

    def critique_config(self):
        """返回当前启用的章节校验维度"""
        return {
            "word_count": self.chk_crit_words.isChecked(),
            "hook":       self.chk_crit_hook.isChecked(),
            "canon":      self.chk_crit_canon.isChecked(),
            "rhythm":     self.chk_crit_rhythm.isChecked(),
            "character":  self.chk_crit_char.isChecked(),
        }

    # ── v2.12:一致性上下文方法(从 CreationSettings 迁入)──
    def _emit_ctx_changed(self, *args):
        """3 个上下文相关控件变化时,上抛信号给 MainWindow 重算预估字数。"""
        try:
            self.ctx_settings_changed.emit()
        except Exception:
            pass

    def get_ctx_config(self):
        """返回当前上下文注入配置 dict,供 _build_prev_context 使用。"""
        return {
            "chapters_n": int(self.prev_chapters_n.value())
                if hasattr(self, "prev_chapters_n") else 1,
            "tail_chars": int(self.prev_tail_chars.value())
                if hasattr(self, "prev_tail_chars") else 2500,
            "use_summaries": bool(self.prev_use_summaries.isChecked())
                if hasattr(self, "prev_use_summaries") else True,
        }

    def _append_log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = {"info": "ℹ", "success": "✓", "warn": "⚠", "error": "✗"}.get(level, "·")
        self.log_edit.appendPlainText(f"[{ts}] {prefix} {msg}")
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def log(self, msg, level="info"):
        self.log_signal.emit(msg, level)

    def clear_log(self):
        self.log_edit.clear()
