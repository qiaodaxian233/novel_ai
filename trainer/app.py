from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget
)

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_ID = "Qwen/Qwen3-4B-Base"
DEFAULT_MODEL_DIR = ROOT / "models" / "Qwen3-4B-Base"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Novel AI Trainer · 3B QLoRA")
        self.resize(1100, 780)
        self.proc: QProcess | None = None
        self.operation = ""
        self.generated_buffer = ""
        self.proc_buffer = ""
        self._build_ui()
        self._load_settings()   # 记住上次的全部表单配置
        self._apply_style()
        self.gpu_timer = QTimer(self)
        self.gpu_timer.timeout.connect(self.update_gpu_status)
        self.gpu_timer.start(2500)
        self.update_gpu_status()

    def _build_ui(self):
        tabs = QTabWidget()
        tabs.addTab(self._build_train_tab(), "训练")
        tabs.addTab(self._build_test_tab(), "测试 LoRA")
        self.setCentralWidget(tabs)

    def _build_train_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        model_box = QGroupBox("1. 基座模型")
        grid = QGridLayout(model_box)
        self.model_id = QLineEdit(DEFAULT_MODEL_ID)
        self.model_dir = QLineEdit(str(DEFAULT_MODEL_DIR))
        btn_model_dir = QPushButton("选择目录")
        btn_model_dir.clicked.connect(lambda: self.pick_dir(self.model_dir))
        self.btn_download = QPushButton("一键下载模型")
        self.btn_download.clicked.connect(self.download_model)
        grid.addWidget(QLabel("Hugging Face ID"), 0, 0)
        grid.addWidget(self.model_id, 0, 1, 1, 2)
        grid.addWidget(QLabel("本地模型目录"), 1, 0)
        grid.addWidget(self.model_dir, 1, 1)
        grid.addWidget(btn_model_dir, 1, 2)
        grid.addWidget(self.btn_download, 2, 1)
        layout.addWidget(model_box)

        data_box = QGroupBox("2. 训练数据")
        grid = QGridLayout(data_box)
        self.data_mode = QComboBox()
        self.data_mode.addItem("小说正文续训（TXT / MD）", "cpt")
        self.data_mode.addItem("小说指令微调（JSONL）", "sft")
        self.data_path = QLineEdit(str(ROOT / "data" / "novels"))
        btn_data = QPushButton("选择")
        btn_data.clicked.connect(self.pick_data)
        self.max_length = QComboBox()
        self.max_length.addItems(["1024", "1536", "2048", "2560", "3072", "4096"])
        self.max_length.setCurrentText("4096")  # SFT 大纲→整章常超 2048,截断会砍掉大纲
        self.overlap = QSpinBox(); self.overlap.setRange(0, 1024); self.overlap.setValue(0); self.overlap.setSingleStep(64)
        self.data_mode.currentIndexChanged.connect(self.on_mode_changed)
        grid.addWidget(QLabel("数据类型"), 0, 0); grid.addWidget(self.data_mode, 0, 1, 1, 2)
        grid.addWidget(QLabel("数据路径"), 1, 0); grid.addWidget(self.data_path, 1, 1); grid.addWidget(btn_data, 1, 2)
        grid.addWidget(QLabel("Context"), 2, 0); grid.addWidget(self.max_length, 2, 1)
        self.clean_titles = QCheckBox("清洗重复章节标题/装饰线(推荐)")
        self.clean_titles.setChecked(True)
        self.clean_titles.setToolTip(
            "站点源常见脏数据:同一章标题连报两遍(中文序号+站点阿拉伯序号)、\n"
            "行首隐形 BOM、------ 装饰线。勾选后预处理时自动清除。\n"
            "改动此项会重建数据缓存(重新分词一次)。")
        grid.addWidget(QLabel("相邻块重叠 token"), 3, 0); grid.addWidget(self.overlap, 3, 1)
        grid.addWidget(self.clean_titles, 3, 2)
        self.data_hint = QLabel("建议：每本小说一个 TXT；程序会在每本末尾加 EOS，不会把两本书直接粘连。")
        self.data_hint.setWordWrap(True)
        grid.addWidget(self.data_hint, 4, 0, 1, 3)
        layout.addWidget(data_box)

        param_box = QGroupBox("3. QLoRA 参数（3080 Ti 12GB 默认值）")
        form = QFormLayout(param_box)
        row1 = QHBoxLayout()
        self.epochs = QDoubleSpinBox(); self.epochs.setRange(0.1, 20); self.epochs.setValue(1.0); self.epochs.setSingleStep(0.5)
        self.lr = QLineEdit("0.0001")
        self.batch = QSpinBox(); self.batch.setRange(1, 8); self.batch.setValue(1)
        self.grad_acc = QSpinBox(); self.grad_acc.setRange(1, 256); self.grad_acc.setValue(16)
        row1.addWidget(QLabel("Epoch")); row1.addWidget(self.epochs)
        row1.addWidget(QLabel("LR")); row1.addWidget(self.lr)
        row1.addWidget(QLabel("Batch")); row1.addWidget(self.batch)
        row1.addWidget(QLabel("梯度累积")); row1.addWidget(self.grad_acc)
        form.addRow(row1)

        row2 = QHBoxLayout()
        self.rank = QComboBox(); self.rank.addItems(["8", "16", "32", "64"]); self.rank.setCurrentText("16")
        self.alpha = QComboBox(); self.alpha.addItems(["16", "32", "64", "128"]); self.alpha.setCurrentText("32")
        self.dropout = QDoubleSpinBox(); self.dropout.setRange(0, .5); self.dropout.setDecimals(3); self.dropout.setSingleStep(.01); self.dropout.setValue(.05)
        self.targets = QComboBox(); self.targets.addItem("全部线性层（效果优先）", "all-linear"); self.targets.addItem("仅注意力层（更省显存）", "attention")
        self.precision = QComboBox(); self.precision.addItems(["fp16", "bf16"]); self.precision.setCurrentText("bf16")  # 30 系是 Ampere,bf16 防 fp16 偶发 loss NaN
        row2.addWidget(QLabel("Rank")); row2.addWidget(self.rank)
        row2.addWidget(QLabel("Alpha")); row2.addWidget(self.alpha)
        row2.addWidget(QLabel("Dropout")); row2.addWidget(self.dropout)
        row2.addWidget(QLabel("LoRA层")); row2.addWidget(self.targets)
        row2.addWidget(QLabel("精度")); row2.addWidget(self.precision)
        form.addRow(row2)

        row3 = QHBoxLayout()
        self.save_steps = QSpinBox(); self.save_steps.setRange(10, 100000); self.save_steps.setValue(100); self.save_steps.setSingleStep(50)
        self.log_steps = QSpinBox(); self.log_steps.setRange(1, 10000); self.log_steps.setValue(1)
        self.seed = QSpinBox(); self.seed.setRange(0, 999999); self.seed.setValue(42)
        row3.addWidget(QLabel("每 N step 存档")); row3.addWidget(self.save_steps)
        row3.addWidget(QLabel("日志 step")); row3.addWidget(self.log_steps)
        row3.addWidget(QLabel("Seed")); row3.addWidget(self.seed)
        form.addRow(row3)
        layout.addWidget(param_box)

        out_box = QGroupBox("4. 输出与断点")
        grid = QGridLayout(out_box)
        self.output_dir = QLineEdit(str(ROOT / "outputs" / "novel_qwen3b_lora"))
        btn_out = QPushButton("选择目录"); btn_out.clicked.connect(lambda: self.pick_dir(self.output_dir))
        self.resume_dir = QLineEdit("")
        btn_resume = QPushButton("选择 checkpoint"); btn_resume.clicked.connect(lambda: self.pick_dir(self.resume_dir))
        grid.addWidget(QLabel("输出目录"), 0, 0); grid.addWidget(self.output_dir, 0, 1); grid.addWidget(btn_out, 0, 2)
        grid.addWidget(QLabel("断点续训（可空）"), 1, 0); grid.addWidget(self.resume_dir, 1, 1); grid.addWidget(btn_resume, 1, 2)
        layout.addWidget(out_box)

        controls = QHBoxLayout()
        self.btn_start = QPushButton("▶ 一键开始训练")
        self.btn_start.clicked.connect(self.start_training)
        self.btn_stop = QPushButton("■ 安全停止")
        self.btn_stop.clicked.connect(self.stop_training)
        self.btn_stop.setEnabled(False)
        btn_open = QPushButton("打开输出目录")
        btn_open.clicked.connect(lambda: self.open_folder(self.output_dir.text()))
        controls.addWidget(self.btn_start); controls.addWidget(self.btn_stop); controls.addWidget(btn_open)
        layout.addLayout(controls)

        self.gpu_label = QLabel("GPU：检测中……")
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.progress.setFormat("等待训练")
        layout.addWidget(self.gpu_label)
        layout.addWidget(self.progress)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(4000)
        font = QFont("Consolas"); font.setPointSize(9); self.log.setFont(font)
        layout.addWidget(self.log, 1)
        return page

    def _build_test_tab(self):
        page = QWidget(); layout = QVBoxLayout(page)
        form = QFormLayout()
        self.test_base = QLineEdit(str(DEFAULT_MODEL_DIR))
        self.test_adapter = QLineEdit(str(ROOT / "outputs" / "novel_qwen3b_lora" / "final_adapter"))
        b1 = QPushButton("选择基座"); b1.clicked.connect(lambda: self.pick_dir(self.test_base))
        b2 = QPushButton("选择 LoRA"); b2.clicked.connect(lambda: self.pick_dir(self.test_adapter))
        r1 = QHBoxLayout(); r1.addWidget(self.test_base); r1.addWidget(b1)
        r2 = QHBoxLayout(); r2.addWidget(self.test_adapter); r2.addWidget(b2)
        form.addRow("基座模型", r1); form.addRow("LoRA 目录", r2)
        layout.addLayout(form)

        layout.addWidget(QLabel("开头 / 提示词"))
        self.prompt = QTextEdit("夜雨落在青石巷里。沈砚推开客栈的门，发现本该空无一人的大堂中，坐着一个已经死了三年的人。\n")
        self.prompt.setMaximumHeight(150)
        layout.addWidget(self.prompt)
        opts = QHBoxLayout()
        self.max_new = QSpinBox(); self.max_new.setRange(32, 4096); self.max_new.setValue(512)
        self.temp = QDoubleSpinBox(); self.temp.setRange(0.1, 2.0); self.temp.setValue(.85); self.temp.setSingleStep(.05)
        self.top_p = QDoubleSpinBox(); self.top_p.setRange(.1, 1.0); self.top_p.setValue(.92); self.top_p.setSingleStep(.02)
        opts.addWidget(QLabel("生成 token")); opts.addWidget(self.max_new)
        opts.addWidget(QLabel("Temperature")); opts.addWidget(self.temp)
        opts.addWidget(QLabel("Top-p")); opts.addWidget(self.top_p)
        self.btn_generate = QPushButton("生成测试")
        self.btn_generate.clicked.connect(self.generate_text)
        opts.addWidget(self.btn_generate)
        layout.addLayout(opts)
        self.gen_output = QPlainTextEdit(); self.gen_output.setPlaceholderText("生成结果会显示在这里……")
        layout.addWidget(self.gen_output, 1)
        return page

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #17191d; color: #f0f0f0; }
            QWidget { background: #17191d; color: #f0f0f0; font-size: 14px; }
            QLabel { color: #f0f0f0; background: transparent; }
            QGroupBox { border: 1px solid #4a5160; border-radius: 8px; margin-top: 12px; padding: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #8fb8ff; }
            QTabWidget::pane { border: 1px solid #3c414a; }
            QTabBar::tab { background: #22262c; color: #cfcfcf; padding: 7px 18px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #2d66c3; color: #ffffff; }
            QProgressBar { color: #f0f0f0; }
            QCheckBox, QRadioButton { color: #f0f0f0; }
            QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #22262c; border: 1px solid #444b55; border-radius: 5px; padding: 5px; }
            QPushButton { background: #2d66c3; border: 0; border-radius: 6px; padding: 7px 12px; font-weight: 600; }
            QPushButton:hover { background: #3976d5; }
            QPushButton:disabled { background: #44484e; color: #888; }
            QProgressBar { border: 1px solid #444b55; border-radius: 5px; text-align: center; min-height: 20px; }
            QProgressBar::chunk { background: #3478d4; border-radius: 4px; }
        """)

    def append_log(self, text: str):
        self.log.appendPlainText(text.rstrip())
        sb = self.log.verticalScrollBar(); sb.setValue(sb.maximum())

    def pick_dir(self, edit: QLineEdit):
        start = edit.text() or str(ROOT)
        p = QFileDialog.getExistingDirectory(self, "选择目录", start)
        if p: edit.setText(p)

    def pick_data(self):
        if self.data_mode.currentData() == "sft":
            p, _ = QFileDialog.getOpenFileName(self, "选择 JSONL（也可以取消后手填目录）", self.data_path.text(), "JSONL (*.jsonl)")
            if p: self.data_path.setText(p)
        else:
            self.pick_dir(self.data_path)

    def on_mode_changed(self):
        if self.data_mode.currentData() == "sft":
            self.data_path.setText(str(ROOT / "data" / "sft"))
            self.overlap.setEnabled(False)
            self.data_hint.setText("SFT 支持 messages 格式，或 system/instruction/input/output。只对 assistant 输出计算 loss。")
        else:
            self.data_path.setText(str(ROOT / "data" / "novels"))
            self.overlap.setEnabled(True)
            self.data_hint.setText("建议：每本小说一个 TXT；程序会在每本末尾加 EOS，不会把两本书直接粘连。")

    def open_folder(self, path: str):
        p = Path(path); p.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.resolve())))

    def _start_process(self, op: str, args: list[str]):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "正在运行", "已有任务正在运行，请先结束。")
            return False
        self.operation = op
        self._save_settings()   # 开任务即落盘,GUI 崩了配置也不丢
        self.proc_buffer = ""
        self._prog_t0 = None; self._prog_m0 = 0; self._last_loss = None
        # 增量解码器:QProcess 分块读取会把多字节 UTF-8 字符切成两半,
        # 直接 decode 会把 tqdm 进度条的块字符毁成乱码;增量解码跨块拼接
        import codecs
        self._out_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(ROOT))
        env = QProcessEnvironment.systemEnvironment(); env.insert("PYTHONUNBUFFERED", "1")
        env.insert("TOKENIZERS_PARALLELISM", "false")
        # 钉死子进程输出为 UTF-8(否则中文 Windows 下走 cp936 代码页,日志乱码)
        env.insert("PYTHONUTF8", "1"); env.insert("PYTHONIOENCODING", "utf-8")
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.read_process_output)
        self.proc.finished.connect(self.process_finished)
        self.proc.start(sys.executable, args)
        return True

    def download_model(self):
        repo = self.model_id.text().strip(); dest = self.model_dir.text().strip()
        if not repo or not dest:
            return
        self.append_log(f"\n=== 下载模型：{repo} ===")
        if self._start_process("download", ["-m", "novel_trainer.download_model", "--repo", repo, "--dest", dest]):
            self.btn_download.setEnabled(False)

    def build_config(self):
        local_model = Path(self.model_dir.text().strip())
        model_source = str(local_model) if (local_model / "config.json").exists() else self.model_id.text().strip()
        mode = self.data_mode.currentData()
        return {
            "model_source": model_source,
            "output_dir": self.output_dir.text().strip(),
            "data": {
                "mode": mode,
                "path": self.data_path.text().strip(),
                "max_length": int(self.max_length.currentText()),
                "min_length": 256,
                "overlap": int(self.overlap.value()) if mode == "cpt" else 0,
                "clean_titles": bool(self.clean_titles.isChecked()),
                "min_response_tokens": 16,
            },
            "training": {
                "epochs": float(self.epochs.value()),
                "batch_size": int(self.batch.value()),
                "gradient_accumulation_steps": int(self.grad_acc.value()),
                "learning_rate": float(self.lr.text().strip()),
                "weight_decay": 0.0,
                "warmup_ratio": 0.03,
                "lr_scheduler": "cosine",
                "lora_rank": int(self.rank.currentText()),
                "lora_alpha": int(self.alpha.currentText()),
                "lora_dropout": float(self.dropout.value()),
                "target_modules": self.targets.currentData(),
                "precision": self.precision.currentText(),
                "save_steps": int(self.save_steps.value()),
                "logging_steps": int(self.log_steps.value()),
                "save_total_limit": 2,
                "max_grad_norm": 0.3,
                "seed": int(self.seed.value()),
                "resume_from_checkpoint": self.resume_dir.text().strip(),
            },
        }

    def start_training(self):
        try:
            cfg = self.build_config()
        except Exception as e:
            QMessageBox.critical(self, "参数错误", str(e)); return
        data_path = Path(cfg["data"]["path"])
        if not data_path.exists():
            QMessageBox.warning(self, "数据不存在", f"找不到：{data_path}"); return
        out = Path(cfg["output_dir"]); out.mkdir(parents=True, exist_ok=True)
        stop = out / ".stop_training"
        if stop.exists(): stop.unlink()
        config_path = out / "runtime_config.json"
        config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log.clear(); self.append_log("=== 开始训练 ===")
        self.append_log(f"配置：{config_path}")
        if self._start_process("train", ["-m", "novel_trainer.train", "--config", str(config_path)]):
            self.btn_start.setEnabled(False); self.btn_download.setEnabled(False); self.btn_stop.setEnabled(True); self.btn_generate.setEnabled(False)
            self.progress.setRange(0, 0); self.progress.setFormat("加载模型 / 准备数据……")

    def stop_training(self):
        if self.operation != "train" or not self.proc or self.proc.state() == QProcess.NotRunning:
            return
        out = Path(self.output_dir.text().strip()); out.mkdir(parents=True, exist_ok=True)
        (out / ".stop_training").write_text("stop", encoding="utf-8")
        self.append_log("[GUI] 已请求安全停止；当前 step 完成后会保存 final_adapter。")
        self.btn_stop.setEnabled(False)

    def read_process_output(self):
        if not self.proc:
            return
        chunk = self._out_decoder.decode(bytes(self.proc.readAllStandardOutput()))
        self.proc_buffer += chunk
        while "\n" in self.proc_buffer:
            line, self.proc_buffer = self.proc_buffer.split("\n", 1)
            # 先剥掉 CRLF 行尾的 \r(否则下面 split 会把整行变成空串),
            # 再取 tqdm 原地刷新(行内 \r)的最后一段
            self.handle_process_line(line.rstrip("\r").split("\r")[-1])

    def handle_process_line(self, line: str):
        # tqdm 用 \r 刷新不换行,子进程的 @@PROGRESS@@ 会粘在它后面
        # (如 "44.63s/it]@@PROGRESS@@{...}"):把前缀拆出来照常记日志,
        # JSON 部分照常喂进度条
        if "@@PROGRESS@@" in line and not line.startswith("@@PROGRESS@@"):
            prefix, _, rest = line.partition("@@PROGRESS@@")
            if prefix.strip():
                self.append_log(prefix)
            line = "@@PROGRESS@@" + rest
        if line.startswith("@@PROGRESS@@"):
            try:
                obj = json.loads(line[len("@@PROGRESS@@"):])
                if obj.get("done"):
                    self.progress.setRange(0, 100); self.progress.setValue(100); self.progress.setFormat("训练完成")
                    return
                if obj.get("loss") is not None:
                    self._last_loss = float(obj["loss"])   # on_log 事件:记住最新 loss
                micro = obj.get("micro"); mtotal = obj.get("micro_total")
                if micro is not None and mtotal:
                    # micro-batch 级进度(几秒一跳)+ 按速率估算剩余时间
                    import time as _t
                    now = _t.monotonic()
                    if self._prog_t0 is None or micro < self._prog_m0:
                        self._prog_t0, self._prog_m0 = now, micro
                    eta_txt = ""
                    if micro > self._prog_m0 and now > self._prog_t0:
                        rate = (micro - self._prog_m0) / (now - self._prog_t0)
                        remain = (mtotal - micro) / max(rate, 1e-9)
                        h, m = int(remain // 3600), int(remain % 3600 // 60)
                        eta_txt = f" · 约剩 {h}小时{m:02d}分" if h else f" · 约剩 {m}分钟"
                    pct = min(100, int(micro * 100 / mtotal))
                    self.progress.setRange(0, 100); self.progress.setValue(pct)
                    loss_txt = "" if self._last_loss is None else f" · loss {self._last_loss:.3f}"
                    step = int(obj.get("step", 0)); max_steps = int(obj.get("max_steps", 0))
                    self.progress.setFormat(
                        f"step {step}/{max_steps} · {pct}%{loss_txt}{eta_txt}")
                    return
                step = int(obj.get("step", 0)); max_steps = int(obj.get("max_steps", 0))
                if max_steps > 0:
                    pct = min(100, int(step * 100 / max_steps))
                    self.progress.setRange(0, 100); self.progress.setValue(pct)
                    loss_txt = "" if self._last_loss is None else f" · loss {self._last_loss:.4f}"
                    self.progress.setFormat(f"{step}/{max_steps} · {pct}%{loss_txt}")
            except Exception:
                self.append_log(line)
        elif line.startswith("@@GENERATED@@"):
            self.generated_buffer += line[len("@@GENERATED@@"): ]
        else:
            if self.operation == "generate" and self.generated_buffer:
                self.generated_buffer += "\n" + line
            else:
                self.append_log(line)

    def process_finished(self, code: int, status):
        self.read_process_output()
        if self.proc_buffer:
            self.handle_process_line(self.proc_buffer.rstrip("\r\n"))
            self.proc_buffer = ""
        op = self.operation
        self.append_log(f"=== 任务结束：{op}，退出码 {code} ===")
        self.btn_download.setEnabled(True); self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False); self.btn_generate.setEnabled(True)
        if op == "train" and code != 0:
            self.progress.setRange(0, 100); self.progress.setFormat("训练异常结束，请看日志")
        elif op == "download" and code == 0:
            QMessageBox.information(self, "下载完成", "模型已下载到本地目录。")
        elif op == "generate":
            if self.generated_buffer:
                self.gen_output.setPlainText(self.generated_buffer)
            elif code != 0:
                self.gen_output.setPlainText("生成失败，请切回训练页查看日志。")
        self.operation = ""

    def generate_text(self):
        base = self.test_base.text().strip(); adapter = self.test_adapter.text().strip(); prompt = self.prompt.toPlainText()
        if not Path(base).exists() or not Path(adapter).exists():
            QMessageBox.warning(self, "路径错误", "请先选择存在的基座模型和 LoRA 目录。")
            return
        self.generated_buffer = ""; self.gen_output.clear(); self.append_log("\n=== LoRA 测试生成 ===")
        args = ["-m", "novel_trainer.generate", "--base", base, "--adapter", adapter, "--prompt", prompt,
                "--max-new-tokens", str(self.max_new.value()), "--temperature", str(self.temp.value()), "--top-p", str(self.top_p.value())]
        if self._start_process("generate", args):
            self.btn_generate.setEnabled(False); self.btn_start.setEnabled(False); self.btn_download.setEnabled(False)

    def update_gpu_status(self):
        try:
            out = subprocess.check_output([
                "nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits"
            ], text=True, timeout=1.2, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)).strip().splitlines()[0]
            name, used, total, util, temp = [x.strip() for x in out.split(",")]
            self.gpu_label.setText(f"GPU：{name}  |  显存 {used}/{total} MiB  |  利用率 {util}%  |  {temp}°C")
        except Exception:
            self.gpu_label.setText("GPU：nvidia-smi 未检测到（训练前请确认 CUDA 驱动正常）")

    # ============ 表单配置持久化(记住上次的设置) ============
    def _persist_map(self):
        """(键, 控件, 类型)。断点续训 resume_dir 故意不持久化:
        它是一次性的,残留旧值会重演'无效存档目录'事故。"""
        return [
            ("model_id", self.model_id, "text"),
            ("model_dir", self.model_dir, "text"),
            ("data_mode", self.data_mode, "combo"),
            ("data_path", self.data_path, "text"),
            ("max_length", self.max_length, "combo"),
            ("overlap", self.overlap, "spin"),
            ("clean_titles", self.clean_titles, "check"),
            ("epochs", self.epochs, "dspin"),
            ("lr", self.lr, "text"),
            ("batch", self.batch, "spin"),
            ("grad_acc", self.grad_acc, "spin"),
            ("rank", self.rank, "combo"),
            ("alpha", self.alpha, "combo"),
            ("dropout", self.dropout, "dspin"),
            ("targets", self.targets, "combo"),
            ("precision", self.precision, "combo"),
            ("save_steps", self.save_steps, "spin"),
            ("log_steps", self.log_steps, "spin"),
            ("seed", self.seed, "spin"),
            ("output_dir", self.output_dir, "text"),
            ("test_base", self.test_base, "text"),
            ("test_adapter", self.test_adapter, "text"),
            ("prompt", self.prompt, "plain"),
            ("max_new", self.max_new, "spin"),
            ("temp", self.temp, "dspin"),
            ("top_p", self.top_p, "dspin"),
        ]

    def _load_settings(self):
        qs = QSettings("NovelAITrainer", "GUI")
        for key, w, kind in self._persist_map():
            v = qs.value("form/" + key)
            if v is None:
                continue
            try:
                if kind == "text":
                    w.setText(str(v))
                elif kind == "plain":
                    w.setPlainText(str(v))
                elif kind == "combo":
                    idx = w.findText(str(v))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                elif kind == "spin":
                    w.setValue(int(v))
                elif kind == "dspin":
                    w.setValue(float(v))
                elif kind == "check":
                    w.setChecked(str(v).lower() in ("true", "1"))
            except Exception:
                pass          # 单项坏值不影响其余项恢复

    def _save_settings(self):
        qs = QSettings("NovelAITrainer", "GUI")
        for key, w, kind in self._persist_map():
            try:
                if kind == "text":
                    qs.setValue("form/" + key, w.text())
                elif kind == "plain":
                    qs.setValue("form/" + key, w.toPlainText())
                elif kind == "combo":
                    qs.setValue("form/" + key, w.currentText())
                elif kind in ("spin", "dspin"):
                    qs.setValue("form/" + key, w.value())
                elif kind == "check":
                    qs.setValue("form/" + key, w.isChecked())
            except Exception:
                pass
        qs.sync()

    def closeEvent(self, event):
        self._save_settings()
        if self.proc and self.proc.state() != QProcess.NotRunning:
            r = QMessageBox.question(self, "任务运行中", "任务仍在运行。确定直接关闭 GUI 吗？训练进程可能被终止。")
            if r != QMessageBox.Yes:
                event.ignore(); return
            self.proc.kill(); self.proc.waitForFinished(1500)
        event.accept()


def main():
    app = QApplication(sys.argv)
    # Windows 上 Qt6 默认 windows11 原生风格:标签文字色走系统调色板,
    # 系统浅色模式下 = 黑字压深色背景,整个界面"看不清"。Fusion 完全吃 QSS。
    app.setStyle("Fusion")
    app.setApplicationName("Novel AI Trainer")
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
