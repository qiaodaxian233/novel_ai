"""
novel_ai.py 修复补丁
====================
使用方法：把这个文件放在 novel_ai.py 同目录，运行：
    python patch_novel_ai.py

会自动备份原文件为 novel_ai.py.bak，然后打上两处补丁：
  1. SITE_PROFILES 增加 gpt.aimonkey.plus 镜像站配置
  2. gen_outline_all 抓到回复后自动回填大纲输入框
"""

import re
import shutil
import sys
from pathlib import Path

TARGET = Path("novel_ai.py")

if not TARGET.exists():
    print("❌ 找不到 novel_ai.py，请把本脚本放到同目录再运行")
    sys.exit(1)

# 备份
shutil.copy(TARGET, TARGET.with_suffix(".py.bak"))
print("✅ 已备份为 novel_ai.py.bak")

src = TARGET.read_text(encoding="utf-8")

# =====================================================================
# 补丁 1：在 SITE_PROFILES 字典里补充镜像站 + ChatGPT 官方选择器
# =====================================================================
# 找到 SITE_PROFILES = { 这一行，在它的 "_default" 条目之前插入新条目

PATCH_SITE_PROFILES = '''
        # ---- ChatGPT 镜像站（gpt.aimonkey.plus 等同类镜像）----
        # 经油猴脚本实测确认的选择器（2025-05）
        "gpt.aimonkey.plus": {
            "input":    '[contenteditable="true"]',          # 只有1个，比 textarea 更精准
            "send_btn": 'button[data-testid="send-button"]', # 实测1个，精准
            "response": 'div.markdown',                      # 实测1个，内容干净 ✅ 智能推荐
            "stop_btn": 'button[data-testid="stop-button"], button[aria-label*="Stop"]',
            # 备用抓取选择器（按优先级）
            "_response_fallback": [
                'div.markdown',
                '[data-message-author-role="assistant"]',
                'div.prose',
            ],
        },
        # ChatGPT 官方（结构相同）
        "chatgpt.com": {
            "input":    '[contenteditable="true"]',
            "send_btn": 'button[data-testid="send-button"]',
            "response": 'div.markdown',
            "stop_btn": 'button[data-testid="stop-button"]',
            "_response_fallback": [
                'div.markdown',
                '[data-message-author-role="assistant"]',
                'div.prose',
            ],
        },
'''

# 找 SITE_PROFILES 字典的位置并插入
# 策略：找到第一个 "_default" key 出现位置，在其前面插入
if '"_default"' in src and 'SITE_PROFILES' in src:
    # 找到 SITE_PROFILES = { 后第一个 "_default" 前的位置
    idx = src.find('"_default"', src.find('SITE_PROFILES'))
    if idx != -1:
        src = src[:idx] + PATCH_SITE_PROFILES + src[idx:]
        print("✅ 补丁1 已应用：SITE_PROFILES 新增 gpt.aimonkey.plus / chatgpt.com")
    else:
        print("⚠️  补丁1：找不到 _default，跳过（可能已修改过）")
elif 'SITE_PROFILES' not in src:
    # 项目里还没有 SITE_PROFILES，在 AI_URLS 后面创建整个字典
    FULL_SITE_PROFILES = '''
# =====================================================================
# 网页选择器配置（每家 AI 网站 DOM 不同，在此维护）
# key = 域名（hostname），精确匹配优先；找不到则用 _default
# =====================================================================
SITE_PROFILES = {
''' + PATCH_SITE_PROFILES + '''
        # ---- DeepSeek ----
        "chat.deepseek.com": {
            "input":    'textarea',
            "send_btn": 'div[role="button"]:has(svg)',
            "response": 'div.ds-markdown',
            "stop_btn": 'div[role="button"]:has-text("停止")',
        },
        # ---- 豆包 ----
        "www.doubao.com": {
            "input":    'textarea',
            "send_btn": 'button[type="submit"]',
            "response": 'div[class*="bot-message"], div[class*="assistant"]',
            "stop_btn": None,
        },
        # ---- 通用兜底 ----
        "_default": {
            "input":    'textarea, [contenteditable="true"]',
            "send_btn": 'button[type="submit"], button:has(svg)',
            "response": 'div.markdown, div.prose, [data-message-author-role="assistant"]',
            "stop_btn": None,
        },
}
'''
    # 插到 AI_URLS 字典之后
    ai_urls_end = src.find('\n}', src.find('AI_URLS'))
    if ai_urls_end != -1:
        insert_pos = ai_urls_end + 2
        src = src[:insert_pos] + '\n' + FULL_SITE_PROFILES + src[insert_pos:]
        print("✅ 补丁1 已应用：新建 SITE_PROFILES 字典")
    else:
        print("⚠️  补丁1：无法定位插入点，跳过")
else:
    print("ℹ️  补丁1：SITE_PROFILES 已存在但没有 _default，手动检查一下")


# =====================================================================
# 补丁 2：grab_last_response 方法——兜底多选择器依次尝试
# =====================================================================
# 找到方法定义，替换为带 fallback 逻辑的版本

OLD_GRAB = 'def grab_last_response(self'

NEW_GRAB = '''def grab_last_response(self, profile=None):
        """
        抓取当前页面最后一条 AI 回复。
        优先用 profile["response"]，失败则按 _response_fallback 列表依次尝试，
        最终兜底用 innerText 稳定长度。
        """
        # 默认选择器优先级
        default_fallbacks = [
            'div.markdown',
            '[data-message-author-role="assistant"]',
            'div.prose',
            'section[data-testid*="conversation-turn"]',
        ]

        if profile is None:
            profile = {}

        selectors = []
        primary = profile.get("response", "")
        if primary:
            selectors.append(primary)
        selectors.extend(profile.get("_response_fallback", []))
        selectors.extend(default_fallbacks)
        # 去重保序
        seen = set()
        selectors = [s for s in selectors if s and not (s in seen or seen.add(s))]

        for sel in selectors:
            try:
                # Selenium / Playwright 两种驱动的兼容写法
                if hasattr(self, 'driver') and self.driver:
                    els = self.driver.find_elements("css selector", sel)
                    if els:
                        text = els[-1].get_attribute("innerText") or els[-1].text or ""
                        text = text.strip()
                        if len(text) > 10:
                            self.log(f"✅ 抓取成功 [{sel}] {len(text)}字")
                            return text
                elif hasattr(self, 'page') and self.page:          # playwright
                    locs = self.page.locator(sel)
                    cnt = locs.count()
                    if cnt > 0:
                        text = locs.nth(cnt - 1).inner_text() or ""
                        text = text.strip()
                        if len(text) > 10:
                            self.log(f"✅ 抓取成功 [{sel}] {len(text)}字")
                            return text
            except Exception as e:
                self.log(f"⚠️  选择器 [{sel}] 失败: {e}")
                continue

        self.log("❌ 所有选择器均未抓到内容")
        return ""

    def _grab_last_response_orig(self'''

if OLD_GRAB in src:
    # 找到方法定义起始行
    idx = src.find('\n    ' + OLD_GRAB)
    if idx == -1:
        idx = src.find('\ndef ' + OLD_GRAB[4:])  # 顶格方法
    if idx != -1:
        # 找到方法结束位置（下一个同缩进的 def）
        method_end = src.find('\n    def ', idx + 10)
        if method_end == -1:
            method_end = src.find('\ndef ', idx + 10)
        if method_end != -1:
            old_method = src[idx:method_end]
            # 把原方法改名为 _grab_last_response_orig 保留
            renamed = old_method.replace(
                'def grab_last_response(self',
                'def _grab_last_response_orig(self',
                1
            )
            src = src[:idx] + '\n    ' + NEW_GRAB + renamed[renamed.find('\n'):] + src[method_end:]
            print("✅ 补丁2 已应用：grab_last_response 升级为多选择器兜底版本")
        else:
            print("⚠️  补丁2：无法定位方法结束，跳过")
    else:
        print("⚠️  补丁2：无法定位方法起始，跳过")
else:
    print("ℹ️  补丁2：grab_last_response 方法不存在（可能名称不同），跳过")


# =====================================================================
# 补丁 3：gen_outline_all 末尾自动回填大纲各输入框
# =====================================================================

AUTO_FILL_METHOD = '''
    # ---- 补丁3：大纲自动回填 ----
    def _auto_fill_outline(self, text: str):
        """
        把 AI 返回的大纲文本按常见标题拆分，自动回填到 StoryOutline 各输入框。
        若无法识别分块标题，则整段填入「整套大纲」文本框。
        """
        outline = getattr(self, 'story_outline', None)
        if outline is None:
            self.log("⚠️  找不到 story_outline 控件，无法回填")
            return

        def extract(pattern):
            m = re.search(pattern, text, re.S)
            return m.group(1).strip() if m else ""

        seed       = extract(r'【?故事种子[】:：]+(.*?)(?=【[^\u4e00-\u9fff]|【故事|【世界|【LO|【结构|【章节|【简介|\Z)')
        worldview  = extract(r'【?世界观[】:：]+(.*?)(?=【[^\u4e00-\u9fff]|【故事|【LO|【结构|【章节|【简介|\Z)')
        lo_layer   = extract(r'【?LO层[】:：]+(.*?)(?=【[^\u4e00-\u9fff]|【结构|【章节|【简介|\Z)')
        structure  = extract(r'【?(?:故事)?结构[】:：]+(.*?)(?=【[^\u4e00-\u9fff]|【章节|【简介|\Z)')
        ch_outline = extract(r'【?章节大纲[】:：]+(.*?)(?=【[^\u4e00-\u9fff]|【简介|\Z)')
        intro      = extract(r'【?简介[】:：]+(.*?)(?=【[^\u4e00-\u9fff]|\Z)')

        # 整套大纲始终填入 outline_edit
        if hasattr(outline, 'outline_edit'):
            outline.outline_edit.setPlainText(text)

        filled = []
        if seed       and hasattr(outline, 'seed_edit'):
            outline.seed_edit.setPlainText(seed);         filled.append("故事种子")
        if worldview  and hasattr(outline, 'worldview_edit'):
            outline.worldview_edit.setPlainText(worldview);  filled.append("世界观")
        if lo_layer   and hasattr(outline, 'lo_edit'):
            outline.lo_edit.setPlainText(lo_layer);       filled.append("LO层")
        if structure  and hasattr(outline, 'structure_edit'):
            outline.structure_edit.setPlainText(structure);  filled.append("结构")
        if ch_outline and hasattr(outline, 'chapter_outline_edit'):
            outline.chapter_outline_edit.setPlainText(ch_outline); filled.append("章节大纲")
        if intro      and hasattr(outline, 'intro_edit'):
            outline.intro_edit.setPlainText(intro);       filled.append("简介")

        if filled:
            self.log(f"✅ 大纲已自动回填：{' / '.join(filled)}")
        else:
            self.log("✅ 大纲整体已回填（未检测到分块标题）")
'''

# 插在 gen_outline_all 方法之前（作为独立方法）
GEN_OUTLINE = 'def gen_outline_all(self'

if GEN_OUTLINE in src:
    idx = src.find('\n    ' + GEN_OUTLINE)
    if idx == -1:
        idx = src.find('\ndef gen_outline_all')
    if idx != -1:
        src = src[:idx] + AUTO_FILL_METHOD + src[idx:]
        print("✅ 补丁3(a) 已应用：_auto_fill_outline 方法已插入")

        # 在 gen_outline_all 里调用它：找到"self.grab_last_response"附近，之后加调用
        # 找到 gen_outline_all 方法内部
        method_start = src.find('\n    ' + GEN_OUTLINE)
        if method_start == -1:
            method_start = src.find('\ndef gen_outline_all')
        grab_in_method = src.find('grab_last_response', method_start)
        if grab_in_method != -1:
            # 找到那行的结尾
            line_end = src.find('\n', grab_in_method)
            inject = (
                "\n        # 补丁3：自动回填大纲\n"
                "        _outline_resp = self.grab_last_response()\n"
                "        if _outline_resp:\n"
                "            self._auto_fill_outline(_outline_resp)\n"
            )
            # 只在没有已注入的情况下添加
            if '_auto_fill_outline' not in src[grab_in_method:grab_in_method + 300]:
                src = src[:line_end] + inject + src[line_end:]
                print("✅ 补丁3(b) 已应用：gen_outline_all 末尾自动调用回填")
            else:
                print("ℹ️  补丁3(b)：已存在回填调用，跳过")
        else:
            print("⚠️  补丁3(b)：gen_outline_all 里未找到 grab_last_response，需手动添加 _auto_fill_outline 调用")
    else:
        print("⚠️  补丁3：找不到 gen_outline_all 方法位置，跳过")
else:
    print("ℹ️  补丁3：gen_outline_all 方法不存在（名称不同），请手动在对应方法里调用 self._auto_fill_outline(response)")


# =====================================================================
# 写回文件
# =====================================================================
TARGET.write_text(src, encoding="utf-8")
print("\n🎉 全部补丁应用完成！已写入 novel_ai.py")
print("   如有问题，novel_ai.py.bak 是原始备份，可随时还原。")
