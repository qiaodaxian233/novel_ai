# -*- coding: utf-8 -*-
"""ui/ai_naming.py - AI 智能取名 + 全文替换

生成10个名字 → 选中替换 → 不喜欢继续生成。
支持手动输入自定义名字。
v2.17.2 修复。
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
        self.setWindowTitle("🎭 AI 智能取名 + 全文替换")
        self.resize(580, 520)
        self.selected_name = None
        self._mw = parent

        layout = QVBoxLayout(self)

        # ── 选择角色 ──
        info_box = QGroupBox("① 选择要改名的角色")
        info_lay = QVBoxLayout(info_box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("角色:"))
        self.combo_old = QComboBox()
        self.combo_old.setEditable(True)
        self._char_names = []  # 纯名字列表
        if char_list:
            for name, role in char_list:
                self.combo_old.addItem(f"{name} ({role})")
                self._char_names.append(name)
        if old_name and old_name in self._char_names:
            idx = self._char_names.index(old_name)
            self.combo_old.setCurrentIndex(idx)
        elif old_name:
            self.combo_old.setEditText(old_name)
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

        row2b = QHBoxLayout()
        row2b.addWidget(QLabel("字数:"))
        self.combo_length = QComboBox()
        self.combo_length.addItems(["不限", "2字(如:苏棠)", "3字(如:顾衍之)", "4字(如:欧阳明月)"])
        row2b.addWidget(self.combo_length)
        row2b.addWidget(QLabel("风格:"))
        self.combo_style = QComboBox()
        self.combo_style.addItems(["不限", "现实普通", "文艺清新", "古风雅致", "霸气强势", "温柔甜美"])
        row2b.addWidget(self.combo_style)
        info_lay.addLayout(row2b)

        row2c = QHBoxLayout()
        row2c.addWidget(QLabel("指定姓:"))
        self.input_surname = QLineEdit()
        self.input_surname.setPlaceholderText("留空=AI随机,填'顾'=所有名字姓顾")
        self.input_surname.setMaximumWidth(200)
        row2c.addWidget(self.input_surname)
        row2c.addStretch()
        info_lay.addLayout(row2c)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("补充:"))
        self.input_desc = QLineEdit()
        self.input_desc.setPlaceholderText("性格/身份/气质...")
        row3.addWidget(self.input_desc)
        info_lay.addLayout(row3)
        layout.addWidget(info_box)

        # ── AI 生成 ──
        gen_box = QGroupBox("② AI 生成名字")
        gen_lay = QVBoxLayout(gen_box)
        btn_row = QHBoxLayout()
        self.btn_generate = QPushButton("🎲 AI 生成 10 个名字")
        self.btn_generate.setStyleSheet(
            "QPushButton { background:#3d6fd4; color:white; padding:8px 16px;"
            "font-weight:bold; border-radius:4px; } "
            "QPushButton:hover { background:#1557b0; }")
        self.btn_generate.clicked.connect(self._on_generate)
        btn_row.addWidget(self.btn_generate)
        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "QPushButton { background:#e74c3c; color:white; padding:8px 12px;"
            "border-radius:4px; } "
            "QPushButton:hover { background:#c0392b; }")
        self.btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self.btn_stop)
        gen_lay.addLayout(btn_row)

        self.names_layout = QGridLayout()
        self.names_layout.setSpacing(6)
        self._name_buttons = []
        gen_lay.addLayout(self.names_layout)
        self.lbl_status = QLabel("填好角色信息后点生成,或直接手动输入")
        self.lbl_status.setStyleSheet("color:#6d7c95; font-size:11px;")
        gen_lay.addWidget(self.lbl_status)
        layout.addWidget(gen_box)

        # ── 手动输入 ──
        manual_box = QGroupBox("③ 或手动输入新名字")
        manual_lay = QHBoxLayout(manual_box)
        self.input_custom = QLineEdit()
        self.input_custom.setPlaceholderText("自己想的名字")
        self.input_custom.setStyleSheet("padding:6px; font-size:14px;")
        self.input_custom.textChanged.connect(self._on_custom_changed)
        manual_lay.addWidget(self.input_custom)
        btn_use = QPushButton("✅ 用这个替换全文")
        btn_use.setStyleSheet(
            "QPushButton { background:#1f8b4d; color:white; padding:6px 14px;"
            "font-weight:bold; border-radius:4px; } "
            "QPushButton:hover { background:#186f3d; }")
        btn_use.clicked.connect(self._on_use_custom)
        manual_lay.addWidget(btn_use)
        layout.addWidget(manual_box)

        # ── 底部 ──
        bottom = QHBoxLayout()
        self.btn_replace = QPushButton("✅ 用选中名字替换全文")
        self.btn_replace.setEnabled(False)
        self.btn_replace.setStyleSheet(
            "QPushButton { background:#1f8b4d; color:white; padding:8px 16px;"
            "font-weight:bold; border-radius:4px; } "
            "QPushButton:hover { background:#186f3d; }")
        self.btn_replace.clicked.connect(self._on_replace)
        bottom.addWidget(self.btn_replace)
        bottom.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)
        layout.addLayout(bottom)

    def _get_old_name(self):
        """获取原角色名(纯名字,不含角色定位)"""
        idx = self.combo_old.currentIndex()
        # 从预存的纯名字列表取
        if 0 <= idx < len(self._char_names):
            return self._char_names[idx]
        # 手动输入的,去掉可能的括号后缀
        text = self.combo_old.currentText().strip()
        return text.split(" (")[0].split("(")[0].strip()

    def _build_char_info(self):
        parts = []
        old = self._get_old_name()
        if old:
            parts.append(f"原名: {old}(需要替换)")
        parts.append(f"性别: {self.combo_gender.currentText()}")
        parts.append(f"背景: {self.combo_era.currentText()}")
        # 字数要求
        length = self.combo_length.currentText()
        if "2字" in length:
            parts.append("名字长度: 必须2个字(姓1字+名1字)")
        elif "3字" in length:
            parts.append("名字长度: 必须3个字(姓1字+名2字,或复姓+名1字)")
        elif "4字" in length:
            parts.append("名字长度: 必须4个字(复姓2字+名2字)")
        # 风格
        style = self.combo_style.currentText()
        if style != "不限":
            parts.append(f"名字风格: {style}")
        # 指定姓氏
        surname = self.input_surname.text().strip()
        if surname:
            parts.append(f"指定姓氏: 所有名字必须姓'{surname}'")
        # 补充
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
        self.btn_stop.setEnabled(True)
        self.lbl_status.setText("等待 AI 回复...")
        self._mw._send_to_ai(prompt, "AI取名", target="ai_naming")

    def _on_stop(self):
        """停止等待"""
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("🎲 AI 生成 10 个名字")
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText("已停止。可以重新生成或手动输入")
        # 从 pending 里移除
        if self._mw and hasattr(self._mw, '_pending_task_targets'):
            self._mw._pending_task_targets.pop("AI取名", None)

    def on_names_received(self, content):
        """接收 AI 返回的名字列表"""
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("🎲 不喜欢?再生成 10 个")
        self.btn_stop.setEnabled(False)

        for btn in self._name_buttons:
            btn.deleteLater()
        self._name_buttons.clear()

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

        for i, item in enumerate(names[:10]):
            name = item.get("name", "") if isinstance(item, dict) else str(item)
            reason = item.get("reason", "") if isinstance(item, dict) else ""
            if not name:
                continue
            btn = QPushButton(name)
            btn.setToolTip(reason or name)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { padding:8px 14px; font-size:13px; border:2px solid #ccc;"
                "border-radius:6px; } "
                "QPushButton:checked { border-color:#1a73e8; background:#e3f0ff; color:#3a3f47;"
                "font-weight:bold; } "
                "QPushButton:hover { border-color:#8fa3c4; }")
            btn.clicked.connect(
                lambda _, n=name, b=btn: self._on_name_clicked(n, b))
            self.names_layout.addWidget(btn, i // 5, i % 5)
            self._name_buttons.append(btn)

        self.lbl_status.setText(
            f"✨ {len(self._name_buttons)} 个名字,悬停看理由,或手动输入")

    def _on_name_clicked(self, name, clicked_btn):
        for btn in self._name_buttons:
            if btn is not clicked_btn:
                btn.setChecked(False)
        self.selected_name = name
        self.input_custom.clear()
        self.btn_replace.setEnabled(True)
        self.btn_replace.setText(f"✅ 用「{name}」替换全文")

    def _on_custom_changed(self, text):
        if text.strip():
            for btn in self._name_buttons:
                btn.setChecked(False)
            self.selected_name = None
            self.btn_replace.setEnabled(False)

    def _on_use_custom(self):
        name = self.input_custom.text().strip()
        if not name:
            QMessageBox.information(self, "提示", "请输入名字")
            return
        old = self._get_old_name()
        if not old:
            QMessageBox.information(self, "提示", "请先选择要替换的角色")
            return
        self.selected_name = name
        self.accept()

    def _on_replace(self):
        if not self.selected_name:
            return
        old_name = self._get_old_name()
        if not old_name:
            QMessageBox.information(self, "提示", "请先选择要替换的角色")
            return
        self.accept()

    def get_result(self):
        if self.selected_name and self._get_old_name():
            return (self._get_old_name(), self.selected_name)
        return None
