# Novel AI Trainer（3080 Ti 12GB / QLoRA）

一个本地 Windows GUI 小说模型训练工程。默认基座是 `Qwen/Qwen3-4B-Base`（Apache-2.0，可放心商用；同显存下强于 Qwen2.5-3B）。显存充裕想再进一步可换 `Qwen/Qwen3-8B-Base`（训练时把 Context 降回 2048 或 LoRA target 改仅注意力层）。

> 下载默认走 hf-mirror.com 国内镜像；海外网络可设环境变量 `HF_ENDPOINT=https://huggingface.co` 覆盖。

## 能做什么

- GUI 一键下载 Qwen2.5-3B Base
- TXT / MD 小说正文领域训练（QLoRA）
- JSONL 小说 SFT（只对 assistant 输出计算 loss）
- 4-bit NF4 + double quant
- LoRA rank / alpha / dropout / context / batch / grad accumulation 可调
- 自动把每本小说末尾加 EOS，避免不同小说无边界粘连
- 数据预处理缓存：第二次启动不重复 tokenize
- checkpoint 保存与断点续训
- GUI 安全停止：当前 step 完成后保存 `final_adapter`
- 实时训练日志、loss/step 进度、GPU 显存/利用率/温度
- GUI 直接加载基座 + LoRA 做生成测试

## 推荐环境

- Windows 10/11 x64
- NVIDIA RTX 3080 Ti 12GB
- 较新的 NVIDIA 驱动
- Python 3.11 x64（推荐）
- 至少 16GB 系统内存；32GB 更舒服
- 模型、缓存、checkpoint 建议预留 20GB 以上磁盘空间

## 最简单的使用方法

1. 安装 Python 3.11 x64，并勾选 **Add Python to PATH**。
2. 解压本工程。
3. 双击 `安装并启动.bat`。
4. GUI 打开后先点 **一键下载模型**。
5. 把你有权用于训练的小说放到 `data/novels/`，建议一本一个 TXT。
6. 点 **一键开始训练**。
7. 成品 LoRA 在：`outputs/novel_qwen3b_lora/final_adapter/`。
8. 切到 **测试 LoRA** 标签页测试续写。
9. 满意后双击 `导出到Ollama.bat`：自动合并 LoRA → 注册进 Ollama（内置量化，不需要 llama.cpp）。之后在写作软件里站点选「本地模型(Ollama)」、模型名填 `novel-qwen` 即可接入生成流水线。

之后再次使用只需要双击 `启动GUI.bat`。

## 3080 Ti 12GB 默认训练参数

- 模型：Qwen3-4B-Base
- 量化：4-bit NF4
- Context：4096（SFT 的「大纲→整章」样本常超 2048，太小会把大纲截掉，模型学不到按纲写作）
- Batch：1
- Gradient accumulation：16
- LoRA rank：16
- LoRA alpha：32
- LoRA dropout：0.05
- LoRA target：all-linear
- LR：1e-4
- Precision：BF16（30 系 Ampere 支持；fp16 偶发 loss NaN）
- Gradient checkpointing：开启
- Optimizer：paged AdamW 8-bit

如果显存不足：先把 Context 从 2048 降到 1536 或 1024；再把 LoRA target 改成“仅注意力层”。

## 正文训练数据

目录示例：

```text
data/novels/
├─ 小说A.txt
├─ 小说B.txt
├─ 小说C.txt
└─ 某系列/
   ├─ 第一部.txt
   └─ 第二部.txt
```

程序逐本处理。每本末尾会插入 tokenizer 的 EOS，然后在**书内**切块。默认 `overlap=0`，不会把小说 A 的最后一段和小说 B 的第一段拼成同一个训练样本。

> 只使用你有权用于训练的文本。

## SFT 数据

支持两种 JSONL 格式。

### 1. instruction/input/output

```json
{"system":"你是一名中文小说作者。","instruction":"根据前文续写。","input":"前文……","output":"续写正文……"}
```

### 2. messages

```json
{"messages":[
  {"role":"system","content":"你是一名中文小说作者。"},
  {"role":"user","content":"根据前文续写：……"},
  {"role":"assistant","content":"续写正文……"}
]}
```

工程会 mask 掉 prompt，只让 assistant 部分参与 loss。

## 推荐训练顺序

第一阶段：**正文领域 QLoRA（CPT 风格）**

- 使用 `Qwen/Qwen3-4B-Base`
- 喂高质量小说正文
- 目标是把语言分布、叙事节奏、对白、描写往小说方向推

第二阶段：**小说 SFT**

- 可以在第一阶段得到的 LoRA 基础上继续设计，但实际工程中更推荐保留阶段性 adapter 和清晰的数据版本
- 数据包括：人物卡 → 写场景、大纲 → 写章节、前文 → 续写、改写、视角约束、文风约束等

当前 GUI 的断点续训是 Hugging Face Trainer checkpoint 级别，用于恢复同一训练任务；它不是“把任意一个旧 LoRA 当成新训练起点”的通用 adapter stacking 功能。

## 目录结构

```text
NovelAITrainer/
├─ app.py                       # PySide6 GUI
├─ 安装并启动.bat               # 首次安装环境 + 启动
├─ 启动GUI.bat                  # 后续启动
├─ 检查环境.bat
├─ requirements.txt
├─ novel_trainer/
│  ├─ data.py                   # TXT/SFT 预处理 + memmap dataset
│  ├─ train.py                  # 4-bit QLoRA Trainer
│  ├─ download_model.py         # Hugging Face 下载
│  ├─ generate.py               # 基座 + LoRA 测试生成
│  └─ check_env.py
├─ data/
│  ├─ novels/
│  └─ sft/
├─ examples/
│  └─ sft_example.jsonl
├─ models/
└─ outputs/
```

## 输出目录

典型结构：

```text
outputs/novel_qwen3b_lora/
├─ runtime_config.json
├─ dataset_cache/
├─ checkpoint-100/
├─ checkpoint-200/
└─ final_adapter/
   ├─ adapter_config.json
   ├─ adapter_model.safetensors
   ├─ tokenizer...
   └─ training_config.json
```

`final_adapter` 不是完整 3B 模型，而是 LoRA adapter；推理时需要配合原基座。

## 常见问题

### CUDA unavailable

先双击 `检查环境.bat`。如果 `CUDA available: False`，通常是 PyTorch CUDA 版本或 NVIDIA 驱动问题。

### CUDA out of memory

按顺序尝试：

1. Context 2048 → 1536 → 1024
2. LoRA target：all-linear → attention
3. Rank 16 → 8
4. 保持 batch=1，不要增加

梯度累积主要影响有效 batch，不会像直接提高 micro batch 那样大量增加激活显存。

### 数据量太少

正文领域训练不是“把一本书背下来”。数据过少很容易过拟合、复读、模仿原句。更应该追求来源合法、风格匹配、清洗良好的多本小说语料。

### 为什么用 Base，不默认用 Instruct？

正文领域适配更接近 continued pretraining 的目标，因此默认 Base。真正做“按人物卡/大纲/指令写小说”的能力，再用 SFT 数据训练。

## 说明

这是面向单卡消费级 GPU 的参数高效训练工程，不是 3B 全参数继续预训练。4-bit 基座权重被冻结，训练的是 LoRA 参数。
