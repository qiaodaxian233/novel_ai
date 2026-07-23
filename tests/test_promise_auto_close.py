"""
test_promise_auto_close.py — v1.77 BUG-057 威胁承诺自动闭环

覆盖(对照 v1.76 test_foreshadow_auto_close.py 模式):
A. prompt 设计层(world_extract 规则 9/10 + promise_check + promise_reeval)
B. 代码层(4 新方法存在 + 类归属正确 + target 路由 + pipeline 阶段)
C. UI 层(威胁承诺 Tab 顶部 label + AI 重评估按钮 + 7 列结构)
D. 行为层(build_inject_block 强约束块 + dl=0 不超期 + merge/serialize)
X. 守(防御性)
"""
import re
import ast
import pytest
from tests_helpers import read_all_sources


@pytest.fixture(scope="module")
def src():
    # v2.07:读全源(模块化拆分后)

    return read_all_sources()


@pytest.fixture(scope="module")
def tree(src):
    return ast.parse(src)


@pytest.fixture(scope="module")
def prompts(src):
    m = re.search(r"PROMPTS = \{(.*?)^\}", src, re.DOTALL | re.MULTILINE)
    assert m, "PROMPTS dict 未找到"
    return eval("{" + m.group(1) + "}")


def _method_class(tree, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name == method_name:
                    return node.name
    return None


# ─────────────────────────────────────
# A. prompt 设计层
# ─────────────────────────────────────

def test_A1_world_extract_has_promises_field(prompts):
    """world_extract 必须新增 promises 字段"""
    we = prompts["world_extract"]
    assert '"promises"' in we
    # 必须有 kind/from/to/content/deadline 五字段
    for k in ("kind", '"from"', '"to"', "content", "deadline"):
        assert k in we, f"world_extract 缺字段 {k}"


def test_A2_world_extract_promises_rule_classifies_types(prompts):
    """规则 9 必须明确"承诺/威胁/约定"三类型"""
    we = prompts["world_extract"]
    assert "承诺/威胁/约定" in we
    assert "promise" in we and "threat" in we and "appointment" in we


def test_A3_world_extract_deadline_no_zero(prompts):
    """规则 10 必须禁止 deadline 填 0,给四档保守值"""
    we = prompts["world_extract"]
    # 规则段必须出现禁 0
    assert "不要填 0" in we
    # 必须给即时/短期/中期/长期四档指导
    assert "即时兑现" in we
    assert "短期约定" in we
    assert "中期承诺" in we
    assert "长期誓言" in we


def test_A4_world_extract_deadline_has_conservative_default(prompts):
    """规则 10 必须给保守默认值(+15)"""
    we = prompts["world_extract"]
    assert "+15" in we or "当前章+15" in we


def test_A5_promise_check_prompt_exists(prompts):
    assert "promise_check" in prompts
    pc = prompts["promise_check"]
    for ph in ("{promise_list}", "{ch_num}", "{content}"):
        assert ph in pc


def test_A6_promise_check_outcome_enumerated(prompts):
    """promise_check 必须枚举 outcome:履行/执行/赴约/违约/化解"""
    pc = prompts["promise_check"]
    for outcome in ("履行", "执行", "赴约", "违约", "化解"):
        assert outcome in pc


def test_A7_promise_check_demands_json_array(prompts):
    """promise_check 必须明确要 JSON 数组(防 list-vs-dict)"""
    pc = prompts["promise_check"]
    assert "JSON 数组" in pc or "[]" in pc
    assert "id" in pc


def test_A8_promise_check_substantial_only(prompts):
    """promise_check 必须强调"实质了断",防止模糊提及"""
    pc = prompts["promise_check"]
    assert "实质" in pc or "了断" in pc


def test_A9_promise_reeval_prompt_exists(prompts):
    assert "promise_reeval" in prompts
    pr = prompts["promise_reeval"]
    for ph in ("{promise_list}", "{current_ch}"):
        assert ph in pr


def test_A10_promise_reeval_forbids_zero(prompts):
    """promise_reeval 必须禁止返回 0"""
    pr = prompts["promise_reeval"]
    assert "不要返回 0" in pr or "禁止" in pr.replace(" ", "")


def test_A11_promise_reeval_future_only(prompts):
    """promise_reeval 必须要求 deadline > current_ch"""
    pr = prompts["promise_reeval"]
    assert "> {current_ch}" in pr or "在未来" in pr


def test_A12_promise_reeval_four_tiers(prompts):
    """promise_reeval 必须给四档分类指导(对应 world_extract 规则 10)"""
    pr = prompts["promise_reeval"]
    assert "即时兑现" in pr
    assert "短期" in pr
    assert "中期" in pr
    assert "长期" in pr


def test_A13_promise_check_format_runs(prompts):
    out = prompts["promise_check"].format(
        promise_list='[{"id":0,"content":"x"}]',
        ch_num=5, content="测试正文")
    assert "第 5 章" in out
    assert "测试正文" in out


def test_A14_promise_reeval_format_runs(prompts):
    out = prompts["promise_reeval"].format(
        current_ch=20, promise_list='[{"id":0}]')
    assert "第 20 章" in out


# ─────────────────────────────────────
# B. 代码层
# ─────────────────────────────────────

def test_B1_run_promise_check_in_mainwindow(tree):
    assert _method_class(tree, "_run_promise_check") == "MainWindow"


def test_B2_on_promise_check_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_promise_check_response") == "MainWindow"


def test_B3_reeval_zero_deadline_promise_in_mainwindow(tree):
    """按钮回调必须在 MainWindow,不是 CharacterLibrary"""
    assert _method_class(tree, "_reeval_zero_deadline_promise") == "MainWindow"


def test_B4_on_promise_reeval_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_promise_reeval_response") == "MainWindow"


def test_B5_build_promises_tab_in_characterlibrary(tree):
    """_build_promises_tab 是 UI 构建,必须在 CharacterLibrary"""
    assert _method_class(tree, "_build_promises_tab") == "CharacterLibrary"


def test_B6_add_del_promise_in_characterlibrary(tree):
    assert _method_class(tree, "_add_promise") == "CharacterLibrary"
    assert _method_class(tree, "_del_promise") == "CharacterLibrary"


def test_B7_target_route_promise_check(src):
    """target 路由必须包含 promise_check 分支"""
    assert 'target == "promise_check"' in src
    m = re.search(
        r'target == "promise_check":\s*\n(.*?)(?:elif|else)',
        src, re.DOTALL)
    assert m
    assert "_on_promise_check_response" in m.group(1)


def test_B8_target_route_promise_reeval(src):
    assert 'target == "promise_reeval"' in src


def test_B9_pipeline_has_promise_check_stage(src):
    """_post_chapter_chain 必须挂 promise_check 阶段,在 foreshadow_check 之后"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert 'pipeline.append(("promise_check"' in block
    assert 'pipeline.append(("foreshadow_check"' in block
    pc_pos = block.find('pipeline.append(("promise_check"')
    fs_pos = block.find('pipeline.append(("foreshadow_check"')
    assert pc_pos > fs_pos, "promise_check 必须挂在 foreshadow_check 之后"


def test_B10_pipeline_handler_promise_check(src):
    """_run_next_post_chapter_step 必须有 promise_check 分支"""
    assert 'step[0] == "promise_check"' in src


def test_B11_signal_connect_promise_reeval_button(src):
    """_connect_signals 必须连接 btn_reeval_promise.clicked"""
    assert "btn_reeval_promise" in src
    assert "_reeval_zero_deadline_promise" in src


def test_B12_promises_in_sub_tabs_init(src):
    """_build_promises_tab 必须在 sub_tabs init 序列里被调用"""
    m = re.search(
        r"self\._build_foreshadows_tab\(\)\s*\n\s*self\._build_promises_tab\(\)",
        src)
    assert m, "_build_promises_tab 必须在 _build_foreshadows_tab 之后被调用"


# ─────────────────────────────────────
# C. UI 层
# ─────────────────────────────────────

def test_C1_lbl_last_promise_check_exists(src):
    """威胁承诺 Tab 顶部必须有 lbl_last_promise_check"""
    assert "lbl_last_promise_check" in src
    assert "自动兑现检查" in src or "📌 自动兑现检查" in src


def test_C2_reeval_promise_button_exists(src):
    """威胁承诺 Tab 必须有 AI 重评估按钮"""
    assert "btn_reeval_promise" in src
    assert "重评估" in src
    # 按钮文字必须能让用户看出是"未设截止期"
    assert "未设截止期" in src or "deadline" in src


def test_C3_promises_tab_has_7_columns(src):
    """tbl_promises 必须 7 列(埋设章/类型/发起者/对象/内容/截止章/已兑现?)"""
    m = re.search(r"self\.tbl_promises = QTableWidget\(0, (\d+)\)", src)
    assert m, "tbl_promises 初始化未找到"
    assert m.group(1) == "7", f"tbl_promises 应 7 列,实际 {m.group(1)}"
    # header 必须列全
    for header in ("埋设章", "类型", "发起者", "对象", "内容", "截止章", "已兑现"):
        assert header in src


def test_C4_promises_tab_title_emoji(src):
    """sub_tab 标题必须是 ⚡ 威胁承诺"""
    assert 'addTab(w, "⚡ 威胁承诺")' in src


def test_C5_lbl_last_promise_check_multi_state(src):
    """lbl_last_promise_check 必须有多处 setText(成功/空/失败)"""
    matches = re.findall(r"lbl_last_promise_check\.setText\(", src)
    assert len(matches) >= 3, f"应有多处 setText(初始/成功/空/失败),实际 {len(matches)}"


# ─────────────────────────────────────
# D. 行为层
# ─────────────────────────────────────

def test_D1_build_inject_block_dl_zero_not_overdue(src):
    """build_inject_block 里 dl=0 应该走"未评估"分支,不算超期"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    # 必须有 dl_int == 0 的特判
    assert "dl_int == 0" in block
    # 必须有 pr_pending 收集列表
    assert "pr_pending" in block
    # 必须有"待AI评估"flag
    assert "待AI评估" in block


def test_D2_build_inject_block_pr_must_pay_strict(src):
    """build_inject_block 必须输出'本章硬性必须兑现'强约束块"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "pr_must_pay" in block
    assert "硬性必须兑现" in block
    assert "履行/执行/赴约/违约/化解" in block
    # 禁止敷衍
    assert "改日再说" in block or "失信" in block


def test_D3_build_inject_block_separate_from_foreshadow(src):
    """威胁承诺块必须与伏笔块分开(两块独立)"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 两个标题必须都存在
    assert "【待兑现承诺/威胁/约定" in block
    assert "【待回收伏笔" in block
    # 伏笔块在前,承诺块在后
    fo_pos = block.find("【待回收伏笔")
    pr_pos = block.find("【待兑现承诺")
    assert fo_pos < pr_pos, "伏笔块应在承诺块之前"


def test_D4_reeval_only_targets_dl_zero(src):
    """_reeval_zero_deadline_promise 必须只挑 deadline=0 的行"""
    m = re.search(
        r"def _reeval_zero_deadline_promise\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "int(dl)" in block
    # 必须 != 0 时 continue
    assert "continue" in block


def test_D5_on_promise_check_response_writes_paid(src):
    """_on_promise_check_response 命中后必须 setItem(rid, 6, "是")"""
    m = re.search(
        r"def _on_promise_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert 'QTableWidgetItem("是")' in block
    assert "setItem(rid, 6" in block


def test_D6_on_promise_reeval_response_writes_deadline(src):
    """_on_promise_reeval_response 必须写第 5 列 deadline"""
    m = re.search(
        r"def _on_promise_reeval_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "setItem(rid, 5" in block


def test_D7_on_promise_reeval_guards_against_zero(src):
    """守 — AI 又返回 0 或过去章节时强制 +15 fallback"""
    m = re.search(
        r"def _on_promise_reeval_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "new_dl <= current_ch" in block or "<= current_ch" in block
    # fallback +15
    assert "+ 15" in block or "+15" in block


def test_D8_run_promise_check_skips_when_no_pending(src):
    """_run_promise_check 库里没未兑现承诺时必须跳过 + 推进 pipeline"""
    m = re.search(
        r"def _run_promise_check\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "if not pending" in block or "len(pending) == 0" in block
    assert "_run_next_post_chapter_step" in block


def test_D9_pipeline_only_appends_when_pending(src):
    """pipeline 必须只在库里有未兑现承诺时挂 promise_check 阶段"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "_has_pending_pr" in block


def test_D10_serialize_includes_promises(src):
    """serialize 必须输出 promises key(7 列)"""
    m = re.search(
        r"def serialize\(self\):.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert '"promises"' in block
    assert "tbl_to_list(self.tbl_promises, 7)" in block


def test_D11_load_includes_promises(src):
    """load DICT_KEY_MAPS 必须含 promises 7 字段"""
    m = re.search(
        r"DICT_KEY_MAPS = \{[^}]+\}",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert '"promises":' in block
    assert '"kind"' in block and '"deadline"' in block and '"fulfilled"' in block


def test_D12_merge_into_charlib_adds_pr_counter(src):
    """_merge_into_charlib 必须有 promises 合并 + pr 计数"""
    m = re.search(
        r"def _merge_into_charlib\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "tbl_promises" in block
    assert 'added["pr"]' in block or 'added.get("pr"' in block


def test_D13_all_empty_includes_promises(src):
    """all_empty 检测必须包含 promises"""
    # all_empty 的 not any(...) 是多行带元组,直接 grep 段落
    m = re.search(
        r'all_empty = not any\((.+?)\n        \)',
        src, re.DOTALL)
    assert m, "all_empty 段未找到"
    block = m.group(1)
    assert "promises" in block, f"all_empty 段缺 promises,实际: {block[:200]}"


def test_D14_completion_log_shows_promise_count(src):
    """6 库提取完成日志必须显示承诺计数"""
    assert "承诺+" in src


def test_D15_diagnostic_print_promise(src):
    """诊断日志:_run_promise_check 和 _on_promise_check_response 必须 print"""
    for method in ("_run_promise_check", "_on_promise_check_response"):
        m = re.search(
            rf"def {method}\(.*?(?=\n    def )",
            src, re.DOTALL)
        assert m
        block = m.group(0)
        assert "[promise-check v1.77]" in block, f"{method} 缺诊断日志"


# ─────────────────────────────────────
# X. 守(防御性)
# ─────────────────────────────────────

def test_X1_on_promise_check_guards_non_list(src):
    """_on_promise_check_response 必须有 isinstance(arr, list) 守"""
    m = re.search(
        r"def _on_promise_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X2_on_promise_check_guards_non_dict_item(src):
    """循环 it 必须 isinstance dict 守"""
    m = re.search(
        r"def _on_promise_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(it, dict)" in block


def test_X3_on_promise_reeval_guards_non_list(src):
    m = re.search(
        r"def _on_promise_reeval_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X4_version_bumped_to_1_77_or_higher(src):
    """APP_VERSION 必须 ≥ v1.77(v1.77 引入了 promise auto close)"""
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)(?:\.\d+)?"', src)
    assert m, "APP_VERSION 未找到"
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 77), \
        f"v1.77 的 promise 闭环不应被低版本退回,当前 v{major}.{minor}"
