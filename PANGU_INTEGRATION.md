# 盘古超级系统 · 集成指南

把【盘古 V1.0 真正完整版】(29 套网文创作系统融合)接入到 `novel_ai.py`。

设计原则:**零侵入**——你只在 `novel_ai.py` 加 3 行就完成。原 5431 行代码一行都不动。

---

## 一、新增的文件

把以下 4 个文件放到 `novel_ai.py` 所在目录:

| 文件 | 作用 | 大小 |
|------|------|------|
| `pangu_system.py` | 核心引擎(铁律、风格库、模式切换、质检、本地禁用词扫描) | ~25 KB |
| `pangu_patch.py` | 零侵入安装器,把现有 PROMPTS 字典就地套上盘古铁律 | ~4 KB |
| `pangu_full_spec.md` | 完整 3.5 万字 spec(供 `/帮助` 指令或人工查阅) | ~48 KB |
| `test_pangu_system.py` + `test_pangu_patch.py` | 单元测试(53 个,可选) | ~14 KB |

---

## 二、修改 `novel_ai.py`(只加 6 行)

找到 `PROMPTS = { ... }` 字典定义**结束的那一行**(大概在第 450 行附近,
就是 `"critique_character": ...` 后面的右大括号 `}`)。

**在右大括号下面紧接着加这一段**:

```python
# ---- 盘古超级系统(新增) ----
try:
    from pangu_patch import install_pangu
    install_pangu(globals())  # 就地把 PROMPTS 字典套上盘古铁律
    PANGU_AVAILABLE = True
except ImportError:
    PANGU_AVAILABLE = False
```

完了。这就是全部改动。

---

## 三、它做了什么

`install_pangu(globals())` 在导入时**就地替换** `PROMPTS` 字典里这 6 个键的值:

| 原键 | 处理 |
|------|------|
| `chapter` | 头部加盘古铁律(禁用词/感官/压爆震/智商防火墙),尾部加输出格式(钩子/爽点/伏笔/三选一) |
| `golden_three` | 头部加铁律,尾部加【黄金三章公式】(绝境羞辱→金手指激活→首次反转)+ 循环爽点单元 |
| `outline_full` | 头部加铁律,尾部加【矛盾螺旋大纲规范】(主要矛盾陈述/人物弧光三阶段/P1-P7 标注) |
| `outline_part` | 同上 |
| `ai_optimize` | 替换为【雕刻家模式】:先删再改、能砍的不改、能用动作的不用形容词 |
| `creative_inspiration` | 加上轻量约束:反光/影子/另一个自己题材禁用 + 情绪直给 |

**保持不变**(因为它们是工具型 prompt,不该被盘古铁律污染):

- `title`(取书名)
- `intro`(写简介)
- `chapter_summary` / `character_extract` / `long_term_extract`(对话记忆维护)
- `canon_audit` / `canon_extract` / `critique_rhythm` / `critique_character`(已有的防崩/审稿系统)

**原 `PROMPTS["chapter"].format(...)` 不需要改任何参数**——所有 `{title}`、`{chapter_num}`、
`{target_words}`、`{genre}` 等占位符都被原封不动保留。

---

## 四、可选:在 GUI 加一个开关

如果想让用户在【创作设置】里能勾选启停盘古,在 `CreationSettings.__init__` 里
(放在"AI 配置"分组下面)加一组 checkbox。

**位置**:`CreationSettings.__init__` 里,`ai_layout.addWidget(self.delay_check)` 之后。

```python
# ---- 盘古系统开关 ----
self.pangu_check = QCheckBox("启用【盘古超级系统】(禁用词过滤 + 感官铁律 + 压爆震)")
self.pangu_check.setChecked(True)  # 默认开
self.pangu_check.setStyleSheet("color:#1a4480;font-weight:bold;")
self.pangu_check.setToolTip(
    "勾选后,每章正文 prompt 会自动套上盘古铁律:\n"
    "• 几百个禁用词强制过滤(顿时/连忙/眼神深邃等)\n"
    "• 视/听/触三感必须齐全\n"
    "• 压 70%+爆 5%+震 25% 情绪曲线\n"
    "• 智商防火墙(防止角色降智)\n"
    "• 黄金三章公式(第 1-3 章强制)\n"
    "取消勾选则完全回到原版行为。"
)
ai_layout.addWidget(self.pangu_check)
```

然后在 `CreationSettings.save_settings()` 里加一行:
```python
s.setValue("pangu_enabled", self.pangu_check.isChecked())
```

最后在 `MainWindow` 的某个生成入口(比如 `start_generation` / `gen_outline_all`)
开头加一行运行时切换:

```python
def _refresh_pangu(self):
    """根据 GUI 勾选状态决定是否套盘古"""
    if not PANGU_AVAILABLE:
        return
    from pangu_patch import install_pangu, uninstall_pangu, is_installed
    want = self.settings.pangu_check.isChecked()
    cur = is_installed(globals())
    if want and not cur:
        install_pangu(globals())
    elif not want and cur:
        uninstall_pangu(globals())
```

然后在 `gen_outline_all` / `gen_golden_three` / `start_generation` 第一行调用 `self._refresh_pangu()` 即可。

---

## 五、新增能力(可选地接入到现有按钮)

`pangu_system.py` 还提供了一些**独立调用**的功能,你可以在 GUI 加按钮触发:

### 5.1 本地禁用词扫描(0 token,纯字符串匹配)

每章生成完毕,在保存前预检一遍:

```python
from pangu_system import PanguEngine
engine = PanguEngine()
result = engine.quick_chapter_lint(chapter_text)
# {'score': 86, 'pass': True, 'issues': ['出现禁用词: 顿时×2, 似乎×1', '长句(>25 字)数量: 3 句'], 'stats': {...}}
if not result['pass']:
    self.log(f"⚠️ 本地预检 {result['score']} 分,问题:{'; '.join(result['issues'])}")
```

这一步**不调 AI**,纯 Python 字符串匹配,毫秒级。

### 5.2 风格库自动匹配(根据题材/灵感关键词)

```python
from pangu_system import get_default_engine
engine = get_default_engine()
report = engine.build_style_report("退婚 战神 都市 神豪")
# 🎯 风格匹配报告(关键词: 退婚 战神 都市 神豪)
# 1. 主风格: 周星驰无厘头 | 辅风格: 战神赘婿型 | 点缀: 龙王型 | 女角色基调: 东北/川渝 | 适合平台: 番茄
# 2. 主风格: 神豪系统型 | 辅风格: 战神赘婿型 | 点缀: 金钱碾压 | 女角色基调: 东北/广东 | 适合平台: 番茄
```

可在【创意灵感】文本框旁加一个"🎯 风格匹配"按钮调用它。

### 5.3 四模式快捷指令

```python
prompt = engine.build_mode_switch_prompt("建筑师")  # 或 dreamweaver/alchemist/sculptor
self._send_to_ai(prompt)
```

可在工具栏加四个按钮:🏗️建筑师 / 💭造梦师 / ⚗️炼金术士 / 🗿雕刻家。

### 5.4 30 项质检(发给 AI 做严格审稿)

```python
prompt = engine.build_quality_check_prompt(chapter_text)
result_json = self._send_to_ai(prompt)  # AI 返回 JSON
# {"score": 92, "pass": false, "failed_items": [11, 15], "advice": "..."}
```

### 5.5 螺旋阶段诊断(P1-P7)

```python
prompt = engine.build_spiral_diagnose_prompt(chapter_text)
# AI 返回 {"phase": "P3", "emotion_value": 78, "next_phase": "P4", "advice": "..."}
```

可对应到 README 的【新增能力】快捷栏按钮。

---

## 六、回归测试

新增的两个测试文件可直接跑:

```bash
python -m unittest test_pangu_system.py -v   # 38 个测试
python -m unittest test_pangu_patch.py -v    # 15 个测试
```

53 个都过,才能保证集成不破坏现有功能。

为了**严格验证不破坏现有的 novel_ai.py**,可以再跑一遍仓库已有的:

```bash
python test_v6.py
python test_full_integration.py
python test_workflow_panel.py
python test_lifespan_loops.py
python test_research_report_skills.py
python test_quick_bar.py
```

---

## 七、回滚

如果发现问题想立刻关掉:

**方式一**:在 `novel_ai.py` 那 6 行 try/except 改成:
```python
PANGU_AVAILABLE = False  # 关闭
```

**方式二**:运行时调用:
```python
from pangu_patch import uninstall_pangu
uninstall_pangu(globals())
```
`PROMPTS` 字典会被恢复到加载时的原版。

**方式三**:直接删掉 `pangu_system.py` 和 `pangu_patch.py` 两个文件,
那 6 行 try/except 会自然走 `ImportError` 分支,`PROMPTS` 一开始就没被改过。

---

## 八、git 提交建议

```bash
git add pangu_system.py pangu_patch.py pangu_full_spec.md \
        test_pangu_system.py test_pangu_patch.py \
        PANGU_INTEGRATION.md
git add novel_ai.py  # 只有 6 行新增
git commit -m "feat: 接入【盘古超级系统 V1.0】

- 新增 pangu_system.py:核心引擎(铁律/风格库/模式切换/质检/本地禁用词扫描)
- 新增 pangu_patch.py:零侵入安装器(就地包裹现有 PROMPTS)
- 新增 pangu_full_spec.md:完整 29 系统融合 spec(供 /帮助 调用)
- novel_ai.py 仅新增 6 行 try/except 启用,行为可一键回滚
- 53 个新单元测试全过

盘古会自动给每个章节 prompt 加上:
- 几百个禁用词强制过滤
- 视/听/触三感铁律
- 压 70%+爆 5%+震 25% 情绪曲线
- 智商防火墙(防角色降智)
- 黄金三章公式(1-3 章强制:绝境羞辱→金手指→首次打脸)
- 矛盾螺旋大纲规范(P1-P7 七阶段)
- 输出格式尾(钩子/爽点/伏笔/三选一)
"
git push
```

---

## 九、跟现有模块的协同

盘古与仓库已有的扩展**完全兼容**,不需要任何特殊处理:

| 已有扩展 | 与盘古的关系 |
|---------|-------------|
| `workflow_pipeline.py` | 流水线步骤层,盘古在 prompt 层。互不干扰,可叠加。 |
| `workflow_panel.py` | UI 面板。可选地把"风格匹配"/"质检"/"模式切换"做成 panel 里的快捷按钮。 |
| `lifespan_loops_steps.py` | 寿元台账,管伏笔时序。盘古的【伏笔分级喂养】是它的强约束规范。 |
| `research_report_skills.py` | 出厂技能。可把盘古的【30 项质检】注册为一项新技能。 |
| `license_guard.py` | 许可检查。与盘古无关,各自工作。 |
| 现有 `canon_audit` / `critique_*` prompt | **保留不动**——这些是已有的 AI 审稿管线,盘古不重复定义。 |

---

## 十、版本号

- 盘古引擎版本:`PanguEngine.VERSION = "1.0"`
- 来自《盘古真正完整版 V1.0》(2025-11 文档,融合 29 套子系统)
- 集成包版本:`v1.0.0`(本次新增)
