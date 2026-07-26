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


def _launcher_tokens():
    """从当前主题推导启动页配色(v2.23.6 启动页主题化)。

    此前启动页硬编码配色,且 45ba358 的暗色盲替换只换了 6 处背景、
    没换文字/悬停/顶栏,产生"深底深字项目名隐形、悬停翻回浅色"的嵌合体
    (对比度审计: #1a1a2e on #141d35 = 1.0)。改为跟随用户保存的主题,
    主题读取失败时回退深海暗黑。
    """
    qa = {}
    try:
        from ui.theme import ThemeManager
        name = ThemeManager.current()
        qa = ThemeManager.THEMES.get(
            name, ThemeManager.THEMES["light"]).get("qss_args", {}) or {}
    except Exception:
        pass
    t = {
        "bg":            qa.get("bg", "#0a0e1a"),
        "panel":         qa.get("bg_white", "#141d35"),
        "hover":         qa.get("bg_hover", "#1e2d50"),
        "selected":      qa.get("bg_selected", "#1e3a6e"),
        "text":          qa.get("text", "#e8ecf4"),
        "text_sec":      qa.get("text_sec", "#8fa3c4"),
        "text_hint":     qa.get("text_hint", "#4d6080"),
        "border":        qa.get("border", "#1e2d50"),
        "primary":       qa.get("primary", "#4a9eff"),
        "primary_dark":  qa.get("primary_dark", "#3584e4"),
        "primary_light": qa.get("primary_light", "#0f1628"),
    }
    # 亮度感知的语义色:成功绿在浅色主题用深绿、深色主题用亮绿
    def _lum(hexs):
        hexs = hexs.lstrip("#")
        r, g, b = (int(hexs[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        def lin(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    t["is_dark"] = _lum(t["panel"]) < 0.35
    t["ok"] = "#4fce7f" if t["is_dark"] else "#1e7e45"
    return t


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
        tk = _launcher_tokens()
        self._tk = tk
        self.setStyleSheet(f"""
            #project_card {{
                background: {tk["panel"]};
                border: 1px solid {tk["border"]};
                border-radius: 8px;
            }}
            #project_card:hover {{
                border-color: {tk["primary"]};
                background: {tk["hover"]};
            }}
            #project_card > QLabel {{ background: transparent; border: none; }}
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
        name_lbl.setStyleSheet(f"color:{tk['text']};")
        name_lbl.setToolTip(path.name)
        title_row.addWidget(name_lbl, 1)

        if is_last:
            badge = QLabel("上次")
            badge.setStyleSheet(
                f"background:{tk['primary_dark']}; color:white; border-radius:3px;"
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
            f"color:{tk['text_sec']}; font-size:11px; padding-left:24px;")
        lay.addWidget(stats_lbl)

        # 路径(灰色小字,截断)
        full_str = str(path)
        if len(full_str) > 40:
            short = full_str[:18] + "..." + full_str[-18:]
        else:
            short = full_str
        path_lbl = QLabel(short)
        path_lbl.setStyleSheet(
            f"color:{tk['text_hint']}; font-size:10px; padding-left:24px;")
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

        self._tk = _launcher_tokens()
        _tk = self._tk
        self.setStyleSheet(f"QDialog {{ background: {_tk['bg']}; }}")

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
        _tk = self._tk
        header.setStyleSheet(f"""
            QFrame {{
                background: {_tk["panel"]};
                border-bottom: 1px solid {_tk["border"]};
            }}
            QFrame > QLabel {{ background:transparent; border:none; }}
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)

        logo_lbl = QLabel("⚡")
        logo_lbl.setFont(QFont("Segoe UI Emoji", 16))
        h_lay.addWidget(logo_lbl)

        name_lbl = QLabel("盘古写作引擎")
        name_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        name_lbl.setStyleSheet(f"color:{_tk['text']};")
        h_lay.addWidget(name_lbl)

        ver_lbl = QLabel(f" {self._app_version} ")
        ver_lbl.setStyleSheet(
            f"background:{_tk['primary_dark']}; color:white; border-radius:4px;"
            "padding:2px 8px; font-size:11px; font-weight:bold; border:none;")
        h_lay.addWidget(ver_lbl)

        h_lay.addStretch()

        btn_about = QPushButton("ⓘ 关于")
        btn_about.setFlat(True)
        btn_about.setCursor(Qt.PointingHandCursor)
        btn_about.setStyleSheet(
            f"QPushButton {{ color:{_tk['text_sec']}; font-size:12px; padding:4px 8px;"
            "border:none; background:transparent; }"
            f"QPushButton:hover {{ color:{_tk['primary']}; }}")
        btn_about.clicked.connect(self._on_about)
        h_lay.addWidget(btn_about)

        parent_lay.addWidget(header)

    # ──────────── 左栏:快速操作 ────────────

    def _build_left_panel(self, parent_lay):
        panel = QFrame()
        panel.setFixedWidth(220)
        _tk = self._tk
        panel.setStyleSheet(
            f"QFrame {{ background: {_tk['panel']}; border-right: 1px solid {_tk['border']}; }}"
            "QFrame > QLabel { background:transparent; border:none; }")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 20, 16, 16)
        lay.setSpacing(8)

        # 新建项目(主按钮)
        btn_new = QPushButton("📁  新建项目")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setStyleSheet(f"""
            QPushButton {{
                background: {_tk["primary_dark"]}; color: white;
                padding: 14px; font-size: 13px; font-weight: bold;
                border-radius: 8px; border: none;
                text-align: left;
            }}
            QPushButton:hover {{ background: {_tk["primary"]}; }}
            QPushButton:pressed {{ background: {_tk["primary_dark"]}; }}
        """)
        btn_new.clicked.connect(self._on_new)
        lay.addWidget(btn_new)

        # 继续上次(强调按钮)
        btn_last = QPushButton("▶  继续上次")
        btn_last.setCursor(Qt.PointingHandCursor)
        btn_last.setStyleSheet(f"""
            QPushButton {{
                background: {_tk["selected"]}; color: {_tk["text"]};
                padding: 12px; font-size: 13px; font-weight: bold;
                border-radius: 8px; border: 1px solid {_tk["primary"]};
                text-align: left;
            }}
            QPushButton:hover {{ background: {_tk["hover"]}; border-color: {_tk["primary_dark"]}; }}
        """)
        btn_last.clicked.connect(self._on_continue_last)
        lay.addWidget(btn_last)

        # 打开项目(次要按钮)
        btn_open = QPushButton("📂  浏览打开")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setStyleSheet(f"""
            QPushButton {{
                background: {_tk["panel"]}; color: {_tk["text_sec"]};
                padding: 12px; font-size: 13px;
                border-radius: 8px; border: 1px solid {_tk["border"]};
                text-align: left;
            }}
            QPushButton:hover {{ background: {_tk["hover"]};
                border-color: {_tk["primary"]}; color: {_tk["text"]}; }}
        """)
        btn_open.clicked.connect(self._on_browse)
        lay.addWidget(btn_open)

        lay.addStretch()

        # 项目目录信息
        dir_lbl = QLabel("📁 项目目录")
        dir_lbl.setStyleSheet(
            f"color:{_tk['text_sec']}; font-size:11px; padding:4px 0;")
        lay.addWidget(dir_lbl)

        dir_path = str(self.project_dir)
        if len(dir_path) > 30:
            dir_path = dir_path[:14] + "..." + dir_path[-14:]
        dir_path_lbl = QLabel(dir_path)
        dir_path_lbl.setStyleSheet(f"color:{_tk['text_hint']}; font-size:10px;")
        dir_path_lbl.setToolTip(str(self.project_dir))
        lay.addWidget(dir_path_lbl)

        btn_change_dir = QPushButton("更改目录")
        btn_change_dir.setCursor(Qt.PointingHandCursor)
        btn_change_dir.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_tk["primary"]};
                padding: 6px; font-size: 11px;
                border: 1px dashed {_tk["primary"]};
                border-radius: 4px;
            }}
            QPushButton:hover {{ background: {_tk["hover"]}; }}
        """)
        btn_change_dir.clicked.connect(self._on_change_project_dir)
        lay.addWidget(btn_change_dir)

        parent_lay.addWidget(panel)

    # ──────────── 右栏:项目卡片网格 ────────────

    def _build_right_panel(self, parent_lay):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        _tk = self._tk
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {_tk["bg"]}; }}
            QScrollBar:vertical {{
                width: 8px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {_tk["border"]}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {_tk["text_hint"]}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(16)

        # ── 紧凑 hero(只占 72px,不浪费空间) ──
        hero = QFrame()
        hero.setFixedHeight(76)
        hero.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {_tk["primary_dark"]}, stop:1 {_tk["primary"]});
                border-radius: 10px;
            }}
            QFrame > QLabel {{ background:transparent; border:none; color:white; }}
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
        section_title.setStyleSheet(f"color:{_tk['text']};")
        section_row.addWidget(section_title)
        section_row.addStretch()
        self._lbl_section_hint = QLabel("双击卡片打开 · 单击选择")
        self._lbl_section_hint.setStyleSheet(
            f"color:{_tk['text_sec']}; font-size:11px;")
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
        _tk = self._tk
        footer.setStyleSheet(f"""
            QFrame {{
                background: {_tk["panel"]};
                border-top: 1px solid {_tk["border"]};
            }}
            QFrame > QLabel {{ background:transparent; border:none; }}
        """)
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(16, 0, 16, 0)

        status = QLabel("✅ 系统正常")
        status.setStyleSheet(f"font-size:11px; color:{_tk['ok']};")
        f_lay.addWidget(status)
        f_lay.addStretch()

        ver_lbl = QLabel(self._app_version)
        ver_lbl.setStyleSheet(f"font-size:11px; color:{_tk['text_sec']};")
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
            _tk = self._tk
            empty_widget.setStyleSheet(f"""
                QFrame {{
                    background: {_tk["panel"]}; border: 2px dashed {_tk["border"]};
                    border-radius: 12px;
                }}
                QFrame > QLabel {{ background:transparent; border:none; }}
            """)
            empty_widget.setMinimumHeight(200)
            ev = QVBoxLayout(empty_widget)
            ev.setAlignment(Qt.AlignCenter)

            empty_icon = QLabel("📚")
            empty_icon.setAlignment(Qt.AlignCenter)
            empty_icon.setStyleSheet(f"font-size:40px; color:{_tk['text_hint']};")
            ev.addWidget(empty_icon)

            empty_title = QLabel("还没有项目")
            empty_title.setAlignment(Qt.AlignCenter)
            empty_title.setStyleSheet(
                f"color:{_tk['text_sec']}; font-size:14px; font-weight:bold; padding:4px;")
            ev.addWidget(empty_title)

            empty_sub = QLabel('点击左侧"新建项目"开始你的第一个故事')
            empty_sub.setAlignment(Qt.AlignCenter)
            empty_sub.setStyleSheet(f"color:{_tk['text_hint']}; font-size:11px;")
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
            _tk = self._tk
            self._selected_card.setStyleSheet(f"""
                #project_card {{
                    background: {_tk["panel"]};
                    border: 1px solid {_tk["border"]};
                    border-radius: 8px;
                }}
                #project_card:hover {{
                    border-color: {_tk["primary"]};
                    background: {_tk["hover"]};
                }}
                #project_card > QLabel {{ background: transparent; border: none; }}
            """)
        _tk = self._tk
        card.setStyleSheet(f"""
            #project_card {{
                background: {_tk["selected"]};
                border: 2px solid {_tk["primary"]};
                border-radius: 8px;
            }}
            #project_card > QLabel {{ background: transparent; border: none; }}
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
