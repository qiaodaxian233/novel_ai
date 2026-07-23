# -*- coding: utf-8 -*-
"""
v2.23.2 BUG-087 守护测试

BUG-087:_scrape_fanqie_all_ranks 调 self._goto() 触发了"同 host 跳过 navigate"优化,
        导致 74 个榜单循环里浏览器从来没真正切换 URL,所有抓取都是同一个详情页 HTML,
        每榜都返回 0 本(用户截图显示 89% 进度 0 本)。

修法:扫榜循环里**不能调 _goto**,必须直接 driver.get(url) 强制每次真 navigate。
     并且改用 JS DOM 查询(querySelectorAll)抓 book_id 和在读数,
     比 page_source 正则更鲁棒(React 应用 page_source 可能是渲染前的 #root 空 div)。

8 条测试:
  1. _scrape_fanqie_all_ranks 不调 self._goto(防回归)
  2. _scrape_fanqie_all_ranks 调 driver.get
  3. _scrape_fanqie_all_ranks 用 querySelectorAll DOM 查询(不只靠 page_source 正则)
  4. driver.get 后等待时间 ≥ 2 秒(给 React 渲染)
  5. JS 抓取后仍保留 page_source 作 fallback(双保险)
  6. 抓 book_id 限制 10 位以上数字(防误中其它 URL)
  7. APP_VERSION 升到 v2.23.2
  8. BUG-087 标识在代码注释里(便于追溯)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根

WORKER_SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "ui/browser_worker.py"),
                  encoding="utf-8").read()
NOVEL_AI_SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "novel_ai.py"),
                    encoding="utf-8").read()


def _extract_func(src, func_name):
    """从源码里抽出某个函数的代码体"""
    m = re.search(
        rf"def {func_name}\(self.*?\n(.*?)(?=\n    def [a-zA-Z_]|\Z)",
        src, re.DOTALL)
    return m.group(1) if m else ""


def test_01_scrape_all_ranks_no_self_goto():
    """BUG-087 主守护:_scrape_fanqie_all_ranks 不能调 self._goto"""
    body = _extract_func(WORKER_SRC, "_scrape_fanqie_all_ranks")
    assert body, "找不到 _scrape_fanqie_all_ranks"
    # _goto 是双 AI 切换优化,扫榜不能用
    # 排除注释中提到的(注释里说"不能用 self._goto"是允许的)
    lines = body.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # 注释行允许提及
        assert "self._goto(" not in stripped, \
            f"扫榜不能用 self._goto(同 host 跳过 bug),发现: {stripped}"


def test_02_uses_driver_get():
    """扫榜应当直接 driver.get(url) 强制 navigate"""
    body = _extract_func(WORKER_SRC, "_scrape_fanqie_all_ranks")
    assert "self.driver.get(url)" in body, \
        "扫榜应该直接 self.driver.get(url) 强制 navigate"


def test_03_uses_dom_query():
    """改用 JS DOM 查询(querySelectorAll)而不只靠 page_source 正则"""
    body = _extract_func(WORKER_SRC, "_scrape_fanqie_all_ranks")
    assert "querySelectorAll" in body, \
        "应该用 querySelectorAll 抓 DOM(React 应用 page_source 不可靠)"
    assert "a[href*=\"/page/\"]" in body or "a[href*='/page/'" in body, \
        "应该查询 /page/ 链接拿 book_id"


def test_04_wait_for_react_render():
    """driver.get 后必须等 ≥ 2 秒让 React 渲染完"""
    body = _extract_func(WORKER_SRC, "_scrape_fanqie_all_ranks")
    # 找 time.sleep 后的数字
    sleeps = re.findall(r"time\.sleep\((\d+(?:\.\d+)?)\)", body)
    sleeps_f = [float(s) for s in sleeps]
    assert sleeps_f and max(sleeps_f) >= 2.0, \
        f"应该有 ≥ 2 秒的等待让 React 渲染完,实际 sleeps: {sleeps_f}"


def test_05_page_source_fallback_kept():
    """JS 抓取失败时仍 fallback 到 page_source 正则(双保险)"""
    body = _extract_func(WORKER_SRC, "_scrape_fanqie_all_ranks")
    assert "page_source" in body, "fallback 路径应该保留 page_source"
    assert "parse_rank_page_minimal" in body, \
        "fallback 应该走 parse_rank_page_minimal"


def test_06_book_id_min_10_digits():
    """JS 抓 book_id 要求至少 10 位数字(防误中其它短数字)"""
    body = _extract_func(WORKER_SRC, "_scrape_fanqie_all_ranks")
    # 在 JS 字符串里应该有 \d{10,} 或类似
    assert re.search(r"\\d\{10", body) or r"\d{10," in body, \
        "应该限制 book_id 至少 10 位数字"


def test_07_app_version_bumped():
    """APP_VERSION 升到 v2.23.2+(允许 v2.23.X 任何 patch 号)"""
    assert re.search(r'APP_VERSION\s*=\s*["\']v2\.23\.[2-9]\d*["\']', NOVEL_AI_SRC) \
           or re.search(r'APP_VERSION\s*=\s*["\']v2\.2[4-9]', NOVEL_AI_SRC) \
           or re.search(r'APP_VERSION\s*=\s*["\']v[3-9]', NOVEL_AI_SRC), \
        "APP_VERSION 应该升到 v2.23.2 或更高"


def test_08_bug087_marker_in_comments():
    """BUG-087 标识在 worker 代码里(便于追溯)"""
    assert "BUG-087" in WORKER_SRC, \
        "worker 里应该有 BUG-087 注释标识"


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
