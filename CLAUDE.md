# NovelAI 盘古写作引擎 — Claude 工作手册

> 完整项目记忆见 `项目对接记忆.md`。本文件是快速入口。

## 第一件事

```bash
git log --oneline -5        # 确认当前 HEAD
```

然后问用户："上次跑得怎么样，有没有新报错？"

---

## 推送前必跑

```bash
QT_QPA_PLATFORM=offscreen python scripts/pre_push_check.py
```

✅ 全部通过才能推。失败了先修，不能绕过。

---

## 核心架构（不能打破的规则）

1. **浏览器只有一个，Worker 独占** — 所有 `driver.xxx()` 必须在 `BrowserWorker` 线程里，主线程不能直接碰
2. **扫榜/详情用 `driver.get()`** — 不能用 `_goto`（`_goto` 同 host 会跳过 navigate）
3. **写文件用 `_atomic_write()`** — 在 `project_io.py`，不要用 `write_text()` 直接写
4. **测试在 `tests/` 目录** — 每个 bug 修复必须带 `test_bugXXX_*.py` 守护测试
5. **`license_guard.py` 不动** — 授权核心，`DEV_MODE` 测试阶段=True，上线前改 False

---

## 遇到 Bug

按 `项目对接记忆.md` 第十一章 DEBUG 流程走（6 个阶段）。核心原则：**先建立可复现的回路，再猜原因**。

---

## 做新功能

改动超过 50 行前，先过 `项目对接记忆.md` 第十一章"新功能规划流程"清单。

---

## 常见坑

- Qwen 思考阶段 80 秒 0 字符是正常的，不是卡死
- 番茄榜单页书名/简介是反爬乱码，只有 `book_id` 和在读数是干净的
- 修完代码必须重启 Python 进程才生效
- `git push` 成功后用 `git fetch` 验证远端 HEAD 是否更新

---

## 项目关键文件

| 文件 | 作用 |
|------|------|
| `novel_ai.py` | 主程序 12380 行，MainWindow |
| `ui/browser_worker.py` | Selenium Worker 3610 行 |
| `core/site_profiles.py` | 8 个 AI 站点 DOM 配置 |
| `core/fanqie_rank_scraper.py` | 番茄榜单抓取 |
| `license_guard.py` | 授权验证（不要乱动） |
| `project_io.py` | 项目文件读写（原子写入） |
| `ui/theme.py` | 主题系统（ThemeManager） |
| `scripts/pre_push_check.py` | 推送前冒烟测试 |
| `项目对接记忆.md` | 完整项目记忆 |
