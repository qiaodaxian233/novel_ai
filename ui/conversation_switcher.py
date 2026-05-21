# -*- coding: utf-8 -*-
"""
ui/conversation_switcher.py - 对话槽管理器(E 模块,随时换对话自动同步记忆)

v2.02 P3 拆分:从 novel_ai.py 第 10106-10272 行整体搬运,内容零修改。
被 novel_ai.py 顶部 `from ui.conversation_switcher import ConversationSwitcher` 导入。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QInputDialog, QMessageBox, QCheckBox, QGroupBox,
)

class ConversationSwitcher(QWidget):
    """
    管理多个 AI 对话槽(会话 URL)。
    核心功能:
      · 保存当前 URL 为命名槽           → 📌 保存当前
      · 一键切换到另一个槽 + 同步记忆  → 🔄 切换 + 同步
      · 新开对话并注册                  → 🆕 新建槽
    槽数据持久化在项目 JSON 的 "conv_slots" 字段里。
    """

    # 当用户点"切换"时,发射 (url, sync_memory:bool)
    switch_requested = pyqtSignal(str, bool)
    # 当用户点"新建"时发射
    new_slot_requested = pyqtSignal(str)   # ai_site name

    def __init__(self):
        super().__init__()
        # 槽列表:每条 {"name", "url", "ai_site", "chapter_at", "created_at"}
        self.slots: list[dict] = []
        self._active_slot_idx: int = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        box = QGroupBox("对话槽管理 — 随时换对话,自动同步记忆")
        box.setStyleSheet(
            "QGroupBox { border: 2px solid #1a73e8; margin-top: 8px; }"
            "QGroupBox::title { color: #1a73e8; font-weight: bold; }"
        )
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        # 当前活跃对话
        active_row = QHBoxLayout()
        active_row.addWidget(QLabel("当前对话:"))
        self.active_label = QLabel("(未绑定槽)")
        self.active_label.setStyleSheet(
            "padding: 3px 8px; background: #e8f0fe; border-radius: 3px; "
            "color: #1a4480; font-weight: bold;")
        active_row.addWidget(self.active_label, 1)
        self.chk_sync = QCheckBox("切换时同步记忆")
        self.chk_sync.setChecked(True)
        self.chk_sync.setToolTip(
            "切换到新对话时,自动发送一条「记忆恢复」提示词,\n"
            "让新对话窗口了解书名/进度/角色/摘要/长期记忆,\n"
            "然后再继续生成。")
        active_row.addWidget(self.chk_sync)
        lay.addLayout(active_row)

        # 槽列表 + 操作列
        list_row = QHBoxLayout()

        self.slot_list = QListWidget()
        self.slot_list.setMaximumHeight(120)
        self.slot_list.setToolTip("双击直接切换到该对话槽")
        list_row.addWidget(self.slot_list, 1)

        btn_col = QVBoxLayout()
        self.btn_save_slot = QPushButton("📌 保存当前")
        self.btn_save_slot.setToolTip(
            "把当前 URL 框里的地址保存为一个命名槽\n"
            "(用于记录『章节上下文满了需要新开』的新对话)")
        self.btn_switch = QPushButton("🔄 切换")
        self.btn_switch.setToolTip("切换到选中槽 URL,并可选同步记忆")
        self.btn_switch.setStyleSheet(
            "QPushButton { background:#1a73e8; color:white; font-weight:bold; "
            "padding:5px 10px; border-radius:3px; }"
            "QPushButton:hover { background:#1557b0; }")
        self.btn_del_slot = QPushButton("🗑 删除")
        self.btn_del_slot.setToolTip("删除选中槽(不影响实际对话)")
        self.btn_new_slot = QPushButton("🆕 新建槽")
        self.btn_new_slot.setToolTip(
            "在浏览器里打开一个新的 AI 对话页面,\n"
            "完成新建后把 URL 填入上方再「保存当前」")
        for b in (self.btn_save_slot, self.btn_switch,
                  self.btn_del_slot, self.btn_new_slot):
            b.setMaximumWidth(90)
            btn_col.addWidget(b)
        btn_col.addStretch()
        list_row.addLayout(btn_col)
        lay.addLayout(list_row)

        # 内部信号连线
        self.btn_del_slot.clicked.connect(self._on_del)
        self.slot_list.itemDoubleClicked.connect(self._on_double_click)

        outer.addWidget(box)

    # ---- 数据操作 ----

    def add_slot(self, name: str, url: str, ai_site: str = "",
                 chapter_at: int = 0) -> int:
        """新增或更新(同名则更新 URL)。返回槽索引。"""
        for i, s in enumerate(self.slots):
            if s["name"] == name:
                s["url"] = url
                s["chapter_at"] = chapter_at
                s["ai_site"] = ai_site
                self._refresh_list()
                return i
        from datetime import datetime as _dt
        self.slots.append({
            "name": name, "url": url, "ai_site": ai_site,
            "chapter_at": chapter_at,
            "created_at": _dt.now().strftime("%m-%d %H:%M"),
        })
        self._refresh_list()
        return len(self.slots) - 1

    def set_active(self, idx: int):
        self._active_slot_idx = idx
        name = self.slots[idx]["name"] if 0 <= idx < len(self.slots) else "(未绑定槽)"
        self.active_label.setText(name)
        self._refresh_list()

    def get_selected_slot(self) -> dict | None:
        row = self.slot_list.currentRow()
        if 0 <= row < len(self.slots):
            return self.slots[row]
        return None

    def _refresh_list(self):
        self.slot_list.clear()
        for i, s in enumerate(self.slots):
            marker = "▶ " if i == self._active_slot_idx else "   "
            ch_hint = f" [ch{s['chapter_at']}]" if s.get("chapter_at") else ""
            item = QListWidgetItem(
                f"{marker}{s['name']}{ch_hint}  "
                f"({s.get('ai_site','') or '—'}  {s.get('created_at','')})"
            )
            item.setToolTip(s["url"])
            if i == self._active_slot_idx:
                item.setForeground(QColor("#1a73e8"))
            self.slot_list.addItem(item)

    def _on_del(self):
        row = self.slot_list.currentRow()
        if 0 <= row < len(self.slots):
            self.slots.pop(row)
            if self._active_slot_idx == row:
                self._active_slot_idx = -1
                self.active_label.setText("(未绑定槽)")
            self._refresh_list()

    def _on_double_click(self, item):
        """双击 = 切换"""
        self.btn_switch.click()

    # ---- 序列化 ----

    def serialize_for_save(self) -> dict:
        return {
            "slots": self.slots,
            "active_idx": self._active_slot_idx,
        }

    def load_from_dict(self, d: dict):
        if not isinstance(d, dict):
            return
        self.slots = d.get("slots", [])
        self._active_slot_idx = d.get("active_idx", -1)
        name = (self.slots[self._active_slot_idx]["name"]
                if 0 <= self._active_slot_idx < len(self.slots)
                else "(未绑定槽)")
        self.active_label.setText(name)
        self._refresh_list()
