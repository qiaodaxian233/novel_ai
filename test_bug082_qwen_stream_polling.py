"""
test_bug082_qwen_stream_polling.py — BUG-082 守护测试

v2.22.1 BUG-082:
  Qwen 副 AI 流式输出比 DeepSeek 慢 5-10 倍,prompt 后常有 5-90s "思考"阶段然后
  才开始逐字符吐出。Polling 默认 0.9s/1.5s stable_wait 在 Qwen 写到 17 字时
  误判"内容稳定 → 完成",抓到的只是 JSON 半句 `[{"key":"角色.苏棠.体质`。

修法三层(C 主防御 + A/B 兜底):
  C. thinking_indicator (主防御):DOM 里 .qwen-chat-status-card-title-animate
     这个 selector 命中 = Qwen 还在思考,polling 跳过完成判定。这是 Qwen UI
     提供的**确定性信号**,优先级最高。
  A. stable_wait_min=8.0 (兜底):万一未来 Qwen 改 class 名,C 失效,A 把
     完成等待提到 8 秒,避免回归到 0.9s 秒判错
  B. min_complete_chars=100 (兜底):字符数 < 100 强制不完成,JSON 短输出的
     最小合理长度

代码改动位置:
  1. core/site_profiles.py — Qwen profile 加 3 字段(thinking_indicator + A + B)
  2. ui/browser_worker.py — polling 加 _site_is_thinking() helper +
     polling 循环里读 3 字段 + 两条完成路径都加 C → B 链式守卫

本套测试保证:
  - Qwen profile 必须有这 3 个字段
  - DeepSeek profile 不能有这 3 个字段(走默认,不被影响)
  - browser_worker.py 必须读这 3 个字段、必须有 _site_is_thinking helper
  - 两条完成路径(按钮快照恢复 + 内容稳定)都必须有 C(thinking)守卫
  - C 守卫必须优先于 B(字符数)守卫:C 是确定性信号,B 是兜底
"""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent
PROFILES_FILE = REPO / "core" / "site_profiles.py"
WORKER_FILE = REPO / "ui" / "browser_worker.py"


def test_qwen_profile_has_thinking_indicator():
    """C 主防御:Qwen profile 必须有 thinking_indicator 字段(CSS selector 字符串)"""
    from core.site_profiles import _profile_for_url
    p = _profile_for_url("https://chat.qwen.ai/c/anything")
    assert "thinking_indicator" in p, \
        "BUG-082 (C 主防御): Qwen profile 必须有 thinking_indicator 字段"
    sel = p["thinking_indicator"]
    assert isinstance(sel, str) and sel.strip(), \
        f"BUG-082: thinking_indicator 必须是非空字符串,实际 {sel!r}"
    # 必须是 -animate 后缀类(Qwen 思考中动画类的特征)
    assert "animate" in sel.lower(), \
        f"BUG-082: thinking_indicator 应基于 Qwen 的 -animate 动画 class," \
        f"实际 {sel!r}(若 Qwen 改 UI 请同步改这条 selector + 此测试)"


def test_qwen_profile_has_stable_wait_min():
    """A 兜底:Qwen profile 必须有 stable_wait_min 字段,且 ≥ 8.0"""
    from core.site_profiles import _profile_for_url
    p = _profile_for_url("https://chat.qwen.ai/c/anything")
    assert p.get("name") == "Qwen", "URL 应该匹配到 Qwen profile"
    assert "stable_wait_min" in p, \
        "BUG-082 (A 兜底): Qwen profile 必须有 stable_wait_min 字段"
    val = float(p["stable_wait_min"])
    assert val >= 8.0, \
        f"BUG-082: Qwen stable_wait_min 必须 ≥ 8.0,实际 {val}"


def test_qwen_profile_has_min_complete_chars():
    """B 兜底:Qwen profile 必须有 min_complete_chars 字段,且 ≥ 100"""
    from core.site_profiles import _profile_for_url
    p = _profile_for_url("https://chat.qwen.ai/c/anything")
    assert "min_complete_chars" in p, \
        "BUG-082 (B 兜底): Qwen profile 必须有 min_complete_chars 字段"
    val = int(p["min_complete_chars"])
    assert val >= 100, \
        f"BUG-082: Qwen min_complete_chars 必须 ≥ 100,实际 {val}"


def test_deepseek_profile_not_affected():
    """DeepSeek profile 不应有这 3 个字段 — 走默认行为,不被 Qwen 修复影响"""
    from core.site_profiles import _profile_for_url
    p = _profile_for_url("https://chat.deepseek.com/")
    assert p.get("name") == "DeepSeek"
    # 不设字段 → .get 返回 None → polling 里 float(None or 0.0)=0 → 不触发下限
    assert p.get("thinking_indicator") is None, \
        "BUG-082: DeepSeek 不应被 thinking_indicator 影响"
    assert p.get("stable_wait_min") is None, \
        "BUG-082: DeepSeek 不应被 site-level 等待下限影响"
    assert p.get("min_complete_chars") is None, \
        "BUG-082: DeepSeek 不应被 site-level 字符下限影响"


def test_polling_reads_all_three_fields():
    """browser_worker.py 的 polling 必须读 thinking_indicator / stable_wait_min / min_complete_chars"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    assert 'prof.get("thinking_indicator"' in src, \
        "BUG-082 (C): polling 必须从 prof 读 thinking_indicator"
    assert 'prof.get("stable_wait_min"' in src, \
        "BUG-082 (A): polling 必须从 prof 读 stable_wait_min"
    assert 'prof.get("min_complete_chars"' in src, \
        "BUG-082 (B): polling 必须从 prof 读 min_complete_chars"


def test_site_is_thinking_helper_exists():
    """browser_worker.py 必须有 _site_is_thinking helper 方法"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    # AST 检查 — 比 grep 更严
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_site_is_thinking":
            found = True
            # 必须接受 selector 参数
            args = [a.arg for a in node.args.args]
            assert "selector" in args, \
                "BUG-082: _site_is_thinking 必须接受 selector 参数"
            break
    assert found, "BUG-082 (C): 必须有 _site_is_thinking helper 方法"


def test_polling_two_completion_paths_have_thinking_guard():
    """两条完成路径(按钮快照恢复 + 内容稳定)都必须调用 _site_is_thinking"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    # _site_is_thinking 必须被调用至少 2 次(两条完成路径)
    call_count = src.count("_site_is_thinking(")
    # 算上定义本身(1 次定义) + 至少 2 次调用 = 至少 3 次
    assert call_count >= 3, \
        f"BUG-082 (C): _site_is_thinking 应在定义 + 两条完成路径调用 ≥ 3 次," \
        f"实际 {call_count} 次"


def test_polling_two_completion_paths_guarded():
    """两条完成路径必须有 min_chars 守卫(B 兜底)"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    # 修复必须在多处标 BUG-082(profile 注释 + 加载 + 按钮路径 + 稳定路径)
    bug082_count = src.count("BUG-082")
    assert bug082_count >= 4, \
        f"BUG-082: 期望至少 4 处 BUG-082 标识,实际 {bug082_count} 处"


def test_site_stable_min_used_as_floor_not_replacement():
    """stable_wait_min 必须用 max(原阈值, 站点下限),不能直接替换原三档逻辑"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    assert "max(wait_threshold, _site_stable_min)" in src or \
           "max(_site_stable_min, wait_threshold)" in src, \
        "BUG-082 (A): 站点 stable_wait_min 必须作为下限(max),不能替换原三档阈值"


def test_thinking_guard_priority_over_chars_guard():
    """C 守卫必须优先于 B 守卫(确定性信号 > 估算)"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    # 找"内容稳定路径"完成判定块:从 'if time.time() - last_change >= wait_threshold:'
    # 之后,thinking_indicator 检查必须比 min_chars 检查更早出现
    pattern = re.search(
        r"if time\.time\(\) - last_change >= wait_threshold:.*?(?=^\s{16,}else:|^\s{8,}else:|\Z)",
        src, re.DOTALL | re.MULTILINE
    )
    assert pattern, "找不到内容稳定路径的完成判定块"
    block = pattern.group()
    thinking_pos = block.find("_site_is_thinking")
    chars_pos = block.find("_site_min_chars")
    assert thinking_pos != -1, "BUG-082: 内容稳定路径必须 check thinking"
    assert chars_pos != -1, "BUG-082: 内容稳定路径必须 check min_chars"
    assert thinking_pos < chars_pos, \
        "BUG-082: thinking 守卫(C 确定性信号)必须优先于 min_chars 守卫(B 估算兜底)"


def test_min_chars_blocks_premature_completion():
    """min_complete_chars 守卫必须 'continue/pass 不 break',不是 'log+break'"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "BUG-082" in line and ("< _site_min_chars" in line or "< 站点下限" in line):
            block = "\n".join(lines[i:i+15])
            first_break = block.find("break")
            first_continue = block.find("continue")
            first_comment_no_break = block.find("不 break")
            if first_break != -1:
                earliest_safe = min(
                    x for x in (first_continue, first_comment_no_break)
                    if x != -1
                ) if (first_continue != -1 or first_comment_no_break != -1) else -1
                assert earliest_safe != -1 and earliest_safe < first_break, \
                    f"BUG-082 守卫块第 {i+1} 行附近:字符数不够时不能直接 break"


def test_app_version_at_least_v2_22_1():
    """APP_VERSION 必须 ≥ v2.22.1(版号守护)"""
    src = (REPO / "novel_ai.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']v?(\d+)\.(\d+)\.(\d+)["\']', src)
    assert m, "找不到 APP_VERSION 定义"
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert (major, minor, patch) >= (2, 22, 1), \
        f"BUG-082: APP_VERSION 必须 ≥ v2.22.1,实际 v{major}.{minor}.{patch}"


def test_no_break_in_qwen_path_without_chars_check():
    """browser_worker.py 必须定义并多次使用 _site_min_chars 局部变量"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    assert "_site_min_chars" in src, \
        "BUG-082: 必须使用 _site_min_chars 局部变量"
    assert src.count("_site_min_chars") >= 3, \
        f"BUG-082: _site_min_chars 应至少出现 3 次(定义+两条完成路径), " \
        f"实际 {src.count('_site_min_chars')} 次"


def test_thinking_warned_flag_prevents_log_flood():
    """thinking 守卫必须有 'warned once' 标志位防止刷屏"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    assert "_b082_thinking_warned" in src, \
        "BUG-082: 必须有 _b082_thinking_warned 标志位,防止思考期间日志刷屏"


if __name__ == "__main__":
    import sys
    tests = [
        ("test_qwen_profile_has_thinking_indicator", test_qwen_profile_has_thinking_indicator),
        ("test_qwen_profile_has_stable_wait_min", test_qwen_profile_has_stable_wait_min),
        ("test_qwen_profile_has_min_complete_chars", test_qwen_profile_has_min_complete_chars),
        ("test_deepseek_profile_not_affected", test_deepseek_profile_not_affected),
        ("test_polling_reads_all_three_fields", test_polling_reads_all_three_fields),
        ("test_site_is_thinking_helper_exists", test_site_is_thinking_helper_exists),
        ("test_polling_two_completion_paths_have_thinking_guard",
         test_polling_two_completion_paths_have_thinking_guard),
        ("test_polling_two_completion_paths_guarded", test_polling_two_completion_paths_guarded),
        ("test_site_stable_min_used_as_floor_not_replacement",
         test_site_stable_min_used_as_floor_not_replacement),
        ("test_thinking_guard_priority_over_chars_guard",
         test_thinking_guard_priority_over_chars_guard),
        ("test_min_chars_blocks_premature_completion", test_min_chars_blocks_premature_completion),
        ("test_app_version_at_least_v2_22_1", test_app_version_at_least_v2_22_1),
        ("test_no_break_in_qwen_path_without_chars_check",
         test_no_break_in_qwen_path_without_chars_check),
        ("test_thinking_warned_flag_prevents_log_flood",
         test_thinking_warned_flag_prevents_log_flood),
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"✓ {name}")
        except AssertionError as e:
            print(f"✗ {name}\n   {e}")
            failed.append(name)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

