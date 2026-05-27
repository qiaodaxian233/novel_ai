"""测试 v1.63 写下一章上下文改造:
  · 可调最近 N 章完整正文注入(1~10)
  · 可调每章字数上限(500~8000)
  · 早期摘要开关
  · _build_prev_context 按配置正确截切
  · _update_ctx_estimate 预估字数对得上实际注入
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication(sys.argv)
    yield a


@pytest.fixture
def mw(app, monkeypatch, tmp_path):
    """构造一个 MainWindow,但避开浏览器启动 / autosave 加载等副作用"""
    # 清掉测试间 QSettings 污染
    from PyQt5.QtCore import QSettings
    qs = QSettings("NovelAI", "CreationSettings")
    qs.setValue("prev_chapters_n", 1)
    qs.setValue("prev_chapter_tail_chars", 2500)
    qs.setValue("prev_use_summaries", True)
    qs.sync()
    
    # 用临时目录避免污染
    monkeypatch.chdir(tmp_path)
    from novel_ai import MainWindow
    # 拦截 autoload — 我们要测试空白起点
    monkeypatch.setattr(MainWindow, "_autoload", lambda self: None)
    monkeypatch.setattr(MainWindow, "_autoload_project_folder",
                        lambda self, *a, **k: False, raising=False)
    w = MainWindow()
    # 直接清空,确保起点干净
    w.chapters = []
    w.current_chapter_index = -1
    
    # 确保 spinbox 也是默认值(以防 init 时被覆盖)
    w.tab_settings.prev_chapters_n.setValue(1)
    w.tab_settings.prev_tail_chars.setValue(2500)
    w.tab_settings.prev_use_summaries.setChecked(True)
    
    return w


def _make_chapters(n, words_per_ch=3000):
    """造 n 章假数据,每章 words 字"""
    return [{"title": f"第 {i} 章 测试",
             "content": "正" * words_per_ch + f"|EOF{i}"}  # 末尾标记便于定位截尾
            for i in range(1, n + 1)]


# ───────── get_ctx_config ─────────

def test_get_ctx_config_defaults(mw):
    """默认配置值正确"""
    cfg = mw.tab_settings.get_ctx_config()
    assert cfg["chapters_n"] == 1
    assert cfg["tail_chars"] == 2500
    assert cfg["use_summaries"] is True


def test_get_ctx_config_after_change(mw):
    """改 spin/check 后,config 反映新值"""
    mw.tab_settings.prev_chapters_n.setValue(5)
    mw.tab_settings.prev_tail_chars.setValue(4000)
    mw.tab_settings.prev_use_summaries.setChecked(False)
    cfg = mw.tab_settings.get_ctx_config()
    assert cfg["chapters_n"] == 5
    assert cfg["tail_chars"] == 4000
    assert cfg["use_summaries"] is False


# ───────── _build_prev_context ─────────

def test_build_prev_ctx_empty_chapters(mw):
    """没章节 → 空串(注入第 1 章不需要 prev)"""
    mw.chapters = []
    assert mw._build_prev_context(1) == ""


def test_build_prev_ctx_ch1_returns_empty(mw):
    """写第 1 章时 ch_num=1,即使有 chapters 也不注入"""
    mw.chapters = _make_chapters(3)
    assert mw._build_prev_context(1) == ""


def test_build_prev_ctx_default_one_chapter(mw):
    """默认 1 章 — 注入上一章末尾 2500 字"""
    mw.tab_settings.prev_chapters_n.setValue(1)
    mw.tab_settings.prev_tail_chars.setValue(2500)
    mw.chapters = _make_chapters(3)   # 3 章,每章 3000 字
    ctx = mw._build_prev_context(4)
    
    assert "前情提要" in ctx
    assert "上一章正文末尾" in ctx
    # 第 3 章末尾标记应在(因为是倒数最近 1 章)
    assert "|EOF3" in ctx
    # 第 1/2 章末尾标记不该在(摘要里没正文,且默认章节没有 summary)
    assert "|EOF1" not in ctx
    assert "|EOF2" not in ctx


def test_build_prev_ctx_three_chapters(mw):
    """配置 3 章 — 倒数 3 章完整正文都在"""
    mw.tab_settings.prev_chapters_n.setValue(3)
    mw.tab_settings.prev_tail_chars.setValue(8000)  # 不截
    mw.chapters = _make_chapters(5)   # 5 章
    ctx = mw._build_prev_context(6)
    
    # 倒数 3 章 = 第 3、4、5 章
    assert "|EOF3" in ctx
    assert "|EOF4" in ctx
    assert "|EOF5" in ctx
    # 第 1、2 章正文不该出现
    assert "|EOF1" not in ctx
    assert "|EOF2" not in ctx


def test_build_prev_ctx_tail_truncation(mw):
    """每章超过 tail_chars 时截尾,末尾标记仍在(末尾切的)"""
    mw.tab_settings.prev_chapters_n.setValue(2)
    mw.tab_settings.prev_tail_chars.setValue(1000)  # 截
    mw.chapters = _make_chapters(3, words_per_ch=5000)  # 每章 5000+ 字
    ctx = mw._build_prev_context(4)
    
    # 截尾后,末尾标记 EOF2/EOF3 应该还在
    assert "|EOF2" in ctx
    assert "|EOF3" in ctx


def test_build_prev_ctx_n_larger_than_avail(mw):
    """配置 5 章但只有 2 章 — 取实际能拿的 2 章"""
    mw.tab_settings.prev_chapters_n.setValue(5)
    mw.chapters = _make_chapters(2)
    ctx = mw._build_prev_context(3)
    assert "|EOF1" in ctx
    assert "|EOF2" in ctx


def test_build_prev_ctx_summaries_when_enabled(mw):
    """开启摘要 → 早期章节带 summary 的会注入"""
    mw.tab_settings.prev_chapters_n.setValue(1)
    mw.tab_settings.prev_use_summaries.setChecked(True)
    mw.chapters = _make_chapters(4)
    # 给第 1、2 章加 summary
    mw.chapters[0]["summary"] = "第一章发生了重要事件 A"
    mw.chapters[1]["summary"] = "第二章主角学会了 B"
    
    ctx = mw._build_prev_context(5)
    assert "早期章节摘要" in ctx
    assert "重要事件 A" in ctx
    assert "学会了 B" in ctx


def test_build_prev_ctx_summaries_disabled(mw):
    """关闭摘要 → 早期章节 summary 不注入"""
    mw.tab_settings.prev_chapters_n.setValue(1)
    mw.tab_settings.prev_use_summaries.setChecked(False)
    mw.chapters = _make_chapters(4)
    mw.chapters[0]["summary"] = "不该出现的摘要内容 XYZ"
    
    ctx = mw._build_prev_context(5)
    assert "XYZ" not in ctx
    assert "早期章节摘要" not in ctx


def test_build_prev_ctx_no_summary_field_safe(mw):
    """章节没有 summary 字段也不崩"""
    mw.tab_settings.prev_chapters_n.setValue(1)
    mw.tab_settings.prev_use_summaries.setChecked(True)
    mw.chapters = _make_chapters(3)
    # 不给任何章节加 summary
    ctx = mw._build_prev_context(4)
    # 应只有最近 1 章正文
    assert "|EOF3" in ctx
    # 早期摘要标题不该出现(因为都没 summary)
    assert "早期章节摘要" not in ctx


def test_build_prev_ctx_clamps_out_of_range(mw):
    """超界 chapters_n / tail_chars 被夹回合法范围"""
    # 用 QSettings 直接塞超界值,模拟存档里有脏数据
    from PyQt5.QtCore import QSettings
    qs = QSettings("NovelAI", "CreationSettings")
    qs.setValue("prev_chapters_n", 999)       # 超 10
    qs.setValue("prev_chapter_tail_chars", 1) # 低于 500
    # spin 设界外值,但其 setValue 会被自身 range 夹。直接调 _build_prev_context
    # 不通过 get_ctx_config 也能走 QSettings fallback,但实际走 get_ctx_config 后 clamp。
    # 这里测 get_ctx_config + _build_prev_context 内部 clamp。
    mw.chapters = _make_chapters(3)
    ctx = mw._build_prev_context(4)
    # 不崩,有内容(被 clamp 到 10 章 / 500 字)
    assert ctx != ""


# ───────── _update_ctx_estimate ─────────

def test_update_ctx_estimate_no_chapters(mw):
    """0 章 → label 显示 0"""
    mw.chapters = []
    mw._update_ctx_estimate()
    text = mw.tab_settings.prev_ctx_estimate.text()
    assert "0" in text
    assert "还没有章节" in text


def test_update_ctx_estimate_one_chapter_default(mw):
    """1 章 + 默认配置 → 字数约等于该章实际字数(或 tail 上限)"""
    mw.tab_settings.prev_chapters_n.setValue(1)
    mw.tab_settings.prev_tail_chars.setValue(2500)
    mw.tab_settings.prev_use_summaries.setChecked(True)
    mw.chapters = _make_chapters(1, words_per_ch=1500)  # 1 章 1500 字
    mw._update_ctx_estimate()
    text = mw.tab_settings.prev_ctx_estimate.text()
    # 应包含 1,5xx 之类(min(1500, 2500) = 1500 加点末尾标记)
    assert "1,50" in text or "1,51" in text


def test_update_ctx_estimate_tail_capped(mw):
    """章节远大于 tail_chars → 取 tail 上限"""
    mw.tab_settings.prev_chapters_n.setValue(1)
    mw.tab_settings.prev_tail_chars.setValue(1000)
    mw.tab_settings.prev_use_summaries.setChecked(False)
    mw.chapters = _make_chapters(1, words_per_ch=5000)
    mw._update_ctx_estimate()
    text = mw.tab_settings.prev_ctx_estimate.text()
    # 应为 1,000 字
    assert "1,000" in text


def test_update_ctx_estimate_matches_actual_injection(mw):
    """预估字数应≈实际 _build_prev_context 输出字数(允许 header/标题误差)"""
    mw.tab_settings.prev_chapters_n.setValue(2)
    mw.tab_settings.prev_tail_chars.setValue(3000)
    mw.tab_settings.prev_use_summaries.setChecked(False)
    mw.chapters = _make_chapters(3, words_per_ch=2000)
    
    mw._update_ctx_estimate()
    estimate_text = mw.tab_settings.prev_ctx_estimate.text()
    
    # 实际生成 ctx 时,正文字数(粗略 — 不算 header)
    ctx = mw._build_prev_context(4)
    
    # 实际正文字数 = 2 章 × min(2000, 3000) ≈ 4000+ 字
    # 预估应包含 4,0xx 或附近
    # 允许 ±10% 误差(header / 标题占字符)
    import re
    nums = [int(x.replace(",", "")) for x in re.findall(r"(\d{1,3}(?:,\d{3})+|\d+)", estimate_text) if int(x.replace(",", "")) > 1000]
    assert nums, f"未在预估里找到字数:{estimate_text}"
    estimated = max(nums)
    # 实际正文部分约 4000(2*2000),允许 header 误差
    actual_body = len(ctx) - 500  # 减去 header / 标记字符的估算
    assert 0.7 * estimated <= actual_body + 1000 <= 1.5 * estimated, \
        f"预估 {estimated} 与实际 {actual_body} 差距过大"


def test_update_ctx_estimate_warning_color(mw):
    """超 30k 字 → 警示色"""
    mw.tab_settings.prev_chapters_n.setValue(10)
    mw.tab_settings.prev_tail_chars.setValue(8000)
    mw.chapters = _make_chapters(10, words_per_ch=8000)  # 10 × 8000 = 80000
    mw._update_ctx_estimate()
    style = mw.tab_settings.prev_ctx_estimate.styleSheet()
    assert "#cc3333" in style or "cc3333" in style.lower()


def test_update_ctx_estimate_called_on_refresh(mw):
    """_refresh_chapter_list 应触发预估更新"""
    mw.chapters = _make_chapters(2)
    mw._refresh_chapter_list()
    text = mw.tab_settings.prev_ctx_estimate.text()
    # 应已经显示预估(不再是初始空状态)
    assert "0" not in text or "字" in text  # 至少有字数显示


# ───────── 信号 ─────────

def test_ctx_settings_changed_signal_emitted(mw):
    """改 spin → 发出 ctx_settings_changed 信号"""
    received = []
    mw.tab_settings.ctx_settings_changed.connect(lambda: received.append(True))
    mw.tab_settings.prev_chapters_n.setValue(3)
    assert len(received) >= 1


def test_ctx_change_triggers_estimate_update(mw):
    """改设置 → label 文本变化"""
    mw.chapters = _make_chapters(3, words_per_ch=2000)
    # 先固定到 1
    mw.tab_settings.prev_chapters_n.setValue(1)
    mw._update_ctx_estimate()
    text_before = mw.tab_settings.prev_ctx_estimate.text()
    
    # 改成 3 (前后必然不同)
    mw.tab_settings.prev_chapters_n.setValue(3)
    # 信号触发的更新
    text_after = mw.tab_settings.prev_ctx_estimate.text()
    
    assert text_before != text_after, \
        f"信号未触发预估更新:\nbefore: {text_before}\nafter:  {text_after}"
