"""
test_foreshadow_auto_close.py — v1.76 BUG-056 全自动伏笔闭环

覆盖:
A. prompt 设计层(world_extract 规则 6 + foreshadow_check + foreshadow_reeval)
B. 代码层(4 个新方法存在 + 类归属正确 + target 路由 + pipeline 阶段)
C. UI 层(伏笔 Tab 顶部 label + AI 重评估按钮)
D. 行为层(_build_writer_context 强约束块 + ch_pay=0 不超期)
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


# ─────────────────────────────────────
# A. prompt 设计层
# ─────────────────────────────────────

def test_A1_world_extract_rule6_no_zero(prompts):
    """world_extract 规则 6 必须明确禁止填 0 + 给保守值指导"""
    we = prompts["world_extract"]
    assert "绝对不要填 0" in we or "0 是无效值" in we
    # 旧规则的"无法判断填 '0'"必须删除
    assert "无法判断填 '0'" not in we


def test_A2_world_extract_rule6_has_conservative_default(prompts):
    """规则 6 必须给保守默认值指导(+30 / 当前章+X)"""
    we = prompts["world_extract"]
    assert "+30" in we or "当前章" in we


def test_A3_foreshadow_check_prompt_exists(prompts):
    assert "foreshadow_check" in prompts
    fc = prompts["foreshadow_check"]
    # 必须有 3 个 placeholder
    assert "{foreshadow_list}" in fc
    assert "{ch_num}" in fc
    assert "{content}" in fc


def test_A4_foreshadow_check_demands_json_array(prompts):
    """foreshadow_check 必须明确要 JSON 数组(防 list-vs-dict bug)"""
    fc = prompts["foreshadow_check"]
    assert "JSON 数组" in fc or "JSON" in fc
    # 没有任何回收时返回 []
    assert "[]" in fc


def test_A5_foreshadow_check_id_constraint(prompts):
    """foreshadow_check 必须要求 id 从清单取,不让 AI 凭空造"""
    fc = prompts["foreshadow_check"]
    assert "id" in fc
    assert "凭空" in fc or "从" in fc


def test_A6_foreshadow_check_substantial_only(prompts):
    """foreshadow_check 必须强调'实质回收',防止模糊提及"""
    fc = prompts["foreshadow_check"]
    assert "实质" in fc or "明确" in fc


def test_A7_foreshadow_reeval_prompt_exists(prompts):
    assert "foreshadow_reeval" in prompts
    fr = prompts["foreshadow_reeval"]
    assert "{foreshadow_list}" in fr
    assert "{current_ch}" in fr


def test_A8_foreshadow_reeval_forbids_zero(prompts):
    """foreshadow_reeval 必须明确禁止返回 0"""
    fr = prompts["foreshadow_reeval"]
    assert "不要返回 0" in fr or "不要返回0" in fr or "禁止" in fr.replace(" ", "")


def test_A9_foreshadow_reeval_future_only(prompts):
    """foreshadow_reeval 必须要求 plan_pay_at > current_ch(未来章节)"""
    fr = prompts["foreshadow_reeval"]
    assert "> {current_ch}" in fr or "在未来" in fr


def test_A10_foreshadow_reeval_tier_guidance(prompts):
    """foreshadow_reeval 必须给小钩子/中线/主线分层指导"""
    fr = prompts["foreshadow_reeval"]
    assert "小钩子" in fr
    assert "中线" in fr or "中线伏笔" in fr
    assert "主线" in fr


def test_A11_foreshadow_check_format_runs(prompts):
    """foreshadow_check 必须能 format 不报错"""
    out = prompts["foreshadow_check"].format(
        foreshadow_list='[{"id":0,"content":"x"}]',
        ch_num=5, content="测试正文")
    assert "第 5 章" in out
    assert "测试正文" in out


def test_A12_foreshadow_reeval_format_runs(prompts):
    """foreshadow_reeval 必须能 format"""
    out = prompts["foreshadow_reeval"].format(
        current_ch=20, foreshadow_list='[{"id":0,"content":"x"}]')
    assert "第 20 章" in out


# ─────────────────────────────────────
# B. 代码层
# ─────────────────────────────────────

def _method_class(tree, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name == method_name:
                    return node.name
    return None


def test_B1_run_foreshadow_check_in_mainwindow(tree):
    """_run_foreshadow_check 必须在 MainWindow"""
    assert _method_class(tree, "_run_foreshadow_check") == "MainWindow"


def test_B2_on_foreshadow_check_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_foreshadow_check_response") == "MainWindow"


def test_B3_reeval_zero_pay_at_in_mainwindow(tree):
    """_reeval_zero_pay_at(按钮回调)必须在 MainWindow,不是 CharacterLibrary"""
    assert _method_class(tree, "_reeval_zero_pay_at") == "MainWindow"


def test_B4_on_foreshadow_reeval_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_foreshadow_reeval_response") == "MainWindow"


def test_B5_build_foreshadows_tab_in_characterlibrary(tree):
    """_build_foreshadows_tab 是 UI 构建,必须在 CharacterLibrary"""
    assert _method_class(tree, "_build_foreshadows_tab") == "CharacterLibrary"


def test_B6_target_route_foreshadow_check(src):
    """target 路由必须包含 foreshadow_check 分支"""
    assert 'target == "foreshadow_check"' in src
    # 必须调 _on_foreshadow_check_response
    rt_match = re.search(
        r'target == "foreshadow_check":\s*\n(.*?)(?:elif|else)',
        src, re.DOTALL)
    assert rt_match
    assert "_on_foreshadow_check_response" in rt_match.group(1)


def test_B7_target_route_foreshadow_reeval(src):
    """target 路由必须包含 foreshadow_reeval 分支"""
    assert 'target == "foreshadow_reeval"' in src


def test_B8_pipeline_has_foreshadow_check_stage(src):
    """_post_chapter_chain 必须挂 foreshadow_check 阶段,且在 charlib_extract 后"""
    # 取 _post_chapter_chain 函数体
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m, "_post_chapter_chain 找不到"
    block = m.group(0)
    assert 'pipeline.append(("foreshadow_check"' in block
    assert 'pipeline.append(("charlib_extract"' in block
    # 在函数体内,foreshadow_check 必须出现在 charlib_extract 之后
    fs_pos = block.find('pipeline.append(("foreshadow_check"')
    cl_pos = block.find('pipeline.append(("charlib_extract"')
    assert fs_pos > cl_pos, "foreshadow_check 必须挂在 charlib_extract 之后"


def test_B9_pipeline_handler_foreshadow_check(src):
    """_run_next_post_chapter_step 必须有 foreshadow_check 分支"""
    assert 'step[0] == "foreshadow_check"' in src


def test_B10_signal_connect_reeval_button(src):
    """_connect_signals 必须连接 btn_reeval_fore.clicked"""
    assert "btn_reeval_fore" in src
    assert "_reeval_zero_pay_at" in src


# ─────────────────────────────────────
# C. UI 层
# ─────────────────────────────────────

def test_C1_lbl_last_check_in_foreshadows_tab(src):
    """伏笔 Tab 顶部必须有 lbl_last_check label"""
    assert "lbl_last_check" in src
    # 必须有初始文案(覆盖"尚未运行"或"自动回收检查")
    assert "📌 自动回收检查" in src or "自动回收检查" in src


def test_C2_reeval_button_exists(src):
    """伏笔 Tab 必须有 AI 重评估按钮"""
    assert "btn_reeval_fore" in src
    assert "AI 重评估" in src or "重评估未设回收期" in src


def test_C3_lbl_last_check_updated_on_success(src):
    """成功时必须更新 lbl_last_check label(✅ 状态)"""
    # 至少有 setText 调用 lbl_last_check
    matches = re.findall(r"lbl_last_check\.setText\(", src)
    assert len(matches) >= 3, f"应有多处更新(成功/空/失败),实际 {len(matches)}"


def test_C4_lbl_last_check_has_failure_state(src):
    """失败时 label 必须显示 ⚠ 提示"""
    # 找出所有 setText 调用周围
    assert "⚠ 最近检查" in src or "JSON 解析失败" in src


# ─────────────────────────────────────
# D. 行为层
# ─────────────────────────────────────

def test_D1_build_inject_block_ch_pay_zero_skipped(src):
    """build_inject_block 里 ch_pay=0 应该走"待AI评估"分支,不算超期"""
    # 找 build_inject_block 段(从 def 到下一个 def)
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m, "build_inject_block 找不到"
    block = m.group(0)
    # 必须有 ch_pay_int == 0 的特判
    assert "ch_pay_int == 0" in block
    # 必须有"待AI评估"或"未评估"flag
    assert "未评估" in block or "AI评估" in block


def test_D2_build_inject_block_must_pay_strict_constraint(src):
    """build_inject_block 必须输出'本章硬性必须回收'强约束块"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "must_pay" in block or "硬性必须回收" in block
    assert "硬性必须回收" in block or "不允许跳过" in block


def test_D3_check_foreshadow_alert_skips_ch_pay_zero(src):
    """_check_foreshadow_alert(生成前弹窗)必须跳过 ch_pay=0"""
    m = re.search(
        r"def _check_foreshadow_alert\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m, "_check_foreshadow_alert 找不到"
    block = m.group(0)
    # 必须有 ch_pay_int == 0 的 continue/skip
    assert "ch_pay_int == 0" in block


def test_D4_reeval_only_targets_zero(src):
    """_reeval_zero_pay_at 必须只挑 ch_pay=0 的行(过滤非 0)"""
    m = re.search(
        r"def _reeval_zero_pay_at\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    # 必须有 int(ch_pay) != 0 的 continue
    assert "int(ch_pay)" in block
    assert "continue" in block


def test_D5_on_foreshadow_check_response_writes_paid_yes(src):
    """_on_foreshadow_check_response 命中后必须写 setItem(rid, 3, "是")"""
    m = re.search(
        r"def _on_foreshadow_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    # 必须写第 3 列(已回收)为"是"
    assert 'QTableWidgetItem("是")' in block
    # 必须写第 4 列(回收章节)为当前章
    assert "setItem(rid, 4" in block


def test_D6_on_foreshadow_reeval_response_writes_plan_pay_at(src):
    """_on_foreshadow_reeval_response 必须写第 2 列 plan_pay_at"""
    m = re.search(
        r"def _on_foreshadow_reeval_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "setItem(rid, 2" in block


def test_D7_on_foreshadow_reeval_guards_against_zero(src):
    """_on_foreshadow_reeval_response 守 — AI 又返回 0 或过去章节时强制 +30 fallback"""
    m = re.search(
        r"def _on_foreshadow_reeval_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "new_pay <= current_ch" in block or "<= current_ch" in block
    # fallback +30
    assert "+ 30" in block or "+30" in block


def test_D8_run_foreshadow_check_skips_when_no_pending(src):
    """_run_foreshadow_check 库里没未回收伏笔时必须跳过 + 推进 pipeline"""
    m = re.search(
        r"def _run_foreshadow_check\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    # 必须有"无可检查"或"无未回收"逻辑
    assert "if not pending" in block or "len(pending) == 0" in block
    # 必须推进 pipeline
    assert "_run_next_post_chapter_step" in block


def test_D9_pipeline_only_appends_when_has_pending(src):
    """_post_chapter_chain 必须只在库里有未回收伏笔时才挂 foreshadow_check 阶段"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    # 必须有 _has_pending 或类似条件
    assert "_has_pending" in block or "has_pending" in block


def test_D10_response_diagnostic_print(src):
    """诊断日志:_on_foreshadow_check_response 必须 print 原始回复前 200 字"""
    m = re.search(
        r"def _on_foreshadow_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "[foreshadow-check v1.76]" in block
    # 原始回复诊断
    assert "AI 原始回复" in block


# ─────────────────────────────────────
# 兜底:防 list-vs-dict / 非 list 守
# ─────────────────────────────────────

def test_X1_on_foreshadow_check_guards_non_list(src):
    """_on_foreshadow_check_response 必须有 isinstance(arr, list) 守"""
    m = re.search(
        r"def _on_foreshadow_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X2_on_foreshadow_check_guards_non_dict_item(src):
    """循环里 it 必须 isinstance dict 守"""
    m = re.search(
        r"def _on_foreshadow_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(it, dict)" in block


def test_X3_version_bumped_to_1_76_or_higher(src):
    """APP_VERSION 必须 ≥ v1.76(v1.76 引入了 foreshadow auto close)"""
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)"', src)
    assert m, "APP_VERSION 未找到"
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 76), \
        f"v1.76 的 foreshadow 闭环不应被低版本退回,当前 v{major}.{minor}"
