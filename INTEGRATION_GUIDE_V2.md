# 寿元台账 + 长期伏笔 + 研究报告技能 — 完整接入指南 (v2)

本次交付一共 3 个新模块、3 个测试文件，共 257 项断言全过。

## 文件清单

| 文件 | 行数 | 用途 |
|---|---:|---|
| `lifespan_loops_steps.py` | 487 | 寿元台账 + 长期伏笔 — Step 类、安装器、存档接口 |
| `lifespan_loops_panel.py` | 380 | 寿元台账 + 长期伏笔 — UI 面板（独立 Tab） |
| `research_report_skills.py` | 282 | 研究报告 §6 的 4 个 AI 模板 + 1 个 auto_match 配套 = 5 条出厂技能 |
| `test_lifespan_loops.py` | 528 | Step 测试（68 断言） |
| `test_lifespan_loops_panel.py` | 360 | UI 测试（66 断言，无头 Qt） |
| `test_research_report_skills.py` | 320 | 出厂技能测试（123 断言） |

## 1. novel_ai.py 修改清单（约 25 行新增）

### 改动 A：顶部 import（第 65 行附近）

```python
# ---- 模块化生成流水线(v7 新增,可选) ----
try:
    from workflow_pipeline import (
        GenerationWorkflow, StepRegistry, _patch_main_window
    )
    WORKFLOW_AVAILABLE = True
except ImportError:
    WORKFLOW_AVAILABLE = False

# ---- 寿元台账 + 长期伏笔检查（新增） ----
try:
    from lifespan_loops_steps import LifespanLoopsExtension
    from lifespan_loops_panel import LifespanLoopsPanel
    LIFESPAN_LOOPS_AVAILABLE = True
except ImportError:
    LIFESPAN_LOOPS_AVAILABLE = False

# ---- 研究报告出厂技能（新增） ----
try:
    from research_report_skills import install_into as _install_research_skills
    RESEARCH_SKILLS_AVAILABLE = True
except ImportError:
    RESEARCH_SKILLS_AVAILABLE = False
```

### 改动 B：MainWindow Tab 注册（第 2935 行附近）

旧：

```python
        self.tab_canon = CanonGuard()
        self.tab_skills = SkillLibrary()
        self.tab_generation = GenerationControl()
        self.tab_editor = ChapterEditor()
        self.tab_cover = CoverGeneration()
        for w, n in [
            (self.tab_settings, "创作设置"),
            (self.tab_outline, "故事大纲"),
            (self.tab_memory, "对话记忆"),
            (self.tab_canon, "Canon 设定"),
            (self.tab_skills, "技能库"),
            (self.tab_generation, "生成控制"),
            (self.tab_editor, "章节编辑器"),
            (self.tab_cover, "小说封面生成"),
        ]:
            self.tabs.addTab(w, n)
```

新（在 Canon 设定 之后插入 寿元/伏笔 Tab，让"约束类"Tab 集中在前段）：

```python
        self.tab_canon = CanonGuard()
        self.tab_skills = SkillLibrary()
        # ---- 新增 ----
        if LIFESPAN_LOOPS_AVAILABLE:
            self.tab_lifespan = LifespanLoopsPanel(mw=self)
        else:
            self.tab_lifespan = None
        # --------------
        self.tab_generation = GenerationControl()
        self.tab_editor = ChapterEditor()
        self.tab_cover = CoverGeneration()

        tab_list = [
            (self.tab_settings, "创作设置"),
            (self.tab_outline, "故事大纲"),
            (self.tab_memory, "对话记忆"),
            (self.tab_canon, "Canon 设定"),
        ]
        # ---- 新增 ----
        if self.tab_lifespan is not None:
            tab_list.append((self.tab_lifespan, "寿元/伏笔"))
        # --------------
        tab_list += [
            (self.tab_skills, "技能库"),
            (self.tab_generation, "生成控制"),
            (self.tab_editor, "章节编辑器"),
            (self.tab_cover, "小说封面生成"),
        ]
        for w, n in tab_list:
            self.tabs.addTab(w, n)
```

注：因为 `LifespanLoopsPanel(mw=self)` 需要先有 `self`，所以这段必须在 `MainWindow.__init__` 已实例化之后执行 — 它本来就是。

### 改动 C：MainWindow.__init__ 末尾（第 2867 行附近）

旧：

```python
        # ---- v7:模块化生成流水线 ----
        if WORKFLOW_AVAILABLE:
            _patch_main_window(self.__class__)
            self.workflow = GenerationWorkflow(self)
            self.workflow.setup_default_steps()
        else:
            self.workflow = None
```

新：

```python
        # ---- v7:模块化生成流水线 ----
        if WORKFLOW_AVAILABLE:
            _patch_main_window(self.__class__)
            self.workflow = GenerationWorkflow(self)
            self.workflow.setup_default_steps()
        else:
            self.workflow = None

        # ---- 寿元台账 + 长期伏笔（新增） ----
        if LIFESPAN_LOOPS_AVAILABLE:
            LifespanLoopsExtension.install(self)
            # 把已初始化的数据同步到 UI
            if self.tab_lifespan is not None:
                self.tab_lifespan.sync_from_mw()
                # 用户在面板按"保存配置"时，触发主程序保存项目
                self.tab_lifespan.request_save.connect(self.save_project)
                self.tab_lifespan.request_log.connect(
                    lambda m, lv: self.tab_generation.log(m, lv)
                )

        # ---- 研究报告出厂技能（新增） ----
        if RESEARCH_SKILLS_AVAILABLE:
            n_added = _install_research_skills(self.tab_skills)
            if n_added:
                self.tab_generation.log(
                    f"📚 已加载研究报告出厂技能 {n_added} 条", "info")
```

### 改动 D：save_project（第 4762 行附近）

旧 `d = {...}` 字典里追加一行：

```python
            "conv_slots": self.tab_generation.conv_switcher.serialize_for_save(),
            # ---- 新增 ----
            "lifespan_loops": (
                self.tab_lifespan.serialize_for_save()
                if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None)
                else {}
            ),
            # --------------
```

### 改动 E：open_project（第 4678 行附近）

在 conv_slots 还原之后追加：

```python
            if d.get("conv_slots"):
                self.tab_generation.conv_switcher.load_from_dict(d["conv_slots"])
            # ---- 新增 ----
            if (LIFESPAN_LOOPS_AVAILABLE and self.tab_lifespan is not None
                    and d.get("lifespan_loops")):
                self.tab_lifespan.load_from_dict(d["lifespan_loops"])
            # --------------
```

## 2. test_v6.py 调整（Test 1 的 Tab 数）

原本 Test 1 检查 8 个 Tab，现在条件性变成 9 个：

```python
# Test 1 — Tab 顺序
expected = ["创作设置", "故事大纲", "对话记忆", "Canon 设定"]
if getattr(mw, "tab_lifespan", None) is not None:
    expected.append("寿元/伏笔")
expected += ["技能库", "生成控制", "章节编辑器", "小说封面生成"]

actual = [mw.tabs.tabText(i) for i in range(mw.tabs.count())]
assert actual == expected, f"Tab 顺序错: 实际 {actual}"
print(f"  ✓ Tab 顺序正确（共 {len(actual)} 个）")
```

## 3. 各 Tab 怎么用

### 寿元/伏笔 Tab

打开 NovelAI 后切到「寿元/伏笔」Tab：

1. **寿元台账**：勾「启用」→ 改起始日数（默认 8760 ≈ 24 年）→ 调阈值 → 点「💾 保存配置」
2. **长期伏笔检查**：勾「启用」→ 在下方录入 ID/描述/抛章/关键词 → 点「➕ 添加」
3. **关键词作用**：当章节正文出现关键词时，自动把该伏笔的 `last_seen_ch` 刷新为本章号 — 这就是"伏笔不被遗忘"的自动追踪机制
4. **保存配置**会把 UI 状态写回 `mw.lifespan_ledger` / `mw.open_loops`，并触发整个项目存盘

### 研究报告技能

切到「技能库」Tab，会看到列表底部多了 5 条新技能：

| 技能名 | 触发 | 默认 | 用法 |
|---|---|---|---|
| 细纲扩展（写章前） | manual | 开 | 把卷目标 + 前情 + 必须完成事 + 角色情绪 + 不可新增设定 一起塞到选中文本，然后右键调用 |
| 桥段扩写（局部 600-1000 字） | manual | 开 | 把 5 个 beat（压迫/误判/反转/爽点/下一章悬念）+ 人物口吻要求塞到选中文本，调用，结果会替换选中区 |
| 一致性校验（红黄绿三档） | after_chapter | 关 | 开了之后每章 +1 次 AI 调用，输出三档审校到日志 |
| 短文本生成（3 版备选） | manual | 开 | 章尾钩 / 高潮片段 / 宣传文案，给 3 版备选 |
| 高潮场面自动重写 | auto_match | 关 | 开了之后，章节里出现"对峙\|对决\|宣战\|审判\|登台\|登顶\|拔剑\|当众\|揭穿\|宣判\|公开\|当面对质"任意一个时自动给出重写候选 |

## 4. 测试

```bash
# 全跑
python test_lifespan_loops.py
QT_QPA_PLATFORM=offscreen python test_lifespan_loops_panel.py
python test_research_report_skills.py
```

预期结果：

```
test_lifespan_loops.py        : 68/68  ✅
test_lifespan_loops_panel.py  : 66/66  ✅
test_research_report_skills.py: 123/123 ✅
合计                          : 257/257 ✅
```

## 5. 默认行为

- 寿元台账：默认 `enabled=False`，普通项目不感知
- 长期伏笔：默认 `enabled=False`，列表为空
- 一致性校验技能：默认 `enabled=False`（每章 +1 AI 调用）
- 高潮自动重写技能：默认 `enabled=False`（auto_match 误触可能多）
- 细纲扩展 / 桥段扩写 / 短文本生成：默认 `enabled=True`（手动触发不耗 token）

## 6. 数据流

```
[用户在面板点保存]
    ↓
panel.sync_to_mw()
    ↓ 写入
mw.lifespan_ledger / mw.open_loops (dict)
    ↓ 在生成下一章时
LifespanInjectStep (PRE_WRITE)  → 注入 prompt
    ↓ AI 返回章节
LifespanAuditStep (POST_WRITE)  → 解析章末 [寿元结算] / 调 AI 抽取 / 兜底
OpenLoopsCheckStep (POST_WRITE) → 关键词检测 + 冻结告警
    ↓ 章节通过校验入库
panel.refresh_status() 刷新右上角"剩余寿元"显示（建议在
    _on_response_received 章节入库后调一次）
```

## 7. 可选优化（下一轮）

- `panel.refresh_status()` 在每章生成完后自动调用 — 在 `_on_response_received` 的 chapter 分支末尾加一行 `if self.tab_lifespan: self.tab_lifespan.refresh_status()`
- 寿元历史的折线图（用 QtCharts 或简易 QGraphicsScene）
- 伏笔检查也支持 AI 自动抽取本章新伏笔追加到列表
- 技能库的 `_refresh_list` 在 install_into 之后调用是否真的能让 UI 立即看到新技能？需要在真机上验证一次（headless 测过 hook 调用，但实际刷新逻辑取决于 SkillLibrary 内部实现）

## 8. 不影响什么

- 不改 `workflow_pipeline.py`
- 不改 `_on_response_received`
- 不改 `_send_to_ai`
- 不改 PROMPTS 字典
- 不改其他 Tab 类
- 不改既有 4 条出厂技能
