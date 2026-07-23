# -*- coding: utf-8 -*-
"""
v2.23.3 详情深度抓取 + 后台 scheduler + 磁盘缓存 + UI 修复 — 守护测试

12 条测试:
  1. V233_DETAIL_TOPK == 5(用户敲定 Top5)
  2. V233_DISK_CACHE_TTL_SEC == 7 天
  3. V233_BG_DELAY_SEC == 30 秒
  4. get_t5_book_ids_from_scraped 正确去重 + 取 Top5
  5. parse_detail_page_html 抓书名/简介/标签/作者(meta 干净)
  6. parse_detail_page_html 反爬:body 乱码但 meta 干净也能成
  7. save/load_book_detail 磁盘读写 round-trip
  8. write_index_md 写出 INDEX.md
  9. build_v233_enriched_prompt 含详情样本时输出有"已扫到的真实爆款样本"
 10. build_v233_enriched_prompt UI 修复:输出"AI 自己想的具体卖点词"指引
 11. creative_inspiration prompt 不再有"【一句话卖点】"字面占位
 12. worker 有 scrape_book_details_batch action 路由 + 礼让逻辑
"""
import os
import re
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根


def test_01_topk_is_5():
    """用户敲定 Top5,不能改"""
    from core.fanqie_rank_scraper import V233_DETAIL_TOPK
    assert V233_DETAIL_TOPK == 5, f"应该是 5,实际 {V233_DETAIL_TOPK}"


def test_02_disk_ttl_7_days():
    """磁盘缓存 7 天"""
    from core.fanqie_rank_scraper import V233_DISK_CACHE_TTL_SEC
    assert V233_DISK_CACHE_TTL_SEC == 7 * 24 * 3600


def test_03_bg_delay_30s():
    """启动后 30 秒触发后台"""
    from core.fanqie_rank_scraper import V233_BG_DELAY_SEC
    assert V233_BG_DELAY_SEC == 30


def test_04_get_t5_book_ids_dedup():
    """get_t5_book_ids_from_scraped 取每榜 Top5 + 去重"""
    from core.fanqie_rank_scraper import get_t5_book_ids_from_scraped
    scraped = [
        {"label": "男频阅读榜·A", "category": "A",
         "books": [{"book_id": f"{i:019d}"} for i in range(10)]},  # 10 本
        {"label": "男频阅读榜·B", "category": "B",
         "books": [{"book_id": "0" * 19}]},  # 重复 book_id 0
    ]
    ids = get_t5_book_ids_from_scraped(scraped)
    # Top5 from A(book_id 0-4) + Top5 from B(book_id 0 已重复)
    # 期望 5 个唯一
    assert len(ids) == 5, f"应该 5 个,实际 {len(ids)}"
    # 第一个应该来自 A
    assert ids[0][1] == "男频阅读榜·A"


def test_05_parse_detail_clean_fields():
    """详情页 HTML 解析:从 meta 抽书名/简介/标签/作者"""
    from core.fanqie_rank_scraper import parse_detail_page_html
    html = """
    <html><head>
    <title>测试书名完整版在线免费阅读_测试书名小说_番茄小说官网</title>
    <meta name="description" content="番茄小说提供测试书名完整版在线免费阅读,精彩小说尽在番茄小说网。【系统】【种田】【穿越】这是一个测试简介。">
    <meta name="keywords" content="测试书名,测试书名免费阅读,某作者测试书名,测试书名全本免费下载">
    </head></html>
    """
    d = parse_detail_page_html(html)
    assert d["title"] == "测试书名"
    assert d["author"] == "某作者"
    assert "系统" in d["tags"]
    assert "种田" in d["tags"]
    assert "穿越" in d["tags"]
    assert "测试简介" in d["abstract"]


def test_06_parse_detail_with_body_obfuscation():
    """body 字体反爬乱码也能解析(只看 head 的 meta)"""
    from core.fanqie_rank_scraper import parse_detail_page_html
    html = """
    <html><head>
    <title>正常书名完整版在线免费阅读_正常书名小说_番茄小说官网</title>
    <meta name="description" content="番茄小说提供正常书名完整版在线免费阅读,精彩小说尽在番茄小说网。【马甲】【打脸】完整的简介内容。">
    <meta name="keywords" content="正常书名,正常书名免费阅读,作者正常书名">
    </head>
    <body>
    <div>乱码:养需步?首,需找赋极佳且孤苦依幼崽</div>
    </body></html>
    """
    d = parse_detail_page_html(html)
    assert d["title"] == "正常书名"
    assert "马甲" in d["tags"]
    assert "完整的简介内容" in d["abstract"]


def test_07_save_load_book_detail_roundtrip():
    """save_book_detail + load_book_detail round-trip"""
    from core.fanqie_rank_scraper import save_book_detail, load_book_detail
    tmpdir = tempfile.mkdtemp(prefix="v233_test_")
    try:
        ok = save_book_detail(tmpdir, "1234567890123456789",
                               {"title": "测试", "tags": ["a", "b"]},
                               "男频阅读榜·X", "X")
        assert ok
        loaded = load_book_detail(tmpdir, "1234567890123456789")
        assert loaded is not None
        assert loaded["detail"]["title"] == "测试"
        assert loaded["source_label"] == "男频阅读榜·X"
        assert "scraped_at" in loaded
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_08_write_index_md():
    """write_index_md 写出 INDEX.md 文件,可读"""
    from core.fanqie_rank_scraper import write_index_md
    tmpdir = tempfile.mkdtemp(prefix="v233_test_")
    try:
        stats = {
            "total_boards_scanned": 74,
            "total_books": 740,
            "unique_books": 423,
            "hot_categories_male": [("玄幻", 500000)],
            "hot_categories_female": [("古风", 300000)],
        }
        ok = write_index_md(tmpdir, stats, [], (10, 100))
        assert ok
        idx_path = os.path.join(tmpdir, ".fanqie_cache", "INDEX.md")
        assert os.path.exists(idx_path)
        content = open(idx_path, encoding="utf-8").read()
        assert "番茄榜单缓存" in content
        assert "740" in content
        assert "玄幻" in content
        assert "10 / 100" in content
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_09_enriched_prompt_uses_samples():
    """build_v233_enriched_prompt 有详情样本时,prompt 含'已扫到的真实爆款样本'"""
    from core.fanqie_rank_scraper import (
        build_v233_enriched_prompt, save_book_detail,
    )
    tmpdir = tempfile.mkdtemp(prefix="v233_test_")
    try:
        # 写一本样本(题材"玄幻")
        save_book_detail(tmpdir, "1111111111111111111",
                          {"title": "样本一", "abstract": "讲了一个玄幻故事很爽",
                           "tags": ["系统", "玄幻"]},
                          "男频阅读榜·传统玄幻", "传统玄幻")
        stats = {
            "total_boards_scanned": 74,
            "total_books": 740,
            "unique_books": 423,
            "by_gender": {"男频": {"boards": 38, "books": 380},
                           "女频": {"boards": 36, "books": 360}},
            "hot_categories_male": [("玄幻", 500000)],
            "hot_categories_female": [],
        }
        p = build_v233_enriched_prompt(stats, ["玄幻"], tmpdir, "请生成 5 个创意")
        assert "已扫到的真实爆款样本" in p
        # v2.23.5: 设计已变更为发送书名(配合"不许复制"约束)
        # 不再要求"不能泄漏书名",改为要求 prompt 含约束语
        assert "不直接复制" in p or "绝不复制" in p or "不能复制" in p \
            or "不许复制" in p, "prompt 必须含'不许复制'约束"
        # 应该有题材名
        assert "传统玄幻" in p or "玄幻" in p
        # 应该有标签组合
        assert "系统" in p
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_10_enriched_prompt_ui_guidance():
    """build_v233_enriched_prompt 含 UI 修复指引(不要写'一句话卖点'字面)"""
    from core.fanqie_rank_scraper import build_v233_enriched_prompt
    stats = {
        "total_boards_scanned": 74,
        "total_books": 100,
        "unique_books": 80,
        "by_gender": {"男频": {"boards": 38, "books": 50},
                       "女频": {"boards": 36, "books": 50}},
        "hot_categories_male": [("玄幻", 500000)],
        "hot_categories_female": [],
    }
    p = build_v233_enriched_prompt(stats, ["玄幻"], "/tmp/nonexistent", "")
    # 应该有"不要写一句话卖点"的指引
    assert "一句话卖点" in p, "应该明确告诉 AI 不要写'一句话卖点'占位字"
    # 应该有正确的卖点词示例
    assert any(ex in p for ex in ["厨子修仙", "系统种田", "废柴逆袭", "马甲女帝"])


def test_11_prompts_no_占位词():
    """creative_inspiration prompt 修复 UI bug:示例改成 AI 自己想词"""
    from core.prompts import PROMPTS
    p = PROMPTS["creative_inspiration"]
    # 原来的死格式 "1. 【一句话卖点】详细说明" 应该不再是唯一的格式说明
    # 必须含正面例子(让 AI 知道要写自己的卖点词)
    assert any(positive in p for positive in
                ["你想的具体卖点词", "你自己想的"]), \
        "prompt 应该明示要 AI 自己想卖点词"
    # 应该有错误示例
    assert "占位" in p or "不能" in p, "prompt 应该说明不要写占位字面"


def test_12_worker_has_detail_action():
    """worker.py 有 scrape_book_details_batch action 路由 + 礼让逻辑"""
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "ui/browser_worker.py"),
                encoding="utf-8").read()
    # action 路由存在
    assert 'action == "scrape_book_details_batch"' in src
    # 实现方法存在
    assert "def _scrape_book_details_batch" in src
    # 礼让逻辑:检查 task_queue.qsize
    body = re.search(r"def _scrape_book_details_batch.*?(?=\n    def )",
                      src, re.DOTALL)
    assert body, "找不到 _scrape_book_details_batch 函数体"
    body_text = body.group(0)
    assert "task_queue.qsize()" in body_text, \
        "礼让逻辑必须检查 task_queue.qsize()"
    assert "load_book_detail" in body_text, \
        "应该用 load_book_detail 跳过已缓存"


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
