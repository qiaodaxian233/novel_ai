from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import torch
from torch.utils.data import Dataset


TEXT_EXTS = {".txt", ".md", ".markdown"}


def log(msg: str) -> None:
    print(msg, flush=True)


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            pass
    return path.read_text(encoding="utf-8", errors="ignore")


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    # 盗版站源常见:行首/行内混入 BOM 和零宽字符,肉眼不可见但污染分词
    text = re.sub(r"[\ufeff\u200b\u200c\u200d\u2060]", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


# 章节标题行:第 + 中文/阿拉伯数字 + 章
_CHAPTER_RE = re.compile(r"^\s*第\s*[0-9零〇一二三四五六七八九十百千万两]+\s*章")
_DECOR_CHARS = set("-—–=_*~·.。 　")


def _norm_title(t: str) -> str:
    """标题归一化:去所有空白/冒号顿号,剥尾部装饰符,便于跨行比对"""
    t = re.sub(r"[\s:：、,，]+", "", t)
    return t.strip("".join(_DECOR_CHARS))


def dedup_chapter_titles(text: str):
    """站点源清洗:同一章标题连报两遍(中文序号一遍/站点阿拉伯序号一遍,
    数字常对不上但'章'后标题相同)→ 相邻重复只留第一个;纯装饰行删除。
    返回 (清洗后文本, 删除行数)。"""
    out, removed = [], 0
    last_title = None          # 最近章节头的归一化标题;空行不打断相邻判断
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if len(stripped) >= 4 and all(c in _DECOR_CHARS for c in stripped):
            removed += 1       # ------------ 之类的装饰线
            continue
        m = _CHAPTER_RE.match(stripped)
        if m:
            norm = _norm_title(stripped[m.end():])
            if not norm:       # 光杆"第X章":用整行(去空白)参与比对
                norm = re.sub(r"\s+", "", stripped)
            if norm == last_title:
                removed += 1
                continue
            last_title = norm
        else:
            last_title = None  # 出现正文,前面的标题不再算"相邻"
        out.append(line)
    return "\n".join(out), removed


def collect_text_files(folder: str) -> List[Path]:
    root = Path(folder)
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTS)


def collect_jsonl_files(path_or_folder: str) -> List[Path]:
    p = Path(path_or_folder)
    if p.is_file() and p.suffix.lower() == ".jsonl":
        return [p]
    if p.is_dir():
        return sorted(x for x in p.rglob("*.jsonl") if x.is_file())
    return []


def source_fingerprint(files: Iterable[Path], extra: Dict[str, Any]) -> str:
    h = hashlib.sha256()
    for p in files:
        s = p.stat()
        h.update(str(p.resolve()).encode("utf-8", errors="ignore"))
        h.update(str(s.st_size).encode())
        h.update(str(s.st_mtime_ns).encode())
    h.update(json.dumps(extra, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()[:24]


@dataclass
class CacheInfo:
    token_bin: str
    index_npy: str
    meta_json: str
    label_bin: str | None = None


class BinaryTokenDataset(Dataset):
    def __init__(self, cache: CacheInfo):
        self.index = np.load(cache.index_npy, mmap_mode="r")
        token_count = os.path.getsize(cache.token_bin) // np.dtype(np.uint32).itemsize
        self.tokens = np.memmap(cache.token_bin, dtype=np.uint32, mode="r", shape=(token_count,))
        self.labels = None
        if cache.label_bin:
            label_count = os.path.getsize(cache.label_bin) // np.dtype(np.int32).itemsize
            self.labels = np.memmap(cache.label_bin, dtype=np.int32, mode="r", shape=(label_count,))

    def __len__(self):
        return int(self.index.shape[0])

    def __getitem__(self, idx):
        off, length = map(int, self.index[idx])
        input_ids = torch.from_numpy(np.asarray(self.tokens[off:off + length], dtype=np.int64))
        item = {"input_ids": input_ids}
        if self.labels is not None:
            labels = torch.from_numpy(np.asarray(self.labels[off:off + length], dtype=np.int64))
            item["labels"] = labels
        return item


class CausalLMCollator:
    def __init__(self, pad_token_id: int, pad_to_multiple_of: int = 8):
        self.pad_token_id = int(pad_token_id)
        self.pad_to_multiple_of = int(pad_to_multiple_of)

    def __call__(self, features: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
        max_len = max(int(x["input_ids"].shape[0]) for x in features)
        if self.pad_to_multiple_of > 1:
            m = self.pad_to_multiple_of
            max_len = ((max_len + m - 1) // m) * m

        input_batch, label_batch, mask_batch = [], [], []
        for x in features:
            ids = x["input_ids"].long()
            labels = x.get("labels", ids.clone()).long()
            pad_n = max_len - ids.shape[0]
            if pad_n:
                ids = torch.cat([ids, torch.full((pad_n,), self.pad_token_id, dtype=torch.long)])
                labels = torch.cat([labels, torch.full((pad_n,), -100, dtype=torch.long)])
                mask = torch.cat([
                    torch.ones(max_len - pad_n, dtype=torch.long),
                    torch.zeros(pad_n, dtype=torch.long),
                ])
            else:
                mask = torch.ones(max_len, dtype=torch.long)
            input_batch.append(ids)
            label_batch.append(labels)
            mask_batch.append(mask)

        return {
            "input_ids": torch.stack(input_batch),
            "labels": torch.stack(label_batch),
            "attention_mask": torch.stack(mask_batch),
        }


def _cache_valid(meta_path: Path, fingerprint: str, required: List[Path]) -> bool:
    if not meta_path.exists() or not all(p.exists() for p in required):
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("fingerprint") == fingerprint
    except Exception:
        return False


def prepare_cpt_dataset(tokenizer, data_path: str, cache_dir: str, max_length: int, min_length: int, overlap: int, clean_titles: bool = True) -> Tuple[BinaryTokenDataset, Dict[str, Any]]:
    files = collect_text_files(data_path)
    if not files:
        raise FileNotFoundError(f"没有在 {data_path} 找到 TXT/MD 小说文件。")
    if overlap >= max_length:
        raise ValueError("overlap 必须小于 max_length。")

    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    token_bin = cache_root / "cpt_tokens.bin"
    index_npy = cache_root / "cpt_index.npy"
    meta_json = cache_root / "cpt_meta.json"
    fp = source_fingerprint(files, {
        "mode": "cpt",
        "max_length": max_length,
        "min_length": min_length,
        "overlap": overlap,
        "clean_titles": clean_titles,
        "tokenizer": getattr(tokenizer, "name_or_path", "unknown"),
    })

    if _cache_valid(meta_json, fp, [token_bin, index_npy]):
        meta = json.loads(meta_json.read_text(encoding="utf-8"))
        log(f"[数据] 命中缓存：{meta.get('samples', 0)} 个样本。")
        return BinaryTokenDataset(CacheInfo(str(token_bin), str(index_npy), str(meta_json))), meta

    eos_id = tokenizer.eos_token_id
    if eos_id is None:
        raise ValueError("Tokenizer 没有 eos_token_id。")

    indices: List[Tuple[int, int]] = []
    token_offset = 0
    raw_chars = 0
    written_tokens = 0
    step = max_length - overlap

    log(f"[数据] 开始预处理 {len(files)} 本/个文本文件……")
    with token_bin.open("wb") as fout:
        for i, path in enumerate(files, 1):
            text = _normalize_text(_read_text(path))
            if clean_titles and text:
                text, _n_removed = dedup_chapter_titles(text)
                if _n_removed:
                    log(f"[清洗] {path.name}:删除 {_n_removed} 行重复标题/装饰线")
            if not text:
                continue
            raw_chars += len(text)
            ids = tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]
            ids.append(eos_id)  # 每本小说独立结束，避免和下一本无缝相连

            made = 0
            for start in range(0, len(ids), step):
                chunk = ids[start:start + max_length]
                if len(chunk) < min_length:
                    break
                arr = np.asarray(chunk, dtype=np.uint32)
                arr.tofile(fout)
                indices.append((token_offset, len(chunk)))
                token_offset += len(chunk)
                written_tokens += len(chunk)
                made += 1
                if start + max_length >= len(ids):
                    break
            log(f"[数据] {i}/{len(files)} {path.name} -> {made} 块")

    if not indices:
        raise ValueError("没有生成训练样本；请降低最小长度，或加入更长的小说文本。")
    np.save(index_npy, np.asarray(indices, dtype=np.int64))
    meta = {
        "fingerprint": fp,
        "mode": "cpt",
        "files": len(files),
        "samples": len(indices),
        "raw_chars": raw_chars,
        "stored_tokens": written_tokens,
        "max_length": max_length,
        "min_length": min_length,
        "overlap": overlap,
    }
    meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[数据] 预处理完成：{len(indices)} 个样本。")
    return BinaryTokenDataset(CacheInfo(str(token_bin), str(index_npy), str(meta_json))), meta


def _record_to_messages(record: Dict[str, Any]) -> List[Dict[str, str]]:
    if isinstance(record.get("messages"), list):
        messages = record["messages"]
        out = []
        for m in messages:
            if not isinstance(m, dict) or "role" not in m or "content" not in m:
                raise ValueError("messages 中每项都需要 role/content。")
            out.append({"role": str(m["role"]), "content": str(m["content"])})
        return out

    if "output" not in record:
        raise ValueError("SFT JSONL 每行需包含 messages，或 instruction/input/output。")
    system = str(record.get("system", "你是一名中文小说创作助手。"))
    instruction = str(record.get("instruction", "请根据给定内容继续创作小说。"))
    inp = str(record.get("input", ""))
    user_text = instruction if not inp else f"{instruction}\n\n{inp}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": str(record["output"])},
    ]




def _encode_messages(tokenizer, messages: List[Dict[str, str]], add_generation_prompt: bool) -> List[int]:
    """Use the tokenizer chat template when present; otherwise use a simple Chinese Base-model template."""
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=add_generation_prompt
        )

    role_names = {"system": "系统", "user": "用户", "assistant": "助手"}
    parts = []
    for m in messages:
        role = role_names.get(m["role"], m["role"])
        parts.append(f"{role}：{m['content']}")
    if add_generation_prompt:
        parts.append("助手：")
    text = "\n\n".join(parts)
    ids = tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]
    if not add_generation_prompt and messages and messages[-1]["role"] == "assistant" and tokenizer.eos_token_id is not None:
        ids = list(ids) + [tokenizer.eos_token_id]
    return ids

def prepare_sft_dataset(tokenizer, data_path: str, cache_dir: str, max_length: int, min_response_tokens: int = 16) -> Tuple[BinaryTokenDataset, Dict[str, Any]]:
    files = collect_jsonl_files(data_path)
    if not files:
        raise FileNotFoundError(f"没有在 {data_path} 找到 JSONL 文件。")

    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    token_bin = cache_root / "sft_tokens.bin"
    label_bin = cache_root / "sft_labels.bin"
    index_npy = cache_root / "sft_index.npy"
    meta_json = cache_root / "sft_meta.json"
    fp = source_fingerprint(files, {
        "mode": "sft",
        "max_length": max_length,
        "min_response_tokens": min_response_tokens,
        "tokenizer": getattr(tokenizer, "name_or_path", "unknown"),
    })

    if _cache_valid(meta_json, fp, [token_bin, label_bin, index_npy]):
        meta = json.loads(meta_json.read_text(encoding="utf-8"))
        log(f"[数据] 命中 SFT 缓存：{meta.get('samples', 0)} 个样本。")
        return BinaryTokenDataset(CacheInfo(str(token_bin), str(index_npy), str(meta_json), str(label_bin))), meta

    indices: List[Tuple[int, int]] = []
    offset = 0
    skipped = 0
    total_lines = 0

    with token_bin.open("wb") as ftok, label_bin.open("wb") as flab:
        for path in files:
            with path.open("r", encoding="utf-8-sig") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    total_lines += 1
                    try:
                        record = json.loads(line)
                        messages = _record_to_messages(record)
                        if not messages or messages[-1]["role"] != "assistant":
                            raise ValueError("最后一条 message 必须是 assistant。")

                        full_ids = _encode_messages(tokenizer, messages, add_generation_prompt=False)
                        prompt_ids = _encode_messages(tokenizer, messages[:-1], add_generation_prompt=True)
                        assistant_start = min(len(prompt_ids), len(full_ids))

                        if len(full_ids) > max_length:
                            cut = len(full_ids) - max_length
                            full_ids = full_ids[cut:]
                            assistant_start = max(0, assistant_start - cut)

                        if len(full_ids) - assistant_start < min_response_tokens:
                            skipped += 1
                            continue

                        labels = np.asarray(full_ids, dtype=np.int32)
                        labels[:assistant_start] = -100
                        ids = np.asarray(full_ids, dtype=np.uint32)
                        ids.tofile(ftok)
                        labels.tofile(flab)
                        indices.append((offset, len(ids)))
                        offset += len(ids)
                    except Exception as e:
                        skipped += 1
                        log(f"[数据][跳过] {path.name}:{line_no}: {e}")

    if not indices:
        raise ValueError("SFT 数据没有产生有效样本，请检查 JSONL 格式。")
    np.save(index_npy, np.asarray(indices, dtype=np.int64))
    meta = {
        "fingerprint": fp,
        "mode": "sft",
        "files": len(files),
        "lines": total_lines,
        "samples": len(indices),
        "skipped": skipped,
        "max_length": max_length,
    }
    meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[数据] SFT 预处理完成：{len(indices)} 个样本，跳过 {skipped}。")
    return BinaryTokenDataset(CacheInfo(str(token_bin), str(index_npy), str(meta_json), str(label_bin))), meta
