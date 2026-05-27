# 安全策略

## 支持的版本

| 版本 | 是否接受安全修复 |
|------|-----------------|
| v2.23.x (最新) | ✅ 是 |
| < v2.23 | ❌ 否，请升级 |

## 报告漏洞

如果你发现了安全漏洞，**请不要在 GitHub Issues 里公开披露**。

请通过以下方式私下联系：
- 在 GitHub 上发送私信给仓库所有者 [@qiaodaxian233](https://github.com/qiaodaxian233)
- 或通过 GitHub 的 [Private Vulnerability Reporting](https://github.com/qiaodaxian233/novel_ai/security/advisories/new) 提交

我会在 **7 个工作日内**回复确认，并在修复后公开披露。

## 已知数据流说明

本项目是本地桌面工具，但以下数据流会离开本机，使用前请知悉：

1. **AI 网站交互**：程序通过 Selenium 驱动真实浏览器访问 DeepSeek、Qwen、ChatGPT 等网站，你的 prompt 和 Cookie 受各 AI 平台隐私政策约束。

2. **授权验证**：启用授权模块时，程序会向 `upd.qiaodaxian233.cloud` 发送以下信息用于验证和心跳：
   - 授权码（加密传输）
   - 机器指纹（匿名哈希）
   - 操作系统版本
   - 应用版本号

3. **本地数据**：项目文件、章节内容、设置均保存在本机 `~/NovelAI_Projects/`，不会主动上传。

## 开发模式

本地开发时可通过环境变量跳过授权验证：

```bash
export NOVEL_AI_DEV_MODE=1
python novel_ai.py
```

**发布版本不应设置此变量。**
