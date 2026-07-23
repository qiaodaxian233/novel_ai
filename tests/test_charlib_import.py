"""测试 CharacterLibrary 的 list-of-dict 导入(v1.63 修复点)

bug 描述:
  v1.62 及之前,CharacterLibrary.load() 只认 list-of-list 格式,
  但 _merge_into_charlib (MainWindow) 和外部 AI 提取工具(DeepSeek/ChatGPT
  按 PROMPTS['world_extract'] 模板回的)都是 list-of-dict 格式。
  导致用户从 deepseek 拿到 6 库 JSON 后,『导入库』按钮形同虚设。

修法:
  1. load() 自动探测每项是 dict 还是 list,dict 按字段名映射到列
  2. 新增 merge_dicts() — 追加去重的导入路径
  3. _import_lib() 问用户『覆盖』还是『追加』
"""

import json
import os
import sys

import pytest

# 必要的 Qt 环境
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PyQt5 = pytest.importorskip("PyQt5", reason="PyQt5 not available")
from PyQt5.QtWidgets import QApplication

# 单例 QApplication
@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication(sys.argv)
    yield a


@pytest.fixture
def charlib(app):
    """构造一个干净的 CharacterLibrary 实例"""
    from novel_ai import CharacterLibrary
    return CharacterLibrary()


# 用户实际从 DeepSeek 拿到的 schema(list-of-dict)
DEEPSEEK_SAMPLE = {
    "characters": [
        {
            "name": "陆明", "role": "主角",
            "appearance": "年轻苍白", "personality": "慵懒",
            "mark": "破工作没五险一金", "ability": "符箓风水",
            "state": "化为法则奇点", "first_ch": "1"
        },
        {
            "name": "卫元", "role": "配角",
            "appearance": "青年道士", "personality": "稳重",
            "mark": "庄老哥时代变了", "ability": "道门术法",
            "state": "守夜人联盟核心", "first_ch": "3"
        },
    ],
    "relations": [
        {"a": "陆明", "type": "盟友", "b": "卫元", "note": "特事局联络人"},
        {"a": "陆明", "type": "宿敌", "b": "李芥末", "note": "末日教团"},
    ],
    "items": [
        {"name": "调色刀", "type": "法器", "owner": "沈烬",
         "source_ch": "29", "ability": "用灵魂作画"},
    ],
    "events": [
        {"ch": "1", "event": "陆明出场", "state_change": "开启天命"},
    ],
    "foreshadows": [
        {"ch": "1", "content": "金色符文流转", "plan_pay_at": "30"},
    ],
}


# ─────── load() 测试 ───────

def test_load_accepts_dict_format(charlib):
    """关键修复:list-of-dict 进 load() 不再崩,字段映射到正确列"""
    charlib.load(DEEPSEEK_SAMPLE)
    
    # 角色表:2 行,字段映射正确
    assert charlib.tbl_chars.rowCount() == 2
    assert charlib.tbl_chars.item(0, 0).text() == "陆明"           # 姓名
    assert charlib.tbl_chars.item(0, 1).text() == "主角"           # 角色定位
    assert charlib.tbl_chars.item(0, 2).text() == "年轻苍白"        # 外貌
    assert charlib.tbl_chars.item(0, 7).text() == "1"             # 首次出场
    assert charlib.tbl_chars.item(1, 0).text() == "卫元"


def test_load_accepts_dict_format_relations(charlib):
    charlib.load(DEEPSEEK_SAMPLE)
    assert charlib.tbl_relations.rowCount() == 2
    assert charlib.tbl_relations.item(0, 0).text() == "陆明"
    assert charlib.tbl_relations.item(0, 1).text() == "盟友"
    assert charlib.tbl_relations.item(0, 2).text() == "卫元"


def test_load_accepts_dict_format_items_events_foreshadows(charlib):
    charlib.load(DEEPSEEK_SAMPLE)
    
    assert charlib.tbl_items.rowCount() == 1
    assert charlib.tbl_items.item(0, 0).text() == "调色刀"
    assert charlib.tbl_items.item(0, 2).text() == "沈烬"
    
    # events → timeline(同义容忍)
    assert charlib.tbl_timeline.rowCount() == 1
    assert charlib.tbl_timeline.item(0, 1).text() == "陆明出场"
    
    assert charlib.tbl_fore.rowCount() == 1
    assert charlib.tbl_fore.item(0, 1).text() == "金色符文流转"


def test_load_still_accepts_old_list_format(charlib):
    """老 list-of-list 格式必须不破(原 serialize 输出)"""
    old_data = {
        "characters": [["林远", "主角", "年轻", "倔强", "我命由我",
                       "咒血者", "练气", "1"]],
        "relations": [["林远", "兄妹", "林悦", "妹妹"]],
    }
    charlib.load(old_data)
    assert charlib.tbl_chars.rowCount() == 1
    assert charlib.tbl_chars.item(0, 0).text() == "林远"
    assert charlib.tbl_chars.item(0, 5).text() == "咒血者"
    assert charlib.tbl_relations.rowCount() == 1
    assert charlib.tbl_relations.item(0, 1).text() == "兄妹"


def test_load_empty_dict_safe(charlib):
    """空 dict 不崩"""
    charlib.load({})
    assert charlib.tbl_chars.rowCount() == 0


def test_load_timeline_fallback_to_events_key(charlib):
    """外部 JSON 用 events 字段时也能落到 timeline 表"""
    charlib.load({"events": [{"ch": "5", "event": "破境",
                              "state_change": "金丹一层"}]})
    assert charlib.tbl_timeline.rowCount() == 1
    assert charlib.tbl_timeline.item(0, 0).text() == "5"
    assert charlib.tbl_timeline.item(0, 1).text() == "破境"


# ─────── merge_dicts() 测试 ───────

def test_merge_dicts_returns_counts(charlib):
    added = charlib.merge_dicts(DEEPSEEK_SAMPLE)
    # v1.74:added 字典从 5 字段扩到 6(加 pw)。用子集断言而不是完全相等。
    assert {"ch": 2, "rel": 2, "it": 1, "ev": 1, "fo": 1}.items() <= added.items()


def test_merge_dicts_deduplicates_by_name(charlib):
    """重复角色按 name 去重"""
    charlib.merge_dicts(DEEPSEEK_SAMPLE)
    added2 = charlib.merge_dicts(DEEPSEEK_SAMPLE)  # 再来一次
    assert added2["ch"] == 0   # 全部重名,0 新增
    assert charlib.tbl_chars.rowCount() == 2


def test_merge_dicts_preserves_existing(charlib):
    """merge 不能清空原有数据"""
    # 先加一个手填角色
    charlib._add_character()
    charlib.tbl_chars.item(0, 0).setText("林远")
    
    charlib.merge_dicts(DEEPSEEK_SAMPLE)
    
    # 林远 + 陆明 + 卫元 = 3
    names = {charlib.tbl_chars.item(r, 0).text()
             for r in range(charlib.tbl_chars.rowCount())}
    assert "林远" in names
    assert "陆明" in names
    assert "卫元" in names


def test_merge_dicts_empty_safe(charlib):
    added = charlib.merge_dicts({})
    # v1.74:added 字典从 5 字段扩到 6(加 pw)。检查所有值都是 0。
    assert all(v == 0 for v in added.values())
    assert {"ch", "rel", "it", "ev", "fo"} <= set(added.keys())


# ─────── 真实用户上传文件 ───────

def test_load_real_deepseek_19_chars(charlib):
    """如果上传的真实 JSON 在测试目录里,验证它能完整加载"""
    fixture = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "test_fixtures", "deepseek_19chars.json")
    if not os.path.exists(fixture):
        pytest.skip("真实样本未提供")
    data = json.load(open(fixture, encoding="utf-8"))
    charlib.load(data)
    assert charlib.tbl_chars.rowCount() == 19
    assert charlib.tbl_relations.rowCount() == 16
    assert charlib.tbl_items.rowCount() == 5
    assert charlib.tbl_timeline.rowCount() == 8
    assert charlib.tbl_fore.rowCount() == 7


# ─────── 章节范围 / Prompt 拼装(v1.63 新增功能)───────

def _sample_chapters(n):
    """造 n 章假数据"""
    return [{"title": f"第 {i} 章 测试", "content": f"这是第 {i} 章的内容。" * 3}
            for i in range(1, n + 1)]


def test_chapters_to_body_all(charlib):
    """不指定范围 → 全部章节"""
    body = charlib._chapters_to_body(_sample_chapters(5))
    # 5 章都在
    for i in range(1, 6):
        assert f"第 {i} 章 测试" in body


def test_chapters_to_body_range(charlib):
    """指定 1-based 闭区间"""
    chapters = _sample_chapters(10)
    body = charlib._chapters_to_body(chapters, start_idx=3, end_idx=5)
    # 3/4/5 在,2/6 不在
    assert "第 3 章 测试" in body
    assert "第 5 章 测试" in body
    assert "第 2 章 测试" not in body
    assert "第 6 章 测试" not in body


def test_chapters_to_body_recent_n(charlib):
    """最近 N 章 = (total-N+1, total) 区间"""
    chapters = _sample_chapters(20)
    # 最近 3 章 → 18,19,20
    body = charlib._chapters_to_body(chapters, start_idx=18, end_idx=20)
    assert "第 18 章 测试" in body
    assert "第 20 章 测试" in body
    assert "第 17 章 测试" not in body


def test_chapters_to_body_out_of_range_clamp(charlib):
    """边界 clamp:end > total / start < 1 自动夹"""
    chapters = _sample_chapters(5)
    body = charlib._chapters_to_body(chapters, start_idx=-100, end_idx=999)
    for i in range(1, 6):
        assert f"第 {i} 章 测试" in body


def test_chapters_to_body_start_gt_end(charlib):
    """start > end → 空串"""
    body = charlib._chapters_to_body(_sample_chapters(5), start_idx=4, end_idx=2)
    assert body == ""


def test_chapters_to_body_empty_chapters(charlib):
    """空列表 → 空串"""
    assert charlib._chapters_to_body([]) == ""
    assert charlib._chapters_to_body(None) == ""


def test_chapters_to_body_skips_empty_content(charlib):
    """跳过 content 为空的章节"""
    chapters = [
        {"title": "第 1 章", "content": "实际内容"},
        {"title": "第 2 章", "content": ""},    # 跳过
        {"title": "第 3 章", "content": "另一些内容"},
    ]
    body = charlib._chapters_to_body(chapters)
    assert "第 1 章" in body
    assert "第 3 章" in body
    assert "第 2 章" not in body


def test_build_extract_prompt_with_body(charlib):
    """有正文时 — 占位符被替换,模板各关键标记仍在"""
    prompt = charlib._build_extract_prompt("第 1 章 内容\n\n第 2 章 内容")
    assert "第 1 章 内容" in prompt
    assert "第 2 章 内容" in prompt
    assert "在这里粘贴" not in prompt           # 占位符已被替换
    assert "characters" in prompt              # JSON schema 在
    assert "提取规则" in prompt
    assert "==================== 小说正文 ====================" in prompt


def test_build_extract_prompt_empty_body(charlib):
    """空正文 → 保留中文占位符"""
    prompt = charlib._build_extract_prompt("")
    assert "在这里粘贴" in prompt


def test_build_extract_prompt_is_valid_template(charlib):
    """prompt 自身不能含未替换的格式占位符,导致 AI 端意外"""
    prompt = charlib._build_extract_prompt("test body")
    # 不能有未处理的 {body} 之类
    assert "{body}" not in prompt
    # JSON 示例内的花括号是合法的(不是 .format 占位符)
    assert "{" in prompt and "}" in prompt  # 但 JSON 模板的 {} 在
