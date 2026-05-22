# -*- coding: utf-8 -*-
"""ui/tabs/book_splitter.py - 拆书学习 Tab(170 行)

v2.03 P4 拆分:从 novel_ai.py 第 487-656 行整体搬运,内容零修改。
"""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

# book_splitter 可用性 flag - 各文件独立判断,避免循环 import
try:
    import book_splitter  # noqa: F401
    BOOK_SPLITTER_AVAILABLE = True
except ImportError:
    book_splitter = None  # 占位,运行时 BookSplitterTab 内部已有 None 检查
    BOOK_SPLITTER_AVAILABLE = False


class BookSplitterTab(QWidget):
    """v1.38: 拆书功能 — 导入未写完的小说 TXT,自动拆章节 + AI 分析"""
    # 信号:用户点了"分析本章" → main window 接管 AI 调用
    request_chapter_analysis = pyqtSignal(int, str)   # (chapter_idx, content)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.book_meta = None   # 当前加载的 BookMeta
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        # ── 顶部:文件加载区 ──
        load_box = QGroupBox("📚 导入小说(.txt)")
        load_lay = QVBoxLayout(load_box)
        ld_row = QHBoxLayout()
        self.btn_load_file = QPushButton("📂 选择 .txt 文件...")
        self.btn_load_file.setStyleSheet(
            "QPushButton { background:#3498db; color:white; padding:8px 16px; "
            "border-radius:3px; font-weight:bold; }} "
            "QPushButton:hover { background:#2980b9; }")
        self.btn_load_file.clicked.connect(self._on_load_file)
        ld_row.addWidget(self.btn_load_file)
        self.lbl_loaded = QLabel("(未加载)")
        self.lbl_loaded.setStyleSheet("color:#888;")
        ld_row.addWidget(self.lbl_loaded, 1)
        load_lay.addLayout(ld_row)
        hint = QLabel(
            "ℹ 用途:导入其他作者的网文 TXT(从 TXT 小说网下载的),自动按"
            "「第 X 章 / 第 X 节」拆分,然后逐章 AI 分析(13 法 / 八大坑 / 钩子)"
            "—— 学习其他作者怎么写。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666; font-size:12px;")
        load_lay.addWidget(hint)
        lay.addWidget(load_box)

        # ── 主区:左侧章节列表 + 右侧正文/分析 ──
        from PyQt5.QtWidgets import QSplitter
        from PyQt5.QtCore import Qt as _Qt
        splitter = QSplitter(_Qt.Horizontal)

        # 左:章节列表
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        meta_lbl = QLabel("章节列表")
        meta_lbl.setStyleSheet("font-weight:bold;")
        ll.addWidget(meta_lbl)
        self.list_chapters = QListWidget()
        self.list_chapters.itemSelectionChanged.connect(self._on_chapter_selected)
        ll.addWidget(self.list_chapters, 1)
        splitter.addWidget(left)

        # 右:正文 + 分析按钮 + 分析结果
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        # 顶部:章节标题 + AI 分析按钮
        rtop = QHBoxLayout()
        self.lbl_ch_title = QLabel("(选中左侧章节查看)")
        self.lbl_ch_title.setStyleSheet("font-weight:bold; font-size:14px;")
        rtop.addWidget(self.lbl_ch_title, 1)
        self.btn_analyze = QPushButton("🔬 AI 分析本章")
        self.btn_analyze.setStyleSheet(
            "QPushButton { background:#8e44ad; color:white; padding:6px 14px; "
            "border-radius:3px; font-weight:bold; }} "
            "QPushButton:hover { background:#6c3483; }} "
            "QPushButton:disabled { background:#ccc; }")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setToolTip(
            "发给 AI 分析这一章:\n"
            "  · 13 法对话铁律评分\n"
            "  · 八大坑各项评分\n"
            "  · 章末钩子强度 / 爽点分布\n"
            "  · 章节结构总评")
        self.btn_analyze.clicked.connect(self._on_analyze_current)
        rtop.addWidget(self.btn_analyze)
        rl.addLayout(rtop)
        # 正文(只读)
        self.te_content = QPlainTextEdit()
        self.te_content.setReadOnly(True)
        self.te_content.setPlaceholderText("章节正文将显示在这里...")
        rl.addWidget(self.te_content, 2)
        # 分析结果(只读)
        ana_lbl = QLabel("🔬 AI 分析结果")
        ana_lbl.setStyleSheet("font-weight:bold; color:#8e44ad; padding-top:6px;")
        rl.addWidget(ana_lbl)
        self.te_analysis = QPlainTextEdit()
        self.te_analysis.setReadOnly(True)
        self.te_analysis.setPlaceholderText(
            "点上方「🔬 AI 分析本章」让 AI 评分这一章。\n"
            "  · 评分细分:13 法 + 八大坑 + 钩子强度 + 爽点密度\n"
            "  · 可对比自己的章节看差距")
        from PyQt5.QtGui import QFont as _QF
        self.te_analysis.setFont(_QF("Consolas", 10))
        rl.addWidget(self.te_analysis, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        lay.addWidget(splitter, 1)

    def _on_load_file(self):
        if not BOOK_SPLITTER_AVAILABLE:
            QMessageBox.warning(self, "拆书模块不可用",
                "book_splitter.py 没找到。请确认文件存在。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择小说 TXT 文件", "",
            "TXT 文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            meta = book_splitter.load_and_split(path)
        except Exception as e:
            QMessageBox.critical(self, "拆书失败", f"加载失败:{e}")
            return
        self.book_meta = meta
        self.lbl_loaded.setText(
            f"📖 {meta.title}  |  {meta.chapter_count} 章  |  "
            f"共 {meta.total_words:,} 字  |  编码 {meta.encoding}")
        self.lbl_loaded.setStyleSheet("color:#27ae60; font-weight:bold;")
        # 填章节列表
        self.list_chapters.clear()
        for ch in meta.chapters:
            self.list_chapters.addItem(
                f"第 {ch.index} 章: {ch.title_clean or '(无标题)'} "
                f"({ch.word_count:,} 字)")
        if meta.chapter_count > 0:
            self.list_chapters.setCurrentRow(0)

    def _on_chapter_selected(self):
        if not self.book_meta:
            return
        row = self.list_chapters.currentRow()
        if not (0 <= row < len(self.book_meta.chapters)):
            self.btn_analyze.setEnabled(False)
            return
        ch = self.book_meta.chapters[row]
        self.lbl_ch_title.setText(
            f"第 {ch.index} 章: {ch.title_clean or '(无标题)'}")
        self.te_content.setPlainText(ch.content)
        # 加载之前的分析结果(如果有)
        if ch.analysis:
            self.te_analysis.setPlainText(ch.analysis.get("report", ""))
        else:
            self.te_analysis.setPlainText("")
        self.btn_analyze.setEnabled(True)

    def _on_analyze_current(self):
        if not self.book_meta:
            return
        row = self.list_chapters.currentRow()
        if not (0 <= row < len(self.book_meta.chapters)):
            return
        ch = self.book_meta.chapters[row]
        # 发信号给 MainWindow 处理 AI 调用
        self.request_chapter_analysis.emit(row, ch.content)
        self.te_analysis.setPlainText("⏳ AI 分析中...约 1 分钟...")
        self.btn_analyze.setEnabled(False)

    def receive_analysis_result(self, ch_idx: int, report: str):
        """MainWindow 调用 — AI 分析完成后写回"""
        if not self.book_meta or not (0 <= ch_idx < len(self.book_meta.chapters)):
            return
        self.book_meta.chapters[ch_idx].analysis = {"report": report}
        # 如果用户还在这一章 → 立刻显示
        if self.list_chapters.currentRow() == ch_idx:
            self.te_analysis.setPlainText(report)
        self.btn_analyze.setEnabled(True)
