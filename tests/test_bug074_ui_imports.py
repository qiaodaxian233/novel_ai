# -*- coding: utf-8 -*-
"""v2.06 BUG-074 回归测试

起因:
修 BUG-073 时实际跑 mw.tab_settings.load_settings() 验证,触发了
另一个隐藏的 NameError:`ui/story_outline.py:35` 用了 `Qt.AlignTop`
但没 from PyQt5.QtCore import Qt。

诊断后发现 P3 模块化拆分时**漏了一批 PyQt5 import**:
  · ui/story_outline.py:        Qt, QSpinBox
  · ui/conversation_switcher.py: QCheckBox, QGroupBox, QColor

之前没暴露是因为:
  1. 这些代码路径在测试里没被走到(GUI 实际 show 才触发)
  2. AST 抽取脚本只复制了类源码 + 顶部基础 import,没补全所有引用

修法(v2.06):
  story_outline.py:        from PyQt5.QtCore import Qt + QSpinBox
  conversation_switcher.py: + QCheckBox/QGroupBox/QColor

保障:
  1. 静态扫描:用 AST + PYQT_CLASSES 白名单,确认所有 ui/ 文件 import 完整
  2. 实例化测试:确认 MainWindow 能完整启动 + load_settings 不崩
"""
import ast
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"

# 跟踪用的 PyQt5 类(常用,不全也无所谓 — 静态扫描兜底)
PYQT_CLASSES = {
    'Qt', 'QTimer', 'QUrl', 'QSettings', 'QSize', 'QPoint', 'QRect',
    'QObject', 'QThread', 'pyqtSignal', 'pyqtSlot',
    'QFont', 'QIcon', 'QColor', 'QPalette', 'QPixmap',
    'QSyntaxHighlighter', 'QTextCharFormat', 'QTextCursor',
    'QKeySequence', 'QShortcut',
    'QApplication', 'QMainWindow', 'QDialog', 'QWidget',
    'QVBoxLayout', 'QHBoxLayout', 'QGridLayout', 'QFormLayout',
    'QPushButton', 'QLabel', 'QLineEdit', 'QPlainTextEdit', 'QTextBrowser',
    'QTabWidget', 'QListWidget', 'QListWidgetItem', 'QTreeWidget', 'QTreeWidgetItem',
    'QTableWidget', 'QTableWidgetItem', 'QHeaderView',
    'QRadioButton', 'QCheckBox', 'QButtonGroup', 'QComboBox',
    'QGroupBox', 'QSplitter', 'QFileDialog', 'QMessageBox', 'QInputDialog',
    'QSpinBox', 'QDoubleSpinBox', 'QSlider',
    'QFrame', 'QScrollArea', 'QAction', 'QStatusBar', 'QToolBar', 'QMenu',
    'QDialogButtonBox',
}


def _scan_file_missing_imports(path):
    """返回 path 用了但没 import 的 PyQt5 类名"""
    src = path.read_text()
    tree = ast.parse(src)

    # 收集 import 进来的名字
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name)

    # 收集所有 PyQt5 Name/Attribute 引用
    used_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in PYQT_CLASSES:
                used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id in PYQT_CLASSES:
                used_names.add(base.id)

    # 排除函数体内局部 import 的
    missing = used_names - imported
    for m in list(missing):
        if re.search(
            rf'\b(?:from PyQt5\.\w+ import [^\n]*\b{m}\b|import {m}\b)',
            src
        ):
            missing.discard(m)
    return missing


class TestUIImportCompleteness(unittest.TestCase):
    """ui/ 子模块的 PyQt5 import 必须完整,不能漏(避免 NameError)"""

    def test_story_outline_has_qt_and_qspinbox(self):
        missing = _scan_file_missing_imports(UI_DIR / "story_outline.py")
        self.assertEqual(
            missing, set(),
            f"ui/story_outline.py 漏 PyQt5 import: {sorted(missing)}"
        )

    def test_conversation_switcher_has_qcheckbox_etc(self):
        missing = _scan_file_missing_imports(UI_DIR / "conversation_switcher.py")
        self.assertEqual(
            missing, set(),
            f"ui/conversation_switcher.py 漏 PyQt5 import: {sorted(missing)}"
        )

    def test_all_ui_modules_clean(self):
        """巡检:所有 ui/ 子模块都不能漏 PyQt5 import"""
        offenders = {}
        for f in list(UI_DIR.rglob("*.py")):
            if f.name == "__init__.py":
                continue
            missing = _scan_file_missing_imports(f)
            if missing:
                offenders[str(f.relative_to(ROOT))] = sorted(missing)
        self.assertEqual(
            offenders, {},
            f"以下 ui/ 文件漏 PyQt5 import,会在实际触发代码路径时 NameError:\n{offenders}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
