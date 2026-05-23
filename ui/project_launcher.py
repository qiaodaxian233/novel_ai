# -*- coding: utf-8 -*-
"""ui/project_launcher.py - 项目启动器

闪屏后第一个界面:选择/新建项目,选完进入主编辑器。
v2.18.3 新增。
"""
import os
import json
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog,
    QMessageBox, QGroupBox,
)
from PyQt5.QtGui import QFont, QColor, QIcon


class ProjectLauncher(QDialog):
    """项目启动器 — 闪屏后弹出,选完项目再进主窗口"""

    def __init__(self, project_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("盘古写作引擎 — 选择项目")
        self.resize(600, 500)
        self.setWindowFlags(
            Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        self.project_dir = Path(project_dir)
        self.selected_path = None  # 最终选中的项目路径

        # 尝试设置图标
        _icon = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "assets", "icon.ico")
        if os.path.exists(_icon):
            self.setWindowIcon(QIcon(_icon))

        layout = QVBoxLayout(self)

        # 标题
        title = QLabel("⚡ 盘古写作引擎")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#d4a843; padding:10px;")
        layout.addWidget(title)

        subtitle = QLabel("选择一个项目开始创作")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#888; font-size:12px; padding-bottom:10px;")
        layout.addWidget(subtitle)

        # 项目列表
        box = QGroupBox("最近项目")
        box_lay = QVBoxLayout(box)
        self.project_list = QListWidget()
        self.project_list.setStyleSheet(
            "QListWidget::item { padding:8px; border-bottom:1px solid #eee; }"
            "QListWidget::item:selected { background:#1a73e8; color:white; }"
            "QListWidget::item:hover { background:#e8f0fe; }")
        self.project_list.itemDoubleClicked.connect(self._on_open)
        box_lay.addWidget(self.project_list)
        layout.addWidget(box, 1)

        # 按钮区
        btn_row = QHBoxLayout()

        btn_new = QPushButton("📁 新建项目")
        btn_new.setStyleSheet(
            "QPushButton { background:#27ae60; color:white; padding:10px 20px;"
            "font-size:13px; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#219a52; }")
        btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(btn_new)

        btn_open = QPushButton("📂 打开项目")
        btn_open.setStyleSheet(
            "QPushButton { background:#1a73e8; color:white; padding:10px 20px;"
            "font-size:13px; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#1557b0; }")
        btn_open.clicked.connect(self._on_browse)
        btn_row.addWidget(btn_open)

        btn_last = QPushButton("⏩ 继续上次")
        btn_last.setToolTip("直接打开上次使用的项目")
        btn_last.setStyleSheet(
            "QPushButton { background:#e67e22; color:white; padding:10px 20px;"
            "font-size:13px; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#d35400; }")
        btn_last.clicked.connect(self._on_continue_last)
        btn_row.addWidget(btn_last)

        layout.addLayout(btn_row)

        # 加载项目列表
        self._load_projects()

    def _load_projects(self):
        """加载最近项目 + 扫描项目目录"""
        self.project_list.clear()
        seen = set()

        # 1. 从 QSettings 读最近项目
        s = QSettings("NovelAI", "UI")
        recent = s.value("recent_projects", [], type=list) or []
        last = s.value("last_project_path", "", type=str)

        for path in recent:
            p = Path(path)
            if p.exists() and p.is_dir() and str(p) not in seen:
                self._add_project_item(p, is_last=(str(p) == last))
                seen.add(str(p))

        # 2. 扫描项目目录下的文件夹
        if self.project_dir.exists():
            for d in sorted(self.project_dir.iterdir()):
                if d.is_dir() and not d.name.startswith(".") and str(d) not in seen:
                    # 检查是否是有效项目(有 chapters/ 或 meta.json)
                    if (d / "chapters").exists() or (d / "meta.json").exists():
                        self._add_project_item(d)
                        seen.add(str(d))

        if self.project_list.count() == 0:
            item = QListWidgetItem("  (没有找到项目,点下方按钮新建或打开)")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(QColor("#999"))
            self.project_list.addItem(item)

    def _add_project_item(self, path, is_last=False):
        """添加一个项目到列表"""
        name = path.name
        # 统计章节数和字数
        ch_count = 0
        word_count = 0
        ch_dir = path / "chapters"
        if ch_dir.exists():
            for f in ch_dir.glob("*.txt"):
                ch_count += 1
                try:
                    word_count += len(f.read_text(encoding="utf-8").replace(" ", "").replace("\n", ""))
                except Exception:
                    pass

        # 最后修改时间
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            time_str = mtime.strftime("%m-%d %H:%M")
        except Exception:
            time_str = ""

        # 显示文本
        prefix = "⏩ " if is_last else "  "
        label = f"{prefix}{name}"
        if ch_count > 0:
            label += f"  —  {ch_count}章 · {word_count:,}字"
        if time_str:
            label += f"  ({time_str})"

        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, str(path))
        if is_last:
            item.setForeground(QColor("#e67e22"))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self.project_list.addItem(item)

    def _on_open(self, item=None):
        """打开选中的项目"""
        if item is None:
            item = self.project_list.currentItem()
        if item is None:
            return
        path = item.data(Qt.UserRole)
        if path and Path(path).exists():
            self.selected_path = path
            self.accept()

    def _on_browse(self):
        """浏览文件夹选择项目"""
        path = QFileDialog.getExistingDirectory(
            self, "选择项目文件夹", str(self.project_dir))
        if path:
            self.selected_path = path
            self.accept()

    def _on_new(self):
        """新建项目"""
        import re
        title, ok = QInputDialog.getText(
            self, "新建项目", "给小说取个名字:", text="我的新小说")
        if not ok or not title.strip():
            return
        safe = re.sub(r'[\\/:*?"<>|]', '_', title.strip())
        proj = self.project_dir / safe
        proj.mkdir(parents=True, exist_ok=True)
        self.selected_path = str(proj)
        self.accept()

    def _on_continue_last(self):
        """继续上次的项目"""
        s = QSettings("NovelAI", "UI")
        last = s.value("last_project_path", "", type=str)
        if last and Path(last).exists():
            self.selected_path = last
            self.accept()
        else:
            QMessageBox.information(self, "提示", "没有找到上次的项目")
