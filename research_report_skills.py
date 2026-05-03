# -*- coding: utf-8 -*-
"""
research_report_skills.py — 深度研究报告 §6 的 4 个 AI 模板，
                            实例化为 NovelAI 出厂技能配置。

模板编号对应深度研究报告 §6:
  模板一 细纲扩展      → 写章前
  模板二 桥段扩写      → 写章中
  模板三 一致性校验    → 写章后（红黄绿三档审校）
  模板四 短文本生成    → 章尾钩 / 高潮片段 / 宣传文案
  额外  高潮自动重写   → auto_match 配套（让 auto_match 不浪费）

每条配置严格遵守 SkillLibrary 的 schema:
  name / when / trigger_pattern / prompt / target / enabled

接入方式（一行）:
    from research_report_skills import RESEARCH_REPORT_SKILLS, install_into
    install_into(self.tab_skills)
"""
from __future__ import annotations
import copy
import re
from typing import Iterable

# 合法字段值（与 SkillLibrary UI 选项一一对应）
VALID_WHEN = {"manual", "after_chapter_generation", "auto_match"}
VALID_TARGET = {"current_chapter", "selected_text", "log_only", "append_to_canon"}


# ============================================================
# 5 条出厂技能（4 个研究模板 + 1 个 auto_match 配套）
# ============================================================

RESEARCH_REPORT_SKILLS = [
    # ----------------------------------------------------------------
    # 1. 细纲扩展（手动，写章前）
    # ----------------------------------------------------------------
    {
        "name": "细纲扩展（写章前）",
        "when": "manual",
        "trigger_pattern": "",
        "prompt": (
            "你现在只做「细纲扩展」，不写整章。\n\n"
            "下面是用户提供的本章上下文（请在 {content} 里识别这 5 项；"
            "若缺项请在输出末尾用「待作者确认」列出）：\n"
            "  1. 卷目标\n"
            "  2. 本章前情\n"
            "  3. 本场景必须完成的事情\n"
            "  4. 角色当前情绪\n"
            "  5. 不可新增的设定\n\n"
            "用户输入：\n{content}\n\n"
            "请按以下结构输出：\n"
            "A. 本章目标（1 句话）\n"
            "B. 冲突来源（外部冲突 + 角色内心张力，2-3 句）\n"
            "C. 转折点（在第几段触发，触发条件是什么，1-2 句）\n"
            "D. 代价体现（主角因这一步付出了什么，1-2 句）\n"
            "E. 章尾钩（一句反常的话 / 一处伤口 / 一段被篡改的记忆，1 句）\n\n"
            "限制：\n"
            "- 总字数 300-600 字\n"
            "- 不新增世界观设定\n"
            "- 如必须新增，请单列「待作者确认」\n"
            "- 不写整段正文，只列结构与核心句"
        ),
        "target": "log_only",
        "enabled": True,
    },

    # ----------------------------------------------------------------
    # 2. 桥段扩写（手动，可写回选中文本）
    # ----------------------------------------------------------------
    {
        "name": "桥段扩写（局部 600-1000 字）",
        "when": "manual",
        "trigger_pattern": "",
        "prompt": (
            "你现在只做「局部扩写」，不改剧情去向。\n\n"
            "用户在 {content} 里给出 beat 列表与人物口吻要求，请按下列约定执行：\n\n"
            "用户输入（含 beat 与人设要求）：\n{content}\n\n"
            "解读规则：\n"
            "1. beat 通常按以下顺序给出（缺项跳过即可）：\n"
            "   压迫 / 误判 / 反转 / 爽点 / 下一章悬念\n"
            "2. 人物口吻要求若给出，请严格保持\n"
            "3. 任何未给出的设定不得自行新增\n\n"
            "输出要求：\n"
            "- 总字数 600-1000 字（按场景密度自适应）\n"
            "- 只写这一个场景，不要跨场景跳转\n"
            "- 必须包含动作、感官、对话三类描写\n"
            "- 严禁替作者决定新设定 / 新人物 / 新地点\n"
            "- 直接输出扩写后的正文，不要任何前后缀，不要 markdown\n\n"
            "请输出："
        ),
        "target": "selected_text",
        "enabled": True,
    },

    # ----------------------------------------------------------------
    # 3. 一致性校验（红黄绿，after_chapter_generation 自动）
    # ----------------------------------------------------------------
    {
        "name": "一致性校验（红黄绿三档）",
        "when": "after_chapter_generation",
        "trigger_pattern": "",
        "prompt": (
            "你现在是「连续性编辑」，不是作者。\n"
            "请对下面这一章做红黄绿三档审校。三档定义：\n"
            "  🔴 红：明确冲突 — 与既有设定 / 时间线 / 寿元规则 / 人设直接矛盾\n"
            "  🟡 黄：可能冲突 — 需作者确认（含信息可得性可疑、动机跳变嫌疑）\n"
            "  🟢 绿：无冲突但值得记录的新增信息（人物、地点、关系、伏笔等）\n\n"
            "审查维度：\n"
            "1. 时间线（路程 / 伤势恢复 / 跨场景日数）\n"
            "2. 寿元代价（如启用了寿元台账，本章施术次数与折寿是否合理）\n"
            "3. 角色动机（与上章相比有无无理由跳变）\n"
            "4. 伏笔回收 / 新增（哪些坑这章碰了 / 抛了）\n"
            "5. 风格一致性（人物口吻是否偏离）\n\n"
            "本章正文：\n{content}\n\n"
            "请输出（严格按以下格式，每条≤80 字）：\n"
            "🔴 红：\n"
            "  - …（无则写「无」）\n"
            "🟡 黄：\n"
            "  - …（无则写「无」）\n"
            "🟢 绿：\n"
            "  - …（无则写「无」）\n"
            "建议追加到设定库：\n"
            "  - …（无则写「无」）\n\n"
            "限制：总字数 200-400 字；不要写「对故事很好」这类无信息量评语。"
        ),
        "target": "log_only",
        "enabled": False,   # 默认关，开启后每章多一次 AI 调用
    },

    # ----------------------------------------------------------------
    # 4. 短文本生成（手动，章尾钩 / 高潮片段 / 宣传）
    # ----------------------------------------------------------------
    {
        "name": "短文本生成（3 版备选）",
        "when": "manual",
        "trigger_pattern": "",
        "prompt": (
            "你现在只生成「短文本」，用于章尾钩、宣传文案或高潮片段试写。\n\n"
            "用户上下文（场景目标、情绪、人设口吻）：\n{content}\n\n"
            "输出要求：\n"
            "- 严格生成 3 版备选\n"
            "- 每版 100-200 字（无论字数怎么浮动，绝不超过 200）\n"
            "- 结构必须是「压迫 → 转折 → 爽点」三段（即使一段只有一句）\n"
            "- 风格偏克制，不要油腻台词，不要刻意金句\n"
            "- 不新增设定、不新增人物，只调用 {content} 里出现过的元素\n\n"
            "输出格式（严格遵守）：\n"
            "【版本 1】\n"
            "（正文）\n"
            "\n"
            "【版本 2】\n"
            "（正文）\n"
            "\n"
            "【版本 3】\n"
            "（正文）"
        ),
        "target": "log_only",
        "enabled": True,
    },

    # ----------------------------------------------------------------
    # 5. 高潮场面自动重写（auto_match，配套让 auto_match 不浪费）
    # ----------------------------------------------------------------
    {
        "name": "高潮场面自动重写",
        "when": "auto_match",
        "trigger_pattern": "对峙|对决|宣战|审判|登台|登顶|拔剑|当众|揭穿|宣判|公开|当面对质",
        "prompt": (
            "本章触发了「高潮场面」自动检测，关键词命中。\n"
            "请按「压迫 → 转折 → 爽点」节奏给出 1 段 100-200 字的"
            "重写候选，仅作为日志备选，不替换原文：\n\n"
            "原文：\n{content}\n\n"
            "重写要求：\n"
            "- 100-200 字\n"
            "- 节奏顺序：先写压迫（环境 / 反派 / 形势），再写转折（主角的关键反制），"
            "最后写爽点（公共视野下的合法性反转）\n"
            "- 严禁新增角色 / 新增设定\n"
            "- 直接给出重写正文，不要前后缀，不要 markdown 代码块"
        ),
        "target": "log_only",
        "enabled": False,   # 默认关，开启后含高潮关键词章节自动触发
    },
]


# ============================================================
# Schema 校验 & 接入工具
# ============================================================

def validate_skill(skill: dict) -> list:
    """校验单条 skill 配置，返回错误列表（空 = OK）。"""
    errs = []
    if not isinstance(skill, dict):
        return ["不是 dict"]
    for k in ("name", "when", "trigger_pattern", "prompt", "target", "enabled"):
        if k not in skill:
            errs.append(f"缺字段: {k}")
    if "when" in skill and skill["when"] not in VALID_WHEN:
        errs.append(f"非法 when={skill['when']!r}")
    if "target" in skill and skill["target"] not in VALID_TARGET:
        errs.append(f"非法 target={skill['target']!r}")
    if skill.get("when") == "auto_match":
        pat = skill.get("trigger_pattern", "")
        if not pat:
            errs.append("auto_match 必须给 trigger_pattern")
        else:
            try:
                re.compile(pat)
            except re.error as e:
                errs.append(f"trigger_pattern 正则非法: {e}")
    if "prompt" in skill and "{content}" not in skill["prompt"]:
        errs.append("prompt 必须含 {content} 占位符")
    if "name" in skill and not skill["name"].strip():
        errs.append("name 不能为空")
    if "enabled" in skill and not isinstance(skill["enabled"], bool):
        errs.append("enabled 必须是 bool")
    return errs


def validate_all() -> dict:
    """对全部 RESEARCH_REPORT_SKILLS 跑校验，返回 {name: [errs]}。"""
    out = {}
    for s in RESEARCH_REPORT_SKILLS:
        errs = validate_skill(s)
        if errs:
            out[s.get("name", "?")] = errs
    return out


def install_into(skill_library, *, replace_same_name: bool = False) -> int:
    """把研究报告技能追加到 SkillLibrary 实例。

    Args:
        skill_library: NovelAI 的 SkillLibrary tab 实例（有 .skills 列表）
        replace_same_name: 已有同名技能时是否替换。默认不替换，跳过已存在的。

    Returns:
        实际新增/替换的条数。
    """
    if not hasattr(skill_library, "skills"):
        return 0
    existing_names = {s.get("name") for s in skill_library.skills}
    n_changed = 0
    for src in RESEARCH_REPORT_SKILLS:
        skill = copy.deepcopy(src)
        if skill["name"] in existing_names:
            if replace_same_name:
                # 替换同名
                for i, ex in enumerate(skill_library.skills):
                    if ex.get("name") == skill["name"]:
                        skill_library.skills[i] = skill
                        n_changed += 1
                        break
            else:
                continue
        else:
            skill_library.skills.append(skill)
            n_changed += 1
    # 如果有刷新方法（比如 list_widget 重绘），调用
    if hasattr(skill_library, "_refresh_list"):
        try:
            skill_library._refresh_list()
        except Exception:
            pass
    return n_changed


def get_skills_copy() -> list:
    """返回一份 deepcopy，方便测试 / 嵌入到 DEFAULT_SKILLS。"""
    return copy.deepcopy(RESEARCH_REPORT_SKILLS)


__all__ = [
    "RESEARCH_REPORT_SKILLS",
    "validate_skill",
    "validate_all",
    "install_into",
    "get_skills_copy",
    "VALID_WHEN",
    "VALID_TARGET",
]
