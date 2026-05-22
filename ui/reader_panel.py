# -*- coding: utf-8 -*-
"""ui/reader_panel.py - 模拟读者评审团

8 种读者类型可自由组合,动态构建提示词。
v2.14.5 新增。
"""
import json
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QLabel, QMessageBox, QGroupBox,
)

# 8 种读者类型
READER_TYPES = [
    {
        "key": "shuang",
        "emoji": "⚡",
        "name": "追爽文的",
        "desc": "只关心爽不爽、打脸够不够狠、节奏快不快。不爽就弃书。",
        "default": True,
    },
    {
        "key": "love",
        "emoji": "💕",
        "name": "追感情线的",
        "desc": "只关心CP互动、感情推进、虐不虐心。没糖就弃书。",
        "default": True,
    },
    {
        "key": "logic",
        "emoji": "🔍",
        "name": "逻辑挑刺的",
        "desc": "逻辑控,专挑设定矛盾、人设崩塌、时间线错误。有硬伤就弃书。",
        "default": True,
    },
    {
        "key": "veteran",
        "emoji": "📚",
        "name": "老书虫",
        "desc": "看过上千本网文,对套路极度敏感。太俗套就弃,但经典桥段玩出新花样会加分。",
        "default": False,
    },
    {
        "key": "newbie",
        "emoji": "🆕",
        "name": "小白读者",
        "desc": "第一次看这类小说,关注看不看得懂、代入感强不强、想不想继续看。",
        "default": False,
    },
    {
        "key": "hater",
        "emoji": "😈",
        "name": "毒舌黑粉",
        "desc": "专门找茬的杠精,但每一条吐槽都指向具体问题。骂得越狠越有参考价值。",
        "default": False,
    },
    {
        "key": "mobile",
        "emoji": "📱",
        "name": "碎片时间读者",
        "desc": "地铁上刷手机看的,注意力只有30秒。开头不抓人直接划走,段落太长就跳。",
        "default": False,
    },
    {
        "key": "author",
        "emoji": "✍️",
        "name": "同行作者",
        "desc": "自己也写网文的作者,从创作技巧角度评价:结构、节奏、人物弧光、伏笔。",
        "default": False,
    },
]


class ReaderSelectDialog(QDialog):
    """选择读者类型的对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("👥 选择模拟读者")
        self.resize(500, 420)
        self.selected = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("勾选你想要的读者类型(至少1个,最多全选):"))

        box = QGroupBox("读者类型")
        box_lay = QVBoxLayout(box)
        self._checks = {}
        for rt in READER_TYPES:
            chk = QCheckBox(f"{rt['emoji']} {rt['name']} — {rt['desc'][:30]}...")
            chk.setChecked(rt["default"])
            chk.setToolTip(rt["desc"])
            box_lay.addWidget(chk)
            self._checks[rt["key"]] = chk
        layout.addWidget(box)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("全选")
        btn_all.clicked.connect(lambda: [c.setChecked(True) for c in self._checks.values()])
        btn_row.addWidget(btn_all)
        btn_none = QPushButton("全不选")
        btn_none.clicked.connect(lambda: [c.setChecked(False) for c in self._checks.values()])
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        btn_ok = QPushButton("✅ 开始评审")
        btn_ok.setStyleSheet(
            "QPushButton { background:#1a73e8; color:white; padding:8px 20px;"
            "font-weight:bold; border-radius:4px; } "
            "QPushButton:hover { background:#1557b0; }")
        btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _on_ok(self):
        self.selected = [k for k, c in self._checks.items() if c.isChecked()]
        if not self.selected:
            QMessageBox.warning(self, "提示", "至少选一个读者")
            return
        self.accept()


def build_reader_prompt(selected_keys, content):
    """根据选中的读者类型构建提示词"""
    from novel_ai import PROMPTS

    # 构建读者描述
    descs = []
    json_parts = []
    for rt in READER_TYPES:
        if rt["key"] in selected_keys:
            descs.append(f"读者{rt['emoji']}【{rt['name']}】: {rt['desc']}")
            json_parts.append(
                f'"{rt["key"]}":{{"stay":true,"comment":"示例评论"}}'
            )

    reader_descriptions = "\n".join(descs)
    reader_json_example = ",".join(json_parts)

    prompt = PROMPTS["reader_panel"].format(
        reader_descriptions=reader_descriptions,
        content=content[:6000],
        reader_json_example=reader_json_example,
    )
    return prompt


def parse_reader_response(content, selected_keys):
    """解析读者评审结果,返回格式化文本"""
    import re
    raw = (content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.M).strip()
    jm = re.search(r"\{[\s\S]*\}", raw)
    if not jm:
        return f"AI 返回:\n{content[:500]}"

    try:
        data = json.loads(jm.group(0))
    except Exception:
        return f"解析失败:\n{content[:500]}"

    lines = ["👥 模拟读者评审团\n"]
    rt_map = {rt["key"]: rt for rt in READER_TYPES}
    for key in selected_keys:
        rt = rt_map.get(key)
        if not rt:
            continue
        r = data.get(key, {})
        stay = "✅ 继续追" if r.get("stay", True) else "❌ 弃书"
        comment = r.get("comment", "无评论")
        lines.append(f"{rt['emoji']} {rt['name']}: {stay}")
        lines.append(f"   「{comment}」\n")

    return "\n".join(lines)
