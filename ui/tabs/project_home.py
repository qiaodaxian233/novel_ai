# -*- coding: utf-8 -*-
"""ui/tabs/project_home.py - 项目主页 Tab(307 行)

v2.03 P4 拆分:从 novel_ai.py 第 178-484 行整体搬运,内容零修改。
"""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)


class ProjectHomeTab(QWidget):
    """v1.41: 项目主页 — 打开项目后第一眼看到的仪表盘

    显示:
      - 当前项目信息(书名/章数/总字数/最后保存时间)
      - 写作进度条(已写 X 章 / 目标 Y 章)
      - 最近 7 天写作字数图(简版,文字版统计)
      - 最近项目列表(快速切换)
      - 快捷操作:打开项目/新建/恢复历史版本
    """
    request_open_project = pyqtSignal()
    request_new_project = pyqtSignal()
    request_open_recent = pyqtSignal(str)   # path
    request_restore_backup = pyqtSignal()
    request_import_continuation = pyqtSignal()   # v1.51: 导入续写

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mw = None   # 主窗口的弱引用,refresh() 时填充
        self._build_ui()

    def _build_ui(self):
        from PyQt5.QtCore import Qt as _Qt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        # ── 顶部:大标题 + 当前项目名 ──
        title_box = QWidget()
        tl = QVBoxLayout(title_box)
        tl.setContentsMargins(0, 0, 0, 0)
        self.lbl_app_title = QLabel("🐉 盘古超级写作助手")
        self.lbl_app_title.setStyleSheet(
            "font-size:24px; font-weight:bold; color:#c9956b;")
        tl.addWidget(self.lbl_app_title)
        self.lbl_current_project = QLabel("(暂无打开的项目)")
        self.lbl_current_project.setStyleSheet(
            "font-size:14px; color:#8fa3c4;")
        tl.addWidget(self.lbl_current_project)
        lay.addWidget(title_box)

        # ── 中部:左快捷操作 + 右当前项目统计 ──
        from PyQt5.QtWidgets import QFrame
        mid_box = QHBoxLayout()
        mid_box.setSpacing(20)

        # 左 1/3:快捷操作
        action_box = QGroupBox("📂 项目操作")
        action_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        action_lay = QVBoxLayout(action_box)
        for txt, color, slot_name in [
            ("📂 打开项目", "#3498db", "open"),
            ("✨ 新建项目", "#27ae60", "new"),
            ("📥 导入续写(外部小说)", "#9b59b6", "import"),
            ("🕓 恢复历史版本", "#95a5a6", "restore"),
        ]:
            btn = QPushButton(txt)
            btn.setMinimumHeight(40)
            btn.setStyleSheet(
                f"QPushButton {{ background:{color}; color:white; "
                "padding:10px; border-radius:4px; font-weight:bold; "
                "font-size:13px; text-align:left; padding-left:14px; }}"
                f"QPushButton:hover {{ background-color:black; }}")
            if slot_name == "open":
                btn.clicked.connect(self.request_open_project.emit)
            elif slot_name == "new":
                btn.clicked.connect(self.request_new_project.emit)
            elif slot_name == "import":
                btn.clicked.connect(self.request_import_continuation.emit)
                btn.setToolTip(
                    "导入其他平台/AI 工具写的小说 TXT,自动拆章节,\n"
                    "可选用 AI 提取角色/世界观/伏笔/续写大纲,\n"
                    "然后从下一章接着用盘古写。")
            elif slot_name == "restore":
                btn.clicked.connect(self.request_restore_backup.emit)
            action_lay.addWidget(btn)
        action_lay.addStretch()
        mid_box.addWidget(action_box, 1)

        # 右 2/3:当前项目统计仪表盘
        stats_box = QGroupBox("📊 当前项目")
        stats_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        stats_lay = QVBoxLayout(stats_box)

        # 数据卡片(章数/总字数/最后保存)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.card_chapters = self._make_stat_card("章节数", "—", "#3498db")
        self.card_words = self._make_stat_card("总字数", "—", "#27ae60")
        self.card_avg = self._make_stat_card("平均章长", "—", "#e67e22")
        self.card_saved = self._make_stat_card("最后保存", "—", "#95a5a6")
        for c in (self.card_chapters, self.card_words,
                  self.card_avg, self.card_saved):
            cards_row.addWidget(c)
        stats_lay.addLayout(cards_row)

        # 写作进度条
        prog_row = QHBoxLayout()
        prog_label = QLabel("📖 写作进度:")
        prog_label.setStyleSheet("font-weight:bold;")
        prog_row.addWidget(prog_label)
        from PyQt5.QtWidgets import QProgressBar
        self.prog_writing = QProgressBar()
        self.prog_writing.setMinimum(0)
        self.prog_writing.setMaximum(100)
        self.prog_writing.setValue(0)
        self.prog_writing.setFormat("%v / %m 章 (%p%)")
        self.prog_writing.setStyleSheet(
            "QProgressBar { border:1px solid #888; border-radius:3px; "
            "text-align:center; height:24px; }} "
            "QProgressBar::chunk { background-color:#27ae60; }")
        prog_row.addWidget(self.prog_writing, 1)
        stats_lay.addLayout(prog_row)

        # 简短文字统计(最近一章信息)
        self.lbl_latest = QLabel("(还没写任何章节)")
        self.lbl_latest.setStyleSheet(
            "color:#8fa3c4; font-size:12px; padding:4px;")
        self.lbl_latest.setWordWrap(True)
        stats_lay.addWidget(self.lbl_latest)
        stats_lay.addStretch()
        mid_box.addWidget(stats_box, 2)

        lay.addLayout(mid_box)

        # ── 底部:最近项目列表 ──
        recent_box = QGroupBox("🕐 最近项目(点击切换)")
        recent_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        recent_lay = QVBoxLayout(recent_box)
        self.list_recent = QListWidget()
        self.list_recent.setAlternatingRowColors(True)
        self.list_recent.itemDoubleClicked.connect(self._on_recent_dblclick)
        recent_lay.addWidget(self.list_recent, 1)

        # 操作行 + 提示
        op_row = QHBoxLayout()
        self.btn_open_recent = QPushButton("📂 打开选中项目")
        self.btn_open_recent.setStyleSheet(
            "QPushButton { background:#3498db; color:white; padding:6px 14px; "
            "border-radius:3px; }")
        self.btn_open_recent.clicked.connect(self._on_open_recent)
        op_row.addWidget(self.btn_open_recent)
        self.btn_remove_recent = QPushButton("✕ 从列表移除(不删文件)")
        self.btn_remove_recent.setStyleSheet(
            "QPushButton { background:#95a5a6; color:white; padding:6px 14px; "
            "border-radius:3px; }")
        self.btn_remove_recent.clicked.connect(self._on_remove_recent)
        op_row.addWidget(self.btn_remove_recent)
        op_row.addStretch()
        recent_lay.addLayout(op_row)

        lay.addWidget(recent_box, 2)

    def _make_stat_card(self, title, value, color):
        """数据卡片:小标题 + 大数字"""
        from PyQt5.QtCore import Qt as _Qt
        w = QGroupBox()
        w.setStyleSheet(
            f"QGroupBox {{ border:2px solid {color}; border-radius:6px; "
            "padding:8px; background:rgba(0,0,0,0.02); }")
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 4, 8, 4)
        t = QLabel(title)
        t.setStyleSheet(f"color:{color}; font-size:11px; font-weight:bold;")
        t.setAlignment(_Qt.AlignCenter)
        v = QLabel(value)
        v.setStyleSheet("font-size:20px; font-weight:bold;")
        v.setAlignment(_Qt.AlignCenter)
        v.setObjectName("stat_value")
        l.addWidget(t)
        l.addWidget(v)
        return w

    def _update_card(self, card, value):
        """更新数据卡片的值"""
        v = card.findChild(QLabel, "stat_value")
        if v:
            v.setText(str(value))

    def refresh(self, mw):
        """主窗口调用 — 把当前项目状态写到仪表盘"""
        self.mw = mw
        # 当前项目名
        title = mw.tab_settings.get_title() if hasattr(mw, "tab_settings") else ""
        if mw.current_project_file:
            from pathlib import Path as _P
            self.lbl_current_project.setText(
                f"📖 当前项目:{title or '(未命名)'}  →  {_P(mw.current_project_file).name}")
            self.lbl_current_project.setStyleSheet(
                "font-size:14px; color:#27ae60; font-weight:bold;")
        else:
            self.lbl_current_project.setText("(暂无打开的项目 — 请新建或打开)")
            self.lbl_current_project.setStyleSheet(
                "font-size:14px; color:#8fa3c4;")

        # 统计
        chapters = mw.chapters or []
        ch_count = len(chapters)
        total_words = sum(len(c.get("content", "")) for c in chapters)
        avg = total_words // max(1, ch_count) if ch_count else 0
        self._update_card(self.card_chapters, f"{ch_count}")
        self._update_card(self.card_words, f"{total_words:,}")
        self._update_card(self.card_avg, f"{avg:,}" if avg else "—")

        # 最后保存时间(从文件 mtime)
        if mw.current_project_file:
            try:
                from pathlib import Path as _P
                from datetime import datetime
                pj = _P(mw.current_project_file) / "project.json"
                if pj.exists():
                    mtime = datetime.fromtimestamp(pj.stat().st_mtime)
                    self._update_card(
                        self.card_saved, mtime.strftime("%m-%d %H:%M"))
                else:
                    self._update_card(self.card_saved, "—")
            except Exception:
                self._update_card(self.card_saved, "—")
        else:
            self._update_card(self.card_saved, "—")

        # 进度条
        target_ch = 100
        try:
            target_ch = int(mw.tab_settings.get_chapter_count() or 100)
        except Exception:
            pass
        self.prog_writing.setMaximum(max(target_ch, ch_count, 1))
        self.prog_writing.setValue(ch_count)

        # 最新一章信息
        if chapters:
            last = chapters[-1]
            lt = last.get("title", "")
            lw = len(last.get("content", ""))
            self.lbl_latest.setText(
                f"📝 最新章节:第 {ch_count} 章【{lt}】 — {lw:,} 字")
        else:
            self.lbl_latest.setText("(还没写任何章节)")

        # 最近项目列表
        self.refresh_recent_list()

    def refresh_recent_list(self):
        """重新加载最近项目列表"""
        from PyQt5.QtCore import QSettings
        from pathlib import Path as _P
        self.list_recent.clear()
        try:
            recent = QSettings("NovelAI", "UI").value(
                "recent_projects", [], type=list) or []
        except Exception:
            recent = []
        if not recent:
            it = QListWidgetItem("(空 — 打开任意项目后会出现在这里)")
            it.setFlags(it.flags() & ~0x21)  # 不可选,不可编辑
            self.list_recent.addItem(it)
            return
        for path in recent[:10]:
            p = _P(path)
            if not p.exists():
                continue
            # 试着读项目信息显示更友好
            display = p.name
            try:
                pj = p / "project.json"
                if pj.exists():
                    import json as _j
                    meta = _j.loads(pj.read_text(encoding="utf-8"))
                    saved = meta.get("saved_at", "")[:16].replace("T", " ")
                    title = meta.get("title", "") or p.name
                    display = f"📖 {title}    📁 {p.name}    🕐 {saved}"
            except Exception:
                pass
            it = QListWidgetItem(display)
            it.setData(0x100, str(p))   # Qt.UserRole=0x100, 存路径
            self.list_recent.addItem(it)
        if self.list_recent.count() == 0:
            it = QListWidgetItem("(列表已清空 — 项目可能被移动或删除)")
            it.setFlags(it.flags() & ~0x21)
            self.list_recent.addItem(it)

    def _on_recent_dblclick(self, item):
        path = item.data(0x100)
        if path:
            self.request_open_recent.emit(path)

    def _on_open_recent(self):
        it = self.list_recent.currentItem()
        if it:
            path = it.data(0x100)
            if path:
                self.request_open_recent.emit(path)

    def _on_remove_recent(self):
        it = self.list_recent.currentItem()
        if not it:
            return
        path = it.data(0x100)
        if not path:
            return
        from PyQt5.QtCore import QSettings
        recent = QSettings("NovelAI", "UI").value(
            "recent_projects", [], type=list) or []
        recent = [p for p in recent if p != path]
        QSettings("NovelAI", "UI").setValue("recent_projects", recent)
        self.refresh_recent_list()
