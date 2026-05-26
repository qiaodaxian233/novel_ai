# -*- coding: utf-8 -*-
"""
core/site_profiles.py - 各 AI 网站的 DOM 选择器档案 + 站点匹配辅助函数

v2.02 P3 拆分:从 novel_ai.py 第 7485-7615 行整体搬运,内容零修改。
被 novel_ai.py 顶部 `from core.site_profiles import SITE_PROFILES` 导入。
"""

SITE_PROFILES = {
    "chatgpt.com": {
        "name": "ChatGPT",
        # 输入框:优先 #prompt-textarea(标准),兜底 contenteditable(ProseMirror)
        "input": '#prompt-textarea, div[contenteditable="true"][role="textbox"], textarea',
        # 发送按钮:data-testid + aria-label 双兜底(中英文)
        "send_btn": (
            'button[data-testid="send-button"], '
            'button[aria-label*="Send" i], '
            'button[aria-label*="发送" i]'
        ),
        # AI 回复:assistant 角色容器(镜像站也大都遵循)
        "response": 'div[data-message-author-role="assistant"]',
        # 停止按钮:中英文
        "stop_btn": (
            'button[data-testid="stop-button"], '
            'button[aria-label*="Stop" i], '
            'button[aria-label*="停止" i]'
        ),
    },
    "gpt.aimonkey.plus": {
        "name": "ChatGPT镜像(aimonkey)",
        # 输入框:按优先级三档兜底
        #   1. #prompt-textarea (官方 ChatGPT 同款 ID)
        #   2. div.ProseMirror (旧版 ProseMirror 编辑器)
        #   3. div[contenteditable="true"] (通用 contenteditable)
        #   4. textarea (纯 textarea 降级)
        "input": (
            '#prompt-textarea, '
            'div.ProseMirror[contenteditable="true"], '
            'div[contenteditable="true"][role="textbox"], '
            'div[contenteditable="true"], '
            'textarea'
        ),
        # 发送按钮: 实测 class=composer-submit-btn，data-testid 不存在
        "send_btn": (
            'button.composer-submit-btn, '
            'button[data-testid="send-button"], '
            'button[aria-label*="发送"], '
            'button[aria-label*="Send" i], '
            'form button[type="submit"]'
        ),
        # 回复区: 油猴脚本实测 div.markdown 最精准
        "response": 'div.markdown',
        "_response_fallback": [
            'div.markdown',
            'div[data-message-author-role="assistant"] div.markdown',
            '[data-message-author-role="assistant"]',
            'div.prose',
        ],
        "stop_btn": (
            'button.composer-submit-btn, '
            'button[data-testid="stop-button"], '
            'button[aria-label*="停止"], '
            'button[aria-label*="Stop" i]'
        ),
        # tm_bridge 关闭：直接用 DOM 选择器抓取，无需油猴脚本配合
        "tm_bridge": False,
    },
    "chat.openai.com": {
        "name": "ChatGPT (旧域名)",
        "input": '#prompt-textarea, div[contenteditable="true"][role="textbox"], textarea',
        "send_btn": (
            'button[data-testid="send-button"], '
            'button[aria-label*="Send" i], '
            'button[aria-label*="发送" i]'
        ),
        "response": 'div[data-message-author-role="assistant"]',
        "stop_btn": (
            'button[data-testid="stop-button"], '
            'button[aria-label*="Stop" i], '
            'button[aria-label*="停止" i]'
        ),
    },
    "chat.deepseek.com": {
        "name": "DeepSeek",
        "input": 'textarea',
        # `:has(svg)` 在现代 Chrome 的 querySelector 里原生支持(2022 后)
        "send_btn": 'div[role="button"]:has(svg)',
        # 主选择器:精确抓 assistant 正式回复主体
        # ── 必须用 ds-assistant-message-main-content,否则 div.ds-markdown
        # 也会匹配到思考过程块 / 用户提问块,导致 `last` 抓错对象
        # (BUG-012 修复:Canon 数组与 score JSON 都因为这个被抓断或抓错)
        "response": 'div.ds-markdown.ds-assistant-message-main-content',
        "_response_fallback": [
            # 用户报告:DeepSeek 改版后回复可能是单段 p,直接挂在外面
            # 选 last 用,但用 has() 排除掉用户提问块(用户块没 p.ds-markdown-paragraph)
            'p.ds-markdown-paragraph',
            # 兜底:DeepSeek UI 改版时保留宽匹配,但放到 fallback 优先级靠后
            'div.ds-markdown',
            '[class*="ds-message-content"]',
            '[class*="markdown-body"]',
        ],
        # 标准 CSS 不支持 :has-text,改用 aria-label
        "stop_btn": 'div[role="button"][aria-label*="停止"]',
        # ── 针对 DeepSeek 的特殊抓取策略:把同一回复块内的所有 p 段落拼起来
        # 因为新版可能没有外层 div.ds-markdown 容器,只有一堆 p
        "_grab_strategy": "deepseek_paragraphs",
    },
    "doubao.com": {
        "name": "豆包",
        "input": 'textarea, div[contenteditable="true"]',
        "send_btn": 'button[data-testid*="send"], button[aria-label*="发送"]',
        "response": '[data-testid*="message_text"], [class*="message-content"]',
        "stop_btn": 'button[aria-label*="停止"]',
    },
    "gemini.google.com": {
        "name": "Gemini",
        "input": 'rich-textarea div[contenteditable="true"], textarea',
        "send_btn": 'button[aria-label*="Send"], button[aria-label*="发送"]',
        "response": 'message-content, .model-response-text',
        "stop_btn": 'button[aria-label*="Stop"]',
    },
    "yuanbao.tencent.com": {
        "name": "元宝",
        "input": 'textarea, div[contenteditable="true"]',
        "send_btn": 'button[class*="send"], a[class*="send"]',
        "response": '[class*="agent-chat"], [class*="markdown"]',
        "stop_btn": 'button[class*="stop"]',
    },
    "chat.qwen.ai": {
        # v2.21.4:Qwen(通义千问)— 适合做"角色与世界抽取"等结构化任务
        # 选择器基于用户提供的真实 DOM 结构(2026-05):
        #   - textarea.message-input-textarea (输入框)
        #   - button.send-button (发送按钮,在 .chat-prompt-send-button 内)
        #   - .response-message-content (AI 回复区)
        #   - .qwen-markdown (回复 markdown 容器)
        "name": "Qwen",
        "input": (
            'textarea.message-input-textarea, '
            'textarea[placeholder*="帮您"], '
            'textarea, '
            'div[contenteditable="true"]'
        ),
        "send_btn": (
            '.chat-prompt-send-button button.send-button, '
            'button.send-button, '
            'button[aria-label*="发送"], '
            'button[type="submit"]:not([disabled])'
        ),
        # AI 回复:.response-message-content + 嵌套的 .qwen-markdown
        "response": (
            '.response-message-content .qwen-markdown, '
            '.response-message-content, '
            '.custom-qwen-markdown'
        ),
        "_response_fallback": [
            '.qwen-markdown',
            '.response-message-content',
            '.markdown-content',
            '[class*="message"][class*="assistant"]',
        ],
        # 停止按钮:发送中按钮会切到停止图标,但 class 仍含 send-button
        "stop_btn": (
            '.chat-prompt-send-button button[aria-label*="停止"], '
            'button[aria-label*="Stop"], '
            'button[aria-label*="停止"]'
        ),
        # v2.22.1 BUG-082:Qwen 流式输出比 DeepSeek 慢 5-10 倍,prompt 后常有
        # 5-90s "思考"阶段然后才开始逐字符吐出,且字符间隔可能 > 1s。
        # 用 polling 默认的 0.9s/1.5s stable_wait 会在 Qwen 写到几十字时
        # 误判"内容稳定 → 完成",抓到的只是 JSON 半句(实战日志:17 字
        # `[{"key":"角色.苏棠.体质`)。
        #
        # 修法分三层(C 主防御 + A/B 兜底):
        #
        # C. thinking_indicator (主防御):Qwen 思考中页面会有
        #    `.qwen-chat-status-card-title-animate` 这个带 -animate 后缀的 div
        #    (例:"梳理情节脉络,提炼核心要素")。思考完后这个动画类消失,
        #    父容器换成 `.qwen-chat-thinking-status-card-completed` + 文本
        #    "已经完成思考"。Polling 看到 -animate 类 → 直接跳过完成判定。
        #    这是 Qwen UI 提供的**确定性信号**,不靠时间/字数估算。
        #
        # A. stable_wait_min (兜底):万一未来 Qwen 改 class 名,C 失效,A 把
        #    完成等待提到 8 秒,避免回归到 0.9s 秒判错。
        #
        # B. min_complete_chars (兜底):字符数 < 100 强制不完成,JSON 短输出
        #    的最小合理长度。
        #
        # DeepSeek 等不设这三个字段(走默认),只对 Qwen 这类慢站生效。
        "thinking_indicator": ".qwen-chat-status-card-title-animate",
        "stable_wait_min": 8.0,
        "min_complete_chars": 100,
    },

"_default": {
        "name": "通用",
        "input": 'textarea, div[contenteditable="true"], input[type="text"]',
        "send_btn": ('button[data-testid*="send"], button[aria-label*="send" i], '
                     'button[aria-label*="发送"], button:has(svg[aria-label*="send" i])'),
        "response": ('[class*="markdown"], [class*="message-content"], '
                     '[data-message-author-role="assistant"]'),
        "stop_btn": 'button[aria-label*="stop" i], button[aria-label*="停止"]',
    },
}


def _profile_for_url(url):
    """根据 URL 返回选择器档案"""
    for host, prof in SITE_PROFILES.items():
        if host != "_default" and host in (url or ""):
            return prof
    return SITE_PROFILES["_default"]
