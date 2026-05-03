#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 写作工作台(Python 仿制版)
=============================================
基于 PyQt5 + Selenium 的本地小说创作辅助软件
- 挂载真实 Chrome / Edge,自动操作 DeepSeek / 豆包 / Gemini / 元宝 等 AI 网页
- 三种启动模式:attach(连接已开调试 Chrome,最稳)/ standalone / temp
- 内置提示词模板(创意灵感、整套大纲、单章节、AI润色、书名、简介)
- 章节列表 / 项目存档(JSON) / 一键保存所有章节
- 多题材 / 多平台 / 黄金三章 / 字数死磕 / 模拟人类延迟

运行依赖:
    pip install PyQt5 selenium
    (selenium 4.6+ 自动管理 driver,无需单独装 chromedriver)
"""

import sys
import os
import re
import json
import time
import random
import socket
import subprocess
import threading
import queue
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QPlainTextEdit, QTabWidget,
    QListWidget, QListWidgetItem, QRadioButton, QCheckBox, QButtonGroup,
    QGroupBox, QSplitter, QFileDialog, QMessageBox, QInputDialog,
    QSpinBox, QFrame, QScrollArea, QGridLayout, QAction, QStatusBar,
    QSlider, QComboBox,
)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QIcon, QColor

# Selenium(可选,装了就启用真浏览器自动化)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    try:
        from selenium.webdriver.edge.options import Options as EdgeOptions
    except ImportError:  # 老版 selenium 没有 Edge
        EdgeOptions = None
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    EdgeOptions = None

# QtWebEngine(已不再使用,仅保留作为兜底状态查看,避免老代码引用报错)
WEB_ENGINE_AVAILABLE = False

# ---- 模块化生成流水线(v7 新增,可选) ----
try:
    from workflow_pipeline import (
        GenerationWorkflow, StepRegistry, _patch_main_window
    )
    WORKFLOW_AVAILABLE = True
except ImportError:
    WORKFLOW_AVAILABLE = False

# ---- 工作流可视化面板(新增) ----
try:
    from workflow_panel import WorkflowPanel
    WORKFLOW_PANEL_AVAILABLE = True
except ImportError:
    WORKFLOW_PANEL_AVAILABLE = False

# ---- 寿元台账 + 长期伏笔检查(新增) ----
try:
    from lifespan_loops_steps import LifespanLoopsExtension
    from lifespan_loops_panel import LifespanLoopsPanel
    LIFESPAN_LOOPS_AVAILABLE = True
except ImportError:
    LIFESPAN_LOOPS_AVAILABLE = False

# ---- 研究报告出厂技能(新增) ----
try:
    from research_report_skills import install_into as _install_research_skills
    RESEARCH_SKILLS_AVAILABLE = True
except ImportError:
    RESEARCH_SKILLS_AVAILABLE = False


# =====================================================================
# 一、内置提示词模板(完全按用户要求的原文,可直接编辑)
# =====================================================================
PROMPTS = {
    "creative_inspiration": (
        "请为一部小说生成一个创意灵感,要求:\n"
        "题材:{genre}\n"
        "禁止抄袭。\n"
        "请直接输出一句话创意(20字以内),不要有其他内容。"
        "如果是恐怖,悬疑题材不能有能反光的物体看见自己 "
        "如镜子 手机屏幕的题材,不能影子题材,不能有另一个自己的题材,"
        "请直接在对话中回答,不要生成文档\n"
        "请勿包含任何血腥、暴力、色情、侮辱女性词语等违规内容。"
    ),

    "outline_full": (
        "请作为资深小说主编,根据以下所有基础信息,一次性生成一份连贯、"
        "无冲突、高度自洽的完整小说大纲。各个设定的内容必须相互关联和呼应。"
        "如果是恐怖,悬疑题材不能有能反光的物体看见自己 如镜子 手机屏幕的题材,"
        "不能影子题材,不能有另一个自己的题材,请直接在对话中回答,不要生成文档。\n\n"
        "【特别指示】总章节数为 {chapter_count} 章。"
        "请严格根据这个数字来规划【章节大纲】部分。\n\n"
        "【基础设定】\n"
        "题材:{genre}\n"
        "创意灵感:{inspiration}"
        "{extra}"
    ),

    "outline_part": (
        "请根据以下信息单独生成【{part_name}】部分的内容:\n"
        "题材:{genre}\n"
        "创意灵感:{inspiration}\n\n"
        "要求:内容详尽、自洽,与其他部分能够呼应,但不要生成其他部分。\n"
        "{extra}"
    ),

    "chapter": (
        "请作为资深网文作者,生成《{title}》第 {chapter_num} 章的小说正文。\n\n"
        "【题材】{genre}\n"
        "【整体世界观/结构】\n{outline}\n\n"
        "【本章大纲】\n{chapter_outline}\n\n"
        "【写作要求】\n"
        "1. 本章字数不少于 {min_words} 字,目标 {target_words} 字\n"
        "2. 与上一章衔接顺畅,人物性格一致\n"
        "3. 对话生动、描写细腻、情节有节奏感\n"
        "4. 严禁血腥、暴力、色情、侮辱女性等违规内容\n"
        "5. 直接输出章节正文,不要任何解释、不要章节标题\n"
    ),

    "golden_three": (
        "请作为资深网文作者,为《{title}》生成黄金三章(第1-3章)。\n"
        "题材:{genre}\n"
        "创意灵感:{inspiration}\n\n"
        "参考章节大纲:\n{ch_outline}\n\n"
        "要求:\n"
        "1. 第一章必须有强钩子,3000字内出现核心冲突\n"
        "2. 第二章深化矛盾,引出主线\n"
        "3. 第三章一个小高潮+悬念结尾\n"
        "4. 每章不少于 3000 字\n"
        "5. 章节之间用 ===第N章 标题=== 分隔\n"
        "6. 严禁违规内容,不要生成文档,直接在对话中输出"
    ),

    "title": (
        "请为一部 {genre} 题材的小说取一个吸引人的书名。\n"
        "创意灵感:{inspiration}\n"
        "适合平台:{platform}\n"
        "要求:8-15字,有网感、有钩子。只输出书名本身,不要任何解释。"
    ),

    "intro": (
        "请根据以下小说大纲,撰写一段 200-300 字的作品简介,"
        "用于平台发布,要有吸引力、突出卖点、点出核心冲突。\n\n"
        "故事种子:{seed}\n世界观:{worldview}\n故事结构:{structure}\n\n"
        "直接输出简介正文,不要其他说明。"
    ),

    "ai_optimize": (
        "请帮我润色以下小说章节,要求:\n"
        "1. 保持原意和情节走向不变\n"
        "2. 让对话更生动,描写更细腻\n"
        "3. 修复语病、错别字、不通顺的地方\n"
        "4. 直接输出润色后的全文,不要任何说明文字\n\n"
        "原文:\n{content}"
    ),

    # ---- 对话记忆相关 ----
    "chapter_summary": (
        "请用一段话精炼总结以下章节的核心剧情(关键事件、人物状态变化、本章埋下的伏笔),"
        "字数严格控制在 {max_len} 字以内,直接输出摘要本身,不要任何前缀、不要分行。\n\n"
        "章节标题:{title}\n章节正文:\n{content}"
    ),

    "character_extract": (
        "请从以下小说章节中提取所有出场人物,生成简洁的角色档案。\n"
        "要求:\n"
        "1. 每个角色一段,格式:【角色名】外貌:xxx;性格:xxx;当前状态:xxx;与主角关系:xxx\n"
        "2. 一行一人,描述简短,但要抓住关键\n"
        "3. 只输出角色档案,不要任何前后缀说明\n"
        "4. 如已有现有档案,请在原有基础上更新,新增角色追加在末尾\n\n"
        "{existing}"
        "章节正文:\n{content}"
    ),

    "long_term_extract": (
        "请从以下章节中提取需要长期记忆的关键信息,以避免后续章节出现矛盾。\n"
        "重点关注:\n"
        "1. 重要伏笔(尚未揭晓的悬念)\n"
        "2. 关键物品/线索(玉佩、信件、信物等)\n"
        "3. 重要承诺/约定/誓言\n"
        "4. 隐藏身份/秘密\n"
        "5. 世界观规则\n\n"
        "格式:每条一行,简短表达,末尾标注章节号。例如:\n"
        "- 玉佩:祖母传给男主(第3章)\n"
        "- 女主双重身份未被发现(全文核心)\n\n"
        "如本章没有需要长期记忆的内容,直接回答\"无\"。只输出条目本身,不要前后缀。\n\n"
        "章节正文:\n{content}"
    ),

    # =========== B / C / D:防崩 + 自鞭策 + 技能 新增提示词 ===========

    "canon_audit": (
        "你是小说设定稽核员。下面是【核心设定档】(每条都不可违反),"
        "以及【新生成的章节】。请检查这章是否有任何与核心设定冲突的地方。\n\n"
        "【核心设定档(锁定项,绝对不可违反)】\n"
        "{canon_locked}\n\n"
        "【演化项(可随情节推进改变,但不可凭空打脸)】\n"
        "{canon_evolving}\n\n"
        "【新生成的章节】\n"
        "{content}\n\n"
        "审查规则:\n"
        "1. 锁定项被违反 = 严重 (severity=high)\n"
        "2. 演化项被无理由颠覆 = 中等 (severity=mid)\n"
        "3. 自身设定矛盾(同章前后冲突)= 低 (severity=low)\n"
        "4. 没问题就返回 OK\n\n"
        "请直接输出严格 JSON,不要任何前后缀、不要 markdown 代码块,格式:\n"
        '{{"violated": false, "items": []}}\n'
        "或者:\n"
        '{{"violated": true, "items": [{{"severity":"high","desc":"违反了林晚晚双重身份未被识破设定,因为本章顾砚深直接戳破了她在夜市卖串"}}]}}'
    ),

    "canon_extract": (
        "你是小说设定提取员。从以下章节中提取出所有【应当被记入设定档】的事实,"
        "用于约束后续章节不要矛盾。\n\n"
        "提取范围:\n"
        "1. 角色稳定属性(名字、年龄、身份、能力、独有称号)→ 锁定项\n"
        "2. 关键物品归属(玉佩在谁手上、剑藏哪里)→ 锁定项\n"
        "3. 关键关系(谁是谁的兄弟、谁欠谁人情)→ 锁定项\n"
        "4. 角色当前状态(等级、修为、健康、心境)→ 演化项\n"
        "5. 已发生的关键事件、已暴露/未暴露的秘密 → 演化项\n\n"
        "现有设定档(避免重复提取):\n{existing}\n\n"
        "章节正文(章节号 {ch_num}):\n{content}\n\n"
        "请直接输出严格 JSON 数组,不要任何前后缀、不要 markdown 代码块,格式:\n"
        '[{{"key":"林晚晚.年龄","value":"25","mode":"locked","ch":1}},'
        '{{"key":"顾砚深.修为","value":"金丹中期","mode":"evolving","ch":7}}]\n'
        "如果本章没有可提取的新设定,直接输出 []。"
    ),

    "critique_rhythm": (
        "你是小说节奏诊断师。请对下面这章打节奏分(1-10 整数):\n"
        "评分维度:开局抓人 / 中段推进 / 结尾钩子 / 整体爽感\n"
        "及格线 = 6,8 分以上为佳。\n\n"
        "章节正文:\n{content}\n\n"
        "请直接输出严格 JSON,不要任何前后缀、不要 markdown 代码块,格式:\n"
        '{{"score":7,"reason":"开局两段铺垫太长,结尾钩子合格但不够强"}}'
    ),

    "critique_character": (
        "你是小说人设审稿员。下面是【角色档案】和【新章节】。"
        "请评估本章人物言行是否符合既定人设,1-10 打分。\n"
        "及格线 = 7,8 分以上为佳。\n\n"
        "【角色档案】\n{characters}\n\n"
        "【新章节】\n{content}\n\n"
        "请直接输出严格 JSON,不要任何前后缀、不要 markdown 代码块,格式:\n"
        '{{"score":8,"reason":"林晚晚台词到位,但顾砚深这章过于温和,与高冷禁欲设定有偏差"}}'
    ),
}

# AI 网页地址
AI_URLS = {
    "ChatGPT镜像": "https://gpt.aimonkey.plus/",
    "ChatGPT":  "https://chatgpt.com/",
    "豆包":     "https://www.doubao.com/chat/",
    "Gemini":   "https://gemini.google.com/",
    "DeepSeek": "https://chat.deepseek.com/",
    "元宝":     "https://yuanbao.tencent.com/",
    "小米AI":   "https://www.xiaomi.com/",
}

GENRES = [
    ["仙侠", "玄幻", "奇幻", "都市"],
    ["言情", "科幻", "末世", "悬疑"],
    ["历史", "无限流", "游戏", "武侠"],
    ["恐怖", "系统流", "轮回流", "规则怪谈"],
    ["惊悚游戏", "模拟器", "全民副本", "升级流"],
    ["扮猪吃虎", "逆袭流"],
]
PLATFORMS = ["起点中文网", "番茄小说", "晋江文学城", "通用/其他平台"]

# 结局倾向(可多选)
ENDINGS = [
    ["圆满结局", "悲剧结局", "开放式结局", "主角胜利", "反派胜利"],
    ["主角牺牲", "全员存活", "全员悲剧", "复仇成功", "遗憾结局"],
    ["和解结局", "成长结局", "留白结局", "反转结局", "轮回结局"],
    ["归隐结局", "登基称帝", "一统天下", "相守一生", "孤独终老"],
]

# 金手指(可多选,4 列)
GOLDEN_FINGERS = [
    "系统流", "先知记忆", "随身空间", "科技/文明",
    "无限神豪", "禁忌天赋", "气运至尊", "纯才华",
    "重生记忆", "穿越者优势", "神级宠物", "上古传承",
    "神秘老爷爷", "签到打卡", "抽奖系统", "任务系统",
    "商城系统", "无限流副本", "主神空间", "快穿任务",
    "诸天万界", "位面交易", "时间回溯", "空间折叠",
    "元素亲和", "魔法天赋", "修仙灵根", "武道全体",
    "异能觉醒", "神级医术", "神级厨艺", "神级黑客",
    "神级演技", "神级投资", "神级鉴宝", "神级赌石",
    "神级赛车", "神级格斗", "神级编程", "神级设计",
    "神级创作", "神级预言", "神级推演", "神级炼器",
    "神级炼丹", "神级制符", "神级布阵", "神级驯兽",
    "神级御兽", "神级召唤", "神级融合", "神级吞噬",
    "神级进化", "神级复制", "神级窃取", "神级伪装",
    "神级潜行", "神级侦查", "神级反侦察", "神级谈判",
    "神级忽悠", "神级易容", "神级催眠", "神级读心",
    "神级控心", "神级控物", "神级控火", "神级控水",
    "神级控风", "神级控雷", "神级控土", "神级控金",
    "神级控木", "神级控光", "神级控暗", "神级控时",
    "神级控空", "神级控生", "神级控死", "神级控魂",
    "神级控灵", "神级控妖", "神级控魔", "神级控仙",
    "神级控神",
]

# 主角人设(可多选,4 列)
PERSONAS = [
    "天才型", "废柴逆袭", "重生/穿越", "普通人",
    "反英雄", "贵族/精英", "气运至尊", "腹黑大佬",
    "杀伐果断", "外冷内热", "外热内冷", "高冷禁欲",
    "温柔治愈", "傲娇毒舌", "沉稳可靠", "冲动热血",
    "孤僻冷漠", "阳光开朗", "呆萌可爱", "成熟稳重",
    "霸道强势", "隐忍坚韧", "机智腹黑", "冷静理智",
    "吊儿郎当", "病帅不羁", "正直善良", "自私利己",
    "慈悲心软", "偏执疯批", "病娇", "忠犬",
    "傲娇", "女王", "御姐", "萝莉",
    "正太", "大叔", "少年", "青年",
    "腹黑反派", "正道君子", "邪道狂徒", "佛系躺平",
    "卷王奋斗", "社恐内向", "社牛外向", "心机深沉",
    "坦率真诚", "护短狂魔", "有仇必报", "重情重义",
    "冷漠无情", "幽默风趣", "沉默寡言", "前世大佬",
    "快穿者", "无限流玩家", "凡人", "修仙者",
    "魔法师", "武者", "异能者", "特种兵",
    "杀手", "特工", "医生", "律师",
    "程序员", "主播", "明星", "富二代",
    "穷小子", "打工人", "学霸", "学渣",
    "太子", "王爷", "皇帝", "权臣",
    "将军", "侠士", "魔头", "精灵",
    "兽人", "吸血鬼", "狼人", "龙族",
    "妖族", "鬼魂", "僵尸", "神明",
    "恶魔", "天使",
]

# 时代背景下拉选项
ERAS = [
    "现代都市", "古代王朝", "近未来科技", "远古洪荒",
    "民国风云", "末世废土", "修真大陆", "魔法世界",
    "星际宇宙", "蒸汽朋克", "异世大陆", "校园青春",
    "江湖武林", "诸天万界",
]

# 风格维度(滑块)
STYLE_DIMENSIONS = ["爽文", "文学", "黑暗", "轻松", "搞笑"]


# =====================================================================
# 二、全局样式表(蓝色主调,接近原版)
# =====================================================================
STYLESHEET = """
QMainWindow, QWidget { background-color: #f0f0f0; color: #222;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif; font-size: 13px; }
QPushButton { background-color: #1a4480; color: white; border: none;
    padding: 7px 14px; border-radius: 3px; font-weight: bold; }
QPushButton:hover { background-color: #2563b3; }
QPushButton:pressed { background-color: #0f3060; }
QPushButton:disabled { background-color: #888; color: #ddd; }
QLineEdit, QPlainTextEdit, QSpinBox {
    background-color: white; border: 1px solid #aaa;
    padding: 4px; border-radius: 3px; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #1a4480; }
QTabWidget::pane { border: 1px solid #1a4480; background-color: white; }
QTabBar::tab { background: #d8d8d8; color: #333; padding: 8px 24px;
    border: 1px solid #aaa; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
QTabBar::tab:selected { background: white; color: #1a4480; font-weight: bold;
    border-bottom: 2px solid #1a4480; }
QTabBar::tab:hover { background: #e8e8e8; }
QListWidget { background-color: white; border: 1px solid #aaa; border-radius: 3px; }
QListWidget::item { padding: 6px; border-bottom: 1px solid #eee; }
QListWidget::item:selected { background-color: #1a4480; color: white; }
QGroupBox { border: 1px solid #1a4480; border-radius: 4px;
    margin-top: 14px; padding-top: 8px; font-weight: bold; color: #1a4480; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QRadioButton, QCheckBox { padding: 4px; }
QStatusBar { background-color: #1a4480; color: white; }
QScrollArea { border: none; background: transparent; }
QSlider::groove:horizontal {
    border: 1px solid #aaa; height: 8px; background: #e0e0e0;
    border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: #1a4480; border-radius: 4px;
}
QSlider::handle:horizontal {
    background: white; border: 2px solid #1a4480; width: 14px;
    margin: -4px 0; border-radius: 8px;
}
QComboBox {
    background: white; border: 1px solid #aaa; padding: 4px 8px; border-radius: 3px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #1a4480;
    selection-color: white; border: 1px solid #1a4480; }
"""


# =====================================================================
# 三、章节编辑器
# =====================================================================
class ChapterEditor(QWidget):
    save_requested = pyqtSignal(str, str)
    optimize_requested = pyqtSignal(str)
    save_all_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("保存章节")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_optimize = QPushButton("AI优化")
        self.btn_optimize.clicked.connect(self._on_optimize)
        self.btn_save_all = QPushButton("一键保存所有")
        self.btn_save_all.clicked.connect(lambda: self.save_all_requested.emit())
        for b in (self.btn_save, self.btn_optimize, self.btn_save_all):
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("章节标题:"))
        self.title_input = QLineEdit()
        layout.addWidget(self.title_input)

        self.content_edit = QPlainTextEdit()
        self.content_edit.setStyleSheet(
            "font-family: 'Microsoft YaHei'; font-size: 14px;")
        self.content_edit.textChanged.connect(self._update_word_count)
        layout.addWidget(self.content_edit, 1)

        self.word_count_label = QLabel("字数: 0")
        self.word_count_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.word_count_label)

    def _update_word_count(self):
        text = self.content_edit.toPlainText()
        count = len(re.sub(r'\s', '', text))
        self.word_count_label.setText(f"字数: {count}")

    def _on_save(self):
        self.save_requested.emit(
            self.title_input.text(), self.content_edit.toPlainText())

    def _on_optimize(self):
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.warning(self, "提示", "章节内容为空,无法优化")
            return
        self.optimize_requested.emit(c)

    def load_chapter(self, title, content):
        self.title_input.setText(title)
        self.content_edit.setPlainText(content)


# =====================================================================
# 四、创作设置页
# =====================================================================
class CreationSettings(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # ---- AI 配置(只管「用什么 AI」;启动 / 关闭 / 内核 / 抓取 在生成控制 Tab) ----
        ai_box = QGroupBox("AI 配置")
        ai_layout = QVBoxLayout(ai_box)

        # —— 第 1 行:选择 AI 模型 ——
        row = QHBoxLayout()
        row.addWidget(QLabel("选择AI模型:"))
        self.ai_group = QButtonGroup(self)
        for i, m in enumerate(["ChatGPT", "豆包", "Gemini", "DeepSeek", "元宝", "小米AI", "自定义"]):
            rb = QRadioButton(m)
            if m == "DeepSeek":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.ai_group.addButton(rb, i)
            row.addWidget(rb)
        self.custom_url = QLineEdit()
        self.custom_url.setPlaceholderText("自定义URL")
        self.custom_url.setEnabled(False)   # 默认禁用,选「自定义」才启用
        row.addWidget(self.custom_url)
        ai_layout.addLayout(row)

        self.delay_check = QCheckBox("模拟人类操作延迟(非必要勿勾选)")
        ai_layout.addWidget(self.delay_check)

        # —— 预登录(快捷:启动浏览器并跳到所选 AI 网站登录页) ——
        prow = QHBoxLayout()
        self.btn_prelogin = QPushButton("预登录所选模型")
        self.btn_prelogin.setStyleSheet(
            "background:#1a73e8;color:white;padding:6px 14px;"
            "font-weight:bold;border-radius:3px;")
        prow.addWidget(self.btn_prelogin)
        hint = QLabel("(也可以到「生成控制」Tab 顶部直接挂载浏览器)")
        hint.setStyleSheet("color:#888;")
        prow.addWidget(hint)
        prow.addStretch()
        ai_layout.addLayout(prow)

        # 选中「自定义」时启用 custom_url
        def _toggle_custom_url(*_):
            btn = self.ai_group.checkedButton()
            self.custom_url.setEnabled(btn is not None and btn.text() == "自定义")
        self.ai_group.buttonClicked.connect(_toggle_custom_url)
        _toggle_custom_url()

        layout.addWidget(ai_box)

        # ---- 标题 ----
        trow = QHBoxLayout()
        trow.addWidget(QLabel("小说标题:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("(留空让 AI 生成 / 也可以自己写)")
        trow.addWidget(self.title_input, 1)
        self.btn_gen_title = QPushButton("AI生成定制长书名")
        self.btn_regen_title = QPushButton("重新生成")
        trow.addWidget(self.btn_gen_title); trow.addWidget(self.btn_regen_title)
        layout.addLayout(trow)

        # ---- 题材 ----
        gbox = QGroupBox("题材选择")
        glay = QGridLayout(gbox)
        self.genre_checks = {}
        for r, row_data in enumerate(GENRES):
            for c, name in enumerate(row_data):
                cb = QCheckBox(name)
                if name in ("都市", "言情"):
                    cb.setChecked(True)
                self.genre_checks[name] = cb
                glay.addWidget(cb, r, c)
        layout.addWidget(gbox)

        # ---- 灵感 ----
        layout.addWidget(QLabel("创意灵感(注意手动标明男频还是女频)"))
        irow = QHBoxLayout()
        self.inspiration_edit = QPlainTextEdit()
        self.inspiration_edit.setMaximumHeight(120)
        self.inspiration_edit.setPlainText("")
        self.inspiration_edit.setPlaceholderText("在这里输入或粘贴你的创意灵感...")
        irow.addWidget(self.inspiration_edit, 1)
        ibtns = QVBoxLayout()
        self.btn_gen_insp = QPushButton("AI生成灵感")
        self.btn_regen_insp = QPushButton("重新生成")
        self.btn_import_txt = QPushButton("📁 从TXT导入文字")
        for b in (self.btn_gen_insp, self.btn_regen_insp, self.btn_import_txt):
            ibtns.addWidget(b)
        irow.addLayout(ibtns)
        layout.addLayout(irow)

        # ---- 商业参数 ----
        bbox = QGroupBox("商业参数")
        blay = QVBoxLayout(bbox)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("平台定位:"))
        self.platform_group = QButtonGroup(self)
        for i, p in enumerate(PLATFORMS):
            rb = QRadioButton(p)
            if p == "番茄小说":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.platform_group.addButton(rb, i)
            prow.addWidget(rb)
        prow.addStretch()
        blay.addLayout(prow)
        layout.addWidget(bbox)

        # ---- 目标读者 ----
        ar_box = QGroupBox("目标读者")
        ar_lay = QHBoxLayout(ar_box)
        self.audience_group = QButtonGroup(self)
        for i, a in enumerate(["青少年", "青年", "成人"]):
            rb = QRadioButton(a)
            if a == "成人":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.audience_group.addButton(rb, i)
            ar_lay.addWidget(rb)
        ar_lay.addStretch()
        layout.addWidget(ar_box)

        # ---- 爽点密度 ----
        dn_box = QGroupBox("爽点密度")
        dn_lay = QHBoxLayout(dn_box)
        self.density_group = QButtonGroup(self)
        for i, d in enumerate(["低密度", "适中", "高密度", "极致爽"]):
            rb = QRadioButton(d)
            if d == "极致爽":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.density_group.addButton(rb, i)
            dn_lay.addWidget(rb)
        dn_lay.addStretch()
        layout.addWidget(dn_box)

        # ---- 成长曲线 ----
        gc_box = QGroupBox("成长曲线")
        gc_lay = QHBoxLayout(gc_box)
        self.growth_group = QButtonGroup(self)
        for i, g in enumerate(["慢热型", "均衡型", "爆发型"]):
            rb = QRadioButton(g)
            if g == "爆发型":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.growth_group.addButton(rb, i)
            gc_lay.addWidget(rb)
        gc_lay.addStretch()
        layout.addWidget(gc_box)

        # ---- 冲突强度 ----
        ci_box = QGroupBox("冲突强度")
        ci_lay = QHBoxLayout(ci_box)
        self.conflict_group = QButtonGroup(self)
        for i, c in enumerate(["轻度", "中度", "强烈", "极端"]):
            rb = QRadioButton(c)
            if c == "极端":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.conflict_group.addButton(rb, i)
            ci_lay.addWidget(rb)
        ci_lay.addStretch()
        layout.addWidget(ci_box)

        # ---- 时代背景 ----
        era_box = QGroupBox("时代背景")
        era_lay = QHBoxLayout(era_box)
        self.era_combo = QComboBox()
        self.era_combo.addItems(ERAS)
        self.era_combo.setCurrentText("古代王朝")
        era_lay.addWidget(self.era_combo, 1)
        era_lay.addWidget(QLabel("自定义:"))
        self.era_custom = QLineEdit("古代王朝")
        era_lay.addWidget(self.era_custom, 1)
        layout.addWidget(era_box)

        # ---- 生成规模 ----
        scale_label = QLabel("生成规模")
        scale_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #1a4480;")
        layout.addWidget(scale_label)

        # 总章节数
        cc_box = QGroupBox("总章节数")
        cc_lay = QVBoxLayout(cc_box)
        cc_row = QHBoxLayout()
        self.chapter_preset_group = QButtonGroup(self)
        for i, n in enumerate(["60章", "120章", "300章", "500章"]):
            rb = QRadioButton(n)
            if n == "300章":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.chapter_preset_group.addButton(rb, i)
            cc_row.addWidget(rb)
        cc_row.addStretch()
        cc_lay.addLayout(cc_row)
        cc_row2 = QHBoxLayout()
        cc_row2.addWidget(QLabel("自定义:"))
        self.chapter_custom = QSpinBox()
        self.chapter_custom.setRange(10, 9999)
        self.chapter_custom.setValue(300)
        cc_row2.addWidget(self.chapter_custom)
        cc_row2.addWidget(QLabel("章"))
        cc_row2.addStretch()
        cc_lay.addLayout(cc_row2)
        # 联动:点击预设填进自定义
        for btn in self.chapter_preset_group.buttons():
            btn.toggled.connect(self._sync_chapter_preset)
        layout.addWidget(cc_box)

        # 每章字数
        wp_box = QGroupBox("每章正文字数")
        wp_lay = QVBoxLayout(wp_box)
        wp_row = QHBoxLayout()
        self.words_preset_group = QButtonGroup(self)
        for i, w in enumerate(["1500字", "2000字", "3000字"]):
            rb = QRadioButton(w)
            if w == "3000字":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.words_preset_group.addButton(rb, i)
            wp_row.addWidget(rb)
        wp_row.addStretch()
        wp_lay.addLayout(wp_row)
        wp_row2 = QHBoxLayout()
        wp_row2.addWidget(QLabel("自定义:"))
        self.words_custom = QSpinBox()
        self.words_custom.setRange(500, 20000)
        self.words_custom.setValue(3000)
        self.words_custom.setSingleStep(500)
        wp_row2.addWidget(self.words_custom)
        wp_row2.addWidget(QLabel("字"))
        wp_row2.addStretch()
        wp_lay.addLayout(wp_row2)
        for btn in self.words_preset_group.buttons():
            btn.toggled.connect(self._sync_words_preset)
        layout.addWidget(wp_box)

        # 大纲详细度
        od_box = QGroupBox("大纲详细度")
        od_lay = QHBoxLayout(od_box)
        self.detail_group = QButtonGroup(self)
        for i, d in enumerate(["简洁", "标准", "详细"]):
            rb = QRadioButton(d)
            if d == "详细":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.detail_group.addButton(rb, i)
            od_lay.addWidget(rb)
        od_lay.addStretch()
        layout.addWidget(od_box)

        # ---- 风格权重(滑块) ----
        sw_box = QGroupBox("风格权重")
        sw_lay = QGridLayout(sw_box)
        self.style_sliders = {}
        defaults = {"爽文": 50, "文学": 0, "黑暗": 0, "轻松": 0, "搞笑": 50}
        for r, name in enumerate(STYLE_DIMENSIONS):
            sw_lay.addWidget(QLabel(name), r, 0)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 100)
            sl.setValue(defaults.get(name, 50))
            self.style_sliders[name] = sl
            pct = QLabel(f"{defaults.get(name, 50)}%")
            pct.setMinimumWidth(40)
            pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sl.valueChanged.connect(lambda v, lab=pct: lab.setText(f"{v}%"))
            sw_lay.addWidget(sl, r, 1)
            sw_lay.addWidget(pct, r, 2)
        sw_lay.setColumnStretch(1, 1)
        layout.addWidget(sw_box)

        # ---- 节奏 ----
        rh_box = QGroupBox("节奏")
        rh_lay = QHBoxLayout(rh_box)
        rh_lay.addWidget(QLabel("故事节奏:"))
        self.rhythm_group = QButtonGroup(self)
        for i, r in enumerate(["慢热", "适中", "紧凑"]):
            rb = QRadioButton(r)
            if r == "适中":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.rhythm_group.addButton(rb, i)
            rh_lay.addWidget(rb)
        rh_lay.addStretch()
        layout.addWidget(rh_box)

        # ---- 结局倾向(可多选) ----
        ed_box = QGroupBox("结局倾向 (可多选)")
        ed_lay = QGridLayout(ed_box)
        self.ending_checks = {}
        for r, row_items in enumerate(ENDINGS):
            for c, name in enumerate(row_items):
                cb = QCheckBox(name)
                if name == "圆满结局":
                    cb.setChecked(True)
                self.ending_checks[name] = cb
                ed_lay.addWidget(cb, r, c)
        layout.addWidget(ed_box)

        # ---- 创作模式 ----
        cm_box = QGroupBox("创作模式")
        cm_lay = QVBoxLayout(cm_box)
        self.mode_group = QButtonGroup(self)
        rb_stable = QRadioButton("稳定版 (遵循经典套路)")
        rb_creative = QRadioButton("创造版 (鼓励创新突破)")
        rb_creative.setChecked(True)
        rb_creative.setStyleSheet("color: #cc3333; font-weight: bold;")
        self.mode_group.addButton(rb_stable, 0)
        self.mode_group.addButton(rb_creative, 1)
        cm_lay.addWidget(rb_stable)
        cm_lay.addWidget(rb_creative)
        layout.addWidget(cm_box)

        # ---- 提示词字数偏移 ----
        po_row = QHBoxLayout()
        po_row.addWidget(QLabel("提示词字数偏移:"))
        self.prompt_offset = QSpinBox()
        self.prompt_offset.setRange(-2000, 2000)
        self.prompt_offset.setSingleStep(50)
        self.prompt_offset.setValue(-200)
        po_row.addWidget(self.prompt_offset)
        po_row.addWidget(QLabel("(负数=要求 AI 写少点,正数=要求多写)"))
        po_row.addStretch()
        layout.addLayout(po_row)

        # ---- 金手指(可多选) ----
        gf_box = QGroupBox("金手指 (可多选)")
        gf_outer = QVBoxLayout(gf_box)
        # 工具按钮:全选 / 清空
        gf_tools = QHBoxLayout()
        btn_gf_all = QPushButton("全选")
        btn_gf_clear = QPushButton("清空")
        btn_gf_all.setMaximumWidth(80); btn_gf_clear.setMaximumWidth(80)
        gf_tools.addWidget(btn_gf_all); gf_tools.addWidget(btn_gf_clear)
        gf_tools.addStretch()
        gf_outer.addLayout(gf_tools)
        gf_grid = QGridLayout()
        self.golden_checks = {}
        for idx, name in enumerate(GOLDEN_FINGERS):
            r, c = idx // 4, idx % 4
            cb = QCheckBox(name)
            self.golden_checks[name] = cb
            gf_grid.addWidget(cb, r, c)
        gf_outer.addLayout(gf_grid)
        btn_gf_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self.golden_checks.values()])
        btn_gf_clear.clicked.connect(lambda: [cb.setChecked(False) for cb in self.golden_checks.values()])
        layout.addWidget(gf_box)

        # ---- 主角人设(可多选) ----
        pe_box = QGroupBox("主角人设 (可多选)")
        pe_outer = QVBoxLayout(pe_box)
        pe_tools = QHBoxLayout()
        btn_pe_all = QPushButton("全选")
        btn_pe_clear = QPushButton("清空")
        btn_pe_all.setMaximumWidth(80); btn_pe_clear.setMaximumWidth(80)
        pe_tools.addWidget(btn_pe_all); pe_tools.addWidget(btn_pe_clear)
        pe_tools.addStretch()
        pe_outer.addLayout(pe_tools)
        pe_grid = QGridLayout()
        self.persona_checks = {}
        for idx, name in enumerate(PERSONAS):
            r, c = idx // 4, idx % 4
            cb = QCheckBox(name)
            self.persona_checks[name] = cb
            pe_grid.addWidget(cb, r, c)
        pe_outer.addLayout(pe_grid)
        btn_pe_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self.persona_checks.values()])
        btn_pe_clear.clicked.connect(lambda: [cb.setChecked(False) for cb in self.persona_checks.values()])
        layout.addWidget(pe_box)

        layout.addStretch()

    # ---- 联动 ----
    def _sync_chapter_preset(self, checked):
        if not checked: return
        b = self.chapter_preset_group.checkedButton()
        if b:
            n = int(re.sub(r'\D', '', b.text()) or 300)
            self.chapter_custom.setValue(n)

    def _sync_words_preset(self, checked):
        if not checked: return
        b = self.words_preset_group.checkedButton()
        if b:
            n = int(re.sub(r'\D', '', b.text()) or 3000)
            self.words_custom.setValue(n)

    # ---- Getter ----
    def get_selected_ai(self):
        b = self.ai_group.checkedButton()
        return b.text() if b else "DeepSeek"

    def get_selected_genres(self):
        return [n for n, cb in self.genre_checks.items() if cb.isChecked()]

    def get_inspiration(self):
        return self.inspiration_edit.toPlainText()

    def get_title(self):
        return self.title_input.text() or "我的小说"

    def get_platform(self):
        b = self.platform_group.checkedButton()
        return b.text() if b else "番茄小说"

    def get_audience(self):
        b = self.audience_group.checkedButton()
        return b.text() if b else "成人"

    def get_density(self):
        b = self.density_group.checkedButton()
        return b.text() if b else "适中"

    def get_growth(self):
        b = self.growth_group.checkedButton()
        return b.text() if b else "均衡型"

    def get_conflict(self):
        b = self.conflict_group.checkedButton()
        return b.text() if b else "中度"

    def get_era(self):
        return self.era_custom.text().strip() or self.era_combo.currentText()

    def get_chapter_count(self):
        return self.chapter_custom.value()

    def get_words_per_chapter(self):
        return self.words_custom.value()

    def get_outline_detail(self):
        b = self.detail_group.checkedButton()
        return b.text() if b else "标准"

    def get_style_weights(self):
        return {n: sl.value() for n, sl in self.style_sliders.items()}

    def get_rhythm(self):
        b = self.rhythm_group.checkedButton()
        return b.text() if b else "适中"

    def get_endings(self):
        return [n for n, cb in self.ending_checks.items() if cb.isChecked()]

    def get_creation_mode(self):
        b = self.mode_group.checkedButton()
        return b.text() if b else "创造版"

    def get_prompt_offset(self):
        return self.prompt_offset.value()

    def get_golden_fingers(self):
        return [n for n, cb in self.golden_checks.items() if cb.isChecked()]

    def get_personas(self):
        return [n for n, cb in self.persona_checks.items() if cb.isChecked()]

    def get_full_settings_block(self):
        """生成一段格式化的「完整设定」文本,用于注入提示词"""
        sw = self.get_style_weights()
        sw_str = "、".join(f"{k}{v}%" for k, v in sw.items() if v > 0) or "默认均衡"
        endings = self.get_endings() or ["未指定"]
        gfs = self.get_golden_fingers()
        gf_str = "、".join(gfs) if gfs else "无金手指"
        ps = self.get_personas()
        ps_str = "、".join(ps) if ps else "未指定"
        return (
            f"题材:{'/'.join(self.get_selected_genres()) or '言情'}\n"
            f"小说标题:{self.get_title()}\n"
            f"平台定位:{self.get_platform()}\n"
            f"目标读者:{self.get_audience()}\n"
            f"爽点密度:{self.get_density()}\n"
            f"成长曲线:{self.get_growth()}\n"
            f"冲突强度:{self.get_conflict()}\n"
            f"时代背景:{self.get_era()}\n"
            f"风格权重:{sw_str}\n"
            f"故事节奏:{self.get_rhythm()}\n"
            f"结局倾向:{'、'.join(endings)}\n"
            f"创作模式:{self.get_creation_mode()}\n"
            f"金手指:{gf_str}\n"
            f"主角人设:{ps_str}\n"
            f"每章字数:{self.get_words_per_chapter()} 字"
            f"(偏移 {self.get_prompt_offset():+d})\n"
            f"大纲详细度:{self.get_outline_detail()}\n"
        )


    def save_settings(self):
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        s.setValue("genres", [n for n, cb in self.genre_checks.items() if cb.isChecked()])
        b = self.platform_group.checkedButton()
        s.setValue("platform", b.text() if b else "番茄小说")
        b = self.audience_group.checkedButton()
        s.setValue("audience", b.text() if b else "成人")
        b = self.density_group.checkedButton()
        s.setValue("density", b.text() if b else "适中")
        b = self.growth_group.checkedButton()
        s.setValue("growth", b.text() if b else "均衡型")
        b = self.conflict_group.checkedButton()
        s.setValue("conflict", b.text() if b else "中度")
        s.setValue("era_combo", self.era_combo.currentText())
        s.setValue("era_custom", self.era_custom.text())
        s.setValue("chapter_count", self.chapter_custom.value())
        s.setValue("words_per_chapter", self.words_custom.value())
        b = self.detail_group.checkedButton()
        s.setValue("outline_detail", b.text() if b else "标准")
        b = self.rhythm_group.checkedButton()
        s.setValue("rhythm", b.text() if b else "适中")
        s.setValue("endings", [n for n, cb in self.ending_checks.items() if cb.isChecked()])
        b = self.mode_group.checkedButton()
        s.setValue("creation_mode", b.text() if b else "创造版")
        s.setValue("golden_fingers", [n for n, cb in self.golden_checks.items() if cb.isChecked()])
        s.setValue("personas", [n for n, cb in self.persona_checks.items() if cb.isChecked()])
        s.setValue("prompt_offset", self.prompt_offset.value())
        s.setValue("style_sliders", {n: sl.value() for n, sl in self.style_sliders.items()})
        b = self.ai_group.checkedButton()
        s.setValue("ai_model", b.text() if b else "ChatGPT镜像")
        s.setValue("custom_url", self.custom_url.text())
        s.setValue("delay_check", self.delay_check.isChecked())
        s.setValue("special_edit", self.special_edit.toPlainText() if hasattr(self, "special_edit") else "")

    def load_settings(self):
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        if not s.contains("platform"):
            return  # 首次启动，用默认值

        genres = s.value("genres", [])
        if isinstance(genres, str):
            genres = [genres]
        for n, cb in self.genre_checks.items():
            cb.setChecked(n in genres)

        def _set_radio(group, text):
            for btn in group.buttons():
                if btn.text() == text:
                    btn.setChecked(True)
                    return

        _set_radio(self.platform_group, s.value("platform", "番茄小说"))
        _set_radio(self.audience_group, s.value("audience", "成人"))
        _set_radio(self.density_group,  s.value("density",  "适中"))
        _set_radio(self.growth_group,   s.value("growth",   "均衡型"))
        _set_radio(self.conflict_group, s.value("conflict", "中度"))

        era_combo = s.value("era_combo", "")
        if era_combo:
            idx = self.era_combo.findText(era_combo)
            if idx >= 0:
                self.era_combo.setCurrentIndex(idx)
        self.era_custom.setText(s.value("era_custom", ""))

        ch = s.value("chapter_count", None)
        if ch is not None:
            self.chapter_custom.setValue(int(ch))
        wpc = s.value("words_per_chapter", None)
        if wpc is not None:
            self.words_custom.setValue(int(wpc))

        _set_radio(self.detail_group, s.value("outline_detail", "标准"))
        _set_radio(self.rhythm_group, s.value("rhythm", "适中"))

        endings = s.value("endings", [])
        if isinstance(endings, str):
            endings = [endings]
        for n, cb in self.ending_checks.items():
            cb.setChecked(n in endings)

        _set_radio(self.mode_group, s.value("creation_mode", "创造版"))

        gfs = s.value("golden_fingers", [])
        if isinstance(gfs, str):
            gfs = [gfs]
        for n, cb in self.golden_checks.items():
            cb.setChecked(n in gfs)

        ps = s.value("personas", [])
        if isinstance(ps, str):
            ps = [ps]
        for n, cb in self.persona_checks.items():
            cb.setChecked(n in ps)

        po = s.value("prompt_offset", None)
        if po is not None:
            self.prompt_offset.setValue(int(po))

        sw = s.value("style_sliders", {})
        if isinstance(sw, dict):
            for n, sl in self.style_sliders.items():
                if n in sw:
                    sl.setValue(int(sw[n]))

        _set_radio(self.ai_group, s.value("ai_model", "ChatGPT镜像"))
        self.custom_url.setText(s.value("custom_url", ""))
        delay = s.value("delay_check", False)
        self.delay_check.setChecked(delay if isinstance(delay, bool) else delay == "true")
        special = s.value("special_edit", "")
        if special and hasattr(self, "special_edit"):
            self.special_edit.setPlainText(special)


# =====================================================================
# 五、故事大纲页
# =====================================================================
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
        obtns.addWidget(self.btn_gen_all); obtns.addWidget(self.btn_regen_all)
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


# =====================================================================
# 六、对话记忆系统
# =====================================================================
class DialogMemory(QWidget):
    """
    对话记忆 - 让 AI 写到第 100 章也不忘第 1 章
    
    工作原理:
    1. 每章生成完毕,自动让 AI 用 80 字概括本章
    2. 在生成下一章前,把前面所有章节的摘要 + 最近 N 章正文尾段 + 角色档案 + 长期伏笔
       打包成「对话记忆」注入到提示词
    3. 这样 AI 看到的上下文虽然不是完整 N 章原文,但有足够的脉络保持人设/伏笔一致
    """
    
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget(); scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("对话记忆 — 让 AI 写到第 100 章也不忘第 1 章")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a4480;")
        layout.addWidget(title)

        intro = QLabel(
            "每章生成完毕会自动总结成 80 字摘要,在生成下一章前自动把"
            "「角色档案 + 章节摘要 + 最近 N 章详细回顾 + 长期伏笔」打包注入到提示词,"
            "保证 AI 持续掌握剧情脉络,人设不崩、伏笔不断。"
        )
        intro.setStyleSheet("color: #666; padding: 4px;")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ---- 一键生成对话记忆(主入口) ----
        full_box = QGroupBox("一键生成对话记忆 (推荐)")
        full_box.setStyleSheet(
            "QGroupBox { border: 2px solid #cc3333; }"
            "QGroupBox::title { color: #cc3333; }")
        full_lay = QVBoxLayout(full_box)
        full_tip = QLabel(
            "基于当前所有章节,串行调用 AI 生成:补齐所有缺失摘要 → 提取角色档案 → 提取长期记忆。\n"
            "适合首次使用、导入旧项目、或长篇小说里手动整理记忆。"
        )
        full_tip.setWordWrap(True)
        full_tip.setStyleSheet("color: #666; padding: 4px;")
        full_lay.addWidget(full_tip)

        full_btn_row = QHBoxLayout()
        self.btn_gen_full_memory = QPushButton("✨ 一键生成完整对话记忆")
        self.btn_gen_full_memory.setStyleSheet(
            "QPushButton { background-color: #cc3333; color: white; "
            "padding: 12px 20px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #e04444; }")
        self.btn_stop_full_memory = QPushButton("⏹ 中止")
        self.btn_stop_full_memory.setMaximumWidth(80)
        self.btn_stop_full_memory.setEnabled(False)
        full_btn_row.addWidget(self.btn_gen_full_memory, 1)
        full_btn_row.addWidget(self.btn_stop_full_memory)
        full_lay.addLayout(full_btn_row)

        self.full_memory_progress = QLabel("就绪")
        self.full_memory_progress.setStyleSheet(
            "padding: 6px 10px; background: #f4f4f4; border-radius: 3px; color: #555;")
        full_lay.addWidget(self.full_memory_progress)
        layout.addWidget(full_box)

        # ---- 自动记忆策略 ----
        st_box = QGroupBox("自动记忆策略")
        sl = QVBoxLayout(st_box)
        self.auto_summarize = QCheckBox(
            "每章生成后自动总结(批量生成时,会在每章正文之后自动跑一次摘要任务)")
        self.auto_summarize.setChecked(True)
        self.auto_inject = QCheckBox(
            "发送下一章时自动把记忆块注入到提示词")
        self.auto_inject.setChecked(True)
        for cb in (self.auto_summarize, self.auto_inject):
            sl.addWidget(cb)

        srow = QHBoxLayout()
        srow.addWidget(QLabel("最近"))
        self.recent_n = QSpinBox(); self.recent_n.setRange(0, 20); self.recent_n.setValue(3)
        srow.addWidget(self.recent_n)
        srow.addWidget(QLabel("章用详细尾段(每段约 300 字),其它章节只用摘要"))
        srow.addStretch()
        srow.addWidget(QLabel("每条摘要长度上限:"))
        self.summary_len = QSpinBox(); self.summary_len.setRange(30, 300); self.summary_len.setValue(80)
        srow.addWidget(self.summary_len); srow.addWidget(QLabel("字"))
        sl.addLayout(srow)
        layout.addWidget(st_box)

        # ---- 角色档案 ----
        cbox = QGroupBox("角色档案 (人设/状态/关系)")
        cl = QVBoxLayout(cbox)
        cbtns = QHBoxLayout()
        self.btn_extract_chars = QPushButton("✨ 从最新章节提取/更新角色")
        self.btn_clear_chars = QPushButton("清空")
        cbtns.addWidget(self.btn_extract_chars); cbtns.addWidget(self.btn_clear_chars)
        cbtns.addStretch()
        cl.addLayout(cbtns)
        self.chars_edit = QPlainTextEdit()
        self.chars_edit.setMinimumHeight(140)
        self.chars_edit.setPlaceholderText(
            "格式:【角色名】外貌:xxx;性格:xxx;当前状态:xxx;关系:xxx\n"
            "可手动编辑,也可点上面按钮 AI 自动提取。")
        cl.addWidget(self.chars_edit)
        layout.addWidget(cbox)

        # ---- 章节摘要 ----
        sbox = QGroupBox("章节摘要 (每章一行,自动随章节生成)")
        sml = QVBoxLayout(sbox)
        sbtns = QHBoxLayout()
        self.btn_gen_all_sum = QPushButton("✨ 一键补齐所有缺失摘要")
        self.btn_gen_cur_sum = QPushButton("只生成选中章节的摘要")
        self.btn_clear_sum = QPushButton("清空")
        for b in (self.btn_gen_all_sum, self.btn_gen_cur_sum, self.btn_clear_sum):
            sbtns.addWidget(b)
        sbtns.addStretch()
        sml.addLayout(sbtns)
        self.summaries_edit = QPlainTextEdit()
        self.summaries_edit.setMinimumHeight(180)
        self.summaries_edit.setPlaceholderText(
            "每章一行,格式:第N章 标题 :: 摘要内容\n"
            "AI 写完一章会自动追加一行。也可手动编辑。")
        self.summaries_edit.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 12px;")
        sml.addWidget(self.summaries_edit)
        layout.addWidget(sbox)

        # ---- 长期记忆 ----
        ltbox = QGroupBox("长期记忆 (伏笔 / 重要物品 / 关键关系 / 隐藏设定)")
        ll = QVBoxLayout(ltbox)
        ltbtns = QHBoxLayout()
        self.btn_extract_lt = QPushButton("✨ AI 从最新章节提取长期记忆")
        self.btn_clear_lt = QPushButton("清空")
        ltbtns.addWidget(self.btn_extract_lt); ltbtns.addWidget(self.btn_clear_lt)
        ltbtns.addStretch()
        ll.addLayout(ltbtns)
        self.long_term_edit = QPlainTextEdit()
        self.long_term_edit.setMinimumHeight(120)
        self.long_term_edit.setPlaceholderText(
            "每行一条。例如:\n"
            "- 玉佩:祖母传给男主(第3章)\n"
            "- 女主白天/夜晚双重身份未被识破(全文核心)\n"
            "- 苏小雨暗恋男主(第5章)")
        ll.addWidget(self.long_term_edit)
        layout.addWidget(ltbox)

        # ---- 注入预览 ----
        pvbox = QGroupBox("注入预览 (实际会随提示词一起发给 AI)")
        pvl = QVBoxLayout(pvbox)
        prow = QHBoxLayout()
        self.btn_preview = QPushButton("🔍 刷新预览")
        prow.addWidget(self.btn_preview); prow.addStretch()
        info = QLabel("(下次生成章节时会自动注入这段内容)")
        info.setStyleSheet("color: #888;")
        prow.addWidget(info)
        pvl.addLayout(prow)
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setStyleSheet(
            "background: #f8f8f8; font-family: 'Microsoft YaHei'; font-size: 12px; color: #333;")
        self.preview_edit.setMinimumHeight(180)
        pvl.addWidget(self.preview_edit)
        layout.addWidget(pvbox)

        layout.addStretch()

    def update_progress(self, text, level="info"):
        """更新一键生成的进度显示"""
        colors = {
            "info": ("#666", "#f4f4f4"),
            "running": ("white", "#1a4480"),
            "success": ("white", "#28a745"),
            "error": ("white", "#cc3333"),
        }
        fg, bg = colors.get(level, colors["info"])
        self.full_memory_progress.setText(text)
        self.full_memory_progress.setStyleSheet(
            f"padding: 6px 10px; background: {bg}; color: {fg}; "
            f"border-radius: 3px; font-weight: bold;")

    def parse_summaries(self):
        """从 summaries_edit 解析出 {ch_num: summary} 字典"""
        result = {}
        for line in self.summaries_edit.toPlainText().splitlines():
            line = line.strip()
            if not line: continue
            # 匹配:第N章 任意标题 :: 摘要 ,或 第N章 :: 摘要
            m = re.match(r'^第\s*(\d+)\s*章[^:]*?::\s*(.+)$', line)
            if m:
                result[int(m.group(1))] = m.group(2).strip()
        return result

    def append_summary(self, ch_num, ch_title, summary):
        """追加或更新一章的摘要"""
        sums = self.parse_summaries()
        sums[ch_num] = summary.strip().replace('\n', ' ')
        # 重排序
        lines = []
        for n in sorted(sums.keys()):
            lines.append(f"第{n}章 :: {sums[n]}")
        self.summaries_edit.setPlainText("\n".join(lines))





# =====================================================================
# B / C / D 新增模块:Canon 设定守护 + 多维自鞭策 + 技能库
# =====================================================================

# 内置出厂技能(用户可在 UI 里增删)
DEFAULT_SKILLS = [
    {
        "name": "战斗扩写",
        "when": "manual",
        "trigger_pattern": "",
        "prompt": (
            "请把下面这段战斗描写扩写到 2500 字以上,要求:\n"
            "1. 重点写招式细节、心理博弈、攻防回合,不要流水账\n"
            "2. 加入感官描写(刀光、风声、血腥气、震感)\n"
            "3. 节奏先紧后缓,结尾留余韵\n"
            "4. 保持原文人设、世界观,不要新增角色\n\n"
            "原文:\n{content}\n\n"
            "请直接输出扩写后的完整段落,不要任何前后缀。"
        ),
        "target": "current_chapter",
        "enabled": True,
    },
    {
        "name": "对话润色",
        "when": "manual",
        "trigger_pattern": "",
        "prompt": (
            "请把下面文本中的对话部分改得更有人物个性,要求:\n"
            "1. 不同角色说话风格明显区分(语气、用词、口头禅)\n"
            "2. 减少陈述,增加潜台词\n"
            "3. 不要改动情节,只改对话\n\n"
            "原文:\n{content}\n\n"
            "请直接输出修改后的完整版本。"
        ),
        "target": "selected_text",
        "enabled": True,
    },
    {
        "name": "节奏诊断",
        "when": "after_chapter_generation",
        "trigger_pattern": "",
        "prompt": (
            "请评估这章的节奏,从开局/中段/结尾分别 1-10 打分,并给出 30 字内的总评。\n\n"
            "章节:\n{content}\n\n"
            "格式:开局X分 中段X分 结尾X分。总评:xxx"
        ),
        "target": "log_only",
        "enabled": False,  # 默认关,有需要再开
    },
    {
        "name": "战斗扩写(自动触发)",
        "when": "auto_match",
        "trigger_pattern": "战斗|交手|出招|对决|厮杀|拔剑|挥刀|对峙",
        "prompt": (
            "这章出现了战斗场面。请对下面的战斗片段进行扩写润色,要求:\n"
            "1. 丰富招式细节和攻防节奏,不要流水账\n"
            "2. 加入人物心理博弈和感官描写\n"
            "3. 保持原文情节走向不变,不得新增/删除角色\n\n"
            "原文:\n{content}\n\n"
            "请直接输出扩写后的完整版本。"
        ),
        "target": "log_only",  # 默认 log_only,用户可改为 current_chapter
        "enabled": False,       # 默认关,开启后只要章节含战斗词就自动触发
    },
]


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

        # 开关行
        crow = QHBoxLayout()
        self.chk_inject = QCheckBox("写章节前自动注入 Canon 约束")
        self.chk_inject.setChecked(True)
        self.chk_audit = QCheckBox("写完后自动稽核(高严重度违反 → 触发死磕重写)")
        self.chk_audit.setChecked(True)
        self.chk_extract = QCheckBox("写完后自动从章节抽取新 Canon")
        self.chk_extract.setChecked(True)
        crow.addWidget(self.chk_inject); crow.addWidget(self.chk_audit)
        crow.addWidget(self.chk_extract); crow.addStretch()
        layout.addLayout(crow)

        # Canon 文本编辑区(简单方便,JSON 内部表达,UI 是结构化文本)
        # 行格式:[L|E][severity:H/M/L] key = value (chN)
        # 例:  [L][H] 林晚晚.身份 = 豪门夫人 + 夜市烤串摊主 (ch1)
        gbox = QGroupBox("Canon 设定档(锁定项 + 演化项)")
        glay = QVBoxLayout(gbox)

        legend = QLabel(
            "格式:[L 锁定 / E 演化][H 高 / M 中 / L 低] 键 = 值 (chN)\n"
            "示例:[L][H] 林晚晚.年龄 = 25 (ch1)\n"
            "      [E][M] 顾砚深.修为 = 金丹中期 (ch7)")
        legend.setStyleSheet("color: #888; font-size: 11px;")
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
            "background:#1a73e8;color:white;padding:6px 12px;font-weight:bold;border-radius:3px;")
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



# 各 AI 网站的选择器档案
# 每家 DOM 不同,这里只列经验上比较稳的,跑不通时可微调
SITE_PROFILES = {
    "chatgpt.com": {
        "name": "ChatGPT",
        # 输入框:优先 #prompt-textarea(标准),兜底 contenteditable(ProseMirror)
        "input": '#prompt-textarea, div[contenteditable="true"][role="textbox"], textarea',
        # 发送按钮:data-testid + aria-label 双兜底(中英文)
        "send_btn": (
            'button[data-testid="send-button"], '
            'button[aria-label*="Send" i], '
            'button[aria-label*="发送" i]'
        ),
        # AI 回复:assistant 角色容器(镜像站也大都遵循)
        "response": 'div[data-message-author-role="assistant"]',
        # 停止按钮:中英文
        "stop_btn": (
            'button[data-testid="stop-button"], '
            'button[aria-label*="Stop" i], '
            'button[aria-label*="停止" i]'
        ),
    },
    "gpt.aimonkey.plus": {
        "name": "ChatGPT镜像(aimonkey)",
        # 输入框:按优先级三档兜底
        #   1. #prompt-textarea (官方 ChatGPT 同款 ID)
        #   2. div.ProseMirror (旧版 ProseMirror 编辑器)
        #   3. div[contenteditable="true"] (通用 contenteditable)
        #   4. textarea (纯 textarea 降级)
        "input": (
            '#prompt-textarea, '
            'div.ProseMirror[contenteditable="true"], '
            'div[contenteditable="true"][role="textbox"], '
            'div[contenteditable="true"], '
            'textarea'
        ),
        # 发送按钮:五档兜底(镜像站可能改掉 aria-label 文字或去掉 data-testid)
        "send_btn": (
            'button[data-testid="send-button"], '
            'button[aria-label*="发送"], '
            'button[aria-label*="Send" i], '
            'button[aria-label*="submit" i], '
            'form button[type="submit"]'
        ),
        # 回复区:四档兜底,优先 markdown 精准层,最后降到整个 assistant 容器
        "response": (
            'div[data-message-author-role="assistant"] div.markdown, '
            'div[data-message-author-role="assistant"] .prose, '
            'div[data-message-author-role="assistant"] .markdown-content, '
            'div[data-message-author-role="assistant"]'
        ),
        "stop_btn": (
            'button[data-testid="stop-button"], '
            'button[aria-label*="停止"], '
            'button[aria-label*="Stop" i]'
        ),
        # 标记此站点启用 TamperMonkey bridge 模式(localStorage 中继)
        "tm_bridge": True,
    },
    "chat.openai.com": {
        "name": "ChatGPT (旧域名)",
        "input": '#prompt-textarea, div[contenteditable="true"][role="textbox"], textarea',
        "send_btn": (
            'button[data-testid="send-button"], '
            'button[aria-label*="Send" i], '
            'button[aria-label*="发送" i]'
        ),
        "response": 'div[data-message-author-role="assistant"]',
        "stop_btn": (
            'button[data-testid="stop-button"], '
            'button[aria-label*="Stop" i], '
            'button[aria-label*="停止" i]'
        ),
    },
    "chat.deepseek.com": {
        "name": "DeepSeek",
        "input": 'textarea',
        # `:has(svg)` 在现代 Chrome 的 querySelector 里原生支持(2022 后)
        "send_btn": 'div[role="button"]:has(svg)',
        "response": 'div.ds-markdown, [class*="markdown-body"]',
        # 标准 CSS 不支持 :has-text,改用 aria-label
        "stop_btn": 'div[role="button"][aria-label*="停止"]',
    },
    "doubao.com": {
        "name": "豆包",
        "input": 'textarea, div[contenteditable="true"]',
        "send_btn": 'button[data-testid*="send"], button[aria-label*="发送"]',
        "response": '[data-testid*="message_text"], [class*="message-content"]',
        "stop_btn": 'button[aria-label*="停止"]',
    },
    "gemini.google.com": {
        "name": "Gemini",
        "input": 'rich-textarea div[contenteditable="true"], textarea',
        "send_btn": 'button[aria-label*="Send"], button[aria-label*="发送"]',
        "response": 'message-content, .model-response-text',
        "stop_btn": 'button[aria-label*="Stop"]',
    },
    "yuanbao.tencent.com": {
        "name": "元宝",
        "input": 'textarea, div[contenteditable="true"]',
        "send_btn": 'button[class*="send"], a[class*="send"]',
        "response": '[class*="agent-chat"], [class*="markdown"]',
        "stop_btn": 'button[class*="stop"]',
    },
    "_default": {
        "name": "通用",
        "input": 'textarea, div[contenteditable="true"], input[type="text"]',
        "send_btn": ('button[data-testid*="send"], button[aria-label*="send" i], '
                     'button[aria-label*="发送"], button:has(svg[aria-label*="send" i])'),
        "response": ('[class*="markdown"], [class*="message-content"], '
                     '[data-message-author-role="assistant"]'),
        "stop_btn": 'button[aria-label*="stop" i], button[aria-label*="停止"]',
    },
}


def _profile_for_url(url):
    """根据 URL 返回选择器档案"""
    for host, prof in SITE_PROFILES.items():
        if host != "_default" and host in (url or ""):
            return prof
    return SITE_PROFILES["_default"]


class BrowserWorker(QObject):
    """
    在独立线程里跑 Selenium,挂载真实 Chrome/Edge 浏览器。
    主线程通过 submit() 投递任务,通过信号接收日志/回复/状态变化。

    三种启动模式(由 channel 参数选择):
      - "chrome"  → attach 模式:自动启动调试 Chrome(--remote-debugging-port=9222)再 attach。
                    最稳:与浏览器解耦,Chrome 崩了 driver 不会一起死。
      - "msedge"  → standalone Edge,自带 profile。
      - 其它(None / "chromium") → standalone Chrome,自带 profile。
    """
    log_signal = pyqtSignal(str, str)            # message, level
    response_received = pyqtSignal(str, str)     # task_id, content
    status_signal = pyqtSignal(str)              # idle / busy / starting / stopped / error
    started = pyqtSignal()                       # 浏览器就绪

    DEBUG_PORT = 9222

    def __init__(self):
        super().__init__()
        self.task_queue = queue.Queue()
        self.thread = None
        self._stop = threading.Event()
        self._browser_ready = threading.Event()
        self.user_data_dir = str(Path.home() / "NovelAI_Browser_Data")
        Path(self.user_data_dir).mkdir(exist_ok=True)
        self.channel = None
        self.driver = None
        # 用于"内容稳定即视为回复完成"的等待窗口(秒)
        self.stable_wait = 4
        self.max_wait = 240  # 单次最长等待 4 分钟

    # ============ 主线程调用接口 ============
    def start(self, channel=None):
        if self.thread and self.thread.is_alive():
            self.log_signal.emit("浏览器已在运行", "warn")
            return
        if not SELENIUM_AVAILABLE:
            self.log_signal.emit(
                "未安装 Selenium。请运行:\n"
                "  pip install -U selenium\n"
                "(selenium 4.6+ 自动管理 chromedriver,无需单独装)", "error")
            return
        self.channel = channel
        self._stop.clear()
        self._browser_ready.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.status_signal.emit("starting")

    def stop(self):
        self._stop.set()
        # 投空任务唤醒队列
        self.task_queue.put({"action": "_quit"})

    def submit(self, task):
        """提交任务。task: {'action': 'navigate'|'send_prompt'|'just_grab', ...}"""
        self.task_queue.put(task)

    def is_ready(self):
        return self._browser_ready.is_set()

    # ============ Chrome 探测与启动辅助 ============
    @staticmethod
    def _find_chrome_exe():
        """探测 Chrome 可执行文件路径(Windows / macOS / Linux)"""
        candidates = []
        if sys.platform == "win32":
            for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                       os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                       os.environ.get("LocalAppData", "")):
                if pf:
                    candidates.append(Path(pf) / "Google/Chrome/Application/chrome.exe")
        elif sys.platform == "darwin":
            candidates.append(Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        else:
            for p in ("/usr/bin/google-chrome", "/usr/bin/chromium-browser",
                      "/usr/bin/chromium", "/snap/bin/chromium"):
                candidates.append(Path(p))
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    @staticmethod
    def _find_edge_exe():
        candidates = []
        if sys.platform == "win32":
            for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                       os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
                candidates.append(Path(pf) / "Microsoft/Edge/Application/msedge.exe")
        elif sys.platform == "darwin":
            candidates.append(Path(
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))
        else:
            candidates.append(Path("/usr/bin/microsoft-edge"))
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    @staticmethod
    def _port_in_use(port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            return s.connect_ex(("127.0.0.1", int(port))) == 0
        finally:
            s.close()

    @staticmethod
    def _profile_locked(profile_dir):
        """检测 user-data-dir 是否被另一个 Chrome 占用"""
        p = Path(profile_dir)
        if not p.exists():
            return False
        for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            f = p / lock
            if f.exists() or f.is_symlink():
                return True
        return False

    def _launch_debug_chrome(self, port, user_data_dir):
        """
        启动一个带远程调试端口的 Chrome 子进程。
        与本程序解耦,即使 driver 挂了 Chrome 还在,反之亦然。
        """
        if self._port_in_use(port):
            self.log_signal.emit(
                f"端口 {port} 已被占用 —— 直接 attach 现有调试 Chrome", "info")
            return  # 已有调试 Chrome,直接 attach 即可

        chrome_path = self._find_chrome_exe()
        if not chrome_path:
            raise RuntimeError(
                "找不到 Chrome 可执行文件。\n"
                "请确认已安装 Google Chrome,或改用「Chromium 自带」(standalone)模式。")

        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        if self._profile_locked(user_data_dir):
            raise RuntimeError(
                f"Profile 目录被锁定:{user_data_dir}\n"
                f"请关闭所有使用该 profile 的 Chrome,或删除目录里的 Singleton* 文件。")

        cmd = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
        subprocess.Popen(cmd, **kwargs)
        self.log_signal.emit(f"已派发调试 Chrome 子进程,端口 {port}", "info")

        # 最长等 5 秒,等端口监听起来
        for _ in range(10):
            time.sleep(0.5)
            if self._port_in_use(port):
                return
        raise RuntimeError(
            f"调试 Chrome 启动后端口 {port} 5 秒内未监听 —— 可能被防火墙挡了或参数被忽略")

    @staticmethod
    def _diagnose(msg):
        m = (msg or "").lower()
        if "session not created" in m and "chrome" in m:
            return ("【诊断】Chrome 启动后立刻退出。常见原因:\n"
                    "  1. 同 profile 已有 Chrome 运行 → 关掉所有 Chrome 重试\n"
                    "  2. ChromeDriver 与 Chrome 版本不匹配 → pip install -U selenium\n"
                    "  3. profile 目录被锁 → 删除 ~/NovelAI_Browser_Data 里的 Singleton* 文件\n"
                    "✅ 推荐:把内核切成「系统 Chrome」(自动起调试 Chrome 后 attach,最稳)")
        if "chrome not reachable" in m:
            return "【诊断】无法连接 Chrome(端口不对或浏览器已关)"
        if "chromedriver" in m and ("version" in m or "mismatch" in m):
            return "【诊断】ChromeDriver 版本不匹配。执行:pip install -U selenium"
        if "no such file" in m or "not found" in m or "cannot find" in m:
            return "【诊断】找不到浏览器可执行文件,请确认 Chrome / Edge 已安装"
        return "【诊断】未知错误。建议:关闭所有 Chrome 窗口后重试,或换 attach 模式"

    # ============ Worker 后台主循环 ============
    def _run(self):
        try:
            self._launch_driver()
            self._browser_ready.set()
            self.started.emit()
            self.log_signal.emit(
                f"真实浏览器已就绪 (channel={self.channel or 'chromium'}),"
                f"用户数据目录:{self.user_data_dir}", "success")
            self.status_signal.emit("idle")

            while not self._stop.is_set():
                try:
                    task = self.task_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if task.get("action") == "_quit":
                    break
                self._handle(task)
        except Exception as e:
            self.log_signal.emit(f"浏览器异常:{e}", "error")
            self.status_signal.emit("error")
        finally:
            self._teardown_driver()
            self.status_signal.emit("stopped")
            self.log_signal.emit("浏览器已关闭", "info")

    def _launch_driver(self):
        """根据 channel 选择启动方式"""
        ch = self.channel
        if ch == "msedge":
            if EdgeOptions is None:
                raise RuntimeError("当前 selenium 不支持 Edge,请升级:pip install -U selenium")
            opts = EdgeOptions()
            edge_path = self._find_edge_exe()
            if edge_path:
                opts.binary_location = edge_path
            opts.add_argument(f"--user-data-dir={self.user_data_dir}_edge")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            self.log_signal.emit("→ Edge standalone 模式", "info")
            try:
                self.driver = webdriver.Edge(options=opts)
            except Exception as e:
                raise RuntimeError(f"{e}\n\n{self._diagnose(str(e))}")

        elif ch == "chrome":
            # attach 模式 + 自动起调试 Chrome
            self.log_signal.emit("→ Chrome attach 模式(先起调试 Chrome 再 attach)", "info")
            self._launch_debug_chrome(self.DEBUG_PORT, self.user_data_dir)
            opts = ChromeOptions()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.DEBUG_PORT}")
            try:
                self.driver = webdriver.Chrome(options=opts)
            except Exception as e:
                raise RuntimeError(f"{e}\n\n{self._diagnose(str(e))}")

        else:
            # standalone Chromium
            opts = ChromeOptions()
            chrome_path = self._find_chrome_exe()
            if chrome_path:
                opts.binary_location = chrome_path
            if self._profile_locked(self.user_data_dir):
                raise RuntimeError(
                    f"Profile 已被另一个 Chrome 占用:{self.user_data_dir}\n"
                    "请关闭所有 Chrome 窗口,或换成「系统 Chrome」(attach 模式)")
            opts.add_argument(f"--user-data-dir={self.user_data_dir}")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            self.log_signal.emit("→ Chromium standalone 模式", "info")
            try:
                self.driver = webdriver.Chrome(options=opts)
            except Exception as e:
                raise RuntimeError(f"{e}\n\n{self._diagnose(str(e))}")

        # 反爬:抹掉 navigator.webdriver
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            })
        except Exception:
            pass

    def _teardown_driver(self):
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _is_alive(self):
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    # ============ 任务派发 ============
    def _handle(self, task):
        action = task.get("action")
        try:
            self.status_signal.emit("busy")
            if action == "navigate":
                self._goto(task["url"])
            elif action == "goto":
                # E 模块:对话槽切换导航(同 navigate,alias 更清晰)
                self._goto(task["url"])
                self.log_signal.emit(
                    f"已导航到:{task['url'][:80]}", "info")
            elif action == "send_prompt":
                self._send_prompt(task)
            elif action == "just_grab":
                prof = _profile_for_url(self._current_url())
                self.response_received.emit(
                    task.get("task_id", ""), self._grab_last_response(prof))
            self.status_signal.emit("idle")
        except Exception as e:
            self.log_signal.emit(f"任务执行失败:{e}", "error")
            self.status_signal.emit("idle")

    def _current_url(self):
        try:
            return self.driver.current_url or ""
        except Exception:
            return ""

    def _goto(self, url):
        if not self._is_alive():
            return
        cur = self._current_url()
        # attach 模式下尽量保留用户已有标签 —— 同站点直接复用,异站点开新标签
        if self.channel == "chrome" and cur and url and url.split("?")[0] != cur.split("?")[0]:
            try:
                from urllib.parse import urlparse
                if urlparse(url).hostname not in (cur or ""):
                    self.driver.execute_script(f"window.open({json.dumps(url)},'_blank');")
                    handles = self.driver.window_handles
                    self.driver.switch_to.window(handles[-1])
                    self.log_signal.emit(f"已在新标签打开:{url}", "info")
                    return
            except Exception:
                pass
        self.driver.get(url)
        self.log_signal.emit(f"已访问:{url}", "info")

    # ============ 核心:发送提示词 + 等回复 ============
    def _send_prompt(self, task):
        prompt = task["prompt"]
        task_id = task.get("task_id", "")
        target_url = task.get("url")

        if target_url and target_url not in self._current_url():
            self._goto(target_url)
            time.sleep(1.5)

        prof = _profile_for_url(self._current_url())
        self.log_signal.emit(f"使用档案:{prof['name']}", "info")

        # 1) 等输入框出现(最长 15s)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._stop.is_set(): return
            try:
                found = self.driver.execute_script(
                    f"return !!document.querySelector({json.dumps(prof['input'])});")
                if found:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            self.log_signal.emit("等待输入框超时,请确认网页已加载且已登录", "error")
            self.response_received.emit(task_id, "")
            return

        prev_count = self._count_responses(prof)

        # 发送前清除 TamperMonkey bridge 旧数据,防止读到上一轮回复
        if prof.get("tm_bridge"):
            try:
                self.driver.execute_script(
                    "localStorage.removeItem('__novelai_reply');")
            except Exception:
                pass

        # 2) 注入文本(三档兜底:textarea native setter / contenteditable execCommand / innerHTML)
        if not self._inject_prompt(prof["input"], prompt):
            self.log_signal.emit("文本注入失败", "error")
            self.response_received.emit(task_id, "")
            return

        # 模拟人类停顿(给 React 一点时间 setState)
        time.sleep(0.3)

        # 3) 点发送(优先 Enter,失败再点按钮 + 兜底 forced click)
        if not self._dispatch_send(prof["send_btn"]):
            self.log_signal.emit("回车与发送按钮均失败,放弃本次任务", "error")
            self.response_received.emit(task_id, "")
            return

        self.log_signal.emit(
            f"提示词已发送 ({len(prompt)} 字符),等待 AI 回复...", "info")

        # 4) 等新回复出现(对话条数 +1)
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._stop.is_set(): return
            if self._count_responses(prof) > prev_count:
                break
            time.sleep(0.5)
        else:
            self.log_signal.emit(
                "未检测到新回复条目,可能选择器需调整(到 SITE_PROFILES 微调)", "warn")

        # 5) 等内容稳定 N 秒
        last_text = ""
        last_change = time.time()
        start = time.time()
        while time.time() - start < self.max_wait:
            if self._stop.is_set(): return
            cur = self._grab_last_response(prof)
            if cur and cur == last_text:
                if time.time() - last_change >= self.stable_wait:
                    break
            else:
                last_text = cur
                last_change = time.time()
            elapsed = int(time.time() - start)
            if elapsed and elapsed % 5 == 0:
                self.log_signal.emit(
                    f"AI 生成中...已 {elapsed}s,当前 {len(cur or '')} 字符", "info")
            time.sleep(1)

        if last_text:
            self.log_signal.emit(f"回复完成,共 {len(last_text)} 字符", "success")
        else:
            self.log_signal.emit(
                "回复抓取为空,可能选择器需调整(到 SITE_PROFILES 微调)", "warn")
        self.response_received.emit(task_id, last_text)

    # ---------- 文本注入(借鉴 GPTWebController 的 execCommand 路径)----------
    def _inject_prompt(self, input_selector, text):
        """
        注入策略(按优先级依次尝试,成功即返回 True):
          A0. Clipboard API  ── 写 text 到剪贴板 → Ctrl+V(对镜像站/ProseMirror 最稳)
          A1. CDP Input.insertText ── focus+清空后用 DevTools Protocol 打字
          B.  React native setter ── textarea/input 的 value setter + input event
          C.  execCommand ── 通用兜底,React 可能不响应但总有机会触发
        """
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains

        sel = json.dumps(input_selector)
        text_js = json.dumps(text)

        # 判断元素类型
        try:
            tag_info = self.driver.execute_script(f"""
                const box = document.querySelector({sel});
                if (!box) return null;
                return {{
                    tag: (box.tagName || '').toUpperCase(),
                    ce:  box.isContentEditable,
                    pm:  box.classList.contains('ProseMirror') || box.id === 'prompt-textarea',
                    vis: !!(box.offsetWidth || box.offsetHeight)
                }};
            """)
        except Exception:
            tag_info = None

        if tag_info is None:
            self.log_signal.emit("找不到输入框元素", "warn")
            return False

        is_pm  = tag_info.get("pm", False)
        is_ce  = tag_info.get("ce", False)
        tag    = tag_info.get("tag", "")
        is_div = (tag == "DIV") or is_pm or is_ce

        # ── A0. Clipboard API + Ctrl+V (最可靠,对所有 React contenteditable 站点)
        if is_div:
            try:
                # 1) 把文本写进剪贴板(navigator.clipboard 需要 https,所以用 execCommand copy)
                copy_ok = self.driver.execute_script(f"""
                    const ta = document.createElement('textarea');
                    ta.value = {text_js};
                    ta.style.position = 'fixed';
                    ta.style.opacity  = '0';
                    document.body.appendChild(ta);
                    ta.focus(); ta.select();
                    const ok = document.execCommand('copy');
                    document.body.removeChild(ta);
                    return ok;
                """)
                if copy_ok:
                    # 2) focus 编辑器 + 全选删除旧内容
                    self.driver.execute_script(f"""
                        const box = document.querySelector({sel});
                        box.focus();
                        const s = window.getSelection();
                        s.selectAllChildren(box);
                        s.deleteFromDocument();
                        box.focus();
                    """)
                    import time as _t; _t.sleep(0.1)
                    # 3) Ctrl+V 粘贴
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    import time as _t2; _t2.sleep(0.3)
                    # 4) 验证
                    injected = self.driver.execute_script(f"""
                        const box = document.querySelector({sel});
                        return !!(box && (box.innerText || box.textContent || '').trim());
                    """)
                    if injected:
                        self.log_signal.emit("✓ 剪贴板+Ctrl+V 注入成功", "info")
                        return True
                    self.log_signal.emit("剪贴板注入后内容为空,尝试CDP", "warn")
            except Exception as e:
                self.log_signal.emit(f"剪贴板注入异常:{e},尝试CDP", "warn")

        # ── A1. ProseMirror —— JS清空 + CDP Input.insertText
        if is_div:
            try:
                import time as _time
                # 1. 用JS清空编辑器(不用Ctrl+A避免触发浏览器快捷键)
                self.driver.execute_script(f"""
                    const box = document.querySelector({sel});
                    if (!box) return;
                    box.focus();
                    // 清空ProseMirror内容
                    const sel2 = window.getSelection();
                    sel2.selectAllChildren(box);
                    sel2.deleteFromDocument();
                    // 确保光标在编辑器内
                    box.focus();
                """)
                _time.sleep(0.15)
                # 2. CDP Input.insertText 直接注入文本
                self.driver.execute_cdp_cmd('Input.insertText', {'text': text})
                _time.sleep(0.3)
                # 3. 验证注入是否成功
                injected = self.driver.execute_script(f"""
                    const box = document.querySelector({sel});
                    return !!(box && (box.innerText || box.textContent || '').trim());
                """)
                if injected:
                    return True
                self.log_signal.emit("CDP注入后内容为空，尝试JS兜底", "warn")
            except Exception as e:
                self.log_signal.emit(f"CDP注入失败:{e}，尝试JS兜底", "warn")
        # B. textarea/input —— React native setter
        if tag in ("TEXTAREA", "INPUT"):
            try:
                js = f"""
                const box = document.querySelector({sel});
                box.focus();
                const proto = ('{tag}' === 'TEXTAREA')
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(box, {text_js});
                box.dispatchEvent(new Event('input', {{bubbles:true}}));
                box.dispatchEvent(new Event('change', {{bubbles:true}}));
                return 'OK_TEXTAREA';
                """
                r = self.driver.execute_script(js)
                if r == 'OK_TEXTAREA':
                    return True
            except Exception:
                pass

        # C. execCommand 兜底
        try:
            js = f"""
            const box = document.querySelector({sel});
            if (!box) return 'NO_BOX';
            box.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            if (document.execCommand('insertText', false, {text_js})) return 'OK_EXEC';
            box.innerHTML = '';
            const p = document.createElement('p');
            p.textContent = {text_js};
            box.appendChild(p);
            box.dispatchEvent(new InputEvent('input',
                {{bubbles:true, data:{text_js}, inputType:'insertText'}}));
            return 'OK_FALLBACK';
            """
            r = self.driver.execute_script(js)
            if r == "NO_BOX":
                return False
            if r == "OK_FALLBACK":
                self.log_signal.emit("退回innerHTML注入(React可能不响应)", "warn")
            return True
        except Exception as e:
            self.log_signal.emit(f"注入异常:{e}", "warn")
            return False

    # ---------- 发送派发(Enter / 按钮 / 兜底强点)----------
    def _dispatch_send(self, send_btn_selector):
        """
        优先级:
          1. 模拟在输入框按 Enter
          2. 等待发送按钮变可点(最多 10s),点它
          3. 兜底:无明显上传指示就强制 click(对付 React state 卡住)
        """
        # 1) Enter —— ProseMirror编辑器跳过(会换行),其他走Enter
        try:
            is_pm = self.driver.execute_script("""
                const el = document.activeElement;
                return el && (el.classList.contains('ProseMirror') ||
                              el.id === 'prompt-textarea');
            """)
            if not is_pm:
                self.driver.execute_script("""
                    const ev = new KeyboardEvent('keydown',
                        {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true});
                    const box = document.activeElement || document.body;
                    box.dispatchEvent(ev);
                """)
        except Exception:
            pass

        # 1.5) ProseMirror专用: 先尝试CDP触发提交事件
        try:
            self.driver.execute_script("""
                const btn = document.querySelector('[data-testid="send-button"]')
                         || document.querySelector('button[aria-label*="发送"]');
                if (btn) btn.click();
            """)
            time.sleep(0.5)
            # 如果页面出现新消息则成功
        except Exception:
            pass

        # 2) 等按钮可点(每 0.25s 轮询,最多 10s)
        sel = json.dumps(send_btn_selector)
        deadline = time.time() + 10
        while time.time() < deadline:
            if self._stop.is_set(): return False
            clicked = self.driver.execute_script(f"""
                const btn = document.querySelector({sel})
                         || document.querySelector('[data-testid="send-button"]')
                         || document.querySelector('button[aria-label*="发送" i]')
                         || document.querySelector('button[aria-label*="Send" i]')
                         || document.querySelector('form button[type="submit"]');
                if (!btn) return false;
                const ariaDis = (btn.getAttribute('aria-disabled') || '').toLowerCase();
                const cls = (typeof btn.className === 'string' ? btn.className : '').toLowerCase();
                const dis = btn.disabled
                         || ariaDis === 'true'
                         || cls.includes('disabled')
                         || cls.includes('inactive');
                if (!dis) {{ btn.click(); return true; }}
                return false;
            """)
            if clicked:
                return True
            time.sleep(0.25)

        # 3) 兜底强点(无上传中就信任视觉)
        forced = self.driver.execute_script(f"""
            const upScopes = document.querySelectorAll(
                'div[class*="attachment" i], div[class*="file-preview" i], ' +
                'form [class*="upload" i]'
            );
            let uploading = 0;
            upScopes.forEach(s => {{
                uploading += s.querySelectorAll(
                    'svg[class*="animate-spin" i], svg[class*="spinner" i], ' +
                    '[role="progressbar"], [class*="loading" i]'
                ).length;
            }});
            if (uploading > 0) return {{ok:false, reason:'uploading'}};
            const btn = document.querySelector({sel})
                     || document.querySelector('[data-testid="send-button"]')
                     || document.querySelector('button[aria-label*="发送" i]')
                     || document.querySelector('button[aria-label*="Send" i]')
                     || document.querySelector('form button[type="submit"]');
            if (!btn) return {{ok:false, reason:'no_btn'}};
            try {{ btn.click(); return {{ok:true, reason:'forced'}}; }}
            catch (e) {{ return {{ok:false, reason:'exc', err:String(e)}}; }}
        """) or {}
        if forced.get("ok"):
            self.log_signal.emit("⚡ 兜底:按钮 disabled 但无上传中,已强制点击", "warn")
            return True
        return False

    # ---------- 抓取/计数(用 querySelectorAll,跳过 selenium 的 CSS 解析)----------
    def _count_responses(self, prof):
        try:
            return int(self.driver.execute_script(
                f"return document.querySelectorAll({json.dumps(prof['response'])}).length;"
            ) or 0)
        except Exception:
            return 0

    def _grab_last_response(self, prof):
        """
        抓取最新 AI 回复文本。
        优先级:
          1. TamperMonkey bridge —— 如果档案有 tm_bridge=True,
             先读 localStorage.__novelai_reply(由 TM 脚本写入),
             有内容且时间戳在 60s 内就直接用,跳过 DOM 选择器。
          2. DOM 选择器 —— 标准路径。
        """
        # ── 1. TamperMonkey bridge
        if prof.get("tm_bridge"):
            try:
                bridge = self.driver.execute_script("""
                    try {
                        const raw = localStorage.getItem('__novelai_reply');
                        if (!raw) return null;
                        const obj = JSON.parse(raw);
                        if (!obj || !obj.text) return null;
                        // 60 秒内的数据才算有效
                        if (Date.now() - (obj.ts || 0) > 60000) return null;
                        return obj.text;
                    } catch(e) { return null; }
                """)
                if bridge and bridge.strip():
                    return bridge.strip()
            except Exception:
                pass  # bridge 不可用则降级到 DOM 选择器

        # ── 2. DOM 选择器(标准路径)
        try:
            return self.driver.execute_script(f"""
                const ns = document.querySelectorAll({json.dumps(prof['response'])});
                if (!ns.length) return '';
                const last = ns[ns.length - 1];
                return last.innerText || last.textContent || '';
            """) or ""
        except Exception:
            return ""

# =====================================================================
# 对话槽管理器(E 模块:随时换对话,自动同步记忆)
# =====================================================================

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


class GenerationControl(QWidget):
    """生成控制页(Selenium 模式 - 挂载真实浏览器)"""
    log_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("生成控制 — 挂载真实浏览器(Selenium 自动化)")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a4480;")
        layout.addWidget(title)

        # ---- 浏览器内核挂载(完整面板,日常工作的主入口)----
        bbox = QGroupBox("浏览器内核挂载")
        blay = QVBoxLayout(bbox)

        # 第 1 行:内核选择 + 启动 / 关闭
        b1 = QHBoxLayout()
        b1.addWidget(QLabel("内核:"))
        self.kernel_group = QButtonGroup(self)
        # 内核 0: standalone Chrome,自有 profile(简单,但同 profile 不能再开 Chrome)
        # 内核 1: attach 模式,自动起调试 Chrome 后 attach(最稳)
        # 内核 2: standalone Edge
        rb_chromium = QRadioButton("Chrome 独立(standalone)"); rb_chromium.setChecked(True)
        rb_chrome = QRadioButton("Chrome 调试(attach,推荐)")
        rb_edge = QRadioButton("系统 Edge")
        self.kernel_group.addButton(rb_chromium, 0)
        self.kernel_group.addButton(rb_chrome, 1)
        self.kernel_group.addButton(rb_edge, 2)
        for rb in (rb_chromium, rb_chrome, rb_edge):
            b1.addWidget(rb)
        b1.addStretch()
        self.btn_launch = QPushButton("🚀 启动浏览器(首次请登录)")
        self.btn_launch.setStyleSheet(
            "background:#1a73e8;color:white;padding:6px 14px;"
            "font-weight:bold;border-radius:3px;")
        self.btn_close = QPushButton("⛔ 关闭浏览器")
        self.btn_close.setEnabled(False)
        b1.addWidget(self.btn_launch); b1.addWidget(self.btn_close)
        blay.addLayout(b1)

        # 第 2 行:AI 网站 + URL + 访问 + 抓取
        b2 = QHBoxLayout()
        b2.addWidget(QLabel("AI 网站:"))
        self.site_combo = QComboBox()
        self.site_combo.addItems(list(AI_URLS.keys()))
        self.site_combo.setCurrentText("ChatGPT镜像")
        b2.addWidget(self.site_combo)
        b2.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit("https://gpt.aimonkey.plus/")
        b2.addWidget(self.url_input, 1)
        self.btn_go = QPushButton("访问")
        self.btn_grab = QPushButton("📋 抓取最后一条回复")
        b2.addWidget(self.btn_go); b2.addWidget(self.btn_grab)
        blay.addLayout(b2)

        # 第 3 行:状态指示
        self.status_label = QLabel("状态:未启动")
        self.status_label.setStyleSheet(
            "padding: 4px 10px; background: #eee; border-radius: 3px; color: #666;")
        blay.addWidget(self.status_label)

        layout.addWidget(bbox)

        # 联动:站点切换更新 URL
        self.site_combo.currentTextChanged.connect(
            lambda name: self.url_input.setText(AI_URLS.get(name, ""))
            if name in AI_URLS else None)

        # ---- 生成参数 ----
        gbox = QGroupBox("批量生成参数")
        glay = QVBoxLayout(gbox)
        crow = QHBoxLayout()
        self.btn_gen_three = QPushButton("生成黄金三章")
        self.btn_regen_three = QPushButton("不想要,重生成黄金三章")
        crow.addWidget(self.btn_gen_three); crow.addWidget(self.btn_regen_three)

        crow.addWidget(QLabel("连续生成:"))
        self.batch_count = QSpinBox()
        self.batch_count.setRange(1, 999); self.batch_count.setValue(15)
        crow.addWidget(self.batch_count)
        crow.addWidget(QLabel("章"))

        crow.addWidget(QLabel("字数死磕:"))
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 10); self.retry_count.setValue(3)
        crow.addWidget(self.retry_count)
        crow.addWidget(QLabel("次"))

        self.btn_start = QPushButton("▶ 开始连续生成")
        self.btn_pause = QPushButton("⏸ 暂停/停止")
        crow.addWidget(self.btn_start); crow.addWidget(self.btn_pause)
        crow.addStretch()
        glay.addLayout(crow)

        crow2 = QHBoxLayout()
        self.auto_save = QCheckBox("自动保存到 TXT")
        self.auto_save.setChecked(True)
        crow2.addWidget(self.auto_save)
        self.auto_grab = QCheckBox("自动抓取并回填(生成完即写入章节)")
        self.auto_grab.setChecked(True)
        crow2.addWidget(self.auto_grab)
        crow2.addStretch()
        self.btn_clear = QPushButton("清除日志")
        self.btn_clear.clicked.connect(self.clear_log)
        crow2.addWidget(self.btn_clear)
        glay.addLayout(crow2)

        # ---- C 模块:多维自鞭策 ----
        crit_box = QGroupBox("章节质量校验(写完后自动跑,任一不达标 → 触发死磕重写)")
        crit_lay = QHBoxLayout(crit_box)
        crit_lay.addWidget(QLabel("启用维度:"))
        self.chk_crit_words = QCheckBox("字数(默认开)")
        self.chk_crit_words.setChecked(True)
        self.chk_crit_hook = QCheckBox("章末钩子(瞬时,无 AI 调用)")
        self.chk_crit_hook.setChecked(True)
        self.chk_crit_canon = QCheckBox("Canon 稽核(1 次 AI 调用)")
        self.chk_crit_canon.setChecked(True)
        self.chk_crit_rhythm = QCheckBox("节奏分(1 次 AI 调用)")
        self.chk_crit_rhythm.setChecked(False)
        self.chk_crit_char = QCheckBox("人设分(1 次 AI 调用)")
        self.chk_crit_char.setChecked(False)
        for w in (self.chk_crit_words, self.chk_crit_hook,
                  self.chk_crit_canon, self.chk_crit_rhythm, self.chk_crit_char):
            crit_lay.addWidget(w)
        crit_lay.addStretch()
        glay.addWidget(crit_box)
        layout.addWidget(gbox)

        # ---- E 模块:对话槽管理 ----
        self.conv_switcher = ConversationSwitcher()
        # 保存当前按钮 & 切换按钮由 MainWindow 接管(需要访问 url_input / worker)
        layout.addWidget(self.conv_switcher)

        # ---- 日志区 ----
        log_box = QGroupBox("生成进度 / 自动化日志")
        ll = QVBoxLayout(log_box)
        self.log_edit = QPlainTextEdit(); self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 12px; background: #fafafa;")
        ll.addWidget(self.log_edit)
        layout.addWidget(log_box, 1)

        # 联动:站点切换更新 URL —— 已移到「创作设置」AI配置 区域内自带处理

        if not SELENIUM_AVAILABLE:
            self._append_log(
                "⚠ 未检测到 Selenium,无法挂载真实浏览器。\n"
                "请运行:  pip install -U selenium\n"
                "(selenium 4.6+ 自动管理 chromedriver)\n"
                "安装后重启本软件。", "error")

        self.log_signal.connect(self._append_log)

    def selected_kernel_channel(self):
        """0=Chrome 独立(standalone) / 1=Chrome 调试 attach / 2=系统 Edge"""
        idx = self.kernel_group.checkedId()
        if idx < 0:
            idx = 0
        return [None, "chrome", "msedge"][idx]

    def critique_config(self):
        """返回当前启用的章节校验维度"""
        return {
            "word_count": self.chk_crit_words.isChecked(),
            "hook":       self.chk_crit_hook.isChecked(),
            "canon":      self.chk_crit_canon.isChecked(),
            "rhythm":     self.chk_crit_rhythm.isChecked(),
            "character":  self.chk_crit_char.isChecked(),
        }

    def _append_log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = {"info": "ℹ", "success": "✓", "warn": "⚠", "error": "✗"}.get(level, "·")
        self.log_edit.appendPlainText(f"[{ts}] {prefix} {msg}")
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def log(self, msg, level="info"):
        self.log_signal.emit(msg, level)

    def clear_log(self):
        self.log_edit.clear()


# =====================================================================
# 七、封面生成页
# =====================================================================
class CoverGeneration(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        title = QLabel("小说封面生成")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a4480;")
        layout.addWidget(title)

        layout.addWidget(QLabel("封面描述(Prompt):"))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setMaximumHeight(150)
        self.desc_edit.setPlaceholderText(
            "例如:都市言情风格,女主侧脸特写,城市夜景背景,书名居中,"
            "霓虹灯氛围,高饱和度,杂志大片质感...")
        layout.addWidget(self.desc_edit)

        brow = QHBoxLayout()
        self.btn_gen_desc = QPushButton("AI生成封面描述")
        self.btn_gen_cover = QPushButton("生成封面图(打开AI画图网页)")
        self.btn_save_cover = QPushButton("保存封面")
        for b in (self.btn_gen_desc, self.btn_gen_cover, self.btn_save_cover):
            brow.addWidget(b)
        brow.addStretch()
        layout.addLayout(brow)

        self.preview = QLabel()
        self.preview.setMinimumSize(400, 500)
        self.preview.setStyleSheet(
            "background: white; border: 2px dashed #aaa; color: #888; font-size: 14px;")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setText("封面预览区\n\n请先生成封面描述,再生成封面图")
        layout.addWidget(self.preview, 1)


# =====================================================================
# 八、主窗口
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 写作工作台")
        self.resize(1280, 820)
        self.setStyleSheet(STYLESHEET)

        # 恢复上次窗口大小和位置
        from PyQt5.QtCore import QSettings
        _s = QSettings("NovelAI", "MainWindow")
        _geo = _s.value("geometry")
        if _geo:
            self.restoreGeometry(_geo)

        self.chapters = []
        self.current_chapter_index = -1
        self.project_dir = Path.home() / "NovelAI_Projects"
        self.project_dir.mkdir(exist_ok=True)
        self.current_project_file = None

        # 浏览器自动化 worker
        self.worker = BrowserWorker()
        # 批量生成状态
        self._batch_remaining = 0
        self._batch_paused = False
        # 当前任务的语义,用于把回复填到正确位置
        # 例如 {"target": "chapter_content"|"inspiration"|"chapter_outline"|..., "ch_num": 7}
        self._pending_task_target = None
        # 一键生成对话记忆的流水线状态
        # 列表元素:(step_name, arg)  step_name ∈ "summary"|"character"|"long_term"
        self._full_memory_pipeline = []
        self._full_memory_total = 0  # 总步数(用于显示进度)
        self._full_memory_running = False

        self._build_menu()
        self._build_ui()
        self._build_statusbar()
        self._connect_signals()
        self._connect_worker()
        self._init_demo_chapters()

        # ---- v7:模块化生成流水线 ----
        if WORKFLOW_AVAILABLE:
            _patch_main_window(self.__class__)       # 注入 _send_to_ai_with_callback
            self.workflow = GenerationWorkflow(self)
            self.workflow.setup_default_steps()
        else:
            self.workflow = None

        # ---- 寿元台账 + 长期伏笔(新增) ----
        if LIFESPAN_LOOPS_AVAILABLE:
            LifespanLoopsExtension.install(self)
            if self.tab_lifespan is not None:
                self.tab_lifespan.sync_from_mw()
                self.tab_lifespan.request_save.connect(self.save_project)
                self.tab_lifespan.request_log.connect(
                    lambda m, lv: self.tab_generation.log(m, lv))

        # ---- 研究报告出厂技能(新增) ----
        if RESEARCH_SKILLS_AVAILABLE:
            try:
                n_added = _install_research_skills(self.tab_skills)
                if n_added:
                    self.tab_generation.log(
                        f"📚 已加载研究报告出厂技能 {n_added} 条", "info")
            except Exception as e:
                self.tab_generation.log(
                    f"⚠ 研究报告技能装载失败:{e}", "warn")

        # ---- 工作流可视化 Tab(新增) ----
        # 必须在 workflow.setup_default_steps 之后,这样 register hooks 才能拿到完整 step 列表
        if WORKFLOW_PANEL_AVAILABLE and self.workflow is not None:
            self.tab_workflow = WorkflowPanel(mw=self)
            self.tab_workflow.request_log.connect(
                lambda m, lv: self.tab_generation.log(m, lv))
            # 插到「技能库」之后、「生成控制」之前
            insert_idx = self.tabs.indexOf(self.tab_generation)
            if insert_idx < 0:
                insert_idx = self.tabs.count()
            self.tabs.insertTab(insert_idx, self.tab_workflow, "工作流")

        # 恢复上次设置和项目数据
        # 先加载项目数据，再加载设置（QSettings优先级更高，覆盖项目文件中的旧设置）
        self._autoload()
        self.tab_settings.load_settings()

    def _connect_worker(self):
        self.worker.log_signal.connect(self.tab_generation.log_signal.emit)
        self.worker.status_signal.connect(self.update_browser_status)
        self.worker.response_received.connect(self._on_response_received)
        self.worker.started.connect(self._on_browser_started)

    def update_browser_status(self, status):
        """浏览器状态变化时由 BrowserWorker 信号调用 — 把状态显示在状态栏右侧 + 控制 close 按钮"""
        colors = {
            "idle":     ("#28a745", "空闲(就绪)"),
            "busy":     ("#ff9500", "繁忙(执行任务中)"),
            "starting": ("#666",    "启动中..."),
            "stopped":  ("#999",    "已停止"),
            "error":    ("#cc3333", "出错"),
        }
        color, text = colors.get(status, ("#666", str(status)))
        # 生成控制 Tab 顶部状态条
        self.tab_generation.status_label.setText(f"状态:{text}")
        self.tab_generation.status_label.setStyleSheet(
            f"padding: 4px 10px; background: {color}; color: white;"
            f"border-radius: 3px; font-weight: bold;")
        # 主窗口状态栏右侧显示
        if hasattr(self, "_status_indicator"):
            self._status_indicator.setText(f"● {text}")
            self._status_indicator.setStyleSheet(
                f"color: {color}; font-weight: bold; padding: 2px 8px;")
        # 启动 / 关闭 按钮状态切换
        if status == "idle":
            self.tab_generation.btn_launch.setEnabled(False)
            self.tab_generation.btn_close.setEnabled(True)
        elif status in ("stopped", "error"):
            self.tab_generation.btn_launch.setEnabled(True)
            self.tab_generation.btn_close.setEnabled(False)

    # ---- 菜单 ----
    def _build_menu(self):
        m = self.menuBar()
        fm = m.addMenu("文件(&F)")
        for txt, slot, sc in [
            ("新建项目", self.new_project, ""),
            ("打开项目", self.open_project, "Ctrl+O"),
            ("保存项目", self.save_project, "Ctrl+S"),
            (None, None, ""),
            ("退出", self.close, ""),
        ]:
            if txt is None:
                fm.addSeparator(); continue
            a = QAction(txt, self)
            if sc: a.setShortcut(sc)
            a.triggered.connect(slot)
            fm.addAction(a)

        sm = m.addMenu("设置(&S)")
        a = QAction("关于", self); a.triggered.connect(self.show_about)
        sm.addAction(a)

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        ml = QHBoxLayout(central)
        ml.setContentsMargins(8, 8, 8, 8); ml.setSpacing(8)

        # ---- 左侧 ----
        left = QWidget()
        left.setMaximumWidth(220); left.setMinimumWidth(180)
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("章节列表 (按Ctrl多选)"))
        self.chapter_list = QListWidget()
        self.chapter_list.itemClicked.connect(self._on_chapter_clicked)
        ll.addWidget(self.chapter_list, 1)

        bg = QGridLayout(); bg.setSpacing(4)
        for txt, slot, r, c in [
            ("新增章节", self.add_chapter, 0, 0),
            ("删除章节", self.delete_chapter, 0, 1),
            ("章节重命名", self.rename_chapter, 1, 0),
            ("新建空白创作", self.new_project, 1, 1),
            ("新建目录", self.new_directory, 2, 0),
            ("导入存档", self.open_project, 2, 1),
            ("返回上级目录", self.back_directory, 3, 0),
            ("解锁编辑", self.toggle_lock, 3, 1),
        ]:
            b = QPushButton(txt); b.clicked.connect(slot)
            bg.addWidget(b, r, c)
        ll.addLayout(bg)
        ml.addWidget(left)

        # ---- 右侧 Tab ----
        self.tabs = QTabWidget()
        self.tab_settings = CreationSettings()
        self.tab_outline = StoryOutline()
        self.tab_memory = DialogMemory()
        self.tab_canon = CanonGuard()
        # 寿元/伏笔(可选模块)
        if LIFESPAN_LOOPS_AVAILABLE:
            self.tab_lifespan = LifespanLoopsPanel(mw=self)
        else:
            self.tab_lifespan = None
        self.tab_skills = SkillLibrary()
        self.tab_generation = GenerationControl()
        self.tab_editor = ChapterEditor()
        self.tab_cover = CoverGeneration()
        # 工作流可视化(可选模块,放最后实例化,因为依赖 self.workflow 已就绪)
        # 这里先占位 None,真正的 WorkflowPanel 在 __init__ 末尾装配
        self.tab_workflow = None

        tab_list = [
            (self.tab_settings, "创作设置"),
            (self.tab_outline, "故事大纲"),
            (self.tab_memory, "对话记忆"),
            (self.tab_canon, "Canon 设定"),
        ]
        if self.tab_lifespan is not None:
            tab_list.append((self.tab_lifespan, "寿元/伏笔"))
        tab_list.append((self.tab_skills, "技能库"))
        tab_list += [
            (self.tab_generation, "生成控制"),
            (self.tab_editor, "章节编辑器"),
            (self.tab_cover, "小说封面生成"),
        ]
        for w, n in tab_list:
            self.tabs.addTab(w, n)
        ml.addWidget(self.tabs, 1)

    def _build_statusbar(self):
        sb = QStatusBar(); self.setStatusBar(sb)
        sb.addWidget(QLabel("© 2026 AI 写作工作台 | Python + PyQt5"))
        self._status_indicator = QLabel("● 未启动")
        self._status_indicator.setStyleSheet(
            "color: #999; font-weight: bold; padding: 2px 8px;")
        sb.addPermanentWidget(self._status_indicator)

    def _connect_signals(self):
        # 创作设置
        self.tab_settings.btn_gen_insp.clicked.connect(self.gen_inspiration)
        self.tab_settings.btn_regen_insp.clicked.connect(self.gen_inspiration)
        self.tab_settings.btn_gen_title.clicked.connect(self.gen_title)
        self.tab_settings.btn_regen_title.clicked.connect(self.gen_title)
        self.tab_settings.btn_import_txt.clicked.connect(
            lambda: self._import_to(self.tab_settings.inspiration_edit))
        self.tab_settings.btn_prelogin.clicked.connect(self.prelogin_ai)
        self.tab_settings.ai_group.buttonClicked.connect(self._on_ai_changed)

        # 大纲
        self.tab_outline.btn_gen_all.clicked.connect(self.gen_outline_all)
        self.tab_outline.btn_regen_all.clicked.connect(self.gen_outline_all)
        self.tab_outline.btn_gen_seed.clicked.connect(lambda: self.gen_outline_part("故事种子"))
        self.tab_outline.btn_gen_wv.clicked.connect(lambda: self.gen_outline_part("世界观"))
        self.tab_outline.btn_gen_lo.clicked.connect(lambda: self.gen_outline_part("LO世界观层"))
        self.tab_outline.btn_gen_struct.clicked.connect(lambda: self.gen_outline_part("故事结构"))
        self.tab_outline.btn_gen_ch.clicked.connect(lambda: self.gen_outline_part("章节大纲"))
        self.tab_outline.btn_extract_intro.clicked.connect(self.extract_intro)
        self.tab_outline.btn_import_special.clicked.connect(
            lambda: self._import_to(self.tab_outline.special_edit))

        # 生成控制 - 浏览器
        self.tab_generation.btn_launch.clicked.connect(self.launch_browser)
        self.tab_generation.btn_close.clicked.connect(self.close_browser)
        self.tab_generation.btn_go.clicked.connect(self._goto_url)
        self.tab_generation.btn_grab.clicked.connect(self.grab_response)

        # 创作设置 ai_group(单选) ↔ 生成控制 site_combo(下拉) 双向同步
        def _ai_radio_to_combo(btn):
            name = btn.text()
            if name in AI_URLS:
                cur = self.tab_generation.site_combo.currentText()
                if cur != name:
                    self.tab_generation.site_combo.blockSignals(True)
                    self.tab_generation.site_combo.setCurrentText(name)
                    self.tab_generation.site_combo.blockSignals(False)
                    self.tab_generation.url_input.setText(AI_URLS[name])
            elif name == "自定义":
                u = self.tab_settings.custom_url.text().strip()
                if u:
                    self.tab_generation.url_input.setText(u)
        self.tab_settings.ai_group.buttonClicked.connect(_ai_radio_to_combo)

        def _ai_combo_to_radio(name):
            for btn in self.tab_settings.ai_group.buttons():
                if btn.text() == name and not btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                    break
        self.tab_generation.site_combo.currentTextChanged.connect(_ai_combo_to_radio)

        # 生成控制 - 任务
        self.tab_generation.btn_start.clicked.connect(self.start_generation)
        self.tab_generation.btn_pause.clicked.connect(self.pause_generation)
        self.tab_generation.btn_gen_three.clicked.connect(self.gen_golden_three)
        self.tab_generation.btn_regen_three.clicked.connect(self.gen_golden_three)

        # 章节编辑
        self.tab_editor.save_requested.connect(self.save_current_chapter)
        self.tab_editor.optimize_requested.connect(self.optimize_chapter)
        self.tab_editor.save_all_requested.connect(self.save_all_chapters)

        # 对话记忆
        self.tab_memory.btn_gen_full_memory.clicked.connect(self.gen_full_memory)
        self.tab_memory.btn_stop_full_memory.clicked.connect(self.stop_full_memory)
        self.tab_memory.btn_extract_chars.clicked.connect(self.extract_characters)
        self.tab_memory.btn_clear_chars.clicked.connect(
            lambda: self.tab_memory.chars_edit.clear())
        self.tab_memory.btn_gen_all_sum.clicked.connect(self.gen_all_missing_summaries)
        self.tab_memory.btn_gen_cur_sum.clicked.connect(self.gen_current_summary)
        self.tab_memory.btn_clear_sum.clicked.connect(
            lambda: self.tab_memory.summaries_edit.clear())
        self.tab_memory.btn_extract_lt.clicked.connect(self.extract_long_term)
        self.tab_memory.btn_clear_lt.clicked.connect(
            lambda: self.tab_memory.long_term_edit.clear())
        self.tab_memory.btn_preview.clicked.connect(self._refresh_memory_preview)

        # Canon Tab
        self.tab_canon.btn_extract_now.clicked.connect(self._canon_extract_all_chapters)

        # Skill Tab
        self.tab_skills.btn_test.clicked.connect(self._skill_test_run)

        # ChapterEditor 右键菜单(应用技能)
        self.tab_editor.content_edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_editor.content_edit.customContextMenuRequested.connect(
            self._show_chapter_editor_menu)

        # E 模块:对话槽管理
        sw = self.tab_generation.conv_switcher
        sw.btn_save_slot.clicked.connect(self._conv_save_current_slot)
        sw.btn_switch.clicked.connect(self._conv_switch_selected)
        sw.btn_new_slot.clicked.connect(self._conv_open_new_dialog)

    # ---- 浏览器控制 ----
    def launch_browser(self):
        if not SELENIUM_AVAILABLE:
            QMessageBox.critical(
                self, "缺少依赖",
                "未安装 Selenium,无法挂载真实浏览器。\n\n"
                "请在终端运行:\n"
                "  pip install -U selenium\n\n"
                "(selenium 4.6+ 自动管理 chromedriver,无需单独装。\n"
                "三种内核模式:\n"
                "  • Chrome 独立 — standalone,程序自管 profile\n"
                "  • Chrome 调试 — attach 已开调试 Chrome,程序与浏览器解耦,最稳\n"
                "  • 系统 Edge — standalone Edge)")
            return
        ch = self.tab_generation.selected_kernel_channel()
        self.tab_generation.btn_launch.setEnabled(False)
        self.tab_generation.btn_close.setEnabled(True)
        mode_label = {
            "chrome": "Chrome attach 调试模式",
            "msedge": "Edge standalone",
        }.get(ch, "Chrome standalone")
        self.tab_generation.log(f"准备启动浏览器({mode_label})...", "info")
        self.worker.start(channel=ch)

    def _on_browser_started(self):
        # 浏览器就绪后,自动跳到当前选定的 AI 网站
        url = self.tab_generation.url_input.text().strip()
        if url:
            self.worker.submit({"action": "navigate", "url": url})

    def close_browser(self):
        self.worker.stop()
        self.tab_generation.btn_launch.setEnabled(True)
        self.tab_generation.btn_close.setEnabled(False)

    def _goto_url(self):
        if not self.worker.is_ready():
            QMessageBox.warning(self, "提示", "请先点『启动浏览器』")
            return
        url = self.tab_generation.url_input.text().strip()
        if not url:
            return
        if not url.startswith("http"):
            url = "https://" + url
            self.tab_generation.url_input.setText(url)
        self.worker.submit({"action": "navigate", "url": url})

    def _on_ai_changed(self, button):
        ai = button.text()
        url = AI_URLS.get(ai)
        if not url and ai == "自定义":
            url = self.tab_settings.custom_url.text().strip()
        if url:
            self.tab_generation.url_input.setText(url)
            self.tab_generation.site_combo.setCurrentText(ai if ai in AI_URLS else "DeepSeek")
            self.tab_generation.log(f"已切换到 {ai}: {url}", "info")
            if self.worker.is_ready():
                self.worker.submit({"action": "navigate", "url": url})

    def _init_demo_chapters(self):
        # 不再预填示例章节,启动时章节列表为空
        # 用户通过「新增章节」或「新建空白创作」按钮自行添加
        self._refresh_chapter_list()

    def _refresh_chapter_list(self):
        self.chapter_list.clear()
        for ch in self.chapters:
            self.chapter_list.addItem(QListWidgetItem(ch["title"]))
        if 0 <= self.current_chapter_index < len(self.chapters):
            self.chapter_list.setCurrentRow(self.current_chapter_index)

    def _on_chapter_clicked(self, item):
        idx = self.chapter_list.row(item)
        if not (0 <= idx < len(self.chapters)): return
        # 自动保存当前章
        if 0 <= self.current_chapter_index < len(self.chapters):
            self.chapters[self.current_chapter_index]["title"] = self.tab_editor.title_input.text()
            self.chapters[self.current_chapter_index]["content"] = self.tab_editor.content_edit.toPlainText()
        self.current_chapter_index = idx
        ch = self.chapters[idx]
        self.tab_editor.load_chapter(ch["title"], ch["content"])
        self.tabs.setCurrentWidget(self.tab_editor)

    # ---- 章节管理 ----
    def add_chapter(self):
        n = len(self.chapters) + 1
        title, ok = QInputDialog.getText(self, "新增章节", "章节标题:", text=f"第{n}章 ")
        if ok and title:
            self.chapters.append({"title": title, "content": ""})
            self.current_chapter_index = len(self.chapters) - 1
            self._refresh_chapter_list()
            self.tab_editor.load_chapter(title, "")
            self.tabs.setCurrentWidget(self.tab_editor)

    def delete_chapter(self):
        idx = self.chapter_list.currentRow()
        if idx < 0: return
        if QMessageBox.question(
            self, "确认", f"删除『{self.chapters[idx]['title']}』?"
        ) == QMessageBox.Yes:
            self.chapters.pop(idx)
            self.current_chapter_index = -1
            self.tab_editor.load_chapter("", "")
            self._refresh_chapter_list()

    def rename_chapter(self):
        idx = self.chapter_list.currentRow()
        if idx < 0: return
        title, ok = QInputDialog.getText(
            self, "重命名", "新标题:", text=self.chapters[idx]["title"])
        if ok and title:
            self.chapters[idx]["title"] = title
            self._refresh_chapter_list()

    def save_current_chapter(self, title, content):
        if self.current_chapter_index < 0:
            QMessageBox.warning(self, "提示", "请先新增或选择章节")
            return
        self.chapters[self.current_chapter_index]["title"] = title
        self.chapters[self.current_chapter_index]["content"] = content
        self._refresh_chapter_list()
        self._save_chapter_to_disk(self.chapters[self.current_chapter_index])
        self.statusBar().showMessage(f"已保存:{title}", 3000)

    def _save_chapter_to_disk(self, chapter):
        title = self.tab_settings.get_title()
        proj = self.project_dir / re.sub(r'[\\/:*?"<>|]', '_', title)
        proj.mkdir(exist_ok=True)
        safe = re.sub(r'[\\/:*?"<>|]', '_', chapter["title"])
        path = proj / f"{safe}.txt"
        path.write_text(chapter["content"], encoding="utf-8")
        self.tab_generation.log(f"章节已保存到: {path}", "success")

    def save_all_chapters(self):
        if 0 <= self.current_chapter_index < len(self.chapters):
            self.chapters[self.current_chapter_index]["title"] = self.tab_editor.title_input.text()
            self.chapters[self.current_chapter_index]["content"] = self.tab_editor.content_edit.toPlainText()
        for ch in self.chapters:
            self._save_chapter_to_disk(ch)
        QMessageBox.information(self, "完成", f"已保存 {len(self.chapters)} 章到\n{self.project_dir}")

    # ---- AI 调用入口 ----
    def _send_to_ai(self, prompt, label="提示词", target=None, **extra):
        """
        统一的发送入口。
        target: 用于自动回填到 UI 的目标标识。可选:
            'inspiration' / 'title' / 'outline_full' / 'outline_part:<name>'
            / 'intro' / 'chapter' / 'golden_three' / 'optimize'
            None 表示只显示日志,弹窗手动选择。
        """
        if not SELENIUM_AVAILABLE:
            QMessageBox.critical(
                self, "缺少依赖",
                "未安装 Selenium,无法自动发送/抓取。\n\n"
                "请运行:\n"
                "  pip install -U selenium")
            return
        if not self.worker.is_ready():
            self.tabs.setCurrentWidget(self.tab_generation)
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』,完成 AI 网站登录后再生成。")
            return
        self.tabs.setCurrentWidget(self.tab_generation)
        self.tab_generation.log(f"准备发送:{label} ({len(prompt)} 字符)", "info")
        # 记录这次任务的目标位置(由 _on_response_received 处理回填)
        self._pending_task_target = {"target": target, "label": label, **extra}
        # 应用人类延迟
        type_delay = 30 if self.tab_settings.delay_check.isChecked() else 5
        # 投递任务
        url = self.tab_generation.url_input.text().strip()
        self.worker.submit({
            "action": "send_prompt",
            "prompt": prompt,
            "task_id": label,
            "url": url,
            "type_delay_ms": type_delay,
        })

    def _on_response_received(self, task_id, content):
        """worker 回调:某次提示词的 AI 回复已抓取完毕"""
        if not content or not content.strip():
            self.tab_generation.log(f"任务『{task_id}』未抓到内容(选择器需调整)", "warn")
            content = ""
        else:
            self.tab_generation.log(
                f"任务『{task_id}』抓取成功,{len(content)} 字符", "success")

        meta = self._pending_task_target or {}
        target = meta.get("target")
        # ★ 关键:先清空 pending,handler 才能在内部重新设置(链式任务依赖此)
        self._pending_task_target = None

        # 根据目标自动回填
        if target == "inspiration":
            self.tab_settings.inspiration_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_settings)
        elif target == "conv_restore":
            # 记忆恢复确认回复 — 只记日志
            self.tab_generation.log(
                f"✓ 新对话已确认上下文({len(content)} 字符回复):"
                f" {content[:80].replace(chr(10),' ')}…", "success")
            self.tab_generation.log(
                "🟢 对话槽切换完成,可以继续生成章节。", "success")
        elif target == "title":
            # 提取第一行非空文本作为书名
            t = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
            t = re.sub(r'^[「《【\s"\']+|[」》】\s"\']+$', '', t)[:30]
            if t: self.tab_settings.title_input.setText(t)
            self.tabs.setCurrentWidget(self.tab_settings)
        elif target == "outline_full":
            self.tab_outline.chapter_outline_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_outline)
        elif target and target.startswith("outline_part:"):
            part = target.split(":", 1)[1]
            mp = {
                "故事种子": self.tab_outline.seed_edit,
                "世界观": self.tab_outline.worldview_edit,
                "LO世界观层": self.tab_outline.lo_edit,
                "故事结构": self.tab_outline.structure_edit,
                "章节大纲": self.tab_outline.chapter_outline_edit,
            }
            if part in mp:
                mp[part].setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_outline)
        elif target == "intro":
            self.tab_outline.intro_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_outline)
        elif target in ("chapter", "golden_three"):
            if self.workflow and meta.get("_workflow_ctx") and target == "chapter":
                # ★ 新路径:由 workflow.start() 发起的章节(含 _workflow_ctx)
                self.workflow.on_ai_content(content, meta)
            else:
                # 旧路径:外部直接设置 _pending_task_target 或 golden_three
                self._handle_chapter_response(content, meta)
        elif target and target.startswith("_cb_"):
            # workflow_pipeline 一次性 callback(AI 稽核步骤回调)
            cb = getattr(self, "_one_shot_callbacks", {}).pop(target, None)
            if cb:
                cb(content)
        elif target == "optimize":
            self.tab_editor.content_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_editor)
        elif target == "chapter_summary":
            # 章节摘要回填到记忆系统
            ch_num = meta.get("ch_num")
            if ch_num and content:
                ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
                summary = content.strip().replace('\n', ' ')
                # 截断超长摘要
                max_len = self.tab_memory.summary_len.value()
                if len(summary) > max_len * 1.5:
                    summary = summary[:max_len] + "..."
                if ch:
                    ch["summary"] = summary
                    self.tab_memory.append_summary(ch_num, ch["title"], summary)
                self.tab_generation.log(f"✓ 第 {ch_num} 章摘要已记入对话记忆", "success")
            # 链式触发:正在跑后置流水线 → 推进
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
            # 链式触发:批量生成中且摘要是为下一章准备的(老路径,无后置流水线时)
            elif meta.get("chain_to_next") and self._batch_remaining > 0 and not self._batch_paused:
                QTimer.singleShot(1000, self._send_next_chapter)
            elif meta.get("chain_to_next"):
                self.tab_generation.log("批量生成已结束", "info")
            # 链式触发:一键生成对话记忆流水线推进
            if meta.get("chain_full_memory"):
                QTimer.singleShot(800, self._run_next_full_memory_step)
            # workflow_pipeline 回调
            done_cb = meta.get("_done_cb")
            if done_cb:
                QTimer.singleShot(100, done_cb)
        elif target == "character_extract":
            # 角色档案提取
            if content.strip():
                self.tab_memory.chars_edit.setPlainText(content.strip())
                self.tab_generation.log("✓ 角色档案已更新", "success")
            self.tabs.setCurrentWidget(self.tab_memory)
            if meta.get("chain_full_memory"):
                QTimer.singleShot(800, self._run_next_full_memory_step)
        elif target == "long_term_extract":
            # 长期记忆提取 - 追加到现有内容
            if content.strip() and content.strip() != "无":
                cur = self.tab_memory.long_term_edit.toPlainText().strip()
                merged = (cur + "\n" + content.strip()) if cur else content.strip()
                self.tab_memory.long_term_edit.setPlainText(merged)
                self.tab_generation.log("✓ 长期记忆已追加", "success")
            else:
                self.tab_generation.log("本章无新增长期记忆", "info")
            self.tabs.setCurrentWidget(self.tab_memory)
            if meta.get("chain_full_memory"):
                QTimer.singleShot(800, self._run_next_full_memory_step)

        # ============ B / C / D 新增 target 分发 ============
        elif target == "canon_audit":
            self._on_canon_audit_response(content)
        elif target == "canon_extract":
            self._on_canon_extract_response(content, meta)
            # 后置流水线下一步(单章生成完后的链)
            if getattr(self, "_post_chapter_pipeline", None):
                QTimer.singleShot(500, self._run_next_post_chapter_step)
            # 批量抽取流水线下一步(用户点「从已有章节抽取」)
            if getattr(self, "_canon_batch_active", False):
                self._canon_batch_active = False
                QTimer.singleShot(800, self._run_next_canon_extract)
        elif target == "critique_rhythm":
            ch_num = meta.get("ch_num", 0)
            self._on_critique_score_response(content, "rhythm", ch_num)
        elif target == "critique_character":
            ch_num = meta.get("ch_num", 0)
            self._on_critique_score_response(content, "character", ch_num)
        elif target == "skill_run":
            self._on_skill_response(content, meta)

        else:
            # 没指定目标,弹窗让用户选
            self._popup_choose_target(content)

    def _handle_chapter_response(self, content, meta):
        """处理章节生成回复 → 多维校验 → 死磕重写 / 入库 + 后置链"""
        if not content:
            self._batch_remaining = 0
            return
        target_words = meta.get("target_words", 3000)
        min_words = meta.get("min_words", int(target_words * 0.85))

        # ---- 即时校验(无 AI 调用)----
        instant_issues, need_ai_audit = self._check_chapter_quality(
            content, target_words, min_words)

        cfg = self.tab_generation.critique_config()

        # ---- 是否需要 AI 稽核(Canon / 节奏 / 人设)----
        if need_ai_audit and meta.get("target") != "golden_three":
            # 启动 AI 稽核串联流水线
            self._start_ai_audit_chain(content, meta, instant_issues)
            return

        # 没有 AI 稽核需求,直接根据即时问题决定
        if instant_issues:
            new_meta = dict(meta)
            new_meta["_held_content"] = content
            self._retry_chapter_with_reasons(new_meta, instant_issues)
            return

        self._accept_chapter_and_continue(content, meta)

    def _start_ai_audit_chain(self, content, meta, instant_issues):
        """串行 AI 稽核:Canon → 节奏 → 人设,把所有 issues 汇总后决定是否死磕"""
        cfg = self.tab_generation.critique_config()
        # 留存 content 在 meta 里供 callback 使用
        audit_state = {
            "content": content,
            "meta": dict(meta),
            "issues": list(instant_issues),
            "remaining": [],
        }
        if cfg.get("canon"):
            audit_state["remaining"].append("canon")
        if cfg.get("rhythm"):
            audit_state["remaining"].append("rhythm")
        if cfg.get("character"):
            audit_state["remaining"].append("character")
        self._audit_state = audit_state
        self._continue_ai_audit_chain()

    def _continue_ai_audit_chain(self):
        """推进 AI 稽核流水线,完成时统一决定 retry / accept"""
        st = getattr(self, "_audit_state", None)
        if st is None:
            return
        if not st["remaining"]:
            # 全部稽核完成 → 决定走向
            content = st["content"]
            meta = st["meta"]
            issues = st["issues"]
            self._audit_state = None
            if issues:
                meta["_held_content"] = content
                self._retry_chapter_with_reasons(meta, issues)
            else:
                self._accept_chapter_and_continue(content, meta)
            return

        next_kind = st["remaining"].pop(0)
        ch_num = st["meta"].get("ch_num", len(self.chapters) + 1)
        content = st["content"]
        if next_kind == "canon":
            def on_canon_done(violations):
                # 仅 high 严重度才作为重写理由(mid/low 只记录不死磕)
                for v in violations:
                    if v.get("severity") == "high":
                        st["issues"].append(
                            "Canon 违反(严重):" + v.get("desc", "")[:120])
                self._continue_ai_audit_chain()
            self._run_canon_audit(content, ch_num, on_canon_done)
        elif next_kind == "rhythm":
            self._pending_task_target = {
                "target": "critique_rhythm",
                "ch_num": ch_num,
                "_audit_resume": True,
            }
            prompt = PROMPTS["critique_rhythm"].format(content=content[:6000])
            self._send_to_ai(prompt, f"节奏稽核-第{ch_num}章",
                             target="critique_rhythm", ch_num=ch_num)
        elif next_kind == "character":
            chars = self.tab_memory.chars_edit.toPlainText().strip() or "(暂无)"
            prompt = PROMPTS["critique_character"].format(
                characters=chars, content=content[:6000])
            self._pending_task_target = {
                "target": "critique_character",
                "ch_num": ch_num,
                "_audit_resume": True,
            }
            self._send_to_ai(prompt, f"人设稽核-第{ch_num}章",
                             target="critique_character", ch_num=ch_num)

    def _on_critique_score_response(self, content, kind, ch_num):
        """处理节奏 / 人设打分回复"""
        st = getattr(self, "_audit_state", None)
        if st is None:
            return
        threshold = 6 if kind == "rhythm" else 7
        try:
            text = self._extract_json_blob(content)
            data = json.loads(text)
            score = int(data.get("score", 10))
            reason = (data.get("reason", "") or "")[:120]
            label = {"rhythm": "节奏", "character": "人设"}[kind]
            self.tab_generation.log(
                f"  {label}打分:{score}/10 — {reason}", "info")
            if score < threshold:
                st["issues"].append(f"{label}评分不足({score}<{threshold}):{reason}")
        except Exception as e:
            self.tab_generation.log(f"  {kind} 打分解析失败:{e}", "warn")
        self._continue_ai_audit_chain()

    # ===================================================================
    # 技能库(D 模块):手动调用 + 章末自动调用
    # ===================================================================
    def _run_skill_on_chapter(self, skill, ch_num, chain_post=False,
                              body_override=None, _done_cb=None):
        """在某一章上运行技能。chain_post=True 时回复后会推进 post-chapter 流水线"""
        if 0 < ch_num <= len(self.chapters):
            ch = self.chapters[ch_num - 1]
            content = body_override if body_override is not None else (ch.get("content") or "")
        else:
            content = body_override or ""
        if not content:
            self.tab_generation.log(f"技能「{skill['name']}」: 无可用文本", "warn")
            if chain_post:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
            if _done_cb:
                QTimer.singleShot(100, _done_cb)
            return
        try:
            prompt = skill["prompt"].format(content=content[:8000])
        except Exception:
            prompt = skill["prompt"] + "\n\n" + content[:8000]
        self._send_to_ai(
            prompt, f"技能-{skill['name']}",
            target="skill_run",
            ch_num=ch_num,
            skill_name=skill["name"],
            skill_target=skill.get("target", "log_only"),
            chain_post=chain_post,
            _done_cb=_done_cb,          # workflow_pipeline 回调
        )

    def _on_skill_response(self, content, meta):
        skill_name = meta.get("skill_name", "?")
        skill_target = meta.get("skill_target", "log_only")
        ch_num = meta.get("ch_num", 0)
        if not content.strip():
            self.tab_generation.log(f"技能「{skill_name}」未抓到内容", "warn")
        elif skill_target == "current_chapter":
            if 0 < ch_num <= len(self.chapters):
                self.chapters[ch_num - 1]["content"] = content
                self.tab_editor.content_edit.setPlainText(content)
                self.tab_generation.log(
                    f"✓ 技能「{skill_name}」已替换第 {ch_num} 章正文", "success")
        elif skill_target == "selected_text":
            cur = self.tab_editor.content_edit.textCursor()
            if cur.hasSelection():
                cur.insertText(content)
            else:
                self.tab_editor.content_edit.setPlainText(content)
            self.tab_generation.log(
                f"✓ 技能「{skill_name}」已应用到选区", "success")
        elif skill_target == "append_to_canon":
            # 简单追加为 evolving 演化项
            try:
                cur = self.tab_canon.canon_edit.toPlainText()
                self.tab_canon.canon_edit.setPlainText(
                    (cur + "\n" if cur else "") + f"# 技能「{skill_name}」于 ch{ch_num} 追加\n"
                    + "\n".join(
                        f"[E][M] 技能.{skill_name}.{i} = {ln.strip()} (ch{ch_num})"
                        for i, ln in enumerate(content.splitlines()[:20])
                        if ln.strip())
                )
                self.tab_generation.log(
                    f"✓ 技能「{skill_name}」结果已追加到 Canon", "success")
            except Exception as e:
                self.tab_generation.log(f"追加 Canon 失败:{e}", "warn")
        else:  # log_only
            self.tab_generation.log(
                f"📝 技能「{skill_name}」结果(ch{ch_num}):", "info")
            for line in content.splitlines()[:10]:
                if line.strip():
                    self.tab_generation.log(f"   {line.strip()[:200]}", "info")

        # 链式推进
        if meta.get("chain_post"):
            QTimer.singleShot(500, self._run_next_post_chapter_step)
        # workflow_pipeline 回调
        done_cb = meta.get("_done_cb")
        if done_cb:
            QTimer.singleShot(500, done_cb)

    def _canon_extract_all_chapters(self):
        """从所有已生成章节自动抽取 Canon"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节,无法抽取")
            return
        if not self.worker.is_ready():
            self.tabs.setCurrentWidget(self.tab_generation)
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』,完成 AI 网站登录后再抽取。")
            return
        ret = QMessageBox.question(
            self, "确认",
            f"将对 {len(self.chapters)} 章逐一发送 AI 抽取设定,大约需要 "
            f"{len(self.chapters) * 30} 秒。是否继续?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self._canon_batch_pipeline = list(range(1, len(self.chapters) + 1))
        self._run_next_canon_extract()

    def _run_next_canon_extract(self):
        if not getattr(self, "_canon_batch_pipeline", None):
            self.tab_generation.log("✓ Canon 批量抽取完成", "success")
            return
        ch_num = self._canon_batch_pipeline.pop(0)
        ch = self.chapters[ch_num - 1]
        if not ch.get("content"):
            QTimer.singleShot(100, self._run_next_canon_extract)
            return
        # 复用现有 _run_canon_extract 但要在响应里推进队列
        self._canon_batch_active = True
        self._run_canon_extract(ch["content"], ch_num)

    def _skill_test_run(self):
        """技能 Tab 里点「测试运行」时,在当前编辑器选中章节上跑该技能"""
        idx = self.tab_skills._current_idx
        if idx < 0 or idx >= len(self.tab_skills.skills):
            QMessageBox.information(self, "提示", "请先在左侧选中一个技能")
            return
        skill = self.tab_skills.skills[idx]
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器", "请先到『生成控制』启动浏览器")
            return
        ch_idx = self.chapter_list.currentRow()
        if ch_idx < 0 or ch_idx >= len(self.chapters):
            QMessageBox.information(self, "提示", "请先在左侧选中一章")
            return
        # 使用编辑器当前文本(用户可能改过未保存)
        body = self.tab_editor.content_edit.toPlainText()
        self._run_skill_on_chapter(skill, ch_idx + 1, body_override=body)

    def _show_chapter_editor_menu(self, pos):
        """章节编辑器右键菜单 - 应用技能"""
        menu = self.tab_editor.content_edit.createStandardContextMenu()
        manual_skills = self.tab_skills.get_manual_skills()
        if manual_skills:
            menu.addSeparator()
            sk_menu = menu.addMenu("⚡ 应用技能")
            for s in manual_skills:
                act = sk_menu.addAction(s["name"])
                act.triggered.connect(
                    lambda _, sk=s: self._apply_manual_skill_to_editor(sk))
        menu.exec_(self.tab_editor.content_edit.mapToGlobal(pos))

    def _apply_manual_skill_to_editor(self, skill):
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器", "请先到『生成控制』启动浏览器")
            return
        ch_idx = self.chapter_list.currentRow()
        ch_num = ch_idx + 1 if ch_idx >= 0 else 0

        # selected_text 模式:取选中文本;否则取全文
        target = skill.get("target", "current_chapter")
        if target == "selected_text":
            cur = self.tab_editor.content_edit.textCursor()
            if not cur.hasSelection():
                QMessageBox.information(
                    self, "提示",
                    f"技能「{skill['name']}」目标是选中文本,但你没有选中任何内容。\n"
                    f"请先选中一段再调用,或改技能 target 为 current_chapter")
                return
            body = cur.selectedText().replace('\u2029', '\n')
        else:
            body = self.tab_editor.content_edit.toPlainText()

        self._run_skill_on_chapter(skill, ch_num, body_override=body)
    def _submit_summary_task(self, ch_num, chain_to_next=False,
                             chain_full_memory=False, _done_cb=None):
        """提交一个『生成本章摘要』的任务给浏览器自动化"""
        if not (0 < ch_num <= len(self.chapters)):
            return
        ch = self.chapters[ch_num - 1]
        max_len = self.tab_memory.summary_len.value()
        prompt = PROMPTS["chapter_summary"].format(
            max_len=max_len,
            title=ch.get("title", f"第{ch_num}章"),
            content=ch.get("content", "")[:5000],
        )
        self._send_to_ai(
            prompt, f"摘要-第{ch_num}章",
            target="chapter_summary",
            ch_num=ch_num,
            chain_to_next=chain_to_next,
            chain_full_memory=chain_full_memory,
            _done_cb=_done_cb,          # workflow_pipeline 回调
        )

    def _split_and_save_golden_three(self, content):
        """把黄金三章按 ===第N章=== 拆分入库"""
        chunks = re.split(r'={2,}\s*第\s*[一二三123]\s*章[^\n=]*={2,}', content)
        chunks = [c.strip() for c in chunks if c.strip()]
        if len(chunks) < 3:
            # 退化:整体作为一章
            self.chapters.append({"title": "黄金三章合订", "content": content})
        else:
            titles = re.findall(r'={2,}\s*(第\s*[一二三123]\s*章[^=\n]*?)={2,}', content)
            for i, body in enumerate(chunks[:3]):
                t = titles[i].strip() if i < len(titles) else f"第{i+1}章"
                self.chapters.append({"title": t, "content": body})
        self._refresh_chapter_list()
        if self.tab_generation.auto_save.isChecked():
            for ch in self.chapters[-3:]:
                self._save_chapter_to_disk(ch)
        self.tab_generation.log("✓ 黄金三章已生成并保存", "success")

    def _extract_chapter_title(self, content):
        """从生成内容里尝试提取章节标题"""
        for line in content.splitlines()[:3]:
            line = line.strip()
            if re.match(r'^第[一二三四五六七八九十百千零\d]+章', line):
                return line[:60]
        return None

    def _strip_chapter_title(self, content):
        """如果首行是章节标题就移除"""
        lines = content.splitlines()
        if lines and re.match(r'^第[一二三四五六七八九十百千零\d]+章', lines[0].strip()):
            return "\n".join(lines[1:]).lstrip()
        return content

    def _send_next_chapter(self):
        """批量生成里发下一章(自动注入对话记忆)"""
        if self._batch_paused or self._batch_remaining <= 0:
            return
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        ch_num = len(self.chapters) + 1
        outline = (self.tab_outline.worldview_edit.toPlainText() + "\n"
                   + self.tab_outline.structure_edit.toPlainText())[:1500]
        target = self.tab_settings.get_words_per_chapter()
        offset = self.tab_settings.get_prompt_offset()
        target_with_offset = max(500, target + offset)
        min_words = max(300, int(target_with_offset * 0.85))
        full = self.tab_settings.get_full_settings_block()
        prompt = PROMPTS["chapter"].format(
            chapter_num=ch_num,
            title=self.tab_settings.get_title(),
            genre="/".join(self.tab_settings.get_selected_genres() or ["言情"]),
            outline=outline,
            chapter_outline=co[:2500],
            min_words=min_words, target_words=target_with_offset,
        ) + f"\n\n【完整设定参考】\n{full}"

        # ★ 注入对话记忆(旧路径兜底:仅在 workflow 不可用时执行)
        if not self.workflow:
            if self.tab_memory.auto_inject.isChecked():
                mem_block = self._build_memory_block()
                if mem_block:
                    prompt += f"\n\n{mem_block}"
                    self.tab_generation.log(
                        f"已注入对话记忆({len(mem_block)} 字符)到第 {ch_num} 章提示词", "info")

            # ★ B 模块:注入 Canon 设定约束
            if self.tab_canon.chk_inject.isChecked():
                canon_block = self._build_canon_block()
                if canon_block:
                    prompt += f"\n\n{canon_block}"
                    self.tab_generation.log(
                        f"已注入 Canon 约束({len(canon_block)} 字符)到第 {ch_num} 章提示词", "info")

        if self.workflow:
            # ★ 新路径:PRE_WRITE 阶段负责注入,workflow 接管完整生命周期
            self.workflow.start(
                prompt=prompt,
                ch_num=ch_num,
                target_words=target_with_offset,
                min_words=min_words,
                retry_left=self.tab_generation.retry_count.value(),
            )
        else:
            # 旧路径兜底
            self._send_to_ai(
                prompt, f"第 {ch_num} 章",
                target="chapter", ch_num=ch_num,
                target_words=target_with_offset, min_words=min_words,
                retry_left=self.tab_generation.retry_count.value(),
                original_prompt=prompt,
            )

    # ===================================================================
    # 对话记忆系统
    # ===================================================================
    # ===================================================================
    # E 模块:对话槽管理(随时换对话 + 自动同步记忆)
    # ===================================================================

    def _conv_save_current_slot(self):
        """保存当前 URL 为命名槽"""
        url = self.tab_generation.url_input.text().strip()
        if not url:
            QMessageBox.information(self, "提示", "URL 框为空,请先填入对话地址")
            return
        ch_num = len(self.chapters)
        # 生成默认名:AI站点 + 当前章数
        site = self.tab_generation.site_combo.currentText()
        from datetime import datetime as _dt
        default_name = f"{site}-ch{ch_num}-{_dt.now().strftime('%H%M')}"
        name, ok = QInputDialog.getText(
            self, "保存对话槽", "槽名称:", text=default_name)
        if not ok or not name.strip():
            return
        sw = self.tab_generation.conv_switcher
        idx = sw.add_slot(name.strip(), url, ai_site=site, chapter_at=ch_num)
        sw.set_active(idx)
        self.tab_generation.log(f"📌 已保存对话槽「{name.strip()}」(ch{ch_num})", "success")

    def _conv_switch_selected(self):
        """切换到列表中选中的槽"""
        sw = self.tab_generation.conv_switcher
        slot = sw.get_selected_slot()
        if not slot:
            QMessageBox.information(self, "提示", "请先在列表中选中一个对话槽")
            return
        url = slot.get("url", "").strip()
        if not url:
            QMessageBox.warning(self, "槽 URL 为空", f"槽「{slot['name']}」没有保存有效 URL")
            return
        sync = sw.chk_sync.isChecked()

        # 1. 切换 URL
        self.tab_generation.url_input.setText(url)
        row = sw.slot_list.currentRow()
        sw.set_active(row)
        self.tab_generation.log(
            f"🔄 切换到对话槽「{slot['name']}」(url={url[:60]}...)", "info")

        # 2. 导航到新 URL
        if self.worker.is_ready():
            self.worker.submit({
                "action": "goto",
                "url": url,
                "task_id": f"切换对话槽-{slot['name']}",
            })
        else:
            self.tab_generation.log(
                "⚠ 浏览器未就绪,已更新 URL 框,待启动后可手动访问", "warn")

        # 3. 同步记忆(可选)
        if sync:
            # 用 QTimer 错开,让 goto 先完成
            QTimer.singleShot(3500, self._conv_send_restore_prompt)
        else:
            self.tab_generation.log(
                "ℹ 未开启「切换时同步记忆」,跳过上下文恢复", "info")

    def _conv_open_new_dialog(self):
        """在浏览器中打开新对话页,然后引导用户保存"""
        site = self.tab_generation.site_combo.currentText()
        url = AI_URLS.get(site, "https://chat.deepseek.com/")
        if self.worker.is_ready():
            self.worker.submit({
                "action": "goto",
                "url": url,
                "task_id": "新建对话槽",
            })
            QMessageBox.information(
                self, "新建对话",
                f"已导航到 {site} 主页。\n\n"
                "请在浏览器里开启一个新对话,\n"
                "然后把新对话的完整 URL 复制到「URL」框,\n"
                "再点「📌 保存当前」绑定为槽。")
        else:
            QMessageBox.information(
                self, "提示",
                "请先启动浏览器,再点「新建槽」。")

    def _build_context_restore_prompt(self) -> str:
        """
        构建「记忆恢复」提示词:把书名/进度/角色/摘要/长期记忆/Canon
        打包成一条完整的上下文恢复消息,发给新对话窗口。
        AI 读完后确认,之后就能像老对话一样继续写。
        """
        title = self.tab_settings.get_title() or "未命名小说"
        genre = "/".join(self.tab_settings.get_selected_genres() or ["—"])
        ch_count = len(self.chapters)
        next_ch = ch_count + 1

        parts = [
            f"你是我的网文写作助手,正在辅助创作《{title}》。\n"
            f"以下是目前的全部写作进度,请仔细阅读后回复确认。\n",

            f"【基本信息】\n"
            f"书名:《{title}》  题材:{genre}  "
            f"当前进度:已完成第 {ch_count} 章,下一章将写第 {next_ch} 章\n",
        ]

        # 角色档案
        chars = self.tab_memory.chars_edit.toPlainText().strip()
        if chars:
            parts.append(f"【角色档案(人设/状态/关系,必须保持一致)】\n{chars}\n")

        # 章节摘要
        sums = self.tab_memory.parse_summaries()
        if sums:
            lines = [f"第{n}章:{s}" for n, s in sorted(sums.items())]
            parts.append("【已完成章节摘要(按顺序,了解剧情脉络)】\n" + "\n".join(lines) + "\n")

        # 最近 N 章详细
        recent_n = self.tab_memory.recent_n.value()
        if recent_n > 0 and self.chapters:
            start = max(0, ch_count - recent_n)
            detail = []
            for ch in self.chapters[start:]:
                body = (ch.get("content") or "").strip()
                tail = ("..." + body[-500:]) if len(body) > 500 else body
                s = f"——{ch.get('title','')}——"
                if ch.get("summary"):
                    s += f"\n[核心] {ch['summary']}"
                s += f"\n[末尾片段]\n{tail}"
                detail.append(s)
            if detail:
                parts.append(
                    f"【最近 {len(detail)} 章详细内容(衔接关键)】\n\n"
                    + "\n\n".join(detail) + "\n")

        # 长期记忆
        lt = self.tab_memory.long_term_edit.toPlainText().strip()
        if lt:
            parts.append(
                f"【长期记忆 / 重要伏笔(不可遗忘,不可矛盾)】\n{lt}\n")

        # Canon 约束
        canon_block = self._build_canon_block()
        if canon_block:
            parts.append(canon_block + "\n")

        # 世界观/大纲片段
        wv = self.tab_outline.worldview_edit.toPlainText().strip()[:600]
        if wv:
            parts.append(f"【世界观/设定(节选)】\n{wv}\n")

        parts.append(
            f"以上就是全部进度。\n"
            f"请回复:「已了解,当前进度:第 {ch_count} 章已完成,"
            f"下一章将写第 {next_ch} 章,随时可以继续。」"
        )

        return "\n\n".join(parts)

    def _conv_send_restore_prompt(self):
        """向当前 URL(新对话)发送一次完整的记忆恢复提示词"""
        if not self.worker.is_ready():
            self.tab_generation.log(
                "⚠ 浏览器未就绪,无法发送记忆恢复提示词", "warn")
            return
        prompt = self._build_context_restore_prompt()
        self.tab_generation.log(
            f"📨 发送记忆恢复提示词({len(prompt)} 字符)…", "info")
        self._send_to_ai(
            prompt,
            label="记忆恢复·上下文同步",
            target="conv_restore",
        )

    def _build_memory_block(self):
        """
        组装记忆块:角色档案 + 早期章节摘要 + 最近 N 章详细尾段 + 长期伏笔
        返回完整的 【对话记忆】 段落,可直接拼到提示词末尾
        """
        parts = []
        m = self.tab_memory

        # 1. 角色档案
        chars = m.chars_edit.toPlainText().strip()
        if chars:
            parts.append(f"【角色档案(必须保持人设一致)】\n{chars}")

        # 2. 章节摘要 + 最近 N 章详细
        recent_n = m.recent_n.value()
        cur_ch_count = len(self.chapters)
        sums = m.parse_summaries()
        if cur_ch_count > 0:
            sum_lines = []
            # 早期章节(只用摘要)
            early_end = max(0, cur_ch_count - recent_n)
            for n in range(1, early_end + 1):
                if n in sums:
                    sum_lines.append(f"第{n}章:{sums[n]}")
            if sum_lines:
                parts.append("【已发生剧情概要(早期章节)】\n" + "\n".join(sum_lines))

            # 最近 N 章详细尾段
            if recent_n > 0:
                start = max(0, cur_ch_count - recent_n)
                detail_chunks = []
                for ch in self.chapters[start:]:
                    body = (ch.get("content") or "").strip()
                    # 取尾段 + 摘要
                    tail = body[-400:] if len(body) > 400 else body
                    block = f"——{ch.get('title', '')}——"
                    if ch.get("summary"):
                        block += f"\n[本章核心] {ch['summary']}"
                    if tail:
                        block += f"\n[本章末尾片段]\n...{tail}"
                    detail_chunks.append(block)
                if detail_chunks:
                    parts.append(
                        f"【最近 {len(detail_chunks)} 章详细回顾(请基于这些细节衔接)】\n"
                        + "\n\n".join(detail_chunks))

        # 3. 长期记忆
        lt = m.long_term_edit.toPlainText().strip()
        if lt:
            parts.append(f"【长期记忆 - 重要伏笔/物品/关系(不要遗忘、不要矛盾)】\n{lt}")

        if not parts:
            return ""
        return "【对话记忆 - AI 必读 ↓】\n" + "\n\n".join(parts)

    def _refresh_memory_preview(self):
        """更新对话记忆预览面板"""
        block = self._build_memory_block()
        if not block:
            self.tab_memory.preview_edit.setPlainText(
                "(暂无记忆内容。请先生成章节,或手动填写角色/长期记忆)")
        else:
            self.tab_memory.preview_edit.setPlainText(block)
        self.tab_generation.log(
            f"记忆预览已刷新,共 {len(block)} 字符", "info")

    # ===================================================================
    # Canon 设定守护(B 模块)
    # ===================================================================
    def _build_canon_block(self):
        """组装 Canon 约束块,注入到下一章提示词末尾"""
        if not hasattr(self, "tab_canon"):
            return ""
        locked = self.tab_canon.serialize_locked()
        evolving = self.tab_canon.serialize_evolving()
        if locked == "(暂无锁定项)" and evolving == "(暂无演化项)":
            return ""
        return (
            "【★ Canon 核心设定 - 绝对不可违反 ★】\n"
            "以下是必须遵守的核心设定,任何与之冲突的内容都视为这章作废。\n\n"
            "[锁定项 - 严格遵守]\n" + locked + "\n\n"
            "[演化项 - 可推进但不可凭空打脸]\n" + evolving)

    def _run_canon_audit(self, content, ch_num, on_done):
        """对一章正文跑 Canon 稽核 prompt。
        on_done(violations: list) 在 AI 回复后被调用。"""
        if not hasattr(self, "tab_canon"):
            on_done([])
            return
        locked = self.tab_canon.serialize_locked()
        evolving = self.tab_canon.serialize_evolving()
        if locked == "(暂无锁定项)" and evolving == "(暂无演化项)":
            on_done([])
            return
        prompt = PROMPTS["canon_audit"].format(
            canon_locked=locked, canon_evolving=evolving, content=content[:6000])
        # 暂存 callback,_on_response_received 里特殊处理
        self._canon_audit_callback = (on_done, ch_num)
        self._send_to_ai(prompt, f"Canon稽核-第{ch_num}章", target="canon_audit")

    def _on_canon_audit_response(self, content):
        """处理 Canon 稽核 AI 回复"""
        cb_tuple = getattr(self, "_canon_audit_callback", None)
        if not cb_tuple:
            return
        on_done, ch_num = cb_tuple
        self._canon_audit_callback = None

        violations = []
        try:
            text = self._extract_json_blob(content)
            data = json.loads(text)
            if data.get("violated") and data.get("items"):
                violations = data["items"]
                for it in violations:
                    self.tab_canon.add_audit_log(
                        ch_num, it.get("severity", "mid"), it.get("desc", ""))
        except Exception as e:
            self.tab_generation.log(f"Canon 稽核解析失败:{e}(原文已忽略)", "warn")
        on_done(violations)

    def _run_canon_extract(self, content, ch_num):
        """从一章正文提取新 Canon,异步追加到设定档"""
        existing = self.tab_canon.canon_edit.toPlainText()[:2000]
        prompt = PROMPTS["canon_extract"].format(
            existing=existing or "(空)",
            ch_num=ch_num, content=content[:6000])
        self._send_to_ai(prompt, f"Canon抽取-第{ch_num}章",
                         target="canon_extract", ch_num=ch_num)

    def _on_canon_extract_response(self, content, meta):
        """处理 Canon 抽取 AI 回复"""
        ch_num = meta.get("ch_num", 0)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            count = 0
            for it in arr:
                key = it.get("key", "").strip()
                value = it.get("value", "").strip()
                mode = it.get("mode", "evolving")
                ch = it.get("ch", ch_num)
                if not key or not value:
                    continue
                self.tab_canon.add_item(
                    key, value, mode=mode,
                    severity="high" if mode == "locked" else "mid",
                    ch=ch)
                count += 1
            self.tab_generation.log(
                f"✓ Canon 抽取完成,新增/更新 {count} 条", "success")
        except Exception as e:
            self.tab_generation.log(f"Canon 抽取解析失败:{e}", "warn")

    @staticmethod
    def _extract_json_blob(text):
        """从 AI 回复里提取 JSON 字符串(去掉 ```json 包裹、前后说明文字)"""
        if not text:
            return "{}"
        # 去 markdown 代码块
        m = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', text, re.DOTALL)
        if m:
            return m.group(1)
        # 找首个 { 或 [,谁先出现就用谁(避免数组里的内层 {} 被先匹配)
        i_obj = text.find('{')
        i_arr = text.find('[')
        candidates = [(i, o, c) for i, o, c in
                      [(i_obj, '{', '}'), (i_arr, '[', ']')] if i >= 0]
        if not candidates:
            return "{}"
        candidates.sort()  # 按位置升序,先出现的优先
        i, ch_open, ch_close = candidates[0]
        depth = 0
        for j in range(i, len(text)):
            if text[j] == ch_open:
                depth += 1
            elif text[j] == ch_close:
                depth -= 1
                if depth == 0:
                    return text[i:j+1]
        return "{}"

    # ===================================================================
    # 多维自鞭策(C 模块)
    # ===================================================================
    def _check_chapter_quality(self, content, target_words, min_words):
        """对章节做即时校验(无 AI 调用部分)。
        返回 (issues:list[str], need_ai_audit:bool)"""
        issues = []
        cfg = self.tab_generation.critique_config()

        # 1. 字数
        actual = len(re.sub(r'\s', '', content))
        if cfg.get("word_count") and actual < min_words:
            issues.append(
                f"字数不达标:目标 {target_words} 字,实际 {actual} 字"
                f"(差 {min_words - actual} 字)")

        # 2. 章末钩子(无 AI 调用,启发式)
        if cfg.get("hook"):
            tail = content[-200:].strip()
            # 启发式:章末段最后一句是否含悬念词、问号、省略号
            hook_markers = (
                '?', '?', '...', '……',
                '突然', '却见', '只是', '可是', '然而', '没想到',
                '但下一秒', '正当', '就在', '直到')
            has_hook = any(m in tail for m in hook_markers)
            if not has_hook:
                issues.append(
                    "章末缺少钩子:最后一段没有问号/省略号/转折词,"
                    "读者追更欲不足。请在结尾留一个新悬念或反转")

        return issues, (cfg.get("canon") or cfg.get("rhythm") or cfg.get("character"))

    def _retry_chapter_with_reasons(self, meta, reasons):
        """字数 / 钩子 / Canon / 节奏 / 人设 任一不达标 → 拼强化 prompt 重发"""
        retry = meta.get("retry_left", 0)
        if retry <= 0:
            self.tab_generation.log(
                "✗ 死磕次数用尽,接受这章(质量不达标)", "warn")
            self._accept_chapter_and_continue(
                meta.get("_held_content", ""), meta)
            return

        new_meta = dict(meta)
        new_meta["retry_left"] = retry - 1
        new_meta.pop("_held_content", None)
        reason_block = "\n".join(f"  · {r}" for r in reasons)
        stronger = (meta.get("original_prompt", "")
                    + "\n\n【上次问题清单(必须修正)】\n" + reason_block
                    + "\n\n请重写本章,严格规避以上所有问题。")
        self._pending_task_target = new_meta
        self.tab_generation.log(
            f"⚠ 章节校验未通过 ({len(reasons)} 个问题),死磕重写...剩余 {retry-1} 次", "warn")
        for r in reasons:
            self.tab_generation.log(f"  · {r}", "warn")
        self.worker.submit({
            "action": "send_prompt",
            "prompt": stronger,
            "task_id": meta.get("label", "章节"),
            "url": self.tab_generation.url_input.text().strip(),
            "type_delay_ms": 5,
        })

    def _accept_chapter_and_continue(self, content, meta):
        """章节通过校验或死磕用尽 → 入库并触发后续链"""
        if meta.get("target") == "golden_three":
            self._split_and_save_golden_three(content)
            last_ch_num = len(self.chapters)
        else:
            ch_num = meta.get("ch_num", len(self.chapters) + 1)
            ch_title = self._extract_chapter_title(content) or f"第{ch_num}章"
            ch_body = self._strip_chapter_title(content)
            self.chapters.append({"title": ch_title, "content": ch_body, "summary": ""})
            self._refresh_chapter_list()
            if self.tab_generation.auto_save.isChecked():
                self._save_chapter_to_disk(self.chapters[-1])
            actual = len(re.sub(r'\s', '', content))
            self.tab_generation.log(
                f"✓ 第 {ch_num} 章生成成功!字数:{actual} 字", "success")
            last_ch_num = ch_num

        self._batch_remaining -= 1

        # 后置链:Canon 抽取 → 摘要 → after_chapter 技能 → 下一章
        # (用 QTimer 错开,避免一窝蜂砸到 worker)
        self._post_chapter_chain(last_ch_num)

    def _post_chapter_chain(self, ch_num):
        """章节通过后的链式处理:Canon 抽取 → 章末技能 → 摘要 → 下一章"""
        if ch_num <= 0:
            return
        pipeline = []
        if self.tab_canon.chk_extract.isChecked():
            pipeline.append(("canon_extract", ch_num))

        # after_chapter_generation 技能(固定自动触发)
        for s in self.tab_skills.get_after_chapter_skills():
            pipeline.append(("skill_after", ch_num, s))

        # auto_match 技能(根据章节内容正则匹配触发)
        ch_content = (self.chapters[ch_num - 1].get("content", "")
                      if 0 < ch_num <= len(self.chapters) else "")
        for s in self.tab_skills.get_auto_match_skills(ch_content):
            self.tab_generation.log(
                f"🎯 auto_match 技能「{s['name']}」命中(第{ch_num}章)", "info")
            pipeline.append(("skill_after", ch_num, s))

        if self.tab_memory.auto_summarize.isChecked():
            need_more = self._batch_remaining > 0 and not self._batch_paused
            pipeline.append(("summary", ch_num, need_more))
        else:
            need_more = self._batch_remaining > 0 and not self._batch_paused
            if need_more:
                pipeline.append(("next_chapter",))
            else:
                pipeline.append(("end_batch",))

        self._post_chapter_pipeline = pipeline
        QTimer.singleShot(800, self._run_next_post_chapter_step)

    def _run_next_post_chapter_step(self):
        """后置流水线推进"""
        if not getattr(self, "_post_chapter_pipeline", None):
            return
        step = self._post_chapter_pipeline.pop(0)
        if step[0] == "canon_extract":
            ch = self.chapters[step[1] - 1] if step[1] <= len(self.chapters) else None
            if ch and ch.get("content"):
                self._run_canon_extract(ch["content"], step[1])
            else:
                QTimer.singleShot(100, self._run_next_post_chapter_step)
        elif step[0] == "skill_after":
            ch_num, skill = step[1], step[2]
            self._run_skill_on_chapter(skill, ch_num, chain_post=True)
        elif step[0] == "summary":
            ch_num, need_more = step[1], step[2]
            self._submit_summary_task(ch_num, chain_to_next=need_more)
        elif step[0] == "next_chapter":
            QTimer.singleShot(800, self._send_next_chapter)
        elif step[0] == "end_batch":
            self.tab_generation.log("批量生成已结束", "info")

    def gen_current_summary(self):
        """生成当前选中章节的摘要"""
        idx = self.chapter_list.currentRow()
        if idx < 0:
            QMessageBox.information(self, "提示", "请先在左侧选中一章")
            return
        # 同步当前编辑器内容到 chapters
        if self.current_chapter_index == idx:
            self.chapters[idx]["title"] = self.tab_editor.title_input.text()
            self.chapters[idx]["content"] = self.tab_editor.content_edit.toPlainText()
        if not self.chapters[idx].get("content", "").strip():
            QMessageBox.warning(self, "提示", "本章正文为空,无法生成摘要")
            return
        self._submit_summary_task(idx + 1, chain_to_next=False)

    def gen_all_missing_summaries(self):
        """补齐所有缺失的章节摘要"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "还没有章节内容")
            return
        sums = self.tab_memory.parse_summaries()
        missing = []
        for i, ch in enumerate(self.chapters):
            n = i + 1
            if n not in sums and ch.get("content", "").strip():
                missing.append(n)
        if not missing:
            QMessageBox.information(self, "提示", "所有章节都已有摘要")
            return
        self.tab_generation.log(
            f"准备补齐 {len(missing)} 章摘要(将依次发到浏览器队列)", "info")
        # 依次提交,worker 会按顺序处理
        for n in missing:
            self._submit_summary_task(n, chain_to_next=False)

    def extract_characters(self, chain_full_memory=False):
        """从最新章节提取/更新角色档案"""
        if not self.chapters:
            if not chain_full_memory:
                QMessageBox.information(self, "提示", "还没有章节内容")
            return False
        # 流水线模式:扫描更多章节(最多 5 章)以获得更全面的角色档案
        recent = self.chapters[-5:] if chain_full_memory else self.chapters[-3:]
        content = "\n\n".join(
            f"{ch.get('title', '')}\n{ch.get('content', '')[:2500]}" for ch in recent)
        existing = self.tab_memory.chars_edit.toPlainText().strip()
        existing_block = (
            f"已有的角色档案(请在此基础上更新/补充):\n{existing}\n\n"
            if existing else "")
        prompt = PROMPTS["character_extract"].format(
            existing=existing_block, content=content[:8000])
        self._send_to_ai(
            prompt, "角色提取",
            target="character_extract",
            chain_full_memory=chain_full_memory,
        )
        return True

    def extract_long_term(self, chain_full_memory=False):
        """从最新章节提取长期记忆"""
        if not self.chapters:
            if not chain_full_memory:
                QMessageBox.information(self, "提示", "还没有章节内容")
            return False
        ch = self.chapters[-1]
        if not ch.get("content", "").strip():
            if not chain_full_memory:
                QMessageBox.warning(self, "提示", "最新章节正文为空")
            return False
        content = f"{ch.get('title', '')}\n{ch.get('content', '')[:5000]}"
        prompt = PROMPTS["long_term_extract"].format(content=content)
        self._send_to_ai(
            prompt, f"长期记忆-{ch.get('title', '')}",
            target="long_term_extract",
            chain_full_memory=chain_full_memory,
        )
        return True

    # ===================================================================
    # 一键生成对话记忆 - 流水线
    # ===================================================================
    def gen_full_memory(self):
        """一键生成完整对话记忆: 补齐摘要 → 提取角色 → 提取长期记忆"""
        if not self.chapters:
            QMessageBox.warning(self, "提示", "还没有章节内容,无法生成对话记忆")
            return
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录。")
            return
        if self._full_memory_running:
            QMessageBox.information(self, "提示", "当前一键生成正在进行中,请等待或点中止")
            return

        # 构造流水线:[(step, arg), ...]
        pipeline = []
        # 第 1 阶段:补齐所有缺失的摘要
        sums = self.tab_memory.parse_summaries()
        missing = []
        for i, ch in enumerate(self.chapters):
            n = i + 1
            if n not in sums and ch.get("content", "").strip():
                missing.append(n)
                pipeline.append(("summary", n))
        # 第 2 阶段:提取角色档案(只一次)
        pipeline.append(("character", None))
        # 第 3 阶段:提取长期记忆(只一次)
        pipeline.append(("long_term", None))

        self._full_memory_pipeline = pipeline
        self._full_memory_total = len(pipeline)
        self._full_memory_running = True

        # UI 反馈
        self.tab_memory.btn_gen_full_memory.setEnabled(False)
        self.tab_memory.btn_stop_full_memory.setEnabled(True)
        steps_desc = (
            f"{len(missing)} 个缺失摘要 + 角色档案 + 长期记忆"
            if missing else "角色档案 + 长期记忆(摘要已齐全)")
        self.tab_memory.update_progress(
            f"启动:共 {self._full_memory_total} 步({steps_desc})", "running")
        self.tab_generation.log(
            f"▶ 一键生成对话记忆启动,共 {self._full_memory_total} 步:{steps_desc}",
            "info")
        self.tabs.setCurrentWidget(self.tab_memory)

        self._run_next_full_memory_step()

    def _run_next_full_memory_step(self):
        """流水线推进一步"""
        if not self._full_memory_running:
            return
        if not self._full_memory_pipeline:
            # 全部完成
            self._full_memory_running = False
            self.tab_memory.btn_gen_full_memory.setEnabled(True)
            self.tab_memory.btn_stop_full_memory.setEnabled(False)
            self.tab_memory.update_progress("✓ 对话记忆生成完成!", "success")
            self.tab_generation.log("✓ 一键生成对话记忆全部完成", "success")
            # 自动刷新预览
            self._refresh_memory_preview()
            return

        step, arg = self._full_memory_pipeline.pop(0)
        done = self._full_memory_total - len(self._full_memory_pipeline)
        progress_prefix = f"[{done}/{self._full_memory_total}]"

        if step == "summary":
            self.tab_memory.update_progress(
                f"{progress_prefix} 正在生成第 {arg} 章摘要...", "running")
            self._submit_summary_task(arg, chain_full_memory=True)
        elif step == "character":
            self.tab_memory.update_progress(
                f"{progress_prefix} 正在提取角色档案...", "running")
            ok = self.extract_characters(chain_full_memory=True)
            if not ok:
                # 跳过本步
                self._run_next_full_memory_step()
        elif step == "long_term":
            self.tab_memory.update_progress(
                f"{progress_prefix} 正在提取长期记忆...", "running")
            ok = self.extract_long_term(chain_full_memory=True)
            if not ok:
                self._run_next_full_memory_step()

    def stop_full_memory(self):
        """中止一键生成"""
        if not self._full_memory_running:
            return
        self._full_memory_running = False
        self._full_memory_pipeline = []
        self.tab_memory.btn_gen_full_memory.setEnabled(True)
        self.tab_memory.btn_stop_full_memory.setEnabled(False)
        self.tab_memory.update_progress("已中止", "error")
        self.tab_generation.log("一键生成对话记忆已中止", "warn")

    def _popup_choose_target(self, content):
        """没指定 target 时让用户选回填位置"""
        if not content.strip(): return
        box = QMessageBox(self)
        box.setWindowTitle("抓取成功")
        box.setText(f"已抓取 {len(content)} 字符,填到哪里?")
        b1 = box.addButton("当前章节正文", QMessageBox.AcceptRole)
        b2 = box.addButton("创意灵感", QMessageBox.AcceptRole)
        b3 = box.addButton("章节大纲", QMessageBox.AcceptRole)
        b4 = box.addButton("作品简介", QMessageBox.AcceptRole)
        b5 = box.addButton("仅复制到剪贴板", QMessageBox.RejectRole)
        box.exec_()
        c = box.clickedButton()
        if c is b1:
            self.tab_editor.content_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_editor)
        elif c is b2:
            self.tab_settings.inspiration_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_settings)
        elif c is b3:
            self.tab_outline.chapter_outline_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_outline)
        elif c is b4:
            self.tab_outline.intro_edit.setPlainText(content)
            self.tabs.setCurrentWidget(self.tab_outline)
        else:
            QApplication.clipboard().setText(content)
            self.tab_generation.log("已复制到剪贴板", "info")

    def gen_inspiration(self):
        genres = self.tab_settings.get_selected_genres()
        if not genres:
            QMessageBox.warning(self, "提示", "请至少选一个题材"); return
        prompt = PROMPTS["creative_inspiration"].format(genre="/".join(genres))
        self._send_to_ai(prompt, "创意灵感", target="inspiration")

    def gen_title(self):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        insp = self.tab_settings.get_inspiration()
        if not insp.strip():
            QMessageBox.warning(self, "提示", "请先填写创意灵感"); return
        prompt = PROMPTS["title"].format(
            genre="/".join(genres), inspiration=insp,
            platform=self.tab_settings.get_platform())
        self._send_to_ai(prompt, "AI生成书名", target="title")

    def gen_outline_all(self):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        insp = self.tab_settings.get_inspiration()
        if not insp.strip():
            QMessageBox.warning(self, "提示", "请先填写创意灵感"); return
        cc = self.tab_settings.get_chapter_count()
        self.tab_outline.chapter_count.setValue(cc)
        special = self.tab_outline.special_edit.toPlainText()
        full_settings = self.tab_settings.get_full_settings_block()
        extra_parts = [f"\n\n【完整设定】\n{full_settings}"]
        if special.strip():
            extra_parts.append(f"\n【特殊需求/外部资料】\n{special}")
        detail = self.tab_settings.get_outline_detail()
        extra_parts.append(
            f"\n【大纲详细度】{detail}"
            f"({'每章一句话' if detail == '简洁' else '每章 50-80 字' if detail == '标准' else '每章 100-200 字,含主要情节、冲突、转折'})")
        extra = "".join(extra_parts)
        prompt = PROMPTS["outline_full"].format(
            genre="/".join(genres), inspiration=insp,
            chapter_count=cc, extra=extra)
        self._send_to_ai(prompt, "完整大纲", target="outline_full")

    def gen_outline_part(self, part_name):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        insp = self.tab_settings.get_inspiration()
        extra = f"\n【完整设定参考】\n{self.tab_settings.get_full_settings_block()}"
        if part_name == "章节大纲":
            extra += f"\n总章节数:{self.tab_settings.get_chapter_count()} 章。"
        prompt = PROMPTS["outline_part"].format(
            part_name=part_name, genre="/".join(genres),
            inspiration=insp, extra=extra)
        self._send_to_ai(prompt, part_name, target=f"outline_part:{part_name}")

    def extract_intro(self):
        seed = self.tab_outline.seed_edit.toPlainText()
        wv = self.tab_outline.worldview_edit.toPlainText()
        st = self.tab_outline.structure_edit.toPlainText()
        if not (seed or wv or st):
            QMessageBox.warning(self, "提示", "请先填写大纲内容"); return
        prompt = PROMPTS["intro"].format(seed=seed, worldview=wv, structure=st)
        self._send_to_ai(prompt, "作品简介", target="intro")

    def gen_golden_three(self):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        full = self.tab_settings.get_full_settings_block()
        prompt = PROMPTS["golden_three"].format(
            title=self.tab_settings.get_title(),
            genre="/".join(genres),
            inspiration=self.tab_settings.get_inspiration(),
            ch_outline=self.tab_outline.chapter_outline_edit.toPlainText()[:3000]
        ) + f"\n\n【完整设定】\n{full}"
        self._send_to_ai(prompt, "黄金三章", target="golden_three")

    def start_generation(self):
        """开始批量自动生成 - 真自动:发送→等回复→抓取→存章节→发下一章"""
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录。")
            return
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        if not co.strip():
            QMessageBox.warning(self, "提示", "请先生成或填写章节大纲"); return
        # 启动批量
        self._batch_remaining = self.tab_generation.batch_count.value()
        self._batch_paused = False
        target = self.tab_settings.get_words_per_chapter()
        offset = self.tab_settings.get_prompt_offset()
        target_with_offset = max(500, target + offset)
        self.tab_generation.log(
            f"▶ 批量启动:{self._batch_remaining} 章,目标 {target_with_offset} 字"
            f"(基础 {target} {offset:+d}),死磕 {self.tab_generation.retry_count.value()} 次", "info")
        self._send_next_chapter()

    def batch_count_value(self):
        return self.tab_generation.batch_count.value()

    def pause_generation(self):
        self._batch_paused = True
        self._batch_remaining = 0
        self.tab_generation.log("⏸ 已请求停止批量(等待当前任务结束)", "warn")

    def grab_response(self):
        """手动触发抓取最后一条 AI 回复"""
        if not self.worker.is_ready():
            QMessageBox.warning(self, "提示", "请先启动浏览器"); return
        # target=None,弹窗让用户选回填位置
        self._pending_task_target = {"target": None, "label": "手动抓取"}
        self.worker.submit({"action": "just_grab", "task_id": "手动抓取"})

    def optimize_chapter(self, content):
        prompt = PROMPTS["ai_optimize"].format(content=content[:6000])
        self._send_to_ai(prompt, "AI润色", target="optimize")

    # ---- 其他 ----
    def _import_to(self, target_edit):
        path, _ = QFileDialog.getOpenFileName(self, "导入TXT", "", "文本 (*.txt)")
        if path:
            try:
                txt = Path(path).read_text(encoding="utf-8", errors="ignore")
                target_edit.setPlainText(txt)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取失败:{e}")

    def prelogin_ai(self):
        ai = self.tab_settings.get_selected_ai()
        url = AI_URLS.get(ai) or self.tab_settings.custom_url.text().strip()
        if not url:
            return
        self.tab_generation.url_input.setText(url)
        if ai in AI_URLS:
            self.tab_generation.site_combo.setCurrentText(ai)
        if not self.worker.is_ready():
            self.tab_generation.log(f"启动浏览器以登录 {ai}...", "info")
            self.launch_browser()
        else:
            self.worker.submit({"action": "navigate", "url": url})
            self.tab_generation.log(f"请在浏览器中完成 {ai} 的登录", "info")

    def closeEvent(self, event):
        """关闭主窗口时停止浏览器线程"""
        from PyQt5.QtCore import QSettings
        QSettings("NovelAI", "MainWindow").setValue("geometry", self.saveGeometry())
        self.tab_settings.save_settings()
        self._autosave()
        try:
            self.worker.stop()
        except Exception:
            pass
        event.accept()

    def _autosave(self):
        """自动保存到当前项目文件，若无则保存到 autosave.json"""
        try:
            if 0 <= self.current_chapter_index < len(self.chapters):
                self.chapters[self.current_chapter_index]["title"] = self.tab_editor.title_input.text()
                self.chapters[self.current_chapter_index]["content"] = self.tab_editor.content_edit.toPlainText()
            save_path = self.current_project_file or str(self.project_dir / "autosave.json")
            s = self.tab_settings
            d = {
                "title": s.get_title(),
                "inspiration": s.get_inspiration(),
                "seed": self.tab_outline.seed_edit.toPlainText(),
                "worldview": self.tab_outline.worldview_edit.toPlainText(),
                "lo": self.tab_outline.lo_edit.toPlainText(),
                "structure": self.tab_outline.structure_edit.toPlainText(),
                "chapter_outline": self.tab_outline.chapter_outline_edit.toPlainText(),
                "intro": self.tab_outline.intro_edit.toPlainText(),
                "chapters": self.chapters,
                "memory": {
                    "characters": self.tab_memory.chars_edit.toPlainText(),
                    "summaries": self.tab_memory.summaries_edit.toPlainText(),
                    "long_term": self.tab_memory.long_term_edit.toPlainText(),
                    "auto_summarize": self.tab_memory.auto_summarize.isChecked(),
                    "auto_inject": self.tab_memory.auto_inject.isChecked(),
                    "recent_n": self.tab_memory.recent_n.value(),
                    "summary_len": self.tab_memory.summary_len.value(),
                },
                "canon": self.tab_canon.serialize_for_save(),
                "skills": self.tab_skills.serialize_for_save(),
                "critique": self.tab_generation.critique_config(),
                "conv_slots": self.tab_generation.conv_switcher.serialize_for_save(),
                "lifespan_loops": (
                    self.tab_lifespan.serialize_for_save()
                    if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None)
                    else {}
                ),
                "advanced": {
                    "genres": s.get_selected_genres(),
                    "platform": s.get_platform(),
                    "audience": s.get_audience(),
                    "density": s.get_density(),
                    "growth": s.get_growth(),
                    "conflict": s.get_conflict(),
                    "era": s.get_era(),
                    "chapter_count": s.get_chapter_count(),
                    "words_per_chapter": s.get_words_per_chapter(),
                    "outline_detail": s.get_outline_detail(),
                    "style_weights": s.get_style_weights(),
                    "rhythm": s.get_rhythm(),
                    "endings": s.get_endings(),
                    "creation_mode": s.get_creation_mode(),
                    "prompt_offset": s.get_prompt_offset(),
                    "golden_fingers": s.get_golden_fingers(),
                    "personas": s.get_personas(),
                    "ai": s.get_selected_ai(),
                },
                "saved_at": datetime.now().isoformat(),
                "gen_url": self.tab_generation.url_input.text(),
                "gen_site": self.tab_generation.site_combo.currentText(),
            }
            Path(save_path).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            self.statusBar().showMessage(f"自动保存失败:{e}", 5000)

    def _autoload(self):
        """启动时自动加载上次的项目"""
        autosave = self.project_dir / "autosave.json"
        if not autosave.exists():
            return
        try:
            d = json.loads(autosave.read_text(encoding="utf-8"))
            self.chapters = d.get("chapters", [])
            self.tab_settings.title_input.setText(d.get("title", ""))
            self.tab_settings.inspiration_edit.setPlainText(d.get("inspiration", ""))
            self.tab_outline.seed_edit.setPlainText(d.get("seed", ""))
            self.tab_outline.worldview_edit.setPlainText(d.get("worldview", ""))
            self.tab_outline.lo_edit.setPlainText(d.get("lo", ""))
            self.tab_outline.structure_edit.setPlainText(d.get("structure", ""))
            self.tab_outline.chapter_outline_edit.setPlainText(d.get("chapter_outline", ""))
            self.tab_outline.intro_edit.setPlainText(d.get("intro", ""))
            adv = d.get("advanced", {})
            if adv:
                self._apply_advanced(adv)
            mem = d.get("memory", {})
            if mem:
                self.tab_memory.chars_edit.setPlainText(mem.get("characters", ""))
                self.tab_memory.summaries_edit.setPlainText(mem.get("summaries", ""))
                self.tab_memory.long_term_edit.setPlainText(mem.get("long_term", ""))
                self.tab_memory.auto_summarize.setChecked(mem.get("auto_summarize", True))
                self.tab_memory.auto_inject.setChecked(mem.get("auto_inject", True))
                self.tab_memory.recent_n.setValue(int(mem.get("recent_n", 3)))
                self.tab_memory.summary_len.setValue(int(mem.get("summary_len", 80)))
            if d.get("canon"):
                self.tab_canon.load_from_dict(d["canon"])
            if d.get("skills"):
                self.tab_skills.load_from_dict(d["skills"])
            crit = d.get("critique", {})
            if crit:
                self.tab_generation.chk_crit_words.setChecked(crit.get("word_count", True))
                self.tab_generation.chk_crit_hook.setChecked(crit.get("hook", True))
                self.tab_generation.chk_crit_canon.setChecked(crit.get("canon", True))
                self.tab_generation.chk_crit_rhythm.setChecked(crit.get("rhythm", False))
                self.tab_generation.chk_crit_char.setChecked(crit.get("character", False))
            if d.get("conv_slots"):
                self.tab_generation.conv_switcher.load_from_dict(d["conv_slots"])
            if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None and d.get("lifespan_loops")):
                self.tab_lifespan.load_from_dict(d["lifespan_loops"])
            # 恢复生成控制 URL
            if d.get("gen_url"):
                self.tab_generation.url_input.setText(d["gen_url"])
            if d.get("gen_site"):
                self.tab_generation.site_combo.setCurrentText(d["gen_site"])
            self._refresh_chapter_list()
            self.statusBar().showMessage("已恢复上次自动保存的项目", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"自动加载失败:{e}", 5000)

    def new_project(self):
        if QMessageBox.question(
            self, "新建项目", "新建将清空所有数据,继续?"
        ) != QMessageBox.Yes: return
        self.chapters.clear()
        self.current_chapter_index = -1
        self.current_project_file = None
        self.tab_editor.load_chapter("", "")
        for w in [
            self.tab_settings.title_input, self.tab_settings.inspiration_edit,
            self.tab_outline.special_edit, self.tab_outline.intro_edit,
            self.tab_outline.seed_edit, self.tab_outline.worldview_edit,
            self.tab_outline.lo_edit, self.tab_outline.structure_edit,
            self.tab_outline.chapter_outline_edit,
            # 对话记忆
            self.tab_memory.chars_edit, self.tab_memory.summaries_edit,
            self.tab_memory.long_term_edit, self.tab_memory.preview_edit,
        ]:
            (w.clear() if hasattr(w, 'clear') else w.setPlainText(""))
        self._refresh_chapter_list()
        self.statusBar().showMessage("新项目已创建", 3000)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开", str(self.project_dir), "项目 (*.json)")
        if not path: return
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            self.chapters = d.get("chapters", [])
            self.tab_settings.title_input.setText(d.get("title", ""))
            self.tab_settings.inspiration_edit.setPlainText(d.get("inspiration", ""))
            self.tab_outline.seed_edit.setPlainText(d.get("seed", ""))
            self.tab_outline.worldview_edit.setPlainText(d.get("worldview", ""))
            self.tab_outline.lo_edit.setPlainText(d.get("lo", ""))
            self.tab_outline.structure_edit.setPlainText(d.get("structure", ""))
            self.tab_outline.chapter_outline_edit.setPlainText(d.get("chapter_outline", ""))
            self.tab_outline.intro_edit.setPlainText(d.get("intro", ""))
            # 还原高级设定
            adv = d.get("advanced", {})
            if adv:
                self._apply_advanced(adv)
            # 还原对话记忆
            mem = d.get("memory", {})
            if mem:
                self.tab_memory.chars_edit.setPlainText(mem.get("characters", ""))
                self.tab_memory.summaries_edit.setPlainText(mem.get("summaries", ""))
                self.tab_memory.long_term_edit.setPlainText(mem.get("long_term", ""))
                self.tab_memory.auto_summarize.setChecked(mem.get("auto_summarize", True))
                self.tab_memory.auto_inject.setChecked(mem.get("auto_inject", True))
                self.tab_memory.recent_n.setValue(int(mem.get("recent_n", 3)))
                self.tab_memory.summary_len.setValue(int(mem.get("summary_len", 80)))
            # 还原 Canon 设定档(B 模块)
            if d.get("canon"):
                self.tab_canon.load_from_dict(d["canon"])
            # 还原技能库(D 模块)
            if d.get("skills"):
                self.tab_skills.load_from_dict(d["skills"])
            # 还原章节质量校验配置(C 模块)
            crit = d.get("critique", {})
            if crit:
                self.tab_generation.chk_crit_words.setChecked(crit.get("word_count", True))
                self.tab_generation.chk_crit_hook.setChecked(crit.get("hook", True))
                self.tab_generation.chk_crit_canon.setChecked(crit.get("canon", True))
                self.tab_generation.chk_crit_rhythm.setChecked(crit.get("rhythm", False))
                self.tab_generation.chk_crit_char.setChecked(crit.get("character", False))
            # 还原对话槽(E 模块)
            if d.get("conv_slots"):
                self.tab_generation.conv_switcher.load_from_dict(d["conv_slots"])
            # 寿元/伏笔(可选模块)
            if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None
                    and d.get("lifespan_loops")):
                self.tab_lifespan.load_from_dict(d["lifespan_loops"])
            self.current_project_file = path
            self.current_chapter_index = -1
            self._refresh_chapter_list()
            self.statusBar().showMessage(f"已打开:{path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开失败:{e}")

    def _apply_advanced(self, adv):
        """根据存档还原创作设置中的高级选项"""
        s = self.tab_settings
        # 题材
        for n, cb in s.genre_checks.items():
            cb.setChecked(n in adv.get("genres", []))
        # 单选项
        def _set_radio(group, value):
            for b in group.buttons():
                if b.text() == value:
                    b.setChecked(True); return
        _set_radio(s.platform_group, adv.get("platform", "番茄小说"))
        _set_radio(s.audience_group, adv.get("audience", "成人"))
        _set_radio(s.density_group, adv.get("density", "极致爽"))
        _set_radio(s.growth_group, adv.get("growth", "爆发型"))
        _set_radio(s.conflict_group, adv.get("conflict", "极端"))
        _set_radio(s.detail_group, adv.get("outline_detail", "详细"))
        _set_radio(s.rhythm_group, adv.get("rhythm", "适中"))
        _set_radio(s.mode_group, adv.get("creation_mode", "创造版"))
        # 数值
        s.era_custom.setText(adv.get("era", "古代王朝"))
        s.chapter_custom.setValue(int(adv.get("chapter_count", 300)))
        s.words_custom.setValue(int(adv.get("words_per_chapter", 3000)))
        s.prompt_offset.setValue(int(adv.get("prompt_offset", -200)))
        # 风格滑块
        for n, v in adv.get("style_weights", {}).items():
            if n in s.style_sliders:
                s.style_sliders[n].setValue(int(v))
        # 多选
        for n, cb in s.ending_checks.items():
            cb.setChecked(n in adv.get("endings", []))
        for n, cb in s.golden_checks.items():
            cb.setChecked(n in adv.get("golden_fingers", []))
        for n, cb in s.persona_checks.items():
            cb.setChecked(n in adv.get("personas", []))


    def save_project(self):
        if 0 <= self.current_chapter_index < len(self.chapters):
            self.chapters[self.current_chapter_index]["title"] = self.tab_editor.title_input.text()
            self.chapters[self.current_chapter_index]["content"] = self.tab_editor.content_edit.toPlainText()
        if not self.current_project_file:
            path, _ = QFileDialog.getSaveFileName(
                self, "保存项目",
                str(self.project_dir / f"{self.tab_settings.get_title()}.json"),
                "项目 (*.json)")
            if not path: return
            self.current_project_file = path
        s = self.tab_settings
        d = {
            "title": s.get_title(),
            "inspiration": s.get_inspiration(),
            "seed": self.tab_outline.seed_edit.toPlainText(),
            "worldview": self.tab_outline.worldview_edit.toPlainText(),
            "lo": self.tab_outline.lo_edit.toPlainText(),
            "structure": self.tab_outline.structure_edit.toPlainText(),
            "chapter_outline": self.tab_outline.chapter_outline_edit.toPlainText(),
            "intro": self.tab_outline.intro_edit.toPlainText(),
            "chapters": self.chapters,
            # 对话记忆
            "memory": {
                "characters": self.tab_memory.chars_edit.toPlainText(),
                "summaries": self.tab_memory.summaries_edit.toPlainText(),
                "long_term": self.tab_memory.long_term_edit.toPlainText(),
                "auto_summarize": self.tab_memory.auto_summarize.isChecked(),
                "auto_inject": self.tab_memory.auto_inject.isChecked(),
                "recent_n": self.tab_memory.recent_n.value(),
                "summary_len": self.tab_memory.summary_len.value(),
            },
            # B 模块:Canon 设定档
            "canon": self.tab_canon.serialize_for_save(),
            # D 模块:技能库
            "skills": self.tab_skills.serialize_for_save(),
            # C 模块:章节质量校验配置
            "critique": self.tab_generation.critique_config(),
            # E 模块:对话槽
            "conv_slots": self.tab_generation.conv_switcher.serialize_for_save(),
            # 寿元/伏笔(可选模块)
            "lifespan_loops": (
                self.tab_lifespan.serialize_for_save()
                if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None)
                else {}
            ),
            # 高级设定
            "advanced": {
                "genres": s.get_selected_genres(),
                "platform": s.get_platform(),
                "audience": s.get_audience(),
                "density": s.get_density(),
                "growth": s.get_growth(),
                "conflict": s.get_conflict(),
                "era": s.get_era(),
                "chapter_count": s.get_chapter_count(),
                "words_per_chapter": s.get_words_per_chapter(),
                "outline_detail": s.get_outline_detail(),
                "style_weights": s.get_style_weights(),
                "rhythm": s.get_rhythm(),
                "endings": s.get_endings(),
                "creation_mode": s.get_creation_mode(),
                "prompt_offset": s.get_prompt_offset(),
                "golden_fingers": s.get_golden_fingers(),
                "personas": s.get_personas(),
                "ai": s.get_selected_ai(),
            },
            "saved_at": datetime.now().isoformat(),
        }
        Path(self.current_project_file).write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"已保存:{self.current_project_file}", 3000)

    def new_directory(self):
        name, ok = QInputDialog.getText(self, "新建目录", "目录名:")
        if ok and name:
            (self.project_dir / name).mkdir(exist_ok=True)
            QMessageBox.information(self, "完成", f"目录已创建:{self.project_dir / name}")

    def back_directory(self):
        QMessageBox.information(self, "项目目录", str(self.project_dir))

    def toggle_lock(self):
        ro = self.tab_editor.content_edit.isReadOnly()
        self.tab_editor.content_edit.setReadOnly(not ro)
        self.tab_editor.title_input.setReadOnly(not ro)
        self.statusBar().showMessage("已解锁,可以编辑" if ro else "已锁定,只读模式", 3000)

    def show_about(self):
        QMessageBox.about(
            self, "关于",
            "<h2>AI 写作工作台</h2>"
            "<p><b>技术栈:</b>Python 3 + PyQt5 + QtWebEngine</p>"
            "<p><b>核心特性:</b></p>"
            "<ul>"
            "<li>内置网页浏览器,挂载 DeepSeek/Doubao/Gemini 等 AI 网页</li>"
            "<li>内置提示词模板(灵感/大纲/章节/润色/书名/简介)</li>"
            "<li>章节管理 + JSON 项目存档 + 一键保存所有 TXT</li>"
            "<li>多题材、多平台、黄金三章、字数死磕</li>"
            "<li>JS 自动注入 + 半自动抓取回复</li>"
            "</ul>"
            "<p><i>提示:本程序为 UI 仿制 + 核心逻辑实现示例,"
            "用于学习交流。各 AI 网页 DOM 不同,自动化提交/采集需根据实际 DOM 微调。</i></p>"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ── 授权验证 ──────────────────────────
    from license_guard import LicenseGuard
    guard = LicenseGuard(app)
    if not guard.check():
        sys.exit(0)

    try:
        win = MainWindow()
        win.show()
    except Exception as e:
        import traceback
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "启动错误", traceback.format_exc())
        sys.exit(1)

    # 启动后台心跳
    guard.start_heartbeat(win)
    app.aboutToQuit.connect(guard.stop_heartbeat)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
