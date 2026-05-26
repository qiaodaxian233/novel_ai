# -*- coding: utf-8 -*-
"""ui/project_launcher.py - 项目启动器

v2.23.4 重写:从简陋对话框升级为双栏专业启动页。
左栏:新建/打开/继续 + 最近项目列表
右栏:产品介绍 + 核心功能亮点卡片
"""
import os
import json
import re
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import Qt, QSettings, QSize
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog,
    QMessageBox, QFrame, QGridLayout, QWidget, QScrollArea,
    QSizePolicy, QGraphicsDropShadowEffect,
)
from PyQt5.QtGui import QFont, QColor, QIcon, QPalette, QPixmap, QPainter


APP_VERSION = "v2.23.4"


class FeatureCard(QFrame):
    """单个功能亮点卡片"""
    def __init__(self, icon_text, title, desc, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            FeatureCard {
                background: white;
                border: 1px solid #e0e6ed;
                border-radius: 8px;
                padding: 16px;
            }
            FeatureCard:hover {
                border-color: #4a9eff;
                background: #f8fbff;
            }
        """)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # 图标 + 标题行
        top = QHBoxLayout()
        icon_lbl = QLabel(icon_text)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignCenter)
        top.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        title_lbl.setStyleSheet("color:#1a1a2e; border:none;")
        top.addWidget(title_lbl)
        top.addStretch()
        lay.addLayout(top)

        # 描述
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            "color:#666; font-size:11px; border:none; padding-top:4px;")
        lay.addWidget(desc_lbl)


class ProjectLauncher(QDialog):
    """项目启动器 — 双栏专业启动页"""

    def __init__(self, project_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("盘古写作引擎")
        self.resize(960, 640)
        self.setMinimumSize(800, 500)
        self.setWindowFlags(
            Qt.WindowCloseButtonHint | Qt.WindowTitleHint
            | Qt.WindowMinMaxButtonsHint)
        self.project_dir = Path(project_dir)
        self.selected_path = None

        # 图标
        _icon = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "assets", "icon.ico")
        if os.path.exists(_icon):
            self.setWindowIcon(QIcon(_icon))

        self.setStyleSheet("""
            QDialog { background: #f5f7fa; }
        """)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # ── 顶部标题栏 ──
        self._build_header(main_lay)

        # ── 中间主体(左栏 + 右栏) ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._build_left_panel(body)
        self._build_right_panel(body)

        main_lay.addLayout(body, 1)

        # ── 底部状态栏 ──
        self._build_footer(main_lay)

        # 加载数据
        self._load_projects()

    # ──────────── 顶部标题栏 ────────────

    def _build_header(self, parent_lay):
        header = QFrame()
        header.setFixedHeight(48)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f8f9ff, stop:1 #eef2ff);
                border-bottom: 1px solid #e0e4ef;
            }
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)

        # Logo + 名称 + 版本
        logo_lbl = QLabel("⚡")
        logo_lbl.setFont(QFont("Segoe UI Emoji", 16))
        h_lay.addWidget(logo_lbl)

        name_lbl = QLabel("盘古写作引擎")
        name_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        name_lbl.setStyleSheet("color:#1a1a2e;")
        h_lay.addWidget(name_lbl)

        ver_lbl = QLabel(f" {APP_VERSION} ")
        ver_lbl.setStyleSheet(
            "background:#4a9eff; color:white; border-radius:4px;"
            "padding:2px 8px; font-size:11px; font-weight:bold;")
        h_lay.addWidget(ver_lbl)

        h_lay.addStretch()

        # 右侧链接
        for text in ["⊕ 官网", "⚙ 设置", "ⓘ 关于"]:
            btn = QPushButton(text)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { color:#555; font-size:12px; padding:4px 8px;"
                "border:none; }"
                "QPushButton:hover { color:#1a73e8; }")
            if "关于" in text:
                btn.clicked.connect(self._on_about)
            h_lay.addWidget(btn)

        parent_lay.addWidget(header)

    # ──────────── 左栏:操作 + 项目列表 ────────────

    def _build_left_panel(self, parent_lay):
        panel = QFrame()
        panel.setFixedWidth(260)
        panel.setStyleSheet("""
            QFrame { background: white; border-right: 1px solid #e0e4ef; }
        """)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(8)

        # 操作按钮
        btn_new = QPushButton("📁  新建项目")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setStyleSheet("""
            QPushButton {
                background: #4a9eff; color: white;
                padding: 12px; font-size: 13px; font-weight: bold;
                border-radius: 6px; border: none;
                text-align: left;
            }
            QPushButton:hover { background: #3584e4; }
        """)
        btn_new.clicked.connect(self._on_new)
        lay.addWidget(btn_new)

        btn_open = self._make_side_btn("📂  打开项目")
        btn_open.clicked.connect(self._on_browse)
        lay.addWidget(btn_open)

        btn_last = self._make_side_btn("▶  继续上次")
        btn_last.clicked.connect(self._on_continue_last)
        lay.addWidget(btn_last)

        lay.addSpacing(12)

        # 最近项目
        recent_lbl = QLabel("🕐  最近项目")
        recent_lbl.setStyleSheet(
            "color:#555; font-size:12px; font-weight:bold; padding:4px 0;")
        lay.addWidget(recent_lbl)

        self.project_list = QListWidget()
        self.project_list.setStyleSheet("""
            QListWidget {
                border: none; background: transparent;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #f0f0f0;
                border-radius: 4px;
                color: #333;
            }
            QListWidget::item:selected {
                background: #eef5ff; color: #1a73e8;
            }
            QListWidget::item:hover {
                background: #f5f8ff;
            }
        """)
        self.project_list.itemDoubleClicked.connect(self._on_open)
        lay.addWidget(self.project_list, 1)

        # 底部
        btn_manage = self._make_side_btn("📋  项目管理")
        btn_manage.clicked.connect(self._on_browse)
        lay.addWidget(btn_manage)

        hint = QLabel("提示：双击项目可快速打开")
        hint.setStyleSheet("color:#aaa; font-size:10px; padding-top:4px;")
        lay.addWidget(hint)

        parent_lay.addWidget(panel)

    def _make_side_btn(self, text):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #333;
                padding: 10px; font-size: 13px;
                border-radius: 6px; border: none;
                text-align: left;
            }
            QPushButton:hover { background: #f0f4ff; color: #1a73e8; }
        """)
        return btn

    # ──────────── 右栏:产品介绍 + 功能卡片 ────────────

    def _build_right_panel(self, parent_lay):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #f5f7fa; }
            QScrollBar:vertical { width: 6px; }
        """)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 28, 32, 20)
        lay.setSpacing(20)

        # ── Hero 区 ──
        hero = QFrame()
        hero.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #eef3ff, stop:0.5 #f0f0ff, stop:1 #e8edff);
                border-radius: 12px;
                padding: 24px;
            }
        """)
        hero_lay = QVBoxLayout(hero)
        hero_lay.setSpacing(8)

        hero_icon = QLabel("⚡")
        hero_icon.setFont(QFont("Segoe UI Emoji", 28))
        hero_lay.addWidget(hero_icon)

        hero_title = QLabel("盘古写作引擎")
        hero_title.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        hero_title.setStyleSheet("color:#1a1a2e;")
        hero_lay.addWidget(hero_title)

        hero_sub = QLabel('选择一个项目<span style="color:#4a9eff;">开始创作</span>')
        hero_sub.setStyleSheet("color:#666; font-size:14px;")
        hero_lay.addWidget(hero_sub)

        lay.addWidget(hero)

        # ── 功能亮点标题 ──
        feat_title = QLabel("核心功能亮点")
        feat_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        feat_title.setStyleSheet("color:#1a1a2e;")
        lay.addWidget(feat_title)

        # ── 功能卡片 2×3 网格 ──
        grid = QGridLayout()
        grid.setSpacing(12)

        cards = [
            ("🌐", "AI 辅助创作",
             "集成 DeepSeek、豆包、通义千问等主流 AI 模型"),
            ("🛡️", "盘古世界观系统",
             "禁用词过滤 + 感官铁律 + 压爆震 + 黄金三章公式"),
            ("👥", "角色自动同步",
             "角色、关系、时间线、物品、战力等自动关联"),
            ("🔬", "30 项质检",
             "AI 自动修复 + 章节无信息面板快速检查"),
            ("💾", "自动保存",
             "每章 + 60 秒 + 章后立即保存，安全不丢稿"),
            ("🔧", "自定义工具链",
             "自定义题材 + 金手指 + 主角设定 + 折叠链"),
        ]

        for idx, (icon, title, desc) in enumerate(cards):
            card = FeatureCard(icon, title, desc)
            grid.addWidget(card, idx // 3, idx % 3)

        lay.addLayout(grid)

        # ── 底部产品信息卡 ──
        info = QFrame()
        info.setStyleSheet("""
            QFrame {
                background: #f0f4fa;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        info_lay = QHBoxLayout(info)

        info_text = QVBoxLayout()
        info_title_row = QHBoxLayout()
        info_name = QLabel("盘古超级写作助手")
        info_name.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        info_name.setStyleSheet("color:#1a1a2e;")
        info_title_row.addWidget(info_name)

        info_ver = QLabel(f" {APP_VERSION} ")
        info_ver.setStyleSheet(
            "background:#e0e8f0; color:#555; border-radius:4px;"
            "padding:2px 8px; font-size:11px;")
        info_title_row.addWidget(info_ver)
        info_title_row.addStretch()
        info_text.addLayout(info_title_row)

        info_stack = QLabel("技术栈：Python 3 + PyQt5 + Selenium")
        info_stack.setStyleSheet("color:#888; font-size:11px; padding:4px 0;")
        info_text.addWidget(info_stack)

        info_desc = QLabel(
            "集 AI 辅助、世界观管理、角色同步、自动保存、质检优化等强大功能于一体，"
            "助力您高效创作。通过科学的创作流程和丰富的辅助工具，让您的创作之旅更加顺畅。")
        info_desc.setWordWrap(True)
        info_desc.setStyleSheet("color:#555; font-size:12px; line-height:1.6;")
        info_text.addWidget(info_desc)

        info_lay.addLayout(info_text, 1)

        # Logo 图片(如果有)
        _logo = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "assets", "icon_64.png")
        if os.path.exists(_logo):
            logo_lbl = QLabel()
            pixmap = QPixmap(_logo).scaled(
                80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_lbl.setPixmap(pixmap)
            logo_lbl.setFixedSize(90, 90)
            logo_lbl.setAlignment(Qt.AlignCenter)
            info_lay.addWidget(logo_lbl)

        lay.addWidget(info)
        lay.addStretch()

        scroll.setWidget(content)
        parent_lay.addWidget(scroll, 1)

    # ──────────── 底部状态栏 ────────────

    def _build_footer(self, parent_lay):
        footer = QFrame()
        footer.setFixedHeight(32)
        footer.setStyleSheet("""
            QFrame {
                background: white;
                border-top: 1px solid #e0e4ef;
            }
        """)
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(16, 0, 16, 0)

        status = QLabel("✅ 系统状态：<b style='color:#27ae60;'>正常运行</b>")
        status.setStyleSheet("font-size:11px; color:#555;")
        f_lay.addWidget(status)
        f_lay.addStretch()

        update_time = QLabel(
            f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        update_time.setStyleSheet("font-size:11px; color:#999;")
        f_lay.addWidget(update_time)

        parent_lay.addWidget(footer)

    # ──────────── 数据加载 ────────────

    def _load_projects(self):
        self.project_list.clear()
        seen = set()

        s = QSettings("NovelAI", "UI")
        recent = s.value("recent_projects", [], type=list) or []
        last = s.value("last_project_path", "", type=str)

        for path in recent:
            p = Path(path)
            if p.exists() and p.is_dir() and str(p) not in seen:
                self._add_project_item(p, is_last=(str(p) == last))
                seen.add(str(p))

        if self.project_dir.exists():
            for d in sorted(self.project_dir.iterdir()):
                if d.is_dir() and not d.name.startswith(".") and str(d) not in seen:
                    if (d / "chapters").exists() or (d / "meta.json").exists() or \
                       (d / "project.json").exists():
                        self._add_project_item(d)
                        seen.add(str(d))

        if self.project_list.count() == 0:
            item = QListWidgetItem("  暂无项目")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(QColor("#999"))
            self.project_list.addItem(item)

    def _add_project_item(self, path, is_last=False):
        name = path.name
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            time_str = mtime.strftime("%m-%d %H:%M")
        except Exception:
            time_str = ""

        label = f"{name}"
        if time_str:
            label += f"\n{time_str}"

        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, str(path))
        item.setSizeHint(QSize(0, 48))
        if is_last:
            item.setForeground(QColor("#1a73e8"))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self.project_list.addItem(item)

    # ──────────── 用户操作 ────────────

    def _on_open(self, item=None):
        if item is None:
            item = self.project_list.currentItem()
        if item is None:
            return
        path = item.data(Qt.UserRole)
        if path and Path(path).exists():
            self.selected_path = path
            self.accept()

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择项目文件夹", str(self.project_dir))
        if path:
            self.selected_path = path
            self.accept()

    def _on_new(self):
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
        s = QSettings("NovelAI", "UI")
        last = s.value("last_project_path", "", type=str)
        if last and Path(last).exists():
            self.selected_path = last
            self.accept()
        else:
            QMessageBox.information(self, "提示", "没有找到上次的项目")

    def _on_about(self):
        QMessageBox.about(
            self, "关于",
            f"<h3>盘古写作引擎 {APP_VERSION}</h3>"
            f"<p>AI 辅助网文写作桌面应用</p>"
            f"<p>Python 3 + PyQt5 + Selenium</p>")
