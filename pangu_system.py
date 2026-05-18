#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古超级系统 · Python 引擎
==============================================
将"盘古真正完整版 V1.0"(29套网文创作系统融合)封装为可注入的提示词层。

设计原则:
1. 与现有 PROMPTS 解耦——盘古做"包裹层",不替换原提示词
2. 可选启用——通过 PanguEngine(enabled=False) 一键关闭,行为完全回到原版
3. 与 workflow_pipeline / lifespan_loops 等扩展并存,采用相同的可选导入模式

主要 API:
- PanguEngine.wrap_prompt(base_prompt, scenario, ctx) -> str
    将原提示词加上盘古铁律头+输出格式尾,生成最终发给 AI 的完整提示词
- PanguEngine.match_style(keywords) -> dict
    根据关键词自动匹配主风格/辅风格/点缀风格/女角色/平台
- PanguEngine.get_first_activation_banner() -> str
    返回首次激活的欢迎横幅文本
- PanguEngine.build_quality_check_prompt(content) -> str
    返回 30 项质检提示词
- PanguEngine.build_mode_switch_prompt(mode, content=None) -> str
    建筑师 / 造梦师 / 炼金术士 / 雕刻家 四模式切换
- PanguEngine.build_spiral_diagnose_prompt(content) -> str
    螺旋阶段 P1-P7 自动判定
- PanguEngine.detect_forbidden_words(text) -> List[str]
    本地静态扫禁用词(不发 AI,纯字符串匹配,用于事前/事后审查)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================
# 一、永久铁律(每次发提示词时都要前置注入的核心规则)
# ============================================================
# 注:这是从 Part 1 提炼的"瘦身版",约 1.5KB,适合每章注入。
# 完整 4.8万字的 Pangu Spec 存在 pangu_full_spec.md,只在
# 用户主动 /帮助 或首次激活时整体下发。

PANGU_CORE_RULES = """\
# ===== 盘古超级系统 · 核心铁律(每章必守)=====
你是【盘古】——融合 29 套网文创作系统的终极写作引擎。
**核心使命:替我写,不是教我写。** 只输出正文,不要分析、说明、复盘、预告、评分过程。

【输出铁律】
- 只输出正文,段落之间空一行
- 番茄风每章 2000-2500 字,起点风 2500-3000 字
- 每段不超过 3 句话
- 番茄风对话占比≥50%,起点风 30%-50%

【禁用词强制过滤】(以下词汇绝对禁止出现在正文,共 117 个)
副词类:顿时、连忙、显然、似乎、或许、可能、一定、十分、几乎、立刻、大致、确实、
  注定、渐渐、更是、略微、猛地、暂时、不断、瞬间、再次、一时之间、看似、看不出、
比喻词:仿佛、如同、像(比喻用法)、一抹、一股、一丝
形容词:沉重、淡淡、郑重、清淡、纯粹、冰冷、清冷、沸腾、扭曲、撕裂、漆黑、窒息、
  剧痛、不易察觉
心理动词(禁直接说想/觉/知):知道、觉得、意识到、感觉到、想、认为、不知道、
  他知道、她知道、我知道(改用具体动作或对话)
身体微表情(全部套话):嘴角、脸色、紧锁、的眼神、的目光、坚定的眼神、坚定的目光、
程度副词:至关重要、显著、绝对、不可估量、无法想象、无法用言语形容、此刻、恐怕、
  这一刻、这一次
套话短语(整词禁):嘴角勾起一抹、眼中闪过一丝、行云流水、心下了然、心中一凛、
  心中了然、心中一动、心中一片平静、话锋一转、眼神深邃、微微挑眉、波涛汹涌、
  脸上带着笑意、脸上堆满了笑、深吸一口气、缓缓地说、锐利的眼睛、嘴角微微上扬、
  不容置疑、目光扫过、沉吟、沉吟片刻、隐隐有了猜测、不动声色、小心翼翼、
  不卑不亢、显得异常清晰、显得更加、平静地、激动地、眼神热切、目光里毫不遮掩、
  果然、口吻、带着、显得有些兴奋、淡淡地、淡淡地应了一句、
  他的嘴角微微上扬、他的表情变暗、他的心一跳、他的脸变了、心里隐隐有了猜测
其他过度词:电弧、闪烁、裹挟、有点

【通用单字的违规情境】(以下单字本身不禁,但出现以下组合算违规):
- "像":禁比喻用法(像被雷劈一般),正常做动词(他像哥哥)可用
- "坚定":禁套话(坚定的眼神/目光),做形容词单用(他很坚定)可用
- "心中":禁套话(心中XX,如心中一凛/心中了然 都已在禁用清单),
  做位置词(藏在心中)可用

【情绪铁律】直给情绪词,不用形容词定义情绪。
- 写"他很绝望",不写"眼里一片荒芜"
- 写"她紧张了",不写"她的手指无意识地绞着衣角"

【动作铁律】只写动作+结果,不写过程。
- 写"他打了拳",不写"他缓缓抬起手臂,蓄力,然后一拳打出"
- 拟声词当动词:"啪地摔了碗",不写"啪的一声响"

【环境铁律】环境不单独成段,附在动作前面。每章环境描写不超过 3 句。

【句式铁律】
- 单句不超过 25 字,超出自动拆分
- 主语清晰,每句话让读者知道"谁在做什么"
- 禁用破折号,省略号用六个点......
- 对话占比 50%以上时,每句对话必须有用途(推剧情/亮人设)

【对话铁律 · 13 法】高频用"说/道/喊/吼"是稚嫩信号。整章"说"出现次数 ≤ 章节字数/600
(3000 字章节 ≤ 5 次,5000 字 ≤ 8 次)。强制替换为以下 13 法,**每法每章至少用 1 次**:

  L1 动作卡位:用动作替代提示语 — "她攥紧剑柄。'你过来。'"
  L2 神态神韵:用专属微动作 — "林远的嘴角压不住。'赌赢了。'"
  L3 情境穿插:对话间插环境/物 — "'凡人。'山风灌进祠堂,木门吱呀。"
  L4 语感辨识:角色有专属语气/口头禅(如赵乾每次以"凡人"开头)
  L5 语义衔接:对话直接回应前句的物/事,跳过提示 —
                "妖兽爪子撕开了他的肩。'还能站。'"
  L6 标点替代:短促交锋用换行 + 中文引号,完全省提示语。示例:
              "去哪?"
              "天剑宗。"
              "找谁?"
              (注意:每句对话必须用中文引号「」或英文引号 "" 包裹,绝不允许用 ── 或 — 开头)
  L7 内心独白回切:角色对话后接主角自己的预判反应 —
                "'凡人,领路费回家。' 林远没动 — 这种人不会只说一句。"
  L8 群体反应衬托:用其他人对那句话的反应反推说话人 —
                "'你不是凡人!' 二十多个村民全部后退一步。"
  L9 重复词锚定:给特定角色刻意重复一个词/句式(全章至少 2 次复用)
  L10 空格断句:对话占据独立段落 + 上下空一行(节奏需要时用,不要每段都用)。
              注意"独立段落"≠ 前面加破折号或符号,就是单独成段加空行而已
  L11 通感法:把一种感官的体验写成另一种 —
                "嘴里全是铁锈味"(味觉写疲惫)
  L12 信息差:让读者比角色多/少知道一点,产生张力
  L13 节奏开关:整章节奏脉冲 急-慢-急-慢,不能全急也不能全慢

【对话标点硬性要求 · 必须遵守】
- **对话必须用中文引号 "" 或英文引号 "" 包裹,不准用其他标记**
- **不准用 ── 或 — 作为对话开头**(欧美小说风格,中文网文不用)
- **不准用 「」内嵌另一对 「」**(嵌套用单引号 '' 或英文引号)
- 段首不加任何符号(对话顶格 = 没有缩进,而不是加破折号)

正确示例:
  林远把血滴进凹槽。
  "凡人。"
  山风灌进祠堂。
  
错误示例(13 法说的"省提示语"绝不是这个意思):
  林远把血滴进凹槽。
  ──凡人。              ← 错!破折号开头
  山风灌进祠堂。
  
  或:
  ── 跟我走。           ← 错!破折号代替引号
  ── 我哥呢?           ← 错!

【对话稚嫩信号 · 自检红线(违反任一即扣 5 分)】
- "X 说" 出现 > 章节字数/600
- 同一段 3 句对话都用 "X 说/X 道" 提示
- 出现 "怒吼道/喃喃道/喝道/低声道/淡淡道/缓缓道" 等套词
- 修饰词修饰对话 "他生气地说" "她担心地问" (改用动作+对话)
- **段落以 ── 或 — 开头作为对话(违反盘古破折号禁令)**

【感官铁律(每章必须)】
- 视觉细节:至少 1 处(具体物件的颜色/形状/状态)
- 听觉细节:至少 1 处(对话内容/环境音/动作声)
- 触觉/嗅觉/味觉:至少 1 处(三选一)
- 细节分散植入,不集中写大段描写

【结构铁律】
- 开篇三句话内必须进入事件
- 禁止环境描写开头、背景介绍开头、天气描写开头
- 每章结尾必须有钩子,强度≥8/10
- 钩子类型:对话没说完/人出现/秘密暴露/倒计时/关键动作
- 每章至少 2 个爽点:打脸/捡漏/暧昧/突破/反转/碾压/夺宝/收服/揭秘/共鸣

【智商防火墙】任何智商≥5 的角色绝对禁止:
- 直接暴露核心秘密
- 主动相认"你也穿越了吧?"
- 在公共场合说现代词汇
- 不设防地交底

【视角铁律】视角锁主角 70%,对手 15%,第三方 10%,上帝视角 5%(仅用于大高潮定格)。不跳别人心理,不写"他在想什么"。

【八大坑铁律 · 写章节前必读】网文八大致命坑,中一个就容易扑街:

  K1 视角混乱:一段里不准在主角/配角/上帝视角之间跳。
       别人的想法 → 通过主角观察呈现,不直接钻别人脑子。

  K2 对话尴尬:台词不能像念课文/借嘴堆设定/不符身份/堆废话。
       每句对话必须:推剧情 OR 立人设 OR 藏信息(至少一个)。

  K3 逻辑崩坏:爽点不能靠巧合硬凑(快死了掉山洞捡神功/没钱捡戒指)。
       爽点必须有:① 代价(用什么换的) ② 铺垫(前面埋过的雷)
       ③ 规则(系统的内部逻辑)。开挂前先付费。

  K4 主角提线木偶:主角不能全程被推着走。
       每章主角必须有:清晰目标 + 即时行动。
       不写"他被卷入..." 写"他决定..."。

  K5 反派全员弱智:反派必须有:立场 + 目标 + 合理性。
       反派不是恶心主角的工具,是有自己的算盘。
       强弱对等冲突才好看(反派不应该比主角弱太多)。

  K6 毒点雷区:三观别扭 / 角色降智 / 强行虐主 / 尴尬煽情 → 一律删。
       写完一段问自己:"这段是不是会让读者关闭页面?"
       常见雷:绿主角 / 主角圣母 / 龟缩到读者跳脚 / 莫名其妙的虐。

  K7 节奏拖沓:开篇 3 秒必须抓眼球。
       禁止:大段写景开篇 / 大段回忆开篇 / 无关支线 / 念大纲。
       黄金三章必须亮:主角 + 困境 + 核心冲突 + 一个钩子。

  K8 自我感动:别只写自己想写的。
       必须考虑:平台调性(番茄/起点/晋江各不同)/ 目标读者 /
       爽点节奏 / 卖点。
       自查:这一章读者看完会想干嘛?(翻下一章 OR 关闭?)

【情绪曲线·压爆震】压 70%(用日常、沉默、什么都没发生来蓄力)+ 爆 5%(最短句最少词,只写那一下)+ 震 25%(用沉默/细节/动作/空镜让读者消化)。每 300 字至少一个情绪点。

# ===== 以上为永久铁律,下面是本次任务 =====
"""


# ============================================================
# 二、关键词 → 风格自动匹配表(来自 Part 2.1)
# ============================================================
# 输入题材/灵感关键词,自动匹配主风格+辅风格+点缀风格+女角色类型+平台。
# 与 CreationSettings 中用户已选的 platform/genre/persona 互补,不冲突。

STYLE_MAPPING: List[Dict[str, str]] = [
    # 关键词以"|"分隔
    {"kw": "雨夜|离别|遗憾|错过|追妻|火葬场",
     "main": "王家卫情绪型", "sub": "陈可辛情感型", "accent": "萧红型",
     "female": "台湾/江南", "platform": "起点"},
    {"kw": "打脸|逆袭|爽文|退婚|战神|赘婿|龙王",
     "main": "周星驰无厘头", "sub": "战神赘婿型", "accent": "龙王型",
     "female": "东北/川渝", "platform": "番茄"},
    {"kw": "搞笑|日常|轻松|脑洞",
     "main": "刘镇伟奇幻型", "sub": "国漫搞笑型", "accent": "吐槽之王",
     "female": "湖南/湖北", "platform": "番茄"},
    {"kw": "热血|战斗|升级|宗门|武侠",
     "main": "徐克武侠型", "sub": "中原五白型", "accent": "国漫玄幻",
     "female": "山东/北京", "platform": "起点"},
    {"kw": "悬疑|恐怖|灵异|鬼|规则怪谈",
     "main": "僵尸道长型", "sub": "规则怪谈型", "accent": "邱礼涛型",
     "female": "广东/陕西", "platform": "番茄"},
    {"kw": "末世|生存|囤货|丧尸|废土",
     "main": "末世家国型", "sub": "囤货求生型", "accent": "国漫末世",
     "female": "东北/河南", "platform": "番茄"},
    {"kw": "情色|后宫|禁忌|擦边|风月",
     "main": "王晶咸湿型", "sub": "风月型", "accent": "情色擦边库",
     "female": "四川/上海", "platform": "番茄"},
    {"kw": "修仙|长生|渡劫|飞升|凡人流",
     "main": "国漫凡人流", "sub": "玄幻修仙型", "accent": "中原五青",
     "female": "江南/山东", "platform": "起点"},
    {"kw": "权谋|宫斗|朝堂|夺嫡|帝王",
     "main": "权谋宫斗型", "sub": "人性博弈型", "accent": "幕后黑手",
     "female": "江南/北京", "platform": "起点"},
    {"kw": "都市|神豪|系统|签到",
     "main": "神豪系统型", "sub": "战神赘婿型", "accent": "金钱碾压",
     "female": "东北/广东", "platform": "番茄"},
    {"kw": "重生|穿越|先知|剧透",
     "main": "重生穿越型", "sub": "考据式穿越", "accent": "迪化流",
     "female": "湖南/上海", "platform": "番茄"},
    {"kw": "虐恋|追妻|火葬场|甜宠|霸总",
     "main": "陈可辛情感型", "sub": "霸总契约型", "accent": "虐恋追妻",
     "female": "台湾/江南", "platform": "晋江"},
    {"kw": "黑帮|江湖|义气|复仇|枭雄",
     "main": "麦当雄枭雄型", "sub": "吴宇森暴力美学", "accent": "林岭东型",
     "female": "东北/湖北", "platform": "起点"},
    {"kw": "写实|底层|社会|残酷",
     "main": "尔冬升写实型", "sub": "沈从文型", "accent": "汪曾祺型",
     "female": "河南/陕西", "platform": "知乎"},
    {"kw": "甜宠|恋爱|校园|青梅",
     "main": "席绢真实版", "sub": "于晴真实版", "accent": "陈可辛情感",
     "female": "台湾/江南", "platform": "晋江"},
    {"kw": "无敌|隐藏大佬|扮猪吃虎",
     "main": "无敌摆烂型", "sub": "战神赘婿型", "accent": "龙王型",
     "female": "任意", "platform": "番茄"},
    {"kw": "脑洞|反套路|迪化|乐子",
     "main": "反套路祖师", "sub": "迪化修仙流", "accent": "乐子天尊",
     "female": "任意", "platform": "番茄"},
    {"kw": "苟道|稳健|谨慎",
     "main": "国漫凡人流", "sub": "苟道修仙流", "accent": "稳健流",
     "female": "任意", "platform": "起点"},
    {"kw": "诡异|克苏鲁|污染",
     "main": "痛苦邪神型", "sub": "规则怪谈型", "accent": "恐惧魔王",
     "female": "任意", "platform": "番茄"},
]


# ============================================================
# 三、黄金三章公式(Part 4.1)
# ============================================================
GOLDEN_THREE_FORMULA = """\
【黄金三章公式(第 1-3 章强制)】
- 第 1 章 · 绝境+羞辱:必写被看不起/被嘲讽/被抛弃/被威胁/被退婚/被裁员/被背叛
- 第 2 章 · 金手指激活:濒死或绝望一刻,系统绑定/重生归来/觉醒异能/获得传承/签到成功
- 第 3 章 · 首次反转打脸:反派继续装逼,主角小试牛刀,现场震惊,反派脸色剧变,结尾留钩子

【循环爽点单元(每 3-5 章自动循环)】
1. 新冲突:新反派登场装逼/挑衅/看不起主角
2. 装弱铺垫:主角低调,旁人嘲讽,反派更嚣张
3. 反转爆发:主角亮实力/身份/系统奖励
4. 打脸碾压:反派崩溃、求饶、后悔
5. 奖励兑现:升级/得钱/收小弟/获崇拜/美人青睐
6. 留钩子:引出更强敌人/新地图/新任务
"""


# ============================================================
# 四、矛盾螺旋引擎大纲规划块(Part 3)
# ============================================================
SPIRAL_OUTLINE_SPEC = """\
【矛盾螺旋引擎要求】
1. 主要矛盾陈述(一句话):主角想要__________,但__________阻碍他。
2. 次要矛盾列表(3-5 个):资源矛盾 / 人际关系矛盾 / 身份秘密矛盾 / 外部威胁矛盾 / 内部背叛矛盾
3. 矛盾演化路径:个人→家族→势力→世界 的层层升级路径
4. 人物弧光三阶段:
   - 第一阶段·旧信念(开篇):主角相信__________
   - 第二阶段·遭遇否定(中段):__________事件摧毁了这个信念
   - 第三阶段·新信念(结局):主角建立了更复杂的信念:__________
5. 章节大纲必须标注每章所处的螺旋阶段:P1 量变铺垫 / P2 量变压抑 / P3 临界 / P4 质变爆发 / P5 否定落地 / P6 否定被否(可选) / P7 更高层次量变
"""


# ============================================================
# 五、输出格式尾巴(Part 11)
# ============================================================
def chapter_output_format(chapter_num: int = 1, show_options: bool = True) -> str:
    """生成每章正文输出后追加的结构化尾部。"""
    tail = f"""\

【输出格式要求】每章末尾追加以下结构化信息(用 markdown):

```
本章完

【断章钩子】
类型:[对话没说完/人出现/秘密暴露/倒计时/关键动作]
强度:[★-★★★★★]
内容:[具体钩子内容]

【本章爽点】
[爽点类型 1]:[具体内容]
[爽点类型 2]:[具体内容]

【伏笔状态】
本章埋雷:[内容](计划第 X 章收)
本章收雷:[内容](第 X 章所埋)
```
"""
    if show_options:
        tail += """
【下一章选项(必须给)】
1. [选项一]
2. [选项二]
3. [选项三]
"""
    return tail


# ============================================================
# 五·B、章节元信息解析(配合 chapter_output_format 的反向操作)
# ============================================================
# AI 按 chapter_output_format 输出的章节回复结构:
#   [正文]
#   本章完
#
#   【断章钩子】...
#   【本章爽点】...
#   【伏笔状态】本章埋雷:...  /  本章收雷:...
#   【下一章选项】1. ... 2. ... 3. ...
#
# 这些元信息**不属于正文**,必须从入库的章节内容里剥离;
# 同时把【伏笔状态】结构化提取出来,供 lifespan_loops 自动落库。

_META_SECTION_TITLES = (
    "【断章钩子】", "【本章爽点】", "【伏笔状态】", "【下一章选项】",
    # 容错:【XXX 】中间或两侧可能有空格
    "【 断章钩子 】", "【 本章爽点 】", "【 伏笔状态 】", "【 下一章选项 】",
    # 容错:有 AI 用方括号或井号代替
    "[断章钩子]", "[本章爽点]", "[伏笔状态]", "[下一章选项]",
    "## 断章钩子", "## 本章爽点", "## 伏笔状态", "## 下一章选项",
)
# 兼容容错:有时 AI 漏写"本章完"、或者把【XXX】换成 [XXX] / ## XXX
_CHAPTER_END_MARKERS = (
    "本章完", "—— 本章完 ——", "（本章完）", "(本章完)",
    "本章完。", "本章完！", "—本章完—", "***本章完***",
    "（完）", "(完)",
)


def strip_chapter_meta(content: str) -> str:
    """
    从 AI 章节回复里剥离尾部元信息块,只保留正文。
    
    剥离策略(按优先级):
    1. 找到"本章完"(或变体),从该处截断,前面全是正文
    2. 找不到"本章完" → 找第一个【断章钩子】/【本章爽点】等元信息标题,截断
    3. 都找不到 → 内容本身就是干净正文,原样返回
    
    末尾保留正文最后段落的空白裁剪。
    """
    if not content:
        return ""
    text = content
    cut_at = -1

    # 1) 优先按 "本章完" 切
    for marker in _CHAPTER_END_MARKERS:
        idx = text.rfind(marker)
        # 用 rfind:章节正文里很少有"本章完"三个字,即使有,
        # 最后那个一定是 AI 加的尾部标记
        if idx >= 0:
            cut_at = idx
            break

    # 2) 退路:找第一个元信息标题
    if cut_at < 0:
        for title in _META_SECTION_TITLES:
            idx = text.find(title)
            if idx >= 0 and (cut_at < 0 or idx < cut_at):
                cut_at = idx

    # 3) 没找到任何标记,原样返回
    if cut_at < 0:
        return text.rstrip()

    body = text[:cut_at].rstrip()
    # 再扫一遍,把可能黏在前面的 ``` 代码围栏移除
    body = re.sub(r'\n+```\s*$', '', body).rstrip()
    return body


def parse_chapter_meta(content: str) -> Dict:
    """
    从 AI 章节回复里解析出元信息块。
    返回 dict:
      {
        "body":          str   净化后的章节正文(已剥离元信息)
        "hook":          {"type": str, "intensity": str, "content": str} | None
        "cool_points":   [str, ...]
        "seeds_planted": [{"desc": str, "plan_pay_at": int|None}, ...]
        "seeds_paid":    [{"desc": str, "planted_at": int|None}, ...]
        "next_options":  [str, str, str]
      }
    
    解析尽可能宽容:AI 不按格式输出/漏字段/中文标点变化都不应抛异常,
    抓不到的字段返回空/默认即可。
    """
    out = {
        "body":          "",
        "hook":          None,
        "cool_points":   [],
        "seeds_planted": [],
        "seeds_paid":    [],
        "next_options":  [],
    }
    if not content:
        return out

    out["body"] = strip_chapter_meta(content)

    # 取出元信息那段(本章完 之后的所有内容)
    tail = ""
    for marker in _CHAPTER_END_MARKERS:
        idx = content.rfind(marker)
        if idx >= 0:
            tail = content[idx + len(marker):]
            break
    if not tail:
        # 没"本章完"标记,从第一个元标题开始当尾
        for title in _META_SECTION_TITLES:
            idx = content.find(title)
            if idx >= 0:
                tail = content[idx:]
                break

    if not tail:
        return out  # 没元信息,只回 body

    # 把尾部按【XXX】切成块
    blocks = {}
    # 正则:【任一标题】至下一个【或字符串末尾
    pattern = r'【(断章钩子|本章爽点|伏笔状态|下一章选项)(?:\(必须给\))?】([\s\S]*?)(?=【(?:断章钩子|本章爽点|伏笔状态|下一章选项)|```|$)'
    for m in re.finditer(pattern, tail):
        title = m.group(1)
        body  = m.group(2).strip().strip('`').strip()
        blocks[title] = body

    # ── 断章钩子 ──
    if "断章钩子" in blocks:
        hook = {"type": "", "intensity": "", "content": ""}
        for line in blocks["断章钩子"].splitlines():
            line = line.strip()
            if line.startswith("类型"):
                hook["type"] = line.split(":", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("强度"):
                hook["intensity"] = line.split(":", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("内容"):
                hook["content"] = line.split(":", 1)[-1].split(":", 1)[-1].strip()
        if any(hook.values()):
            out["hook"] = hook

    # ── 本章爽点 ──
    if "本章爽点" in blocks:
        for line in blocks["本章爽点"].splitlines():
            line = line.strip().lstrip("-").lstrip("*").strip()
            if line and not line.startswith("[") and len(line) > 2:
                out["cool_points"].append(line)

    # ── 伏笔状态 ──
    if "伏笔状态" in blocks:
        for line in blocks["伏笔状态"].splitlines():
            line = line.strip().lstrip("-").lstrip("*").strip()
            if not line:
                continue
            # "本章埋雷:XXX(计划第 N 章收)" / "(计划第 N-M 章收)"
            m_plant = re.match(
                r'本章埋雷[:：](.+?)(?:[(（]\s*计划第\s*(\d+)(?:\s*[-~—]\s*\d+)?\s*章收\s*[)）])?\s*$', line)
            if m_plant:
                desc = m_plant.group(1).strip()
                # 如果 desc 末尾还残留 "(计划第..." 没被吃掉,清理一下
                desc = re.sub(r'\s*[(（]\s*计划第\s*\d+(?:\s*[-~—]\s*\d+)?\s*章收\s*[)）]\s*$', '', desc).strip()
                if desc and desc not in ("无", "无。", "(无)"):
                    plan = int(m_plant.group(2)) if m_plant.group(2) else None
                    out["seeds_planted"].append({"desc": desc, "plan_pay_at": plan})
                continue
            # "本章收雷:XXX(第 N 章所埋)" / "(第 N-M 章所埋)"
            m_pay = re.match(
                r'本章收雷[:：](.+?)(?:[(（]\s*第\s*(\d+)(?:\s*[-~—]\s*\d+)?\s*章所埋\s*[)）])?\s*$', line)
            if m_pay:
                desc = m_pay.group(1).strip()
                desc = re.sub(r'\s*[(（]\s*第\s*\d+(?:\s*[-~—]\s*\d+)?\s*章所埋\s*[)）]\s*$', '', desc).strip()
                if desc and desc not in ("无", "无。", "(无)"):
                    planted = int(m_pay.group(2)) if m_pay.group(2) else None
                    out["seeds_paid"].append({"desc": desc, "planted_at": planted})

    # ── 下一章选项 ──
    if "下一章选项" in blocks:
        for line in blocks["下一章选项"].splitlines():
            line = line.strip()
            if not line:
                continue
            # "1. xxx" / "1、xxx" / "①xxx"
            m_opt = re.match(r'^\s*(?:\d+|[①-⑩])\s*[\.\、\:\：]?\s*(.+?)\s*$', line)
            if m_opt:
                opt = m_opt.group(1).strip()
            else:
                # 兜底:整行视为选项(用户/AI 经常漏写数字前缀)
                # 但要排除明显不是选项的内容(纯标点、太短、太长)
                opt = line
                if len(opt) < 4 or len(opt) > 120:
                    continue
                # 排除常见的元信息行
                if re.match(r'^[\-\*\—\=\【\[]', opt):
                    continue
            if opt and len(opt) > 2:
                out["next_options"].append(opt)
        # 截断到最多 5 个
        out["next_options"] = out["next_options"][:5]

    return out


# ============================================================
# 六、四模式切换(Part 8)
# ============================================================
MODE_PROMPTS = {
    "architect": """\
切换至【建筑师】模式:搭骨架优先。
- 适用:大纲卡住、伏笔理不清、规划节奏
- 输出:用清单/表格列出主要矛盾、人物弧光、章节阶段(P1-P7)、伏笔时刻表
- 禁止:写细节、铺情绪、写正文
""",
    "dreamweaver": """\
切换至【造梦师】模式:写正文(默认)。
- 适用:沉浸式写作、铺感官和情绪
- 严格遵守盘古所有铁律,只输出正文
- 禁止:自我审查、边写边改、写完后复盘
""",
    "alchemist": """\
切换至【炼金术士】模式:破局。
- 适用:彻底卡文、剧情死胡同、需要脑洞
- 操作:对当前情境问"反着来会怎样",写出 3 个荒谬走向,标注最心动的那个
- 禁止:说"这不合理"
""",
    "sculptor": """\
切换至【雕刻家】模式:打磨。
- 适用:改稿、删冗余、调整句子节奏
- 法则:先删再改 / 能砍的不改 / 能用动作的不用形容词 / 改完朗读一遍
- 禁止:心软
""",
}


# ============================================================
# 七、首次激活横幅(Part 13)
# ============================================================
FIRST_ACTIVATION_BANNER = """\
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🪐 盘古超级系统 V1.0 · 真正完整版 🪐                ║
║                                                              ║
║   已激活 · 待命中                                              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

【已融合 29 套系统精华】

【核心引擎】
✓ 矛盾螺旋引擎(P1-P7 七阶段自动判定)
✓ 风格库自动匹配(港片 15 型 + 国漫 9 型 + 电视剧 8 型 + 短剧 8 型 + 网文 5 型)
✓ 地域女性库(13 型完整人物模板)
✓ 题材基因库(60+ 题材完整设定)

【文笔保障】
✓ 禁用词强制过滤(几百个 AI 高频词)
✓ 感官描写铁律(视觉+听觉+触嗅味)
✓ 压爆震结构(压 70%+爆 5%+震 25%)
✓ 情绪直给+动作只写结果

【长篇保障】
✓ 伏笔分级喂养(短线/中线/长线)
✓ 状态表自动维护(情绪值/关系进度/伏笔状态)
✓ 30 项质检清单(95 分及格)
✓ 四模式切换(建筑师/造梦师/炼金术士/雕刻家)

【平台适配】
✓ 番茄:黄金三章+循环爽点+每章钩子
✓ 起点:世界观宏大+升级体系清晰+伏笔深远
✓ 晋江:情感细腻+人物弧光+甜虐有度
"""


# ============================================================
# 八、30 项质检 prompt(Part 6.1)
# ============================================================
QUALITY_CHECK_PROMPT_TPL = """\
你是【盘古·质检员】。对以下章节执行 38 项智能质检(含八大坑专项),任何一项不通过则给出修改意见。

【A. 番茄流量检查(10 项,满分 100,≥95 及格)】
1. 开局冲击力:前三段是否出现让读者瞳孔地震的钩子
2. 人设辨识度:本章至少一个细节让主角人设立起来
3. 情绪浓度:至少一处能让读者产生强烈情绪
4. 节奏推进:本章至少推进了一个核心矛盾
5. 对话张力:对话话里有话
6. 钩子密度:每 500 字至少一个小钩子
7. 反套路指数:是否有打破读者预期的情节或台词
8. 结尾余味:最后一句让人想立刻翻下一章
9. 画面感:至少一个画面能让读者"看见"
10. 降智审查:所有角色做出了符合其智商的选择

【B. 文笔检查(5 项)】
11. 单句≤25 字
12. 主语清晰
13. 五感齐全(视觉 1+听觉 1+触/嗅/味 1)
14. 细节分散植入,无集中大段描写
15. 无禁用词

【C. 笔力检查(5 项)】
16. 每 300 字一个情绪点
17. 情绪高潮符合"压 70%+爆 5%+震 25%"
18. 无形容词情绪
19. 对话写法符合 13 法(动作卡位/神态神韵/情境穿插/语义衔接/标点替代等),不靠"X说"堆砌
20. 结尾一句能截图

【D. 段落结构检查(4 项)】
21. 每段只做一件事
22. 每段视角锁同一人
23. 每段能用一句话概括
24. 节奏匹配场景类型

【E. 逻辑完整性(5 项)】
25. 因果链完整
26. 关键信息前置
27. 新人物出场有因果
28. 对话触发有原因
29. 关键行为有动机

【F. 人物关系与称呼(3 项)】(归并到 30 项)
30. 称呼与关系匹配、关系变化有交代

【G. 八大坑专项(8 项,任一不过强烈扣分)】
31. K1 视角统一:一段内视角不跳(只锁一个观察主体)
32. K2 对话有效:每句对话至少满足 推剧情/立人设/藏信息 之一
33. K3 爽点付费:本章爽点有代价/铺垫/规则,无强行开挂
34. K4 主角主动:主角有清晰目标 + 即时行动,不全程被推
35. K5 反派合理:反派有立场+目标,智商在线
36. K6 无毒点:无三观别扭/角色降智/强行虐主/尴尬煽情
37. K7 节奏紧凑:开篇 3 段内进入冲突,无大段写景/回忆/念设定
38. K8 市场意识:符合目标平台调性,有明确爽点/钩子,非自嗨

【章节正文】
{content}

【输出格式】严格 JSON,不要 markdown 包装:
{{
  "score": <0-100 整数>,
  "pass": <true/false>,
  "failed_items": [<未通过条目编号>],
  "advice": "<修改建议简述,200 字以内>",
  "K_scores": {{<K1-K8 每项 0-10 分>}},
  "K_worst": [<最严重的 2-3 个 K>],
  "K_verdict": "<八大坑总评 1 句>"
}}
"""


# ============================================================
# 九、螺旋阶段诊断 prompt(Part 3.3)
# ============================================================
SPIRAL_DIAGNOSE_PROMPT_TPL = """\
你是【盘古·螺旋诊断师】。判定以下章节处于 P1-P7 哪个阶段。

判定依据:
- P1 量变铺垫:日常/过渡/回家/吃饭/修炼/赶路/见面/醒来,情绪 30-50
- P2 量变压抑:被嘲讽/被无视/吃亏/忍/憋屈/被抢/被压,情绪 30→60-70
- P3 临界:忍不住了/时机到了/动手/站起来/冷笑/开口/终于/够了,情绪 70→85
- P4 质变爆发:打脸/反击/碾压/秒杀/身份暴露/亮底牌,情绪 85→100
- P5 否定落地:打完/收手/跪下/认错/跑了/从此/再也不敢,情绪 100→60-70
- P6 否定被否(可选):输了/没打过/计划失败/没想到/中计,情绪 60→40
- P7 更高层次量变:战后/事后/新身份/换地方/搬家,情绪 40-50

【章节正文】
{content}

【输出格式】严格 JSON:
{{"phase": "P<1-7>", "emotion_value": <0-100>, "next_phase": "P<1-7>", "advice": "下章应往哪个阶段推进"}}
"""


# ============================================================
# 十、核心引擎
# ============================================================
class PanguEngine:
    """盘古系统的统一入口。可被 MainWindow 持有为 self.pangu。"""

    VERSION = "1.0"

    def __init__(self, enabled: bool = True, full_spec_path: Optional[Path] = None):
        """
        :param enabled: 主开关。False 时 wrap_prompt 直接返回原 prompt,实现完全旁路。
        :param full_spec_path: 完整 4.8 万字 spec 的路径(可选)。仅在 /帮助 或首次激活时被读取。
        """
        self.enabled = bool(enabled)
        self._full_spec_path = full_spec_path
        self._full_spec_cache: Optional[str] = None

    # ----- 主 API:包裹任意提示词 -----
    def wrap_prompt(
        self,
        base_prompt: str,
        scenario: str = "chapter",
        ctx: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        把原 PROMPTS[xxx] 渲染好的提示词加上盘古铁律头+输出格式尾。

        :param base_prompt: 已经 .format() 完毕的原提示词字符串
        :param scenario: 场景标识,决定追加哪些尾部块。可选值:
                         'chapter'      - 单章正文(头+尾+格式)
                         'golden_three' - 黄金三章(头+黄金三章公式+格式)
                         'outline'      - 全大纲(头+螺旋大纲规范)
                         'inspiration'  - 创意灵感(轻头,无尾)
                         'optimize'     - 润色(轻头,无尾)
                         'title'        - 书名(完全旁路)
                         'intro'        - 简介(完全旁路)
                         其他           - 头,无尾
        :param ctx: 上下文,目前可用键:
                    'platform' (番茄小说/起点中文网/晋江文学城)
                    'chapter_num' (int)
                    'show_options' (bool, 默认 True 给三选一)
        """
        if not self.enabled:
            return base_prompt

        ctx = ctx or {}
        head = PANGU_CORE_RULES
        body = base_prompt
        tail_parts: List[str] = []

        if scenario in ("title", "intro"):
            # 这两类是非正文输出,盘古完全旁路,避免污染
            return base_prompt

        if scenario == "inspiration":
            # 创意灵感只要一句话,只用轻量提示
            return (
                "你是【盘古】写作引擎(精简版),请遵守:\n"
                "- 禁用反光/影子/另一个自己题材\n"
                "- 禁止血腥/暴力/色情/侮辱女性\n"
                "- 一句话核心,20 字以内\n\n"
                + base_prompt
            )

        if scenario == "optimize":
            head = (
                "# ===== 盘古·雕刻家模式 =====\n"
                + MODE_PROMPTS["sculptor"]
                + "\n禁用词列表参见盘古铁律:顿时/连忙/显然/似乎/或许/可能/一定/十分/几乎...\n\n"
                "# ===== 任务 =====\n"
            )

        elif scenario == "golden_three":
            tail_parts.append(GOLDEN_THREE_FORMULA)
            tail_parts.append(chapter_output_format(1, show_options=False))

        elif scenario == "outline":
            tail_parts.append(SPIRAL_OUTLINE_SPEC)

        elif scenario == "chapter":
            ch_num = int(ctx.get("chapter_num", 1) or 1)
            show_opts = bool(ctx.get("show_options", True))
            tail_parts.append(chapter_output_format(ch_num, show_options=show_opts))

        # 平台对齐(可选,只在 chapter/golden_three 上加)
        platform = (ctx.get("platform") or "").strip()
        if platform and scenario in ("chapter", "golden_three"):
            platform_hint = self._platform_hint(platform)
            if platform_hint:
                tail_parts.append(platform_hint)

        return head + "\n" + body + ("\n" + "\n".join(tail_parts) if tail_parts else "")

    @staticmethod
    def _platform_hint(platform: str) -> str:
        if "番茄" in platform:
            return (
                "【平台:番茄】\n"
                "- 每章 2000-2500 字\n"
                "- 对话占比≥50%\n"
                "- 黄金三章+循环爽点+每章钩子,节奏快、爽点密"
            )
        if "起点" in platform:
            return (
                "【平台:起点】\n"
                "- 每章 2500-3000 字\n"
                "- 对话占比 30%-50%\n"
                "- 世界观宏大+升级体系清晰+伏笔深远"
            )
        if "晋江" in platform:
            return (
                "【平台:晋江】\n"
                "- 情感细腻+人物弧光+甜虐有度\n"
                '- 心理描写有度,但仍守"情绪直给"铁律'
            )
        return ""

    # ----- 风格自动匹配 -----
    def match_style(
        self,
        keywords: str,
        topk: int = 3,
    ) -> List[Dict[str, str]]:
        """
        根据题材/灵感关键词命中风格库,返回排序后的候选(最多 topk 条)。
        关键词大小写不敏感、中文按子串匹配。
        """
        keywords = (keywords or "").lower()
        scored: List[Tuple[int, Dict[str, str]]] = []
        for row in STYLE_MAPPING:
            kws = row["kw"].split("|")
            hits = sum(1 for k in kws if k.lower() in keywords)
            if hits:
                scored.append((hits, row))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:topk]]

    def build_style_report(self, keywords: str) -> str:
        """生成可直接显示给用户的"风格匹配报告"文本。"""
        matches = self.match_style(keywords)
        if not matches:
            return "未匹配到风格库条目,将使用默认组合(神级正文 V2.0 + 适中节奏)"
        lines = [f"🎯 风格匹配报告(关键词: {keywords[:60]})\n"]
        for i, m in enumerate(matches, 1):
            lines.append(
                f"{i}. 主风格: {m['main']} | 辅风格: {m['sub']} | 点缀: {m['accent']} "
                f"| 女角色基调: {m['female']} | 适合平台: {m['platform']}"
            )
        return "\n".join(lines)

    # ----- 其他辅助 prompt -----
    def build_quality_check_prompt(self, content: str) -> str:
        return QUALITY_CHECK_PROMPT_TPL.format(content=content)

    def build_mode_switch_prompt(self, mode: str, content: Optional[str] = None) -> str:
        mode = mode.lower().strip().lstrip("/")
        # 中文别名
        aliases = {
            "建筑师": "architect",
            "造梦师": "dreamweaver",
            "炼金术士": "alchemist",
            "雕刻家": "sculptor",
        }
        mode = aliases.get(mode, mode)
        if mode not in MODE_PROMPTS:
            raise ValueError(
                f"未知模式 '{mode}',可选: architect/dreamweaver/alchemist/sculptor "
                "或中文 建筑师/造梦师/炼金术士/雕刻家"
            )
        out = MODE_PROMPTS[mode]
        if content:
            out = out + "\n\n【任务内容】\n" + content
        return out

    def build_spiral_diagnose_prompt(self, content: str) -> str:
        return SPIRAL_DIAGNOSE_PROMPT_TPL.format(content=content)

    # ----- Phase C-1:章节段落差异化(防 AI 套路化) -----
    def build_seed_variation_block(self, chapter_num: int, recent_chapters=None) -> str:
        # 基于章节号生成差异化参数提示块,塞进 prompt 让 AI 每章用不同的写法
        import random
        seed_base = chapter_num * 1000
        if recent_chapters:
            for ch in recent_chapters[-2:]:
                seed_base += sum(ord(c) for c in (ch or "")[:20]) % 997
        rng = random.Random(seed_base)

        openings = [
            "对话开场(主角和某人正在说话,直接进入冲突或线索)",
            "动作开场(主角正在做某事,身体感觉/动作描写起手)",
            "内心独白开场(主角的情绪/思考/回忆切入)",
            "环境特写开场(雨/雪/光/声/嗅觉一个具体细节起手)",
            "倒叙开场(从一个未来场景倒回当下)",
            "对比开场(两个场景平行剪辑或大小对比)",
        ]
        rhythms = [
            "前慢后快(前 1/3 铺垫,后 2/3 推进+爆发)",
            "前快后慢(开篇就冲突,后半深入情绪)",
            "匀速推进(整章保持中速,靠细节堆叠)",
            "三幕节奏(铺垫-发酵-反转,均匀三段)",
            "波浪式(小高潮-喘息-大高潮)",
        ]
        sensories = [
            "视觉主导(光影/色彩/形体/距离描写优先)",
            "听觉主导(声音/对话/环境音/沉默优先)",
            "触觉主导(温度/压力/材质/疼痛优先)",
            "嗅觉味觉主导(气味/味道/呼吸优先)",
            "通感混合(两种以上感官交替,适合情绪段)",
        ]
        word_offset_pct = rng.uniform(-0.10, 0.15)

        opening = rng.choice(openings)
        rhythm = rng.choice(rhythms)
        sensory = rng.choice(sensories)

        block = (
            "【本章差异化参数(为防止 AI 重复套路,本章请严格遵守)】\n"
            f"  · 开篇方式:{opening}\n"
            f"  · 节奏:{rhythm}\n"
            f"  · 感官重心:{sensory}\n"
            f"  · 字数微调:目标 ±{int(word_offset_pct * 100)}%(基于章节目标)\n"
            "  · 切忌重复上一章的开篇句式 / 转场词 / 情绪曲线"
        )
        return block

    def get_word_count_jitter(self, chapter_num: int) -> float:
        # 返回字数浮动系数 0.90-1.10,让每章字数略有差异
        import random
        rng = random.Random(chapter_num * 1000)
        return rng.uniform(0.90, 1.10)

    def get_first_activation_banner(self) -> str:
        return FIRST_ACTIVATION_BANNER

    # ----- 本地禁用词扫描(不发 AI) -----
    # 静态词表 v2,完整对齐用户提供的 117 词清单(含组合套话)
    _FORBIDDEN_WORDS: List[str] = [
        # 副词类(AI 最高频偷懒词)
        "顿时", "连忙", "显然", "似乎", "或许", "可能", "一定", "十分", "几乎",
        "立刻", "大致", "确实", "注定", "渐渐", "更是", "略微", "猛地",
        "暂时", "不断", "瞬间", "再次", "一时之间", "看似", "看不出",
        # 形容词类(AI 套路词)
        "沉重", "淡淡", "郑重", "清淡", "纯粹", "冰冷", "清冷", "沸腾",
        "扭曲", "撕裂", "漆黑", "窒息", "剧痛", "不易察觉",
        # 比喻类
        "仿佛", "如同", "一抹", "一股", "一丝",
        # 心理活动类(AI 偷懒)
        "知道", "觉得", "意识到", "感觉到", "想", "认为", "不知道",
        # 心理活动组合套话(整词匹配,比单字更精准)
        "他知道", "她知道", "我知道",
        # 套话短语(必须整词匹配)
        "嘴角勾起一抹", "眼中闪过一丝", "行云流水", "心下了然",
        "心中一凛", "心中了然", "心中一动", "心中一片平静",
        "话锋一转", "眼神深邃", "微微挑眉", "波涛汹涌",
        "脸上带着笑意", "脸上堆满了笑", "深吸一口气", "缓缓地说",
        "锐利的眼睛", "嘴角微微上扬", "不容置疑", "目光扫过",
        "沉吟", "沉吟片刻", "隐隐有了猜测", "不动声色", "小心翼翼",
        "不卑不亢", "显得异常清晰", "显得更加", "平静地", "激动地",
        "眼神热切", "目光里毫不遮掩", "果然", "口吻", "带着",
        # 主谓套话(AI 写人物反应最爱用)
        "显得有些兴奋", "淡淡地", "淡淡地应了一句",
        "他的嘴角微微上扬", "他的表情变暗", "他的心一跳", "他的脸变了",
        "心里隐隐有了猜测",
        # 程度副词(过度修饰)
        "至关重要", "显著", "绝对", "不可估量", "无法想象",
        "无法用言语形容", "此刻", "恐怕", "这一刻", "这一次",
        # 微小动作(AI 高频)
        "嘴角", "脸色", "紧锁",
        # 其他过度词
        "电弧", "闪烁", "裹挟", "有点",
        # 通用词的"组合短语"形式(单字误杀风险大,只禁组合)
        # 注意:"坚定" / "心中" / "像" / "有点" 本身常用,
        # 真正违规是 "坚定的眼神" / "心中XX" 这种套话,所以只列组合形式
        "坚定的眼神", "坚定的目光",
        "的眼神", "的目光",  # 这俩短到极致,但确实是 AI 套话模式
    ]

    # 用户自定义白名单(运行时通过 set_whitelist 注入,避免误杀)
    _whitelist: set = set()

    @classmethod
    def set_whitelist(cls, words):
        """设置白名单(空格/换行分隔的词列表)。被白名单覆盖的词不计入禁用词。"""
        if isinstance(words, str):
            words = re.split(r"\s+", words.strip())
        cls._whitelist = {w.strip() for w in words if w and w.strip()}

    @classmethod
    def get_whitelist(cls):
        return sorted(cls._whitelist)

    @classmethod
    def get_active_forbidden_words(cls):
        """实际生效的禁用词(剔除白名单)。"""
        return [w for w in cls._FORBIDDEN_WORDS if w not in cls._whitelist]

    @classmethod
    def detect_forbidden_words(cls, text: str) -> List[Tuple[str, int]]:
        """
        本地静态扫禁用词。返回 [(词, 出现次数), ...],按出现次数降序。
        用于章节生成完成后的本地预检(不消耗 token)。
        """
        if not text:
            return []
        hits: Dict[str, int] = {}
        wl = cls._whitelist
        for w in cls._FORBIDDEN_WORDS:
            if w in wl:
                continue
            c = text.count(w)
            if c > 0:
                hits[w] = c
        return sorted(hits.items(), key=lambda x: -x[1])

    @classmethod
    def quick_chapter_lint(cls, text: str) -> Dict[str, object]:
        """
        本地快速 lint:扫禁用词 + 长句检测 + 段落长度统计。
        不调用 AI,纯字符串/正则。
        返回 dict 含 score(0-100)、issues(list)。
        """
        issues: List[str] = []
        score = 100

        if not text or not text.strip():
            return {"score": 0, "issues": ["内容为空"], "stats": {}}

        # 1. 禁用词
        forbidden = cls.detect_forbidden_words(text)
        if forbidden:
            top = ", ".join(f"{w}×{c}" for w, c in forbidden[:5])
            issues.append(f"出现禁用词: {top}")
            score -= min(40, sum(c for _, c in forbidden) * 2)

        # 2. 长句(单句>25 字,以中文逗号/句号/问号/感叹号/分号/省略号为切分)
        sents = re.split(r"[,，。!?!?;；\n]", text)
        long_sents = [s.strip() for s in sents if len(s.strip()) > 25]
        if long_sents:
            issues.append(f"长句(>25 字)数量: {len(long_sents)} 句")
            score -= min(20, len(long_sents))

        # 3. 段落长度(每段>3 句视为超标)
        paragraphs = [p for p in text.split("\n") if p.strip()]
        over_paragraphs = []
        for i, p in enumerate(paragraphs, 1):
            sents_in_p = re.split(r"[。!?!?]", p)
            sents_in_p = [s for s in sents_in_p if s.strip()]
            if len(sents_in_p) > 3:
                over_paragraphs.append(i)
        if over_paragraphs:
            issues.append(f"超 3 句的段落: 第 {over_paragraphs[:6]} 段")
            score -= min(15, len(over_paragraphs))

        # 4. 破折号检测(盘古禁用)
        if "——" in text or "—" in text:
            cnt = text.count("——") + text.count("—") - text.count("——") * 2  # 单破折号
            if cnt < 0:  # 修正:含双破折号
                cnt = (text.count("——")) + max(0, text.count("—") - text.count("——") * 2)
            issues.append(f"出现破折号(盘古禁用,应改用逗号/句号/省略号)")
            score -= 5

        # 5. 三连点省略号(盘古要求六连点 ......)
        if re.search(r"(?<!\.)\.{3}(?!\.)", text) or "…" in text:
            issues.append("省略号未用六连点(......)")
            score -= 5

        score = max(0, score)
        return {
            "score": score,
            "pass": score >= 70,
            "issues": issues,
            "stats": {
                "chars": len(text),
                "paragraphs": len(paragraphs),
                "long_sentences": len(long_sents),
                "forbidden_word_kinds": len(forbidden),
            },
        }

    # ----- 完整 spec 懒加载 -----
    def get_full_spec(self) -> str:
        """读取完整 4.8 万字 Pangu spec(用于 /帮助 命令)。失败返回空字符串。"""
        if self._full_spec_cache is not None:
            return self._full_spec_cache
        if not self._full_spec_path:
            # 默认尝试同目录下的 pangu_full_spec.md
            here = Path(__file__).parent
            cand = here / "pangu_full_spec.md"
            if cand.exists():
                self._full_spec_path = cand
        if self._full_spec_path and self._full_spec_path.exists():
            try:
                self._full_spec_cache = self._full_spec_path.read_text(encoding="utf-8")
            except Exception:
                self._full_spec_cache = ""
        else:
            self._full_spec_cache = ""
        return self._full_spec_cache


# ============================================================
# 十一、便捷工厂(供 novel_ai.py 极简集成)
# ============================================================
_default_engine: Optional[PanguEngine] = None


def get_default_engine() -> PanguEngine:
    """单例。novel_ai.py 可直接 `from pangu_system import get_default_engine`。"""
    global _default_engine
    if _default_engine is None:
        _default_engine = PanguEngine(enabled=True)
    return _default_engine


def wrap(base_prompt: str, scenario: str = "chapter", **ctx) -> str:
    """函数式快捷方式:`wrap(prompt, 'chapter', platform='番茄小说', chapter_num=12)`"""
    return get_default_engine().wrap_prompt(base_prompt, scenario, ctx)


__all__ = [
    "PanguEngine",
    "PANGU_CORE_RULES",
    "STYLE_MAPPING",
    "GOLDEN_THREE_FORMULA",
    "SPIRAL_OUTLINE_SPEC",
    "MODE_PROMPTS",
    "FIRST_ACTIVATION_BANNER",
    "QUALITY_CHECK_PROMPT_TPL",
    "SPIRAL_DIAGNOSE_PROMPT_TPL",
    "chapter_output_format",
    "get_default_engine",
    "wrap",
]
