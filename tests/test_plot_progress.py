"""
test_plot_progress.py — v1.78 BUG-058 剧情进度管理

3 子表 = 故事弧线 / 关系值矩阵 / 当前目标(统一放在 📈 剧情进度 sub-tab)。
模式复用 v1.77 promise 闭环,但关键不同:
  - delta 累加(不是设布尔标记) — arc.progress += delta(封顶 100),rel_value += delta(封顶 ±100)
  - 没有 reeval 按钮(progress/value 是连续值,没有"评估失败"的二元状态)
  - 注入块分 3 段:【当前弧线进度】(全) + 【当前关系热点】(|value|≥50 前 8) + 【主角当前目标】(进行中)

覆盖:
  A. prompt 设计(world_extract 12/13/14 + arc_advance_check + relation_change_check)
  B. 代码层(4 新方法存在 + 类归属正确 + target 路由 + pipeline 阶段)
  C. UI 层(剧情进度 Tab + lbl_last_arc_check + 3 子表 + 列数 + 标题)
  D. 行为层(merge/serialize/inject + delta 累加 + clamping)
  X. 守(防御性)
"""
import re
import ast
import json
import os
import sys
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

def test_A1_world_extract_has_arcs_field(prompts):
    """world_extract 必须新增 arcs 字段"""
    we = prompts["world_extract"]
    assert '"arcs"' in we
    # 三字段都要在 schema 里
    for f in ('"name"', '"progress"', '"phase"'):
        assert f in we, f"world_extract 缺 arcs 字段 {f}"


def test_A2_world_extract_has_relations_value_field(prompts):
    """world_extract 必须新增 relations_value 字段"""
    we = prompts["world_extract"]
    assert '"relations_value"' in we
    # 字段:a/b/value/ch
    for f in ('"value"', '"ch"'):
        assert f in we


def test_A3_world_extract_has_goals_field(prompts):
    """world_extract 必须新增 goals 字段"""
    we = prompts["world_extract"]
    assert '"goals"' in we
    for f in ('"priority"', '"status"', '"set_ch"'):
        assert f in we


def test_A4_world_extract_phase_enum(prompts):
    """arcs.phase 必须是 5 选 1 枚举"""
    we = prompts["world_extract"]
    # 5 个阶段在规则里
    for ph in ("开端", "铺垫", "转折", "高潮", "收束"):
        assert ph in we, f"phase 枚举缺 {ph}"


def test_A5_world_extract_rule_12_arcs_progress_bounds(prompts):
    """规则 12 必须给 phase × progress 的对应区间"""
    we = prompts["world_extract"]
    # 必须有 progress 分档说明
    assert "progress" in we
    # 必须明确 0-100
    assert "0-100" in we or "0~100" in we


def test_A6_world_extract_rule_13_value_bounds(prompts):
    """规则 13 必须明确 value -100~+100 范围 + 关系定级"""
    we = prompts["world_extract"]
    # 范围
    assert "-100" in we and "+100" in we
    # 定级关键词
    for v in ("死敌", "朋友", "陌生"):
        assert v in we


def test_A7_world_extract_rule_14_goals_priority_status(prompts):
    """规则 14 必须明确 priority 三选一 + status 三选一"""
    we = prompts["world_extract"]
    for v in ("主线", "支线", "紧急", "进行中", "已达成", "已放弃"):
        assert v in we, f"goals 枚举缺 {v}"


def test_A8_arc_advance_check_prompt_exists(prompts):
    assert "arc_advance_check" in prompts
    p = prompts["arc_advance_check"]
    for ph in ("{arc_list}", "{ch_num}", "{content}"):
        assert ph in p


def test_A9_arc_advance_check_delta_range(prompts):
    """arc_advance_check 必须明确 delta 1-15 分档"""
    p = prompts["arc_advance_check"]
    # 1-15 或 +1~3 / +5~10 / +10~15
    assert "+1~3" in p or "+1-3" in p or "1-15" in p
    assert "+10~15" in p or "+10-15" in p or "决战" in p


def test_A10_arc_advance_check_progress_cap(prompts):
    """arc_advance_check 必须说明 progress 上限 100"""
    p = prompts["arc_advance_check"]
    assert "100" in p


def test_A11_arc_advance_check_demands_json_array(prompts):
    p = prompts["arc_advance_check"]
    assert "JSON 数组" in p or "[]" in p


def test_A12_arc_advance_check_substantial_only(prompts):
    """arc_advance_check 必须强调"实质推进",防止泛泛而谈"""
    p = prompts["arc_advance_check"]
    assert "实质" in p or "推进" in p


def test_A13_relation_change_check_prompt_exists(prompts):
    assert "relation_change_check" in prompts
    p = prompts["relation_change_check"]
    for ph in ("{relation_list}", "{ch_num}", "{content}"):
        assert ph in p


def test_A14_relation_change_check_delta_range(prompts):
    """relation_change_check 必须明确 delta ±50 上限"""
    p = prompts["relation_change_check"]
    assert "-50" in p or "±50" in p or "50" in p
    # 必须给三档(小/中/大变化)
    assert "小变化" in p or "±5" in p


def test_A15_relation_change_check_value_cap(prompts):
    """relation_change_check 必须说明 value 上下限 ±100"""
    p = prompts["relation_change_check"]
    assert "+100" in p and "-100" in p


def test_A16_relation_change_check_new_pair_id_minus_one(prompts):
    """relation_change_check 必须支持 id=-1(本章新建关系对)"""
    p = prompts["relation_change_check"]
    assert "-1" in p
    assert "新" in p  # "新建" / "新建立的"


def test_A17_arc_advance_check_format_runs(prompts):
    out = prompts["arc_advance_check"].format(
        arc_list='[{"id":0,"name":"x","progress":10,"phase":"开端"}]',
        ch_num=5, content="测试正文")
    assert "第 5 章" in out
    assert "测试正文" in out


def test_A18_relation_change_check_format_runs(prompts):
    out = prompts["relation_change_check"].format(
        relation_list='[{"id":0,"a":"主角","b":"反派","value":-30}]',
        ch_num=10, content="测试正文")
    assert "第 10 章" in out


def test_A19_world_extract_format_includes_new_fields(prompts):
    """world_extract.format() 应包含新字段占位"""
    out = prompts["world_extract"].format(
        ch_num=7, existing="", content="测试")
    assert '"arcs"' in out
    assert '"relations_value"' in out
    assert '"goals"' in out


# ─────────────────────────────────────
# B. 代码层
# ─────────────────────────────────────

def test_B1_run_arc_advance_check_in_mainwindow(tree):
    assert _method_class(tree, "_run_arc_advance_check") == "MainWindow"


def test_B2_on_arc_advance_check_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_arc_advance_check_response") == "MainWindow"


def test_B3_run_relation_change_check_in_mainwindow(tree):
    assert _method_class(tree, "_run_relation_change_check") == "MainWindow"


def test_B4_on_relation_change_check_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_relation_change_check_response") == "MainWindow"


def test_B5_build_plot_progress_tab_in_characterlibrary(tree):
    """UI 构建必须在 CharacterLibrary"""
    assert _method_class(tree, "_build_plot_progress_tab") == "CharacterLibrary"


def test_B6_add_del_methods_in_characterlibrary(tree):
    for m in ("_add_arc", "_del_arc", "_add_rel_value", "_del_rel_value",
              "_add_goal", "_del_goal"):
        assert _method_class(tree, m) == "CharacterLibrary", f"{m} 应在 CharacterLibrary"


def test_B7_target_route_arc_advance_check(src):
    """target 路由必须包含 arc_advance_check 分支"""
    assert 'target == "arc_advance_check"' in src
    m = re.search(
        r'target == "arc_advance_check":\s*\n(.*?)(?:elif|else)',
        src, re.DOTALL)
    assert m
    assert "_on_arc_advance_check_response" in m.group(1)


def test_B8_target_route_relation_change_check(src):
    assert 'target == "relation_change_check"' in src
    m = re.search(
        r'target == "relation_change_check":\s*\n(.*?)(?:elif|else)',
        src, re.DOTALL)
    assert m
    assert "_on_relation_change_check_response" in m.group(1)


def test_B9_pipeline_has_arc_advance_check_stage(src):
    """_post_chapter_chain 必须挂 arc_advance_check 阶段,在 promise_check 之后"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert 'pipeline.append(("arc_advance_check"' in block
    assert 'pipeline.append(("promise_check"' in block
    arc_pos = block.find('pipeline.append(("arc_advance_check"')
    pc_pos = block.find('pipeline.append(("promise_check"')
    assert arc_pos > pc_pos, "arc_advance_check 必须挂在 promise_check 之后"


def test_B10_pipeline_has_relation_change_check_stage(src):
    """_post_chapter_chain 必须挂 relation_change_check 阶段,在 arc_advance_check 之后"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert 'pipeline.append(("relation_change_check"' in block
    arc_pos = block.find('pipeline.append(("arc_advance_check"')
    rel_pos = block.find('pipeline.append(("relation_change_check"')
    assert rel_pos > arc_pos, "relation_change_check 必须挂在 arc_advance_check 之后"


def test_B11_pipeline_handler_arc_advance_check(src):
    """_run_next_post_chapter_step 必须有 arc_advance_check 分支"""
    assert 'step[0] == "arc_advance_check"' in src


def test_B12_pipeline_handler_relation_change_check(src):
    assert 'step[0] == "relation_change_check"' in src


def test_B13_plot_progress_tab_in_sub_tabs_init(src):
    """_build_plot_progress_tab 必须在 sub_tabs init 序列里被调用,在 _build_promises_tab 之后"""
    m = re.search(
        r"self\._build_promises_tab\(\)\s*[^\n]*\n\s*self\._build_plot_progress_tab\(\)",
        src)
    assert m, "_build_plot_progress_tab 必须在 _build_promises_tab 之后被调用"


def test_B14_no_reeval_button_for_plot_progress(src):
    """蓝图明确说 v1.78 无 reeval 按钮 — 不应存在 btn_reeval_arc/btn_reeval_progress 等"""
    # 这是个反向检查:确保没有意外添加 reeval 按钮
    assert "btn_reeval_arc" not in src
    assert "btn_reeval_goal" not in src
    # _reeval_arcs / _reeval_plot 等也不该存在
    assert "_reeval_arcs" not in src
    assert "_reeval_plot_progress" not in src


# ─────────────────────────────────────
# C. UI 层
# ─────────────────────────────────────

def test_C1_lbl_last_arc_check_exists(src):
    """剧情进度 Tab 顶部必须有 lbl_last_arc_check"""
    assert "lbl_last_arc_check" in src
    assert "自动弧线/关系值评估" in src or "自动弧线" in src


def test_C2_three_subtables_constructed(src):
    """必须构造 3 个 QTableWidget:tbl_arcs / tbl_rel_values / tbl_goals"""
    m_arc = re.search(r"self\.tbl_arcs = QTableWidget\(0, (\d+)\)", src)
    assert m_arc, "tbl_arcs 初始化未找到"
    assert m_arc.group(1) == "3", f"tbl_arcs 应 3 列,实际 {m_arc.group(1)}"

    m_rv = re.search(r"self\.tbl_rel_values = QTableWidget\(0, (\d+)\)", src)
    assert m_rv, "tbl_rel_values 初始化未找到"
    assert m_rv.group(1) == "4", f"tbl_rel_values 应 4 列,实际 {m_rv.group(1)}"

    m_gl = re.search(r"self\.tbl_goals = QTableWidget\(0, (\d+)\)", src)
    assert m_gl, "tbl_goals 初始化未找到"
    assert m_gl.group(1) == "4", f"tbl_goals 应 4 列,实际 {m_gl.group(1)}"


def test_C3_arcs_table_headers(src):
    """tbl_arcs 必须有:弧线名 / 当前进度 / 阶段"""
    for header in ("弧线名", "当前进度", "阶段"):
        assert header in src


def test_C4_rel_values_table_headers(src):
    """tbl_rel_values 必须有:角色A / 角色B / 关系值 / 最近变化章"""
    for header in ("角色A", "角色B", "关系值", "最近变化章"):
        assert header in src


def test_C5_goals_table_headers(src):
    """tbl_goals 必须有:目标名 / 优先级 / 状态 / 设立章节"""
    for header in ("目标名", "优先级", "状态", "设立章节"):
        assert header in src


def test_C6_plot_progress_tab_title_emoji(src):
    """sub_tab 标题必须是 📈 剧情进度"""
    assert 'addTab(w, "📈 剧情进度")' in src


def test_C7_inner_tab_titles(src):
    """嵌套 tab 标题必须能让用户看出 3 子页"""
    # 至少要有三个 emoji + 中文标识
    for title in ("📊 故事弧线", "💞 关系值矩阵", "🎯 当前目标"):
        assert title in src, f"内嵌 tab 标题缺 {title}"


def test_C8_lbl_last_arc_check_multi_state(src):
    """lbl_last_arc_check 必须有多处 setText(初始/成功/空/失败)"""
    matches = re.findall(r"lbl_last_arc_check\.setText\(", src)
    assert len(matches) >= 3, f"应有多处 setText,实际 {len(matches)}"


# ─────────────────────────────────────
# D. 行为层
# ─────────────────────────────────────

def test_D1_build_inject_block_has_arc_progress_section(src):
    """build_inject_block 必须有【当前弧线进度】段"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "【当前弧线进度】" in block
    assert "tbl_arcs" in block


def test_D2_build_inject_block_has_relation_hot_section(src):
    """build_inject_block 必须有【当前关系热点】段,只取 |value|>=50"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "【当前关系热点" in block
    assert "tbl_rel_values" in block
    # 必须按绝对值筛选
    assert "abs(val)" in block
    assert "< 50" in block or ">= 50" in block


def test_D3_build_inject_block_has_goals_section(src):
    """build_inject_block 必须有【主角当前目标】段,只取进行中"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "【主角当前目标" in block
    assert "tbl_goals" in block
    # 必须过滤 status != 进行中
    assert "进行中" in block


def test_D4_build_inject_block_relation_hot_uses_mentioned_names(src):
    """关系热点段必须能基于 mentioned_names 筛选(防止注入无关角色的关系值)"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # mentioned_names 筛选发生在收集 hot 列表的循环里(在 append 标题之前)
    # 整段函数必须包含 mentioned_names 的过滤逻辑 + 关系热点收集
    assert "mentioned_names" in block
    assert "tbl_rel_values" in block
    # 必须有"在循环里基于 mentioned_names 过滤角色"的代码段:
    # mentioned_names 出现后,要么 continue 要么不收入 hot 列表
    # 找 tbl_rel_values 段
    rel_idx = block.find("tbl_rel_values")
    assert rel_idx >= 0
    rel_block = block[rel_idx:rel_idx + 2500]
    # 关系收集段里必须用到 mentioned_names
    assert "mentioned_names" in rel_block, \
        "关系热点收集段必须用 mentioned_names 过滤"


def test_D5_on_arc_advance_check_response_adds_delta(src):
    """_on_arc_advance_check_response 必须用 += delta(累加,不是覆盖)"""
    m = re.search(
        r"def _on_arc_advance_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    # 必须读 old + delta
    assert "old + delta" in block or "old+delta" in block
    # 必须封顶 100
    assert "min(100" in block
    # 必须 setItem(rid, 1, ...) — 第 1 列是 progress
    assert "setItem(rid, 1" in block


def test_D6_on_arc_advance_check_response_clamps_delta(src):
    """_on_arc_advance_check_response 必须 clamp delta 到 0~15(守 AI 越界)"""
    m = re.search(
        r"def _on_arc_advance_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # max(0, min(15, delta)) 或类似
    assert "min(15" in block and "max(0" in block


def test_D7_on_relation_change_check_response_handles_existing_pair(src):
    """_on_relation_change_check_response 必须能更新已有关系对(rid>=0 → 累加)"""
    m = re.search(
        r"def _on_relation_change_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "0 <= rid" in block or "rid >= 0" in block
    # 累加逻辑
    assert "old + delta" in block or "old+delta" in block
    # 封顶 ±100
    assert "min(100" in block and "max(-100" in block


def test_D8_on_relation_change_check_response_handles_new_pair(src):
    """_on_relation_change_check_response 必须支持新建关系对(rid==-1)"""
    m = re.search(
        r"def _on_relation_change_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "rid == -1" in block
    # 新建时必须填 a/b/value/ch
    assert "insertRow" in block


def test_D9_on_relation_change_check_response_clamps_delta(src):
    """_on_relation_change_check_response 必须 clamp delta 到 ±50"""
    m = re.search(
        r"def _on_relation_change_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "min(50" in block and "max(-50" in block


def test_D10_run_arc_advance_check_skips_when_all_completed(src):
    """_run_arc_advance_check 库里无可推进弧线(全部 100%)时必须跳过"""
    m = re.search(
        r"def _run_arc_advance_check\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    # 必须有 progress>=100 跳过
    assert ">= 100" in block or "= 100" in block
    # 必须有跳过 → _run_next_post_chapter_step
    assert "_run_next_post_chapter_step" in block


def test_D11_pipeline_only_appends_when_open_arc(src):
    """pipeline 必须只在库里有未完成弧线时挂 arc_advance_check"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "_has_open_arc" in block


def test_D12_pipeline_only_appends_when_existing_relations(src):
    """pipeline 必须只在库里有关系对时挂 relation_change_check"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "_has_rel" in block


def test_D13_serialize_includes_v178_fields(src):
    """serialize 必须输出 arcs / relations_value / goals"""
    m = re.search(
        r"def serialize\(self\):.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert '"arcs"' in block
    assert '"relations_value"' in block
    assert '"goals"' in block
    assert "tbl_to_list(self.tbl_arcs, 3)" in block
    assert "tbl_to_list(self.tbl_rel_values, 4)" in block
    assert "tbl_to_list(self.tbl_goals, 4)" in block


def test_D14_load_dict_key_maps_includes_v178(src):
    """load 的 DICT_KEY_MAPS 必须含 arcs / relations_value / goals"""
    m = re.search(
        r"DICT_KEY_MAPS = \{[^}]+\}",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert '"arcs":' in block
    assert '"relations_value":' in block
    assert '"goals":' in block
    # 字段全
    assert '"progress"' in block and '"phase"' in block
    assert '"value"' in block
    assert '"priority"' in block and '"status"' in block and '"set_ch"' in block


def test_D15_merge_into_charlib_adds_v178_counters(src):
    """_merge_into_charlib 必须有 arc/rv/gl 计数 + 3 段合并代码"""
    m = re.search(
        r"def _merge_into_charlib\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "tbl_arcs" in block
    assert "tbl_rel_values" in block
    assert "tbl_goals" in block
    assert 'added["arc"]' in block or 'added.get("arc"' in block
    assert 'added["rv"]' in block or 'added.get("rv"' in block
    assert 'added["gl"]' in block or 'added.get("gl"' in block


def test_D16_merge_arc_progress_takes_max(src):
    """arc 合并必须取 max(old_progress, new_progress)— 不回退"""
    m = re.search(
        r"def _merge_into_charlib\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 找 arcs 段
    arc_idx = block.find("故事弧线 arcs")
    assert arc_idx >= 0
    arc_block = block[arc_idx:arc_idx + 1500]
    # 必须有 new_prog > old_prog 的判断
    assert "new_prog > old_prog" in arc_block or "new_prog >old_prog" in arc_block


def test_D17_all_empty_includes_v178_fields(src):
    """all_empty 检测必须包含 arcs/relations_value/goals"""
    m = re.search(
        r'all_empty = not any\((.+?)\n        \)',
        src, re.DOTALL)
    assert m, "all_empty 段未找到"
    block = m.group(1)
    assert "arcs" in block, f"all_empty 缺 arcs: {block[:300]}"
    assert "relations_value" in block, f"all_empty 缺 relations_value"
    assert "goals" in block, f"all_empty 缺 goals"


def test_D18_completion_log_shows_v178_counts(src):
    """6 库提取完成日志必须显示弧线/关系值/目标计数"""
    assert "弧线+" in src
    assert "关系值+" in src
    assert "目标+" in src


def test_D19_diagnostic_print_arc(src):
    """诊断日志:_run_arc_advance_check 和 _on_arc_advance_check_response 必须 print"""
    for method in ("_run_arc_advance_check", "_on_arc_advance_check_response"):
        m = re.search(
            rf"def {method}\(.*?(?=\n    def )",
            src, re.DOTALL)
        assert m
        block = m.group(0)
        assert "[arc-check v1.78]" in block, f"{method} 缺诊断日志"


def test_D20_diagnostic_print_rel(src):
    for method in ("_run_relation_change_check", "_on_relation_change_check_response"):
        m = re.search(
            rf"def {method}\(.*?(?=\n    def )",
            src, re.DOTALL)
        assert m
        block = m.group(0)
        assert "[rel-check v1.78]" in block, f"{method} 缺诊断日志"


def test_D21_inject_block_phase_displayed(src):
    """弧线注入块必须显示 phase(开端/铺垫/转折/高潮/收束)"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # phase 渲染发生在收集 arc_lines 的循环里(在 parts.append 标题之前)
    arc_idx = block.find("tbl_arcs")
    assert arc_idx >= 0
    # 找到 arc_lines / arc_progress 收集段
    nearby = block[arc_idx:arc_idx + 2500]
    # 必须有 [{ph}] / [{phase}] 在收集行里 — 或者明确 phase 变量出现在 append 行
    assert "[{ph}]" in nearby or "[{phase}]" in nearby, \
        "arc 注入行应显示 phase,如 f'弧线名: 35% [{ph}]'"


def test_D22_inject_block_goals_priority_sorted(src):
    """目标段必须按 紧急 > 主线 > 支线 排序"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 排序逻辑在 tbl_goals 收集段(在 parts.append 标题之前)
    g_idx = block.find("tbl_goals")
    assert g_idx >= 0
    nearby = block[g_idx:g_idx + 2500]
    # 必须有排序逻辑 — 三个优先级关键词都要出现
    assert "紧急" in nearby and "主线" in nearby and "支线" in nearby


# ─────────────────────────────────────
# 行为层 — 运行时端到端(需要 Qt)
# ─────────────────────────────────────

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PyQt5 = pytest.importorskip("PyQt5", reason="PyQt5 not available")


@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    a = QApplication.instance() or QApplication(sys.argv)
    yield a


@pytest.fixture
def charlib(app):
    """干净的 CharacterLibrary 实例"""
    sys.path.insert(0, os.path.dirname(__file__) or ".")
    from novel_ai import CharacterLibrary
    return CharacterLibrary()


def test_D23_merge_dicts_arcs(charlib):
    added = charlib.merge_dicts({
        "arcs": [
            {"name": "主线-灭门复仇", "progress": 35, "phase": "铺垫"},
            {"name": "支线", "progress": 5, "phase": "开端"},
        ]
    })
    assert added["arc"] == 2
    assert charlib.tbl_arcs.rowCount() == 2


def test_D24_merge_dicts_arcs_progress_taken_higher(charlib):
    charlib.merge_dicts({"arcs": [{"name": "主线", "progress": 35, "phase": "铺垫"}]})
    charlib.merge_dicts({"arcs": [{"name": "主线", "progress": 25, "phase": "开端"}]})
    # 应保留 35,不回退到 25
    assert charlib.tbl_arcs.item(0, 1).text() == "35"


def test_D25_merge_dicts_arcs_progress_clamped(charlib):
    charlib.merge_dicts({"arcs": [{"name": "主线", "progress": 500, "phase": "高潮"}]})
    # 应封顶 100
    assert charlib.tbl_arcs.item(0, 1).text() == "100"


def test_D26_merge_dicts_relations_value_clamped(charlib):
    charlib.merge_dicts({"relations_value": [
        {"a": "A", "b": "B", "value": -500, "ch": "1"},
        {"a": "C", "b": "D", "value": 999, "ch": "1"},
    ]})
    # 应封顶 ±100
    assert charlib.tbl_rel_values.item(0, 2).text() == "-100"
    assert charlib.tbl_rel_values.item(1, 2).text() == "100"


def test_D27_merge_dicts_relations_value_dedupe_updates(charlib):
    charlib.merge_dicts({"relations_value": [
        {"a": "主角", "b": "反派", "value": -30, "ch": "1"}]})
    charlib.merge_dicts({"relations_value": [
        {"a": "主角", "b": "反派", "value": -80, "ch": "5"}]})
    # 同一对 a→b 第二次应更新 value 和 ch(不新建)
    assert charlib.tbl_rel_values.rowCount() == 1
    assert charlib.tbl_rel_values.item(0, 2).text() == "-80"
    assert charlib.tbl_rel_values.item(0, 3).text() == "5"


def test_D28_merge_dicts_goals_dedupe_updates_status(charlib):
    charlib.merge_dicts({"goals": [
        {"name": "找仇人", "priority": "主线", "status": "进行中", "set_ch": "1"}]})
    charlib.merge_dicts({"goals": [
        {"name": "找仇人", "priority": "主线", "status": "已达成", "set_ch": "1"}]})
    assert charlib.tbl_goals.rowCount() == 1
    # status 应更新为"已达成"
    assert charlib.tbl_goals.item(0, 2).text() == "已达成"


def test_D29_serialize_load_roundtrip(charlib, app):
    charlib.merge_dicts({
        "arcs": [{"name": "主线", "progress": 50, "phase": "转折"}],
        "relations_value": [{"a": "主角", "b": "对手", "value": -80, "ch": "10"}],
        "goals": [{"name": "突破", "priority": "主线", "status": "进行中", "set_ch": "5"}],
    })
    out = charlib.serialize()
    from novel_ai import CharacterLibrary
    cl2 = CharacterLibrary()
    cl2.load(out)
    assert cl2.tbl_arcs.rowCount() == 1
    assert cl2.tbl_arcs.item(0, 0).text() == "主线"
    assert cl2.tbl_arcs.item(0, 1).text() == "50"
    assert cl2.tbl_rel_values.item(0, 2).text() == "-80"
    assert cl2.tbl_goals.item(0, 2).text() == "进行中"


def test_D30_build_inject_block_includes_all_three_v178_sections(charlib):
    charlib.merge_dicts({
        "arcs": [{"name": "主线", "progress": 35, "phase": "铺垫"}],
        "relations_value": [
            {"a": "主角", "b": "反派", "value": -80, "ch": "3"},
            {"a": "主角", "b": "盟友", "value": 60, "ch": "5"},
            {"a": "主角", "b": "陌生人", "value": 10, "ch": "1"},  # |10|<50,不该出现
        ],
        "goals": [
            {"name": "找仇人", "priority": "主线", "status": "进行中", "set_ch": "1"},
            {"name": "已完成事", "priority": "支线", "status": "已达成", "set_ch": "2"},
        ],
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=10)
    assert "【当前弧线进度】" in block
    assert "【当前关系热点" in block
    assert "【主角当前目标" in block
    assert "主线" in block
    # |value|<50 不该出现
    assert "陌生人" not in block
    # 已达成目标不该出现
    assert "已完成事" not in block


def test_D31_build_inject_block_relation_filtered_by_mentioned_names(charlib):
    charlib.merge_dicts({
        "relations_value": [
            {"a": "林远", "b": "王屠户", "value": -80, "ch": "3"},
            {"a": "孙悟空", "b": "牛魔王", "value": -80, "ch": "5"},
        ]
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=10,
                                       mentioned_names={"林远", "王屠户"})
    # 出场的对儿出现
    assert "林远" in block
    # 不出场的关系热点不该污染本章注入
    assert "孙悟空" not in block


# ─────────────────────────────────────
# X. 守(防御性)
# ─────────────────────────────────────

def test_X1_on_arc_advance_check_guards_non_list(src):
    """_on_arc_advance_check_response 必须有 isinstance(arr, list) 守"""
    m = re.search(
        r"def _on_arc_advance_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X2_on_arc_advance_check_guards_non_dict_item(src):
    m = re.search(
        r"def _on_arc_advance_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(it, dict)" in block


def test_X3_on_relation_change_check_guards_non_list(src):
    m = re.search(
        r"def _on_relation_change_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X4_on_relation_change_check_guards_non_dict_item(src):
    m = re.search(
        r"def _on_relation_change_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(it, dict)" in block


def test_X5_run_arc_advance_check_guards_no_tbl(src):
    """_run_arc_advance_check 必须守 hasattr(charlib, tbl_arcs)"""
    m = re.search(
        r"def _run_arc_advance_check\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert 'hasattr(self.tab_charlib, "tbl_arcs")' in block


def test_X6_run_relation_change_check_guards_no_tbl(src):
    m = re.search(
        r"def _run_relation_change_check\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert 'hasattr(self.tab_charlib, "tbl_rel_values")' in block


def test_X7_version_bumped_to_1_78_or_higher(src):
    """APP_VERSION 必须 ≥ v1.78"""
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)(?:\.\d+)?"', src)
    assert m, "APP_VERSION 未找到"
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 78), \
        f"v1.78 的剧情进度不应被低版本退回,当前 v{major}.{minor}"


def test_X8_inject_block_empty_when_inject_off(charlib):
    """chk_inject 关闭时,build_inject_block 应返回空串(连 v1.78 段也不出)"""
    charlib.merge_dicts({"arcs": [{"name": "主线", "progress": 50, "phase": "转折"}]})
    charlib.chk_inject.setChecked(False)
    block = charlib.build_inject_block(current_chapter=10)
    assert block == ""
