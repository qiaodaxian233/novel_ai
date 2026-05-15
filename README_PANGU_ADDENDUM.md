# 🪐 盘古·终极融合写作系统 (V1.0 集成版)

> **请把本节加到现有 `README.md` 的"九、合规说明"前面,作为新的第八节或独立第十节。**

---

## 🪐 盘古·终极融合写作系统 (新增能力)

[#-盘古·终极融合写作系统-新增能力](#-盘古·终极融合写作系统-新增能力)

本工程已集成【**盘古·终极融合写作系统 V1.0 真正完整版**】——
融合了 29 套国内主流网文创作系统精华的写作引擎,一次性给所有章节 prompt 套上铁律:

- **几百个禁用词强制过滤**:`顿时 / 连忙 / 嘴角勾起一抹 / 眼神深邃 / 行云流水 / 心下了然 / 仿佛 / 似乎...` 等 AI 高频废话词,生成正文里**绝对不出现**。
- **感官铁律**:每章必须有视觉×1 + 听觉×1 + 触/嗅/味×1 的具体细节,分散植入。
- **压爆震情绪曲线**:压 70%(日常蓄力)+ 爆 5%(最短句最少词)+ 震 25%(沉默/细节让读者消化)。每 300 字至少一个情绪点。
- **智商防火墙**:任何智商≥5 的角色绝不"主动相认你也穿了吧?"、不暴露核心秘密、不在公共场合说现代词汇。
- **黄金三章公式**(第 1-3 章强制):第 1 章绝境+羞辱 → 第 2 章金手指激活 → 第 3 章首次反转打脸。
- **矛盾螺旋大纲**:大纲必须给出主要矛盾/人物弧光三阶段/螺旋 P1-P7 阶段标注。
- **输出格式尾**:每章末尾自动追加【断章钩子】(强度≥8/10)+【本章爽点】+【伏笔状态】+【下一章三选一】。
- **四模式切换**:🏗️ 建筑师(搭骨架) / 💭 造梦师(写正文) / ⚗️ 炼金术士(破局) / 🗿 雕刻家(打磨)。

### 怎么开/关

默认**已开启**。任何时候想完全关掉、回到原版行为,把 `novel_ai.py` 末尾这段:

```python
try:
    from pangu_patch import install_pangu
    install_pangu(globals())
    PANGU_AVAILABLE = True
except ImportError:
    PANGU_AVAILABLE = False
```

改成:
```python
PANGU_AVAILABLE = False  # 关闭盘古
```

或者直接删掉 `pangu_system.py` / `pangu_patch.py` 两个文件——
`try/except ImportError` 会自动走旁路,PROMPTS 一字未改。

### 本地禁用词预检(0 token)

每章生成完后,可以在保存前用纯 Python 扫一遍禁用词,**不消耗任何 token**:

```python
from pangu_system import PanguEngine
result = PanguEngine().quick_chapter_lint(chapter_text)
# {'score': 86, 'pass': True, 'issues': ['出现禁用词: 顿时×2, 似乎×1'], 'stats': {...}}
```

返回:总分(0-100)、是否合格、问题列表、字数/长句/段落统计。

### 风格库自动匹配

输入题材/灵感关键词,自动选主风格+辅风格+点缀风格+女角色基调+平台:

```python
from pangu_system import get_default_engine
print(get_default_engine().build_style_report("退婚 战神 都市 神豪"))
# 🎯 风格匹配报告
# 1. 主风格: 周星驰无厘头 | 辅风格: 战神赘婿型 | 点缀: 龙王型 | 女角色: 东北/川渝 | 平台: 番茄
# 2. 主风格: 神豪系统型 | 辅风格: 战神赘婿型 | 点缀: 金钱碾压 | 女角色: 东北/广东 | 平台: 番茄
```

风格库覆盖 19 个题材关键词组,可在【创意灵感】文本框旁加一个"🎯 风格匹配"按钮触发。

### 四模式快捷指令

```python
from pangu_system import get_default_engine
engine = get_default_engine()
prompt = engine.build_mode_switch_prompt("建筑师")   # 大纲卡住时用
prompt = engine.build_mode_switch_prompt("造梦师")   # 写正文(默认)
prompt = engine.build_mode_switch_prompt("炼金术士") # 彻底卡文破局
prompt = engine.build_mode_switch_prompt("雕刻家")   # 改稿打磨
```

### 30 项质检 + 螺旋诊断

```python
engine = get_default_engine()
# 发给 AI 做严格 30 项审稿
qc_prompt = engine.build_quality_check_prompt(chapter_text)
# 返回 {"score": 92, "pass": false, "failed_items": [11, 15], "advice": "..."}

# 判定本章处于螺旋 P1-P7 哪个阶段
diag_prompt = engine.build_spiral_diagnose_prompt(chapter_text)
# 返回 {"phase": "P3", "emotion_value": 78, "next_phase": "P4", "advice": "..."}
```

详见 [`PANGU_INTEGRATION.md`](./PANGU_INTEGRATION.md) 完整集成指南。

### 单元测试

```bash
python -m unittest test_pangu_system.py -v   # 38 个
python -m unittest test_pangu_patch.py -v    # 15 个
```

---
