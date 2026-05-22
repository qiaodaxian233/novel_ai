# -*- coding: utf-8 -*-
"""ui/debug_panel.py - DEBUG 面板

捕获所有 print() 输出 + 关键状态变化,出问题一键复制发给开发者。
v2.13.3 新增。
"""
import sys
import io
from datetime import datetime

from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QApplication, QCheckBox,
)


class _StdoutCapture(QObject):
    """拦截 sys.stdout,同时写原 stdout + 发信号给 DEBUG 面板"""
    text_written = pyqtSignal(str)

    def __init__(self, original):
        super().__init__()
        self._original = original

    def write(self, text):
        if self._original:
            self._original.write(text)
        if text and text.strip():
            self.text_written.emit(text)

    def flush(self):
        if self._original:
            self._original.flush()

    def fileno(self):
        if self._original:
            return self._original.fileno()
        raise io.UnsupportedOperation("fileno")

    def isatty(self):
        return False


class DebugPanel(QWidget):
    """DEBUG 面板 — 捕获 print + 状态变化 + 异常"""

    MAX_LINES = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("🔧 DEBUG 输出(内部状态 + print 捕获)"))
        toolbar.addStretch()

        self.chk_capture = QCheckBox("捕获 print")
        self.chk_capture.setChecked(True)
        self.chk_capture.stateChanged.connect(self._toggle_capture)
        toolbar.addWidget(self.chk_capture)

        btn_copy = QPushButton("📋 复制全部")
        btn_copy.clicked.connect(self._copy_all)
        btn_copy.setStyleSheet(
            "QPushButton { background:#1a73e8; color:white; padding:4px 12px;"
            "border-radius:3px; } "
            "QPushButton:hover { background:#1557b0; }")
        toolbar.addWidget(btn_copy)

        btn_clear = QPushButton("🗑 清空")
        btn_clear.clicked.connect(self._clear)
        toolbar.addWidget(btn_clear)

        layout.addLayout(toolbar)

        # 日志区
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(self.MAX_LINES)
        self.log_edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 11px; background: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.log_edit)

        # stdout 捕获
        self._capture = None
        self._original_stdout = sys.stdout
        self._start_capture()

    def _start_capture(self):
        if self._capture is None:
            self._capture = _StdoutCapture(self._original_stdout)
            self._capture.text_written.connect(self._on_stdout)
            sys.stdout = self._capture

    def _stop_capture(self):
        if self._capture is not None:
            sys.stdout = self._original_stdout
            self._capture = None

    def _toggle_capture(self, state):
        if state:
            self._start_capture()
        else:
            self._stop_capture()

    def _on_stdout(self, text):
        for line in text.splitlines():
            if line.strip():
                ts = datetime.now().strftime("%H:%M:%S.%f")[:12]
                self.log_edit.appendPlainText(f"[{ts}] {line}")
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def debug(self, msg, tag="DEBUG"):
        """手动写入一条 debug 日志"""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:12]
        self.log_edit.appendPlainText(f"[{ts}] [{tag}] {msg}")
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_all(self):
        text = self.log_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.debug(f"已复制 {len(text)} 字符到剪贴板", "SYS")

    def _clear(self):
        self.log_edit.clear()
        self.debug("已清空", "SYS")

    def closeEvent(self, event):
        self._stop_capture()
        super().closeEvent(event)
