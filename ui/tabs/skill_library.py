# -*- coding: utf-8 -*-
"""ui/tabs/skill_library.py - 写作技能库 Tab(242 行)

v2.03 P4 拆分:从 novel_ai.py 第 6823-7064 行整体搬运,内容零修改。
"""
import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from core.default_skills import DEFAULT_SKILLS


class SkillLibrary(QWidget):
    """D 模块:技能库 — 可配置的提示词模板 + 触发条件"""

    def __init__(self):
        super().__init__()
        self.skills = [dict(s) for s in DEFAULT_SKILLS]  # 副本
        self._current_idx = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("技能库 — 自定义专用提示词 + 触发条件")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a4480;")
        layout.addWidget(title)

        intro = QLabel(
            "把常用提示词做成可复用技能。触发方式:\n"
            "  · 手动:章节编辑器右键菜单调用,或下方「测试运行」\n"
            "  · 章节生成后自动:每章生成后自动跑(目标 = log_only 时不污染章节)")
        intro.setStyleSheet("color: #555; padding: 6px 0;")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # 主体:左侧列表 + 右侧编辑
        splitter = QSplitter(Qt.Horizontal)

        # 左侧
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("技能列表"))
        self.list_widget = QListWidget()
        ll.addWidget(self.list_widget, 1)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("➕ 新增")
        self.btn_del = QPushButton("🗑 删除")
        self.btn_dup = QPushButton("⎘ 复制")
        btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_dup)
        btn_row.addWidget(self.btn_del)
        ll.addLayout(btn_row)
        splitter.addWidget(left)

        # 右侧编辑区
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        form = QGridLayout()
        form.addWidget(QLabel("名称:"), 0, 0)
        self.name_edit = QLineEdit()
        form.addWidget(self.name_edit, 0, 1, 1, 3)

        form.addWidget(QLabel("启用:"), 1, 0)
        self.chk_enabled = QCheckBox("启用此技能")
        form.addWidget(self.chk_enabled, 1, 1)
        form.addWidget(QLabel("触发:"), 1, 2)
        self.when_combo = QComboBox()
        self.when_combo.addItems([
            "manual (手动右键调用)",
            "after_chapter_generation (每章生成后自动)",
            "auto_match (匹配触发词时自动)",
        ])
        form.addWidget(self.when_combo, 1, 3)

        form.addWidget(QLabel("触发词:"), 2, 0)
        self.trigger_edit = QLineEdit()
        self.trigger_edit.setPlaceholderText(
            "仅 auto_match 用,正则,例如:战斗|交手|出招")
        form.addWidget(self.trigger_edit, 2, 1, 1, 3)

        form.addWidget(QLabel("目标:"), 3, 0)
        self.target_combo = QComboBox()
        self.target_combo.addItems([
            "current_chapter (替换当前章节正文)",
            "selected_text (替换选中文本)",
            "log_only (只输出到日志,不写回)",
            "append_to_canon (尝试追加到 Canon)",
        ])
        form.addWidget(self.target_combo, 3, 1, 1, 3)

        rl.addLayout(form)

        rl.addWidget(QLabel("提示词模板(可用 {content} 占位):"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(
            "请把下面段落扩写到 2000 字以上...\n\n原文:\n{content}\n\n"
            "请直接输出修改后的完整版本。")
        rl.addWidget(self.prompt_edit, 1)

        save_row = QHBoxLayout()
        self.btn_save = QPushButton("💾 保存当前修改")
        self.btn_save.setStyleSheet(
            "background:#1a73e8;color:white;padding:6px 14px;font-weight:bold;border-radius:3px;")
        self.btn_test = QPushButton("🧪 测试运行(对当前章节)")
        self.btn_reset = QPushButton("恢复出厂技能")
        save_row.addWidget(self.btn_save); save_row.addWidget(self.btn_test)
        save_row.addStretch(); save_row.addWidget(self.btn_reset)
        rl.addLayout(save_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        # 事件
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_del.clicked.connect(self._on_del)
        self.btn_dup.clicked.connect(self._on_dup)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_reset.clicked.connect(self._on_reset)
        # btn_test 由 MainWindow 接管(需要访问当前章节文本)

        self._refresh_list()
        if self.skills:
            self.list_widget.setCurrentRow(0)

    # ---------- 列表渲染 ----------
    def _refresh_list(self):
        self.list_widget.clear()
        for s in self.skills:
            mark = "✅" if s.get("enabled") else "⬜"
            when = s.get("when", "manual").split("(")[0].strip()
            self.list_widget.addItem(f"{mark} {s['name']}  ({when})")

    def _on_select(self, idx):
        if idx < 0 or idx >= len(self.skills):
            self._current_idx = -1
            return
        s = self.skills[idx]
        self._current_idx = idx
        self.name_edit.setText(s.get("name", ""))
        self.chk_enabled.setChecked(s.get("enabled", True))
        when = s.get("when", "manual")
        for i in range(self.when_combo.count()):
            if self.when_combo.itemText(i).startswith(when):
                self.when_combo.setCurrentIndex(i)
                break
        self.trigger_edit.setText(s.get("trigger_pattern", ""))
        target = s.get("target", "current_chapter")
        for i in range(self.target_combo.count()):
            if self.target_combo.itemText(i).startswith(target):
                self.target_combo.setCurrentIndex(i)
                break
        self.prompt_edit.setPlainText(s.get("prompt", ""))

    def _on_add(self):
        self.skills.append({
            "name": "新技能", "when": "manual", "trigger_pattern": "",
            "prompt": "请改写下文:\n\n{content}\n\n直接输出结果。",
            "target": "current_chapter", "enabled": True,
        })
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self.skills) - 1)

    def _on_del(self):
        if self._current_idx < 0 or self._current_idx >= len(self.skills):
            return
        ret = QMessageBox.question(
            self, "确认", f"删除技能「{self.skills[self._current_idx]['name']}」?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.skills.pop(self._current_idx)
        self._refresh_list()
        self.list_widget.setCurrentRow(min(self._current_idx, len(self.skills) - 1))

    def _on_dup(self):
        if self._current_idx < 0 or self._current_idx >= len(self.skills):
            return
        new_s = dict(self.skills[self._current_idx])
        new_s["name"] += "_副本"
        self.skills.append(new_s)
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self.skills) - 1)

    def _on_save(self):
        if self._current_idx < 0 or self._current_idx >= len(self.skills):
            return
        s = self.skills[self._current_idx]
        s["name"] = self.name_edit.text().strip() or "未命名"
        s["enabled"] = self.chk_enabled.isChecked()
        s["when"] = self.when_combo.currentText().split(" ")[0].strip()
        s["trigger_pattern"] = self.trigger_edit.text().strip()
        s["target"] = self.target_combo.currentText().split(" ")[0].strip()
        s["prompt"] = self.prompt_edit.toPlainText()
        self._refresh_list()
        self.list_widget.setCurrentRow(self._current_idx)
        QMessageBox.information(self, "已保存", f"技能「{s['name']}」已保存到当前会话")

    def _on_reset(self):
        ret = QMessageBox.question(
            self, "确认", "恢复出厂技能?当前所有自定义技能将被覆盖。",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.skills = [dict(s) for s in DEFAULT_SKILLS]
        self._refresh_list()
        if self.skills:
            self.list_widget.setCurrentRow(0)

    # ---------- 公共接口(供 MainWindow 调用)----------
    def get_enabled_skills(self, when=None):
        out = [s for s in self.skills if s.get("enabled")]
        if when:
            out = [s for s in out if s.get("when") == when]
        return out

    def get_manual_skills(self):
        return self.get_enabled_skills(when="manual")

    def get_after_chapter_skills(self):
        return self.get_enabled_skills(when="after_chapter_generation")

    def get_auto_match_skills(self, content: str) -> list:
        """
        返回 when="auto_match" 且 trigger_pattern 正则命中 content 的技能列表。
        trigger_pattern 为空的技能视为未配置,跳过不触发。
        匹配只扫前 3000 字符,避免超大章节慢;使用 IGNORECASE | DOTALL。
        """
        sample = content[:3000]
        matched = []
        for s in self.get_enabled_skills(when="auto_match"):
            pat = s.get("trigger_pattern", "").strip()
            if not pat:
                continue
            try:
                if re.search(pat, sample, re.IGNORECASE | re.DOTALL):
                    matched.append(s)
            except re.error:
                pass   # 正则写坏了,只跳过,不崩
        return matched

    def serialize_for_save(self):
        return {"skills": self.skills}

    def load_from_dict(self, d):
        if isinstance(d, dict) and isinstance(d.get("skills"), list) and d["skills"]:
            self.skills = d["skills"]
            self._refresh_list()
            if self.skills:
                self.list_widget.setCurrentRow(0)
