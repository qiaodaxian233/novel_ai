from __future__ import annotations

import argparse
import os
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--max-new-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.85)
    p.add_argument("--top-p", type=float, default=0.92)
    args = p.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("需要 CUDA GPU。")
    dtype = torch.float16
    qcfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=dtype,
    )
    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        quantization_config=qcfg,
        device_map="auto",
        trust_remote_code=True,
        dtype=dtype,
    )
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    inputs = tok(args.prompt, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(
            **inputs,
            max_new_tokens=args.max_new_tokens,
            do_sample=True,
            temperature=args.temperature,
            top_p=args.top_p,
            repetition_penalty=1.08,
        )
    text = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print("@@GENERATED@@" + text, flush=True)


if __name__ == "__main__":
    main()
