from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainerCallback,
    TrainingArguments,
)

from .data import CausalLMCollator, prepare_cpt_dataset, prepare_sft_dataset


def jprint(obj):
    print("@@PROGRESS@@" + json.dumps(obj, ensure_ascii=False), flush=True)


class GuiCallback(TrainerCallback):
    def __init__(self, stop_file: str, grad_accum: int = 1, loss_log: str | None = None):
        self.stop_file = stop_file
        self.grad_accum = max(1, int(grad_accum))
        self.loss_log = loss_log
        self._micro_in_step = 0   # 当前优化器 step 内已完成的 micro-batch 数

    def _emit_micro(self, state):
        total = int(state.max_steps or 0) * self.grad_accum
        if total <= 0:
            return
        done = int(state.global_step) * self.grad_accum + self._micro_in_step
        jprint({
            "micro": min(done, total), "micro_total": total,
            "step": int(state.global_step),
            "max_steps": int(state.max_steps or 0),
        })

    def on_log(self, args, state, control, logs=None, **kwargs):
        logs = logs or {}
        rec = {
            "step": int(state.global_step),
            "max_steps": int(state.max_steps or 0),
            "epoch": float(state.epoch or 0),
            "loss": logs.get("loss"),
            "learning_rate": logs.get("learning_rate"),
            "grad_norm": logs.get("grad_norm"),
        }
        jprint(rec)
        if self.loss_log and rec["loss"] is not None:
            try:  # loss 曲线落盘,训完可以画图复盘
                with open(self.loss_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError:
                pass

    def on_substep_end(self, args, state, control, **kwargs):
        # 梯度累积的每个 micro-batch 结束都报一次进度(约几秒一跳,看得见盼头)
        self._micro_in_step += 1
        self._emit_micro(state)

    def on_step_end(self, args, state, control, **kwargs):
        self._micro_in_step = 0   # global_step 已 +1,micro 计数归零
        self._emit_micro(state)
        if os.path.exists(self.stop_file):
            print("[控制] 收到停止请求，将在当前 step 后安全停止并保存 LoRA。", flush=True)
            control.should_training_stop = True
        return control


def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def choose_precision(name: str):
    name = (name or "bf16").lower()
    if name == "bf16" and torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        return torch.bfloat16, True, False
    return torch.float16, False, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)

    if not torch.cuda.is_available():
        raise RuntimeError("没有检测到 CUDA。请先安装 NVIDIA 驱动和 CUDA 版 PyTorch。")

    model_source = cfg["model_source"]
    output_dir = os.path.abspath(cfg["output_dir"])
    os.makedirs(output_dir, exist_ok=True)
    stop_file = os.path.join(output_dir, ".stop_training")
    if os.path.exists(stop_file):
        os.remove(stop_file)

    print(f"[GPU] {torch.cuda.get_device_name(0)}", flush=True)
    print(f"[模型] {model_source}", flush=True)
    print(f"[输出] {output_dir}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(model_source, trust_remote_code=True, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    data_cfg = cfg["data"]
    cache_dir = os.path.join(output_dir, "dataset_cache")
    if data_cfg["mode"] == "cpt":
        dataset, meta = prepare_cpt_dataset(
            tokenizer,
            data_cfg["path"],
            cache_dir,
            int(data_cfg["max_length"]),
            int(data_cfg.get("min_length", 256)),
            int(data_cfg.get("overlap", 0)),
        )
    else:
        dataset, meta = prepare_sft_dataset(
            tokenizer,
            data_cfg["path"],
            cache_dir,
            int(data_cfg["max_length"]),
            int(data_cfg.get("min_response_tokens", 16)),
        )
    print(f"[数据] 样本数：{len(dataset)}", flush=True)

    train_cfg = cfg["training"]
    compute_dtype, use_bf16, use_fp16 = choose_precision(train_cfg.get("precision", "fp16"))
    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    print("[模型] 以 4-bit NF4 加载基座……", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        quantization_config=bnb_cfg,
        device_map="auto",
        trust_remote_code=True,
        dtype=compute_dtype,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    target_choice = train_cfg.get("target_modules", "all-linear")
    if target_choice == "attention":
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj"]
    else:
        target_modules = "all-linear"

    lora_cfg = LoraConfig(
        r=int(train_cfg.get("lora_rank", 16)),
        lora_alpha=int(train_cfg.get("lora_alpha", 32)),
        lora_dropout=float(train_cfg.get("lora_dropout", 0.05)),
        target_modules=target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    grad_accum = int(train_cfg.get("gradient_accumulation_steps", 16))
    batch_size = int(train_cfg.get("batch_size", 1))
    epochs = float(train_cfg.get("epochs", 1.0))
    approximate_steps = math.ceil(len(dataset) / max(1, batch_size * grad_accum) * epochs)
    print(f"[训练] 预计优化器 steps 约 {approximate_steps}（实际以 Trainer 为准）", flush=True)
    # 存档步长钳到总步数的 1/3 以内:65 步的训练配 100 步存档 = 中途从不存档,
    # 崩了就全丢;钳完至少存 2-3 个中间点
    _save_steps = int(train_cfg.get("save_steps", 100))
    _clamp = max(10, approximate_steps // 3)
    if _save_steps > _clamp:
        print(f"[兼容] 存档步长 {_save_steps} > 总步数的 1/3,已钳制为 {_clamp}", flush=True)
        _save_steps = _clamp

    # transformers v5 对 TrainingArguments 做了大瘦身(比如删掉 warmup_ratio),
    # 直接传会 TypeError。这里按"当前安装版本实际支持的字段"过滤:
    # 不支持的丢弃并打日志,warmup_ratio 换算成等价 warmup_steps。
    import dataclasses
    _valid = {f.name for f in dataclasses.fields(TrainingArguments)}
    _kw = dict(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=float(train_cfg.get("learning_rate", 1e-4)),
        weight_decay=float(train_cfg.get("weight_decay", 0.0)),
        warmup_ratio=float(train_cfg.get("warmup_ratio", 0.03)),
        lr_scheduler_type=train_cfg.get("lr_scheduler", "cosine"),
        logging_strategy="steps",
        logging_steps=int(train_cfg.get("logging_steps", 1)),
        logging_first_step=True,
        save_strategy="steps",
        save_steps=_save_steps,
        save_total_limit=int(train_cfg.get("save_total_limit", 2)),
        optim="paged_adamw_8bit",
        fp16=use_fp16,
        bf16=use_bf16,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_grad_norm=float(train_cfg.get("max_grad_norm", 0.3)),
        report_to="none",
        seed=int(train_cfg.get("seed", 42)),
        dataloader_num_workers=0,
        dataloader_pin_memory=True,
        remove_unused_columns=False,
    )
    if "warmup_steps" in _valid:
        # warmup_ratio 在 v5 已弃用/移除,只要 warmup_steps 可用就主动换算,
        # 同时躲开"弃用警告"和"已移除报错"两个坑
        _ratio = _kw.pop("warmup_ratio")
        _kw["warmup_steps"] = max(1, int(_ratio * approximate_steps))
        print(f"[兼容] warmup_ratio={_ratio} 已换算为"
              f" warmup_steps={_kw['warmup_steps']}", flush=True)
    for _k in [k for k in _kw if k not in _valid]:
        print(f"[兼容] 此版本 transformers 不支持参数 {_k},已忽略", flush=True)
        _kw.pop(_k)
    ta = TrainingArguments(**_kw)

    collator = CausalLMCollator(tokenizer.pad_token_id)
    trainer = Trainer(
        model=model,
        args=ta,
        train_dataset=dataset,
        data_collator=collator,
        callbacks=[GuiCallback(stop_file, grad_accum,
                                os.path.join(output_dir, "loss_history.jsonl"))],
    )

    resume = train_cfg.get("resume_from_checkpoint") or None
    if resume and not os.path.exists(resume):
        print(f"[警告] 断点目录不存在，忽略：{resume}", flush=True)
        resume = None

    print("[训练] 开始。", flush=True)
    trainer.train(resume_from_checkpoint=resume)

    final_dir = os.path.join(output_dir, "final_adapter")
    os.makedirs(final_dir, exist_ok=True)
    trainer.model.save_pretrained(final_dir)
    tokenizer.save_pretrained(final_dir)
    with open(os.path.join(final_dir, "training_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"[完成] LoRA 已保存：{final_dir}", flush=True)
    jprint({"done": True, "step": int(trainer.state.global_step), "max_steps": int(trainer.state.max_steps or 0)})


if __name__ == "__main__":
    main()
