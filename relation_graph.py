# -*- coding: utf-8 -*-
"""
关系网络图模块 (v1.70 新增)

把 CharacterLibrary 里 tbl_chars + tbl_relations 的数据,
渲染成可交互的力导向网络图 (vis-network 9.x)。

设计要点:
- 零侵入:QWebEngineView 缺失时降级为 QLabel 提示装包
- 离线优先:vis-network.min.js vendor 到 vendor/ 目录,QUrl 本地加载
- 节点按"角色定位"染色,边按"关系类型"染色
- hover tooltip 显示完整角色卡 / 关系备注
- 角色库没有但关系表里出现的角色,自动补节点(不会丢)
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

# ── QWebEngineView 软依赖 ──────────────────────────────────
# 用户机器可能没装 PyQtWebEngine。装的话直接用,没装就降级提示。
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView  # type: ignore
    WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None  # type: ignore
    WEBENGINE_AVAILABLE = False


# ── 配色表 ─────────────────────────────────────────────────
# 节点颜色:按 tbl_chars 的"角色定位"列
ROLE_COLORS: dict[str, dict[str, str]] = {
    "主角":   {"bg": "#FFD700", "border": "#B8860B", "font": "#000000"},  # 金
    "女主":   {"bg": "#FF80AB", "border": "#C2185B", "font": "#4A0028"},  # 粉 — 深玫红字(dot 标签在浅背景上)
    "反派":   {"bg": "#8B0000", "border": "#5C0000", "font": "#4A0000"},  # 深红 — 暗红字
    "导师":   {"bg": "#1E88E5", "border": "#0D47A1", "font": "#0D2B5E"},  # 蓝 — 深蓝字
    "配角":   {"bg": "#9E9E9E", "border": "#616161", "font": "#333333"},  # 灰 — 深灰字
    "路人":   {"bg": "#CFD8DC", "border": "#90A4AE", "font": "#000000"},  # 浅灰
}
DEFAULT_ROLE_COLOR = {"bg": "#B0BEC5", "border": "#78909C", "font": "#263238"}

# 边颜色:按 tbl_relations 的"关系类型"列 (支持别名)
RELATION_COLORS: dict[str, str] = {
    # 师承
    "师父":   "#1E88E5",
    "师弟":   "#42A5F5",
    "师妹":   "#42A5F5",
    "师兄":   "#42A5F5",
    "师姐":   "#42A5F5",
    "徒弟":   "#1E88E5",
    "弟子":   "#1E88E5",
    # 情感
    "恋人":   "#EC407A",
    "暗恋对象": "#F48FB1",
    "夫妻":   "#D81B60",
    # 血缘
    "血缘":   "#FB8C00",
    "父":     "#FB8C00",
    "母":     "#FB8C00",
    "兄":     "#FFA726",
    "弟":     "#FFA726",
    "姐":     "#FFA726",
    "妹":     "#FFA726",
    "子":     "#FFA726",
    "女":     "#FFA726",
    # 阵营
    "同盟":   "#43A047",
    "盟友":   "#43A047",
    "好友":   "#66BB6A",
    "上下级": "#7E57C2",
    "下属":   "#7E57C2",
    "上司":   "#7E57C2",
    # 敌对
    "对手":   "#EF5350",
    "敌对":   "#E53935",
    "宿敌":   "#B71C1C",
    "仇人":   "#B71C1C",
}
DEFAULT_EDGE_COLOR = "#90A4AE"


def _pick_role_color(role: str) -> dict[str, str]:
    """按角色定位选颜色。子串模糊匹配 ('女配角' → 女主?不,先精确再子串)"""
    if not role:
        return DEFAULT_ROLE_COLOR
    role = role.strip()
    if role in ROLE_COLORS:
        return ROLE_COLORS[role]
    # 子串兜底:用户可能写 "男主"、"女主角"、"小反派" 等
    for key, color in ROLE_COLORS.items():
        if key in role or role in key:
            return color
    return DEFAULT_ROLE_COLOR


def _pick_edge_color(rel_type: str) -> str:
    """按关系类型选边颜色。子串模糊匹配。"""
    if not rel_type:
        return DEFAULT_EDGE_COLOR
    rel_type = rel_type.strip()
    if rel_type in RELATION_COLORS:
        return RELATION_COLORS[rel_type]
    # 子串兜底:'师徒关系' → '师'? 不,精确度差。改用包含
    for key, color in RELATION_COLORS.items():
        if key in rel_type:
            return color
    return DEFAULT_EDGE_COLOR


def _esc(s: Any) -> str:
    """HTML escape,防止用户在备注/角色名里写 <script> 之类的进入 tooltip"""
    return html.escape(str(s or ""), quote=True)


# ── 数据构建:从表格行转 vis-network nodes/edges ────────────
def build_graph_data(
    chars_rows: list[list[str]],
    relations_rows: list[list[str]],
) -> dict[str, list[dict]]:
    """
    chars_rows: 每行 [姓名, 角色定位, 外貌, 性格, 口头禅, 能力, 当前状态, 首次出场]
    relations_rows: 每行 [角色A, 关系类型, 角色B, 备注]

    返回 {"nodes": [...], "edges": [...]}
    - 角色库里所有角色都成节点
    - 关系表里出现但角色库没有的角色,自动补节点(灰色,标记"未在角色库")
    """
    nodes: list[dict] = []
    seen: set[str] = set()

    # 1. 角色库里的角色
    for row in chars_rows:
        # 兼容:row 长度可能不足 8(老存档)
        cells = [(row[i] if i < len(row) else "") for i in range(8)]
        name, role, looks, personality, motto, ability, state, first_chap = [
            (c or "").strip() for c in cells
        ]
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        color = _pick_role_color(role)
        # tooltip:多行 HTML(vis-network 9.x 支持 HTMLElement / String)
        tooltip_lines = []
        if role:        tooltip_lines.append(f"<b>定位:</b>{_esc(role)}")
        if looks:       tooltip_lines.append(f"<b>外貌:</b>{_esc(looks)}")
        if personality: tooltip_lines.append(f"<b>性格:</b>{_esc(personality)}")
        if motto:       tooltip_lines.append(f"<b>标志:</b>{_esc(motto)}")
        if ability:     tooltip_lines.append(f"<b>能力:</b>{_esc(ability)}")
        if state:       tooltip_lines.append(f"<b>当前状态:</b>{_esc(state)}")
        if first_chap:  tooltip_lines.append(f"<b>首次出场:</b>{_esc(first_chap)}")
        tooltip = "<br/>".join(tooltip_lines) or "(无更多信息)"

        nodes.append({
            "id": name,
            "label": name,
            "title": tooltip,
            "color": {"background": color["bg"], "border": color["border"]},
            "font": {"color": color["font"], "size": 16, "face": "Microsoft YaHei, sans-serif"},
            "borderWidth": 2,
            "shape": "dot",
            "size": 22,
        })

    # 2. 边 + 关系表里没在角色库的角色,自动补节点
    edges: list[dict] = []
    for row in relations_rows:
        cells = [(row[i] if i < len(row) else "") for i in range(4)]
        a, rel_type, b, note = [(c or "").strip() for c in cells]
        if not a or not b:
            continue  # 关系两端都得有

        # 补节点(角色库漏了的)
        for missing in (a, b):
            if missing not in seen:
                seen.add(missing)
                nodes.append({
                    "id": missing,
                    "label": missing,
                    "title": "<i>(关系表中出现,但角色库未登记)</i>",
                    "color": {"background": "#ECEFF1", "border": "#B0BEC5"},
                    "font": {"color": "#37474F", "size": 14, "face": "Microsoft YaHei, sans-serif"},
                    "borderWidth": 1,
                    "borderWidthSelected": 2,
                    "shape": "dot",
                    "size": 16,
                })

        edge_color = _pick_edge_color(rel_type)
        edges.append({
            "from": a,
            "to": b,
            "label": rel_type or "",
            "title": (_esc(note) if note else _esc(rel_type)),
            "color": {"color": edge_color, "highlight": edge_color, "hover": edge_color},
            "font": {"color": edge_color, "size": 12, "face": "Microsoft YaHei, sans-serif",
                     "strokeWidth": 3, "strokeColor": "#FFFFFF", "align": "middle"},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
            "smooth": {"type": "continuous"},
            "width": 2,
        })

    return {"nodes": nodes, "edges": edges}


# ── HTML 模板 ─────────────────────────────────────────────
def _build_html(nodes: list[dict], edges: list[dict], vendor_url: str) -> str:
    """生成内嵌 HTML。vendor_url 是 vis-network.min.js 的相对 url"""
    data_json = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=True)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html, body {{ margin:0; padding:0; height:100%; background:#fafafa; font-family: 'Microsoft YaHei', sans-serif; overflow:hidden; }}
  #network {{ position:absolute; top:0; left:0; right:0; bottom:0; }}
  #empty {{
    position:absolute; top:50%; left:50%; transform:translate(-50%, -50%);
    color:#999; font-size:14px; text-align:center; line-height:1.8;
  }}
  .vis-tooltip {{
    background:#fff !important;
    border:1px solid #ccc !important;
    border-radius:4px !important;
    padding:8px !important;
    font-size:12px !important;
    max-width:320px !important;
    line-height:1.6 !important;
    box-shadow:0 2px 8px rgba(0,0,0,0.15) !important;
  }}
  #legend {{
    position:absolute; top:8px; right:8px;
    background:rgba(255,255,255,0.92); border:1px solid #ddd; border-radius:4px;
    padding:6px 10px; font-size:11px; line-height:1.6; max-width:280px;
  }}
  #legend b {{ display:block; margin-top:4px; color:#555; }}
  #legend .sw {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; vertical-align:middle; }}
  #legend .ln {{ display:inline-block; width:14px; height:2px; margin-right:4px; vertical-align:middle; }}
</style>
<script src="{vendor_url}"></script>
</head>
<body>
<div id="network"></div>
<div id="empty" style="display:none;">
  暂无角色或关系数据。<br/>
  请先在 <b>👤 角色库</b> / <b>🔗 关系图谱</b> 子页添加数据,然后点 🔄 刷新图谱。
</div>
<div id="legend">
  <b>节点(角色定位):</b>
  <span><span class="sw" style="background:#FFD700"></span>主角</span>
  <span><span class="sw" style="background:#FF80AB"></span>女主</span>
  <span><span class="sw" style="background:#8B0000"></span>反派</span>
  <span><span class="sw" style="background:#1E88E5"></span>导师</span>
  <span><span class="sw" style="background:#9E9E9E"></span>配角</span>
  <br/>
  <b>边(关系类型):</b>
  <span><span class="ln" style="background:#1E88E5"></span>师承</span>
  <span><span class="ln" style="background:#EC407A"></span>情感</span>
  <span><span class="ln" style="background:#FB8C00"></span>血缘</span>
  <span><span class="ln" style="background:#43A047"></span>同盟</span>
  <span><span class="ln" style="background:#B71C1C"></span>宿敌</span>
</div>
<script>
  var data = {data_json};
  var container = document.getElementById('network');
  var empty = document.getElementById('empty');
  if (!data.nodes.length) {{
    empty.style.display = 'block';
    document.getElementById('legend').style.display = 'none';
  }} else {{
    var options = {{
      nodes: {{
        shape: 'dot',
        scaling: {{ min: 14, max: 28 }},
        font: {{ size: 16, face: 'Microsoft YaHei, sans-serif' }},
      }},
      edges: {{
        arrows: 'to',
        smooth: {{ type: 'continuous' }},
        font: {{ align: 'middle' }},
      }},
      physics: {{
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {{
          gravitationalConstant: -45,
          centralGravity: 0.06,
          springLength: 110,
          springConstant: 0.10,
          damping: 0.55,
        }},
        stabilization: {{ iterations: 250, fit: true }},
      }},
      interaction: {{
        hover: true,
        tooltipDelay: 150,
        zoomView: true,
        dragView: true,
        dragNodes: true,
        navigationButtons: false,
      }},
    }};
    // vis-network 把 string title 当纯文本显示,需转 DOM Element 才渲染 HTML
    data.nodes.forEach(function(n) {{
      if (typeof n.title === 'string') {{
        var el = document.createElement('div');
        el.innerHTML = n.title;
        el.style.lineHeight = '1.6';
        n.title = el;
      }}
    }});
    data.edges.forEach(function(e) {{
      if (typeof e.title === 'string') {{
        var el = document.createElement('div');
        el.innerHTML = e.title;
        e.title = el;
      }}
    }});
    var network = new vis.Network(container, data, options);
    // 稳定后:关物理 + 显式 fit 一次,保证节点居中铺满
    network.once('stabilizationIterationsDone', function () {{
      network.setOptions({{ physics: {{ enabled: false }} }});
      network.fit({{ animation: false }});
    }});
    // QWebEngineView 尺寸变化时(用户拉宽窗口/切 Tab 等),重新 fit
    var _fitTimer = null;
    window.addEventListener('resize', function () {{
      if (_fitTimer) clearTimeout(_fitTimer);
      _fitTimer = setTimeout(function () {{
        try {{ network.redraw(); network.fit({{ animation: false }}); }} catch (e) {{}}
      }}, 120);
    }});
  }}
</script>
</body>
</html>
"""


# ── 主 Widget ─────────────────────────────────────────────
class RelationGraphWidget(QWidget):
    """
    嵌在 CharacterLibrary sub_tab 里的关系网组件。
    用法:
      w = RelationGraphWidget()
      w.set_data(chars_rows, relations_rows)   # 任何时候可重刷
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._view: Any = None
        self._fallback: QLabel | None = None
        # vendor 路径(相对本模块)
        self._vendor_dir = Path(__file__).resolve().parent / "vendor"

        if WEBENGINE_AVAILABLE:
            self._view = QWebEngineView(self)
            self._layout.addWidget(self._view)
            # 初始空图
            self.set_data([], [])
        else:
            self._fallback = QLabel(
                "🕸️ 关系网功能需要 <b>PyQtWebEngine</b>。<br/><br/>"
                "请在命令行运行:<br/>"
                "<code style='background:#f0f0f0;padding:2px 6px;'>"
                "pip install PyQtWebEngine</code><br/><br/>"
                "装完重启程序即可。<br/><br/>"
                "(关系表格仍可在「🔗 关系图谱」子页正常使用)"
            )
            self._fallback.setStyleSheet(
                "padding:24px; color:#555; font-size:13px; line-height:1.6;"
            )
            self._fallback.setWordWrap(True)
            self._fallback.setTextFormat(1)  # Qt.RichText
            self._layout.addWidget(self._fallback)

    def set_data(self, chars_rows: list[list[str]], relations_rows: list[list[str]]) -> None:
        """重新渲染图。chars_rows / relations_rows 是 [[cell, ...], ...] 的二维列表"""
        if not WEBENGINE_AVAILABLE or self._view is None:
            return
        graph = build_graph_data(chars_rows, relations_rows)
        # 用相对路径加载 vendor/vis-network.min.js
        # base url 必须是 file:// 协议、必须以 / 结尾,setHtml 才能解析 <script src="vis-network.min.js">
        vendor_url = "vis-network.min.js"
        html_text = _build_html(graph["nodes"], graph["edges"], vendor_url)
        base_url = QUrl.fromLocalFile(str(self._vendor_dir) + "/")
        self._view.setHtml(html_text, base_url)

    # 测试用钩子:暴露 web view 是否启用
    def is_webengine_available(self) -> bool:
        return WEBENGINE_AVAILABLE and self._view is not None
