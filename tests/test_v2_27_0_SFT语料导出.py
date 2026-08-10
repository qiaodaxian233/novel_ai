# -*- coding: utf-8 -*-
"""v2.27.0 SFT 语料导出 守护测试

训练线与写作线的合流点:库内成章(=质检通过入库)配对
"本章大纲+前情摘要",导出 trainer SFT 阶段可直接用的 JSONL。
"""
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    return io.open(ROOT / rel, encoding="utf-8").read()


def _mk_chapters():
    long_a = "刀口贴上脖子。" * 200          # ≈1400 字,够长
    long_b = "他汗毛立起来,退了半步。" * 150
    return [
        {"title": "初见", "content": long_a},
        {"title": "残章", "content": "太短了。"},          # 应被跳过
        {"title": "反杀", "content": long_b},
    ]


CO = (
    "第1章 初见:主角在码头遇袭,刀口贴颈。\n"
    "第2章 过渡:养伤。\n"
    "第3章 反杀:主角设局反杀仇家,埋下解药伏笔。\n"
)


def test_build_records_basic():
    from project_io import build_sft_records
    recs, skipped = build_sft_records(
        _mk_chapters(), chapter_outline=CO,
        summaries={1: "码头遇袭", 2: "养伤蛰伏"},
        book_title="残响", genre="都市/复仇")
    assert skipped == 1 and len(recs) == 2
    r3 = recs[1]["messages"]
    assert r3[0]["role"] == "system"
    user = r3[1]["content"]
    # 章号按原始位置(第3章),不是过滤后的顺序(第2条)
    assert "第3章" in user and "《反杀》" in user
    # 本章大纲精确切片:只含第3章的,不含第1章的
    assert "设局反杀" in user and "码头遇袭,刀口贴颈" not in user
    # 前情用前两章摘要
    assert "第1章:码头遇袭" in user and "第2章:养伤蛰伏" in user
    # assistant = 原文
    assert r3[2]["role"] == "assistant" and r3[2]["content"].startswith("他汗毛")


def test_outline_slice_fallback():
    """章纲里找不到对应章号 → 退全书章纲节选;完全没章纲 → 不加该段"""
    from project_io import build_sft_records
    recs, _ = build_sft_records(_mk_chapters(), chapter_outline="只有一段没有章号的纲",
                                book_title="x", genre="y")
    assert "【全书章纲(节选)】" in recs[0]["messages"][1]["content"]
    recs2, _ = build_sft_records(_mk_chapters())
    assert "章纲" not in recs2[0]["messages"][1]["content"]


def test_records_are_valid_trainer_sft_format():
    """导出格式必须能被 trainer 的 SFT 解析器接受:
    messages 列表、每项含 role/content、最后一条是 assistant"""
    from project_io import build_sft_records
    recs, _ = build_sft_records(_mk_chapters(), chapter_outline=CO)
    for r in recs:
        line = json.dumps(r, ensure_ascii=False)
        back = json.loads(line)
        msgs = back["messages"]
        assert all("role" in m and "content" in m for m in msgs)
        assert msgs[-1]["role"] == "assistant"


def test_gui_wiring():
    src = _read("novel_ai.py")
    assert "def _export_sft_corpus" in src
    assert "build_sft_records" in src
    assert "导出SFT训练语料" in src           # 工具菜单入口
    assert "_export_sft_corpus)" in src        # triggered.connect
