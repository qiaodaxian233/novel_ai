# -*- coding: utf-8 -*-
"""
v2.22.3 BUG-084 / BUG-085 守护测试
====================================

**BUG-084**:BUG-082 守卫死循环(3 分 35 秒 200+ 圈)
**BUG-085**:Qwen 思考期 _check_timeout 误报"卡住"
"""
import re
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def _read(path):
    with open(os.path.join(ROOT, path), 'r', encoding='utf-8') as f:
        return f.read()


# ============ BUG-084 ============

def test_bug084_guard_first_at_variable_exists():
    code = _read('ui/browser_worker.py')
    assert '_b082_guard_first_at' in code
    assert re.search(r'_b082_guard_first_at\s*=\s*None', code)


def test_bug084_guard_max_constant():
    code = _read('ui/browser_worker.py')
    m = re.search(r'_B082_GUARD_MAX\s*=\s*(\d+(?:\.\d+)?)', code)
    assert m
    val = float(m.group(1))
    assert 60 <= val <= 120, f"守卫超时 {val}s 应在 60-120 秒区间"


def test_bug084_guard_sleep_constant():
    code = _read('ui/browser_worker.py')
    m = re.search(r'_b082_guard_sleep\s*=\s*(\d+(?:\.\d+)?)', code)
    assert m
    assert float(m.group(1)) >= 1.0


def test_bug084_button_resume_log_silenced():
    code = _read('ui/browser_worker.py')
    assert '_b082_button_resume_log_silenced' in code
    for m in re.finditer(r'log_signal\.emit\([^)]*⏳ 按钮快照已恢复', code):
        pre = code[max(0, m.start() - 200):m.start()]
        assert '_b082_button_resume_log_silenced' in pre


def test_bug084_giveup_label_in_log():
    code = _read('ui/browser_worker.py')
    assert '[BUG-084]' in code
    assert '放弃守卫' in code or '放弃' in code


def test_bug084_guard_timeout_has_break():
    code = _read('ui/browser_worker.py')
    for m in re.finditer(r'\[BUG-084\]', code):
        post = code[m.end():m.end() + 400]
        assert 'break' in post


def test_bug084_guard_reset_on_content_growth():
    code = _read('ui/browser_worker.py')
    matches = re.findall(r'_b082_guard_first_at\s*=\s*None', code)
    assert len(matches) >= 2


# ============ BUG-085 ============

def test_bug085_task_thinking_signal_exists():
    code = _read('ui/browser_worker.py')
    assert re.search(r'task_thinking\s*=\s*pyqtSignal', code)
    m = re.search(r'task_thinking\s*=\s*pyqtSignal\(([^)]+)\)', code)
    assert m
    sig = m.group(1)
    assert 'str' in sig and 'bool' in sig


def test_bug085_main_process_connects_signal():
    code = _read('novel_ai.py')
    assert re.search(
        r'task_thinking\.connect\s*\(\s*self\._on_task_thinking',
        code)


def test_bug085_on_task_thinking_handler_exists():
    code = _read('novel_ai.py')
    assert re.search(r'def\s+_on_task_thinking\s*\(self,\s*task_id,\s*is_thinking',
                     code)


def test_bug085_task_thinking_state_tracked():
    code = _read('novel_ai.py')
    assert '_task_thinking_state' in code


def test_bug085_check_timeout_has_thinking_gate():
    code = _read('novel_ai.py')
    m = re.search(r'def _check_timeout\(\):(.*?)QTimer\.singleShot\(90000,\s*_check_timeout\)',
                  code, re.DOTALL)
    assert m
    body = m.group(1)
    assert '_task_thinking_state' in body
    assert 'QTimer.singleShot' in body


def test_bug085_response_received_clears_thinking_state():
    code = _read('novel_ai.py')
    m = re.search(r'def _on_response_received\(self,[^)]+\):(.*?)def\s+',
                  code, re.DOTALL)
    assert m
    body = m.group(1)
    assert '_task_thinking_state' in body and 'pop' in body


def test_bug085_worker_emits_on_thinking_change():
    code = _read('ui/browser_worker.py')
    assert re.search(r'self\.task_thinking\.emit', code)
    assert '_last_thinking_emitted' in code


def test_bug085_polling_exit_emits_false():
    code = _read('ui/browser_worker.py')
    idx = code.rfind('response_received.emit')
    assert idx > 0
    pre = code[max(0, idx - 600):idx]
    assert 'task_thinking.emit' in pre and 'False' in pre


def test_bug085_version_bumped():
    code = _read('novel_ai.py')
    # v2.22.3 + 起,允许后续 minor/patch 继续升,只要 ≥ v2.22.3
    m = re.search(r'APP_VERSION\s*=\s*["\']v?(\d+)\.(\d+)\.(\d+)', code)
    assert m
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert (major, minor, patch) >= (2, 22, 3), \
        f"APP_VERSION 必须 ≥ v2.22.3,实际 v{major}.{minor}.{patch}"


# ============ 综合 ============

def test_bug084_bug085_no_regression_to_old_buggy_code():
    code = _read('ui/browser_worker.py')
    for m in re.finditer(r'log_signal\.emit\([^)]*⏳ 按钮快照已恢复', code):
        pre = code[max(0, m.start() - 300):m.start()]
        assert '_b082_button_resume_log_silenced' in pre


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
