# -*- coding: utf-8 -*-
"""
core/stylesheet.py - 应用 QSS 全局样式表

v2.23.4 重写:从旧式灰蓝风格升级为现代白底蓝线扁平风格。
设计参考:盘古写作引擎 v2.23.4 目标 UI(白底 + 蓝色强调 + 圆角卡片)
"""

# ── 颜色变量(便于统一修改) ──
_C = {
    "bg":           "#f5f7fa",       # 全局背景(浅灰蓝)
    "bg_white":     "#ffffff",       # 卡片/面板背景
    "bg_hover":     "#f0f4ff",       # 悬停背景
    "bg_selected":  "#e8f0fe",       # 选中背景
    "primary":      "#4a9eff",       # 主色(蓝)
    "primary_dark": "#3584e4",       # 主色深(按下)
    "primary_light":"#eef5ff",       # 主色浅(Tab 选中底)
    "text":         "#1a1a2e",       # 主文字(深黑蓝)
    "text_sec":     "#555",          # 次要文字
    "text_hint":    "#999",          # 提示文字
    "border":       "#e0e6ed",       # 边框
    "border_focus": "#4a9eff",       # 聚焦边框
    "danger":       "#e74c3c",       # 危险/删除
    "success":      "#27ae60",       # 成功/保存
    "warn":         "#e67e22",       # 警告/橙
    "tab_bg":       "#f8f9fc",       # Tab 栏背景
    "statusbar":    "#ffffff",       # 状态栏背景
}


def _c(key):
    return _C.get(key, "#000")


STYLESHEET = f"""

/* ── 全局 ── */
QMainWindow, QWidget {{
    background-color: {_c('bg')};
    color: {_c('text')};
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}}

/* ── 按钮 ── */
QPushButton {{
    background-color: {_c('primary')};
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {_c('primary_dark')};
}}
QPushButton:pressed {{
    background-color: #2a6fc8;
}}
QPushButton:disabled {{
    background-color: #c0c8d4;
    color: #f0f0f0;
}}

/* ── 输入框 ── */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {{
    background-color: {_c('bg_white')};
    border: 1px solid {_c('border')};
    padding: 6px 8px;
    border-radius: 6px;
    color: {_c('text')};
    selection-background-color: {_c('bg_selected')};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1.5px solid {_c('border_focus')};
}}

/* ── Tab 栏(核心视觉改变) ── */
QTabWidget::pane {{
    border: 1px solid {_c('border')};
    background-color: {_c('bg_white')};
    border-radius: 0 0 8px 8px;
    top: -1px;
}}
QTabBar {{
    background: {_c('tab_bg')};
}}
QTabBar::tab {{
    background: transparent;
    color: {_c('text_sec')};
    padding: 10px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    color: {_c('primary')};
    font-weight: bold;
    border-bottom: 2px solid {_c('primary')};
    background: {_c('bg_white')};
}}
QTabBar::tab:hover {{
    color: {_c('primary')};
    background: {_c('bg_hover')};
}}

/* ── 列表 ── */
QListWidget {{
    background-color: {_c('bg_white')};
    border: 1px solid {_c('border')};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid #f0f2f5;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background-color: {_c('bg_selected')};
    color: {_c('primary')};
}}
QListWidget::item:hover {{
    background-color: {_c('bg_hover')};
}}

/* ── 分组框 ── */
QGroupBox {{
    border: 1px solid {_c('border')};
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 12px;
    font-weight: bold;
    color: {_c('text')};
    background: {_c('bg_white')};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: {_c('primary')};
}}

/* ── 单选/复选 ── */
QRadioButton, QCheckBox {{
    padding: 4px;
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
}}
QCheckBox::indicator:checked {{
    background: {_c('primary')};
    border: 1px solid {_c('primary')};
    border-radius: 3px;
}}
QRadioButton::indicator:checked {{
    background: {_c('primary')};
    border: 2px solid {_c('primary')};
    border-radius: 8px;
}}

/* ── 状态栏 ── */
QStatusBar {{
    background-color: {_c('statusbar')};
    color: {_c('text_sec')};
    border-top: 1px solid {_c('border')};
    padding: 2px 8px;
    font-size: 11px;
}}

/* ── 滚动区 ── */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c8cdd4;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #a0a8b4;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── 滑块 ── */
QSlider::groove:horizontal {{
    border: none;
    height: 6px;
    background: #e0e4ea;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {_c('primary')};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: white;
    border: 2px solid {_c('primary')};
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

/* ── 下拉框 ── */
QComboBox {{
    background: {_c('bg_white')};
    border: 1px solid {_c('border')};
    padding: 6px 10px;
    border-radius: 6px;
    color: {_c('text')};
}}
QComboBox:hover {{
    border-color: {_c('border_focus')};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {_c('bg_white')};
    selection-background-color: {_c('bg_selected')};
    selection-color: {_c('primary')};
    border: 1px solid {_c('border')};
    border-radius: 4px;
    padding: 4px;
}}

/* ── 表格 ── */
QTableWidget {{
    background: {_c('bg_white')};
    border: 1px solid {_c('border')};
    border-radius: 6px;
    gridline-color: #f0f2f5;
    selection-background-color: {_c('bg_selected')};
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QHeaderView::section {{
    background: {_c('tab_bg')};
    color: {_c('text')};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {_c('border')};
    font-weight: bold;
    font-size: 12px;
}}

/* ── 工具栏 ── */
QToolBar {{
    background: {_c('bg_white')};
    border-bottom: 1px solid {_c('border')};
    padding: 4px 8px;
    spacing: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: none;
    padding: 6px 10px;
    border-radius: 4px;
    color: {_c('text_sec')};
    font-size: 12px;
}}
QToolBar QToolButton:hover {{
    background: {_c('bg_hover')};
    color: {_c('primary')};
}}

/* ── 菜单栏 ── */
QMenuBar {{
    background: {_c('bg_white')};
    border-bottom: 1px solid {_c('border')};
    padding: 2px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {_c('bg_hover')};
    color: {_c('primary')};
}}
QMenu {{
    background: {_c('bg_white')};
    border: 1px solid {_c('border')};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {_c('bg_selected')};
    color: {_c('primary')};
}}
QMenu::separator {{
    height: 1px;
    background: {_c('border')};
    margin: 4px 8px;
}}

/* ── 进度条 ── */
QProgressBar {{
    border: none;
    background: #e0e4ea;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: {_c('primary')};
    border-radius: 4px;
}}

/* ── 消息框 ── */
QMessageBox {{
    background: {_c('bg_white')};
}}

/* ── Tooltip ── */
QToolTip {{
    background: {_c('text')};
    color: white;
    border: none;
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 12px;
}}
"""
