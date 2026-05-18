# -*- coding: utf-8 -*-
"""
test_relation_graph.py — v1.70 🕸️ 关系网测试

覆盖:
1. relation_graph 模块结构与公开 API
2. build_graph_data 数据转换正确性(节点染色 / 边染色 / 自动补节点 / HTML escape)
3. novel_ai.py 集成正确性:
   - import 语句 + RELATION_GRAPH_AVAILABLE 标志
   - 3 个新方法都在 CharacterLibrary 类里(BUG-046 教训:ast 防错插)
   - sub_tabs 加入 "🕸️ 关系网"
   - APP_VERSION 已升到 v1.70
4. vendor/vis-network.min.js 文件存在且非空
"""

import ast
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
NOVEL_AI_PY = ROOT / "novel_ai.py"
RELATION_GRAPH_PY = ROOT / "relation_graph.py"
VENDOR_JS = ROOT / "vendor" / "vis-network.min.js"


# ── 1. relation_graph 模块文件 + 关键定义 ────────────────
def test_module_file_exists():
    assert RELATION_GRAPH_PY.exists(), "relation_graph.py 不存在"


def test_module_has_key_definitions():
    src = RELATION_GRAPH_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.ClassDef))
    }
    for must in [
        "RelationGraphWidget", "build_graph_data",
        "_pick_role_color", "_pick_edge_color", "_build_html",
    ]:
        assert must in names, f"relation_graph 缺定义 {must}"


def test_color_constants_present():
    import relation_graph
    # 节点颜色:6 种角色定位
    for role in ["主角", "女主", "反派", "导师", "配角", "路人"]:
        assert role in relation_graph.ROLE_COLORS, f"ROLE_COLORS 缺 {role}"
    # 边颜色:用户拍板的 6 类型必须命中
    for rel in ["师父", "恋人", "血缘", "同盟", "宿敌", "敌对"]:
        assert rel in relation_graph.RELATION_COLORS, f"RELATION_COLORS 缺 {rel}"


# ── 2. build_graph_data 数据转换 ─────────────────────────
def test_build_graph_data_basic():
    import relation_graph
    chars = [
        ["林远", "主角", "黑发", "坚毅", "", "咒血者", "练气一层", "第1章"],
        ["林悦", "女主", "清秀", "聪慧", "", "剑修", "内门弟子", "第1章"],
    ]
    relations = [["林远", "血缘", "林悦", "亲兄妹"]]
    data = relation_graph.build_graph_data(chars, relations)
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["from"] == "林远"
    assert data["edges"][0]["to"] == "林悦"


def test_node_color_by_role():
    import relation_graph
    chars = [
        ["A", "主角", "", "", "", "", "", ""],
        ["B", "反派", "", "", "", "", "", ""],
        ["C", "导师", "", "", "", "", "", ""],
    ]
    data = relation_graph.build_graph_data(chars, [])
    colors = {n["id"]: n["color"]["background"] for n in data["nodes"]}
    assert colors["A"] == "#FFD700"  # 主角=金
    assert colors["B"] == "#8B0000"  # 反派=深红
    assert colors["C"] == "#1E88E5"  # 导师=蓝


def test_edge_color_by_type():
    import relation_graph
    chars = [["A", "", "", "", "", "", "", ""], ["B", "", "", "", "", "", "", ""]]
    relations = [
        ["A", "血缘", "B", ""],
        ["A", "宿敌", "B", ""],
        ["A", "同盟", "B", ""],
    ]
    data = relation_graph.build_graph_data(chars, relations)
    colors = {e["label"]: e["color"]["color"] for e in data["edges"]}
    assert colors["血缘"] == "#FB8C00"
    assert colors["宿敌"] == "#B71C1C"
    assert colors["同盟"] == "#43A047"


def test_auto_add_missing_node_from_relations():
    """关系表里出现但角色库没有的角色,应自动补节点(灰色)"""
    import relation_graph
    chars = [["林远", "主角", "", "", "", "", "", ""]]
    relations = [["林远", "同盟", "苏婉清", "客栈相识"]]  # 苏婉清没在角色库
    data = relation_graph.build_graph_data(chars, relations)
    names = [n["id"] for n in data["nodes"]]
    assert "苏婉清" in names, "应该自动补节点"
    su = next(n for n in data["nodes"] if n["id"] == "苏婉清")
    assert su["color"]["background"] == "#ECEFF1", "补的节点应该是灰底"


def test_html_escape_in_tooltip():
    """用户在角色字段写 <script> 之类的,必须 escape,不能直接进 tooltip HTML"""
    import relation_graph
    chars = [["A", "主角", "<script>alert(1)</script>", "", "", "", "", ""]]
    data = relation_graph.build_graph_data(chars, [])
    tooltip = data["nodes"][0]["title"]
    assert "<script>" not in tooltip, "tooltip 应该 escape 用户输入"
    assert "&lt;script&gt;" in tooltip, "escape 应该用 &lt;"


def test_empty_data_returns_empty_lists():
    import relation_graph
    data = relation_graph.build_graph_data([], [])
    assert data == {"nodes": [], "edges": []}


def test_skip_empty_name_rows():
    """角色库里有空行(用户加了又删一半),不应产生空 id 节点"""
    import relation_graph
    chars = [
        ["林远", "主角", "", "", "", "", "", ""],
        ["", "配角", "", "", "", "", "", ""],  # 空名
    ]
    data = relation_graph.build_graph_data(chars, [])
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "林远"


def test_skip_incomplete_relations():
    """A 或 B 为空的关系不入边"""
    import relation_graph
    chars = [["林远", "主角", "", "", "", "", "", ""]]
    relations = [
        ["林远", "师父", "", ""],   # B 空
        ["", "敌对", "王屠户", ""],  # A 空
    ]
    data = relation_graph.build_graph_data(chars, relations)
    assert len(data["edges"]) == 0, "不完整的关系应跳过"


# ── 3. novel_ai.py 集成验证 ──────────────────────────────
def _read_src():
    return NOVEL_AI_PY.read_text(encoding="utf-8")


def test_import_in_novel_ai():
    src = _read_src()
    assert "import relation_graph" in src
    assert "RELATION_GRAPH_AVAILABLE" in src


def test_app_version_at_least_v1_70():
    """v1.70 是关系网功能引入的版本,之后版本号必须 ≥ v1.70(后续 bug fix 末位+1 都通过)"""
    src = _read_src()
    m = re.search(r'APP_VERSION\s*=\s*["\']v(\d+)\.(\d+)["\']', src)
    assert m, "找不到 APP_VERSION 声明"
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 70), f"APP_VERSION 应 ≥ v1.70,实际 v{major}.{minor}"


def test_new_methods_in_CharacterLibrary():
    """BUG-046 教训:3 个新方法必须在 CharacterLibrary 类里,不能错插到其他类"""
    src = _read_src()
    tree = ast.parse(src)
    target = {"_build_relation_graph_tab", "_refresh_relation_graph", "_on_sub_tab_changed"}
    found = set()
    elsewhere = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in target:
                    if node.name == "CharacterLibrary":
                        found.add(item.name)
                    else:
                        elsewhere.append((node.name, item.name))
    assert found == target, f"CharacterLibrary 内方法不全:{found}"
    assert not elsewhere, f"方法被错插到其他类:{elsewhere}"


def test_sub_tab_added():
    """新 sub_tab '🕸️ 关系网' 必须被 addTab"""
    src = _read_src()
    assert '"🕸️ 关系网"' in src, "addTab 字串未出现"


def test_sub_tab_order():
    """sub_tab 顺序:角色库 → 关系图谱 → 关系网 → 时间线 → ..."""
    src = _read_src()
    # 找 _build_ui 里的方法调用顺序
    calls_block = re.search(
        r"self\._build_characters_tab\(\).*?self\._build_coolpts_tab\(\)",
        src, re.DOTALL,
    )
    assert calls_block, "找不到 _build_ui 调用块"
    block = calls_block.group(0)
    # 验证顺序:relation_graph_tab 必须在 relations_tab 后、timeline_tab 前
    p_rel = block.find("_build_relations_tab")
    p_graph = block.find("_build_relation_graph_tab")
    p_timeline = block.find("_build_timeline_tab")
    assert p_rel < p_graph < p_timeline, \
        f"sub_tab 顺序错:_build_relations_tab({p_rel}) → _build_relation_graph_tab({p_graph}) → _build_timeline_tab({p_timeline})"


def test_currentChanged_signal_connected():
    """切换 sub_tab 必须触发刷新"""
    src = _read_src()
    assert "self.sub_tabs.currentChanged.connect" in src
    assert "_on_sub_tab_changed" in src


# ── 4. vendor 文件 ───────────────────────────────────────
def test_vendor_vis_network_present():
    assert VENDOR_JS.exists(), "vendor/vis-network.min.js 不存在"
    sz = VENDOR_JS.stat().st_size
    # 9.x standalone min 大约 600KB,容差 ±200KB
    assert 400_000 < sz < 900_000, f"vis-network.min.js 大小异常: {sz} bytes"


def test_vendor_vis_network_is_real_library():
    """sanity check:文件确实是 vis-network,不是空文件 / 占位文本"""
    text = VENDOR_JS.read_text(encoding="utf-8", errors="replace")[:5000]
    assert "vis-network" in text or "visjs" in text.lower(), \
        "vis-network.min.js 头部不像真库"


# ── 5. RELATION_COLORS 必须覆盖用户提示语里所有示例 ──────
def test_relation_colors_cover_user_examples():
    """关系图谱 sub_tab 的提示标签里列了一串示例,RELATION_COLORS 应该都能命中"""
    import relation_graph
    # 提示语:"师父/师弟/师妹/对手/暗恋对象/恋人/血缘/宿敌/同盟/上下级"
    for rel in ["师父", "师弟", "师妹", "对手", "暗恋对象", "恋人",
                "血缘", "宿敌", "同盟", "上下级"]:
        color = relation_graph._pick_edge_color(rel)
        assert color != relation_graph.DEFAULT_EDGE_COLOR, \
            f"关系类型 '{rel}' 没在 RELATION_COLORS 命中,会用默认灰色"


# ── 6. v1.71 修复回归守护 ───────────────────────────────
def test_html_uses_absolute_fill_not_vh():
    """v1.71 A 修复:HTML 模板 #network 用 absolute fill 替代 100vh,确保铺满 view"""
    import relation_graph
    html_text = relation_graph._build_html(
        [{"id": "A", "label": "A"}], [], "vis-network.min.js")
    # #network 必须用 absolute 定位
    assert "position:absolute" in html_text or "position: absolute" in html_text, \
        "#network 应使用 absolute 定位"
    # 不能再用 100vh(它在 QWebEngineView 里会出问题)
    assert "100vh" not in html_text, "不应再使用 100vh,改用 absolute fill"


def test_html_calls_fit_after_stabilization():
    """v1.71 A 修复:stabilization 后必须显式调用 network.fit() 把节点居中"""
    import relation_graph
    html_text = relation_graph._build_html(
        [{"id": "A", "label": "A"}], [], "vis-network.min.js")
    assert "network.fit(" in html_text, "stabilization 后应显式调 network.fit() 居中"
    assert "stabilizationIterationsDone" in html_text


def test_widget_has_max_height_constraint():
    """v1.71 B 修复:RelationGraphWidget 在 _build_relation_graph_tab 里被
    setMaximumHeight 限制,避免画布把整个 sub_tab 撑爆。"""
    src = _read_src()
    # 找到 _build_relation_graph_tab 函数体
    m = re.search(
        r"def _build_relation_graph_tab\(self\):(.*?)def \w",
        src, re.DOTALL,
    )
    assert m, "找不到 _build_relation_graph_tab"
    body = m.group(1)
    assert "setMaximumHeight" in body, "应该给 relation_graph_widget 设 setMaximumHeight"
    assert "setMinimumHeight" in body, "应该给 relation_graph_widget 设 setMinimumHeight"
