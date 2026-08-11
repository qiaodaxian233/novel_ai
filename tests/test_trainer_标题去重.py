# -*- coding: utf-8 -*-
"""trainer 数据清洗守护测试:重复章节标题去重

站点源脏数据:同一章标题连报两遍(作者中文序号一遍/站点阿拉伯序号一遍,
两个数字常对不上但标题相同)、行首隐形 BOM、装饰线。

注:trainer 依赖 torch/numpy,主项目 venv 没有 → importorskip 自动跳过,
不影响主项目 pre_push_check。
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trainer"))
from novel_trainer import data as d  # noqa: E402


DIRTY = """第一百零一章 鼎威
\ufeff第一百零一章鼎威
------------
刀口贴上脖子。
第一千八百零六章 第一世落幕
    第1843章 第一世落幕
他汗毛立起来。
第一千八百零五章 两万岁
    第1842章 两万岁
正文继续。
第一千八百零七章 新的开始
不同标题的相邻章头要保留:
第一千八百零八章 另一个标题
"""


def _clean(text):
    return d.dedup_chapter_titles(d._normalize_text(text))


def test_user_reported_samples():
    cleaned, removed = _clean(DIRTY)
    assert removed == 4
    # 三组重复各留一份(留第一个出现的)
    assert cleaned.count("鼎威") == 1
    assert cleaned.count("第一世落幕") == 1
    assert cleaned.count("两万岁") == 1
    # 站点阿拉伯序号版被删
    assert "1843" not in cleaned and "1842" not in cleaned
    # BOM 和装饰线清净
    assert "\ufeff" not in cleaned and "------------" not in cleaned


def test_different_titles_not_deleted():
    cleaned, _ = _clean(DIRTY)
    assert "新的开始" in cleaned and "另一个标题" in cleaned


def test_body_breaks_adjacency():
    """标题相同但中间隔着正文 → 不算相邻,不删(如上/下章同名的合法情况)"""
    text = "第一章 重逢\n正文一大段。\n第二章 重逢\n又一段正文。\n"
    cleaned, removed = _clean(text)
    assert removed == 0
    assert cleaned.count("重逢") == 2


def test_blank_lines_do_not_break_adjacency():
    text = "第一章 鼎威\n\n\n第1章 鼎威\n正文。\n"
    cleaned, removed = _clean(text)
    assert removed == 1 and cleaned.count("鼎威") == 1


def test_cpt_pipeline_accepts_flag():
    """prepare_cpt_dataset 签名/指纹接入 clean_titles(源码断言,不跑分词)"""
    import io
    src = io.open(Path(__file__).resolve().parent.parent
                  / "trainer/novel_trainer/data.py", encoding="utf-8").read()
    assert "clean_titles: bool = True" in src
    assert '"clean_titles": clean_titles' in src   # 进缓存指纹


def test_author_notes_stripped():
    """v2:作者留言剥除(实测污染:CPT 后试写冒出'第三更到!')"""
    text = ("第三更到!\nPS：今天有事\n求月票求推荐票!\n"
            "感谢\"书友123\"的打赏!\n正文里说他更强了不受影响。\n")
    cleaned, removed = _clean(text)
    assert removed == 4
    assert "第三更到" not in cleaned and "求月票" not in cleaned
    assert "他更强了不受影响" in cleaned      # 正文含'更'不误删


def test_strip_all_titles_mode():
    """v2:纯风格续训模式删全部章节标题行"""
    from novel_trainer import data as d
    text = "第一章 初见\n刀口贴上脖子。\n第二章 反杀\n他退了半步。\n"
    cleaned, removed = d.dedup_chapter_titles(text, strip_all_titles=True)
    assert removed == 2
    assert "第一章" not in cleaned and "第二章" not in cleaned
    assert "刀口贴上脖子" in cleaned and "他退了半步" in cleaned
