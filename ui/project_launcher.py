# -*- coding: utf-8 -*-
"""ui/project_launcher.py - 项目启动器

v2.23.5 重写:从"营销落地页"重新设计为"用户启动页"
设计理念:
- 用户打开是为了"快速进入项目",不是看产品介绍
- 大部分空间留给最近项目卡片(带统计预览)
- 去掉无意义的 6 个功能宣传卡片(用户都用过应用了)
- 紧凑 hero + 项目卡片网格 + 底部状态栏
"""
import os
import re
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QInputDialog, QMessageBox, QFrame, QGridLayout,
    QWidget, QScrollArea,
)
from PyQt5.QtGui import QFont, QIcon


APP_VERSION = "v2.23.5"


def _get_app_version():
    """从 novel_ai.py 读取最新版本号(避免硬编码漂移)"""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "novel_ai.py"), encoding="utf-8") as f:
            for _ in range(30):
                line = f.readline()
                m = re.search(r'APP_VERSION\s*=\s*"(v[\d.]+)"', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return APP_VERSION


def _count_project_stats(path):
    """快速统计项目:章节数 / 最后修改时间"""
    stats = {"chapters": 0, "mtime": None}
    try:
        ch_dir = path / "chapters"
        if ch_dir.exists():
            files = [f for f in ch_dir.iterdir() if f.is_file()
                     and f.suffix in (".txt", ".md", ".json")]
            stats["chapters"] = len(files)
        try:
            stats["mtime"] = datetime.fromtimestamp(path.stat().st_mtime)
        except Exception:
            pass
    except Exception:
        pass
    return stats


def _is_valid_project(path):
    """判断一个目录是否为有效项目(过滤 autosave/migrated 等垃圾)"""
    name = path.name
    # 排除明显的系统/备份文件夹
    if name.startswith(".") or name.startswith("_"):
        return False
    if name.endswith("_backup") or name.endswith("_migrated"):
        return False
    if name in ("autosave", "trash", "logs", "cache", "NovelAI_Projects"):
        return False
    # 必须有项目标志文件
    has_marker = (
        (path / "chapters").exists()
        or (path / "meta.json").exists()
        or (path / "project.json").exists()
    )
    return has_marker


def _format_time_ago(mtime):
    """格式化时间为"X 分钟前 / X 小时前 / X 天前 / 日期" """
    if not mtime:
        return ""
    now = datetime.now()
    delta = now - mtime
    if delta.days == 0:
        if delta.seconds < 60:
            return "刚刚"
        if delta.seconds < 3600:
            return f"{delta.seconds // 60} 分钟前"
        return f"{delta.seconds // 3600} 小时前"
    if delta.days < 7:
        return f"{delta.days} 天前"
    return mtime.strftime("%Y-%m-%d")


class ProjectCard(QFrame):
    """项目卡片 — 显示项目名、章节数、最后修改时间"""

    def __init__(self, path, is_last=False, parent=None):
        super().__init__(parent)
        self.path = path
        self.setObjectName("project_card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            #project_card {
                background: white;
                border: 1px solid #e0e6ed;
                border-radius: 8px;
            }
            #project_card:hover {
                border-color: #4a9eff;
                background: #f8fbff;
            }
            #project_card > QLabel { background: transparent; border: none; }
        """)
        self.setMinimumHeight(112)
        self.setMaximumHeight(128)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(6)

        # 标题行:📖 项目名 + "最近"徽章
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        icon_lbl = QLabel("📖")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 14))
        title_row.addWidget(icon_lbl)

        # 项目名(超长截断)
        name = path.name
        if len(name) > 14:
            name_display = name[:12] + "..."
        else:
            name_display = name
        name_lbl = QLabel(name_display)
        name_lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        name_lbl.setStyleSheet("color:#1a1a2e;")
        name_lbl.setToolTip(path.name)
        title_row.addWidget(name_lbl, 1)

        if is_last:
            badge = QLabel("上次")
            badge.setStyleSheet(
                "background:#4a9eff; color:white; border-radius:3px;"
                "padding:1px 6px; font-size:10px; border:none;")
            title_row.addWidget(badge)
        lay.addLayout(title_row)

        # 统计行
        stats = _count_project_stats(path)
        stat_text = []
        if stats["chapters"] > 0:
            stat_text.append(f"📄 {stats['chapters']} 章")
        if stats["mtime"]:
            stat_text.append(f"🕐 {_format_time_ago(stats['mtime'])}")

        stats_lbl = QLabel("   ·   ".join(stat_text) or "(空项目)")
        stats_lbl.setStyleSheet(
            "color:#888; font-size:11px; padding-left:24px;")
        lay.addWidget(stats_lbl)

        # 路径(灰色小字,截断)
        full_str = str(path)
        if len(full_str) > 40:
            short = full_str[:18] + "..." + full_str[-18:]
        else:
            short = full_str
        path_lbl = QLabel(short)
        path_lbl.setStyleSheet(
            "color:#bbb; font-size:10px; padding-left:24px;")
        path_lbl.setToolTip(full_str)
        lay.addWidget(path_lbl)

    def mouseDoubleClickEvent(self, ev):
        # 双击 = 打开项目
        w = self
        while w and not isinstance(w, ProjectLauncher):
            w = w.parent()
        if w:
            w.selected_path = str(self.path)
            w.accept()

    def mousePressEvent(self, ev):
        # 单击 = 单选高亮
        w = self
        while w and not isinstance(w, ProjectLauncher):
            w = w.parent()
        if w:
            w._select_card(self)
        super().mousePressEvent(ev)


class ProjectLauncher(QDialog):
    """项目启动器 v2.23.5 — 用户启动页"""

    def __init__(self, project_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("盘古写作引擎")
        self.resize(880, 600)
        self.setMinimumSize(720, 500)
        self.setWindowFlags(
            Qt.WindowCloseButtonHint | Qt.WindowTitleHint
            | Qt.WindowMinMaxButtonsHint)
        self.project_dir = Path(project_dir)
        self.selected_path = None
        self._app_version = _get_app_version()
        self._selected_card = None

        # 图标
        _icon = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "assets", "icon.ico")
        if os.path.exists(_icon):
            self.setWindowIcon(QIcon(_icon))

        self.setStyleSheet("QDialog { background: #f5f7fa; }")

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        self._build_header(main_lay)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._build_left_panel(body)
        self._build_right_panel(body)
        main_lay.addLayout(body, 1)

        self._build_footer(main_lay)

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
            QFrame > QLabel { background:transparent; border:none; }
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)

        logo_lbl = QLabel("⚡")
        logo_lbl.setFont(QFont("Segoe UI Emoji", 16))
        h_lay.addWidget(logo_lbl)

        name_lbl = QLabel("盘古写作引擎")
        name_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        name_lbl.setStyleSheet("color:#1a1a2e;")
        h_lay.addWidget(name_lbl)

        ver_lbl = QLabel(f" {self._app_version} ")
        ver_lbl.setStyleSheet(
            "background:#4a9eff; color:white; border-radius:4px;"
            "padding:2px 8px; font-size:11px; font-weight:bold; border:none;")
        h_lay.addWidget(ver_lbl)

        h_lay.addStretch()

        btn_about = QPushButton("ⓘ 关于")
        btn_about.setFlat(True)
        btn_about.setCursor(Qt.PointingHandCursor)
        btn_about.setStyleSheet(
            "QPushButton { color:#555; font-size:12px; padding:4px 8px;"
            "border:none; background:transparent; }"
            "QPushButton:hover { color:#1a73e8; }")
        btn_about.clicked.connect(self._on_about)
        h_lay.addWidget(btn_about)

        parent_lay.addWidget(header)

    # ──────────── 左栏:快速操作 ────────────

    def _build_left_panel(self, parent_lay):
        panel = QFrame()
        panel.setFixedWidth(220)
        panel.setStyleSheet(
            "QFrame { background: white; border-right: 1px solid #e0e4ef; }"
            "QFrame > QLabel { background:transparent; border:none; }")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(8)

        # 新建项目(主按钮)
        btn_new = QPushButton("📁  新建项目")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setStyleSheet("""
            QPushButton {
                background: #4a9eff; color: white;
                padding: 14px; font-size: 13px; font-weight: bold;
                border-radius: 8px; border: none;
                text-align: left;
            }
            QPushButton:hover { background: #3584e4; }
            QPushButton:pressed { background: #2563cc; }
        """)
        btn_new.clicked.connect(self._on_new)
        lay.addWidget(btn_new)

        # 继续上次(强调按钮)
        btn_last = QPushButton("▶  继续上次")
        btn_last.setCursor(Qt.PointingHandCursor)
        btn_last.setStyleSheet("""
            QPushButton {
                background: #eef5ff; color: #1a73e8;
                padding: 12px; font-size: 13px; font-weight: bold;
                border-radius: 8px; border: 1px solid #c8def5;
                text-align: left;
            }
            QPushButton:hover { background: #dceaff; border-color: #4a9eff; }
        """)
        btn_last.clicked.connect(self._on_continue_last)
        lay.addWidget(btn_last)

        # 打开项目(次要按钮)
        btn_open = QPushButton("📂  浏览打开")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setStyleSheet("""
            QPushButton {
                background: white; color: #555;
                padding: 12px; font-size: 13px;
                border-radius: 8px; border: 1px solid #e0e6ed;
                text-align: left;
            }
            QPushButton:hover { background: #f5f8ff;
                border-color: #4a9eff; color: #1a73e8; }
        """)
        btn_open.clicked.connect(self._on_browse)
        lay.addWidget(btn_open)

        lay.addStretch()

        # 项目目录信息
        dir_lbl = QLabel("📁 项目目录")
        dir_lbl.setStyleSheet(
            "color:#888; font-size:11px; padding:4px 0;")
        lay.addWidget(dir_lbl)

        dir_path = str(self.project_dir)
        if len(dir_path) > 30:
            dir_path = dir_path[:14] + "..." + dir_path[-14:]
        dir_path_lbl = QLabel(dir_path)
        dir_path_lbl.setStyleSheet("color:#aaa; font-size:10px;")
        dir_path_lbl.setToolTip(str(self.project_dir))
        lay.addWidget(dir_path_lbl)

        btn_change_dir = QPushButton("更改目录")
        btn_change_dir.setCursor(Qt.PointingHandCursor)
        btn_change_dir.setStyleSheet("""
            QPushButton {
                background: transparent; color: #4a9eff;
                padding: 6px; font-size: 11px;
                border: 1px dashed #4a9eff;
                border-radius: 4px;
            }
            QPushButton:hover { background: #eef5ff; }
        """)
        btn_change_dir.clicked.connect(self._on_change_project_dir)
        lay.addWidget(btn_change_dir)

        parent_lay.addWidget(panel)

    # ──────────── 右栏:项目卡片网格 ────────────

    def _build_right_panel(self, parent_lay):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #f5f7fa; }
            QScrollBar:vertical {
                width: 8px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #c0c8d0; border-radius: 4px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #a0a8b0; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(16)

        # ── 紧凑 hero(只占 72px,不浪费空间) ──
        hero = QFrame()
        hero.setFixedHeight(76)
        hero.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4a9eff, stop:1 #6eb5ff);
                border-radius: 10px;
            }
            QFrame > QLabel { background:transparent; border:none; color:white; }
        """)
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(20, 12, 20, 12)
        hero_lay.setSpacing(12)

        hero_icon = QLabel("✍️")
        hero_icon.setFont(QFont("Segoe UI Emoji", 26))
        hero_lay.addWidget(hero_icon)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(2)
        hero_title = QLabel("欢迎回来,开始你的创作")
        hero_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        hero_text.addWidget(hero_title)

        hero_sub = QLabel("选择最近项目继续,或新建一个故事")
        hero_sub.setStyleSheet("color:rgba(255,255,255,200); font-size:11px;")
        hero_text.addWidget(hero_sub)
        hero_lay.addLayout(hero_text, 1)

        # 右上角统计
        stats_box = QVBoxLayout()
        stats_box.setSpacing(0)
        self._lbl_total_proj = QLabel("0")
        self._lbl_total_proj.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        self._lbl_total_proj.setStyleSheet("color:white;")
        self._lbl_total_proj.setAlignment(Qt.AlignRight)
        stats_box.addWidget(self._lbl_total_proj)
        stats_lbl = QLabel("个项目")
        stats_lbl.setStyleSheet("color:rgba(255,255,255,200); font-size:11px;")
        stats_lbl.setAlignment(Qt.AlignRight)
        stats_box.addWidget(stats_lbl)
        hero_lay.addLayout(stats_box)

        lay.addWidget(hero)

        # ── "最近项目" 标题行 ──
        section_row = QHBoxLayout()
        section_title = QLabel("📚 最近项目")
        section_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        section_title.setStyleSheet("color:#1a1a2e;")
        section_row.addWidget(section_title)
        section_row.addStretch()
        self._lbl_section_hint = QLabel("双击卡片打开 · 单击选择")
        self._lbl_section_hint.setStyleSheet("color:#999; font-size:11px;")
        section_row.addWidget(self._lbl_section_hint)
        lay.addLayout(section_row)

        # ── 项目卡片网格容器 ──
        self.cards_widget = QWidget()
        self.cards_grid = QGridLayout(self.cards_widget)
        self.cards_grid.setSpacing(12)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.cards_widget)

        lay.addStretch()

        scroll.setWidget(content)
        parent_lay.addWidget(scroll, 1)

    # ──────────── 底部状态栏 ────────────

    def _build_footer(self, parent_lay):
        footer = QFrame()
        footer.setFixedHeight(28)
        footer.setStyleSheet("""
            QFrame {
                background: white;
                border-top: 1px solid #e0e4ef;
            }
            QFrame > QLabel { background:transparent; border:none; }
        """)
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(16, 0, 16, 0)

        status = QLabel("✅ 系统正常")
        status.setStyleSheet("font-size:11px; color:#27ae60;")
        f_lay.addWidget(status)
        f_lay.addStretch()

        ver_lbl = QLabel(self._app_version)
        ver_lbl.setStyleSheet("font-size:11px; color:#999;")
        f_lay.addWidget(ver_lbl)

        parent_lay.addWidget(footer)

    # ──────────── 数据加载 ────────────

    def _load_projects(self):
        # 清空现有 cards
        while self.cards_grid.count():
            child = self.cards_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._selected_card = None

        seen = set()
        projects = []

        s = QSettings("NovelAI", "UI")
        recent = s.value("recent_projects", [], type=list) or []
        last = s.value("last_project_path", "", type=str)

        # 先加 recent_projects(保持时间顺序)
        for path in recent:
            p = Path(path)
            if p.exists() and p.is_dir() and str(p) not in seen \
                    and _is_valid_project(p):
                projects.append((p, str(p) == last))
                seen.add(str(p))

        # 再扫 project_dir(按修改时间倒序)
        if self.project_dir.exists():
            try:
                items = sorted(
                    [d for d in self.project_dir.iterdir() if d.is_dir()],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True)
            except Exception:
                items = list(self.project_dir.iterdir())
            for d in items:
                if str(d) not in seen and _is_valid_project(d):
                    projects.append((d, False))
                    seen.add(str(d))

        # 统计
        self._lbl_total_proj.setText(str(len(projects)))

        if not projects:
            # 空状态
            empty_widget = QFrame()
            empty_widget.setStyleSheet("""
                QFrame {
                    background: white; border: 2px dashed #e0e6ed;
                    border-radius: 12px;
                }
                QFrame > QLabel { background:transparent; border:none; }
            """)
            empty_widget.setMinimumHeight(200)
            ev = QVBoxLayout(empty_widget)
            ev.setAlignment(Qt.AlignCenter)

            empty_icon = QLabel("📚")
            empty_icon.setAlignment(Qt.AlignCenter)
            empty_icon.setStyleSheet("font-size:40px; color:#bbb;")
            ev.addWidget(empty_icon)

            empty_title = QLabel("还没有项目")
            empty_title.setAlignment(Qt.AlignCenter)
            empty_title.setStyleSheet(
                "color:#666; font-size:14px; font-weight:bold; padding:4px;")
            ev.addWidget(empty_title)

            empty_sub = QLabel('点击左侧"新建项目"开始你的第一个故事')
            empty_sub.setAlignment(Qt.AlignCenter)
            empty_sub.setStyleSheet("color:#999; font-size:11px;")
            ev.addWidget(empty_sub)

            self.cards_grid.addWidget(empty_widget, 0, 0, 1, 2)
            self._lbl_section_hint.setText("")
            return

        # 添加项目卡片(2 列)
        for idx, (path, is_last) in enumerate(projects):
            card = ProjectCard(path, is_last=is_last)
            self.cards_grid.addWidget(card, idx // 2, idx % 2)

        self.cards_grid.setColumnStretch(0, 1)
        self.cards_grid.setColumnStretch(1, 1)

    def _select_card(self, card):
        """单选高亮"""
        if self._selected_card is card:
            return
        if self._selected_card is not None:
            self._selected_card.setStyleSheet("""
                #project_card {
                    background: white;
                    border: 1px solid #e0e6ed;
                    border-radius: 8px;
                }
                #project_card:hover {
                    border-color: #4a9eff;
                    background: #f8fbff;
                }
                #project_card > QLabel { background: transparent; border: none; }
            """)
        card.setStyleSheet("""
            #project_card {
                background: #eef5ff;
                border: 2px solid #4a9eff;
                border-radius: 8px;
            }
            #project_card > QLabel { background: transparent; border: none; }
        """)
        self._selected_card = card

    # ──────────── 用户操作 ────────────

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
            QMessageBox.information(
                self, "提示",
                "没有找到上次的项目,请从最近项目中选择或新建")

    def _on_change_project_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择新的项目目录", str(self.project_dir))
        if path:
            self.project_dir = Path(path)
            QSettings("NovelAI", "UI").setValue("project_dir", path)
            self._load_projects()

    def _on_about(self):
        QMessageBox.about(
            self, "关于",
            f"<h3>盘古写作引擎 {self._app_version}</h3>"
            f"<p>AI 辅助网文写作桌面应用</p>"
            f"<p>Python 3 + PyQt5 + Selenium</p>")
