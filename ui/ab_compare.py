# -*- coding: utf-8 -*-
"""ui/ab_compare.py - A/B 对比对话框

左右并排显示两个版本，用户选择保留哪个。
v2.14.4 新增。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QSplitter, QWidget,
)


class ABCompareDialog(QDialog):
    """A/B 对比对话框"""

    PICK_NONE = 0
    PICK_A = 1
    PICK_B = 2

    def __init__(self, title_a, text_a, title_b, text_b, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 A/B 对比 — 选择更好的版本")
        self.resize(1100, 650)
        self.picked = self.PICK_NONE

        layout = QVBoxLayout(self)

        # 统计行
        len_a = len(text_a.replace(" ", "").replace("\n", ""))
        len_b = len(text_b.replace(" ", "").replace("\n", ""))
        stats = QLabel(f"A 版 {len_a} 字 | B 版 {len_b} 字")
        stats.setAlignment(Qt.AlignCenter)
        stats.setStyleSheet("color:#8fa3c4; font-size:12px; padding:4px;")
        layout.addWidget(stats)

        # 左右分栏
        splitter = QSplitter(Qt.Horizontal)

        # A 版
        panel_a = QWidget()
        lay_a = QVBoxLayout(panel_a)
        lay_a.setContentsMargins(4, 4, 4, 4)
        lbl_a = QLabel(f"📄 {title_a}")
        lbl_a.setStyleSheet("font-weight:bold; font-size:14px; color:#3498db;")
        lay_a.addWidget(lbl_a)
        self.edit_a = QPlainTextEdit()
        self.edit_a.setPlainText(text_a)
        self.edit_a.setReadOnly(True)
        self.edit_a.setStyleSheet("font-size:13px; line-height:1.6;")
        lay_a.addWidget(self.edit_a)
        btn_a = QPushButton("✅ 保留 A 版")
        btn_a.setStyleSheet(
            "QPushButton { background:#3498db; color:white; padding:10px;"
            "font-size:14px; font-weight:bold; border-radius:4px; } "
            "QPushButton:hover { background:#2980b9; }")
        btn_a.clicked.connect(self._pick_a)
        lay_a.addWidget(btn_a)
        splitter.addWidget(panel_a)

        # B 版
        panel_b = QWidget()
        lay_b = QVBoxLayout(panel_b)
        lay_b.setContentsMargins(4, 4, 4, 4)
        lbl_b = QLabel(f"📄 {title_b}")
        lbl_b.setStyleSheet("font-weight:bold; font-size:14px; color:#e74c3c;")
        lay_b.addWidget(lbl_b)
        self.edit_b = QPlainTextEdit()
        self.edit_b.setPlainText(text_b)
        self.edit_b.setReadOnly(True)
        self.edit_b.setStyleSheet("font-size:13px; line-height:1.6;")
        lay_b.addWidget(self.edit_b)
        btn_b = QPushButton("✅ 保留 B 版")
        btn_b.setStyleSheet(
            "QPushButton { background:#e74c3c; color:white; padding:10px;"
            "font-size:14px; font-weight:bold; border-radius:4px; } "
            "QPushButton:hover { background:#c0392b; }")
        btn_b.clicked.connect(self._pick_b)
        lay_b.addWidget(btn_b)
        splitter.addWidget(panel_b)

        layout.addWidget(splitter)

    def _pick_a(self):
        self.picked = self.PICK_A
        self.accept()

    def _pick_b(self):
        self.picked = self.PICK_B
        self.accept()
