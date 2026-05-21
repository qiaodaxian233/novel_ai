# -*- coding: utf-8 -*-
"""core/default_skills.py - 默认写作技能模板列表

v2.03 P4 拆分:从 novel_ai.py 第 2679-2738 行整体搬运,内容零修改。
"""

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
