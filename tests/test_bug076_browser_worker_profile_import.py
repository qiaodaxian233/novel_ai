# -*- coding: utf-8 -*-
"""
test_bug076_browser_worker_profile_import.py — v2.11 BUG-076 修复守护

BUG-076(实战曝光,2026-05-22 14:37):
  ui/browser_worker.py 用了 _profile_for_url 4 次(_dispatch_send / _send_prompt /
  _build_send_xpath / 等),但顶部没 `from core.site_profiles import _profile_for_url`。
  P6 拆分时 AST 抽取脚本漏了这个 module-level 函数,静态测试没触发
  (只在真实派发 prompt 时进入这些代码路径),实战立刻 NameError。

  跟 BUG-074 同根因(P3~P6 模块化拆分留下的隐藏地雷)。

  修法:browser_worker.py 顶部加 `from core.site_profiles import _profile_for_url`

测试策略:
  1. 真实 import ui.browser_worker,确认能从 _profile_for_url 找到符号
  2. 对所有 ui/*.py + ui/tabs/*.py 做"NameError 静态扫描":
     对每个文件抽取所有 module 调用的"裸标识符"(非 self.xxx / 非 import 的),
     验证它们都在该模块的 import / 内置 / 模块定义中存在
     —— 这是 BUG-074/076 的根本治法
"""
import unittest
import ast
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent  # tests/ 的上一级 = 仓库根(测试搬迁修复)
class TestProfileForUrlImportedInBrowserWorker(unittest.TestCase):
    """v2.11 BUG-076 直接验证:_profile_for_url 在 browser_worker.py 里可用"""

    def test_can_import_from_browser_worker(self):
        """ui.browser_worker 必须能找到 _profile_for_url"""
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        # 清掉可能的旧 module cache
        for mod_name in list(sys.modules):
            if mod_name.startswith("ui."):
                del sys.modules[mod_name]
        # 真实 import,如果没补 import 会直接 ImportError
        from ui.browser_worker import _profile_for_url, BrowserWorker
        self.assertTrue(callable(_profile_for_url))
        self.assertIsNotNone(BrowserWorker)

    def test_function_actually_works(self):
        """import 后真实调用一次,确认能返回 profile dict"""
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        from ui.browser_worker import _profile_for_url
        prof = _profile_for_url("https://chat.deepseek.com/")
        self.assertIsInstance(prof, dict)
        self.assertIn("name", prof)  # SITE_PROFILES 项必有 name 字段

    def test_top_level_import_present(self):
        """ui/browser_worker.py 顶部必须有 import _profile_for_url(不能是局部 import)"""
        src = (HERE / "ui" / "browser_worker.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        found = False
        for node in ast.iter_child_nodes(tree):
            # 只看模块顶层(不下钻进函数体)
            if isinstance(node, ast.ImportFrom):
                if node.module == "core.site_profiles":
                    names = [a.name for a in node.names]
                    if "_profile_for_url" in names:
                        found = True
                        break
        self.assertTrue(
            found,
            "ui/browser_worker.py 顶部应有 `from core.site_profiles import _profile_for_url`\n"
            "(BUG-076 修复点 — 否则 _dispatch_send 等运行时 NameError)"
        )


class TestProfileForUrlImportedInAllUsers(unittest.TestCase):
    """v2.11:精准守护 — _profile_for_url 在所有使用方都已 import

    这是 BUG-074 / BUG-076 的根本治法的"精准版":不做雄心勃勃的通用 NameError 巡检
    (那个误报多,comprehension target / 多层作用域 / 动态属性 都要处理,工程量大),
    而是聚焦在"已知会出问题的 module-level 函数"上做点查。

    _profile_for_url 是个被多文件用的 module-level 函数,P6 拆分时漏了一次(BUG-076)。
    本测试扫所有 ui/ 文件,只要用了这个名字就必须在该文件顶层 import。
    """

    @staticmethod
    def _has_top_level_import(src: str, target_name: str) -> bool:
        """模块顶层(不下钻函数体)是否 import 了 target_name"""
        tree = ast.parse(src)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if (a.asname or a.name) == target_name:
                        return True
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if (a.asname or a.name).split(".")[0] == target_name:
                        return True
            elif isinstance(node, ast.Try):
                # try/except 包的 import 也算
                for sub in ast.walk(node):
                    if isinstance(sub, ast.ImportFrom):
                        for a in sub.names:
                            if (a.asname or a.name) == target_name:
                                return True
        return False

    @staticmethod
    def _uses_name(src: str, target_name: str) -> bool:
        """文件里是否调用了 target_name(裸名,非 self.xxx)"""
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == target_name:
                if isinstance(node.ctx, ast.Load):
                    return True
        return False

    def test_profile_for_url_imported_wherever_used(self):
        """ui/ 下所有用了 _profile_for_url 的文件,都必须顶层 import"""
        ui_dir = HERE / "ui"
        if not ui_dir.exists():
            self.skipTest("ui/ 子包不存在")
        files = list(ui_dir.glob("*.py")) + list(ui_dir.glob("tabs/*.py"))
        problems = []
        for fp in files:
            if fp.name == "__init__.py":
                continue
            src = fp.read_text(encoding="utf-8")
            if self._uses_name(src, "_profile_for_url"):
                if not self._has_top_level_import(src, "_profile_for_url"):
                    problems.append(str(fp.relative_to(HERE)))
        self.assertEqual(
            problems, [],
            f"以下文件用了 _profile_for_url 但顶层没 import(BUG-076 风格隐患):\n  "
            + "\n  ".join(problems)
        )


class TestAppVersionBumped(unittest.TestCase):

    def test_at_least_v211(self):
        novel_ai_path = HERE / "novel_ai.py"
        if not novel_ai_path.exists():
            self.skipTest("novel_ai.py 不在")
        src = novel_ai_path.read_text(encoding="utf-8")
        import re
        m = re.search(r'APP_VERSION\s*=\s*["\']v(\d+)\.(\d+)(?:\.\d+)?["\']', src)
        self.assertIsNotNone(m)
        major, minor = int(m.group(1)), int(m.group(2))
        self.assertGreaterEqual((major, minor), (2, 11),
                                f"APP_VERSION 应 ≥ v2.11,实际 v{major}.{minor:02d}")


if __name__ == "__main__":
    unittest.main()
