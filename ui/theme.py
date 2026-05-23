# -*- coding: utf-8 -*-
"""ui/theme.py - 多主题管理器

支持主题: 浅色 / 暗黑 / 护眼绿 / 暖黄
v2.15.1 重写。
"""
from PyQt5.QtCore import QSettings


# ── 基础 QSS 模板 ──
_BASE_FONT = ""  # 不强制全局字体,让控件保持自己的 font-size

_QSS_TEMPLATE = """
    {base_font}
    QMainWindow, QWidget, QDialog, QFrame {{
        background-color: {bg}; color: {fg};
    }}
    QPlainTextEdit, QTextEdit, QLineEdit {{
        background-color: {input_bg}; color: {fg};
        border: 1px solid {border}; selection-background-color: {accent};
    }}
    QGroupBox {{
        border: 1px solid {border}; margin-top: 12px; padding-top: 6px; color: {fg};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: 8px; color: {fg}; font-weight: bold;
    }}
    QTabWidget::pane {{ background-color: {bg}; border: 1px solid {border}; }}
    QTabBar::tab {{
        background-color: {tab_bg}; color: {fg};
        padding: 6px 14px; border: 1px solid {border}; border-bottom: 0;
    }}
    QTabBar::tab:selected {{ background-color: {accent}; color: {accent_fg}; }}
    QTabBar::tab:hover {{ background-color: {hover}; }}
    QTableWidget, QTreeWidget, QListWidget, QTableView, QTreeView, QListView {{
        background-color: {input_bg}; color: {fg};
        gridline-color: {border}; alternate-background-color: {alt_bg};
        selection-background-color: {accent}; selection-color: {accent_fg};
    }}
    QHeaderView::section {{
        background-color: {tab_bg}; color: {fg};
        border: 1px solid {border}; padding: 4px;
    }}
    QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {hover}; color: {fg};
        border: 1px solid {border}; padding: 3px 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {tab_bg}; color: {fg}; selection-background-color: {accent};
    }}
    QCheckBox, QRadioButton {{ color: {fg}; spacing: 6px; }}
    QMenuBar {{ background-color: {tab_bg}; color: {fg}; }}
    QMenuBar::item:selected {{ background-color: {accent}; }}
    QMenu {{ background-color: {tab_bg}; color: {fg}; border: 1px solid {border}; }}
    QMenu::item:selected {{ background-color: {accent}; }}
    QPushButton {{
        background-color: {btn_bg}; color: {fg};
        border: 1px solid {border}; padding: 5px 12px; border-radius: 3px;
    }}
    QPushButton:hover {{ background-color: {hover}; }}
    QPushButton:pressed {{ background-color: {accent}; }}
    QPushButton:disabled {{ background-color: {tab_bg}; color: {dim}; }}
    QProgressBar {{
        background-color: {tab_bg}; border: 1px solid {border};
        border-radius: 3px; color: {fg}; text-align: center;
    }}
    QProgressBar::chunk {{ background-color: {accent}; border-radius: 2px; }}
    QScrollBar:vertical {{
        background-color: {bg}; width: 12px; border: 0;
    }}
    QScrollBar::handle:vertical {{
        background-color: {border}; min-height: 24px; border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{ background-color: {hover}; }}
    QScrollBar:horizontal {{ background-color: {bg}; height: 12px; border: 0; }}
    QScrollBar::handle:horizontal {{
        background-color: {border}; min-width: 24px; border-radius: 3px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ background: none; }}
    QStatusBar {{ background-color: {tab_bg}; color: {fg}; }}
    QToolBar {{ background-color: {tab_bg}; border: 0; }}
    QSplitter::handle {{ background-color: {border}; }}
    QLabel {{ color: {fg}; background: transparent; }}
    QToolTip {{ background-color: {tab_bg}; color: {fg}; border: 1px solid {border}; }}
"""


def _make_qss(**colors):
    return _QSS_TEMPLATE.format(base_font=_BASE_FONT, **colors)


class ThemeManager:
    """多主题管理器"""

    THEMES = {
        "light": {
            "label": "☀️ 浅色",
            "icon": "☀️",
            "qss": "",   # 浅色用 Fusion 默认
            "palette": None,  # 用 standardPalette
        },
        "dark": {
            "label": "🌙 暗黑",
            "icon": "🌙",
            "qss": _make_qss(
                bg="#1e1e1e", fg="#d4d4d4", input_bg="#1a1a1a",
                border="#3c3c3c", accent="#094771", accent_fg="#ffffff",
                tab_bg="#2d2d30", hover="#4f4f4f", alt_bg="#252526",
                btn_bg="#3c3c3c", dim="#787878",
            ),
            "palette": {
                "Window": "#1e1e1e", "WindowText": "#d4d4d4",
                "Base": "#1a1a1a", "AlternateBase": "#252526",
                "Text": "#d4d4d4", "Button": "#3c3c3c",
                "ButtonText": "#d4d4d4", "Highlight": "#094771",
                "HighlightedText": "#ffffff",
            },
        },
        "green": {
            "label": "🌿 护眼绿",
            "icon": "🌿",
            "qss": _make_qss(
                bg="#f0f5e6", fg="#2d3319", input_bg="#f7faf0",
                border="#c5d6a0", accent="#5a8c32", accent_fg="#ffffff",
                tab_bg="#e4edcf", hover="#d8e5bb", alt_bg="#eaf2dc",
                btn_bg="#e4edcf", dim="#8a9970",
            ),
            "palette": {
                "Window": "#f0f5e6", "WindowText": "#2d3319",
                "Base": "#f7faf0", "AlternateBase": "#eaf2dc",
                "Text": "#2d3319", "Button": "#e4edcf",
                "ButtonText": "#2d3319", "Highlight": "#5a8c32",
                "HighlightedText": "#ffffff",
            },
        },
        "warm": {
            "label": "🌅 暖黄",
            "icon": "🌅",
            "qss": _make_qss(
                bg="#faf5ee", fg="#3d2b1f", input_bg="#fff9f2",
                border="#d4b896", accent="#c67f4a", accent_fg="#ffffff",
                tab_bg="#f0e4d4", hover="#e8d5bf", alt_bg="#f5ece0",
                btn_bg="#f0e4d4", dim="#a08060",
            ),
            "palette": {
                "Window": "#faf5ee", "WindowText": "#3d2b1f",
                "Base": "#fff9f2", "AlternateBase": "#f5ece0",
                "Text": "#3d2b1f", "Button": "#f0e4d4",
                "ButtonText": "#3d2b1f", "Highlight": "#c67f4a",
                "HighlightedText": "#ffffff",
            },
        },
        "pangu": {
            "label": "⚡ 盘古黑金",
            "icon": "⚡",
            "qss": _make_qss(
                bg="#0a0a14", fg="#d4a843", input_bg="#0d0d1a",
                border="#2a2520", accent="#b8860b", accent_fg="#0a0a14",
                tab_bg="#12121f", hover="#1e1e30", alt_bg="#0f0f1c",
                btn_bg="#161625", dim="#6b5d3a",
            ) + """
    /* ── 盘古黑金特效 ── */
    QTabBar::tab:selected {
        background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #b8860b, stop:1 #8b6508);
        color: #0a0a14;
        font-weight: bold;
    }
    QPushButton {
        border: 1px solid #3d3520;
    }
    QPushButton:hover {
        border-color: #d4a843;
        color: #ffd700;
    }
    QGroupBox {
        border: 1px solid #2a2520;
    }
    QGroupBox::title {
        color: #d4a843;
    }
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
        background-color: #3d3520;
    }
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
        background-color: #d4a843;
    }
    QHeaderView::section {
        background-color: #161625;
        color: #d4a843;
        border: 1px solid #2a2520;
    }
    QProgressBar::chunk {
        background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #b8860b, stop:1 #ffd700);
    }
    """,
            "palette": {
                "Window": "#0a0a14", "WindowText": "#d4a843",
                "Base": "#0d0d1a", "AlternateBase": "#0f0f1c",
                "Text": "#d4a843", "Button": "#161625",
                "ButtonText": "#d4a843", "Highlight": "#b8860b",
                "HighlightedText": "#0a0a14",
            },
        },
    }

    # 保持向后兼容
    LIGHT_QSS = ""
    DARK_QSS = THEMES["dark"]["qss"]

    @classmethod
    def apply(cls, app, name="light"):
        """应用主题"""
        from PyQt5.QtGui import QPalette, QColor
        theme = cls.THEMES.get(name, cls.THEMES["light"])

        palette_data = theme.get("palette")
        if palette_data:
            palette = QPalette()
            _map = {
                "Window": QPalette.Window, "WindowText": QPalette.WindowText,
                "Base": QPalette.Base, "AlternateBase": QPalette.AlternateBase,
                "Text": QPalette.Text, "Button": QPalette.Button,
                "ButtonText": QPalette.ButtonText,
                "Highlight": QPalette.Highlight,
                "HighlightedText": QPalette.HighlightedText,
            }
            for key, role in _map.items():
                if key in palette_data:
                    palette.setColor(role, QColor(palette_data[key]))
            app.setPalette(palette)
        else:
            from PyQt5.QtWidgets import QStyle
            app.setPalette(app.style().standardPalette())

        qss = theme.get("qss", "")
        app.setStyleSheet(qss)

        try:
            QSettings("NovelAI", "UI").setValue("theme", name)
        except Exception:
            pass

    @classmethod
    def current(cls):
        try:
            return QSettings("NovelAI", "UI").value("theme", "light", type=str)
        except Exception:
            return "light"

    @classmethod
    def toggle(cls, app):
        """切换到下一个主题"""
        themes = list(cls.THEMES.keys())
        cur = cls.current()
        idx = themes.index(cur) if cur in themes else 0
        new = themes[(idx + 1) % len(themes)]
        cls.apply(app, new)
        return new
