# -*- coding: utf-8 -*-
"""v2.26.0 本地模型通道 守护测试

核心风险点:
1. SSE 流式解析错/思考块没剥掉 → 起一个 mock OpenAI 服务,端到端真跑
2. 连接失败必须发空响应(触发上游 0字节重试),而不是卡死或抛异常杀线程
3. 三处 send_prompt 路由漏一处 → 源码文本断言
"""
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    return io.open(ROOT / rel, encoding="utf-8").read()


# ---------- mock OpenAI 兼容服务 ----------

class _MockHandler(BaseHTTPRequestHandler):
    """极简 /v1/chat/completions SSE:回三个 delta,含 <think> 块"""
    chunks = ["<think>推理过程", "不该外泄</think>", "第一章 ", "刀口贴上脖子。"]

    def do_POST(self):
        body = json.loads(self.rfile.read(
            int(self.headers.get("Content-Length", 0))))
        assert body.get("stream") is True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in self.chunks:
            payload = {"choices": [{"delta": {"content": c}}]}
            self.wfile.write(
                f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                .encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *a):        # 静音
        pass


def _start_mock():
    srv = HTTPServer(("127.0.0.1", 0), _MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _run_worker_task(task, timeout=10):
    """起 worker → 投任务 → 等 response_received → 干净关停"""
    from PyQt5.QtWidgets import QApplication
    global _APP
    _APP = QApplication.instance() or QApplication([])
    from local_llm_backend import LocalLLMWorker
    w = LocalLLMWorker()
    got, logs = [], []
    w.response_received.connect(lambda tid, txt: got.append((tid, txt)))
    w.log_signal.connect(lambda m, lv: logs.append((lv, m)))
    w.start()
    w.submit(task)
    deadline = time.time() + timeout
    while not got and time.time() < deadline:
        _APP.processEvents()
        time.sleep(0.05)
    w.shutdown()
    w.wait(3000)
    return got, logs


_APP = None   # QApplication 引用必须持有,否则 QObject 相关会被 GC


# ---------- 1. 端到端(真跑) ----------

def test_streaming_end_to_end_and_think_stripped():
    srv, base = _start_mock()
    try:
        got, _ = _run_worker_task({
            "action": "send_prompt", "prompt": "写一章",
            "task_id": "章节-第1章", "base_url": base, "model": "qwen3:14b",
        })
    finally:
        srv.shutdown()
    assert got, "10 秒内没收到 response_received"
    tid, txt = got[0]
    assert tid == "章节-第1章"
    assert txt == "第一章 刀口贴上脖子。"        # delta 正确拼接
    assert "<think>" not in txt and "推理过程" not in txt   # 思考块剥净


def test_base_url_with_v1_suffix_tolerated():
    """用户把 URL 填成 …/v1 也要能用(不能拼成 /v1/v1)"""
    srv, base = _start_mock()
    try:
        got, _ = _run_worker_task({
            "action": "send_prompt", "prompt": "x",
            "task_id": "t", "base_url": base + "/v1", "model": "m",
        })
    finally:
        srv.shutdown()
    assert got and got[0][1].startswith("第一章")


def test_connection_refused_emits_empty_response():
    """服务没启动:必须 emit 空响应触发上游 0字节重试,且给出可读错误日志"""
    got, logs = _run_worker_task({
        "action": "send_prompt", "prompt": "x",
        "task_id": "t2", "base_url": "http://127.0.0.1:1", "model": "m",
    })
    assert got and got[0] == ("t2", "")
    assert any("连不上" in m for _, m in logs)


# ---------- 2. 接线端(源码文本断言) ----------

def test_send_prompt_all_three_sites_routed():
    src = _read("novel_ai.py")
    # 主入口:路由判定 + 分流
    assert "_local_route" in src
    assert "self.local_worker.submit(_task_payload)" in src
    # 0字节重试沿用原路由
    assert "self.local_worker.submit(_p0)" in src
    # 死磕重写沿用原路由
    assert "self.local_worker.submit(_pr)" in src
    # 路由记忆写进 pending meta
    assert '"_route"' in src and '"_local_base"' in src
    # 本地路由放行浏览器前置检查
    assert "not _local_route and not SELENIUM_AVAILABLE" in src
    assert "not _local_route and not self.worker.is_ready()" in src
    # worker 创建/接线/退出清理
    assert "self.local_worker = LocalLLMWorker()" in src
    assert "self.local_worker.response_received.connect(self._on_response_received)" in src
    assert "self.local_worker.shutdown()" in src


def test_constants_and_ui():
    assert "本地模型(Ollama)" in _read("core/constants.py")
    src = _read("ui/tabs/generation_control.py")
    assert "local_model_input" in src
    assert '"local.model"' in src        # 持久化
