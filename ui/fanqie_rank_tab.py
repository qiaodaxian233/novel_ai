# -*- coding: utf-8 -*-
"""ui/fanqie_rank_tab.py - 📊 番茄榜单 独立 Tab

v2.23.4: 扫完的番茄榜单在主界面独立 Tab 展示。
数据来源:
  - 内存缓存 `_v231_rank_stats_cache`(最新扫榜统计)
  - 磁盘缓存 `.fanqie_cache/`(扫榜快照 + 书详情)
  - Worker 信号(实时更新进度)

布局:
  ┌──────────────────────────────────────────────┐
  │ 📊 番茄榜单   [最后更新: 2026-05-27 00:33]   │
  │              [🔄 刷新扫榜] [📂 打开缓存目录] │
  ├──────────────┬───────────────────────────────┤
  │ 🔥 男频热度  │ 💃 女频热度                   │
  │ ┌──────────┐ │ ┌──────────────┐              │
  │ │ 都市高武 │ │ │ 豪门总裁     │              │
  │ │  87万    │ │ │  60万        │              │
  │ │ ...      │ │ │ ...          │              │
  │ └──────────┘ │ └──────────────┘              │
  ├──────────────┴───────────────────────────────┤
  │ 📚 详情已抓 32/300 本                        │
  │ ┌──┬─────────┬────┬──────┬─────┬───────────┐ │
  │ │# │ 书名    │作者│ 题材 │ 标签│ 在读数    │ │
  │ ├──┼─────────┼────┼──────┼─────┼───────────┤ │
  │ │1 │ 早知道..│嘎嘎│西方奇│系统..│ 64.7万   │ │
  │ └──┴─────────┴────┴──────┴─────┴───────────┘ │
  └──────────────────────────────────────────────┘
"""

import json
import os
import time

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush
from PyQt5.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QGroupBox, QProgressBar, QAbstractItemView,
)


class FanqieRankTab(QWidget):
    """📊 番茄榜单展示面板"""

    # 用户点"刷新扫榜"发出(主进程 connect 后触发 worker 任务)
    request_rescan = pyqtSignal()
    request_log = pyqtSignal(str, str)

    def __init__(self, mw=None, parent=None):
        super().__init__(parent)
        self.mw = mw
        self._last_stats = None       # 最近一次的 stats dict
        self._last_scraped_at = 0.0   # 最近一次扫榜时间
        self._detail_total = 0
        self._detail_done = 0
        self._project_root = ""       # 项目根目录(由主进程设)
        self._build_ui()

    # ──────────────── UI 构建 ────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # ── 顶部:标题 + 状态 + 按钮 ──
        top_row = QHBoxLayout()

        title = QLabel("📊 番茄榜单")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        top_row.addWidget(title)

        self.lbl_status = QLabel("尚未扫描")
        self.lbl_status.setStyleSheet(
            "color:#888; font-size:13px; padding-left:12px;")
        top_row.addWidget(self.lbl_status)
        top_row.addStretch()

        self.btn_rescan = QPushButton("🔄 刷新扫榜")
        self.btn_rescan.setMinimumWidth(100)
        self.btn_rescan.clicked.connect(self._on_rescan_clicked)
        top_row.addWidget(self.btn_rescan)

        self.btn_open_cache = QPushButton("📂 打开缓存目录")
        self.btn_open_cache.setMinimumWidth(120)
        self.btn_open_cache.clicked.connect(self._on_open_cache)
        top_row.addWidget(self.btn_open_cache)

        lay.addLayout(top_row)

        # ── 提示 ──
        hint = QLabel(
            "展示番茄小说全榜扫描结果(74 个分类 × Top10)。"
            "程序启动后 30 秒自动后台扫描,24 小时缓存。"
            "详情会后台逐本抓取,7 天缓存。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666; font-size:12px; padding-bottom:4px;")
        lay.addWidget(hint)

        # ── 中间:男频 / 女频 热度(左右分栏) ──
        splitter = QSplitter(Qt.Horizontal)

        # 男频
        male_box = QGroupBox("🔥 男频题材热度")
        male_box.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        male_lay = QVBoxLayout(male_box)
        self.tbl_male = self._make_heat_table()
        male_lay.addWidget(self.tbl_male)
        splitter.addWidget(male_box)

        # 女频
        female_box = QGroupBox("💃 女频题材热度")
        female_box.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        female_lay = QVBoxLayout(female_box)
        self.tbl_female = self._make_heat_table()
        female_lay.addWidget(self.tbl_female)
        splitter.addWidget(female_box)

        splitter.setSizes([400, 400])
        lay.addWidget(splitter)

        # ── 下方:详情进度 + 详情表格 ──
        detail_header = QHBoxLayout()
        self.lbl_detail = QLabel("📚 详情抓取:等待扫榜完成")
        self.lbl_detail.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        detail_header.addWidget(self.lbl_detail)
        detail_header.addStretch()

        self.progress_detail = QProgressBar()
        self.progress_detail.setMinimumWidth(200)
        self.progress_detail.setMaximumHeight(18)
        self.progress_detail.setVisible(False)
        detail_header.addWidget(self.progress_detail)
        lay.addLayout(detail_header)

        self.tbl_detail = self._make_detail_table()
        lay.addWidget(self.tbl_detail, 1)  # stretch=1 让它占满剩余空间

    def _make_heat_table(self) -> QTableWidget:
        """创建题材热度表(排名 / 题材 / 平均在读)"""
        tbl = QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["#", "题材", "平均在读(万)"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.setColumnWidth(0, 40)
        tbl.setColumnWidth(2, 110)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        return tbl

    def _make_detail_table(self) -> QTableWidget:
        """创建详情表(书名 / 作者 / 题材 / 标签 / 在读数 / 简介)"""
        tbl = QTableWidget(0, 6)
        tbl.setHorizontalHeaderLabels(
            ["书名", "作者", "题材", "标签", "在读", "简介"])
        tbl.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        tbl.setColumnWidth(0, 180)
        tbl.setColumnWidth(1, 100)
        tbl.setColumnWidth(2, 100)
        tbl.setColumnWidth(3, 200)
        tbl.setColumnWidth(4, 80)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setSortingEnabled(True)
        return tbl

    # ──────────────── 数据更新 API(主进程调用) ────────────────

    def set_project_root(self, root: str):
        """设置项目根目录(用于读磁盘缓存)"""
        self._project_root = root or ""

    def update_stats(self, stats: dict, scraped_at: float = 0.0):
        """
        用扫榜统计刷新热度表。

        stats 格式同 aggregate_v231_stats 输出:
          hot_categories_male: [(cat, avg_read), ...]
          hot_categories_female: [(cat, avg_read), ...]
          total_books, unique_books, ...
        """
        if not stats:
            return

        self._last_stats = stats
        self._last_scraped_at = scraped_at or time.time()

        # 更新状态
        from datetime import datetime
        dt = datetime.fromtimestamp(self._last_scraped_at)
        total = stats.get("total_books", 0)
        unique = stats.get("unique_books", 0)
        self.lbl_status.setText(
            f"最后扫描: {dt.strftime('%Y-%m-%d %H:%M')}  |  "
            f"总计 {total} 本(去重 {unique} 本) | 74 个榜单")
        self.lbl_status.setStyleSheet(
            "color:#2d8a4e; font-size:13px; padding-left:12px; font-weight:bold;")

        # 填男频
        self._fill_heat_table(
            self.tbl_male, stats.get("hot_categories_male", []))
        # 填女频
        self._fill_heat_table(
            self.tbl_female, stats.get("hot_categories_female", []))

    def _fill_heat_table(self, tbl: QTableWidget,
                         data: list):
        """
        填充热度表

        data: [(category_name, avg_read_num), ...]  avg_read_num 是原始数字
        """
        tbl.setRowCount(0)
        tbl.setSortingEnabled(False)

        # 颜色梯度:前 3 名金/银/铜,4-10 渐变淡
        GOLD = QColor(255, 215, 0)
        SILVER = QColor(192, 192, 192)
        BRONZE = QColor(205, 127, 50)
        COLORS = [GOLD, SILVER, BRONZE]

        for i, (cat, avg_read) in enumerate(data[:20]):
            row = tbl.rowCount()
            tbl.insertRow(row)

            # 排名
            rank_item = QTableWidgetItem(str(i + 1))
            rank_item.setTextAlignment(Qt.AlignCenter)
            if i < 3:
                rank_item.setBackground(QBrush(COLORS[i].lighter(160)))
                rank_item.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            tbl.setItem(row, 0, rank_item)

            # 题材
            cat_item = QTableWidgetItem(cat)
            if i < 3:
                cat_item.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            tbl.setItem(row, 1, cat_item)

            # 在读(万)
            if avg_read >= 10000:
                display = f"{avg_read / 10000:.1f}"
            else:
                display = f"{avg_read / 10000:.2f}"
            read_item = QTableWidgetItem(display)
            read_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            # 排序用原始数字
            read_item.setData(Qt.UserRole, avg_read)
            if i < 3:
                read_item.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            tbl.setItem(row, 2, read_item)

        tbl.setSortingEnabled(True)

    def update_scan_progress(self, current: int, total: int,
                             label: str, n_books: int):
        """扫榜进度(每扫完一个榜单 worker emit)"""
        pct = int(current / total * 100) if total else 0
        self.lbl_status.setText(
            f"扫描中 {current}/{total} ({pct}%)  当前: {label} → {n_books} 本")
        self.lbl_status.setStyleSheet(
            "color:#c67b17; font-size:13px; padding-left:12px;")

    def update_detail_progress(self, current: int, total: int, book_id: str):
        """详情抓取进度"""
        self._detail_done = current
        self._detail_total = total
        self.progress_detail.setVisible(True)
        self.progress_detail.setMaximum(total)
        self.progress_detail.setValue(current)
        self.lbl_detail.setText(
            f"📚 详情抓取: {current}/{total} 本")

    def on_detail_batch_done(self, success: int, fail: int):
        """详情批抓完成"""
        self.progress_detail.setVisible(False)
        self.lbl_detail.setText(
            f"📚 详情已抓 {success} 本(失败 {fail})")
        # 自动刷新详情表格
        self.load_details_from_disk()

    def load_details_from_disk(self):
        """从磁盘缓存加载书详情并填充表格"""
        if not self._project_root:
            return

        cache_dir = os.path.join(self._project_root, ".fanqie_cache", "books")
        if not os.path.isdir(cache_dir):
            self.lbl_detail.setText("📚 详情: 无缓存(等待后台抓取)")
            return

        books = []
        now = time.time()
        TTL = 7 * 24 * 3600  # 7 天

        try:
            for fname in os.listdir(cache_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(cache_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                # 过期跳过
                if now - float(data.get("scraped_at", 0)) > TTL:
                    continue
                detail = data.get("detail", {})
                if not detail:
                    continue
                books.append({
                    "title": detail.get("title", ""),
                    "author": detail.get("author", ""),
                    "category": data.get("source_category", ""),
                    "tags": ", ".join(detail.get("tags", [])),
                    "read": detail.get("word_count", ""),
                    "abstract": (detail.get("abstract", "") or "")[:200],
                })
        except Exception:
            pass

        self._fill_detail_table(books)

    def _fill_detail_table(self, books: list):
        """填充详情表格"""
        tbl = self.tbl_detail
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)

        for i, b in enumerate(books):
            row = tbl.rowCount()
            tbl.insertRow(row)

            tbl.setItem(row, 0, QTableWidgetItem(b.get("title", "")))
            tbl.setItem(row, 1, QTableWidgetItem(b.get("author", "")))
            tbl.setItem(row, 2, QTableWidgetItem(b.get("category", "")))
            tbl.setItem(row, 3, QTableWidgetItem(b.get("tags", "")))
            tbl.setItem(row, 4, QTableWidgetItem(b.get("read", "")))

            # 简介用 tooltip 显示完整版
            abstract = b.get("abstract", "")
            abstract_item = QTableWidgetItem(
                abstract[:60] + "..." if len(abstract) > 60 else abstract)
            abstract_item.setToolTip(abstract)
            tbl.setItem(row, 5, abstract_item)

        tbl.setSortingEnabled(True)
        self.lbl_detail.setText(f"📚 详情: 已加载 {len(books)} 本")

    def load_snapshot_from_disk(self):
        """
        启动时尝试从磁盘加载最近的扫榜快照(rank_snapshot_*.json)

        这样即使程序刚启动,上次扫过的数据也能立刻展示。
        """
        if not self._project_root:
            return

        cache_dir = os.path.join(self._project_root, ".fanqie_cache")
        if not os.path.isdir(cache_dir):
            return

        # 找最近的 rank_snapshot_*.json
        snapshots = []
        try:
            for f in os.listdir(cache_dir):
                if f.startswith("rank_snapshot_") and f.endswith(".json"):
                    fpath = os.path.join(cache_dir, f)
                    snapshots.append(fpath)
        except Exception:
            return

        if not snapshots:
            return

        snapshots.sort(reverse=True)  # 日期大的在前
        latest = snapshots[0]

        try:
            with open(latest, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        stats = data.get("stats", {})
        scraped_at = float(data.get("scraped_at", 0))

        if stats:
            self.update_stats(stats, scraped_at)
            self.load_details_from_disk()

    # ──────────────── 用户操作 ────────────────

    def _on_rescan_clicked(self):
        """用户点"刷新扫榜"""
        self.btn_rescan.setEnabled(False)
        self.btn_rescan.setText("扫描中...")
        self.lbl_status.setText("正在启动全榜扫描...")
        self.lbl_status.setStyleSheet(
            "color:#c67b17; font-size:13px; padding-left:12px;")

        # 5 秒后恢复按钮(防连点)
        QTimer.singleShot(5000, self._reenable_rescan)

        self.request_rescan.emit()

    def _reenable_rescan(self):
        self.btn_rescan.setEnabled(True)
        self.btn_rescan.setText("🔄 刷新扫榜")

    def _on_open_cache(self):
        """打开缓存目录"""
        if not self._project_root:
            QMessageBox.information(self, "提示", "请先打开一个项目")
            return
        cache_dir = os.path.join(self._project_root, ".fanqie_cache")
        if not os.path.isdir(cache_dir):
            QMessageBox.information(
                self, "提示", f"缓存目录不存在:\n{cache_dir}\n请先扫一次榜。")
            return
        # 打开文件管理器
        import subprocess
        try:
            subprocess.Popen(["explorer", cache_dir.replace("/", "\\")])
        except Exception:
            try:
                os.startfile(cache_dir)
            except Exception:
                QMessageBox.information(
                    self, "缓存目录", cache_dir)
