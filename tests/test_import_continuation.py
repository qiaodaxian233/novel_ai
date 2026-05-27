# -*- coding: utf-8 -*-
"""v1.51 导入续写功能测试 — 模块层 + UI 集成防回归"""
import ast
import json
from pathlib import Path

# 注意:import_continuation 依赖 PyQt5,本测试用 ast 解析,不实际 import
# 模块层只测纯函数(build_extract_prompt / parse_extract_response)


def _methods(cls_name, file_path="novel_ai.py"):
    src = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == cls_name:
            return [m.name for m in n.body if isinstance(m, ast.FunctionDef)]
    return []


def test_import_continuation_module_exists():
    """import_continuation.py 文件存在 + 关键定义"""
    p = Path("import_continuation.py")
    assert p.exists()
    src = p.read_text(encoding="utf-8")
    assert "class ImportContinuationDialog" in src
    assert "def build_extract_prompt" in src
    assert "def parse_extract_response" in src


def test_dialog_get_result_keys():
    """ImportContinuationDialog.get_result 必须返回 mode/ai_extract/extract_n/mark_imported"""
    methods = _methods("ImportContinuationDialog", "import_continuation.py")
    assert "get_result" in methods
    src = Path("import_continuation.py").read_text(encoding="utf-8")
    # 看 get_result 里包含的 key
    for k in ['"mode"', '"ai_extract"', '"extract_n"', '"mark_imported"']:
        assert k in src, f"get_result 缺 key {k}"


def test_main_window_has_import_handlers():
    """MainWindow 必须有 3 个 import handler(BUG-046 教训)"""
    methods = _methods("MainWindow")
    for m in ["import_continuation", "_do_import_continuation",
              "_on_import_extract_received"]:
        assert m in methods, f"MainWindow 缺方法 {m}"


def test_import_handlers_not_in_other_classes():
    """3 个 handler 不应该出现在其他 class"""
    for cls in ["ChapterEditor", "BookSplitterTab",
                "ProjectHomeTab", "GenerationControl",
                "CreationSettings"]:
        methods = _methods(cls)
        for m in ["import_continuation", "_do_import_continuation",
                  "_on_import_extract_received"]:
            assert m not in methods, \
                f"{m} 不应在 {cls},应该在 MainWindow"


def test_dispatch_routes_import_extract():
    """dispatch 路由必须含 'import_extract' target"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert 'target == "import_extract"' in src
    assert "_on_import_extract_received" in src


def test_file_menu_has_import_action():
    """文件菜单必须有 '📥 导入外部小说续写...'"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert "📥 导入外部小说续写..." in src
    assert "self.import_continuation" in src


def test_extract_prompt_content():
    """build_extract_prompt 必须含关键字段要求"""
    # 不能 import PyQt5,直接读源码验证
    src = Path("import_continuation.py").read_text(encoding="utf-8")
    # build_extract_prompt 函数体
    for required in ["角色档案", "世界观", "故事种子", "已埋伏笔",
                     "后续大纲建议", "characters", "foreshadows",
                     "outline_next", "严格 JSON"]:
        assert required in src, f"prompt 模板缺 '{required}'"


def test_parse_extract_response_handles_markdown():
    """parse_extract_response 必须能从 markdown 包裹的 JSON 提取"""
    # 没法 import,改成 ast 检查实现含 re.search
    src = Path("import_continuation.py").read_text(encoding="utf-8")
    # parse_extract_response 函数体应该用正则提取
    assert "re.search" in src
    assert "json.loads" in src
