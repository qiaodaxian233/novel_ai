# -*- coding: utf-8 -*-
"""ui/plot_timeline.py - 剧情线可视化地图

把全书章节、伏笔、情绪、关键事件画成时间轴，
一眼看到哪里埋了坑、哪里填了坑、哪里节奏平。
v2.14.1 新增。
"""
import json
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from PyQt5.QtCore import QUrl

# 尝试导入 QWebEngineView，不可用时降级
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    WEBVIEW_OK = True
except ImportError:
    WEBVIEW_OK = False


def _build_timeline_html(chapters, canon_items=None, foreshadows=None):
    """构建时间轴 HTML"""
    # 准备章节数据
    ch_data = []
    for i, ch in enumerate(chapters):
        ch_num = i + 1
        emo = ch.get("emotion_scores", {})
        ch_data.append({
            "num": ch_num,
            "title": str(ch.get("title", f"第{ch_num}章") or ""),
            "summary": str(ch.get("summary") or "")[:120],
            "hook": str(ch.get("hook") or "")[:60] if isinstance(ch.get("hook"), str) else "",
            "tension": emo.get("tension", 0) if isinstance(emo, dict) else 0,
            "satisfaction": emo.get("satisfaction", 0) if isinstance(emo, dict) else 0,
            "emotion": emo.get("emotion", 0) if isinstance(emo, dict) else 0,
            "warmth": emo.get("warmth", 0) if isinstance(emo, dict) else 0,
            "emo_summary": str(emo.get("summary", "")) if isinstance(emo, dict) else "",
            "seeds": str(ch.get("_pangu_seeds_summary") or ""),
        })

    # Canon 锁定项按章号分组
    canon_by_ch = {}
    if canon_items:
        for item in canon_items:
            ch = item.get("ch", 0)
            if ch not in canon_by_ch:
                canon_by_ch[ch] = []
            canon_by_ch[ch].append(item.get("key", ""))

    canon_json = json.dumps(canon_by_ch, ensure_ascii=False)
    data_json = json.dumps(ch_data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: 'Microsoft YaHei','PingFang SC',sans-serif; background:#1a1a2e; color:#e0e0e0; padding:20px; }}
h1 {{ text-align:center; color:#e94560; margin-bottom:20px; font-size:18px; }}
.timeline {{ position:relative; padding-left:60px; }}
.timeline::before {{ content:''; position:absolute; left:30px; top:0; bottom:0; width:3px; background:linear-gradient(to bottom,#e94560,#0f3460,#e94560); }}
.chapter {{ position:relative; margin-bottom:16px; padding:12px 16px; background:#16213e; border-radius:8px; border-left:4px solid #0f3460; cursor:pointer; transition:all 0.2s; }}
.chapter:hover {{ background:#1a2744; border-left-color:#e94560; transform:translateX(4px); }}
.chapter::before {{ content:attr(data-num); position:absolute; left:-48px; top:12px; width:30px; height:30px; background:#0f3460; border-radius:50%; text-align:center; line-height:30px; font-size:12px; font-weight:bold; color:#e94560; }}
.ch-title {{ font-weight:bold; color:#e94560; font-size:14px; }}
.ch-summary {{ font-size:12px; color:#aaa; margin-top:4px; line-height:1.5; }}
.ch-hook {{ font-size:11px; color:#f39c12; margin-top:3px; }}
.ch-seeds {{ font-size:11px; color:#2ecc71; margin-top:3px; }}
.ch-canon {{ font-size:11px; color:#3498db; margin-top:3px; }}
.emo-bar {{ display:flex; gap:4px; margin-top:6px; }}
.emo-bar .bar {{ height:6px; border-radius:3px; transition:width 0.3s; }}
.bar-tension {{ background:#e74c3c; }}
.bar-satisfaction {{ background:#f39c12; }}
.bar-emotion {{ background:#3498db; }}
.bar-warmth {{ background:#2ecc71; }}
.legend {{ display:flex; gap:12px; justify-content:center; margin-bottom:16px; font-size:12px; }}
.legend span {{ display:flex; align-items:center; gap:4px; }}
.legend .dot {{ width:10px; height:10px; border-radius:50%; }}
.filter {{ text-align:center; margin-bottom:16px; }}
.filter button {{ background:#0f3460; color:#e0e0e0; border:1px solid #e94560; padding:4px 12px; border-radius:4px; cursor:pointer; margin:0 4px; font-size:12px; }}
.filter button:hover {{ background:#e94560; }}
.filter button.active {{ background:#e94560; }}
.alert {{ background:#4a1a1a; border-left-color:#e74c3c !important; }}
.alert::before {{ background:#e74c3c !important; color:white !important; }}
.stats {{ text-align:center; margin-bottom:12px; font-size:13px; color:#8fa3c4; }}
</style></head><body>
<h1>🗺️ 剧情线地图</h1>
<div class="legend">
  <span><div class="dot" style="background:#e74c3c"></div>紧张</span>
  <span><div class="dot" style="background:#f39c12"></div>爽感</span>
  <span><div class="dot" style="background:#3498db"></div>虐/感动</span>
  <span><div class="dot" style="background:#2ecc71"></div>温馨</span>
  <span><div class="dot" style="background:#2ecc71"></div>🌱伏笔</span>
  <span><div class="dot" style="background:#3498db"></div>🔒设定</span>
</div>
<div class="filter">
  <button onclick="filterAll()" class="active" id="btn-all">全部</button>
  <button onclick="filterLow()">⚠ 节奏低谷</button>
  <button onclick="filterSeeds()">🌱 有伏笔</button>
  <button onclick="filterCanon()">🔒 有新设定</button>
</div>
<div class="stats" id="stats"></div>
<div class="timeline" id="timeline"></div>
<script>
const chapters = {data_json};
const canonByCh = {canon_json};

function render(filter) {{
  const tl = document.getElementById('timeline');
  tl.innerHTML = '';
  let shown = 0;
  chapters.forEach(ch => {{
    const hasCanon = canonByCh[ch.num] && canonByCh[ch.num].length > 0;
    const isLow = ch.tension < 4 && ch.satisfaction < 4;
    const hasSeeds = ch.seeds && ch.seeds.length > 0;
    
    if (filter === 'low' && !isLow) return;
    if (filter === 'seeds' && !hasSeeds) return;
    if (filter === 'canon' && !hasCanon) return;
    shown++;
    
    const div = document.createElement('div');
    div.className = 'chapter' + (isLow ? ' alert' : '');
    div.setAttribute('data-num', ch.num);
    
    let html = '<div class="ch-title">' + ch.title + '</div>';
    if (ch.summary) html += '<div class="ch-summary">' + ch.summary + '</div>';
    if (ch.hook) html += '<div class="ch-hook">🪝 ' + ch.hook + '</div>';
    if (ch.seeds) html += '<div class="ch-seeds">🌱 ' + ch.seeds + '</div>';
    if (hasCanon) html += '<div class="ch-canon">🔒 ' + canonByCh[ch.num].join(', ') + '</div>';
    
    // 情绪条
    const maxW = 120;
    html += '<div class="emo-bar">';
    html += '<div class="bar bar-tension" style="width:' + (ch.tension*maxW/10) + 'px" title="紧张 ' + ch.tension + '"></div>';
    html += '<div class="bar bar-satisfaction" style="width:' + (ch.satisfaction*maxW/10) + 'px" title="爽感 ' + ch.satisfaction + '"></div>';
    html += '<div class="bar bar-emotion" style="width:' + (ch.emotion*maxW/10) + 'px" title="虐心 ' + ch.emotion + '"></div>';
    html += '<div class="bar bar-warmth" style="width:' + (ch.warmth*maxW/10) + 'px" title="温馨 ' + ch.warmth + '"></div>';
    html += '</div>';
    if (ch.emo_summary) html += '<div style="font-size:11px;color:#8fa3c4;margin-top:2px">' + ch.emo_summary + '</div>';
    
    div.innerHTML = html;
    tl.appendChild(div);
  }});
  document.getElementById('stats').textContent = '显示 ' + shown + '/' + chapters.length + ' 章';
}}

function filterAll() {{ setActive('btn-all'); render('all'); }}
function filterLow() {{ setActive(null); render('low'); }}
function filterSeeds() {{ setActive(null); render('seeds'); }}
function filterCanon() {{ setActive(null); render('canon'); }}
function setActive(id) {{
  document.querySelectorAll('.filter button').forEach(b => b.classList.remove('active'));
  if (id) document.getElementById(id).classList.add('active');
}}

render('all');
</script></body></html>"""
    return html


def show_plot_timeline(parent, chapters, canon_items=None, foreshadows=None):
    """弹出剧情线地图对话框"""
    if not WEBVIEW_OK:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(parent, "剧情线地图",
            "需要 PyQt5.QtWebEngineWidgets 才能显示地图。\n"
            "pip install PyQtWebEngine")
        return

    html = _build_timeline_html(chapters, canon_items, foreshadows)

    dlg = QDialog(parent)
    dlg.setWindowTitle("🗺️ 剧情线地图")
    dlg.resize(700, 800)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(0, 0, 0, 0)

    web = QWebEngineView()
    web.setHtml(html, QUrl("about:blank"))
    lay.addWidget(web)

    dlg.exec_()
