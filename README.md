# 盘古超级写作助手

> 一款本地小说自动化创作工具,挂载真实 Chrome/Edge 浏览器,自动驱动 ChatGPT / DeepSeek / 豆包 / Gemini / 元宝等 AI 网页完成长篇网文创作。
> **不调用任何 API**,用浏览器自动化方式访问 AI 对话界面,适合长期写一本书时把上下文连贯性、人设一致性、伏笔回收等问题自动管起来。

**当前版本:v2.06** · Python 3.10+ · PyQt5 + Selenium 4.6+

---

## 1. 这是什么

一个 PyQt5 桌面 GUI,加上 Selenium 浏览器自动化层,让你把网文创作的"重复劳动"全部交给程序处理:

- 章节按目标字数自动生成,达不到自动死磕重写
- 每章生成完自动维护**对话记忆**(角色档案 / 章节摘要 / 长期伏笔)
- 自动注入到下一章 prompt,**让 AI 第 200 章时也不忘第 1 章人设**
- 内置**盘古超级系统**:123 项 AI 写作禁用词检测、30 项质量自检、感官铁律、压爆震、黄金三章模板
- 全章节结束后自动跑伏笔回收检查、承诺兑现检查、知识穿帮检查
- 自动维护**剧情树**、**关系图谱**、**时间线**、**物品/法器库**、**战力体系**、**信息隔离表**

---

## 2. 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python novel_ai.py
```

**首次使用:**
1. 启动后在「生成控制」Tab 点 🚀 启动浏览器(独立 Chrome/Edge 窗口弹出)
2. 在弹出的浏览器里**手动登录一次** AI 网站(Cookie 持久化到 `~/NovelAI_Browser_Data`,后续不用再登)
3. 回主程序,在「创作设置」填写灵感 → 「故事大纲」生成大纲 → 「生成控制」点 ▶ 开始生成

依赖要求详见 `requirements.txt`,其中 `webdriver-manager` / `edge-tts` / `pygame` 都是可选项,缺了对应功能停用但主程序仍能跑。

---

## 3. 项目结构(v2.06)

经过 P1~P6 模块化拆分,代码组织清晰:

```
novel_ai/
├── novel_ai.py             # 主程序(12380 行,MainWindow 装配中心 + main())
│
├── core/                   # 数据 + 配置层(9 个文件)
│   ├── constants.py        # AI_URLS / GENRES / PLATFORMS / 等 8 个常量
│   ├── prompts.py          # PROMPTS 字典(29 keys / 583 行)
│   ├── site_profiles.py    # SITE_PROFILES(各 AI 网页 DOM 选择器)
│   ├── default_skills.py   # DEFAULT_SKILLS(出厂技能库)
│   └── stylesheet.py       # STYLESHEET(全局 QSS)
│
├── ui/                     # UI 组件层(7 个文件)
│   ├── browser_worker.py   # Selenium 浏览器自动化 worker(3610 行)
│   ├── theme.py            # 主题管理(白/黑切换)
│   ├── highlighters.py     # 盘古禁用词实时高亮
│   ├── threads.py          # TTS 合成后台线程
│   ├── conversation_switcher.py  # 对话槽切换器
│   ├── story_outline.py    # 故事大纲 Tab(独立 widget)
│   └── tabs/               # 主要 Tab 实现(9 个文件)
│       ├── project_home.py        # 🏠 项目主页(项目仪表盘 / 最近文件)
│       ├── creation_settings.py   # 创作设置(题材/平台/金手指/人设/...)
│       ├── dialog_memory.py       # 对话记忆 Tab
│       ├── canon_guard.py         # Canon 设定守护
│       ├── character_library.py   # 🎭 角色与世界(13 子页:角色/关系/时间线/...)
│       ├── skill_library.py       # 技能库 Tab
│       ├── generation_control.py  # 生成控制(浏览器 + 批量生成)
│       ├── chapter_editor.py      # 章节编辑器(含盘古面板)
│       └── book_splitter.py       # 📚 拆书学习
│
├── pangu_system.py         # 盘古超级系统引擎(123 禁用词 / 30 项质检 / 风格库)
├── pangu_patch.py          # 盘古零侵入接入(就地包裹 PROMPTS)
├── lifespan_loops_steps.py # 寿元台账 + 长期伏笔
├── lifespan_loops_panel.py # 寿元/伏笔 Tab
├── workflow_pipeline.py    # 生成流水线(可视化 + 强化学习)
├── workflow_panel.py       # 工作流可视化 Tab
├── research_report_skills.py  # 研究报告技能(5 条出厂技能)
├── dialogue_critic.py      # 13 法对话铁律评分
├── flow_rl.py              # 流程强化学习(自学习最优等待/重试策略)
├── housekeeper.py          # 章末管家日报
├── book_splitter.py        # 拆书核心引擎
├── import_continuation.py  # 导入外部小说续写
├── project_io.py           # 项目文件夹格式读写
├── relation_graph.py       # 关系图谱(vis-network 力导向图)
├── license_guard.py        # 授权验证
├── tts_backend.py          # TTS 后端(EdgeTTS / Index-TTS)
├── patch_novel_ai.py       # 历史代码补丁注入器(慎动)
│
├── requirements.txt
├── README.md
└── 项目对接记忆.md         # AI 接班手册(给下一代 Claude)
```

**累计模块化进展:** 主程序从 20740 行(1.0 MB)→ 12380 行(v2.23.5 含番茄榜单系统)。详见 `项目对接记忆.md` 里 v2.00~v2.05 的 P1~P6 段。

---

## 4. 核心功能

### 4.1 全自动批量生成(★ 核心工作流)

```
点 🚀 启动浏览器(独立 Chrome 窗口弹出)
       ↓
首次手动登录 AI 网站(Cookie 持久化)
       ↓
回主程序 → 点 ▶ 开始连续生成(50 章批量)
       ↓
程序自动循环:
  ① 注入对话记忆 + 角色库 + Canon + 上一章末尾 + 盘古铁律到 prompt
  ② 跳转 AI 网页,逐字打字粘贴,按回车 / 点发送
  ③ 实时检测 AI 是否还在打字(稳定 4 秒视为完成)
  ④ 抓取最后一条 assistant 消息
  ⑤ 多维质检:字数 / 钩子 / 禁用词 / 盘古综合评分 / Canon / 节奏 / 人设
  ⑥ 不达标自动死磕重写(最多 3 次)
  ⑦ 通过 → 入章节库 + 自动剥离元信息(钩子/爽点/下章选项)
  ⑧ 章末流水线:Canon 抽取 → 6 库抽取 → 伏笔回收检查 →
       承诺兑现检查 → 弧线推进检查 → 信息披露检查 → 写作回流 → 摘要 → 下一章
  ⑨ 持续循环直到 N 章完成
```

### 4.2 对话记忆系统(关键加成)

写到第 100 章时,普通 AI 早就忘了第 1 章发生了什么——**人设会崩、伏笔会断**。本程序内置一套对话记忆,在「对话记忆」Tab 里自动维护:

| 类别 | 内容 | 维护方式 |
|---|---|---|
| **角色档案** | 外貌/性格/当前状态/与主角关系 | 章末 AI 自动抽取,合并到角色与世界库 |
| **章节摘要** | 每章 80 字精炼概括 | 章末自动生成,追加到记忆 |
| **长期记忆** | 伏笔、关键物品、未揭晓秘密 | 章末 AI 抽取 + 用户编辑 |

发下一章前自动注入(可配置开关):

```
【对话记忆 - AI 必读】
【角色档案(必须保持人设一致)】
林晚晚:外柔内刚,刚结婚...
顾砚深:高冷禁欲,A 集团总裁...

【已发生剧情概要(早期章节)】
第1章:林晚晚双重身份首次登场,夜市偶遇男主
第2章:酸梅汤的试探,情绪暗涌
... (前面 N-3 章只用摘要)

【最近 3 章详细回顾(请基于这些细节衔接)】
——第N-2章 ——
[本章核心] xxx
[本章末尾片段] ...原文最后 400 字...

【长期记忆 - 重要伏笔/物品/关系】
- 玉佩:祖母传给男主(第3章)
- 女主双重身份未被识破(全文核心)
```

可调参数:最近 N 章详细回顾(默认 3)、单条摘要长度(默认 80 字)、是否自动总结、是否自动注入。

### 4.3 盘古超级系统

零侵入接入(`pangu_patch.install_pangu(globals())`),就地把 PROMPTS 字典套上 9 条铁律:

- **123 项 AI 写作禁用词清单**(顿时/连忙/显然/嘴角勾起 等),实时高亮编辑器
- **感官铁律**:每段必须命中 ≥2 种感官(视/听/触/嗅/味/温/动觉)
- **压爆震法则**:压抑—爆发—震慑 三段节奏
- **黄金三章模板**:首章钩子 / 次章信息密度 / 三章付费点
- **30 项 + 8 大坑质检**:章末 AI 综合评分,< 阈值自动死磕重写
- **风格库**(可视化编辑器):关键词 → 主/辅/点缀风格 + 女基调 + 平台映射
- **章节差异化**(防套路):每章用不同 RNG 种子,锁定不同开篇/节奏/感官组合

### 4.4 自动结构化抽取(章末流水线)

每章生成完毕后自动跑(均为可关开关):

| 步骤 | 作用 | 库 |
|---|---|---|
| Canon 抽取 | 单值条目(年龄/身份/物品)入 Canon Tab | tab_canon |
| 6 库抽取 | 角色/关系/时间线/物品/战力/伏笔/承诺/弧线/关系值/目标/信息/知情人/剧情树 入对应表 | tab_charlib |
| 伏笔回收检查 | AI 扫本章哪些伏笔被收(BUG-056) | tbl_fore |
| 承诺兑现检查 | AI 扫本章哪些承诺/威胁兑现(BUG-057) | tbl_promises |
| 弧线推进检查 | AI 评估本章对哪几条弧线推进了多少 progress(BUG-058) | tbl_arcs |
| 关系值变化检查 | AI 评估本章哪些关系值变化(BUG-058) | tbl_rel_values |
| 信息披露追踪 | AI 扫本章新披露事件,自动入库 known_by(BUG-059) | tbl_known_by |
| 知识穿帮检查 | AI 扫某角色用了不该知道的信息,标红警告(BUG-059) | — |
| 写作模式回流 | AI 反查本章对应剧情树哪些节点,挂章号(BUG-062) | tree_plot |
| 摘要生成 | 80 字精炼章节摘要 | tab_memory |

### 4.5 支持的 AI 网站

```python
AI_URLS = {
    "ChatGPT镜像": "https://gpt.aimonkey.plus/",
    "ChatGPT":     "https://chatgpt.com/",
    "豆包":        "https://www.doubao.com/chat/",
    "Gemini":      "https://gemini.google.com/",
    "DeepSeek":    "https://chat.deepseek.com/",
    "元宝":        "https://yuanbao.tencent.com/",
    "小米AI":      "https://www.xiaomi.com/",
}
```

`SITE_PROFILES`(`core/site_profiles.py`)定义每家网站的 DOM 选择器(输入框/发送按钮/回复区/停止按钮)。每个站点支持多选择器逗号分隔,前一个失效后一个兜底。可通过菜单 → 工具 → 🎯 现场拾取选择器 在浏览器里 hover 元素自动生成新选择器。

---

## 5. 数据存档

### 项目文件夹格式(v1.30+ 推荐)

`Ctrl+S` 保存为文件夹结构:

```
~/NovelAI_Projects/<书名>/
├── project.json         # 项目元数据(设置/大纲/记忆/库)
├── chapters/
│   ├── ch001.txt
│   ├── ch002.txt
│   └── ...
└── .backups/            # 自动版本备份(最近 10 次保存)
    └── ...
```

- 兼容老的单 `.json` 格式(打开时自动升级,原 `.json` 备份为 `.legacy-original.json`)
- 60 秒定时 autosave(防崩溃),关闭时也强制保存
- 章节锁定字段(v1.92):锁定后 save/重命名/删除/写回全部拦截,适合中稿/终稿冻结

---

## 6. 二次开发

### 找代码的位置

| 想改什么 | 在哪里 |
|---|---|
| 提示词模板 | `core/prompts.py`(29 keys) |
| AI 网址 / 题材 / 金手指清单 | `core/constants.py` |
| DOM 选择器 | `core/site_profiles.py` |
| 浏览器自动化(Selenium) | `ui/browser_worker.py` |
| 某个 Tab 的 UI 和事件 | `ui/tabs/<tab_name>.py` |
| 章节生成主流水线 | `novel_ai.py`(`MainWindow._send_next_chapter` / `_accept_chapter_and_continue` / `_post_chapter_chain`) |
| 盘古铁律 / 风格库 / 词扫 | `pangu_system.py` |
| 寿元/伏笔台账 | `lifespan_loops_steps.py` |
| 13 法对话评分 | `dialogue_critic.py` |

### 测试

```bash
# 全套测试(1178 个)
QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -q
QT_QPA_PLATFORM=offscreen python3 test_full_integration.py    # 48 集成测试
QT_QPA_PLATFORM=offscreen python3 test_lifespan_loops.py       # 68
QT_QPA_PLATFORM=offscreen python3 test_research_report_skills.py  # 123
QT_QPA_PLATFORM=offscreen python3 test_workflow_panel.py       # 31
```

67 个测试文件(统一在 tests/ 目录)覆盖:全部 BUG-065~074 回归 + 各模块单元测试 + 完整 UI 集成测试。

### 接入新 AI 站点

1. `core/constants.py` 的 `AI_URLS` 加一行
2. `core/site_profiles.py` 的 `SITE_PROFILES` 加 DOM 选择器(用 F12 抠 input / send_btn / response 选择器)
3. 重启程序 → 「创作设置」选新 AI → 「生成控制」启动浏览器

### 改成走 API 而不是浏览器

`ui/browser_worker.py` 的 `_send_prompt` / `_grab_response` 改成 `requests.post` 调对应 API,信号机制保持不变,UI 层无需改。

---

## 7. 文档导航

| 文档 | 用途 |
|---|---|
| `README.md`(本文件)| 项目介绍 + 快速上手 |
| `项目对接记忆.md` | **给下一代 AI 接班用的完整开发记忆**(7000+ 行):BUG 修复历史 / 设计决策 / 用户偏好 / 给下个 Claude 的警告 |
| `pangu_full_spec.md` | 盘古超级系统完整规范(在程序内 ❓ 盘古手册 也能查) |
| `docs/archive/` | v7 时代历史接入文档(5 份,已过期归档,留作考古)。详见 `docs/archive/README.md` |

---

## 8. 合规说明

- 程序内置安全约束(禁止血腥、暴力、色情、镜面/影子/另一个自己题材等)已写进所有提示词,**会一并发到 AI 那边**
- 程序不存储/上传任何用户数据,所有文件都在本地
- 仅作技术学习与小说创作辅助,请勿用于侵权目的
- AI 网页 DOM 经常变动,选择器适配难免有滞后,欢迎提 issue 反馈
