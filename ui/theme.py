# -*- coding: utf-8 -*-
"""ui/theme.py - 多主题管理器

v2.23.4 重写:所有主题统一使用现代扁平设计语言(圆角/阴影/clean tabs)。
支持: 浅色 / 暗黑 / 护眼绿 / 暖黄 / 盘古黑金
"""
from PyQt5.QtCore import QSettings


def _build_modern_qss(
    bg, bg_white, bg_hover, bg_selected,
    primary, primary_dark, primary_light,
    text, text_sec, text_hint,
    border, border_focus,
    tab_bg, statusbar_bg,
    btn_bg=None, btn_fg="white",
    extra_qss="",
):
    """生成统一的现代扁平 QSS(所有主题共用同一模板,只换颜色)"""
    if btn_bg is None:
        btn_bg = primary
    return f"""
/* ── 全局 ── */
QMainWindow, QWidget, QDialog {{
    background-color: {bg};
    color: {text};
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QFrame {{ color: {text}; }}
QLabel {{ color: {text}; background: transparent; }}

/* ── 按钮 ── */
QPushButton {{
    background-color: {btn_bg}; color: {btn_fg};
    border: none; padding: 9px 18px;
    border-radius: 10px; font-weight: bold; font-size: 12px;
}}
QPushButton:hover {{ background-color: {primary_dark}; }}
QPushButton:pressed {{ background-color: {primary}; padding-top: 10px; padding-bottom: 8px; }}
QPushButton:disabled {{ background-color: {border}; color: {text_hint}; }}

/* ── 输入框 ── */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {bg_white}; border: 1px solid {border};
    padding: 6px 8px; border-radius: 6px; color: {text};
    selection-background-color: {bg_selected};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1.5px solid {border_focus};
}}

/* ── Tab 栏 ── */
QTabWidget::pane {{
    border: 1px solid {border}; background-color: {bg_white};
    border-radius: 0 0 8px 8px; top: -1px;
}}
QTabBar {{ background: {tab_bg}; }}
QTabBar::tab {{
    background: transparent; color: {text_sec};
    padding: 10px 20px; border: none;
    border-bottom: 2px solid transparent; margin-right: 2px; font-size: 12px;
}}
QTabBar::tab:selected {{
    color: {primary}; font-weight: bold;
    border-bottom: 2px solid {primary}; background: {bg_white};
}}
QTabBar::tab:hover {{ color: {primary}; background: {bg_hover}; }}

/* ── 列表/表格 ── */
QListWidget, QTableWidget, QTreeWidget {{
    background-color: {bg_white}; border: 1px solid {border};
    border-radius: 6px; outline: none; color: {text};
    gridline-color: {bg_hover}; alternate-background-color: {bg_hover};
    selection-background-color: {bg_selected}; selection-color: {primary};
}}
QListWidget::item {{ padding: 8px 10px; border-bottom: 1px solid {bg_hover}; }}
QListWidget::item:selected {{ background-color: {bg_selected}; color: {primary}; }}
QListWidget::item:hover {{ background-color: {bg_hover}; }}
QHeaderView::section {{
    background: {tab_bg}; color: {text}; padding: 8px; border: none;
    border-bottom: 1px solid {border}; font-weight: bold; font-size: 12px;
}}

/* ── 分组框 ── */
QGroupBox {{
    border: 1px solid {border}; border-radius: 8px;
    margin-top: 16px; padding-top: 12px;
    font-weight: bold; color: {text}; background: {bg_white};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 8px; color: {primary};
}}

/* ── 单选/复选 ── */
QRadioButton, QCheckBox {{ color: {text}; padding: 4px; spacing: 6px; }}

/* ── 状态栏 ── */
QStatusBar {{
    background-color: {statusbar_bg}; color: {text_sec};
    border-top: 1px solid {border}; padding: 2px 8px; font-size: 11px;
}}

/* ── 滚动条 ── */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{
    background: {border}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {text_hint}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{
    background: {border}; border-radius: 4px; min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── 下拉框 ── */
QComboBox {{
    background: {bg_white}; border: 1px solid {border};
    padding: 6px 10px; border-radius: 6px; color: {text};
}}
QComboBox:hover {{ border-color: {border_focus}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {bg_white}; selection-background-color: {bg_selected};
    selection-color: {primary}; border: 1px solid {border}; padding: 4px;
}}

/* ── 滑块 ── */
QSlider::groove:horizontal {{
    border: none; height: 6px; background: {border}; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{ background: {primary}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {bg_white}; border: 2px solid {primary};
    width: 16px; margin: -5px 0; border-radius: 8px;
}}

/* ── 工具栏/菜单 ── */
QToolBar {{
    background: {bg_white}; border-bottom: 1px solid {border}; padding: 4px 8px;
}}
QToolBar QToolButton {{
    background: transparent; border: none; padding: 6px 10px;
    border-radius: 4px; color: {text_sec}; font-size: 12px;
}}
QToolBar QToolButton:hover {{ background: {bg_hover}; color: {primary}; }}
QMenuBar {{ background: {bg_white}; border-bottom: 1px solid {border}; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {bg_hover}; color: {primary}; }}
QMenu {{
    background: {bg_white}; border: 1px solid {border};
    border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 8px 24px; border-radius: 4px; color: {text}; }}
QMenu::item:selected {{ background: {bg_selected}; color: {primary}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}

/* ── 进度条 ── */
QProgressBar {{
    border: none; background: {border}; border-radius: 4px;
    height: 8px; text-align: center; font-size: 10px;
}}
QProgressBar::chunk {{ background: {primary}; border-radius: 4px; }}

/* ── Tooltip ── */
QToolTip {{
    background: {text}; color: {bg_white};
    border: none; padding: 6px 10px; border-radius: 4px; font-size: 12px;
}}

/* ── Splitter ── */
QSplitter::handle {{ background-color: {border}; }}

/* ── 左侧导航栏(跟随主题) ── */
QFrame#nav_sidebar {{
    background-color: {bg_white};
    border-right: 1px solid {border};
}}
QPushButton#nav_primary_btn {{
    background: {primary}; color: {btn_fg};
    padding: 10px 14px; font-size: 12px; font-weight: bold;
    border-radius: 10px; text-align: left;
}}
QPushButton#nav_primary_btn:hover {{ background: {primary_dark}; }}
QPushButton#nav_side_btn {{
    background: transparent; color: {text_sec};
    padding: 8px 12px; font-size: 12px; border-radius: 8px; text-align: left;
}}
QPushButton#nav_side_btn:hover {{ background: {bg_hover}; color: {primary}; }}
QPushButton#nav_step_btn {{
    background: transparent; color: {text_sec};
    padding: 7px 12px; font-size: 12px;
    border-radius: 0px 8px 8px 0px;
    border-left: 2px solid transparent; text-align: left;
}}
QPushButton#nav_step_btn:hover {{
    background: {bg_hover}; color: {primary};
    border-left: 2px solid {primary};
}}
QPushButton#nav_danger_btn {{
    background: rgba(231,76,60,0.18); color: #e74c3c;
    border: 1px solid rgba(231,76,60,0.35);
    padding: 4px 8px; font-size: 12px; border-radius: 8px;
}}
QPushButton#nav_danger_btn:hover {{ background: rgba(231,76,60,0.28); }}

{extra_qss}
"""


class ThemeManager:
    """多主题管理器"""

    THEMES = {
        "light": {
            "label": "☀️ 浅色",
            "icon": "☀️",
            "qss_args": dict(
                bg="#f5f7fa", bg_white="#ffffff", bg_hover="#f0f4ff",
                bg_selected="#e8f0fe", primary="#4a9eff",
                primary_dark="#3584e4", primary_light="#eef5ff",
                text="#1a1a2e", text_sec="#555555", text_hint="#999999",
                border="#e0e6ed", border_focus="#4a9eff",
                tab_bg="#f8f9fc", statusbar_bg="#ffffff",
            ),
        },
        "dark": {
            "label": "🌙 深海暗黑",
            "icon": "🌙",
            "qss_args": dict(
                bg="#0a0e1a", bg_white="#141d35", bg_hover="#1e2d50",
                bg_selected="#1e3a6e", primary="#5b8dee",
                primary_dark="#3d6fd4", primary_light="#0f1628",
                text="#e8ecf4", text_sec="#8fa3c4", text_hint="#4d6080",
                border="#1e2d50", border_focus="#5b8dee",
                tab_bg="#0f1628", statusbar_bg="#0a0e1a",
                btn_bg="#5b8dee",
            ),
            "palette": {
                "Window": "#0a0e1a", "WindowText": "#e8ecf4",
                "Base": "#141d35", "AlternateBase": "#1a2540",
                "Text": "#e8ecf4", "Button": "#5b8dee",
                "ButtonText": "#ffffff", "Highlight": "#5b8dee",
                "HighlightedText": "#ffffff",
            },
        },
        "green": {
            "label": "🌿 护眼绿",
            "icon": "🌿",
            "qss_args": dict(
                bg="#f0f5e6", bg_white="#f7faf0", bg_hover="#e8f0d8",
                bg_selected="#d4e8b8", primary="#5a8c32",
                primary_dark="#4a7828", primary_light="#e8f5d0",
                text="#2d3319", text_sec="#5a6640", text_hint="#8a9970",
                border="#c5d6a0", border_focus="#5a8c32",
                tab_bg="#e4edcf", statusbar_bg="#f0f5e6",
                btn_bg="#5a8c32",
            ),
            "palette": {
                "Window": "#f0f5e6", "WindowText": "#2d3319",
                "Base": "#f7faf0", "AlternateBase": "#eaf2dc",
                "Text": "#2d3319", "Button": "#5a8c32",
                "ButtonText": "#ffffff", "Highlight": "#5a8c32",
                "HighlightedText": "#ffffff",
            },
        },
        "warm": {
            "label": "🌅 暖黄",
            "icon": "🌅",
            "qss_args": dict(
                bg="#faf5ee", bg_white="#fff9f2", bg_hover="#f0e4d4",
                bg_selected="#e8d0b0", primary="#c67f4a",
                primary_dark="#b06835", primary_light="#faf0e4",
                text="#3d2b1f", text_sec="#7a5c40", text_hint="#a08060",
                border="#d4b896", border_focus="#c67f4a",
                tab_bg="#f0e4d4", statusbar_bg="#faf5ee",
                btn_bg="#c67f4a",
            ),
            "palette": {
                "Window": "#faf5ee", "WindowText": "#3d2b1f",
                "Base": "#fff9f2", "AlternateBase": "#f5ece0",
                "Text": "#3d2b1f", "Button": "#c67f4a",
                "ButtonText": "#ffffff", "Highlight": "#c67f4a",
                "HighlightedText": "#ffffff",
            },
        },
        "pangu": {
            "label": "⚡ 盘古黑金",
            "icon": "⚡",
            "qss_args": dict(
                bg="#0a0a14", bg_white="#12121f", bg_hover="#1e1e30",
                bg_selected="#2a2520", primary="#d4a843",
                primary_dark="#b8860b", primary_light="#1a1510",
                text="#d4a843", text_sec="#a08050", text_hint="#6b5d3a",
                border="#2a2520", border_focus="#d4a843",
                tab_bg="#12121f", statusbar_bg="#0a0a14",
                btn_bg="#1a1510", btn_fg="#d4a843",
                extra_qss="""
QTabBar::tab:selected {
    background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #d4a843, stop:1 #8b6508);
    color: #0a0a14; font-weight: bold;
    border-bottom: none;
}
QPushButton:hover { color: #ffd700; border: 1px solid #d4a843; }
QProgressBar::chunk {
    background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #b8860b, stop:1 #ffd700);
}
""",
            ),
            "palette": {
                "Window": "#0a0a14", "WindowText": "#d4a843",
                "Base": "#12121f", "AlternateBase": "#0f0f1c",
                "Text": "#d4a843", "Button": "#1a1510",
                "ButtonText": "#d4a843", "Highlight": "#b8860b",
                "HighlightedText": "#0a0a14",
            },
        },
    }

    @classmethod
    def apply(cls, app, name="light"):
        """应用主题"""
        from PyQt5.QtGui import QPalette, QColor
        theme = cls.THEMES.get(name, cls.THEMES["light"])

        # 调色板
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

        # QSS
        qss_args = theme.get("qss_args", {})
        if qss_args:
            qss = _build_modern_qss(**qss_args)
        else:
            qss = ""
        app.setStyleSheet(qss)

        try:
            QSettings("NovelAI", "UI").setValue("theme", name)
        except Exception:
            pass

    @classmethod
    def current(cls):
        try:
            return QSettings("NovelAI", "UI").value("theme", "dark", type=str)
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
