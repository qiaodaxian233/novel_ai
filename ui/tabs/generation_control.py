# -*- coding: utf-8 -*-
"""ui/tabs/generation_control.py - 生成控制 Tab

v2.03 P4 拆分。v2.12 迁入一致性上下文。
v2.12.4 整合排版:生成操作+批量参数合并,自动化+质量校验合并。
"""
from datetime import datetime

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from core.constants import AI_URLS
from core.site_profiles import _profile_for_url
from ui.conversation_switcher import ConversationSwitcher

try:
    import selenium  # noqa: F401
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class GenerationControl(QWidget):
    """生成控制页(Selenium 模式 - 挂载真实浏览器)"""
    log_signal = pyqtSignal(str, str)
    ctx_settings_changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        title = QLabel("生成控制 — 挂载真实浏览器 · Selenium 自动化")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1a4480; padding-bottom: 2px;")
        layout.addWidget(title)

        # ═══════════════════════════════════════════════
        # A. 浏览器内核挂载
        # ═══════════════════════════════════════════════
        bbox = QGroupBox("🌐 浏览器内核挂载")
        bbox.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        blay = QVBoxLayout(bbox)
        blay.setSpacing(6)

        b1 = QHBoxLayout()
        b1.addWidget(QLabel("内核:"))
        self.kernel_group = QButtonGroup(self)
        rb_chrome = QRadioButton("Chrome 调试(attach,推荐)")
        rb_chrome.setChecked(True)
        rb_edge = QRadioButton("系统 Edge")
        self.kernel_group.addButton(rb_chrome, 1)
        self.kernel_group.addButton(rb_edge, 2)
        b1.addWidget(rb_chrome); b1.addWidget(rb_edge)
        b1.addStretch()
        self.btn_launch = QPushButton("🚀 启动浏览器(首次请登录)")
        self.btn_launch.setStyleSheet(
            "background:#3d6fd4; color:white; padding:6px 14px;"
            "font-weight:bold; border-radius:3px;")
        self.btn_close = QPushButton("⛔ 关闭浏览器")
        self.btn_close.setEnabled(False)
        self.chk_auto_start = QCheckBox("自动启动")
        self.chk_auto_start.setChecked(False)
        self.chk_auto_start.setToolTip("下次打开软件自动启动浏览器并连接上次的AI")
        self.btn_new_chat = QPushButton("🔄 新建对话")
        self.btn_new_chat.setToolTip(
            "在AI网站开启新对话,清空上下文\n"
            "建议: 改完大纲/名字后点一下,防止AI用旧名字")
        self.btn_new_chat.setStyleSheet(
            "QPushButton { background:#e67e22; color:white; padding:6px 12px;"
            "border-radius:3px; font-weight:bold; }"
            "QPushButton:hover { background:#d35400; }")
        self.chk_hide_browser = QCheckBox("🫥 隐藏浏览器")
        self.chk_hide_browser.setChecked(False)
        self.chk_hide_browser.setToolTip(
            "启动时隐藏Chrome窗口(在后台运行)\n"
            "取消勾选后重启浏览器即可显示")
        b1.addWidget(self.btn_launch); b1.addWidget(self.btn_close)
        b1.addWidget(self.btn_new_chat)
        b1.addWidget(self.chk_hide_browser)
        b1.addWidget(self.chk_auto_start)
        blay.addLayout(b1)

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
        self.btn_grab = QPushButton("📋 抓取回复")
        b2.addWidget(self.btn_go); b2.addWidget(self.btn_grab)
        blay.addLayout(b2)

        # ── v2.21.4:🤝 双 AI 分工(副 AI 处理数据/抽取任务) ──
        # 主 AI(DeepSeek)写正文,副 AI(Qwen)抽取/稽核,两个浏览器标签页自动切换
        b3 = QHBoxLayout()
        from PyQt5.QtCore import QSettings as _QS_aux
        _aux_settings = _QS_aux("NovelAI", "AuxAI")
        self.chk_aux_ai = QCheckBox("🤝 启用副 AI(数据任务)")
        self.chk_aux_ai.setChecked(_aux_settings.value("enabled", False, type=bool))
        self.chk_aux_ai.setToolTip(
            "启用后:\n"
            "  • 主 AI(如 DeepSeek)负责写章节正文/优化/创意/取名\n"
            "  • 副 AI(如 Qwen)负责角色抽取/Canon 稽核/节奏打分/摘要等数据任务\n"
            "  • 两个 AI 各开一个浏览器标签页,自动切换\n"
            "\n"
            "好处:\n"
            "  ✓ 主 AI 不被打断,对话上下文干净\n"
            "  ✓ 数据任务并行处理,效率更高\n"
            "  ✓ 充分利用不同 AI 的擅长领域\n"
            "\n"
            "需要先在两个 AI 网站分别登录(同一个 Chrome 用户数据目录,登录一次永久)。")
        b3.addWidget(self.chk_aux_ai)
        b3.addWidget(QLabel("副 AI:"))
        self.aux_site_combo = QComboBox()
        self.aux_site_combo.addItems(list(AI_URLS.keys()))
        _saved_aux = _aux_settings.value("site", "Qwen", type=str)
        self.aux_site_combo.setCurrentText(_saved_aux if _saved_aux in AI_URLS else "Qwen")
        self.aux_site_combo.setToolTip("副 AI 站点。推荐 Qwen — 结构化输出/JSON 能力强")
        b3.addWidget(self.aux_site_combo)
        b3.addWidget(QLabel("URL:"))
        _saved_aux_url = _aux_settings.value("url", AI_URLS.get("Qwen", ""), type=str)
        self.aux_url_input = QLineEdit(_saved_aux_url)
        b3.addWidget(self.aux_url_input, 1)
        # v2.21.5:打开副 AI 登录按钮 — 首次使用必须登录
        self.btn_open_aux = QPushButton("🔓 登录副 AI")
        self.btn_open_aux.setToolTip(
            "在新标签打开副 AI(Qwen),用于首次登录。\n"
            "登录后 Chrome 会记住 cookie,以后自动用。")
        self.btn_open_aux.setStyleSheet("padding:4px 10px;")
        b3.addWidget(self.btn_open_aux)
        # 状态指示
        self.aux_status_label = QLabel("●")
        self.aux_status_label.setStyleSheet("color:#aaa; font-size:14px;")
        self.aux_status_label.setToolTip("● 灰 = 未启用 | ● 绿 = 已启用 | ● 蓝 = 副 AI 正在工作")
        b3.addWidget(self.aux_status_label)
        blay.addLayout(b3)

        # 副 AI 设置变化时持久化
        def _save_aux_settings():
            _aux_settings.setValue("enabled", self.chk_aux_ai.isChecked())
            _aux_settings.setValue("site", self.aux_site_combo.currentText())
            _aux_settings.setValue("url", self.aux_url_input.text().strip())
            # 更新状态指示
            if self.chk_aux_ai.isChecked():
                self.aux_status_label.setStyleSheet("color:#27ae60; font-size:14px;")
                self.aux_status_label.setToolTip(f"● 副 AI 已启用 ({self.aux_site_combo.currentText()})")
            else:
                self.aux_status_label.setStyleSheet("color:#aaa; font-size:14px;")
                self.aux_status_label.setToolTip("● 副 AI 未启用")

        # 站点切换时自动填 URL
        def _on_aux_site_changed(name):
            if name in AI_URLS:
                self.aux_url_input.setText(AI_URLS[name])
            _save_aux_settings()

        self.chk_aux_ai.stateChanged.connect(lambda _: _save_aux_settings())
        self.aux_site_combo.currentTextChanged.connect(_on_aux_site_changed)
        self.aux_url_input.editingFinished.connect(_save_aux_settings)
        # 启动时刷新一次状态指示
        _save_aux_settings()

        self.status_label = QLabel("状态:未启动")
        self.status_label.setStyleSheet(
            "padding:4px 10px; background:#eee; border-radius:3px; color:#8fa3c4;")
        blay.addWidget(self.status_label)
        layout.addWidget(bbox)
        self.site_combo.currentTextChanged.connect(self._on_site_changed)

        # ═══════════════════════════════════════════════
        # B. 生成操作(按钮 + 批量参数 + 启停,合为一体)
        # ═══════════════════════════════════════════════
        layout.addSpacing(6)
        gen_box = QGroupBox("📖 生成操作")
        gen_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        gen_lay = QVBoxLayout(gen_box)
        gen_lay.setSpacing(8)

        # 行 1:单次操作按钮
        row1 = QHBoxLayout()
        self.btn_gen_one = QPushButton("📖 生成第一章")
        self.btn_gen_one.setStyleSheet(
            "background:#27ae60; color:white; padding:7px 14px;"
            "font-weight:bold; border-radius:3px;")
        self.btn_gen_three = QPushButton("生成黄金三章")
        self.btn_regen_three = QPushButton("重生成黄金三章")
        self.btn_gen_next = QPushButton("▶ 写下一章(单章)")
        self.btn_gen_next.setStyleSheet(
            "background:#3498db; color:white; padding:7px 14px;"
            "font-weight:bold; border-radius:3px;")
        self.btn_gen_next.setToolTip(
            "只写 1 章就停。想连续写多章请用下面的「开始连续生成」。")
        for btn in (self.btn_gen_one, self.btn_gen_three,
                    self.btn_regen_three, self.btn_gen_next):
            row1.addWidget(btn)
        row1.addStretch()
        gen_lay.addLayout(row1)

        # 分隔线
        _sep = QLabel("")
        _sep.setFixedHeight(1)
        _sep.setStyleSheet("background: #ddd;")
        gen_lay.addWidget(_sep)

        # 行 2:连续生成参数 + 启停(醒目大按钮)
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(QLabel("连续生成:"))
        self.batch_count = QSpinBox()
        self.batch_count.setRange(1, 999); self.batch_count.setValue(15)
        row2.addWidget(self.batch_count)
        row2.addWidget(QLabel("章"))
        row2.addSpacing(12)
        row2.addWidget(QLabel("死磕:"))
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 50); self.retry_count.setValue(10)
        self.retry_count.setToolTip("死磕次数上限(防死循环)")
        row2.addWidget(self.retry_count)
        row2.addWidget(QLabel("次"))
        row2.addSpacing(12)
        row2.addWidget(QLabel("阈值≥"))
        self.quality_threshold = QSpinBox()
        self.quality_threshold.setRange(0, 100); self.quality_threshold.setValue(75)
        self.quality_threshold.setSuffix(" 分")
        self.quality_threshold.setToolTip(
            "盘古质量评分阈值。75=宽松 85=推荐 95=严苛 0=关闭\n"
            "评分已校准:质量良好的章节通常 90+ 分,95 分门可达但需 AI 死磕。")
        row2.addWidget(self.quality_threshold)
        row2.addSpacing(16)
        self.btn_start = QPushButton("  ▶▶ 开始连续生成  ")
        self.btn_start.setStyleSheet(
            "QPushButton { background:#e65100; color:white; padding:8px 20px;"
            "font-weight:bold; font-size:13px; border-radius:4px; } "
            "QPushButton:hover { background:#bf360c; }")
        self.btn_start.setToolTip("按设定章数自动连续写,写完一章自动写下一章")
        self.btn_pause = QPushButton("⏸ 暂停")
        row2.addWidget(self.btn_start)
        row2.addWidget(self.btn_pause)
        row2.addStretch()
        gen_lay.addLayout(row2)
        layout.addWidget(gen_box)

        # ═══════════════════════════════════════════════
        # C. 自动化 & 质量校验(合为一体)
        # ═══════════════════════════════════════════════
        layout.addSpacing(6)
        opt_box = QGroupBox("⚙ 自动化 & 质量校验")
        opt_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        opt_lay = QVBoxLayout(opt_box)
        opt_lay.setSpacing(6)

        # 行 1:自动化选项
        orow1 = QHBoxLayout()
        self.auto_save_project = QCheckBox("💾 自动保存项目")
        self.auto_save_project.setChecked(True)
        self.auto_save_project.setToolTip("每章后立即写盘 + 每60秒定时保存")
        self.auto_save_project.setStyleSheet(
            "QCheckBox { color: #2ecc71; font-weight: bold; }")
        self.auto_save = QCheckBox("保存TXT")
        self.auto_save.setChecked(True)
        self.auto_grab = QCheckBox("自动抓取回填")
        self.auto_grab.setChecked(True)
        self.use_attachment = QCheckBox("📎 走附件(绕审核)")
        self.use_attachment.setChecked(True)
        self.use_attachment.setToolTip("推荐:通过附件发送,绕过镜像站审核")
        self.chk_auto_tts = QCheckBox("🔊 自动朗读")
        self.chk_auto_tts.setChecked(False)
        self.chk_auto_tts.setToolTip("每章入库后自动朗读,按顺序排队播放")
        self.chk_new_chat = QCheckBox("🔄 每章新对话")
        self.chk_new_chat.setChecked(True)
        self.chk_new_chat.setToolTip(
            "每章写完后在AI网站开启新对话,避免上下文污染\n"
            "(推荐开启:防止前面章节的错误名字/内容影响后面)")
        self.chk_shutdown = QCheckBox("🔌 完成后关机")
        self.chk_shutdown.setChecked(False)
        self.chk_shutdown.setToolTip(
            "批量生成全部完成后,自动保存并关机\n"
            "适合晚上挂机跑,第二天来看结果")
        for w in (self.auto_save_project, self.auto_save,
                  self.auto_grab, self.use_attachment,
                  self.chk_auto_tts, self.chk_new_chat, self.chk_shutdown):
            orow1.addWidget(w)
        orow1.addStretch()
        self.btn_clear = QPushButton("🗑 清除日志")
        self.btn_clear.clicked.connect(self.clear_log)
        orow1.addWidget(self.btn_clear)
        opt_lay.addLayout(orow1)

        # 行 2:质量校验维度
        orow2 = QHBoxLayout()
        orow2.addWidget(QLabel("质量校验:"))
        self.chk_crit_words = QCheckBox("字数")
        self.chk_crit_words.setChecked(True)
        self.chk_crit_hook = QCheckBox("章末钩子")
        self.chk_crit_hook.setChecked(True)
        self.chk_crit_canon = QCheckBox("Canon稽核")
        self.chk_crit_canon.setChecked(True)
        self.chk_crit_rhythm = QCheckBox("节奏分")
        self.chk_crit_rhythm.setChecked(False)
        self.chk_crit_char = QCheckBox("人设分")
        self.chk_crit_char.setChecked(False)
        self.chk_crit_ai_style = QCheckBox("AI文风")
        self.chk_crit_ai_style.setChecked(True)
        self.chk_crit_ai_style.setToolTip("写完后AI自检文风:句子节奏/段落均匀/细节/角色区分/情绪/留白")
        for w in (self.chk_crit_words, self.chk_crit_hook,
                  self.chk_crit_canon, self.chk_crit_rhythm, self.chk_crit_char,
                  self.chk_crit_ai_style):
            orow2.addWidget(w)
        orow2.addStretch()
        opt_lay.addLayout(orow2)
        layout.addWidget(opt_box)

        # ═══════════════════════════════════════════════
        # D. 一致性上下文
        # ═══════════════════════════════════════════════
        layout.addSpacing(6)
        from PyQt5.QtCore import QSettings as _QS_ctx
        _qs_ctx = _QS_ctx("NovelAI", "CreationSettings")

        ctx_box = QGroupBox("📖 一致性上下文(注入到下章 prompt)")
        ctx_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        ctx_lay = QVBoxLayout(ctx_box)
        ctx_lay.setSpacing(6)

        ctx_r0 = QHBoxLayout()
        ctx_r0.addWidget(QLabel("注入最近"))
        self.prev_chapters_n = QSpinBox()
        self.prev_chapters_n.setRange(1, 10); self.prev_chapters_n.setSingleStep(1)
        self.prev_chapters_n.setValue(
            max(1, min(10, _qs_ctx.value("prev_chapters_n", 1, type=int))))
        self.prev_chapters_n.setToolTip("推荐:短篇1章,一般1~2章,复杂剧情3~5章")
        ctx_r0.addWidget(self.prev_chapters_n)
        ctx_r0.addWidget(QLabel("章,每章末尾最多"))
        self.prev_tail_chars = QSpinBox()
        self.prev_tail_chars.setRange(500, 8000); self.prev_tail_chars.setSingleStep(500)
        _saved = _qs_ctx.value("prev_chapter_tail_chars", 2500, type=int)
        self.prev_tail_chars.setValue(max(500, min(8000, _saved)))
        self.prev_tail_chars.setToolTip("超过此字数只保留末尾。推荐2500")
        self.prev_tail_chars.valueChanged.connect(
            lambda v: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_chapter_tail_chars", v))
        ctx_r0.addWidget(self.prev_tail_chars)
        ctx_r0.addWidget(QLabel("字"))
        ctx_r0.addSpacing(16)
        self.prev_use_summaries = QCheckBox("早期章节用摘要注入")
        self.prev_use_summaries.setChecked(
            _qs_ctx.value("prev_use_summaries", True, type=bool))
        self.prev_use_summaries.setToolTip(
            "勾选:N章之前的章节取摘要前200字注入,串起主线\n不勾:只注入最近N章,早期完全不注入")
        self.prev_use_summaries.stateChanged.connect(
            lambda s: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_use_summaries", bool(s)))
        ctx_r0.addWidget(self.prev_use_summaries)
        ctx_r0.addStretch()
        ctx_lay.addLayout(ctx_r0)

        self.prev_ctx_estimate = QLabel("📊 预估注入字数:—(写完第 1 章后实时显示)")
        self.prev_ctx_estimate.setStyleSheet(
            "color:#5b8dee; font-weight:bold;"
            "padding:3px 8px; background:#eef4fb; border-radius:3px;")
        self.prev_ctx_estimate.setWordWrap(True)
        ctx_lay.addWidget(self.prev_ctx_estimate)

        self.prev_chapters_n.valueChanged.connect(
            lambda v: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_chapters_n", v))
        self.prev_chapters_n.valueChanged.connect(self._emit_ctx_changed)
        self.prev_tail_chars.valueChanged.connect(self._emit_ctx_changed)
        self.prev_use_summaries.stateChanged.connect(self._emit_ctx_changed)
        layout.addWidget(ctx_box)

        # ═══════════════════════════════════════════════
        # E. 对话槽管理
        # ═══════════════════════════════════════════════
        layout.addSpacing(4)
        self.conv_switcher = ConversationSwitcher()
        layout.addWidget(self.conv_switcher)

        # ═══════════════════════════════════════════════
        # F. 日志区
        # ═══════════════════════════════════════════════
        layout.addSpacing(4)
        log_box = QGroupBox("📋 生成日志")
        log_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        ll = QVBoxLayout(log_box)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(120)
        self.log_edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 12px; background: #fafafa;")
        ll.addWidget(self.log_edit)
        layout.addWidget(log_box, 1)

        if not SELENIUM_AVAILABLE:
            self._append_log(
                "⚠ 未检测到 Selenium。请运行: pip install -U selenium", "error")

        self.log_signal.connect(self._append_log)
        self._install_persistence()

    # ─── 持久化 ───────────────────────────────────────
    def _install_persistence(self):
        from PyQt5.QtCore import QSettings as _QS
        s = _QS("NovelAI", "GenerationControl")
        items = [
            ("batch.batch_count", self.batch_count, "value", "setValue", "valueChanged", 15),
            ("batch.retry_count", self.retry_count, "value", "setValue", "valueChanged", 10),
            ("batch.quality_threshold", self.quality_threshold, "value", "setValue", "valueChanged", 75),
            ("crit.words", self.chk_crit_words, "isChecked", "setChecked", "stateChanged", True),
            ("crit.hook", self.chk_crit_hook, "isChecked", "setChecked", "stateChanged", True),
            ("crit.canon", self.chk_crit_canon, "isChecked", "setChecked", "stateChanged", True),
            ("crit.rhythm", self.chk_crit_rhythm, "isChecked", "setChecked", "stateChanged", False),
            ("crit.char", self.chk_crit_char, "isChecked", "setChecked", "stateChanged", False),
            ("crit.ai_style", self.chk_crit_ai_style, "isChecked", "setChecked", "stateChanged", True),
            ("site.last_model", self.site_combo, "currentText", "setCurrentText", "currentTextChanged", "DeepSeek"),
            ("tts.auto_read", self.chk_auto_tts, "isChecked", "setChecked", "stateChanged", False),
            ("browser.auto_start", self.chk_auto_start, "isChecked", "setChecked", "stateChanged", False),
        ]
        for attr in ("chk_autosave_proj", "chk_autosave_txt", "chk_auto_grab"):
            if hasattr(self, attr):
                w = getattr(self, attr)
                items.append((f"save.{attr}", w, "isChecked", "setChecked", "stateChanged", True))
        for key, widget, getter, setter, sig_name, default in items:
            try:
                if isinstance(default, int):
                    _type = int
                elif isinstance(default, str):
                    _type = str
                else:
                    _type = bool
                stored = s.value(key, default, type=_type)
                getattr(widget, setter)(stored)
                signal = getattr(widget, sig_name)
                signal.connect(
                    lambda _v=None, k=key, w=widget, g=getter:
                    _QS("NovelAI", "GenerationControl").setValue(k, getattr(w, g)()))
            except Exception:
                pass

    def selected_kernel_channel(self):
        return "msedge" if self.kernel_group.checkedId() == 2 else "chrome"

    # ─── 站点偏好 ─────────────────────────────────────
    SITE_PREFERENCES = {
        "ChatGPT镜像": {"auto_save": False, "auto_grab": True, "use_attachment": True},
    }

    def _on_site_changed(self, name):
        if name in AI_URLS:
            self.url_input.setText(AI_URLS[name])
        pref = self.SITE_PREFERENCES.get(name)
        if not pref:
            return
        for attr, expected in pref.items():
            w = getattr(self, attr, None)
            if w and w.isChecked() != expected:
                w.setChecked(expected)
        target_url = AI_URLS.get(name, "")
        try:
            prof_name = _profile_for_url(target_url).get("name", "通用")
        except Exception:
            prof_name = "?"
        summary = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in pref.items())
        msg = f"📌 [{name}] {summary} | 档案: {prof_name}"
        w = self
        while w and not hasattr(w, "statusBar"):
            w = w.parent()
        if w and hasattr(w, "statusBar"):
            try: w.statusBar().showMessage(msg, 5000)
            except Exception: pass

    def critique_config(self):
        return {
            "word_count": self.chk_crit_words.isChecked(),
            "hook":       self.chk_crit_hook.isChecked(),
            "canon":      self.chk_crit_canon.isChecked(),
            "rhythm":     self.chk_crit_rhythm.isChecked(),
            "character":  self.chk_crit_char.isChecked(),
            "ai_style":   self.chk_crit_ai_style.isChecked(),
        }

    def _emit_ctx_changed(self, *args):
        try: self.ctx_settings_changed.emit()
        except Exception: pass

    def get_ctx_config(self):
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
        self.log_edit.verticalScrollBar().setValue(
            self.log_edit.verticalScrollBar().maximum())

    def log(self, msg, level="info"):
        self.log_signal.emit(msg, level)

    def clear_log(self):
        self.log_edit.clear()
