# -*- coding: utf-8 -*-
"""
export_ollama.py — 把训练好的 LoRA 合并进基座并注册到 Ollama(最后一公里)

流程:
  1. 以 fp16/bf16 在 CPU 上加载基座(不占显存,占内存:4B≈8GB,8B≈16GB)
  2. 挂 LoRA → merge_and_unload → 保存合并后的 safetensors 目录
  3. 生成 Modelfile(带 Qwen chat 模板)
  4. 若检测到 ollama 命令,自动执行:
       ollama create <名字> -f Modelfile -q q4_K_M
     (Ollama 原生支持导入 safetensors 目录并量化,不需要 llama.cpp)

用法(在训练器目录、激活 .venv 后):
  python -m novel_trainer.export_ollama ^
      --base models/Qwen3-4B-Base ^
      --adapter outputs/novel_qwen_lora/final_adapter ^
      --out outputs/merged_novel ^
      --name novel-qwen

完成后回主软件:站点选「本地模型(Ollama)」,模型名填 novel-qwen 即可。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

# Qwen 系 chat 模板(im_start 格式)。导入 safetensors 时 Ollama 不一定能
# 从 tokenizer 配置自动推出模板,显式写进 Modelfile 最稳。
QWEN_TEMPLATE = '''TEMPLATE """{{- range .Messages }}<|im_start|>{{ .Role }}
{{ .Content }}<|im_end|>
{{ end }}<|im_start|>assistant
"""
PARAMETER stop <|im_end|>
PARAMETER temperature 0.8
PARAMETER top_p 0.92
PARAMETER repeat_penalty 1.08
'''


def main():
    p = argparse.ArgumentParser(description="合并 LoRA 并注册到 Ollama")
    p.add_argument("--base", required=True, help="基座模型目录(本地路径)")
    p.add_argument("--adapter", required=True, help="LoRA 目录(final_adapter)")
    p.add_argument("--out", required=True, help="合并输出目录")
    p.add_argument("--name", default="novel-qwen", help="Ollama 模型名")
    p.add_argument("--quant", default="q4_K_M",
                   help="量化档(q4_K_M 推荐;q8_0 更好但更大)")
    p.add_argument("--skip-merge", action="store_true",
                   help="out 目录已有合并模型时跳过第 1-2 步")
    args = p.parse_args()

    out_dir = os.path.abspath(args.out)

    if not args.skip_merge:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        print(f"[1/4] CPU 加载基座(fp16):{args.base}", flush=True)
        print("      4B 约需 8GB 内存,8B 约需 16GB;显卡不参与,耐心等。", flush=True)
        model = AutoModelForCausalLM.from_pretrained(
            args.base,
            dtype=torch.float16,
            device_map="cpu",
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        print(f"[2/4] 挂载并合并 LoRA:{args.adapter}", flush=True)
        model = PeftModel.from_pretrained(model, args.adapter)
        model = model.merge_and_unload()
        os.makedirs(out_dir, exist_ok=True)
        model.save_pretrained(out_dir, safe_serialization=True)
        tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
        tok.save_pretrained(out_dir)
        del model
        print(f"      合并完成 → {out_dir}", flush=True)
    else:
        print(f"[1-2/4] 跳过合并,直接使用:{out_dir}", flush=True)

    print("[3/4] 写 Modelfile", flush=True)
    modelfile = os.path.join(out_dir, "Modelfile")
    with open(modelfile, "w", encoding="utf-8") as f:
        # Windows 上 Ollama 接受正斜杠路径,统一用 as_posix 风格避免转义坑
        f.write(f"FROM {out_dir.replace(os.sep, '/')}\n")
        f.write(QWEN_TEMPLATE)

    print(f"[4/4] 注册到 Ollama:{args.name}(量化 {args.quant})", flush=True)
    if shutil.which("ollama") is None:
        print("  ⚠ 没找到 ollama 命令。装好 Ollama 后手动执行:", flush=True)
        print(f'    ollama create {args.name} -f "{modelfile}" -q {args.quant}',
              flush=True)
        return
    ret = subprocess.call(
        ["ollama", "create", args.name, "-f", modelfile, "-q", args.quant])
    if ret == 0:
        print(f"\n✅ 完成。主软件里:站点选「本地模型(Ollama)」,"
              f"模型名填 {args.name}", flush=True)
    else:
        print(f"\n❌ ollama create 失败(退出码 {ret}),"
              f"把上面的报错发出来排查。", flush=True)
        sys.exit(ret)


if __name__ == "__main__":
    main()
