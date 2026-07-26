# -*- coding: utf-8 -*-
"""ui/tabs/chapter_editor.py - 章节编辑器 Tab(404 行)

v2.03 P4 拆分:从 novel_ai.py 第 659-1062 行整体搬运,内容零修改。
"""
import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ui.highlighters import _PanguForbiddenHighlighter


class ChapterEditor(QWidget):
    save_requested = pyqtSignal(str, str)
    optimize_requested = pyqtSignal(str)
    save_all_requested = pyqtSignal()
    # 盘古超级系统:3 个新信号
    pangu_quicklint_requested = pyqtSignal(str)
    pangu_qcheck_requested = pyqtSignal(str)
    laodao_critique_requested = pyqtSignal(str)
    pangu_spiral_requested = pyqtSignal(str)
    pangu_preview_prompt_requested = pyqtSignal()
    # v1.10:TTS 朗读
    tts_play_requested  = pyqtSignal()   # 开始朗读本章
    tts_pause_requested = pyqtSignal()   # 暂停/继续
    tts_stop_requested  = pyqtSignal()   # 停止 + 清队列
    tts_speed_changed   = pyqtSignal(float)  # 速度滑块变化
    dialogue_critic_requested = pyqtSignal()  # v1.32:13 法对话诊断    # 预览章节 prompt
    # BUG-014:用户在元信息面板点了某条"下一章选项",把选项文本传给主程序,
    # 主程序在下次生成下一章时把它作为开局指引注入 prompt
    next_option_picked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("保存章节")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_optimize = QPushButton("AI优化")
        self.btn_optimize.clicked.connect(self._on_optimize)
        self.btn_save_all = QPushButton("一键保存所有")
        self.btn_save_all.clicked.connect(lambda: self.save_all_requested.emit())
        # 盘古超级系统:3 个新功能按钮
        self.btn_pangu_lint = QPushButton("🛡️ 本地词扫")
        self.btn_pangu_lint.setStyleSheet(
            "background:#1f8b4d;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_lint.setToolTip("0-token 本地检测:禁用词/长句/破折号/三连点")
        self.btn_pangu_lint.clicked.connect(self._on_pangu_lint)
        self.btn_pangu_qcheck = QPushButton("📊 智能质检")
        self.btn_pangu_qcheck.setStyleSheet(
            "background:#b8651b;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_qcheck.setToolTip(
            "📊 智能质检(38 项 = 30 项原盘古 + 8 大坑专项)\n"
            "发 AI 深度审稿,返回 JSON:\n"
            "  · 总分 0-100\n"
            "  · 失败条目编号\n"
            "  · 八大坑 K1-K8 各项 0-10 分\n"
            "  · 修改建议")
        self.btn_pangu_qcheck.clicked.connect(self._on_pangu_qcheck)
        self.btn_laodao = QPushButton("🔪 老刀毒舌点评")
        self.btn_laodao.setStyleSheet(
            "background:#c0392b;color:white;padding:4px 10px;border-radius:3px;font-weight:bold;")
        self.btn_laodao.setToolTip(
            "请 AI 扮演十五年资深网文编辑老刀,毒舌点评当前章节。\n"
            "8 维度 + 致命伤 / 三章弃书率预估。\n"
            "若弃书率超过目标值,自动重写并再点评,直到达标或到最大轮数。")
        self.btn_laodao.clicked.connect(self._on_laodao_critique)

        # ── 弃书率目标设置 ──
        from PyQt5.QtWidgets import QSpinBox, QLabel
        from PyQt5.QtCore import QSettings
        self._laodao_target_lbl = QLabel("目标弃书率≤")
        self._laodao_target_lbl.setStyleSheet("font-size:11px; color:#6d7c95;")
        self.spn_laodao_target = QSpinBox()
        self.spn_laodao_target.setRange(10, 80)
        self.spn_laodao_target.setSuffix("%")
        self.spn_laodao_target.setFixedWidth(72)
        self.spn_laodao_target.setToolTip(
            "老刀点评后自动重写的弃书率门槛。\n"
            "弃书率 > 此值 → 自动重写再点评，直到达标或满 5 轮。\n"
            "建议 30-40%。")
        _saved = QSettings("NovelAI", "Laodao").value("target_quit_rate", 35, type=int)
        self.spn_laodao_target.setValue(_saved)
        self.spn_laodao_target.valueChanged.connect(
            lambda v: QSettings("NovelAI", "Laodao").setValue("target_quit_rate", v))

        self._laodao_max_lbl = QLabel("最多")
        self._laodao_max_lbl.setStyleSheet("font-size:11px; color:#6d7c95;")
        self.spn_laodao_max = QSpinBox()
        self.spn_laodao_max.setRange(1, 8)
        self.spn_laodao_max.setSuffix("轮")
        self.spn_laodao_max.setFixedWidth(60)
        self.spn_laodao_max.setToolTip("自动重写最多循环几轮，防止死循环。")
        _saved_max = QSettings("NovelAI", "Laodao").value("max_autofix_rounds", 3, type=int)
        self.spn_laodao_max.setValue(_saved_max)
        self.spn_laodao_max.valueChanged.connect(
            lambda v: QSettings("NovelAI", "Laodao").setValue("max_autofix_rounds", v))
        self.btn_pangu_spiral = QPushButton("🌀 螺旋诊断")
        self.btn_pangu_spiral.setStyleSheet(
            "background:#253352;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_spiral.setToolTip("AI 诊断当前章节处于 P1-P7 哪个螺旋阶段")
        self.btn_pangu_spiral.clicked.connect(self._on_pangu_spiral)
        self.btn_pangu_preview = QPushButton("👁️ 预览Prompt")
        self.btn_pangu_preview.setStyleSheet(
            "background:#2c3e50;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_preview.setToolTip("查看下一章节生成时实际发给 AI 的完整 prompt(含盘古铁律)")
        self.btn_pangu_preview.clicked.connect(lambda: self.pangu_preview_prompt_requested.emit())
        self.btn_style_check = QPushButton("🎨 风格一致性检测")
        self.btn_style_check.setStyleSheet(
            "background:#7c5cbf;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_regen_alt = QPushButton("🎲 生成备选版本")
        self.btn_regen_alt.setStyleSheet(
            "background:#1a8a72;color:white;padding:4px 10px;border-radius:3px;")
        for b in (self.btn_save, self.btn_optimize, self.btn_save_all,
                  self.btn_pangu_lint, self.btn_pangu_qcheck, self.btn_laodao,
                  self.btn_pangu_spiral, self.btn_pangu_preview,
                  self.btn_style_check, self.btn_regen_alt):
            btn_row.addWidget(b)
        btn_row.addWidget(self._laodao_target_lbl)
        btn_row.addWidget(self.spn_laodao_target)
        btn_row.addWidget(self._laodao_max_lbl)
        btn_row.addWidget(self.spn_laodao_max)
        btn_row.addStretch()
        # v1.10:TTS 朗读控件 — 单独一组,右侧对齐
        self.btn_tts_play = QPushButton("🔊 朗读本章")
        self.btn_tts_play.setStyleSheet(
            "background:#1f8b4d;color:white;padding:4px 10px;border-radius:3px;"
            "font-weight:bold;")
        self.btn_tts_play.setToolTip(
            "用 TTS 朗读当前章节(后端在 创作设置 → TTS 朗读 里配置)\n"
            "默认 EdgeTTS(免费在线),可切到 Index-TTS(本地声音克隆)")
        self.btn_tts_play.clicked.connect(self.tts_play_requested.emit)
        self.btn_tts_stop = QPushButton("⏹")
        self.btn_tts_stop.setStyleSheet(
            "background:#c0392b;color:white;padding:4px 8px;border-radius:3px;")
        self.btn_tts_stop.setToolTip("停止朗读 + 清空合成队列")
        self.btn_tts_stop.clicked.connect(self.tts_stop_requested.emit)
        self.btn_tts_stop.setEnabled(False)  # 没在朗读时禁用
        # 速度滑块
        self.lbl_tts_speed = QLabel("速度 1.0x")
        self.lbl_tts_speed.setStyleSheet("color:#6d7c95;font-size:11px;")
        self.slider_tts_speed = QSlider(Qt.Horizontal)
        self.slider_tts_speed.setRange(50, 200)  # 0.5x ~ 2.0x
        self.slider_tts_speed.setValue(100)       # 默认 1.0x
        self.slider_tts_speed.setFixedWidth(80)
        self.slider_tts_speed.setToolTip("朗读速度 0.5x ~ 2.0x")
        self.slider_tts_speed.valueChanged.connect(
            lambda v: (
                self.lbl_tts_speed.setText(f"速度 {v/100:.1f}x"),
                self.tts_speed_changed.emit(v / 100.0),
            ))
        # TTS 状态 label(显示"合成中 3/10"之类)
        self.lbl_tts_status = QLabel("")
        self.lbl_tts_status.setStyleSheet("color:#1f8b4d;font-size:11px;")
        btn_row.addWidget(self.btn_tts_play)
        btn_row.addWidget(self.btn_tts_stop)
        btn_row.addWidget(self.lbl_tts_speed)
        btn_row.addWidget(self.slider_tts_speed)
        btn_row.addWidget(self.lbl_tts_status)
        # v1.20:🎨 编辑器自定义字色 + 🖌 背景色
        self.btn_editor_fg = QPushButton("🎨 字色")
        self.btn_editor_fg.setToolTip("调整章节编辑器的文字颜色")
        self.btn_editor_fg.setStyleSheet(
            "background:#7f8c8d;color:white;padding:4px 8px;border-radius:3px;")
        self.btn_editor_fg.clicked.connect(self._pick_editor_fg)
        self.btn_editor_bg = QPushButton("🖌 背景")
        self.btn_editor_bg.setToolTip("调整章节编辑器的背景颜色")
        self.btn_editor_bg.setStyleSheet(
            "background:#7f8c8d;color:white;padding:4px 8px;border-radius:3px;")
        self.btn_editor_bg.clicked.connect(self._pick_editor_bg)
        self.btn_editor_reset = QPushButton("↺")
        self.btn_editor_reset.setToolTip("重置编辑器颜色为默认(跟随当前主题)")
        self.btn_editor_reset.setStyleSheet(
            "background:#6d7b7c;color:white;padding:4px 8px;border-radius:3px;")
        self.btn_editor_reset.clicked.connect(self._reset_editor_colors)
        btn_row.addWidget(self.btn_editor_fg)
        btn_row.addWidget(self.btn_editor_bg)
        btn_row.addWidget(self.btn_editor_reset)
        # v1.32:🔬 13 法对话诊断按钮
        self.btn_dialogue_critic = QPushButton("🔬 13法诊断")
        self.btn_dialogue_critic.setToolTip(
            "用 13 法对话铁律诊断本章:\n"
            "  · 静态扫描:统计「说/道」密度、套词、连续 X 说\n"
            "  · AI 深度评分:13 法逐条评分 + 改写建议(发 AI,要 token)\n"
            "快捷键: F9")
        self.btn_dialogue_critic.setStyleSheet(
            "background:#8e44ad;color:white;padding:4px 10px;border-radius:3px;"
            "font-weight:bold;")
        self.btn_dialogue_critic.setShortcut("F9")
        self.btn_dialogue_critic.clicked.connect(self.dialogue_critic_requested.emit)
        btn_row.addWidget(self.btn_dialogue_critic)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("章节标题:"))
        self.title_input = QLineEdit()
        layout.addWidget(self.title_input)

        self.content_edit = QPlainTextEdit()
        self.content_edit.setStyleSheet(
            "font-family: 'Microsoft YaHei'; font-size: 14px;")
        self.content_edit.textChanged.connect(self._update_word_count)
        layout.addWidget(self.content_edit, 1)

        self.word_count_label = QLabel("字数: 0")
        self.word_count_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.word_count_label)

        # ── 盘古元信息面板 (BUG-014 配套 GUI:把剥离出来的钩子/爽点/伏笔/下章选项展示)
        self.pangu_meta_box = QGroupBox(
            "📌 本章元信息(钩子/爽点/伏笔/下一章选项)— 已自动从正文剥离,会引导下一章生成")
        self.pangu_meta_box.setStyleSheet(
            "QGroupBox { border: 2px solid #b4884e; margin-top: 8px; padding-top: 14px; "
            "  background: #fffbf2; color:#3a3f47; } "
            "QGroupBox::title { color: #977242; font-weight: bold; left: 10px; "
            "  font-size: 13px; }")
        pml = QVBoxLayout(self.pangu_meta_box)
        pml.setContentsMargins(8, 4, 8, 6)
        pml.setSpacing(4)
        # 顶部说明:这些信息会自动用于下一章生成
        tip = QLabel(
            "💡 这些信息**自动注入下一章生成**:钩子做开篇,选项做走向,爽点防重复。"
            "你也可以点下方按钮手动指定下一章开局。")
        tip.setWordWrap(True)
        tip.setStyleSheet(
            "color:#4e79cd; padding:4px 6px; background:#eaf3ff; "
            "border-left:3px solid #1a4480; font-size:11px;")
        pml.addWidget(tip)
        self.pangu_hook_label = QLabel("断章钩子: —")
        self.pangu_hook_label.setWordWrap(True)
        self.pangu_hook_label.setStyleSheet("color:#6d6d6d; padding:2px 4px;")
        pml.addWidget(self.pangu_hook_label)
        self.pangu_cool_label = QLabel("本章爽点: —")
        self.pangu_cool_label.setWordWrap(True)
        self.pangu_cool_label.setStyleSheet("color:#6d6d6d; padding:2px 4px;")
        pml.addWidget(self.pangu_cool_label)
        self.pangu_seeds_label = QLabel("伏笔: —")
        self.pangu_seeds_label.setStyleSheet("color:#6d6d6d; padding:2px 4px;")
        pml.addWidget(self.pangu_seeds_label)
        # 下一章选项区:3 个按钮,点哪个就用哪个开局生成下一章
        nl = QLabel("下一章选项(点按钮用此选项作为下一章开局指引):")
        nl.setStyleSheet("color:#6d7c95; padding:4px 4px 0; font-size:11px;")
        pml.addWidget(nl)
        self.pangu_next_opt_row = QHBoxLayout()
        self.pangu_next_opt_row.setSpacing(4)
        pml.addLayout(self.pangu_next_opt_row)
        self.pangu_next_opt_btns = []
        self.pangu_meta_box.setVisible(False)  # 章节没元信息时整块隐藏
        layout.addWidget(self.pangu_meta_box)

        # 盘古禁用词实时高亮(Phase A 新增)
        try:
            self.pangu_highlighter = _PanguForbiddenHighlighter(self.content_edit.document())
        except Exception:
            self.pangu_highlighter = None

    def _pick_editor_fg(self):
        """v1.20:选择编辑器文字颜色 + 持久化 + 立即应用"""
        from PyQt5.QtWidgets import QColorDialog
        from PyQt5.QtGui import QColor
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "Editor")
        cur = s.value("fg", "", type=str)
        init = QColor(cur) if cur else QColor("#d4d4d4")
        c = QColorDialog.getColor(init, self, "选择文字颜色")
        if c.isValid():
            hex_str = c.name()
            s.setValue("fg", hex_str)
            self._apply_editor_colors()

    def _pick_editor_bg(self):
        """v1.20:选择编辑器背景颜色 + 持久化 + 立即应用"""
        from PyQt5.QtWidgets import QColorDialog
        from PyQt5.QtGui import QColor
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "Editor")
        cur = s.value("bg", "", type=str)
        init = QColor(cur) if cur else QColor("#1a1a1a")
        c = QColorDialog.getColor(init, self, "选择背景颜色")
        if c.isValid():
            hex_str = c.name()
            s.setValue("bg", hex_str)
            self._apply_editor_colors()

    def _reset_editor_colors(self):
        """v1.20:重置 → 删 QSettings 里的 fg/bg → 应用空 stylesheet → 跟随全局主题"""
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "Editor")
        s.remove("fg")
        s.remove("bg")
        self._apply_editor_colors()

    def _apply_editor_colors(self):
        """读 QSettings 的 fg/bg,组合成 stylesheet 应用到 content_edit"""
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "Editor")
        fg = s.value("fg", "", type=str)
        bg = s.value("bg", "", type=str)
        # 字体保留原值
        base = "font-family: 'Microsoft YaHei'; font-size: 14px;"
        style_parts = [base]
        if fg:
            style_parts.append(f"color: {fg};")
        if bg:
            style_parts.append(f"background-color: {bg};")
        self.content_edit.setStyleSheet(" ".join(style_parts))

    def _update_word_count(self):
        text = self.content_edit.toPlainText()
        count = len(re.sub(r'\s', '', text))
        self.word_count_label.setText(f"字数: {count}")

    def _on_save(self):
        self.save_requested.emit(
            self.title_input.text(), self.content_edit.toPlainText())

    def _on_optimize(self):
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.warning(self, "提示", "章节内容为空,无法优化")
            return
        self.optimize_requested.emit(c)

    def _on_pangu_lint(self):
        # 本地 0-token 词扫
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空,没什么可扫的。")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古",
                "找不到 pangu_system.py,请确认它在仓库根目录。")
            return
        r = get_default_engine().quick_chapter_lint(c)
        status = "OK 通过" if r.get("pass") else "WARN 未通过"
        msg = f"{status}  得分 {r.get('score', 0)} / 100\n\n"
        issues = r.get("issues", [])
        if issues:
            msg += "问题清单:\n" + "\n".join(f"• {x}" for x in issues) + "\n\n"
        stats = r.get("stats", {})
        if stats:
            msg += "统计:\n"
            for k, v in stats.items():
                msg += f"  {k}: {v}\n"
        QMessageBox.information(self, "盘古本地词扫结果", msg)
        self.pangu_quicklint_requested.emit(c)

    def _on_pangu_qcheck(self):
        # 发起 30 项质检(调 AI)
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空")
            return
        self.pangu_qcheck_requested.emit(c)

    def _on_laodao_critique(self):
        # 发起老刀毒舌点评(调 AI)
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空")
            return
        self.laodao_critique_requested.emit(c)

    def _on_pangu_spiral(self):
        # 发起 P1-P7 螺旋诊断(调 AI)
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空")
            return
        self.pangu_spiral_requested.emit(c)

    def load_chapter(self, title, content):
        self.title_input.setText(title)
        self.content_edit.setPlainText(content)
        # 章节没有 meta(纯 load 走这里),清空面板
        self._set_pangu_meta_display(None)

    def show_chapter(self, ch_dict, idx):
        """加载并跟踪当前章节索引(供风格检测和备选版本使用)"""
        self.current_index = idx
        self.title_input.setText(ch_dict.get("title", f"第{idx+1}章"))
        self.content_edit.setPlainText(ch_dict.get("content", ""))
        # 显示元信息(BUG-014:从 chapter dict 读 hook/cool_points/next_options)
        self._set_pangu_meta_display(ch_dict)

    def _set_pangu_meta_display(self, ch_dict):
        """根据章节 dict 更新盘古元信息面板。
        ch_dict 为 None 或没元信息 → 整块隐藏。"""
        # 清除旧的下一章选项按钮
        while self.pangu_next_opt_row.count():
            it = self.pangu_next_opt_row.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.pangu_next_opt_btns = []

        has_any = False
        if ch_dict:
            hook = ch_dict.get("hook") or {}
            cool = ch_dict.get("cool_points") or []
            opts = ch_dict.get("next_options") or []
            # 钩子
            if hook and (hook.get("type") or hook.get("content")):
                bits = []
                if hook.get("type"):      bits.append(hook["type"])
                if hook.get("intensity"): bits.append(hook["intensity"])
                head = " / ".join(bits)
                content = hook.get("content", "")
                self.pangu_hook_label.setText(f"<b>断章钩子:</b> [{head}] {content}")
                has_any = True
            else:
                self.pangu_hook_label.setText("断章钩子: —")
            # 爽点
            if cool:
                self.pangu_cool_label.setText(
                    "<b>本章爽点:</b> " + "  ".join(f"• {p}" for p in cool[:5]))
                has_any = True
            else:
                self.pangu_cool_label.setText("本章爽点: —")
            # 伏笔(从 chapter['hook']/['seeds_planted_count'] 拿,如有)
            sp = ch_dict.get("_pangu_seeds_summary") or ""
            if sp:
                self.pangu_seeds_label.setText(f"<b>伏笔:</b> {sp} (已自动入伏笔追踪库)")
                has_any = True
            else:
                self.pangu_seeds_label.setText("伏笔: — (没有埋雷/收雷)")
            # 下一章选项
            for i, opt in enumerate(opts[:5]):
                btn = QPushButton(f"{i+1}. {opt[:60]}{'…' if len(opt) > 60 else ''}")
                # v1.94 BUG-068:显式指定 color(原样式漏写,默认前景色在某些主题下
                # 跟米色背景对比度极低,文字几乎不可见 — 截图反馈"按钮看不清")
                btn.setStyleSheet(
                    "QPushButton { text-align:left; padding:4px 8px; "
                    "color:#3a2a10; "                                   # 深棕,配米色背景对比度 >7:1
                    "background:#fff8ea; border:1px solid #e0c896; } "
                    "QPushButton:hover { background:#ffe9b8; color:#000; }")  # hover 更深
                btn.setToolTip(opt)
                btn.clicked.connect(lambda _, x=opt: self.next_option_picked.emit(x))
                self.pangu_next_opt_btns.append(btn)
                self.pangu_next_opt_row.addWidget(btn)
                has_any = True
            self.pangu_next_opt_row.addStretch()

        self.pangu_meta_box.setVisible(bool(has_any))

    current_index = -1  # 当前选中的章节索引(-1 表示无)
