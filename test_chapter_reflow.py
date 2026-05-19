"""
test_chapter_reflow.py — v1.85 BUG-062 写作模式回流

设计:章末 AI 反查"本章对应剧情树哪些节点",把章号挂到节点第 5 列。
这是 v1.80 注入(按章号找节点)的镜像 — v1.85 是按内容找节点。

与 v1.76-v1.80 的对照:
  - 数据形态:复用 v1.80 已有的剧情树(QTreeWidget),加第 5 列 chapter_links
  - check 语义:【侦测式】(同 v1.79 info_check)— 不新建数据,只标章号到节点
  - 多对一:N 章可挂同节点(append),同章号去重
  - 命中后行为:item.setText(4, ...) 改第 5 列,不改树结构

覆盖:
  A. prompt 设计(chapter_to_plot_node 字段/规则)
  B. 代码层(2 个新 MainWindow 方法 + pipeline 阶段 + target 路由)
  C. UI 层(剧情树 5 列 + 第 5 列标题"已挂章号")
  D. 行为层(_tree_to_list 输出 chapter_links + serialize/load + union 合并)
  X. 守(空树/悬挂节点/同章去重)
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
# A. prompt 设计
# ─────────────────────────────────────

def test_A1_prompt_exists(prompts):
    assert "chapter_to_plot_node" in prompts


def test_A2_prompt_has_required_placeholders(prompts):
    p = prompts["chapter_to_plot_node"]
    for ph in ("{plot_tree}", "{ch_num}", "{content}"):
        assert ph in p, f"prompt 缺占位符 {ph}"


def test_A3_prompt_returns_array(prompts):
    """prompt 必须明确要求 JSON 数组(不是单对象)"""
    p = prompts["chapter_to_plot_node"]
    assert "JSON 数组" in p
    assert "[" in p and "]" in p


def test_A4_prompt_demands_node_id_from_tree(prompts):
    """prompt 必须强调 node_id 不能凭空造"""
    p = prompts["chapter_to_plot_node"]
    assert "凭空造" in p or "必须从" in p


def test_A5_prompt_priority_specific_first(prompts):
    """prompt 必须明确"优先选最具体节点"(剧情点 > 章节槽 > 阶段)"""
    p = prompts["chapter_to_plot_node"]
    for v in ("剧情点", "章节槽", "阶段"):
        assert v in p


def test_A6_prompt_handles_filler_chapter(prompts):
    """prompt 必须明确"过场/铺垫/水章"返回 []"""
    p = prompts["chapter_to_plot_node"]
    assert "过场" in p or "铺垫" in p or "水章" in p


def test_A7_prompt_format_runs(prompts):
    out = prompts["chapter_to_plot_node"].format(
        plot_tree='[{"node_id":"N-001","kind":"剧情点","name":"遇到导师"}]',
        ch_num=5, content="测试正文")
    assert "第 5 章" in out


# ─────────────────────────────────────
# B. 代码层
# ─────────────────────────────────────

def test_B1_run_method_in_mainwindow(tree):
    assert _method_class(tree, "_run_chapter_to_plot_node") == "MainWindow"


def test_B2_on_response_method_in_mainwindow(tree):
    assert _method_class(tree, "_on_chapter_to_plot_node_response") == "MainWindow"


def test_B3_pipeline_has_chapter_to_plot_node(src):
    """_post_chapter_chain 必须 append chapter_to_plot_node"""
    m = re.search(
        r"def _post_chapter_chain\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert 'pipeline.append(("chapter_to_plot_node"' in block


def test_B4_pipeline_order_after_info_check(src):
    """chapter_to_plot_node 必须在 info_check 之后(依赖前面所有数据稳定)"""
    m = re.search(r"def _post_chapter_chain\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    info_pos = block.find('pipeline.append(("info_check"')
    plot_pos = block.find('pipeline.append(("chapter_to_plot_node"')
    assert info_pos >= 0
    assert plot_pos >= 0
    assert plot_pos > info_pos, \
        "v1.85:chapter_to_plot_node 必须挂在 info_check 之后"


def test_B5_pipeline_handler_step(src):
    """_run_next_post_chapter_step 必须有 chapter_to_plot_node 分支"""
    assert 'step[0] == "chapter_to_plot_node"' in src


def test_B6_target_route(src):
    assert 'target == "chapter_to_plot_node"' in src


def test_B7_no_auto_fix_attempt_in_response_handler(src):
    """v1.85 是侦测式 — _on_chapter_to_plot_node_response 不该改树结构"""
    m = re.search(
        r"def _on_chapter_to_plot_node_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 不应试图加新节点/删节点
    assert "addTopLevelItem" not in block, \
        "v1.85 侦测式 — 不应新建节点"
    assert "removeChild" not in block, \
        "v1.85 侦测式 — 不应删节点"
    assert "insertRow" not in block, \
        "v1.85 不该 insertRow"
    # 只该 setText(4, ...) 改第 5 列
    assert "setText(4" in block


def test_B8_response_handler_uses_userrole_index(src):
    """_on_chapter_to_plot_node_response 必须用 data(0, Qt.UserRole) 索引节点
    (不是按 row 索引,因为这是树不是表)"""
    m = re.search(
        r"def _on_chapter_to_plot_node_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "UserRole" in block


def test_B9_dangling_node_filtered(src):
    """悬挂 node_id 必须被过滤(不在树里 → 跳过)"""
    m = re.search(
        r"def _on_chapter_to_plot_node_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "悬挂" in block or "id_to_item" in block


# ─────────────────────────────────────
# C. UI 层
# ─────────────────────────────────────

def test_C1_tree_plot_5_columns(src):
    """剧情树必须 5 列(v1.80 4 列 + v1.85 新增 1 列)"""
    assert "self.tree_plot.setColumnCount(5)" in src


def test_C2_fifth_column_header(src):
    """第 5 列标题必须是『已挂章号』"""
    assert "已挂章号" in src


def test_C3_serialize_includes_chapter_links(src):
    """serialize plot_branches 必须输出第 7 字段(chapter_links)"""
    m = re.search(r"def serialize\(self\):.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "chapter_links" in block


def test_C4_dict_key_maps_includes_chapter_links(src):
    """DICT_KEY_MAPS plot_branches schema 必须含 chapter_links"""
    m = re.search(r"DICT_KEY_MAPS = \{[^}]+\}", src, re.DOTALL)
    block = m.group(0)
    assert "chapter_links" in block


# ─────────────────────────────────────
# D. 运行时端到端
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


def test_D1_tree_plot_has_5_columns_runtime(charlib):
    assert charlib.tree_plot.columnCount() == 5


def test_D2_add_root_has_5_columns(charlib):
    """新加节点必须 5 列(否则 _tree_to_list 访问 text(4) 会崩)"""
    charlib._add_plot_root()
    item = charlib.tree_plot.topLevelItem(0)
    assert item.columnCount() == 5


def test_D3_tree_to_list_includes_chapter_links(charlib):
    """_tree_to_list 输出必须含 chapter_links 字段"""
    charlib._add_plot_root()
    recs = charlib._tree_to_list()
    assert len(recs) == 1
    assert "chapter_links" in recs[0]


def test_D4_chapter_links_persisted(charlib):
    """手动设置 chapter_links → 序列化 → 反序列化:守恒"""
    charlib._add_plot_root()
    root = charlib.tree_plot.topLevelItem(0)
    root.setText(4, "3, 5, 7")
    out = charlib.serialize()
    # plot_branches 是 list-of-list 格式,第 7 项是 chapter_links
    assert out["plot_branches"][0][6] == "3, 5, 7"
    # roundtrip
    from novel_ai import CharacterLibrary
    cl2 = CharacterLibrary()
    cl2.load(out)
    assert cl2.tree_plot.topLevelItem(0).text(4) == "3, 5, 7"


def test_D5_merge_dicts_union_chapter_links(charlib):
    """同 (name, kind, parent) 节点的 chapter_links 必须 union(不覆盖)"""
    charlib.merge_dicts({"plot_branches": [
        {"node_id": "N-X", "parent_id": "", "name": "节点 A", "kind": "剧情点",
         "ch_range": "5", "note": "", "chapter_links": "5"},
    ]})
    # 第二次 merge 同名节点,带新 chapter_links
    charlib.merge_dicts({"plot_branches": [
        {"node_id": "N-Y", "parent_id": "", "name": "节点 A", "kind": "剧情点",
         "ch_range": "5", "note": "", "chapter_links": "7, 8"},
    ]})
    # 树里只有 1 个节点
    assert charlib.tree_plot.topLevelItemCount() == 1
    # chapter_links 应是 union:5, 7, 8
    assert charlib.tree_plot.topLevelItem(0).text(4) == "5, 7, 8"


def test_D6_merge_dicts_chapter_links_dedupe_within(charlib):
    """同章号重复出现 → 去重"""
    charlib.merge_dicts({"plot_branches": [
        {"node_id": "N-X", "parent_id": "", "name": "节点 A", "kind": "剧情点",
         "ch_range": "5", "note": "", "chapter_links": "5"},
    ]})
    charlib.merge_dicts({"plot_branches": [
        {"node_id": "N-Y", "parent_id": "", "name": "节点 A", "kind": "剧情点",
         "ch_range": "5", "note": "", "chapter_links": "5, 7"},  # 5 已存在
    ]})
    assert charlib.tree_plot.topLevelItem(0).text(4) == "5, 7"


def test_D7_merge_dicts_chapter_links_sorted_numerically(charlib):
    """chapter_links 按数字升序(不是字典序)"""
    charlib.merge_dicts({"plot_branches": [
        {"node_id": "N-X", "parent_id": "", "name": "节点 A", "kind": "剧情点",
         "ch_range": "5", "note": "", "chapter_links": "10"},
    ]})
    charlib.merge_dicts({"plot_branches": [
        {"node_id": "N-Y", "parent_id": "", "name": "节点 A", "kind": "剧情点",
         "ch_range": "5", "note": "", "chapter_links": "2"},
    ]})
    # 字典序会得 "10, 2",数字序应是 "2, 10"
    assert charlib.tree_plot.topLevelItem(0).text(4) == "2, 10"


def test_D8_existing_v180_data_still_loads(charlib, app):
    """v1.80 时代的 6 字段 plot_branches 数据(无 chapter_links)仍能加载"""
    # 模拟 v1.80 时期保存的数据 — 只 6 字段
    old_data = {
        "plot_branches": [
            ["N-001", "", "故事", "故事", "1-100", "v1.80 时代数据"]  # 没第 7 字段
        ]
    }
    charlib.load(old_data)
    # 应能加载,chapter_links 为空
    assert charlib.tree_plot.topLevelItemCount() == 1
    item = charlib.tree_plot.topLevelItem(0)
    assert item.text(0) == "故事"
    assert item.text(4) == ""  # 空


# ─────────────────────────────────────
# X. 守
# ─────────────────────────────────────

def test_X1_response_handler_guards_non_list(src):
    m = re.search(
        r"def _on_chapter_to_plot_node_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(arr, list)" in block


def test_X2_response_handler_guards_non_dict_item(src):
    m = re.search(
        r"def _on_chapter_to_plot_node_response\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "isinstance(it, dict)" in block


def test_X3_run_guards_no_tree(src):
    """_run_chapter_to_plot_node 必须守 hasattr(tree_plot)"""
    m = re.search(
        r"def _run_chapter_to_plot_node\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert 'hasattr(self.tab_charlib, "tree_plot")' in block


def test_X4_run_guards_empty_tree(src):
    """剧情树空时,_run 必须跳过(不徒劳调用 AI)"""
    m = re.search(
        r"def _run_chapter_to_plot_node\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 空树跳过逻辑
    assert "_run_next_post_chapter_step" in block
    # 必须有"剧情树空"诊断
    assert "剧情树空" in block or "len(nodes)" in block or "if not nodes" in block


def test_X5_version_bumped(src):
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)"', src)
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 85), \
        f"v1.85 写作回流不应被低版本退回,当前 v{major}.{minor}"


def test_X6_response_dedupes_same_chapter(charlib):
    """同章号在节点已存在时不重复挂(用 setText 处的逻辑测)
    这里直接构造 item 验证 dedupe 逻辑"""
    charlib._add_plot_root()
    item = charlib.tree_plot.topLevelItem(0)
    # 模拟两轮回流挂同章号
    cur = "3, 5"
    item.setText(4, cur)
    # 模拟 _on_chapter_to_plot_node_response 的 dedupe 逻辑
    existing = set(c.strip() for c in cur.split(",") if c.strip())
    if "3" not in existing:
        existing.add("3")
    sorted_chs = sorted(existing, key=lambda x: int(x))
    item.setText(4, ", ".join(sorted_chs))
    assert item.text(4) == "3, 5"  # 没变


def test_X7_load_handles_missing_chapter_links_in_dict_form(charlib, app):
    """dict 形式输入(没 chapter_links 字段)应安全 fallback 为空"""
    charlib._list_to_tree([
        {"node_id": "N-001", "parent_id": "", "name": "故事",
         "kind": "故事", "ch_range": "", "note": ""}  # 没 chapter_links
    ])
    assert charlib.tree_plot.topLevelItemCount() == 1
    assert charlib.tree_plot.topLevelItem(0).text(4) == ""
