# 工作流 Tab — 接入指南

新交付一个 Tab,叫「**工作流**」。把 `workflow_pipeline.py` 的整条流水线
可视化出来,集中开关 + 运行时高亮。

## 文件清单

| 文件 | 行数 | 用途 |
|---|---:|---|
| `workflow_panel.py` | 478 | 工作流 Tab 主体(单文件,纯 PyQt5,零业务逻辑改动) |
| `test_workflow_panel.py` | 240 | 31 项无头测试,全过 |

## 它做了什么

```
┌──────────────────────────────────────────────────┐
│  Phase 1 — 写章节前                              │  ← 蓝
│   ☐ 对话记忆注入       (即时)                    │
│   ☑ Canon 约束注入     (即时)                    │
│   ⊟ 审稿清单注入       (自动派生)                │
├──────────────────────────────────────────────────┤
│  Phase 2 — 写完后校验                            │  ← 琥珀
│   ☑ 字数检查           (即时)                    │
│   ☑ 章末钩子           (即时)                    │
│   ☑ Canon 稽核         (+1 AI)                   │
│   ☐ 节奏打分           (+1 AI)                   │
│   ☐ 人设打分           (+1 AI)                   │
├──────────────────────────────────────────────────┤
│  Phase 3 — 通过后链式                            │  ← 绿
│   ☑ Canon 自动抽取     (+1 AI)                   │
│   ☑ 生成章节摘要       (+1 AI)                   │
│   ⊟ 链式下一章         (运行时决定)              │
└──────────────────────────────────────────────────┘
```

每张卡片:**[运行指示灯] [开关] [步骤名] [阶段徽章] [成本徽章] [描述]**

- **集中开关** — 卡片上的 checkbox 直接驱动散落在 对话记忆 / Canon 设定 /
  生成控制 三个 Tab 里的对应 QCheckBox。**双向同步**:从其他 Tab 改也会
  反映到这里。
- **运行时高亮** — 章节生成时,正在执行的卡片背景变黄、运行灯亮琥珀色,
  完成后短暂显示 ✓ / ✗。底部状态条同步显示「正在执行: xxx」。
- **批量按钮** — 顶部「全开 / 全关 / 🔄 同步状态」三个快捷键。

技术实现:**纯 monkey-patch,不改 `workflow_pipeline.py` 一行代码。**

---

## novel_ai.py 修改清单(共 5 处,新增 ~12 行)

### 改动 A:顶部 import(第 65 行附近,跟其它 try-import 平级)

在已有的 `WORKFLOW_AVAILABLE`、`LIFESPAN_LOOPS_AVAILABLE` 那一组下面追加:

```python
# ---- 工作流可视化面板(新增) ----
try:
    from workflow_panel import WorkflowPanel
    WORKFLOW_PANEL_AVAILABLE = True
except ImportError:
    WORKFLOW_PANEL_AVAILABLE = False
```

### 改动 B:MainWindow Tab 注册(第 2935 行附近)

旧:

```python
        self.tab_canon = CanonGuard()
        self.tab_skills = SkillLibrary()
        self.tab_generation = GenerationControl()
        self.tab_editor = ChapterEditor()
        self.tab_cover = CoverGeneration()
        for w, n in [
            (self.tab_settings, "创作设置"),
            ...
            (self.tab_skills, "技能库"),
            (self.tab_generation, "生成控制"),
            ...
        ]:
            self.tabs.addTab(w, n)
```

新(在「技能库」与「生成控制」之间插入「工作流」):

```python
        self.tab_canon = CanonGuard()
        self.tab_skills = SkillLibrary()
        self.tab_generation = GenerationControl()
        self.tab_editor = ChapterEditor()
        self.tab_cover = CoverGeneration()

        tab_list = [
            (self.tab_settings, "创作设置"),
            (self.tab_outline, "故事大纲"),
            (self.tab_memory, "对话记忆"),
            (self.tab_canon, "Canon 设定"),
        ]
        # 寿元/伏笔(若启用)
        if getattr(self, "tab_lifespan", None) is not None:
            tab_list.append((self.tab_lifespan, "寿元/伏笔"))

        tab_list.append((self.tab_skills, "技能库"))

        # ---- 新增:工作流 Tab(集中开关 + 运行时高亮) ----
        # 必须在 workflow 已实例化、其它依赖 Tab 已构造之后
        if WORKFLOW_PANEL_AVAILABLE:
            self.tab_workflow = None  # 占位,真正实例化放到 __init__ 末尾
        # ----------------------------------------------------

        tab_list += [
            (self.tab_generation, "生成控制"),
            (self.tab_editor, "章节编辑器"),
            (self.tab_cover, "小说封面生成"),
        ]
        for w, n in tab_list:
            self.tabs.addTab(w, n)
```

### 改动 C:MainWindow.__init__ 末尾(workflow 装配段后)

在已有的:

```python
        if WORKFLOW_AVAILABLE:
            _patch_main_window(self.__class__)
            self.workflow = GenerationWorkflow(self)
            self.workflow.setup_default_steps()
        else:
            self.workflow = None
```

下面追加:

```python
        # ---- 工作流可视化 Tab(必须在 workflow.setup_default_steps 之后) ----
        if WORKFLOW_PANEL_AVAILABLE and self.workflow is not None:
            self.tab_workflow = WorkflowPanel(mw=self)
            self.tab_workflow.request_log.connect(
                lambda m, lv: self.tab_generation.log(m, lv))
            # 插到「技能库」之后、「生成控制」之前
            insert_idx = self.tabs.indexOf(self.tab_generation)
            if insert_idx < 0:
                insert_idx = self.tabs.count()
            self.tabs.insertTab(insert_idx, self.tab_workflow, "工作流")
        else:
            self.tab_workflow = None
```

### 改动 D:test_v6.py 的 Tab 数检查

`test_v6.py` Test 1 现在期望 8(或 9)个 Tab。新增「工作流」之后变 9(或 10)。

```python
expected = ["创作设置", "故事大纲", "对话记忆", "Canon 设定"]
if getattr(mw, "tab_lifespan", None) is not None:
    expected.append("寿元/伏笔")
expected.append("技能库")
if getattr(mw, "tab_workflow", None) is not None:
    expected.append("工作流")
expected += ["生成控制", "章节编辑器", "小说封面生成"]
```

### 改动 E(可选):序列化

工作流 Tab **没有自己的持久化数据** — 所有开关都同步到上游 Tab,
项目存档时上游 Tab 的状态自然会被保存。所以 save_project / open_project
**不需要改**。

---

## 测试

```bash
# 单元测试(31 项无头)
QT_QPA_PLATFORM=offscreen python test_workflow_panel.py

# 期待
测试总数: 31   通过: 31   失败: 0
✅ 全部通过
```

实机跑 `python novel_ai.py`,你应该看到 Tab 条上多一个「工作流」,点进去
看到 11 张卡片整齐排列,每张都能勾选。开了之后再去「生成控制」Tab 看,
对应的复选框跟着动了,反之亦然 — 这就是双向同步生效的样子。

---

## 设计决定备忘

1. **不改 `workflow_pipeline.py`** — 通过 monkey-patch `step.run` 注入运行时
   钩子,代码层面零侵入。卸载时只要不再 `install_runtime_hooks` 就行。

2. **没有独立配置** — Workflow Tab 不存自己的状态,而是当所有上游开关
   的"中央仪表盘"。这样不会出现两边数据漂移。

3. **派生 step / 运行时 step 是只读的** —
   - `critique_rules_inject` 由「节奏打分」与「人设打分」自动派生
   - `next_chapter` 由批量生成的运行时状态决定
   - 这两张卡片的复选框被禁用,鼠标悬停时显示 tooltip 说明原因

4. **运行时高亮的边界** — 单步是否"成功"很难界定(POST_WRITE 步骤
   往 ctx.issues 塞东西也算正常路径)。所以这里**单步只显示 ✓**,
   重写 / retry 等"整体失败"由顶部状态条的颜色表达,不在单卡片上反映。

5. **小屏适配** — 整个面板裹在 QScrollArea 里,Tab 高度不够时可滚动,
   不会挤压。

---

## 未做(下次再说)

- 拖拽重排 Step 顺序 — 当前固定按 priority,改顺序需要重写 StepRegistry
- Step 自定义参数(比如调节奏阈值的 7 改成 8) — 现在阈值写在 Step 类里
- 多 AI 路由 Step(每条 Step 选不同模型) — 暂时所有 Step 都用同一个浏览器
