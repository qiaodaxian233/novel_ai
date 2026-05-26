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
def _role_layer(role: str) -> int:
    """v2.21.4:把角色定位映射成"层级"(0=中心,3=外圈),供初始布局分圈用
    
    主角/女主放最里圈;反派/导师次之;配角再外;路人最外。
    这样力布局收敛后视觉结构清晰,不会一锅粥。
    """
    r = (role or "").strip()
    # 主线核心
    if any(k in r for k in ("主角", "女主", "男主", "MC", "穿越者")):
        return 0
    # 主要对手 / 引路人
    if any(k in r for k in ("反派", "BOSS", "敌人", "对手")):
        return 1
    if any(k in r for k in ("导师", "师父", "师傅", "贵人", "队友")):
        return 1
    # 重要配角
    if any(k in r for k in ("配角", "亲人", "家人")):
        return 2
    # 路人 / 龙套 / 其他
    return 3


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
    
    v2.21.4 改进:
      - 节点大小按 degree(连边数)动态调整,主角(关系多)更大更突出
      - 按 _role_layer 分组,vis-network 按 group 初始分圈布局
      - tooltip 加显"关系数"
    """
    # 第 0 步:统计每个角色的连边数(度数)— 用于动态节点大小
    degree: dict[str, int] = {}
    for row in relations_rows:
        cells = [(row[i] if i < len(row) else "") for i in range(4)]
        a, _rel_type, b, _note = [(c or "").strip() for c in cells]
        if a:
            degree[a] = degree.get(a, 0) + 1
        if b:
            degree[b] = degree.get(b, 0) + 1
    
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
        deg = degree.get(name, 0)
        # 节点大小:基础 18 + 每条关系加 4,封顶 50(避免巨型节点)
        node_size = min(18 + deg * 4, 50)
        layer = _role_layer(role)
        # tooltip:多行 HTML(vis-network 9.x 支持 HTMLElement / String)
        tooltip_lines = []
        if role:        tooltip_lines.append(f"<b>定位:</b>{_esc(role)}")
        if deg:         tooltip_lines.append(f"<b>关系数:</b>{deg}")
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
            "size": node_size,
            "group": f"layer{layer}",   # v2.21.4:供 vis-network 初始分圈用
            "_layer": layer,            # 自定义字段(JS 端用于 manual initial position)
            "_role": role,
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
                deg = degree.get(missing, 0)
                nodes.append({
                    "id": missing,
                    "label": missing,
                    "title": f"<i>(关系表中出现,但角色库未登记)</i><br/><b>关系数:</b>{deg}",
                    "color": {"background": "#ECEFF1", "border": "#B0BEC5"},
                    "font": {"color": "#37474F", "size": 14, "face": "Microsoft YaHei, sans-serif"},
                    "borderWidth": 1,
                    "borderWidthSelected": 2,
                    "shape": "dot",
                    "size": min(14 + deg * 3, 40),
                    "group": "layer3",
                    "_layer": 3,
                    "_role": "未登记",
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
    """生成内嵌 HTML。vendor_url 是 vis-network.min.js 的相对 url
    
    v2.21.4 关系图布局重做:
      ① 按 _layer 字段在 4 个同心圆上铺初始位置 → 强分层,避免一锅粥
      ② barnesHut 引擎 + 强斥力 + 长 spring,节点真正分散
      ③ avoidOverlap=1 强制不重叠
      ④ 顶部加 [重排] [扩散] [缩小] 工具栏,排坏了一键重排
    """
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
  #toolbar {{
    position:absolute; top:8px; left:8px;
    background:rgba(255,255,255,0.96); border:1px solid #ccc; border-radius:4px;
    padding:4px 6px; z-index:1000; user-select:none;
    box-shadow:0 1px 3px rgba(0,0,0,0.1);
  }}
  #toolbar button {{
    margin:0 2px; padding:3px 10px; border:1px solid #bbb; background:#fff;
    border-radius:3px; cursor:pointer; font-size:11px; font-family:inherit;
  }}
  #toolbar button:hover {{ background:#e3f2fd; border-color:#1976d2; color:#1976d2; }}
  #toolbar .sep {{ display:inline-block; width:1px; height:14px; background:#ddd; margin:0 4px; vertical-align:middle; }}
  #stats {{ display:inline-block; color:#888; font-size:10px; margin-left:8px; }}
</style>
<script src="{vendor_url}"></script>
</head>
<body>
<div id="toolbar">
  <button onclick="relayout()" title="按角色层级重新分圈布局(主角居中,配角外圈)">🔄 重排</button>
  <button onclick="spread()" title="把节点之间推开,减少拥挤">↔ 扩散</button>
  <button onclick="cluster()" title="把节点拉拢,显示主要关系结构">✕ 紧凑</button>
  <span class="sep"></span>
  <button onclick="network && network.fit()" title="缩放到刚好看到所有节点">🔍 全览</button>
  <span id="stats"></span>
</div>
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
  <br/>
  <b style="font-size:10px;">💡 节点越大,关系越多</b>
</div>
<script>
  var data = {data_json};
  var container = document.getElementById('network');
  var empty = document.getElementById('empty');
  var network = null;
  
  // v2.21.4:按 _layer 字段在 4 个同心圆上铺初始位置(主角中心,配角外圈)
  // 同 layer 内按"度数"再排:度数高的靠近圆心
  function assignInitialPositions(nodes) {{
    var layers = {{0: [], 1: [], 2: [], 3: []}};
    nodes.forEach(function(n) {{
      var L = (typeof n._layer === 'number') ? n._layer : 3;
      layers[L].push(n);
    }});
    // 每层一个圆环半径(根据节点数自适应)
    var radii = {{0: 0, 1: 200, 2: 380, 3: 560}};
    // 主角层(layer0)如果只有 1-2 个,放正中心
    Object.keys(layers).forEach(function(L) {{
      var arr = layers[L];
      var n = arr.length;
      if (n === 0) return;
      // 节点多的层,半径自适应放大(避免挤一圈)
      var r = radii[L];
      if (n > 8 && L > 0) {{
        r = radii[L] * (1 + (n - 8) * 0.06);
      }}
      arr.forEach(function(node, i) {{
        if (L === 0 && n === 1) {{
          // 单主角放原点
          node.x = 0;
          node.y = 0;
        }} else {{
          var angle = (2 * Math.PI * i) / n;
          // 错开起始角度让各层不在同一条线上
          var offset = L * 0.4;
          node.x = r * Math.cos(angle + offset);
          node.y = r * Math.sin(angle + offset);
        }}
        // 固定初始位置(让物理引擎从这里开始优化,不会全聚到原点)
        // physics 用 fixed=false 让其继续松弛,但 x/y 提供初值
      }});
    }});
    return layers;
  }}
  
  if (!data.nodes.length) {{
    empty.style.display = 'block';
    document.getElementById('legend').style.display = 'none';
    document.getElementById('toolbar').style.display = 'none';
  }} else {{
    // 应用初始位置
    assignInitialPositions(data.nodes);
    
    // 统计信息
    document.getElementById('stats').textContent =
      '节点 ' + data.nodes.length + ' · 关系 ' + data.edges.length;
    
    var options = {{
      nodes: {{
        shape: 'dot',
        scaling: {{ min: 14, max: 50 }},
        font: {{ size: 16, face: 'Microsoft YaHei, sans-serif' }},
      }},
      edges: {{
        arrows: {{ to: {{ enabled: true, scaleFactor: 0.6 }} }},
        // v2.21.4:dynamic smooth 自动避开节点,边不会从节点中间穿
        smooth: {{ enabled: true, type: 'dynamic', roundness: 0.5 }},
        font: {{ align: 'middle' }},
      }},
      physics: {{
        enabled: true,
        // v2.21.4:换 barnesHut 引擎,比 forceAtlas2Based 更适合分层分散布局
        solver: 'barnesHut',
        barnesHut: {{
          gravitationalConstant: -12000,  // 强斥力(原 -45 弱爆了)
          centralGravity: 0.15,           // 适度向心(防止飞散)
          springLength: 180,              // 长 spring(原 110 太短挤一起)
          springConstant: 0.04,           // 弱弹簧(让斥力主导)
          damping: 0.6,                   // 较高阻尼,快速稳定
          avoidOverlap: 1,                // 0..1,1=绝不重叠 — 关键!
        }},
        maxVelocity: 50,
        minVelocity: 0.3,
        stabilization: {{
          enabled: true,
          iterations: 300,
          updateInterval: 25,
          fit: true,
        }},
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
    
    network = new vis.Network(container, data, options);
    
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
  
  // ── 工具栏函数 ──────────────────────────────
  // 🔄 重排:按 layer 重新分圈,跑物理引擎重新收敛
  function relayout() {{
    if (!network) return;
    // 重新计算初始位置
    var nodesArr = data.nodes.map(function(n) {{ return n; }});
    assignInitialPositions(nodesArr);
    var updates = nodesArr.map(function(n) {{
      return {{ id: n.id, x: n.x, y: n.y }};
    }});
    // 用 nodes.update 强制设位置
    network.body.data.nodes.update(updates);
    // 重开物理,跑 300 次再关
    network.setOptions({{ physics: {{ enabled: true }} }});
    setTimeout(function() {{
      try {{
        network.setOptions({{ physics: {{ enabled: false }} }});
        network.fit({{ animation: {{ duration: 600 }} }});
      }} catch (e) {{}}
    }}, 2500);
  }}
  
  // ↔ 扩散:把所有节点位置 ×1.4,然后跑物理让它重新平衡
  function spread() {{
    if (!network) return;
    var positions = network.getPositions();
    var updates = [];
    Object.keys(positions).forEach(function(id) {{
      var p = positions[id];
      updates.push({{ id: id, x: p.x * 1.4, y: p.y * 1.4 }});
    }});
    network.body.data.nodes.update(updates);
    network.setOptions({{ physics: {{ enabled: true }} }});
    setTimeout(function() {{
      try {{
        network.setOptions({{ physics: {{ enabled: false }} }});
        network.fit({{ animation: {{ duration: 400 }} }});
      }} catch (e) {{}}
    }}, 1500);
  }}
  
  // ✕ 紧凑:节点位置 ×0.7
  function cluster() {{
    if (!network) return;
    var positions = network.getPositions();
    var updates = [];
    Object.keys(positions).forEach(function(id) {{
      var p = positions[id];
      updates.push({{ id: id, x: p.x * 0.7, y: p.y * 0.7 }});
    }});
    network.body.data.nodes.update(updates);
    network.setOptions({{ physics: {{ enabled: true }} }});
    setTimeout(function() {{
      try {{
        network.setOptions({{ physics: {{ enabled: false }} }});
        network.fit({{ animation: {{ duration: 400 }} }});
      }} catch (e) {{}}
    }}, 1500);
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
