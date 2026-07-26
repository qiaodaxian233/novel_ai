# -*- coding: utf-8 -*-
"""ui/tabs/book_splitter.py - 拆书学习 Tab

v2.19.0 升级: 批量分析 + 统计面板 + 导出报告 + 一键学习
"""
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
    QSplitter, QProgressBar,
)

try:
    import book_splitter
    BOOK_SPLITTER_AVAILABLE = True
except ImportError:
    book_splitter = None
    BOOK_SPLITTER_AVAILABLE = False


class BookSplitterTab(QWidget):
    """拆书功能 — 导入TXT,自动拆章 + AI分析 + 学习"""
    request_chapter_analysis = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.book_meta = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # ── 顶部:文件加载 + 统计 ──
        top_row = QHBoxLayout()
        self.btn_load_file = QPushButton("📂 选择 .txt 文件")
        self.btn_load_file.setStyleSheet(
            "QPushButton { background:#3498db; color:white; padding:8px 14px;"
            "border-radius:3px; font-weight:bold; }"
            "QPushButton:hover { background:#2980b9; }")
        self.btn_load_file.clicked.connect(self._on_load_file)
        top_row.addWidget(self.btn_load_file)
        self.lbl_loaded = QLabel("(未加载)")
        self.lbl_loaded.setStyleSheet("color:#6d7c95; padding:0 8px;")
        top_row.addWidget(self.lbl_loaded, 1)
        lay.addLayout(top_row)

        # 统计条
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color:#6d7c95; font-size:11px; padding:2px;")
        lay.addWidget(self.lbl_stats)

        # ── 主区 ──
        splitter = QSplitter(Qt.Horizontal)

        # 左:章节列表
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("章节列表"))
        self.list_chapters = QListWidget()
        self.list_chapters.itemSelectionChanged.connect(self._on_chapter_selected)
        ll.addWidget(self.list_chapters, 1)

        # 左底:批量操作
        btn_batch = QHBoxLayout()
        self.btn_batch_analyze = QPushButton("🔬 批量分析全书")
        self.btn_batch_analyze.setStyleSheet(
            "QPushButton { background:#b8651b; color:white; padding:6px 12px;"
            "border-radius:3px; font-weight:bold; }"
            "QPushButton:hover { background:#9a4a12; }")
        self.btn_batch_analyze.clicked.connect(self._on_batch_analyze)
        self.btn_batch_analyze.setEnabled(False)
        btn_batch.addWidget(self.btn_batch_analyze)
        self.btn_export = QPushButton("📋 导出报告")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export.setEnabled(False)
        btn_batch.addWidget(self.btn_export)
        ll.addLayout(btn_batch)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        ll.addWidget(self.progress_bar)
        splitter.addWidget(left)

        # 右:正文 + 分析
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        rtop = QHBoxLayout()
        self.lbl_ch_title = QLabel("(选中左侧章节查看)")
        self.lbl_ch_title.setStyleSheet("font-weight:bold; font-size:14px;")
        rtop.addWidget(self.lbl_ch_title, 1)
        self.btn_analyze = QPushButton("🔬 AI 分析本章")
        self.btn_analyze.setStyleSheet(
            "QPushButton { background:#8e44ad; color:white; padding:6px 14px;"
            "border-radius:3px; font-weight:bold; }"
            "QPushButton:hover { background:#6c3483; }"
            "QPushButton:disabled { background:#ccc; color:#5c5c5c; }")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self._on_analyze_current)
        rtop.addWidget(self.btn_analyze)
        self.btn_learn = QPushButton("📝 学习此章技巧")
        self.btn_learn.setStyleSheet(
            "QPushButton { background:#1f8b4d; color:white; padding:6px 14px;"
            "border-radius:3px; font-weight:bold; }"
            "QPushButton:hover { background:#186f3d; }"
            "QPushButton:disabled { background:#ccc; color:#5c5c5c; }")
        self.btn_learn.setEnabled(False)
        self.btn_learn.setToolTip("提取本章写作技巧,生成学习笔记")
        self.btn_learn.clicked.connect(self._on_learn_chapter)
        rtop.addWidget(self.btn_learn)
        rl.addLayout(rtop)

        # 正文
        self.te_content = QPlainTextEdit()
        self.te_content.setReadOnly(True)
        self.te_content.setPlaceholderText("章节正文...")
        rl.addWidget(self.te_content, 2)

        # 分析结果
        ana_lbl = QLabel("🔬 AI 分析 / 学习笔记")
        ana_lbl.setStyleSheet("font-weight:bold; color:#aa52d0; padding-top:4px;")
        rl.addWidget(ana_lbl)
        self.te_analysis = QPlainTextEdit()
        self.te_analysis.setReadOnly(True)
        self.te_analysis.setPlaceholderText(
            "点「🔬 AI 分析本章」或「📝 学习此章技巧」")
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
            f"📖 {meta.title} | {meta.chapter_count} 章 | "
            f"{meta.total_words:,} 字 | 编码 {meta.encoding}")
        self.lbl_loaded.setStyleSheet("color:#1f8b4d; font-weight:bold;")

        # 统计
        if meta.chapters:
            wcs = [ch.word_count for ch in meta.chapters]
            avg = sum(wcs) // len(wcs)
            mx = max(wcs)
            mn = min(wcs)
            self.lbl_stats.setText(
                f"📊 平均{avg:,}字/章 | 最长{mx:,}字 | 最短{mn:,}字 | "
                f"标准差{int((sum((w-avg)**2 for w in wcs)/len(wcs))**0.5):,}字")

        # 填章节列表
        self.list_chapters.clear()
        for ch in meta.chapters:
            analyzed = "✅" if ch.analysis else "  "
            self.list_chapters.addItem(
                f"{analyzed} 第{ch.index}章: {ch.title_clean or '(无标题)'} "
                f"({ch.word_count:,}字)")
        if meta.chapter_count > 0:
            self.list_chapters.setCurrentRow(0)
        self.btn_batch_analyze.setEnabled(True)
        self.btn_export.setEnabled(True)

    def _on_chapter_selected(self):
        if not self.book_meta:
            return
        row = self.list_chapters.currentRow()
        if not (0 <= row < len(self.book_meta.chapters)):
            self.btn_analyze.setEnabled(False)
            self.btn_learn.setEnabled(False)
            return
        ch = self.book_meta.chapters[row]
        self.lbl_ch_title.setText(
            f"第{ch.index}章: {ch.title_clean or '(无标题)'}")
        self.te_content.setPlainText(ch.content)
        if ch.analysis:
            self.te_analysis.setPlainText(ch.analysis.get("report", ""))
        else:
            self.te_analysis.setPlainText("")
        self.btn_analyze.setEnabled(True)
        self.btn_learn.setEnabled(True)

    def _on_analyze_current(self):
        if not self.book_meta:
            return
        row = self.list_chapters.currentRow()
        if not (0 <= row < len(self.book_meta.chapters)):
            return
        ch = self.book_meta.chapters[row]
        self.request_chapter_analysis.emit(row, ch.content)
        self.te_analysis.setPlainText("⏳ AI 分析中...")
        self.btn_analyze.setEnabled(False)

    def _on_learn_chapter(self):
        """提取本章写作技巧"""
        if not self.book_meta:
            return
        row = self.list_chapters.currentRow()
        if not (0 <= row < len(self.book_meta.chapters)):
            return
        ch = self.book_meta.chapters[row]
        content = ch.content[:6000]
        # 发分析请求(用learn类型)
        self.request_chapter_analysis.emit(row,
            f"[学习模式]请分析这章小说的写作技巧,提取可学习的要点:\n"
            f"1. 开头怎么抓人(前3句话分析)\n"
            f"2. 对话写法(自然度/信息量/节奏)\n"
            f"3. 冲突怎么设计的\n"
            f"4. 章末钩子是什么\n"
            f"5. 值得学的3个技巧\n"
            f"6. 需要避免的1个问题\n\n"
            f"章节正文:\n{content}")
        self.te_analysis.setPlainText("📝 正在提取写作技巧...")
        self.btn_learn.setEnabled(False)

    def _on_batch_analyze(self):
        """批量分析所有章节"""
        if not self.book_meta or not self.book_meta.chapters:
            return
        n = len(self.book_meta.chapters)
        ret = QMessageBox.question(
            self, "批量分析",
            f"将对 {n} 章逐一发给 AI 分析。\n"
            f"每章约需 30-60 秒,总计可能需要 {n//2}-{n} 分钟。\n\n"
            f"继续?")
        if ret != QMessageBox.Yes:
            return
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(n)
        self.progress_bar.setValue(0)
        self._batch_idx = 0
        self._batch_analyze_next()

    def _batch_analyze_next(self):
        if not self.book_meta:
            return
        n = len(self.book_meta.chapters)
        if self._batch_idx >= n:
            self.progress_bar.setVisible(False)
            QMessageBox.information(self, "完成", f"全部 {n} 章分析完成!")
            return
        ch = self.book_meta.chapters[self._batch_idx]
        if ch.analysis:
            # 已分析过,跳过
            self._batch_idx += 1
            self.progress_bar.setValue(self._batch_idx)
            self._batch_analyze_next()
            return
        self.request_chapter_analysis.emit(self._batch_idx, ch.content)
        self.progress_bar.setValue(self._batch_idx)

    def receive_analysis_result(self, ch_idx: int, report: str):
        """AI 分析完成后写回"""
        if not self.book_meta or not (0 <= ch_idx < len(self.book_meta.chapters)):
            return
        self.book_meta.chapters[ch_idx].analysis = {"report": report}
        # 更新列表显示(加 ✅)
        ch = self.book_meta.chapters[ch_idx]
        self.list_chapters.item(ch_idx).setText(
            f"✅ 第{ch.index}章: {ch.title_clean or '(无标题)'} "
            f"({ch.word_count:,}字)")
        # 如果用户还在这一章
        if self.list_chapters.currentRow() == ch_idx:
            self.te_analysis.setPlainText(report)
        self.btn_analyze.setEnabled(True)
        self.btn_learn.setEnabled(True)
        # 批量模式:继续下一章
        if hasattr(self, "_batch_idx") and self._batch_idx == ch_idx:
            self._batch_idx += 1
            self.progress_bar.setValue(self._batch_idx)
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(500, self._batch_analyze_next)

    def _on_export(self):
        """导出分析报告"""
        if not self.book_meta:
            return
        lines = [f"# 《{self.book_meta.title}》拆书分析报告\n"]
        lines.append(f"共 {self.book_meta.chapter_count} 章,"
                     f" {self.book_meta.total_words:,} 字\n")
        for ch in self.book_meta.chapters:
            lines.append(f"\n## 第{ch.index}章: {ch.title_clean or '(无标题)'}")
            lines.append(f"字数: {ch.word_count:,}\n")
            if ch.analysis:
                lines.append(ch.analysis.get("report", "(未分析)"))
            else:
                lines.append("(未分析)")
            lines.append("\n---\n")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出报告", f"{self.book_meta.title}_分析报告.md",
            "Markdown (*.md);;文本 (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "导出完成", f"已保存到:\n{path}")
