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
