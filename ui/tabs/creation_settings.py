# -*- coding: utf-8 -*-
"""ui/tabs/creation_settings.py - 创作设定 Tab(1388 行,P4 最大)

v2.03 P4 拆分:从 novel_ai.py 第 1068-2455 行整体搬运,内容零修改。
"""
import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from core.constants import (
    ENDINGS, ERAS, GENRES, GOLDEN_FINGERS, PERSONAS, PLATFORMS,
    STYLE_DIMENSIONS,
)


class CreationSettings(QWidget):
    # v1.63:上下文设置变更时上抛,MainWindow 用来重算字数预估
    # v2.12: ctx_settings_changed 信号已迁移到 GenerationControl
    
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── 🔒 锁定设置按钮(防止滑动误触) ──
        lock_row = QHBoxLayout()
        lock_row.setContentsMargins(10, 5, 10, 0)
        self.btn_lock = QPushButton("🔒 设置已锁定(点击解锁)")
        self.btn_lock.setCheckable(True)
        self.btn_lock.setChecked(True)
        self._settings_locked = True
        self.btn_lock.setStyleSheet(
            "QPushButton { background:#e74c3c; color:white; padding:6px 16px;"
            "font-weight:bold; border-radius:4px; }"
            "QPushButton:checked { background:#e74c3c; }"
            "QPushButton:!checked { background:#1f8b4d; }"
            "QPushButton:hover { background:#c0392b; }")
        self.btn_lock.clicked.connect(self._toggle_lock)
        lock_row.addWidget(self.btn_lock)
        lock_row.addStretch()
        outer.addLayout(lock_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # ---- AI 配置(只管「用什么 AI」;启动 / 关闭 / 内核 / 抓取 在生成控制 Tab) ----
        ai_box = QGroupBox("AI 配置")
        ai_layout = QVBoxLayout(ai_box)

        # —— 第 1 行:选择 AI 模型 ——
        row = QHBoxLayout()
        row.addWidget(QLabel("选择AI模型:"))
        self.ai_group = QButtonGroup(self)
        for i, m in enumerate(["ChatGPT", "豆包", "Gemini", "DeepSeek", "元宝", "小米AI", "自定义"]):
            rb = QRadioButton(m)
            if m == "DeepSeek":
                rb.setChecked(True)
                rb.setStyleSheet("color: #cc3333; font-weight: bold;")
            self.ai_group.addButton(rb, i)
            row.addWidget(rb)
        self.custom_url = QLineEdit()
        self.custom_url.setPlaceholderText("自定义URL")
        self.custom_url.setEnabled(False)   # 默认禁用,选「自定义」才启用
        row.addWidget(self.custom_url)
        ai_layout.addLayout(row)

        self.delay_check = QCheckBox("模拟人类操作延迟(非必要勿勾选)")
        ai_layout.addWidget(self.delay_check)

        # DeepSeek 深度思考模式(R1)
        self.chk_deep_think = QCheckBox(
            "🧠 启用 DeepSeek 深度思考模式(质量更高,生成稍慢)")
        # 持久化
        from PyQt5.QtCore import QSettings as _QS_dt
        self.chk_deep_think.setChecked(
            _QS_dt("NovelAI", "UserPrefs").value("deepseek_deep_think", True, type=bool))
        self.chk_deep_think.setStyleSheet("color:#9b72cf;font-weight:bold;")
        self.chk_deep_think.setToolTip(
            "勾选后,每次发送消息前自动点击 DeepSeek 的「深度思考」按钮(R1 模式)。\n"
            "效果:\n"
            "  ✓ 写作质量明显提升,逻辑更严谨\n"
            "  ✓ 严格遵循盘古铁律和禁用词的能力增强\n"
            "代价:\n"
            "  · 生成时间增加 30%~50%(R1 需要思考过程)\n"
            "  · 章节正文不变,但前置「思考过程」会在 DeepSeek 页面显示\n"
            "仅 DeepSeek 站点生效,其他 AI 自动忽略。")
        self.chk_deep_think.stateChanged.connect(
            lambda v: _QS_dt("NovelAI", "UserPrefs").setValue("deepseek_deep_think", bool(v)))
        ai_layout.addWidget(self.chk_deep_think)

        # ---- 盘古超级系统开关 ----
        self.pangu_check = QCheckBox(
            "启用【盘古超级系统】(禁用词过滤 + 感官铁律 + 压爆震 + 黄金三章公式)")
        self.pangu_check.setChecked(True)
        self.pangu_check.setStyleSheet("color:#4e79cd;font-weight:bold;")
        self.pangu_check.setToolTip(
            "勾选后,每个章节 prompt 会被盘古铁律自动包裹:\n"
            "• 116 个禁用词强制过滤(顿时/连忙/眼神深邃 等)\n"
            "• 视/听/触 三感必须齐全\n"
            "• 压 70%+ 爆 5%+ 震 25% 情绪曲线\n"
            "• 智商防火墙(防止角色降智)\n"
            "• 黄金三章公式(第 1-3 章强制套用)\n"
            "取消勾选则完全回到原版行为,可一键切换。")
        ai_layout.addWidget(self.pangu_check)

        # —— 预登录(快捷:启动浏览器并跳到所选 AI 网站登录页) ——
        prow = QHBoxLayout()
        self.btn_prelogin = QPushButton("预登录所选模型")
        self.btn_prelogin.setStyleSheet(
            "background:#3d6fd4;color:white;padding:6px 14px;"
            "font-weight:bold;border-radius:3px;")
        prow.addWidget(self.btn_prelogin)
        hint = QLabel("(也可以到「生成控制」Tab 顶部直接挂载浏览器)")
        hint.setStyleSheet("color:#6d7c95;")
        prow.addWidget(hint)
        prow.addStretch()
        ai_layout.addLayout(prow)

        # 选中「自定义」时启用 custom_url
        def _toggle_custom_url(*_):
            btn = self.ai_group.checkedButton()
            self.custom_url.setEnabled(btn is not None and btn.text() == "自定义")
        self.ai_group.buttonClicked.connect(_toggle_custom_url)
        _toggle_custom_url()

        layout.addWidget(ai_box)

        # ---- 标题 ----
        trow = QHBoxLayout()
        trow.addWidget(QLabel("小说标题:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("(留空让 AI 生成 / 也可以自己写)")
        trow.addWidget(self.title_input, 1)
        self.btn_gen_title = QPushButton("AI生成定制长书名")
        self.btn_regen_title = QPushButton("重新生成")
        trow.addWidget(self.btn_gen_title); trow.addWidget(self.btn_regen_title)
        layout.addLayout(trow)

        # ---- 题材选择(v2.23.5 重写:根据番茄真实分类分组展示)----
        gbox = QGroupBox("题材选择(番茄真实分类)")
        self.box_genre = gbox  # 第 7 项:用于折叠链
        gbox_lay = QVBoxLayout(gbox)
        gbox_lay.setContentsMargins(8, 6, 8, 6)
        gbox_lay.setSpacing(4)
        self.genre_checks = {}

        # v2.23.5: 用 fanqie_genre_provider 提供分组数据
        try:
            from core.fanqie_genre_provider import get_genre_groups
            genre_groups = get_genre_groups()
        except Exception:
            # 退回到老 GENRES(扁平)作为单一组
            genre_groups = [("题材", [n for row in GENRES for n in row])]

        # 默认勾选的题材(尽量挑番茄上有热度的)
        defaults = {"都市日常", "都市修真", "豪门总裁", "玄幻言情"}

        # 主 grid layout(子分组用 QGroupBox + QGridLayout)
        for group_name, items in genre_groups:
            sub = QGroupBox(group_name)
            sub.setStyleSheet(
                "QGroupBox { font-weight: normal; margin-top: 6px; padding-top: 8px;}"
                "QGroupBox::title { subcontrol-position: top left; padding: 0 4px; }")
            sublay = QGridLayout(sub)
            sublay.setContentsMargins(6, 4, 6, 4)
            sublay.setSpacing(4)
            for i, name in enumerate(items):
                cb = QCheckBox(name)
                if name in defaults:
                    cb.setChecked(True)
                self.genre_checks[name] = cb
                r, c = i // 4, i % 4
                sublay.addWidget(cb, r, c)
            gbox_lay.addWidget(sub)

        # 第 3 项:加 "✏️ 自定义" 按钮
        custom_row = QHBoxLayout()
        self.btn_genre_custom = QPushButton("✏️ 自定义题材")
        self.btn_genre_custom.setStyleSheet(
            "QPushButton { color:#4e79cd; padding:4px 8px; border:1px dashed #1a4480; }"
            "QPushButton:hover { background:#eaf3ff; }")
        self.btn_genre_custom.clicked.connect(self._add_custom_genre)
        custom_row.addWidget(self.btn_genre_custom)
        custom_row.addStretch()
        gbox_lay.addLayout(custom_row)

        # _genre_layout: 老代码 (_add_custom_checkbox) 期望它是 QGridLayout
        # 这里用最后一个分组的 sub layout 充当"自定义题材落地点"
        # (实际新自定义题材都会加到最后一个"通用题材"组)
        self._genre_layout = sublay  # 指向最后一个 sub(通用题材)
        self._genre_custom_row = (len(items) + 3) // 4  # 通用组下一空行
        self._genre_custom_col = 0
        layout.addWidget(gbox)

        # ---- 主角名字(生成大纲时使用) ----
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("男主名字:"))
        self.input_male_lead = QLineEdit()
        self.input_male_lead.setPlaceholderText("如: 顾衍之")
        self.input_male_lead.setMaximumWidth(150)
        name_row.addWidget(self.input_male_lead)
        name_row.addWidget(QLabel("女主名字:"))
        self.input_female_lead = QLineEdit()
        self.input_female_lead.setPlaceholderText("如: 苏棠")
        self.input_female_lead.setMaximumWidth(150)
        name_row.addWidget(self.input_female_lead)
        name_row.addStretch()
        layout.addLayout(name_row)

        # ---- 灵感 ----
        layout.addWidget(QLabel("创意灵感(注意手动标明男频还是女频)"))
        irow = QHBoxLayout()
        self.inspiration_edit = QPlainTextEdit()
        self.inspiration_edit.setMaximumHeight(120)
        self.inspiration_edit.setPlainText("")
        self.inspiration_edit.setPlaceholderText("在这里输入或粘贴你的创意灵感...")
        irow.addWidget(self.inspiration_edit, 1)
        ibtns = QVBoxLayout()
        self.btn_gen_insp = QPushButton("AI生成灵感")
        self.btn_regen_insp = QPushButton("重新生成")
        self.btn_import_txt = QPushButton("📁 从TXT导入文字")
        for b in (self.btn_gen_insp, self.btn_regen_insp, self.btn_import_txt):
            ibtns.addWidget(b)
        irow.addLayout(ibtns)
        layout.addLayout(irow)

        # ---- 盘古禁用词白名单 ----
        wl_box = QGroupBox("🛡️ 盘古禁用词白名单(避免误杀,用空格/换行分隔)")
        wl_lay = QVBoxLayout(wl_box)
        self.pangu_whitelist_edit = QPlainTextEdit()
        self.pangu_whitelist_edit.setMaximumHeight(60)
        self.pangu_whitelist_edit.setPlaceholderText(
            "例如:仿佛 似乎 知道  (这些词会被允许出现在正文,不再被标红)")
        wl_lay.addWidget(self.pangu_whitelist_edit)
        wl_btn_row = QHBoxLayout()
        self.btn_pangu_wl_apply = QPushButton("✓ 应用白名单")
        self.btn_pangu_wl_apply.setStyleSheet(
            "background:#1a8a72;color:white;padding:4px 10px;border-radius:3px;")
        wl_btn_row.addWidget(self.btn_pangu_wl_apply)
        wl_btn_row.addStretch()
        wl_lay.addLayout(wl_btn_row)
        layout.addWidget(wl_box)

        # ---- v1.10:🔊 TTS 朗读配置(默认折叠) ----
        tts_box = QGroupBox("🔊 TTS 朗读配置(点击展开)")
        tts_box.setCheckable(True)
        tts_box.setChecked(False)
        tts_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        tts_lay = QVBoxLayout(tts_box)
        # 后端下拉
        tts_r1 = QHBoxLayout()
        tts_r1.addWidget(QLabel("后端:"))
        self.cb_tts_backend = QComboBox()
        try:
            from tts_backend import list_backends as _list_bk
            for bn, disp in _list_bk():
                self.cb_tts_backend.addItem(disp, bn)
        except Exception:
            self.cb_tts_backend.addItem("(tts_backend.py 加载失败)", "disabled")
        # 持久化
        from PyQt5.QtCore import QSettings as _QS_tts
        _ts = _QS_tts("NovelAI", "TTS")
        _saved_backend = _ts.value("backend", "edge_tts", type=str)
        _idx = max(0, self.cb_tts_backend.findData(_saved_backend))
        self.cb_tts_backend.setCurrentIndex(_idx)
        self.cb_tts_backend.currentIndexChanged.connect(
            lambda i: _QS_tts("NovelAI", "TTS").setValue(
                "backend", self.cb_tts_backend.itemData(i)))
        tts_r1.addWidget(self.cb_tts_backend, 1)
        tts_lay.addLayout(tts_r1)
        # EdgeTTS 音色下拉
        tts_r2 = QHBoxLayout()
        tts_r2.addWidget(QLabel("EdgeTTS 音色:"))
        self.cb_edge_voice = QComboBox()
        try:
            from tts_backend import EdgeTTSBackend as _ETB
            for vid, vname in _ETB.VOICES.items():
                self.cb_edge_voice.addItem(vname, vid)
        except Exception:
            self.cb_edge_voice.addItem("(加载失败)", "zh-CN-XiaoxiaoNeural")
        _saved_voice = _ts.value("edge_voice", "zh-CN-XiaoxiaoNeural", type=str)
        _vidx = max(0, self.cb_edge_voice.findData(_saved_voice))
        self.cb_edge_voice.setCurrentIndex(_vidx)
        self.cb_edge_voice.currentIndexChanged.connect(
            lambda i: _QS_tts("NovelAI", "TTS").setValue(
                "edge_voice", self.cb_edge_voice.itemData(i)))
        tts_r2.addWidget(self.cb_edge_voice, 1)
        tts_lay.addLayout(tts_r2)
        # Index-TTS URL
        tts_r3 = QHBoxLayout()
        tts_r3.addWidget(QLabel("Index-TTS URL:"))
        self.ed_index_url = QLineEdit(
            _ts.value("index_url", "http://127.0.0.1:7862/", type=str))
        self.ed_index_url.setToolTip(
            "本地 Index-TTS Gradio 服务地址。默认 7862,看你启动时显示的端口。")
        self.ed_index_url.textChanged.connect(
            lambda t: _QS_tts("NovelAI", "TTS").setValue("index_url", t))
        tts_r3.addWidget(self.ed_index_url, 1)
        tts_lay.addLayout(tts_r3)
        # Index-TTS 参考音频
        tts_r4 = QHBoxLayout()
        tts_r4.addWidget(QLabel("Index-TTS 参考音频:"))
        self.ed_index_ref = QLineEdit(_ts.value("index_ref_audio", "", type=str))
        self.ed_index_ref.setToolTip(
            "声音克隆的参考音频(WAV/MP3,10-30 秒清晰人声),Index-TTS 必填。\n"
            "可以是 Index-TTS 自带的示例,也可以是你提供的人声样本。")
        self.ed_index_ref.textChanged.connect(
            lambda t: _QS_tts("NovelAI", "TTS").setValue("index_ref_audio", t))
        self.btn_pick_ref = QPushButton("📁 选择...")
        self.btn_pick_ref.clicked.connect(self._on_pick_index_ref_audio)
        tts_r4.addWidget(self.ed_index_ref, 1)
        tts_r4.addWidget(self.btn_pick_ref)
        tts_lay.addLayout(tts_r4)
        # 测试按钮
        tts_r5 = QHBoxLayout()
        self.btn_tts_test = QPushButton("🎵 测试 TTS")
        self.btn_tts_test.setStyleSheet(
            "background:#1f8b4d;color:white;padding:6px 14px;border-radius:3px;")
        self.btn_tts_test.setToolTip("合成一段测试音频,看看后端是否工作 + 音色是否合心意")
        self.btn_tts_test.clicked.connect(self._on_tts_test)
        tts_r5.addWidget(self.btn_tts_test)
        tts_r5.addStretch()
        tts_lay.addLayout(tts_r5)
        layout.addWidget(tts_box)

        # ---- v1.32:🔬 13 法对话诊断 ----
        dc_box = QGroupBox("🔬 13 法对话诊断")
        dc_box.setStyleSheet("QGroupBox::title { font-weight: bold; }")
        dc_lay = QVBoxLayout(dc_box)
        # 老刀风格开关
        from PyQt5.QtCore import QSettings as _QS_dc
        _dcs = _QS_dc("NovelAI", "DialogueCritic")
        self.chk_dc_laodao = QCheckBox("🔪 启用老刀风格毒舌点评(AI 深度诊断时)")
        self.chk_dc_laodao.setChecked(_dcs.value("laodao_style", False, type=bool))
        self.chk_dc_laodao.setToolTip(
            "勾选后,AI 诊断 verdict 字段用老刀语气:\n"
            "直接、毒舌、不绕弯,看到稚嫩处直接说『删了重写』,\n"
            "看到精彩处也大方夸『这处一击毙命,顶级笔法』。\n"
            "不勾 = 中性专业评价。")
        self.chk_dc_laodao.stateChanged.connect(
            lambda s: _QS_dc("NovelAI", "DialogueCritic").setValue(
                "laodao_style", bool(s)))
        dc_lay.addWidget(self.chk_dc_laodao)
        # 自动诊断开关(每章生成后自动跑静态扫描)
        self.chk_dc_auto = QCheckBox("✨ 每章生成后自动跑静态扫描(发现红线自动提示)")
        self.chk_dc_auto.setChecked(_dcs.value("auto_static", False, type=bool))
        self.chk_dc_auto.setToolTip(
            "勾选后,AI 写完一章自动跑 13 法本地静态扫描(不发 AI 不耗 token)。\n"
            "如果发现红线违反(说/道超标 / 套词 / 连续 X 说),弹提示。\n"
            "深度 AI 评分仍需手动点 🔬 13法诊断 按钮触发。")
        self.chk_dc_auto.stateChanged.connect(
            lambda s: _QS_dc("NovelAI", "DialogueCritic").setValue(
                "auto_static", bool(s)))
        dc_lay.addWidget(self.chk_dc_auto)
        # 提示
        _hint_dc = QLabel(
            "ℹ 章节编辑器顶部 🔬 13法诊断 按钮(或 F9)触发深度 AI 评分。\n"
            "  自动扫描是本地的,不发 AI 不耗 token,只看『说/道』密度和套词。")
        _hint_dc.setStyleSheet("color: #6d7c95; font-size: 11px;")
        _hint_dc.setWordWrap(True)
        dc_lay.addWidget(_hint_dc)
        layout.addWidget(dc_box)

        # ---- 盘古快捷工具 ----
        pangu_tools_box = QGroupBox("🛕 盘古快捷工具")
        pangu_tools_lay = QVBoxLayout(pangu_tools_box)
        p_row1 = QHBoxLayout()
        self.btn_pangu_style = QPushButton("🎯 风格匹配(基于关键词)")
        self.btn_pangu_style.setStyleSheet(
            "background:#1a8a72;color:white;padding:6px 12px;border-radius:3px;")
        self.btn_pangu_style.setToolTip(
            "输入题材/灵感关键词,匹配主辅风格 + 女角色基调 + 适合平台")
        p_row1.addWidget(self.btn_pangu_style)
        p_row1.addStretch()
        pangu_tools_lay.addLayout(p_row1)
        p_row2 = QHBoxLayout()
        self.btn_pangu_arch = QPushButton("🏗️ 建筑师")
        self.btn_pangu_dream = QPushButton("🎭 造梦师")
        self.btn_pangu_alch = QPushButton("⚗️ 炼金术士")
        self.btn_pangu_sculpt = QPushButton("🗿 雕刻家")
        for b, color, tip in [
            (self.btn_pangu_arch, "#34495e", "结构/大纲/世界观:严密自洽,优先骨架"),
            (self.btn_pangu_dream, "#9b59b6", "氛围/情绪/意象:渲染感官与情绪密度"),
            (self.btn_pangu_alch, "#e67e22", "提纯/优化/字数死磕:精准压缩"),
            (self.btn_pangu_sculpt, "#7f8c8d", "成品/润色:先删再改、能砍的不改"),
        ]:
            b.setStyleSheet(
                f"background:{color};color:white;padding:6px 10px;border-radius:3px;")
            b.setToolTip(tip)
            p_row2.addWidget(b)
        p_row2.addStretch()
        pangu_tools_lay.addLayout(p_row2)
        layout.addWidget(pangu_tools_box)

        # ---- 写作参数(v2.23.4 紧凑化:5 个设置合并为一个网格) ----
        param_box = QGroupBox("写作参数")
        param_grid = QGridLayout(param_box)
        param_grid.setSpacing(4)
        param_grid.setContentsMargins(8, 8, 8, 8)

        def _add_radio_row(grid, row, label, group_attr, options, default, parent):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight:bold; font-size:11px; color:#6d7c95;")
            grid.addWidget(lbl, row, 0)
            grp = QButtonGroup(parent)
            for i, text in enumerate(options):
                rb = QRadioButton(text)
                if text == default:
                    rb.setChecked(True)
                grp.addButton(rb, i)
                grid.addWidget(rb, row, i + 1)
            setattr(parent, group_attr, grp)

        _add_radio_row(param_grid, 0, "平台定位:", "platform_group",
                       PLATFORMS, "番茄小说", self)
        _add_radio_row(param_grid, 1, "目标读者:", "audience_group",
                       ["青少年", "青年", "成人"], "成人", self)
        _add_radio_row(param_grid, 2, "爽点密度:", "density_group",
                       ["低密度", "适中", "高密度", "极致爽"], "极致爽", self)
        _add_radio_row(param_grid, 3, "成长曲线:", "growth_group",
                       ["慢热型", "均衡型", "爆发型"], "爆发型", self)
        _add_radio_row(param_grid, 4, "冲突强度:", "conflict_group",
                       ["轻度", "中度", "强烈", "极端"], "极端", self)
        layout.addWidget(param_box)

        # ---- 时代背景 ----
        era_box = QGroupBox("时代背景")
        self.box_era = era_box  # 第 7 项
        era_lay = QHBoxLayout(era_box)
        self.era_combo = QComboBox()
        self.era_combo.setEditable(False)
        self.era_combo.addItems(ERAS)
        # 末尾加一个"✏️ 自定义..."条目
        self.era_combo.addItem("✏️ 自定义...")
        self.era_combo.setCurrentText("古代王朝")
        # 第 4 项:选中"自定义..."条目 → 弹输入框,新值加进下拉并选中
        def _on_era_changed(text):
            if text == "✏️ 自定义...":
                from PyQt5.QtWidgets import QInputDialog
                new_era, ok = QInputDialog.getText(
                    self, "自定义时代背景",
                    "输入新的时代背景(回车确认):")
                if ok and new_era.strip():
                    new_era = new_era.strip()
                    # 插入到"自定义..."条目前
                    insert_idx = self.era_combo.count() - 1
                    # 检查是否已存在
                    exist = self.era_combo.findText(new_era)
                    if exist >= 0:
                        self.era_combo.setCurrentIndex(exist)
                    else:
                        self.era_combo.insertItem(insert_idx, new_era)
                        self.era_combo.setCurrentText(new_era)
                    # 持久化自定义时代列表
                    self._save_custom_eras()
                else:
                    # 取消 → 回到上一个选项(不是自定义占位符)
                    if self.era_combo.count() > 1:
                        self.era_combo.setCurrentIndex(0)
        self.era_combo.currentTextChanged.connect(_on_era_changed)
        era_lay.addWidget(self.era_combo, 1)
        era_lay.addWidget(QLabel("自定义:"))
        self.era_custom = QLineEdit("古代王朝")
        era_lay.addWidget(self.era_custom, 1)
        layout.addWidget(era_box)
        # 启动时加载用户保存过的自定义时代
        try:
            self._load_custom_eras()
        except Exception:
            pass

        # ---- 生成规模(v2.23.4: 紧凑化 — 三项合一) ----
        scale_box = QGroupBox("生成规模")
        scale_grid = QGridLayout(scale_box)
        scale_grid.setSpacing(4)
        scale_grid.setContentsMargins(8, 8, 8, 8)

        # 总章节数(第 0 行)
        scale_grid.addWidget(QLabel("总章节:"), 0, 0)
        self.chapter_preset_group = QButtonGroup(self)
        for i, n in enumerate(["60章", "120章", "300章", "500章"]):
            rb = QRadioButton(n)
            if n == "300章":
                rb.setChecked(True)
            self.chapter_preset_group.addButton(rb, i)
            scale_grid.addWidget(rb, 0, i + 1)
        self.chapter_custom = QSpinBox()
        self.chapter_custom.setRange(10, 9999)
        self.chapter_custom.setValue(300)
        self.chapter_custom.setFixedWidth(80)
        scale_grid.addWidget(self.chapter_custom, 0, 5)
        for btn in self.chapter_preset_group.buttons():
            btn.toggled.connect(self._sync_chapter_preset)

        # 每章字数(第 1 行)
        scale_grid.addWidget(QLabel("每章字数:"), 1, 0)
        self.words_preset_group = QButtonGroup(self)
        for i, w in enumerate(["1500字", "2000字", "3000字"]):
            rb = QRadioButton(w)
            if w == "3000字":
                rb.setChecked(True)
            self.words_preset_group.addButton(rb, i)
            scale_grid.addWidget(rb, 1, i + 1)
        self.words_custom = QSpinBox()
        self.words_custom.setRange(500, 20000)
        self.words_custom.setValue(3000)
        self.words_custom.setSingleStep(500)
        self.words_custom.setFixedWidth(80)
        scale_grid.addWidget(self.words_custom, 1, 4)
        for btn in self.words_preset_group.buttons():
            btn.toggled.connect(self._sync_words_preset)

        # 大纲详细度(第 2 行)
        scale_grid.addWidget(QLabel("大纲详细度:"), 2, 0)
        self.detail_group = QButtonGroup(self)
        for i, d in enumerate(["简洁", "标准", "详细"]):
            rb = QRadioButton(d)
            if d == "详细":
                rb.setChecked(True)
            self.detail_group.addButton(rb, i)
            scale_grid.addWidget(rb, 2, i + 1)

        layout.addWidget(scale_box)

        # ---- 风格权重(滑块,总计=100%) ----
        sw_box = QGroupBox("风格权重 (总计 100%)")
        sw_lay = QGridLayout(sw_box)
        self.style_sliders = {}
        self._style_pct_labels = {}
        self._style_balancing = False  # 防递归
        defaults = {"爽文": 50, "文学": 0, "黑暗": 0, "轻松": 0, "搞笑": 50}
        for r, name in enumerate(STYLE_DIMENSIONS):
            sw_lay.addWidget(QLabel(name), r, 0)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 100)
            sl.setValue(defaults.get(name, 0))
            self.style_sliders[name] = sl
            pct = QLabel(f"{defaults.get(name, 0)}%")
            pct.setMinimumWidth(40)
            pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._style_pct_labels[name] = pct
            sl.valueChanged.connect(
                lambda v, n=name: self._on_style_weight_changed(n, v))
            sw_lay.addWidget(sl, r, 1)
            sw_lay.addWidget(pct, r, 2)
        sw_lay.setColumnStretch(1, 1)
        # 总计标签
        self._style_total_label = QLabel("总计: 100%")
        self._style_total_label.setStyleSheet("font-weight:bold; color:#1f8b4d;")
        sw_lay.addWidget(self._style_total_label, len(STYLE_DIMENSIONS), 0, 1, 3)
        layout.addWidget(sw_box)

        # ---- 节奏(v2.23.4: 内联,不用 GroupBox) ----
        rh_row = QHBoxLayout()
        rh_row.addWidget(QLabel("故事节奏:"))
        self.rhythm_group = QButtonGroup(self)
        for i, r in enumerate(["慢热", "适中", "紧凑"]):
            rb = QRadioButton(r)
            if r == "适中":
                rb.setChecked(True)
            self.rhythm_group.addButton(rb, i)
            rh_row.addWidget(rb)
        rh_row.addStretch()
        layout.addLayout(rh_row)

        # ---- 结局倾向(可多选) ----
        ed_box = QGroupBox("结局倾向 (可多选)")
        ed_lay = QGridLayout(ed_box)
        self.ending_checks = {}
        for r, row_items in enumerate(ENDINGS):
            for c, name in enumerate(row_items):
                cb = QCheckBox(name)
                if name == "圆满结局":
                    cb.setChecked(True)
                self.ending_checks[name] = cb
                ed_lay.addWidget(cb, r, c)
        layout.addWidget(ed_box)

        # ---- 创作模式(v2.23.4: 内联) ----
        cm_row = QHBoxLayout()
        cm_row.addWidget(QLabel("创作模式:"))
        self.mode_group = QButtonGroup(self)
        rb_stable = QRadioButton("稳定版(经典套路)")
        rb_creative = QRadioButton("创造版(创新突破)")
        rb_creative.setChecked(True)
        self.mode_group.addButton(rb_stable, 0)
        self.mode_group.addButton(rb_creative, 1)
        cm_row.addWidget(rb_stable)
        cm_row.addWidget(rb_creative)
        cm_row.addStretch()
        layout.addLayout(cm_row)

        # ---- 提示词字数偏移 ----
        po_row = QHBoxLayout()
        po_row.addWidget(QLabel("提示词字数偏移:"))
        self.prompt_offset = QSpinBox()
        self.prompt_offset.setRange(-2000, 2000)
        self.prompt_offset.setSingleStep(50)
        self.prompt_offset.setValue(-200)
        po_row.addWidget(self.prompt_offset)
        po_row.addWidget(QLabel("(负数=要求 AI 写少点,正数=要求多写)"))
        po_row.addStretch()
        layout.addLayout(po_row)

        # ---- 金手指(可多选) ----
        gf_box = QGroupBox("金手指 (可多选)")
        self.box_golden = gf_box  # 第 7 项
        gf_outer = QVBoxLayout(gf_box)
        # 工具按钮:全选 / 清空
        gf_tools = QHBoxLayout()
        btn_gf_all = QPushButton("全选")
        btn_gf_clear = QPushButton("清空")
        btn_gf_all.setMaximumWidth(80); btn_gf_clear.setMaximumWidth(80)
        gf_tools.addWidget(btn_gf_all); gf_tools.addWidget(btn_gf_clear)
        gf_tools.addStretch()
        gf_outer.addLayout(gf_tools)
        gf_grid = QGridLayout()
        self.golden_checks = {}
        for idx, name in enumerate(GOLDEN_FINGERS):
            r, c = idx // 4, idx % 4
            cb = QCheckBox(name)
            self.golden_checks[name] = cb
            gf_grid.addWidget(cb, r, c)
        gf_outer.addLayout(gf_grid)
        btn_gf_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self.golden_checks.values()])
        btn_gf_clear.clicked.connect(lambda: [cb.setChecked(False) for cb in self.golden_checks.values()])
        # 第 5 项:金手指自定义按钮
        self._golden_grid = gf_grid
        btn_gf_custom = QPushButton("✏️ 自定义金手指")
        btn_gf_custom.setStyleSheet(
            "QPushButton { color:#4e79cd; padding:4px 8px; border:1px dashed #1a4480; } "
            "QPushButton:hover { background:#eaf3ff; }")
        btn_gf_custom.clicked.connect(self._add_custom_golden)
        gf_outer.addWidget(btn_gf_custom)
        layout.addWidget(gf_box)

        # ---- 主角人设(可多选) ----
        pe_box = QGroupBox("主角人设 (可多选)")
        pe_outer = QVBoxLayout(pe_box)
        pe_tools = QHBoxLayout()
        btn_pe_all = QPushButton("全选")
        btn_pe_clear = QPushButton("清空")
        btn_pe_all.setMaximumWidth(80); btn_pe_clear.setMaximumWidth(80)
        pe_tools.addWidget(btn_pe_all); pe_tools.addWidget(btn_pe_clear)
        pe_tools.addStretch()
        pe_outer.addLayout(pe_tools)
        pe_grid = QGridLayout()
        self.persona_checks = {}
        for idx, name in enumerate(PERSONAS):
            r, c = idx // 4, idx % 4
            cb = QCheckBox(name)
            self.persona_checks[name] = cb
            pe_grid.addWidget(cb, r, c)
        pe_outer.addLayout(pe_grid)
        btn_pe_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self.persona_checks.values()])
        btn_pe_clear.clicked.connect(lambda: [cb.setChecked(False) for cb in self.persona_checks.values()])
        # 第 6 项:主角人设自定义按钮
        self._persona_grid = pe_grid
        btn_pe_custom = QPushButton("✏️ 自定义主角人设")
        btn_pe_custom.setStyleSheet(
            "QPushButton { color:#4e79cd; padding:4px 8px; border:1px dashed #1a4480; } "
            "QPushButton:hover { background:#eaf3ff; }")
        btn_pe_custom.clicked.connect(self._add_custom_persona)
        pe_outer.addWidget(btn_pe_custom)
        layout.addWidget(pe_box)

        layout.addStretch()

        # 启动时从 QSettings 恢复白名单并应用
        try:
            from PyQt5.QtCore import QSettings as _QS
            _s = _QS("NovelAI", "CreationSettings")
            _wl = _s.value("pangu_whitelist", "", type=str)
            if _wl:
                self.pangu_whitelist_edit.setPlainText(_wl)
                try:
                    from pangu_system import PanguEngine
                    PanguEngine.set_whitelist(_wl)
                except Exception:
                    pass
        except Exception:
            pass

        # 安装实时持久化:任何控件变化立即 save_settings(防止程序异常退出丢失)
        # save_settings 内部一次性写 30+ 项,200ms 防抖避免连续切换时频繁写盘
        try:
            from PyQt5.QtCore import QTimer
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(200)
            self._save_timer.timeout.connect(self.save_settings)
            def _trig():
                if hasattr(self, "_save_timer"):
                    self._save_timer.start()
            # 注册所有需要持久化的控件
            for group in (self.platform_group, self.audience_group, self.density_group,
                          self.growth_group, self.conflict_group, self.detail_group,
                          self.rhythm_group, self.mode_group, self.ai_group):
                try:
                    group.buttonClicked.connect(lambda *_: _trig())
                except Exception:
                    pass
            for d in (self.genre_checks, self.ending_checks, self.golden_checks,
                      self.persona_checks):
                for cb in d.values():
                    try:
                        cb.stateChanged.connect(lambda *_: _trig())
                    except Exception:
                        pass
            self.era_combo.currentTextChanged.connect(lambda *_: _trig())
            self.era_custom.textChanged.connect(lambda *_: _trig())
            self.chapter_custom.valueChanged.connect(lambda *_: _trig())
            self.words_custom.valueChanged.connect(lambda *_: _trig())
            self.prompt_offset.valueChanged.connect(lambda *_: _trig())
            self.custom_url.textChanged.connect(lambda *_: _trig())
            self.delay_check.stateChanged.connect(lambda *_: _trig())
            self.pangu_check.stateChanged.connect(lambda *_: _trig())
            for sl in self.style_sliders.values():
                try:
                    sl.valueChanged.connect(lambda *_: _trig())
                except Exception:
                    pass
        except Exception as _e_persist:
            print(f"[持久化注册] 部分控件挂载失败,不影响功能:{_e_persist}")

    # ---- 联动 ----
    def _sync_chapter_preset(self, checked):
        if not checked: return
        b = self.chapter_preset_group.checkedButton()
        if b:
            n = int(re.sub(r'\D', '', b.text()) or 300)
            self.chapter_custom.setValue(n)

    def _sync_words_preset(self, checked):
        if not checked: return
        b = self.words_preset_group.checkedButton()
        if b:
            n = int(re.sub(r'\D', '', b.text()) or 3000)
            self.words_custom.setValue(n)

    # ---- Getter ----
    def get_selected_ai(self):
        b = self.ai_group.checkedButton()
        return b.text() if b else "DeepSeek"

    def get_selected_genres(self):
        return [n for n, cb in self.genre_checks.items() if cb.isChecked()]

    def get_inspiration(self):
        return self.inspiration_edit.toPlainText()

    def get_title(self):
        return self.title_input.text() or "我的小说"

    def get_platform(self):
        b = self.platform_group.checkedButton()
        return b.text() if b else "番茄小说"

    def get_audience(self):
        b = self.audience_group.checkedButton()
        return b.text() if b else "成人"

    def get_density(self):
        b = self.density_group.checkedButton()
        return b.text() if b else "适中"

    def get_growth(self):
        b = self.growth_group.checkedButton()
        return b.text() if b else "均衡型"

    def get_conflict(self):
        b = self.conflict_group.checkedButton()
        return b.text() if b else "中度"

    def get_era(self):
        return self.era_custom.text().strip() or self.era_combo.currentText()

    def get_chapter_count(self):
        return self.chapter_custom.value()

    def get_words_per_chapter(self):
        return self.words_custom.value()

    def get_outline_detail(self):
        b = self.detail_group.checkedButton()
        return b.text() if b else "标准"

    def _on_style_weight_changed(self, changed_name, new_val):
        """风格权重滑块变化 → 自动平衡其他滑块使总计=100"""
        if self._style_balancing:
            return
        self._style_balancing = True
        try:
            others = [n for n in self.style_sliders if n != changed_name]
            other_total = sum(self.style_sliders[n].value() for n in others)
            remaining = 100 - new_val

            if remaining < 0:
                # 超过100,强制回调
                new_val = 100
                remaining = 0
                self.style_sliders[changed_name].setValue(100)

            if other_total > 0:
                # 按比例缩减其他滑块
                ratio = remaining / other_total
                for n in others:
                    old = self.style_sliders[n].value()
                    self.style_sliders[n].setValue(int(old * ratio))
            elif remaining > 0 and others:
                # 其他都是0,把剩余平分给第一个非零的(或第一个)
                self.style_sliders[others[0]].setValue(remaining)

            # 更新所有标签
            total = 0
            for n, sl in self.style_sliders.items():
                v = sl.value()
                total += v
                self._style_pct_labels[n].setText(f"{v}%")
            # 修正舍入误差
            if total != 100 and others:
                diff = 100 - total
                first_other = others[0]
                self.style_sliders[first_other].setValue(
                    self.style_sliders[first_other].value() + diff)
                self._style_pct_labels[first_other].setText(
                    f"{self.style_sliders[first_other].value()}%")
                total = 100
            self._style_total_label.setText(f"总计: {total}%")
            self._style_total_label.setStyleSheet(
                "font-weight:bold; color:#1f8b4d;" if total == 100
                else "font-weight:bold; color:#e74c3c;")
        finally:
            self._style_balancing = False

    def get_style_weights(self):
        return {n: sl.value() for n, sl in self.style_sliders.items()}

    def get_rhythm(self):
        b = self.rhythm_group.checkedButton()
        return b.text() if b else "适中"

    def get_endings(self):
        return [n for n, cb in self.ending_checks.items() if cb.isChecked()]

    def get_creation_mode(self):
        b = self.mode_group.checkedButton()
        return b.text() if b else "创造版"

    def get_prompt_offset(self):
        return self.prompt_offset.value()

    def get_golden_fingers(self):
        return [n for n, cb in self.golden_checks.items() if cb.isChecked()]

    def get_personas(self):
        return [n for n, cb in self.persona_checks.items() if cb.isChecked()]

    def _toggle_lock(self):
        """切换锁定/解锁"""
        locked = self.btn_lock.isChecked()
        self._settings_locked = locked
        if locked:
            self.btn_lock.setText("🔒 设置已锁定(点击解锁)")
            self.btn_lock.setStyleSheet(
                "QPushButton { background:#e74c3c; color:white; padding:6px 16px;"
                "font-weight:bold; border-radius:4px; }")
        else:
            self.btn_lock.setText("🔓 设置已解锁(点击锁定)")
            self.btn_lock.setStyleSheet(
                "QPushButton { background:#1f8b4d; color:white; padding:6px 16px;"
                "font-weight:bold; border-radius:4px; }")
        # 禁用/启用所有滑块和SpinBox
        for sl in self.findChildren(QSlider):
            sl.setEnabled(not locked)
        for sb in self.findChildren(QSpinBox):
            sb.setEnabled(not locked)

    def get_full_settings_block(self):
        """生成一段格式化的「完整设定」文本,用于注入提示词"""
        sw = self.get_style_weights()
        sw_str = "、".join(f"{k}{v}%" for k, v in sw.items() if v > 0) or "默认均衡"
        endings = self.get_endings() or ["未指定"]
        gfs = self.get_golden_fingers()
        gf_str = "、".join(gfs) if gfs else "无金手指"
        ps = self.get_personas()
        ps_str = "、".join(ps) if ps else "未指定"
        return (
            f"题材:{'/'.join(self.get_selected_genres()) or '言情'}\n"
            f"小说标题:{self.get_title()}\n"
            f"平台定位:{self.get_platform()}\n"
            f"目标读者:{self.get_audience()}\n"
            f"爽点密度:{self.get_density()}\n"
            f"成长曲线:{self.get_growth()}\n"
            f"冲突强度:{self.get_conflict()}\n"
            f"时代背景:{self.get_era()}\n"
            f"风格权重:{sw_str}\n"
            f"故事节奏:{self.get_rhythm()}\n"
            f"结局倾向:{'、'.join(endings)}\n"
            f"创作模式:{self.get_creation_mode()}\n"
            f"金手指:{gf_str}\n"
            f"主角人设:{ps_str}\n"
            f"男主名字:{self.input_male_lead.text().strip() or '未指定(AI自动取名)'}\n"
            f"女主名字:{self.input_female_lead.text().strip() or '未指定(AI自动取名)'}\n"
            f"每章字数:{self.get_words_per_chapter()} 字"
            f"(偏移 {self.get_prompt_offset():+d})\n"
            f"大纲详细度:{self.get_outline_detail()}\n"
        )


    def _on_pick_index_ref_audio(self):
        from PyQt5.QtWidgets import QFileDialog
        fn, _ = QFileDialog.getOpenFileName(
            self, "选择 Index-TTS 参考音频",
            "", "音频 (*.wav *.mp3 *.m4a *.flac *.ogg);;所有 (*)")
        if fn:
            self.ed_index_ref.setText(fn)

    def _on_tts_test(self):
        """合成一段固定测试文本,弹窗告知结果。不放后台线程,因为是测试,允许短暂卡 UI。"""
        try:
            import tts_backend as _tb
        except ImportError as e:
            QMessageBox.warning(self, "TTS 测试",
                f"tts_backend.py 加载失败:{e}")
            return
        backend_name = self.cb_tts_backend.currentData()
        if backend_name == "disabled":
            QMessageBox.information(self, "TTS 测试", "请先选一个后端(EdgeTTS 或 Index-TTS)")
            return
        kwargs = {}
        voice = None
        if backend_name == "edge_tts":
            voice = self.cb_edge_voice.currentData()
        elif backend_name == "index_tts":
            kwargs = {
                "url": self.ed_index_url.text().strip() or "http://127.0.0.1:7862/",
                "ref_audio": self.ed_index_ref.text().strip(),
            }
            voice = kwargs["ref_audio"]
            if not voice:
                QMessageBox.warning(self, "TTS 测试", "Index-TTS 需要先选参考音频")
                return
        backend = _tb.get_backend(backend_name, **kwargs)
        if not backend.is_available():
            tip = ("pip install edge-tts" if backend_name == "edge_tts"
                   else "pip install gradio_client")
            QMessageBox.warning(self, "TTS 测试",
                f"后端 {backend.display} 不可用。\n命令行运行:{tip}")
            return
        import tempfile, os
        test_text = "你好,这是盘古超级写作助手的 TTS 测试,如果你听到这句话,说明配置成功。"
        ext = "mp3" if backend_name == "edge_tts" else "wav"
        out = os.path.join(tempfile.gettempdir(),
                           f"novelai_tts_test.{ext}")
        try:
            ok, msg = backend.synthesize(test_text, out, voice=voice, speed=1.0)
        except Exception as e:
            ok, msg = False, f"未捕获异常:{type(e).__name__}: {e}"
        if not ok:
            QMessageBox.warning(self, "TTS 测试失败", msg)
            return
        # 播放 — v1.16 BUG-038:pygame 优先(SDL2,无视 WAV 编码),winsound 次之
        played_by = None
        play_err = None
        import sys, os
        ext = os.path.splitext(out)[1].lower()

        # WAV 格式诊断 — 打到 console,帮助定位 winsound 不兼容问题
        if ext == ".wav":
            try:
                import wave
                with wave.open(out, "rb") as _w:
                    print(
                        f"[TTS test] WAV 诊断: "
                        f"{_w.getnchannels()}ch / "
                        f"{_w.getsampwidth()*8}bit / "
                        f"{_w.getframerate()}Hz / "
                        f"{_w.getnframes()}帧 / "
                        f"comptype={_w.getcomptype()}",
                        flush=True)
            except Exception as _we:
                print(f"[TTS test] WAV header 解析失败({_we}) — 可能是非标准编码,winsound 大概率不认", flush=True)

        # 路径 1(新增): pygame.mixer — SDL2 后端,绕过所有 WAV 格式坑
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            print(f"[TTS test] pygame 已 init,准备 load: {out}", flush=True)
            pygame.mixer.music.load(out)
            pygame.mixer.music.play()
            played_by = "pygame.mixer(SDL2,最稳)"
            print(f"[TTS test] pygame.mixer.music.play() 已调用", flush=True)
        except ImportError:
            print(f"[TTS test] 没装 pygame,尝试 winsound 兜底(建议 pip install pygame)", flush=True)
            play_err = "pygame 未安装"
        except Exception as e:
            play_err = f"pygame 失败:{e}"
            print(f"[TTS test] pygame 异常:{e}", flush=True)

        # 路径 2:Windows + WAV → winsound(标准库兜底)
        if played_by is None and sys.platform == "win32" and ext == ".wav":
            try:
                _exists = os.path.exists(out)
                _size = os.path.getsize(out) if _exists else 0
                print(f"[TTS test] 准备 winsound 播放: {out} exists={_exists} size={_size}", flush=True)
                if not _exists or _size == 0:
                    play_err = f"文件不存在或空(size={_size}),winsound 跳过"
                else:
                    import winsound
                    winsound.PlaySound(out, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    played_by = "winsound(标准库)"
                    print(f"[TTS test] winsound.PlaySound 已调用", flush=True)
            except Exception as e:
                play_err = (play_err or "") + f" / winsound:{e}"
                print(f"[TTS test] winsound 异常: {e}", flush=True)
        # 路径 3:QMediaPlayer 兜底
        if played_by is None:
            try:
                from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
                from PyQt5.QtCore import QUrl
                if not hasattr(self, "_test_player"):
                    self._test_player = QMediaPlayer(self)
                    # 监听错误信号,失败时把具体原因暴露
                    self._test_player.error.connect(
                        lambda e: print(
                            f"[TTS 测试 QMediaPlayer error] code={e} / "
                            f"msg={self._test_player.errorString()}", flush=True))
                self._test_player.setMedia(QMediaContent(QUrl.fromLocalFile(out)))
                self._test_player.play()
                played_by = "QMediaPlayer"
            except Exception as e:
                play_err = (play_err or "") + f" / QMediaPlayer:{e}"
        # 路径 3:os.startfile 终极兜底(让系统默认播放器开)
        if played_by is None:
            try:
                os.startfile(out)
                played_by = "系统默认播放器(已用文件管理器打开)"
            except Exception as e:
                play_err = (play_err or "") + f" / startfile:{e}"
        if played_by:
            QMessageBox.information(self, "TTS 测试成功",
                f"已合成 + 播放测试音频。\n"
                f"播放方式:{played_by}\n"
                f"文件:{out}\n\n"
                f"如果没声音:检查系统音量 / 默认输出设备")
        else:
            QMessageBox.information(self, "TTS 测试成功(三种播放方式都失败)",
                f"音频已合成到:\n{out}\n\n"
                f"但 3 条播放路径都失败:\n{play_err}\n\n"
                f"建议:文件管理器手动打开听一听,确认合成本身没问题。")

    def save_settings(self):
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        s.setValue("genres", [n for n, cb in self.genre_checks.items() if cb.isChecked()])
        b = self.platform_group.checkedButton()
        s.setValue("platform", b.text() if b else "番茄小说")
        b = self.audience_group.checkedButton()
        s.setValue("audience", b.text() if b else "成人")
        b = self.density_group.checkedButton()
        s.setValue("density", b.text() if b else "适中")
        b = self.growth_group.checkedButton()
        s.setValue("growth", b.text() if b else "均衡型")
        b = self.conflict_group.checkedButton()
        s.setValue("conflict", b.text() if b else "中度")
        s.setValue("era_combo", self.era_combo.currentText())
        s.setValue("era_custom", self.era_custom.text())
        s.setValue("chapter_count", self.chapter_custom.value())
        s.setValue("words_per_chapter", self.words_custom.value())
        b = self.detail_group.checkedButton()
        s.setValue("outline_detail", b.text() if b else "标准")
        b = self.rhythm_group.checkedButton()
        s.setValue("rhythm", b.text() if b else "适中")
        s.setValue("endings", [n for n, cb in self.ending_checks.items() if cb.isChecked()])
        b = self.mode_group.checkedButton()
        s.setValue("creation_mode", b.text() if b else "创造版")
        s.setValue("golden_fingers", [n for n, cb in self.golden_checks.items() if cb.isChecked()])
        s.setValue("personas", [n for n, cb in self.persona_checks.items() if cb.isChecked()])
        # 盘古超级系统开关
        s.setValue("pangu_enabled", self.pangu_check.isChecked())
        s.setValue("pangu_whitelist", self.pangu_whitelist_edit.toPlainText())
        s.setValue("prompt_offset", self.prompt_offset.value())
        s.setValue("style_sliders", {n: sl.value() for n, sl in self.style_sliders.items()})
        b = self.ai_group.checkedButton()
        s.setValue("ai_model", b.text() if b else "ChatGPT镜像")
        s.setValue("custom_url", self.custom_url.text())
        s.setValue("delay_check", self.delay_check.isChecked())
        s.setValue("special_edit", self.special_edit.toPlainText() if hasattr(self, "special_edit") else "")

    def load_settings(self):
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        if not s.contains("platform"):
            return  # 首次启动，用默认值

        # BUG-073:Linux PyQt5 无存档时 s.value("key", []) 返回 None 不是 [],下面 n in None 会 TypeError
        # Windows 因 QSettings 序列化方式差异不触发 — 沙箱 offscreen / Linux 才暴露
        genres = s.value("genres", []) or []
        if isinstance(genres, str):
            genres = [genres]
        for n, cb in self.genre_checks.items():
            cb.setChecked(n in genres)

        def _set_radio(group, text):
            for btn in group.buttons():
                if btn.text() == text:
                    btn.setChecked(True)
                    return

        _set_radio(self.platform_group, s.value("platform", "番茄小说"))
        _set_radio(self.audience_group, s.value("audience", "成人"))
        _set_radio(self.density_group,  s.value("density",  "适中"))
        _set_radio(self.growth_group,   s.value("growth",   "均衡型"))
        _set_radio(self.conflict_group, s.value("conflict", "中度"))

        era_combo = s.value("era_combo", "")
        if era_combo:
            idx = self.era_combo.findText(era_combo)
            if idx >= 0:
                self.era_combo.setCurrentIndex(idx)
        self.era_custom.setText(s.value("era_custom", ""))

        ch = s.value("chapter_count", None)
        if ch is not None:
            self.chapter_custom.setValue(int(ch))
        wpc = s.value("words_per_chapter", None)
        if wpc is not None:
            self.words_custom.setValue(int(wpc))

        _set_radio(self.detail_group, s.value("outline_detail", "标准"))
        _set_radio(self.rhythm_group, s.value("rhythm", "适中"))

        endings = s.value("endings", []) or []
        if isinstance(endings, str):
            endings = [endings]
        for n, cb in self.ending_checks.items():
            cb.setChecked(n in endings)

        _set_radio(self.mode_group, s.value("creation_mode", "创造版"))

        gfs = s.value("golden_fingers", []) or []
        if isinstance(gfs, str):
            gfs = [gfs]
        for n, cb in self.golden_checks.items():
            cb.setChecked(n in gfs)

        ps = s.value("personas", []) or []
        if isinstance(ps, str):
            ps = [ps]
        for n, cb in self.persona_checks.items():
            cb.setChecked(n in ps)

        po = s.value("prompt_offset", None)
        if po is not None:
            self.prompt_offset.setValue(int(po))

        sw = s.value("style_sliders", {})
        if isinstance(sw, dict):
            for n, sl in self.style_sliders.items():
                if n in sw:
                    sl.setValue(int(sw[n]))

        _set_radio(self.ai_group, s.value("ai_model", "ChatGPT镜像"))
        self.custom_url.setText(s.value("custom_url", ""))
        delay = s.value("delay_check", False)
        self.delay_check.setChecked(delay if isinstance(delay, bool) else delay == "true")
        special = s.value("special_edit", "")
        if special and hasattr(self, "special_edit"):
            self.special_edit.setPlainText(special)

    def enable_auto_save(self):
        """第 1 项: 任何设置改动后 1.5 秒自动持久化(debounce)
        防止用户改了设置没关窗口就丢失"""
        from PyQt5.QtCore import QTimer
        if hasattr(self, "_auto_save_timer"):
            return  # 已安装,不重复
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(1500)
        self._auto_save_timer.timeout.connect(self._auto_save_fire)

        def _dirty(*_a, **_kw):
            self._auto_save_timer.start()

        # 多选 checkbox 组
        for d in (self.genre_checks, self.ending_checks,
                  self.golden_checks, self.persona_checks):
            for cb in d.values():
                cb.toggled.connect(_dirty)
        # 单选 button group
        for grp in (self.platform_group, self.audience_group,
                    self.density_group, self.growth_group,
                    self.conflict_group, self.detail_group,
                    self.rhythm_group, self.mode_group, self.ai_group):
            grp.buttonClicked.connect(_dirty)
        # 数值 spinbox
        for sb in (self.chapter_custom, self.words_custom, self.prompt_offset):
            sb.valueChanged.connect(_dirty)
        # ComboBox / LineEdit / 单 checkbox / TextEdit
        self.era_combo.currentTextChanged.connect(_dirty)
        self.era_custom.textChanged.connect(_dirty)
        self.custom_url.textChanged.connect(_dirty)
        self.delay_check.toggled.connect(_dirty)
        self.pangu_check.toggled.connect(_dirty)
        self.pangu_whitelist_edit.textChanged.connect(_dirty)
        if hasattr(self, "special_edit"):
            self.special_edit.textChanged.connect(_dirty)
        # 风格滑块
        for sl in self.style_sliders.values():
            sl.valueChanged.connect(_dirty)

    def _auto_save_fire(self):
        """timer 到点,真实写盘"""
        try:
            self.save_settings()
        except Exception:
            pass  # 自动保存失败不影响 UI

    # ── 第 3/5/6 项:自定义选项 helpers ──────────────────
    def _add_custom_checkbox(self, title, target_dict, grid_layout, prefs_key):
        """通用:弹输入框 → 加 QCheckBox → 持久化到 QSettings"""
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, f"自定义{title}", f"输入新的{title}名称(回车确认):")
        if not (ok and name.strip()):
            return
        name = name.strip()
        if name in target_dict:
            return  # 重复忽略
        cb = QCheckBox(name)
        cb.setChecked(True)
        cb.setStyleSheet("QCheckBox { color:#997151; }")  # 自定义条目用米色区分
        target_dict[name] = cb
        # 找空格子追加(末行末尾)
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        existing = s.value(prefs_key, [], type=list) or []
        if name not in existing:
            existing.append(name)
        s.setValue(prefs_key, existing)
        # 添加到 grid:扫一遍找空位
        n = len(target_dict) - 1  # 当前位置
        r, c = n // 4, n % 4
        grid_layout.addWidget(cb, r + 100, c)  # 加大 row 偏移,避开预定义条目
        # 通知 auto_save dirty
        try:
            cb.toggled.connect(lambda: self._auto_save_timer.start()
                               if hasattr(self, "_auto_save_timer") else None)
        except Exception:
            pass

    def _add_custom_genre(self):
        self._add_custom_checkbox(
            "题材", self.genre_checks, self._genre_layout, "custom_genres")

    def _add_custom_golden(self):
        self._add_custom_checkbox(
            "金手指", self.golden_checks, self._golden_grid, "custom_goldens")

    def _add_custom_persona(self):
        self._add_custom_checkbox(
            "主角人设", self.persona_checks, self._persona_grid, "custom_personas")

    def _save_custom_eras(self):
        """把当前下拉里所有用户自定义的时代保存到 QSettings"""
        from PyQt5.QtCore import QSettings
        builtins = set(ERAS) | {"✏️ 自定义..."}
        custom = []
        for i in range(self.era_combo.count()):
            t = self.era_combo.itemText(i)
            if t not in builtins:
                custom.append(t)
        QSettings("NovelAI", "CreationSettings").setValue("custom_eras", custom)

    def _load_custom_eras(self):
        """启动时加载用户保存过的自定义时代,插到"自定义..."条目前"""
        from PyQt5.QtCore import QSettings
        custom = QSettings("NovelAI", "CreationSettings").value(
            "custom_eras", [], type=list) or []
        insert_at = self.era_combo.count() - 1  # 在"自定义..."前
        for era in custom:
            if era and self.era_combo.findText(era) < 0:
                self.era_combo.insertItem(insert_at, era)
                insert_at += 1

    def _load_custom_checks(self):
        """启动时把 QSettings 里的自定义题材/金手指/人设条目加回 UI"""
        from PyQt5.QtCore import QSettings
        s = QSettings("NovelAI", "CreationSettings")
        for prefs_key, target_dict, grid in [
            ("custom_genres",   self.genre_checks,   self._genre_layout),
            ("custom_goldens",  self.golden_checks,  self._golden_grid),
            ("custom_personas", self.persona_checks, self._persona_grid),
        ]:
            items = s.value(prefs_key, [], type=list) or []
            for name in items:
                if name in target_dict:
                    continue
                cb = QCheckBox(name)
                cb.setStyleSheet("QCheckBox { color:#997151; }")
                target_dict[name] = cb
                n = len(target_dict) - 1
                r, c = n // 4, n % 4
                grid.addWidget(cb, r + 100, c)

    def _install_collapsible_chain(self):
        """第 7 项:把题材/时代/金手指/主角人设 4 个 group 串成折叠链
        - 每个 box.setCheckable(True),勾掉 = 折叠内容(节省空间)
        - 每个 box(除最后)末尾加 ✓ 完成,继续下一项按钮:折叠当前 + 展开下一个
        - 配合 enable_auto_save 一起,改了立刻持久化"""
        boxes = [
            getattr(self, "box_genre", None),
            getattr(self, "box_era", None),
            getattr(self, "box_golden", None),
            getattr(self, "box_persona", None),
        ]
        boxes = [b for b in boxes if b is not None and b.layout() is not None]
        if len(boxes) < 2:
            return

        box_inner = {}
        # 步骤 1:让每个 box 可折叠
        for box in boxes:
            # 收集"现在的"layout 里所有 widget(我们加按钮之前)
            inner = []
            def _walk(lay, _out=inner):
                for j in range(lay.count()):
                    it = lay.itemAt(j)
                    w = it.widget() if it else None
                    if w:
                        _out.append(w)
                    sub = it.layout() if it else None
                    if sub:
                        _walk(sub, _out)
            _walk(box.layout())
            box_inner[id(box)] = inner
            box.setCheckable(True)
            box.setChecked(True)
            box.setToolTip("点标题左侧的勾选框可折叠 / 展开")

            def make_handler(w_list):
                def _on_toggled(checked):
                    for w in w_list:
                        w.setVisible(checked)
                return _on_toggled
            box.toggled.connect(make_handler(inner))

        # 步骤 2:除最后一个 box,都加 ✓ 完成按钮 → 折叠当前 + 展开下一个
        for i in range(len(boxes) - 1):
            cur = boxes[i]
            nxt = boxes[i + 1]
            btn = QPushButton("✓ 完成此项,自动跳到下一项")
            btn.setStyleSheet(
                "QPushButton { color:white; background:#1f8b4d; padding:6px 14px; "
                "border-radius:3px; font-weight:bold; margin-top:6px; } "
                "QPushButton:hover { background:#1f8b4d; }")
            def make_next(cur_box=cur, nxt_box=nxt):
                def _f():
                    cur_box.setChecked(False)  # 折叠
                    nxt_box.setChecked(True)   # 展开下一个
                return _f
            btn.clicked.connect(make_next())
            cur.layout().addWidget(btn)
            # 按钮也归到 inner list:折叠时一起隐藏(只剩标题条)
            box_inner[id(cur)].append(btn)
    
    # v2.12: _emit_ctx_changed + get_ctx_config 已迁移到 GenerationControl
