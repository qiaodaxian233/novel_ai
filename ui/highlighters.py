# -*- coding: utf-8 -*-
"""
ui/highlighters.py - 章节编辑器实时高亮器(盘古禁用词红色波浪线 + 长句段落浅黄底色)

v2.02 P3 拆分:从 novel_ai.py 第 166-215 行整体搬运,内容零修改。
被 novel_ai.py 顶部 `from ui.highlighters import _PanguForbiddenHighlighter` 导入。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor

class _PanguForbiddenHighlighter(QSyntaxHighlighter):
    """章节编辑器实时高亮:盘古禁用词红色波浪线 + 长句段落浅黄底色。"""
    def __init__(self, parent):
        super().__init__(parent)
        # 词高亮格式
        self.fmt_forbidden = QTextCharFormat()
        self.fmt_forbidden.setUnderlineColor(QColor(220, 50, 50))
        self.fmt_forbidden.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        self.fmt_forbidden.setForeground(QColor(180, 0, 0))
        # AI 质检失败段落底色
        self.fmt_qcheck = QTextCharFormat()
        self.fmt_qcheck.setBackground(QColor(255, 245, 200))
        # 缓存:词列表 + qcheck 失败段落集合
        self._words = []
        self._qcheck_block_ids = set()  # 段落号(基于 blockNumber)
        try:
            from pangu_system import PanguEngine
            self._words = PanguEngine.get_active_forbidden_words()
        except Exception:
            self._words = []

    def refresh_words(self):
        try:
            from pangu_system import PanguEngine
            self._words = PanguEngine.get_active_forbidden_words()
        except Exception:
            self._words = []
        self.rehighlight()

    def set_qcheck_blocks(self, block_ids):
        """设置质检失败的段落号集合,触发重绘。"""
        self._qcheck_block_ids = set(block_ids or [])
        self.rehighlight()

    def clear_qcheck(self):
        self._qcheck_block_ids = set()
        self.rehighlight()

    def highlightBlock(self, text):
        # 段落底色(qcheck 标记)
        if self.currentBlock().blockNumber() in self._qcheck_block_ids:
            self.setFormat(0, len(text), self.fmt_qcheck)
        # 禁用词高亮
        for w in self._words:
            if not w:
                continue
            i = text.find(w)
            while i >= 0:
                self.setFormat(i, len(w), self.fmt_forbidden)
                i = text.find(w, i + 1)
