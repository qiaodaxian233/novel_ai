# -*- coding: utf-8 -*-
"""ui/ai_toolbox_tab.py - 🛠 AI 工具箱 Tab

v2.23.4: 直接访问 AI 修改章节。
选章节 → 输入指令 → 发给 DeepSeek → 修改完填回。
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget, QMessageBox,
    QFrame,
)


class AIToolboxTab(QWidget):
    """🛠 AI 工具箱 — 用 AI 直接修改选定章节"""

    # 发给主进程:chapter_idx, prompt_text
    request_ai_modify = pyqtSignal(int, str)
    request_log = pyqtSignal(str, str)

    def __init__(self, mw=None, parent=None):
        super().__init__(parent)
        self.mw = mw
        self._ai_result = ""
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(12)

        # ── 标题 ──
        title = QLabel("🛠 AI 工具箱")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        lay.addWidget(title)

        hint = QLabel(
            "选择一个章节,输入修改指令,AI 会根据指令重写该章节内容。"
            "修改后预览确认,再一键填充回去。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666; font-size:12px; padding-bottom:4px;")
        lay.addWidget(hint)

        # ── 章节选择行 ──
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("选择章节:"))
        self.cmb_chapter = QComboBox()
        self.cmb_chapter.setMinimumWidth(300)
        self.cmb_chapter.currentIndexChanged.connect(self._on_chapter_changed)
        sel_row.addWidget(self.cmb_chapter, 1)

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self.refresh_chapters)
        sel_row.addWidget(self.btn_refresh)
        lay.addLayout(sel_row)

        # ── 中间:左(原文) + 右(修改指令 + 结果) ──
        splitter = QSplitter(Qt.Horizontal)

        # 左:原文预览
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lbl = QLabel("📄 原文预览")
        left_lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        left_lay.addWidget(left_lbl)
        self.txt_original = QPlainTextEdit()
        self.txt_original.setReadOnly(True)
        self.txt_original.setPlaceholderText("选择章节后这里显示原文...")
        self.txt_original.setStyleSheet(
            "background:#fafbfd; font-size:12px; line-height:1.6;")
        left_lay.addWidget(self.txt_original)
        splitter.addWidget(left)

        # 右:指令 + 结果
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # 修改指令
        right_lay.addWidget(QLabel("✏️ 修改指令"))
        self.txt_prompt = QPlainTextEdit()
        self.txt_prompt.setMaximumHeight(120)
        self.txt_prompt.setPlaceholderText(
            "输入修改指令,例如:\n"
            "· 把对话改得更有情感张力\n"
            "· 加入环境描写,营造紧张氛围\n"
            "· 把打斗场面扩写到 2000 字\n"
            "· 修改女主的对白,语气更加傲娇")
        right_lay.addWidget(self.txt_prompt)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.btn_send = QPushButton("🤖 发送给 AI 修改")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: #4a9eff; color: white;
                padding: 10px 24px; font-size: 13px; font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover { background: #3584e4; }
        """)
        self.btn_send.clicked.connect(self._on_send)
        btn_row.addWidget(self.btn_send)

        self.btn_apply = QPushButton("✅ 确认填充回章节")
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background: #27ae60; color: white;
                padding: 10px 24px; font-size: 13px; font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover { background: #219a52; }
            QPushButton:disabled { background: #c0c8d4; }
        """)
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self.btn_apply)
        btn_row.addStretch()
        right_lay.addLayout(btn_row)

        # AI 结果预览
        right_lay.addWidget(QLabel("🤖 AI 修改结果"))
        self.txt_result = QPlainTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setPlaceholderText("AI 修改后的内容会显示在这里...")
        self.txt_result.setStyleSheet(
            "background:#f0fff0; font-size:12px; line-height:1.6;")
        right_lay.addWidget(self.txt_result)

        splitter.addWidget(right)
        splitter.setSizes([400, 500])
        lay.addWidget(splitter, 1)

        # ── 状态 ──
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#888; font-size:11px;")
        lay.addWidget(self.lbl_status)

    # ──────────── 数据 ────────────

    def refresh_chapters(self):
        """刷新章节下拉列表"""
        self.cmb_chapter.clear()
        if not self.mw:
            return
        chapters = getattr(self.mw, "chapters", [])
        for i, ch in enumerate(chapters):
            title = ch.get("title", f"第{i+1}章") if isinstance(ch, dict) else f"第{i+1}章"
            content = ch.get("content", "") if isinstance(ch, dict) else str(ch)
            word_count = len(content.replace(" ", "").replace("\n", ""))
            self.cmb_chapter.addItem(
                f"第{i+1}章  {title}  ({word_count}字)", i)
        if self.cmb_chapter.count() == 0:
            self.cmb_chapter.addItem("(无章节)", -1)

    def _on_chapter_changed(self, idx):
        """章节选择变化 → 显示原文"""
        if idx < 0:
            return
        ch_idx = self.cmb_chapter.itemData(idx)
        if ch_idx is None or ch_idx < 0:
            self.txt_original.setPlainText("")
            return
        if not self.mw:
            return
        chapters = getattr(self.mw, "chapters", [])
        if 0 <= ch_idx < len(chapters):
            ch = chapters[ch_idx]
            content = ch.get("content", "") if isinstance(ch, dict) else str(ch)
            self.txt_original.setPlainText(content)
            wc = len(content.replace(" ", "").replace("\n", ""))
            self.lbl_status.setText(f"已加载第 {ch_idx+1} 章,{wc} 字")
        self.txt_result.clear()
        self.btn_apply.setEnabled(False)

    # ──────────── 操作 ────────────

    def _on_send(self):
        """发送给 AI 修改"""
        ch_idx = self.cmb_chapter.currentData()
        if ch_idx is None or ch_idx < 0:
            QMessageBox.information(self, "提示", "请先选择一个章节")
            return
        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.information(self, "提示", "请输入修改指令")
            return

        original = self.txt_original.toPlainText()
        if not original.strip():
            QMessageBox.information(self, "提示", "章节内容为空")
            return

        self.btn_send.setEnabled(False)
        self.btn_send.setText("AI 处理中...")
        self.btn_apply.setEnabled(False)
        self.txt_result.setPlainText("等待 AI 回复...")
        self.lbl_status.setText(f"正在发送第 {ch_idx+1} 章到 AI...")

        # 拼 prompt
        full_prompt = (
            f"请根据以下指令修改这段小说内容。\n\n"
            f"【修改指令】\n{prompt}\n\n"
            f"【原文内容】\n{original}\n\n"
            f"【要求】\n"
            f"1. 只输出修改后的完整章节内容\n"
            f"2. 不要输出任何解释、标题、分隔符\n"
            f"3. 保持原文的人称、时态、风格\n"
            f"4. 不要添加「以下是修改后的内容」这类前缀\n"
            f"5. 直接输出修改后的正文"
        )

        self.request_ai_modify.emit(ch_idx, full_prompt)

    def on_ai_result(self, result_text):
        """主进程回调:AI 返回修改结果"""
        self.btn_send.setEnabled(True)
        self.btn_send.setText("🤖 发送给 AI 修改")

        if not result_text or not result_text.strip():
            self.txt_result.setPlainText("(AI 返回为空)")
            self.lbl_status.setText("⚠ AI 未返回有效内容")
            return

        self._ai_result = result_text.strip()
        self.txt_result.setPlainText(self._ai_result)
        self.btn_apply.setEnabled(True)

        wc_old = len(self.txt_original.toPlainText().replace(" ", "").replace("\n", ""))
        wc_new = len(self._ai_result.replace(" ", "").replace("\n", ""))
        self.lbl_status.setText(
            f"✅ AI 修改完成  原文 {wc_old} 字 → 新文 {wc_new} 字  "
            f"(差 {wc_new - wc_old:+d} 字)")

    def _on_apply(self):
        """确认填充回章节"""
        ch_idx = self.cmb_chapter.currentData()
        if ch_idx is None or ch_idx < 0:
            return
        if not self._ai_result:
            return

        reply = QMessageBox.question(
            self, "确认填充",
            f"确定用 AI 修改后的内容替换第 {ch_idx+1} 章?\n"
            f"(原文会被覆盖,建议先确认 AI 结果无误)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        if not self.mw:
            return
        chapters = getattr(self.mw, "chapters", [])
        if 0 <= ch_idx < len(chapters):
            ch = chapters[ch_idx]
            if isinstance(ch, dict):
                ch["content"] = self._ai_result
            self.lbl_status.setText(
                f"✅ 第 {ch_idx+1} 章已更新!内容已填充回去。")
            self.btn_apply.setEnabled(False)

            # 通知主窗口刷新
            try:
                self.mw._refresh_chapter_list()
                self.mw.save_project()
            except Exception:
                pass
