# -*- coding: utf-8 -*-
"""全量样式表对比度守护(v2.23.6)

由皮肤全量审计工具固化而来:AST 提取全部 setStyleSheet 静态字符串,
WCAG 对比度校验三类危险样式(自洽对 / 只写文字 / 只写背景),
后两类对 5 套主题交叉验证。防止再次出现"某主题下看不清"的回归。
"""
# -*- coding: utf-8 -*-
"""全量样式表对比度审计。

三类危险样式:
  BOTH       — 同一规则里写死了 color + background:自洽对,直接算对比度
  COLOR_ONLY — 只写死 color:背景继承自当前主题 → 对 5 套主题的 bg/bg_white 交叉验
  BG_ONLY    — 只写死 background:文字继承自当前主题 → 对 5 套主题的 text 交叉验

WCAG 相对亮度 + 对比度;< 3.0 判 BROKEN(大字号下限都不够),3.0~4.5 判 WARN。
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── 主题色板(与 ui/theme.py 同步读取) ─────────────────────────
import importlib.util
spec = importlib.util.spec_from_file_location("theme_mod", ROOT / "ui" / "theme.py")
# theme.py 依赖 PyQt5 仅在函数内 — 顶层可安全导入
theme_mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(theme_mod)
    THEMES = {}
    for name, t in theme_mod.ThemeManager.THEMES.items():
        qa = t.get("qss_args", {})
        THEMES[name] = {
            "bg": qa.get("bg", "#ffffff"),
            "bg_white": qa.get("bg_white", "#ffffff"),
            "text": qa.get("text", "#000000"),
        }
except Exception as e:
    print("theme load failed:", e)
    sys.exit(1)

NAMED = {
    "white": "#ffffff", "black": "#000000", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "gray": "#808080",
    "grey": "#808080", "orange": "#ffa500", "yellow": "#ffff00",
    "transparent": None, "none": None,
}


def parse_color(v, blend_bg="#ffffff"):
    """返回 (r,g,b) 或 None(无法解析/透明/渐变)"""
    v = v.strip().lower().rstrip(";")
    if v in NAMED:
        v = NAMED[v]
        if v is None:
            return None
    if v is None or "gradient" in v:
        return None
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)", v)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = float(m.group(4)) if m.group(4) else 1.0
        if a < 1.0:
            base = parse_color(blend_bg) or (255, 255, 255)
            r = round(r * a + base[0] * (1 - a))
            g = round(g * a + base[1] * (1 - a))
            b = round(b * a + base[2] * (1 - a))
        return (r, g, b)
    m = re.match(r"#([0-9a-f]{3})$", v)
    if m:
        s = m.group(1)
        return tuple(int(c * 2, 16) for c in s)
    m = re.match(r"#([0-9a-f]{6})$", v)
    if m:
        s = m.group(1)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    return None  # 非法/9位等 — 已由其他守护覆盖


def luminance(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(c1, c2):
    l1, l2 = luminance(c1), luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# ── setStyleSheet 静态字符串提取 ────────────────────────────────
def extract_sheets(path):
    """yield (lineno, css_text, is_partial)"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    def const_str(node):
        """尽力求值:Constant / 隐式拼接 / BinOp+ / JoinedStr(仅常量段,标记partial)"""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, False
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            l, lp = const_str(node.left)
            r, rp = const_str(node.right)
            if l is None or r is None:
                return (l or "") + (r or ""), True
            return l + r, lp or rp
        if isinstance(node, ast.JoinedStr):
            parts, partial = [], False
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(str(v.value))
                else:
                    parts.append("\x00DYN\x00")
                    partial = True
            return "".join(parts), partial
        return None, True

    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setStyleSheet"
                and node.args):
            text, partial = const_str(node.args[0])
            if text and ("{" in text or ":" in text):
                yield node.lineno, text, partial


# ── QSS 解析 ────────────────────────────────────────────────────
def parse_rules(css):
    """yield (selector, {prop: value});无选择器的裸声明 selector='' """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if "{" in css:
        for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
            yield m.group(1).strip(), parse_decls(m.group(2))
        # 花括号外的残留裸声明
        rest = re.sub(r"[^{}]*\{[^{}]*\}", "", css)
        d = parse_decls(rest)
        if d:
            yield "", d
    else:
        d = parse_decls(css)
        if d:
            yield "", d


def parse_decls(block):
    out = {}
    for decl in block.split(";"):
        if ":" not in decl:
            continue
        p, _, v = decl.partition(":")
        p, v = p.strip().lower(), v.strip()
        if "\x00DYN\x00" in v:
            # 动态值(多为主题令牌):属性存在但值未知
            if p in ("background", "background-color"):
                out["bg_dyn"] = True
            elif p == "color":
                out["color_dyn"] = True
            continue
        if p in ("color",):
            out["color"] = v
        elif p in ("background", "background-color"):
            out["bg"] = v
    return out


def bg_unknown(d):
    """背景存在但不可解析(渐变/动态)→ 自洽未知,不按 COLOR_ONLY 审"""
    return "bg" in d and parse_color(d["bg"]) is None


# ── 主审计 ──────────────────────────────────────────────────────
def audit():
    findings = []  # (severity, file, line, selector, kind, detail)
    files = [ROOT / "novel_ai.py", ROOT / "import_continuation.py",
             ROOT / "lifespan_loops_panel.py"]
    files += sorted((ROOT / "ui").rglob("*.py"))
    files += sorted((ROOT / "core").rglob("*.py"))

    for f in files:
        if not f.exists():
            continue
        try:
            sheets = list(extract_sheets(f))
        except SyntaxError:
            continue
        for lineno, css, partial in sheets:
            rules = list(parse_rules(css))
            # 伪状态继承:':hover/:pressed/:checked/:disabled/:focus' 规则
            # 未声明的属性回落到同一样式表内同根选择器的基础规则(Qt 语义)
            base = {}
            for sel, d in rules:
                root = sel.split(":")[0].strip()
                if ":" not in sel:
                    base.setdefault(root, {}).update(d)
            merged_rules = []
            for sel, d in rules:
                root = sel.split(":")[0].strip()
                if ":" in sel and root in base:
                    m = dict(base[root]); m.update(d)
                    merged_rules.append((sel, m))
                else:
                    merged_rules.append((sel, d))
            for sel, d in merged_rules:
                fg_s, bg_s = d.get("color"), d.get("bg")
                sel_l = sel.lower()
                state = ":hover" in sel_l or ":pressed" in sel_l or ":focus" in sel_l
                if fg_s and bg_s:
                    bg = parse_color(bg_s)
                    fg = parse_color(fg_s, blend_bg=bg_s)
                    if fg and bg is None:
                        continue  # 渐变等未知背景:自洽,跳过
                    if fg and bg:
                        r = contrast(fg, bg)
                        if r < 3.0:
                            findings.append(("BROKEN", f, lineno, sel, "PAIR",
                                             f"{fg_s} on {bg_s} = {r:.2f}"))
                        elif r < 4.5 and not state:
                            findings.append(("WARN", f, lineno, sel, "PAIR",
                                             f"{fg_s} on {bg_s} = {r:.2f}"))
                elif fg_s and not bg_s:
                    if d.get("bg_dyn"):
                        continue  # 背景是主题令牌:自适应,跳过
                    fg = parse_color(fg_s)
                    if fg:
                        bad = []
                        for tn, tc in THEMES.items():
                            worst = min(
                                contrast(fg, parse_color(tc["bg"])),
                                contrast(fg, parse_color(tc["bg_white"])))
                            if worst < 3.0:
                                bad.append(f"{tn}({worst:.1f})")
                        if bad:
                            findings.append(
                                ("THEME", f, lineno, sel, "COLOR_ONLY",
                                 f"color:{fg_s} 在主题 {','.join(bad)} 下撞底"))
                elif bg_s and not fg_s:
                    if d.get("color_dyn"):
                        continue  # 文字是主题令牌:自适应,跳过
                    bg = parse_color(bg_s)
                    if bg:
                        bad = []
                        for tn, tc in THEMES.items():
                            r = contrast(parse_color(tc["text"]), bg)
                            if r < 3.0:
                                bad.append(f"{tn}({r:.1f})")
                        if bad and len(bad) >= 1:
                            findings.append(
                                ("THEME", f, lineno, sel, "BG_ONLY",
                                 f"bg:{bg_s} 在主题 {','.join(bad)} 下文字撞底"))
    return findings




# ── 白名单:架构性误报(有据可查,新增项不得随意进入) ──────────
# 1. 启动页 hero 白字:背景是父控件的 primary_dark→primary 渐变,
#    白字对 5 套主题的 primary_dark 最差对比度 3.25(已数学验证)
# 2. project_home QGroupBox rgba(0,0,0,0.02):近乎全透明,实际底色
#    ≈ 主题底色,主题文字压上去就是主题自身对比度;审计器按白底混合
#    产生误报
WHITELIST = {
    ("ui/project_launcher.py", "COLOR_ONLY", "color:rgba(255,255,255,200)"),
    ("ui/project_launcher.py", "COLOR_ONLY", "color:white"),
    ("ui/tabs/project_home.py", "BG_ONLY", "bg:rgba(0,0,0,0.02)"),
}


def _whitelisted(f, kind, detail):
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    for wf, wk, wprefix in WHITELIST:
        if rel == wf and kind == wk and detail.startswith(wprefix):
            return True
    return False


def test_no_broken_static_pairs():
    """守护:任何自洽 color+background 静态对,对比度必须 ≥3.0。

    历史教训:45ba358 盲替换制造了 #1a1a2e on #141d35 = 1.0 的隐形
    项目名("开始的皮肤看不清"根因);v2.23.6 全量修复后立此守护。
    """
    broken = [x for x in audit() if x[0] == "BROKEN"]
    msg = "\n".join(
        f"{f.relative_to(ROOT)}:{line} [{kind}] {sel} {detail}"
        for _, f, line, sel, kind, detail in broken)
    assert not broken, "发现对比度 <3.0 的自洽样式对:\n" + msg


def test_theme_findings_whitelisted():
    """守护:只写死一半(仅文字/仅背景)且在任一主题下 <3.0 的样式,
    必须在白名单内(白名单条目均有'为何安全'的书面依据)。"""
    bad = []
    for sev, f, line, sel, kind, detail in audit():
        if sev == "THEME" and not _whitelisted(f, kind, detail):
            bad.append(f"{f.relative_to(ROOT)}:{line} [{kind}] {sel} {detail}")
    assert not bad, "发现未白名单的主题相关对比度问题:\n" + "\n".join(bad)
