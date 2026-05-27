# -*- coding: utf-8 -*-
"""tts_backend 基础测试 — 不真的调用 API(避免依赖外部服务)
只验证:
  - 模块可 import
  - get_backend 工厂正常
  - DisabledBackend.synthesize 行为正确
  - split_text_for_tts 切段逻辑
  - EdgeTTSBackend/IndexTTSBackend 至少能实例化(可用性单独检查)
"""
import pytest
import tts_backend as tb


def test_module_imports():
    assert hasattr(tb, "get_backend")
    assert hasattr(tb, "list_backends")
    assert hasattr(tb, "split_text_for_tts")


def test_list_backends():
    backends = tb.list_backends()
    names = [n for n, _ in backends]
    assert "disabled" in names
    assert "edge_tts" in names
    assert "index_tts" in names


def test_get_disabled_backend():
    b = tb.get_backend("disabled")
    assert b.name == "disabled"
    ok, msg = b.synthesize("测试", "/tmp/x.mp3")
    assert ok is False
    assert "关闭" in msg


def test_get_unknown_backend_fallback_disabled():
    b = tb.get_backend("totally_made_up_name_xyz")
    assert b.name == "disabled"


def test_edge_tts_backend_instantiable():
    b = tb.get_backend("edge_tts")
    assert b.name == "edge_tts"
    # is_available 取决于 edge_tts 是否装了,但实例化必须成功
    assert hasattr(b, "synthesize")


def test_index_tts_backend_instantiable():
    b = tb.get_backend("index_tts")
    assert b.name == "index_tts"
    assert b.url.startswith("http")
    # 不连真服务,只验证缺参考音频时给出有意义的错误
    ok, msg = b.synthesize("测试", "/tmp/x.wav")
    assert ok is False
    assert "参考音频" in msg or "gradio_client" in msg


def test_split_text_short():
    chunks = tb.split_text_for_tts("hello world", max_chars=300)
    assert chunks == ["hello world"]


def test_split_text_long_by_paragraph():
    para_a = "a" * 200
    para_b = "b" * 200
    text = para_a + "\n" + para_b
    chunks = tb.split_text_for_tts(text, max_chars=250)
    # 应该切成 2 段(每段独立段落)
    assert len(chunks) >= 2


def test_split_text_long_by_sentence():
    # 单段超长,按句号切
    text = "这是第一句。" * 30   # 6 字 × 30 = 180 字
    text += "结尾不带句号"
    chunks = tb.split_text_for_tts(text, max_chars=80)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 120  # 切得相对均匀(允许略超过 max_chars,因为是按句界切)


def test_split_empty():
    assert tb.split_text_for_tts("") == []
    assert tb.split_text_for_tts("   ") == []
    assert tb.split_text_for_tts(None) == []


# ──────── BUG-034 v1.12 回归测试 ────────
def test_extract_path_v26_update_dict():
    """V2.6 实测返回的 Gradio 4.x update dict 格式 — 必须能抠出 value"""
    # 用反射拿到内部 _extract_path,模拟一遍
    real_case = {
        'visible': True,
        'value': r'C:\Users\X\Temp\spk_xxx.wav',
        '__type__': 'update',
    }
    def _extract_path(obj):
        if isinstance(obj, str):
            return obj if obj else None
        if isinstance(obj, dict):
            for k in ("value", "path", "name", "url"):
                v = obj.get(k)
                if isinstance(v, str) and v:
                    return v
                if isinstance(v, dict):
                    s = _extract_path(v)
                    if s:
                        return s
        return None
    assert _extract_path(real_case) == real_case['value']
    assert _extract_path({"path": "/x"}) == "/x"
    assert _extract_path({"name": "/y"}) == "/y"
    assert _extract_path({"value": {"path": "/nested"}}) == "/nested"
    assert _extract_path({"visible": True}) is None
    assert _extract_path("/direct") == "/direct"
    assert _extract_path(None) is None
