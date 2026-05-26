"""
test_bug083_stuck_alert_zero_byte.py — BUG-083 守护测试

v2.22.2 BUG-083:卡死提醒从"纯时间触发"改为"0字节卡 90 秒才报警"
  旧逻辑(novel_ai.py 1786 行 `_check_timeout`):
    QTimer.singleShot(90000, _check_timeout)
    if _task_label in self._pending_task_targets:
        弹窗 + TTS
  问题:Qwen 写章节本来就要 4-5 分钟,90 秒任务远没完成,每次都误报。

  新逻辑:
    worker 加 task_progress = pyqtSignal(str, int) 信号
    polling 抓到内容时 emit (task_id, char_count)
    主进程 _on_task_progress 更新 _task_char_progress dict
    _check_timeout 检查字符数:> 0 静默,== 0 才报警

本套测试守护:
  - worker 有 task_progress 信号
  - polling 循环里至少 emit 一次 task_progress
  - 主进程连了这个信号到 _on_task_progress
  - _check_timeout 里有 0 字节判定(char_progress > 0 → return)
  - 任务完成时清掉 _task_char_progress entry
  - APP_VERSION >= v2.22.2
"""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent
WORKER_FILE = REPO / "ui" / "browser_worker.py"
MAIN_FILE = REPO / "novel_ai.py"


def test_worker_has_task_progress_signal():
    """worker 必须有 task_progress = pyqtSignal(str, int) 信号"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    # grep 模式
    assert "task_progress" in src, "BUG-083: worker 必须有 task_progress 信号"
    assert "task_progress = pyqtSignal(str, int)" in src, \
        "BUG-083: task_progress 必须是 pyqtSignal(str, int) — task_id + char_count"


def test_worker_emits_task_progress_in_polling():
    """worker polling 循环里至少 emit 一次 task_progress"""
    src = WORKER_FILE.read_text(encoding="utf-8")
    # 至少出现 emit 调用 2 次(内容变化时 + 5秒同步)
    count = src.count("self.task_progress.emit(")
    assert count >= 2, \
        f"BUG-083: worker polling 必须 emit task_progress 至少 2 次," \
        f"实际 {count} 次"


def test_main_connects_task_progress():
    """主进程必须把 task_progress 连到 _on_task_progress"""
    src = MAIN_FILE.read_text(encoding="utf-8")
    assert "task_progress.connect" in src, \
        "BUG-083: 主进程必须 connect worker.task_progress"
    assert "_on_task_progress" in src, \
        "BUG-083: 主进程必须有 _on_task_progress slot"


def test_main_has_on_task_progress_method():
    """_on_task_progress 必须是个方法,接受 (task_id, char_count) 参数"""
    src = MAIN_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_task_progress":
            found = True
            args = [a.arg for a in node.args.args]
            assert "task_id" in args, "BUG-083: _on_task_progress 必须有 task_id 参数"
            assert "char_count" in args, "BUG-083: _on_task_progress 必须有 char_count 参数"
            break
    assert found, "BUG-083: 必须有 _on_task_progress 方法"


def test_check_timeout_has_zero_byte_check():
    """_check_timeout 必须查 _task_char_progress,且字符数 > 0 时 return(静默)"""
    src = MAIN_FILE.read_text(encoding="utf-8")
    # 检查 _check_timeout 函数体里有 _task_char_progress 引用
    # 简化:全文 grep 即可
    assert "_task_char_progress" in src, \
        "BUG-083: 主进程必须有 _task_char_progress dict 跟踪每个任务的字符进度"
    # _check_timeout 必须有 'char_progress > 0' 类型的判定
    # 找 _check_timeout 函数定义
    m = re.search(r"def _check_timeout\(\):(.+?)(?=\n        from PyQt5|\Z)",
                  src, re.DOTALL)
    assert m, "BUG-083: 找不到 _check_timeout 函数体"
    body = m.group(1)
    assert "_task_char_progress" in body, \
        "BUG-083: _check_timeout 必须查 _task_char_progress"
    assert "char_progress > 0" in body or "char_progress >= 1" in body, \
        "BUG-083: _check_timeout 必须有 'char_progress > 0 → return' 判定"


def test_progress_dict_cleaned_on_response():
    """任务完成时(_on_response_received)必须清掉 _task_char_progress entry"""
    src = MAIN_FILE.read_text(encoding="utf-8")
    # _on_response_received 函数体里必须有 _task_char_progress.pop(task_id, None)
    m = re.search(r"def _on_response_received\(self.+?\):(.+?)(?=\n    def )",
                  src, re.DOTALL)
    assert m, "找不到 _on_response_received 方法"
    body = m.group(1)
    assert "_task_char_progress" in body, \
        "BUG-083: _on_response_received 必须清理 _task_char_progress(防止内存泄漏)"
    assert ".pop(task_id" in body or "del self._task_char_progress" in body, \
        "BUG-083: 必须 pop 或 del 当前 task_id 的进度记录"


def test_check_timeout_message_changed():
    """_check_timeout 报警文案必须明确说"0 字节"(跟旧"已等待90秒未回复"区分)"""
    src = MAIN_FILE.read_text(encoding="utf-8")
    # 旧文案:已等待90秒未回复
    # 新文案:已等待 90 秒,0 字节无回复
    assert "0 字节" in src or "0字节" in src, \
        "BUG-083: 报警文案必须包含 '0 字节',说明只有真卡死才报警"


def test_app_version_at_least_v2_22_2():
    """APP_VERSION 必须 ≥ v2.22.2"""
    src = MAIN_FILE.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']v?(\d+)\.(\d+)\.(\d+)["\']', src)
    assert m, "找不到 APP_VERSION 定义"
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert (major, minor, patch) >= (2, 22, 2), \
        f"BUG-083: APP_VERSION 必须 ≥ v2.22.2,实际 v{major}.{minor}.{patch}"


def test_bug083_markers_in_both_files():
    """两个文件都必须有 BUG-083 标识(便于未来 grep)"""
    worker_src = WORKER_FILE.read_text(encoding="utf-8")
    main_src = MAIN_FILE.read_text(encoding="utf-8")
    assert worker_src.count("BUG-083") >= 2, \
        "BUG-083: worker 必须有至少 2 处 BUG-083 标识(signal 定义 + polling emit)"
    assert main_src.count("BUG-083") >= 2, \
        "BUG-083: 主进程必须有至少 2 处 BUG-083 标识(signal 连接/handler + _check_timeout)"


if __name__ == "__main__":
    import sys
    tests = [
        ("test_worker_has_task_progress_signal", test_worker_has_task_progress_signal),
        ("test_worker_emits_task_progress_in_polling",
         test_worker_emits_task_progress_in_polling),
        ("test_main_connects_task_progress", test_main_connects_task_progress),
        ("test_main_has_on_task_progress_method", test_main_has_on_task_progress_method),
        ("test_check_timeout_has_zero_byte_check", test_check_timeout_has_zero_byte_check),
        ("test_progress_dict_cleaned_on_response", test_progress_dict_cleaned_on_response),
        ("test_check_timeout_message_changed", test_check_timeout_message_changed),
        ("test_app_version_at_least_v2_22_2", test_app_version_at_least_v2_22_2),
        ("test_bug083_markers_in_both_files", test_bug083_markers_in_both_files),
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"✓ {name}")
        except AssertionError as e:
            print(f"✗ {name}\n   {e}")
            failed.append(name)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
