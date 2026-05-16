"""
回归测试:确保几个关键一致性不再被破坏。

测试目标:
  1. workflow_pipeline._parse_score 支持 JSON 格式
  2. README 与 requirements 一致(Selenium 不能 Playwright)
  3. 测试文件不能再硬编码 /home/claude
  4. license_guard 用了 requests 时,requirements 必须含 requests

跑法:
  python -m unittest test_regression_consistency
  或:python test_regression_consistency.py
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent


class TestParseScore(unittest.TestCase):
    """BUG-003 回归:_parse_score 必须能解析 JSON,不再只识别 8/10。"""

    @classmethod
    def setUpClass(cls):
        # workflow_pipeline 需要 PyQt5,这里用静态抽取的方式跑 _parse_score
        src = (ROOT / "workflow_pipeline.py").read_text(encoding="utf-8")
        m = re.search(
            r'@staticmethod\s*\n\s+def _parse_score\(text: str\):.*?(?=\n    @|\n\nclass )',
            src, re.DOTALL)
        if not m:
            raise unittest.SkipTest("_parse_score 没找到")
        fn_code = m.group(0).replace("@staticmethod\n", "").replace(
            "    def _parse_score", "def _parse_score")
        # 减一级缩进
        lines = fn_code.split('\n')
        out = [lines[0]]
        for l in lines[1:]:
            if l.startswith('        '):
                out.append(l[4:])
            elif l.startswith('    '):
                out.append(l[4:])
            else:
                out.append(l)
        ns = {'re': re}
        exec('\n'.join(out), ns)
        cls.parse = staticmethod(ns['_parse_score'])

    def test_json_simple(self):
        score, reason = self.parse('{"score":8,"reason":"OK"}')
        self.assertEqual(score, 8.0)
        self.assertEqual(reason, "OK")

    def test_json_with_chinese_reason(self):
        score, reason = self.parse('{"score":7.5,"reason":"节奏顺畅"}')
        self.assertEqual(score, 7.5)
        self.assertEqual(reason, "节奏顺畅")

    def test_json_in_markdown_block(self):
        score, reason = self.parse('```json\n{"score":9,"reason":"好"}\n```')
        self.assertEqual(score, 9.0)
        self.assertEqual(reason, "好")

    def test_legacy_slash_format(self):
        score, reason = self.parse('8/10,节奏不错')
        self.assertEqual(score, 8.0)
        self.assertIn("节奏", reason)

    def test_legacy_with_spaces(self):
        score, _ = self.parse('评分 7 / 10')
        self.assertEqual(score, 7.0)

    def test_fallback_unknown_format(self):
        score, reason = self.parse('一些不带格式的文本')
        self.assertEqual(score, 5.0)
        self.assertIn("文本", reason)


class TestReadmeConsistency(unittest.TestCase):
    """BUG-001/002 回归:README 不能再引用 Playwright 当依赖。"""

    def test_no_playwright_install(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        if "selenium" in req.lower():
            self.assertNotIn(
                "playwright install", readme.lower(),
                "README 还在叫用户装 Playwright,但 requirements 是 Selenium")
            self.assertNotIn(
                "pip install playwright", readme.lower(),
                "README 还在叫用户装 Playwright,但 requirements 是 Selenium")


class TestNoHardcodedHomePath(unittest.TestCase):
    """BUG-010 回归:测试文件不能再硬编码 /home/claude。"""

    def test_no_hardcoded_home_claude(self):
        offenders = []
        # 跳过测试自身(它的代码里包含目标字符串作为字面量,会被自己扫到)
        SELF = Path(__file__).name
        for path in ROOT.glob("test_*.py"):
            if path.name == SELF:
                continue
            text = path.read_text(encoding="utf-8")
            for ln_idx, line in enumerate(text.split("\n"), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                # 找真正的 sys.path.insert(..., "/home/claude")
                if "sys.path.insert" in stripped and "/home/claude" in stripped:
                    offenders.append(f"{path.name}:{ln_idx}")
                # 找硬编码 importlib 路径
                if "spec_from_file_location" in stripped and "/home/claude" in stripped:
                    offenders.append(f"{path.name}:{ln_idx}")
        self.assertEqual(
            offenders, [],
            f"以下测试文件仍硬编码 /home/claude:{offenders}")


class TestRequirementsHasRequestsIfUsed(unittest.TestCase):
    """BUG-009 回归:license_guard 用了 requests 就必须在 requirements 里有。"""

    def test_requests_listed_if_imported(self):
        license_path = ROOT / "license_guard.py"
        if not license_path.exists():
            self.skipTest("license_guard.py 不存在")
        license_text = license_path.read_text(encoding="utf-8")
        req_text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        if "import requests" in license_text:
            self.assertIn(
                "requests", req_text,
                "license_guard.py 用了 requests,但 requirements.txt 里没有")


if __name__ == "__main__":
    unittest.main(verbosity=2)
