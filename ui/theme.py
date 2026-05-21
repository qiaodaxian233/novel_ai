# -*- coding: utf-8 -*-
"""
ui/theme.py - 应用主题管理器(亮/暗主题切换 + QSettings 持久化)

v2.02 P3 拆分:从 novel_ai.py 第 216-439 行整体搬运,内容零修改。
被 novel_ai.py 顶部 `from ui.theme import ThemeManager` 导入。
"""

from PyQt5.QtCore import QSettings

class ThemeManager:
    """v1.20 全局主题管理器
    - light:默认浅色主题(保持原貌)
    - dark:深炭灰主题(VSCode Dark 同款色板,保留 ✨ 金色强调)
    - apply(app, name):一键切换,持久化到 QSettings('NovelAI','UI').theme
    """
    LIGHT_QSS = ""   # 空字符串 = 用 Qt 默认浅色主题

    DARK_QSS = """
    /* ─── 主背景 + 文字 ─── */
    QMainWindow, QWidget, QDialog, QFrame {
        background-color: #1e1e1e;
        color: #d4d4d4;
    }

    /* ─── 文本输入 ─── */
    QPlainTextEdit, QTextEdit, QLineEdit {
        background-color: #1a1a1a;
        color: #d4d4d4;
        border: 1px solid #3c3c3c;
        selection-background-color: #094771;
    }

    /* ─── GroupBox 框 ─── */
    QGroupBox {
        border: 1px solid #3c3c3c;
        margin-top: 12px;
        padding-top: 6px;
        color: #d4d4d4;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        color: #d4d4d4;
    }

    /* ─── Tab ─── */
    QTabWidget::pane {
        background-color: #1e1e1e;
        border: 1px solid #3c3c3c;
    }
    QTabBar::tab {
        background-color: #2d2d30;
        color: #d4d4d4;
        padding: 6px 14px;
        border: 1px solid #3c3c3c;
        border-bottom: 0;
    }
    QTabBar::tab:selected {
        background-color: #094771;
        color: #ffffff;
    }
    QTabBar::tab:hover {
        background-color: #3c3c3c;
    }

    /* ─── 表格 / 树 / 列表 ─── */
    QTableWidget, QTreeWidget, QListWidget, QTableView, QTreeView, QListView {
        background-color: #1a1a1a;
        color: #d4d4d4;
        gridline-color: #3c3c3c;
        alternate-background-color: #252526;
        selection-background-color: #094771;
        selection-color: #ffffff;
    }
    QHeaderView::section {
        background-color: #2d2d30;
        color: #d4d4d4;
        border: 1px solid #3c3c3c;
        padding: 4px;
    }

    /* ─── 下拉 / 微调 ─── */
    QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {
        background-color: #3c3c3c;
        color: #d4d4d4;
        border: 1px solid #555;
        padding: 3px 6px;
    }
    QComboBox QAbstractItemView {
        background-color: #2d2d30;
        color: #d4d4d4;
        selection-background-color: #094771;
    }

    /* ─── Checkbox / Radio(保留特殊 color 如金色,只换通用)─── */
    QCheckBox, QRadioButton {
        color: #d4d4d4;
        spacing: 6px;
    }

    /* ─── 菜单 ─── */
    QMenuBar {
        background-color: #2d2d30;
        color: #d4d4d4;
    }
    QMenuBar::item:selected {
        background-color: #094771;
    }
    QMenu {
        background-color: #2d2d30;
        color: #d4d4d4;
        border: 1px solid #3c3c3c;
    }
    QMenu::item:selected {
        background-color: #094771;
    }

    /* ─── 滚动条 ─── */
    QScrollBar:vertical {
        background-color: #1e1e1e;
        width: 12px;
        border: 0;
    }
    QScrollBar::handle:vertical {
        background-color: #3c3c3c;
        min-height: 24px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #4f4f4f;
    }
    QScrollBar:horizontal {
        background-color: #1e1e1e;
        height: 12px;
        border: 0;
    }
    QScrollBar::handle:horizontal {
        background-color: #3c3c3c;
        min-width: 24px;
        border-radius: 3px;
    }
    QScrollBar::add-line, QScrollBar::sub-line { background: none; }

    /* ─── 状态栏 / 工具栏 / 分隔线 ─── */
    QStatusBar {
        background-color: #2d2d30;
        color: #d4d4d4;
    }
    QToolBar {
        background-color: #2d2d30;
        border: 0;
    }
    QSplitter::handle {
        background-color: #3c3c3c;
    }

    /* ─── 标签 / 工具提示 ─── */
    QLabel {
        color: #d4d4d4;
        background: transparent;
    }
    QToolTip {
        background-color: #2d2d30;
        color: #d4d4d4;
        border: 1px solid #555;
    }

    /* ─── ✨ 金色强调保留(用户要求)─── */
    /* 局部 setStyleSheet('color:#b4884e') 会自然覆盖此处通用色 */
    """

    @classmethod
    def apply(cls, app, name):
        """app 是 QApplication 实例,name = 'light' 或 'dark'
        v1.33 BUG-047: Fusion style 的 background/text 受 QPalette 控制,
        QSS 优先级低 → 必须同时设 QPalette + QSS 才能完全切换主题。
        """
        from PyQt5.QtGui import QPalette, QColor
        from PyQt5.QtCore import Qt
        # 1. 设 QPalette(Fusion style 听这个)
        palette = QPalette()
        if name == "dark":
            # VSCode Dark 同款色板
            palette.setColor(QPalette.Window,           QColor("#1e1e1e"))   # 主窗口背景
            palette.setColor(QPalette.WindowText,       QColor("#d4d4d4"))   # 主文字
            palette.setColor(QPalette.Base,             QColor("#1a1a1a"))   # 输入框/编辑器底
            palette.setColor(QPalette.AlternateBase,    QColor("#252526"))   # 表格隔行
            palette.setColor(QPalette.ToolTipBase,      QColor("#2d2d30"))
            palette.setColor(QPalette.ToolTipText,      QColor("#d4d4d4"))
            palette.setColor(QPalette.Text,             QColor("#d4d4d4"))   # 输入框文字
            palette.setColor(QPalette.Button,           QColor("#3c3c3c"))   # 按钮底
            palette.setColor(QPalette.ButtonText,       QColor("#d4d4d4"))
            palette.setColor(QPalette.BrightText,       QColor("#ffffff"))
            palette.setColor(QPalette.Link,             QColor("#3794ff"))
            palette.setColor(QPalette.Highlight,        QColor("#094771"))   # 选中蓝
            palette.setColor(QPalette.HighlightedText,  QColor("#ffffff"))
            # Disabled 状态(防止灰按钮看不清)
            palette.setColor(QPalette.Disabled, QPalette.WindowText,
                             QColor("#787878"))
            palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#787878"))
            palette.setColor(QPalette.Disabled, QPalette.ButtonText,
                             QColor("#787878"))
        else:
            # light = Fusion 默认浅色(不强制改,用 standardPalette)
            from PyQt5.QtWidgets import QStyle
            palette = app.style().standardPalette()
        app.setPalette(palette)

        # 2. 再叠 QSS(细节:滚动条/表头/边框/hover)
        qss = cls.DARK_QSS if name == "dark" else cls.LIGHT_QSS
        app.setStyleSheet(qss)

        try:
            from PyQt5.QtCore import QSettings
            QSettings("NovelAI", "UI").setValue("theme", name)
        except Exception:
            pass

    @classmethod
    def current(cls):
        """读上次保存的主题(默认 light)"""
        try:
            from PyQt5.QtCore import QSettings
            return QSettings("NovelAI", "UI").value("theme", "light", type=str)
        except Exception:
            return "light"

    @classmethod
    def toggle(cls, app):
        """切换 light ↔ dark,返回新主题名"""
        new = "dark" if cls.current() == "light" else "light"
        cls.apply(app, new)
        return new
