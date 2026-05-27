# -*- coding: utf-8 -*-
"""
ui/story_outline.py - 故事大纲页(QWidget Tab,提供 18 个大纲字段)

v2.02 P3 拆分:从 novel_ai.py 第 2760-2875 行整体搬运,内容零修改。
被 novel_ai.py 顶部 `from ui.story_outline import StoryOutline` 导入。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
)

class StoryOutline(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget(); scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(15, 15, 15, 15); layout.setSpacing(12)

        # 特殊需求
        layout.addWidget(QLabel("特殊需求与外部资料"))
        layout.addWidget(QLabel("(可直接将外部设定、灵感文档TXT导入到此处作为核心约束)"))
        srow = QHBoxLayout()
        self.special_edit = QPlainTextEdit()
        self.special_edit.setMaximumHeight(100)
        self.special_edit.setPlainText("")
        self.special_edit.setPlaceholderText("在这里粘贴外部设定、参考资料或核心约束...")
        srow.addWidget(self.special_edit, 1)
        self.btn_import_special = QPushButton("📁 从TXT导入文字")
        srow.addWidget(self.btn_import_special, 0, Qt.AlignTop)
        layout.addLayout(srow)

        obtns = QHBoxLayout()
        self.btn_gen_all = QPushButton("✨ 一键补齐所有大纲 (AI智能统筹) ✨")
        self.btn_regen_all = QPushButton("不满意?重新生成整套大纲")
        self.btn_rename = QPushButton("🔄 改名工具 (角色/地名/门派一键替换)")
        self.btn_rename.setStyleSheet(
            "background:#7c5cbf;color:white;padding:4px 10px;border-radius:3px;font-weight:bold;")
        self.btn_rename.setToolTip(
            "扫描大纲全部文本(简介/种子/世界观/LO层/结构/章节大纲/特殊需求/角色设定),\n"
            "把指定的旧名换成新名。支持多个对应关系一次替换。\n"
            "例如:林远 → 苏白 + 林悦 → 苏雨,一次提交。")
        obtns.addWidget(self.btn_gen_all); obtns.addWidget(self.btn_regen_all)
        obtns.addWidget(self.btn_rename)
        layout.addLayout(obtns)

        crow = QHBoxLayout()
        crow.addWidget(QLabel("总章节数:"))
        self.chapter_count = QSpinBox()
        self.chapter_count.setRange(10, 1000); self.chapter_count.setValue(300)
        crow.addWidget(self.chapter_count); crow.addStretch()
        layout.addLayout(crow)

        # 简介
        layout.addWidget(QLabel("最终作品简介 (用于平台发布,自动提取下方大纲生成)"))
        irow = QHBoxLayout()
        self.intro_edit = QPlainTextEdit(); self.intro_edit.setMaximumHeight(100)
        irow.addWidget(self.intro_edit, 1)
        self.btn_extract_intro = QPushButton("✨ 提取大纲生成简介")
        irow.addWidget(self.btn_extract_intro, 0, Qt.AlignTop)
        layout.addLayout(irow)

        # 故事种子
        srow2 = QHBoxLayout()
        sbox = QGroupBox("故事种子")
        slay = QVBoxLayout(sbox)
        self.seed_edit = QPlainTextEdit(); self.seed_edit.setMaximumHeight(80)
        self.seed_edit.setPlaceholderText("一句话描述故事核心冲突、主角遭遇与情感主线...")
        slay.addWidget(self.seed_edit)
        srow2.addWidget(sbox, 1)
        self.btn_gen_seed = QPushButton("单独生成")
        srow2.addWidget(self.btn_gen_seed, 0, Qt.AlignTop)
        layout.addLayout(srow2)

        # 故事核心
        cbox = QGroupBox("故事核心")
        clay = QVBoxLayout(cbox)

        wvr = QHBoxLayout()
        wvr.addWidget(QLabel("世界观"), 0, Qt.AlignTop)
        self.worldview_edit = QPlainTextEdit()
        self.worldview_edit.setMaximumHeight(100)
        self.worldview_edit.setPlaceholderText("故事发生在什么样的世界?时代/地理/社会规则的核心特征...")
        wvr.addWidget(self.worldview_edit, 1)
        self.btn_gen_wv = QPushButton("单独生成")
        wvr.addWidget(self.btn_gen_wv, 0, Qt.AlignTop)
        clay.addLayout(wvr)

        lor = QHBoxLayout()
        lor.addWidget(QLabel("LO世界观层"), 0, Qt.AlignTop)
        self.lo_edit = QPlainTextEdit(); self.lo_edit.setMaximumHeight(100)
        self.lo_edit.setPlaceholderText("世界观底层规则:支配人物行为的不可违反的逻辑...")
        lor.addWidget(self.lo_edit, 1)
        self.btn_gen_lo = QPushButton("单独生成")
        lor.addWidget(self.btn_gen_lo, 0, Qt.AlignTop)
        clay.addLayout(lor)

        layout.addWidget(cbox)

        # 故事结构
        srow3 = QHBoxLayout()
        sbox2 = QGroupBox("故事结构")
        slay2 = QVBoxLayout(sbox2)
        self.structure_edit = QPlainTextEdit()
        self.structure_edit.setPlaceholderText("故事的整体结构:开场 → 转折 → 高潮 → 结局,以及关键节点...")
        slay2.addWidget(self.structure_edit)
        srow3.addWidget(sbox2, 1)
        self.btn_gen_struct = QPushButton("单独生成")
        srow3.addWidget(self.btn_gen_struct, 0, Qt.AlignTop)
        layout.addLayout(srow3)

        # 章节大纲
        chrow = QHBoxLayout()
        chbox = QGroupBox("章节大纲")
        chlay = QVBoxLayout(chbox)
        self.chapter_outline_edit = QPlainTextEdit()
        self.chapter_outline_edit.setMinimumHeight(180)
        chlay.addWidget(self.chapter_outline_edit)
        chrow.addWidget(chbox, 1)
        self.btn_gen_ch = QPushButton("单独生成")
        chrow.addWidget(self.btn_gen_ch, 0, Qt.AlignTop)
        layout.addLayout(chrow)

        layout.addStretch()
