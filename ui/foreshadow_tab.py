# -*- coding: utf-8 -*-
"""ui/foreshadow_tab.py - 长期伏笔检查 独立Tab

v2.20.5 从 lifespan_loops_panel.py 拆出,独立大界面。
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class ForeshadowTab(QWidget):
    """长期伏笔检查 — 独立 Tab,大字体,清晰可见"""
    request_save = pyqtSignal()
    request_log = pyqtSignal(str, str)

    def __init__(self, mw=None, parent=None):
        super().__init__(parent)
        self.mw = mw
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # 标题
        title = QLabel("🪤 长期伏笔检查")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        lay.addWidget(title)

        hint = QLabel(
            "跟踪所有埋下的伏笔,超过设定章数未回收的自动标红。"
            "写章节时自动扫描关键词,检测是否已触及。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666; font-size:13px; padding-bottom:8px;")
        lay.addWidget(hint)

        # 配置行
        cfg_row = QHBoxLayout()
        self.chk_enabled = QCheckBox("启用伏笔检查")
        self.chk_enabled.setChecked(False)
        self.chk_enabled.setFont(QFont("Microsoft YaHei", 12))
        cfg_row.addWidget(self.chk_enabled)
        cfg_row.addSpacing(20)
        cfg_row.addWidget(QLabel("预警阈值:"))
        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(5, 1000)
        self.spin_warn.setValue(80)
        self.spin_warn.setSuffix(" 章")
        self.spin_warn.setMinimumWidth(80)
        cfg_row.addWidget(self.spin_warn)
        cfg_row.addSpacing(10)
        cfg_row.addWidget(QLabel("严重阈值:"))
        self.spin_critical = QSpinBox()
        self.spin_critical.setRange(10, 2000)
        self.spin_critical.setValue(150)
        self.spin_critical.setSuffix(" 章")
        self.spin_critical.setMinimumWidth(80)
        cfg_row.addWidget(self.spin_critical)
        cfg_row.addStretch()
        lay.addLayout(cfg_row)

        # 伏笔表格
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "伏笔描述", "埋设章节", "最近触及", "关键词", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 80)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setFont(QFont("Microsoft YaHei", 11))
        self.table.verticalHeader().setDefaultSectionSize(32)
        lay.addWidget(self.table, 1)

        # 编辑区
        edit_box = QGroupBox("添加/编辑伏笔")
        edit_box.setFont(QFont("Microsoft YaHei", 11))
        grid = QGridLayout(edit_box)
        grid.setSpacing(8)

        grid.addWidget(QLabel("ID:"), 0, 0)
        self.edit_id = QLineEdit()
        self.edit_id.setPlaceholderText("f001")
        self.edit_id.setFont(QFont("Microsoft YaHei", 12))
        grid.addWidget(self.edit_id, 0, 1)

        grid.addWidget(QLabel("描述:"), 0, 2)
        self.edit_desc = QLineEdit()
        self.edit_desc.setPlaceholderText("主角身世之谜")
        self.edit_desc.setFont(QFont("Microsoft YaHei", 12))
        grid.addWidget(self.edit_desc, 0, 3)

        grid.addWidget(QLabel("埋设章节:"), 1, 0)
        self.spin_chapter = QSpinBox()
        self.spin_chapter.setRange(1, 99999)
        self.spin_chapter.setValue(1)
        self.spin_chapter.setPrefix("第 ")
        self.spin_chapter.setSuffix(" 章")
        self.spin_chapter.setFont(QFont("Microsoft YaHei", 12))
        grid.addWidget(self.spin_chapter, 1, 1)

        grid.addWidget(QLabel("关键词:"), 1, 2)
        self.edit_keyword = QLineEdit()
        self.edit_keyword.setPlaceholderText("身世/秘密(用于自动扫描)")
        self.edit_keyword.setFont(QFont("Microsoft YaHei", 12))
        grid.addWidget(self.edit_keyword, 1, 3)
        lay.addWidget(edit_box)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        for text, style, handler in [
            ("➕ 添加", "background:#27ae60; color:white;", self._on_add),
            ("✓ 标记已回收", "background:#1a73e8; color:white;", self._on_close),
            ("↺ 重开", "background:#e67e22; color:white;", self._on_reopen),
            ("🔍 检查逾期", "background:#e74c3c; color:white;", self._on_check),
            ("🗑 删除", "background:#c0392b; color:white;", self._on_delete),
            ("🗑 清空全部", "background:#95a5a6; color:white;", self._on_clear),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(
                f"QPushButton {{ {style} padding:8px 16px; font-size:13px;"
                f"font-weight:bold; border-radius:4px; }}")
            btn.clicked.connect(handler)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

    def _on_add(self):
        fid = self.edit_id.text().strip() or f"f{self.table.rowCount()+1:03d}"
        desc = self.edit_desc.text().strip()
        if not desc:
            QMessageBox.warning(self, "提示", "请填写伏笔描述")
            return
        ch = str(self.spin_chapter.value())
        kw = self.edit_keyword.text().strip()
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate([fid, desc, ch, "", kw, "🟢 未回收"]):
            item = QTableWidgetItem(v)
            if c == 5:
                item.setForeground(QColor("#27ae60"))
            self.table.setItem(r, c, item)
        self.edit_id.clear()
        self.edit_desc.clear()
        self.edit_keyword.clear()
        self.sync_to_mw()

    def _on_close(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.setItem(row, 5, QTableWidgetItem("✅ 已回收"))
        try:
            ch_count = len(self.mw.chapters) if self.mw else 0
            self.table.setItem(row, 3, QTableWidgetItem(str(ch_count)))
        except Exception:
            pass
        self.sync_to_mw()

    def _on_reopen(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = QTableWidgetItem("🟢 未回收")
        item.setForeground(QColor("#27ae60"))
        self.table.setItem(row, 5, item)
        self.sync_to_mw()

    def _on_delete(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.sync_to_mw()

    def _on_clear(self):
        if self.table.rowCount() == 0:
            return
        ret = QMessageBox.question(self, "确认",
            f"清空全部 {self.table.rowCount()} 条伏笔?")
        if ret == QMessageBox.Yes:
            self.table.setRowCount(0)
            self.sync_to_mw()

    def _on_check(self):
        """检查逾期伏笔"""
        try:
            ch_count = len(self.mw.chapters) if self.mw else 0
        except Exception:
            ch_count = 0
        warn_gap = self.spin_warn.value()
        critical_gap = self.spin_critical.value()
        overdue = []
        for r in range(self.table.rowCount()):
            status = self.table.item(r, 5)
            if status and "已回收" in status.text():
                continue
            ch_item = self.table.item(r, 2)
            try:
                added_ch = int(ch_item.text()) if ch_item else 0
            except ValueError:
                added_ch = 0
            gap = ch_count - added_ch
            desc_item = self.table.item(r, 1)
            desc = desc_item.text() if desc_item else "?"
            if gap >= critical_gap:
                overdue.append(f"🔴 严重! 第{added_ch}章埋下,已过{gap}章: {desc}")
                status_item = QTableWidgetItem(f"🔴 逾期{gap}章")
                status_item.setForeground(QColor("#e74c3c"))
                self.table.setItem(r, 5, status_item)
            elif gap >= warn_gap:
                overdue.append(f"🟡 预警! 第{added_ch}章埋下,已过{gap}章: {desc}")
                status_item = QTableWidgetItem(f"🟡 预警{gap}章")
                status_item.setForeground(QColor("#e67e22"))
                self.table.setItem(r, 5, status_item)
        if overdue:
            QMessageBox.warning(self, f"⚠ {len(overdue)} 条伏笔逾期",
                "\n\n".join(overdue[:10]))
        else:
            QMessageBox.information(self, "✅ 检查完成",
                f"当前已写 {ch_count} 章,所有伏笔正常!")

    def get_data(self):
        """导出数据"""
        rows = []
        for r in range(self.table.rowCount()):
            row = {}
            for c, key in enumerate(["id", "desc", "added_ch", "last_touch", "keyword", "status"]):
                item = self.table.item(r, c)
                row[key] = item.text() if item else ""
            rows.append(row)
        return {
            "enabled": self.chk_enabled.isChecked(),
            "warn_gap": self.spin_warn.value(),
            "critical_gap": self.spin_critical.value(),
            "items": rows,
        }

    def set_data(self, data):
        """导入数据"""
        if not data:
            return
        self.chk_enabled.setChecked(data.get("enabled", False))
        self.spin_warn.setValue(data.get("warn_gap", 80))
        self.spin_critical.setValue(data.get("critical_gap", 150))
        self.table.setRowCount(0)
        for row in data.get("items", []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, key in enumerate(["id", "desc", "added_ch", "last_touch", "keyword", "status"]):
                self.table.setItem(r, c, QTableWidgetItem(row.get(key, "")))

    def sync_to_mw(self):
        """同步数据到 mw.open_loops,供工作流管线使用"""
        if not self.mw:
            return
        loops = []
        for r in range(self.table.rowCount()):
            item = {}
            for c, key in enumerate(["id", "desc", "added_ch", "last_seen_ch", "keyword", "status"]):
                cell = self.table.item(r, c)
                item[key] = cell.text() if cell else ""
            # 转换状态
            status_text = item.get("status", "")
            if "已回收" in status_text or "closed" in status_text.lower():
                item["status"] = "closed"
            else:
                item["status"] = "open"
            # 转换章节号
            try:
                item["added_ch"] = int(item["added_ch"])
            except (ValueError, TypeError):
                item["added_ch"] = 0
            try:
                item["last_seen_ch"] = int(item["last_seen_ch"]) if item["last_seen_ch"] else item["added_ch"]
            except (ValueError, TypeError):
                item["last_seen_ch"] = item["added_ch"]
            loops.append(item)
        if not hasattr(self.mw, "open_loops") or self.mw.open_loops is None:
            self.mw.open_loops = {}
        self.mw.open_loops["enabled"] = self.chk_enabled.isChecked()
        self.mw.open_loops["warn_gap"] = self.spin_warn.value()
        self.mw.open_loops["critical_gap"] = self.spin_critical.value()
        self.mw.open_loops["loops"] = loops

    def sync_from_mw(self):
        """从 mw.open_loops 读取数据(启动时/加载项目时)"""
        if not self.mw:
            return
        cfg = getattr(self.mw, "open_loops", None)
        if not cfg:
            return
        self.chk_enabled.setChecked(cfg.get("enabled", False))
        self.spin_warn.setValue(int(cfg.get("warn_gap", 80)))
        self.spin_critical.setValue(int(cfg.get("critical_gap", 150)))
        self.table.setRowCount(0)
        for loop in cfg.get("loops", []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [
                str(loop.get("id", "")),
                str(loop.get("desc", "")),
                str(loop.get("added_ch", "")),
                str(loop.get("last_seen_ch", "")),
                str(loop.get("keyword", "")),
                "✅ 已回收" if loop.get("status") == "closed" else "🟢 未回收",
            ]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
