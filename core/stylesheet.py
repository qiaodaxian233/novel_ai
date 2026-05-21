# -*- coding: utf-8 -*-
"""
core/stylesheet.py - 应用 QSS 全局样式表

v2.00 P1 拆分:从 novel_ai.py 第 832-877 行整体搬运,内容零修改。
被 novel_ai.py 顶部 `from core.stylesheet import STYLESHEET` 导入。
"""

STYLESHEET = """
QMainWindow, QWidget { background-color: #f0f0f0; color: #222;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif; font-size: 13px; }
QPushButton { background-color: #1a4480; color: white; border: none;
    padding: 7px 14px; border-radius: 3px; font-weight: bold; }
QPushButton:hover { background-color: #2563b3; }
QPushButton:pressed { background-color: #0f3060; }
QPushButton:disabled { background-color: #888; color: #ddd; }
QLineEdit, QPlainTextEdit, QSpinBox {
    background-color: white; border: 1px solid #aaa;
    padding: 4px; border-radius: 3px; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #1a4480; }
QTabWidget::pane { border: 1px solid #1a4480; background-color: white; }
QTabBar::tab { background: #d8d8d8; color: #333; padding: 8px 24px;
    border: 1px solid #aaa; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
QTabBar::tab:selected { background: white; color: #1a4480; font-weight: bold;
    border-bottom: 2px solid #1a4480; }
QTabBar::tab:hover { background: #e8e8e8; }
QListWidget { background-color: white; border: 1px solid #aaa; border-radius: 3px; }
QListWidget::item { padding: 6px; border-bottom: 1px solid #eee; }
QListWidget::item:selected { background-color: #1a4480; color: white; }
QGroupBox { border: 1px solid #1a4480; border-radius: 4px;
    margin-top: 14px; padding-top: 8px; font-weight: bold; color: #1a4480; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QRadioButton, QCheckBox { padding: 4px; }
QStatusBar { background-color: #1a4480; color: white; }
QScrollArea { border: none; background: transparent; }
QSlider::groove:horizontal {
    border: 1px solid #aaa; height: 8px; background: #e0e0e0;
    border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: #1a4480; border-radius: 4px;
}
QSlider::handle:horizontal {
    background: white; border: 2px solid #1a4480; width: 14px;
    margin: -4px 0; border-radius: 8px;
}
QComboBox {
    background: white; border: 1px solid #aaa; padding: 4px 8px; border-radius: 3px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #1a4480;
    selection-color: white; border: 1px solid #1a4480; }
"""
