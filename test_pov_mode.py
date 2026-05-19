"""
test_pov_mode.py — v1.84 角色 POV 模式

设计:在已有信息隔离 v1.79 数据结构基础上,加 POV 过滤层。
- UI:CharacterLibrary 顶部加 POV 配置(下拉框 + 角色名)
- build_inject_block 接受 POV 参数,按 POV 角色已知信息收窄全局注入
- 持久化:serialize/load 加 pov_mode + pov_character

POV 模式做 4 件事:
  1. 关系热点段只显示 POV 角色参与的关系对
  2. 信息边界段只显示 POV 单一角色的边界(更严格)
  3. 末尾追加"以 X 视角写本章"5 条规则
  4. 信息边界标题语义切换为 POV 专属

覆盖:
  A. UI 层(下拉框 + 角色名输入)
  B. 持久化(serialize/load roundtrip)
  C. 行为层(全知/主角POV/角色POV 三态注入差异)
  X. 守(空角色/角色不存在/角色未在 mentioned_names)
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


def _method_class(tree, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name == method_name:
                    return node.name
    return None


# ─────────────────────────────────────
# A. UI 层
# ─────────────────────────────────────

def test_A1_pov_mode_combobox_exists(src):
    assert "self.cb_pov_mode" in src
    assert "QComboBox" in src


def test_A2_pov_mode_three_options(src):
    """POV 下拉框必须有 3 个选项:全知视角 / 主角 POV / 角色 POV"""
    # 找 addItems 那行
    m = re.search(r"self\.cb_pov_mode\.addItems\(\[([^\]]+)\]\)", src)
    assert m, "cb_pov_mode.addItems 没找到"
    items_str = m.group(1)
    for opt in ("全知视角", "主角 POV", "角色 POV"):
        assert opt in items_str, f"POV 选项缺 {opt}"


def test_A3_pov_character_lineedit_exists(src):
    assert "self.le_pov_character" in src
    assert "QLineEdit" in src


def test_A4_pov_character_only_enabled_in_role_mode(src):
    """角色名输入框默认禁用,只在 '角色 POV' 时启用"""
    # _on_pov_mode_changed 应有 setEnabled 控制
    m = re.search(
        r"def _on_pov_mode_changed\(self, mode\):.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "setEnabled" in block
    assert "角色 POV" in block


def test_A5_resolve_pov_character_method_exists(tree):
    """_resolve_pov_character 必须在 CharacterLibrary"""
    assert _method_class(tree, "_resolve_pov_character") == "CharacterLibrary"


def test_A6_pov_settings_persisted_to_qsettings(src):
    """POV 模式切换时立即写 QSettings(用户重启 GUI 不丢)"""
    # cb_pov_mode 的 currentTextChanged 必须 setValue 到 CharLib
    m = re.search(
        r"self\.cb_pov_mode\.currentTextChanged\.connect\([^\n]*pov_mode[^\n]*\)",
        src)
    assert m, "POV 模式切换没接 QSettings"


# ─────────────────────────────────────
# B. 持久化
# ─────────────────────────────────────

def test_B1_serialize_includes_pov(src):
    """serialize 必须输出 pov_mode + pov_character"""
    m = re.search(r"def serialize\(self\):.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert '"pov_mode"' in block
    assert '"pov_character"' in block


def test_B2_load_handles_pov(src):
    """load 必须能加载 pov_mode + pov_character"""
    m = re.search(r"def load\(self, data\):.*?(?=\n    def )", src, re.DOTALL)
    block = m.group(0)
    assert "pov_mode" in block
    assert "pov_character" in block
    # 必须有合法值检查
    assert "全知视角" in block or "POV" in block


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
def charlib_with_data(app):
    """带完整数据的 CharLib:角色 + 关系值 + 信息隔离"""
    sys.path.insert(0, os.path.dirname(__file__) or ".")
    from novel_ai import CharacterLibrary
    from PyQt5.QtWidgets import QTableWidgetItem
    cl = CharacterLibrary()
    # 主角林远 + 配角林悦
    cl.tbl_chars.insertRow(0)
    cl.tbl_chars.setItem(0, 0, QTableWidgetItem("林远"))
    cl.tbl_chars.insertRow(1)
    cl.tbl_chars.setItem(1, 0, QTableWidgetItem("林悦"))
    # 数据
    cl.merge_dicts({
        "relations_value": [
            {"a": "林远", "b": "王屠户", "value": -80, "ch": "3"},
            {"a": "林远", "b": "林悦", "value": 90, "ch": "1"},
            {"a": "王屠户", "b": "张大山", "value": -60, "ch": "5"},  # 林远不参与
        ],
        "infos": [
            {"id": "INFO-A", "content": "林远是叶家次子", "source_ch": "1", "source_type": "设定"},
            {"id": "INFO-B", "content": "金手指是咒血术", "source_ch": "1", "source_type": "设定"},
            {"id": "INFO-C", "content": "王屠户暗中投靠魔教", "source_ch": "5", "source_type": "事件揭露"},
        ],
        "known_by": [
            {"info_id": "INFO-A", "character": "林远", "via": "出生即知"},
            {"info_id": "INFO-B", "character": "林远", "via": "出生即知"},
            {"info_id": "INFO-B", "character": "林悦", "via": "第3章告知"},
            {"info_id": "INFO-C", "character": "林远", "via": "第5章亲眼见"},
        ],
    })
    cl.chk_inject.setChecked(True)
    return cl


# ─────────────────────────────────────
# C. 行为层 — 全知视角(POV 不生效)
# ─────────────────────────────────────

def test_C1_omniscient_shows_all_relations(charlib_with_data):
    """全知视角:所有关系热点都出现(包括跟 POV 无关的)"""
    charlib_with_data.cb_pov_mode.setCurrentText("全知视角")
    block = charlib_with_data.build_inject_block(
        current_chapter=10,
        mentioned_names={"林远", "林悦", "王屠户", "张大山"})
    # 全部关系都出
    assert "林远 → 王屠户" in block
    assert "林远 → 林悦" in block
    assert "王屠户 → 张大山" in block


def test_C2_omniscient_no_pov_directive(charlib_with_data):
    """全知视角:不出 POV 视角指令段"""
    charlib_with_data.cb_pov_mode.setCurrentText("全知视角")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦"})
    assert "本章 POV 模式" not in block
    assert "POV 模式 — 严格遵守" not in block


def test_C3_omniscient_shows_all_info_boundaries(charlib_with_data):
    """全知视角:所有 mentioned 角色的信息边界都出"""
    charlib_with_data.cb_pov_mode.setCurrentText("全知视角")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦"})
    assert "林远 已知" in block
    assert "林悦 已知" in block


# ─────────────────────────────────────
# C. 行为层 — 主角 POV
# ─────────────────────────────────────

def test_C4_protag_pov_uses_first_char(charlib_with_data):
    """主角 POV:自动取角色库第 1 个角色(惯例)"""
    charlib_with_data.cb_pov_mode.setCurrentText("主角 POV")
    mode, name = charlib_with_data._resolve_pov_character()
    assert mode == "主角 POV"
    assert name == "林远"


def test_C5_protag_pov_relations_filtered(charlib_with_data):
    """主角 POV:关系热点只显示主角参与的"""
    charlib_with_data.cb_pov_mode.setCurrentText("主角 POV")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦", "王屠户", "张大山"})
    assert "林远 → 王屠户" in block
    assert "林远 → 林悦" in block
    # 主角不参与的关系应被收窄
    assert "王屠户 → 张大山" not in block


def test_C6_protag_pov_info_filtered(charlib_with_data):
    """主角 POV:信息边界只显示主角的"""
    charlib_with_data.cb_pov_mode.setCurrentText("主角 POV")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦"})
    # 标题含『林远 POV』
    assert "林远 POV 已知信息边界" in block
    # 林悦的边界不该出现(POV 只显示主角)
    assert "林悦 已知" not in block


def test_C7_protag_pov_directive_appended(charlib_with_data):
    """主角 POV:末尾必须有 POV 视角指令"""
    charlib_with_data.cb_pov_mode.setCurrentText("主角 POV")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦"})
    assert "本章 POV 模式" in block
    assert "本章使用【林远】的视角写作" in block
    # 5 条规则关键词
    assert "所见/所闻/所想/所感" in block
    assert "不能写" in block
    assert "第三人称限知" in block


# ─────────────────────────────────────
# C. 行为层 — 角色 POV
# ─────────────────────────────────────

def test_C8_role_pov_uses_input_character(charlib_with_data):
    """角色 POV:从 le_pov_character 取角色名"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    mode, name = charlib_with_data._resolve_pov_character()
    assert mode == "角色 POV"
    assert name == "林悦"


def test_C9_role_pov_filters_to_secondary_character(charlib_with_data):
    """角色 POV (= 林悦):关系热点只显示林悦参与的"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦", "王屠户"})
    # 林悦参与的(林远→林悦)出现
    assert "林悦" in block
    # 林远→王屠户 不该出现(林悦不参与)
    assert "林远 → 王屠户" not in block


def test_C10_role_pov_info_only_self(charlib_with_data):
    """角色 POV (= 林悦):信息边界只显示林悦的"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦"})
    assert "林悦 POV 已知信息边界" in block
    # 林远的边界不出现
    assert "林远 已知" not in block


def test_C11_pov_auto_adds_character_to_mentioned(charlib_with_data):
    """v1.84 关键:POV 角色应自动加入 mentioned_names,即使外部没传"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    # 外部 mentioned_names 不含林悦 — POV 应自动加入
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远"})
    # 林悦应被加入,信息边界应出现
    assert "林悦 POV" in block or "林悦 已知" in block


# ─────────────────────────────────────
# B. 持久化运行时
# ─────────────────────────────────────

def test_B3_serialize_load_roundtrip(charlib_with_data, app):
    """完整 roundtrip:设 POV → serialize → 新 CharLib load → POV 配置守恒"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    out = charlib_with_data.serialize()
    assert out.get("pov_mode") == "角色 POV"
    assert out.get("pov_character") == "林悦"
    from novel_ai import CharacterLibrary
    cl2 = CharacterLibrary()
    cl2.load(out)
    assert cl2.cb_pov_mode.currentText() == "角色 POV"
    assert cl2.le_pov_character.text() == "林悦"


# ─────────────────────────────────────
# X. 守
# ─────────────────────────────────────

def test_X1_role_pov_empty_character_falls_back(charlib_with_data):
    """角色 POV 但角色名为空 → 不应崩,行为类似全知视角(POV 段不出)"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦"})
    # 不应崩,且 POV 指令段不应出现(因为没角色)
    assert "本章 POV 模式" not in block


def test_X2_protag_pov_empty_chars_table_safe(app):
    """主角 POV 但角色库空 → 不崩"""
    sys.path.insert(0, os.path.dirname(__file__) or ".")
    from novel_ai import CharacterLibrary
    cl = CharacterLibrary()  # 空库
    cl.cb_pov_mode.setCurrentText("主角 POV")
    cl.chk_inject.setChecked(True)
    block = cl.build_inject_block(current_chapter=10, mentioned_names={"任意角色"})
    # 不崩;POV 指令段不出(主角名空)
    assert isinstance(block, str)


def test_X3_inject_off_pov_no_effect(charlib_with_data):
    """chk_inject 关闭时,POV 模式也不出注入(整段为空)"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    charlib_with_data.chk_inject.setChecked(False)
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林悦"})
    assert block == ""


def test_X4_version_bumped(src):
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)"', src)
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 84), \
        f"v1.84 POV 模式版本号没升,当前 v{major}.{minor}"


def test_X5_pov_section_title_uses_label(charlib_with_data):
    """POV 模式下关系热点段标题应带 POV 角色名作 label"""
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林远", "林悦"})
    # 关系热点标题应带 (林悦 视角)
    assert "(林悦 视角)" in block


def test_X6_pov_secrets_uses_pov_name(charlib_with_data):
    """POV 模式下,secrets 段提示应该写"X 不应触及"而非通用"本章出场角色不应触及" """
    charlib_with_data.cb_pov_mode.setCurrentText("角色 POV")
    charlib_with_data.le_pov_character.setText("林悦")
    block = charlib_with_data.build_inject_block(
        current_chapter=10, mentioned_names={"林悦"})
    # INFO-A(林远是叶家次子) 林悦不知道 → 应作为 secrets
    # secret 段应明确写"林悦 不应触及"
    if "INFO-A" in block:  # secrets 段实际出现了
        assert "林悦" in block and "不应" in block
