# -*- coding: utf-8 -*-
"""
v2.23.1 番茄全榜扫描 MVP — 守护测试

测什么(13 条):
  1. get_all_rank_urls 返回 74 个榜单(男 38 + 女 36)
  2. 真实 cat_id 不是连续 1-19 序号(防止上一轮编 ID 灾难重现)
  3. URL 格式正确(/rank/{gender}_{type}_{cat_id})
  4. parse_rank_page_minimal 从 HTML 抽 book_id(从 /page/ URL)
  5. parse_rank_page_minimal 抽在读数(数字+万)
  6. parse_rank_page_minimal 不依赖书名/简介(反爬乱码也能跑)
  7. aggregate_v231_stats 正确算 total / unique
  8. aggregate_v231_stats 按性别正确分桶
  9. aggregate_v231_stats 题材热度按在读数排序
 10. build_v231_full_rank_prompt 输出非空且含关键字段
 11. build_v231_full_rank_prompt 不传具体 book_id(防 AI 抄)
 12. V231_CACHE_TTL_SEC 是 24 小时(不是 30 分钟)
 13. v2.23.0 向后兼容:Book/FanqieRankCache/parse_scraped_books 仍可用
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根


def test_01_all_rank_urls_count():
    """74 榜单 = 男频 38 + 女频 36"""
    from core.fanqie_rank_scraper import get_all_rank_urls
    urls = get_all_rank_urls()
    assert len(urls) == 74, f"应该 74 个榜单,实际 {len(urls)}"
    male = [u for u in urls if u["gender"] == "男频"]
    female = [u for u in urls if u["gender"] == "女频"]
    assert len(male) == 38, f"男频应 38,实际 {len(male)}"
    assert len(female) == 36, f"女频应 36,实际 {len(female)}"


def test_02_real_cat_ids_not_sequential():
    """
    防御性测试:防止"编 cat_id 1-19 顺序号"灾难重现

    真实 cat_id 是非连续乱码(西方奇幻=1141 不是 11)。
    """
    from core.fanqie_rank_scraper import V231_MALE_CATEGORIES, V231_FEMALE_CATEGORIES
    male_dict = dict(V231_MALE_CATEGORIES)
    assert male_dict.get("西方奇幻") == "1141", \
        f"西方奇幻 cat_id 应是真实抓到的 1141,实际是 {male_dict.get('西方奇幻')}"
    assert male_dict.get("东方仙侠") == "1140"
    assert male_dict.get("科幻末世") == "8"
    assert male_dict.get("战神赘婿") == "27"
    female_dict = dict(V231_FEMALE_CATEGORIES)
    assert female_dict.get("古风世情") == "1139"
    assert female_dict.get("民国言情") == "1017"
    male_ids = [int(cid) for _, cid in V231_MALE_CATEGORIES]
    assert max(male_ids) - min(male_ids) > 100, "cat_id 应该分布散乱,不是 1-19"


def test_03_url_format():
    """URL 应是 /rank/{gender}_{type}_{cat_id} 格式"""
    from core.fanqie_rank_scraper import get_all_rank_urls
    urls = get_all_rank_urls()
    pattern = re.compile(r"^https://fanqienovel\.com/rank/[01]_[12]_\d+$")
    for u in urls:
        assert pattern.match(u["url"]), f"URL 格式不对:{u['url']}"


def test_04_parse_extracts_book_id():
    """从榜单 HTML 抽 book_id(从 /page/ URL 里,反爬不影响)"""
    from core.fanqie_rank_scraper import parse_rank_page_minimal
    html = """
    # 01
    [书名乱码](https://fanqienovel.com/page/7560536855758785598)
    在读:66.4万

    # 02
    [乱码](https://fanqienovel.com/page/9999999999999999999)
    在读:50万
    """
    books = parse_rank_page_minimal(html, max_books=10)
    assert len(books) == 2
    assert books[0]["book_id"] == "7560536855758785598"
    assert books[1]["book_id"] == "9999999999999999999"


def test_05_parse_extracts_read_count():
    """从榜单 HTML 抽在读数(数字+万,反爬不影响)"""
    from core.fanqie_rank_scraper import parse_rank_page_minimal
    html = """
    # 01
    [x](https://fanqienovel.com/page/7560536855758785598)
    在读:66.4万
    """
    books = parse_rank_page_minimal(html)
    assert len(books) == 1
    assert books[0]["read_count_num"] == 664000
    assert "66.4万" in books[0]["read_count_raw"]


def test_06_parse_works_with_obfuscated_text():
    """
    反爬乱码场景:书名简介全是乱码,但 book_id 在 URL 里干净 → 仍能抓
    """
    from core.fanqie_rank_scraper import parse_rank_page_minimal
    obfuscated = """
    # 01
    早玩!
    [早玩!](https://fanqienovel.com/page/7560536855758785598)
    养需步?首,需找赋极佳且孤苦依幼崽,限温暖怀.
    在读:66.4万
    """
    books = parse_rank_page_minimal(obfuscated)
    assert len(books) == 1
    assert books[0]["book_id"] == "7560536855758785598"
    assert books[0]["read_count_num"] == 664000


def test_07_aggregate_counts():
    """聚合统计:total / unique 正确"""
    from core.fanqie_rank_scraper import aggregate_v231_stats
    scraped = [
        {"label": "男频阅读榜·西方奇幻", "gender": "男频", "type": "阅读榜",
         "category": "西方奇幻", "books": [
             {"book_id": "1111111111111111111", "read_count_num": 100000},
             {"book_id": "2222222222222222222", "read_count_num": 200000},
         ]},
        {"label": "男频阅读榜·都市", "gender": "男频", "type": "阅读榜",
         "category": "都市", "books": [
             {"book_id": "1111111111111111111", "read_count_num": 100000},
             {"book_id": "3333333333333333333", "read_count_num": 50000},
         ]},
    ]
    stats = aggregate_v231_stats(scraped)
    assert stats["total_books"] == 4
    assert stats["unique_books"] == 3


def test_08_aggregate_gender_bucket():
    """聚合统计:正确按性别分桶"""
    from core.fanqie_rank_scraper import aggregate_v231_stats
    scraped = [
        {"label": "男频阅读榜·a", "gender": "男频", "type": "阅读榜", "category": "a",
         "books": [{"book_id": "1111111111111111111", "read_count_num": 100000}]},
        {"label": "男频阅读榜·b", "gender": "男频", "type": "阅读榜", "category": "b",
         "books": [{"book_id": "2222222222222222222", "read_count_num": 100000}]},
        {"label": "女频阅读榜·c", "gender": "女频", "type": "阅读榜", "category": "c",
         "books": [{"book_id": "3333333333333333333", "read_count_num": 100000}]},
    ]
    stats = aggregate_v231_stats(scraped)
    assert stats["by_gender"]["男频"]["boards"] == 2
    assert stats["by_gender"]["男频"]["books"] == 2
    assert stats["by_gender"]["女频"]["boards"] == 1
    assert stats["by_gender"]["女频"]["books"] == 1


def test_09_aggregate_hot_categories_sorted():
    """聚合统计:题材热度按在读数排序"""
    from core.fanqie_rank_scraper import aggregate_v231_stats
    scraped = [
        {"label": "男频阅读榜·a", "gender": "男频", "type": "阅读榜", "category": "a",
         "books": [{"book_id": "1111111111111111111", "read_count_num": 100000}]},
        {"label": "男频阅读榜·b", "gender": "男频", "type": "阅读榜", "category": "b",
         "books": [{"book_id": "2222222222222222222", "read_count_num": 500000}]},
        {"label": "男频阅读榜·c", "gender": "男频", "type": "阅读榜", "category": "c",
         "books": [{"book_id": "3333333333333333333", "read_count_num": 300000}]},
    ]
    stats = aggregate_v231_stats(scraped)
    hot = stats["hot_categories_male"]
    assert hot[0][0] == "b"
    assert hot[1][0] == "c"
    assert hot[2][0] == "a"


def test_10_prompt_contains_key_fields():
    """build_v231_full_rank_prompt 输出含 stats 关键字段"""
    from core.fanqie_rank_scraper import build_v231_full_rank_prompt
    stats = {
        "total_boards_scanned": 74,
        "total_books": 740,
        "unique_books": 423,
        "by_gender": {"男频": {"boards": 38, "books": 380}, "女频": {"boards": 36, "books": 360}},
        "category_distribution": {},
        "hot_categories_male": [("玄幻", 500000), ("都市", 300000)],
        "hot_categories_female": [("古风", 400000)],
    }
    p = build_v231_full_rank_prompt(stats, ["玄幻"], "请生成 5 个创意")
    assert "番茄小说全榜真实数据" in p
    assert "740" in p
    assert "423" in p
    assert "玄幻" in p
    assert "硬性约束" in p
    assert "差异化卖点" in p


def test_11_prompt_no_book_ids_leak():
    """build_v231_full_rank_prompt 不能在输出里泄漏 book_id(防 AI 抄)"""
    from core.fanqie_rank_scraper import build_v231_full_rank_prompt, aggregate_v231_stats
    scraped = [
        {"label": "男频阅读榜·a", "gender": "男频", "type": "阅读榜", "category": "a",
         "books": [{"book_id": "7560536855758785598", "read_count_num": 100000}]},
    ]
    stats = aggregate_v231_stats(scraped)
    p = build_v231_full_rank_prompt(stats, ["玄幻"])
    assert "7560536855758785598" not in p, "prompt 里不能出现具体 book_id"


def test_12_cache_ttl_24h():
    """缓存 TTL 应是 24 小时(86400 秒),不是 v2.23.0 的 30 分钟"""
    from core.fanqie_rank_scraper import V231_CACHE_TTL_SEC
    assert V231_CACHE_TTL_SEC == 24 * 3600, \
        f"v2.23.1 TTL 应是 24h,实际 {V231_CACHE_TTL_SEC}s"


def test_13_v230_backward_compat():
    """v2.23.0 老 API 完全保留 — Book / FanqieRankCache / parse_scraped_books"""
    from core.fanqie_rank_scraper import (
        Book, FanqieRankCache, parse_scraped_books, filter_by_genres,
        build_enhanced_inspiration_prompt, extract_genre_combinations,
        extract_abstract_keywords, FANQIE_SCRAPER_PROFILE,
        FANQIE_RANK_URL, SCRAPE_TARGET_TOPK, CACHE_TTL_SEC,
    )
    b = Book(title="测试", category="玄幻", abstract="爽文系统")
    assert b.is_valid()
    assert b.title == "测试"
    c = FanqieRankCache()
    c.put("番茄", ["玄幻"], [b])
    assert c.get("番茄", ["玄幻"]) is not None
    books = parse_scraped_books([{"title": "a", "category": "玄幻"}])
    assert len(books) == 1
    assert FANQIE_RANK_URL == "https://fanqienovel.com/rank?enter_from=menu"
    assert CACHE_TTL_SEC == 30 * 60


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
