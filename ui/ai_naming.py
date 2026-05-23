# -*- coding: utf-8 -*-
"""ui/ai_naming.py - AI 智能取名 + 全文替换

生成10个名字 → 选中替换 → 不喜欢继续生成。
v2.15.6 新增。
"""
import json
import re
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QGridLayout,
    QMessageBox, QPlainTextEdit,
)


class AINamingDialog(QDialog):
    """AI 取名对话框"""

    def __init__(self, old_name="", char_list=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎭 AI 智能取名")
        self.resize(550, 480)
        self.selected_name = None
        self._mw = parent

        layout = QVBoxLayout(self)

        # ── 输入区 ──
        info_box = QGroupBox("角色信息(帮AI取更合适的名字)")
        info_lay = QVBoxLayout(info_box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("选择角色:"))
        self.combo_old = QComboBox()
        self.combo_old.setEditable(True)
        if char_list:
            for name, role in char_list:
                self.combo_old.addItem(f"{name} ({role})", name)
        if old_name:
            # 选中主角
            for i in range(self.combo_old.count()):
                if self.combo_old.itemData(i) == old_name:
                    self.combo_old.setCurrentIndex(i)
                    break
            else:
                self.combo_old.setEditText(old_name)
        self.combo_old.setToolTip("选择要改名的角色,或手动输入")
        row1.addWidget(self.combo_old)
        info_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("性别:"))
        self.combo_gender = QComboBox()
        self.combo_gender.addItems(["男", "女", "不限"])
        row2.addWidget(self.combo_gender)
        row2.addWidget(QLabel("背景:"))
        self.combo_era = QComboBox()
        self.combo_era.addItems(["现代都市", "古代宫廷", "修仙玄幻", "民国", "未来科幻", "其他"])
        row2.addWidget(self.combo_era)
        info_lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("补充:"))
        self.input_desc = QLineEdit()
        self.input_desc.setPlaceholderText("性格/身份/气质,如: 冷静理性的女律师、霸道总裁、落魄书生...")
        row3.addWidget(self.input_desc)
        info_lay.addLayout(row3)

        layout.addWidget(info_box)

        # ── 生成按钮 ──
        btn_row = QHBoxLayout()
        self.btn_generate = QPushButton("🎲 AI 生成 10 个名字")
        self.btn_generate.setStyleSheet(
            "QPushButton { background:#1a73e8; color:white; padding:8px 20px;"
            "font-weight:bold; border-radius:4px; font-size:14px; } "
            "QPushButton:hover { background:#1557b0; }")
        self.btn_generate.clicked.connect(self._on_generate)
        btn_row.addWidget(self.btn_generate)
        layout.addLayout(btn_row)

        # ── 名字列表区 ──
        self.names_box = QGroupBox("选一个你喜欢的(点击选中)")
        self.names_layout = QGridLayout(self.names_box)
        self.names_layout.setSpacing(6)
        self._name_buttons = []
        layout.addWidget(self.names_box)

        # ── 状态 ──
        self.lbl_status = QLabel("👆 填好信息后点生成")
        self.lbl_status.setStyleSheet("color:#888; padding:4px;")
        layout.addWidget(self.lbl_status)

        # ── 底部操作 ──
        bottom = QHBoxLayout()
        self.btn_replace = QPushButton("✅ 用选中名字替换全文")
        self.btn_replace.setEnabled(False)
        self.btn_replace.setStyleSheet(
            "QPushButton { background:#27ae60; color:white; padding:8px 16px;"
            "font-weight:bold; border-radius:4px; } "
            "QPushButton:hover { background:#219a52; }")
        self.btn_replace.clicked.connect(self._on_replace)
        bottom.addWidget(self.btn_replace)
        bottom.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)
        layout.addLayout(bottom)

    def _get_old_name(self):
        """从 combo 获取原角色名"""
        idx = self.combo_old.currentIndex()
        if idx >= 0 and self.combo_old.itemData(idx):
            return str(self.combo_old.itemData(idx)).strip()
        return self.combo_old.currentText().strip().split(" (")[0].strip()

    def _build_char_info(self):
        parts = []
        old = self._get_old_name()
        if old:
            parts.append(f"原名: {old}(需要替换)")
        parts.append(f"性别: {self.combo_gender.currentText()}")
        parts.append(f"背景: {self.combo_era.currentText()}")
        desc = self.input_desc.text().strip()
        if desc:
            parts.append(f"角色特征: {desc}")
        return "\n".join(parts)

    def _on_generate(self):
        if not self._mw:
            return
        char_info = self._build_char_info()
        from novel_ai import PROMPTS
        prompt = PROMPTS["ai_naming"].format(char_info=char_info)
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("⏳ AI 正在取名...")
        self.lbl_status.setText("等待 AI 回复...")
        self._mw._send_to_ai(prompt, "AI取名", target="ai_naming")

    def on_names_received(self, content):
        """接收 AI 返回的名字列表"""
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("🎲 不喜欢?再生成 10 个")

        # 清除旧按钮
        for btn in self._name_buttons:
            btn.deleteLater()
        self._name_buttons.clear()

        # 解析 JSON
        raw = (content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.M).strip()
        jm = re.search(r"\[[\s\S]*\]", raw)
        if not jm:
            self.lbl_status.setText("⚠ AI 返回格式异常,请重试")
            return
        try:
            names = json.loads(jm.group(0))
        except Exception:
            self.lbl_status.setText("⚠ JSON 解析失败,请重试")
            return

        if not names:
            self.lbl_status.setText("⚠ AI 没返回名字,请重试")
            return

        # 创建名字按钮
        for i, item in enumerate(names[:10]):
            name = item.get("name", "") if isinstance(item, dict) else str(item)
            reason = item.get("reason", "") if isinstance(item, dict) else ""
            if not name:
                continue
            btn = QPushButton(name)
            btn.setToolTip(reason)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { padding:8px 16px; font-size:14px; border:2px solid #ccc;"
                "border-radius:6px; } "
                "QPushButton:checked { border-color:#1a73e8; background:#e3f0ff;"
                "font-weight:bold; } "
                "QPushButton:hover { border-color:#888; }")
            btn.clicked.connect(lambda checked, n=name, b=btn: self._on_name_clicked(n, b))
            self.names_layout.addWidget(btn, i // 5, i % 5)
            self._name_buttons.append(btn)

        self.lbl_status.setText(
            f"✨ 生成了 {len(self._name_buttons)} 个名字,鼠标悬停看理由")

    def _on_name_clicked(self, name, clicked_btn):
        # 取消其他按钮的选中
        for btn in self._name_buttons:
            if btn is not clicked_btn:
                btn.setChecked(False)
        self.selected_name = name
        self.btn_replace.setEnabled(True)
        self.btn_replace.setText(f"✅ 用「{name}」替换全文")

    def _on_replace(self):
        if not self.selected_name:
            return
        old_name = self._get_old_name()
        if not old_name:
            QMessageBox.information(self, "提示", "请填写要替换的原名")
            return
        self.accept()

    def get_result(self):
        """返回 (old_name, new_name) 或 None"""
        if self.selected_name and self._get_old_name():
            return (self._get_old_name(), self.selected_name)
        return None
