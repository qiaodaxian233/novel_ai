# -*- coding: utf-8 -*-
"""ui/tabs/canon_guard.py - Canon 锁(设定守护)Tab(213 行)

v2.03 P4 拆分:从 novel_ai.py 第 6608-6820 行整体搬运,内容零修改。
"""
import re
from datetime import datetime

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)


class CanonGuard(QWidget):
    """B 模块:核心设定守护
    维护一个 Canon 表(锁定项 / 演化项),写章节前注入硬约束,
    写完后跑稽核 prompt 检测违反。"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Canon 设定守护 — 防止写到 N 章设定崩塌")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a4480;")
        layout.addWidget(title)

        intro = QLabel(
            "在这里维护一个【核心设定档】。写每一章前会自动作为硬约束注入提示词,"
            "写完后会自动稽核是否违反。\n"
            "  · 锁定项:绝对不可变(年龄、关键物品归属、女主双重身份等)\n"
            "  · 演化项:可随情节推进改变(修为、关系、心境)")
        intro.setStyleSheet("color: #555; padding: 6px 0;")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # 开关行 — 加 QSettings 持久化
        from PyQt5.QtCore import QSettings as _QS_canon
        _cs = _QS_canon("NovelAI", "CanonTab")
        crow = QHBoxLayout()
        self.chk_inject = QCheckBox("写章节前自动注入 Canon 约束")
        self.chk_inject.setChecked(_cs.value("inject", True, type=bool))
        self.chk_audit = QCheckBox("写完后自动稽核(高严重度违反 → 触发死磕重写)")
        self.chk_audit.setChecked(_cs.value("audit", True, type=bool))
        self.chk_extract = QCheckBox("写完后自动从章节抽取新 Canon")
        self.chk_extract.setChecked(_cs.value("extract", True, type=bool))
        # 实时写入
        self.chk_inject.stateChanged.connect(
            lambda v: _QS_canon("NovelAI", "CanonTab").setValue("inject", bool(v)))
        self.chk_audit.stateChanged.connect(
            lambda v: _QS_canon("NovelAI", "CanonTab").setValue("audit", bool(v)))
        self.chk_extract.stateChanged.connect(
            lambda v: _QS_canon("NovelAI", "CanonTab").setValue("extract", bool(v)))
        crow.addWidget(self.chk_inject); crow.addWidget(self.chk_audit)
        crow.addWidget(self.chk_extract); crow.addStretch()
        layout.addLayout(crow)
        
        # v1.75:自动抽取可见性 label — 每次自动抽取后更新,让用户不用翻日志就能确认
        self.lbl_last_extract = QLabel("📌 自动抽取状态:尚未运行(写完下一章后查看)")
        self.lbl_last_extract.setStyleSheet(
            "color: #8fa3c4; font-size: 11px; padding: 4px 6px; "
            "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
        layout.addWidget(self.lbl_last_extract)

        # Canon 文本编辑区(简单方便,JSON 内部表达,UI 是结构化文本)
        # 行格式:[L|E][severity:H/M/L] key = value (chN)
        # 例:  [L][H] 林晚晚.身份 = 豪门夫人 + 夜市烤串摊主 (ch1)
        gbox = QGroupBox("Canon 设定档(锁定项 + 演化项)")
        glay = QVBoxLayout(gbox)

        legend = QLabel(
            "格式:[L 锁定 / E 演化][H 高 / M 中 / L 低] 键 = 值 (chN)\n"
            "示例:[L][H] 林晚晚.年龄 = 25 (ch1)\n"
            "      [E][M] 顾砚深.修为 = 金丹中期 (ch7)")
        legend.setStyleSheet("color: #8fa3c4; font-size: 11px;")
        glay.addWidget(legend)

        self.canon_edit = QPlainTextEdit()
        self.canon_edit.setPlaceholderText(
            "[L][H] 女主双重身份 = 未被识破 (ch1)\n"
            "[L][H] 玉佩 = 男主祖母传给男主 (ch3)\n"
            "[E][M] 顾砚深.心境 = 从嫌弃到真香 (ch6)")
        self.canon_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 13px;")
        glay.addWidget(self.canon_edit, 1)

        btn_row = QHBoxLayout()
        self.btn_extract_now = QPushButton("✨ 从已有章节自动抽取 Canon")
        self.btn_extract_now.setStyleSheet(
            "background:#3d6fd4;color:white;padding:6px 12px;font-weight:bold;border-radius:3px;")
        self.btn_clear = QPushButton("清空")
        self.btn_dedupe = QPushButton("去重 + 排序")
        btn_row.addWidget(self.btn_extract_now); btn_row.addWidget(self.btn_dedupe)
        btn_row.addWidget(self.btn_clear); btn_row.addStretch()
        glay.addLayout(btn_row)

        layout.addWidget(gbox, 1)

        # 稽核日志区
        log_box = QGroupBox("最近稽核日志(违反记录)")
        ll = QVBoxLayout(log_box)
        self.audit_log = QPlainTextEdit()
        self.audit_log.setReadOnly(True)
        self.audit_log.setMaximumHeight(120)
        self.audit_log.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; background: #fff7f0;")
        ll.addWidget(self.audit_log)
        layout.addWidget(log_box)

        # 按钮事件
        self.btn_clear.clicked.connect(self.canon_edit.clear)
        self.btn_dedupe.clicked.connect(self._dedupe)

    # ---------- 解析 / 序列化 ----------
    _LINE_RE = re.compile(
        r'^\s*\[([LE])\]\[([HML])\]\s*(.+?)\s*=\s*(.+?)\s*(?:\(ch(\d+)\))?\s*$',
        re.IGNORECASE)

    def parse(self):
        """解析为 [{key, value, mode, severity, ch}, ...]"""
        items = []
        for line in self.canon_edit.toPlainText().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = self._LINE_RE.match(line)
            if not m:
                continue
            mode_c, sev_c, key, value, ch = m.groups()
            items.append({
                "key": key.strip(),
                "value": value.strip(),
                "mode": "locked" if mode_c.upper() == "L" else "evolving",
                "severity": {"H": "high", "M": "mid", "L": "low"}[sev_c.upper()],
                "ch": int(ch) if ch else None,
            })
        return items

    def serialize_locked(self):
        """生成给 prompt 注入用的锁定项文本"""
        items = [it for it in self.parse() if it["mode"] == "locked"]
        if not items:
            return "(暂无锁定项)"
        return "\n".join(
            f"- [{it['severity']}] {it['key']}:{it['value']}"
            + (f"(ch{it['ch']})" if it['ch'] else "")
            for it in items)

    def serialize_evolving(self):
        items = [it for it in self.parse() if it["mode"] == "evolving"]
        if not items:
            return "(暂无演化项)"
        return "\n".join(
            f"- {it['key']}:{it['value']}"
            + (f"(ch{it['ch']})" if it['ch'] else "")
            for it in items)

    def serialize_for_save(self):
        """存盘用 dict"""
        return {
            "items": self.parse(),
            "raw_text": self.canon_edit.toPlainText(),
            "inject": self.chk_inject.isChecked(),
            "audit": self.chk_audit.isChecked(),
            "extract": self.chk_extract.isChecked(),
        }

    def load_from_dict(self, d):
        if not isinstance(d, dict):
            return
        if d.get("raw_text"):
            self.canon_edit.setPlainText(d["raw_text"])
        elif d.get("items"):
            # 从结构化反序列化为文本
            self.canon_edit.setPlainText(self._items_to_text(d["items"]))
        self.chk_inject.setChecked(d.get("inject", True))
        self.chk_audit.setChecked(d.get("audit", True))
        self.chk_extract.setChecked(d.get("extract", True))

    @staticmethod
    def _items_to_text(items):
        out = []
        for it in items:
            mode_c = "L" if it.get("mode") == "locked" else "E"
            sev_c = {"high": "H", "mid": "M", "low": "L"}.get(it.get("severity"), "M")
            ch = f" (ch{it['ch']})" if it.get("ch") else ""
            out.append(f"[{mode_c}][{sev_c}] {it['key']} = {it['value']}{ch}")
        return "\n".join(out)

    def add_item(self, key, value, mode="locked", severity="mid", ch=None):
        """添加一条(供自动抽取调用),自动去重"""
        items = self.parse()
        # key 相同 → 更新
        for it in items:
            if it["key"] == key:
                it["value"] = value
                it["mode"] = mode
                it["severity"] = severity
                if ch:
                    it["ch"] = ch
                self.canon_edit.setPlainText(self._items_to_text(items))
                return
        # 新增
        items.append({"key": key, "value": value, "mode": mode,
                      "severity": severity, "ch": ch})
        self.canon_edit.setPlainText(self._items_to_text(items))

    def _dedupe(self):
        """按 key 去重 + 锁定项在前 + 高严重度在前"""
        items = self.parse()
        seen = {}
        for it in items:
            k = it["key"]
            if k not in seen or it.get("ch") is not None:
                seen[k] = it
        items = list(seen.values())
        items.sort(key=lambda x: (
            0 if x["mode"] == "locked" else 1,
            {"high": 0, "mid": 1, "low": 2}.get(x["severity"], 3),
            x["key"]))
        self.canon_edit.setPlainText(self._items_to_text(items))

    def add_audit_log(self, ch_num, severity, desc):
        ts = datetime.now().strftime("%H:%M:%S")
        sev_icon = {"high": "🔴", "mid": "🟡", "low": "🟢"}.get(severity, "·")
        self.audit_log.appendPlainText(
            f"[{ts}] {sev_icon} ch{ch_num}({severity}): {desc}")
