# -*- coding: utf-8 -*-
"""
local_llm_backend.py — 本地模型通道(v2.26.0)

目的:让软件绕开浏览器,直连本机(或局域网)的 OpenAI 兼容推理服务
(Ollama / LM Studio / vLLM 等),用于:
  1. 提示词绝对不出本机(彻底堵死"AI 网站聊天记录"泄露通道)
  2. 零成本无限量生成
  3. 接入自训 LoRA 模型

设计原则:对主程序伪装成另一个 BrowserWorker——
  · submit({"action": "send_prompt", "prompt", "task_id", ...}) 同款任务口
  · log_signal / response_received / task_progress 三个信号签名与
    BrowserWorker 完全一致,下游(质检/稽核/死磕/超时看门狗)零改动复用

协议:POST {base}/v1/chat/completions, stream=True, SSE 逐行解析。
Ollama 默认地址 http://127.0.0.1:11434 ,LM Studio 默认 :1234 。

线程纪律:本 worker 独占 HTTP 会话,主线程只 submit,不直接调用。
"""
import json
import queue
import re
import time

from PyQt5.QtCore import QThread, pyqtSignal

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:          # pragma: no cover
    REQUESTS_AVAILABLE = False

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:14b"

# 思考型模型(qwen3/deepseek-r1 本地版)会输出 <think>…</think> 推理块,
# 必须剥掉:章节正文混入思考会污染入库,JSON 稽核混入思考会解析失败
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


class LocalLLMWorker(QThread):
    """本地模型任务线程:队列驱动,信号签名对齐 BrowserWorker"""
    log_signal = pyqtSignal(str, str)            # message, level
    response_received = pyqtSignal(str, str)     # task_id, content
    task_progress = pyqtSignal(str, int)         # task_id, current_char_count

    def __init__(self):
        super().__init__()
        self.task_queue = queue.Queue()
        self._running = True

    # ---------- 主线程调用 ----------
    def submit(self, task: dict):
        self.task_queue.put(task)

    def shutdown(self):
        self._running = False
        self.task_queue.put(None)      # 唤醒阻塞的 get

    # ---------- 线程内部 ----------
    def run(self):
        while self._running:
            try:
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if task is None:
                continue
            try:
                if task.get("action") == "send_prompt":
                    self._send(task)
            except Exception as e:            # 兜底:任何异常不能杀线程
                self.log_signal.emit(f"本地模型任务异常:{e}", "error")
                self.response_received.emit(task.get("task_id", ""), "")

    def _send(self, task: dict):
        tid = task.get("task_id", "")
        prompt = task.get("prompt", "")
        model = (task.get("model") or "").strip() or DEFAULT_MODEL
        base = (task.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = base + "/v1/chat/completions"

        if not REQUESTS_AVAILABLE:
            self.log_signal.emit("缺少 requests 库,无法使用本地模型", "error")
            self.response_received.emit(tid, "")
            return

        self.log_signal.emit(
            f"🖥️ 本地模型请求:{model} ({len(prompt)} 字符)", "info")
        text = ""
        try:
            with requests.post(
                url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
                stream=True,
                timeout=(5, 900),   # 连接 5s;生成最长 15 分钟(本地大模型慢)
            ) as resp:
                resp.raise_for_status()
                # 关键:SSE 响应头常不带 charset,requests 会退到 ISO-8859-1
                # 把中文解成乱码 — 必须强制 UTF-8(实测踩坑,守护测试覆盖)
                resp.encoding = "utf-8"
                last_emit = time.time()
                for line in resp.iter_lines(decode_unicode=True):
                    if not self._running:
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = (json.loads(data)["choices"][0]
                                 .get("delta", {}).get("content") or "")
                    except Exception:
                        continue
                    text += delta
                    now = time.time()
                    if now - last_emit >= 1.0:   # 喂超时看门狗(BUG-083)
                        last_emit = now
                        self.task_progress.emit(tid, len(text))
        except Exception as e:
            if REQUESTS_AVAILABLE and isinstance(
                    e, requests.exceptions.ConnectionError):
                self.log_signal.emit(
                    f"本地模型连不上({base}):\n"
                    "  确认 Ollama 已启动(命令行跑 ollama serve 或打开客户端),\n"
                    "  且『URL』填的是服务地址,如 http://127.0.0.1:11434", "error")
            else:
                self.log_signal.emit(f"本地模型请求失败:{e}", "error")
            # 已流出的部分照常走后面的剥思考+emit,质检不过会自动死磕

        text = _THINK_RE.sub("", text).strip()
        self.log_signal.emit(
            f"🖥️ 本地模型完成:{tid} ({len(text)} 字符)", "info")
        self.response_received.emit(tid, text)
