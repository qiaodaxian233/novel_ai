"""
test_cross_ref.py — v1.86 BUG-063 多视角反查

设计:右键剧情树节点 → 弹窗显示该节点关联的角色/伏笔/承诺/关系/信息。
所有数据已在 v1.50/v1.76-v1.85 各库就位,v1.86 只做反查算法 + UI。

反查算法:节点的 chapter_links(v1.85)+ ch_range(v1.80)合并出
"该节点关联章号集合"chs,然后扫各库找章号 ∈ chs 的条目。

与 v1.76-v1.85 的对照:
  - 数据形态:【完全不动数据】,只读 6 库现有字段
  - PROMPTS:【无新增】 — 纯本地计算,不调 AI
  - 章末检查:【无】 — 用户主动右键触发
  - pipeline 阶段:【无】
  - 性质:纯查询 + UI 弹窗

覆盖:
  A. 算法层:_node_chapter_set + _compute_node_cross_refs
  B. 代码归属:3 个新方法在 CharacterLibrary
  C. UI 层:右键菜单 + Dialog 构造不崩
  D. 端到端:完整库 → 反查 → 期望条目命中
  X. 守:空数据/非法 ch_range/无关库
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
# B. 代码归属
# ─────────────────────────────────────

def test_B1_node_chapter_set_in_charlib(tree):
    assert _method_class(tree, "_node_chapter_set") == "CharacterLibrary"


def test_B2_compute_cross_refs_in_charlib(tree):
    assert _method_class(tree, "_compute_node_cross_refs") == "CharacterLibrary"


def test_B3_show_context_menu_in_charlib(tree):
    assert _method_class(tree, "_show_plot_node_context_menu") == "CharacterLibrary"


def test_B4_open_dialog_in_charlib(tree):
    assert _method_class(tree, "_open_node_cross_refs_dialog") == "CharacterLibrary"


def test_B5_no_new_prompt_no_pipeline(src):
    """v1.86 是纯查询 — 不应有新 PROMPTS,不应有新 pipeline 阶段"""
    # PROMPTS 没新 key
    assert "cross_ref" not in src or 'PROMPTS["cross_ref"]' not in src
    assert "node_cross" not in src or 'PROMPTS["node_cross"]' not in src
    # pipeline 没加新 step
    m = re.search(r"def _post_chapter_chain\(.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert 'pipeline.append(("cross_ref"' not in block
    assert 'pipeline.append(("node_cross"' not in block


def test_B6_context_menu_registered(src):
    """剧情树必须设置 CustomContextMenu + connect 到 _show_plot_node_context_menu"""
    assert "setContextMenuPolicy(_Qt.CustomContextMenu)" in src or \
           "setContextMenuPolicy(Qt.CustomContextMenu)" in src
    assert "customContextMenuRequested.connect" in src
    assert "_show_plot_node_context_menu" in src


# ─────────────────────────────────────
# A & D. 算法 + 端到端
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
def charlib_with_node(charlib):
    """带一个剧情树节点的 CharLib(用于反查测试)"""
    charlib._add_plot_root()
    return charlib


# ─────────────────────────────────────
# A. _node_chapter_set 算法
# ─────────────────────────────────────

def test_A1_chapter_set_from_ch_range(charlib_with_node):
    """ch_range='1-5' → {1,2,3,4,5}"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "1-5")
    root.setText(4, "")
    assert charlib_with_node._node_chapter_set(root) == {1, 2, 3, 4, 5}


def test_A2_chapter_set_from_links(charlib_with_node):
    """chapter_links='3, 7, 9' → {3, 7, 9}"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "")
    root.setText(4, "3, 7, 9")
    assert charlib_with_node._node_chapter_set(root) == {3, 7, 9}


def test_A3_chapter_set_union(charlib_with_node):
    """ch_range='3-5' + chapter_links='7,9' → union {3,4,5,7,9}"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "3-5")
    root.setText(4, "7, 9")
    assert charlib_with_node._node_chapter_set(root) == {3, 4, 5, 7, 9}


def test_A4_chapter_set_single_number(charlib_with_node):
    """ch_range='10' 单数 → {10}"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "10")
    root.setText(4, "")
    assert charlib_with_node._node_chapter_set(root) == {10}


def test_A5_chapter_set_invalid_safe(charlib_with_node):
    """非法 ch_range 不崩"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "乱写")
    root.setText(4, "")
    assert charlib_with_node._node_chapter_set(root) == set()


def test_A6_chapter_set_empty(charlib_with_node):
    """全空 → 空集"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "")
    root.setText(4, "")
    assert charlib_with_node._node_chapter_set(root) == set()


def test_A7_chapter_set_dedupe(charlib_with_node):
    """ch_range='1-5' 与 chapter_links 重复章号 → 自动去重"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "1-5")
    root.setText(4, "3, 4, 7")
    assert charlib_with_node._node_chapter_set(root) == {1, 2, 3, 4, 5, 7}


# ─────────────────────────────────────
# D. _compute_node_cross_refs 端到端
# ─────────────────────────────────────

@pytest.fixture
def populated_charlib(charlib_with_node):
    """填充 6 库数据,用第 1/4/10 章作为各库的章号锚点"""
    from PyQt5.QtWidgets import QTableWidgetItem
    cl = charlib_with_node

    # 节点 ch_range 3-5,chapter_links 4 → chs = {3,4,5}
    root = cl.tree_plot.topLevelItem(0)
    root.setText(0, "得知线索")
    root.setText(2, "3-5")
    root.setText(4, "4")

    # 角色:1=不命中,4=命中,10=不命中
    def add_char(name, role, first):
        r = cl.tbl_chars.rowCount()
        cl.tbl_chars.insertRow(r)
        cl.tbl_chars.setItem(r, 0, QTableWidgetItem(name))
        cl.tbl_chars.setItem(r, 1, QTableWidgetItem(role))
        cl.tbl_chars.setItem(r, 7, QTableWidgetItem(str(first)))
    add_char("林远", "主角", 1)
    add_char("林悦", "妹妹", 4)
    add_char("王屠户", "反派", 10)

    # 伏笔:埋第 3 章=命中,埋第 4 章=命中,埋第 10 章=不命中
    def add_fore(set_ch, content, recover, done):
        r = cl.tbl_fore.rowCount()
        cl.tbl_fore.insertRow(r)
        for col, v in enumerate([set_ch, content, "", done, recover]):
            cl.tbl_fore.setItem(r, col, QTableWidgetItem(v))
    add_fore("3", "黑袍人真身", "", "否")
    add_fore("4", "玉佩来历", "", "否")
    add_fore("10", "魔教阴谋", "", "否")

    # 承诺:埋第 5 章=命中,埋第 8 章=不命中
    def add_promise(set_ch, kind, a, b, content, deadline, done):
        r = cl.tbl_promises.rowCount()
        cl.tbl_promises.insertRow(r)
        for col, v in enumerate([set_ch, kind, a, b, content, deadline, done]):
            cl.tbl_promises.setItem(r, col, QTableWidgetItem(v))
    add_promise("5", "承诺", "林远", "林悦", "三年救你", "108", "否")
    add_promise("8", "威胁", "魔教", "林远", "灭你满门", "20", "否")

    # 关系值变化:第 4 章=命中,第 10 章=不命中
    def add_relv(a, b, val, ch):
        r = cl.tbl_rel_values.rowCount()
        cl.tbl_rel_values.insertRow(r)
        for col, v in enumerate([a, b, val, ch]):
            cl.tbl_rel_values.setItem(r, col, QTableWidgetItem(v))
    add_relv("林远", "林悦", "90", "4")
    add_relv("林远", "王屠户", "-80", "10")

    # 信息:第 3 章=命中,第 12 章=不命中
    def add_info(iid, content, src_ch, src_type):
        r = cl.tbl_infos.rowCount()
        cl.tbl_infos.insertRow(r)
        for col, v in enumerate([iid, content, src_ch, src_type]):
            cl.tbl_infos.setItem(r, col, QTableWidgetItem(v))
    add_info("INFO-001", "林远是叶家次子", "3", "设定")
    add_info("INFO-002", "魔教大长老", "12", "事件揭露")

    return cl


def test_D1_cross_refs_returns_dict(populated_charlib):
    """返回必须是 dict 含 6 个 key"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    refs = populated_charlib._compute_node_cross_refs(root)
    for k in ("chapters", "foreshadows", "promises",
              "rel_changes", "infos", "characters"):
        assert k in refs, f"反查结果缺 key {k}"


def test_D2_cross_refs_chapters_sorted(populated_charlib):
    """chapters 必须是有序 list[int]"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    refs = populated_charlib._compute_node_cross_refs(root)
    assert refs["chapters"] == [3, 4, 5]


def test_D3_cross_refs_characters_filtered(populated_charlib):
    """角色:只林悦命中(首次出场=4)"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    refs = populated_charlib._compute_node_cross_refs(root)
    names = [c[1] for c in refs["characters"]]
    assert "林悦" in names
    assert "林远" not in names
    assert "王屠户" not in names


def test_D4_cross_refs_foreshadows_filtered(populated_charlib):
    """伏笔:第 3 / 第 4 章埋设的命中"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    refs = populated_charlib._compute_node_cross_refs(root)
    contents = [f[1] for f in refs["foreshadows"]]
    assert "黑袍人真身" in contents
    assert "玉佩来历" in contents
    assert "魔教阴谋" not in contents


def test_D5_cross_refs_promises_filtered(populated_charlib):
    """承诺:第 5 章埋的命中,第 8 章的不命中"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    refs = populated_charlib._compute_node_cross_refs(root)
    contents = [p[3] for p in refs["promises"]]
    assert "三年救你" in contents
    assert "灭你满门" not in contents


def test_D6_cross_refs_rel_changes_filtered(populated_charlib):
    """关系变化:第 4 章=命中,第 10 章=不命中"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    refs = populated_charlib._compute_node_cross_refs(root)
    pairs = [(c[1], c[2]) for c in refs["rel_changes"]]
    assert ("林远", "林悦") in pairs
    assert ("林远", "王屠户") not in pairs


def test_D7_cross_refs_infos_filtered(populated_charlib):
    """信息:第 3 章来源=命中,第 12 章=不命中"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    refs = populated_charlib._compute_node_cross_refs(root)
    iids = [i[1] for i in refs["infos"]]
    assert "INFO-001" in iids
    assert "INFO-002" not in iids


def test_D8_cross_refs_uses_both_ch_range_and_links(populated_charlib):
    """改成 ch_range 空 + chapter_links='4' → 只命中第 4 章相关的"""
    root = populated_charlib.tree_plot.topLevelItem(0)
    root.setText(2, "")  # 清空 ch_range
    root.setText(4, "4")  # 只第 4 章
    refs = populated_charlib._compute_node_cross_refs(root)
    assert refs["chapters"] == [4]
    # 林悦(首次第 4 章)命中
    assert any("林悦" in c[1] for c in refs["characters"])
    # 第 3 章的伏笔『黑袍人真身』不命中,第 4 章的『玉佩来历』命中
    fore_contents = [f[1] for f in refs["foreshadows"]]
    assert "玉佩来历" in fore_contents
    assert "黑袍人真身" not in fore_contents


# ─────────────────────────────────────
# X. 守
# ─────────────────────────────────────

def test_X1_empty_node_no_crash(charlib_with_node):
    """空节点(ch_range 和 chapter_links 都空)反查不崩,所有类别空"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "")
    root.setText(4, "")
    refs = charlib_with_node._compute_node_cross_refs(root)
    assert refs["chapters"] == []
    for k in ("foreshadows", "promises", "rel_changes", "infos", "characters"):
        assert refs[k] == []


def test_X2_invalid_ch_range_no_crash(charlib_with_node):
    """非法 ch_range 不崩"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "完全不是数字")
    root.setText(4, "")
    refs = charlib_with_node._compute_node_cross_refs(root)
    assert refs["chapters"] == []  # 不崩,但章节集为空


def test_X3_invalid_links_partial_safe(charlib_with_node):
    """chapter_links 部分合法 → 跳过非法,保留合法"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "")
    root.setText(4, "5, abc, 7")
    chs = charlib_with_node._node_chapter_set(root)
    assert chs == {5, 7}  # abc 被跳过


def test_X4_empty_libs_no_crash(charlib_with_node):
    """6 库全空时反查不崩"""
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "1-100")
    root.setText(4, "")
    refs = charlib_with_node._compute_node_cross_refs(root)
    assert refs["chapters"] == list(range(1, 101))
    for k in ("foreshadows", "promises", "rel_changes", "infos", "characters"):
        assert refs[k] == []  # 库都空


def test_X5_lib_row_with_empty_ch_field_no_crash(charlib_with_node):
    """某行的章号字段空时,反查不该崩"""
    from PyQt5.QtWidgets import QTableWidgetItem
    root = charlib_with_node.tree_plot.topLevelItem(0)
    root.setText(2, "1-5")
    # 加个伏笔但章号字段空
    charlib_with_node.tbl_fore.insertRow(0)
    charlib_with_node.tbl_fore.setItem(0, 0, QTableWidgetItem(""))  # 空埋设章
    charlib_with_node.tbl_fore.setItem(0, 1, QTableWidgetItem("无章号伏笔"))
    charlib_with_node.tbl_fore.setItem(0, 4, QTableWidgetItem(""))  # 空回收章
    refs = charlib_with_node._compute_node_cross_refs(root)
    # 不崩,且该伏笔不命中(因为没章号匹配)
    fore_contents = [f[1] for f in refs["foreshadows"]]
    assert "无章号伏笔" not in fore_contents


def test_X6_version_bumped(src):
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)(?:\.\d+)?"', src)
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 86), \
        f"v1.86 多视角反查不应被低版本退回,当前 v{major}.{minor}"


def test_X7_dialog_opens_no_crash(populated_charlib, app):
    """对话框能开不崩 — 直接调用 _open_node_cross_refs_dialog
    但因为 exec_() 会阻塞,这里只检查构造不抛异常"""
    # 用 monkey patch 让 exec_ 立刻返回
    from PyQt5.QtWidgets import QDialog
    orig_exec = QDialog.exec_
    QDialog.exec_ = lambda self: 0
    try:
        root = populated_charlib.tree_plot.topLevelItem(0)
        # 不应抛异常
        populated_charlib._open_node_cross_refs_dialog(root)
    finally:
        QDialog.exec_ = orig_exec


def test_X8_context_menu_no_item_no_crash(charlib_with_node, app):
    """右键在没节点的位置 → itemAt 返回 None → 不该崩"""
    from PyQt5.QtCore import QPoint
    # 模拟点在 (0, 9999)(树外)
    charlib_with_node._show_plot_node_context_menu(QPoint(0, 9999))
    # 没崩就过
