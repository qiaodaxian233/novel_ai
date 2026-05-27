# -*- coding: utf-8 -*-
"""
test_hook_detection.py — v1.73 章末钩子检测扩词测试

覆盖:
1. HOOK_MARKERS 数量 ≥ 60(用户反馈"经常误判"的根因是关键词太少)
2. 中文全角问号/感叹号必须被识别(v1.64 之前的 typo:'?' 重复两次都是英文 0x3f)
3. 用户实际场景:9 类网文常见章末写法都应放行
4. 真平淡叙事必须命中(false negative 不能太多)
5. 末段不足 300 字时,扩到末 300 字兜底
6. 两处调用源头(novel_ai / workflow_pipeline)都改用 PanguEngine.check_chapter_has_hook
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
NOVEL_AI_PY = ROOT / "novel_ai.py"
WORKFLOW_PY = ROOT / "workflow_pipeline.py"


# ── 1. HOOK_MARKERS 基础健康 ───────────────────────────────
def test_hook_markers_count_sufficient():
    """关键词应该 ≥ 60(v1.64 旧版只有 14 个,误判率高)"""
    from pangu_system import PanguEngine
    n = len(PanguEngine.HOOK_MARKERS)
    assert n >= 60, f"HOOK_MARKERS 应 ≥ 60,实际 {n}"


def test_hook_markers_no_duplicates():
    """无重复项(v1.64 旧版有 '?' 重复两次的 typo bug)"""
    from pangu_system import PanguEngine
    markers = PanguEngine.HOOK_MARKERS
    assert len(markers) == len(set(markers)), \
        f"HOOK_MARKERS 有重复:{[m for m in set(markers) if markers.count(m) > 1]}"


def test_hook_markers_includes_chinese_punctuation():
    """中文全角问号/感叹号必须在内(v1.64 之前的 typo 让全角问号一直没被检测)"""
    from pangu_system import PanguEngine
    markers = PanguEngine.HOOK_MARKERS
    assert "\uff1f" in markers, "中文全角问号 ?(\\uff1f)应在 HOOK_MARKERS"
    assert "\uff01" in markers, "中文全角感叹号 !(\\uff01)应在 HOOK_MARKERS"
    assert "?" in markers, "英文问号 ? 应在 HOOK_MARKERS"
    assert "!" in markers, "英文感叹号 ! 应在 HOOK_MARKERS"


# ── 2. 真实场景:用户原本误判的 9 类网文常见结尾应放行 ─────
@pytest.mark.parametrize("name,text", [
    ("强情绪决断",   "林远握紧拳头,该上路了。"),
    ("神秘人出现",   "正当此时,一个黑影从林中走出。"),
    ("时间跳转",     "三日后,他终于到了那座城。"),
    ("场景切换",     "与此同时,千里之外的天剑宗,惊起一阵涟漪。"),
    ("情绪留白",     "他望着远方的星空,陷入沉思。"),
    ("不祥预感",     "他心中升起一股不祥的预感。"),
    ("反转",         "可是谁料,事情并非如此简单。"),
    ("强情绪+省略号", "他咬牙切齿……"),
    ("决心",         "他暗下决心,从此他将变得不一样。"),
    ("中文全角问号", "\u4ed6\u4f1a\u8d62\u5417\uff1f"),  # 他会赢吗?
    ("中文全角叹号", "\u201c\u6765\u554a\uff01\u201d"),  # "来啊!"
])
def test_common_hook_writing_styles_pass(name, text):
    """这些是用户被误判触发死磕的常见结尾,新规则应识别为有钩子"""
    from pangu_system import PanguEngine
    assert PanguEngine.check_chapter_has_hook(text), \
        f"'{name}' 应识别为有钩子: {text!r}"


# ── 3. 真平淡叙事必须命中(避免假阳性失控) ────────────────
@pytest.mark.parametrize("name,text", [
    ("纯写景平淡", "天色渐晚,城里点起了灯。街上的人慢慢稀少。狗叫声此起彼伏。"),
    ("test_v6 旧反例", "平淡的结尾,没有任何悬念。" * 50),
])
def test_truly_boring_text_caught(name, text):
    """这些是真没钩子的文本,必须能识别出来触发死磕"""
    from pangu_system import PanguEngine
    assert not PanguEngine.check_chapter_has_hook(text), \
        f"'{name}' 应识别为缺钩子(否则真问题被放过): {text[:60]!r}"


# ── 4. 末段扩展兜底 ───────────────────────────────────────
def test_short_last_paragraph_extends_to_300_chars():
    """末段太短(对话短句结尾)时,扩到末 300 字兜底,避免漏掉前一段的钩子"""
    from pangu_system import PanguEngine
    # 末段只有 "他知道了。" 5 字,但前面段落有"望着""陷入"
    text = ("(章节正文很多内容,中间他望着远方陷入了沉思,一切难以言说)" * 5
            + "\n\n他知道了。")
    assert PanguEngine.check_chapter_has_hook(text), \
        "末段过短时应扩到末 300 字,前段的钩子词不该被漏"


def test_empty_text():
    """空内容判定为缺钩子"""
    from pangu_system import PanguEngine
    assert not PanguEngine.check_chapter_has_hook("")
    assert not PanguEngine.check_chapter_has_hook(None or "")


# ── 5. 两处调用源头统一(防 v1.64 typo 那种"两处不一致" BUG) ──
def test_novel_ai_uses_pangu_check():
    """novel_ai.py 的 _check_chapter_quality 必须调 PanguEngine.check_chapter_has_hook,
    不能再有本地的 hook_markers tuple(否则两处维护漂移)"""
    src = NOVEL_AI_PY.read_text(encoding="utf-8")
    # 找 _check_chapter_quality 里的钩子检测段
    # 关键标识:必须 import PanguEngine 然后调 check_chapter_has_hook
    m = re.search(
        r"#\s*2\.\s*章末钩子.*?(?=#\s*3\.|def )",
        src, re.DOTALL
    )
    assert m, "找不到 _check_chapter_quality 里的钩子检测段"
    block = m.group(0)
    assert "check_chapter_has_hook" in block, \
        "novel_ai 应调 PanguEngine.check_chapter_has_hook,不应自己维护 hook_markers"
    # 反向断言:不能有大段自己定义的 markers tuple
    assert "hook_markers = (" not in block, \
        "novel_ai 不应再自己定义 hook_markers tuple(应该用 pangu_system 的)"


def test_workflow_pipeline_uses_pangu_check():
    """workflow_pipeline.py 的 HookCheckStep 必须调 PanguEngine.check_chapter_has_hook"""
    src = WORKFLOW_PY.read_text(encoding="utf-8")
    m = re.search(
        r"class HookCheckStep.*?(?=^class |\Z)",
        src, re.DOTALL | re.MULTILINE
    )
    assert m, "找不到 HookCheckStep 类"
    block = m.group(0)
    assert "check_chapter_has_hook" in block, \
        "HookCheckStep 应调 PanguEngine.check_chapter_has_hook"
    assert "_MARKERS = (" not in block, \
        "HookCheckStep 不应再自己定义 _MARKERS tuple"


# ── 6. APP_VERSION ≥ v1.73 ───────────────────────────────
def test_app_version_at_least_v1_73():
    """v1.73 是钩子扩词修复版本,APP_VERSION 必须 ≥ v1.73"""
    src = NOVEL_AI_PY.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']v(\d+)\.(\d+)["\']', src)
    assert m, "找不到 APP_VERSION 声明"
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 73), f"APP_VERSION 应 ≥ v1.73,实际 v{major}.{minor}"
