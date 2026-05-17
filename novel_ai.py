#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古超级写作助手
=============================================
基于 PyQt5 + Selenium 的本地小说创作辅助软件
- 挂载真实 Chrome / Edge,自动操作 DeepSeek / 豆包 / Gemini / 元宝 等 AI 网页
- 三种启动模式:attach(连接已开调试 Chrome,最稳)/ standalone / temp
- 内置盘古超级系统(禁用词过滤 + 感官铁律 + 压爆震 + 黄金三章公式)
- 章节列表 / 项目存档(JSON) / 一键保存所有章节
- 角色与世界 6 库自动同步 / 30 项质检 + AI 自动修复 / 章节元信息面板

运行依赖:
    pip install PyQt5 selenium
    (selenium 4.6+ 自动管理 driver,无需单独装 chromedriver)
"""

# ── 版本号(改这里就行,会同步到窗口标题/状态栏/关于框) ──
APP_VERSION = "v1.0.0"
APP_NAME    = "盘古超级写作助手"
APP_FULL    = f"{APP_NAME} {APP_VERSION}"

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
    QDialog, QTextBrowser, QDialogButtonBox, QListWidgetItem,
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QPlainTextEdit, QTabWidget,
    QListWidget, QListWidgetItem, QRadioButton, QCheckBox, QButtonGroup,
    QGroupBox, QSplitter, QFileDialog, QMessageBox, QInputDialog,
    QSpinBox, QFrame, QScrollArea, QGridLayout, QAction, QStatusBar,
    QSlider, QComboBox,
)
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QIcon, QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor

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
        "【输出格式要求-必须严格遵守】\n"
        "请严格按照以下6个【】标题分块输出,每个标题单独一行,顺序不可调换:\n"
        "【故事种子】\n一句话描述故事核心冲突、主角遭遇与情感主线\n\n"
        "【世界观】\n详细说明时代/地理/社会规则等\n\n"
        "【LO世界观层】\n世界观底层规则,支配人物行为的不可违反的逻辑\n\n"
        "【故事结构】\n开场→转折→高潮→结局,以及关键节点\n\n"
        "【章节大纲】\n按章节列出每章的具体情节(共{chapter_count}章)\n\n"
        "【简介】\n200字左右的作品简介,用于平台发布\n\n"
        "禁止用其他标题格式(如###、**加粗**等),必须用【】括起标题。\n\n"
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
        "请作为资深网文作者,生成《{title}》第 {chapter_num} 章。\n\n"
        "⚠️ 重要:必须输出完整章节,不要询问、不要简介、不要分点列表、不要『以下是章节』等开场白。\n\n"
        "【题材】{genre}\n"
        "【整体世界观/结构】\n{outline}\n\n"
        "【本章大纲】\n{chapter_outline}\n\n"
        "【输出格式-严格遵守】\n"
        "第一行: 第 {chapter_num} 章 章节名(章节名不超过15字,要有吸引力,概括本章核心冲突)\n"
        "第二行: 空行\n"
        "第三行起: 正文内容\n\n"
        "示例格式:\n"
        "第 {chapter_num} 章 觉醒之夜\n"
        "\n"
        "(正文第一句开始...)\n\n"
        "【写作要求】\n"
        "1. 本章字数严格控制在 {min_words}-{target_words} 字之间(必须达到,不含标题)\n"
        "2. 与上一章衔接顺畅,人物性格一致\n"
        "3. 对话生动、描写细腻、情节有节奏感\n"
        "4. 严禁血腥、暴力、色情、侮辱女性等违规内容\n"
        "5. 章末必须留有钩子(问号/省略号/转折词/新悬念)\n"
        "6. 如果上下文不足,请基于现有信息合理创作,不要询问用户\n"
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

    "style_audit": (
        "你是网文风格审稿员。请评估【新章节】的写作风格是否与【参考章节】保持一致。\n\n"
        "【参考章节】(已确认风格,作为基准):\n{reference}\n\n"
        "【新章节】(待审):\n{content}\n\n"
        "评估维度:\n"
        "1. 用词风格(口语/文雅/古风/现代)\n"
        "2. 节奏感(快节奏战斗/慢节奏铺垫/对话密度)\n"
        "3. 描写偏好(动作/心理/环境/对话比例)\n"
        "4. 角色语气(主角对白是否统一)\n\n"
        "输出格式(严格遵守):\n"
        "评分:X/10\n"
        "主要问题(不超过3条,每条1句话):\n"
        "  1. xxx\n"
        "  2. xxx\n"
        "改进建议:xxx\n"
    ),

    "world_extract": (
        "请从以下小说章节中提取结构化信息,严格按下面的 JSON 格式输出,不要任何前后缀说明,不要 markdown 代码块标记。\n\n"
        "{{\n"
        '  "characters": [\n'
        '    {{"name": "角色名", "role": "主角/女主/配角/导师/反派/路人", "appearance": "外貌简述", "personality": "性格", "mark": "口头禅或标志", "ability": "能力或职业", "state": "当前状态", "first_ch": "{ch_num}"}}\n'
        "  ],\n"
        '  "relations": [\n'
        '    {{"a": "角色A名字", "type": "师父/师弟/恋人/对手/血缘等", "b": "角色B名字", "note": "备注或起因"}}\n'
        "  ],\n"
        '  "items": [\n'
        '    {{"name": "物品名", "type": "法器/丹药/秘籍/材料/信物", "owner": "持有者", "source_ch": "{ch_num}", "ability": "能力或状态"}}\n'
        "  ],\n"
        '  "events": [\n'
        '    {{"ch": "{ch_num}", "event": "本章重大事件简述", "state_change": "主角状态变化(如:晋升金丹/获得XX/到达XX地)"}}\n'
        "  ],\n"
        '  "foreshadows": [\n'
        '    {{"ch": "{ch_num}", "content": "本章埋下的伏笔(神秘物品/隐藏身份/可疑话语)", "plan_pay_at": "建议第几章回收(如:30)"}}\n'
        "  ]\n"
        "}}\n\n"
        "提取规则:\n"
        "1. characters 只列【本章新出场】或【信息有更新】的角色,普通配角可省略\n"
        "2. relations 只列首次出现或变化的关系\n"
        "3. items 只列主角【新获得】的物品,不列敌人物品或一次性消耗品\n"
        "4. events 只列影响主线的重大事件,日常对话不算\n"
        "5. foreshadows 必须是【作者埋下、读者会记住的悬念】,不是普通铺垫\n"
        "6. plan_pay_at 根据伏笔重要性给出合理回收章节,无法判断填 '0'\n"
        "7. 若某类无内容,对应数组留空 [] 即可,不要省略整个字段\n\n"
        "已有数据(避免重复提取):\n{existing}\n\n"
        "本章是第 {ch_num} 章,正文:\n{content}"
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
        "**key 必须使用分类前缀**(共 6 类),便于按类别筛选:\n"
        "  · `角色.X.字段`   — X 的姓名、年龄、身份、外貌、能力、独有称号、当前状态\n"
        "  · `关系.X-Y.内容` — X 与 Y 的关系(债务/血缘/师徒/敌对/欠人情/暗恋等)\n"
        "  · `时间线.第N章.事件` — 已发生的关键事件、时间锚(几年前/几日后/N岁时)\n"
        "  · `物品.名称.字段` — 法器/功法书/装备/信物,字段如 持有人/来源/状态/能力\n"
        "  · `战力.体系名.字段` — 修为体系、技能/咒术、等级名、突破条件、任务进度\n"
        "  · `伏笔.内容简称.状态` — 已埋下未收的悬念(注:【断章钩子】里的伏笔由程序自动入库,这里只补 AI 觉得重要但格式没覆盖的)\n\n"
        "锁定 vs 演化:\n"
        "  · `mode=locked`:不会随剧情改变(年龄、身世、关键关系)\n"
        "  · `mode=evolving`:随剧情演化(修为、状态、好感度)\n\n"
        "现有设定档(避免重复提取):\n{existing}\n\n"
        "章节正文(章节号 {ch_num}):\n{content}\n\n"
        "请直接输出严格 JSON 数组,不要任何前后缀、不要 markdown 代码块,格式示例:\n"
        '[{{"key":"角色.林远.身份","value":"无灵根凡人","mode":"locked","ch":1}},'
        '{{"key":"关系.林远-王屠户.债务","value":"欠 3 两银子,有借条","mode":"locked","ch":1}},'
        '{{"key":"时间线.第1章.父死","value":"父亲三年前死于妖兽袭击","mode":"locked","ch":1}},'
        '{{"key":"物品.混元功.持有人","value":"林远(18岁开启)","mode":"locked","ch":1}},'
        '{{"key":"战力.咒术系统.等级","value":"虚弱诅咒(力量减半1时辰,代价3天虚弱)","mode":"evolving","ch":1}}]\n'
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

    "critique_laodao": (
        "你是老刀,从业十五年的资深网文编辑兼扑街作者收割机。\n"
        "- 你经手过多部百万订阅顶流爆款,也亲眼送走过三千多个扑街作者\n"
        "- 你坚信'捧杀害死的新人比差评多十倍',但凡你说一句'还行',作者就该改行\n"
        "- 你讨厌:注水开篇 / 立不住的人设 / 靠巧合推动的剧情\n"
        "- 你说话尖酸刻薄但每刀必扎具体问题,不做空泛嘲讽,不做人身攻击\n\n"
        "我会给你一段网文【正文】(可能是大纲或一章/多章),你需要:\n"
        "1. 用最毒最狠的话挖出问题,让作者疼到睡不着\n"
        "2. 每条批评必须精确定位到原文(引用原句 / 第X段)\n"
        "3. 每条批评后跟一条具体可执行的修改建议(不准说'多读书'/'自己体会')\n"
        "4. 最后给出综合诊断 + 三章弃书率预估\n\n"
        "8 个维度全部覆盖(有缺陷展开,无缺陷一句话带过):\n"
        "  1. 开篇钩子:前 300 字抓不抓得住,会不会 3 秒划走\n"
        "  2. 人设立不立得住:动机扎不扎实,有没有纸片感\n"
        "  3. 金手指:合理吗?白给还是有代价?\n"
        "  4. 冲突设计:真冲突还是硬凹的?反派是智障还是威胁?\n"
        "  5. 节奏与爽点:爽点密度,憋屈是否过久,铺垫爆发比例\n"
        "  6. 毒点排查:圣母/绿帽/降智/工具人女主/强行误会\n"
        "  7. 设定与世界观:硬伤 / 自相矛盾 / 缝合怪\n"
        "  8. 文笔与信息密度:废话注水 / 全是'他说她说' / 盘古禁用词违规\n\n"
        "【本次审查的网文正文】\n{content}\n\n"
        "严格按以下结构输出(纯文本,不要 markdown 代码块包裹):\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "【开场毒评】(一句话总结,越狠越好)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "【逐条开刀】(按严重程度排序,5-10 条,不凑数)\n\n"
        "❌ 问题1:[辛辣的名字, 如'主角人设薄得像 A4 纸']\n"
        "   📍 位置:[引用原文 / 第X段]\n"
        "   🔪 批评:[最毒的话, 说清问题在哪, 会怎么劝退读者]\n"
        "   🩹 改法:[具体到能直接落笔的修改方案]\n\n"
        "❌ 问题2: ...\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "【综合诊断】\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "- 致命伤(不改必扑):\n"
        "- 中等病(影响留存):\n"
        "- 小毛病(能忍但难受):\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "【存活概率评估】\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "- 当前版本三章弃书率预估:__%\n"
        "- 按我说的改完, 上架均订预估:____ 区间\n"
        "- 最后一句忠告:[最狠最真诚的一句]\n\n"
        "现在,老刀,开刀吧,别留情:"
    ),

    "pangu_autofix": (
        "你是【盘古超级系统】驻场修复员。下面是一篇章节,以及盘古 30 项质检发现的问题。\n"
        "请按建议**直接修复原文**,不要解释、不要 JSON、不要 markdown 代码块。\n\n"
        "修复规则:\n"
        "1. **只改有问题的地方**,没问题的段落原样保留,不要随意改\n"
        "2. **字数和章节结构基本保持**(允许 ±5%)\n"
        "3. 严格遵循盘古铁律(感官铁律 / 对话只用「说」/ 禁用词如「仿佛/似乎/知道/喊道/笑道」等)\n"
        "4. **不要在末尾加任何元信息**(不加【断章钩子】【本章爽点】【伏笔状态】【下一章选项】【本章完】等)\n"
        "5. 输出**整篇修复后的章节正文**,从第一句到最后一句,完整一篇\n\n"
        "【质检得分】{score} / 100\n"
        "【失败项编号】{failed}\n"
        "【AI 修改建议】\n{advice}\n\n"
        "【原章节正文】\n{content}\n\n"
        "现在请直接输出修复后的完整章节正文(只输出小说正文,无任何前后缀):"
    ),
}

# ---- 盘古超级系统(零侵入集成,新增) ----
try:
    from pangu_patch import install_pangu
    install_pangu(globals())  # 就地把 PROMPTS 字典套上盘古铁律
    PANGU_AVAILABLE = True
except ImportError:
    PANGU_AVAILABLE = False


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
# 三、章节编辑器(+ 盘古禁用词实时高亮器)
# =====================================================================
class _PanguForbiddenHighlighter(QSyntaxHighlighter):
    """章节编辑器实时高亮:盘古禁用词红色波浪线 + 长句段落浅黄底色。"""
    def __init__(self, parent):
        super().__init__(parent)
        # 词高亮格式
        self.fmt_forbidden = QTextCharFormat()
        self.fmt_forbidden.setUnderlineColor(QColor(220, 50, 50))
        self.fmt_forbidden.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        self.fmt_forbidden.setForeground(QColor(180, 0, 0))
        # AI 质检失败段落底色
        self.fmt_qcheck = QTextCharFormat()
        self.fmt_qcheck.setBackground(QColor(255, 245, 200))
        # 缓存:词列表 + qcheck 失败段落集合
        self._words = []
        self._qcheck_block_ids = set()  # 段落号(基于 blockNumber)
        try:
            from pangu_system import PanguEngine
            self._words = PanguEngine.get_active_forbidden_words()
        except Exception:
            self._words = []

    def refresh_words(self):
        try:
            from pangu_system import PanguEngine
            self._words = PanguEngine.get_active_forbidden_words()
        except Exception:
            self._words = []
        self.rehighlight()

    def set_qcheck_blocks(self, block_ids):
        """设置质检失败的段落号集合,触发重绘。"""
        self._qcheck_block_ids = set(block_ids or [])
        self.rehighlight()

    def clear_qcheck(self):
        self._qcheck_block_ids = set()
        self.rehighlight()

    def highlightBlock(self, text):
        # 段落底色(qcheck 标记)
        if self.currentBlock().blockNumber() in self._qcheck_block_ids:
            self.setFormat(0, len(text), self.fmt_qcheck)
        # 禁用词高亮
        for w in self._words:
            if not w:
                continue
            i = text.find(w)
            while i >= 0:
                self.setFormat(i, len(w), self.fmt_forbidden)
                i = text.find(w, i + 1)
class ChapterEditor(QWidget):
    save_requested = pyqtSignal(str, str)
    optimize_requested = pyqtSignal(str)
    save_all_requested = pyqtSignal()
    # 盘古超级系统:3 个新信号
    pangu_quicklint_requested = pyqtSignal(str)
    pangu_qcheck_requested = pyqtSignal(str)
    laodao_critique_requested = pyqtSignal(str)
    pangu_spiral_requested = pyqtSignal(str)
    pangu_preview_prompt_requested = pyqtSignal()    # 预览章节 prompt
    # BUG-014:用户在元信息面板点了某条"下一章选项",把选项文本传给主程序,
    # 主程序在下次生成下一章时把它作为开局指引注入 prompt
    next_option_picked = pyqtSignal(str)

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
        # 盘古超级系统:3 个新功能按钮
        self.btn_pangu_lint = QPushButton("🛡️ 本地词扫")
        self.btn_pangu_lint.setStyleSheet(
            "background:#27ae60;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_lint.setToolTip("0-token 本地检测:禁用词/长句/破折号/三连点")
        self.btn_pangu_lint.clicked.connect(self._on_pangu_lint)
        self.btn_pangu_qcheck = QPushButton("📊 30项质检")
        self.btn_pangu_qcheck.setStyleSheet(
            "background:#e67e22;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_qcheck.setToolTip("发给 AI 跑盘古 30 项深度质检,返回 JSON")
        self.btn_pangu_qcheck.clicked.connect(self._on_pangu_qcheck)
        self.btn_laodao = QPushButton("🔪 老刀毒舌点评")
        self.btn_laodao.setStyleSheet(
            "background:#c0392b;color:white;padding:4px 10px;border-radius:3px;font-weight:bold;")
        self.btn_laodao.setToolTip(
            "请 AI 扮演十五年资深网文编辑老刀,毒舌点评当前章节。\n"
            "8 维度 + 致命伤 / 三章弃书率预估。\n"
            "如果点评不通过,会自动再跑一次。")
        self.btn_laodao.clicked.connect(self._on_laodao_critique)
        self.btn_pangu_spiral = QPushButton("🌀 螺旋诊断")
        self.btn_pangu_spiral.setStyleSheet(
            "background:#34495e;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_spiral.setToolTip("AI 诊断当前章节处于 P1-P7 哪个螺旋阶段")
        self.btn_pangu_spiral.clicked.connect(self._on_pangu_spiral)
        self.btn_pangu_preview = QPushButton("👁️ 预览Prompt")
        self.btn_pangu_preview.setStyleSheet(
            "background:#2c3e50;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_pangu_preview.setToolTip("查看下一章节生成时实际发给 AI 的完整 prompt(含盘古铁律)")
        self.btn_pangu_preview.clicked.connect(lambda: self.pangu_preview_prompt_requested.emit())
        self.btn_style_check = QPushButton("🎨 风格一致性检测")
        self.btn_style_check.setStyleSheet(
            "background:#9b59b6;color:white;padding:4px 10px;border-radius:3px;")
        self.btn_regen_alt = QPushButton("🎲 生成备选版本")
        self.btn_regen_alt.setStyleSheet(
            "background:#16a085;color:white;padding:4px 10px;border-radius:3px;")
        for b in (self.btn_save, self.btn_optimize, self.btn_save_all,
                  self.btn_pangu_lint, self.btn_pangu_qcheck, self.btn_laodao,
                  self.btn_pangu_spiral, self.btn_pangu_preview,
                  self.btn_style_check, self.btn_regen_alt):
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

        # ── 盘古元信息面板 (BUG-014 配套 GUI:把剥离出来的钩子/爽点/伏笔/下章选项展示)
        self.pangu_meta_box = QGroupBox(
            "📌 本章元信息(钩子/爽点/伏笔/下一章选项)— 已自动从正文剥离,会引导下一章生成")
        self.pangu_meta_box.setStyleSheet(
            "QGroupBox { border: 2px solid #b4884e; margin-top: 8px; padding-top: 14px; "
            "  background: #fffbf2; }"
            "QGroupBox::title { color: #b4884e; font-weight: bold; left: 10px; "
            "  font-size: 13px; }")
        pml = QVBoxLayout(self.pangu_meta_box)
        pml.setContentsMargins(8, 4, 8, 6)
        pml.setSpacing(4)
        # 顶部说明:这些信息会自动用于下一章生成
        tip = QLabel(
            "💡 这些信息**自动注入下一章生成**:钩子做开篇,选项做走向,爽点防重复。"
            "你也可以点下方按钮手动指定下一章开局。")
        tip.setWordWrap(True)
        tip.setStyleSheet(
            "color:#1a4480; padding:4px 6px; background:#eaf3ff; "
            "border-left:3px solid #1a4480; font-size:11px;")
        pml.addWidget(tip)
        self.pangu_hook_label = QLabel("断章钩子: —")
        self.pangu_hook_label.setWordWrap(True)
        self.pangu_hook_label.setStyleSheet("color:#444; padding:2px 4px;")
        pml.addWidget(self.pangu_hook_label)
        self.pangu_cool_label = QLabel("本章爽点: —")
        self.pangu_cool_label.setWordWrap(True)
        self.pangu_cool_label.setStyleSheet("color:#444; padding:2px 4px;")
        pml.addWidget(self.pangu_cool_label)
        self.pangu_seeds_label = QLabel("伏笔: —")
        self.pangu_seeds_label.setStyleSheet("color:#444; padding:2px 4px;")
        pml.addWidget(self.pangu_seeds_label)
        # 下一章选项区:3 个按钮,点哪个就用哪个开局生成下一章
        nl = QLabel("下一章选项(点按钮用此选项作为下一章开局指引):")
        nl.setStyleSheet("color:#666; padding:4px 4px 0; font-size:11px;")
        pml.addWidget(nl)
        self.pangu_next_opt_row = QHBoxLayout()
        self.pangu_next_opt_row.setSpacing(4)
        pml.addLayout(self.pangu_next_opt_row)
        self.pangu_next_opt_btns = []
        self.pangu_meta_box.setVisible(False)  # 章节没元信息时整块隐藏
        layout.addWidget(self.pangu_meta_box)

        # 盘古禁用词实时高亮(Phase A 新增)
        try:
            self.pangu_highlighter = _PanguForbiddenHighlighter(self.content_edit.document())
        except Exception:
            self.pangu_highlighter = None

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

    def _on_pangu_lint(self):
        # 本地 0-token 词扫
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空,没什么可扫的。")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古",
                "找不到 pangu_system.py,请确认它在仓库根目录。")
            return
        r = get_default_engine().quick_chapter_lint(c)
        status = "OK 通过" if r.get("pass") else "WARN 未通过"
        msg = f"{status}  得分 {r.get('score', 0)} / 100\n\n"
        issues = r.get("issues", [])
        if issues:
            msg += "问题清单:\n" + "\n".join(f"• {x}" for x in issues) + "\n\n"
        stats = r.get("stats", {})
        if stats:
            msg += "统计:\n"
            for k, v in stats.items():
                msg += f"  {k}: {v}\n"
        QMessageBox.information(self, "盘古本地词扫结果", msg)
        self.pangu_quicklint_requested.emit(c)

    def _on_pangu_qcheck(self):
        # 发起 30 项质检(调 AI)
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空")
            return
        self.pangu_qcheck_requested.emit(c)

    def _on_laodao_critique(self):
        # 发起老刀毒舌点评(调 AI)
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空")
            return
        self.laodao_critique_requested.emit(c)

    def _on_pangu_spiral(self):
        # 发起 P1-P7 螺旋诊断(调 AI)
        c = self.content_edit.toPlainText()
        if not c.strip():
            QMessageBox.information(self, "提示", "章节为空")
            return
        self.pangu_spiral_requested.emit(c)

    def load_chapter(self, title, content):
        self.title_input.setText(title)
        self.content_edit.setPlainText(content)
        # 章节没有 meta(纯 load 走这里),清空面板
        self._set_pangu_meta_display(None)

    def show_chapter(self, ch_dict, idx):
        """加载并跟踪当前章节索引(供风格检测和备选版本使用)"""
        self.current_index = idx
        self.title_input.setText(ch_dict.get("title", f"第{idx+1}章"))
        self.content_edit.setPlainText(ch_dict.get("content", ""))
        # 显示元信息(BUG-014:从 chapter dict 读 hook/cool_points/next_options)
        self._set_pangu_meta_display(ch_dict)

    def _set_pangu_meta_display(self, ch_dict):
        """根据章节 dict 更新盘古元信息面板。
        ch_dict 为 None 或没元信息 → 整块隐藏。"""
        # 清除旧的下一章选项按钮
        while self.pangu_next_opt_row.count():
            it = self.pangu_next_opt_row.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.pangu_next_opt_btns = []

        has_any = False
        if ch_dict:
            hook = ch_dict.get("hook") or {}
            cool = ch_dict.get("cool_points") or []
            opts = ch_dict.get("next_options") or []
            # 钩子
            if hook and (hook.get("type") or hook.get("content")):
                bits = []
                if hook.get("type"):      bits.append(hook["type"])
                if hook.get("intensity"): bits.append(hook["intensity"])
                head = " / ".join(bits)
                content = hook.get("content", "")
                self.pangu_hook_label.setText(f"<b>断章钩子:</b> [{head}] {content}")
                has_any = True
            else:
                self.pangu_hook_label.setText("断章钩子: —")
            # 爽点
            if cool:
                self.pangu_cool_label.setText(
                    "<b>本章爽点:</b> " + "  ".join(f"• {p}" for p in cool[:5]))
                has_any = True
            else:
                self.pangu_cool_label.setText("本章爽点: —")
            # 伏笔(从 chapter['hook']/['seeds_planted_count'] 拿,如有)
            sp = ch_dict.get("_pangu_seeds_summary") or ""
            if sp:
                self.pangu_seeds_label.setText(f"<b>伏笔:</b> {sp} (已自动入伏笔追踪库)")
                has_any = True
            else:
                self.pangu_seeds_label.setText("伏笔: — (没有埋雷/收雷)")
            # 下一章选项
            for i, opt in enumerate(opts[:5]):
                btn = QPushButton(f"{i+1}. {opt[:60]}{'…' if len(opt) > 60 else ''}")
                btn.setStyleSheet(
                    "QPushButton { text-align:left; padding:4px 8px; "
                    "background:#fff8ea; border:1px solid #e0c896; }"
                    "QPushButton:hover { background:#ffe9b8; }")
                btn.setToolTip(opt)
                btn.clicked.connect(lambda _, x=opt: self.next_option_picked.emit(x))
                self.pangu_next_opt_btns.append(btn)
                self.pangu_next_opt_row.addWidget(btn)
                has_any = True
            self.pangu_next_opt_row.addStretch()

        self.pangu_meta_box.setVisible(bool(has_any))

    current_index = -1  # 当前选中的章节索引(-1 表示无)


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

        # ---- 盘古超级系统开关 ----
        self.pangu_check = QCheckBox(
            "启用【盘古超级系统】(禁用词过滤 + 感官铁律 + 压爆震 + 黄金三章公式)")
        self.pangu_check.setChecked(True)
        self.pangu_check.setStyleSheet("color:#1a4480;font-weight:bold;")
        self.pangu_check.setToolTip(
            "勾选后,每个章节 prompt 会被盘古铁律自动包裹:\n"
            "• 116 个禁用词强制过滤(顿时/连忙/眼神深邃 等)\n"
            "• 视/听/触 三感必须齐全\n"
            "• 压 70%+ 爆 5%+ 震 25% 情绪曲线\n"
            "• 智商防火墙(防止角色降智)\n"
            "• 黄金三章公式(第 1-3 章强制套用)\n"
            "取消勾选则完全回到原版行为,可一键切换。")
        ai_layout.addWidget(self.pangu_check)

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
        self.box_genre = gbox  # 第 7 项:用于折叠链
        glay = QGridLayout(gbox)
        self.genre_checks = {}
        for r, row_data in enumerate(GENRES):
            for c, name in enumerate(row_data):
                cb = QCheckBox(name)
                if name in ("都市", "言情"):
                    cb.setChecked(True)
                self.genre_checks[name] = cb
                glay.addWidget(cb, r, c)
        # 第 3 项:加 "✏️ 自定义" 按钮(末行),弹 QInputDialog 输入新题材
        self._genre_custom_row = len(GENRES)
        self._genre_custom_col = 0
        self.btn_genre_custom = QPushButton("✏️ 自定义题材")
        self.btn_genre_custom.setStyleSheet(
            "QPushButton { color:#1a4480; padding:4px 8px; border:1px dashed #1a4480; }"
            "QPushButton:hover { background:#eaf3ff; }")
        self.btn_genre_custom.clicked.connect(self._add_custom_genre)
        glay.addWidget(self.btn_genre_custom, self._genre_custom_row, 0, 1, 4)
        self._genre_layout = glay  # 留引用,自定义条目时往里加
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

        # ---- 盘古禁用词白名单 ----
        wl_box = QGroupBox("🛡️ 盘古禁用词白名单(避免误杀,用空格/换行分隔)")
        wl_lay = QVBoxLayout(wl_box)
        self.pangu_whitelist_edit = QPlainTextEdit()
        self.pangu_whitelist_edit.setMaximumHeight(60)
        self.pangu_whitelist_edit.setPlaceholderText(
            "例如:仿佛 似乎 知道  (这些词会被允许出现在正文,不再被标红)")
        wl_lay.addWidget(self.pangu_whitelist_edit)
        wl_btn_row = QHBoxLayout()
        self.btn_pangu_wl_apply = QPushButton("✓ 应用白名单")
        self.btn_pangu_wl_apply.setStyleSheet(
            "background:#16a085;color:white;padding:4px 10px;border-radius:3px;")
        wl_btn_row.addWidget(self.btn_pangu_wl_apply)
        wl_btn_row.addStretch()
        wl_lay.addLayout(wl_btn_row)
        layout.addWidget(wl_box)

        # ---- 盘古快捷工具 ----
        pangu_tools_box = QGroupBox("🛕 盘古快捷工具")
        pangu_tools_lay = QVBoxLayout(pangu_tools_box)
        p_row1 = QHBoxLayout()
        self.btn_pangu_style = QPushButton("🎯 风格匹配(基于关键词)")
        self.btn_pangu_style.setStyleSheet(
            "background:#16a085;color:white;padding:6px 12px;border-radius:3px;")
        self.btn_pangu_style.setToolTip(
            "输入题材/灵感关键词,匹配主辅风格 + 女角色基调 + 适合平台")
        p_row1.addWidget(self.btn_pangu_style)
        p_row1.addStretch()
        pangu_tools_lay.addLayout(p_row1)
        p_row2 = QHBoxLayout()
        self.btn_pangu_arch = QPushButton("🏗️ 建筑师")
        self.btn_pangu_dream = QPushButton("🎭 造梦师")
        self.btn_pangu_alch = QPushButton("⚗️ 炼金术士")
        self.btn_pangu_sculpt = QPushButton("🗿 雕刻家")
        for b, color, tip in [
            (self.btn_pangu_arch, "#34495e", "结构/大纲/世界观:严密自洽,优先骨架"),
            (self.btn_pangu_dream, "#9b59b6", "氛围/情绪/意象:渲染感官与情绪密度"),
            (self.btn_pangu_alch, "#e67e22", "提纯/优化/字数死磕:精准压缩"),
            (self.btn_pangu_sculpt, "#7f8c8d", "成品/润色:先删再改、能砍的不改"),
        ]:
            b.setStyleSheet(
                f"background:{color};color:white;padding:6px 10px;border-radius:3px;")
            b.setToolTip(tip)
            p_row2.addWidget(b)
        p_row2.addStretch()
        pangu_tools_lay.addLayout(p_row2)
        layout.addWidget(pangu_tools_box)

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
        self.box_era = era_box  # 第 7 项
        era_lay = QHBoxLayout(era_box)
        self.era_combo = QComboBox()
        self.era_combo.setEditable(False)
        self.era_combo.addItems(ERAS)
        # 末尾加一个"✏️ 自定义..."条目
        self.era_combo.addItem("✏️ 自定义...")
        self.era_combo.setCurrentText("古代王朝")
        # 第 4 项:选中"自定义..."条目 → 弹输入框,新值加进下拉并选中
        def _on_era_changed(text):
            if text == "✏️ 自定义...":
                from PyQt5.QtWidgets import QInputDialog
                new_era, ok = QInputDialog.getText(
                    self, "自定义时代背景",
                    "输入新的时代背景(回车确认):")
                if ok and new_era.strip():
                    new_era = new_era.strip()
                    # 插入到"自定义..."条目前
                    insert_idx = self.era_combo.count() - 1
                    # 检查是否已存在
                    exist = self.era_combo.findText(new_era)
                    if exist >= 0:
                        self.era_combo.setCurrentIndex(exist)
                    else:
                        self.era_combo.insertItem(insert_idx, new_era)
                        self.era_combo.setCurrentText(new_era)
                    # 持久化自定义时代列表
                    self._save_custom_eras()
                else:
                    # 取消 → 回到上一个选项(不是自定义占位符)
                    if self.era_combo.count() > 1:
                        self.era_combo.setCurrentIndex(0)
        self.era_combo.currentTextChanged.connect(_on_era_changed)
        era_lay.addWidget(self.era_combo, 1)
        era_lay.addWidget(QLabel("自定义:"))
        self.era_custom = QLineEdit("古代王朝")
        era_lay.addWidget(self.era_custom, 1)
        layout.addWidget(era_box)
        # 启动时加载用户保存过的自定义时代
        try:
            self._load_custom_eras()
        except Exception:
            pass

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
        self.box_golden = gf_box  # 第 7 项
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
        # 第 5 项:金手指自定义按钮
        self._golden_grid = gf_grid
        btn_gf_custom = QPushButton("✏️ 自定义金手指")
        btn_gf_custom.setStyleSheet(
            "QPushButton { color:#1a4480; padding:4px 8px; border:1px dashed #1a4480; }"
            "QPushButton:hover { background:#eaf3ff; }")
        btn_gf_custom.clicked.connect(self._add_custom_golden)
        gf_outer.addWidget(btn_gf_custom)
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
        # 第 6 项:主角人设自定义按钮
        self._persona_grid = pe_grid
        btn_pe_custom = QPushButton("✏️ 自定义主角人设")
        btn_pe_custom.setStyleSheet(
            "QPushButton { color:#1a4480; padding:4px 8px; border:1px dashed #1a4480; }"
            "QPushButton:hover { background:#eaf3ff; }")
        btn_pe_custom.clicked.connect(self._add_custom_persona)
        pe_outer.addWidget(btn_pe_custom)
        layout.addWidget(pe_box)

        layout.addStretch()

        # 启动时从 QSettings 恢复白名单并应用
        try:
            from PyQt5.QtCore import QSettings as _QS
            _s = _QS("NovelAI", "CreationSettings")
            _wl = _s.value("pangu_whitelist", "", type=str)
            if _wl:
                self.pangu_whitelist_edit.setPlainText(_wl)
                try:
                    from pangu_system import PanguEngine
                    PanguEngine.set_whitelist(_wl)
                except Exception:
                    pass
        except Exception:
            pass

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
        # 盘古超级系统开关
        s.setValue("pangu_enabled", self.pangu_check.isChecked())
        s.setValue("pangu_whitelist", self.pangu_whitelist_edit.toPlainText())
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

    def enable_auto_save(self):
        """第 1 项: 任何设置改动后 1.5 秒自动持久化(debounce)
        防止用户改了设置没关窗口就丢失"""
        from PyQt5.QtCore import QTimer
        if hasattr(self, "_auto_save_timer"):
            return  # 已安装,不重复
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(1500)
        self._auto_save_timer.timeout.connect(self._auto_save_fire)

        def _dirty(*_a, **_kw):
            self._auto_save_timer.start()

        # 多选 checkbox 组
        for d in (self.genre_checks, self.ending_checks,
                  self.golden_checks, self.persona_checks):
            for cb in d.values():
                cb.toggled.connect(_dirty)
        # 单选 button group
        for grp in (self.platform_group, self.audience_group,
                    self.density_group, self.growth_group,
                    self.conflict_group, self.detail_group,
                    self.rhythm_group, self.mode_group, self.ai_group):
            grp.buttonClicked.connect(_dirty)
        # 数值 spinbox
        for sb in (self.chapter_custom, self.words_custom, self.prompt_offset):
            sb.valueChanged.connect(_dirty)
        # ComboBox / LineEdit / 单 checkbox / TextEdit
        self.era_combo.currentTextChanged.connect(_dirty)
        self.era_custom.textChanged.connect(_dirty)
        self.custom_url.textChanged.connect(_dirty)
        self.delay_check.toggled.connect(_dirty)
        self.pangu_check.toggled.connect(_dirty)
        self.pangu_whitelist_edit.textChanged.connect(_dirty)
        if hasattr(self, "special_edit"):
            self.special_edit.textChanged.connect(_dirty)
        # 风格滑块
        for sl in self.style_sliders.values():
            sl.valueChanged.connect(_dirty)

    def _auto_save_fire(self):
        """timer 到点,真实写盘"""
        try:
            self.save_settings()
        except Exception:
            pass  # 自动保存失败不影响 UI

    # ── 第 3/5/6 项:自定义选项 helpers ──────────────────
    def _add_custom_checkbox(self, title, target_dict, grid_layout, prefs_key):
        """通用:弹输入框 → 加 QCheckBox → 持久化到 QSettings"""
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, f"自定义{title}", f"输入新的{title}名称(回车确认):")
        if not (ok and name.strip()):
            return
        name = name.strip()
        if name in target_dict:
            return  # 重复忽略
        cb = QCheckBox(name)
        cb.setChecked(True)
        cb.setStyleSheet("QCheckBox { color:#b4884e; }")  # 自定义条目用米色区分
        target_dict[name] = cb
        # 找空格子追加(末行末尾)
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        existing = s.value(prefs_key, [], type=list) or []
        if name not in existing:
            existing.append(name)
        s.setValue(prefs_key, existing)
        # 添加到 grid:扫一遍找空位
        n = len(target_dict) - 1  # 当前位置
        r, c = n // 4, n % 4
        grid_layout.addWidget(cb, r + 100, c)  # 加大 row 偏移,避开预定义条目
        # 通知 auto_save dirty
        try:
            cb.toggled.connect(lambda: self._auto_save_timer.start()
                               if hasattr(self, "_auto_save_timer") else None)
        except Exception:
            pass

    def _add_custom_genre(self):
        self._add_custom_checkbox(
            "题材", self.genre_checks, self._genre_layout, "custom_genres")

    def _add_custom_golden(self):
        self._add_custom_checkbox(
            "金手指", self.golden_checks, self._golden_grid, "custom_goldens")

    def _add_custom_persona(self):
        self._add_custom_checkbox(
            "主角人设", self.persona_checks, self._persona_grid, "custom_personas")

    def _save_custom_eras(self):
        """把当前下拉里所有用户自定义的时代保存到 QSettings"""
        from PyQt5.QtCore import QSettings
        builtins = set(ERAS) | {"✏️ 自定义..."}
        custom = []
        for i in range(self.era_combo.count()):
            t = self.era_combo.itemText(i)
            if t not in builtins:
                custom.append(t)
        QSettings("NovelAI", "CreationSettings").setValue("custom_eras", custom)

    def _load_custom_eras(self):
        """启动时加载用户保存过的自定义时代,插到"自定义..."条目前"""
        from PyQt5.QtCore import QSettings
        custom = QSettings("NovelAI", "CreationSettings").value(
            "custom_eras", [], type=list) or []
        insert_at = self.era_combo.count() - 1  # 在"自定义..."前
        for era in custom:
            if era and self.era_combo.findText(era) < 0:
                self.era_combo.insertItem(insert_at, era)
                insert_at += 1

    def _load_custom_checks(self):
        """启动时把 QSettings 里的自定义题材/金手指/人设条目加回 UI"""
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        for prefs_key, target_dict, grid in [
            ("custom_genres",   self.genre_checks,   self._genre_layout),
            ("custom_goldens",  self.golden_checks,  self._golden_grid),
            ("custom_personas", self.persona_checks, self._persona_grid),
        ]:
            items = s.value(prefs_key, [], type=list) or []
            for name in items:
                if name in target_dict:
                    continue
                cb = QCheckBox(name)
                cb.setStyleSheet("QCheckBox { color:#b4884e; }")
                target_dict[name] = cb
                n = len(target_dict) - 1
                r, c = n // 4, n % 4
                grid.addWidget(cb, r + 100, c)

    def _install_collapsible_chain(self):
        """第 7 项:把题材/时代/金手指/主角人设 4 个 group 串成折叠链
        - 每个 box.setCheckable(True),勾掉 = 折叠内容(节省空间)
        - 每个 box(除最后)末尾加 ✓ 完成,继续下一项按钮:折叠当前 + 展开下一个
        - 配合 enable_auto_save 一起,改了立刻持久化"""
        boxes = [
            getattr(self, "box_genre", None),
            getattr(self, "box_era", None),
            getattr(self, "box_golden", None),
            getattr(self, "box_persona", None),
        ]
        boxes = [b for b in boxes if b is not None and b.layout() is not None]
        if len(boxes) < 2:
            return

        box_inner = {}
        # 步骤 1:让每个 box 可折叠
        for box in boxes:
            # 收集"现在的"layout 里所有 widget(我们加按钮之前)
            inner = []
            def _walk(lay, _out=inner):
                for j in range(lay.count()):
                    it = lay.itemAt(j)
                    w = it.widget() if it else None
                    if w:
                        _out.append(w)
                    sub = it.layout() if it else None
                    if sub:
                        _walk(sub, _out)
            _walk(box.layout())
            box_inner[id(box)] = inner
            box.setCheckable(True)
            box.setChecked(True)
            box.setToolTip("点标题左侧的勾选框可折叠 / 展开")

            def make_handler(w_list):
                def _on_toggled(checked):
                    for w in w_list:
                        w.setVisible(checked)
                return _on_toggled
            box.toggled.connect(make_handler(inner))

        # 步骤 2:除最后一个 box,都加 ✓ 完成按钮 → 折叠当前 + 展开下一个
        for i in range(len(boxes) - 1):
            cur = boxes[i]
            nxt = boxes[i + 1]
            btn = QPushButton("✓ 完成此项,自动跳到下一项")
            btn.setStyleSheet(
                "QPushButton { color:white; background:#2ecc71; padding:6px 14px; "
                "border-radius:3px; font-weight:bold; margin-top:6px; }"
                "QPushButton:hover { background:#27ae60; }")
            def make_next(cur_box=cur, nxt_box=nxt):
                def _f():
                    cur_box.setChecked(False)  # 折叠
                    nxt_box.setChecked(True)   # 展开下一个
                return _f
            btn.clicked.connect(make_next())
            cur.layout().addWidget(btn)
            # 按钮也归到 inner list:折叠时一起隐藏(只剩标题条)
            box_inner[id(cur)].append(btn)


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
        self.btn_rename = QPushButton("🔄 改名工具 (角色/地名/门派一键替换)")
        self.btn_rename.setStyleSheet(
            "background:#9b59b6;color:white;padding:4px 10px;border-radius:3px;font-weight:bold;")
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




# ═══════════════════════════════════════════════════════════════════
# 角色库 + 关系图谱 + 时间线 + 物品/法器库 + 伏笔追踪
# ═══════════════════════════════════════════════════════════════════
class CharacterLibrary(QWidget):
    """
    全方位角色与世界状态管理：
      - 角色库: 主角/配角/反派,每人含详细档案
      - 关系图谱: 师徒/敌对/暗恋/血缘
      - 时间线: 主角境界/年龄/势力/重大事件
      - 物品库: 法器/丹药/秘籍及来源
      - 伏笔追踪: 已埋伏笔与回收状态
    数据自动持久化到项目 JSON, 写章节时按需注入提示词。
    """
    
    def __init__(self):
        super().__init__()
        # 数据结构
        self.characters = []   # [{name, role, appearance, personality, ability, ...}]
        self.relations  = []   # [{from, to, type, note}]
        self.timeline   = []   # [{ch_num, event, hero_state}]
        self.items      = []   # [{name, owner, source, ability, status}]
        self.foreshadows= []   # [{ch_num, content, plan_pay_at, paid, paid_at}]
        # 新增:钩子编年 + 爽点编年
        self.hooks      = []   # [{ch_num, type, intensity, content}]
        self.cool_pts   = []   # [{ch_num, type, content}]
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 顶部: 内嵌标签页 (7个子模块)
        self.sub_tabs = QTabWidget()
        layout.addWidget(self.sub_tabs)
        
        self._build_characters_tab()
        self._build_relations_tab()
        self._build_timeline_tab()
        self._build_items_tab()
        self._build_power_tab()
        self._build_foreshadows_tab()
        self._build_hooks_tab()      # 新增:钩子编年
        self._build_coolpts_tab()    # 新增:爽点编年
        
        # 底部: 操作按钮
        btn_row = QHBoxLayout()
        self.chk_inject = QCheckBox("写章节时自动注入到提示词")
        self.chk_inject.setChecked(True)
        self.chk_inject.setToolTip(
            "勾选后,每次生成新章节会把:\n"
            " - 本章可能出场的角色档案\n"
            " - 主角当前状态(境界/位置/装备)\n"
            " - 待回收的伏笔\n"
            "自动拼到提示词里,有效防止人设崩坏与前后矛盾。")
        btn_row.addWidget(self.chk_inject)

        # BUG-014 配套:每章生成完后自动抽取 6 库(默认关,避免太多 AI 调用)
        self.chk_auto_extract = QCheckBox("✨ 每章生成后自动抽取到 6 库")
        self.chk_auto_extract.setChecked(False)
        self.chk_auto_extract.setToolTip(
            "勾选后,每生成完一章,自动调用 AI 提取:\n"
            "  角色 / 关系 / 时间线 / 物品 / 战力 / 伏笔\n"
            "并合并到这 6 个表里。\n"
            "代价:每章多 1 次 AI 调用。如果你 AI 额度有限,可以关掉,\n"
            "改成手动批量提取(下方「🔍 从已写章节提取角色」按钮)。")
        self.chk_auto_extract.setStyleSheet("QCheckBox { color:#b4884e; font-weight:bold; }")
        btn_row.addWidget(self.chk_auto_extract)

        btn_row.addStretch()
        
        self.btn_extract_from_chapters = QPushButton("🔍 从已写章节提取角色")
        self.btn_extract_from_chapters.setStyleSheet(
            "background:#3498db;color:white;padding:6px 12px;border-radius:3px;")
        btn_row.addWidget(self.btn_extract_from_chapters)
        
        self.btn_export = QPushButton("📥 导出库")
        btn_row.addWidget(self.btn_export)
        self.btn_import = QPushButton("📤 导入库")
        btn_row.addWidget(self.btn_import)
        
        layout.addLayout(btn_row)
        
        self.btn_export.clicked.connect(self._export_lib)
        self.btn_import.clicked.connect(self._import_lib)
    
    # ── 1. 角色库子页 ──────────────────────────────────────
    def _build_characters_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        # 顶部按钮
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增角色")
        btn_add.clicked.connect(self._add_character)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_character)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        # 表格
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_chars = QTableWidget(0, 8)
        self.tbl_chars.setHorizontalHeaderLabels([
            "姓名", "角色定位", "外貌", "性格", "口头禅/标志",
            "能力/职业", "当前状态", "首次出场"
        ])
        self.tbl_chars.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_chars.horizontalHeader().setStretchLastSection(True)
        self.tbl_chars.verticalHeader().setVisible(False)
        self.tbl_chars.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_chars.setColumnWidth(0, 100)
        self.tbl_chars.setColumnWidth(1, 80)
        self.tbl_chars.setColumnWidth(2, 150)
        self.tbl_chars.setColumnWidth(3, 150)
        self.tbl_chars.setColumnWidth(4, 120)
        self.tbl_chars.setColumnWidth(5, 120)
        self.tbl_chars.setColumnWidth(6, 120)
        lay.addWidget(self.tbl_chars)
        
        tip = QLabel(
            "💡 提示: 双击单元格直接编辑。【角色定位】填:主角/女主/配角/导师/反派/路人。\n"
            "    【当前状态】会随剧情更新,写章节时自动注入此字段保证前后一致。")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "👤 角色库")
    
    def _add_character(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_chars.rowCount()
        self.tbl_chars.insertRow(r)
        defaults = ["新角色", "配角", "", "", "", "", "", ""]
        for c, v in enumerate(defaults):
            self.tbl_chars.setItem(r, c, QTableWidgetItem(v))
    
    def _del_character(self):
        rows = sorted(set(idx.row() for idx in self.tbl_chars.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_chars.removeRow(r)
    
    # ── 2. 关系图谱子页 ────────────────────────────────────
    def _build_relations_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增关系")
        btn_add.clicked.connect(self._add_relation)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_relation)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_relations = QTableWidget(0, 4)
        self.tbl_relations.setHorizontalHeaderLabels([
            "角色A", "关系类型", "角色B", "备注"
        ])
        self.tbl_relations.horizontalHeader().setStretchLastSection(True)
        self.tbl_relations.verticalHeader().setVisible(False)
        self.tbl_relations.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_relations.setColumnWidth(0, 120)
        self.tbl_relations.setColumnWidth(1, 100)
        self.tbl_relations.setColumnWidth(2, 120)
        lay.addWidget(self.tbl_relations)
        
        tip = QLabel(
            "💡 关系类型示例: 师父/师弟/师妹/对手/暗恋对象/恋人/血缘/宿敌/同盟/上下级")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🔗 关系图谱")
    
    def _add_relation(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_relations.rowCount()
        self.tbl_relations.insertRow(r)
        defaults = ["", "师父", "", ""]
        for c, v in enumerate(defaults):
            self.tbl_relations.setItem(r, c, QTableWidgetItem(v))
    
    def _del_relation(self):
        rows = sorted(set(idx.row() for idx in self.tbl_relations.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_relations.removeRow(r)
    
    # ── 3. 时间线子页 ──────────────────────────────────────
    def _build_timeline_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        # 主角当前状态总览
        from PyQt5.QtWidgets import QFormLayout
        state_box = QGroupBox("📊 主角当前状态(写章节时自动注入)")
        sf = QFormLayout(state_box)
        self.hero_age = QLineEdit("18")
        self.hero_realm = QLineEdit("练气期一层")
        self.hero_location = QLineEdit("青云山·李家村")
        self.hero_faction = QLineEdit("无门无派")
        self.hero_mood = QLineEdit("平静")
        sf.addRow("主角年龄:", self.hero_age)
        sf.addRow("修为/境界:", self.hero_realm)
        sf.addRow("当前位置:", self.hero_location)
        sf.addRow("所属势力:", self.hero_faction)
        sf.addRow("近期心境:", self.hero_mood)
        lay.addWidget(state_box)
        
        # 重大事件时间线
        evt_label = QLabel("📅 重大事件时间线 (按章节顺序):")
        evt_label.setStyleSheet("font-weight:bold;margin-top:6px")
        lay.addWidget(evt_label)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增事件")
        btn_add.clicked.connect(self._add_event)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_event)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_timeline = QTableWidget(0, 3)
        self.tbl_timeline.setHorizontalHeaderLabels(["章节", "事件", "状态变化"])
        self.tbl_timeline.horizontalHeader().setStretchLastSection(True)
        self.tbl_timeline.verticalHeader().setVisible(False)
        self.tbl_timeline.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_timeline.setColumnWidth(0, 60)
        self.tbl_timeline.setColumnWidth(1, 350)
        lay.addWidget(self.tbl_timeline)
        
        self.sub_tabs.addTab(w, "📅 时间线")
    
    def _add_event(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_timeline.rowCount()
        self.tbl_timeline.insertRow(r)
        defaults = [str(r+1), "新事件", ""]
        for c, v in enumerate(defaults):
            self.tbl_timeline.setItem(r, c, QTableWidgetItem(v))
    
    def _del_event(self):
        rows = sorted(set(idx.row() for idx in self.tbl_timeline.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_timeline.removeRow(r)
    
    # ── 4. 物品库子页 ──────────────────────────────────────
    def _build_items_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增物品")
        btn_add.clicked.connect(self._add_item)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_item)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_items = QTableWidget(0, 5)
        self.tbl_items.setHorizontalHeaderLabels([
            "物品名", "类型", "持有者", "来源章节", "能力/状态"
        ])
        self.tbl_items.horizontalHeader().setStretchLastSection(True)
        self.tbl_items.verticalHeader().setVisible(False)
        self.tbl_items.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_items.setColumnWidth(0, 120)
        self.tbl_items.setColumnWidth(1, 80)
        self.tbl_items.setColumnWidth(2, 100)
        self.tbl_items.setColumnWidth(3, 80)
        lay.addWidget(self.tbl_items)
        
        tip = QLabel(
            "💡 类型示例: 法器/灵器/丹药/秘籍/材料/信物/防具/坐骑\n"
            "    防止 AI 漏掉主角已有装备,或重复让主角『获得』同一件东西")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "💎 物品库")
    
    def _add_item(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_items.rowCount()
        self.tbl_items.insertRow(r)
        defaults = ["新物品", "法器", "李远", "1", "未启用"]
        for c, v in enumerate(defaults):
            self.tbl_items.setItem(r, c, QTableWidgetItem(v))
    
    def _del_item(self):
        rows = sorted(set(idx.row() for idx in self.tbl_items.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_items.removeRow(r)
    
    # ── 5.5 战力等级体系子页 ────────────────────────────────
    def _build_power_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        # 顶部说明
        intro = QLabel(
            "📌 设定故事的境界/等级体系,写章节时自动注入,防止『小喽啰一拳打飞主角』『跨级越打越奇怪』"
        )
        intro.setStyleSheet("color:#666;padding:4px;")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        # 预设模板按钮
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("快速套用:"))
        for tpl in ["仙侠九境", "玄幻斗气", "都市修真", "西方魔法", "科幻能力等级"]:
            b = QPushButton(tpl)
            b.clicked.connect(lambda _, t=tpl: self._apply_power_preset(t))
            preset_row.addWidget(b)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        # 操作按钮
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增等级")
        btn_add.clicked.connect(self._add_power_level)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_power_level)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)

        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_power = QTableWidget(0, 4)
        self.tbl_power.setHorizontalHeaderLabels([
            "序号", "境界/等级名", "战力描述", "代表能力"
        ])
        self.tbl_power.horizontalHeader().setStretchLastSection(True)
        self.tbl_power.verticalHeader().setVisible(False)
        self.tbl_power.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_power.setColumnWidth(0, 50)
        self.tbl_power.setColumnWidth(1, 120)
        self.tbl_power.setColumnWidth(2, 220)
        lay.addWidget(self.tbl_power)

        self.sub_tabs.addTab(w, "⚔️ 战力体系")

    def _add_power_level(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_power.rowCount()
        self.tbl_power.insertRow(r)
        defaults = [str(r+1), "", "", ""]
        for c, v in enumerate(defaults):
            self.tbl_power.setItem(r, c, QTableWidgetItem(v))

    def _del_power_level(self):
        rows = sorted(set(idx.row() for idx in self.tbl_power.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_power.removeRow(r)

    def _apply_power_preset(self, name):
        from PyQt5.QtWidgets import QTableWidgetItem
        presets = {
            "仙侠九境": [
                ("练气期", "凡人之上,可初步操控灵气", "御物·小术法"),
                ("筑基期", "构建灵根根基", "凝物为器·小神通"),
                ("金丹期", "凝结金丹,寿元三百", "御空飞行·一气化三清"),
                ("元婴期", "元神出窍,寿八百", "瞬移·分身术"),
                ("化神期", "神识凝实,可压境", "言出法随·小神通成形"),
                ("炼虚期", "虚无之境,寿三千", "破碎虚空·掌控规则"),
                ("合体期", "本命合一,渡劫前夜", "万法归一·镇压一域"),
                ("大乘期", "天劫将至,半步飞升", "言出法随·镇压一界"),
                ("飞升期", "羽化登仙,超脱凡尘", "破开界壁·飞升上界"),
            ],
            "玄幻斗气": [
                ("斗者", "初识斗气", "基础斗技"),
                ("斗师", "斗气外放", "凝实斗气"),
                ("大斗师", "斗气化形", "斗技初成"),
                ("斗灵", "斗气化羽", "御空短行"),
                ("斗王", "镇压一城", "操控斗气"),
                ("斗皇", "破碎山岳", "斗技自创"),
                ("斗宗", "镇压宗门", "驾驭天地之力"),
                ("斗尊", "言出法随", "异火融身"),
                ("斗圣", "化身万千", "撕裂虚空"),
                ("斗帝", "执掌天地", "言出生灭"),
            ],
            "都市修真": [
                ("后天", "凡人体魄", "强健·武艺"),
                ("先天", "突破极限", "内力·感知"),
                ("化劲", "劲入血肉", "穿透·震荡"),
                ("宗师", "镇压一方", "意境·气场"),
                ("大宗师", "返璞归真", "破甲·神识"),
                ("陆地神仙", "万法不侵", "御物·驻颜"),
            ],
            "西方魔法": [
                ("学徒", "刚入门", "小型咒语"),
                ("初级法师", "掌握基础元素", "火球·闪电"),
                ("中级法师", "复合咒语", "法阵·防护罩"),
                ("高级法师", "操控元素之力", "元素亲和"),
                ("大法师", "可创造新咒语", "时空小术"),
                ("圣域法师", "镇压区域", "禁咒入门"),
                ("传奇法师", "活化身于法则", "禁咒·龙息"),
                ("神级法师", "人形法则", "言出法随"),
            ],
            "科幻能力等级": [
                ("E级", "微弱异能", "辅助·感知"),
                ("D级", "可控异能", "局部增强"),
                ("C级", "战斗级", "对抗一队普通士兵"),
                ("B级", "区域级", "对抗一支小队"),
                ("A级", "战略级", "对抗特种部队"),
                ("S级", "城市级", "镇压一城"),
                ("SS级", "国家级", "撼动战局"),
                ("SSS级", "毁灭级", "毁灭一国"),
            ],
        }
        rows = presets.get(name, [])
        if not rows:
            return
        # 清空并填充
        self.tbl_power.setRowCount(0)
        for i, (lv, desc, ab) in enumerate(rows):
            r = self.tbl_power.rowCount()
            self.tbl_power.insertRow(r)
            for c, v in enumerate([str(i+1), lv, desc, ab]):
                self.tbl_power.setItem(r, c, QTableWidgetItem(v))

    # ── 5. 伏笔追踪子页 ────────────────────────────────────
    def _build_foreshadows_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增伏笔")
        btn_add.clicked.connect(self._add_fore)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_fore)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_fore = QTableWidget(0, 5)
        self.tbl_fore.setHorizontalHeaderLabels([
            "埋设章节", "伏笔内容", "计划回收章节", "已回收?", "回收章节"
        ])
        self.tbl_fore.horizontalHeader().setStretchLastSection(True)
        self.tbl_fore.verticalHeader().setVisible(False)
        self.tbl_fore.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_fore.setColumnWidth(0, 70)
        self.tbl_fore.setColumnWidth(1, 280)
        self.tbl_fore.setColumnWidth(2, 90)
        self.tbl_fore.setColumnWidth(3, 70)
        lay.addWidget(self.tbl_fore)
        
        tip = QLabel(
            "💡 已埋伏笔越久未回收越扣读者分。生成新章节时,程序会优先提醒『接近回收期』的伏笔。\n"
            "    『已回收?』填 是/否,回收后填上回收章节号。")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🪤 伏笔追踪")
    
    def _add_fore(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_fore.rowCount()
        self.tbl_fore.insertRow(r)
        defaults = ["1", "新伏笔", "30", "否", ""]
        for c, v in enumerate(defaults):
            self.tbl_fore.setItem(r, c, QTableWidgetItem(v))
    
    def _del_fore(self):
        rows = sorted(set(idx.row() for idx in self.tbl_fore.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_fore.removeRow(r)

    # ── 6. 钩子编年子页 ────────────────────────────────────
    def _build_hooks_tab(self):
        from PyQt5.QtWidgets import QTableWidget
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        
        ops = QHBoxLayout()
        btn_add = QPushButton("➕ 手动添加")
        btn_add.setMaximumWidth(110)
        btn_add.clicked.connect(self._add_hook)
        ops.addWidget(btn_add)
        btn_del = QPushButton("🗑 删除选中")
        btn_del.setMaximumWidth(110)
        btn_del.clicked.connect(self._del_hook)
        ops.addWidget(btn_del)
        ops.addStretch()
        lay.addLayout(ops)
        
        self.tbl_hooks = QTableWidget(0, 4)
        self.tbl_hooks.setHorizontalHeaderLabels([
            "章节", "钩子类型", "强度", "内容(每章末尾留的悬念)"])
        self.tbl_hooks.horizontalHeader().setStretchLastSection(True)
        self.tbl_hooks.verticalHeader().setVisible(False)
        self.tbl_hooks.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_hooks.setColumnWidth(0, 60)
        self.tbl_hooks.setColumnWidth(1, 110)
        self.tbl_hooks.setColumnWidth(2, 70)
        lay.addWidget(self.tbl_hooks)
        
        tip = QLabel(
            "💡 每章生成完后,AI 输出的【断章钩子】自动入这里。\n"
            "    用途:全书钩子审计 — 看强度分布、避免连用同类型(对话没说完 + 对话没说完 = 重复)。\n"
            "    类型常见:对话没说完 / 人物出现 / 秘密暴露 / 倒计时 / 关键动作")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🎣 钩子编年")
    
    def _add_hook(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_hooks.rowCount()
        self.tbl_hooks.insertRow(r)
        defaults = [str(r+1), "对话没说完", "★★★", "新钩子"]
        for c, v in enumerate(defaults):
            self.tbl_hooks.setItem(r, c, QTableWidgetItem(v))
    
    def _del_hook(self):
        rows = sorted(set(idx.row() for idx in self.tbl_hooks.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_hooks.removeRow(r)

    # ── 7. 爽点编年子页 ────────────────────────────────────
    def _build_coolpts_tab(self):
        from PyQt5.QtWidgets import QTableWidget
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        
        ops = QHBoxLayout()
        btn_add = QPushButton("➕ 手动添加")
        btn_add.setMaximumWidth(110)
        btn_add.clicked.connect(self._add_coolpt)
        ops.addWidget(btn_add)
        btn_del = QPushButton("🗑 删除选中")
        btn_del.setMaximumWidth(110)
        btn_del.clicked.connect(self._del_coolpt)
        ops.addWidget(btn_del)
        ops.addStretch()
        lay.addLayout(ops)
        
        self.tbl_cool = QTableWidget(0, 3)
        self.tbl_cool.setHorizontalHeaderLabels([
            "章节", "爽点类型", "内容"])
        self.tbl_cool.horizontalHeader().setStretchLastSection(True)
        self.tbl_cool.verticalHeader().setVisible(False)
        self.tbl_cool.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_cool.setColumnWidth(0, 60)
        self.tbl_cool.setColumnWidth(1, 110)
        lay.addWidget(self.tbl_cool)
        
        tip = QLabel(
            "💡 每章 AI 输出的【本章爽点】自动入这里。\n"
            "    用途:全书爽点审计 — 看类型分布,避免连续 3 章都是同种(全是打脸=审美疲劳)。\n"
            "    类型常见:打脸 / 反转 / 碾压 / 揭秘 / 救场 / 装逼 / 复仇")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🎯 爽点编年")
    
    def _add_coolpt(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_cool.rowCount()
        self.tbl_cool.insertRow(r)
        defaults = [str(r+1), "打脸", "新爽点"]
        for c, v in enumerate(defaults):
            self.tbl_cool.setItem(r, c, QTableWidgetItem(v))
    
    def _del_coolpt(self):
        rows = sorted(set(idx.row() for idx in self.tbl_cool.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_cool.removeRow(r)
    
    # ── 数据序列化(保存/加载到项目JSON) ────────────────────
    def serialize(self):
        """导出全部数据为 dict, 用于持久化"""
        def tbl_to_list(tbl, ncol):
            out = []
            for r in range(tbl.rowCount()):
                row = []
                for c in range(ncol):
                    item = tbl.item(r, c)
                    row.append(item.text() if item else "")
                out.append(row)
            return out
        
        return {
            "characters": tbl_to_list(self.tbl_chars, 8),
            "relations":  tbl_to_list(self.tbl_relations, 4),
            "timeline":   tbl_to_list(self.tbl_timeline, 3),
            "items":      tbl_to_list(self.tbl_items, 5),
            "power_levels": tbl_to_list(self.tbl_power, 4),
            "foreshadows":tbl_to_list(self.tbl_fore, 5),
            "hooks":      tbl_to_list(self.tbl_hooks, 4),  # 新增
            "cool_pts":   tbl_to_list(self.tbl_cool, 3),   # 新增
            "hero_state": {
                "age":      self.hero_age.text(),
                "realm":    self.hero_realm.text(),
                "location": self.hero_location.text(),
                "faction":  self.hero_faction.text(),
                "mood":     self.hero_mood.text(),
            },
            "auto_inject": self.chk_inject.isChecked(),
        }
    
    def load(self, data):
        """从 dict 加载数据"""
        from PyQt5.QtWidgets import QTableWidgetItem
        if not data:
            return
        
        def list_to_tbl(tbl, rows, ncol):
            tbl.setRowCount(0)
            for row in rows:
                r = tbl.rowCount()
                tbl.insertRow(r)
                for c in range(ncol):
                    val = row[c] if c < len(row) else ""
                    tbl.setItem(r, c, QTableWidgetItem(str(val)))
        
        list_to_tbl(self.tbl_chars,     data.get("characters", []), 8)
        list_to_tbl(self.tbl_relations, data.get("relations", []), 4)
        list_to_tbl(self.tbl_timeline,  data.get("timeline", []), 3)
        list_to_tbl(self.tbl_items,     data.get("items", []), 5)
        list_to_tbl(self.tbl_power,     data.get("power_levels", []), 4)
        list_to_tbl(self.tbl_fore,      data.get("foreshadows", []), 5)
        list_to_tbl(self.tbl_hooks,     data.get("hooks", []), 4)      # 新增
        list_to_tbl(self.tbl_cool,      data.get("cool_pts", []), 3)   # 新增
        
        hs = data.get("hero_state", {})
        self.hero_age.setText(hs.get("age", "18"))
        self.hero_realm.setText(hs.get("realm", "练气期一层"))
        self.hero_location.setText(hs.get("location", ""))
        self.hero_faction.setText(hs.get("faction", ""))
        self.hero_mood.setText(hs.get("mood", "平静"))
        
        self.chk_inject.setChecked(data.get("auto_inject", True))
    
    # ── 注入到提示词 ───────────────────────────────────────
    def build_inject_block(self, current_chapter=None, mentioned_names=None):
        """
        生成给 AI 的注入文本块。可按当前章节智能筛选最相关的内容。
        
        参数:
          current_chapter: 即将生成的章节号(int),用于伏笔提醒
          mentioned_names: 提示词中已提到的角色名集合(set),只注入相关角色
        
        返回:
          str: 拼好的注入文本块,直接 append 到提示词后面
        """
        if not self.chk_inject.isChecked():
            return ""
        
        parts = []
        
        # 1. 主角当前状态
        hs = (
            f"年龄 {self.hero_age.text()}, "
            f"修为 {self.hero_realm.text()}, "
            f"位置 {self.hero_location.text()}, "
            f"势力 {self.hero_faction.text()}, "
            f"心境 {self.hero_mood.text()}"
        )
        parts.append(f"【主角当前状态】\n{hs}")
        
        # 2. 角色档案(只取主角+前5个配角,避免提示词过长)
        chars = []
        for r in range(self.tbl_chars.rowCount()):
            row = [self.tbl_chars.item(r, c).text() if self.tbl_chars.item(r, c) else "" 
                   for c in range(8)]
            if not row[0].strip():
                continue
            chars.append(row)
        
        if chars:
            char_lines = []
            # 主角和女主优先
            chars.sort(key=lambda x: 0 if "主角" in x[1] or "女主" in x[1] else 1)
            for row in chars[:8]:
                name, role, look, pers, mark, ability, state, _ = row
                line = f"  • {name}({role}): "
                bits = []
                if look:    bits.append(f"外貌-{look}")
                if pers:    bits.append(f"性格-{pers}")
                if mark:    bits.append(f"标志-{mark}")
                if ability: bits.append(f"能力-{ability}")
                if state:   bits.append(f"状态-{state}")
                line += "; ".join(bits)
                char_lines.append(line)
            parts.append("【角色档案】\n" + "\n".join(char_lines))
        
        # 3. 关系图谱(简洁)
        rels = []
        for r in range(self.tbl_relations.rowCount()):
            a    = self.tbl_relations.item(r, 0).text() if self.tbl_relations.item(r, 0) else ""
            tp   = self.tbl_relations.item(r, 1).text() if self.tbl_relations.item(r, 1) else ""
            b    = self.tbl_relations.item(r, 2).text() if self.tbl_relations.item(r, 2) else ""
            note = self.tbl_relations.item(r, 3).text() if self.tbl_relations.item(r, 3) else ""
            if a and b and tp:
                rels.append(f"  • {a} -[{tp}]- {b}" + (f" ({note})" if note else ""))
        if rels:
            parts.append("【人物关系】\n" + "\n".join(rels[:15]))
        
        # 4. 主角已有物品
        items = []
        for r in range(self.tbl_items.rowCount()):
            name  = self.tbl_items.item(r, 0).text() if self.tbl_items.item(r, 0) else ""
            tp    = self.tbl_items.item(r, 1).text() if self.tbl_items.item(r, 1) else ""
            owner = self.tbl_items.item(r, 2).text() if self.tbl_items.item(r, 2) else ""
            ability = self.tbl_items.item(r, 4).text() if self.tbl_items.item(r, 4) else ""
            if name and ("主角" in owner or owner == "" or "李远" in owner):
                items.append(f"  • {name}({tp}): {ability}")
        if items:
            parts.append("【主角已有物品/法器】\n" + "\n".join(items[:10]))
        
        # 5. 待回收的伏笔(按距离回收期排序)
        if current_chapter is not None:
            pending = []
            for r in range(self.tbl_fore.rowCount()):
                ch_set = self.tbl_fore.item(r, 0).text() if self.tbl_fore.item(r, 0) else "0"
                content= self.tbl_fore.item(r, 1).text() if self.tbl_fore.item(r, 1) else ""
                ch_pay = self.tbl_fore.item(r, 2).text() if self.tbl_fore.item(r, 2) else "0"
                paid   = self.tbl_fore.item(r, 3).text() if self.tbl_fore.item(r, 3) else "否"
                if paid == "是" or not content:
                    continue
                try:
                    ch_pay_int = int(ch_pay)
                    distance = ch_pay_int - current_chapter
                    if -5 <= distance <= 10:  # 接近回收期或已超期
                        pending.append((distance, ch_set, content, ch_pay))
                except ValueError:
                    pending.append((999, ch_set, content, ch_pay))
            pending.sort(key=lambda x: x[0])
            if pending:
                lines = []
                for dist, cs, ct, cp in pending[:5]:
                    flag = "⚠️超期" if dist < 0 else ("🎯本章可回收" if dist <= 2 else f"还有{dist}章")
                    lines.append(f"  • 第{cs}章埋: {ct} → 第{cp}章回收[{flag}]")
                parts.append("【待回收伏笔(优先考虑)】\n" + "\n".join(lines))
        
        # 6. 战力等级体系(防止跨级混乱)
        powers = []
        for r in range(self.tbl_power.rowCount()):
            lv   = self.tbl_power.item(r, 1).text() if self.tbl_power.item(r, 1) else ""
            desc = self.tbl_power.item(r, 2).text() if self.tbl_power.item(r, 2) else ""
            if lv:
                powers.append(f"  • {lv}: {desc}")
        if powers:
            parts.append("【战力等级体系(由低到高)】\n" + "\n".join(powers))

        # 7. 最近时间线事件(防剧情漂移)
        events = []
        for r in range(self.tbl_timeline.rowCount()):
            ch     = self.tbl_timeline.item(r, 0).text() if self.tbl_timeline.item(r, 0) else "0"
            evt    = self.tbl_timeline.item(r, 1).text() if self.tbl_timeline.item(r, 1) else ""
            change = self.tbl_timeline.item(r, 2).text() if self.tbl_timeline.item(r, 2) else ""
            try:
                ch_int = int(ch)
                events.append((ch_int, evt, change))
            except ValueError:
                continue
        events.sort()
        if events and current_chapter:
            recent = [e for e in events if e[0] <= current_chapter][-5:]
            if recent:
                lines = [f"  • 第{c}章: {e}" + (f" [{ch}]" if ch else "") for c, e, ch in recent]
                parts.append("【最近重大事件】\n" + "\n".join(lines))
        
        if not parts:
            return ""
        
        return "\n\n" + "═" * 30 + "\n📚 角色与世界状态(必须严格遵守):\n" + "═" * 30 + "\n\n" + "\n\n".join(parts)
    
    # ── 导入/导出 ──────────────────────────────────────────
    def _export_lib(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出角色库", "character_lib.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.serialize(), f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功", f"已导出到:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))
    
    def _import_lib(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "导入角色库", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.load(data)
            QMessageBox.information(self, "成功", "导入完成")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))


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
        # 发送按钮: 实测 class=composer-submit-btn，data-testid 不存在
        "send_btn": (
            'button.composer-submit-btn, '
            'button[data-testid="send-button"], '
            'button[aria-label*="发送"], '
            'button[aria-label*="Send" i], '
            'form button[type="submit"]'
        ),
        # 回复区: 油猴脚本实测 div.markdown 最精准
        "response": 'div.markdown',
        "_response_fallback": [
            'div.markdown',
            'div[data-message-author-role="assistant"] div.markdown',
            '[data-message-author-role="assistant"]',
            'div.prose',
        ],
        "stop_btn": (
            'button.composer-submit-btn, '
            'button[data-testid="stop-button"], '
            'button[aria-label*="停止"], '
            'button[aria-label*="Stop" i]'
        ),
        # tm_bridge 关闭：直接用 DOM 选择器抓取，无需油猴脚本配合
        "tm_bridge": False,
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
        # 主选择器:精确抓 assistant 正式回复主体
        # ── 必须用 ds-assistant-message-main-content,否则 div.ds-markdown
        # 也会匹配到思考过程块 / 用户提问块,导致 `last` 抓错对象
        # (BUG-012 修复:Canon 数组与 score JSON 都因为这个被抓断或抓错)
        "response": 'div.ds-markdown.ds-assistant-message-main-content',
        "_response_fallback": [
            # 用户报告:DeepSeek 改版后回复可能是单段 p,直接挂在外面
            # 选 last 用,但用 has() 排除掉用户提问块(用户块没 p.ds-markdown-paragraph)
            'p.ds-markdown-paragraph',
            # 兜底:DeepSeek UI 改版时保留宽匹配,但放到 fallback 优先级靠后
            'div.ds-markdown',
            '[class*="ds-message-content"]',
            '[class*="markdown-body"]',
        ],
        # 标准 CSS 不支持 :has-text,改用 aria-label
        "stop_btn": 'div[role="button"][aria-label*="停止"]',
        # ── 针对 DeepSeek 的特殊抓取策略:把同一回复块内的所有 p 段落拼起来
        # 因为新版可能没有外层 div.ds-markdown 容器,只有一堆 p
        "_grab_strategy": "deepseek_paragraphs",
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
        if "unable to obtain driver" in m or "selenium manager" in m or "could not start" in m:
            return ("【诊断】Selenium 自动下载 chromedriver 失败!常见原因:\n"
                    "  1. 网络/防火墙拦截了 Selenium Manager(无法访问 googleapis.com)\n"
                    "  2. 公司机器禁止下载可执行文件\n"
                    "  3. Chrome 版本太新,driver 还没匹配\n"
                    "✅ 解决方案(任选一):\n"
                    "  方案 A: pip install webdriver-manager,程序会自动用它兜底下载(推荐)\n"
                    "  方案 B: 手动下载 chromedriver → "
                    "https://googlechromelabs.github.io/chrome-for-testing/ "
                    "→ 解压到 PATH 路径(如 C:\\Windows\\)\n"
                    "  方案 C: 切换内核到「系统 Edge」(Windows 10+ 内置不用下 driver)")
        if "session not created" in m and "chrome" in m:
            return ("【诊断】Chrome 启动后立刻退出。常见原因:\n"
                    "  1. 同 profile 已有 Chrome 运行 → 关掉所有 Chrome 重试\n"
                    "  2. ChromeDriver 与 Chrome 版本不匹配 → pip install -U selenium\n"
                    "  3. profile 目录被锁 → 删除 ~/NovelAI_Browser_Data 里的 Singleton* 文件\n"
                    "✅ 推荐:把内核切成「系统 Chrome」(自动起调试 Chrome 后 attach,最稳)")
        if "chrome not reachable" in m:
            return "【诊断】无法连接 Chrome(端口不对或浏览器已关)"
        if "chromedriver" in m and ("version" in m or "mismatch" in m):
            return ("【诊断】ChromeDriver 版本不匹配。\n"
                    "  方案 A: pip install -U selenium\n"
                    "  方案 B: pip install -U webdriver-manager(自动管理版本)")
        if "no such file" in m or "not found" in m or "cannot find" in m:
            return "【诊断】找不到浏览器可执行文件,请确认 Chrome / Edge 已安装"
        return ("【诊断】未知错误。\n"
                "  · 先试:关闭所有 Chrome 窗口后重试\n"
                "  · 再试:切换内核到「系统 Edge」(最稳兜底)\n"
                "  · 最后:pip install -U selenium webdriver-manager")

    @staticmethod
    def _resolve_chrome_driver_service():
        """三层兜底获取 chromedriver Service:
        1) None (用 Selenium Manager 自动下载,Selenium 4.6+ 默认)
        2) webdriver-manager 兜底(pip install webdriver-manager)
        3) PATH 里的 chromedriver(用户手动放的)
        返回 Service 对象或 None"""
        try:
            from selenium.webdriver.chrome.service import Service as _CS
            # 尝试 webdriver-manager 兜底
            try:
                from webdriver_manager.chrome import ChromeDriverManager as _CDM
                return _CS(_CDM().install())
            except ImportError:
                pass  # 没装 webdriver-manager 就走 None 路径
            # 尝试 PATH 里的 chromedriver
            import shutil as _shu
            cd_path = _shu.which("chromedriver") or _shu.which("chromedriver.exe")
            if cd_path:
                return _CS(cd_path)
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_edge_driver_service():
        """同上,Edge 版本兜底"""
        try:
            from selenium.webdriver.edge.service import Service as _ES
            try:
                from webdriver_manager.microsoft import EdgeChromiumDriverManager as _EDM
                return _ES(_EDM().install())
            except ImportError:
                pass
            import shutil as _shu
            ed_path = _shu.which("msedgedriver") or _shu.which("msedgedriver.exe")
            if ed_path:
                return _ES(ed_path)
        except Exception:
            pass
        return None

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
                # 第一次:Selenium Manager 默认路径
                self.driver = webdriver.Edge(options=opts)
            except Exception as e:
                # 兜底 1:webdriver-manager / PATH chromedriver
                svc = self._resolve_edge_driver_service()
                if svc:
                    self.log_signal.emit("Selenium Manager 失败,改用 webdriver-manager 兜底", "warn")
                    try:
                        self.driver = webdriver.Edge(options=opts, service=svc)
                    except Exception as e2:
                        raise RuntimeError(f"{e2}\n\n{self._diagnose(str(e2))}")
                else:
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
                svc = self._resolve_chrome_driver_service()
                if svc:
                    self.log_signal.emit("Selenium Manager 失败,改用 webdriver-manager 兜底", "warn")
                    try:
                        self.driver = webdriver.Chrome(options=opts, service=svc)
                    except Exception as e2:
                        raise RuntimeError(f"{e2}\n\n{self._diagnose(str(e2))}")
                else:
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
                svc = self._resolve_chrome_driver_service()
                if svc:
                    self.log_signal.emit("Selenium Manager 失败,改用 webdriver-manager 兜底", "warn")
                    try:
                        self.driver = webdriver.Chrome(options=opts, service=svc)
                    except Exception as e2:
                        raise RuntimeError(f"{e2}\n\n{self._diagnose(str(e2))}")
                else:
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

    def run_dom_diagnostics(self):
        """诊断:对当前页跑所有候选选择器,返回命中情况
        给主线程调,通过 future 同步返回结果"""
        try:
            from selenium.common.exceptions import WebDriverException
            url = self._current_url()
            prof = _profile_for_url(url)
            # 收集要测的选择器
            test_selectors = {
                "input(输入框)": prof.get("input", ""),
                "send_btn(发送按钮)": prof.get("send_btn", ""),
                "response(回复区)": prof.get("response", ""),
                "stop_btn(停止按钮)": prof.get("stop_btn", ""),
            }
            fb = prof.get("_response_fallback", [])
            for i, s in enumerate(fb):
                test_selectors[f"_response_fallback[{i}]"] = s

            # 浏览器里跑诊断
            js = r"""
            const sels = arguments[0];
            const result = {};
            for (const [name, sel] of Object.entries(sels)) {
                if (!sel) { result[name] = {selector: sel, count: 0, samples: []}; continue; }
                try {
                    const els = document.querySelectorAll(sel);
                    const samples = [];
                    for (let i = 0; i < Math.min(els.length, 3); i++) {
                        const el = els[i];
                        const visible = el.offsetParent !== null;
                        const text = (el.innerText || el.value || '').slice(0, 80).replace(/\n/g, '⏎');
                        samples.push({
                            tag: el.tagName.toLowerCase(),
                            class: (el.className || '').toString().slice(0, 60),
                            visible: visible,
                            text: text
                        });
                    }
                    result[name] = {selector: sel, count: els.length, samples: samples};
                } catch (e) {
                    result[name] = {selector: sel, error: e.message};
                }
            }
            // 额外:统计页面 DOM 概况
            result['__overview__'] = {
                title: document.title,
                url: location.href,
                total_textareas: document.querySelectorAll('textarea').length,
                total_contenteditable: document.querySelectorAll('[contenteditable="true"]').length,
                total_buttons: document.querySelectorAll('button, [role="button"]').length,
                ds_markdown_count: document.querySelectorAll('div.ds-markdown').length,
                ds_assistant_count: document.querySelectorAll('div.ds-markdown.ds-assistant-message-main-content').length,
            };
            return result;
            """
            return self.driver.execute_script(js, test_selectors)
        except WebDriverException as e:
            return {"__error__": str(e)}
        except Exception as e:
            return {"__error__": f"诊断失败:{e}"}

    def install_dom_picker(self):
        """在页面上安装现场拾取助手:
        - 鼠标 hover 时高亮元素并显示选择器建议
        - 点击时把选择器写入 window.__novelai_picked
        - 按 ESC 退出
        Python 端可以轮询 window.__novelai_picked 拿到用户选的"""
        try:
            self.driver.execute_script(r"""
            if (window.__novelai_picker_active) return;
            window.__novelai_picker_active = true;
            window.__novelai_picked = null;

            // 建议选择器:优先 id,其次 [data-testid],其次 class chain,最次 tagName
            function suggestSelector(el) {
                if (!el) return null;
                if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) {
                    return '#' + el.id;
                }
                const tid = el.getAttribute('data-testid');
                if (tid) return `[data-testid="${tid}"]`;
                const aria = el.getAttribute('aria-label');
                if (aria) return `${el.tagName.toLowerCase()}[aria-label*="${aria.slice(0,20)}"]`;
                // 优先用稳定 class(过滤 hash 形式)
                const cls = (el.className || '').toString().split(/\s+/)
                    .filter(c => c && c.length > 2 && !/^_[a-f0-9]/.test(c) && !/^[a-f0-9]{6,}$/.test(c))
                    .slice(0, 2);
                if (cls.length > 0) {
                    return el.tagName.toLowerCase() + '.' + cls.join('.');
                }
                // 兜底:tagName + nth-child
                const parent = el.parentElement;
                if (parent) {
                    const idx = Array.from(parent.children).indexOf(el);
                    return parent.tagName.toLowerCase() + ' > ' +
                           el.tagName.toLowerCase() + ':nth-child(' + (idx+1) + ')';
                }
                return el.tagName.toLowerCase();
            }

            // 浮动提示框
            let tip = document.createElement('div');
            tip.style.cssText = `
                position:fixed; z-index:999999; padding:8px 12px;
                background:#1a4480; color:white; font:13px/1.4 monospace;
                border-radius:4px; pointer-events:none;
                box-shadow:0 4px 12px rgba(0,0,0,0.3);
                max-width:600px; word-break:break-all;
            `;
            tip.innerHTML = '🎯 拾取模式 — hover 看选择器, 点击采集, ESC 退出';
            tip.style.top = '10px';
            tip.style.left = '10px';
            document.body.appendChild(tip);

            let lastHover = null;
            function onHover(e) {
                if (lastHover) lastHover.style.outline = '';
                lastHover = e.target;
                lastHover.style.outline = '3px solid red';
                const sel = suggestSelector(e.target);
                const cnt = document.querySelectorAll(sel).length;
                const txt = (e.target.innerText || e.target.value || '').slice(0, 50).replace(/\n/g, '⏎');
                tip.innerHTML = `🎯 选择器: <b>${sel}</b><br>命中 ${cnt} 个 | tag=${e.target.tagName.toLowerCase()} | text="${txt}"`;
            }
            function onClick(e) {
                e.preventDefault(); e.stopPropagation();
                const sel = suggestSelector(e.target);
                const cnt = document.querySelectorAll(sel).length;
                window.__novelai_picked = {selector: sel, count: cnt, tag: e.target.tagName.toLowerCase()};
                tip.innerHTML = `✅ 已拾取: <b>${sel}</b><br>命中 ${cnt} 个。回 PyQt 程序点用即可,或继续 hover 拾取其他。`;
                tip.style.background = '#2ecc71';
                setTimeout(() => { tip.style.background = '#1a4480'; }, 1500);
                return false;
            }
            function onKey(e) {
                if (e.key === 'Escape') {
                    if (lastHover) lastHover.style.outline = '';
                    tip.remove();
                    document.removeEventListener('mouseover', onHover, true);
                    document.removeEventListener('click', onClick, true);
                    document.removeEventListener('keydown', onKey, true);
                    window.__novelai_picker_active = false;
                }
            }
            document.addEventListener('mouseover', onHover, true);
            document.addEventListener('click', onClick, true);
            document.addEventListener('keydown', onKey, true);
            """)
            return True
        except Exception:
            return False

    def get_picked_selector(self):
        """轮询读取拾取结果"""
        try:
            return self.driver.execute_script(r"""
                const p = window.__novelai_picked;
                if (p) { window.__novelai_picked = null; return p; }
                return null;
            """)
        except Exception:
            return None

    def _inject_kbd_guard(self):
        """注入 DeepSeek 搜索 modal 三重防护(BUG-013 + 用户报告的搜索 modal 弹窗):
        1. Ctrl+K / Cmd+K 键盘拦截(capture 阶段)
        2. 直接隐藏顶部搜索按钮(用户不用 DeepSeek 自带搜索)
        3. MutationObserver 兜底:搜索 modal 一出现就关掉,防止 Selenium 误点
        用 window.__novelai_search_guard 做 flag,重复调用不会重复绑定。"""
        try:
            self.driver.execute_script(r"""
                if (window.__novelai_search_guard) return 'already';
                window.__novelai_search_guard = true;

                // ─── 1. Ctrl+K / Cmd+K 拦截(capture 阶段) ───
                window.addEventListener('keydown', function(e) {
                    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
                        e.preventDefault();
                        e.stopImmediatePropagation();
                        console.log('[novelai] Ctrl+K blocked');
                        return false;
                    }
                }, true);

                // ─── 2. 隐藏顶部搜索按钮 ───
                // 搜索按钮的 SVG 是放大镜:path d 以 "M11.894845 6.647401" 开头
                function hideSearchButtons() {
                    document.querySelectorAll('div[role="button"]').forEach(btn => {
                        if (btn.dataset.naiHidden === '1') return;
                        const path = btn.querySelector('svg path');
                        if (path) {
                            const d = path.getAttribute('d') || '';
                            // 放大镜 svg 的 d 起始
                            if (d.startsWith('M11.894845') || d.indexOf('M11.894845 6.647401') >= 0) {
                                btn.style.display = 'none';
                                btn.dataset.naiHidden = '1';
                                console.log('[novelai] 搜索按钮已隐藏');
                            }
                        }
                    });
                }
                hideSearchButtons();
                // 周期性扫(SPA 切页面后按钮会重生)
                setInterval(hideSearchButtons, 1500);

                // ─── 3. 搜索 modal 兜底:出现就关闭 ───
                // 简化版:不依赖 input placeholder,直接按 X 按钮 SVG 特征找
                // X 按钮 SVG path d 含 14.187(用户提供的稳定特征)
                function dismissSearchModal() {
                    // 找页面上所有可能的 X 按钮(svg path d 含 14.187)
                    const paths = document.querySelectorAll('svg path');
                    let closedCount = 0;
                    for (const p of paths) {
                        const d = p.getAttribute('d') || '';
                        if (d.indexOf('14.187') < 0) continue;
                        const btn = p.closest('[role="button"]');
                        if (!btn || btn.dataset.naiClosed === '1') continue;
                        // 检查 X 按钮是否在 modal/dialog 容器里(避免误关其他 X)
                        const modal = btn.closest('[role="dialog"]') ||
                                      btn.closest('.ds-modal-content') ||
                                      btn.closest('[class*="modal"]');
                        if (modal && modal.offsetParent !== null) {
                            btn.dataset.naiClosed = '1';  // 防同帧重复点
                            btn.click();
                            closedCount++;
                            console.log('[novelai] 搜索 modal X 按钮已点关闭');
                            // 0.5 秒后清掉标记,允许下次新 modal 再关
                            setTimeout(() => { delete btn.dataset.naiClosed; }, 500);
                        }
                    }
                    return closedCount;
                }
                // 立即扫一次 + MutationObserver 持续盯 + 每 800ms 周期扫(双保险)
                dismissSearchModal();
                setInterval(dismissSearchModal, 800);
                const obs = new MutationObserver(function() {
                    dismissSearchModal();
                });
                obs.observe(document.body, {childList: true, subtree: true});

                // 暴露给外部供 Python 主动调用
                window.__novelai_dismiss_modal = dismissSearchModal;

                return 'OK';
            """)
        except Exception:
            pass  # 注入失败不影响正常发送

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

        # BUG-013 + 搜索 modal 兜底:注入三重防护(Ctrl+K 拦截 + 隐藏搜索按钮 + 自动关 modal)
        # 用 idempotent 的全局 flag 防重复绑定
        self._inject_kbd_guard()

        # 发消息前再强制关一次搜索 modal(如果用户之前手动触发或 selenium 误触发还残留)
        # 反复关 3 次,每次间隔 200ms,防 modal 关闭动画期间又重生
        try:
            for _i in range(3):
                closed = self.driver.execute_script(r"""
                    if (typeof window.__novelai_dismiss_modal === 'function') {
                        return window.__novelai_dismiss_modal();
                    }
                    return 0;
                """) or 0
                if closed > 0:
                    self.log_signal.emit(
                        f"发消息前关闭了 {closed} 个搜索 modal", "info")
                    time.sleep(0.2)
                else:
                    break  # 没 modal 了,无需再扫
        except Exception:
            pass

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

        # 发送前快照 textarea 附近 icon 按钮的 SVG 形状,
        # 这样 AI 写完后可以对比"按钮 SVG 是不是变回发送前的样子"判定完成
        try:
            self._btn_snapshot_before = self.driver.execute_script(r"""
                const ta = document.querySelector('textarea');
                if (!ta) return null;
                let container = ta.parentElement;
                for (let i = 0; i < 5 && container; i++) {
                    const btns = container.querySelectorAll('div[role="button"]');
                    if (btns.length > 0) {
                        // 把按钮们的 SVG path/rect d 属性拼成指纹
                        const fp = [];
                        for (const b of btns) {
                            if (b.offsetParent === null) continue;
                            const paths = b.querySelectorAll('svg path, svg rect');
                            const dlist = [];
                            for (const p of paths) {
                                dlist.push((p.getAttribute('d') || '') +
                                           '|' + (p.getAttribute('width') || ''));
                            }
                            fp.push(dlist.join(';'));
                        }
                        return fp.join('||');
                    }
                    container = container.parentElement;
                }
                return null;
            """)
        except Exception:
            self._btn_snapshot_before = None

        # 发送前清除 TamperMonkey bridge 旧数据,防止读到上一轮回复
        if prof.get("tm_bridge"):
            try:
                self.driver.execute_script(
                    "localStorage.removeItem('__novelai_reply');")
            except Exception:
                pass

        # 2.0) 长文本附件模式：超过 1500 字符时转成 txt 文件上传
        # 优势：绕过审核（附件不进入文本审核）+ 避免输入框卡顿
        upload_threshold = task.get("upload_threshold", 0)  # 0 = 全部走附件,绕过审核
        use_attachment = (
            prof.get("name", "").startswith("ChatGPT")  # 仅 ChatGPT 系列支持
            and len(prompt) >= upload_threshold
            and task.get("allow_attachment", True)
        )
        
        if use_attachment:
            self.log_signal.emit(
                f"⚡ 长文本({len(prompt)}字)启用附件上传模式", "info")
            uploaded = self._upload_prompt_as_file(prof, prompt)
            if uploaded:
                # 引导语 - 用追加方式注入,不清空(避免附件丢失)
                short_guide = (
                    "请仔细阅读附件内容，按其要求生成完整结果。"
                    "直接输出，不要复述、不要省略、注意字数要求。"
                )
                # 用 execCommand insertText 直接追加,不 selectAll
                inject_ok = self.driver.execute_script(f"""
                    const sel = '#prompt-textarea, div.ProseMirror[contenteditable="true"], div[contenteditable="true"]';
                    const box = document.querySelector(sel);
                    if (!box) return 'NO_BOX';
                    box.focus();
                    // 移动光标到末尾(不用 selectAll, 避免删除附件块)
                    const range = document.createRange();
                    range.selectNodeContents(box);
                    range.collapse(false);
                    const s = window.getSelection();
                    s.removeAllRanges();
                    s.addRange(range);
                    // 直接 insertText 追加
                    document.execCommand('insertText', false, {json.dumps(short_guide)});
                    box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true, inputType:'insertText'}}));
                    box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                    return 'OK';
                """)
                self.log_signal.emit(f"引导语注入: {inject_ok}", "info")
                import time as _ti; _ti.sleep(0.5)
                self.log_signal.emit("✓ 准备发送(附件+引导语)", "info")
            else:
                self.log_signal.emit("⚠️ 附件上传失败，降级为直接发送文本", "warn")
                if not self._inject_prompt(prof["input"], prompt):
                    self.log_signal.emit("文本注入失败", "error")
                    self.response_received.emit(task_id, "")
                    return
        else:
            # 短文本：直接注入
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

        # 4) 等新回复出现(对话条数 +1 OR 抓到内容)
        # 因 DeepSeek 计数策略 prev/cur 在短回复时容易失灵,加内容兜底
        # 提速:30s deadline → 15s,轮询 0.5s → 0.2s
        time.sleep(1.5)  # 给 DOM 渲染新回复块的最短时间(原 3s)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._stop.is_set(): return
            cur_cnt = self._count_responses(prof)
            # 计数增加 OR 已经能抓到回复内容(> 30 字)就认为开始了
            if cur_cnt > prev_count:
                break
            try:
                early_text = self._grab_last_response(prof)
                if early_text and len(early_text) > 30:
                    # 可能 prev_count 算错了,但实际已有内容
                    self.log_signal.emit(
                        f"检测到回复内容(已抓 {len(early_text)} 字符),进入稳定等待",
                        "info")
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            self.log_signal.emit(
                "未检测到新回复条目,可能选择器需调整(到 SITE_PROFILES 微调)", "warn")

        # 5) 等内容稳定 N 秒 / stop 按钮消失 / 完成后按钮出现 任一条件
        # 提速:轮询间隔 0.3s(原 1s), stable_wait 内部 1.5s(原 4s), stop 按钮检测加强
        last_text = ""
        last_change = time.time()
        start = time.time()
        # 智能稳定阈值:根据内容长度分档
        # 短回复(JSON/评分/摘要 <300 字)→ 0.9s 稳定即完成(超快)
        # 中等回复(<1000 字)→ 1.5s
        # 长章节(>=1000 字)→ 用 self.stable_wait(默认 4s)防 AI 卡顿误判
        ultrafast_stable_wait = 0.9
        fast_stable_wait = 1.5
        normal_stable_wait = self.stable_wait
        no_change_streak = 0  # 连续无变化的轮数
        while time.time() - start < self.max_wait:
            if self._stop.is_set(): return
            cur = self._grab_last_response(prof)

            # 完成信号 1: 按钮快照恢复(AI 写完后,textarea 旁边按钮 SVG 变回发送前的样子)
            # 这是最稳的完成信号:不依赖任何 class/aria-label,只看按钮 SVG 形状指纹
            # AI 在写时,纸飞机(发送)→ 方块(停止),所以指纹会变;
            # 写完后停止按钮消失/变回纸飞机 → 指纹恢复成发送前的样子
            stopping = False
            try:
                cur_snapshot = self.driver.execute_script(r"""
                    const ta = document.querySelector('textarea');
                    if (!ta) return null;
                    let container = ta.parentElement;
                    for (let i = 0; i < 5 && container; i++) {
                        const btns = container.querySelectorAll('div[role="button"]');
                        if (btns.length > 0) {
                            const fp = [];
                            for (const b of btns) {
                                if (b.offsetParent === null) continue;
                                const paths = b.querySelectorAll('svg path, svg rect');
                                const dlist = [];
                                for (const p of paths) {
                                    dlist.push((p.getAttribute('d') || '') +
                                               '|' + (p.getAttribute('width') || ''));
                                }
                                fp.push(dlist.join(';'));
                            }
                            return fp.join('||');
                        }
                        container = container.parentElement;
                    }
                    return null;
                """)
                # 快照变化中 → 还在写;快照跟"发送前"一致 → 写完了
                snap_before = getattr(self, "_btn_snapshot_before", None)
                if snap_before and cur_snapshot is not None:
                    # 快照不一致 = 现在有"停止按钮"在 → AI 还在写
                    # 快照一致 = 按钮 SVG 变回发送前样子 → AI 写完了
                    if cur_snapshot != snap_before:
                        stopping = True
                else:
                    # 快照不可用,退化到原 selector 检测
                    stopping = self.driver.execute_script(r"""
                        let s = document.querySelector('div[role="button"][aria-label*="停止"]') ||
                                document.querySelector('button[aria-label*="停止"]') ||
                                document.querySelector('button[aria-label*="Stop" i]') ||
                                document.querySelector('button[data-testid*="stop"]');
                        if (s && s.offsetParent !== null) return true;
                        const ta = document.querySelector('textarea');
                        if (ta) {
                            let c = ta.parentElement;
                            for (let i = 0; i < 5 && c; i++) {
                                const b = c.querySelectorAll('div[role="button"]:has(svg rect)');
                                for (const x of b) if (x.offsetParent !== null) return true;
                                c = c.parentElement;
                            }
                        }
                        return false;
                    """) or False
            except Exception:
                pass

            # stop 不可见(按钮恢复) + 抓到内容 + 内容跟上次相同 → 立即完成(最快路径)
            if not stopping and cur and len(cur) > 30 and cur == last_text:
                self.log_signal.emit(
                    f"✓ 按钮快照已恢复(AI 写完)+ 内容稳定 → 完成 ({len(cur)} 字符)", "info")
                break

            if cur and cur == last_text:
                no_change_streak += 1
                # 智能三档稳定阈值:
                #   <300 字 (JSON/评分/摘要) → 0.9s 即可
                #   <1000 字 → 1.5s
                #   >=1000 字 (长章节) → self.stable_wait (默认 4s,防 AI 卡顿误判)
                clen = len(cur)
                if clen < 300:
                    wait_threshold = ultrafast_stable_wait
                elif clen < 1000:
                    wait_threshold = fast_stable_wait
                else:
                    wait_threshold = normal_stable_wait
                if time.time() - last_change >= wait_threshold:
                    self.log_signal.emit(
                        f"✓ 内容稳定 {wait_threshold:.1f}s → 完成 ({clen} 字符)", "info")
                    break
            else:
                last_text = cur
                last_change = time.time()
                no_change_streak = 0
            elapsed = int(time.time() - start)
            if elapsed and elapsed % 5 == 0 and no_change_streak == 0:
                self.log_signal.emit(
                    f"AI 生成中...已 {elapsed}s,当前 {len(cur or '')} 字符", "info")
            time.sleep(0.3)  # 提速:1s → 0.3s,响应快 3 倍

        if last_text:
            self.log_signal.emit(f"回复完成,共 {len(last_text)} 字符", "success")
        else:
            self.log_signal.emit(
                "回复抓取为空,可能选择器需调整(到 SITE_PROFILES 微调)", "warn")
        self.response_received.emit(task_id, last_text)

    # ---------- 附件上传：把长文本 prompt 转 txt 上传 ----------
    def _clear_existing_attachments(self):
        """清空 composer 输入区的待发送附件
        实测镜像站删除按钮 aria-label='移除文件1：xxx.txt'
        """
        try:
            # 多轮清除（点一个删除按钮后 React 重渲染，需要再扫一遍）
            for round_idx in range(5):
                removed = self.driver.execute_script(r"""
                    let count = 0;
                    
                    // 找页面上所有按钮（不限定在 composer 内，因为附件有时挂在 composer 外）
                    const btns = document.querySelectorAll('button');
                    btns.forEach(btn => {
                        const aria = btn.getAttribute('aria-label') || '';
                        
                        // 排除发送/侧边栏等无关按钮
                        if (aria.includes('发送') || aria.includes('Send') ||
                            aria.includes('边栏') || aria.includes('sidebar') ||
                            aria.includes('Stop') || aria.includes('停止')) {
                            return;
                        }
                        
                        // 精确匹配镜像站附件删除按钮
                        // 实测格式: "移除文件1：xxx.txt"  或  "Remove file 1: xxx.txt"
                        const isAttClose = (
                            aria.match(/移除文件\s*\d*[：:]/) ||
                            aria.match(/^移除[\s文件]*\d*$/) ||
                            aria.match(/Remove\s+file\s*\d*[：:]/i) ||
                            aria.match(/^Remove\s+attachment/i) ||
                            aria.match(/^Delete\s+file/i)
                        );
                        
                        if (isAttClose) {
                            try { btn.click(); count++; } catch(e) {}
                        }
                    });
                    
                    return count;
                """) or 0
                
                if removed == 0:
                    if round_idx == 0:
                        # 首轮就没找到删除按钮,正常情况(无附件)
                        pass
                    break
                
                self.log_signal.emit(f"✓ 第{round_idx+1}轮清除 {removed} 个附件", "info")
                import time as _t; _t.sleep(0.5)  # 等 React 重渲染
            
            # 重置所有 file input 的 value
            self.driver.execute_script("""
                document.querySelectorAll('input[type="file"]').forEach(el => {
                    try { el.value = ''; } catch(e) {}
                });
            """)
        except Exception as e:
            self.log_signal.emit(f"清除附件异常: {e}", "warn")

    def _upload_prompt_as_file(self, prof, text):
        """
        把 prompt 写成临时 txt 文件，通过 ChatGPT 的文件上传 input 注入。
        ChatGPT 系列(包括镜像站)有隐藏的 <input type="file" />，
        Selenium 直接 send_keys(filepath) 即可上传，无需点开文件选择对话框。
        """
        import os, tempfile, time as _t, glob
        # 0) 先清除已存在的附件，避免堆积
        self._clear_existing_attachments()
        # 0.5) 删除磁盘上残留的旧临时文件(保留最近 3 个,以防发送中)
        try:
            tmp_dir = tempfile.gettempdir()
            old_files = sorted(
                glob.glob(os.path.join(tmp_dir, "novel_ai_prompt_*.txt")),
                key=os.path.getmtime
            )
            # 保留最近 3 个,删掉更老的
            for old_f in old_files[:-3]:
                try:
                    os.remove(old_f)
                except Exception:
                    pass
            if len(old_files) > 3:
                self.log_signal.emit(f"已清理 {len(old_files)-3} 个旧临时文件", "info")
        except Exception:
            pass
        # 1) 写临时文件
        try:
            tmp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(tmp_dir, f"novel_ai_prompt_{int(_t.time())}.txt")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            # 记录到实例,方便后续清理
            if not hasattr(self, "_temp_files"):
                self._temp_files = []
            self._temp_files.append(tmp_path)
            # 实例只保留最近 3 个引用
            if len(self._temp_files) > 3:
                old_path = self._temp_files.pop(0)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
            self.log_signal.emit(f"已创建临时附件: {os.path.basename(tmp_path)} ({len(text)}字)", "info")
        except Exception as e:
            self.log_signal.emit(f"写入临时文件失败: {e}", "error")
            return False

        # 2) 找到隐藏的 <input type="file"> 元素
        # ChatGPT/镜像站通常有这个隐藏控件用于文件上传
        try:
            # 等待 input[type=file] 出现（页面可能延迟渲染）
            file_input = None
            for _ in range(10):
                file_inputs = self.driver.execute_script("""
                    return Array.from(document.querySelectorAll('input[type="file"]'))
                        .map(el => ({
                            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                            accept: el.accept || '',
                            multiple: el.multiple
                        }));
                """)
                if file_inputs:
                    self.log_signal.emit(
                        f"找到 {len(file_inputs)} 个 input[type=file]", "info")
                    break
                _t.sleep(0.3)
            else:
                self.log_signal.emit("页面未找到 input[type=file]，无法上传附件", "warn")
                return False

            # 3) 用 Selenium 的 send_keys 注入文件路径
            from selenium.webdriver.common.by import By
            inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if not inputs:
                return False

            # 强制让 input 可见（Selenium 不能给隐藏元素 send_keys）
            self.driver.execute_script("""
                document.querySelectorAll('input[type="file"]').forEach(el => {
                    el.style.display = 'block';
                    el.style.visibility = 'visible';
                    el.style.opacity = '1';
                    el.style.position = 'fixed';
                    el.style.left = '0';
                    el.style.top = '0';
                    el.style.width = '1px';
                    el.style.height = '1px';
                    el.removeAttribute('hidden');
                });
            """)
            _t.sleep(0.3)

            # 关键: send_keys 前先重置 input 的 value,避免追加上次的文件
            self.driver.execute_script("""
                document.querySelectorAll('input[type="file"]').forEach(el => {
                    try { el.value = ''; } catch(e) {}
                });
            """)
            _t.sleep(0.2)
            
            # 选第一个 input（通常就是聊天框的附件上传）
            inputs[0].send_keys(tmp_path)
            self.log_signal.emit("文件路径已 send_keys 到 input", "info")

            # 4) 等待上传完成 - 多策略检测
            fname = os.path.basename(tmp_path)
            uploaded = False
            for i in range(40):  # 最多等20秒
                state = self.driver.execute_script(f"""
                    const fname = {json.dumps(fname)};
                    // 检查方式1: 整个页面文字含文件名
                    const hasName = document.body.innerText.includes(fname);
                    // 检查方式2: 有 attachment 类名元素出现
                    const attEls = document.querySelectorAll(
                        '[class*="attachment" i], [class*="file-preview" i], ' +
                        '[class*="file-card" i], [data-testid*="attachment" i], ' +
                        '[class*="composer-file" i], [aria-label*="附件" i]'
                    );
                    // 检查方式3: input 框附近有 .txt 字样
                    const composer = document.querySelector('form, [class*="composer" i]');
                    const composerText = composer ? composer.innerText : '';
                    const hasTxt = composerText.includes('.txt');
                    return {{ hasName, attCount: attEls.length, hasTxt }};
                """) or {{}}
                # 任何一种检测到就认为上传完成
                if state.get('hasName') or state.get('attCount', 0) > 0 or state.get('hasTxt'):
                    self.log_signal.emit(
                        f"✓ 附件已就位 ({(i+1)*0.5}s) [name={state.get('hasName')} att={state.get('attCount')} txt={state.get('hasTxt')}]",
                        "info")
                    _t.sleep(2.5)  # 让后端完整接收附件
                    uploaded = True
                    break
                _t.sleep(0.5)

            if not uploaded:
                self.log_signal.emit("⚠ 等待附件上传超时(20s)", "warn")
                # 即使没检测到也试试,可能是镜像站DOM结构特殊
                _t.sleep(1.5)
                return True

            return True

        except Exception as e:
            self.log_signal.emit(f"附件上传异常: {e}", "warn")
            return False

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
        import time as _t_inj

        # 长文本注入需要更长的脚本超时
        try:
            self.driver.set_script_timeout(90)
        except Exception:
            pass

        sel = json.dumps(input_selector)
        text_js = json.dumps(text)

        # ── 0. textarea 专属注入(DeepSeek 等用 textarea, 不是 contenteditable)
        # React 把 value 控制锁住, 直接 .value=... 不触发 setState
        # 必须用 React 的内部 setter 才能让 state 更新
        try:
            result = self.driver.execute_script(f"""
                const ta = document.querySelector('textarea');
                if (!ta) return 'NO_TA';
                ta.focus();
                // 用 React 内部 setter 设 value (绕过 React 的 controlled lock)
                const proto = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value');
                if (proto && proto.set) {{
                    proto.set.call(ta, {text_js});
                }} else {{
                    ta.value = {text_js};
                }}
                // 触发 React 合成事件
                ta.dispatchEvent(new Event('input',  {{bubbles:true}}));
                ta.dispatchEvent(new Event('change', {{bubbles:true}}));
                return (ta.value && ta.value.length > 10) ? 'OK_TA' : 'EMPTY_TA';
            """)
            self.log_signal.emit(f"textarea 注入: {result}", "info")
            if result == 'OK_TA':
                _t_inj.sleep(0.3)
                # 等发送按钮 enabled
                return True
        except Exception as _e:
            self.log_signal.emit(f"textarea 注入异常(降级):{_e}", "warn")

        # ── 快速路径: ProseMirror / #prompt-textarea
        # 实测最有效: focus → selectAll → delete → execCommand insertText → 触发 React 事件
        # 优先用 #prompt-textarea，不依赖可能含特殊字符的多选择器字符串
        _pm_sel = json.dumps('#prompt-textarea, div.ProseMirror[contenteditable="true"], div[contenteditable="true"]')
        try:
            result = self.driver.execute_script(f"""
                const box = document.querySelector({_pm_sel});
                if (!box || !box.isContentEditable) return 'SKIP';
                box.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                const ok = document.execCommand('insertText', false, {text_js});
                // 触发 React 合成事件让发送按钮解锁
                box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true, inputType:'insertText'}}));
                box.dispatchEvent(new Event('change', {{bubbles:true}}));
                box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                const content = (box.innerText || box.textContent || '').trim();
                return content ? 'OK' : 'EMPTY';
            """)
            self.log_signal.emit(f"注入结果: {result}", "info")
            if result == 'OK':
                # 等待发送按钮出现（输入框为空时按钮不在DOM，有内容后才渲染）
                _btn_sel = json.dumps(
                    'button.composer-submit-btn, [data-testid="send-button"], '
                    'button[aria-label*="Send" i], button[aria-label*="发送"]'
                )
                for _wi in range(20):
                    _btn_ok = self.driver.execute_script(f"""
                        return !!document.querySelector({_btn_sel});
                    """)
                    if _btn_ok:
                        break
                    _t_inj.sleep(0.15)
                else:
                    self.log_signal.emit("⚠️ 注入成功但发送按钮未出现，仍尝试发送", "warn")
                _t_inj.sleep(0.2)
                self.log_signal.emit("✓ insertText 注入成功，发送按钮已就绪", "info")
                return True
            elif result in ('EMPTY', 'SKIP'):
                self.log_signal.emit(f"insertText 结果={result}，尝试 CDP 注入", "warn")
                # CDP Input.insertText — Selenium attach模式下最可靠
                try:
                    self.driver.execute_script(f"""
                        const box = document.querySelector({_pm_sel});
                        if (box) {{ box.focus(); document.execCommand('selectAll'); document.execCommand('delete'); }}
                    """)
                    _t_inj.sleep(0.1)
                    self.driver.execute_cdp_cmd('Input.insertText', {'text': text})
                    _t_inj.sleep(0.3)
                    # 触发 React 事件
                    cdp_ok = self.driver.execute_script(f"""
                        const box = document.querySelector({_pm_sel});
                        if (!box) return false;
                        box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true}}));
                        box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                        return (box.innerText || box.textContent || '').trim().length > 0;
                    """)
                    if cdp_ok:
                        self.log_signal.emit("✓ CDP insertText 注入成功", "info")
                        # 等发送按钮出现
                        _btn_sel2 = json.dumps('button.composer-submit-btn, [data-testid="send-button"]')
                        for _wi2 in range(20):
                            if self.driver.execute_script(f"return !!document.querySelector({_btn_sel2});"):
                                break
                            _t_inj.sleep(0.15)
                        _t_inj.sleep(0.2)
                        return True
                    self.log_signal.emit("CDP 注入后内容仍为空", "warn")
                except Exception as _cdp_e:
                    self.log_signal.emit(f"CDP 注入失败: {_cdp_e}", "warn")
        except Exception as e:
            self.log_signal.emit(f"快速注入异常: {e}，降级处理", "warn")

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
                        # 补触发 React 合成事件，让发送按钮从 disabled 变可用
                        self.driver.execute_script(f"""
                            const box = document.querySelector({sel});
                            if (!box) return;
                            // 触发 React 可识别的 input 事件
                            box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true}}));
                            box.dispatchEvent(new Event('change', {{bubbles:true}}));
                            // ChatGPT/镜像站专用：触发 compositionend 解锁发送按钮
                            box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                        """)
                        import time as _tw; _tw.sleep(0.2)
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
                    # 补触发 React 合成事件
                    self.driver.execute_script(f"""
                        const box = document.querySelector({sel});
                        if (!box) return;
                        box.dispatchEvent(new InputEvent('input', {{bubbles:true, cancelable:true}}));
                        box.dispatchEvent(new Event('change', {{bubbles:true}}));
                        box.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:' '}}));
                    """)
                    import time as _tw2; _tw2.sleep(0.2)
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
        # 用通用的回复数计数(DeepSeek/豆包/Gemini 各种都覆盖到)
        _count_js = """
            return (
                document.querySelectorAll('div.ds-markdown.ds-assistant-message-main-content').length ||
                Math.floor(document.querySelectorAll('p.ds-markdown-paragraph').length / 1) ||
                document.querySelectorAll('div.markdown,[data-message-author-role="assistant"]').length
            );
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

        # 1.5) 镜像站/ChatGPT 专用: 多策略发送
        _before_cnt = 0
        try:
            _before_cnt = self.driver.execute_script(_count_js) or 0
        except Exception:
            pass

        # 策略A: focus 输入框 + Enter (实测最稳定的方式,DeepSeek 也支持)
        try:
            from selenium.webdriver.common.action_chains import ActionChains as _AC
            from selenium.webdriver.common.keys import Keys as _K
            self.driver.execute_script("""
                const box = document.querySelector('textarea')
                         || document.querySelector('#prompt-textarea')
                         || document.querySelector('div[contenteditable="true"]');
                if (box) box.focus();
            """)
            time.sleep(0.2)
            _AC(self.driver).send_keys(_K.RETURN).perform()
            self.log_signal.emit("已按 Enter 发送，等待响应...", "info")
            time.sleep(1.5)
            _after_cnt = self.driver.execute_script(_count_js) or 0
            if _after_cnt > _before_cnt:
                self.log_signal.emit(f"✓ 发送成功(消息数 {_before_cnt}→{_after_cnt})", "info")
                return True
            self.log_signal.emit(f"Enter后消息数未增加({_before_cnt}→{_after_cnt})，尝试按钮", "warn")
        except Exception as e:
            self.log_signal.emit(f"Enter发送异常: {e}", "warn")

        # 策略B: 强制点击按钮(DeepSeek + ChatGPT 通用,加 textarea 邻近按钮策略)
        try:
            clicked = self.driver.execute_script(r"""
                // 1) 通用按钮选择器(ChatGPT/Claude 镜像站)
                let btn = document.querySelector('button.composer-submit-btn')
                       || document.querySelector('[data-testid="send-button"]')
                       || document.querySelector('button[aria-label*="发送"]')
                       || document.querySelector('button[aria-label*="Send" i]');
                if (btn) {
                    btn.removeAttribute('disabled');
                    btn.removeAttribute('aria-disabled');
                    btn.click();
                    return 'compat-btn';
                }
                // 2) DeepSeek: textarea 旁边的最右下角带 svg 的 [role=button]
                //    (textarea 的祖父级 form/div 里, 选 m 尺寸或 sizing-container)
                const ta = document.querySelector('textarea');
                if (ta) {
                    // 找 textarea 共同祖先(往上找 form/div 容器)
                    let container = ta.parentElement;
                    for (let i = 0; i < 5 && container; i++) {
                        const candidates = container.querySelectorAll(
                            'div[role="button"]:has(svg)');
                        // 候选里选可见 + 右下位置的(taX > textarea.x 且 visible)
                        const taRect = ta.getBoundingClientRect();
                        let best = null;
                        let bestX = -Infinity;
                        for (const c of candidates) {
                            if (c.offsetParent === null) continue;
                            const r = c.getBoundingClientRect();
                            // 选 textarea 右下方的, 优先最靠右
                            if (r.top >= taRect.top - 10 && r.left >= taRect.left
                                    && r.right > bestX) {
                                best = c;
                                bestX = r.right;
                            }
                        }
                        if (best) {
                            best.click();
                            return 'deepseek-nearby-btn:' + (best.className || '').slice(0, 50);
                        }
                        container = container.parentElement;
                    }
                }
                return 'no-btn';
            """)
            self.log_signal.emit(f"点击发送按钮策略B: {clicked}", "info")
            time.sleep(1.5)
            _after_cnt2 = self.driver.execute_script(_count_js) or 0
            if _after_cnt2 > _before_cnt:
                self.log_signal.emit(f"✓ 按钮点击成功(消息数 {_before_cnt}→{_after_cnt2})", "info")
                return True
        except Exception as e:
            self.log_signal.emit(f"按钮发送异常: {e}", "warn")

        # 策略C: 走原来的旧逻辑(fallback)
        self.log_signal.emit("策略 A/B 都未确认发送, 退到旧 selector 兜底", "warn")

        # 2) 等按钮可点(每 0.25s 轮询,最多 10s)
        sel = json.dumps(send_btn_selector)
        deadline = time.time() + 10
        while time.time() < deadline:
            if self._stop.is_set(): return False
            clicked = self.driver.execute_script(f"""
                const btn = document.querySelector('button.composer-submit-btn')
                         || document.querySelector({sel})
                         || document.querySelector('[data-testid="send-button"]')
                         || document.querySelector('button[aria-label*="发送" i]')
                         || document.querySelector('button[aria-label*="Send" i]')
                         || document.querySelector('form button[type="submit"]');
                if (!btn) return false;
                const ariaDis = (btn.getAttribute('aria-disabled') || '').toLowerCase();
                // 只检查 disabled 属性和 aria-disabled，不检查 className（避免误判）
                const dis = btn.disabled || ariaDis === 'true';
                if (!dis) {{ btn.click(); return true; }}
                // 即使 disabled 也强点
                btn.removeAttribute('disabled');
                btn.removeAttribute('aria-disabled');
                btn.click();
                return true;
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
        # DeepSeek 专属:用"p.ds-markdown-paragraph 的父分组数"做计数
        # 这样新版 / 旧版都能用一致计数
        if prof.get("_grab_strategy") == "deepseek_paragraphs":
            try:
                n = int(self.driver.execute_script(r"""
                    let n1 = document.querySelectorAll(
                        'div.ds-markdown.ds-assistant-message-main-content').length;
                    if (n1 > 0) return n1;
                    // 退路:数 p.ds-markdown-paragraph 的"父分组数"
                    const paragraphs = document.querySelectorAll('p.ds-markdown-paragraph');
                    if (!paragraphs.length) return 0;
                    let groups = 0;
                    let curParent = null;
                    for (const p of paragraphs) {
                        if (p.parentElement !== curParent) {
                            groups++;
                            curParent = p.parentElement;
                        }
                    }
                    return groups;
                """) or 0)
                if n > 0:
                    return n
            except Exception:
                pass  # 降级到通用流程

        # 依次尝试 response 主选择器 + fallback，返回第一个有结果的数量
        selectors = []
        primary = prof.get('response', '')
        if primary:
            selectors.append(primary)
        selectors.extend(prof.get('_response_fallback', []))
        if not selectors:
            selectors = ['div.markdown', '[data-message-author-role="assistant"]']
        for sel in selectors:
            try:
                cnt = int(self.driver.execute_script(
                    f"return document.querySelectorAll({json.dumps(sel)}).length;"
                ) or 0)
                if cnt > 0:
                    return cnt
            except Exception:
                continue
        return 0

    def _grab_last_response(self, prof):
        """
        抓取最新 AI 回复文本。
        优先级:
          1. TamperMonkey bridge —— 如果档案有 tm_bridge=True,
             先读 localStorage.__novelai_reply(由 TM 脚本写入),
             有内容且时间戳在 60s 内就直接用,跳过 DOM 选择器。
          2. DOM 选择器(profile 主选择器 → _response_fallback → 通用兜底)
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

        # ── 1.5. DeepSeek 专属策略:把"最近一组 p.ds-markdown-paragraph"拼成完整回复
        # 用户报告 DeepSeek DOM 变化:
        #   div.ds-markdown.ds-assistant-message-main-content 是外层容器
        #   p.ds-markdown-paragraph 是段落,但新版可能拿不到外层 div,只有 p
        # 策略:扫所有 p.ds-markdown-paragraph,按 DOM 顺序找最后一组连续的(共同父亲)
        if prof.get("_grab_strategy") == "deepseek_paragraphs":
            try:
                ds_text = self.driver.execute_script(r"""
                    // 1) 优先用外层 div.ds-markdown.ds-assistant-message-main-content
                    let containers = document.querySelectorAll(
                        'div.ds-markdown.ds-assistant-message-main-content');
                    if (containers.length > 0) {
                        const last = containers[containers.length - 1];
                        return (last.innerText || last.textContent || '').trim();
                    }
                    // 2) 退路:扫所有 p.ds-markdown-paragraph,按"父节点分组"取最后一组
                    const paragraphs = document.querySelectorAll('p.ds-markdown-paragraph');
                    if (!paragraphs.length) return '';
                    // 按 immediate parent 分组(同一回复的 p 共父亲)
                    const groups = [];
                    let curParent = null;
                    let curGroup = [];
                    for (const p of paragraphs) {
                        if (p.parentElement !== curParent) {
                            if (curGroup.length) groups.push(curGroup);
                            curParent = p.parentElement;
                            curGroup = [p];
                        } else {
                            curGroup.push(p);
                        }
                    }
                    if (curGroup.length) groups.push(curGroup);
                    if (!groups.length) return '';
                    // 用最后一组
                    const lastGroup = groups[groups.length - 1];
                    return lastGroup.map(p => (p.innerText || p.textContent || '').trim())
                                    .filter(t => t).join('\n\n');
                """) or ""
                if ds_text and len(ds_text.strip()) > 10:
                    return ds_text.strip()
            except Exception:
                pass  # 降级到通用 selector 流程

        # ── 2. DOM 选择器(优先抓 assistant role 的最后一条)
        # 顺序: assistant 容器内的 markdown > assistant 容器 > 任意 markdown
        _fallback_defaults = [
            '[data-message-author-role="assistant"] div.markdown',
            '[data-message-author-role="assistant"] .prose',
            '[data-message-author-role="assistant"]',
            'div.markdown',  # 兜底:可能是用户消息,但有内容总比没有强
            'div.prose',
        ]
        selectors = []
        primary = prof.get('response', '')
        # 主选择器先用 assistant 限定的版本
        if primary == 'div.markdown':
            selectors.append('[data-message-author-role="assistant"] div.markdown')
        if primary:
            selectors.append(primary)
        selectors.extend(prof.get('_response_fallback', []))
        selectors.extend(_fallback_defaults)
        # 去重保序
        seen = set()
        selectors = [s for s in selectors if s and not (s in seen or seen.add(s))]

        for sel in selectors:
            try:
                text = self.driver.execute_script(f"""
                    const ns = document.querySelectorAll({json.dumps(sel)});
                    if (!ns.length) return '';
                    const last = ns[ns.length - 1];
                    return (last.innerText || last.textContent || '').trim();
                """) or ""
                if len(text.strip()) > 10:
                    return text.strip()
            except Exception:
                continue
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
        rb_chrome = QRadioButton("Chrome 调试(attach,推荐)"); rb_chrome.setChecked(True)
        rb_edge = QRadioButton("系统 Edge")
        self.kernel_group.addButton(rb_chrome, 1)
        self.kernel_group.addButton(rb_edge, 2)
        for rb in (rb_chrome, rb_edge):
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
        self.btn_gen_one = QPushButton("📖 生成第一章")
        self.btn_gen_one.setStyleSheet(
            "background:#27ae60;color:white;padding:6px 14px;font-weight:bold;border-radius:3px;")
        self.btn_gen_three = QPushButton("生成黄金三章")
        self.btn_regen_three = QPushButton("不想要,重生成黄金三章")
        crow.addWidget(self.btn_gen_one)
        crow.addWidget(self.btn_gen_three)
        crow.addWidget(self.btn_regen_three)

        crow.addWidget(QLabel("连续生成:"))
        self.batch_count = QSpinBox()
        self.batch_count.setRange(1, 999); self.batch_count.setValue(15)
        crow.addWidget(self.batch_count)
        crow.addWidget(QLabel("章"))

        crow.addWidget(QLabel("字数死磕:"))
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 50); self.retry_count.setValue(10)  # 上限提到 50,默认 10
        self.retry_count.setToolTip(
            "死磕次数上限(防死循环用,不是必然次数)。\n"
            "实际重写次数 = 直到达标或用尽次数。\n"
            "如果质量阈值高、模型差,可能用满。建议留 10 次以上。")
        crow.addWidget(self.retry_count)
        crow.addWidget(QLabel("次上限"))

        crow.addWidget(QLabel("|质量阈值≥"))
        self.quality_threshold = QSpinBox()
        self.quality_threshold.setRange(0, 100); self.quality_threshold.setValue(75)
        self.quality_threshold.setSuffix(" 分")
        self.quality_threshold.setToolTip(
            "盘古质量评分阈值(0-100)。\n"
            "评分低于此值 → 触发死磕重写(直到达标或用尽次数上限)。\n"
            "设 0 = 关闭分数门(只看字数/钩子/禁用词)。\n"
            "设 75 = 中等严苛(推荐),设 85 = 严苛,设 90+ = 强迫症")
        crow.addWidget(self.quality_threshold)

        self.btn_start = QPushButton("▶ 开始连续生成")
        self.btn_pause = QPushButton("⏸ 暂停/停止")
        crow.addWidget(self.btn_start); crow.addWidget(self.btn_pause)
        crow.addStretch()
        glay.addLayout(crow)

        crow2 = QHBoxLayout()
        self.auto_save_project = QCheckBox("💾 自动保存项目(每章后立即写盘)")
        self.auto_save_project.setChecked(True)
        self.auto_save_project.setToolTip(
            "勾选后,每生成完一章会立即把项目保存到当前 .json 文件\n"
            "+ 摘要写完后再自动保存一次\n"
            "+ 每 60 秒额外定时保存一次\n"
            "防止意外关机/崩溃丢章节,强烈推荐保留。")
        self.auto_save_project.setStyleSheet("QCheckBox { color: #2ecc71; font-weight: bold; }")
        crow2.addWidget(self.auto_save_project)
        self.auto_save = QCheckBox("自动保存到 TXT")
        self.auto_save.setChecked(True)
        self.auto_save.setToolTip("生成完后另存一份独立 TXT 到项目目录(章节标题做文件名)")
        crow2.addWidget(self.auto_save)
        self.auto_grab = QCheckBox("自动抓取并回填(生成完即写入章节)")
        self.auto_grab.setChecked(True)
        crow2.addWidget(self.auto_grab)
        self.use_attachment = QCheckBox("📎 全部任务走附件(绕过镜像站审核-推荐)")
        self.use_attachment.setChecked(True)  # 默认开启
        self.use_attachment.setToolTip(
            "勾选后,所有任务(包括短任务)都通过 txt 附件发送给 AI\n"
            "✅ 推荐: 镜像站对短文本也可能触发审核,统一走附件最稳\n"
            "⚠️ 不勾: 直接发文本,可能被 flagged_by_moderation 拦截\n"
            "── DeepSeek 等无审核站默认会关掉这个 + 自动抓取 + 自动 TXT")
        crow2.addWidget(self.use_attachment)
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
        """1=Chrome 调试 attach / 2=系统 Edge (standalone 已移除)"""
        idx = self.kernel_group.checkedId()
        if idx == 2:
            return "msedge"
        return "chrome"  # 默认 attach

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
# 七、(原封面生成页已删除 — 用户不需要,2026-05-16 第十三批)
# =====================================================================


# =====================================================================
# 八、主窗口
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_FULL)
        self.resize(1280, 820)
        # 按 font_scale 把全局样式表里的 font-size: Npx 全部按倍率放大
        # 这是修 BUG-016 的关键 — 不然 app.setFont() 被这里的 13px 死压
        _scale = 1.0
        try:
            from PyQt5.QtWidgets import QApplication as _QA
            _scale = float(_QA.instance().property("_novelai_dpi_scale") or 1.0)
        except Exception:
            pass
        if _scale > 1.0:
            import re as _re
            def _sz(m):
                n = int(m.group(1))
                return f"font-size: {int(round(n * _scale))}px"
            scaled_qss = _re.sub(r'font-size:\s*(\d+)px', _sz, STYLESHEET)
            self.setStyleSheet(scaled_qss)
        else:
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
            # Phase C-3:盘古 ↔ lifespan_loops 联动桥
            try:
                self._install_pangu_lifespan_bridge()
            except Exception as e:
                print(f"[warn] 盘古-lifespan 联动安装失败: {e}")
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
        # 第 3/5/6 项:恢复用户保存过的自定义题材/金手指/人设条目
        try:
            self.tab_settings._load_custom_checks()
        except Exception:
            pass
        # 第 1 项:加载完之后再装自动保存钩子(避免 load 过程被当作 dirty)
        self.tab_settings.enable_auto_save()
        # 加载用户为站点存的选择器覆盖(BUG-018:DOM 不稳定的解决)
        try:
            self._load_site_profile_overrides()
        except Exception:
            pass
        # 第 7 项:把题材/时代/金手指/人设串成折叠链
        try:
            self.tab_settings._install_collapsible_chain()
        except Exception:
            pass

        # Phase C-2:启动时加载用户自定义风格库(覆盖内置)
        try:
            from PyQt5.QtCore import QSettings as _QS2
            _ps_settings = _QS2("NovelAI", "PanguStyleLib")
            _custom_styles = _ps_settings.value("custom_mapping", None)
            if _custom_styles and isinstance(_custom_styles, list) and _custom_styles:
                from pangu_system import STYLE_MAPPING as _SM
                _SM.clear()
                _SM.extend(_custom_styles)
        except Exception:
            pass

        # ───── 第 9 项:60 秒定时 autosave(防止崩溃丢失对话记忆) ─────
        try:
            from PyQt5.QtCore import QTimer as _AsT
            self._periodic_autosave_timer = _AsT(self)
            self._periodic_autosave_timer.setInterval(60_000)  # 60 秒
            self._periodic_autosave_timer.timeout.connect(self._periodic_autosave_fire)
            self._periodic_autosave_timer.start()
        except Exception:
            pass

        # BUG-016 配套:遍历所有子 widget 把局部 setStyleSheet 里的 font-size 也按倍率放大
        # (全文 26 处 setStyleSheet 写死 font-size,只改全局 STYLESHEET 还不够)
        if _scale > 1.0:
            try:
                import re as _re2
                def _scale_qss_str(s):
                    return _re2.sub(r'font-size:\s*(\d+)px',
                        lambda m: f"font-size: {int(round(int(m.group(1)) * _scale))}px", s)
                for w in self.findChildren(QWidget):
                    ss = w.styleSheet()
                    if ss and "font-size" in ss:
                        w.setStyleSheet(_scale_qss_str(ss))
            except Exception:
                pass

        # ───── 启动时按当前 AI 站点联动 3 checkbox 默认值 ─────
        # 用户原话:'除了镜像站和GPT 其他都不勾选'
        try:
            _cur_btn = self.tab_settings.ai_group.checkedButton()
            if _cur_btn is not None:
                _ai = _cur_btn.text()
                if _ai in ("ChatGPT", "ChatGPT镜像"):
                    self.tab_generation.auto_save.setChecked(True)
                    self.tab_generation.auto_grab.setChecked(True)
                    self.tab_generation.use_attachment.setChecked(True)
                elif _ai != "自定义":
                    self.tab_generation.auto_save.setChecked(False)
                    self.tab_generation.auto_grab.setChecked(False)
                    self.tab_generation.use_attachment.setChecked(False)
        except Exception:
            pass

        # ───── 首次启动盘古介绍 banner(Phase A,真位置) ─────
        try:
            from PyQt5.QtCore import QSettings as _QS, QTimer as _QT
            _s = _QS("NovelAI", "Pangu")
            if not _s.value("first_seen", False, type=bool):
                try:
                    from pangu_system import get_default_engine as _pe
                    _banner = _pe().get_first_activation_banner()
                except Exception:
                    _banner = None
                if _banner:
                    # 延迟 500ms,等主窗口完全显示后再弹
                    def _show_banner():
                        QMessageBox.information(
                            self, "🛕 欢迎使用【盘古超级系统】", _banner)
                        _s.setValue("first_seen", True)
                    _QT.singleShot(500, _show_banner)
                else:
                    _s.setValue("first_seen", True)
        except Exception:
            pass

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
            ("🕓 恢复历史版本(最近 10 次)", self.restore_project_backup, ""),
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
        a_font = QAction("🔍 界面字体大小...", self)
        a_font.triggered.connect(self.show_font_scale_dialog)
        sm.addAction(a_font)
        sm.addSeparator()
        a = QAction("关于", self); a.triggered.connect(self.show_about)
        sm.addAction(a)

        # 工具菜单(诊断 / 现场拾取 / 清理)
        tm = m.addMenu("工具(&T)")
        a_diag = QAction("🔬 诊断当前 AI 网页 DOM(看选择器命中)", self)
        a_diag.triggered.connect(self.show_dom_diagnostics)
        tm.addAction(a_diag)
        a_pick = QAction("🎯 现场拾取选择器(点页面元素自动生成)", self)
        a_pick.triggered.connect(self.start_dom_picker)
        tm.addAction(a_pick)
        tm.addSeparator()
        a_override = QAction("📝 手动编辑当前站点选择器...", self)
        a_override.triggered.connect(self.edit_site_profile_override)
        tm.addAction(a_override)
        tm.addSeparator()
        a_clean_meta = QAction("🧹 扫描清理所有章节尾部元信息(本章完/钩子/选项)", self)
        a_clean_meta.triggered.connect(self.batch_clean_chapter_meta)
        tm.addAction(a_clean_meta)

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
        self.tab_charlib = CharacterLibrary()  # 新增: 角色库+关系+时间线+物品+伏笔
        # 寿元/伏笔(可选模块)
        if LIFESPAN_LOOPS_AVAILABLE:
            self.tab_lifespan = LifespanLoopsPanel(mw=self)
        else:
            self.tab_lifespan = None
        self.tab_skills = SkillLibrary()
        self.tab_generation = GenerationControl()
        self.tab_editor = ChapterEditor()
        # 工作流可视化(可选模块,放最后实例化,因为依赖 self.workflow 已就绪)
        # 这里先占位 None,真正的 WorkflowPanel 在 __init__ 末尾装配
        self.tab_workflow = None

        tab_list = [
            (self.tab_settings, "创作设置"),
            (self.tab_outline, "故事大纲"),
            (self.tab_memory, "对话记忆"),
            (self.tab_canon, "Canon 设定"),
            (self.tab_charlib, "🎭 角色与世界"),
        ]
        if self.tab_lifespan is not None:
            tab_list.append((self.tab_lifespan, "寿元/伏笔"))
        tab_list.append((self.tab_skills, "技能库"))
        tab_list += [
            (self.tab_generation, "生成控制"),
            (self.tab_editor, "章节编辑器"),
        ]
        for w, n in tab_list:
            self.tabs.addTab(w, n)
        ml.addWidget(self.tabs, 1)

    def _build_statusbar(self):
        sb = QStatusBar();
        # ───── Phase B:盘古手册 + 批量巡检 顶部工具栏 ─────
        _tb_pangu = self.addToolBar("盘古工具")
        _tb_pangu.setMovable(False)
        _act_manual = QAction("❓ 盘古手册", self)
        _act_manual.triggered.connect(self._on_pangu_show_manual)
        _tb_pangu.addAction(_act_manual)
        _act_batch = QAction("🛡️ 全书巡检", self)
        _act_batch.triggered.connect(self._on_pangu_batch_scan)
        _tb_pangu.addAction(_act_batch)
        # Phase C-2:风格库编辑器
        _act_style_edit = QAction("🎨 风格库", self)
        _act_style_edit.setToolTip("打开盘古风格库可视化编辑器")
        _act_style_edit.triggered.connect(self._on_pangu_style_editor)
        _tb_pangu.addAction(_act_style_edit)
        # Phase C-1:差异化状态查看
        _act_diff_info = QAction("🎲 差异化", self)
        _act_diff_info.setToolTip("查看章节差异化(防 AI 套路)当前状态和下一章预览参数")
        _act_diff_info.triggered.connect(self._on_pangu_diff_info)
        _tb_pangu.addAction(_act_diff_info)
        self.setStatusBar(sb)
        sb.addWidget(QLabel(f"© 2026 {APP_NAME} {APP_VERSION} | Python + PyQt5"))
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
        self.tab_outline.btn_rename.clicked.connect(self.open_rename_dialog)
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
        self.tab_generation.btn_gen_one.clicked.connect(self.gen_first_chapter)
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

        # 角色与世界 Tab
        self.tab_charlib.btn_extract_from_chapters.clicked.connect(self._charlib_extract_from_chapters)

        # 章节编辑器: 风格检测 + 备选版本
        self.tab_editor.btn_style_check.clicked.connect(self._on_style_check)
        self.tab_editor.btn_regen_alt.clicked.connect(self._on_regen_alt)

        # ChapterEditor 盘古超级系统按钮(本地词扫已在 ChapterEditor 内消化)
        self.tab_editor.pangu_qcheck_requested.connect(self._on_pangu_qcheck)
        self.tab_editor.laodao_critique_requested.connect(self._on_laodao_critique)
        self.tab_editor.pangu_spiral_requested.connect(self._on_pangu_spiral)
        self.tab_editor.pangu_preview_prompt_requested.connect(self._on_pangu_preview_prompt)
        # BUG-014:用户在元信息面板点了"下一章选项"按钮 → 记到 _user_picked_next_option,
        # _send_next_chapter 会把它当作开局指引注入 prompt
        self.tab_editor.next_option_picked.connect(self._on_pangu_next_option_picked)
        self.tab_settings.btn_pangu_wl_apply.clicked.connect(self._on_pangu_apply_whitelist)
        # CreationSettings 盘古快捷工具
        self.tab_settings.btn_pangu_style.clicked.connect(self._on_pangu_style_match)
        self.tab_settings.btn_pangu_arch.clicked.connect(
            lambda: self._on_pangu_mode("architect"))
        self.tab_settings.btn_pangu_dream.clicked.connect(
            lambda: self._on_pangu_mode("dreamweaver"))
        self.tab_settings.btn_pangu_alch.clicked.connect(
            lambda: self._on_pangu_mode("alchemist"))
        self.tab_settings.btn_pangu_sculpt.clicked.connect(
            lambda: self._on_pangu_mode("sculptor"))
        # 盘古开关 → 运行时切换
        self.tab_settings.pangu_check.toggled.connect(self._on_pangu_toggle)

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
                "两种内核模式:\n"
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
        # AI 站点联动:ChatGPT/镜像站 → 3 checkbox 全开;其他 AI → 全关
        # 用户原话:"除了镜像站和GPT 其他都不勾选"
        # 注意:radio text 是 "ChatGPT"(不是 AI_URLS 里的 "ChatGPT镜像")
        try:
            tg = self.tab_generation
            if ai in ("ChatGPT", "ChatGPT镜像"):
                tg.auto_save.setChecked(True)
                tg.auto_grab.setChecked(True)
                tg.use_attachment.setChecked(True)
                tg.log(f"已切到 {ai} → 自动保存TXT/自动抓取/附件模式 全部打开", "info")
            elif ai == "自定义":
                pass  # 不动用户当前选择
            else:
                tg.auto_save.setChecked(False)
                tg.auto_grab.setChecked(False)
                tg.use_attachment.setChecked(False)
                tg.log(f"已切到 {ai} → 自动保存TXT/自动抓取/附件模式 全部关闭(此站无审核,直发更快)", "info")
        except Exception:
            pass

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
        self.tab_editor.show_chapter(ch, idx)  # 记录索引,供风格检测/备选版本使用
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
        # 盘古超级系统:保存前自动本地词扫(0 token,只在日志提示)
        try:
            if getattr(self.tab_settings, "pangu_check", None) and self.tab_settings.pangu_check.isChecked():
                from pangu_system import get_default_engine as _pg_engine
                _content = self.tab_editor.content_edit.toPlainText()
                if _content.strip():
                    _r = _pg_engine().quick_chapter_lint(_content)
                    if not _r.get("pass"):
                        _msg = f"WARN 盘古词扫 {_r.get('score', 0)}分 - " + "; ".join(_r.get("issues", [])[:3])
                        if hasattr(self, "tab_generation"):
                            self.tab_generation.log(_msg, "warn")
        except Exception:
            pass
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
        # 读取附件模式开关
        allow_att = self.tab_generation.use_attachment.isChecked() if hasattr(self.tab_generation, 'use_attachment') else True
        self.worker.submit({
            "action": "send_prompt",
            "prompt": prompt,
            "task_id": label,
            "url": url,
            "type_delay_ms": type_delay,
            "allow_attachment": allow_att,
        })

    def _on_response_received(self, task_id, content):
        """worker 回调:某次提示词的 AI 回复已抓取完毕"""
        # Phase B:盘古质检结果路由(优先级最高,不走原回填逻辑)
        try:
            tgt = (self._pending_task_target or {}).get("target", "") if hasattr(self, "_pending_task_target") else ""
            if tgt == "pangu_qcheck":
                # 拿当前章节原文做段落映射
                _cur_idx = self.tab_editor.current_index if hasattr(self.tab_editor, "current_index") else 0
                _orig = ""
                if self.chapters and isinstance(_cur_idx, int) and 0 <= _cur_idx < len(self.chapters):
                    _orig = self.chapters[_cur_idx].get("content", "")
                self._on_pangu_qcheck_response(content, _orig)
                self._pending_task_target = None
                return
            if tgt == "pangu_spiral":
                QMessageBox.information(self, "🌀 盘古 P1-P7 螺旋诊断", content[:3000])
                self._pending_task_target = None
                return
            if tgt == "pangu_mode":
                self.tab_generation.log(f"✓ 盘古模式切换完成:\n{content[:200]}", "info")
                self._pending_task_target = None
                return
            if tgt == "pangu_autofix":
                # AI 修复完成 → 把内容回填当前章节
                meta = self._pending_task_target or {}
                ch_idx = meta.get("ch_idx", -1)
                orig = meta.get("original_chapter", "")
                self._on_pangu_autofix_response(content, ch_idx, orig)
                self._pending_task_target = None
                return
            if tgt == "laodao_critique":
                # 老刀毒舌点评返回 → 弹窗展示
                meta = self._pending_task_target or {}
                self._on_laodao_critique_response(content, meta)
                self._pending_task_target = None
                return
        except Exception:
            pass
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
            # 整段内容始终填入章节大纲框
            self.tab_outline.chapter_outline_edit.setPlainText(content)
            # 同时尝试按标题拆分回填各分项框
            self._auto_fill_outline(content)
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
                # 第 9 项:摘要进盘 → 立即 autosave,保证不丢
                # 尊重 auto_save_project 开关(用户可关掉)
                if getattr(self.tab_generation, "auto_save_project", None) is None \
                        or self.tab_generation.auto_save_project.isChecked():
                    try:
                        self._autosave()
                        self.tab_generation.log("  · 已自动保存到项目文件", "info")
                    except Exception:
                        pass
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
        elif target == "world_extract":
            # 角色库结构化提取
            self._on_world_extract_received(content, meta.get("ch_num", 0))
        elif target == "style_audit":
            # 风格检测结果 - 弹窗显示
            ch_idx = meta.get("ch_idx", 0)
            if content.strip():
                QMessageBox.information(
                    self, f"风格检测结果 - 第{ch_idx+1}章",
                    content.strip())
            else:
                QMessageBox.warning(self, "失败", "AI 未返回检测结果")
        elif target == "alt_version":
            # 备选版本 - 弹窗让用户选择保留
            ch_idx = meta.get("ch_idx", 0)
            if not content.strip():
                QMessageBox.warning(self, "失败", "AI 未返回新版本")
                return
            ret = QMessageBox.question(
                self, f"备选版本 - 第{ch_idx+1}章",
                f"AI 已生成备选版本({len(content)} 字)。\n\n"
                f"前 200 字预览:\n{content[:200]}...\n\n"
                "是否用此版本替换原章节内容?\n"
                "(选「否」则只显示在编辑器供你比对,不替换)",
                QMessageBox.Yes | QMessageBox.No)
            if ret == QMessageBox.Yes:
                if 0 <= ch_idx < len(self.chapters):
                    self.chapters[ch_idx]["content"] = content.strip()
                    self.tab_editor.show_chapter(self.chapters[ch_idx], ch_idx)
                    self.tab_generation.log(
                        f"✓ 第{ch_idx+1}章已替换为备选版本", "success")
            else:
                # 仅显示在编辑器
                self.tab_editor.content_edit.setPlainText(content.strip())
                self.tabs.setCurrentWidget(self.tab_editor)
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

    # ─────────────── 风格一致性检测 ───────────────
    def _on_style_check(self):
        """检测当前章节风格与参考章节的一致性"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节")
            return
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』再使用风格检测。")
            return
        cur_idx = self.tab_editor.current_index
        if cur_idx is None or cur_idx < 0 or cur_idx >= len(self.chapters):
            QMessageBox.information(self, "提示", "请先在编辑器选中一个章节")
            return
        if cur_idx == 0:
            QMessageBox.information(
                self, "提示",
                "第 1 章是基准章,无需检测。请打开第 2 章及以后的章节进行风格检测。")
            return
        cur_ch = self.chapters[cur_idx]
        # 用第 1 章作为风格基准
        ref_ch = self.chapters[0]
        prompt = PROMPTS["style_audit"].format(
            reference=ref_ch.get("content", "")[:3000],
            content=cur_ch.get("content", "")[:3000],
        )
        self._send_to_ai(
            prompt, f"风格检测-第{cur_idx+1}章",
            target="style_audit",
            ch_idx=cur_idx,
        )

    # ─────────────── 多版本备选生成 ───────────────
    def _on_regen_alt(self):
        """为当前章节生成备选版本(同样的提示词,让 AI 给不同写法)"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节")
            return
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先点『启动浏览器』")
            return
        cur_idx = self.tab_editor.current_index
        if cur_idx is None or cur_idx < 0 or cur_idx >= len(self.chapters):
            QMessageBox.information(self, "提示", "请先选中要重生成的章节")
            return
        ch_num = cur_idx + 1
        co = self.tab_outline.chapter_outline_edit.toPlainText()
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
        )
        prompt += (
            f"\n\n【完整设定参考】\n{full}"
            "\n\n【备选版本要求】\n"
            "请用与上一版【截然不同】的写法重写本章。可以:\n"
            "  · 改变开场切入点(从对话开场/从动作开场/从内心独白开场)\n"
            "  · 调整节奏(放慢或加快)\n"
            "  · 用不同视角或描写偏重\n"
            "保持核心情节不变,但表达完全不同。"
        )
        self._send_to_ai(
            prompt, f"备选版本-第{ch_num}章",
            target="alt_version",
            ch_idx=cur_idx,
        )

    # ─────────────── 角色库自动提取 ───────────────
    # ─────────────── 盘古超级系统:新功能入口 ───────────────
    def _on_pangu_toggle(self, checked):
        # 运行时根据 GUI 勾选状态切换盘古的 PROMPTS 包裹
        try:
            from pangu_patch import install_pangu, uninstall_pangu, is_installed
        except ImportError:
            return
        g = globals()
        cur = is_installed(g)
        if checked and not cur:
            install_pangu(g)
            self.tab_generation.log("✓ 盘古超级系统已启用(PROMPTS 已包裹)", "info")
        elif not checked and cur:
            uninstall_pangu(g)
            self.tab_generation.log("⊘ 盘古超级系统已停用(PROMPTS 已还原)", "info")

    def _on_pangu_style_match(self):
        # 基于创意灵感关键词匹配盘古风格库,弹结果
        kw = self.tab_settings.inspiration_edit.toPlainText().strip()
        if not kw:
            QMessageBox.information(
                self, "提示",
                "先在【创意灵感】输入框填几个关键词(如 '退婚 战神 都市 神豪')")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        report = get_default_engine().build_style_report(kw)
        dlg = QMessageBox(self)
        dlg.setWindowTitle("🎯 盘古风格匹配")
        dlg.setText("基于你的关键词,推荐 Top 3 风格组合:")
        dlg.setDetailedText(report)
        dlg.exec_()

    def _on_pangu_mode(self, mode_key):
        # 切换盘古四模式(发个 mode-switch prompt 给当前 AI)
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』Tab 启动浏览器并完成 AI 网站登录。")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        prompt = get_default_engine().build_mode_switch_prompt(mode_key)
        names = {"architect": "建筑师", "dreamweaver": "造梦师",
                 "alchemist": "炼金术士", "sculptor": "雕刻家"}
        self._send_to_ai(
            prompt, f"盘古模式切换-{names.get(mode_key, mode_key)}",
            target="pangu_mode")

    def _on_pangu_qcheck(self, content):
        # 让 AI 按盘古 30 项质检规范深度审稿
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        prompt = get_default_engine().build_quality_check_prompt(content)
        self._send_to_ai(prompt, "盘古30项质检", target="pangu_qcheck")

    def _on_laodao_critique(self, content, retry_round=1):
        """🔪 老刀毒舌点评:让 AI 扮老刀给当前章节开刀。
        retry_round=N 表示第 N 轮(不通过会自动跑下一轮,最多 3 轮)"""
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器并完成登录")
            return
        # 安全截断:老刀 prompt 本身就 ~1.5k,加章节正文要控制总长
        snippet = content[:6000] if len(content) > 6000 else content
        prompt = PROMPTS["critique_laodao"].format(content=snippet)
        self.tab_generation.log(
            f"▶ 召唤老刀 (第 {retry_round} 轮),约 1 分钟回填...", "info")
        self._send_to_ai(
            prompt, f"老刀毒舌点评-第{retry_round}轮",
            target="laodao_critique",
            retry_round=retry_round,
            original_content=content,
        )

    def _on_laodao_critique_response(self, content, meta):
        """老刀点评返回 → 弹窗展示 + 如点评不通过 → 自动再跑一轮(最多 3 轮)"""
        retry_round = meta.get("retry_round", 1)
        original_content = meta.get("original_content", "")
        # 简单的"成功"判定:老刀回复要包含【逐条开刀】或❌或【综合诊断】才算成功格式
        success_markers = ("逐条开刀", "综合诊断", "❌", "🔪", "存活概率", "致命伤")
        is_valid = any(m in content for m in success_markers)
        # 内容太短(<200 字)也算失败
        if len(content) < 200:
            is_valid = False
        if not is_valid:
            if retry_round < 3:
                self.tab_generation.log(
                    f"✗ 老刀点评第 {retry_round} 轮返回格式不对 (字数 {len(content)}),自动重试...",
                    "warn")
                # 自动再跑(原章节再点评一次)
                self._on_laodao_critique(original_content, retry_round=retry_round + 1)
                return
            else:
                self.tab_generation.log(
                    f"✗ 老刀点评 3 轮都不通过,放弃。最后一次返回:\n{content[:500]}",
                    "warn")
                QMessageBox.warning(
                    self, "老刀点评失败",
                    f"3 轮都没拿到合格点评。最后返回(前 500 字):\n\n{content[:500]}")
                return
        # 弹窗展示
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🔪 老刀点评(第 {retry_round} 轮)")
        dlg.resize(900, 700)
        lay = QVBoxLayout(dlg)
        top = QLabel(
            f"<h3 style='color:#c0392b'>🔪 老刀的开刀报告</h3>"
            f"<p>第 {retry_round} 轮 · {len(content)} 字 · "
            f"基于 {len(original_content)} 字的章节正文</p>")
        top.setTextFormat(Qt.RichText)
        lay.addWidget(top)
        txt = QPlainTextEdit()
        txt.setPlainText(content)
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "font-family: 'Microsoft YaHei', sans-serif; font-size: 13px; "
            "line-height: 1.6; background: #fff9f9; padding: 10px;")
        lay.addWidget(txt, 1)
        # 按钮区
        btn_row = QHBoxLayout()
        btn_recheck = QPushButton("🔁 再来一刀(让老刀再点评一次)")
        btn_recheck.setStyleSheet(
            "background:#c0392b;color:white;padding:6px 14px;border-radius:3px;")
        btn_recheck.clicked.connect(
            lambda: (dlg.accept(), self._on_laodao_critique(original_content, 1)))
        btn_copy = QPushButton("📋 复制全部")
        btn_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(content))
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_recheck)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)
        self.tab_generation.log(
            f"✓ 老刀第 {retry_round} 轮点评完成,{len(content)} 字", "success")
        dlg.exec_()

    def _on_pangu_spiral(self, content):
        # 让 AI 诊断当前章节处于 P1-P7 哪个螺旋阶段
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器")
            return
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        prompt = get_default_engine().build_spiral_diagnose_prompt(content)
        self._send_to_ai(prompt, "盘古P1-P7螺旋诊断", target="pangu_spiral")

    # ───── Phase A:Prompt 预览 + 白名单应用 ─────
    def _on_pangu_preview_prompt(self):
        # 预览章节生成时实际发给 AI 的 prompt
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节,无法预览。请先生成一章。")
            return
        cur_idx = self.tab_editor.current_index
        if cur_idx is None or cur_idx < 0:
            cur_idx = 0
        try:
            ch = self.chapters[cur_idx] if cur_idx < len(self.chapters) else self.chapters[0]
        except Exception:
            ch = {}
        # 用当前已生成最后一章作为"上下文",预览下一章 prompt
        s = self.tab_settings
        # BUG #3 修复:从真实大纲控件读取(原 self._outline_text 不存在)
        try:
            _outline_real = (
                self.tab_outline.worldview_edit.toPlainText() + "\n"
                + self.tab_outline.structure_edit.toPlainText()
            ).strip() or "(尚未填写世界观和结构大纲)"
        except Exception:
            _outline_real = "(无法读取大纲)"
        try:
            _ch_outline = self.tab_outline.chapter_outline_edit.toPlainText().strip() or "(无章节大纲)"
        except Exception:
            _ch_outline = "(无章节大纲)"
        try:
            preview_prompt = PROMPTS["chapter"].format(
                title=s.get_title(),
                chapter_num=cur_idx + 2,
                genre="/".join(s.get_selected_genres()) or "通用",
                outline=_outline_real[:1500],
                chapter_outline=_ch_outline[:2500],
                min_words=int(s.get_words_per_chapter() * 0.9),
                target_words=s.get_words_per_chapter(),
            )
        except Exception as e:
            preview_prompt = f"[预览失败] PROMPTS['chapter'].format 报错: {e}"

        dlg = QDialog(self)
        dlg.setWindowTitle(f"👁️ 预览发送给 AI 的 Prompt(已含盘古铁律,共 {len(preview_prompt)} 字符)")
        dlg.resize(900, 700)
        lay = QVBoxLayout(dlg)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setStyleSheet("font-family:'Consolas','Microsoft YaHei';font-size:12px;background:#fafafa;")
        viewer.setPlainText(preview_prompt)
        lay.addWidget(viewer)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec_()

    def _on_pangu_apply_whitelist(self):
        # 应用白名单到 PanguEngine + 刷新高亮
        try:
            from pangu_system import PanguEngine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        text = self.tab_settings.pangu_whitelist_edit.toPlainText()
        PanguEngine.set_whitelist(text)
        wl = PanguEngine.get_whitelist()
        # 刷新章节编辑器高亮
        if hasattr(self.tab_editor, "pangu_highlighter") and self.tab_editor.pangu_highlighter:
            self.tab_editor.pangu_highlighter.refresh_words()
        QMessageBox.information(
            self, "白名单已应用",
            f"已设置 {len(wl)} 个允许词。\n这些词不会再被高亮 / 计入词扫:\n{', '.join(wl) if wl else '(空)'}")

    def _on_pangu_next_option_picked(self, option_text):
        """用户在元信息面板点了某条【下一章选项】 → 记录,下次 _send_next_chapter 注入"""
        self._user_picked_next_option = option_text
        QMessageBox.information(
            self, "✓ 已设定下章开局",
            f"已记录你选的下一章开局走向:\n\n{option_text}\n\n"
            f"下次生成下一章时,会自动把这条作为开局指引注入到 AI 提示词里。\n"
            f"(单次有效,生成后自动清空)")
        try:
            self.tab_generation.log(
                f"📌 用户指定下章开局:「{option_text[:40]}」", "info")
        except Exception:
            pass

    # ───── Phase B:30 项质检 JSON 解析 + 段落标注 ─────
    def _on_pangu_qcheck_response(self, content_response, original_chapter):
        # 解析 AI 返回的 JSON,把失败项映射到段落,然后让 highlighter 标黄
        import json as _json
        try:
            # 提取 JSON(可能包在 markdown code block 里)
            m = re.search(r"\{[\s\S]*\}", content_response)
            if not m:
                raise ValueError("没找到 JSON")
            data = _json.loads(m.group(0))
        except Exception as e:
            QMessageBox.warning(
                self, "盘古质检 JSON 解析失败",
                f"AI 返回不是合法 JSON,无法标注。\n错误:{e}\n\n原始返回前 500 字:\n{content_response[:500]}")
            return
        score = data.get("score", "?")
        failed = data.get("failed_items", [])
        advice = data.get("advice", "")
        # 在章节文本里找 advice 提到的关键词所在段落
        block_ids = set()
        if advice and original_chapter:
            for kw in re.findall(r"[\u4e00-\u9fa5]{2,10}", advice)[:20]:
                idx = original_chapter.find(kw)
                if idx >= 0:
                    block_no = original_chapter.count("\n", 0, idx)
                    block_ids.add(block_no)
        if hasattr(self.tab_editor, "pangu_highlighter") and self.tab_editor.pangu_highlighter:
            self.tab_editor.pangu_highlighter.set_qcheck_blocks(block_ids)

        # 弹结果对话框(改成 QDialog,加"AI 自动修复"按钮)
        dlg = QDialog(self)
        dlg.setWindowTitle("📊 盘古 30 项质检结果")
        dlg.setMinimumWidth(600)
        lay = QVBoxLayout(dlg)

        # 顶部得分行
        score_lab = QLabel(f"<h2>得分:{score}/100</h2><b>失败项:</b>{failed}")
        score_lab.setStyleSheet("color:#1a4480; padding:6px;")
        lay.addWidget(score_lab)

        # 建议(可滚动)
        advice_lab = QLabel(f"<b>建议:</b><br>{advice}")
        advice_lab.setWordWrap(True)
        advice_lab.setStyleSheet("padding:8px; background:#f7f7f7; border:1px solid #ddd;")
        advice_scroll = QScrollArea()
        advice_scroll.setWidget(advice_lab)
        advice_scroll.setWidgetResizable(True)
        advice_scroll.setMinimumHeight(150)
        lay.addWidget(advice_scroll, 1)

        if block_ids:
            seg_lab = QLabel(
                f"<i>相关段落已在编辑器里浅黄高亮(段号:{sorted(block_ids)[:10]})</i>")
            seg_lab.setStyleSheet("color:#888; padding:4px;")
            lay.addWidget(seg_lab)

        # 按钮区
        btn_row = QHBoxLayout()
        btn_autofix = QPushButton("🔧 让 AI 自动修复这些问题")
        btn_autofix.setStyleSheet(
            "QPushButton { background:#e67e22; color:white; padding:8px 16px; "
            "border-radius:3px; font-weight:bold; font-size:14px; }"
            "QPushButton:hover { background:#d35400; }")
        btn_autofix.setToolTip(
            "把章节正文 + 失败项 + 建议发给 AI,让它直接重写有问题的部分。\n"
            "完成后修复版本会自动覆盖当前章节内容(原版本通过项目备份找回:菜单 → 🕓 恢复历史版本)。")
        btn_close = QPushButton("先关掉(我手动改)")
        btn_close.setStyleSheet("QPushButton { background:#888; padding:8px 16px; }")

        # 失败项太少时不必修复
        if not failed:
            btn_autofix.setEnabled(False)
            btn_autofix.setText("✓ 已无失败项,无需修复")
            btn_autofix.setStyleSheet(
                "QPushButton { background:#2ecc71; color:white; padding:8px 16px; "
                "border-radius:3px; font-weight:bold; }")

        def _on_autofix():
            dlg.accept()
            self._on_pangu_autofix_request(score, failed, advice, original_chapter)

        btn_autofix.clicked.connect(_on_autofix)
        btn_close.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_autofix, 2)
        btn_row.addWidget(btn_close, 1)
        lay.addLayout(btn_row)

        dlg.exec_()

    def _on_pangu_autofix_request(self, score, failed, advice, original_chapter):
        """触发 AI 自动修复 — 把 issues + content 发给 AI 让它重写问题段落"""
        if not original_chapter or not original_chapter.strip():
            QMessageBox.warning(self, "提示", "原章节内容为空,无法修复")
            return
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录")
            return
        # 记下当前章节 idx,用于回填(用户可能中途切章节)
        ch_idx = getattr(self.tab_editor, "current_index", -1)
        if ch_idx < 0 or ch_idx >= len(self.chapters):
            QMessageBox.warning(
                self, "提示",
                "请先在左侧章节列表里选中要修复的章节(_current_index 无效)")
            return
        prompt = PROMPTS["pangu_autofix"].format(
            score=score,
            failed=failed if failed else "[]",
            advice=advice or "(无具体建议,请按盘古铁律检查并修复)",
            content=original_chapter[:8000],   # 安全截断
        )
        self.tab_generation.log(
            f"▶ 让 AI 修复第 {ch_idx+1} 章(失败项 {failed}),约 1 分钟回填……",
            "info")
        self._send_to_ai(
            prompt, f"AI 修复-第{ch_idx+1}章",
            target="pangu_autofix",
            ch_idx=ch_idx,
            original_chapter=original_chapter,
        )

    def _on_pangu_autofix_response(self, content, ch_idx, original_chapter):
        """AI 修复返回 → 回填当前章节(原内容已通过 save_project 的 .backups 备份)"""
        if not content or not content.strip():
            QMessageBox.warning(
                self, "AI 修复失败", "AI 没返回任何内容,请重试或先检查浏览器/网络。")
            return
        # 容错:去掉可能的 markdown 包裹 / 元信息块(用 pangu_system.strip_chapter_meta)
        fixed = content.strip()
        try:
            from pangu_system import strip_chapter_meta
            fixed = strip_chapter_meta(fixed)
        except Exception:
            pass
        # 比较长度,异常时给提示
        orig_len = len(original_chapter)
        new_len = len(fixed)
        ratio = new_len / orig_len if orig_len > 0 else 1.0
        if ratio < 0.5 or ratio > 1.8:
            ret = QMessageBox.question(
                self, "⚠️ 修复结果异常",
                f"AI 返回内容长度跟原章节差太多:\n"
                f"  原章节:{orig_len} 字  →  AI 返回:{new_len} 字(变化 {(ratio-1)*100:+.1f}%)\n\n"
                f"前 300 字预览:\n{fixed[:300]}...\n\n"
                f"还要回填吗?\n"
                f"  ✓ 是 → 覆盖当前章节(原内容已通过 .backups 备份)\n"
                f"  ✗ 否 → 放弃这次修复",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                self.tab_generation.log("已放弃 AI 修复结果(长度异常)", "warn")
                return
        # 回填
        if 0 <= ch_idx < len(self.chapters):
            self.chapters[ch_idx]["content"] = fixed
            # 如果当前正在编辑这一章,刷新编辑器
            if self.tab_editor.current_index == ch_idx:
                self.tab_editor.content_edit.setPlainText(fixed)
            # 清掉质检高亮(修完了)
            if hasattr(self.tab_editor, "pangu_highlighter") and self.tab_editor.pangu_highlighter:
                self.tab_editor.pangu_highlighter.set_qcheck_blocks(set())
            # 立即 autosave + 备份
            try:
                self.save_project()  # save_project 会触发 _rotate_project_backups 保留 10 次
            except Exception:
                self._autosave()
            self.tab_generation.log(
                f"✓ AI 修复完成第 {ch_idx+1} 章:{orig_len}→{new_len} 字。"
                f"原版本可通过菜单 → 🕓 恢复历史版本 找回",
                "success")
            QMessageBox.information(
                self, "✓ AI 修复完成",
                f"第 {ch_idx+1} 章已自动修复 + 回填 + 保存。\n\n"
                f"字数变化:{orig_len} → {new_len}\n"
                f"想要旧版本?菜单 → 文件 → 🕓 恢复历史版本(最近 10 次)\n\n"
                f"建议:再点一次「📊 30项质检」看新得分。")

    # ───── Phase B:盘古帮助查询面板 ─────
    def _on_pangu_show_manual(self):
        # 弹独立窗口展示盘古完整 spec,带搜索
        try:
            from pangu_system import get_default_engine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        full = get_default_engine().get_full_spec() if hasattr(get_default_engine(), "get_full_spec") else None
        if not full:
            try:
                with open("pangu_full_spec.md", "r", encoding="utf-8") as f:
                    full = f.read()
            except Exception:
                full = "(无法加载 pangu_full_spec.md)"
        dlg = QDialog(self)
        dlg.setWindowTitle("❓ 盘古超级系统 · 完整手册")
        dlg.resize(1100, 800)
        lay = QVBoxLayout(dlg)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("🔍 搜索:"))
        search_input = QLineEdit()
        search_input.setPlaceholderText("输入关键词回车跳转")
        srow.addWidget(search_input, 1)
        btn_next = QPushButton("下一个")
        srow.addWidget(btn_next)
        lay.addLayout(srow)
        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(True)
        viewer.setStyleSheet("font-family:'Microsoft YaHei';font-size:13px;line-height:1.6;")
        viewer.setMarkdown(full)
        lay.addWidget(viewer, 1)

        def do_search():
            kw = search_input.text().strip()
            if not kw:
                return
            cursor = viewer.document().find(kw, viewer.textCursor())
            if cursor.isNull():
                cursor = viewer.document().find(kw)
            if not cursor.isNull():
                viewer.setTextCursor(cursor)
                viewer.ensureCursorVisible()
        search_input.returnPressed.connect(do_search)
        btn_next.clicked.connect(do_search)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec_()

    # ───── Phase B:批量扫描整本书 ─────
    def _on_pangu_batch_scan(self):
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节")
            return
        try:
            from pangu_system import get_default_engine, PanguEngine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        engine = get_default_engine()
        results = []
        all_forbidden_count = {}
        for i, ch in enumerate(self.chapters):
            content = ch.get("content", "")
            if not content.strip():
                continue
            r = engine.quick_chapter_lint(content)
            results.append({
                "idx": i + 1,
                "title": ch.get("title", f"第{i+1}章"),
                "score": r.get("score", 0),
                "pass": r.get("pass", False),
                "issues": r.get("issues", []),
            })
            for w, c in PanguEngine.detect_forbidden_words(content):
                all_forbidden_count[w] = all_forbidden_count.get(w, 0) + c
        if not results:
            QMessageBox.information(self, "提示", "所有章节内容为空")
            return
        # 出报告
        avg = sum(r["score"] for r in results) / len(results)
        passed = sum(1 for r in results if r["pass"])
        top_words = sorted(all_forbidden_count.items(), key=lambda x: -x[1])[:10]
        lines = [
            f"# 盘古全书巡检报告",
            "",
            f"- 章节总数:**{len(results)}**",
            f"- 通过率:**{passed}/{len(results)}** ({passed * 100 // len(results)}%)",
            f"- 平均分:**{avg:.1f} / 100**",
            "",
            "## TOP 10 禁用词(全书累计)",
            "",
        ]
        for w, c in top_words:
            lines.append(f"- `{w}` × {c}")
        lines.extend([
            "",
            "## 各章详情",
            "",
            "| # | 标题 | 得分 | 通过 | 主要问题 |",
            "|---|---|---|---|---|",
        ])
        for r in results:
            ok = "✓" if r["pass"] else "✗"
            issues_s = " / ".join(r["issues"][:2]) if r["issues"] else "-"
            issues_s = issues_s.replace("|", "/")
            lines.append(f"| {r['idx']} | {r['title']} | {r['score']} | {ok} | {issues_s} |")
        report_md = "\n".join(lines)
        # 展示 + 提供保存按钮
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🛡️ 盘古全书巡检报告(共扫描 {len(results)} 章)")
        dlg.resize(1000, 720)
        lay = QVBoxLayout(dlg)
        viewer = QTextBrowser()
        viewer.setMarkdown(report_md)
        viewer.setStyleSheet("font-family:'Microsoft YaHei';font-size:13px;")
        lay.addWidget(viewer, 1)
        brow = QHBoxLayout()
        btn_save_md = QPushButton("💾 保存为 Markdown")
        btn_save_html = QPushButton("🌐 保存为 HTML")
        brow.addStretch()
        brow.addWidget(btn_save_md)
        brow.addWidget(btn_save_html)
        lay.addLayout(brow)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)

        def do_save_md():
            fn, _ = QFileDialog.getSaveFileName(
                dlg, "保存巡检报告", "盘古巡检报告.md", "Markdown (*.md)")
            if fn:
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(report_md)
                QMessageBox.information(dlg, "已保存", fn)

        def do_save_html():
            fn, _ = QFileDialog.getSaveFileName(
                dlg, "保存巡检报告", "盘古巡检报告.html", "HTML (*.html)")
            if fn:
                html_body = viewer.toHtml()
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(html_body)
                QMessageBox.information(dlg, "已保存", fn)

        btn_save_md.clicked.connect(do_save_md)
        btn_save_html.clicked.connect(do_save_html)
        dlg.exec_()

    # ───── Phase C-1:差异化说明弹窗 ─────
    def _on_pangu_diff_info(self):
        # 显示当前差异化状态 + 预览下一章会用什么参数
        try:
            from pangu_system import get_default_engine as _pg
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        enabled = (getattr(self.tab_settings, "pangu_check", None)
                   and self.tab_settings.pangu_check.isChecked())
        next_ch = len(self.chapters) + 1
        engine = _pg()
        recent = [c.get("content", "") for c in self.chapters[-3:]] if self.chapters else []
        preview = engine.build_seed_variation_block(next_ch, recent)
        jitter = engine.get_word_count_jitter(next_ch)
        status = "✅ 已启用" if enabled else "⊘ 已停用(盘古总开关关闭)"
        msg = (
            f"章节差异化:{status}\n\n"
            "原理:每章用不同的 RNG 种子,锁定到不同的开篇/节奏/感官组合,\n"
            "防止 AI 反复用同一套套路写章节。\n\n"
            f"下一章(第 {next_ch} 章)预览参数:\n{preview}\n\n"
            f"字数浮动:×{jitter:.2f}"
        )
        QMessageBox.information(self, "🎲 章节差异化(防套路)", msg)

    # ───── Phase C-3:盘古 ↔ lifespan_loops 联动 ─────
    def _install_pangu_lifespan_bridge(self):
        # 在 workflow post_write 加一个低优先级步骤:
        # 寿元/伏笔 audit 完后,自动跑盘古词扫,有问题就在日志提示用户做 30 项质检
        if not (getattr(self, "workflow", None) and self.workflow):
            return
        if not getattr(self.workflow, "_registry", None):
            return
        try:
            from workflow_pipeline import PipelineStep
        except ImportError:
            return

        mw = self

        class _PanguLifespanBridgeStep(PipelineStep):
            name = "pangu_lifespan_bridge"

            @property
            def enabled(self_step):
                pangu_on = (getattr(mw.tab_settings, "pangu_check", None)
                            and mw.tab_settings.pangu_check.isChecked())
                lifespan_on = bool(getattr(mw, "lifespan_ledger", {}).get("enabled"))
                return pangu_on and lifespan_on

            def run(self_step, ctx, done):
                content = getattr(ctx, "content", "")
                if not content:
                    done()
                    return
                try:
                    from pangu_system import get_default_engine
                    e = get_default_engine()
                    r = e.quick_chapter_lint(content)
                    if not r.get("pass") and hasattr(mw, "tab_generation"):
                        score = r.get("score", 0)
                        issues_cnt = len(r.get("issues", []))
                        level = "warn" if score < 70 else "info"
                        mw.tab_generation.log(
                            f"🌀 盘古-lifespan 联动:本章盘古词扫 {score}/100 ({issues_cnt} 处问题)。"
                            f"建议在章节编辑器点 📊 30项质检 做深度审稿。",
                            level
                        )
                except Exception:
                    pass
                done()

        self.workflow._registry.register(
            "post_write", _PanguLifespanBridgeStep(),
            priority=45  # 在 lifespan audit (35) / open_loops (40) 之后
        )

    # ───── Phase C-2:盘古风格库可视化编辑器 ─────
    def _on_pangu_style_editor(self):
        try:
            from pangu_system import STYLE_MAPPING, PanguEngine
        except ImportError:
            QMessageBox.warning(self, "缺少盘古", "找不到 pangu_system.py")
            return
        from PyQt5.QtCore import QSettings as _QS
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        _s = _QS("NovelAI", "PanguStyleLib")

        dlg = QDialog(self)
        dlg.setWindowTitle("🎨 盘古风格库编辑器")
        dlg.resize(1200, 700)
        lay = QVBoxLayout(dlg)
        info = QLabel(
            "在此编辑/添加/删除风格映射规则。每行一组:\n"
            "  · 关键词(用 | 分隔)\n"
            "  · 主风格 / 辅风格 / 点缀风格\n"
            "  · 女角色基调 / 适合平台\n"
            "保存后会持久化到本机,覆盖内置规则。点【恢复内置】可还原。"
        )
        info.setStyleSheet("color:#666;padding:6px;background:#f5f5f5;border-radius:4px;")
        lay.addWidget(info)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["关键词(|分隔)", "主风格", "辅风格", "点缀", "女基调 / 平台"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        saved = _s.value("custom_mapping", None)
        if saved and isinstance(saved, list) and saved:
            rules = saved
        else:
            rules = [dict(r) for r in STYLE_MAPPING]

        def load_table(rs):
            table.setRowCount(len(rs))
            for i, r in enumerate(rs):
                table.setItem(i, 0, QTableWidgetItem(r.get("kw", "")))
                table.setItem(i, 1, QTableWidgetItem(r.get("main", "")))
                table.setItem(i, 2, QTableWidgetItem(r.get("sub", "")))
                table.setItem(i, 3, QTableWidgetItem(r.get("accent", "")))
                table.setItem(i, 4, QTableWidgetItem(
                    f"{r.get('female', '')} / {r.get('platform', '')}"))

        load_table(rules)
        lay.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ 添加")
        btn_del = QPushButton("🗑️ 删除选中")
        btn_save = QPushButton("💾 保存(覆盖内置)")
        btn_save.setStyleSheet("background:#16a085;color:white;padding:6px 14px;border-radius:3px;")
        btn_reset = QPushButton("🔄 恢复内置")
        btn_export = QPushButton("📤 导出")
        btn_close = QPushButton("关闭")
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        btn_row.addWidget(btn_export)
        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        def do_add():
            r = table.rowCount()
            table.insertRow(r)
            for col in range(5):
                table.setItem(r, col, QTableWidgetItem(""))

        def do_del():
            rows = sorted({i.row() for i in table.selectedIndexes()}, reverse=True)
            for r in rows:
                table.removeRow(r)

        def serialize_table():
            out = []
            for i in range(table.rowCount()):
                kw = table.item(i, 0).text().strip() if table.item(i, 0) else ""
                if not kw:
                    continue
                main = table.item(i, 1).text().strip() if table.item(i, 1) else ""
                sub = table.item(i, 2).text().strip() if table.item(i, 2) else ""
                accent = table.item(i, 3).text().strip() if table.item(i, 3) else ""
                fp = table.item(i, 4).text().strip() if table.item(i, 4) else ""
                if "/" in fp:
                    female, platform = [s.strip() for s in fp.split("/", 1)]
                else:
                    female, platform = fp, ""
                out.append({
                    "kw": kw, "main": main, "sub": sub,
                    "accent": accent, "female": female, "platform": platform,
                })
            return out

        def do_save():
            data = serialize_table()
            if not data:
                QMessageBox.warning(dlg, "保存失败", "至少需要 1 条规则")
                return
            _s.setValue("custom_mapping", data)
            from pangu_system import STYLE_MAPPING as _SM
            _SM.clear()
            _SM.extend(data)
            QMessageBox.information(dlg, "已保存",
                f"已保存 {len(data)} 条规则到本机,并立即生效。\n下次启动会自动加载。")

        def do_reset():
            if QMessageBox.question(
                dlg, "确认", "恢复成内置规则?会丢失你的自定义编辑。"
            ) != QMessageBox.Yes:
                return
            _s.remove("custom_mapping")
            import importlib
            import pangu_system as _ps
            importlib.reload(_ps)
            load_table(list(_ps.STYLE_MAPPING))

        def do_export():
            data = serialize_table()
            fn, _ = QFileDialog.getSaveFileName(
                dlg, "导出风格库", "盘古风格库.json", "JSON (*.json)")
            if fn:
                import json as _json
                Path(fn).write_text(_json.dumps(data, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
                QMessageBox.information(dlg, "已导出", fn)

        btn_add.clicked.connect(do_add)
        btn_del.clicked.connect(do_del)
        btn_save.clicked.connect(do_save)
        btn_reset.clicked.connect(do_reset)
        btn_export.clicked.connect(do_export)
        btn_close.clicked.connect(dlg.reject)
        dlg.exec_()


    def _charlib_extract_from_chapters(self):
        """从已写章节用 AI 一键提取角色/关系/物品/事件/伏笔"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "尚未生成任何章节,无法提取")
            return
        if not self.worker.is_ready():
            self.tabs.setCurrentWidget(self.tab_generation)
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』,完成 AI 网站登录后再提取。")
            return
        # 让用户选范围
        from PyQt5.QtWidgets import QInputDialog
        max_ch = len(self.chapters)
        text, ok = QInputDialog.getText(
            self, "提取范围",
            f"请输入要提取的章节范围(共 {max_ch} 章)\n"
            f"格式:'all' 或 '1-5' 或 '3' (单章)\n"
            f"建议:每次 3-5 章一批,避免提示词过长",
            text=f"1-{min(5, max_ch)}")
        if not ok or not text.strip():
            return
        # 解析范围
        nums = []
        try:
            t = text.strip().lower()
            if t == "all":
                nums = list(range(1, max_ch + 1))
            elif "-" in t:
                a, b = t.split("-")
                nums = list(range(int(a), int(b) + 1))
            else:
                nums = [int(t)]
        except Exception:
            QMessageBox.warning(self, "格式错误", "请按照 '1-5' 或 '3' 格式输入")
            return
        nums = [n for n in nums if 1 <= n <= max_ch]
        if not nums:
            return

        self._charlib_batch_queue = nums
        self.tab_generation.log(
            f"▶ 开始批量提取角色库,共 {len(nums)} 章: {nums}", "info")
        self._run_next_charlib_extract()

    def _run_next_charlib_extract(self):
        """处理 charlib 提取队列里下一个章节"""
        queue = getattr(self, "_charlib_batch_queue", None)
        if not queue:
            self.tab_generation.log("✅ 角色库批量提取完成", "success")
            # 如果是 _post_chapter_chain 触发的,推进链
            if getattr(self, "_charlib_chain_post", False):
                self._charlib_chain_post = False
                QTimer.singleShot(500, self._run_next_post_chapter_step)
            else:
                self.tabs.setCurrentWidget(self.tab_charlib)
            return
        ch_num = queue.pop(0)
        ch = self.chapters[ch_num - 1]
        content = ch.get("content", "")
        if not content.strip():
            QTimer.singleShot(100, self._run_next_charlib_extract)
            return
        # 现有数据摘要(避免重复提取)
        existing = self.tab_charlib.serialize()
        existing_brief = json.dumps({
            "characters": [r[0] for r in existing.get("characters", []) if r[0]],
            "items":      [r[0] for r in existing.get("items", []) if r[0]],
        }, ensure_ascii=False)[:600]

        prompt = PROMPTS["world_extract"].format(
            ch_num=ch_num,
            existing=existing_brief,
            content=content[:5000],
        )
        self._send_to_ai(
            prompt,
            f"提取角色库-第{ch_num}章",
            target="world_extract",
            ch_num=ch_num,
        )

    def _on_world_extract_received(self, content, ch_num):
        """world_extract 回调:解析 JSON 并合并到 charlib"""
        if not content.strip():
            self.tab_generation.log(f"第{ch_num}章提取为空", "warn")
            QTimer.singleShot(500, self._run_next_charlib_extract)
            return
        # 容错:抠出 JSON 部分(去掉可能的 markdown 包裹)
        text = content.strip()
        if "```" in text:
            import re as _re
            m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.S)
            if m:
                text = m.group(1)
        # 找第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end+1]
        try:
            data = json.loads(text)
        except Exception as e:
            self.tab_generation.log(f"第{ch_num}章 JSON 解析失败: {e}", "warn")
            self.tab_generation.log(f"  原始内容前 200字: {content[:200]}", "warn")
            QTimer.singleShot(500, self._run_next_charlib_extract)
            return

        added = self._merge_into_charlib(data)
        self.tab_generation.log(
            f"✓ 第{ch_num}章提取完成: 角色+{added['ch']} 关系+{added['rel']} "
            f"物品+{added['it']} 事件+{added['ev']} 伏笔+{added['fo']}",
            "success")
        # 触发下一章
        QTimer.singleShot(800, self._run_next_charlib_extract)

    def _merge_into_charlib(self, data):
        """把提取的数据合并进 charlib UI 表格(去重)"""
        from PyQt5.QtWidgets import QTableWidgetItem
        cl = self.tab_charlib
        added = {"ch": 0, "rel": 0, "it": 0, "ev": 0, "fo": 0}

        def existing_names(tbl, col=0):
            return set((tbl.item(r, col).text() if tbl.item(r, col) else "")
                       for r in range(tbl.rowCount()))

        # 角色
        ex_chars = existing_names(cl.tbl_chars)
        for c in (data.get("characters") or []):
            name = c.get("name", "").strip()
            if not name or name in ex_chars:
                continue
            row = cl.tbl_chars.rowCount()
            cl.tbl_chars.insertRow(row)
            vals = [
                name, c.get("role", "配角"), c.get("appearance", ""),
                c.get("personality", ""), c.get("mark", ""),
                c.get("ability", ""), c.get("state", ""),
                str(c.get("first_ch", "")),
            ]
            for col, v in enumerate(vals):
                cl.tbl_chars.setItem(row, col, QTableWidgetItem(str(v)))
            added["ch"] += 1
            ex_chars.add(name)

        # 关系(去重 key=a+type+b)
        ex_rels = set()
        for r in range(cl.tbl_relations.rowCount()):
            a = cl.tbl_relations.item(r, 0).text() if cl.tbl_relations.item(r, 0) else ""
            t = cl.tbl_relations.item(r, 1).text() if cl.tbl_relations.item(r, 1) else ""
            b = cl.tbl_relations.item(r, 2).text() if cl.tbl_relations.item(r, 2) else ""
            ex_rels.add(f"{a}|{t}|{b}")
        for rel in (data.get("relations") or []):
            a = rel.get("a", "").strip()
            t = rel.get("type", "").strip()
            b = rel.get("b", "").strip()
            if not (a and t and b):
                continue
            k = f"{a}|{t}|{b}"
            if k in ex_rels:
                continue
            row = cl.tbl_relations.rowCount()
            cl.tbl_relations.insertRow(row)
            for col, v in enumerate([a, t, b, rel.get("note", "")]):
                cl.tbl_relations.setItem(row, col, QTableWidgetItem(v))
            added["rel"] += 1
            ex_rels.add(k)

        # 物品
        ex_items = existing_names(cl.tbl_items)
        for it in (data.get("items") or []):
            name = it.get("name", "").strip()
            if not name or name in ex_items:
                continue
            row = cl.tbl_items.rowCount()
            cl.tbl_items.insertRow(row)
            vals = [name, it.get("type", "法器"), it.get("owner", ""),
                    str(it.get("source_ch", "")), it.get("ability", "")]
            for col, v in enumerate(vals):
                cl.tbl_items.setItem(row, col, QTableWidgetItem(str(v)))
            added["it"] += 1
            ex_items.add(name)

        # 事件
        ex_evs = set()
        for r in range(cl.tbl_timeline.rowCount()):
            ch = cl.tbl_timeline.item(r, 0).text() if cl.tbl_timeline.item(r, 0) else ""
            ev = cl.tbl_timeline.item(r, 1).text() if cl.tbl_timeline.item(r, 1) else ""
            ex_evs.add(f"{ch}|{ev[:20]}")
        for ev in (data.get("events") or []):
            ch = str(ev.get("ch", ""))
            evt = ev.get("event", "").strip()
            if not evt:
                continue
            k = f"{ch}|{evt[:20]}"
            if k in ex_evs:
                continue
            row = cl.tbl_timeline.rowCount()
            cl.tbl_timeline.insertRow(row)
            for col, v in enumerate([ch, evt, ev.get("state_change", "")]):
                cl.tbl_timeline.setItem(row, col, QTableWidgetItem(v))
            added["ev"] += 1
            ex_evs.add(k)

        # 伏笔
        ex_fos = set()
        for r in range(cl.tbl_fore.rowCount()):
            ch = cl.tbl_fore.item(r, 0).text() if cl.tbl_fore.item(r, 0) else ""
            ct = cl.tbl_fore.item(r, 1).text() if cl.tbl_fore.item(r, 1) else ""
            ex_fos.add(f"{ch}|{ct[:30]}")
        for fo in (data.get("foreshadows") or []):
            ch = str(fo.get("ch", ""))
            ct = fo.get("content", "").strip()
            if not ct:
                continue
            k = f"{ch}|{ct[:30]}"
            if k in ex_fos:
                continue
            row = cl.tbl_fore.rowCount()
            cl.tbl_fore.insertRow(row)
            vals = [ch, ct, str(fo.get("plan_pay_at", "0")), "否", ""]
            for col, v in enumerate(vals):
                cl.tbl_fore.setItem(row, col, QTableWidgetItem(v))
            added["fo"] += 1
            ex_fos.add(k)

        return added

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
        """从生成内容里尝试提取章节标题
        支持格式:
          第 1 章 觉醒之夜
          第一章 觉醒之夜
          第1章：觉醒之夜
          【第 1 章】觉醒之夜
        """
        for line in content.splitlines()[:5]:
            line = line.strip()
            if not line:
                continue
            # 匹配各种章节标题格式
            m = re.match(
                r'^[【\[]?\s*第\s*[一二三四五六七八九十百千零\d]+\s*章[】\]]?\s*[：:、\s]*\s*(.*)$',
                line
            )
            if m:
                # 整行作为完整标题(包含"第N章 xxx")
                # 限制长度,避免把正文也算进来
                if len(line) <= 50:
                    return line
                # 太长说明是正文,不是标题
                continue
        return None

    def _strip_chapter_title(self, content):
        """如果首行是章节标题就移除 + 最终防线剥离任何残留元信息"""
        # ── 最终防线:强制再 strip 一次元信息(双保险,不管上游有没有剥过)
        try:
            from pangu_system import strip_chapter_meta
            content = strip_chapter_meta(content)
        except Exception:
            pass

        lines = content.splitlines()
        if not lines:
            return content
        first = lines[0].strip()
        if re.match(r'^[【\[]?\s*第\s*[一二三四五六七八九十百千零\d]+\s*章', first) and len(first) <= 50:
            # 移除标题行 + 可能的空行
            i = 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            return "\n".join(lines[i:])
        return content

    def _check_foreshadow_alert(self, ch_num):
        """检查即将到期的伏笔,如有则弹窗提醒"""
        if not hasattr(self, "tab_charlib"):
            return
        cl = self.tab_charlib
        urgent = []  # 0~3章后该回收
        overdue = []  # 已超期
        for r in range(cl.tbl_fore.rowCount()):
            ch_set = cl.tbl_fore.item(r, 0).text() if cl.tbl_fore.item(r, 0) else "0"
            content = cl.tbl_fore.item(r, 1).text() if cl.tbl_fore.item(r, 1) else ""
            ch_pay = cl.tbl_fore.item(r, 2).text() if cl.tbl_fore.item(r, 2) else "0"
            paid = cl.tbl_fore.item(r, 3).text() if cl.tbl_fore.item(r, 3) else "否"
            if paid == "是" or not content:
                continue
            try:
                ch_pay_int = int(ch_pay)
            except ValueError:
                continue
            distance = ch_pay_int - ch_num
            if distance < 0:
                overdue.append((ch_set, content, ch_pay, abs(distance)))
            elif distance <= 3:
                urgent.append((ch_set, content, ch_pay, distance))
        if not urgent and not overdue:
            return
        # 弹窗
        msg_lines = [f"🔔 第 {ch_num} 章生成前伏笔提醒:\n"]
        if overdue:
            msg_lines.append(f"⚠️ 已超期未回收的伏笔 ({len(overdue)} 个):")
            for cs, ct, cp, d in overdue[:5]:
                msg_lines.append(f"  · 第{cs}章埋: {ct[:50]}")
                msg_lines.append(f"    应在第{cp}章回收,已超 {d} 章")
        if urgent:
            msg_lines.append(f"\n🎯 即将回收的伏笔 ({len(urgent)} 个):")
            for cs, ct, cp, d in urgent[:5]:
                flag = "本章可回收!" if d == 0 else f"还有 {d} 章"
                msg_lines.append(f"  · 第{cs}章埋: {ct[:50]} [{flag}]")
        msg_lines.append("\n是否继续生成? (这些信息已自动注入到提示词中提醒AI)")
        ret = QMessageBox.question(
            self, "伏笔提醒", "\n".join(msg_lines),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret == QMessageBox.No:
            self._batch_paused = True
            self._batch_remaining = 0
            self.tab_generation.log("用户取消,批量生成已停止", "warn")

    def _send_next_chapter(self):
        """批量生成里发下一章(自动注入对话记忆+伏笔提醒)"""
        if self._batch_paused or self._batch_remaining <= 0:
            # 批量结束,清 silent 标记(下次单章生成或重启批量恢复正常)
            if getattr(self, "_batch_silent", False):
                self._batch_silent = False
            return
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        ch_num = len(self.chapters) + 1

        # ★ 伏笔到期提醒(只在第1章和达到回收期的章节弹一次,且仅手动模式)
        if hasattr(self, "tab_charlib") and not getattr(self, "_batch_silent", False):
            self._check_foreshadow_alert(ch_num)

        outline = (self.tab_outline.worldview_edit.toPlainText() + "\n"
                   + self.tab_outline.structure_edit.toPlainText())[:1500]
        target = self.tab_settings.get_words_per_chapter()
        offset = self.tab_settings.get_prompt_offset()
        target_with_offset = max(500, target + offset)
        # Phase C-1:盘古章节差异化(随盘古总开关启用)
        _diff_block = ""
        try:
            if (getattr(self.tab_settings, "pangu_check", None)
                    and self.tab_settings.pangu_check.isChecked()):
                from pangu_system import get_default_engine as _pg_get
                _recent = [c.get("content", "") for c in self.chapters[-3:]] if self.chapters else []
                _diff_block = _pg_get().build_seed_variation_block(ch_num, _recent)
                # 字数浮动 ±10%(章节确定性,同章重试拿同样结果)
                _jitter = _pg_get().get_word_count_jitter(ch_num)
                target_with_offset = max(500, int(target_with_offset * _jitter))
        except Exception:
            pass
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
        if _diff_block:
            prompt += f"\n\n{_diff_block}"

        # BUG-014:如果用户在上一章元信息面板点了"下一章选项",
        # 把它作为本章开局指引注入(prompt 末尾,优先级高)
        picked_opt = getattr(self, "_user_picked_next_option", None)
        if picked_opt:
            prompt += (
                f"\n\n【本章开局指引(用户从上一章【下一章选项】中指定)】\n"
                f"本章必须从以下情境展开:{picked_opt}\n"
                f"严格按这条线索写,不要换到其他选项。"
            )
            self.tab_generation.log(
                f"已注入用户指定的下章开局:{picked_opt[:30]}...", "info")
            # 用完即清,避免影响后续章节
            self._user_picked_next_option = None
        else:
            # 用户没点选项 → 自动用上一章的元信息引导
            # (钩子 / 待解决悬念 / 备选下一章方向)
            if self.chapters and len(self.chapters) >= 1:
                prev_ch = self.chapters[-1]
                hook = prev_ch.get("hook") or {}
                cool = prev_ch.get("cool_points") or []
                opts = prev_ch.get("next_options") or []
                bridge_lines = []
                if hook and hook.get("content"):
                    htype = hook.get("type", "")
                    bridge_lines.append(
                        f"上一章悬念(类型:{htype}):{hook['content']}")
                if opts:
                    bridge_lines.append(
                        f"上一章列出的可能走向(任选其一展开,或合并几条):\n  "
                        + "\n  ".join(f"- {o}" for o in opts[:5]))
                if cool:
                    bridge_lines.append(
                        f"上一章已用爽点(避免重复):{', '.join(c[:30] for c in cool[:3])}")
                if bridge_lines:
                    prompt += (
                        "\n\n【本章承接(自动从上一章元信息提取)】\n"
                        + "\n".join(bridge_lines)
                        + "\n要求:本章开篇直接承接上面的悬念,把它推进到下一个高潮。"
                    )
                    self.tab_generation.log(
                        f"已自动注入上一章承接信息({len(bridge_lines)} 条)",
                        "info")

                # 防重复:扫最近 3 章钩子类型 + 爽点类型,如有连用同种,提示 AI 换花样
                recent_3 = self.chapters[-3:]
                hook_types = [
                    (c.get("hook") or {}).get("type", "")
                    for c in recent_3
                    if c.get("hook")
                ]
                cool_types = []
                for c in recent_3:
                    for cp in (c.get("cool_points") or []):
                        # 取 "类型:内容" 的类型部分
                        m = re.match(r'^\s*([^::]{1,8})\s*[::]', cp)
                        if m:
                            cool_types.append(m.group(1).strip())
                # 找连用同种(2 次及以上)
                from collections import Counter
                hook_cnt = Counter(hook_types)
                cool_cnt = Counter(cool_types)
                avoid_lines = []
                for t, n in hook_cnt.items():
                    if t and n >= 2:
                        avoid_lines.append(
                            f"- 钩子类型【{t}】最近{n}章已用,本章换其他类型"
                            f"(对话没说完/人物出现/秘密暴露/倒计时/关键动作)")
                for t, n in cool_cnt.items():
                    if t and n >= 2:
                        avoid_lines.append(
                            f"- 爽点类型【{t}】最近{n}章已用,本章换其他类型"
                            f"(打脸/反转/碾压/揭秘/救场/装逼/复仇)")
                if avoid_lines:
                    prompt += (
                        "\n\n【避免审美疲劳(最近章节统计)】\n"
                        + "\n".join(avoid_lines))
                    self.tab_generation.log(
                        f"已注入防重复提示({len(avoid_lines)} 条):避免连用同类型钩子/爽点",
                        "info")

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

            # ★ 角色库 + 关系 + 时间线 + 物品 + 伏笔 一键注入
            if hasattr(self, "tab_charlib"):
                charlib_block = self.tab_charlib.build_inject_block(current_chapter=ch_num)
                if charlib_block:
                    prompt += charlib_block
                    self.tab_generation.log(
                        f"已注入角色与世界状态({len(charlib_block)} 字符)到第 {ch_num} 章提示词", "info")

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
        """处理 Canon 抽取 AI 回复
        既写 Canon Tab(单值条目),也按前缀分发到 🎭 角色与世界 6 库"""
        ch_num = meta.get("ch_num", 0)
        try:
            text = self._extract_json_blob(content)
            arr = json.loads(text)
            count = 0
            # 用于按前缀分发到 charlib 的结构化 dict
            charlib_data = {
                "characters": [],
                "relations": [],
                "items": [],
                "events": [],   # 时间线
                "foreshadows": [],
            }
            # 角色聚合:同一角色多字段合并到一行
            chars_acc = {}      # name -> {role, appearance, personality, ability, state, first_ch}
            items_acc = {}      # name -> {owner, source, status, ability}

            for it in arr:
                key = it.get("key", "").strip()
                value = it.get("value", "").strip()
                mode = it.get("mode", "evolving")
                ch = it.get("ch", ch_num)
                if not key or not value:
                    continue

                # 1) 写 Canon Tab (保留全字段路径,任意 key 都能录)
                self.tab_canon.add_item(
                    key, value, mode=mode,
                    severity="high" if mode == "locked" else "mid",
                    ch=ch)
                count += 1

                # 2) 按前缀分发到 charlib 的结构化 dict
                #    格式: <类别>.<主键>.<字段>  (例如 角色.林远.身份)
                parts = key.split(".", 2)  # 最多分 3 段
                if len(parts) < 2:
                    continue
                category = parts[0]
                main_key = parts[1] if len(parts) >= 2 else ""
                field = parts[2] if len(parts) >= 3 else "info"

                if category == "角色":
                    if main_key not in chars_acc:
                        chars_acc[main_key] = {"name": main_key, "first_ch": ch}
                    # 字段映射到 charlib 8 列
                    fmap = {
                        "身份": "role", "角色": "role",
                        "外貌": "appearance", "样貌": "appearance",
                        "性格": "personality", "人设": "personality",
                        "标志": "mark", "标记": "mark", "独有称号": "mark",
                        "能力": "ability", "技能": "ability", "战力": "ability",
                        "状态": "state", "当前状态": "state",
                    }
                    col_key = fmap.get(field, "personality")  # 未知字段塞 personality
                    # 合并 value(同字段多次提取 → 用 / 拼接)
                    cur = chars_acc[main_key].get(col_key, "")
                    chars_acc[main_key][col_key] = (cur + " / " + value) if cur else value
                elif category == "关系":
                    # main_key = "X-Y" 或 "X与Y"
                    m = re.match(r'^(.+?)\s*[-与]\s*(.+)$', main_key)
                    if m:
                        a, b = m.group(1).strip(), m.group(2).strip()
                        charlib_data["relations"].append({
                            "a": a, "type": field, "b": b, "note": value,
                        })
                elif category == "时间线":
                    # main_key = 第N章 (或 三年前 / 十八岁 等),作为时间锚
                    charlib_data["events"].append({
                        "time": main_key, "event": value, "ch": ch,
                    })
                elif category == "物品":
                    if main_key not in items_acc:
                        items_acc[main_key] = {"name": main_key}
                    fmap_it = {
                        "持有人": "owner", "拥有者": "owner",
                        "来源": "source",
                        "状态": "status", "当前状态": "status",
                        "能力": "ability", "效果": "ability", "功效": "ability",
                    }
                    col_key = fmap_it.get(field, "source")
                    cur = items_acc[main_key].get(col_key, "")
                    items_acc[main_key][col_key] = (cur + " / " + value) if cur else value
                elif category == "战力":
                    # 战力体系归到角色 ability 或单独物品行(看用户偏好)
                    # 这里塞到 items_acc 以"<体系名>"作 name,字段 ability 存所有细节
                    if main_key not in items_acc:
                        items_acc[main_key] = {"name": main_key, "source": "(战力体系)"}
                    cur = items_acc[main_key].get("ability", "")
                    items_acc[main_key]["ability"] = \
                        (cur + " / " + f"{field}:{value}") if cur else f"{field}:{value}"
                elif category == "伏笔":
                    charlib_data["foreshadows"].append({
                        "content": main_key + ("|" + value if main_key != value else ""),
                        "ch": ch,
                        "plan_pay_at": 0,
                    })

            # 合并累积的 chars / items
            charlib_data["characters"] = list(chars_acc.values())
            charlib_data["items"] = list(items_acc.values())

            # 同步到 🎭 角色与世界
            added = {}
            try:
                added = self._merge_into_charlib(charlib_data)
            except Exception as _me:
                self.tab_generation.log(f"同步 6 库失败:{_me}", "warn")

            self.tab_generation.log(
                f"✓ Canon 抽取完成:Canon Tab +{count} 条 / "
                f"🎭 角色与世界 角色+{added.get('ch',0)} 关系+{added.get('rel',0)} "
                f"物品+{added.get('it',0)} 时间线+{added.get('ev',0)} 伏笔+{added.get('fo',0)}",
                "success")
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

        # 3. 禁用词扫描(高严重度 → 直接触发死磕重写)
        # 阈值:总命中次数 >5 或 单词命中 >2 都算违反
        try:
            from pangu_system import PanguEngine as _PE
            hits = _PE.detect_forbidden_words(content)
            total_count = sum(c for _, c in hits)
            heavy_words = [(w, c) for w, c in hits if c >= 2]
            if total_count > 5 or heavy_words:
                top_str = ", ".join(f"{w}×{c}" for w, c in hits[:8])
                issues.append(
                    f"禁用词违规(累计 {total_count} 次,触发铁律):{top_str}。"
                    f"必须全部删除或换说法,这是盘古铁律第 15 条"
                )
        except Exception:
            pass

        # 4. 盘古综合评分门(分数低于阈值 → 死磕)
        try:
            threshold = self.tab_generation.quality_threshold.value()
            if threshold > 0:
                from pangu_system import get_default_engine
                eng = get_default_engine()
                lint = eng.quick_chapter_lint(content)
                score = lint.get("score", 0)
                # 存到 meta 供日志输出 — 通过 issues 末尾的特殊标记携带
                if score < threshold:
                    score_issues = lint.get("issues", [])
                    issues.append(
                        f"评分不达标:盘古综合评分 {score}/100 < 阈值 {threshold}。"
                        f"主要问题: {'; '.join(score_issues[:3]) if score_issues else '段落/句式/禁用词复合问题'}。"
                        f"分数到 {threshold} 才放行"
                    )
                else:
                    # 达标也打个肯定日志(让用户看到)
                    self.tab_generation.log(
                        f"  · 盘古评分 {score}/100 ≥ 阈值 {threshold} ✓", "info")
        except Exception as _se:
            self.tab_generation.log(f"评分门跑失败(忽略):{_se}", "warn")

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
        # 如果违规里有禁用词,加超强力指令
        has_forbidden = any("禁用词违规" in r for r in reasons)
        forbidden_extra = ""
        if has_forbidden:
            forbidden_extra = (
                "\n\n🚨【最高优先级:禁用词清零】🚨\n"
                "上次本章用了禁用词,这是盘古铁律不可违反的死规。\n"
                "重写本章时,每写一句都问自己:这句有禁用词吗?\n"
                "替换策略:\n"
                "- 副词类(顿时/连忙/显然/似乎/可能/几乎...)→ 直接删除,不加任何替代\n"
                "- 心理动词(知道/觉得/想/认为)→ 换成具体动作或对话\n"
                "  错例:他知道这不对   正例:他咬了咬牙\n"
                "  错例:她觉得很冷    正例:她搓了搓手臂,起了一层鸡皮疙瘩\n"
                "- 套话(嘴角勾起/眼中闪过/心下了然)→ 整句重写\n"
                "- 比喻词(仿佛/如同/像)→ 改成直接断言\n"
                "  错例:他仿佛被雷劈了    正例:他僵在原地\n"
                "重写完后自查一遍,如果还有任何禁用词,继续删继续换,直到清零。\n"
            )

        stronger = (meta.get("original_prompt", "")
                    + "\n\n【上次问题清单(必须修正)】\n" + reason_block
                    + forbidden_extra
                    + "\n\n请重写本章,严格规避以上所有问题。")
        self._pending_task_target = new_meta
        self.tab_generation.log(
            f"⚠ 章节质量未达标 ({len(reasons)} 个问题),死磕重写中... "
            f"(本次第 {meta.get('retry_count_used', 0) + 1} 轮,上限 {meta.get('retry_left', retry)} 次)",
            "warn")
        for r in reasons:
            self.tab_generation.log(f"  · {r}", "warn")
        # 重试时也走附件模式(镜像站审核严,文本会被拒绝)
        # _clear_existing_attachments 会自动清掉旧附件,不会堆积
        self.worker.submit({
            "action": "send_prompt",
            "prompt": stronger,
            "task_id": meta.get("label", "章节"),
            "url": self.tab_generation.url_input.text().strip(),
            "type_delay_ms": 5,
            "allow_attachment": True,  # 镜像站需要附件绕审核
        })

    def _accept_chapter_and_continue(self, content, meta):
        """章节通过校验或死磕用尽 → 入库并触发后续链"""
        if meta.get("target") == "golden_three":
            self._split_and_save_golden_three(content)
            last_ch_num = len(self.chapters)
        else:
            ch_num = meta.get("ch_num", len(self.chapters) + 1)
            # ── 解析并剥离盘古章节尾部元信息(【断章钩子】【本章爽点】
            #     【伏笔状态】【下一章选项】),只把正文写入 chapter['content']
            pangu_meta = None
            body_clean = content
            try:
                from pangu_system import parse_chapter_meta as _pangu_parse
                pangu_meta = _pangu_parse(content)
                body_clean = pangu_meta.get("body") or content
                # 诊断日志:让用户能看到是否真的剥离了元信息
                _stripped = len(content) - len(body_clean)
                if _stripped > 0:
                    self.tab_generation.log(
                        f"✓ 已剥离章节尾部元信息 {_stripped} 字 → 切到【章节编辑器】Tab,"
                        f"字数下方📌米色面板可看钩子/爽点/伏笔/下一章选项",
                        "info")
                elif "本章完" in content or "【断章钩子】" in content \
                        or "断章钩子" in content or "下一章选项" in content:
                    # 元信息标记还在正文里 → 剥离失败,打 warn
                    self.tab_generation.log(
                        "⚠️ 检测到元信息标记但剥离失败(parse_chapter_meta 没匹配)。"
                        "请把这段章节末尾 30 行复制发给开发者,以便加新匹配规则",
                        "warn")
            except ImportError:
                pass
            except Exception as _pm_e:
                self.tab_generation.log(f"盘古元信息解析失败(降级保留原文):{_pm_e}", "warn")

            ch_title = self._extract_chapter_title(body_clean) or f"第{ch_num}章"
            ch_body = self._strip_chapter_title(body_clean)
            chapter = {"title": ch_title, "content": ch_body, "summary": ""}

            # ── 元信息存进 chapter dict,供 UI/工作流后续用
            if pangu_meta:
                if pangu_meta.get("hook"):
                    chapter["hook"] = pangu_meta["hook"]
                if pangu_meta.get("cool_points"):
                    chapter["cool_points"] = pangu_meta["cool_points"]
                if pangu_meta.get("next_options"):
                    chapter["next_options"] = pangu_meta["next_options"]
                # 伏笔摘要(给 GUI 用,方便看"埋 X 收 Y";真正入库走 _sync 函数)
                _sp = len(pangu_meta.get("seeds_planted", []))
                _pd = len(pangu_meta.get("seeds_paid", []))
                if _sp or _pd:
                    parts = []
                    if _sp: parts.append(f"埋雷 {_sp} 条")
                    if _pd: parts.append(f"收雷 {_pd} 条")
                    chapter["_pangu_seeds_summary"] = " / ".join(parts)

            self.chapters.append(chapter)

            # ── 把【伏笔状态】同步到 lifespan_loops 伏笔库
            if pangu_meta:
                self._sync_pangu_seeds_to_lifespan(pangu_meta, ch_num)
                # ── 钩子 + 爽点 自动写入 🎭 角色与世界 → 🎣 钩子编年 / 🎯 爽点编年
                self._sync_hook_and_cool_to_charlib(pangu_meta, ch_num)

            self._refresh_chapter_list()
            if self.tab_generation.auto_save.isChecked():
                self._save_chapter_to_disk(self.chapters[-1])
            actual = len(re.sub(r'\s', '', ch_body))
            self.tab_generation.log(
                f"✓ 第 {ch_num} 章生成成功!字数:{actual} 字", "success")
            if pangu_meta and (pangu_meta.get("hook") or pangu_meta.get("cool_points")
                               or pangu_meta.get("seeds_planted") or pangu_meta.get("next_options")):
                bits = []
                if pangu_meta.get("hook"):          bits.append("钩子")
                if pangu_meta.get("cool_points"):   bits.append(f"爽点×{len(pangu_meta['cool_points'])}")
                if pangu_meta.get("seeds_planted"): bits.append(f"埋雷×{len(pangu_meta['seeds_planted'])}")
                if pangu_meta.get("seeds_paid"):    bits.append(f"收雷×{len(pangu_meta['seeds_paid'])}")
                if pangu_meta.get("next_options"):  bits.append(f"下章选项×{len(pangu_meta['next_options'])}")
                self.tab_generation.log("  · 盘古元信息已剥离并归档:" + " / ".join(bits), "info")
            last_ch_num = ch_num

        self._batch_remaining -= 1

        # 后置链:Canon 抽取 → 摘要 → after_chapter 技能 → 下一章
        # (用 QTimer 错开,避免一窝蜂砸到 worker)
        self._post_chapter_chain(last_ch_num)

    def _sync_hook_and_cool_to_charlib(self, pangu_meta: dict, ch_num: int):
        """把【断章钩子】+【本章爽点】写入 🎭 角色与世界 → 🎣 钩子编年 / 🎯 爽点编年
        每章一行。如同章重复触发(死磕重写),会按章号去重,只保留最新。"""
        if not hasattr(self, "tab_charlib"):
            return
        from PyQt5.QtWidgets import QTableWidgetItem
        cl = self.tab_charlib

        # 钩子
        hook = pangu_meta.get("hook") or {}
        if hook and hook.get("content"):
            # 先去掉同章号旧行(死磕重写时)
            for r in range(cl.tbl_hooks.rowCount() - 1, -1, -1):
                if cl.tbl_hooks.item(r, 0) and cl.tbl_hooks.item(r, 0).text() == str(ch_num):
                    cl.tbl_hooks.removeRow(r)
            r = cl.tbl_hooks.rowCount()
            cl.tbl_hooks.insertRow(r)
            vals = [
                str(ch_num),
                hook.get("type", ""),
                hook.get("intensity", ""),
                hook.get("content", ""),
            ]
            for c, v in enumerate(vals):
                cl.tbl_hooks.setItem(r, c, QTableWidgetItem(str(v)))
            try:
                self.tab_generation.log(
                    f"  · 钩子已入库:第{ch_num}章 / {hook.get('type','')} "
                    f"/ 强度{hook.get('intensity','')}", "info")
            except Exception:
                pass

        # 爽点(可能多条,每条一行;同样按章号去重)
        cool_list = pangu_meta.get("cool_points") or []
        if cool_list:
            # 先去掉同章号旧行
            for r in range(cl.tbl_cool.rowCount() - 1, -1, -1):
                if cl.tbl_cool.item(r, 0) and cl.tbl_cool.item(r, 0).text() == str(ch_num):
                    cl.tbl_cool.removeRow(r)
            for cool_str in cool_list:
                # 格式可能是 "类型:内容" 或纯内容
                cool_type = ""
                cool_content = cool_str
                if ":" in cool_str or ":" in cool_str:
                    parts = re.split(r'[::]', cool_str, 1)
                    if len(parts) == 2:
                        cool_type = parts[0].strip()
                        cool_content = parts[1].strip()
                r = cl.tbl_cool.rowCount()
                cl.tbl_cool.insertRow(r)
                vals = [str(ch_num), cool_type, cool_content]
                for c, v in enumerate(vals):
                    cl.tbl_cool.setItem(r, c, QTableWidgetItem(str(v)))
            try:
                self.tab_generation.log(
                    f"  · 爽点已入库:第{ch_num}章 / {len(cool_list)} 条", "info")
            except Exception:
                pass

    def _sync_pangu_seeds_to_lifespan(self, pangu_meta: dict, ch_num: int):
        """把盘古【伏笔状态】的埋雷/收雷自动写入 lifespan_loops 的伏笔库。
        如果 lifespan_loops 未加载或未初始化 open_loops,静默跳过。"""
        try:
            from lifespan_loops_steps import LifespanLoopsExtension
        except ImportError:
            return
        # 收雷:遍历现有 open_loops,desc 子串匹配则 close
        for paid in pangu_meta.get("seeds_paid", []):
            desc = paid.get("desc", "")
            if not desc:
                continue
            loops = (getattr(self, "open_loops", None) or {}).get("loops", []) if hasattr(self, "open_loops") else []
            matched = None
            for loop in loops:
                if loop.get("status") == "closed":
                    continue
                ld = loop.get("desc", "")
                # 双向子串匹配(短的在长的里 或 反过来),避免 AI 措辞微差就匹配不上
                if (ld and (ld in desc or desc in ld)):
                    matched = loop
                    break
            if matched:
                LifespanLoopsExtension.close_loop(self, matched["id"], ch_num)
                try:
                    self.tab_generation.log(
                        f"  · 伏笔自动闭环:「{matched.get('desc','')[:30]}」 @第{ch_num}章", "info")
                except Exception:
                    pass
        # 埋雷:每条新加一条伏笔
        existing_ids = set(
            l.get("id") for l in (getattr(self, "open_loops", None) or {}).get("loops", [])
            if hasattr(self, "open_loops")
        )
        for i, seed in enumerate(pangu_meta.get("seeds_planted", [])):
            desc = seed.get("desc", "")
            if not desc:
                continue
            # 生成 unique id
            loop_id = f"pangu_ch{ch_num}_seed{i+1}"
            while loop_id in existing_ids:
                i += 1
                loop_id = f"pangu_ch{ch_num}_seed{i+1}"
            existing_ids.add(loop_id)
            # 关键词:取 desc 前 6 个字作为粗略关键词(用于章节文本扫描自动刷新 last_seen_ch)
            keyword = desc[:6] if len(desc) >= 6 else desc
            LifespanLoopsExtension.add_loop(
                self,
                loop_id=loop_id,
                desc=desc,
                added_ch=ch_num,
                keyword=keyword,
            )
            try:
                self.tab_generation.log(
                    f"  · 伏笔自动入库:「{desc[:30]}」 @第{ch_num}章 "
                    + (f"(计划第{seed['plan_pay_at']}章收)" if seed.get("plan_pay_at") else ""),
                    "info")
            except Exception:
                pass

    def _post_chapter_chain(self, ch_num):
        """章节通过后的链式处理:Canon 抽取 → 6库抽取 → 章末技能 → 摘要 → 下一章"""
        if ch_num <= 0:
            return
        pipeline = []
        if self.tab_canon.chk_extract.isChecked():
            pipeline.append(("canon_extract", ch_num))

        # BUG-014:6 库自动抽取(角色/关系/时间线/物品/战力/伏笔)
        if hasattr(self.tab_charlib, "chk_auto_extract") and \
                self.tab_charlib.chk_auto_extract.isChecked():
            pipeline.append(("charlib_extract", ch_num))

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
        elif step[0] == "charlib_extract":
            # BUG-014:批量抽取 6 库(角色/关系/时间线/物品/战力/伏笔)
            ch_num = step[1]
            ch = self.chapters[ch_num - 1] if 0 < ch_num <= len(self.chapters) else None
            if ch and ch.get("content"):
                # 复用 _charlib_extract_from_chapters 的单章逻辑
                self._charlib_batch_queue = [ch_num]
                # 设置 flag,让 _on_world_extract_received 完成后回 post_chapter 链
                self._charlib_chain_post = True
                self._run_next_charlib_extract()
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
        """没指定 target 时:直接复制到剪贴板,不弹窗打扰"""
        if not content.strip():
            return
        QApplication.clipboard().setText(content)
        self.tab_generation.log(
            f"✓ 已抓取 {len(content)} 字符,内容已复制到剪贴板", "success")

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

    # ---- 补丁3：大纲自动回填 ----
    def _auto_fill_outline(self, text: str):
        """
        把 AI 返回的大纲文本按常见标题拆分，自动回填到 StoryOutline 各输入框。
        支持三种格式：
          1. 中文方括号: 【故事种子】、【世界观】、【章节大纲】
          2. Markdown 标题: ### 世界观设定、## 章节大纲、#### 第一卷
          3. 普通段落标题: 世界观设定、主角设定 等
        """
        outline = getattr(self, 'tab_outline', None)
        if outline is None:
            self.tab_generation.log("⚠️  找不到 tab_outline 控件，无法回填", "warn")
            return

        def extract_block(keywords, text, is_chapter=False):
            """
            提取以 keywords 中任意一个为标题的段落内容。
            支持 【xxx】、## xxx、xxx: 等多种格式。
            
            参数:
              is_chapter: 章节大纲特殊处理 - 匹配到文末（因为下面通常嵌套子标题如 #### 第一卷）
            """
            kw_pattern = '|'.join(re.escape(k) for k in keywords)
            # 标题行模式：可能带 【】 或 # 标记，关键词后允许有括号备注等
            title_pattern = (
                r'(?:^|\n)\s*'                          # 行首
                r'(?:【\s*)?'                             # 可选 【
                r'(?:#{1,6}\s*|\*+\s*)?'                # 可选 # 或 *
                r'(?:' + kw_pattern + r')'                # 关键词
                r'[^\n【]*'                               # 允许标题后任意非换行非【内容（如"章节大纲（300章）"）
                r'(?:】|[:：])?'                           # 可选结尾标点
                r'\s*\n+'                                # 换行
            )
            
            if is_chapter:
                # 章节大纲：匹配到下一个【】块或文末（不被 #### 子标题截断）
                pattern = title_pattern + r'(.*?)(?=\n\s*【|\Z)'
            else:
                # 其他模块：匹配到下一个标题（任何 # 级或【】）
                pattern = title_pattern + r'(.*?)(?=\n\s*(?:【|#{1,6}\s)|\Z)'
            
            m = re.search(pattern, text, re.S | re.M)
            return m.group(1).strip() if m else ""

        # 各模块的关键词（同义词组）
        seed_kws       = ["故事种子", "故事核心", "核心设定", "故事概要"]
        worldview_kws  = ["世界观", "世界观设定", "世界设定", "背景设定"]
        lo_kws         = ["LO层", "LO世界观", "底层逻辑", "世界规则"]
        structure_kws  = ["故事结构", "故事架构", "结构设定", "整体结构"]
        chapter_kws    = ["章节大纲", "分章大纲", "章节梗概", "章节列表"]
        intro_kws      = ["简介", "作品简介", "故事简介"]

        def extract_kv(keywords, text):
            """兜底：匹配 **关键词**：内容 / 关键词：内容 这种键值对（单行）"""
            kw_pattern = '|'.join(re.escape(k) for k in keywords)
            pattern = (
                r'(?:\*\*\s*)?'                 # 可选 **
                r'(?:' + kw_pattern + r')'         # 关键词
                r'(?:\s*\*\*)?'                 # 可选 **
                r'\s*[:：]\s*'                   # 冒号
                r'(.+?)'                           # 内容
                r'(?=\n|\Z)'                     # 行尾或文末
            )
            m = re.search(pattern, text)
            return m.group(1).strip() if m else ""

        # 先尝试段落标题，再降级到键值对
        seed       = extract_block(seed_kws, text)       or extract_kv(seed_kws + ["题材", "故事题材"], text)
        worldview  = extract_block(worldview_kws, text)  or extract_kv(worldview_kws, text)
        lo_layer   = extract_block(lo_kws, text)         or extract_kv(lo_kws, text)
        structure  = extract_block(structure_kws, text)  or extract_kv(structure_kws + ["节奏", "升级逻辑"], text)
        ch_outline = extract_block(chapter_kws, text, is_chapter=True)
        intro      = extract_block(intro_kws, text)      or extract_kv(intro_kws, text)

        # 兜底：如果章节大纲没识别到，但文本里有大量 "1." "2." "第X章" 这种列表
        # 就把列表部分作为章节大纲
        if not ch_outline:
            # 找到第一个章节列表的开始位置
            list_match = re.search(r'(?:^|\n)\s*(?:1[\.\、]|第[一二三四五六七八九十1-9][章卷])', text, re.M)
            if list_match:
                # 从这里到文末作为章节大纲
                ch_outline = text[list_match.start():].strip()

        filled = []
        if seed       and hasattr(outline, 'seed_edit'):
            outline.seed_edit.setPlainText(seed);            filled.append("故事种子")
        if worldview  and hasattr(outline, 'worldview_edit'):
            outline.worldview_edit.setPlainText(worldview);  filled.append("世界观")
        if lo_layer   and hasattr(outline, 'lo_edit'):
            outline.lo_edit.setPlainText(lo_layer);          filled.append("LO层")
        if structure  and hasattr(outline, 'structure_edit'):
            outline.structure_edit.setPlainText(structure);  filled.append("结构")
        if ch_outline and hasattr(outline, 'chapter_outline_edit'):
            outline.chapter_outline_edit.setPlainText(ch_outline); filled.append("章节大纲")
        if intro      and hasattr(outline, 'intro_edit'):
            outline.intro_edit.setPlainText(intro);          filled.append("简介")

        if filled:
            self.tab_generation.log(f"✅ 大纲已自动回填：{' / '.join(filled)}", "success")
        else:
            self.tab_generation.log("✅ 大纲整体已回填（未检测到分块标题）", "success")

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

    def open_rename_dialog(self):
        """🔄 改名工具:多对应一次替换大纲全部文本(也可选择是否覆盖章节正文)
        例如:林远→苏白 + 林悦→苏雨 + 天剑宗→玄霄宗,一次提交。"""
        # 收集所有要扫描的目标(QPlainTextEdit + chapter content)
        targets = [
            ("特殊需求", self.tab_outline.special_edit),
            ("简介", self.tab_outline.intro_edit),
            ("故事种子", self.tab_outline.seed_edit),
            ("世界观", self.tab_outline.worldview_edit),
            ("LO世界观层", self.tab_outline.lo_edit),
            ("故事结构", self.tab_outline.structure_edit),
            ("章节大纲", self.tab_outline.chapter_outline_edit),
            ("角色设定", self.tab_settings.chars_edit),
        ]

        dlg = QDialog(self)
        dlg.setWindowTitle("🔄 改名工具(批量替换大纲/章节中的角色/地名/门派)")
        dlg.setMinimumWidth(700)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "<b>使用方法:</b>每行一个对应关系,格式 <code>旧名 → 新名</code> 或 "
            "<code>旧名 = 新名</code>(中间用 → 或 = 或制表符或多个空格都行)<br>"
            "支持一次替换多个,例如:<br>"
            "&nbsp;&nbsp;<code>林远 → 苏白</code><br>"
            "&nbsp;&nbsp;<code>林悦 → 苏雨</code><br>"
            "&nbsp;&nbsp;<code>天剑宗 → 玄霄宗</code>"))
        rename_text = QPlainTextEdit()
        rename_text.setPlaceholderText("林远 → 苏白\n林悦 → 苏雨\n天剑宗 → 玄霄宗")
        rename_text.setMinimumHeight(150)
        rename_text.setStyleSheet("font-family:monospace;font-size:13px;")
        lay.addWidget(rename_text)

        # 范围 checkbox
        cb_outline = QCheckBox("替换大纲全部文本(简介/种子/世界观/LO/结构/章节大纲/特殊需求/角色设定)")
        cb_outline.setChecked(True)
        cb_chapters = QCheckBox(f"同时替换已生成章节正文({len(self.chapters)} 章)")
        cb_chapters.setChecked(False)  # 默认不动章节,只动大纲(更安全)
        cb_charlib = QCheckBox("同时替换 🎭 角色与世界 库的所有表(角色名/关系/物品持有人等)")
        cb_charlib.setChecked(True)
        for cb in (cb_outline, cb_chapters, cb_charlib):
            lay.addWidget(cb)

        # 按钮
        btn_row = QHBoxLayout()
        btn_preview = QPushButton("👁 预览替换数(不写盘)")
        btn_preview.setStyleSheet("background:#3498db;color:white;padding:6px 14px;border-radius:3px;")
        btn_apply = QPushButton("✓ 应用替换(写盘 + 自动保存)")
        btn_apply.setStyleSheet(
            "background:#27ae60;color:white;padding:6px 14px;border-radius:3px;font-weight:bold;")
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)

        def parse_pairs():
            """从文本解析"旧名 → 新名"映射"""
            pairs = []
            for line in rename_text.toPlainText().splitlines():
                line = line.strip()
                if not line:
                    continue
                # 支持 → / -> / = / \t / 多空格 作分隔
                m = re.split(r'\s*(?:→|->|=>|=)\s*|\t+|\s{2,}', line, 1)
                if len(m) == 2 and m[0].strip() and m[1].strip():
                    pairs.append((m[0].strip(), m[1].strip()))
            return pairs

        def do_scan_and_apply(write):
            pairs = parse_pairs()
            if not pairs:
                QMessageBox.warning(dlg, "提示",
                    "没解析出有效对应关系。\n格式:旧名 → 新名,每行一个")
                return
            # 验证没重名
            old_set = set()
            for old, new in pairs:
                if old in old_set:
                    QMessageBox.warning(dlg, "重复",
                        f"旧名 '{old}' 出现多次,只能定义一次。")
                    return
                old_set.add(old)

            # 统计 & 替换
            stats = []
            total = 0
            # 1) 大纲编辑器
            if cb_outline.isChecked():
                for label, widget in targets:
                    txt = widget.toPlainText()
                    n_changes = 0
                    new_txt = txt
                    for old, new in pairs:
                        cnt = new_txt.count(old)
                        if cnt > 0:
                            new_txt = new_txt.replace(old, new)
                            n_changes += cnt
                    if n_changes > 0:
                        stats.append(f"{label}: {n_changes} 处")
                        total += n_changes
                        if write:
                            widget.setPlainText(new_txt)

            # 2) 章节正文
            if cb_chapters.isChecked() and self.chapters:
                ch_changes = 0
                for ch in self.chapters:
                    c = ch.get("content", "")
                    new_c = c
                    for old, new in pairs:
                        cnt = new_c.count(old)
                        if cnt > 0:
                            new_c = new_c.replace(old, new)
                            ch_changes += cnt
                    if write and new_c != c:
                        ch["content"] = new_c
                    # 章节标题也换
                    t = ch.get("title", "")
                    new_t = t
                    for old, new in pairs:
                        new_t = new_t.replace(old, new)
                    if write and new_t != t:
                        ch["title"] = new_t
                if ch_changes > 0:
                    stats.append(f"章节正文: {ch_changes} 处")
                    total += ch_changes

            # 3) 🎭 角色与世界库 — 遍历每张表的每个单元格
            if cb_charlib.isChecked() and hasattr(self, "tab_charlib"):
                cl = self.tab_charlib
                tables = [
                    ("角色档案", cl.tbl_chars),
                    ("关系图谱", cl.tbl_relations),
                    ("时间线", cl.tbl_timeline),
                    ("物品法器", cl.tbl_items),
                    ("战力等级", cl.tbl_power),
                    ("伏笔追踪", cl.tbl_fore),
                ]
                # 钩子/爽点子页如果存在(用户已升级到 bf9f713 之后)
                if hasattr(cl, "tbl_hooks"):
                    tables.append(("钩子编年", cl.tbl_hooks))
                if hasattr(cl, "tbl_cool"):
                    tables.append(("爽点编年", cl.tbl_cool))
                for tname, tbl in tables:
                    t_changes = 0
                    for r in range(tbl.rowCount()):
                        for c in range(tbl.columnCount()):
                            item = tbl.item(r, c)
                            if not item:
                                continue
                            v = item.text()
                            new_v = v
                            for old, new in pairs:
                                cnt = new_v.count(old)
                                if cnt > 0:
                                    new_v = new_v.replace(old, new)
                                    t_changes += cnt
                            if write and new_v != v:
                                from PyQt5.QtWidgets import QTableWidgetItem
                                tbl.setItem(r, c, QTableWidgetItem(new_v))
                    if t_changes > 0:
                        stats.append(f"{tname}: {t_changes} 处")
                        total += t_changes

            # 输出报告
            if total == 0:
                QMessageBox.information(dlg, "结果",
                    f"扫描完成,没有匹配的内容。\n请检查旧名拼写是否正确。")
                return

            msg = (f"共 {len(pairs)} 个对应关系,"
                   f"{'已替换' if write else '将替换'} {total} 处:\n\n"
                   + "\n".join(f"  · {s}" for s in stats))
            if write:
                # 自动保存
                try:
                    self.save_project()
                except Exception:
                    try:
                        self._autosave()
                    except Exception:
                        pass
                # 刷新当前章节编辑器
                try:
                    ci = self.tab_editor.current_index
                    if 0 <= ci < len(self.chapters):
                        self.tab_editor.show_chapter(self.chapters[ci], ci)
                except Exception:
                    pass
                self.tab_generation.log(f"🔄 改名应用:{total} 处替换,已自动保存", "success")
                msg += "\n\n✓ 已自动保存项目(.backups 保留原版本,可菜单 → 🕓 恢复)"
                QMessageBox.information(dlg, "✓ 完成", msg)
                dlg.accept()
            else:
                QMessageBox.information(dlg, "👁 预览(未写盘)", msg)

        btn_preview.clicked.connect(lambda: do_scan_and_apply(write=False))
        btn_apply.clicked.connect(lambda: do_scan_and_apply(write=True))
        btn_row.addWidget(btn_preview)
        btn_row.addWidget(btn_apply)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        dlg.exec_()

    def gen_first_chapter(self):
        """单独生成第一章（要求已有章节大纲）"""
        co = self.tab_outline.chapter_outline_edit.toPlainText()
        if not co.strip():
            QMessageBox.warning(self, "提示", "请先生成或填写章节大纲")
            return
        if not self.worker.is_ready():
            QMessageBox.information(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并完成 AI 网站登录。")
            return
        # 重置章节列表（如果用户想重新从第一章开始）
        if self.chapters:
            reply = QMessageBox.question(
                self, "确认", 
                f"已有 {len(self.chapters)} 章，是否清空后从第 1 章开始？\n（选「否」则继续生成下一章）",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.chapters.clear()
                self.tab_generation.log("已清空已生成章节，准备生成第 1 章", "info")
        # 设置批量参数(单章生成: remaining=1)
        self._batch_remaining = 1
        self._batch_paused = False
        self.tab_generation.log("▶ 开始生成第 1 章...", "info")
        self._send_next_chapter()

    def gen_golden_three(self):
        genres = self.tab_settings.get_selected_genres() or ["言情"]
        full = self.tab_settings.get_full_settings_block()
        # 角色库 + 时间线 + 伏笔 一键注入
        charlib_block = ""
        if hasattr(self, "tab_charlib"):
            charlib_block = self.tab_charlib.build_inject_block(current_chapter=1)
        prompt = PROMPTS["golden_three"].format(
            title=self.tab_settings.get_title(),
            genre="/".join(genres),
            inspiration=self.tab_settings.get_inspiration(),
            ch_outline=self.tab_outline.chapter_outline_edit.toPlainText()[:3000]
        ) + f"\n\n【完整设定】\n{full}"
        if charlib_block:
            prompt += charlib_block
            self.tab_generation.log(
                f"已注入角色与世界状态({len(charlib_block)} 字符)到黄金三章", "info")
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
        # BUG #8 修复:批量生成时静默伏笔提醒,避免阻塞自动化流程
        # 伏笔信息仍会注入到 prompt,只是不弹 modal
        self._batch_silent = True
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
        self._batch_silent = False  # 退出批量,恢复伏笔提醒
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
        """关闭主窗口时停止浏览器线程,清理临时文件"""
        from PyQt5.QtCore import QSettings
        QSettings("NovelAI", "MainWindow").setValue("geometry", self.saveGeometry())
        self.tab_settings.save_settings()
        self._autosave()
        try:
            self.worker.stop()
        except Exception:
            pass
        # 清理所有 novel_ai 临时文件
        try:
            import os, tempfile, glob
            tmp_dir = tempfile.gettempdir()
            for f in glob.glob(os.path.join(tmp_dir, "novel_ai_prompt_*.txt")):
                try:
                    os.remove(f)
                except Exception:
                    pass
        except Exception:
            pass
        event.accept()

    def _periodic_autosave_fire(self):
        """第 9 项配套:60 秒定时 autosave,只在有项目文件且内容有变化时跑,
        避免无意义的写盘和日志噪音"""
        try:
            # 尊重用户开关:auto_save_project 关掉就不跑定时
            cb = getattr(self.tab_generation, "auto_save_project", None)
            if cb is not None and not cb.isChecked():
                return
            # 没打开任何项目,跳过
            if not self.current_project_file:
                return
            # 章节为空且记忆为空 → 跳过
            if not self.chapters and not self.tab_memory.summaries_edit.toPlainText().strip():
                return
            self._autosave()
            # 静默写日志(不弹 UI),便于事后追溯
            try:
                self.tab_generation.log("⏱ 60s 定时 autosave 已执行", "info")
            except Exception:
                pass
        except Exception:
            pass

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
            if d.get("charlib") and hasattr(self, "tab_charlib"):
                self.tab_charlib.load(d["charlib"])
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
            # 🎭 角色库 + 关系 + 时间线 + 物品 + 伏笔
            "charlib": self.tab_charlib.serialize() if hasattr(self, "tab_charlib") else {},
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
        try:
            # 第 2 项:写入前先备份当前文件,保留最近 10 次
            self._rotate_project_backups(self.current_project_file)
            Path(self.current_project_file).write_text(
                json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            self.statusBar().showMessage(f"已保存:{self.current_project_file}", 3000)
        except Exception as e:
            QMessageBox.critical(
                self, "保存失败",
                f"无法写入项目文件:\n{self.current_project_file}\n\n错误:{e}\n\n"
                "请检查:1) 路径是否可写  2) 磁盘是否已满  3) 文件名是否合法")
            self.tab_generation.log(f"✗ 保存项目失败:{e}", "error")

    def _rotate_project_backups(self, project_path: str, keep: int = 10):
        """第 2 项:在 .backups/ 子目录里保留最近 N 次保存的快照。
        命名:<项目名>.YYYYMMDD-HHMMSS.json  超过 keep 个的最老备份删除。"""
        try:
            p = Path(project_path)
            if not p.exists():
                return  # 第一次保存没旧文件可备份
            backup_dir = p.parent / ".backups"
            backup_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = backup_dir / f"{p.stem}.{ts}{p.suffix}"
            backup_path.write_bytes(p.read_bytes())
            # 清理超过 keep 个的旧备份(只清同名前缀的)
            siblings = sorted(
                backup_dir.glob(f"{p.stem}.*{p.suffix}"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            for old in siblings[keep:]:
                try:
                    old.unlink()
                except Exception:
                    pass
        except Exception:
            pass  # 备份失败不影响主保存

    def restore_project_backup(self):
        """第 2 项配套:从 .backups/ 里挑一个版本恢复"""
        if not self.current_project_file:
            QMessageBox.information(self, "提示", "当前没有打开的项目文件,无备份可选")
            return
        p = Path(self.current_project_file)
        backup_dir = p.parent / ".backups"
        if not backup_dir.exists():
            QMessageBox.information(self, "提示", f"找不到 {backup_dir}\n还没产生过备份")
            return
        backups = sorted(
            backup_dir.glob(f"{p.stem}.*{p.suffix}"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if not backups:
            QMessageBox.information(self, "提示", "备份目录为空")
            return
        items = [f"{i+1}. {b.name}  ({datetime.fromtimestamp(b.stat().st_mtime).strftime('%m-%d %H:%M:%S')})"
                 for i, b in enumerate(backups)]
        choice, ok = QInputDialog.getItem(
            self, "选择恢复版本",
            f"从最近 {len(backups)} 个备份里选:",
            items, 0, False)
        if not ok or not choice:
            return
        idx = items.index(choice)
        chosen = backups[idx]
        ret = QMessageBox.question(
            self, "确认恢复",
            f"将用以下备份覆盖当前项目文件:\n\n{chosen.name}\n\n"
            f"当前文件会先备份为 .before_restore 后缀。继续?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        try:
            # 当前先额外存一份
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            before = backup_dir / f"{p.stem}.before_restore.{ts}{p.suffix}"
            if p.exists():
                before.write_bytes(p.read_bytes())
            p.write_bytes(chosen.read_bytes())
            QMessageBox.information(
                self, "已恢复",
                f"恢复完成。现重新打开项目以加载内容。\n\n"
                f"恢复前的版本另存为:{before.name}")
            # 重新加载
            self.open_project(self.current_project_file)
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

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

    def show_font_scale_dialog(self):
        """界面字体大小对话框 — 从顶部菜单'设置 → 🔍 界面字体大小...' 弹出"""
        from PyQt5.QtCore import QSettings
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
            QDialogButtonBox, QApplication as _QA)
        dlg = QDialog(self)
        dlg.setWindowTitle("🔍 界面字体大小")
        dlg.setMinimumWidth(500)
        lay = QVBoxLayout(dlg)

        tip = QLabel(
            "调字体倍数 — 4K 屏 / 老花眼 / 看不清都用这个。\n"
            "拖滑块到你舒服的位置,点确定,**关闭程序重新打开**生效。\n"
            "(Qt 字体只能在启动时设,运行中没法即时变)")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666; padding:6px; background:#f4f4f4; border-radius:3px;")
        lay.addWidget(tip)

        # 读当前值
        s = QSettings("NovelAI", "CreationSettings")
        cur = s.value("font_scale", 0.0, type=float) or 0.0
        if cur < 0.5:
            cur = float(_QA.instance().property("_novelai_dpi_scale") or 1.0)

        row = QHBoxLayout()
        row.addWidget(QLabel("字体倍数:"))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(80, 220)         # ×0.80 ~ ×2.20
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(20)
        slider.setValue(int(round(cur * 100)))
        row.addWidget(slider, 1)
        lab = QLabel(f"×{cur:.2f}")
        lab.setMinimumWidth(60)
        lab.setStyleSheet("font-weight:bold; font-size:14px; color:#b4884e;")
        row.addWidget(lab)
        lay.addLayout(row)

        # 实时更新标签
        slider.valueChanged.connect(lambda v: lab.setText(f"×{v/100:.2f}"))

        # 常用预设
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("快速预设:"))
        for label, val in [("1.0(默认)", 100), ("1.25", 125),
                            ("1.5(推荐 4K)", 150), ("1.75", 175), ("2.0", 200)]:
            btn = QPushButton(label)
            btn.setMaximumWidth(110)
            btn.clicked.connect(lambda _, v=val: slider.setValue(v))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)

        if dlg.exec_() == QDialog.Accepted:
            v = slider.value() / 100.0
            s.setValue("font_scale", float(v))
            QMessageBox.information(
                self, "已保存",
                f"字体倍数 ×{v:.2f} 已保存。\n\n"
                f"请关闭程序后重新打开生效。")

    # ==================== DOM 诊断 / 拾取工具(BUG-018 配套) ====================
    def show_dom_diagnostics(self):
        """🔬 诊断当前 AI 网页 DOM:看每个选择器在当前页命中了多少元素"""
        if not self.worker.is_ready():
            QMessageBox.warning(
                self, "请先启动浏览器",
                "请先在『生成控制』页点『🚀 启动浏览器』并打开 AI 网站")
            return
        # 在 worker 线程跑(driver 必须在 worker 线程访问)
        # 用一个简单的 deferred:postEvent / Queue 都行,这里用 invokeMethod
        from PyQt5.QtCore import QMetaObject, Qt, Q_RETURN_ARG
        # 简单点:同步走 — DOM 诊断很快,worker 当前如果不忙,直接调
        try:
            result = self.worker.run_dom_diagnostics()
        except Exception as e:
            QMessageBox.critical(self, "诊断失败", str(e))
            return
        # 渲染结果对话框
        dlg = QDialog(self)
        dlg.setWindowTitle("🔬 DOM 诊断结果")
        dlg.resize(800, 600)
        lay = QVBoxLayout(dlg)
        if "__error__" in result:
            lay.addWidget(QLabel(f"<b>诊断失败:</b>{result['__error__']}"))
        else:
            ov = result.get("__overview__", {})
            top = QLabel(
                f"<h3>页面概况</h3>"
                f"<p><b>URL:</b>{ov.get('url', '?')}</p>"
                f"<p><b>标题:</b>{ov.get('title', '?')}</p>"
                f"<p><b>页面统计:</b>textarea×{ov.get('total_textareas', 0)},"
                f"contenteditable×{ov.get('total_contenteditable', 0)},"
                f"button×{ov.get('total_buttons', 0)}"
                f"<br>DeepSeek 特有:ds-markdown×{ov.get('ds_markdown_count', 0)},"
                f"ds-assistant-message-main-content×{ov.get('ds_assistant_count', 0)}</p>")
            top.setTextFormat(Qt.RichText)
            top.setWordWrap(True)
            lay.addWidget(top)
            # 详细结果
            txt = QPlainTextEdit()
            txt.setReadOnly(True)
            txt.setStyleSheet("font-family:monospace; font-size:12px;")
            lines = ["<选择器诊断>\n" + "=" * 60]
            for name, info in result.items():
                if name == "__overview__":
                    continue
                sel = info.get("selector", "")
                cnt = info.get("count", 0)
                err = info.get("error", "")
                flag = "✓" if cnt > 0 else ("✗" if not err else "⚠")
                lines.append(f"\n[{flag}] {name}")
                lines.append(f"  选择器: {sel}")
                if err:
                    lines.append(f"  错误: {err}")
                else:
                    lines.append(f"  命中: {cnt} 个")
                    for j, s in enumerate(info.get("samples", [])):
                        vis = "可见" if s.get("visible") else "隐藏"
                        lines.append(f"    [{j}] <{s['tag']}.{s['class']}> [{vis}] '{s['text']}'")
            txt.setPlainText("\n".join(lines))
            lay.addWidget(txt, 1)
        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_pick = QPushButton("🎯 改用现场拾取")
        btn_pick.clicked.connect(lambda: (dlg.accept(), self.start_dom_picker()))
        btn_pick.setStyleSheet(
            "QPushButton { background:#e67e22; color:white; padding:6px 14px; "
            "border-radius:3px; font-weight:bold; }")
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_pick)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)
        dlg.exec_()

    def start_dom_picker(self):
        """🎯 现场拾取:在浏览器开 picker,用户 hover/点击,Python 端轮询读结果"""
        if not self.worker.is_ready():
            QMessageBox.warning(self, "请先启动浏览器", "请先启动浏览器并打开 AI 网页")
            return
        ok = self.worker.install_dom_picker()
        if not ok:
            QMessageBox.warning(self, "安装失败", "JS 注入失败,请确认浏览器已挂载到 AI 网页")
            return
        # 弹引导对话框,用户每点一次 "采集刚才点的",就读一次 picked
        dlg = QDialog(self)
        dlg.setWindowTitle("🎯 现场拾取选择器")
        dlg.setMinimumWidth(700)
        lay = QVBoxLayout(dlg)
        guide = QLabel(
            "<h3>用法</h3>"
            "<ol>"
            "<li>切到浏览器(挂载的 AI 网页)</li>"
            "<li>鼠标 hover 各元素,左上角蓝条会显示建议的选择器</li>"
            "<li>点击 <b>输入框</b> / <b>发送按钮</b> / <b>AI 回复区</b> 任一</li>"
            "<li>回到这里,点下方对应的[采集...为...]按钮,把刚点的选择器存到对应字段</li>"
            "<li>采集完点【💾 保存覆盖】生效</li>"
            "<li>浏览器里按 ESC 退出拾取模式</li>"
            "</ol>")
        guide.setWordWrap(True)
        guide.setStyleSheet("background:#f5f5f5; padding:10px; border-radius:3px;")
        lay.addWidget(guide)

        # 当前已采集的字段
        url = self.tab_generation.url_input.text() or "?"
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        lay.addWidget(QLabel(f"<b>目标站点:</b>{host}"))

        # 三个字段的"采集到此"
        fields = {}
        for key, label in [("input", "输入框"), ("send_btn", "发送按钮"), ("response", "AI 回复区"),
                            ("stop_btn", "停止按钮(可选)")]:
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText(f"<未采集 {label} 的选择器>")
            row.addWidget(QLabel(f"{label}:"))
            row.addWidget(edit, 1)
            btn = QPushButton(f"📥 用刚点击的元素填入")
            btn.setStyleSheet("QPushButton { background:#3498db; color:white; padding:4px 8px; }")
            def make_cap(e=edit, k=key, l=label):
                def _cap():
                    p = self.worker.get_picked_selector()
                    if p:
                        e.setText(p.get("selector", ""))
                        QMessageBox.information(
                            dlg, "✓ 已采集",
                            f"{l} 选择器:\n{p.get('selector')}\n命中 {p.get('count')} 个元素")
                    else:
                        QMessageBox.warning(
                            dlg, "没采到",
                            f"还没在浏览器里点元素,请先去浏览器 hover + 点{l}")
                return _cap
            btn.clicked.connect(make_cap())
            row.addWidget(btn)
            fields[key] = edit
            lay.addLayout(row)

        # 保存按钮
        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 保存覆盖到 QSettings(立即生效)")
        btn_save.setStyleSheet(
            "QPushButton { background:#2ecc71; color:white; padding:8px 16px; "
            "border-radius:3px; font-weight:bold; }")
        def _save():
            overrides = {k: e.text().strip() for k, e in fields.items() if e.text().strip()}
            if not overrides:
                QMessageBox.warning(dlg, "提示", "至少要填一个选择器")
                return
            self._apply_site_profile_override(host, overrides)
            QMessageBox.information(
                dlg, "✓ 已保存",
                f"{host} 选择器覆盖已保存。\n"
                f"立即生效,下次发消息会用新选择器。\n"
                f"覆盖项:{list(overrides.keys())}")
            dlg.accept()
        btn_save.clicked.connect(_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        dlg.exec_()

    def _apply_site_profile_override(self, host, overrides):
        """把用户拾取的选择器覆盖到运行时 SITE_PROFILES + 持久化到 QSettings"""
        global SITE_PROFILES
        # 找最匹配的 host key
        match_key = None
        for hk in SITE_PROFILES:
            if hk in host or host.endswith(hk):
                match_key = hk
                break
        if not match_key:
            # 新建一份(复制 _default 当底)
            match_key = host
            base = dict(SITE_PROFILES.get("_default", {}))
            base["name"] = host
            SITE_PROFILES[match_key] = base
        # 应用覆盖
        for k, v in overrides.items():
            SITE_PROFILES[match_key][k] = v
        # 持久化
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "SiteProfiles")
        for k, v in overrides.items():
            s.setValue(f"{match_key}/{k}", v)
        self.tab_generation.log(
            f"✓ 已更新 {match_key} 选择器:{list(overrides.keys())}", "success")

    def _load_site_profile_overrides(self):
        """启动时加载用户在 QSettings 里存的选择器覆盖"""
        global SITE_PROFILES
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "SiteProfiles")
        for host in list(SITE_PROFILES.keys()) + ['__custom__']:
            s.beginGroup(host)
            for k in s.childKeys():
                v = s.value(k)
                if v:
                    if host not in SITE_PROFILES:
                        SITE_PROFILES[host] = dict(SITE_PROFILES.get("_default", {}))
                    SITE_PROFILES[host][k] = v
            s.endGroup()

    def edit_site_profile_override(self):
        """📝 手动编辑当前站点选择器(高级用户)"""
        url = self.tab_generation.url_input.text() or ""
        from urllib.parse import urlparse
        host = urlparse(url).netloc or "chat.deepseek.com"
        match_key = None
        for hk in SITE_PROFILES:
            if hk in host or host.endswith(hk):
                match_key = hk
                break
        if not match_key:
            match_key = "_default"
        cur = SITE_PROFILES.get(match_key, {})

        dlg = QDialog(self)
        dlg.setWindowTitle(f"📝 编辑 {match_key} 选择器")
        dlg.setMinimumWidth(700)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"<b>当前站点:</b>{host}<br>"
            f"<b>使用 profile:</b>{match_key}<br>"
            f"<i>修改后立即生效,持久化到 QSettings。</i>"))
        fields = {}
        for key, label in [("input", "输入框 input"),
                            ("send_btn", "发送按钮 send_btn"),
                            ("response", "AI 回复区 response"),
                            ("stop_btn", "停止按钮 stop_btn")]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}:"))
            edit = QLineEdit(cur.get(key, ""))
            edit.setMinimumWidth(450)
            row.addWidget(edit, 1)
            fields[key] = edit
            lay.addLayout(row)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("💾 保存覆盖")
        btn_ok.setStyleSheet("QPushButton { background:#2ecc71; color:white; padding:6px 14px; }")
        def _ok():
            overrides = {k: e.text().strip() for k, e in fields.items() if e.text().strip()}
            if overrides:
                self._apply_site_profile_override(host, overrides)
            dlg.accept()
        btn_ok.clicked.connect(_ok)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)
        dlg.exec_()

    def batch_clean_chapter_meta(self):
        """🧹 扫描所有章节,把残留的元信息(本章完/钩子/爽点/选项)剥到 dict 字段
        用于清理'旧章节'(之前没有 strip 逻辑时生成的脏数据)"""
        if not self.chapters:
            QMessageBox.information(self, "提示", "当前没有章节可清理")
            return
        try:
            from pangu_system import parse_chapter_meta as _pangu_parse
        except ImportError:
            QMessageBox.warning(self, "无法清理", "找不到 pangu_system 模块")
            return

        # 先扫一遍看有几章需要清
        dirty_idxs = []
        for i, ch in enumerate(self.chapters):
            c = ch.get("content", "")
            if not c:
                continue
            # 含元信息标记之一就算 dirty
            if "本章完" in c or "【断章钩子】" in c or "【下一章选项】" in c \
                    or "【本章爽点】" in c or "【伏笔状态】" in c:
                dirty_idxs.append(i)

        if not dirty_idxs:
            QMessageBox.information(
                self, "✓ 不用清理",
                f"扫描 {len(self.chapters)} 章,**没有发现**残留元信息。\n"
                f"如果你看到章节正文里还有'本章完'等,可能是:\n"
                f"  · 拉的代码不是最新(git log 看 HEAD 是不是 cdcbfde 或更新)\n"
                f"  · 章节内容是 AI 加了变体格式,可以把章节末尾发我加规则")
            return

        ret = QMessageBox.question(
            self, "🧹 一键清理章节尾部元信息",
            f"扫描 {len(self.chapters)} 章,**发现 {len(dirty_idxs)} 章**含残留元信息:\n"
            f"  章节号:{[i+1 for i in dirty_idxs[:10]]}{'...' if len(dirty_idxs) > 10 else ''}\n\n"
            f"清理后:\n"
            f"  ✓ 章节正文剥离'本章完 / 【断章钩子】/ 【本章爽点】/ ...'\n"
            f"  ✓ 元信息存进 chapter dict 的 hook/cool_points/next_options 字段\n"
            f"  ✓ 自动保存项目(会触发 .backups 备份原版本)\n\n"
            f"继续吗?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return

        cleaned = 0
        total_stripped = 0
        for i in dirty_idxs:
            ch = self.chapters[i]
            orig = ch.get("content", "")
            if not orig:
                continue
            try:
                meta = _pangu_parse(orig)
                new_body = meta.get("body") or orig
                if len(new_body) == len(orig):
                    continue  # 没真的剥到
                stripped = len(orig) - len(new_body)
                total_stripped += stripped
                cleaned += 1
                ch["content"] = new_body
                # 存元信息到 dict 字段
                if meta.get("hook"): ch["hook"] = meta["hook"]
                if meta.get("cool_points"): ch["cool_points"] = meta["cool_points"]
                if meta.get("next_options"): ch["next_options"] = meta["next_options"]
                _sp = len(meta.get("seeds_planted", []))
                _pd = len(meta.get("seeds_paid", []))
                if _sp or _pd:
                    parts = []
                    if _sp: parts.append(f"埋雷 {_sp} 条")
                    if _pd: parts.append(f"收雷 {_pd} 条")
                    ch["_pangu_seeds_summary"] = " / ".join(parts)
                self.tab_generation.log(
                    f"  · 第 {i+1} 章 剥离 {stripped} 字 + 元信息入档",
                    "info")
            except Exception as e:
                self.tab_generation.log(f"  ✗ 第 {i+1} 章 剥离失败:{e}", "warn")

        # 刷新 UI
        try:
            cur_idx = self.tab_editor.current_index
            if 0 <= cur_idx < len(self.chapters):
                self.tab_editor.show_chapter(self.chapters[cur_idx], cur_idx)
        except Exception:
            pass
        # 保存
        try:
            self.save_project()
        except Exception:
            self._autosave()

        QMessageBox.information(
            self, "✓ 清理完成",
            f"清理 {cleaned} 章,共剥离 {total_stripped} 字元信息。\n\n"
            f"已自动保存项目(原版本可通过菜单 → 🕓 恢复历史版本 找回)。\n"
            f"切到章节编辑器看『📌 本章元信息』面板,钩子/爽点/选项已就位。")

    def show_about(self):
        QMessageBox.about(
            self, f"关于 {APP_NAME}",
            f"<h2>{APP_NAME}</h2>"
            f"<p><b>版本:</b>{APP_VERSION}</p>"
            "<p><b>技术栈:</b>Python 3 + PyQt5 + Selenium</p>"
            "<p><b>核心特性:</b></p>"
            "<ul>"
            "<li>挂载真实 Chrome / Edge,自动驱动 DeepSeek/豆包/Gemini/元宝/小米AI/ChatGPT 镜像</li>"
            "<li>盘古超级系统:禁用词过滤 + 感官铁律 + 压爆震 + 黄金三章公式</li>"
            "<li>角色与世界 6 库(角色/关系/时间线/物品/战力/伏笔)自动同步</li>"
            "<li>30 项质检 + 🔧 AI 自动修复</li>"
            "<li>章节元信息面板(钩子/爽点/伏笔/下一章选项,点选项自动指引下章)</li>"
            "<li>项目自动保存(每章+60s+章后立即)+ 最近 10 次版本备份</li>"
            "<li>自定义题材/时代/金手指/主角人设 + 折叠链</li>"
            "<li>设置菜单 → 🔍 界面字体大小(支持 4K HiDPI 手动放大)</li>"
            "</ul>"
            "<p><i>提示:本程序为 UI 仿制 + 核心逻辑实现示例,用于学习交流。"
            "各 AI 网页 DOM 不同,自动化提交/采集需根据实际 DOM 微调。</i></p>"
        )


def main():
    # ── 第 8 项: 4K HiDPI 自动缩放 ──────────────────────
    # 必须在 QApplication 创建 *之前* 设置这两个属性
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 字体倍数:只读用户手动设置(QSettings.font_scale),不再做自动检测
    # 原因:多屏 / 高分屏 Windows 缩放各种组合下自动检测不靠谱,
    #      手动滑块(创作设置最底)最稳。默认 ×1.0,用户拖了再生效。
    try:
        from PyQt5.QtCore import QSettings as _QSf
        _manual = _QSf("NovelAI", "CreationSettings").value(
            "font_scale", 0.0, type=float) or 0.0
        _scale = _manual if _manual >= 0.5 else 1.0
        if _scale > 1.0:
            from PyQt5.QtGui import QFont
            _font = app.font()
            _base = _font.pointSizeF() if _font.pointSizeF() > 0 else 9.0
            _font.setPointSizeF(_base * _scale)
            app.setFont(_font)
        app.setProperty("_novelai_dpi_scale", _scale)
    except Exception:
        pass

    # ── 授权验证 ──────────────────────────
    from license_guard import LicenseGuard
    guard = LicenseGuard(app)
    if not guard.check():
        sys.exit(0)

    try:
        win = MainWindow()
        win.show()
        # 字体倍数启动日志(只在 >1.0 时打,简洁)
        try:
            _sc = app.property("_novelai_dpi_scale") or 1.0
            if _sc > 1.0:
                win.tab_generation.log(
                    f"字体倍数 ×{_sc:.2f} 已应用(创作设置 → 底部 🔍 界面字体大小)",
                    "info")
        except Exception:
            pass
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
