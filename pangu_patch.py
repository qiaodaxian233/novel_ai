#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘古·零侵入安装器
==================================
让你只用 3 行就把【盘古超级系统】套到现有的 novel_ai.py 上。

集成步骤(在 novel_ai.py 的 PROMPTS 字典定义之后,加这一段):

    # ---- 盘古超级系统(新增) ----
    try:
        from pangu_patch import install_pangu
        install_pangu(globals())  # 把 PROMPTS 字典就地套上盘古铁律
        PANGU_AVAILABLE = True
    except ImportError:
        PANGU_AVAILABLE = False

就这样。原来怎么调 PROMPTS["chapter"].format(...) 现在还怎么调,
只是发给 AI 的字符串前后多了盘古铁律+输出格式+模式头。

任何时候想关掉,把 install_pangu(globals()) 注释掉或改成
install_pangu(globals(), enabled=False) 即可,行为完全回到原版。

要事后撤销 patch:uninstall_pangu(globals())  → 恢复原 PROMPTS 字典。
"""

from __future__ import annotations
from typing import Dict, Any, Iterable, Optional


# 哪些原 PROMPTS 键需要被盘古包裹,以及对应的场景标识
DEFAULT_SCENARIO_MAP: Dict[str, str] = {
    "chapter":              "chapter",
    "golden_three":         "golden_three",
    "outline_full":         "outline",
    "outline_part":         "outline",
    "ai_optimize":          "optimize",
    "creative_inspiration": "inspiration",
    # title / intro / chapter_summary / character_extract /
    # long_term_extract / canon_audit / canon_extract /
    # critique_rhythm / critique_character —— 这些是工具型 prompt,
    # 不需要盘古铁律污染。默认保持原样。
}


def install_pangu(
    g: Dict[str, Any],
    *,
    enabled: bool = True,
    keys: Optional[Iterable[str]] = None,
    show_options_in_chapter: bool = True,
) -> bool:
    """
    把 PROMPTS 字典里指定的几个键就地包上盘古铁律。

    :param g: 调用方的 globals() —— 用于定位 PROMPTS 字典
    :param enabled: False 时什么都不做(便于通过外部 settings 关闭)
    :param keys: 只 patch 这些键。None 表示按 DEFAULT_SCENARIO_MAP 全部 patch
    :param show_options_in_chapter: 章节末尾是否要"下一章三选一"。
                                    番茄/起点连续生成时建议 False
                                    (避免 AI 多输出 200 字废稿)
    :returns: True 表示成功 patch
    """
    if not enabled:
        g["_PANGU_INSTALLED"] = False
        return False

    PROMPTS = g.get("PROMPTS")
    if PROMPTS is None or not isinstance(PROMPTS, dict):
        raise RuntimeError(
            "install_pangu: 在 globals() 里没找到 PROMPTS 字典。"
            "请在 PROMPTS = {...} 之后调用 install_pangu(globals())。"
        )

    # 必须 import 成功;失败让上层 except ImportError 抓
    from pangu_system import (
        PANGU_CORE_RULES,
        GOLDEN_THREE_FORMULA,
        SPIRAL_OUTLINE_SPEC,
        MODE_PROMPTS,
        chapter_output_format,
    )

    # 备份原 PROMPTS(支持后续 uninstall)
    if "_PANGU_ORIG_PROMPTS" not in g:
        g["_PANGU_ORIG_PROMPTS"] = dict(PROMPTS)

    scenario_map = DEFAULT_SCENARIO_MAP
    if keys is not None:
        keys_set = set(keys)
        scenario_map = {k: v for k, v in DEFAULT_SCENARIO_MAP.items() if k in keys_set}

    head = PANGU_CORE_RULES + "\n"
    tail_chapter = "\n" + chapter_output_format(1, show_options=show_options_in_chapter)
    tail_golden = (
        "\n" + GOLDEN_THREE_FORMULA + "\n"
        + chapter_output_format(1, show_options=False)
    )
    tail_outline = "\n" + SPIRAL_OUTLINE_SPEC

    patched: list = []
    for key, scenario in scenario_map.items():
        if key not in PROMPTS:
            continue
        original = PROMPTS[key]

        if scenario == "chapter":
            PROMPTS[key] = head + original + tail_chapter
        elif scenario == "golden_three":
            PROMPTS[key] = head + original + tail_golden
        elif scenario == "outline":
            PROMPTS[key] = head + original + tail_outline
        elif scenario == "optimize":
            PROMPTS[key] = (
                "# ===== 盘古·雕刻家模式 =====\n"
                + MODE_PROMPTS["sculptor"]
                + "\n# ===== 任务 =====\n"
                + original
            )
        elif scenario == "inspiration":
            PROMPTS[key] = (
                "你是【盘古】写作引擎(精简版),请遵守:\n"
                "- 禁用反光/影子/另一个自己题材\n"
                "- 禁止血腥/暴力/色情/侮辱女性\n"
                "- 一句话核心,20 字以内\n"
                "- 禁用形容词定义情绪,只用直给情绪词\n\n"
                + original
            )
        else:
            # 未识别的 scenario,只加头不加尾
            PROMPTS[key] = head + original

        patched.append(key)

    g["_PANGU_INSTALLED"] = True
    g["_PANGU_PATCHED_KEYS"] = patched
    return True


def uninstall_pangu(g: Dict[str, Any]) -> bool:
    """撤销 install_pangu,把 PROMPTS 字典恢复到原样。"""
    orig = g.get("_PANGU_ORIG_PROMPTS")
    PROMPTS = g.get("PROMPTS")
    if orig is None or PROMPTS is None:
        return False
    PROMPTS.clear()
    PROMPTS.update(orig)
    g["_PANGU_INSTALLED"] = False
    return True


def is_installed(g: Dict[str, Any]) -> bool:
    return bool(g.get("_PANGU_INSTALLED"))


__all__ = ["install_pangu", "uninstall_pangu", "is_installed", "DEFAULT_SCENARIO_MAP"]
