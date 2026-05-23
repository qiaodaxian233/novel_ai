# -*- coding: utf-8 -*-
"""
LifespanLoopsPanel — 寿元台账 + 长期伏笔检查 的 UI 面板
========================================================

提供一个可作为独立 Tab 嵌入到 NovelAI MainWindow 的 QWidget。
设计风格对齐既有的 CanonGuard / SkillLibrary：
  - 顶部标题 + 灰色简介
  - 两个 GroupBox（寿元台账 / 长期伏笔检查）
  - 主蓝按钮 #1a73e8 用于"保存配置"主动作

数据流:
  panel.sync_from_mw()   ← UI 从 mw.lifespan_ledger / mw.open_loops 拉
  panel.sync_to_mw()     → UI 数据写回 mw.lifespan_ledger / mw.open_loops
  panel.refresh_status() — 仅刷新右上角"当前状态"显示（自动入账后调用）

依赖:
  - 同包模块 lifespan_loops_steps（提供 LifespanLoopsExtension 的 add_loop / close_loop / reset_lifespan）
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QMessageBox,
)

from lifespan_loops_steps import (
    DEFAULT_LIFESPAN_LEDGER, DEFAULT_OPEN_LOOPS_CFG,
    LifespanLoopsExtension,
)

# 主题色 / 字体规范，跟 CanonGuard 对齐
TITLE_STYLE = "font-size: 16px; font-weight: bold; color: #1a4480;"
INTRO_STYLE = "color: #555; padding: 6px 0;"
HINT_STYLE = "color: #888; font-size: 11px;"
PRIMARY_BTN = (
    "background:#1a73e8;color:white;padding:6px 14px;"
    "font-weight:bold;border-radius:3px;"
)
DANGER_BTN = (
    "background:#d93025;color:white;padding:6px 12px;"
    "font-weight:bold;border-radius:3px;"
)
STATUS_OK = "color:#137333;font-weight:bold;"
STATUS_WARN = "color:#e37400;font-weight:bold;"
STATUS_CRIT = "color:#d93025;font-weight:bold;"


class LifespanLoopsPanel(QWidget):
    """寿元台账 + 长期伏笔检查 UI（独立 Tab）"""

    # 用户要求 MainWindow 应执行某动作时发的信号
    request_log = pyqtSignal(str, str)  # (msg, level)
    request_save = pyqtSignal()         # 用户点保存配置

    def __init__(self, mw=None, parent=None):
        super().__init__(parent)
        self.mw = mw

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("寿元台账 — 修仙连载约束")
        title.setStyleSheet(TITLE_STYLE)
        layout.addWidget(title)

        intro = QLabel(
            "针对修仙 / 倒计时型连载的硬约束：\n"
            "  · 寿元台账：每章自动累加折寿，注入下一章 prompt，剩余触底自动告警。\n"
            "  · 长期伏笔检查已移到独立Tab「🪤 伏笔检查」。\n"
            "  默认全关，对普通项目零感知；开启后请记得【保存配置】并保存项目。"
        )
        intro.setStyleSheet(INTRO_STYLE)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ---- 寿元台账 ----
        layout.addWidget(self._build_lifespan_box())
        layout.addStretch(1)

        # 保存
        save_row = QHBoxLayout()
        self.btn_save_all = QPushButton("💾 保存配置（写回到内存）")
        self.btn_save_all.setStyleSheet(PRIMARY_BTN)
        self.btn_save_all.clicked.connect(self._on_save_all_clicked)
        save_row.addStretch()
        save_row.addWidget(self.btn_save_all)
        layout.addLayout(save_row)

        if self.mw is not None:
            self.sync_from_mw()

    # ============================================================
    # GroupBox 构建
    # ============================================================
    def _build_lifespan_box(self) -> QGroupBox:
        gbox = QGroupBox("寿元台账")
        outer = QVBoxLayout(gbox)

        # 第一行：启用 + 自动入账
        crow = QHBoxLayout()
        self.chk_lifespan_on = QCheckBox("启用寿元台账（注入 prompt + POST_WRITE 入账）")
        self.chk_lifespan_on.setChecked(False)
        self.chk_auto_audit = QCheckBox("章末无 [寿元结算] 标记时调 AI 自动入账")
        self.chk_auto_audit.setChecked(True)
        crow.addWidget(self.chk_lifespan_on)
        crow.addWidget(self.chk_auto_audit)
        crow.addStretch()
        outer.addLayout(crow)

        # 第二行：参数
        form = QFormLayout()
        self.spin_total_days = QSpinBox()
        self.spin_total_days.setRange(30, 1_000_000)
        self.spin_total_days.setValue(8760)
        self.spin_total_days.setSuffix("  日")
        self.lbl_total_days_hint = QLabel("(8760 日 ≈ 24 年)")
        self.lbl_total_days_hint.setStyleSheet(HINT_STYLE)
        self.spin_total_days.valueChanged.connect(self._refresh_total_hint)

        days_row = QHBoxLayout()
        days_row.addWidget(self.spin_total_days)
        days_row.addWidget(self.lbl_total_days_hint)
        days_row.addStretch()
        form.addRow("起始寿元：", days_row)

        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(1, 10_000)
        self.spin_warn.setValue(365)
        self.spin_warn.setSuffix("  日")
        form.addRow("⚠️ 警戒阈值：", self.spin_warn)

        self.spin_critical = QSpinBox()
        self.spin_critical.setRange(1, 10_000)
        self.spin_critical.setValue(30)
        self.spin_critical.setSuffix("  日")
        form.addRow("🚨 危急阈值：", self.spin_critical)

        self.spin_default_per = QSpinBox()
        self.spin_default_per.setRange(0, 30)
        self.spin_default_per.setValue(1)
        self.spin_default_per.setSuffix("  日 / 章")
        form.addRow("兜底每章折寿：", self.spin_default_per)

        outer.addLayout(form)

        # 第三行：当前状态（只读）
        status_box = QGroupBox("当前状态")
        st_grid = QGridLayout(status_box)
        self.lbl_used = QLabel("0")
        self.lbl_used.setStyleSheet("font-family:Consolas;font-size:14px;")
        self.lbl_remaining = QLabel("0")
        self.lbl_remaining.setStyleSheet("font-family:Consolas;font-size:14px;")
        self.lbl_status_tag = QLabel("✅ 正常")
        self.lbl_status_tag.setStyleSheet(STATUS_OK)
        self.lbl_history_count = QLabel("0 条")

        st_grid.addWidget(QLabel("已折寿："), 0, 0)
        st_grid.addWidget(self.lbl_used, 0, 1)
        st_grid.addWidget(QLabel("剩余："), 0, 2)
        st_grid.addWidget(self.lbl_remaining, 0, 3)
        st_grid.addWidget(QLabel("状态："), 1, 0)
        st_grid.addWidget(self.lbl_status_tag, 1, 1)
        st_grid.addWidget(QLabel("入账记录："), 1, 2)
        st_grid.addWidget(self.lbl_history_count, 1, 3)
        outer.addWidget(status_box)

        # 第四行：操作按钮
        op_row = QHBoxLayout()
        self.btn_reset_lifespan = QPushButton("🔄 重置台账（清零已折寿）")
        self.btn_reset_lifespan.setStyleSheet(DANGER_BTN)
        self.btn_reset_lifespan.clicked.connect(self._on_reset_lifespan)
        self.btn_show_history = QPushButton("📊 查看入账历史")
        self.btn_show_history.clicked.connect(self._on_show_history)
        op_row.addWidget(self.btn_reset_lifespan)
        op_row.addWidget(self.btn_show_history)
        op_row.addStretch()
        outer.addLayout(op_row)

        return gbox

    def _build_loops_box(self) -> QGroupBox:
        gbox = QGroupBox("长期伏笔检查")
        outer = QVBoxLayout(gbox)

        crow = QHBoxLayout()
        self.chk_loops_on = QCheckBox("启用伏笔检查")
        self.chk_loops_on.setChecked(False)
        crow.addWidget(self.chk_loops_on)

        self.spin_warn_gap = QSpinBox()
        self.spin_warn_gap.setRange(5, 1000)
        self.spin_warn_gap.setValue(80)
        self.spin_warn_gap.setSuffix(" 章")
        self.spin_critical_gap = QSpinBox()
        self.spin_critical_gap.setRange(10, 2000)
        self.spin_critical_gap.setValue(150)
        self.spin_critical_gap.setSuffix(" 章")
        crow.addWidget(QLabel("  warn 阈值："))
        crow.addWidget(self.spin_warn_gap)
        crow.addWidget(QLabel("  critical 阈值："))
        crow.addWidget(self.spin_critical_gap)
        crow.addStretch()
        outer.addLayout(crow)

        # 列表
        self.tbl_loops = QTableWidget(0, 6)
        self.tbl_loops.setHorizontalHeaderLabels(
            ["ID", "描述", "抛章", "最近触及", "关键词", "状态"]
        )
        self.tbl_loops.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_loops.horizontalHeader().setStretchLastSection(False)
        # 让"描述"列拉伸
        self.tbl_loops.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_loops.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_loops.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_loops.setSelectionMode(QTableWidget.SingleSelection)
        outer.addWidget(self.tbl_loops, 1)

        # 编辑行
        edit_grid = QGridLayout()
        self.edit_loop_id = QLineEdit()
        self.edit_loop_id.setPlaceholderText("f001")
        self.edit_loop_desc = QLineEdit()
        self.edit_loop_desc.setPlaceholderText("妹妹咒斑来源")
        self.spin_loop_added = QSpinBox()
        self.spin_loop_added.setRange(1, 99999)
        self.spin_loop_added.setValue(1)
        self.spin_loop_added.setPrefix("第 ")
        self.spin_loop_added.setSuffix(" 章")
        self.edit_loop_kw = QLineEdit()
        self.edit_loop_kw.setPlaceholderText("咒斑")
        edit_grid.addWidget(QLabel("ID："), 0, 0)
        edit_grid.addWidget(self.edit_loop_id, 0, 1)
        edit_grid.addWidget(QLabel("描述："), 0, 2)
        edit_grid.addWidget(self.edit_loop_desc, 0, 3)
        edit_grid.addWidget(QLabel("抛出章号："), 1, 0)
        edit_grid.addWidget(self.spin_loop_added, 1, 1)
        edit_grid.addWidget(QLabel("关键词（可选）："), 1, 2)
        edit_grid.addWidget(self.edit_loop_kw, 1, 3)
        outer.addLayout(edit_grid)

        # 按钮行
        btn_row = QHBoxLayout()
        self.btn_loop_add = QPushButton("➕ 添加")
        self.btn_loop_add.setStyleSheet(PRIMARY_BTN)
        self.btn_loop_add.clicked.connect(self._on_loop_add)
        self.btn_loop_close = QPushButton("✓ 标记已回收")
        self.btn_loop_close.clicked.connect(self._on_loop_close)
        self.btn_loop_reopen = QPushButton("↺ 重开")
        self.btn_loop_reopen.clicked.connect(self._on_loop_reopen)
        self.btn_loop_del = QPushButton("🗑 删除")
        self.btn_loop_del.clicked.connect(self._on_loop_delete)
        btn_row.addWidget(self.btn_loop_add)
        btn_row.addWidget(self.btn_loop_close)
        btn_row.addWidget(self.btn_loop_reopen)
        btn_row.addWidget(self.btn_loop_del)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        return gbox

    # ============================================================
    # 数据双向同步
    # ============================================================
    def sync_from_mw(self):
        """从 mw.lifespan_ledger / mw.open_loops 拉数据到 UI。"""
        if self.mw is None:
            return
        # 寿元
        led = getattr(self.mw, "lifespan_ledger", None) \
              or dict(DEFAULT_LIFESPAN_LEDGER)
        self.chk_lifespan_on.setChecked(bool(led.get("enabled", False)))
        self.chk_auto_audit.setChecked(bool(led.get("auto_audit", True)))
        self.spin_total_days.setValue(int(led.get("total_days", 8760)))
        self.spin_warn.setValue(int(led.get("warn_threshold", 365)))
        self.spin_critical.setValue(int(led.get("critical_threshold", 30)))
        self.spin_default_per.setValue(int(led.get("default_per_chapter", 1)))
        self._refresh_total_hint()
        self.refresh_status()

        # 伏笔(已移到独立Tab,这里跳过)
        if hasattr(self, 'chk_loops_on'):
            cfg = getattr(self.mw, "open_loops", None) \
                  or dict(DEFAULT_OPEN_LOOPS_CFG)
            self.chk_loops_on.setChecked(bool(cfg.get("enabled", False)))
            self.spin_warn_gap.setValue(int(cfg.get("warn_gap", 80)))
            self.spin_critical_gap.setValue(int(cfg.get("critical_gap", 150)))
            self._refresh_loops_table()

    def sync_to_mw(self):
        """从 UI 把数据写回 mw.lifespan_ledger / mw.open_loops。

        注意：表格里的 loops 是直接操作 mw.open_loops["loops"]，无需在这里同步。
        """
        if self.mw is None:
            return
        # 确保字典存在
        if not getattr(self.mw, "lifespan_ledger", None):
            from copy import deepcopy
            self.mw.lifespan_ledger = deepcopy(DEFAULT_LIFESPAN_LEDGER)
        if not getattr(self.mw, "open_loops", None):
            from copy import deepcopy
            self.mw.open_loops = deepcopy(DEFAULT_OPEN_LOOPS_CFG)

        led = self.mw.lifespan_ledger
        led["enabled"] = self.chk_lifespan_on.isChecked()
        led["auto_audit"] = self.chk_auto_audit.isChecked()
        led["total_days"] = self.spin_total_days.value()
        led["warn_threshold"] = self.spin_warn.value()
        led["critical_threshold"] = self.spin_critical.value()
        led["default_per_chapter"] = self.spin_default_per.value()

        if hasattr(self, 'chk_loops_on'):
            cfg = self.mw.open_loops
            cfg["enabled"] = self.chk_loops_on.isChecked()
            cfg["warn_gap"] = self.spin_warn_gap.value()
            cfg["critical_gap"] = self.spin_critical_gap.value()

    def refresh_status(self):
        """刷新"当前状态"显示。"""
        if self.mw is None:
            return
        led = getattr(self.mw, "lifespan_ledger", None) \
              or dict(DEFAULT_LIFESPAN_LEDGER)
        total = int(led.get("total_days", 8760))
        used = int(led.get("used_days", 0))
        remaining = max(0, total - used)
        warn = int(led.get("warn_threshold", 365))
        critical = int(led.get("critical_threshold", 30))

        self.lbl_used.setText(f"{used} 日")
        years = remaining // 365
        days = remaining % 365
        self.lbl_remaining.setText(f"{remaining} 日（约 {years} 年 {days} 日）")

        if remaining <= critical:
            self.lbl_status_tag.setText("🚨 危急")
            self.lbl_status_tag.setStyleSheet(STATUS_CRIT)
        elif remaining <= warn:
            self.lbl_status_tag.setText("⚠️ 警戒")
            self.lbl_status_tag.setStyleSheet(STATUS_WARN)
        else:
            self.lbl_status_tag.setText("✅ 正常")
            self.lbl_status_tag.setStyleSheet(STATUS_OK)

        history = led.get("history") or []
        self.lbl_history_count.setText(f"{len(history)} 条")

    # ============================================================
    # 内部辅助
    # ============================================================
    def _refresh_total_hint(self):
        n = self.spin_total_days.value()
        years = n // 365
        days = n % 365
        if days == 0:
            txt = f"({n} 日 ≈ {years} 年)"
        else:
            txt = f"({n} 日 ≈ {years} 年 {days} 日)"
        self.lbl_total_days_hint.setText(txt)

    def _refresh_loops_table(self):
        if self.mw is None:
            return
        cfg = getattr(self.mw, "open_loops", None) or {}
        loops = cfg.get("loops") or []
        self.tbl_loops.setRowCount(len(loops))
        for r, loop in enumerate(loops):
            for c, key, default in [
                (0, "id", ""),
                (1, "desc", ""),
                (2, "added_ch", 0),
                (3, "last_seen_ch", 0),
                (4, "keyword", ""),
                (5, "status", "open"),
            ]:
                v = loop.get(key, default)
                item = QTableWidgetItem(str(v))
                if c == 5:
                    if v == "closed":
                        item.setForeground(Qt.darkGray)
                    else:
                        item.setForeground(Qt.darkGreen)
                self.tbl_loops.setItem(r, c, item)

    def _selected_loop_index(self) -> int:
        rows = self.tbl_loops.selectionModel().selectedRows()
        if not rows:
            return -1
        return rows[0].row()

    def _selected_loop_id(self) -> Optional[str]:
        i = self._selected_loop_index()
        if i < 0:
            return None
        item = self.tbl_loops.item(i, 0)
        return item.text() if item else None

    def _emit_log(self, msg: str, level: str = "info"):
        # 优先发信号；如果 MainWindow 没接，但有 tab_generation.log，用 fallback
        self.request_log.emit(msg, level)
        try:
            tab = getattr(self.mw, "tab_generation", None)
            if tab is not None and hasattr(tab, "log"):
                tab.log(msg, level)
        except Exception:
            pass

    # ============================================================
    # 槽函数（按钮回调）
    # ============================================================
    def _on_save_all_clicked(self):
        self.sync_to_mw()
        self.refresh_status()
        self._emit_log("✓ 寿元/伏笔配置已保存到内存（请保存项目以持久化）", "success")
        self.request_save.emit()

    def _on_reset_lifespan(self):
        if self.mw is None:
            return
        # 二次确认
        reply = QMessageBox.question(
            self, "重置寿元台账",
            f"将清零已折寿、清空入账历史，并把起始寿元设为 "
            f"{self.spin_total_days.value()} 日。是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        LifespanLoopsExtension.reset_lifespan(
            self.mw, total_days=self.spin_total_days.value()
        )
        self.refresh_status()
        self._emit_log(
            f"🔄 寿元台账已重置：起始 {self.spin_total_days.value()} 日",
            "info",
        )

    def _on_show_history(self):
        if self.mw is None:
            return
        led = getattr(self.mw, "lifespan_ledger", None) or {}
        history = led.get("history") or []
        if not history:
            QMessageBox.information(self, "入账历史", "（空）")
            return
        # 简易展示：最近 30 条
        lines = []
        for rec in history[-30:]:
            lines.append(
                f"第{rec.get('ch','?')}章: -{rec.get('days',0)} 日"
                f"   ({rec.get('note','')})"
            )
        text = "\n".join(lines)
        QMessageBox.information(
            self, f"入账历史（最近 {min(30,len(history))} 条 / 共 {len(history)} 条）",
            text,
        )

    def _on_loop_add(self):
        loop_id = self.edit_loop_id.text().strip()
        desc = self.edit_loop_desc.text().strip()
        added = int(self.spin_loop_added.value())
        kw = self.edit_loop_kw.text().strip()
        if not loop_id or not desc:
            QMessageBox.warning(self, "缺字段", "ID 和描述都不能为空")
            return
        # 重 ID 检测
        cfg = getattr(self.mw, "open_loops", None) or {}
        for loop in cfg.get("loops") or []:
            if loop.get("id") == loop_id:
                QMessageBox.warning(self, "ID 已存在", f"伏笔 ID「{loop_id}」已存在")
                return
        LifespanLoopsExtension.add_loop(
            self.mw, loop_id=loop_id, desc=desc, added_ch=added, keyword=kw,
        )
        self._refresh_loops_table()
        self.edit_loop_id.clear()
        self.edit_loop_desc.clear()
        self.edit_loop_kw.clear()
        self._emit_log(f"➕ 新增伏笔：{loop_id} — {desc}", "info")

    def _on_loop_close(self):
        lid = self._selected_loop_id()
        if not lid:
            QMessageBox.information(self, "提示", "请先在表格里选中一行")
            return
        # 当前章号：尝试从 mw.chapters 推断；推断不出来用 0
        ch = 0
        try:
            if hasattr(self.mw, "chapters") and self.mw.chapters:
                ch = len(self.mw.chapters)
        except Exception:
            pass
        ok = LifespanLoopsExtension.close_loop(self.mw, lid, ch_num=ch)
        if ok:
            self._refresh_loops_table()
            self._emit_log(f"✓ 伏笔 {lid} 标记为已回收（在第 {ch} 章）", "success")

    def _on_loop_reopen(self):
        lid = self._selected_loop_id()
        if not lid:
            QMessageBox.information(self, "提示", "请先在表格里选中一行")
            return
        cfg = getattr(self.mw, "open_loops", None) or {}
        for loop in cfg.get("loops") or []:
            if loop.get("id") == lid:
                loop["status"] = "open"
                self._refresh_loops_table()
                self._emit_log(f"↺ 伏笔 {lid} 已重开", "info")
                return

    def _on_loop_delete(self):
        lid = self._selected_loop_id()
        if not lid:
            QMessageBox.information(self, "提示", "请先在表格里选中一行")
            return
        cfg = getattr(self.mw, "open_loops", None)
        if not cfg or not cfg.get("loops"):
            return
        reply = QMessageBox.question(
            self, "删除伏笔",
            f"确认删除伏笔「{lid}」？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        cfg["loops"] = [l for l in cfg["loops"] if l.get("id") != lid]
        self._refresh_loops_table()
        self._emit_log(f"🗑 伏笔 {lid} 已删除", "warn")

    # ============================================================
    # 测试 / 调试便捷接口
    # ============================================================
    def serialize_for_save(self) -> dict:
        """跟 CanonGuard / SkillLibrary 的 serialize_for_save 同名同形。"""
        self.sync_to_mw()
        return LifespanLoopsExtension.serialize(self.mw) if self.mw else {}

    def load_from_dict(self, d: dict):
        if self.mw is None or not d:
            return
        LifespanLoopsExtension.deserialize(self.mw, d)
        self.sync_from_mw()


__all__ = ["LifespanLoopsPanel"]
