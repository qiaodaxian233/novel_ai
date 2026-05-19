"""
test_info_isolation.py — v1.79 BUG-059 信息隔离控制

与 v1.76/v1.77/v1.78 的关键差异:
  - 数据形态:2 表 via info_id 外键引用(infos.id ↔ known_by.info_id)
  - check 语义:info_check 是【侦测违规】 — AI 返回的是"哪些角色穿帮了",
    系统标红警告不自动修(修正文需要重写,超出本版范围)
  - 自动续号:tbl_infos 的 id 用 INFO-001/INFO-002 顺序编号,
    AI 用占位符也能在 merge 时被重映射;known_by 引用悬挂时自动过滤
  - 注入:【角色已知信息边界】 — 既列"X 已知:[...]"又列"本章不应触及的:[...]"
    (双向防御 — 既防角色用他不知道的,也防作者无意中泄露伏笔)

覆盖:
  A. prompt 设计(world_extract 15/16 + info_check + info_disclose_check)
  B. 代码层(4 新方法 + 类归属 + target 路由 + pipeline 顺序)
  C. UI 层(信息隔离 Tab + lbl_last_info_check + 2 子表 + 列数 + 标题)
  D. 行为层(merge/serialize/inject + id 续号 + 悬挂过滤)
  X. 守(防御性)
"""
import re
import ast
import json
import os
import sys
import pytest


@pytest.fixture(scope="module")
def src():
    with open("novel_ai.py", encoding="utf-8") as f:
        return f.read()


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

def test_A1_world_extract_has_infos_field(prompts):
    we = prompts["world_extract"]
    assert '"infos"' in we
    for f in ('"content"', '"source_ch"', '"source_type"'):
        assert f in we, f"world_extract 缺 infos 字段 {f}"


def test_A2_world_extract_has_info_disclosures_field(prompts):
    we = prompts["world_extract"]
    assert '"info_disclosures"' in we
    for f in ('"info_id"', '"to"', '"via"'):
        assert f in we


def test_A3_world_extract_rule_15_info_id_format(prompts):
    """规则 15 必须说明 id 用 INFO-XXX 自动续号"""
    we = prompts["world_extract"]
    assert "INFO-001" in we
    assert "去重和续号" in we or "顺序编号" in we


def test_A4_world_extract_rule_15_source_type_enum(prompts):
    """source_type 必须是三选一:设定/事件揭露/角色透露"""
    we = prompts["world_extract"]
    for v in ("设定", "事件揭露", "角色透露"):
        assert v in we


def test_A5_world_extract_rule_16_via_paths(prompts):
    """规则 16 必须给清晰的 via 路径示例"""
    we = prompts["world_extract"]
    for v in ("出生即知", "亲口告诉", "亲眼见"):
        assert v in we


def test_A6_world_extract_rule_16_no_orphan_knowing(prompts):
    """规则 16 必须强调『知情链断了不要补』"""
    we = prompts["world_extract"]
    assert "知情链" in we or "没见证" in we


def test_A7_info_check_prompt_exists(prompts):
    assert "info_check" in prompts
    p = prompts["info_check"]
    for ph in ("{known_table}", "{ch_num}", "{content}"):
        assert ph in p


def test_A8_info_check_is_violation_detection(prompts):
    """info_check 必须是【侦测违规】 — 不是状态推进"""
    p = prompts["info_check"]
    assert "穿帮" in p
    # 输出格式:violations 列表
    assert "info_id" in p
    assert "character" in p
    assert "evidence" in p
    assert "why_should_not_know" in p


def test_A9_info_check_demands_evidence_quote(prompts):
    """info_check 必须要求 evidence 是【正文里的实际句子】"""
    p = prompts["info_check"]
    assert "原文" in p or "摘录" in p
    # 必须强调"宁可放过 5 个不要冤枉 1 个"的保守原则
    assert "放过" in p or "拿不准" in p or "宁可" in p


def test_A10_info_check_protag_exempt(prompts):
    """info_check 必须明确主角是合法的(主角什么都知道)"""
    p = prompts["info_check"]
    assert "主角" in p
    assert "默认是合法" in p or "什么都知道" in p


def test_A11_info_check_ignores_group_reactions(prompts):
    """info_check 必须忽略群体反应(『众人窃窃私语』不算穿帮)"""
    p = prompts["info_check"]
    assert "群体" in p or "众人" in p


def test_A12_info_disclose_check_prompt_exists(prompts):
    assert "info_disclose_check" in prompts
    p = prompts["info_disclose_check"]
    for ph in ("{info_table}", "{known_table}", "{ch_num}", "{content}"):
        assert ph in p


def test_A13_info_disclose_check_no_duplicates(prompts):
    """info_disclose_check 必须强调『已知情人不要重复列』"""
    p = prompts["info_disclose_check"]
    assert "已经" in p and "重复" in p


def test_A14_info_disclose_check_protag_exempt(prompts):
    """info_disclose_check 必须不要列主角(主角默认就是出生即知)"""
    p = prompts["info_disclose_check"]
    assert "主角" in p
    assert "出生即知" in p


def test_A15_info_disclose_check_via_specific(prompts):
    """info_disclose_check 必须要求 via 具体(亲口告诉/亲眼见/读到字条)"""
    p = prompts["info_disclose_check"]
    for v in ("亲口", "亲眼", "字条"):
        assert v in p


def test_A16_info_check_format_runs(prompts):
    """info_check format 不应崩"""
    out = prompts["info_check"].format(
        known_table='[{"info_id":"INFO-001","content":"x","knowers":["林远"]}]',
        ch_num=10, content="测试")
    assert "第 10 章" in out


def test_A17_info_disclose_check_format_runs(prompts):
    out = prompts["info_disclose_check"].format(
        info_table='[]', known_table='[]', ch_num=10, content="测试")
    assert "第 10 章" in out


def test_A18_world_extract_format_runs_with_infos(prompts):
    out = prompts["world_extract"].format(ch_num=10, existing="", content="测试")
    assert '"infos"' in out
    assert '"info_disclosures"' in out


# ─────────────────────────────────────
# B. 代码层
# ─────────────────────────────────────

def test_B1_run_info_check_in_mainwindow(tree):
    assert _method_class(tree, "_run_info_check") == "MainWindow"


def test_B2_on_info_check_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_info_check_response") == "MainWindow"


def test_B3_run_info_disclose_check_in_mainwindow(tree):
    assert _method_class(tree, "_run_info_disclose_check") == "MainWindow"


def test_B4_on_info_disclose_check_response_in_mainwindow(tree):
    assert _method_class(tree, "_on_info_disclose_check_response") == "MainWindow"


def test_B5_build_known_table_snapshot_in_mainwindow(tree):
    """构造已知信息边界表的工具方法必须在 MainWindow"""
    assert _method_class(tree, "_build_known_table_snapshot") == "MainWindow"


def test_B6_build_info_isolation_tab_in_characterlibrary(tree):
    assert _method_class(tree, "_build_info_isolation_tab") == "CharacterLibrary"


def test_B7_add_del_methods_in_characterlibrary(tree):
    for m in ("_add_info", "_del_info", "_add_known_by", "_del_known_by"):
        assert _method_class(tree, m) == "CharacterLibrary", f"{m} 应在 CharacterLibrary"


def test_B8_target_route_info_check(src):
    assert 'target == "info_check"' in src
    m = re.search(
        r'target == "info_check":\s*\n(.*?)(?:elif|else)',
        src, re.DOTALL)
    assert m
    assert "_on_info_check_response" in m.group(1)


def test_B9_target_route_info_disclose_check(src):
    assert 'target == "info_disclose_check"' in src
    m = re.search(
        r'target == "info_disclose_check":\s*\n(.*?)(?:elif|else)',
        src, re.DOTALL)
    assert m
    assert "_on_info_disclose_check_response" in m.group(1)


def test_B10_pipeline_has_info_disclose_check_stage(src):
    """info_disclose_check 必须在 relation_change_check 之后"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert 'pipeline.append(("info_disclose_check"' in block
    rel_pos = block.find('pipeline.append(("relation_change_check"')
    disc_pos = block.find('pipeline.append(("info_disclose_check"')
    assert disc_pos > rel_pos, "info_disclose_check 必须在 relation_change_check 之后"


def test_B11_pipeline_has_info_check_stage(src):
    """info_check 必须在 info_disclose_check 之后(disclose 先入库,check 才不会误判)"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert 'pipeline.append(("info_check"' in block
    disc_pos = block.find('pipeline.append(("info_disclose_check"')
    check_pos = block.find('pipeline.append(("info_check"')
    assert check_pos > disc_pos, "info_check 必须在 info_disclose_check 之后"


def test_B12_pipeline_handler_info_check(src):
    assert 'step[0] == "info_check"' in src


def test_B13_pipeline_handler_info_disclose_check(src):
    assert 'step[0] == "info_disclose_check"' in src


def test_B14_info_isolation_tab_in_sub_tabs_init(src):
    """_build_info_isolation_tab 必须在 _build_plot_progress_tab 之后被调用"""
    m = re.search(
        r"self\._build_plot_progress_tab\(\)\s*[^\n]*\n\s*self\._build_info_isolation_tab\(\)",
        src)
    assert m


def test_B15_no_auto_fix_attempt_in_info_check(src):
    """info_check 是【侦测】不是【修复】 — 不应有 setItem(rid, N, '...') 等自动修复逻辑"""
    m = re.search(
        r"def _on_info_check_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 不应试图改 tbl_infos / tbl_known_by(违反"只警告"原则)
    assert "tbl_infos.setItem" not in block
    assert "tbl_known_by.setItem" not in block
    assert "insertRow" not in block, \
        "info_check 是【侦测】 — 命中后不应改库,只能标红警告"


# ─────────────────────────────────────
# C. UI 层
# ─────────────────────────────────────

def test_C1_lbl_last_info_check_exists(src):
    assert "lbl_last_info_check" in src
    assert "知识穿帮" in src


def test_C2_two_subtables_constructed(src):
    """必须构造 2 个 QTableWidget:tbl_infos / tbl_known_by"""
    m_i = re.search(r"self\.tbl_infos = QTableWidget\(0, (\d+)\)", src)
    assert m_i, "tbl_infos 初始化未找到"
    assert m_i.group(1) == "4", f"tbl_infos 应 4 列,实际 {m_i.group(1)}"

    m_k = re.search(r"self\.tbl_known_by = QTableWidget\(0, (\d+)\)", src)
    assert m_k, "tbl_known_by 初始化未找到"
    assert m_k.group(1) == "3", f"tbl_known_by 应 3 列,实际 {m_k.group(1)}"


def test_C3_infos_table_headers(src):
    for header in ("信息 id", "信息内容", "来源章", "来源类型"):
        assert header in src


def test_C4_known_by_table_headers(src):
    """tbl_known_by 4 列含义:信息 id(引用) / 知情人 / 知情来源"""
    assert "知情人" in src
    assert "知情来源" in src


def test_C5_info_isolation_tab_title(src):
    """sub_tab 标题必须是 🔒 信息隔离"""
    assert 'addTab(w, "🔒 信息隔离")' in src


def test_C6_inner_tab_titles(src):
    """嵌套 tab 标题:📋 信息条目 / 👁 知情人表"""
    for title in ("📋 信息条目", "👁 知情人表"):
        assert title in src


def test_C7_lbl_last_info_check_multi_state(src):
    """lbl_last_info_check 必须多处 setText(初始/无穿帮/有穿帮/失败)"""
    matches = re.findall(r"lbl_last_info_check\.setText\(", src)
    assert len(matches) >= 3


# ─────────────────────────────────────
# D. 行为层
# ─────────────────────────────────────

def test_D1_build_inject_block_has_known_boundary_section(src):
    """build_inject_block 必须有【角色已知信息边界】段"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "已知信息边界" in block
    assert "tbl_infos" in block and "tbl_known_by" in block


def test_D2_inject_requires_mentioned_names(src):
    """v1.79 注入必须以 mentioned_names 为前提(空则整段不出)"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 关键信息段必须用 mentioned_names 做条件
    info_idx = block.find("tbl_infos")
    assert info_idx >= 0
    nearby = block[info_idx:info_idx + 3000]
    assert "mentioned_names" in nearby


def test_D3_inject_has_secrets_warning(src):
    """注入块必须列出『本章出场角色不应触及的信息』(防止伏笔过早泄露)"""
    m = re.search(
        r"def build_inject_block\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "不应" in block and "触及" in block


def test_D4_serialize_includes_v179_fields(src):
    m = re.search(r"def serialize\(self\):.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert '"infos"' in block
    assert '"known_by"' in block
    assert "tbl_to_list(self.tbl_infos, 4)" in block
    assert "tbl_to_list(self.tbl_known_by, 3)" in block


def test_D5_load_dict_key_maps_includes_v179(src):
    """load 的 DICT_KEY_MAPS 必须含 infos / known_by"""
    m = re.search(r"DICT_KEY_MAPS = \{[^}]+\}", src, re.DOTALL)
    block = m.group(0)
    assert '"infos":' in block
    assert '"known_by":' in block
    # 字段
    assert '"source_ch"' in block and '"source_type"' in block
    assert '"info_id"' in block and '"character"' in block


def test_D6_merge_dicts_has_info_id_remap(src):
    """merge_dicts 必须有 id_remap(AI 给占位符 → 实际 id)"""
    m = re.search(r"def merge_dicts\(self.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "id_remap" in block


def test_D7_merge_dicts_auto_renumber_info_id(src):
    """merge_dicts 必须能自动续号 INFO-001/INFO-002..."""
    m = re.search(r"def merge_dicts\(self.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "INFO-" in block
    assert "_next_info_id" in block or "n += 1" in block


def test_D8_merge_filters_dangling_references(src):
    """merge_dicts 必须过滤 known_by 里悬挂的 info_id 引用"""
    m = re.search(r"def merge_dicts\(self.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    # info_id 不在 tbl_infos 里 → continue
    assert "valid_ids" in block
    assert "info_id not in valid_ids" in block or "info_id not in valid" in block


def test_D9_merge_into_charlib_has_v179_counters(src):
    """_merge_into_charlib 必须有 info/kb 计数 + 两段合并"""
    m = re.search(r"def _merge_into_charlib\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "tbl_infos" in block
    assert "tbl_known_by" in block
    assert 'added["info"]' in block or 'added.get("info"' in block
    assert 'added["kb"]' in block or 'added.get("kb"' in block


def test_D10_merge_into_charlib_also_accepts_info_disclosures(src):
    """_merge_into_charlib 必须同时接受 known_by 和 info_disclosures 字段"""
    m = re.search(r"def _merge_into_charlib\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "info_disclosures" in block
    assert "known_by" in block


def test_D11_on_info_disclose_check_filters_dangling(src):
    """_on_info_disclose_check_response 必须过滤悬挂引用"""
    m = re.search(r"def _on_info_disclose_check_response\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "valid_ids" in block
    assert "info_id not in valid_ids" in block


def test_D12_on_info_disclose_check_dedupes(src):
    """_on_info_disclose_check_response 必须去重(同 info|character 不要重复入库)"""
    m = re.search(r"def _on_info_disclose_check_response\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "ex_kbs" in block


def test_D13_all_empty_includes_v179_fields(src):
    """all_empty 必须包含 infos / info_disclosures"""
    m = re.search(r'all_empty = not any\((.+?)\n        \)', src, re.DOTALL)
    block = m.group(1)
    assert "infos" in block
    assert "info_disclosures" in block


def test_D14_completion_log_shows_v179_counts(src):
    """完成日志必须有信息+/知情+"""
    assert "信息+" in src
    assert "知情+" in src


def test_D15_diagnostic_print_info(src):
    """诊断日志:4 个新方法都必须 print"""
    for method in ("_run_info_check", "_on_info_check_response",
                   "_run_info_disclose_check", "_on_info_disclose_check_response"):
        m = re.search(rf"def {method}\(.*?(?=\n    def )", src, re.DOTALL)
        assert m
        block = m.group(0)
        assert "v1.79" in block, f"{method} 缺诊断日志"


def test_D16_violation_label_uses_red(src):
    """命中穿帮时 label 必须红底白字(高 alert)"""
    m = re.search(r"def _on_info_check_response\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    # background red
    assert "#c00" in block or "#fff5f5" in block
    # 文案
    assert "穿帮" in block


# ─────────────────────────────────────
# D — 运行时端到端
# ─────────────────────────────────────

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")


@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    a = QApplication.instance() or QApplication(sys.argv)
    yield a


@pytest.fixture
def charlib(app):
    sys.path.insert(0, os.path.dirname(__file__) or ".")
    from novel_ai import CharacterLibrary
    return CharacterLibrary()


def test_D17_merge_dicts_infos_auto_id_renumber(charlib):
    """AI 用 INFO-XXX 占位符,合并后应自动续号"""
    added = charlib.merge_dicts({
        "infos": [
            {"id": "INFO-XXX", "content": "信息一", "source_ch": "1", "source_type": "设定"},
            {"id": "INFO-YYY", "content": "信息二", "source_ch": "2", "source_type": "事件揭露"},
        ],
    })
    assert added["info"] == 2
    assert charlib.tbl_infos.item(0, 0).text() == "INFO-001"
    assert charlib.tbl_infos.item(1, 0).text() == "INFO-002"


def test_D18_merge_dicts_infos_content_dedupe(charlib):
    """相同 content 第二次合并不应新建"""
    charlib.merge_dicts({"infos": [
        {"id": "INFO-X", "content": "唯一信息", "source_ch": "1", "source_type": "设定"}]})
    a2 = charlib.merge_dicts({"infos": [
        {"id": "INFO-Y", "content": "唯一信息", "source_ch": "1", "source_type": "设定"}]})
    assert a2["info"] == 0
    assert charlib.tbl_infos.rowCount() == 1


def test_D19_merge_dicts_known_by_filters_dangling(charlib):
    """known_by 引用不存在的 info_id 应被过滤"""
    charlib.merge_dicts({
        "infos": [{"id": "INFO-A", "content": "x", "source_ch": "1", "source_type": "设定"}],
        "known_by": [
            {"info_id": "INFO-A", "character": "林远", "via": "出生即知"},
            {"info_id": "NONEXISTENT", "character": "王屠户", "via": "瞎扯"},
        ],
    })
    # 应只有 1 条进表 — 第二条悬挂被过滤
    assert charlib.tbl_known_by.rowCount() == 1
    assert charlib.tbl_known_by.item(0, 1).text() == "林远"


def test_D20_merge_dicts_known_by_dedupes(charlib):
    """known_by 同 info|character 重复不入库"""
    charlib.merge_dicts({
        "infos": [{"id": "INFO-A", "content": "x", "source_ch": "1", "source_type": "设定"}],
        "known_by": [{"info_id": "INFO-A", "character": "林远", "via": "v1"}],
    })
    a2 = charlib.merge_dicts({
        "known_by": [{"info_id": "INFO-A", "character": "林远", "via": "v2(不该覆盖)"}],
    })
    assert a2["kb"] == 0
    assert charlib.tbl_known_by.rowCount() == 1


def test_D21_merge_dicts_known_by_id_remap(charlib):
    """AI 给的占位符 id 在 info_disclosures 引用时,合并应通过 id_remap 找到真实 id"""
    # AI 一次性返回 infos + info_disclosures,disclosures 引用占位符
    added = charlib.merge_dicts({
        "infos": [{"id": "INFO-XXX", "content": "信息甲", "source_ch": "1", "source_type": "设定"}],
        "info_disclosures": [{"info_id": "INFO-XXX", "to": "林远", "via": "出生即知"}],
    })
    assert added["info"] == 1
    assert added["kb"] == 1
    # known_by 里 info_id 应该是续号后的 INFO-001(不是 INFO-XXX)
    assert charlib.tbl_known_by.item(0, 0).text() == "INFO-001"


def test_D22_serialize_load_roundtrip(charlib, app):
    charlib.merge_dicts({
        "infos": [
            {"id": "INFO-X", "content": "a", "source_ch": "1", "source_type": "设定"},
            {"id": "INFO-Y", "content": "b", "source_ch": "2", "source_type": "事件揭露"},
        ],
        "known_by": [
            {"info_id": "INFO-X", "character": "林远", "via": "出生即知"},
            {"info_id": "INFO-Y", "character": "林悦", "via": "第2章亲眼见"},
        ],
    })
    # 占位符 INFO-X 应被映射为 INFO-001
    out = charlib.serialize()
    from novel_ai import CharacterLibrary
    cl2 = CharacterLibrary()
    cl2.load(out)
    assert cl2.tbl_infos.rowCount() == 2
    assert cl2.tbl_known_by.rowCount() == 2


def test_D23_inject_block_includes_known_boundary(charlib):
    charlib.merge_dicts({
        "infos": [
            {"id": "INFO-A", "content": "林远是叶家次子", "source_ch": "1", "source_type": "设定"},
            {"id": "INFO-B", "content": "金手指是咒血术", "source_ch": "1", "source_type": "设定"},
            {"id": "INFO-C", "content": "王屠户密通敌人", "source_ch": "5", "source_type": "事件揭露"},
        ],
        "known_by": [
            {"info_id": "INFO-A", "character": "林远", "via": "出生即知"},
            {"info_id": "INFO-B", "character": "林远", "via": "出生即知"},
            {"info_id": "INFO-B", "character": "林悦", "via": "第3章告知"},
        ],
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=10, mentioned_names={"林远", "林悦"})
    assert "已知信息边界" in block
    # 林远应该知道 INFO-001 和 INFO-002
    assert "林远 已知" in block
    # 林悦应该只知道 INFO-002
    assert "林悦 已知" in block
    # INFO-003 没在 known_by 里且不在 mentioned,应作为 secrets 警示
    assert "INFO-003" in block


def test_D24_inject_block_filters_non_mentioned_characters(charlib):
    """v1.79 注入只对 mentioned_names 中的角色注入"""
    charlib.merge_dicts({
        "infos": [{"id": "INFO-A", "content": "x", "source_ch": "1", "source_type": "设定"}],
        "known_by": [
            {"info_id": "INFO-A", "character": "林远", "via": "出生即知"},
            {"info_id": "INFO-A", "character": "王屠户", "via": "第3章告知"},
        ],
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=10, mentioned_names={"林远"})
    # 林远应该出现
    assert "林远 已知" in block
    # 王屠户不在 mentioned_names,他的 known 行不该出现
    assert "王屠户 已知" not in block


def test_D25_inject_block_no_emit_without_mentioned_names(charlib):
    """没传 mentioned_names → 信息隔离段整个不出(只能精确定向才能用)"""
    charlib.merge_dicts({
        "infos": [{"id": "INFO-A", "content": "x", "source_ch": "1", "source_type": "设定"}],
        "known_by": [{"info_id": "INFO-A", "character": "林远", "via": "出生即知"}],
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=10)  # 没传 mentioned_names
    assert "已知信息边界" not in block


# ─────────────────────────────────────
# X. 守(防御性)
# ─────────────────────────────────────

def test_X1_on_info_check_guards_non_list(src):
    m = re.search(r"def _on_info_check_response\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X2_on_info_check_guards_non_dict_item(src):
    m = re.search(r"def _on_info_check_response\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(it, dict)" in block


def test_X3_on_info_disclose_check_guards_non_list(src):
    m = re.search(r"def _on_info_disclose_check_response\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X4_on_info_disclose_check_guards_non_dict_item(src):
    m = re.search(r"def _on_info_disclose_check_response\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(it, dict)" in block


def test_X5_run_info_check_guards_no_tbl(src):
    """_run_info_check 必须守 hasattr(tbl_infos / tbl_known_by)"""
    m = re.search(r"def _run_info_check\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert 'hasattr(self.tab_charlib, "tbl_infos")' in block
    assert 'hasattr(self.tab_charlib, "tbl_known_by")' in block


def test_X6_run_info_check_guards_empty_infos(src):
    """_run_info_check 库里没 info 时必须跳过(不徒劳调用 AI)"""
    m = re.search(r"def _run_info_check\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "rowCount() == 0" in block
    assert "_run_next_post_chapter_step" in block


def test_X7_version_bumped_to_1_79_or_higher(src):
    """APP_VERSION ≥ v1.79"""
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)"', src)
    assert m
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 79), \
        f"v1.79 信息隔离不应被低版本退回,当前 v{major}.{minor}"


def test_X8_inject_block_empty_when_inject_off(charlib):
    """chk_inject 关闭时不出任何 v1.79 段"""
    charlib.merge_dicts({
        "infos": [{"id": "INFO-A", "content": "x", "source_ch": "1", "source_type": "设定"}],
        "known_by": [{"info_id": "INFO-A", "character": "林远", "via": "出生即知"}],
    })
    charlib.chk_inject.setChecked(False)
    block = charlib.build_inject_block(current_chapter=10, mentioned_names={"林远"})
    assert block == ""
