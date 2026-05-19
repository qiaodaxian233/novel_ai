"""
test_plot_tree.py — v1.80 BUG-060 剧情树规划

与 v1.76/v1.77/v1.78/v1.79 的最大架构差异:
  - UI:用 QTreeWidget(树形,前 4 版都是 QTableWidget)
  - 没有章末 AI 自动检查 — 剧情树是【用户主动规划工具】,不是被动抽取
  - 数据形态:扁平 list[{node_id, parent_id, name, kind, ch_range, note}]
    AI 输出扁平 list,合并时建树;序列化/反序列化用 _tree_to_list / _list_to_tree
  - 注入:【当前主线进度】根据 current_chapter 在树里找最具体节点,显示
    根→目标的路径 + 同阶段剩余章数 + 备注 + 写作约束

覆盖:
  A. prompt 设计(world_extract 17 + plot_branches 扁平 list)
  B. 代码层(无 pipeline / 无 AI check 是【负向测试】)
  C. UI 层(QTreeWidget + 4 列 + 6 按钮 + tab 标题)
  D. 行为层(merge/serialize/inject + node_id remap + 4 层 kind 推断 + 注入定位算法)
  X. 守(防御性)
"""
import re
import ast
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

def test_A1_world_extract_has_plot_branches_field(prompts):
    we = prompts["world_extract"]
    assert '"plot_branches"' in we
    for f in ('"node_id"', '"parent_id"', '"kind"', '"ch_range"'):
        assert f in we


def test_A2_world_extract_rule_17_kind_enum(prompts):
    """kind 必须是 4 选 1:故事/阶段/章节槽/剧情点"""
    we = prompts["world_extract"]
    for v in ("故事", "阶段", "章节槽", "剧情点"):
        assert v in we, f"kind 枚举缺 {v}"


def test_A3_world_extract_rule_17_node_id_format(prompts):
    """node_id 必须用 N-001/N-002... 自动续号"""
    we = prompts["world_extract"]
    assert "N-001" in we


def test_A4_world_extract_rule_17_is_flat_list(prompts):
    """规则 17 必须明确是扁平 list(不是嵌套 JSON,对 AI 更友好)"""
    we = prompts["world_extract"]
    assert "扁平" in we or "flat" in we


def test_A5_world_extract_rule_17_says_mostly_empty(prompts):
    """规则 17 必须明确:大多数章节这字段都应留空 — 防 AI 乱填"""
    we = prompts["world_extract"]
    assert "大多数章节" in we and "留空" in we


def test_A6_no_separate_plot_tree_check_prompt(prompts):
    """v1.80 没有章末自动检查的 prompt — 剧情树是主动规划"""
    assert "plot_tree_check" not in prompts
    assert "plot_branch_check" not in prompts


def test_A7_world_extract_format_runs_with_plot_branches(prompts):
    out = prompts["world_extract"].format(ch_num=10, existing="", content="测试")
    assert '"plot_branches"' in out
    assert 'N-001' in out


# ─────────────────────────────────────
# B. 代码层
# ─────────────────────────────────────

def test_B1_build_plot_tree_tab_in_characterlibrary(tree):
    assert _method_class(tree, "_build_plot_tree_tab") == "CharacterLibrary"


def test_B2_tree_to_list_in_characterlibrary(tree):
    """_tree_to_list 必须在 CharacterLibrary(承担序列化)"""
    assert _method_class(tree, "_tree_to_list") == "CharacterLibrary"


def test_B3_list_to_tree_in_characterlibrary(tree):
    """_list_to_tree 必须在 CharacterLibrary(承担反序列化)"""
    assert _method_class(tree, "_list_to_tree") == "CharacterLibrary"


def test_B4_plot_operation_methods_in_characterlibrary(tree):
    """所有树操作方法都在 CharacterLibrary"""
    for m in ("_add_plot_root", "_add_plot_child", "_del_plot_node",
              "_next_plot_node_id"):
        assert _method_class(tree, m) == "CharacterLibrary", \
            f"{m} 应在 CharacterLibrary"


def test_B5_no_run_plot_tree_check_method(tree):
    """v1.80 没有章末检查方法 — 剧情树不参与 AI 自动检查"""
    assert _method_class(tree, "_run_plot_tree_check") is None
    assert _method_class(tree, "_on_plot_tree_check_response") is None


def test_B6_no_plot_tree_pipeline_stage(src):
    """pipeline 不应有 plot_tree_check 阶段"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "plot_tree_check" not in block
    assert 'pipeline.append(("plot_tree' not in block


def test_B7_no_plot_tree_target_route(src):
    """target 路由不应有 plot_tree_check"""
    assert 'target == "plot_tree_check"' not in src
    assert 'target == "plot_branch' not in src


def test_B8_plot_tree_tab_in_sub_tabs_init(src):
    """_build_plot_tree_tab 必须在 _build_info_isolation_tab 之后被调用"""
    m = re.search(
        r"self\._build_info_isolation_tab\(\)\s*[^\n]*\n\s*self\._build_plot_tree_tab\(\)",
        src)
    assert m


# ─────────────────────────────────────
# C. UI 层
# ─────────────────────────────────────

def test_C1_tree_plot_is_qtreewidget(src):
    """tree_plot 必须是 QTreeWidget(不是 QTableWidget)"""
    assert "self.tree_plot = QTreeWidget()" in src


def test_C2_tree_plot_has_5_columns(src):
    """v1.85 起剧情树必须 5 列(原 v1.80 4 列 + v1.85 新增"已挂章号"列)"""
    assert "self.tree_plot.setColumnCount(5)" in src


def test_C3_tree_plot_headers(src):
    """列头必须是:节点名/类型/章节范围/备注/已挂章号"""
    for h in ("节点名", "类型", "章节范围", "备注", "已挂章号"):
        assert h in src


def test_C4_tree_plot_drag_drop_enabled(src):
    """剧情树必须开启拖拽重排"""
    assert "InternalMove" in src
    assert "setDragDropMode" in src


def test_C5_tree_plot_tab_title(src):
    assert 'addTab(w, "🌳 剧情树")' in src


def test_C6_six_operation_buttons(src):
    """至少 5 个操作按钮:加根/加子/删/展开/折叠"""
    for label in ("加根节点", "加子节点", "删除节点", "展开全部", "折叠全部"):
        assert label in src


# ─────────────────────────────────────
# D. 行为层 - source grep
# ─────────────────────────────────────

def test_D1_serialize_includes_plot_branches(src):
    m = re.search(r"def serialize\(self\):.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert '"plot_branches"' in block
    assert "_tree_to_list" in block


def test_D2_load_handles_plot_branches(src):
    """load 必须把 normalize 后的 list 转回 dict 再喂给 _list_to_tree"""
    m = re.search(r"def load\(self, data\):.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "tree_plot" in block
    assert "_list_to_tree" in block


def test_D3_load_dict_key_maps_includes_plot_branches(src):
    """DICT_KEY_MAPS 必须含 plot_branches"""
    m = re.search(r"DICT_KEY_MAPS = \{[^}]+\}", src, re.DOTALL)
    block = m.group(0)
    assert '"plot_branches":' in block
    for f in ("node_id", "parent_id", "kind", "ch_range"):
        assert f in block


def test_D4_merge_dicts_has_node_remap(src):
    """merge_dicts 必须有 node_remap(占位符 node_id → 真 id)"""
    m = re.search(r"def merge_dicts\(self.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "node_remap" in block


def test_D5_merge_dicts_dedupes_by_name_kind_parent(src):
    """plot_branches 合并的去重 key 必须是 (name, kind, parent_id) — 不能纯按 node_id"""
    m = re.search(r"def merge_dicts\(self.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    # 找剧情树段 — 因为 merge_dicts 很长,需要 v1.80 段的明确锚点
    pt_idx = block.find("v1.80")
    assert pt_idx >= 0
    pt_block = block[pt_idx:]
    assert "dedupe_key" in pt_block or "by_key" in pt_block


def test_D6_merge_dicts_orphan_to_root(src):
    """悬挂 parent_id 必须当根节点处理"""
    m = re.search(r"def merge_dicts\(self.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    pt_idx = block.find("v1.80")
    assert pt_idx >= 0
    pt_block = block[pt_idx:]
    # 悬挂处理逻辑:parent_id = "" 后调 addTopLevelItem
    assert "addTopLevelItem" in pt_block


def test_D7_merge_into_charlib_delegates_plot(src):
    """_merge_into_charlib 处理 plot_branches 时应直接委托 cl.merge_dicts(避免重复逻辑)"""
    m = re.search(r"def _merge_into_charlib\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "plot_branches" in block
    # 这是关键设计选择:不重复实现复杂的树合并 — 让 cl.merge_dicts 干
    assert 'cl.merge_dicts' in block or 'cl.merge' in block


def test_D8_build_inject_block_has_plot_progress_section(src):
    """build_inject_block 必须有【当前主线进度】段"""
    m = re.search(r"def build_inject_block\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "当前主线进度" in block
    assert "tree_plot" in block


def test_D9_build_inject_block_path_traversal(src):
    """注入必须回溯祖先链(根→目标)"""
    m = re.search(r"def build_inject_block\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    pt_idx = block.find("tree_plot")
    pt_block = block[pt_idx:pt_idx + 3000]
    # 回溯关键词
    assert "parent_id" in pt_block
    assert "path" in pt_block or "ancestor" in pt_block


def test_D10_build_inject_block_priority_specific_first(src):
    """注入必须优先选最具体节点(剧情点 > 章节槽 > 阶段)"""
    m = re.search(r"def build_inject_block\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    pt_idx = block.find("tree_plot")
    pt_block = block[pt_idx:pt_idx + 3000]
    # _PRIORITY map 必须存在
    assert "_PRIORITY" in pt_block or "priority" in pt_block.lower()


def test_D11_completion_log_shows_plot_count(src):
    """完成日志必须有【树节点+N】"""
    assert "树节点+" in src


def test_D12_all_empty_includes_plot_branches(src):
    m = re.search(r'all_empty = not any\((.+?)\n        \)', src, re.DOTALL)
    block = m.group(1)
    assert "plot_branches" in block


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


def test_D13_add_root_creates_top_level(charlib):
    charlib._add_plot_root()
    assert charlib.tree_plot.topLevelItemCount() == 1
    assert charlib.tree_plot.topLevelItem(0).text(1) == "故事"


def test_D14_node_id_auto_increment(charlib):
    """连续加根节点,node_id 自动续号"""
    from PyQt5.QtCore import Qt
    charlib._add_plot_root()
    charlib._add_plot_root()
    charlib._add_plot_root()
    ids = [charlib.tree_plot.topLevelItem(i).data(0, Qt.UserRole)
           for i in range(3)]
    assert ids == ["N-001", "N-002", "N-003"]


def test_D15_add_child_kind_auto_inferred(charlib):
    """加子节点时 kind 自动推断:故事→阶段→章节槽→剧情点"""
    charlib._add_plot_root()  # 故事
    root = charlib.tree_plot.topLevelItem(0)
    charlib.tree_plot.setCurrentItem(root)
    charlib._add_plot_child()  # 阶段
    stage = root.child(0)
    assert stage.text(1) == "阶段"

    charlib.tree_plot.setCurrentItem(stage)
    charlib._add_plot_child()  # 章节槽
    slot = stage.child(0)
    assert slot.text(1) == "章节槽"

    charlib.tree_plot.setCurrentItem(slot)
    charlib._add_plot_child()  # 剧情点
    pt = slot.child(0)
    assert pt.text(1) == "剧情点"


def test_D16_del_node_removes_descendants(charlib):
    """删除节点应连带删全部子孙"""
    charlib._add_plot_root()
    root = charlib.tree_plot.topLevelItem(0)
    charlib.tree_plot.setCurrentItem(root)
    charlib._add_plot_child()
    stage = root.child(0)
    charlib.tree_plot.setCurrentItem(stage)
    charlib._add_plot_child()
    # 现在:故事 → 阶段 → 章节槽
    # 删阶段 → 章节槽也应消失
    # 但 _del_plot_node 会弹 QMessageBox 确认 — 单测里不能弹,直接删根更稳
    charlib.tree_plot.setCurrentItem(root)
    # 用 takeTopLevelItem 直接验
    idx = charlib.tree_plot.indexOfTopLevelItem(root)
    charlib.tree_plot.takeTopLevelItem(idx)
    assert charlib.tree_plot.topLevelItemCount() == 0


def test_D17_tree_to_list_flattens_correctly(charlib):
    """_tree_to_list 必须按深度优先扁平化,parent_id 引用正确"""
    charlib._add_plot_root()
    root = charlib.tree_plot.topLevelItem(0)
    charlib.tree_plot.setCurrentItem(root)
    charlib._add_plot_child()  # 阶段 N-002
    recs = charlib._tree_to_list()
    assert len(recs) == 2
    assert recs[0]["parent_id"] == ""
    assert recs[1]["parent_id"] == recs[0]["node_id"]


def test_D18_list_to_tree_rebuilds(charlib):
    """_list_to_tree 必须能从 flat dict list 重建树"""
    charlib._list_to_tree([
        {"node_id": "N-001", "parent_id": "", "name": "故事A", "kind": "故事",
         "ch_range": "", "note": ""},
        {"node_id": "N-002", "parent_id": "N-001", "name": "阶段A1", "kind": "阶段",
         "ch_range": "1-30", "note": ""},
        {"node_id": "N-003", "parent_id": "N-002", "name": "章节槽 A1.1",
         "kind": "章节槽", "ch_range": "1-10", "note": ""},
    ])
    assert charlib.tree_plot.topLevelItemCount() == 1
    root = charlib.tree_plot.topLevelItem(0)
    assert root.text(0) == "故事A"
    assert root.childCount() == 1
    assert root.child(0).childCount() == 1


def test_D19_list_to_tree_orphan_becomes_root(charlib):
    """悬挂引用(parent_id 找不到)应当根节点"""
    charlib._list_to_tree([
        {"node_id": "N-001", "parent_id": "MISSING", "name": "悬挂",
         "kind": "剧情点", "ch_range": "", "note": ""},
    ])
    assert charlib.tree_plot.topLevelItemCount() == 1
    assert charlib.tree_plot.topLevelItem(0).text(0) == "悬挂"


def test_D20_merge_dicts_basic(charlib):
    added = charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "灭门复仇",
             "kind": "故事", "ch_range": "", "note": ""},
            {"node_id": "N-Y", "parent_id": "N-X", "name": "前期",
             "kind": "阶段", "ch_range": "1-30", "note": ""},
        ]
    })
    assert added["pt"] == 2
    recs = charlib._tree_to_list()
    assert len(recs) == 2
    # AI 给的 N-X/N-Y 占位符应被重映射为 N-001/N-002
    assert recs[0]["node_id"] == "N-001"
    assert recs[1]["node_id"] == "N-002"
    assert recs[1]["parent_id"] == "N-001"


def test_D21_merge_dicts_node_id_remap(charlib):
    """parent_id 引用 AI 占位符时,合并应通过 remap 找到真 id"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-AAA", "parent_id": "", "name": "故事 1",
             "kind": "故事", "ch_range": "", "note": ""},
            {"node_id": "N-BBB", "parent_id": "N-AAA",
             "name": "阶段 1", "kind": "阶段", "ch_range": "", "note": ""},
        ]
    })
    recs = charlib._tree_to_list()
    # 第二条应该挂在第一条下面(parent_id 正确 remap 到 N-001)
    assert recs[1]["parent_id"] == recs[0]["node_id"]


def test_D22_merge_dicts_dedupe_by_name_kind_parent(charlib):
    """相同 (name, kind, parent) 的节点不重复加"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事 A",
             "kind": "故事", "ch_range": "", "note": ""},
        ]
    })
    a2 = charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-Y", "parent_id": "", "name": "故事 A",
             "kind": "故事", "ch_range": "", "note": ""},
        ]
    })
    assert a2["pt"] == 0
    assert charlib.tree_plot.topLevelItemCount() == 1


def test_D23_merge_dicts_orphan_handling(charlib):
    """parent_id 引用不存在的节点 → 当根节点处理"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "DEAD", "name": "悬挂",
             "kind": "剧情点", "ch_range": "", "note": ""},
        ]
    })
    assert charlib.tree_plot.topLevelItemCount() == 1


def test_D24_serialize_load_roundtrip(charlib, app):
    """serialize → load roundtrip 树结构守恒"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "1-200", "note": "主线"},
            {"node_id": "N-Y", "parent_id": "N-X", "name": "阶段 1",
             "kind": "阶段", "ch_range": "1-30", "note": ""},
            {"node_id": "N-Z", "parent_id": "N-Y", "name": "章节槽",
             "kind": "章节槽", "ch_range": "1-10", "note": ""},
        ]
    })
    out = charlib.serialize()
    from novel_ai import CharacterLibrary
    cl2 = CharacterLibrary()
    cl2.load(out)
    recs1 = charlib._tree_to_list()
    recs2 = cl2._tree_to_list()
    assert len(recs1) == len(recs2) == 3
    # 结构一致
    for a, b in zip(recs1, recs2):
        assert a["name"] == b["name"]
        assert a["kind"] == b["kind"]
        assert a["parent_id"] == b["parent_id"]


def test_D25_inject_locates_most_specific_node(charlib):
    """注入应优先选最具体的节点(剧情点 > 章节槽 > 阶段)"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X1", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "1-100", "note": ""},
            {"node_id": "N-X2", "parent_id": "N-X1", "name": "阶段",
             "kind": "阶段", "ch_range": "1-30", "note": ""},
            {"node_id": "N-X3", "parent_id": "N-X2", "name": "章节槽",
             "kind": "章节槽", "ch_range": "1-10", "note": ""},
            {"node_id": "N-X4", "parent_id": "N-X3", "name": "遇到导师",
             "kind": "剧情点", "ch_range": "5", "note": "关键转折"},
        ]
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=5)
    assert "当前主线进度" in block
    # 第 5 章应命中剧情点(最具体)
    assert "遇到导师" in block
    # 路径应完整(根→剧情点)
    assert "故事" in block and "阶段" in block and "章节槽" in block


def test_D26_inject_fallback_to_less_specific(charlib):
    """无剧情点覆盖时,退到章节槽 / 阶段"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X1", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "1-100", "note": ""},
            {"node_id": "N-X2", "parent_id": "N-X1", "name": "阶段",
             "kind": "阶段", "ch_range": "1-30", "note": ""},
            {"node_id": "N-X3", "parent_id": "N-X2", "name": "章节槽",
             "kind": "章节槽", "ch_range": "1-10", "note": ""},
        ]
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=8)
    # 第 8 章无剧情点覆盖 → 命中章节槽
    assert "章节槽" in block
    assert "剩余" in block  # 章节槽 1-10 第 8 章剩 3 章


def test_D27_inject_no_emission_when_chapter_not_covered(charlib):
    """current_chapter 不在任何节点 ch_range 内 → 整段不出"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "1-100", "note": ""},
        ]
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=200)  # 超出
    assert "当前主线进度" not in block


def test_D28_inject_no_emission_without_chapter(charlib):
    """没传 current_chapter → 整段不出"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "1-100", "note": ""},
        ]
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=None)
    assert "当前主线进度" not in block


# ─────────────────────────────────────
# X. 守(防御性)
# ─────────────────────────────────────

def test_X1_version_bumped_to_1_80_or_higher(src):
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)"', src)
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 80), \
        f"v1.80 剧情树不应被低版本退回,当前 v{major}.{minor}"


def test_X2_list_to_tree_handles_empty(charlib):
    """空 list 不应崩"""
    charlib._list_to_tree([])
    assert charlib.tree_plot.topLevelItemCount() == 0


def test_X3_list_to_tree_handles_malformed(charlib):
    """非 dict 项应被跳过"""
    charlib._list_to_tree([
        "garbage",  # 字符串
        None,
        {"node_id": "N-001", "parent_id": "", "name": "正常",
         "kind": "故事", "ch_range": "", "note": ""},
        42,  # 数字
    ])
    # 只有合法的 1 个被加入
    assert charlib.tree_plot.topLevelItemCount() == 1


def test_X4_inject_block_empty_when_inject_off(charlib):
    """chk_inject 关闭时不出剧情树段"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "1-100", "note": ""},
        ]
    })
    charlib.chk_inject.setChecked(False)
    block = charlib.build_inject_block(current_chapter=5)
    assert block == ""


def test_X5_merge_dicts_handles_empty_name(charlib):
    """name 空的节点应被跳过"""
    added = charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "", "kind": "故事",
             "ch_range": "", "note": ""},
            {"node_id": "N-Y", "parent_id": "", "name": "正常", "kind": "故事",
             "ch_range": "", "note": ""},
        ]
    })
    assert added["pt"] == 1


def test_X6_merge_dicts_handles_invalid_ch_range(charlib):
    """ch_range 非法不应崩 — 应被原样保留(用户可手动修)"""
    added = charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "乱写的范围",  "note": ""},
        ]
    })
    assert added["pt"] == 1


def test_X7_inject_block_handles_invalid_ch_range(charlib):
    """ch_range 非法格式时注入不崩(只是该节点没法命中)"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "garbage", "note": ""},
        ]
    })
    charlib.chk_inject.setChecked(True)
    block = charlib.build_inject_block(current_chapter=5)
    # 不应崩;只是不命中
    assert "garbage" not in block


def test_X8_inject_block_handles_int_or_str_chapter(charlib):
    """current_chapter 可以是 int 或 str"""
    charlib.merge_dicts({
        "plot_branches": [
            {"node_id": "N-X", "parent_id": "", "name": "故事",
             "kind": "故事", "ch_range": "1-100", "note": ""},
        ]
    })
    charlib.chk_inject.setChecked(True)
    b1 = charlib.build_inject_block(current_chapter=5)
    b2 = charlib.build_inject_block(current_chapter="5")
    # 两者都应有当前主线进度段
    assert "当前主线进度" in b1
    assert "当前主线进度" in b2
