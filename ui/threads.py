# -*- coding: utf-8 -*-
"""
ui/threads.py - TTS 合成后台线程(v1.10 引入,逐段合成,边出边发信号不阻塞 UI)

v2.02 P3 拆分:从 novel_ai.py 第 442-474 行整体搬运,内容零修改。
被 novel_ai.py 顶部 `from ui.threads import _TTSSynthThread` 导入。
"""

from PyQt5.QtCore import QThread, pyqtSignal

class _TTSSynthThread(QThread):
    """v1.10:TTS 合成后台线程 — 逐段合成,边出边发信号,不阻塞 UI"""
    chunk_ready  = pyqtSignal(int, int, str)   # (idx, total, audio_path)
    chunk_failed = pyqtSignal(int, int, str)   # (idx, total, err_msg)
    finished_all = pyqtSignal()

    def __init__(self, backend, chunks, voice, speed, temp_dir, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.chunks = chunks
        self.voice = voice
        self.speed = speed
        self.temp_dir = temp_dir

    def run(self):
        import os
        total = len(self.chunks)
        for i, text in enumerate(self.chunks):
            if self.isInterruptionRequested():
                return
            # 文件名:序号 + 后端名(EdgeTTS 用 mp3,Index-TTS 一般 wav)
            ext = "mp3" if self.backend.name == "edge_tts" else "wav"
            out_path = os.path.join(self.temp_dir, f"chunk_{i:04d}.{ext}")
            try:
                ok, msg = self.backend.synthesize(
                    text, out_path, voice=self.voice, speed=self.speed)
            except Exception as e:
                ok, msg = False, f"未捕获异常:{type(e).__name__}: {e}"
            if ok and os.path.exists(out_path):
                self.chunk_ready.emit(i, total, out_path)
            else:
                self.chunk_failed.emit(i, total, msg)
        self.finished_all.emit()
