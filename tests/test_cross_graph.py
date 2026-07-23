"""
test_cross_graph.py — v1.87 BUG-064 跨表关联可视化(系列收官)

设计:CharLib 加新 sub-tab "关联图谱",用 QGraphicsView 画
"剧情节点 ↔ 角色 ↔ 伏笔 ↔ 承诺 ↔ 信息"网络图。
节点用颜色区分类别,边用同章号关联(复用 v1.86 反查算法语义)。
布局用力导向算法(Fruchterman-Reingold 简化版),纯 Python 实现。

与 v1.84-v1.86 的对照:
  - 数据结构:【完全不动】(v1.86 已经为零依赖查询打好基础)
  - PROMPTS:【无新增】
  - AI 调用:【完全不调】
  - pipeline 阶段:【无新增】
  - 外部依赖:【无】— 不用 cytoscape.js,不用 QtWebEngine
  - 工程量集中:UI + 算法(力导向布局 + 图渲染)

覆盖:
  A. 数据收集 _collect_graph_data(6 个边界)
  B. 力导向算法 _force_directed_layout(节点位置 + 边界约束 + 可重现)
  C. UI 层(sub-tab 添加 + 控件 + 类别过滤实时刷新)
  D. 渲染层 _render_cross_graph(空数据 / 完整数据 / 类别过滤)
  X. 守(空树 / 空库 / 非法章号 / 版本)
"""
import re
import ast
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


def _method_class(tree, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name == method_name:
                    return node.name
    return None


# ─────────────────────────────────────
# 代码归属
# ─────────────────────────────────────

def test_S1_build_method_in_charlib(tree):
    assert _method_class(tree, "_build_cross_graph_tab") == "CharacterLibrary"


def test_S2_collect_method_in_charlib(tree):
    assert _method_class(tree, "_collect_graph_data") == "CharacterLibrary"


def test_S3_layout_method_in_charlib(tree):
    assert _method_class(tree, "_force_directed_layout") == "CharacterLibrary"


def test_S4_render_method_in_charlib(tree):
    assert _method_class(tree, "_render_cross_graph") == "CharacterLibrary"


def test_S5_build_called_in_init(src):
    """_build_cross_graph_tab 必须在 __init__ 里被调用"""
    assert "self._build_cross_graph_tab()" in src


def test_S6_no_new_prompt_no_pipeline(src):
    """v1.87 是纯 UI — 不应有新 PROMPTS,不应有新 pipeline 阶段"""
    # PROMPTS 没新 key
    assert "cross_graph" not in src or 'PROMPTS["cross_graph"]' not in src
    # pipeline 没加新 step
    m = re.search(r"def _post_chapter_chain\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert 'pipeline.append(("cross_graph"' not in block


def test_S7_no_external_deps(src):
    """v1.87 必须只用 PyQt5,不依赖 cytoscape / QtWebEngine"""
    m = re.search(
        r"def _build_cross_graph_tab\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 必须用 QGraphicsView(纯 Qt5)
    assert "QGraphicsView" in block
    assert "QGraphicsScene" in block
    # 不应用 QtWebEngine
    assert "QtWebEngine" not in block
    assert "QWebEngineView" not in block


# ─────────────────────────────────────
# 运行时端到端
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


@pytest.fixture
def populated_charlib(charlib):
    """填充 1 剧情节点 + 角色/伏笔/承诺/信息各 1 条命中"""
    from PyQt5.QtWidgets import QTableWidgetItem
    cl = charlib

    cl._add_plot_root()
    root = cl.tree_plot.topLevelItem(0)
    root.setText(0, "主线 A")
    root.setText(2, "1-5")

    def add_char(name, role, first):
        r = cl.tbl_chars.rowCount()
        cl.tbl_chars.insertRow(r)
        cl.tbl_chars.setItem(r, 0, QTableWidgetItem(name))
        cl.tbl_chars.setItem(r, 1, QTableWidgetItem(role))
        cl.tbl_chars.setItem(r, 7, QTableWidgetItem(str(first)))
    add_char("林远", "主角", 1)  # 命中
    add_char("林悦", "妹妹", 3)  # 命中
    add_char("王屠户", "反派", 10)  # 不命中

    def add_fore(set_ch, content, recover_ch, done):
        r = cl.tbl_fore.rowCount()
        cl.tbl_fore.insertRow(r)
        for col, v in enumerate([set_ch, content, "", done, recover_ch]):
            cl.tbl_fore.setItem(r, col, QTableWidgetItem(v))
    add_fore("3", "黑袍人真身", "", "否")  # 命中

    def add_promise(set_ch, kind, a, b, content, deadline, done):
        r = cl.tbl_promises.rowCount()
        cl.tbl_promises.insertRow(r)
        for col, v in enumerate([set_ch, kind, a, b, content, deadline, done]):
            cl.tbl_promises.setItem(r, col, QTableWidgetItem(v))
    add_promise("4", "承诺", "林远", "林悦", "三年救你", "108", "否")  # 命中

    def add_info(iid, content, src_ch, src_type):
        r = cl.tbl_infos.rowCount()
        cl.tbl_infos.insertRow(r)
        for col, v in enumerate([iid, content, src_ch, src_type]):
            cl.tbl_infos.setItem(r, col, QTableWidgetItem(v))
    add_info("INFO-001", "林远是叶家次子", "2", "设定")  # 命中

    return cl


# ─────────────────────────────────────
# C. UI 层
# ─────────────────────────────────────

def test_C1_sub_tab_added(charlib):
    """CharLib 必须新增"关联图谱" sub-tab"""
    tab_texts = [charlib.sub_tabs.tabText(i)
                 for i in range(charlib.sub_tabs.count())]
    assert any("关联图谱" in t for t in tab_texts), \
        f"sub-tab 列表里没找到 '关联图谱',现状: {tab_texts}"


def test_C2_view_and_scene_exist(charlib):
    assert hasattr(charlib, "cross_graph_view")
    assert hasattr(charlib, "cross_graph_scene")


def test_C3_category_checkboxes(charlib):
    """4 个类别复选框都存在 且 默认勾上"""
    for attr in ("chk_show_chars", "chk_show_fore",
                 "chk_show_promises", "chk_show_infos"):
        assert hasattr(charlib, attr), f"缺 {attr}"
        assert getattr(charlib, attr).isChecked(), f"{attr} 默认应勾选"


def test_C4_iters_spinbox(charlib):
    assert hasattr(charlib, "sb_graph_iters")
    assert charlib.sb_graph_iters.value() == 50  # 默认 50


# ─────────────────────────────────────
# A. 数据收集
# ─────────────────────────────────────

def test_A1_collect_empty(charlib):
    """空树 + 空库 → 空节点 + 空边"""
    nodes, edges = charlib._collect_graph_data()
    assert nodes == []
    assert edges == []


def test_A2_collect_with_plot_only(charlib):
    """有剧情节点但无其他库数据 → 1 节点 0 边"""
    charlib._add_plot_root()
    root = charlib.tree_plot.topLevelItem(0)
    root.setText(0, "主线")
    root.setText(2, "1-5")
    nodes, edges = charlib._collect_graph_data()
    assert len(nodes) == 1
    assert nodes[0]["kind"] == "plot"
    assert edges == []


def test_A3_collect_full(populated_charlib):
    """完整数据 → 6 节点 5 边(1 plot + 2 char + 1 fore + 1 promise + 1 info)"""
    nodes, edges = populated_charlib._collect_graph_data()
    assert len(nodes) == 6
    assert len(edges) == 5


def test_A4_collect_node_kinds(populated_charlib):
    """6 节点应包含全部 5 个 kind"""
    nodes, _ = populated_charlib._collect_graph_data()
    kinds = set(n["kind"] for n in nodes)
    assert kinds == {"plot", "char", "fore", "promise", "info"}


def test_A5_collect_filter_chars(populated_charlib):
    """关掉角色复选框 → 角色不被收集"""
    populated_charlib.chk_show_chars.setChecked(False)
    nodes, edges = populated_charlib._collect_graph_data()
    char_nodes = [n for n in nodes if n["kind"] == "char"]
    assert char_nodes == []
    # 边也应减少(2 个 plot↔char 边消失)
    assert len(edges) == 3


def test_A6_collect_filter_all_categories(populated_charlib):
    """关掉所有非 plot 类别 → 只剩 1 个 plot 节点 0 边"""
    populated_charlib.chk_show_chars.setChecked(False)
    populated_charlib.chk_show_fore.setChecked(False)
    populated_charlib.chk_show_promises.setChecked(False)
    populated_charlib.chk_show_infos.setChecked(False)
    nodes, edges = populated_charlib._collect_graph_data()
    assert len(nodes) == 1
    assert nodes[0]["kind"] == "plot"
    assert edges == []


def test_A7_collect_dangling_char_not_in_plot_range(populated_charlib):
    """王屠户@10 不在剧情节点 ch_range=1-5 内 → 不该被收集"""
    nodes, _ = populated_charlib._collect_graph_data()
    char_labels = [n["label"] for n in nodes if n["kind"] == "char"]
    assert "王屠户" not in " ".join(char_labels)


def test_A8_collect_each_node_has_color(populated_charlib):
    """每个节点必须有 color 字段(用于渲染)"""
    nodes, _ = populated_charlib._collect_graph_data()
    for n in nodes:
        assert "color" in n
        assert n["color"].startswith("#")


def test_A9_collect_each_edge_has_label(populated_charlib):
    """每条边必须有章号 label"""
    _, edges = populated_charlib._collect_graph_data()
    for a, b, label in edges:
        assert label and "章" in label


# ─────────────────────────────────────
# B. 力导向算法
# ─────────────────────────────────────

def test_B1_layout_empty_returns_empty(charlib):
    pos = charlib._force_directed_layout([], [], iters=10)
    assert pos == {}


def test_B2_layout_returns_all_node_positions(charlib):
    nodes = [
        {"id": "a", "label": "A", "kind": "plot", "color": "#3a6fc4"},
        {"id": "b", "label": "B", "kind": "char", "color": "#2da44e"},
        {"id": "c", "label": "C", "kind": "fore", "color": "#dd7e1c"},
    ]
    edges = [("a", "b", "第1章"), ("a", "c", "第2章")]
    pos = charlib._force_directed_layout(nodes, edges, iters=20)
    assert set(pos.keys()) == {"a", "b", "c"}
    for nid, (x, y) in pos.items():
        assert isinstance(x, float)
        assert isinstance(y, float)


def test_B3_layout_bounded_within_canvas(charlib):
    """所有节点位置应在画布内(20 ≤ x,y ≤ width-20 / height-20)"""
    nodes = [
        {"id": f"n{i}", "label": str(i), "kind": "plot", "color": "#3a6fc4"}
        for i in range(10)
    ]
    edges = []
    pos = charlib._force_directed_layout(
        nodes, edges, iters=50, width=800, height=600)
    for nid, (x, y) in pos.items():
        assert 20 <= x <= 800 - 20
        assert 20 <= y <= 600 - 20


def test_B4_layout_reproducible(charlib):
    """两次调用同样输入应得同样结果(seed=42)"""
    nodes = [
        {"id": "a", "label": "A", "kind": "plot", "color": "#3a6fc4"},
        {"id": "b", "label": "B", "kind": "char", "color": "#2da44e"},
    ]
    edges = [("a", "b", "第1章")]
    pos1 = charlib._force_directed_layout(nodes, edges, iters=20)
    pos2 = charlib._force_directed_layout(nodes, edges, iters=20)
    assert pos1 == pos2


def test_B5_layout_connected_closer_than_disconnected(charlib):
    """相连节点应比孤立节点更近(力导向核心特性)"""
    import math
    nodes = [
        {"id": "a", "label": "A", "kind": "plot", "color": "#3a6fc4"},
        {"id": "b", "label": "B", "kind": "plot", "color": "#3a6fc4"},
        {"id": "c", "label": "C", "kind": "plot", "color": "#3a6fc4"},
    ]
    # a, b 相连;a, c 不相连
    edges = [("a", "b", "第1章")]
    pos = charlib._force_directed_layout(nodes, edges, iters=100)
    dist_ab = math.sqrt(
        (pos["a"][0] - pos["b"][0]) ** 2 +
        (pos["a"][1] - pos["b"][1]) ** 2)
    dist_ac = math.sqrt(
        (pos["a"][0] - pos["c"][0]) ** 2 +
        (pos["a"][1] - pos["c"][1]) ** 2)
    # 相连节点 a-b 应比孤立的 a-c 近(力导向应让相连的吸引)
    assert dist_ab < dist_ac, \
        f"相连节点应更近: ab={dist_ab:.1f}, ac={dist_ac:.1f}"


# ─────────────────────────────────────
# D. 渲染层
# ─────────────────────────────────────

def test_D1_render_empty_shows_hint(charlib):
    """空数据时 render 应显示提示文字,不该崩"""
    charlib._render_cross_graph()
    items = charlib.cross_graph_scene.items()
    assert len(items) >= 1  # 至少有提示文字


def test_D2_render_populated_creates_items(populated_charlib):
    """完整数据 render 应在 scene 上创建多个 item"""
    populated_charlib._render_cross_graph()
    items = populated_charlib.cross_graph_scene.items()
    # 6 节点 → 6 ellipse + 6 label;5 边 → 5 line;部分 edge label
    assert len(items) >= 17, f"items 太少: {len(items)}"


def test_D3_render_clears_previous(populated_charlib):
    """多次 render 不应累积"""
    populated_charlib._render_cross_graph()
    n1 = len(populated_charlib.cross_graph_scene.items())
    populated_charlib._render_cross_graph()
    n2 = len(populated_charlib.cross_graph_scene.items())
    assert n1 == n2, f"重复 render 不该累积: 第一次 {n1}, 第二次 {n2}"


def test_D4_render_with_filter_fewer_items(populated_charlib):
    """关类别后 render 的 item 应减少"""
    populated_charlib._render_cross_graph()
    full_n = len(populated_charlib.cross_graph_scene.items())
    # 关闭信息
    populated_charlib.chk_show_infos.setChecked(False)
    populated_charlib._render_cross_graph()
    filtered_n = len(populated_charlib.cross_graph_scene.items())
    assert filtered_n < full_n, \
        f"过滤后 item 应减少: full={full_n}, filtered={filtered_n}"


# ─────────────────────────────────────
# X. 守
# ─────────────────────────────────────

def test_X1_collect_invalid_char_first_chapter_no_crash(charlib):
    """角色"首次出场"字段非法时 → 不该崩"""
    from PyQt5.QtWidgets import QTableWidgetItem
    charlib._add_plot_root()
    root = charlib.tree_plot.topLevelItem(0)
    root.setText(2, "1-5")
    r = charlib.tbl_chars.rowCount()
    charlib.tbl_chars.insertRow(r)
    charlib.tbl_chars.setItem(r, 0, QTableWidgetItem("某人"))
    charlib.tbl_chars.setItem(r, 7, QTableWidgetItem("乱写"))  # 非法
    # 不应崩
    nodes, _ = charlib._collect_graph_data()
    # 该角色应被跳过
    assert "某人" not in [n["label"] for n in nodes
                         if n["kind"] == "char"]


def test_X2_collect_empty_content_skipped(charlib):
    """伏笔/承诺/信息的核心字段(内容/iid)空时跳过"""
    from PyQt5.QtWidgets import QTableWidgetItem
    charlib._add_plot_root()
    root = charlib.tree_plot.topLevelItem(0)
    root.setText(2, "1-5")
    # 空 content 的伏笔
    r = charlib.tbl_fore.rowCount()
    charlib.tbl_fore.insertRow(r)
    charlib.tbl_fore.setItem(r, 0, QTableWidgetItem("3"))
    charlib.tbl_fore.setItem(r, 1, QTableWidgetItem(""))  # 空内容
    nodes, _ = charlib._collect_graph_data()
    fore_nodes = [n for n in nodes if n["kind"] == "fore"]
    assert fore_nodes == []


def test_X3_collect_no_plot_returns_empty(charlib):
    """没剧情节点时,即便其他库有数据也返回空(因为没参考点)"""
    from PyQt5.QtWidgets import QTableWidgetItem
    r = charlib.tbl_chars.rowCount()
    charlib.tbl_chars.insertRow(r)
    charlib.tbl_chars.setItem(r, 0, QTableWidgetItem("林远"))
    charlib.tbl_chars.setItem(r, 7, QTableWidgetItem("1"))
    nodes, edges = charlib._collect_graph_data()
    assert nodes == []
    assert edges == []


def test_X4_layout_single_node_safe(charlib):
    """单节点(无边)布局不该崩"""
    nodes = [{"id": "solo", "label": "S", "kind": "plot", "color": "#3a6fc4"}]
    pos = charlib._force_directed_layout(nodes, [], iters=20)
    assert "solo" in pos


def test_X5_render_after_data_change(populated_charlib):
    """改数据后再 render → item 数应反映新数据"""
    from PyQt5.QtWidgets import QTableWidgetItem
    populated_charlib._render_cross_graph()
    n1 = len(populated_charlib.cross_graph_scene.items())
    # 加一个新承诺
    r = populated_charlib.tbl_promises.rowCount()
    populated_charlib.tbl_promises.insertRow(r)
    for col, v in enumerate(["5", "承诺", "X", "Y", "新承诺", "20", "否"]):
        populated_charlib.tbl_promises.setItem(r, col, QTableWidgetItem(v))
    populated_charlib._render_cross_graph()
    n2 = len(populated_charlib.cross_graph_scene.items())
    assert n2 > n1, f"新数据 render 后 items 应增加: {n1} → {n2}"


def test_X6_version_bumped(src):
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)(?:\.\d+)?"', src)
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 87), \
        f"v1.87 跨表关联可视化不应被低版本退回,当前 v{major}.{minor}"


def test_X7_wheel_event_handler_exists(src):
    """滚轮缩放 handler 必须接到 cross_graph_view.wheelEvent"""
    assert "self.cross_graph_view.wheelEvent" in src
    assert "_cross_graph_wheel" in src


def test_X8_node_id_uses_kind_prefix(populated_charlib):
    """节点 id 应有 kind:row 前缀格式(避免不同库的同 row 冲突)"""
    nodes, _ = populated_charlib._collect_graph_data()
    for n in nodes:
        assert ":" in n["id"], f"节点 id 应含前缀: {n['id']}"
        kind, _ = n["id"].split(":", 1)
        assert kind in ("plot", "char", "fore", "promise", "info")
