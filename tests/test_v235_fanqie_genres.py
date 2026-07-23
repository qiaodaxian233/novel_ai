# -*- coding: utf-8 -*-
"""v2.23.5 守护测试:番茄题材 + 增强灵感采样

测试:
1. fanqie_genre_provider 提供分组数据(男频/女频/通用)
2. 智能题材匹配:用户输入 → 番茄真实分类
3. _gather_matched_samples 升级:更多样本 + 长简介 + 智能匹配
4. build_v233_enriched_prompt 升级:用智能匹配 + 分组展示
5. APP_VERSION 升到 v2.23.5
"""
import sys
import os
import re
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_01_genre_provider_module_exists():
    """fanqie_genre_provider 模块存在"""
    from core import fanqie_genre_provider
    assert hasattr(fanqie_genre_provider, "get_genre_groups")
    assert hasattr(fanqie_genre_provider, "match_user_genre_to_fanqie")
    assert hasattr(fanqie_genre_provider, "match_user_genres_to_fanqie")


def test_02_get_genre_groups_returns_three_groups():
    """题材分组:男频 + 女频 + 通用"""
    from core.fanqie_genre_provider import get_genre_groups
    groups = get_genre_groups()
    assert len(groups) == 3
    names = [g[0] for g in groups]
    assert "男频题材(番茄)" in names
    assert "女频题材(番茄)" in names
    assert "通用题材" in names


def test_03_genre_groups_match_fanqie_categories():
    """男频组包含番茄实际男频分类(19 个)"""
    from core.fanqie_genre_provider import (
        get_genre_groups, FANQIE_MALE_CATEGORIES, FANQIE_FEMALE_CATEGORIES,
    )
    groups = dict(get_genre_groups())
    male_group = groups.get("男频题材(番茄)", [])
    assert "西方奇幻" in male_group
    assert "都市修真" in male_group
    assert "战神赘婿" in male_group
    assert len(male_group) >= 19

    female_group = groups.get("女频题材(番茄)", [])
    assert "豪门总裁" in female_group
    assert "古风世情" in female_group
    assert "快穿" in female_group


def test_04_match_user_genre_exact():
    """精确匹配:用户输入"豪门总裁" → 番茄"豪门总裁" """
    from core.fanqie_genre_provider import match_user_genre_to_fanqie
    result = match_user_genre_to_fanqie("豪门总裁")
    assert "豪门总裁" in result


def test_05_match_user_genre_aliases():
    """别名匹配:玄幻 → [传统玄幻, 玄幻脑洞, 玄幻言情, 都市高武]"""
    from core.fanqie_genre_provider import match_user_genre_to_fanqie
    result = match_user_genre_to_fanqie("玄幻")
    assert len(result) >= 3
    assert "传统玄幻" in result or "玄幻脑洞" in result
    assert "玄幻言情" in result


def test_06_match_user_genre_inclusive():
    """包含匹配:都市 → 含"都市"的所有分类"""
    from core.fanqie_genre_provider import match_user_genre_to_fanqie
    result = match_user_genre_to_fanqie("都市")
    # 至少应该匹配到几个含"都市"的真实分类
    matched_with_city = [r for r in result if "都市" in r]
    assert len(matched_with_city) >= 3


def test_07_match_user_genres_batch():
    """批量匹配:玄幻 + 都市 → 去重合并"""
    from core.fanqie_genre_provider import match_user_genres_to_fanqie
    result = match_user_genres_to_fanqie(["玄幻", "都市"])
    # 应该有玄幻相关 + 都市相关
    assert any("玄幻" in r for r in result)
    assert any("都市" in r for r in result)
    # 应该去重
    assert len(result) == len(set(result))


def test_08_match_empty_input():
    """空输入返回空列表"""
    from core.fanqie_genre_provider import (
        match_user_genre_to_fanqie, match_user_genres_to_fanqie,
    )
    assert match_user_genre_to_fanqie("") == []
    assert match_user_genres_to_fanqie([]) == []
    assert match_user_genres_to_fanqie(None) == []


def test_09_gather_samples_max_20():
    """v2.23.5: _gather_matched_samples 默认 max=20(从 8 升级)"""
    from core.fanqie_rank_scraper import _gather_matched_samples
    import inspect
    sig = inspect.signature(_gather_matched_samples)
    max_samples_default = sig.parameters["max_samples"].default
    assert max_samples_default == 20, f"v2.23.5 应该升到 20,当前 {max_samples_default}"


def test_10_gather_samples_returns_title_and_read():
    """v2.23.5: 样本字段含 title 和 read_count(v2.23.3 没有)"""
    with tempfile.TemporaryDirectory() as tmp:
        from core.fanqie_rank_scraper import (
            ensure_cache_dirs, save_book_detail, _gather_matched_samples,
        )
        ensure_cache_dirs(tmp)
        save_book_detail(tmp, "7000000000000000001", {
            "title": "测试爆款 A",
            "author": "测试作者",
            "abstract": "这是一本测试书的简介。" * 10,
            "tags": ["系统", "重生", "无敌"],
            "word_count": "100 万字",
        }, source_label="男频阅读榜·都市修真", source_category="都市修真")

        # 用户题材"修真"应该匹配"都市修真"
        samples = _gather_matched_samples(tmp, ["修真"], max_samples=5)
        # 至少 1 个
        assert len(samples) >= 1
        s = samples[0]
        assert "title" in s
        assert "read_count" in s
        # 智能匹配让 source_category=都市修真 被匹配到
        # 但即使没匹配,第二轮也会补,所以这里不强制 title 等于"测试爆款 A"


def test_11_enriched_prompt_uses_long_summary():
    """v2.23.5: 简介支持长度 300(从 80 升级)"""
    with tempfile.TemporaryDirectory() as tmp:
        from core.fanqie_rank_scraper import (
            ensure_cache_dirs, save_book_detail, build_v233_enriched_prompt,
        )
        ensure_cache_dirs(tmp)
        long_abstract = "这是一本爆款书的详细简介。" * 20  # > 300 字
        save_book_detail(tmp, "7000000000000000002", {
            "title": "长简介测试",
            "abstract": long_abstract,
            "tags": ["系统"],
        }, source_label="男频阅读榜·都市修真",
            source_category="都市修真")

        stats = {
            "total_books": 740, "unique_books": 600,
            "total_boards_scanned": 74,
            "by_gender": {
                "男频": {"boards": 38, "books": 380},
                "女频": {"boards": 36, "books": 360},
            },
            "hot_categories_male": [("都市修真", 870000)],
            "hot_categories_female": [],
        }
        prompt = build_v233_enriched_prompt(
            stats, ["修真"], tmp, "基础 prompt")
        # 简介应该不止 80 字,应该接近 300
        # 检查方法:简介里出现"这是一本"重复次数
        appearances = prompt.count("这是一本爆款书的详细简介")
        assert appearances >= 5, f"简介长度不足,只出现 {appearances} 次"


def test_12_enriched_prompt_shows_mapped_categories():
    """v2.23.5: prompt 展示用户题材→番茄分类的映射"""
    with tempfile.TemporaryDirectory() as tmp:
        from core.fanqie_rank_scraper import build_v233_enriched_prompt
        stats = {
            "total_books": 740, "unique_books": 600,
            "total_boards_scanned": 74,
            "by_gender": {
                "男频": {"boards": 38, "books": 380},
                "女频": {"boards": 36, "books": 360},
            },
            "hot_categories_male": [],
            "hot_categories_female": [],
        }
        prompt = build_v233_enriched_prompt(
            stats, ["玄幻"], tmp, "")
        # 应该展示用户题材在番茄对应的分类
        assert "你选的题材" in prompt or "对应分类" in prompt


def test_13_enriched_prompt_groups_by_category():
    """v2.23.5: 样本按分类分组展示"""
    with tempfile.TemporaryDirectory() as tmp:
        from core.fanqie_rank_scraper import (
            ensure_cache_dirs, save_book_detail, build_v233_enriched_prompt,
        )
        ensure_cache_dirs(tmp)
        save_book_detail(tmp, "7000000000000000003", {
            "title": "书 A",
            "abstract": "AAA",
            "tags": ["X"],
        }, source_category="都市修真")
        save_book_detail(tmp, "7000000000000000004", {
            "title": "书 B",
            "abstract": "BBB",
            "tags": ["Y"],
        }, source_category="都市修真")
        save_book_detail(tmp, "7000000000000000005", {
            "title": "书 C",
            "abstract": "CCC",
            "tags": ["Z"],
        }, source_category="传统玄幻")

        stats = {
            "total_books": 740, "unique_books": 600,
            "total_boards_scanned": 74,
            "by_gender": {
                "男频": {"boards": 38, "books": 380},
                "女频": {"boards": 36, "books": 360},
            },
            "hot_categories_male": [],
            "hot_categories_female": [],
        }
        prompt = build_v233_enriched_prompt(
            stats, ["都市", "玄幻"], tmp, "")
        # 应该有"▼ 【都市修真】" 或类似分组标识
        # 检查"按分类分组"提示存在
        assert "按分类分组" in prompt or "▼" in prompt


def test_14_app_version_v2_23_5():
    """APP_VERSION 应该升到 v2.23.5"""
    # 文件可能直接在项目根,也可能在子目录,都试
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
    candidates = [
        os.path.join(root, "novel_ai.py"),
        os.path.join(root, "..", "novel_ai.py"),
    ]
    novel_ai_path = next((p for p in candidates if os.path.exists(p)), None)
    assert novel_ai_path, f"找不到 novel_ai.py,试过: {candidates}"
    with open(novel_ai_path, encoding="utf-8") as f:
        head = "".join(f.readline() for _ in range(30))
    m = re.search(r'APP_VERSION\s*=\s*"(v\d+\.\d+\.\d+)"', head)
    assert m, "找不到 APP_VERSION"
    v = m.group(1)
    # 至少 v2.23.5
    parts = [int(x) for x in v[1:].split(".")]
    assert parts[0] >= 2 and parts[1] >= 23 and parts[2] >= 5, \
        f"版本至少 v2.23.5,当前 {v}"


def test_15_genre_provider_get_gender():
    """通过分类名查询性别"""
    from core.fanqie_genre_provider import get_gender_for_fanqie_category
    assert get_gender_for_fanqie_category("都市高武") == "男频"
    assert get_gender_for_fanqie_category("豪门总裁") == "女频"
    assert get_gender_for_fanqie_category("不存在的题材") == "通用"


def test_16_all_genres_flat_no_duplicates():
    """get_all_genres_flat 去重"""
    from core.fanqie_genre_provider import get_all_genres_flat
    all_g = get_all_genres_flat()
    assert len(all_g) == len(set(all_g))


def test_17_creation_settings_uses_genre_provider():
    """ui/tabs/creation_settings.py 引用 fanqie_genre_provider"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
    candidates = [
        os.path.join(root, "ui", "tabs", "creation_settings.py"),
        os.path.join(root, "..", "ui", "tabs", "creation_settings.py"),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    assert path, f"找不到 creation_settings.py,试过: {candidates}"
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "fanqie_genre_provider" in content, \
        "ui/tabs/creation_settings.py 应该 import fanqie_genre_provider"
    assert "get_genre_groups" in content, \
        "ui/tabs/creation_settings.py 应该调用 get_genre_groups"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed.append(t.__name__)
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
