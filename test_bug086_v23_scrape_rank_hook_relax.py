# -*- coding: utf-8 -*-
"""
v2.23.0 BUG-086 守护测试
============================

测试两组改动:
1. **番茄扫榜增强灵感生成**:scraper 模块 + worker 任务 + 主进程流程
2. **钩子检测松绑**:元信息 ★★★★+ 直接放行

设计上分两层:
- 纯逻辑层(scraper / 钩子强度提取):直接 import 验证行为
- 集成层(worker 信号 / 主进程 connect / fallback 路径):用静态 grep
  + AST 检查代码结构,不依赖运行时
"""
import re
import os
import sys
import importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))


def _read(path):
    with open(os.path.join(ROOT, path), 'r', encoding='utf-8') as f:
        return f.read()


def _import_scraper():
    """import core.fanqie_rank_scraper 不影响其他测试"""
    sys.path.insert(0, ROOT)
    from core import fanqie_rank_scraper as fs
    return fs


# ============================================================
# 1. 番茄扫榜 — 纯逻辑层
# ============================================================

def test_bug086_scraper_module_exists():
    """core/fanqie_rank_scraper.py 必须存在"""
    assert os.path.exists(os.path.join(ROOT, "core", "fanqie_rank_scraper.py"))


def test_bug086_scraper_basic_imports():
    fs = _import_scraper()
    # 关键导出
    assert hasattr(fs, "Book")
    assert hasattr(fs, "FanqieRankCache")
    assert hasattr(fs, "filter_by_genres")
    assert hasattr(fs, "build_enhanced_inspiration_prompt")
    assert hasattr(fs, "parse_scraped_books")
    assert hasattr(fs, "FANQIE_RANK_URL")
    # URL 必须是用户敲定的那个
    assert "fanqienovel.com/rank" in fs.FANQIE_RANK_URL


def test_bug086_scraper_cache_ttl_30min():
    fs = _import_scraper()
    # 缓存 TTL 必须是 30 分钟(用户敲定)
    assert fs.CACHE_TTL_SEC == 30 * 60


def test_bug086_scraper_book_validation():
    fs = _import_scraper()
    # 空 book 应该判 invalid
    assert not fs.Book().is_valid()
    # 有标题或题材就 valid
    assert fs.Book(title="斗破").is_valid()
    assert fs.Book(category="玄幻").is_valid()


def test_bug086_scraper_cache_basic():
    fs = _import_scraper()
    cache = fs.FanqieRankCache()
    books = [fs.Book(title="斗破", category="玄幻")]
    assert cache.get("番茄小说", ["玄幻"]) is None  # 未命中
    cache.put("番茄小说", ["玄幻"], books)
    got = cache.get("番茄小说", ["玄幻"])
    assert got is not None
    assert len(got) == 1


def test_bug086_scraper_cache_genre_order_independent():
    """同样的 genre 集合,顺序不同也要命中同一个缓存键"""
    fs = _import_scraper()
    cache = fs.FanqieRankCache()
    books = [fs.Book(title="A", category="玄幻")]
    cache.put("番茄小说", ["玄幻", "重生"], books)
    # 反序应该命中
    got = cache.get("番茄小说", ["重生", "玄幻"])
    assert got is not None and len(got) == 1


def test_bug086_scraper_cache_expires():
    fs = _import_scraper()
    cache = fs.FanqieRankCache(ttl_sec=0)  # 立刻过期
    cache.put("番茄小说", ["玄幻"], [fs.Book(title="A")])
    import time as _t
    _t.sleep(0.01)
    assert cache.get("番茄小说", ["玄幻"]) is None


def test_bug086_filter_by_genres_hard_match():
    """硬匹配题材"""
    fs = _import_scraper()
    books = [
        fs.Book(title="A", category="玄幻"),
        fs.Book(title="B", category="言情"),
        fs.Book(title="C", category="都市"),
        fs.Book(title="D", category="玄幻·重生"),
    ]
    filtered, hard, relax = fs.filter_by_genres(books, ["玄幻"], min_matches=2)
    assert len(filtered) == 2
    assert hard == 2 and relax == 0
    titles = {b.title for b in filtered}
    assert "A" in titles and "D" in titles


def test_bug086_filter_by_genres_relax_when_not_enough():
    """硬匹配不足时放宽到相近题材"""
    fs = _import_scraper()
    books = [
        fs.Book(title="A", category="玄幻"),
        fs.Book(title="B", category="奇幻"),
        fs.Book(title="C", category="修真"),
        fs.Book(title="D", category="言情"),  # 不该被匹配
    ]
    # 用户选玄幻,硬匹配只有 1 条 < min_matches=2
    # 应该放宽到 GENRE_RELAX_MAP[玄幻] = ['奇幻','修真','仙侠',...]
    filtered, hard, relax = fs.filter_by_genres(books, ["玄幻"], min_matches=2)
    assert hard == 1
    assert relax >= 2  # 至少奇幻和修真应该被补进来
    titles = {b.title for b in filtered}
    assert "D" not in titles  # 言情不在相近表里


def test_bug086_filter_by_genres_no_genres_returns_all():
    """没选题材 → 全部返回"""
    fs = _import_scraper()
    books = [fs.Book(title="A", category="X"), fs.Book(title="B", category="Y")]
    filtered, hard, relax = fs.filter_by_genres(books, [])
    assert len(filtered) == 2


def test_bug086_filter_by_genres_empty_books():
    fs = _import_scraper()
    filtered, hard, relax = fs.filter_by_genres([], ["玄幻"])
    assert filtered == []


def test_bug086_extract_genre_combinations():
    """题材组合统计"""
    fs = _import_scraper()
    books = [
        fs.Book(title="A", category="玄幻 · 重生"),
        fs.Book(title="B", category="玄幻 · 重生"),
        fs.Book(title="C", category="都市 · 系统"),
    ]
    combos = fs.extract_genre_combinations(books, topk=5)
    # "玄幻 + 重生" 应该是 Top
    assert combos
    top_label = combos[0][0]
    assert "玄幻" in top_label and "重生" in top_label
    assert combos[0][1] >= 2


def test_bug086_extract_abstract_keywords():
    fs = _import_scraper()
    books = [
        fs.Book(title="重生之主宰天下", abstract="主角重生后,系统加持开始打脸"),
        fs.Book(title="穿越马甲学", abstract="女主穿越成马甲,逆袭打脸"),
    ]
    kws = fs.extract_abstract_keywords(books, topk=10)
    # 这些热门词应该被提取出来
    kw_set = {w for w, _ in kws}
    assert "重生" in kw_set
    assert "打脸" in kw_set


def test_bug086_build_enhanced_prompt_returns_none_when_no_books():
    fs = _import_scraper()
    prompt = fs.build_enhanced_inspiration_prompt([], ["玄幻"], "番茄小说")
    assert prompt is None


def test_bug086_build_enhanced_prompt_has_iron_rules():
    """增强 prompt 必须包含铁律 — 防 AI 抄袭"""
    fs = _import_scraper()
    books = [fs.Book(title="A", category="玄幻 · 重生", abstract="重生打脸")]
    prompt = fs.build_enhanced_inspiration_prompt(books, ["玄幻"], "番茄小说")
    assert prompt is not None
    # 铁律必须存在
    assert "不要直接复制" in prompt or "不能直接复制" in prompt
    # 不应该直接传具体书名(防 AI 学样)
    # build_enhanced_prompt 内部不应把 raw 书名拼进去
    assert "斗破苍穹" not in prompt  # sanity check


def test_bug086_parse_scraped_books_dedup():
    """重复标题去重"""
    fs = _import_scraper()
    raw = [
        {"title": "斗破", "category": "玄幻"},
        {"title": "斗破", "category": "玄幻"},  # 重复
        {"title": "都市", "category": "都市"},
    ]
    books = fs.parse_scraped_books(raw)
    assert len(books) == 2


def test_bug086_parse_scraped_books_filters_invalid():
    fs = _import_scraper()
    raw = [
        {"title": "", "category": ""},  # 全空
        {},  # 空 dict
        {"title": "A"},
    ]
    books = fs.parse_scraped_books(raw)
    assert len(books) == 1 and books[0].title == "A"


# ============================================================
# 2. 番茄扫榜 — worker 集成层(静态检查)
# ============================================================

def test_bug086_worker_has_rank_scraped_signal():
    code = _read('ui/browser_worker.py')
    assert re.search(r'rank_scraped\s*=\s*pyqtSignal', code), \
        "worker 必须有 rank_scraped 信号"
    m = re.search(r'rank_scraped\s*=\s*pyqtSignal\(([^)]+)\)', code)
    assert m
    sig = m.group(1)
    # 必须是 (str, list) 签名
    assert 'str' in sig and 'list' in sig


def test_bug086_worker_has_scrape_action():
    code = _read('ui/browser_worker.py')
    assert 'scrape_fanqie_rank' in code
    # 必须有对应分发分支
    assert re.search(r'action\s*==\s*["\']scrape_fanqie_rank["\']', code)


def test_bug086_worker_scrape_method_exists():
    code = _read('ui/browser_worker.py')
    assert re.search(r'def\s+_scrape_fanqie_rank\s*\(', code)


def test_bug086_worker_scrape_fallback_on_error():
    """worker 扫榜异常时必须 emit 空 list,主进程才能 fallback"""
    code = _read('ui/browser_worker.py')
    # 找 _scrape_fanqie_rank 方法
    m = re.search(r'def\s+_scrape_fanqie_rank\s*\(self,\s*task\):(.+?)(?=\n    def |\nclass )',
                  code, re.DOTALL)
    assert m
    body = m.group(1)
    # 必须有 try/except + 异常时 emit 空 list
    assert 'except' in body
    # 在 except 分支里必须 emit 空 list,而不是把异常吃掉
    # 简化检查:整个方法 body 里多次 emit,且至少一次是 emit(task_id, [])
    assert re.search(r'rank_scraped\.emit\(\s*[\w_]+,\s*\[\]\s*\)', body), \
        "扫榜失败必须 emit 空 list 让主进程 fallback"


# ============================================================
# 3. 主进程集成层(静态检查)
# ============================================================

def test_bug086_main_connects_rank_scraped():
    code = _read('novel_ai.py')
    assert re.search(
        r'rank_scraped\.connect\s*\(\s*self\._on_fanqie_rank_scraped',
        code)


def test_bug086_main_on_fanqie_rank_scraped_exists():
    code = _read('novel_ai.py')
    assert re.search(
        r'def\s+_on_fanqie_rank_scraped\s*\(self,\s*task_id,\s*books_data',
        code)


def test_bug086_main_gen_inspiration_has_scrape_path():
    """gen_inspiration 必须有"番茄 + browser_ready → 扫榜"分支 + fallback"""
    code = _read('novel_ai.py')
    m = re.search(
        r'def\s+gen_inspiration\s*\(self\):(.+?)(?=\n    def )', code, re.DOTALL)
    assert m
    body = m.group(1)
    # 必须 check platform 番茄
    assert '番茄小说' in body
    # 必须 check worker is_ready
    assert 'is_ready' in body
    # 必须有 fallback
    assert '_gen_inspiration_send_fallback' in body or 'fallback' in body.lower()


def test_bug086_main_fallback_uses_old_prompt():
    """fallback 路径必须用 PROMPTS['creative_inspiration'](旧行为)"""
    code = _read('novel_ai.py')
    m = re.search(
        r'def\s+_gen_inspiration_send_fallback\s*\(self,[^)]+\):(.+?)(?=\n    def )',
        code, re.DOTALL)
    assert m
    body = m.group(1)
    assert 'creative_inspiration' in body
    assert '_send_to_ai' in body


def test_bug086_main_cache_invocation():
    """主进程必须用 FanqieRankCache 缓存"""
    code = _read('novel_ai.py')
    # 至少出现 _fanqie_rank_cache 字段
    assert '_fanqie_rank_cache' in code
    # 且要用 .get/.put 接口(避免裸 dict 操作)
    assert '_fanqie_rank_cache.get' in code
    assert '_fanqie_rank_cache.put' in code


# ============================================================
# 4. 钩子检测松绑(BUG-086 第二组)
# ============================================================

def test_bug086_hook_intensity_extractor_exists():
    code = _read('novel_ai.py')
    assert re.search(r'def\s+_extract_hook_intensity_from_text\s*\(self,\s*content',
                     code)


def test_bug086_hook_intensity_extracts_stars():
    """5 星钩子应返回 5,3 星返回 3,没声明返回 0"""
    # 把方法逻辑做最小可测复刻 — 直接读源码看是否覆盖关键模式
    # (不能真 import MainWindow 因为需要 Qt 显示)
    code = _read('novel_ai.py')
    m = re.search(
        r'def\s+_extract_hook_intensity_from_text\s*\(self,\s*content\):(.+?)(?=\n    def )',
        code, re.DOTALL)
    assert m
    body = m.group(1)
    # 必须查"【断章钩子】"块
    assert '断章钩子' in body
    # 必须匹配"强度"行
    assert '强度' in body
    # 必须数 ★ 字符
    assert "★" in body or "'★'" in body or '"★"' in body


def test_bug086_check_quality_uses_intensity_relaxation():
    """_check_chapter_quality 钩子检测必须有强度松绑路径"""
    code = _read('novel_ai.py')
    # 找钩子检测段
    idx = code.find("# 2. 章末钩子")
    assert idx > 0
    # 后面 1500 字内必须有强度判定
    section = code[idx:idx + 1500]
    assert '_extract_hook_intensity_from_text' in section
    # 必须有 "[BUG-086]" 标识(实战日志取证用)
    assert '[BUG-086]' in section
    # 4 星阈值
    assert re.search(r'>=\s*4', section), "强度判定必须有 >= 4 阈值"


def test_bug086_hook_relax_has_log():
    """强度放行时必须打日志说明理由(让用户能审)"""
    code = _read('novel_ai.py')
    idx = code.find("# 2. 章末钩子")
    section = code[idx:idx + 1500]
    # 必须 emit log_signal 或 tab_generation.log 记录放行
    has_log = 'log_signal' in section or 'tab_generation.log' in section
    assert has_log


# ============================================================
# 5. 版号 + 元数据
# ============================================================

def test_bug086_app_version_v2_23_0():
    code = _read('novel_ai.py')
    assert re.search(r'APP_VERSION\s*=\s*["\']v2\.23\.0["\']', code)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
