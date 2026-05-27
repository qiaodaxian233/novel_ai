# -*- coding: utf-8 -*-
"""
core/stylesheet.py - 应用 QSS 全局样式表

v2.23.6 重写: 深色高端风格
设计语言: 深海蓝底 + 紫蓝渐变强调色 + 大圆角 + 卡片层次
"""

_C = {
    # 背景层次
    "bg_base":      "#0a0e1a",   # 最底层背景
    "bg_panel":     "#0f1628",   # 面板/侧栏
    "bg_card":      "#141d35",   # 卡片背景
    "bg_card2":     "#1a2540",   # 次级卡片
    "bg_hover":     "#1e2d50",   # 悬停
    "bg_selected":  "#1e3a6e",   # 选中
    "bg_input":     "#111827",   # 输入框

    # 强调色
    "primary":      "#5b8dee",   # 主蓝
    "primary_dark": "#3d6fd4",   # 深蓝(按下)
    "primary_glow": "#4a7de0",   # 光晕蓝
    "accent":       "#7c5cbf",   # 紫色强调
    "accent2":      "#6366f1",   # 靛蓝

    # 文字
    "text":         "#e8ecf4",   # 主文字(亮白蓝)
    "text_sec":     "#8fa3c4",   # 次要文字
    "text_hint":    "#4d6080",   # 提示/占位

    # 边框
    "border":       "#1e2d50",   # 默认边框
    "border_light": "#253352",   # 浅边框
    "border_focus": "#5b8dee",   # 聚焦边框

    # 语义色
    "danger":       "#f04c5a",
    "success":      "#30d988",
    "warn":         "#f5a623",
    "info":         "#5b8dee",
}


def _c(k):
    return _C.get(k, "#fff")


STYLESHEET = f"""

/* ══════════════════════════════════════
   全局基础
══════════════════════════════════════ */
QMainWindow, QDialog, QWidget {{
    background-color: {_c('bg_base')};
    color: {_c('text')};
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}}

/* ══════════════════════════════════════
   左侧导航栏
══════════════════════════════════════ */
QFrame#nav_sidebar {{
    background-color: {_c('bg_panel')};
    border-right: 1px solid {_c('border')};
}}

/* 主操作按钮(新建项目) */
QPushButton#nav_primary_btn {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {_c('primary')}, stop:1 {_c('accent2')});
    color: white;
    border: none;
    padding: 10px 16px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 13px;
}}
QPushButton#nav_primary_btn:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {_c('primary_dark')}, stop:1 #4f55d4);
}}
QPushButton#nav_primary_btn:pressed {{
    background: {_c('primary_dark')};
}}

/* 侧栏普通按钮 */
QPushButton#nav_side_btn {{
    background: transparent;
    color: {_c('text_sec')};
    border: none;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 12px;
    text-align: left;
}}
QPushButton#nav_side_btn:hover {{
    background: {_c('bg_hover')};
    color: {_c('text')};
}}

/* 创作流程步骤按钮 */
QPushButton#nav_step_btn {{
    background: transparent;
    color: {_c('text_sec')};
    border: none;
    border-left: 2px solid transparent;
    padding: 7px 12px;
    border-radius: 0px 8px 8px 0px;
    font-size: 12px;
    text-align: left;
}}
QPushButton#nav_step_btn:hover {{
    background: {_c('bg_hover')};
    color: {_c('primary')};
    border-left: 2px solid {_c('primary')};
}}

/* 危险按钮(删除) */
QPushButton#nav_danger_btn {{
    background: rgba(240,76,90,0.15);
    color: {_c('danger')};
    border: 1px solid rgba(240,76,90,0.3);
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 12px;
}}
QPushButton#nav_danger_btn:hover {{
    background: rgba(240,76,90,0.25);
}}

/* ══════════════════════════════════════
   通用按钮
══════════════════════════════════════ */
QPushButton {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {_c('primary')}, stop:1 {_c('primary_dark')});
    color: white;
    border: none;
    padding: 8px 18px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 12px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #6fa0f5, stop:1 {_c('primary')});
}}
QPushButton:pressed {{
    background: {_c('primary_dark')};
    padding-top: 9px;
    padding-bottom: 7px;
}}
QPushButton:disabled {{
    background: {_c('bg_card2')};
    color: {_c('text_hint')};
}}
QPushButton:flat {{
    background: transparent;
    color: {_c('primary')};
    border: none;
    font-weight: normal;
}}
QPushButton:flat:hover {{
    color: #7fb5ff;
    text-decoration: underline;
}}

/* ══════════════════════════════════════
   输入框
══════════════════════════════════════ */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {_c('bg_input')};
    border: 1px solid {_c('border_light')};
    padding: 7px 10px;
    border-radius: 8px;
    color: {_c('text')};
    selection-background-color: {_c('bg_selected')};
    selection-color: white;
}}
QLineEdit:focus, QSpinBox:focus {{
    border: 1.5px solid {_c('border_focus')};
    background: #141d35;
}}
QLineEdit:disabled {{
    background: {_c('bg_panel')};
    color: {_c('text_hint')};
}}

QPlainTextEdit, QTextEdit {{
    background-color: {_c('bg_input')};
    border: 1px solid {_c('border_light')};
    padding: 8px;
    border-radius: 10px;
    color: {_c('text')};
    selection-background-color: {_c('bg_selected')};
}}
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1.5px solid {_c('border_focus')};
}}

/* ══════════════════════════════════════
   Tab 栏
══════════════════════════════════════ */
QTabWidget::pane {{
    border: none;
    background: {_c('bg_base')};
}}
QTabWidget::tab-bar {{
    alignment: left;
}}
QTabBar {{
    background: {_c('bg_panel')};
}}
QTabBar::tab {{
    background: transparent;
    color: {_c('text_sec')};
    padding: 10px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-size: 12px;
    border-radius: 0;
}}
QTabBar::tab:selected {{
    color: {_c('primary')};
    font-weight: bold;
    border-bottom: 2px solid {_c('primary')};
    background: rgba(91,141,238,0.08);
}}
QTabBar::tab:hover:!selected {{
    color: {_c('text')};
    background: {_c('bg_hover')};
}}

/* ══════════════════════════════════════
   列表
══════════════════════════════════════ */
QListWidget {{
    background-color: {_c('bg_card')};
    border: 1px solid {_c('border')};
    border-radius: 10px;
    outline: none;
    padding: 4px;
}}
QListWidget::item {{
    padding: 7px 10px;
    border-radius: 6px;
    color: {_c('text_sec')};
    margin: 1px 0;
}}
QListWidget::item:selected {{
    background-color: {_c('bg_selected')};
    color: {_c('text')};
}}
QListWidget::item:hover:!selected {{
    background-color: {_c('bg_hover')};
    color: {_c('text')};
}}

/* ══════════════════════════════════════
   分组框 (卡片)
══════════════════════════════════════ */
QGroupBox {{
    border: 1px solid {_c('border_light')};
    border-radius: 12px;
    margin-top: 18px;
    padding-top: 14px;
    font-weight: bold;
    color: {_c('text')};
    background: {_c('bg_card')};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {_c('primary')};
    font-size: 12px;
}}

/* ══════════════════════════════════════
   下拉框
══════════════════════════════════════ */
QComboBox {{
    background: {_c('bg_input')};
    border: 1px solid {_c('border_light')};
    padding: 7px 12px;
    border-radius: 8px;
    color: {_c('text')};
    min-width: 80px;
}}
QComboBox:hover {{
    border-color: {_c('border_focus')};
}}
QComboBox:focus {{
    border: 1.5px solid {_c('border_focus')};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {_c('bg_card2')};
    selection-background-color: {_c('bg_selected')};
    selection-color: {_c('text')};
    border: 1px solid {_c('border_light')};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}

/* ══════════════════════════════════════
   表格
══════════════════════════════════════ */
QTableWidget {{
    background: {_c('bg_card')};
    border: 1px solid {_c('border')};
    border-radius: 10px;
    gridline-color: {_c('border')};
    selection-background-color: {_c('bg_selected')};
    outline: none;
}}
QTableWidget::item {{
    padding: 6px 10px;
    color: {_c('text')};
    border: none;
}}
QTableWidget::item:selected {{
    background: {_c('bg_selected')};
    color: white;
}}
QHeaderView::section {{
    background: {_c('bg_card2')};
    color: {_c('text_sec')};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {_c('border_light')};
    border-right: 1px solid {_c('border')};
    font-weight: bold;
    font-size: 12px;
}}
QHeaderView::section:first {{
    border-radius: 10px 0 0 0;
}}

/* ══════════════════════════════════════
   单选/复选
══════════════════════════════════════ */
QCheckBox, QRadioButton {{
    color: {_c('text_sec')};
    padding: 4px;
    spacing: 8px;
}}
QCheckBox:hover, QRadioButton:hover {{
    color: {_c('text')};
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1.5px solid {_c('border_light')};
    border-radius: 4px;
    background: {_c('bg_input')};
}}
QCheckBox::indicator:checked {{
    background: {_c('primary')};
    border-color: {_c('primary')};
}}
QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1.5px solid {_c('border_light')};
    border-radius: 8px;
    background: {_c('bg_input')};
}}
QRadioButton::indicator:checked {{
    background: {_c('primary')};
    border: 2px solid {_c('primary')};
}}

/* ══════════════════════════════════════
   状态栏
══════════════════════════════════════ */
QStatusBar {{
    background: {_c('bg_panel')};
    color: {_c('text_sec')};
    border-top: 1px solid {_c('border')};
    padding: 3px 10px;
    font-size: 11px;
}}
QStatusBar::item {{
    border: none;
}}

/* ══════════════════════════════════════
   工具栏
══════════════════════════════════════ */
QToolBar {{
    background: {_c('bg_panel')};
    border-bottom: 1px solid {_c('border')};
    padding: 4px 8px;
    spacing: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: none;
    padding: 6px 12px;
    border-radius: 8px;
    color: {_c('text_sec')};
    font-size: 12px;
}}
QToolBar QToolButton:hover {{
    background: {_c('bg_hover')};
    color: {_c('primary')};
}}
QToolBar QToolButton:pressed {{
    background: {_c('bg_selected')};
}}

/* ══════════════════════════════════════
   菜单栏 & 菜单
══════════════════════════════════════ */
QMenuBar {{
    background: {_c('bg_panel')};
    border-bottom: 1px solid {_c('border')};
    padding: 2px 4px;
    color: {_c('text_sec')};
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 14px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background: {_c('bg_hover')};
    color: {_c('text')};
}}
QMenu {{
    background: {_c('bg_card2')};
    border: 1px solid {_c('border_light')};
    border-radius: 10px;
    padding: 6px;
    color: {_c('text')};
}}
QMenu::item {{
    padding: 8px 28px 8px 16px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {_c('bg_selected')};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {_c('border')};
    margin: 4px 10px;
}}

/* ══════════════════════════════════════
   滚动条
══════════════════════════════════════ */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {_c('border_light')};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_c('text_hint')};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {_c('border_light')};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_c('text_hint')};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ══════════════════════════════════════
   滑块
══════════════════════════════════════ */
QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background: {_c('bg_card2')};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {_c('primary')};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: white;
    border: 2px solid {_c('primary')};
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

/* ══════════════════════════════════════
   进度条
══════════════════════════════════════ */
QProgressBar {{
    border: none;
    background: {_c('bg_card2')};
    border-radius: 5px;
    height: 6px;
    text-align: center;
    font-size: 10px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {_c('primary')}, stop:1 {_c('accent2')});
    border-radius: 5px;
}}

/* ══════════════════════════════════════
   分割线
══════════════════════════════════════ */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {_c('border')};
    background: {_c('border')};
    border: none;
    max-height: 1px;
}}

/* ══════════════════════════════════════
   分割器手柄
══════════════════════════════════════ */
QSplitter::handle {{
    background: {_c('border')};
    width: 1px;
    height: 1px;
}}

/* ══════════════════════════════════════
   Tooltip
══════════════════════════════════════ */
QToolTip {{
    background: {_c('bg_card2')};
    color: {_c('text')};
    border: 1px solid {_c('border_light')};
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 12px;
}}

/* ══════════════════════════════════════
   消息框
══════════════════════════════════════ */
QMessageBox {{
    background: {_c('bg_card')};
}}
QMessageBox QLabel {{
    color: {_c('text')};
}}

/* ══════════════════════════════════════
   数字输入框箭头
══════════════════════════════════════ */
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 16px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {_c('bg_hover')};
    border-radius: 4px;
}}
"""
