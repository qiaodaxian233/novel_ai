# -*- coding: utf-8 -*-
"""ui/tabs/character_library.py - 角色库 / 关系 / 时间线 / 物品 / 伏笔 Tab(3860 行,P5 最大)

v2.04 P5 拆分:从 novel_ai.py 第 225-4084 行整体搬运,内容零修改。
13 子表/子页 + 80 个方法,自包含程度极高,零项目内类依赖。
"""
import json
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

# relation_graph 可用性 flag - 各文件独立判断,避免循环 import(P4 模式)
try:
    import relation_graph  # noqa: F401
    RELATION_GRAPH_AVAILABLE = True
except ImportError:
    relation_graph = None
    RELATION_GRAPH_AVAILABLE = False


class CharacterLibrary(QWidget):
    """
    全方位角色与世界状态管理：
      - 角色库: 主角/配角/反派,每人含详细档案
      - 关系图谱: 师徒/敌对/暗恋/血缘
      - 时间线: 主角境界/年龄/势力/重大事件
      - 物品库: 法器/丹药/秘籍及来源
      - 伏笔追踪: 已埋伏笔与回收状态
    数据自动持久化到项目 JSON, 写章节时按需注入提示词。
    """
    
    def __init__(self):
        super().__init__()
        # 数据结构
        self.characters = []   # [{name, role, appearance, personality, ability, ...}]
        self.relations  = []   # [{from, to, type, note}]
        self.timeline   = []   # [{ch_num, event, hero_state}]
        self.items      = []   # [{name, owner, source, ability, status}]
        self.foreshadows= []   # [{ch_num, content, plan_pay_at, paid, paid_at}]
        # 新增:钩子编年 + 爽点编年
        self.hooks      = []   # [{ch_num, type, intensity, content}]
        self.cool_pts   = []   # [{ch_num, type, content}]
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 顶部: 内嵌标签页 (7个子模块)
        self.sub_tabs = QTabWidget()
        layout.addWidget(self.sub_tabs)
        
        self._build_characters_tab()
        self._build_relations_tab()
        self._build_relation_graph_tab()  # v1.70 新增:🕸️ 关系网(vis-network 可视化)
        self._build_timeline_tab()
        self._build_items_tab()
        self._build_power_tab()
        self._build_foreshadows_tab()
        self._build_promises_tab()   # v1.77 新增:⚡ 威胁承诺
        self._build_plot_progress_tab()   # v1.78 新增:📈 剧情进度(弧线/关系值/目标)
        self._build_info_isolation_tab()  # v1.79 新增:🔒 信息隔离(infos + known_by)
        self._build_plot_tree_tab()       # v1.80 新增:🌳 剧情树(QTreeWidget 4 层)
        self._build_hooks_tab()      # 新增:钩子编年
        self._build_coolpts_tab()    # 新增:爽点编年
        self._build_cross_graph_tab()  # v1.87 新增:🕸️ 关联图谱(QGraphicsView 跨表可视化)

        # v1.70: 切换到 🕸️ 关系网 子页时自动用最新数据刷新图
        self.sub_tabs.currentChanged.connect(self._on_sub_tab_changed)
        
        # 底部: 操作按钮
        from PyQt5.QtCore import QSettings as _QS_charlib
        _cls = _QS_charlib("NovelAI", "CharLib")
        btn_row = QHBoxLayout()
        self.chk_inject = QCheckBox("写章节时自动注入到提示词")
        self.chk_inject.setChecked(_cls.value("inject", True, type=bool))
        self.chk_inject.setToolTip(
            "勾选后,每次生成新章节会把:\n"
            " - 本章可能出场的角色档案\n"
            " - 主角当前状态(境界/位置/装备)\n"
            " - 待回收的伏笔\n"
            "自动拼到提示词里,有效防止人设崩坏与前后矛盾。")
        self.chk_inject.stateChanged.connect(
            lambda v: _QS_charlib("NovelAI", "CharLib").setValue("inject", bool(v)))
        btn_row.addWidget(self.chk_inject)

        # v1.84:POV 模式 — 让 AI 用某个角色的视角写本章,自动按其已知信息边界收窄注入
        # 配合 v1.79 信息隔离,直接堵"路人甲突然知道主角秘密"这种 OOC bug
        btn_row.addSpacing(20)
        btn_row.addWidget(QLabel("👁 视角:"))
        self.cb_pov_mode = QComboBox()
        self.cb_pov_mode.addItems(["全知视角", "主角 POV", "角色 POV"])
        self.cb_pov_mode.setCurrentText(
            _cls.value("pov_mode", "全知视角", type=str))
        self.cb_pov_mode.setToolTip(
            "v1.84 新增。选择本章用哪个视角生成:\n"
            "  • 全知视角:注入全部库信息(默认,适合上帝视角叙事)\n"
            "  • 主角 POV:只注入主角已知的信息(从角色库第 1 个角色取)\n"
            "  • 角色 POV:只注入指定角色已知的信息(在右边输入角色名)\n\n"
            "选 POV 模式时会自动:\n"
            "  ① 关系热点只显示 POV 角色参与的关系对\n"
            "  ② 信息边界只显示 POV 知道的信息\n"
            "  ③ 在 prompt 加『以 X 视角写本章』的视角约束\n\n"
            "配合 v1.79 信息隔离,从根上堵 OOC bug(路人开上帝视角)。")
        self.cb_pov_mode.currentTextChanged.connect(
            lambda t: _QS_charlib("NovelAI", "CharLib").setValue("pov_mode", t))
        self.cb_pov_mode.currentTextChanged.connect(self._on_pov_mode_changed)
        btn_row.addWidget(self.cb_pov_mode)

        self.le_pov_character = QLineEdit()
        self.le_pov_character.setPlaceholderText("仅『角色 POV』时填角色名(如:林悦)")
        self.le_pov_character.setMaximumWidth(180)
        self.le_pov_character.setText(_cls.value("pov_character", "", type=str))
        self.le_pov_character.textChanged.connect(
            lambda t: _QS_charlib("NovelAI", "CharLib").setValue("pov_character", t))
        # 初始化禁用状态(只有"角色 POV"时可用)
        self.le_pov_character.setEnabled(self.cb_pov_mode.currentText() == "角色 POV")
        btn_row.addWidget(self.le_pov_character)

        # 每章生成完后自动抽取到所有库(默认勾上,QSettings 记住用户选择)
        # v1.81 文案修正:库数从 v1.50 初的 6 个扩到 v1.80 时的 10+ 个,
        # 文案改用"全部库"避免误导用户以为只有 6 个
        self.chk_auto_extract = QCheckBox("✨ 每章生成后自动抽取到全部库")
        # 从 QSettings 读上次选择,首次默认 True(推荐使用)
        from PyQt5.QtCore import QSettings as _QS
        _settings = _QS("NovelAI", "UserPrefs")
        self.chk_auto_extract.setChecked(
            _settings.value("auto_extract_6lib", True, type=bool))
        self.chk_auto_extract.setToolTip(
            "勾选后,每生成【未来章节】时自动调用 AI 提取:\n"
            "  角色 / 关系 / 时间线 / 物品 / 战力 / 伏笔(原 6 库)\n"
            "  + 威胁承诺(v1.77) / 弧线-关系值-目标(v1.78)\n"
            "  + 信息隔离(v1.79) / 剧情树(v1.80)\n"
            "并合并到对应的表里。\n\n"
            "⚠️ 注意:此勾选【只对勾选之后生成的章节】生效。\n"
            "  已有章节请点旁边的「🔄 立即从所有章节提取」按钮补抽。\n\n"
            "代价:每章多 1 次 AI 调用。如果你 AI 额度有限,可以关掉,\n"
            "改成手动批量提取(旁边那个按钮)。")
        self.chk_auto_extract.setStyleSheet("QCheckBox { color:#b4884e; font-weight:bold; }")
        # 状态变化时持久化保存
        self.chk_auto_extract.stateChanged.connect(
            lambda s: _QS("NovelAI", "UserPrefs").setValue(
                "auto_extract_6lib", bool(s)))
        btn_row.addWidget(self.chk_auto_extract)
        
        # v1.64:B 方案 — AI 抽 6 库时同步主角状态字段
        self.chk_auto_sync_hero = QCheckBox("🎯 同步主角状态")
        _cs = _QS("NovelAI", "CreationSettings")
        self.chk_auto_sync_hero.setChecked(
            _cs.value("auto_sync_hero_state", True, type=bool))
        self.chk_auto_sync_hero.setToolTip(
            "勾选后,AI 抽全部库时顺便提取本章末主角的 5 个状态字段\n"
            "  (年龄/修为/位置/势力/心境),自动填到上方表单。\n\n"
            "✗ 取消:AI 不抽,你可以点上方『🔄 从时间线同步』按钮手动同步\n"
            "       (本地正则,不烧 token)\n\n"
            "提示:用户切到『✏️ 手动改』模式时,自动同步会被跳过,保护手填值。")
        self.chk_auto_sync_hero.setStyleSheet("QCheckBox { color:#666; }")
        self.chk_auto_sync_hero.stateChanged.connect(
            lambda s: _QS("NovelAI", "CreationSettings").setValue(
                "auto_sync_hero_state", bool(s)))
        btn_row.addWidget(self.chk_auto_sync_hero)

        btn_row.addStretch()
        
        self.btn_extract_from_chapters = QPushButton("🔄 立即从所有章节提取")
        self.btn_extract_from_chapters.setStyleSheet(
            "background:#3498db;color:white;padding:6px 12px;border-radius:3px;")
        btn_row.addWidget(self.btn_extract_from_chapters)
        
        self.btn_export = QPushButton("📥 导出库")
        btn_row.addWidget(self.btn_export)
        self.btn_import = QPushButton("📤 导入库")
        btn_row.addWidget(self.btn_import)
        self.btn_copy_extract_prompt = QPushButton("📋 复制提取 Prompt")
        self.btn_copy_extract_prompt.setToolTip(
            "把一份完整 prompt 复制到剪贴板,贴给 DeepSeek/ChatGPT。\n"
            "AI 返回的 JSON 直接保存为 .json,用『导入库』即可一键合并。")
        btn_row.addWidget(self.btn_copy_extract_prompt)
        
        # 🗑 清空所有数据
        btn_row.addStretch()
        self.btn_clear_all = QPushButton("🗑 清空所有")
        self.btn_clear_all.setToolTip("清空角色库、关系、时间线、物品、伏笔等全部数据")
        self.btn_clear_all.setStyleSheet(
            "QPushButton { color:#e74c3c; border:1px solid #e74c3c; padding:4px 12px;"
            "border-radius:3px; } QPushButton:hover { background:#fce4e4; }")
        self.btn_clear_all.clicked.connect(self._clear_all_data)
        btn_row.addWidget(self.btn_clear_all)
        layout.addLayout(btn_row)
        
        self.btn_export.clicked.connect(self._export_lib)
        self.btn_import.clicked.connect(self._import_lib)
        self.btn_copy_extract_prompt.clicked.connect(self._copy_extract_prompt)
    
    # ── 1. 角色库子页 ──────────────────────────────────────
    def _build_characters_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        # 顶部按钮
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增角色")
        btn_add.clicked.connect(self._add_character)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_character)
        # v1.93 BUG-067:同名不同姓检查(避免 AI 写正文时混淆)
        btn_lint = QPushButton("🔍 同名检查")
        btn_lint.setToolTip("扫描角色库,找出 name 完全相同的角色 — AI 写正文时容易混淆,建议改名(保留姓氏)")
        btn_lint.clicked.connect(self._on_check_duplicate_names)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addWidget(btn_lint); top.addStretch()
        lay.addLayout(top)
        
        # 表格
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        # v1.93 BUG-067:加"退场章节"列(放 first_ch 之后,列 8)
        self.tbl_chars = QTableWidget(0, 10)
        self.tbl_chars.setHorizontalHeaderLabels([
            "姓名", "角色定位", "外貌", "性格", "口头禅/标志",
            "能力/职业", "说话风格", "当前状态", "首次出场", "退场章节"
        ])
        self.tbl_chars.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_chars.horizontalHeader().setStretchLastSection(True)
        self.tbl_chars.verticalHeader().setVisible(False)
        self.tbl_chars.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_chars.setColumnWidth(0, 100)
        self.tbl_chars.setColumnWidth(1, 80)
        self.tbl_chars.setColumnWidth(2, 150)
        self.tbl_chars.setColumnWidth(3, 150)
        self.tbl_chars.setColumnWidth(4, 120)
        self.tbl_chars.setColumnWidth(5, 120)
        self.tbl_chars.setColumnWidth(6, 120)
        self.tbl_chars.setColumnWidth(7, 80)   # v1.93 BUG-067:首次出场原本最后列,加 last_ch 后让它固定 80
        lay.addWidget(self.tbl_chars)
        
        tip = QLabel(
            "💡 提示: 双击单元格直接编辑。【角色定位】填:主角/女主/配角/导师/反派/路人。\n"
            "    【当前状态】会随剧情更新,写章节时自动注入此字段保证前后一致。\n"
            "    【退场章节】留空表示尚未退场;AI 不会自动填,需手动标记(用于长篇人物管理)。")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "👤 角色库")
    
    def _add_character(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_chars.rowCount()
        self.tbl_chars.insertRow(r)
        # v1.93 BUG-067:9 列默认值(末尾加"退场章节"空字符串)
        defaults = ["新角色", "配角", "", "", "", "", "", "", ""]
        for c, v in enumerate(defaults):
            self.tbl_chars.setItem(r, c, QTableWidgetItem(v))
    
    def _del_character(self):
        rows = sorted(set(idx.row() for idx in self.tbl_chars.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_chars.removeRow(r)

    def _on_check_duplicate_names(self):
        """v1.93 BUG-067:同名不同姓检查 — 扫角色库找 name 完全相同的角色。

        借鉴竞品由风写作 v1.1.7 思路 — AI 写正文时,两个同名角色容易混淆。
        建议改名(保留姓氏),让 AI 能区分。

        本 MVP 只做完全重名检测;包含/被包含(如"林清"vs"林清歌")留 v1.94。
        """
        # 把表格数据读成 (name, role) 列表,纯逻辑用 staticmethod 处理(便于单测)
        rows_data = []
        for r in range(self.tbl_chars.rowCount()):
            name_item = self.tbl_chars.item(r, 0)
            role_item = self.tbl_chars.item(r, 1)
            name = (name_item.text().strip() if name_item else "")
            role = (role_item.text().strip() if role_item else "")
            rows_data.append((name, role))
        conflicts = self._find_duplicate_names(rows_data)
        if not conflicts:
            QMessageBox.information(
                self, "🔍 同名检查",
                f"✓ 角色库共 {self.tbl_chars.rowCount()} 个角色,未发现重名冲突。")
            return
        # 拼报告
        lines = [
            f"⚠ 发现 {len(conflicts)} 组重名角色(共 {sum(len(rs) for rs in conflicts.values())} 个角色):",
            "",
        ]
        for name, rows in conflicts.items():
            roles = " / ".join(f"第{r+1}行({role or '未填角色定位'})" for r, role in rows)
            lines.append(f"  • 「{name}」— {roles}")
        lines.extend([
            "",
            "💡 建议:把其中一个改名(保留姓氏即可)。",
            "AI 写正文时,完全同名的角色会被混淆,即使角色定位/外貌不同也容易写错。",
        ])
        QMessageBox.warning(self, "🔍 同名检查 — 发现冲突", "\n".join(lines))

    @staticmethod
    def _find_duplicate_names(rows_data):
        """v1.93 BUG-067:纯函数 — 找重名角色组。

        Args:
            rows_data: [(name: str, role: str), ...] — 角色表所有行的 (name, role)

        Returns:
            {name: [(row_idx, role), ...], ...} — 只包含 ≥2 次出现的 name。
            空名(name == "")不计入(还没填好的行不算冲突)。

        测试用例覆盖:正例(重名)+ 反例(无重名)+ 边界(空表 / 单角色 / 空名)。
        """
        from collections import defaultdict
        groups = defaultdict(list)
        for idx, (name, role) in enumerate(rows_data):
            name = (name or "").strip()
            if name:  # 空名不算
                groups[name].append((idx, role))
        return {n: rs for n, rs in groups.items() if len(rs) >= 2}
    
    # ── 2. 关系图谱子页 ────────────────────────────────────
    def _build_relations_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增关系")
        btn_add.clicked.connect(self._add_relation)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_relation)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_relations = QTableWidget(0, 4)
        self.tbl_relations.setHorizontalHeaderLabels([
            "角色A", "关系类型", "角色B", "备注"
        ])
        self.tbl_relations.horizontalHeader().setStretchLastSection(True)
        self.tbl_relations.verticalHeader().setVisible(False)
        self.tbl_relations.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_relations.setColumnWidth(0, 120)
        self.tbl_relations.setColumnWidth(1, 100)
        self.tbl_relations.setColumnWidth(2, 120)
        lay.addWidget(self.tbl_relations)
        
        tip = QLabel(
            "💡 关系类型示例: 师父/师弟/师妹/对手/暗恋对象/恋人/血缘/宿敌/同盟/上下级")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🔗 关系图谱")
    
    def _add_relation(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_relations.rowCount()
        self.tbl_relations.insertRow(r)
        defaults = ["", "师父", "", ""]
        for c, v in enumerate(defaults):
            self.tbl_relations.setItem(r, c, QTableWidgetItem(v))
    
    def _del_relation(self):
        rows = sorted(set(idx.row() for idx in self.tbl_relations.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_relations.removeRow(r)
    
    # ── 3. 时间线子页 ──────────────────────────────────────
    def _build_timeline_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        # 主角当前状态总览
        # v1.64:从手填字段改造为派生数据展示
        #   · 默认只读(防止误以为是待填表单)
        #   · "🔄 从时间线同步"按钮 — 从 timeline state_change 自动抽取填充
        #   · "✏️ 解锁手动改" 按钮 — 用户想覆盖时再开
        #   · 来源 label — 显示数据从哪一章来
        from PyQt5.QtWidgets import QFormLayout
        state_box = QGroupBox("📊 主角当前状态(写章节时自动注入)")
        state_box_lay = QVBoxLayout(state_box)
        
        # 顶部:同步按钮行 + 来源 label
        sync_row = QHBoxLayout()
        self.btn_sync_hero = QPushButton("🔄 从时间线同步")
        self.btn_sync_hero.setToolTip(
            "从下方【重大事件时间线】的『状态变化』列里,\n"
            "按章节倒序自动抽取 修为/位置/势力/年龄/心境 关键词,\n"
            "填到 5 个字段里。\n\n"
            "适合写了若干章后,一键把主角状态推到最新。\n"
            "(纯本地正则,不调 AI 不烧 token)")
        self.btn_sync_hero.setStyleSheet(
            "QPushButton { background:#3498db; color:white; padding:5px 10px; "
            "border-radius:3px; font-weight:bold; }} "
            "QPushButton:hover { background:#2980b9; }")
        sync_row.addWidget(self.btn_sync_hero)
        
        self.btn_unlock_hero = QPushButton("✏️ 手动改")
        self.btn_unlock_hero.setCheckable(True)
        self.btn_unlock_hero.setToolTip(
            "✓ 切到手动模式:5 个字段变可编辑,你随便填\n"
            "✗ 切回派生模式:字段重新只读,由同步功能自动填\n\n"
            "默认只读避免手填值被覆盖;想长期手填就按一下保持手动模式")
        sync_row.addWidget(self.btn_unlock_hero)
        sync_row.addStretch()
        state_box_lay.addLayout(sync_row)
        
        # 来源 label
        self.lbl_hero_source = QLabel("📌 数据来源:未同步(可点🔄按钮自动抽取,或✏️手动填)")
        self.lbl_hero_source.setStyleSheet(
            "color: #888; font-size: 11px; padding: 2px 4px;")
        self.lbl_hero_source.setWordWrap(True)
        state_box_lay.addWidget(self.lbl_hero_source)
        
        # 5 个字段(form 布局)
        from PyQt5.QtWidgets import QWidget as _QW_state
        form_holder = _QW_state()
        sf = QFormLayout(form_holder)
        self.hero_age = QLineEdit("18")
        self.hero_realm = QLineEdit("练气期一层")
        self.hero_location = QLineEdit("青云山·李家村")
        self.hero_faction = QLineEdit("无门无派")
        self.hero_mood = QLineEdit("平静")
        sf.addRow("主角年龄:", self.hero_age)
        sf.addRow("修为/境界:", self.hero_realm)
        sf.addRow("当前位置:", self.hero_location)
        sf.addRow("所属势力:", self.hero_faction)
        sf.addRow("近期心境:", self.hero_mood)
        state_box_lay.addWidget(form_holder)
        
        # 收集 5 个 QLineEdit 到一个列表,便于批量设置只读状态
        self._hero_edits = [self.hero_age, self.hero_realm,
                            self.hero_location, self.hero_faction,
                            self.hero_mood]
        # 默认进入只读模式
        self._set_hero_readonly(True)
        
        # 信号绑定
        self.btn_sync_hero.clicked.connect(self._sync_hero_from_timeline)
        self.btn_unlock_hero.toggled.connect(self._on_hero_unlock_toggled)
        
        lay.addWidget(state_box)
        
        # 重大事件时间线
        evt_label = QLabel("📅 重大事件时间线 (按章节顺序):")
        evt_label.setStyleSheet("font-weight:bold;margin-top:6px")
        lay.addWidget(evt_label)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增事件")
        btn_add.clicked.connect(self._add_event)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_event)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_timeline = QTableWidget(0, 3)
        self.tbl_timeline.setHorizontalHeaderLabels(["章节", "事件", "状态变化"])
        self.tbl_timeline.horizontalHeader().setStretchLastSection(True)
        self.tbl_timeline.verticalHeader().setVisible(False)
        self.tbl_timeline.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_timeline.setColumnWidth(0, 60)
        self.tbl_timeline.setColumnWidth(1, 350)
        lay.addWidget(self.tbl_timeline)
        
        self.sub_tabs.addTab(w, "📅 时间线")
    
    def _add_event(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_timeline.rowCount()
        self.tbl_timeline.insertRow(r)
        defaults = [str(r+1), "新事件", ""]
        for c, v in enumerate(defaults):
            self.tbl_timeline.setItem(r, c, QTableWidgetItem(v))
    
    def _del_event(self):
        rows = sorted(set(idx.row() for idx in self.tbl_timeline.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_timeline.removeRow(r)
    
    # ── 4. 物品库子页 ──────────────────────────────────────
    # 按题材分类的物品类型
    ITEM_TYPES_BY_GENRE = {
        "都市": ["礼物", "信物", "钥匙", "照片", "文件", "珠宝", "手机", "车", "房产", "合同", "日记"],
        "言情": ["礼物", "信物", "戒指", "项链", "照片", "信件", "钥匙", "文件", "日记", "手机"],
        "玄幻": ["法器", "灵器", "丹药", "秘籍", "材料", "坐骑", "防具", "灵石", "令牌", "灵宠"],
        "修仙": ["法器", "灵器", "丹药", "秘籍", "材料", "坐骑", "防具", "灵石", "令牌", "仙器"],
        "奇幻": ["魔法器具", "药水", "卷轴", "武器", "护甲", "宝石", "魔杖", "坐骑", "圣物"],
        "悬疑": ["证物", "线索", "文件", "录音", "照片", "钥匙", "日记", "武器", "毒药", "密码"],
        "科幻": ["芯片", "能量核", "装甲", "武器", "飞船", "AI模块", "改造体", "数据卡"],
        "历史": ["圣旨", "兵符", "宝剑", "玉佩", "书信", "地图", "令牌", "印章", "密旨"],
        "军事": ["武器", "情报", "电台", "地图", "勋章", "军令", "弹药", "密码本"],
        "游戏": ["武器", "防具", "药水", "材料", "坐骑", "宠物", "技能书", "宝箱", "任务道具"],
    }

    def _get_item_types_for_genre(self):
        """根据当前题材返回适合的物品类型"""
        # 尝试从创作设置获取题材
        try:
            mw = self.window()
            genres = mw.tab_settings.get_selected_genres() or []
        except Exception:
            genres = []
        types = set()
        for g in genres:
            for key, vals in self.ITEM_TYPES_BY_GENRE.items():
                if key in g:
                    types.update(vals)
        if not types:
            # 默认通用类型
            types = {"信物", "礼物", "钥匙", "文件", "武器", "道具"}
        return sorted(types)

    def _build_items_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增物品")
        btn_add.clicked.connect(self._add_item)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_item)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_items = QTableWidget(0, 5)
        self.tbl_items.setHorizontalHeaderLabels([
            "物品名", "类型", "持有者", "来源章节", "能力/状态"
        ])
        self.tbl_items.horizontalHeader().setStretchLastSection(True)
        self.tbl_items.verticalHeader().setVisible(False)
        self.tbl_items.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_items.setColumnWidth(0, 120)
        self.tbl_items.setColumnWidth(1, 80)
        self.tbl_items.setColumnWidth(2, 100)
        self.tbl_items.setColumnWidth(3, 80)
        lay.addWidget(self.tbl_items)
        
        self.lbl_item_types = QLabel("")
        self.lbl_item_types.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        self.lbl_item_types.setWordWrap(True)
        lay.addWidget(self.lbl_item_types)
        self._refresh_item_type_hint()
        
        self.sub_tabs.addTab(w, "💎 物品库")
    
    def _refresh_item_type_hint(self):
        """刷新物品类型提示(根据题材)"""
        types = self._get_item_types_for_genre()
        self.lbl_item_types.setText(
            f"💡 当前题材适用类型: {'/'.join(types)}\n"
            f"    防止AI漏掉主角已有装备,或重复让主角『获得』同一件东西")

    def _add_item(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_items.rowCount()
        self.tbl_items.insertRow(r)
        types = self._get_item_types_for_genre()
        default_type = types[0] if types else "道具"
        defaults = ["新物品", default_type, "", "", ""]
        for c, v in enumerate(defaults):
            self.tbl_items.setItem(r, c, QTableWidgetItem(v))
    
    def _del_item(self):
        rows = sorted(set(idx.row() for idx in self.tbl_items.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_items.removeRow(r)
    
    # ── 5.5 战力等级体系子页 ────────────────────────────────
    def _build_power_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        # 顶部说明
        intro = QLabel(
            "📌 设定故事的境界/等级体系,写章节时自动注入,防止『小喽啰一拳打飞主角』『跨级越打越奇怪』"
        )
        intro.setStyleSheet("color:#666;padding:4px;")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        # 预设模板按钮
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("快速套用:"))
        for tpl in ["仙侠九境", "玄幻斗气", "都市修真", "西方魔法", "科幻能力等级"]:
            b = QPushButton(tpl)
            b.clicked.connect(lambda _, t=tpl: self._apply_power_preset(t))
            preset_row.addWidget(b)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        # 操作按钮
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增等级")
        btn_add.clicked.connect(self._add_power_level)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_power_level)
        top.addWidget(btn_add); top.addWidget(btn_del); top.addStretch()
        lay.addLayout(top)

        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_power = QTableWidget(0, 4)
        self.tbl_power.setHorizontalHeaderLabels([
            "序号", "境界/等级名", "战力描述", "代表能力"
        ])
        self.tbl_power.horizontalHeader().setStretchLastSection(True)
        self.tbl_power.verticalHeader().setVisible(False)
        self.tbl_power.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_power.setColumnWidth(0, 50)
        self.tbl_power.setColumnWidth(1, 120)
        self.tbl_power.setColumnWidth(2, 220)
        lay.addWidget(self.tbl_power)

        self.sub_tabs.addTab(w, "⚔️ 战力体系")

    def _add_power_level(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_power.rowCount()
        self.tbl_power.insertRow(r)
        defaults = [str(r+1), "", "", ""]
        for c, v in enumerate(defaults):
            self.tbl_power.setItem(r, c, QTableWidgetItem(v))

    def _del_power_level(self):
        rows = sorted(set(idx.row() for idx in self.tbl_power.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_power.removeRow(r)

    def _apply_power_preset(self, name):
        from PyQt5.QtWidgets import QTableWidgetItem
        presets = {
            "仙侠九境": [
                ("练气期", "凡人之上,可初步操控灵气", "御物·小术法"),
                ("筑基期", "构建灵根根基", "凝物为器·小神通"),
                ("金丹期", "凝结金丹,寿元三百", "御空飞行·一气化三清"),
                ("元婴期", "元神出窍,寿八百", "瞬移·分身术"),
                ("化神期", "神识凝实,可压境", "言出法随·小神通成形"),
                ("炼虚期", "虚无之境,寿三千", "破碎虚空·掌控规则"),
                ("合体期", "本命合一,渡劫前夜", "万法归一·镇压一域"),
                ("大乘期", "天劫将至,半步飞升", "言出法随·镇压一界"),
                ("飞升期", "羽化登仙,超脱凡尘", "破开界壁·飞升上界"),
            ],
            "玄幻斗气": [
                ("斗者", "初识斗气", "基础斗技"),
                ("斗师", "斗气外放", "凝实斗气"),
                ("大斗师", "斗气化形", "斗技初成"),
                ("斗灵", "斗气化羽", "御空短行"),
                ("斗王", "镇压一城", "操控斗气"),
                ("斗皇", "破碎山岳", "斗技自创"),
                ("斗宗", "镇压宗门", "驾驭天地之力"),
                ("斗尊", "言出法随", "异火融身"),
                ("斗圣", "化身万千", "撕裂虚空"),
                ("斗帝", "执掌天地", "言出生灭"),
            ],
            "都市修真": [
                ("后天", "凡人体魄", "强健·武艺"),
                ("先天", "突破极限", "内力·感知"),
                ("化劲", "劲入血肉", "穿透·震荡"),
                ("宗师", "镇压一方", "意境·气场"),
                ("大宗师", "返璞归真", "破甲·神识"),
                ("陆地神仙", "万法不侵", "御物·驻颜"),
            ],
            "西方魔法": [
                ("学徒", "刚入门", "小型咒语"),
                ("初级法师", "掌握基础元素", "火球·闪电"),
                ("中级法师", "复合咒语", "法阵·防护罩"),
                ("高级法师", "操控元素之力", "元素亲和"),
                ("大法师", "可创造新咒语", "时空小术"),
                ("圣域法师", "镇压区域", "禁咒入门"),
                ("传奇法师", "活化身于法则", "禁咒·龙息"),
                ("神级法师", "人形法则", "言出法随"),
            ],
            "科幻能力等级": [
                ("E级", "微弱异能", "辅助·感知"),
                ("D级", "可控异能", "局部增强"),
                ("C级", "战斗级", "对抗一队普通士兵"),
                ("B级", "区域级", "对抗一支小队"),
                ("A级", "战略级", "对抗特种部队"),
                ("S级", "城市级", "镇压一城"),
                ("SS级", "国家级", "撼动战局"),
                ("SSS级", "毁灭级", "毁灭一国"),
            ],
        }
        rows = presets.get(name, [])
        if not rows:
            return
        # 清空并填充
        self.tbl_power.setRowCount(0)
        for i, (lv, desc, ab) in enumerate(rows):
            r = self.tbl_power.rowCount()
            self.tbl_power.insertRow(r)
            for c, v in enumerate([str(i+1), lv, desc, ab]):
                self.tbl_power.setItem(r, c, QTableWidgetItem(v))

    # ── 5. 伏笔追踪子页 ────────────────────────────────────
    def _build_foreshadows_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        # v1.76 BUG-056:顶部状态 label(自动回收检查/重评估状态可见)
        from datetime import datetime as _dt
        self.lbl_last_check = QLabel(
            "📌 自动回收检查:尚未运行(写完下一章后查看)"
        )
        self.lbl_last_check.setStyleSheet(
            "color: #555; font-size: 11px; padding: 4px 6px; "
            "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
        self.lbl_last_check.setWordWrap(True)
        lay.addWidget(self.lbl_last_check)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增伏笔")
        btn_add.clicked.connect(self._add_fore)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_fore)
        btn_check = QPushButton("🔍 检查逾期伏笔")
        btn_check.setToolTip("扫描所有伏笔,找出已超过计划回收章节但未回收的")
        btn_check.setStyleSheet(
            "QPushButton { background:#e74c3c; color:white; padding:4px 10px;"
            "border-radius:3px; } QPushButton:hover { background:#c0392b; }")
        btn_check.clicked.connect(self._check_overdue_foreshadows)
        btn_clear_fore = QPushButton("🗑 清空伏笔")
        btn_clear_fore.clicked.connect(self._clear_all_foreshadows)
        # v1.76 BUG-056:一键 AI 重评估 plan_pay_at=0 的伏笔
        self.btn_reeval_fore = QPushButton("🤖 AI 重评估未设回收期")
        self.btn_reeval_fore.setToolTip(
            "把所有 plan_pay_at=0 的伏笔交给 AI 评估合理回收章节,自动回填")
        self.btn_reeval_fore.setStyleSheet(
            "QPushButton { background:#fff3e0; color:#5d4037; border:1px solid #ffa726; }")
        top.addWidget(btn_add); top.addWidget(btn_del)
        top.addWidget(btn_check); top.addWidget(btn_clear_fore)
        top.addWidget(self.btn_reeval_fore); top.addStretch()
        lay.addLayout(top)
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.tbl_fore = QTableWidget(0, 5)
        self.tbl_fore.setHorizontalHeaderLabels([
            "埋设章节", "伏笔内容", "计划回收章节", "已回收?", "回收章节"
        ])
        self.tbl_fore.horizontalHeader().setStretchLastSection(True)
        self.tbl_fore.verticalHeader().setVisible(False)
        self.tbl_fore.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_fore.setColumnWidth(0, 70)
        self.tbl_fore.setColumnWidth(1, 280)
        self.tbl_fore.setColumnWidth(2, 90)
        self.tbl_fore.setColumnWidth(3, 70)
        lay.addWidget(self.tbl_fore)
        
        tip = QLabel(
            "💡 v1.76 起,程序会在每章生成后自动检查回收(AI 看本章正文回收了哪些伏笔)\n"
            "    『已回收?』填 是/否,回收后填上回收章节号。\n"
            "    plan_pay_at=0 的伏笔会触发误报超期,可用上方按钮一键 AI 重评估。")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🪤 伏笔追踪")
    
    def _add_fore(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_fore.rowCount()
        self.tbl_fore.insertRow(r)
        defaults = ["1", "新伏笔", "30", "否", ""]
        for c, v in enumerate(defaults):
            self.tbl_fore.setItem(r, c, QTableWidgetItem(v))
    
    def _del_fore(self):
        rows = sorted(set(idx.row() for idx in self.tbl_fore.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_fore.removeRow(r)

    def _check_overdue_foreshadows(self):
        """检查逾期伏笔:已超过计划回收章节但未回收的"""
        overdue = []
        try:
            mw = self.window()
            current_ch = len(mw.chapters) if hasattr(mw, 'chapters') else 0
        except Exception:
            current_ch = 999
        for r in range(self.tbl_fore.rowCount()):
            paid_item = self.tbl_fore.item(r, 3)
            paid = paid_item.text().strip() if paid_item else ""
            if paid in ("是", "✓", "yes", "1"):
                continue  # 已回收
            plan_item = self.tbl_fore.item(r, 2)
            plan = 0
            try:
                plan = int(plan_item.text().strip()) if plan_item else 0
            except ValueError:
                pass
            if plan > 0 and current_ch >= plan:
                content_item = self.tbl_fore.item(r, 1)
                content = content_item.text() if content_item else "?"
                ch_item = self.tbl_fore.item(r, 0)
                ch = ch_item.text() if ch_item else "?"
                overdue.append(f"第{ch}章埋下 → 计划第{plan}章回收(当前已写{current_ch}章):\n  {content}")
        if overdue:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, f"⚠ 发现 {len(overdue)} 条逾期伏笔",
                "\n\n".join(overdue[:10]))
        else:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "✅ 伏笔检查", "没有逾期伏笔,全部正常!")

    def _clear_all_foreshadows(self):
        """清空所有伏笔"""
        from PyQt5.QtWidgets import QMessageBox
        ret = QMessageBox.question(self, "确认清空",
            f"确定清空全部 {self.tbl_fore.rowCount()} 条伏笔?")
        if ret == QMessageBox.Yes:
            self.tbl_fore.setRowCount(0)

    def _clear_all_data(self):
        """清空角色与世界的全部数据"""
        from PyQt5.QtWidgets import QMessageBox
        tables = []
        for name in ['tbl_chars', 'tbl_relations', 'tbl_timeline',
                     'tbl_items', 'tbl_fore']:
            t = getattr(self, name, None)
            if t:
                tables.append((name, t))
        total = sum(t.rowCount() for _, t in tables)
        ret = QMessageBox.question(self, "⚠ 确认清空全部数据",
            f"将清空角色与世界的所有数据:\n\n"
            f"  角色库: {getattr(self, 'tbl_chars', None) and self.tbl_chars.rowCount() or 0} 条\n"
            f"  关系: {getattr(self, 'tbl_relations', None) and self.tbl_relations.rowCount() or 0} 条\n"
            f"  时间线: {getattr(self, 'tbl_timeline', None) and self.tbl_timeline.rowCount() or 0} 条\n"
            f"  物品: {getattr(self, 'tbl_items', None) and self.tbl_items.rowCount() or 0} 条\n"
            f"  伏笔: {getattr(self, 'tbl_fore', None) and self.tbl_fore.rowCount() or 0} 条\n\n"
            f"总计 {total} 条数据,清空后不可恢复!\n继续?")
        if ret == QMessageBox.Yes:
            for name, t in tables:
                t.setRowCount(0)

    # ── 5b. 威胁承诺子页(v1.77 BUG-057)────────────────────
    def _build_promises_tab(self):
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem
        w = QWidget()
        lay = QVBoxLayout(w)
        
        # v1.77:顶部状态 label(同 v1.76 五态模式)
        self.lbl_last_promise_check = QLabel(
            "📌 自动兑现检查:尚未运行(写完下一章后查看)"
        )
        self.lbl_last_promise_check.setStyleSheet(
            "color: #555; font-size: 11px; padding: 4px 6px; "
            "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
        self.lbl_last_promise_check.setWordWrap(True)
        lay.addWidget(self.lbl_last_promise_check)
        
        top = QHBoxLayout()
        btn_add = QPushButton("➕ 新增承诺/威胁/约定")
        btn_add.clicked.connect(self._add_promise)
        btn_del = QPushButton("➖ 删除选中")
        btn_del.clicked.connect(self._del_promise)
        # v1.77:AI 重评估按钮(同 v1.76 模式)
        self.btn_reeval_promise = QPushButton("🤖 AI 重评估未设截止期")
        self.btn_reeval_promise.setToolTip(
            "把所有 deadline=0 的承诺/威胁/约定交给 AI 评估合理截止章节,自动回填")
        self.btn_reeval_promise.setStyleSheet(
            "QPushButton { background:#fff3e0; color:#5d4037; border:1px solid #ffa726; }")
        top.addWidget(btn_add); top.addWidget(btn_del)
        top.addWidget(self.btn_reeval_promise); top.addStretch()
        lay.addLayout(top)
        
        self.tbl_promises = QTableWidget(0, 7)
        self.tbl_promises.setHorizontalHeaderLabels([
            "埋设章", "类型", "发起者", "对象", "内容", "截止章", "已兑现?"
        ])
        self.tbl_promises.horizontalHeader().setStretchLastSection(False)
        self.tbl_promises.verticalHeader().setVisible(False)
        self.tbl_promises.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_promises.setColumnWidth(0, 60)
        self.tbl_promises.setColumnWidth(1, 60)
        self.tbl_promises.setColumnWidth(2, 80)
        self.tbl_promises.setColumnWidth(3, 80)
        self.tbl_promises.setColumnWidth(4, 280)
        self.tbl_promises.setColumnWidth(5, 60)
        self.tbl_promises.setColumnWidth(6, 70)
        lay.addWidget(self.tbl_promises)
        
        tip = QLabel(
            "💡 跟踪人物明确说出口的【承诺 / 威胁 / 约定】,与伏笔不同 — 这是【人对人的契约】,违背即失信。\n"
            "    每章生成后,AI 自动检查本章正文是否兑现/触发/到期了清单中的条目。\n"
            "    类型:承诺(许诺) / 威胁(下最后通牒) / 约定(双方约赴某事)。\n"
            "    已兑现? 填 是/否;到期未兑现会触发【本章硬性必须兑现】强约束注入。")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "⚡ 威胁承诺")
    
    def _add_promise(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_promises.rowCount()
        self.tbl_promises.insertRow(r)
        defaults = ["1", "承诺", "", "", "新承诺/威胁/约定", "15", "否"]
        for c, v in enumerate(defaults):
            self.tbl_promises.setItem(r, c, QTableWidgetItem(v))
    
    def _del_promise(self):
        rows = sorted(set(idx.row() for idx in self.tbl_promises.selectedIndexes()),
                      reverse=True)
        for r in rows:
            self.tbl_promises.removeRow(r)

    # ── 5c. 剧情进度子页(v1.78 BUG-058)─────────────────────
    # 3 子表共用一个 sub-tab(嵌套 QTabWidget):
    #   - tbl_arcs:故事弧线(3 列:弧线名/progress/phase)
    #   - tbl_rel_values:关系值矩阵(4 列:角色A/角色B/value/最近变化章)
    #   - tbl_goals:当前目标(4 列:目标名/优先级/状态/设立章)
    def _build_plot_progress_tab(self):
        from PyQt5.QtWidgets import (QTableWidget, QTableWidgetItem, QTabWidget,
                                     QComboBox)
        w = QWidget()
        lay = QVBoxLayout(w)

        # 顶部状态 label(同 v1.76/v1.77 五态模式)
        self.lbl_last_arc_check = QLabel(
            "📌 自动弧线/关系值评估:尚未运行(写完下一章后查看)"
        )
        self.lbl_last_arc_check.setStyleSheet(
            "color: #555; font-size: 11px; padding: 4px 6px; "
            "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
        self.lbl_last_arc_check.setWordWrap(True)
        lay.addWidget(self.lbl_last_arc_check)

        # 内嵌 3 子选项卡
        inner_tabs = QTabWidget()
        lay.addWidget(inner_tabs)

        # ── 子表 1:故事弧线 ──────────────────────────────
        w_arcs = QWidget()
        lay_arcs = QVBoxLayout(w_arcs)
        top_arcs = QHBoxLayout()
        btn_add_arc = QPushButton("➕ 新增弧线")
        btn_add_arc.clicked.connect(self._add_arc)
        btn_del_arc = QPushButton("➖ 删除选中")
        btn_del_arc.clicked.connect(self._del_arc)
        top_arcs.addWidget(btn_add_arc); top_arcs.addWidget(btn_del_arc)
        top_arcs.addStretch()
        lay_arcs.addLayout(top_arcs)

        self.tbl_arcs = QTableWidget(0, 3)
        self.tbl_arcs.setHorizontalHeaderLabels([
            "弧线名", "当前进度(0-100)", "阶段"
        ])
        self.tbl_arcs.horizontalHeader().setStretchLastSection(False)
        self.tbl_arcs.verticalHeader().setVisible(False)
        self.tbl_arcs.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_arcs.setColumnWidth(0, 200)
        self.tbl_arcs.setColumnWidth(1, 130)
        self.tbl_arcs.setColumnWidth(2, 100)
        lay_arcs.addWidget(self.tbl_arcs)

        tip_arcs = QLabel(
            "💡 故事弧线(主线/支线/金手指线)的整体推进百分比。\n"
            "    阶段:开端/铺垫/转折/高潮/收束(5 选 1)。\n"
            "    每章生成后,AI 自动评估本章推进了哪几条弧线、推进了多少 progress,自动累加(封顶 100)。")
        tip_arcs.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip_arcs.setWordWrap(True)
        lay_arcs.addWidget(tip_arcs)
        inner_tabs.addTab(w_arcs, "📊 故事弧线")

        # ── 子表 2:关系值矩阵 ──────────────────────────
        w_rels = QWidget()
        lay_rels = QVBoxLayout(w_rels)
        top_rels = QHBoxLayout()
        btn_add_rel = QPushButton("➕ 新增关系值")
        btn_add_rel.clicked.connect(self._add_rel_value)
        btn_del_rel = QPushButton("➖ 删除选中")
        btn_del_rel.clicked.connect(self._del_rel_value)
        top_rels.addWidget(btn_add_rel); top_rels.addWidget(btn_del_rel)
        top_rels.addStretch()
        lay_rels.addLayout(top_rels)

        self.tbl_rel_values = QTableWidget(0, 4)
        self.tbl_rel_values.setHorizontalHeaderLabels([
            "角色A", "角色B", "关系值(-100~+100)", "最近变化章"
        ])
        self.tbl_rel_values.horizontalHeader().setStretchLastSection(False)
        self.tbl_rel_values.verticalHeader().setVisible(False)
        self.tbl_rel_values.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_rel_values.setColumnWidth(0, 120)
        self.tbl_rel_values.setColumnWidth(1, 120)
        self.tbl_rel_values.setColumnWidth(2, 140)
        self.tbl_rel_values.setColumnWidth(3, 100)
        lay_rels.addWidget(self.tbl_rel_values)

        tip_rels = QLabel(
            "💡 关系值数字化:-100=死敌 / -80=有仇 / -50=不和 / 0=陌生 / "
            "+50=朋友 / +80=至交 / +100=至亲。\n"
            "    AI 每章评估本章互动让哪些关系值变化,自动累加(封顶 ±100)。\n"
            "    注入 prompt 时,|value|≥50 的会作为『关系热点』提示 AI 写出符合该关系的反应。")
        tip_rels.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip_rels.setWordWrap(True)
        lay_rels.addWidget(tip_rels)
        inner_tabs.addTab(w_rels, "💞 关系值矩阵")

        # ── 子表 3:当前目标 ──────────────────────────
        w_goals = QWidget()
        lay_goals = QVBoxLayout(w_goals)
        top_goals = QHBoxLayout()
        btn_add_goal = QPushButton("➕ 新增目标")
        btn_add_goal.clicked.connect(self._add_goal)
        btn_del_goal = QPushButton("➖ 删除选中")
        btn_del_goal.clicked.connect(self._del_goal)
        top_goals.addWidget(btn_add_goal); top_goals.addWidget(btn_del_goal)
        top_goals.addStretch()
        lay_goals.addLayout(top_goals)

        self.tbl_goals = QTableWidget(0, 4)
        self.tbl_goals.setHorizontalHeaderLabels([
            "目标名", "优先级", "状态", "设立章节"
        ])
        self.tbl_goals.horizontalHeader().setStretchLastSection(False)
        self.tbl_goals.verticalHeader().setVisible(False)
        self.tbl_goals.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_goals.setColumnWidth(0, 280)
        self.tbl_goals.setColumnWidth(1, 80)
        self.tbl_goals.setColumnWidth(2, 90)
        self.tbl_goals.setColumnWidth(3, 80)
        lay_goals.addWidget(self.tbl_goals)

        tip_goals = QLabel(
            "💡 主角当前最关心什么。\n"
            "    优先级:主线/支线/紧急。状态:进行中/已达成/已放弃。\n"
            "    注入 prompt 时,只把【进行中】的目标喂给 AI,避免主角行动偏离当前目标。")
        tip_goals.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip_goals.setWordWrap(True)
        lay_goals.addWidget(tip_goals)
        inner_tabs.addTab(w_goals, "🎯 当前目标")

        self.sub_tabs.addTab(w, "📈 剧情进度")

    def _add_arc(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_arcs.rowCount()
        self.tbl_arcs.insertRow(r)
        defaults = ["新弧线", "5", "开端"]
        for c, v in enumerate(defaults):
            self.tbl_arcs.setItem(r, c, QTableWidgetItem(v))

    def _del_arc(self):
        rows = sorted(set(idx.row() for idx in self.tbl_arcs.selectedIndexes()),
                      reverse=True)
        for r in rows:
            self.tbl_arcs.removeRow(r)

    def _add_rel_value(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_rel_values.rowCount()
        self.tbl_rel_values.insertRow(r)
        defaults = ["主角", "", "0", "1"]
        for c, v in enumerate(defaults):
            self.tbl_rel_values.setItem(r, c, QTableWidgetItem(v))

    def _del_rel_value(self):
        rows = sorted(set(idx.row() for idx in self.tbl_rel_values.selectedIndexes()),
                      reverse=True)
        for r in rows:
            self.tbl_rel_values.removeRow(r)

    def _add_goal(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_goals.rowCount()
        self.tbl_goals.insertRow(r)
        defaults = ["新目标", "主线", "进行中", "1"]
        for c, v in enumerate(defaults):
            self.tbl_goals.setItem(r, c, QTableWidgetItem(v))

    def _del_goal(self):
        rows = sorted(set(idx.row() for idx in self.tbl_goals.selectedIndexes()),
                      reverse=True)
        for r in rows:
            self.tbl_goals.removeRow(r)

    # ── 5d. 信息隔离子页(v1.79 BUG-059)──────────────────────
    # 2 子表 via info_id 外键引用:
    #   - tbl_infos:信息条目(4 列:id/内容/来源章/来源类型)
    #   - tbl_known_by:知情人表(3 列:信息 id/知情人/知情来源)
    # 与 v1.78 的核心差异:
    #   - 引入【外键引用】(known_by.info_id 引用 infos.id)
    #   - info_check 是【侦测违规】检查(找穿帮),不是状态推进
    def _build_info_isolation_tab(self):
        from PyQt5.QtWidgets import (QTableWidget, QTableWidgetItem, QTabWidget)
        w = QWidget()
        lay = QVBoxLayout(w)

        # 顶部状态 label(同 v1.76/v1.77/v1.78 五态模式)
        self.lbl_last_info_check = QLabel(
            "📌 自动知识穿帮检查:尚未运行(写完下一章后查看)"
        )
        self.lbl_last_info_check.setStyleSheet(
            "color: #555; font-size: 11px; padding: 4px 6px; "
            "background: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;")
        self.lbl_last_info_check.setWordWrap(True)
        lay.addWidget(self.lbl_last_info_check)

        # 嵌套 2 子选项卡
        inner_tabs = QTabWidget()
        lay.addWidget(inner_tabs)

        # ── 子表 1:信息条目 ─────────────────────────────
        w_infos = QWidget()
        lay_infos = QVBoxLayout(w_infos)
        top_infos = QHBoxLayout()
        btn_add_info = QPushButton("➕ 新增信息")
        btn_add_info.clicked.connect(self._add_info)
        btn_del_info = QPushButton("➖ 删除选中")
        btn_del_info.clicked.connect(self._del_info)
        top_infos.addWidget(btn_add_info); top_infos.addWidget(btn_del_info)
        top_infos.addStretch()
        lay_infos.addLayout(top_infos)

        self.tbl_infos = QTableWidget(0, 4)
        self.tbl_infos.setHorizontalHeaderLabels([
            "信息 id", "信息内容", "来源章", "来源类型"
        ])
        self.tbl_infos.horizontalHeader().setStretchLastSection(False)
        self.tbl_infos.verticalHeader().setVisible(False)
        self.tbl_infos.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_infos.setColumnWidth(0, 100)
        self.tbl_infos.setColumnWidth(1, 380)
        self.tbl_infos.setColumnWidth(2, 80)
        self.tbl_infos.setColumnWidth(3, 100)
        lay_infos.addWidget(self.tbl_infos)

        tip_infos = QLabel(
            "💡 全文唯一可被反复引用的关键信息(角色身份秘密/金手指本质/势力暗线/血脉来历)。\n"
            "    id 用 INFO-001/INFO-002... 顺序编号(系统自动去重续号)。\n"
            "    来源类型 = 设定(出生即有)/事件揭露(场景里被揭穿)/角色透露(亲口说出)。")
        tip_infos.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip_infos.setWordWrap(True)
        lay_infos.addWidget(tip_infos)
        inner_tabs.addTab(w_infos, "📋 信息条目")

        # ── 子表 2:知情人表 ─────────────────────────────
        w_kb = QWidget()
        lay_kb = QVBoxLayout(w_kb)
        top_kb = QHBoxLayout()
        btn_add_kb = QPushButton("➕ 新增知情人")
        btn_add_kb.clicked.connect(self._add_known_by)
        btn_del_kb = QPushButton("➖ 删除选中")
        btn_del_kb.clicked.connect(self._del_known_by)
        top_kb.addWidget(btn_add_kb); top_kb.addWidget(btn_del_kb)
        top_kb.addStretch()
        lay_kb.addLayout(top_kb)

        self.tbl_known_by = QTableWidget(0, 3)
        self.tbl_known_by.setHorizontalHeaderLabels([
            "信息 id(引用)", "知情人", "知情来源"
        ])
        self.tbl_known_by.horizontalHeader().setStretchLastSection(False)
        self.tbl_known_by.verticalHeader().setVisible(False)
        self.tbl_known_by.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_known_by.setColumnWidth(0, 110)
        self.tbl_known_by.setColumnWidth(1, 120)
        self.tbl_known_by.setColumnWidth(2, 400)
        lay_kb.addWidget(self.tbl_known_by)

        tip_kb = QLabel(
            "💡 谁知道哪条信息 + 怎么知道的(信息 id 必须在【信息条目】里存在,系统自动校验)。\n"
            "    AI 章末自动:① 扫描穿帮(不该知道的人用了某 info)② 追踪新披露事件(谁告诉了谁)。\n"
            "    每章生成时,注入会只向【出场角色】告知他们的【已知信息边界】,严防 OOC。")
        tip_kb.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip_kb.setWordWrap(True)
        lay_kb.addWidget(tip_kb)
        inner_tabs.addTab(w_kb, "👁 知情人表")

        self.sub_tabs.addTab(w, "🔒 信息隔离")

    def _add_info(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_infos.rowCount()
        # 自动续号 INFO-XXX
        existing = set()
        for i in range(r):
            it = self.tbl_infos.item(i, 0)
            if it and it.text().strip():
                existing.add(it.text().strip())
        n = 1
        while f"INFO-{n:03d}" in existing:
            n += 1
        new_id = f"INFO-{n:03d}"
        self.tbl_infos.insertRow(r)
        defaults = [new_id, "新关键信息", "1", "设定"]
        for c, v in enumerate(defaults):
            self.tbl_infos.setItem(r, c, QTableWidgetItem(v))

    def _del_info(self):
        rows = sorted(set(idx.row() for idx in self.tbl_infos.selectedIndexes()),
                      reverse=True)
        for r in rows:
            self.tbl_infos.removeRow(r)

    def _add_known_by(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_known_by.rowCount()
        self.tbl_known_by.insertRow(r)
        defaults = ["INFO-001", "", "第1章亲口告诉"]
        for c, v in enumerate(defaults):
            self.tbl_known_by.setItem(r, c, QTableWidgetItem(v))

    def _del_known_by(self):
        rows = sorted(set(idx.row() for idx in self.tbl_known_by.selectedIndexes()),
                      reverse=True)
        for r in rows:
            self.tbl_known_by.removeRow(r)

    # v1.84:POV 模式切换 — 只有"角色 POV"才启用角色名输入框
    def _on_pov_mode_changed(self, mode):
        self.le_pov_character.setEnabled(mode == "角色 POV")

    def _resolve_pov_character(self):
        """v1.84:解析当前 POV 模式对应的角色名。
        返回 (mode, character_name) — character_name 为空表示全知视角"""
        mode = self.cb_pov_mode.currentText() if hasattr(self, "cb_pov_mode") else "全知视角"
        if mode == "全知视角":
            return ("全知视角", "")
        if mode == "主角 POV":
            # 取角色库第 1 个角色当主角(惯例 — 角色库第一条通常是主角)
            if hasattr(self, "tbl_chars") and self.tbl_chars.rowCount() > 0:
                first = self.tbl_chars.item(0, 0)
                if first and first.text().strip():
                    return ("主角 POV", first.text().strip())
            return ("主角 POV", "")  # 角色库空,fallback 全知
        if mode == "角色 POV":
            name = (self.le_pov_character.text() or "").strip() if hasattr(self, "le_pov_character") else ""
            return ("角色 POV", name)
        return ("全知视角", "")

    # ── 5e. 剧情树子页(v1.80 BUG-060)─────────────────────
    # 与其他 sub-tab 的核心差异:用 QTreeWidget(不是 QTableWidget) — 整套 CharLib 唯一的树形 UI。
    # 节点 4 层:故事(根)→ 阶段 → 章节槽 → 剧情点
    # 每节点 4 字段:节点名 / kind(故事/阶段/章节槽/剧情点)/ ch_range / note
    # 节点用 hidden role 存 node_id(N-001 自动续号),AI 抽取扁平 list[parent_id, ...]
    # 后处理建树;持久化用 _tree_to_dict / _dict_to_tree 双向序列化
    def _build_plot_tree_tab(self):
        from PyQt5.QtWidgets import (QTreeWidget, QTreeWidgetItem,
                                     QAbstractItemView, QInputDialog,
                                     QHBoxLayout)
        from PyQt5.QtCore import Qt
        w = QWidget()
        lay = QVBoxLayout(w)

        # 顶部工具栏 — 6 操作按钮
        top = QHBoxLayout()
        btn_add_root = QPushButton("➕ 加根节点(故事)")
        btn_add_root.clicked.connect(self._add_plot_root)
        btn_add_child = QPushButton("➕ 加子节点")
        btn_add_child.clicked.connect(self._add_plot_child)
        btn_del = QPushButton("➖ 删除节点(含子孙)")
        btn_del.clicked.connect(self._del_plot_node)
        btn_expand = QPushButton("⊟ 展开全部")
        btn_expand.clicked.connect(lambda: self.tree_plot.expandAll())
        btn_collapse = QPushButton("⊞ 折叠全部")
        btn_collapse.clicked.connect(lambda: self.tree_plot.collapseAll())
        top.addWidget(btn_add_root)
        top.addWidget(btn_add_child)
        top.addWidget(btn_del)
        top.addWidget(btn_expand)
        top.addWidget(btn_collapse)
        top.addStretch()
        lay.addLayout(top)

        # QTreeWidget — 5 列(v1.85 加"已挂章号"列)
        self.tree_plot = QTreeWidget()
        self.tree_plot.setColumnCount(5)
        self.tree_plot.setHeaderLabels(["节点名", "类型", "章节范围", "备注", "已挂章号"])
        self.tree_plot.setColumnWidth(0, 260)
        self.tree_plot.setColumnWidth(1, 80)
        self.tree_plot.setColumnWidth(2, 90)
        self.tree_plot.setColumnWidth(3, 240)
        self.tree_plot.setColumnWidth(4, 120)
        # 拖拽重排
        self.tree_plot.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree_plot.setEditTriggers(
            QTreeWidget.DoubleClicked | QTreeWidget.SelectedClicked)
        self.tree_plot.setSelectionMode(QAbstractItemView.SingleSelection)
        # v1.86:右键菜单 — 反查相关数据(角色/伏笔/承诺/关系/信息/章节)
        from PyQt5.QtCore import Qt as _Qt
        self.tree_plot.setContextMenuPolicy(_Qt.CustomContextMenu)
        self.tree_plot.customContextMenuRequested.connect(
            self._show_plot_node_context_menu)
        lay.addWidget(self.tree_plot)

        tip = QLabel(
            "💡 剧情树是【作者主动规划的故事架构】,与其他 9 库(被动抽取)不同。\n"
            "    4 层结构:故事(根)→ 阶段(几十章)→ 章节槽(几章)→ 剧情点(单章)。\n"
            "    每节点 5 字段:名/类型/章节范围/备注/已挂章号(v1.85 章末 AI 自动回流)。\n"
            "    支持拖拽重排;每章注入时,系统会找到当前章节所在的最近祖先节点。\n"
            "    v1.85:章节生成后,AI 自动判定『本章写到了哪个节点』,把章号回流到对应节点的『已挂章号』列。\n"
            "    v1.86:右键节点 → 『🔍 反查相关数据』查看该节点关联的角色/伏笔/承诺/关系/信息。")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.sub_tabs.addTab(w, "🌳 剧情树")

    # ── 5e' 剧情树操作方法 ────────────────────────────
    # node_id 存在 QTreeWidgetItem.data(0, Qt.UserRole) — 持久化用,UI 不显示
    _NODE_ROLE = 256  # Qt.UserRole, 但避免硬依赖,用数字

    def _next_plot_node_id(self):
        """扫描树,找下一个可用 N-XXX id"""
        from PyQt5.QtCore import Qt
        used = set()
        def walk(item):
            nid = item.data(0, Qt.UserRole)
            if nid:
                used.add(str(nid))
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.tree_plot.topLevelItemCount()):
            walk(self.tree_plot.topLevelItem(i))
        n = 1
        while f"N-{n:03d}" in used:
            n += 1
        return f"N-{n:03d}"

    def _add_plot_root(self):
        from PyQt5.QtWidgets import QTreeWidgetItem
        from PyQt5.QtCore import Qt
        nid = self._next_plot_node_id()
        item = QTreeWidgetItem(["新故事", "故事", "", "(根节点,整本书的主线)", ""])
        item.setData(0, Qt.UserRole, nid)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.tree_plot.addTopLevelItem(item)
        item.setExpanded(True)

    def _add_plot_child(self):
        """对选中节点加子节点"""
        from PyQt5.QtWidgets import QTreeWidgetItem, QMessageBox
        from PyQt5.QtCore import Qt
        cur = self.tree_plot.currentItem()
        if not cur:
            QMessageBox.information(
                self, "提示", "请先选中一个节点(作为父节点),再点『加子节点』。")
            return
        # 子节点 kind 默认基于父节点 kind 推断
        parent_kind = cur.text(1)
        kind_map = {"故事": "阶段", "阶段": "章节槽",
                    "章节槽": "剧情点", "剧情点": "剧情点"}
        new_kind = kind_map.get(parent_kind, "剧情点")
        nid = self._next_plot_node_id()
        item = QTreeWidgetItem(["新" + new_kind, new_kind, "", "", ""])
        item.setData(0, Qt.UserRole, nid)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        cur.addChild(item)
        cur.setExpanded(True)
        self.tree_plot.setCurrentItem(item)

    def _del_plot_node(self):
        """删除选中节点(含全部子孙)"""
        from PyQt5.QtWidgets import QMessageBox
        cur = self.tree_plot.currentItem()
        if not cur:
            QMessageBox.information(self, "提示", "请先选中一个节点。")
            return
        # 统计子孙数
        def count_descendants(item):
            n = item.childCount()
            for i in range(item.childCount()):
                n += count_descendants(item.child(i))
            return n
        descn = count_descendants(cur)
        if descn > 0:
            ret = QMessageBox.question(
                self, "确认删除",
                f"节点『{cur.text(0)}』下有 {descn} 个子孙节点,确认删除吗?")
            if ret != QMessageBox.Yes:
                return
        parent = cur.parent()
        if parent:
            parent.removeChild(cur)
        else:
            idx = self.tree_plot.indexOfTopLevelItem(cur)
            self.tree_plot.takeTopLevelItem(idx)

    # ── v1.86 BUG-063:多视角反查 ────────────────────────────
    # 右键剧情树节点 → 弹窗显示该节点关联的角色/伏笔/承诺/关系/信息
    # 反查算法基于该节点的 chapter_links 第 5 列 + ch_range 字段(扩大查找范围)

    def _node_chapter_set(self, item):
        """从节点的 chapter_links + ch_range 算出"该节点关联的章号集合"
        返回 set[int]。ch_range 是用户预设范围,chapter_links 是 AI 回流的实际章号"""
        chs = set()
        # 1. chapter_links 第 5 列(逗号分隔)
        if item.columnCount() > 4:
            for c in (item.text(4) or "").split(","):
                c = c.strip()
                try:
                    chs.add(int(c))
                except ValueError:
                    pass
        # 2. ch_range 第 3 列("3-10" 或 "5")
        cr = (item.text(2) or "").strip()
        if cr:
            if "-" in cr:
                try:
                    a, b = cr.split("-", 1)
                    for ch in range(int(a), int(b) + 1):
                        chs.add(ch)
                except ValueError:
                    pass
            else:
                try:
                    chs.add(int(cr))
                except ValueError:
                    pass
        return chs

    def _compute_node_cross_refs(self, item):
        """v1.86 核心反查算法:给定剧情树节点,返回关联的各库条目。
        纯数据计算函数,无 UI 副作用,易测试。

        返回 dict:{
          "chapters":    [int, ...]               关联章号(排序)
          "foreshadows": [(row, 内容, 埋设章, 回收章, 已回收), ...]
          "promises":    [(row, 类型, 发起者→对象, 内容, 埋设章, 截止章), ...]
          "rel_changes": [(row, A, B, value, 章号), ...]
          "infos":       [(row, info_id, 内容, 来源章, 来源类型), ...]
          "characters":  [(row, 姓名, 角色定位, 首次出场), ...]
        }
        """
        chs = self._node_chapter_set(item)

        # 1. 章节列表(直接复用 chs)
        out = {"chapters": sorted(chs)}

        # 2. 伏笔:埋设章 ∈ chs 或 回收章 ∈ chs
        out["foreshadows"] = []
        if hasattr(self, "tbl_fore"):
            for r in range(self.tbl_fore.rowCount()):
                set_ch_s = (self.tbl_fore.item(r, 0).text() if self.tbl_fore.item(r, 0) else "")
                content_s = (self.tbl_fore.item(r, 1).text() if self.tbl_fore.item(r, 1) else "")
                plan_ch_s = (self.tbl_fore.item(r, 2).text() if self.tbl_fore.item(r, 2) else "")
                done_s = (self.tbl_fore.item(r, 3).text() if self.tbl_fore.item(r, 3) else "")
                recover_ch_s = (self.tbl_fore.item(r, 4).text() if self.tbl_fore.item(r, 4) else "")
                hit = False
                for ch_s in (set_ch_s, recover_ch_s):
                    try:
                        if int(ch_s) in chs:
                            hit = True
                            break
                    except ValueError:
                        continue
                if hit:
                    out["foreshadows"].append(
                        (r, content_s, set_ch_s, recover_ch_s or plan_ch_s, done_s))

        # 3. 承诺:埋设章 ∈ chs 或 截止章 ∈ chs
        out["promises"] = []
        if hasattr(self, "tbl_promises"):
            for r in range(self.tbl_promises.rowCount()):
                set_ch_s = (self.tbl_promises.item(r, 0).text() if self.tbl_promises.item(r, 0) else "")
                kind = (self.tbl_promises.item(r, 1).text() if self.tbl_promises.item(r, 1) else "")
                a = (self.tbl_promises.item(r, 2).text() if self.tbl_promises.item(r, 2) else "")
                b = (self.tbl_promises.item(r, 3).text() if self.tbl_promises.item(r, 3) else "")
                content = (self.tbl_promises.item(r, 4).text() if self.tbl_promises.item(r, 4) else "")
                deadline_s = (self.tbl_promises.item(r, 5).text() if self.tbl_promises.item(r, 5) else "")
                hit = False
                for ch_s in (set_ch_s, deadline_s):
                    try:
                        if int(ch_s) in chs:
                            hit = True
                            break
                    except ValueError:
                        continue
                if hit:
                    out["promises"].append((r, kind, f"{a}→{b}", content, set_ch_s, deadline_s))

        # 4. 关系值变化:最近变化章 ∈ chs
        out["rel_changes"] = []
        if hasattr(self, "tbl_rel_values"):
            for r in range(self.tbl_rel_values.rowCount()):
                a = (self.tbl_rel_values.item(r, 0).text() if self.tbl_rel_values.item(r, 0) else "")
                b = (self.tbl_rel_values.item(r, 1).text() if self.tbl_rel_values.item(r, 1) else "")
                val = (self.tbl_rel_values.item(r, 2).text() if self.tbl_rel_values.item(r, 2) else "")
                ch_s = (self.tbl_rel_values.item(r, 3).text() if self.tbl_rel_values.item(r, 3) else "")
                try:
                    if int(ch_s) in chs:
                        out["rel_changes"].append((r, a, b, val, ch_s))
                except ValueError:
                    continue

        # 5. 信息:来源章 ∈ chs
        out["infos"] = []
        if hasattr(self, "tbl_infos"):
            for r in range(self.tbl_infos.rowCount()):
                iid = (self.tbl_infos.item(r, 0).text() if self.tbl_infos.item(r, 0) else "")
                content = (self.tbl_infos.item(r, 1).text() if self.tbl_infos.item(r, 1) else "")
                src_ch_s = (self.tbl_infos.item(r, 2).text() if self.tbl_infos.item(r, 2) else "")
                src_type = (self.tbl_infos.item(r, 3).text() if self.tbl_infos.item(r, 3) else "")
                try:
                    if int(src_ch_s) in chs:
                        out["infos"].append((r, iid, content, src_ch_s, src_type))
                except ValueError:
                    continue

        # 6. 角色:首次出场 ∈ chs(简化判定 — 用首次出场字段)
        out["characters"] = []
        if hasattr(self, "tbl_chars"):
            for r in range(self.tbl_chars.rowCount()):
                name = (self.tbl_chars.item(r, 0).text() if self.tbl_chars.item(r, 0) else "")
                role = (self.tbl_chars.item(r, 1).text() if self.tbl_chars.item(r, 1) else "")
                first_s = (self.tbl_chars.item(r, 7).text() if self.tbl_chars.item(r, 7) else "")
                try:
                    if int(first_s) in chs:
                        out["characters"].append((r, name, role, first_s))
                except ValueError:
                    continue

        return out

    def _show_plot_node_context_menu(self, pos):
        """v1.86:剧情树右键菜单 — 反查相关数据"""
        from PyQt5.QtWidgets import QMenu
        item = self.tree_plot.itemAt(pos)
        if not item:
            return
        menu = QMenu(self.tree_plot)
        act = menu.addAction("🔍 反查相关数据")
        act.triggered.connect(lambda: self._open_node_cross_refs_dialog(item))
        menu.exec_(self.tree_plot.viewport().mapToGlobal(pos))

    def _open_node_cross_refs_dialog(self, item):
        """v1.86:弹反查结果对话框"""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QGroupBox, QListWidget, QLabel,
            QPushButton, QHBoxLayout, QScrollArea, QWidget)
        from PyQt5.QtCore import Qt as _Qt
        refs = self._compute_node_cross_refs(item)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"🔍 反查:{item.text(0)}({item.text(1)})")
        dlg.resize(560, 600)
        outer = QVBoxLayout(dlg)

        # 顶部摘要
        chs = refs["chapters"]
        chs_str = ", ".join(str(c) for c in chs) if chs else "(暂无)"
        totals = (f"📊 关联统计:章节 {len(chs)} | 角色 {len(refs['characters'])} | "
                  f"伏笔 {len(refs['foreshadows'])} | 承诺 {len(refs['promises'])} | "
                  f"关系变 {len(refs['rel_changes'])} | 信息 {len(refs['infos'])}")
        head = QLabel(totals)
        head.setStyleSheet(
            "color:#fff;background:#3a6fc4;font-weight:bold;"
            "padding:6px 8px;border-radius:4px;font-size:11px;")
        head.setWordWrap(True)
        outer.addWidget(head)

        ch_label = QLabel(f"📖 关联章节:{chs_str}")
        ch_label.setStyleSheet("color:#444;padding:4px 8px;font-size:11px;")
        ch_label.setWordWrap(True)
        outer.addWidget(ch_label)

        # 可滚动内容区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setSpacing(8)

        def _add_group(title, rows, empty_hint):
            box = QGroupBox(title)
            box_lay = QVBoxLayout(box)
            if not rows:
                lbl = QLabel(empty_hint)
                lbl.setStyleSheet("color:#999;padding:8px;font-style:italic;")
                box_lay.addWidget(lbl)
            else:
                lw = QListWidget()
                for line in rows:
                    lw.addItem(line)
                lw.setMaximumHeight(min(180, 24 * len(rows) + 12))
                box_lay.addWidget(lw)
            body_lay.addWidget(box)

        # 角色
        char_rows = [
            f"  • {name}({role}) — 首次出场:第 {first} 章"
            for (r, name, role, first) in refs["characters"]
        ]
        _add_group(
            f"👤 角色({len(char_rows)})", char_rows,
            "(此节点关联章节里无新角色首次出场)")

        # 伏笔
        fore_rows = [
            f"  • [{('✅已收' if done == '是' else '⏳待收')}] "
            f"第{set_ch}章: 『{content[:30]}』"
            + (f" → 第{recover}章" if recover and recover != set_ch else "")
            for (r, content, set_ch, recover, done) in refs["foreshadows"]
        ]
        _add_group(
            f"📌 伏笔({len(fore_rows)})", fore_rows,
            "(无伏笔在此节点章节范围内埋设/回收)")

        # 承诺
        prom_rows = [
            f"  • [{kind}] {pair} — 『{content[:30]}』 "
            f"(第{set_ch}章埋 → 第{deadline}章截止)"
            for (r, kind, pair, content, set_ch, deadline) in refs["promises"]
        ]
        _add_group(
            f"⚡ 威胁承诺({len(prom_rows)})", prom_rows,
            "(无承诺在此节点章节范围内埋设/截止)")

        # 关系值变化
        rel_rows = [
            f"  • {a} ↔ {b}: {val} (第 {ch} 章)"
            for (r, a, b, val, ch) in refs["rel_changes"]
        ]
        _add_group(
            f"💞 关系值变动({len(rel_rows)})", rel_rows,
            "(无关系值在此节点章节范围内变化)")

        # 信息
        info_rows = [
            f"  • [{iid}/{src_type}] 第 {src_ch} 章: 『{content[:40]}』"
            for (r, iid, content, src_ch, src_type) in refs["infos"]
        ]
        _add_group(
            f"🔒 关键信息({len(info_rows)})", info_rows,
            "(无关键信息在此节点章节范围内首次确立)")

        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        # 底部关闭按钮
        bot = QHBoxLayout()
        bot.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        bot.addWidget(btn_close)
        outer.addLayout(bot)

        dlg.exec_()

    # ── v1.87 BUG-064:跨表关联可视化(系列收官)─────────────────
    # 用 QGraphicsView 画"剧情节点 ↔ 角色 ↔ 伏笔 ↔ 承诺 ↔ 关系 ↔ 信息"网络图
    # 节点用颜色区分类别,边用同章号关联(复用 v1.86 反查算法)
    # 布局用力导向算法(Fruchterman-Reingold 简化版,纯 Python 实现)
    # 不依赖 cytoscape.js / QtWebEngine,纯 PyQt5

    def _build_cross_graph_tab(self):
        from PyQt5.QtWidgets import (
            QGraphicsView, QGraphicsScene, QVBoxLayout, QHBoxLayout,
            QPushButton, QLabel, QSpinBox, QCheckBox)
        from PyQt5.QtGui import QPainter
        from PyQt5.QtCore import Qt

        w = QWidget()
        lay = QVBoxLayout(w)

        # 顶部控件栏
        ctl = QHBoxLayout()
        btn_refresh = QPushButton("🔄 重新生成布局")
        btn_refresh.setToolTip(
            "扫描所有库,重建关联图谱。\n"
            "如果改了剧情树 / 6 库数据,点这个刷新。")
        btn_refresh.clicked.connect(self._render_cross_graph)
        ctl.addWidget(btn_refresh)

        ctl.addWidget(QLabel("迭代次数:"))
        self.sb_graph_iters = QSpinBox()
        self.sb_graph_iters.setRange(10, 200)
        self.sb_graph_iters.setValue(50)
        self.sb_graph_iters.setToolTip(
            "力导向算法迭代次数。值大布局更稳定但更慢。50 一般够用。")
        ctl.addWidget(self.sb_graph_iters)

        ctl.addSpacing(20)
        ctl.addWidget(QLabel("显示:"))
        self.chk_show_chars = QCheckBox("👤 角色")
        self.chk_show_chars.setChecked(True)
        self.chk_show_chars.stateChanged.connect(
            lambda _: self._render_cross_graph())
        ctl.addWidget(self.chk_show_chars)

        self.chk_show_fore = QCheckBox("📌 伏笔")
        self.chk_show_fore.setChecked(True)
        self.chk_show_fore.stateChanged.connect(
            lambda _: self._render_cross_graph())
        ctl.addWidget(self.chk_show_fore)

        self.chk_show_promises = QCheckBox("⚡ 承诺")
        self.chk_show_promises.setChecked(True)
        self.chk_show_promises.stateChanged.connect(
            lambda _: self._render_cross_graph())
        ctl.addWidget(self.chk_show_promises)

        self.chk_show_infos = QCheckBox("🔒 信息")
        self.chk_show_infos.setChecked(True)
        self.chk_show_infos.stateChanged.connect(
            lambda _: self._render_cross_graph())
        ctl.addWidget(self.chk_show_infos)

        ctl.addStretch()
        lay.addLayout(ctl)

        # 主视图
        self.cross_graph_scene = QGraphicsScene()
        self.cross_graph_view = QGraphicsView(self.cross_graph_scene)
        self.cross_graph_view.setRenderHint(QPainter.Antialiasing)
        self.cross_graph_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.cross_graph_view.setTransformationAnchor(
            QGraphicsView.AnchorUnderMouse)
        # 滚轮缩放
        self.cross_graph_view.wheelEvent = self._cross_graph_wheel
        lay.addWidget(self.cross_graph_view, stretch=1)

        # 底部提示
        tip = QLabel(
            "💡 v1.87 跨表关联可视化(系列收官)— 一图看尽剧情节点/角色/伏笔/承诺/信息的关联。\n"
            "    边的含义:连同章号(剧情节点 chapter_links/ch_range + 其他库的章号字段)。\n"
            "    交互:鼠标拖拽节点 / 滚轮缩放视图 / 顶部勾选过滤类别。\n"
            "    布局:力导向算法(纯 Python 实现,无外部依赖)。空白图请点【🔄 重新生成布局】。")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.sub_tabs.addTab(w, "🕸 关联图谱")

    def _cross_graph_wheel(self, event):
        """滚轮缩放视图"""
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self.cross_graph_view.scale(factor, factor)

    def _collect_graph_data(self):
        """v1.87:收集图谱节点和边。
        返回 (nodes, edges):
          nodes = [{id, label, kind, color}]
            kind ∈ {plot, char, fore, promise, info}
          edges = [(node_id_a, node_id_b, label)]
            label 通常是章号
        """
        nodes = []
        edges = []
        # 配色(v1.87 调色板 — 与盘古风格协调)
        COLORS = {
            "plot":    "#3a6fc4",  # 蓝
            "char":    "#2da44e",  # 绿
            "fore":    "#dd7e1c",  # 橙
            "promise": "#cf222e",  # 红
            "info":    "#8250df",  # 紫
        }

        # 1. 剧情树节点(始终显示 — 是中心枢纽)
        plot_nodes_data = {}  # node_id → (ch_set, item)
        if hasattr(self, "tree_plot"):
            def walk(item):
                nid = item.data(0, 256) or ""  # Qt.UserRole = 256
                if nid and item.text(0).strip():
                    label = item.text(0)[:14]  # 截短防爆
                    nodes.append({
                        "id": f"plot:{nid}",
                        "label": label,
                        "kind": "plot",
                        "color": COLORS["plot"],
                    })
                    plot_nodes_data[f"plot:{nid}"] = (
                        self._node_chapter_set(item), item)
                for i in range(item.childCount()):
                    walk(item.child(i))
            for i in range(self.tree_plot.topLevelItemCount()):
                walk(self.tree_plot.topLevelItem(i))

        # 没剧情节点 — 没参考点,空图返回
        if not plot_nodes_data:
            return nodes, edges

        # 类别过滤(根据顶部 checkbox)
        show_chars = getattr(self, "chk_show_chars", None)
        show_chars = show_chars.isChecked() if show_chars else True
        show_fore = getattr(self, "chk_show_fore", None)
        show_fore = show_fore.isChecked() if show_fore else True
        show_promises = getattr(self, "chk_show_promises", None)
        show_promises = show_promises.isChecked() if show_promises else True
        show_infos = getattr(self, "chk_show_infos", None)
        show_infos = show_infos.isChecked() if show_infos else True

        # 2. 角色(只画跟剧情节点有关联的)
        if show_chars and hasattr(self, "tbl_chars"):
            for r in range(self.tbl_chars.rowCount()):
                name = (self.tbl_chars.item(r, 0).text()
                        if self.tbl_chars.item(r, 0) else "")
                first_s = (self.tbl_chars.item(r, 7).text()
                           if self.tbl_chars.item(r, 7) else "")
                if not name:
                    continue
                try:
                    first_ch = int(first_s)
                except ValueError:
                    continue
                # 找哪些剧情节点包含这个章号
                connected_plots = [
                    pid for pid, (chs, _it) in plot_nodes_data.items()
                    if first_ch in chs
                ]
                if connected_plots:
                    cid = f"char:{r}"
                    nodes.append({
                        "id": cid,
                        "label": name[:10],
                        "kind": "char",
                        "color": COLORS["char"],
                    })
                    for pid in connected_plots:
                        edges.append((pid, cid, f"第{first_ch}章"))

        # 3. 伏笔
        if show_fore and hasattr(self, "tbl_fore"):
            for r in range(self.tbl_fore.rowCount()):
                set_ch_s = (self.tbl_fore.item(r, 0).text()
                            if self.tbl_fore.item(r, 0) else "")
                content = (self.tbl_fore.item(r, 1).text()
                           if self.tbl_fore.item(r, 1) else "")
                recover_ch_s = (self.tbl_fore.item(r, 4).text()
                                if self.tbl_fore.item(r, 4) else "")
                if not content:
                    continue
                connected_plots = []
                for ch_s in (set_ch_s, recover_ch_s):
                    try:
                        ch = int(ch_s)
                    except ValueError:
                        continue
                    for pid, (chs, _it) in plot_nodes_data.items():
                        if ch in chs and pid not in connected_plots:
                            connected_plots.append(pid)
                if connected_plots:
                    fid = f"fore:{r}"
                    nodes.append({
                        "id": fid,
                        "label": content[:10],
                        "kind": "fore",
                        "color": COLORS["fore"],
                    })
                    # 用最早的章号作 label
                    label_ch = set_ch_s or recover_ch_s
                    for pid in connected_plots:
                        edges.append((pid, fid, f"第{label_ch}章"))

        # 4. 承诺
        if show_promises and hasattr(self, "tbl_promises"):
            for r in range(self.tbl_promises.rowCount()):
                set_ch_s = (self.tbl_promises.item(r, 0).text()
                            if self.tbl_promises.item(r, 0) else "")
                kind = (self.tbl_promises.item(r, 1).text()
                        if self.tbl_promises.item(r, 1) else "")
                content = (self.tbl_promises.item(r, 4).text()
                           if self.tbl_promises.item(r, 4) else "")
                deadline_s = (self.tbl_promises.item(r, 5).text()
                              if self.tbl_promises.item(r, 5) else "")
                if not content:
                    continue
                connected_plots = []
                for ch_s in (set_ch_s, deadline_s):
                    try:
                        ch = int(ch_s)
                    except ValueError:
                        continue
                    for pid, (chs, _it) in plot_nodes_data.items():
                        if ch in chs and pid not in connected_plots:
                            connected_plots.append(pid)
                if connected_plots:
                    pid_ = f"promise:{r}"
                    nodes.append({
                        "id": pid_,
                        "label": f"[{kind[:2]}]{content[:8]}",
                        "kind": "promise",
                        "color": COLORS["promise"],
                    })
                    label_ch = set_ch_s or deadline_s
                    for pid in connected_plots:
                        edges.append((pid, pid_, f"第{label_ch}章"))

        # 5. 信息
        if show_infos and hasattr(self, "tbl_infos"):
            for r in range(self.tbl_infos.rowCount()):
                iid = (self.tbl_infos.item(r, 0).text()
                       if self.tbl_infos.item(r, 0) else "")
                content = (self.tbl_infos.item(r, 1).text()
                           if self.tbl_infos.item(r, 1) else "")
                src_ch_s = (self.tbl_infos.item(r, 2).text()
                            if self.tbl_infos.item(r, 2) else "")
                if not iid:
                    continue
                try:
                    src_ch = int(src_ch_s)
                except ValueError:
                    continue
                connected_plots = [
                    pid for pid, (chs, _it) in plot_nodes_data.items()
                    if src_ch in chs
                ]
                if connected_plots:
                    nid_ = f"info:{r}"
                    label_show = iid if len(iid) <= 10 else iid[:10]
                    nodes.append({
                        "id": nid_,
                        "label": label_show,
                        "kind": "info",
                        "color": COLORS["info"],
                    })
                    for pid in connected_plots:
                        edges.append((pid, nid_, f"第{src_ch}章"))

        return nodes, edges

    def _force_directed_layout(self, nodes, edges, iters=80,
                                width=1200, height=900):
        """v1.87:简化版 Fruchterman-Reingold 力导向布局。
        节点初始随机位置,每轮迭代:
          - 所有节点对之间施加斥力(防重叠)
          - 边连接的节点对之间施加引力(往中心拉)
          - 节点位置受温度限制,逐轮降温(模拟退火)
        返回 {node_id: (x, y)}"""
        import random
        import math
        if not nodes:
            return {}
        n = len(nodes)
        # 理想边长 k(增大间距,节点多时更稀疏)
        area = width * height
        k = math.sqrt(area / max(n, 1)) * 1.2
        # 初始位置(中心附近随机散开,范围更大)
        random.seed(42)
        pos = {
            node["id"]: [
                width / 2 + random.uniform(-width / 4, width / 4),
                height / 2 + random.uniform(-height / 4, height / 4),
            ] for node in nodes
        }
        # 温度(逐轮降)
        t = width / 10.0

        node_ids = [n["id"] for n in nodes]
        edge_set = [(a, b) for (a, b, _label) in edges
                    if a in pos and b in pos]

        for _it in range(iters):
            # 1. 计算每个节点位移
            disp = {nid: [0.0, 0.0] for nid in node_ids}
            # 斥力(所有节点对)
            for i in range(n):
                for j in range(i + 1, n):
                    nid_a = node_ids[i]
                    nid_b = node_ids[j]
                    dx = pos[nid_a][0] - pos[nid_b][0]
                    dy = pos[nid_a][1] - pos[nid_b][1]
                    dist = math.sqrt(dx * dx + dy * dy) + 0.01
                    # 斥力 = k² / dist
                    force = (k * k) / dist
                    disp[nid_a][0] += (dx / dist) * force
                    disp[nid_a][1] += (dy / dist) * force
                    disp[nid_b][0] -= (dx / dist) * force
                    disp[nid_b][1] -= (dy / dist) * force
            # 引力(只对相连节点)
            for a, b in edge_set:
                dx = pos[a][0] - pos[b][0]
                dy = pos[a][1] - pos[b][1]
                dist = math.sqrt(dx * dx + dy * dy) + 0.01
                # 引力 = dist² / k
                force = (dist * dist) / k
                disp[a][0] -= (dx / dist) * force
                disp[a][1] -= (dy / dist) * force
                disp[b][0] += (dx / dist) * force
                disp[b][1] += (dy / dist) * force
            # 2. 应用位移(受温度限制)
            for nid in node_ids:
                dx, dy = disp[nid]
                dlen = math.sqrt(dx * dx + dy * dy) + 0.01
                # 位移最大不超过 t
                step = min(dlen, t)
                pos[nid][0] += (dx / dlen) * step
                pos[nid][1] += (dy / dlen) * step
                # 边界约束(不要跑出画布)
                pos[nid][0] = max(20, min(width - 20, pos[nid][0]))
                pos[nid][1] = max(20, min(height - 20, pos[nid][1]))
            # 降温
            t *= 0.95

        return {nid: tuple(pos[nid]) for nid in node_ids}

    def _render_cross_graph(self):
        """v1.87:扫数据 → 布局 → 在 QGraphicsScene 上渲染图谱"""
        from PyQt5.QtWidgets import (
            QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsSimpleTextItem,
            QGraphicsRectItem)
        from PyQt5.QtGui import QBrush, QPen, QColor, QFont
        from PyQt5.QtCore import Qt, QRectF

        self.cross_graph_scene.clear()
        nodes, edges = self._collect_graph_data()
        if not nodes:
            # 提示空数据
            hint = QGraphicsSimpleTextItem(
                "暂无数据可视化。\n请先在剧情树添加节点 + 在 6 库填数据,然后点【🔄 重新生成布局】。")
            hint.setBrush(QBrush(QColor("#999")))
            font = QFont()
            font.setPointSize(12)
            hint.setFont(font)
            hint.setPos(50, 50)
            self.cross_graph_scene.addItem(hint)
            return

        # 布局
        iters = self.sb_graph_iters.value() if hasattr(self, "sb_graph_iters") else 50
        pos = self._force_directed_layout(nodes, edges, iters=iters,
                                           width=900, height=700)

        # 先画边(在节点下)
        edge_pen = QPen(QColor("#aaa"))
        edge_pen.setWidth(1)
        edge_label_brush = QBrush(QColor("#666"))
        for a, b, label in edges:
            if a not in pos or b not in pos:
                continue
            x1, y1 = pos[a]
            x2, y2 = pos[b]
            line = QGraphicsLineItem(x1, y1, x2, y2)
            line.setPen(edge_pen)
            self.cross_graph_scene.addItem(line)
            # 边标签(章号)— 只在边足够长时显示,避免拥挤
            import math
            dlen = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            if dlen > 80 and label:
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2
                lbl = QGraphicsSimpleTextItem(label)
                lbl.setBrush(edge_label_brush)
                font = QFont()
                font.setPointSize(7)
                lbl.setFont(font)
                lbl.setPos(mid_x, mid_y)
                self.cross_graph_scene.addItem(lbl)

        # 再画节点
        text_brush = QBrush(QColor("#fff"))
        for node in nodes:
            nid = node["id"]
            if nid not in pos:
                continue
            x, y = pos[nid]
            r = 30
            ellipse = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
            ellipse.setBrush(QBrush(QColor(node["color"])))
            ellipse.setPen(QPen(QColor(node["color"]).darker(120), 2))
            ellipse.setFlag(QGraphicsEllipseItem.ItemIsMovable)
            ellipse.setToolTip(f"{node['kind']}: {node['label']}")
            self.cross_graph_scene.addItem(ellipse)
            # 标签
            text = QGraphicsSimpleTextItem(node["label"])
            text.setBrush(text_brush)
            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            text.setFont(font)
            # 居中
            text_rect = text.boundingRect()
            text.setPos(x - text_rect.width() / 2, y - text_rect.height() / 2)
            self.cross_graph_scene.addItem(text)

        # 调整视图范围
        self.cross_graph_view.setSceneRect(QRectF(0, 0, 900, 700))
        self.cross_graph_view.resetTransform()

    def _tree_to_list(self):
        """剧情树 → 扁平 list[{node_id, parent_id, name, kind, ch_range, note, chapter_links}]
        持久化与 AI 通信都用这个格式。v1.85 加 chapter_links 字段(写作模式回流)"""
        from PyQt5.QtCore import Qt
        out = []
        def walk(item, parent_id):
            nid = item.data(0, Qt.UserRole) or ""
            out.append({
                "node_id": str(nid),
                "parent_id": str(parent_id or ""),
                "name": item.text(0),
                "kind": item.text(1),
                "ch_range": item.text(2),
                "note": item.text(3),
                "chapter_links": (item.text(4) if item.columnCount() > 4 else ""),  # v1.85
            })
            for i in range(item.childCount()):
                walk(item.child(i), nid)
        for i in range(self.tree_plot.topLevelItemCount()):
            walk(self.tree_plot.topLevelItem(i), "")
        return out

    def _list_to_tree(self, records):
        """扁平 list → 剧情树(重建 QTreeWidget)
        records: list[{node_id, parent_id, name, kind, ch_range, note}]
        悬挂引用(parent_id 找不到)→ 当根节点处理"""
        from PyQt5.QtWidgets import QTreeWidgetItem
        from PyQt5.QtCore import Qt
        self.tree_plot.clear()
        if not records:
            return
        # 1. 建 id → item 索引(先全建出来)
        by_id = {}
        for rec in records:
            if not isinstance(rec, dict):
                continue
            nid = str(rec.get("node_id", "")).strip()
            if not nid:
                continue
            item = QTreeWidgetItem([
                str(rec.get("name", "")),
                str(rec.get("kind", "")),
                str(rec.get("ch_range", "")),
                str(rec.get("note", "")),
                str(rec.get("chapter_links", "")),  # v1.85
            ])
            item.setData(0, Qt.UserRole, nid)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            by_id[nid] = (item, str(rec.get("parent_id", "")).strip())
        # 2. 第二遍挂父子(parent_id 存在 → addChild;不存在 → top level)
        for nid, (item, pid) in by_id.items():
            if pid and pid in by_id:
                by_id[pid][0].addChild(item)
            else:
                # 悬挂引用或根节点
                self.tree_plot.addTopLevelItem(item)
        self.tree_plot.expandAll()

    # ── 6. 钩子编年子页 ────────────────────────────────────
    def _build_hooks_tab(self):
        from PyQt5.QtWidgets import QTableWidget
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        
        ops = QHBoxLayout()
        btn_add = QPushButton("➕ 手动添加")
        btn_add.setMaximumWidth(110)
        btn_add.clicked.connect(self._add_hook)
        ops.addWidget(btn_add)
        btn_del = QPushButton("🗑 删除选中")
        btn_del.setMaximumWidth(110)
        btn_del.clicked.connect(self._del_hook)
        ops.addWidget(btn_del)
        ops.addStretch()
        lay.addLayout(ops)
        
        self.tbl_hooks = QTableWidget(0, 4)
        self.tbl_hooks.setHorizontalHeaderLabels([
            "章节", "钩子类型", "强度", "内容(每章末尾留的悬念)"])
        self.tbl_hooks.horizontalHeader().setStretchLastSection(True)
        self.tbl_hooks.verticalHeader().setVisible(False)
        self.tbl_hooks.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_hooks.setColumnWidth(0, 60)
        self.tbl_hooks.setColumnWidth(1, 110)
        self.tbl_hooks.setColumnWidth(2, 70)
        lay.addWidget(self.tbl_hooks)
        
        tip = QLabel(
            "💡 每章生成完后,AI 输出的【断章钩子】自动入这里。\n"
            "    用途:全书钩子审计 — 看强度分布、避免连用同类型(对话没说完 + 对话没说完 = 重复)。\n"
            "    类型常见:对话没说完 / 人物出现 / 秘密暴露 / 倒计时 / 关键动作")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🎣 钩子编年")
    
    def _add_hook(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_hooks.rowCount()
        self.tbl_hooks.insertRow(r)
        defaults = [str(r+1), "对话没说完", "★★★", "新钩子"]
        for c, v in enumerate(defaults):
            self.tbl_hooks.setItem(r, c, QTableWidgetItem(v))
    
    def _del_hook(self):
        rows = sorted(set(idx.row() for idx in self.tbl_hooks.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_hooks.removeRow(r)

    # ── 7. 爽点编年子页 ────────────────────────────────────
    def _build_coolpts_tab(self):
        from PyQt5.QtWidgets import QTableWidget
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        
        ops = QHBoxLayout()
        btn_add = QPushButton("➕ 手动添加")
        btn_add.setMaximumWidth(110)
        btn_add.clicked.connect(self._add_coolpt)
        ops.addWidget(btn_add)
        btn_del = QPushButton("🗑 删除选中")
        btn_del.setMaximumWidth(110)
        btn_del.clicked.connect(self._del_coolpt)
        ops.addWidget(btn_del)
        ops.addStretch()
        lay.addLayout(ops)
        
        self.tbl_cool = QTableWidget(0, 3)
        self.tbl_cool.setHorizontalHeaderLabels([
            "章节", "爽点类型", "内容"])
        self.tbl_cool.horizontalHeader().setStretchLastSection(True)
        self.tbl_cool.verticalHeader().setVisible(False)
        self.tbl_cool.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tbl_cool.setColumnWidth(0, 60)
        self.tbl_cool.setColumnWidth(1, 110)
        lay.addWidget(self.tbl_cool)
        
        tip = QLabel(
            "💡 每章 AI 输出的【本章爽点】自动入这里。\n"
            "    用途:全书爽点审计 — 看类型分布,避免连续 3 章都是同种(全是打脸=审美疲劳)。\n"
            "    类型常见:打脸 / 反转 / 碾压 / 揭秘 / 救场 / 装逼 / 复仇")
        tip.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        
        self.sub_tabs.addTab(w, "🎯 爽点编年")
    
    def _add_coolpt(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        r = self.tbl_cool.rowCount()
        self.tbl_cool.insertRow(r)
        defaults = [str(r+1), "打脸", "新爽点"]
        for c, v in enumerate(defaults):
            self.tbl_cool.setItem(r, c, QTableWidgetItem(v))
    
    def _del_coolpt(self):
        rows = sorted(set(idx.row() for idx in self.tbl_cool.selectedIndexes()), reverse=True)
        for r in rows:
            self.tbl_cool.removeRow(r)

    # ── 9. 关系网子页(v1.70 新增,vis-network 可视化) ─────
    def _build_relation_graph_tab(self):
        """🕸️ 关系网 sub_tab:把 tbl_chars + tbl_relations 用力导向图渲染"""
        from PyQt5.QtWidgets import QPushButton  # 局部 import 保持风格一致
        w = QWidget()
        lay = QVBoxLayout(w)

        # 顶部工具栏:刷新按钮 + 说明
        top = QHBoxLayout()
        btn_refresh = QPushButton("🔄 刷新图谱")
        btn_refresh.setToolTip("从角色库 + 关系图谱表格重新拉数据渲染")
        btn_refresh.clicked.connect(self._refresh_relation_graph)
        top.addWidget(btn_refresh)
        top.addStretch()
        lbl_hint = QLabel(
            "提示:切换子页会自动刷新。鼠标拖节点 / 滚轮缩放 / 悬停看详情。")
        lbl_hint.setStyleSheet("color:#888;font-size:11px;")
        top.addWidget(lbl_hint)
        lay.addLayout(top)

        # 主图组件
        if RELATION_GRAPH_AVAILABLE:
            self.relation_graph_widget = relation_graph.RelationGraphWidget()
            # v1.72: 让画布自然撑满 sub_tab 剩余空间(v1.71 设的 maxHeight=520
            # 反而导致下方一片空白,用户反馈"改成满了")。只保留 minHeight 防小屏太挤。
            self.relation_graph_widget.setMinimumHeight(320)
            lay.addWidget(self.relation_graph_widget, stretch=1)  # stretch=1 吃满剩余空间
        else:
            # relation_graph.py 缺失(用户删了文件):兜底提示
            self.relation_graph_widget = None
            fallback = QLabel(
                "🕸️ 关系网模块未加载。\n"
                "请确认项目根目录有 relation_graph.py 文件。")
            fallback.setStyleSheet(
                "padding:24px;color:#999;font-size:13px;text-align:center;")
            fallback.setAlignment(Qt.AlignCenter)
            lay.addWidget(fallback)

        self.sub_tabs.addTab(w, "🕸️ 关系网")

    def _refresh_relation_graph(self):
        """把 tbl_chars + tbl_relations 转成行二维数组,送进 RelationGraphWidget"""
        if not RELATION_GRAPH_AVAILABLE or not getattr(self, "relation_graph_widget", None):
            return

        def _tbl_to_rows(tbl, ncol):
            out = []
            for r in range(tbl.rowCount()):
                row = []
                for c in range(ncol):
                    item = tbl.item(r, c)
                    row.append(item.text() if item else "")
                out.append(row)
            return out

        # v1.93 BUG-067:故意保持 8(不传 last_ch)— relation_graph.build_graph_data 接口
        # 注释明确按 8 列设计,加 last_ch 也会被它在 row[0:8] 截掉,传 8 更干净。
        chars_rows = _tbl_to_rows(self.tbl_chars, 8)
        relations_rows = _tbl_to_rows(self.tbl_relations, 4)
        try:
            self.relation_graph_widget.set_data(chars_rows, relations_rows)
        except Exception as e:
            print(f"[relation_graph] set_data failed: {e}")

    def _on_sub_tab_changed(self, idx):
        """切到 🕸️ 关系网 子页时自动刷新最新数据"""
        try:
            tab_text = self.sub_tabs.tabText(idx)
        except Exception:
            return
        if "关系网" in tab_text:
            self._refresh_relation_graph()

    # ── 数据序列化(保存/加载到项目JSON) ────────────────────
    def serialize(self):
        """导出全部数据为 dict, 用于持久化"""
        def tbl_to_list(tbl, ncol):
            out = []
            for r in range(tbl.rowCount()):
                row = []
                for c in range(ncol):
                    item = tbl.item(r, c)
                    row.append(item.text() if item else "")
                out.append(row)
            return out
        
        return {
            "characters": tbl_to_list(self.tbl_chars, 9),  # v1.93 BUG-067:加 last_ch 列
            "relations":  tbl_to_list(self.tbl_relations, 4),
            "timeline":   tbl_to_list(self.tbl_timeline, 3),
            "items":      tbl_to_list(self.tbl_items, 5),
            "power_levels": tbl_to_list(self.tbl_power, 4),
            "foreshadows":tbl_to_list(self.tbl_fore, 5),
            "promises":   tbl_to_list(self.tbl_promises, 7),  # v1.77
            "arcs":          tbl_to_list(self.tbl_arcs, 3),         # v1.78
            "relations_value": tbl_to_list(self.tbl_rel_values, 4), # v1.78
            "goals":         tbl_to_list(self.tbl_goals, 4),        # v1.78
            "infos":         tbl_to_list(self.tbl_infos, 4),        # v1.79
            "known_by":      tbl_to_list(self.tbl_known_by, 3),     # v1.79
            # v1.80 剧情树:直接序列化为扁平 list[dict],不走 tbl_to_list(因为是树)
            # v1.85:加第 7 字段 chapter_links(已写章节回流)
            "plot_branches":
                [[r["node_id"], r["parent_id"], r["name"], r["kind"],
                  r["ch_range"], r["note"], r.get("chapter_links", "")]
                 for r in self._tree_to_list()] if hasattr(self, "tree_plot") else [],
            "hooks":      tbl_to_list(self.tbl_hooks, 4),  # 新增
            "cool_pts":   tbl_to_list(self.tbl_cool, 3),   # 新增
            "hero_state": {
                "age":      self.hero_age.text(),
                "realm":    self.hero_realm.text(),
                "location": self.hero_location.text(),
                "faction":  self.hero_faction.text(),
                "mood":     self.hero_mood.text(),
            },
            "auto_inject": self.chk_inject.isChecked(),
            # v1.84:POV 模式持久化(全知 / 主角 POV / 角色 POV + 角色名)
            "pov_mode": (self.cb_pov_mode.currentText()
                          if hasattr(self, "cb_pov_mode") else "全知视角"),
            "pov_character": (self.le_pov_character.text()
                              if hasattr(self, "le_pov_character") else ""),
        }
    
    def load(self, data):
        """从 dict 加载数据。
        
        兼容两种条目格式:
          (a) list-of-list: [[col0, col1, ...], ...] — 老格式,导出/存档用
          (b) list-of-dict: [{字段名: 值}, ...]      — AI 抽取 / 外部工具(如 DeepSeek)输出
        
        外部 JSON 顶层 key `events` 自动归并到 `timeline`(同义)。
        """
        from PyQt5.QtWidgets import QTableWidgetItem
        if not data:
            return
        
        # ── dict → row 字段映射(列序对齐 _build_*_tab 的 setHorizontalHeaderLabels)──
        DICT_KEY_MAPS = {
            "characters":  ["name", "role", "appearance", "personality",
                            "mark", "ability", "state", "first_ch", "last_ch"],  # v1.93 BUG-067:+last_ch
            "relations":   ["a", "type", "b", "note"],
            "timeline":    ["ch", "event", "state_change"],
            "items":       ["name", "type", "owner", "source_ch", "ability"],
            "power_levels":["realm", "level", "power", "note"],
            "foreshadows": ["ch", "content", "plan_pay_at", "paid", "pay_ch"],
            "promises":    ["ch", "kind", "from", "to", "content", "deadline", "fulfilled"],
            "arcs":            ["name", "progress", "phase"],
            "relations_value": ["a", "b", "value", "ch"],
            "goals":           ["name", "priority", "status", "set_ch"],
            "infos":           ["id", "content", "source_ch", "source_type"],
            "known_by":        ["info_id", "character", "via"],
            "plot_branches":   ["node_id", "parent_id", "name", "kind", "ch_range", "note", "chapter_links"],
            "hooks":       ["ch", "hook", "type", "resolved"],
            "cool_pts":    ["ch", "scene", "score"],
        }
        
        def normalize(entries, schema_key):
            """把任意 entries 标准化成 list-of-list。dict 项按字段名映射,list 项原样。"""
            if not entries:
                return []
            keys = DICT_KEY_MAPS.get(schema_key, [])
            out = []
            for e in entries:
                if isinstance(e, dict):
                    out.append([str(e.get(k, "")) for k in keys])
                elif isinstance(e, (list, tuple)):
                    out.append(list(e))
                else:
                    # 单值字符串等,丢一列
                    out.append([str(e)])
            return out
        
        def list_to_tbl(tbl, rows, ncol):
            tbl.setRowCount(0)
            for row in rows:
                r = tbl.rowCount()
                tbl.insertRow(r)
                for c in range(ncol):
                    val = row[c] if c < len(row) else ""
                    tbl.setItem(r, c, QTableWidgetItem(str(val)))
        
        # timeline 容忍 events 同义
        timeline_raw = data.get("timeline")
        if not timeline_raw:
            timeline_raw = data.get("events", [])
        
        # v1.93 BUG-067:tbl_chars 列数 9(原 8 + last_ch)。
        # normalize 已按 DICT_KEY_MAPS_LOCAL["characters"] 的 9 字段转出 9 元素 list。
        list_to_tbl(self.tbl_chars,     normalize(data.get("characters", []), "characters"), 9)
        list_to_tbl(self.tbl_relations, normalize(data.get("relations", []), "relations"), 4)
        list_to_tbl(self.tbl_timeline,  normalize(timeline_raw, "timeline"), 3)
        list_to_tbl(self.tbl_items,     normalize(data.get("items", []), "items"), 5)
        list_to_tbl(self.tbl_power,     normalize(data.get("power_levels", []), "power_levels"), 4)
        list_to_tbl(self.tbl_fore,      normalize(data.get("foreshadows", []), "foreshadows"), 5)
        list_to_tbl(self.tbl_promises,  normalize(data.get("promises", []), "promises"), 7)  # v1.77
        list_to_tbl(self.tbl_arcs,       normalize(data.get("arcs", []), "arcs"), 3)              # v1.78
        list_to_tbl(self.tbl_rel_values, normalize(data.get("relations_value", []), "relations_value"), 4)  # v1.78
        list_to_tbl(self.tbl_goals,      normalize(data.get("goals", []), "goals"), 4)            # v1.78
        list_to_tbl(self.tbl_infos,      normalize(data.get("infos", []), "infos"), 4)            # v1.79
        list_to_tbl(self.tbl_known_by,   normalize(data.get("known_by", []), "known_by"), 3)      # v1.79
        # v1.80:剧情树 — normalize 后是 list-of-list,转回 dict 再喂给 _list_to_tree
        if hasattr(self, "tree_plot"):
            plot_keys = DICT_KEY_MAPS.get("plot_branches", [])
            plot_norm = normalize(data.get("plot_branches", []), "plot_branches")
            plot_dicts = []
            for row in plot_norm:
                d = {}
                for i, k in enumerate(plot_keys):
                    d[k] = row[i] if i < len(row) else ""
                plot_dicts.append(d)
            self._list_to_tree(plot_dicts)
        list_to_tbl(self.tbl_hooks,     normalize(data.get("hooks", []), "hooks"), 4)
        list_to_tbl(self.tbl_cool,      normalize(data.get("cool_pts", []), "cool_pts"), 3)
        
        hs = data.get("hero_state", {})
        self.hero_age.setText(hs.get("age", "18"))
        self.hero_realm.setText(hs.get("realm", "练气期一层"))
        self.hero_location.setText(hs.get("location", ""))
        self.hero_faction.setText(hs.get("faction", ""))
        self.hero_mood.setText(hs.get("mood", "平静"))
        
        self.chk_inject.setChecked(data.get("auto_inject", True))
        # v1.84:POV 模式加载
        if hasattr(self, "cb_pov_mode"):
            pov_mode = data.get("pov_mode", "全知视角")
            if pov_mode in ("全知视角", "主角 POV", "角色 POV"):
                self.cb_pov_mode.setCurrentText(pov_mode)
        if hasattr(self, "le_pov_character"):
            self.le_pov_character.setText(data.get("pov_character", ""))
    
    def merge_dicts(self, data):
        """把外部 JSON(list-of-dict 格式)合并进当前表(去重,不清空)。
        
        返回 dict: {"ch": N, "rel": N, "it": N, "ev": N, "fo": N, "pw": N} —— 各类新增条目数。
        与 MainWindow._merge_into_charlib 等价,供 CharacterLib 自己的导入路径调用。
        v1.74:加 power_levels(战力体系)合并。
        """
        from PyQt5.QtWidgets import QTableWidgetItem
        added = {"ch": 0, "rel": 0, "it": 0, "ev": 0, "fo": 0, "pw": 0, "pr": 0,
                 "arc": 0, "rv": 0, "gl": 0,                # v1.78
                 "info": 0, "kb": 0,                         # v1.79
                 "pt": 0}                                    # v1.80 plot tree
        if not data:
            return added
        
        def existing_names(tbl, col=0):
            return set((tbl.item(r, col).text() if tbl.item(r, col) else "")
                       for r in range(tbl.rowCount()))
        
        def _as_dict_list(entries, schema_key):
            """容忍 list-of-list 也喂进来。"""
            DICT_KEY_MAPS_LOCAL = {
                "characters":  ["name", "role", "appearance", "personality",
                                "mark", "ability", "state", "first_ch", "last_ch"],  # v1.93 BUG-067:+last_ch
                "relations":   ["a", "type", "b", "note"],
                "timeline":    ["ch", "event", "state_change"],
                "items":       ["name", "type", "owner", "source_ch", "ability"],
                "foreshadows": ["ch", "content", "plan_pay_at", "paid", "pay_ch"],
                "power_levels":["realm", "level", "power", "note"],
                "promises":    ["ch", "kind", "from", "to", "content", "deadline", "fulfilled"],
                "arcs":            ["name", "progress", "phase"],            # v1.78
                "relations_value": ["a", "b", "value", "ch"],                # v1.78
                "goals":           ["name", "priority", "status", "set_ch"], # v1.78
                "infos":           ["id", "content", "source_ch", "source_type"],   # v1.79
                "known_by":        ["info_id", "character", "via"],                 # v1.79
                "info_disclosures": ["info_id", "to", "via"],                       # v1.79(同 known_by 但来自 disclosure 抽取)
                "plot_branches":    ["node_id", "parent_id", "name", "kind", "ch_range", "note", "chapter_links"],  # v1.80 / v1.85 加 chapter_links
            }
            keys = DICT_KEY_MAPS_LOCAL.get(schema_key, [])
            out = []
            for e in (entries or []):
                if isinstance(e, dict):
                    out.append(e)
                elif isinstance(e, (list, tuple)):
                    out.append({keys[i]: e[i] for i in range(min(len(keys), len(e)))})
            return out
        
        # 角色
        ex_chars = existing_names(self.tbl_chars)
        for c in _as_dict_list(data.get("characters"), "characters"):
            name = str(c.get("name", "")).strip()
            if not name or name in ex_chars:
                continue
            row = self.tbl_chars.rowCount()
            self.tbl_chars.insertRow(row)
            # v1.93 BUG-067:9 列(末尾加 last_ch,AI 不填 → "" 兜底)
            vals = [name, c.get("role", "配角"), c.get("appearance", ""),
                    c.get("personality", ""), c.get("mark", ""),
                    c.get("ability", ""), c.get("state", ""),
                    str(c.get("first_ch", "")),
                    str(c.get("last_ch", ""))]
            for col, v in enumerate(vals):
                self.tbl_chars.setItem(row, col, QTableWidgetItem(str(v)))
            added["ch"] += 1
            ex_chars.add(name)
        
        # 关系
        ex_rels = set()
        for r in range(self.tbl_relations.rowCount()):
            a = self.tbl_relations.item(r, 0).text() if self.tbl_relations.item(r, 0) else ""
            t = self.tbl_relations.item(r, 1).text() if self.tbl_relations.item(r, 1) else ""
            b = self.tbl_relations.item(r, 2).text() if self.tbl_relations.item(r, 2) else ""
            ex_rels.add(f"{a}|{t}|{b}")
        for rel in _as_dict_list(data.get("relations"), "relations"):
            a = str(rel.get("a", "")).strip()
            t = str(rel.get("type", "")).strip()
            b = str(rel.get("b", "")).strip()
            if not (a and t and b):
                continue
            k = f"{a}|{t}|{b}"
            if k in ex_rels:
                continue
            row = self.tbl_relations.rowCount()
            self.tbl_relations.insertRow(row)
            for col, v in enumerate([a, t, b, rel.get("note", "")]):
                self.tbl_relations.setItem(row, col, QTableWidgetItem(str(v)))
            added["rel"] += 1
            ex_rels.add(k)
        
        # 物品
        ex_items = existing_names(self.tbl_items)
        for it in _as_dict_list(data.get("items"), "items"):
            name = str(it.get("name", "")).strip()
            if not name or name in ex_items:
                continue
            row = self.tbl_items.rowCount()
            self.tbl_items.insertRow(row)
            vals = [name, it.get("type", "法器"), it.get("owner", ""),
                    str(it.get("source_ch", "")), it.get("ability", "")]
            for col, v in enumerate(vals):
                self.tbl_items.setItem(row, col, QTableWidgetItem(str(v)))
            added["it"] += 1
            ex_items.add(name)
        
        # 事件 / timeline(容忍两种 key)
        ev_raw = data.get("events") or data.get("timeline")
        ex_evs = set()
        for r in range(self.tbl_timeline.rowCount()):
            ch = self.tbl_timeline.item(r, 0).text() if self.tbl_timeline.item(r, 0) else ""
            ev = self.tbl_timeline.item(r, 1).text() if self.tbl_timeline.item(r, 1) else ""
            ex_evs.add(f"{ch}|{ev[:20]}")
        for ev in _as_dict_list(ev_raw, "timeline"):
            ch = str(ev.get("ch", ""))
            evt = str(ev.get("event", "")).strip()
            if not evt:
                continue
            k = f"{ch}|{evt[:20]}"
            if k in ex_evs:
                continue
            row = self.tbl_timeline.rowCount()
            self.tbl_timeline.insertRow(row)
            for col, v in enumerate([ch, evt, ev.get("state_change", "")]):
                self.tbl_timeline.setItem(row, col, QTableWidgetItem(str(v)))
            added["ev"] += 1
            ex_evs.add(k)
        
        # 伏笔
        ex_fos = set()
        for r in range(self.tbl_fore.rowCount()):
            ch = self.tbl_fore.item(r, 0).text() if self.tbl_fore.item(r, 0) else ""
            ct = self.tbl_fore.item(r, 1).text() if self.tbl_fore.item(r, 1) else ""
            ex_fos.add(f"{ch}|{ct[:30]}")
        for fo in _as_dict_list(data.get("foreshadows"), "foreshadows"):
            ch = str(fo.get("ch", ""))
            ct = str(fo.get("content", "")).strip()
            if not ct:
                continue
            k = f"{ch}|{ct[:30]}"
            if k in ex_fos:
                continue
            row = self.tbl_fore.rowCount()
            self.tbl_fore.insertRow(row)
            vals = [ch, ct, str(fo.get("plan_pay_at", "0")), "否", ""]
            for col, v in enumerate(vals):
                self.tbl_fore.setItem(row, col, QTableWidgetItem(str(v)))
            added["fo"] += 1
            ex_fos.add(k)
        
        # v1.74:战力体系 power_levels(去重 key=realm+level)
        ex_pws = set()
        for r in range(self.tbl_power.rowCount()):
            rl = self.tbl_power.item(r, 0).text() if self.tbl_power.item(r, 0) else ""
            lv = self.tbl_power.item(r, 1).text() if self.tbl_power.item(r, 1) else ""
            ex_pws.add(f"{rl}|{lv}")
        for pw in _as_dict_list(data.get("power_levels"), "power_levels"):
            rl = str(pw.get("realm", "")).strip()
            lv = str(pw.get("level", "")).strip()
            if not rl:
                continue
            k = f"{rl}|{lv}"
            if k in ex_pws:
                continue
            row = self.tbl_power.rowCount()
            self.tbl_power.insertRow(row)
            vals = [rl, lv, pw.get("power", ""), pw.get("note", "")]
            for col, v in enumerate(vals):
                self.tbl_power.setItem(row, col, QTableWidgetItem(str(v)))
            added["pw"] += 1
            ex_pws.add(k)
        
        # v1.77:威胁承诺 promises(去重 key=ch + content[:30] + from + to)
        if not hasattr(self, "tbl_promises"):
            return added
        ex_prs = set()
        for r in range(self.tbl_promises.rowCount()):
            ch = self.tbl_promises.item(r, 0).text() if self.tbl_promises.item(r, 0) else ""
            fr = self.tbl_promises.item(r, 2).text() if self.tbl_promises.item(r, 2) else ""
            to = self.tbl_promises.item(r, 3).text() if self.tbl_promises.item(r, 3) else ""
            ct = self.tbl_promises.item(r, 4).text() if self.tbl_promises.item(r, 4) else ""
            ex_prs.add(f"{ch}|{fr}|{to}|{ct[:30]}")
        for pr in _as_dict_list(data.get("promises"), "promises"):
            ch = str(pr.get("ch", "")).strip()
            kind = str(pr.get("kind", "承诺")).strip() or "承诺"
            fr = str(pr.get("from", "")).strip()
            to = str(pr.get("to", "")).strip()
            ct = str(pr.get("content", "")).strip()
            if not ct:
                continue
            k = f"{ch}|{fr}|{to}|{ct[:30]}"
            if k in ex_prs:
                continue
            row = self.tbl_promises.rowCount()
            self.tbl_promises.insertRow(row)
            # 兼容 fulfilled 字段(导入 JSON 可能用 paid/done 等),默认"否"
            fulfilled = str(pr.get("fulfilled", pr.get("paid", "否"))) or "否"
            vals = [ch, kind, fr, to, ct,
                    str(pr.get("deadline", "0")), fulfilled]
            for col, v in enumerate(vals):
                self.tbl_promises.setItem(row, col, QTableWidgetItem(str(v)))
            added["pr"] = added.get("pr", 0) + 1
            ex_prs.add(k)

        # v1.78:故事弧线 arcs(去重 key=name;有重复时 progress 取较大值)
        if hasattr(self, "tbl_arcs"):
            ex_arcs = {}  # name -> row idx
            for r in range(self.tbl_arcs.rowCount()):
                nm = self.tbl_arcs.item(r, 0).text() if self.tbl_arcs.item(r, 0) else ""
                if nm:
                    ex_arcs[nm] = r
            for arc in _as_dict_list(data.get("arcs"), "arcs"):
                nm = str(arc.get("name", "")).strip()
                if not nm:
                    continue
                try:
                    new_prog = max(0, min(100, int(arc.get("progress", 0) or 0)))
                except (TypeError, ValueError):
                    new_prog = 0
                phase = str(arc.get("phase", "开端")).strip() or "开端"
                if nm in ex_arcs:
                    # 取较大 progress;phase 用新值(更新到位)
                    r = ex_arcs[nm]
                    try:
                        old_prog = int(self.tbl_arcs.item(r, 1).text()
                                       if self.tbl_arcs.item(r, 1) else "0")
                    except (TypeError, ValueError):
                        old_prog = 0
                    if new_prog > old_prog:
                        self.tbl_arcs.setItem(
                            r, 1, QTableWidgetItem(str(new_prog)))
                    self.tbl_arcs.setItem(r, 2, QTableWidgetItem(phase))
                    continue
                row = self.tbl_arcs.rowCount()
                self.tbl_arcs.insertRow(row)
                for col, v in enumerate([nm, str(new_prog), phase]):
                    self.tbl_arcs.setItem(row, col, QTableWidgetItem(v))
                added["arc"] = added.get("arc", 0) + 1
                ex_arcs[nm] = row

        # v1.78:关系值矩阵 relations_value(去重 key=a|b;有重复时 value 用新值 + 更新 ch)
        if hasattr(self, "tbl_rel_values"):
            ex_rvs = {}  # "a|b" -> row idx
            for r in range(self.tbl_rel_values.rowCount()):
                a = self.tbl_rel_values.item(r, 0).text() if self.tbl_rel_values.item(r, 0) else ""
                b = self.tbl_rel_values.item(r, 1).text() if self.tbl_rel_values.item(r, 1) else ""
                if a and b:
                    ex_rvs[f"{a}|{b}"] = r
            for rv in _as_dict_list(data.get("relations_value"), "relations_value"):
                a = str(rv.get("a", "")).strip()
                b = str(rv.get("b", "")).strip()
                if not (a and b):
                    continue
                try:
                    val = max(-100, min(100, int(rv.get("value", 0) or 0)))
                except (TypeError, ValueError):
                    val = 0
                ch = str(rv.get("ch", "1")).strip() or "1"
                k = f"{a}|{b}"
                if k in ex_rvs:
                    r = ex_rvs[k]
                    self.tbl_rel_values.setItem(r, 2, QTableWidgetItem(str(val)))
                    self.tbl_rel_values.setItem(r, 3, QTableWidgetItem(ch))
                    continue
                row = self.tbl_rel_values.rowCount()
                self.tbl_rel_values.insertRow(row)
                for col, v in enumerate([a, b, str(val), ch]):
                    self.tbl_rel_values.setItem(row, col, QTableWidgetItem(v))
                added["rv"] = added.get("rv", 0) + 1
                ex_rvs[k] = row

        # v1.78:当前目标 goals(去重 key=name;status 用新值,priority 仅在新建时填)
        if hasattr(self, "tbl_goals"):
            ex_gls = {}
            for r in range(self.tbl_goals.rowCount()):
                nm = self.tbl_goals.item(r, 0).text() if self.tbl_goals.item(r, 0) else ""
                if nm:
                    ex_gls[nm] = r
            for gl in _as_dict_list(data.get("goals"), "goals"):
                nm = str(gl.get("name", "")).strip()
                if not nm:
                    continue
                priority = str(gl.get("priority", "主线")).strip() or "主线"
                status = str(gl.get("status", "进行中")).strip() or "进行中"
                set_ch = str(gl.get("set_ch", "1")).strip() or "1"
                if nm in ex_gls:
                    # 已存在 → 只更新状态(进行中→已达成/已放弃)
                    r = ex_gls[nm]
                    self.tbl_goals.setItem(r, 2, QTableWidgetItem(status))
                    continue
                row = self.tbl_goals.rowCount()
                self.tbl_goals.insertRow(row)
                for col, v in enumerate([nm, priority, status, set_ch]):
                    self.tbl_goals.setItem(row, col, QTableWidgetItem(v))
                added["gl"] = added.get("gl", 0) + 1
                ex_gls[nm] = row

        # v1.79:关键信息条目 infos(去重 key=content;id 自动续号 INFO-XXX)
        # 关键设计:AI 可能用占位符 id(INFO-XXX/INFO-001 重复),系统自动重编号并维护 id_remap
        id_remap = {}  # AI 给的原始 id → 入库后的最终 id(给 info_disclosures 用)
        if hasattr(self, "tbl_infos"):
            # 收集已有 content → row idx 和已用过的 id
            ex_infos_by_content = {}
            used_ids = set()
            for r in range(self.tbl_infos.rowCount()):
                ct_it = self.tbl_infos.item(r, 1)
                id_it = self.tbl_infos.item(r, 0)
                if ct_it and ct_it.text().strip():
                    ex_infos_by_content[ct_it.text().strip()] = r
                if id_it and id_it.text().strip():
                    used_ids.add(id_it.text().strip())

            def _next_info_id():
                n = 1
                while f"INFO-{n:03d}" in used_ids:
                    n += 1
                used_ids.add(f"INFO-{n:03d}")
                return f"INFO-{n:03d}"

            for info in _as_dict_list(data.get("infos"), "infos"):
                content = str(info.get("content", "")).strip()
                if not content:
                    continue
                raw_id = str(info.get("id", "")).strip()
                if content in ex_infos_by_content:
                    # 内容已存在 → 复用现有 id,只把映射记好
                    r = ex_infos_by_content[content]
                    existing_id = self.tbl_infos.item(r, 0).text() if self.tbl_infos.item(r, 0) else ""
                    if raw_id:
                        id_remap[raw_id] = existing_id
                    continue
                # 新内容 → 分配新 id
                final_id = raw_id if (raw_id and raw_id not in used_ids
                                       and re.match(r"^INFO-\d{3}$", raw_id)) else _next_info_id()
                if raw_id and final_id != raw_id:
                    id_remap[raw_id] = final_id
                used_ids.add(final_id)
                src_ch = str(info.get("source_ch", "1")).strip() or "1"
                src_type = str(info.get("source_type", "设定")).strip() or "设定"
                row = self.tbl_infos.rowCount()
                self.tbl_infos.insertRow(row)
                for col, v in enumerate([final_id, content, src_ch, src_type]):
                    self.tbl_infos.setItem(row, col, QTableWidgetItem(v))
                added["info"] = added.get("info", 0) + 1
                ex_infos_by_content[content] = row

        # v1.79:知情人 known_by 合并 — 同时接受 known_by 字段和 info_disclosures 字段
        # info_disclosures 是 world_extract 输出的"披露事件",字段 (info_id, to, via),
        # known_by 是直接的"知情人记录",字段 (info_id, character, via);两者语义相同,合并入同一个表
        if hasattr(self, "tbl_known_by"):
            ex_kbs = set()  # "info_id|character"
            for r in range(self.tbl_known_by.rowCount()):
                info_it = self.tbl_known_by.item(r, 0)
                ch_it = self.tbl_known_by.item(r, 1)
                if info_it and ch_it and info_it.text().strip() and ch_it.text().strip():
                    ex_kbs.add(f"{info_it.text().strip()}|{ch_it.text().strip()}")

            # 收集两种来源
            kb_records = []
            for kb in _as_dict_list(data.get("known_by"), "known_by"):
                kb_records.append({
                    "info_id": str(kb.get("info_id", "")).strip(),
                    "character": str(kb.get("character", "")).strip(),
                    "via": str(kb.get("via", "")).strip(),
                })
            for dc in _as_dict_list(data.get("info_disclosures"), "info_disclosures"):
                kb_records.append({
                    "info_id": str(dc.get("info_id", "")).strip(),
                    "character": str(dc.get("to", "") or dc.get("character", "")).strip(),
                    "via": str(dc.get("via", "")).strip(),
                })

            for rec in kb_records:
                # id_remap 应用(AI 给的占位符 id → 真实 id)
                info_id = id_remap.get(rec["info_id"], rec["info_id"])
                character = rec["character"]
                via = rec["via"]
                if not (info_id and character):
                    continue
                # 守:info_id 必须在 tbl_infos 里存在,否则不要悬挂引用
                if hasattr(self, "tbl_infos"):
                    valid_ids = set()
                    for r in range(self.tbl_infos.rowCount()):
                        it = self.tbl_infos.item(r, 0)
                        if it and it.text().strip():
                            valid_ids.add(it.text().strip())
                    if info_id not in valid_ids:
                        continue
                k = f"{info_id}|{character}"
                if k in ex_kbs:
                    continue
                row = self.tbl_known_by.rowCount()
                self.tbl_known_by.insertRow(row)
                for col, v in enumerate([info_id, character, via or "未知途径"]):
                    self.tbl_known_by.setItem(row, col, QTableWidgetItem(v))
                added["kb"] = added.get("kb", 0) + 1
                ex_kbs.add(k)

        # v1.80:剧情树 plot_branches(扁平 list 合并)
        # 去重 key:(name, kind, parent_name) — 因为 AI 给的 node_id 是占位符不可靠
        # parent_id remap:AI 给的 N-XXX → 真实 N-YYY 重映射,用 node_remap 表
        if hasattr(self, "tree_plot"):
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QTreeWidgetItem
            # 1. 扫描现有树,建索引:
            #    by_key[(name, kind, parent_node_id)] = node_id
            #    used_ids = {N-001, N-002, ...}
            existing_items = {}  # node_id → QTreeWidgetItem
            by_key = {}  # (name, kind, parent_node_id) → node_id
            used_ids = set()

            def _scan(item, parent_id):
                nid = item.data(0, Qt.UserRole)
                nid = str(nid) if nid else ""
                if nid:
                    existing_items[nid] = item
                    used_ids.add(nid)
                key = (item.text(0), item.text(1), parent_id)
                by_key[key] = nid
                for i in range(item.childCount()):
                    _scan(item.child(i), nid)
            for i in range(self.tree_plot.topLevelItemCount()):
                _scan(self.tree_plot.topLevelItem(i), "")

            def _next_node_id():
                n = 1
                while f"N-{n:03d}" in used_ids:
                    n += 1
                new_id = f"N-{n:03d}"
                used_ids.add(new_id)
                return new_id

            # 2. AI 给的 list:node_id 是占位符,parent_id 也可能是占位符
            #    需要先按 dict 顺序遍历(假设 AI 顺序给的 — 父先于子)
            #    用 node_remap[raw_id] = final_id
            node_remap = {}
            records = _as_dict_list(data.get("plot_branches"), "plot_branches")
            for rec in records:
                name = str(rec.get("name", "")).strip()
                kind = str(rec.get("kind", "故事")).strip() or "故事"
                if not name:
                    continue
                raw_id = str(rec.get("node_id", "")).strip()
                raw_parent = str(rec.get("parent_id", "")).strip()
                # parent_id 重映射:① 先看是不是 AI 给的占位符(在 node_remap)
                #                  ② 再看是不是已有树里的 id(直接用)
                #                  ③ 都不是 → 当根节点处理(parent_id="")
                if raw_parent:
                    if raw_parent in node_remap:
                        parent_id = node_remap[raw_parent]
                    elif raw_parent in existing_items:
                        parent_id = raw_parent
                    else:
                        parent_id = ""  # 悬挂引用 → 当根
                else:
                    parent_id = ""
                # 去重 key:(name, kind, parent_id)
                dedupe_key = (name, kind, parent_id)
                if dedupe_key in by_key:
                    # 已存在 → 记 remap(给后续子节点用),不新建
                    existing_id = by_key[dedupe_key]
                    if raw_id:
                        node_remap[raw_id] = existing_id
                    # v1.85:同节点的 chapter_links 合并去重(避免覆盖已有)
                    new_ch_links = str(rec.get("chapter_links", "")).strip()
                    if new_ch_links and existing_id in existing_items:
                        existing_item = existing_items[existing_id]
                        cur = (existing_item.text(4) or "").strip()
                        merged = set(c.strip() for c in cur.split(",") if c.strip())
                        for c in new_ch_links.split(","):
                            c = c.strip()
                            if c:
                                merged.add(c)
                        try:
                            sorted_merged = sorted(merged, key=lambda x: int(x))
                        except ValueError:
                            sorted_merged = sorted(merged)
                        existing_item.setText(4, ", ".join(sorted_merged))
                    continue
                # 新节点 — 分配 final_id
                if (raw_id and raw_id not in used_ids
                        and re.match(r"^N-\d{3}$", raw_id)):
                    final_id = raw_id
                    used_ids.add(final_id)
                else:
                    final_id = _next_node_id()
                if raw_id and final_id != raw_id:
                    node_remap[raw_id] = final_id
                # 建 item(v1.85:第 5 列 chapter_links)
                ch_range = str(rec.get("ch_range", "")).strip()
                note = str(rec.get("note", "")).strip()
                chapter_links = str(rec.get("chapter_links", "")).strip()
                item = QTreeWidgetItem([name, kind, ch_range, note, chapter_links])
                item.setData(0, Qt.UserRole, final_id)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                # 挂到正确父节点
                if parent_id and parent_id in existing_items:
                    existing_items[parent_id].addChild(item)
                    existing_items[parent_id].setExpanded(True)
                else:
                    self.tree_plot.addTopLevelItem(item)
                existing_items[final_id] = item
                by_key[dedupe_key] = final_id
                added["pt"] = added.get("pt", 0) + 1

        return added
    
    # ── 注入到提示词 ───────────────────────────────────────
    def build_inject_block(self, current_chapter=None, mentioned_names=None):
        """
        生成给 AI 的注入文本块。可按当前章节智能筛选最相关的内容。
        
        参数:
          current_chapter: 即将生成的章节号(int),用于伏笔提醒
          mentioned_names: 提示词中已提到的角色名集合(set),只注入相关角色
        
        返回:
          str: 拼好的注入文本块,直接 append 到提示词后面

        v1.84 新增 POV 模式:
          - 通过 self.cb_pov_mode + self.le_pov_character 读出 POV 角色
          - 选 POV 模式时,关系热点/信息边界都按 POV 角色已知信息收窄
          - 末尾自动追加"以 X 视角写本章"指令段
        """
        if not self.chk_inject.isChecked():
            return ""

        parts = []

        # v1.84:解析 POV 模式(全知 / 主角 POV / 角色 POV)
        pov_mode, pov_character = "全知视角", ""
        try:
            pov_mode, pov_character = self._resolve_pov_character()
        except Exception:
            pass
        # POV 模式下,把 POV 角色名加入 mentioned_names(确保该角色信息一定被注入)
        if pov_character:
            if mentioned_names is None:
                mentioned_names = set()
            elif not isinstance(mentioned_names, set):
                mentioned_names = set(mentioned_names)
            mentioned_names.add(pov_character)

        # 1. 主角当前状态
        hs = (
            f"年龄 {self.hero_age.text()}, "
            f"修为 {self.hero_realm.text()}, "
            f"位置 {self.hero_location.text()}, "
            f"势力 {self.hero_faction.text()}, "
            f"心境 {self.hero_mood.text()}"
        )
        parts.append(f"【主角当前状态】\n{hs}")
        
        # 2. 角色档案(只取主角+前5个配角,避免提示词过长)
        chars = []
        _ncols = self.tbl_chars.columnCount()
        for r in range(self.tbl_chars.rowCount()):
            row = [self.tbl_chars.item(r, c).text() if self.tbl_chars.item(r, c) else "" 
                   for c in range(_ncols)]
            if not row[0].strip():
                continue
            chars.append(row)
        
        if chars:
            char_lines = []
            # 主角和女主优先
            chars.sort(key=lambda x: 0 if "主角" in x[1] or "女主" in x[1] else 1)
            for row in chars[:8]:
                # 兼容旧数据(9列)和新数据(10列)
                name = row[0] if len(row) > 0 else ""
                role = row[1] if len(row) > 1 else ""
                look = row[2] if len(row) > 2 else ""
                pers = row[3] if len(row) > 3 else ""
                mark = row[4] if len(row) > 4 else ""
                ability = row[5] if len(row) > 5 else ""
                speech = row[6] if len(row) > 6 else ""
                state = row[7] if len(row) > 7 else ""
                line = f"  • {name}({role}): "
                bits = []
                if look:    bits.append(f"外貌-{look}")
                if pers:    bits.append(f"性格-{pers}")
                if mark:    bits.append(f"标志-{mark}")
                if ability: bits.append(f"能力-{ability}")
                if speech:  bits.append(f"说话风格-{speech}")
                if state:   bits.append(f"状态-{state}")
                line += "; ".join(bits)
                char_lines.append(line)
            parts.append("【角色档案】\n" + "\n".join(char_lines))
        
        # 3. 关系图谱(简洁)
        rels = []
        for r in range(self.tbl_relations.rowCount()):
            a    = self.tbl_relations.item(r, 0).text() if self.tbl_relations.item(r, 0) else ""
            tp   = self.tbl_relations.item(r, 1).text() if self.tbl_relations.item(r, 1) else ""
            b    = self.tbl_relations.item(r, 2).text() if self.tbl_relations.item(r, 2) else ""
            note = self.tbl_relations.item(r, 3).text() if self.tbl_relations.item(r, 3) else ""
            if a and b and tp:
                rels.append(f"  • {a} -[{tp}]- {b}" + (f" ({note})" if note else ""))
        if rels:
            parts.append("【人物关系】\n" + "\n".join(rels[:15]))
        
        # 4. 主角已有物品
        items = []
        for r in range(self.tbl_items.rowCount()):
            name  = self.tbl_items.item(r, 0).text() if self.tbl_items.item(r, 0) else ""
            tp    = self.tbl_items.item(r, 1).text() if self.tbl_items.item(r, 1) else ""
            owner = self.tbl_items.item(r, 2).text() if self.tbl_items.item(r, 2) else ""
            ability = self.tbl_items.item(r, 4).text() if self.tbl_items.item(r, 4) else ""
            if name and ("主角" in owner or owner == "" or "李远" in owner):
                items.append(f"  • {name}({tp}): {ability}")
        if items:
            parts.append("【主角已有物品/法器】\n" + "\n".join(items[:10]))
        
        # 5. 待回收的伏笔(按距离回收期排序)
        if current_chapter is not None:
            pending = []
            must_pay = []   # v1.76:本章硬性必须回收的(plan_pay_at == current_chapter)
            for r in range(self.tbl_fore.rowCount()):
                ch_set = self.tbl_fore.item(r, 0).text() if self.tbl_fore.item(r, 0) else "0"
                content= self.tbl_fore.item(r, 1).text() if self.tbl_fore.item(r, 1) else ""
                ch_pay = self.tbl_fore.item(r, 2).text() if self.tbl_fore.item(r, 2) else "0"
                paid   = self.tbl_fore.item(r, 3).text() if self.tbl_fore.item(r, 3) else "否"
                if paid == "是" or not content:
                    continue
                try:
                    ch_pay_int = int(ch_pay)
                    # v1.76 BUG-056:ch_pay=0 意味着 AI 没评估出回收期,不算超期(灰色温和提示)
                    if ch_pay_int == 0:
                        pending.append((999, ch_set, content, "未评估"))
                        continue
                    distance = ch_pay_int - current_chapter
                    if -5 <= distance <= 10:  # 接近回收期或已超期
                        pending.append((distance, ch_set, content, ch_pay))
                        # 已到回收期或超期 → 进 must_pay(强约束)
                        if distance <= 0:
                            must_pay.append((ch_set, content, ch_pay, distance))
                except ValueError:
                    pending.append((999, ch_set, content, ch_pay))
            pending.sort(key=lambda x: x[0])
            if pending:
                lines = []
                for dist, cs, ct, cp in pending[:5]:
                    if cp == "未评估":
                        flag = "📝待AI评估"
                    elif dist < 0:
                        flag = "⚠️超期"
                    elif dist <= 2:
                        flag = "🎯本章可回收"
                    else:
                        flag = f"还有{dist}章"
                    lines.append(f"  • 第{cs}章埋: {ct} → 第{cp}章回收[{flag}]")
                parts.append("【待回收伏笔(优先考虑)】\n" + "\n".join(lines))
            # v1.76 BUG-056:本章硬性必须回收的伏笔,加强约束块
            if must_pay:
                strict_lines = ["⚠️ 【本章硬性必须回收的伏笔 — 不允许跳过】"]
                strict_lines.append(
                    "本章正文必须明确处理下列伏笔(给出实质解决/揭晓/兑现,不能只字未提):")
                for cs, ct, cp, dist in must_pay[:10]:
                    overdue_tag = f"已超期 {abs(dist)} 章" if dist < 0 else "本章到期"
                    strict_lines.append(f"  • [第{cs}章埋,{overdue_tag}] {ct}")
                strict_lines.append(
                    "回收方式:写到这条伏笔涉及的人物、物品、地点、谜题时,给出确切答案或下一步进展。\n"
                    "    禁止用『以后再说』『暂且不表』等敷衍话术绕过。")
                parts.append("\n".join(strict_lines))
        
        # 5b. 威胁承诺(v1.77 BUG-057)— 与伏笔同模式,但语义是"人对人的契约"
        if current_chapter is not None and hasattr(self, "tbl_promises"):
            pr_pending = []
            pr_must_pay = []
            for r in range(self.tbl_promises.rowCount()):
                ch_set = self.tbl_promises.item(r, 0).text() if self.tbl_promises.item(r, 0) else "0"
                kind = self.tbl_promises.item(r, 1).text() if self.tbl_promises.item(r, 1) else "承诺"
                fr = self.tbl_promises.item(r, 2).text() if self.tbl_promises.item(r, 2) else ""
                to = self.tbl_promises.item(r, 3).text() if self.tbl_promises.item(r, 3) else ""
                ct = self.tbl_promises.item(r, 4).text() if self.tbl_promises.item(r, 4) else ""
                dl = self.tbl_promises.item(r, 5).text() if self.tbl_promises.item(r, 5) else "0"
                fulfilled = self.tbl_promises.item(r, 6).text() if self.tbl_promises.item(r, 6) else "否"
                if fulfilled == "是" or not ct:
                    continue
                try:
                    dl_int = int(dl)
                    # ch_pay=0 同 v1.76 模式:走"待AI评估"分支
                    if dl_int == 0:
                        pr_pending.append((999, ch_set, kind, fr, to, ct, "未评估"))
                        continue
                    distance = dl_int - current_chapter
                    if -5 <= distance <= 10:
                        pr_pending.append((distance, ch_set, kind, fr, to, ct, dl))
                        if distance <= 0:
                            pr_must_pay.append((ch_set, kind, fr, to, ct, dl, distance))
                except ValueError:
                    pr_pending.append((999, ch_set, kind, fr, to, ct, dl))
            pr_pending.sort(key=lambda x: x[0])
            if pr_pending:
                lines = []
                for dist, cs, kd, fr, to, ct, dl in pr_pending[:5]:
                    if dl == "未评估":
                        flag = "📝待AI评估"
                    elif dist < 0:
                        flag = "⚠️超期"
                    elif dist <= 2:
                        flag = "🎯本章可兑现"
                    else:
                        flag = f"还有{dist}章"
                    parties = f"{fr}→{to}" if (fr or to) else ""
                    lines.append(
                        f"  • [{kd}] 第{cs}章 {parties}: {ct} → 第{dl}章截止[{flag}]")
                parts.append("【待兑现承诺/威胁/约定(优先考虑)】\n" + "\n".join(lines))
            if pr_must_pay:
                strict_lines = ["⚠️ 【本章硬性必须兑现的承诺/威胁/约定 — 不允许跳过】"]
                strict_lines.append(
                    "本章正文必须明确处理下列条目(履行/执行/赴约/违约/化解,五选一,不能只字未提):")
                for cs, kd, fr, to, ct, dl, dist in pr_must_pay[:10]:
                    overdue_tag = f"已超期 {abs(dist)} 章" if dist < 0 else "本章到期"
                    parties = f"{fr}→{to}" if (fr or to) else ""
                    strict_lines.append(
                        f"  • [{kd},第{cs}章定下,{overdue_tag}] {parties}: {ct}")
                strict_lines.append(
                    "处理方式:写到涉及的人物时,要让承诺被兑现 / 威胁被执行(或化解) / 约定被赴约(或违约)。\n"
                    "    禁止用『以后再算』『改日再说』敷衍。违背 = 失信,必须有读者可见的结果。")
                parts.append("\n".join(strict_lines))

        # 5c. 剧情进度(v1.78 BUG-058)— 3 段:弧线进度 / 关系热点 / 当前目标
        # 弧线进度 — 总是注入,给 AI "已写多少 / 还能写多少" 的宏观感
        if hasattr(self, "tbl_arcs"):
            arc_lines = []
            for r in range(self.tbl_arcs.rowCount()):
                nm = self.tbl_arcs.item(r, 0).text() if self.tbl_arcs.item(r, 0) else ""
                pg = self.tbl_arcs.item(r, 1).text() if self.tbl_arcs.item(r, 1) else "0"
                ph = self.tbl_arcs.item(r, 2).text() if self.tbl_arcs.item(r, 2) else "开端"
                if not nm:
                    continue
                try:
                    pg_int = max(0, min(100, int(pg)))
                except (TypeError, ValueError):
                    pg_int = 0
                arc_lines.append(f"  • {nm}: {pg_int}% [{ph}]")
            if arc_lines:
                parts.append(
                    "【当前弧线进度】(参考宏观节奏,主线<50% 不收束,>90% 准备高潮)\n"
                    + "\n".join(arc_lines))

        # 关系值热点 — 只注入 |value| ≥ 50 的前 8 条,按绝对值降序
        if hasattr(self, "tbl_rel_values"):
            hot = []
            for r in range(self.tbl_rel_values.rowCount()):
                a = self.tbl_rel_values.item(r, 0).text() if self.tbl_rel_values.item(r, 0) else ""
                b = self.tbl_rel_values.item(r, 1).text() if self.tbl_rel_values.item(r, 1) else ""
                v = self.tbl_rel_values.item(r, 2).text() if self.tbl_rel_values.item(r, 2) else "0"
                if not (a and b):
                    continue
                try:
                    val = int(v)
                except (TypeError, ValueError):
                    continue
                if abs(val) < 50:
                    continue
                # mentioned_names 筛选(若提供)— 二者至少一个出现在本章
                if mentioned_names:
                    if not (a in mentioned_names or b in mentioned_names):
                        continue
                # v1.84:POV 模式下,只显示 POV 角色参与的关系对
                # (POV 角色对外界的关系是他能感知的,与他无关的关系热点不应被他"感知到")
                if pov_character:
                    if not (a == pov_character or b == pov_character):
                        continue
                hot.append((abs(val), val, a, b))
            hot.sort(key=lambda x: -x[0])
            if hot:
                lines = []
                for _av, v, a, b in hot[:8]:
                    if v <= -80:
                        tone = "死敌/血仇"
                    elif v <= -50:
                        tone = "敌对/有仇"
                    elif v >= 80:
                        tone = "至交/挚爱"
                    elif v >= 50:
                        tone = "朋友/亲近"
                    else:
                        tone = "中性"
                    lines.append(f"  • {a} → {b}: {v:+d} [{tone}]")
                pov_label = f"({pov_character} 视角)" if pov_character else ""
                parts.append(
                    f"【当前关系热点{pov_label}(写到对应角色时,情绪反应须符合该关系值)】\n"
                    + "\n".join(lines))

        # 当前目标 — 只注入【进行中】的目标
        if hasattr(self, "tbl_goals"):
            ongoing = []
            for r in range(self.tbl_goals.rowCount()):
                nm = self.tbl_goals.item(r, 0).text() if self.tbl_goals.item(r, 0) else ""
                pr = self.tbl_goals.item(r, 1).text() if self.tbl_goals.item(r, 1) else "主线"
                st = self.tbl_goals.item(r, 2).text() if self.tbl_goals.item(r, 2) else "进行中"
                sc = self.tbl_goals.item(r, 3).text() if self.tbl_goals.item(r, 3) else "1"
                if not nm or st != "进行中":
                    continue
                ongoing.append((pr, nm, sc))
            if ongoing:
                # 紧急 → 主线 → 支线 排序
                _ord = {"紧急": 0, "主线": 1, "支线": 2}
                ongoing.sort(key=lambda x: _ord.get(x[0], 9))
                lines = [f"  • [{pr}] {nm}(第{sc}章立)"
                         for pr, nm, sc in ongoing[:10]]
                parts.append(
                    "【主角当前目标(进行中)— 主角行动应朝这些目标推进,避免偏离】\n"
                    + "\n".join(lines))

        # 5d. 信息隔离(v1.79 BUG-059)— 角色已知信息边界
        # 仅对本章 mentioned_names 中的角色注入,防止 OOC(主角不在场也合理);
        # 若 mentioned_names 为空(没传或全空),整段不出 — 因为没法精确定向。
        # v1.84:POV 模式下只显示 POV 单一角色的边界(更严格)
        if hasattr(self, "tbl_infos") and hasattr(self, "tbl_known_by") and mentioned_names:
            # 1. 建 info_id → content 索引
            info_content = {}
            for r in range(self.tbl_infos.rowCount()):
                id_it = self.tbl_infos.item(r, 0)
                ct_it = self.tbl_infos.item(r, 1)
                if id_it and ct_it:
                    info_content[id_it.text().strip()] = ct_it.text().strip()
            # 2. 按角色聚合
            by_char = {}  # name → set(info_id)
            for r in range(self.tbl_known_by.rowCount()):
                iid_it = self.tbl_known_by.item(r, 0)
                ch_it = self.tbl_known_by.item(r, 1)
                if not (iid_it and ch_it):
                    continue
                iid = iid_it.text().strip()
                ch = ch_it.text().strip()
                if not (iid and ch) or iid not in info_content:
                    continue
                by_char.setdefault(ch, set()).add(iid)
            # 3. 输出范围:POV 模式只 POV 角色,否则 mentioned 全部
            if pov_character:
                target_chars = {pov_character} & set(by_char.keys())
            else:
                target_chars = set(by_char.keys()) & set(mentioned_names)
            lines = []
            for ch in sorted(target_chars):
                ids = sorted(by_char[ch])
                snippets = [f"{iid}({info_content.get(iid, '?')[:20]})" for iid in ids]
                lines.append(f"  • {ch} 已知: " + ", ".join(snippets))
            if lines:
                # 同时列出"全文有但本章角色都不知道"的信息(警示用)
                all_info_ids = set(info_content.keys())
                known_in_chapter = set()
                for ch in target_chars:
                    known_in_chapter |= by_char[ch]
                secrets = all_info_ids - known_in_chapter
                if pov_character:
                    title = f"【{pov_character} POV 已知信息边界(本章 ONLY 用此视角写,不能让 {pov_character} 暴露他不知道的信息)】"
                else:
                    title = "【本章出场角色已知信息边界(严守 — 不在已知列表的信息,该角色绝对不能提及/利用/暗示)】"
                hint_block = title + "\n" + "\n".join(lines)
                if secrets:
                    sec_lines = [f"{iid}({info_content.get(iid, '?')[:20]})"
                                 for iid in sorted(secrets)[:8]]
                    if pov_character:
                        hint_block += (
                            f"\n  ⚠ {pov_character} 【不应】触及/暗示的信息:"
                            + ", ".join(sec_lines))
                    else:
                        hint_block += (
                            "\n  ⚠ 本章出场角色【不应】触及的信息:"
                            + ", ".join(sec_lines))
                parts.append(hint_block)

        # 5e. 剧情树定位(v1.80 BUG-060)— 当前主线进度
        # 找到 current_chapter 所在的最具体节点(剧情点 > 章节槽 > 阶段 > 故事),
        # 输出"当前在 X → Y → Z 路径下"+ 同阶段剩余章数,让 AI 知道宏观位置
        if hasattr(self, "tree_plot") and current_chapter:
            try:
                ch = int(current_chapter)
            except (TypeError, ValueError):
                ch = 0
            if ch > 0:
                # 扁平 list 形式扫描
                from PyQt5.QtCore import Qt as _Qt
                flat_nodes = []
                # 节点结构:{node_id, parent_id, name, kind, ch_range, note}
                def _walk(item, parent_id):
                    nid = item.data(0, _Qt.UserRole)
                    nid = str(nid) if nid else ""
                    flat_nodes.append({
                        "id": nid, "parent_id": parent_id,
                        "name": item.text(0), "kind": item.text(1),
                        "ch_range": item.text(2), "note": item.text(3),
                    })
                    for i in range(item.childCount()):
                        _walk(item.child(i), nid)
                for i in range(self.tree_plot.topLevelItemCount()):
                    _walk(self.tree_plot.topLevelItem(i), "")

                def _node_covers(node, ch):
                    """节点的 ch_range 是否覆盖 ch"""
                    cr = (node.get("ch_range") or "").strip()
                    if not cr:
                        return False
                    if "-" in cr:
                        parts_r = cr.split("-", 1)
                        try:
                            a, b = int(parts_r[0]), int(parts_r[1])
                            return a <= ch <= b
                        except ValueError:
                            return False
                    try:
                        return int(cr) == ch
                    except ValueError:
                        return False

                # 优先级:剧情点 > 章节槽 > 阶段(剧情点最精确)
                _PRIORITY = {"剧情点": 0, "章节槽": 1, "阶段": 2, "故事": 3}
                covering = [n for n in flat_nodes if _node_covers(n, ch)]
                if covering:
                    covering.sort(key=lambda x: _PRIORITY.get(x["kind"], 9))
                    target = covering[0]
                    # 回溯祖先链
                    by_id = {n["id"]: n for n in flat_nodes if n["id"]}
                    path = [target]
                    cur_pid = target["parent_id"]
                    while cur_pid and cur_pid in by_id:
                        path.append(by_id[cur_pid])
                        cur_pid = by_id[cur_pid]["parent_id"]
                    path.reverse()  # 根 → 目标
                    path_str = " → ".join(f"[{n['kind']}]{n['name']}" for n in path)

                    # 算同阶段剩余章数(如果目标节点 ch_range 是范围)
                    rem_hint = ""
                    cr = target.get("ch_range", "").strip()
                    if "-" in cr:
                        try:
                            _a, _b = cr.split("-", 1)
                            b_int = int(_b)
                            if b_int >= ch:
                                rem_hint = f",本节点剩余 {b_int - ch + 1} 章"
                        except ValueError:
                            pass
                    note = target.get("note", "").strip()
                    note_hint = f"\n  备注:{note}" if note else ""
                    parts.append(
                        f"【当前主线进度(本章在剧情树中的位置 — 用于把握宏观节奏)】\n"
                        f"  位置:{path_str}{rem_hint}{note_hint}\n"
                        f"  写作约束:本章内容应推进【{target['name']}】这个节点的进展,"
                        f"避免无意义偏离。")

        # 6. 战力等级体系(防止跨级混乱)
        powers = []
        for r in range(self.tbl_power.rowCount()):
            lv   = self.tbl_power.item(r, 1).text() if self.tbl_power.item(r, 1) else ""
            desc = self.tbl_power.item(r, 2).text() if self.tbl_power.item(r, 2) else ""
            if lv:
                powers.append(f"  • {lv}: {desc}")
        if powers:
            parts.append("【战力等级体系(由低到高)】\n" + "\n".join(powers))

        # 7. 最近时间线事件(防剧情漂移)
        events = []
        for r in range(self.tbl_timeline.rowCount()):
            ch     = self.tbl_timeline.item(r, 0).text() if self.tbl_timeline.item(r, 0) else "0"
            evt    = self.tbl_timeline.item(r, 1).text() if self.tbl_timeline.item(r, 1) else ""
            change = self.tbl_timeline.item(r, 2).text() if self.tbl_timeline.item(r, 2) else ""
            try:
                ch_int = int(ch)
                events.append((ch_int, evt, change))
            except ValueError:
                continue
        events.sort()
        if events and current_chapter:
            recent = [e for e in events if e[0] <= current_chapter][-5:]
            if recent:
                lines = [f"  • 第{c}章: {e}" + (f" [{ch}]" if ch else "") for c, e, ch in recent]
                parts.append("【最近重大事件】\n" + "\n".join(lines))

        # v1.84:POV 模式 — 在所有库信息之后,补一段强约束的视角指令
        if pov_character:
            pov_block = (
                f"【⚠️ 本章 POV 模式 — 严格遵守】\n"
                f"  本章使用【{pov_character}】的视角写作。\n"
                f"  规则:\n"
                f"    1. 只描写【{pov_character}】能感知到的:他的所见/所闻/所想/所感\n"
                f"    2. 不能写【{pov_character}】不在场的场景(切场景需明确『后来听 X 说』)\n"
                f"    3. 不能让【{pov_character}】突然知道他【上方信息边界】之外的事实\n"
                f"    4. 其他角色的内心活动【不能直接写】 — 只能通过 {pov_character} 的观察推断\n"
                f"    5. 描写【{pov_character}】用『他/她』或姓名,不要用『我』(第三人称限知)"
            )
            parts.append(pov_block)

        if not parts:
            return ""

        return "\n\n" + "═" * 30 + "\n📚 角色与世界状态(必须严格遵守):\n" + "═" * 30 + "\n\n" + "\n\n".join(parts)
    
    # ── v1.64:主角状态自动同步 ───────────────────────────────
    
    def _set_hero_readonly(self, readonly):
        """切换 5 个 hero_* 字段的只读状态(D 方案 — UI 派生数据展示)"""
        for ed in getattr(self, "_hero_edits", []):
            ed.setReadOnly(readonly)
            if readonly:
                ed.setStyleSheet(
                    "QLineEdit { background:#f5f5f5; color:#444; "
                    "border:1px solid #ccc; padding:3px; }")
            else:
                ed.setStyleSheet(
                    "QLineEdit { background:white; color:#000; "
                    "border:1px solid #1a4480; padding:3px; }")
    
    def _on_hero_unlock_toggled(self, checked):
        """『✏️ 手动改』按钮 toggled — 切换只读/可编辑"""
        self._set_hero_readonly(not checked)
        if checked:
            self.btn_unlock_hero.setText("🔒 切回只读")
            self.lbl_hero_source.setText(
                "✏️ 手动编辑模式 — 你的修改不会被自动同步覆盖,"
                "切回只读后,下次同步才会再次自动填")
            self.lbl_hero_source.setStyleSheet(
                "color: #b4884e; font-weight: bold; font-size: 11px; "
                "padding: 2px 4px;")
        else:
            self.btn_unlock_hero.setText("✏️ 手动改")
            self.lbl_hero_source.setText(
                "📌 数据来源:派生模式(可点🔄按钮自动抽取)")
            self.lbl_hero_source.setStyleSheet(
                "color: #888; font-size: 11px; padding: 2px 4px;")
    
    # 关键词正则(类属性,便于测试访问)
    # 5 个字段各自的"识别 + 提取"正则
    # 每条:在 state_change 文本里命中关键词 + 截取关键值
    _HERO_PATTERNS = {
        "realm": [
            # 直接说"晋升 / 突破到 XX"
            r"(?:晋升|突破|进阶|跃升|提升)(?:到|至)?\s*([^,，。;；\s]{1,20}(?:期|境|层|阶|段|境界))",
            # "修为达到 XX"
            r"修为(?:达到|为|提升至?)\s*([^,，。;；\s]{1,20}(?:期|境|层|阶|段))",
            # 主流修仙体系白名单:筑基/金丹/元婴/化神/合体/大乘/渡劫 + 期/初中后
            # (避免之前广义 [汉]{1,4}+期|境 匹配"心境"/"环境"等)
            r"((?:练气|筑基|金丹|元婴|化神|合体|大乘|渡劫|真仙)(?:[初中后晚]?期|境|[一二三四五六七八九十]+层)?)",
        ],
        "location": [
            # "抵达/到达 XX / 进入 XX"
            r"(?:抵达|到达|进入|来到|前往)\s*([^,，。;；\s]{1,15}(?:山|城|宗|府|地|境|窟|府邸|岛|界|村|镇|国))",
        ],
        "faction": [
            # "加入/拜入 XX 宗/门/派/盟"
            r"(?:加入|拜入|进入)\s*([^,，。;；\s]{1,15}(?:宗|门|派|盟|会|阁|教|帮|府))",
        ],
        "age": [
            # "年龄 XX 岁" / "XX 岁那年"
            r"年龄\s*(\d{1,3})\s*岁",
            r"(\d{1,3})\s*岁",
        ],
        "mood": [
            # "心境 XX / 心情 XX"
            r"(?:心境|心情|心绪|状态)(?:为|变得|转为|进入)?\s*([\u4e00-\u9fa5]{1,8})",
        ],
    }
    
    def _extract_hero_from_timeline(self, timeline_rows):
        """从 timeline rows 抽取主角状态字段。
        
        参数:
          timeline_rows: list[(ch_num_str, event, state_change)]
                         — 按章节顺序(可乱序,内部会按 ch 降序处理)
        
        返回:
          dict 形如 {"realm": (值, 章节号), "location": (值, 章节号), ...}
          — 章节号:从哪一章抽到的;命中不到的字段不出现在 dict
        """
        import re
        # 按章节号降序排(取最新)— ch 可能不是数字,容错
        def _ch_int(row):
            try:
                return int(re.search(r"\d+", str(row[0] or "")).group())
            except Exception:
                return 0
        rows_sorted = sorted(timeline_rows, key=_ch_int, reverse=True)
        
        result = {}
        for ch_str, _evt, state_change in rows_sorted:
            text = str(state_change or "").strip()
            if not text:
                continue
            ch_num = _ch_int((ch_str,))
            for field, patterns in self._HERO_PATTERNS.items():
                if field in result:
                    continue  # 已命中过最新章节,不覆盖
                for pat in patterns:
                    m = re.search(pat, text)
                    if m:
                        val = m.group(1).strip()
                        # 净化:去标点
                        val = val.rstrip("，。;；,.").strip()
                        if val:
                            result[field] = (val, ch_num)
                            break
        return result
    
    def _sync_hero_from_timeline(self):
        """🔄 从时间线同步 — 按钮 handler。
        
        扫描 timeline 表所有 state_change,自动填到 5 个字段。
        手动模式下提示用户切回只读才能同步(避免覆盖手填值)。
        """
        # 手动模式下警告(避免覆盖用户的手填值)
        if self.btn_unlock_hero.isChecked():
            from PyQt5.QtWidgets import QMessageBox
            ret = QMessageBox.question(
                self, "确认同步",
                "当前在手动编辑模式,同步会覆盖你已经手填的值。\n是否继续?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        
        # 收集 timeline rows
        rows = []
        for r in range(self.tbl_timeline.rowCount()):
            row = []
            for c in range(3):
                it = self.tbl_timeline.item(r, c)
                row.append(it.text() if it else "")
            rows.append(tuple(row))
        
        if not rows:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "提示",
                "时间线为空,无法同步。\n\n"
                "可以:\n"
                "  • 手动在下方时间线添加事件 + 状态变化\n"
                "  • 写完章节后点『立即从所有章节提取』让 AI 自动抽取时间线\n"
                "  • 在创作设置打开『AI 写完每章自动同步主角状态』")
            return
        
        extracted = self._extract_hero_from_timeline(rows)
        
        if not extracted:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "未匹配",
                "扫了 {} 条时间线事件,但没识别到任何"
                "修为/位置/势力/年龄/心境关键词。\n\n"
                "建议时间线的『状态变化』列写成:\n"
                "  • 晋升金丹中期\n"
                "  • 抵达青云山\n"
                "  • 加入天剑宗\n"
                "  • 年龄 22 岁\n"
                "  • 心境 决绝".format(len(rows)))
            return
        
        # 填字段(切只读时不要被 readonly 拦住:先解锁、setText、再恢复)
        was_readonly = self._hero_edits[0].isReadOnly()
        if was_readonly:
            for ed in self._hero_edits:
                ed.setReadOnly(False)
        
        field_map = {
            "age":      self.hero_age,
            "realm":    self.hero_realm,
            "location": self.hero_location,
            "faction":  self.hero_faction,
            "mood":     self.hero_mood,
        }
        filled_summary = []
        max_ch = 0
        for field, (val, ch_num) in extracted.items():
            edit = field_map.get(field)
            if edit:
                edit.setText(val)
                filled_summary.append(f"{field}={val} (第{ch_num}章)")
                max_ch = max(max_ch, ch_num)
        
        # 恢复只读
        if was_readonly:
            for ed in self._hero_edits:
                ed.setReadOnly(True)
        
        # 更新来源 label
        if max_ch > 0:
            self.lbl_hero_source.setText(
                f"📌 数据来源:从时间线同步({len(extracted)}/5 字段命中,"
                f"最新数据来自第 {max_ch} 章)")
        else:
            self.lbl_hero_source.setText(
                f"📌 数据来源:从时间线同步({len(extracted)}/5 字段命中)")
        self.lbl_hero_source.setStyleSheet(
            "color: #1a4480; font-size: 11px; padding: 2px 4px; font-weight:bold;")
        
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "同步完成",
            f"已从时间线抽取 {len(extracted)}/5 个字段:\n\n"
            + "\n".join(f"  • {s}" for s in filled_summary)
            + ("\n\n(未匹配的字段保持原值)"
               if len(extracted) < 5 else ""))
    
    def apply_hero_state_dict(self, hero_state):
        """B 方案:AI 抽取回的 hero_state dict 直接填入字段。
        
        在 MainWindow._on_world_extract_received → _merge_into_charlib 里调用。
        手动模式下不覆盖(保护用户手填值)。
        
        参数 hero_state: dict,字段可包含 age/realm/location/faction/mood
        
        返回:int — 实际写入的字段数(0 = 没匹配 / 在手动模式下跳过)
        """
        if not hero_state or not isinstance(hero_state, dict):
            return 0
        # 手动模式 → 跳过(用户手填值优先)
        if hasattr(self, "btn_unlock_hero") and self.btn_unlock_hero.isChecked():
            return 0
        
        field_map = {
            "age":      self.hero_age,
            "realm":    self.hero_realm,
            "location": self.hero_location,
            "faction":  self.hero_faction,
            "mood":     self.hero_mood,
        }
        
        # 先解锁
        was_readonly = self._hero_edits[0].isReadOnly() if self._hero_edits else False
        if was_readonly:
            for ed in self._hero_edits:
                ed.setReadOnly(False)
        
        n_filled = 0
        for k, edit in field_map.items():
            v = hero_state.get(k)
            if v is None or str(v).strip() == "":
                continue
            edit.setText(str(v).strip())
            n_filled += 1
        
        # 恢复只读
        if was_readonly:
            for ed in self._hero_edits:
                ed.setReadOnly(True)
        
        return n_filled
    
    # ── 导入/导出 ──────────────────────────────────────────
    def _export_lib(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出角色库", "character_lib.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.serialize(), f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功", f"已导出到:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))
    
    def _import_lib(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self, "导入角色库", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "失败", f"JSON 解析失败:\n{e}")
            return
        
        # 检测格式 — 任一表的第一项是 dict ⇒ 外部格式(如 DeepSeek 提取),适合追加
        is_dict_format = False
        for key in ("characters", "relations", "items", "events", "timeline", "foreshadows"):
            seq = data.get(key)
            if seq and isinstance(seq, list) and isinstance(seq[0], dict):
                is_dict_format = True
                break
        
        # 当前表格非空就要问;若 dict 格式默认提示"追加",老格式默认"覆盖"
        any_existing = any(t.rowCount() > 0 for t in (
            self.tbl_chars, self.tbl_relations, self.tbl_timeline,
            self.tbl_items, self.tbl_fore))
        
        if any_existing:
            mb = QMessageBox(self)
            mb.setWindowTitle("导入方式")
            mb.setIcon(QMessageBox.Question)
            mb.setText("当前已有数据,选择导入方式:")
            mb.setInformativeText(
                "• 追加合并:保留现有,只加入新条目(去重)\n"
                "• 覆盖全部:清空现有后用新数据替换"
            )
            btn_merge = mb.addButton("追加合并", QMessageBox.AcceptRole)
            btn_replace = mb.addButton("覆盖全部", QMessageBox.DestructiveRole)
            btn_cancel = mb.addButton("取消", QMessageBox.RejectRole)
            mb.setDefaultButton(btn_merge if is_dict_format else btn_replace)
            mb.exec_()
            clicked = mb.clickedButton()
            if clicked is btn_cancel:
                return
            mode = "merge" if clicked is btn_merge else "replace"
        else:
            # 空表 — 直接走相应路径
            mode = "merge" if is_dict_format else "replace"
        
        try:
            if mode == "merge":
                added = self.merge_dicts(data)
                QMessageBox.information(
                    self, "成功",
                    f"已追加合并:\n"
                    f"  • 角色 +{added['ch']}\n"
                    f"  • 关系 +{added['rel']}\n"
                    f"  • 物品 +{added['it']}\n"
                    f"  • 事件 +{added['ev']}\n"
                    f"  • 伏笔 +{added['fo']}")
            else:
                self.load(data)
                QMessageBox.information(self, "成功", "已覆盖导入完成")
        except Exception as e:
            QMessageBox.warning(self, "失败", f"导入过程出错:\n{e}")
    
    # ── 章节范围 / Prompt 拼装(抽出来便于复用 + 测试)──────────────
    
    _EXTRACT_PROMPT_TEMPLATE = (
        "请从下面的小说正文中,提取结构化设定信息,以便归档到角色与世界库中。\n"
        "**严格按 JSON 格式输出,不要任何前后缀说明,不要 markdown 代码块标记**。\n\n"
        "输出格式(顶层 5 个字段,缺失类别给空数组 []):\n"
        "{\n"
        '  "characters": [\n'
        '    {"name": "角色名", "role": "主角/女主/配角/导师/反派/路人",\n'
        '     "appearance": "外貌简述", "personality": "性格特征",\n'
        '     "mark": "口头禅或标志性细节", "ability": "能力/职业/修为",\n'
        '     "state": "当前状态(剧情结束时)", "first_ch": "首次出场章节号"}\n'
        "  ],\n"
        '  "relations": [\n'
        '    {"a": "角色A名", "type": "师徒/恋人/血缘/敌对/同伴",\n'
        '     "b": "角色B名", "note": "备注或起因"}\n'
        "  ],\n"
        '  "items": [\n'
        '    {"name": "物品名", "type": "法器/丹药/秘籍/材料/信物",\n'
        '     "owner": "持有者", "source_ch": "来源章节", "ability": "能力或状态"}\n'
        "  ],\n"
        '  "events": [\n'
        '    {"ch": "章节号", "event": "重大事件简述",\n'
        '     "state_change": "主角状态变化(如:晋升金丹/获得XX)"}\n'
        "  ],\n"
        '  "foreshadows": [\n'
        '    {"ch": "埋设章节", "content": "伏笔内容(神秘物品/隐藏身份/可疑话语)",\n'
        '     "plan_pay_at": "建议第几章回收(如:30,无法判断填 0)"}\n'
        "  ]\n"
        "}\n\n"
        "提取规则:\n"
        "1. characters:列所有【有名字、有性格、对剧情有影响】的角色,普通路人省略\n"
        "2. relations:列对主线有意义的关系,泛泛之交不列\n"
        "3. items:列主角【获得/失去/重要使用】的物品,敌人物品和一次性消耗品不列\n"
        "4. events:列影响主线的重大事件,日常对话不算\n"
        "5. foreshadows:必须是【作者埋下、读者会记住的悬念】,不是普通铺垫\n"
        "6. first_ch / ch / source_ch 字段尽量按【真实首次出现章节】填,不是文本里这章的章节号\n"
        "7. JSON 必须严格合法 — 引号闭合、逗号位置正确、最外层是 {}\n"
        "8. 字符串内的双引号要转义(\\\"),不要用中文引号\n\n"
        "==================== 小说正文 ====================\n"
        "__BODY_PLACEHOLDER__\n"
    )
    
    @staticmethod
    def _chapters_to_body(chapters, start_idx=None, end_idx=None):
        """把 chapters 列表(MainWindow.chapters)切片转成 prompt 正文段。
        
        参数:
          chapters: list[dict],每项至少有 title/content
          start_idx, end_idx: **1-based** 闭区间;None 表示首/尾
        
        返回:
          str — 拼好的正文(没有可用章节时返回空串)
        """
        if not chapters:
            return ""
        total = len(chapters)
        s = 1 if start_idx is None else max(1, int(start_idx))
        e = total if end_idx is None else min(total, int(end_idx))
        if s > e:
            return ""
        lines = []
        for i in range(s, e + 1):
            ch = chapters[i - 1]
            title = ch.get("title", f"第 {i} 章")
            content = (ch.get("content") or "").strip()
            if content:
                lines.append(f"【{title}】\n{content}")
        return "\n\n".join(lines)
    
    def _build_extract_prompt(self, body=""):
        """拼出完整 prompt;body 为空时保留占位符提示用户手动贴。
        
        用 str.replace 而不是 .format,因为模板内含 JSON 示例的 {} 字符。
        """
        body = body.strip() if body else "（在这里粘贴你的小说全文或章节正文）"
        return self._EXTRACT_PROMPT_TEMPLATE.replace("__BODY_PLACEHOLDER__", body)
    
    def _copy_extract_prompt(self):
        """生成一份完整 prompt 复制到剪贴板,用户贴给 DeepSeek/ChatGPT 提取设定。
        
        弹对话框让用户选章节范围 — 全部 / 最近 N 章 / 指定区间 / 不附带正文。
        AI 返回的 JSON 直接保存为 .json 文件后,用『导入库』就能一键合并到当前所有库。
        """
        from PyQt5.QtWidgets import QApplication, QMessageBox
        
        # 取当前项目的章节
        chapters = []
        try:
            mw = self.window()
            chapters = list(getattr(mw, "chapters", None) or [])
        except Exception:
            pass
        
        # 没有章节 — 直接复制空模板
        if not chapters:
            prompt = self._build_extract_prompt("")
            QApplication.clipboard().setText(prompt)
            QMessageBox.information(
                self, "已复制(空模板)",
                "当前项目没有可用章节内容,已复制【空模板】到剪贴板。\n\n"
                "操作步骤:\n"
                "1. 打开 DeepSeek / ChatGPT,粘贴(Ctrl+V)\n"
                "2. 把『==小说正文==』下方的占位符替换为你要分析的内容\n"
                "3. 发送 → 拿到 JSON 后保存为 .json 文件\n"
                "4. 回到本工具,点『📤 导入库』→ 选『追加合并』")
            return
        
        # 有章节 — 弹范围选择
        s, e = self._ask_chapter_range(len(chapters))
        if s is None:  # 用户取消
            return
        
        # s == 0 表示用户选了"不附带正文",生成空模板
        if s == 0:
            body = ""
            range_desc = "未附带正文(模板模式)"
        else:
            body = self._chapters_to_body(chapters, s, e)
            range_desc = f"已附带第 {s}~{e} 章(共 {e - s + 1} 章, {len(body)} 字)"
        
        prompt = self._build_extract_prompt(body)
        QApplication.clipboard().setText(prompt)
        
        QMessageBox.information(
            self, "已复制",
            f"✓ 提取 prompt 已复制到剪贴板。\n"
            f"  范围:{range_desc}\n"
            f"  总长度:{len(prompt)} 字符\n\n"
            f"操作步骤:\n"
            f"1. 打开 DeepSeek / ChatGPT,粘贴(Ctrl+V)发送\n"
            f"2. AI 返回 JSON 后,全选复制保存为 .json 文件\n"
            f"3. 回到本工具,点『📤 导入库』选中那个文件\n"
            f"4. 选『追加合并』即可")
    
    def _ask_chapter_range(self, total):
        """弹对话框让用户选章节范围。
        
        参数:
          total: 当前项目总章节数(int, >= 1)
        
        返回:
          (start, end) 1-based 闭区间;用户取消返回 (None, None);
          选『不附带正文』返回 (0, 0)
        """
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
            QButtonGroup, QSpinBox, QPushButton, QWidget)
        
        dlg = QDialog(self)
        dlg.setWindowTitle("选择要附带的章节范围")
        dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)
        
        lay.addWidget(QLabel(f"当前项目共 <b>{total}</b> 章。选择要塞进 prompt 的范围:"))
        
        grp = QButtonGroup(dlg)
        
        # 选项 1:全部
        rb_all = QRadioButton(f"📚 全部章节(1 ~ {total})")
        rb_all.setChecked(True)
        grp.addButton(rb_all, 1)
        lay.addWidget(rb_all)
        
        # 选项 2:最近 N 章
        row2 = QHBoxLayout()
        rb_recent = QRadioButton("🕒 最近")
        spin_recent = QSpinBox()
        spin_recent.setRange(1, total)
        spin_recent.setValue(min(10, total))
        spin_recent.setSuffix(" 章")
        row2.addWidget(rb_recent)
        row2.addWidget(spin_recent)
        row2.addStretch()
        w2 = QWidget(); w2.setLayout(row2); lay.addWidget(w2)
        grp.addButton(rb_recent, 2)
        
        # 选项 3:指定区间
        row3 = QHBoxLayout()
        rb_range = QRadioButton("🎯 第")
        spin_from = QSpinBox(); spin_from.setRange(1, total); spin_from.setValue(1)
        spin_to = QSpinBox(); spin_to.setRange(1, total); spin_to.setValue(total)
        row3.addWidget(rb_range)
        row3.addWidget(spin_from)
        row3.addWidget(QLabel(" ~ 第 "))
        row3.addWidget(spin_to)
        row3.addWidget(QLabel(" 章"))
        row3.addStretch()
        w3 = QWidget(); w3.setLayout(row3); lay.addWidget(w3)
        grp.addButton(rb_range, 3)
        
        # 选项 4:不附带
        rb_none = QRadioButton("⬜ 不附带正文(只复制空模板,自己手动贴内容)")
        grp.addButton(rb_none, 4)
        lay.addWidget(rb_none)
        
        # 选中 spin 联动 — 操作 spin 时自动激活对应单选
        spin_recent.valueChanged.connect(lambda _: rb_recent.setChecked(True))
        spin_from.valueChanged.connect(lambda _: rb_range.setChecked(True))
        spin_to.valueChanged.connect(lambda _: rb_range.setChecked(True))
        
        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("✓ 复制 Prompt")
        btn_ok.setDefault(True)
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)
        
        if dlg.exec_() != QDialog.Accepted:
            return (None, None)
        
        choice = grp.checkedId()
        if choice == 1:
            return (1, total)
        elif choice == 2:
            n = spin_recent.value()
            return (max(1, total - n + 1), total)
        elif choice == 3:
            s, e = spin_from.value(), spin_to.value()
            if s > e:
                s, e = e, s
            return (s, e)
        else:  # 4 — 不附带
            return (0, 0)
