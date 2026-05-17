# -*- coding: utf-8 -*-
"""
tts_backend.py · v1.10 — TTS 后端抽象层
─────────────────────────────────────────────
统一接口,目前支持:
  - EdgeTTSBackend:微软在线 TTS,免费 / 不要 GPU / 不要 Index-TTS
  - IndexTTSBackend:用户本地 Index-TTS Gradio 服务(默认 http://127.0.0.1:7862)
  - DisabledBackend:不发声(关闭)

接口:
  backend = get_backend("edge_tts")   # 或 "index_tts" / "disabled"
  ok, msg = backend.synthesize(text, output_path, voice=None, speed=1.0)

设计原则:
  - 同步接口,放后台线程跑(novel_ai 用 QThread)
  - 失败时返回 (False, 详细错误),便于 UI 提示
  - 第一次失败的 Index-TTS,自动尝试 fn_index=0 + 暴露 API schema 帮助诊断
"""
from __future__ import annotations
import asyncio
import shutil
from pathlib import Path

# 可选依赖,缺一个不影响别的后端
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    from gradio_client import Client as _GrCli, handle_file as _gr_file
    GRADIO_CLIENT_AVAILABLE = True
except ImportError:
    GRADIO_CLIENT_AVAILABLE = False


class TTSBackend:
    """基类"""
    name = "base"
    display = "基类"

    def is_available(self) -> bool:
        return False

    def synthesize(self, text: str, output_path: str,
                   voice: str = None, speed: float = 1.0) -> tuple[bool, str]:
        """同步合成。
        参数:
          text: 要合成的文本
          output_path: 输出文件路径(.mp3 或 .wav)
          voice: 音色 id(各后端含义不同)
          speed: 0.5~2.0,1.0 = 正常
        返回:
          (成功?, 错误信息或 "ok")
        """
        raise NotImplementedError


class DisabledBackend(TTSBackend):
    name = "disabled"
    display = "关闭"

    def is_available(self):
        return True  # 总是"可用",但合成会返回 False

    def synthesize(self, text, output_path, voice=None, speed=1.0):
        return False, "TTS 已关闭"


class EdgeTTSBackend(TTSBackend):
    """微软 EdgeTTS — 免费 / 在线 / 不要 GPU。中文音质很好。"""
    name = "edge_tts"
    display = "EdgeTTS(免费在线)"

    # 中文最稳的几个音色
    VOICES = {
        "zh-CN-XiaoxiaoNeural": "晓晓(温柔女声·推荐)",
        "zh-CN-YunxiNeural":    "云希(沉稳男声)",
        "zh-CN-YunyangNeural":  "云扬(新闻男声)",
        "zh-CN-XiaoyiNeural":   "晓伊(活泼女声)",
        "zh-CN-YunjianNeural":  "云健(故事男声)",
        "zh-CN-YunxiaNeural":   "云夏(童声)",
        "zh-CN-XiaomengNeural": "晓梦(深情女声)",
    }
    DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

    def is_available(self):
        return EDGE_TTS_AVAILABLE

    def synthesize(self, text, output_path, voice=None, speed=1.0):
        if not EDGE_TTS_AVAILABLE:
            return False, "需要安装 edge-tts:在命令行跑  pip install edge-tts"
        voice = voice or self.DEFAULT_VOICE
        # speed: 1.0→+0%,1.5→+50%,0.5→-50%(EdgeTTS 接受 ±100%)
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = 1.0
        speed = max(0.5, min(2.0, speed))
        rate_str = f"{int((speed - 1.0) * 100):+d}%"

        async def _do():
            communicate = edge_tts.Communicate(text, voice, rate=rate_str)
            await communicate.save(output_path)

        try:
            try:
                asyncio.run(_do())
            except RuntimeError:
                # 已有 event loop 的情况(罕见,但 GUI 后台线程也可能遇到)
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(_do())
                finally:
                    loop.close()
            return True, "ok"
        except Exception as e:
            return False, f"EdgeTTS 合成失败:{type(e).__name__}: {e}"


class IndexTTSBackend(TTSBackend):
    """Index-TTS 本地 Gradio 服务 — 默认 http://127.0.0.1:7862
    需要用户提供参考音频(WAV/MP3)做声音克隆。

    V2.6 实测 endpoint = /gen_single,6 参数:
        (情感控制方式, 音色参考音频, 文本, 上传情感参考音频, 情感权重, 主情感"喜")
    """
    name = "index_tts"
    display = "Index-TTS(本地·声音克隆)"

    # V2.6 /gen_single 的"情感控制方式"dropdown 候选值 — 按可能性排序试
    EMO_METHOD_CANDIDATES = [
        "与音色参考相同",
        "使用情感参考音频",
        "使用情感向量控制",
        "使用文本描述",
        "默认",
        None,  # gradio 通常会给默认值
    ]

    # 老版 / 其他 fork 的 endpoint 候选(都是 2 参数 audio+text)
    LEGACY_ENDPOINT_CANDIDATES = ["/infer", "/tts", "/generate", "/predict"]

    def __init__(self, url="http://127.0.0.1:7862/", ref_audio=None,
                 api_name=None):
        self.url = url.rstrip("/") + "/"
        self.ref_audio = ref_audio
        self.api_name = api_name  # 用户可显式指定(如 "/gen_single")
        self._client = None

    def is_available(self):
        if not GRADIO_CLIENT_AVAILABLE:
            return False
        try:
            self._ensure_client()
            return True
        except Exception:
            return False

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not GRADIO_CLIENT_AVAILABLE:
            raise RuntimeError("缺 gradio_client:pip install gradio_client")
        self._client = _GrCli(self.url, verbose=False)
        return self._client

    def get_api_schema(self) -> str:
        """返回 Gradio 服务的 API schema 字符串(诊断用)"""
        try:
            client = self._ensure_client()
            info = client.view_api(return_format="dict", print_info=False)
            lines = []
            named = info.get("named_endpoints", {}) if isinstance(info, dict) else {}
            unnamed = info.get("unnamed_endpoints", {}) if isinstance(info, dict) else {}
            lines.append(f"=== Named endpoints({len(named)}个)===")
            for k, v in named.items():
                params = v.get("parameters", []) if isinstance(v, dict) else []
                p_str = ", ".join(p.get("label", "?") for p in params[:6])
                lines.append(f"  {k}({p_str})")
            lines.append(f"\n=== Unnamed endpoints(fn_index)({len(unnamed)}个)===")
            for k, v in list(unnamed.items())[:5]:
                params = v.get("parameters", []) if isinstance(v, dict) else []
                p_str = ", ".join(p.get("label", "?") for p in params[:6])
                lines.append(f"  fn_index={k}({p_str})")
            return "\n".join(lines)
        except Exception as e:
            return f"无法获取 API schema:{e}"

    def synthesize(self, text, output_path, voice=None, speed=1.0):
        if not GRADIO_CLIENT_AVAILABLE:
            return False, "需要安装 gradio_client:在命令行跑  pip install gradio_client"

        ref_audio = voice or self.ref_audio
        if not ref_audio or not Path(ref_audio).exists():
            return False, (
                f"Index-TTS 需要参考音频(声音克隆),"
                f"当前路径:{ref_audio!r} 不存在。请在 设置 → TTS 配置 里选一个 WAV/MP3 文件。"
            )

        try:
            client = self._ensure_client()
        except Exception as e:
            return False, f"无法连接 Index-TTS({self.url}):{e}"

        result = None
        errors = []   # 记录所有失败的尝试,最后一起告诉用户

        # ═══ 路径 1:V2.6 /gen_single 6 参数(实测真签名)═══
        target_ep = self.api_name or "/gen_single"
        if target_ep == "/gen_single" or not self.api_name:
            for method in self.EMO_METHOD_CANDIDATES:
                try:
                    result = client.predict(
                        method,                  # 情感控制方式(dropdown)
                        _gr_file(ref_audio),     # 音色参考音频
                        text,                    # 文本
                        None,                    # 上传情感参考音频(留空)
                        1.0,                     # 情感权重
                        0,                       # 主情感"喜"(数值,0=无强调)
                        api_name="/gen_single",
                    )
                    if result is not None:
                        break
                except Exception as e:
                    errors.append(f"/gen_single method={method!r}: {type(e).__name__}: {str(e)[:120]}")
                    result = None
                    continue

        # ═══ 路径 2:用户显式指定了非 /gen_single 的 api_name → 直接 2 参数 ═══
        if result is None and self.api_name and self.api_name != "/gen_single":
            for args in ((_gr_file(ref_audio), text), (text, _gr_file(ref_audio))):
                try:
                    result = client.predict(*args, api_name=self.api_name)
                    break
                except Exception as e:
                    errors.append(f"{self.api_name} 顺序{args[0].__class__.__name__}先: {str(e)[:120]}")
                    result = None

        # ═══ 路径 3:老版/其他 fork — 2 参数 + 多 endpoint 候选 ═══
        if result is None and not self.api_name:
            for ep in self.LEGACY_ENDPOINT_CANDIDATES:
                for args in ((_gr_file(ref_audio), text), (text, _gr_file(ref_audio))):
                    try:
                        result = client.predict(*args, api_name=ep)
                        break
                    except Exception as e:
                        errors.append(f"{ep}: {str(e)[:80]}")
                        result = None
                if result is not None:
                    break

        # ═══ 路径 4:fn_index=0 最后兜底 ═══
        if result is None:
            for args in ((_gr_file(ref_audio), text), (text, _gr_file(ref_audio))):
                try:
                    result = client.predict(*args, fn_index=0)
                    break
                except Exception as e:
                    errors.append(f"fn_index=0: {str(e)[:80]}")
                    result = None

        if result is None:
            err_summary = "\n  - " + "\n  - ".join(errors[-8:])  # 最多显示后 8 条
            return False, (
                f"Index-TTS 全部调用方式失败({len(errors)} 次尝试):"
                f"{err_summary}\n\n"
                f"--- 服务的 API schema(贴给 Claude 看)---\n"
                f"{self.get_api_schema()}"
            )

        # result 可能是:文件路径字符串 / 元组 / 字典
        audio_path = None
        if isinstance(result, str):
            audio_path = result
        elif isinstance(result, (tuple, list)) and len(result) > 0:
            for item in result:
                if isinstance(item, str) and Path(item).exists():
                    audio_path = item
                    break
                if isinstance(item, dict) and "path" in item:
                    audio_path = item["path"]
                    break
        elif isinstance(result, dict) and "path" in result:
            audio_path = result["path"]

        if not audio_path or not Path(audio_path).exists():
            return False, f"Index-TTS 返回的 result 找不到音频文件:{type(result).__name__} {str(result)[:200]}"

        try:
            shutil.copy(audio_path, output_path)
            return True, "ok"
        except Exception as e:
            return False, f"复制音频文件失败:{e}"


# ──── 工厂 ────
_BACKENDS = {
    "disabled":  DisabledBackend,
    "edge_tts":  EdgeTTSBackend,
    "index_tts": IndexTTSBackend,
}


def get_backend(name: str, **kwargs) -> TTSBackend:
    cls = _BACKENDS.get(name, DisabledBackend)
    return cls(**kwargs) if kwargs else cls()


def list_backends() -> list[tuple[str, str]]:
    """返回 [(name, display), ...] 供 UI 下拉用"""
    return [(name, cls.display) for name, cls in _BACKENDS.items()]


def split_text_for_tts(text: str, max_chars: int = 300) -> list[str]:
    """长文本切段,每段不超过 max_chars 字。优先按段落断,其次按句号。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # 先按段落
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    buf = ""
    for p in paragraphs:
        if len(p) > max_chars:
            # 段太长,按句号切
            if buf:
                chunks.append(buf)
                buf = ""
            # 按中英文句号切
            import re
            sentences = re.split(r'(?<=[。!?\.\!\?])\s*', p)
            sub = ""
            for s in sentences:
                if len(sub) + len(s) > max_chars and sub:
                    chunks.append(sub)
                    sub = s
                else:
                    sub += s
            if sub:
                chunks.append(sub)
            continue
        if len(buf) + len(p) + 1 > max_chars:
            chunks.append(buf)
            buf = p
        else:
            buf = (buf + "\n" + p) if buf else p
    if buf:
        chunks.append(buf)
    return chunks
