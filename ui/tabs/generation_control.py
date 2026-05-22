# -*- coding: utf-8 -*-
"""ui/tabs/generation_control.py - 生成控制 Tab

v2.03 P4 拆分:从 novel_ai.py 整体搬运。
v2.12 迁入一致性上下文。
v2.12.3 重排版:拆大 GroupBox、加呼吸感。
"""
from datetime import datetime

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QRadioButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from core.constants import AI_URLS
from core.site_profiles import _profile_for_url
from ui.conversation_switcher import ConversationSwitcher

try:
    import selenium  # noqa: F401
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


def _section_spacing(layout, px=10):
    layout.addSpacing(px)


class GenerationControl(QWidget):
    """生成控制页(Selenium 模式 - 挂载真实浏览器)"""
    log_signal = pyqtSignal(str, str)
    ctx_settings_changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        # 外层用 QScrollArea 包裹,窗口小时可滚动
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        title = QLabel("生成控制 — 挂载真实浏览器 · Selenium 自动化")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1a4480; padding-bottom: 4px;")
        layout.addWidget(title)

        # ═══════════════════════════════════════════════
        # A. 浏览器内核挂载
        # ═══════════════════════════════════════════════
        bbox = QGroupBox("🌐 浏览器内核挂载")
        bbox.setStyleSheet("QGroupBox { font-weight: bold; }")
        blay = QVBoxLayout(bbox)
        blay.setSpacing(8)

        b1 = QHBoxLayout()
        b1.addWidget(QLabel("内核:"))
        self.kernel_group = QButtonGroup(self)
        rb_chrome = QRadioButton("Chrome 调试(attach,推荐)")
        rb_chrome.setChecked(True)
        rb_edge = QRadioButton("系统 Edge")
        self.kernel_group.addButton(rb_chrome, 1)
        self.kernel_group.addButton(rb_edge, 2)
        b1.addWidget(rb_chrome)
        b1.addWidget(rb_edge)
        b1.addStretch()
        self.btn_launch = QPushButton("🚀 启动浏览器(首次请登录)")
        self.btn_launch.setStyleSheet(
            "background:#1a73e8; color:white; padding:6px 14px;"
            "font-weight:bold; border-radius:3px;")
        self.btn_close = QPushButton("⛔ 关闭浏览器")
        self.btn_close.setEnabled(False)
        b1.addWidget(self.btn_launch)
        b1.addWidget(self.btn_close)
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
        b2.addWidget(self.btn_go)
        b2.addWidget(self.btn_grab)
        blay.addLayout(b2)

        self.status_label = QLabel("状态:未启动")
        self.status_label.setStyleSheet(
            "padding:4px 10px; background:#eee; border-radius:3px; color:#666;")
        blay.addWidget(self.status_label)
        layout.addWidget(bbox)

        self.site_combo.currentTextChanged.connect(self._on_site_changed)

        # ═══════════════════════════════════════════════
        # B. 生成操作(大按钮,一眼找到)
        # ═══════════════════════════════════════════════
        _section_spacing(layout)
        act_box = QGroupBox("📖 生成操作")
        act_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        act_lay = QHBoxLayout(act_box)
        act_lay.setSpacing(10)

        self.btn_gen_one = QPushButton("📖 生成第一章")
        self.btn_gen_one.setStyleSheet(
            "background:#27ae60; color:white; padding:8px 16px;"
            "font-weight:bold; border-radius:3px;")
        self.btn_gen_three = QPushButton("生成黄金三章")
        self.btn_regen_three = QPushButton("重生成黄金三章")
        self.btn_gen_next = QPushButton("▶ 写下一章")
        self.btn_gen_next.setStyleSheet(
            "background:#3498db; color:white; padding:8px 16px;"
            "font-weight:bold; border-radius:3px;")
        self.btn_gen_next.setToolTip(
            "单独生成下一章(不进入批量连续生成模式)。\n"
            "当前已有 N 章 → 点这个写第 N+1 章。")
        for btn in (self.btn_gen_one, self.btn_gen_three,
                    self.btn_regen_three, self.btn_gen_next):
            act_lay.addWidget(btn)
        act_lay.addStretch()
        layout.addWidget(act_box)

        # ═══════════════════════════════════════════════
        # C. 批量参数 + 启停
        # ═══════════════════════════════════════════════
        _section_spacing(layout)
        batch_box = QGroupBox("⚙ 批量生成参数")
        batch_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        batch_lay = QHBoxLayout(batch_box)
        batch_lay.setSpacing(14)

        batch_lay.addWidget(QLabel("连续生成:"))
        self.batch_count = QSpinBox()
        self.batch_count.setRange(1, 999)
        self.batch_count.setValue(15)
        batch_lay.addWidget(self.batch_count)
        batch_lay.addWidget(QLabel("章"))

        batch_lay.addSpacing(20)
        batch_lay.addWidget(QLabel("字数死磕:"))
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 50)
        self.retry_count.setValue(10)
        self.retry_count.setToolTip(
            "死磕次数上限(防死循环)。实际重写次数 = 直到达标或用尽。")
        batch_lay.addWidget(self.retry_count)
        batch_lay.addWidget(QLabel("次上限"))

        batch_lay.addSpacing(20)
        batch_lay.addWidget(QLabel("质量阈值 ≥"))
        self.quality_threshold = QSpinBox()
        self.quality_threshold.setRange(0, 100)
        self.quality_threshold.setValue(75)
        self.quality_threshold.setSuffix(" 分")
        self.quality_threshold.setToolTip(
            "盘古质量评分阈值(0-100)。\n"
            "低于此值 → 触发死磕重写。\n"
            "设 0 = 关闭(只看字数/钩子/禁用词)\n"
            "75 = 宽松  85 = 中等(推荐)  95 = 严苛")
        batch_lay.addWidget(self.quality_threshold)

        batch_lay.addSpacing(20)
        self.btn_start = QPushButton("▶ 开始连续生成")
        self.btn_start.setStyleSheet(
            "background:#e67e22; color:white; padding:6px 14px;"
            "font-weight:bold; border-radius:3px;")
        self.btn_pause = QPushButton("⏸ 暂停")
        batch_lay.addWidget(self.btn_start)
        batch_lay.addWidget(self.btn_pause)
        batch_lay.addStretch()
        layout.addWidget(batch_box)

        # ═══════════════════════════════════════════════
        # D. 自动化选项(2×2 网格)
        # ═══════════════════════════════════════════════
        _section_spacing(layout)
        auto_box = QGroupBox("💾 自动化选项")
        auto_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        auto_grid = QVBoxLayout(auto_box)

        auto_r1 = QHBoxLayout()
        self.auto_save_project = QCheckBox("💾 自动保存项目(每章后立即写盘)")
        self.auto_save_project.setChecked(True)
        self.auto_save_project.setToolTip(
            "每生成完一章立即保存 .json + 每 60 秒定时保存。\n强烈推荐保留。")
        self.auto_save_project.setStyleSheet(
            "QCheckBox { color: #2ecc71; font-weight: bold; }")
        self.auto_save = QCheckBox("自动保存到 TXT")
        self.auto_save.setChecked(True)
        self.auto_save.setToolTip("生成完另存一份独立 TXT(章节标题做文件名)")
        auto_r1.addWidget(self.auto_save_project)
        auto_r1.addSpacing(30)
        auto_r1.addWidget(self.auto_save)
        auto_r1.addStretch()
        auto_grid.addLayout(auto_r1)

        auto_r2 = QHBoxLayout()
        self.auto_grab = QCheckBox("自动抓取并回填(生成完即写入章节)")
        self.auto_grab.setChecked(True)
        self.use_attachment = QCheckBox("📎 全部任务走附件(绕过审核)")
        self.use_attachment.setChecked(True)
        self.use_attachment.setToolTip(
            "勾选:所有任务通过 txt 附件发送(推荐,绕镜像站审核)\n"
            "不勾:直接发文本,可能被拦截")
        auto_r2.addWidget(self.auto_grab)
        auto_r2.addSpacing(30)
        auto_r2.addWidget(self.use_attachment)
        auto_r2.addStretch()
        self.btn_clear = QPushButton("🗑 清除日志")
        self.btn_clear.clicked.connect(self.clear_log)
        auto_r2.addWidget(self.btn_clear)
        auto_grid.addLayout(auto_r2)
        layout.addWidget(auto_box)

        # ═══════════════════════════════════════════════
        # E. 质量校验
        # ═══════════════════════════════════════════════
        _section_spacing(layout)
        crit_box = QGroupBox("🔍 章节质量校验(写完后自动跑,不达标 → 死磕重写)")
        crit_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        crit_lay = QHBoxLayout(crit_box)
        crit_lay.setSpacing(16)
        self.chk_crit_words = QCheckBox("字数")
        self.chk_crit_words.setChecked(True)
        self.chk_crit_hook = QCheckBox("章末钩子")
        self.chk_crit_hook.setChecked(True)
        self.chk_crit_canon = QCheckBox("Canon 稽核")
        self.chk_crit_canon.setChecked(True)
        self.chk_crit_rhythm = QCheckBox("节奏分")
        self.chk_crit_rhythm.setChecked(False)
        self.chk_crit_char = QCheckBox("人设分")
        self.chk_crit_char.setChecked(False)
        for w in (self.chk_crit_words, self.chk_crit_hook,
                  self.chk_crit_canon, self.chk_crit_rhythm, self.chk_crit_char):
            crit_lay.addWidget(w)
        crit_lay.addStretch()
        layout.addWidget(crit_box)

        # ═══════════════════════════════════════════════
        # F. 一致性上下文
        # ═══════════════════════════════════════════════
        _section_spacing(layout)
        from PyQt5.QtCore import QSettings as _QS_ctx
        _qs_ctx = _QS_ctx("NovelAI", "CreationSettings")

        ctx_box = QGroupBox("📖 一致性上下文(注入到下章 prompt)")
        ctx_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        ctx_lay = QVBoxLayout(ctx_box)
        ctx_lay.setSpacing(8)

        ctx_r0 = QHBoxLayout()
        ctx_r0.addWidget(QLabel("完整正文注入【最近几章】:"))
        self.prev_chapters_n = QSpinBox()
        self.prev_chapters_n.setRange(1, 10)
        self.prev_chapters_n.setSingleStep(1)
        self.prev_chapters_n.setValue(
            max(1, min(10, _qs_ctx.value("prev_chapters_n", 1, type=int))))
        self.prev_chapters_n.setToolTip(
            "生成下一章时,把倒数最近 N 章的正文塞进 prompt。\n"
            "推荐:短篇 1 章,一般 1~2 章,复杂剧情 3~5 章。")
        ctx_r0.addWidget(self.prev_chapters_n)
        ctx_r0.addWidget(QLabel("章"))
        ctx_r0.addSpacing(30)
        ctx_r0.addWidget(QLabel("每章最多保留末尾:"))
        self.prev_tail_chars = QSpinBox()
        self.prev_tail_chars.setRange(500, 8000)
        self.prev_tail_chars.setSingleStep(500)
        _saved = _qs_ctx.value("prev_chapter_tail_chars", 2500, type=int)
        self.prev_tail_chars.setValue(max(500, min(8000, _saved)))
        self.prev_tail_chars.setToolTip(
            "超过此字数只保留末尾(节省 token)。推荐 2500。")
        self.prev_tail_chars.valueChanged.connect(
            lambda v: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_chapter_tail_chars", v))
        ctx_r0.addWidget(self.prev_tail_chars)
        ctx_r0.addWidget(QLabel("字/章"))
        ctx_r0.addStretch()
        ctx_lay.addLayout(ctx_r0)

        ctx_r1 = QHBoxLayout()
        self.prev_use_summaries = QCheckBox(
            "再往前的章节用【摘要】注入(每章 ≤200 字,有摘要才注入)")
        self.prev_use_summaries.setChecked(
            _qs_ctx.value("prev_use_summaries", True, type=bool))
        self.prev_use_summaries.stateChanged.connect(
            lambda s: _QS_ctx("NovelAI", "CreationSettings").setValue(
                "prev_use_summaries", bool(s)))
        ctx_r1.addWidget(self.prev_use_summaries)
        ctx_r1.addStretch()
        ctx_lay.addLayout(ctx_r1)

        self.prev_ctx_estimate = QLabel("📊 预估注入字数:—(写完第 1 章后实时显示)")
        self.prev_ctx_estimate.setStyleSheet(
            "color:#1a4480; font-weight:bold; "
            "padding:4px 8px; background:#eef4fb; border-radius:3px;")
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
        # G. 对话槽管理
        # ═══════════════════════════════════════════════
        _section_spacing(layout)
        self.conv_switcher = ConversationSwitcher()
        layout.addWidget(self.conv_switcher)

        # ═══════════════════════════════════════════════
        # H. 日志区(占剩余空间)
        # ═══════════════════════════════════════════════
        _section_spacing(layout)
        log_box = QGroupBox("📋 生成进度 / 自动化日志")
        log_box.setStyleSheet("QGroupBox { font-weight: bold; }")
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
                "⚠ 未检测到 Selenium,无法挂载真实浏览器。\n"
                "请运行:  pip install -U selenium\n"
                "(selenium 4.6+ 自动管理 chromedriver)\n"
                "安装后重启本软件。", "error")

        self.log_signal.connect(self._append_log)
        self._install_persistence()

    # ─── 持久化 ───────────────────────────────────────
    def _install_persistence(self):
        """本 Tab 所有需要持久化的控件 → QSettings 实时写入"""
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
        ]
        for attr in ("chk_autosave_proj", "chk_autosave_txt", "chk_auto_grab"):
            if hasattr(self, attr):
                w = getattr(self, attr)
                items.append((f"save.{attr}", w, "isChecked", "setChecked", "stateChanged", True))
        for key, widget, getter, setter, sig_name, default in items:
            try:
                stored = s.value(key, default,
                                 type=int if isinstance(default, int) else bool)
                getattr(widget, setter)(stored)
                signal = getattr(widget, sig_name)
                signal.connect(
                    lambda _v=None, k=key, w=widget, g=getter:
                    _QS("NovelAI", "GenerationControl").setValue(k, getattr(w, g)()))
            except Exception:
                pass

    # ─── 内核选择 ─────────────────────────────────────
    def selected_kernel_channel(self):
        idx = self.kernel_group.checkedId()
        return "msedge" if idx == 2 else "chrome"

    # ─── 站点偏好 ─────────────────────────────────────
    SITE_PREFERENCES = {
        "ChatGPT镜像": {
            "auto_save": False,
            "auto_grab": True,
            "use_attachment": True,
        },
    }

    def _on_site_changed(self, name):
        if name in AI_URLS:
            self.url_input.setText(AI_URLS[name])
        pref = self.SITE_PREFERENCES.get(name)
        if not pref:
            print(f"[site] 切换到 '{name}',无专属偏好,保持当前 UI 状态", flush=True)
            return
        applied = []
        for attr, expected in pref.items():
            w = getattr(self, attr, None)
            if w is None:
                continue
            if w.isChecked() != expected:
                w.setChecked(expected)
                applied.append(f"{attr}={'开' if expected else '关'}")
        target_url = AI_URLS.get(name, "")
        try:
            prof = _profile_for_url(target_url)
            prof_name = prof.get("name", "通用")
        except Exception:
            prof_name = "?"
        summary = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in pref.items())
        msg = f"📌 [{name}] 偏好已加载: {summary} | 选择器档案: {prof_name}"
        print(f"[site] {msg}", flush=True)
        w = self
        while w and not hasattr(w, "statusBar"):
            w = w.parent()
        if w and hasattr(w, "statusBar"):
            try:
                w.statusBar().showMessage(msg, 5000)
            except Exception:
                pass

    # ─── 质量校验配置 ────────────────────────────────
    def critique_config(self):
        return {
            "word_count": self.chk_crit_words.isChecked(),
            "hook":       self.chk_crit_hook.isChecked(),
            "canon":      self.chk_crit_canon.isChecked(),
            "rhythm":     self.chk_crit_rhythm.isChecked(),
            "character":  self.chk_crit_char.isChecked(),
        }

    # ─── 一致性上下文 ────────────────────────────────
    def _emit_ctx_changed(self, *args):
        try:
            self.ctx_settings_changed.emit()
        except Exception:
            pass

    def get_ctx_config(self):
        return {
            "chapters_n": int(self.prev_chapters_n.value())
                if hasattr(self, "prev_chapters_n") else 1,
            "tail_chars": int(self.prev_tail_chars.value())
                if hasattr(self, "prev_tail_chars") else 2500,
            "use_summaries": bool(self.prev_use_summaries.isChecked())
                if hasattr(self, "prev_use_summaries") else True,
        }

    # ─── 日志 ────────────────────────────────────────
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
