"""Native QGIS batch-design workspace with explicit data and run state."""

from __future__ import annotations

from collections import Counter

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .ui_style import PRIORITY_META, STATUS_META, repolish


_RULE_LABELS = {
    "R_SUBDUCT_CAPACITY": "合成子管余量不足",
    "R_SEGMENT_STATUS": "候选通道已禁用",
    "R_TASK_FORBIDDEN": "任务明确禁用该通道",
    "R_REVIEW_REQUIRED": "风险信息不足，必须人工复核",
}


class BatchDesignWidget(QWidget):
    """Five-stage batch workflow that never silently selects a dataset."""

    sample_requested = pyqtSignal()
    input_changed = pyqtSignal(str)
    import_requested = pyqtSignal(str)
    preview_requested = pyqtSignal()
    execute_requested = pyqtSignal(object)
    export_requested = pyqtSignal()
    filter_requested = pyqtSignal(str)
    focus_requested = pyqtSignal(str)
    route_visibility_requested = pyqtSignal(bool, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._descriptor: dict = {}
        self._dataset_selected = False
        self._busy = False
        self._run_gate_enabled = False
        self._export_gate_enabled = False
        self._has_results = False
        self._confirmed_fingerprint: str | None = None
        self._results: list[dict] = []
        self._results_by_task_id: dict[str, dict] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(7)

        workflow = QLabel(
            "1  数据准备   ›   2  任务确认   ›   3  运行   ›   4  结果复核   ›   5  导出"
        )
        workflow.setObjectName("BatchWorkflow")
        workflow.setProperty("role", "eyebrow")
        workflow.setAlignment(Qt.AlignCenter)
        workflow.setWordWrap(True)
        workflow.setMinimumWidth(0)
        workflow.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        outer.addWidget(workflow)

        self.next_step_label = QLabel("下一步：选择数据来源")
        self.next_step_label.setProperty("role", "nextStep")
        self.next_step_label.setWordWrap(True)
        self.next_step_label.setMinimumWidth(0)
        self.next_step_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        outer.addWidget(self.next_step_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setMinimumSize(0, 0)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll, 1)

        host = QWidget()
        host.setMinimumWidth(0)
        host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        content = QVBoxLayout(host)
        content.setContentsMargins(3, 3, 3, 8)
        content.setSpacing(9)
        self.scroll.setWidget(host)

        self.data_card, data_layout = self._section(
            "01 · 数据准备",
            "先明确选择输入；插件启动时不自动加载样例或任务。",
        )
        self.source_state_label = QLabel("未选择数据集")
        self.source_state_label.setProperty("state", "idle")
        data_layout.addWidget(self.source_state_label)

        self.dataset_label = QLabel("当前操作数据集：无")
        self.dataset_label.setWordWrap(True)
        self.dataset_label.setMinimumWidth(0)
        self.dataset_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.dataset_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_layout.addWidget(self.dataset_label)

        self.dataset_meta_label = QLabel("可选择下方内置样例；选择前不会向 QGIS 项目添加图层。")
        self.dataset_meta_label.setProperty("role", "muted")
        self.dataset_meta_label.setWordWrap(True)
        self.dataset_meta_label.setMinimumWidth(0)
        self.dataset_meta_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.dataset_meta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_layout.addWidget(self.dataset_meta_label)

        self.dataset_source_label = QLabel()
        self.dataset_source_label.setProperty("role", "muted")
        self.dataset_source_label.setWordWrap(True)
        self.dataset_source_label.setMinimumWidth(0)
        self.dataset_source_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.dataset_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_layout.addWidget(self.dataset_source_label)

        source_buttons = QGridLayout()
        source_buttons.setHorizontalSpacing(7)
        source_buttons.setVerticalSpacing(7)
        self.sample_button = QPushButton("加载内置样例")
        self.sample_button.setProperty("buttonRole", "primary")
        self.sample_button.setToolTip("先逐文件校验内置数据哈希，再向当前 QGIS 项目加载输入图层")
        self.external_button = QPushButton("我的工程包 · 待接入")
        self.external_button.setEnabled(False)
        self.external_button.setToolTip(
            "外部工程包已经由独立脚本验证，但插件 GUI Adapter 尚未实现；"
            "本按钮不会偷偷改用内置样例。"
        )
        source_buttons.addWidget(self.sample_button, 0, 0, 1, 2)
        source_buttons.addWidget(self.external_button, 1, 0, 1, 2)
        data_layout.addLayout(source_buttons)

        external_note = QLabel(
            "“我的工程”当前不可用：名古屋、札幌、福冈工程包的内核调用已验证，"
            "但 plugin_gui_integration 仍为 not_implemented，需下一轮单独接入。"
        )
        external_note.setProperty("role", "muted")
        external_note.setWordWrap(True)
        external_note.setMinimumWidth(0)
        external_note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        data_layout.addWidget(external_note)

        self.map_context_label = QLabel("QGIS 项目显示：未加载本插件数据")
        self.map_context_label.setProperty("role", "mapContext")
        self.map_context_label.setWordWrap(True)
        self.map_context_label.setMinimumWidth(0)
        self.map_context_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        data_layout.addWidget(self.map_context_label)

        boundary = QLabel(
            "数据边界：道路、建筑、水体、用地、铁路为公开 OSM 背景；候选走廊沿公开道路几何派生；"
            "设施身份、子管资源、状态、优先级、成本和 BOM 均为合成竞赛属性。"
        )
        boundary.setProperty("role", "boundary")
        boundary.setWordWrap(True)
        boundary.setMinimumWidth(0)
        boundary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        data_layout.addWidget(boundary)
        content.addWidget(self.data_card)

        self.task_card, task_layout = self._section(
            "02 · 任务预览与确认",
            "任务表必须先经过字段、ID 与数据集引用校验；任何输入变化都会让确认失效。",
        )
        self.task_controls = QWidget()
        task_controls_layout = QVBoxLayout(self.task_controls)
        task_controls_layout.setContentsMargins(0, 0, 0, 0)
        task_controls_layout.setSpacing(7)

        path_grid = QGridLayout()
        path_grid.setHorizontalSpacing(7)
        path_grid.setVerticalSpacing(7)
        self.path_edit = QLineEdit()
        self.path_edit.setMinimumWidth(0)
        self.path_edit.setPlaceholderText("先选择数据集，再选择 UTF-8 CSV 任务表")
        self.path_edit.setClearButtonEnabled(True)
        self.browse_button = QPushButton("浏览 CSV…")
        self.import_button = QPushButton("导入并校验")
        self.import_button.setProperty("buttonRole", "secondary")
        path_grid.addWidget(self.path_edit, 0, 0, 1, 2)
        path_grid.addWidget(self.browse_button, 1, 0)
        path_grid.addWidget(self.import_button, 1, 1)
        task_controls_layout.addLayout(path_grid)

        self.task_summary_label = QLabel("任务输入：未导入")
        self.task_summary_label.setProperty("role", "muted")
        self.task_summary_label.setWordWrap(True)
        task_controls_layout.addWidget(self.task_summary_label)

        self.preview_button = QPushButton("预览任务并生成确认指纹")
        self.preview_button.setProperty("buttonRole", "secondary")
        self.preview_button.setToolTip("校验当前任务表，并生成本次运行唯一指纹")
        task_controls_layout.addWidget(self.preview_button)

        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumWidth(0)
        self.preview_text.setMinimumHeight(108)
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setPlaceholderText("数据与任务通过校验后，在这里显示实际数量、排序和确认指纹。")
        task_controls_layout.addWidget(self.preview_text)
        task_layout.addWidget(self.task_controls)
        content.addWidget(self.task_card)

        self.run_card, run_layout = self._section(
            "03 · 运行",
            "按 high → medium → low、同级 task_id 升序执行；不制造假进度或人为延时。",
        )
        run_status_row = QHBoxLayout()
        run_status_row.addWidget(QLabel("运行状态"))
        self.status_label = QLabel("等待数据")
        self.status_label.setProperty("state", "idle")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        run_status_row.addWidget(self.status_label, 1)
        run_layout.addLayout(run_status_row)

        self.execute_button = QPushButton("确认并运行批量设计")
        self.execute_button.setProperty("buttonRole", "primary")
        self.execute_button.setEnabled(False)
        run_layout.addWidget(self.execute_button)

        self.block_reason_label = QLabel("执行阻止原因：尚未选择数据集")
        self.block_reason_label.setProperty("role", "blocking")
        self.block_reason_label.setWordWrap(True)
        run_layout.addWidget(self.block_reason_label)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(7)
        metrics.setVerticalSpacing(7)
        self.metric_labels: dict[str, QLabel] = {}
        for index, (key, title) in enumerate(
            (
                ("completed_direct", "直接成功"),
                ("completed_rerouted", "绕行成功"),
                ("needs_review", "待人工复核"),
                ("failed", "明确失败"),
            )
        ):
            label = QLabel(f"{title}\n—")
            label.setProperty("role", "metric")
            label.setAlignment(Qt.AlignCenter)
            self.metric_labels[key] = label
            metrics.addWidget(label, index // 2, index % 2)
        run_layout.addLayout(metrics)
        content.addWidget(self.run_card)

        self.review_card, review_layout = self._section(
            "04 · 结果复核",
            "按终态筛选；选择任务会定位地图。业务结论优先，底层路线与规则证据按需展开。",
        )
        review_controls = QGridLayout()
        review_controls.setHorizontalSpacing(7)
        review_controls.setVerticalSpacing(6)
        review_controls.addWidget(QLabel("状态筛选"), 0, 0)
        self.filter_combo = QComboBox()
        for label, value in (
            ("全部状态", "all"),
            ("直接成功", "completed_direct"),
            ("绕行成功", "completed_rerouted"),
            ("待人工复核", "needs_review"),
            ("明确失败", "failed"),
        ):
            self.filter_combo.addItem(label, value)
        review_controls.addWidget(self.filter_combo, 0, 1)
        review_controls.addWidget(QLabel("地图路线"), 1, 0)
        route_options = QWidget()
        route_layout = QVBoxLayout(route_options)
        route_layout.setContentsMargins(0, 0, 0, 0)
        route_layout.setSpacing(3)
        self.candidate_check = QCheckBox("约束前候选路线")
        self.candidate_check.setChecked(False)
        self.final_check = QCheckBox("最终 PASS 路线")
        self.final_check.setChecked(True)
        route_layout.addWidget(self.candidate_check)
        route_layout.addWidget(self.final_check)
        review_controls.addWidget(route_options, 1, 1)
        review_layout.addLayout(review_controls)

        self.result_count_label = QLabel("尚无运行结果")
        self.result_count_label.setProperty("role", "muted")
        review_layout.addWidget(self.result_count_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["任务", "优先级", "状态", "改路", "路线(m)", "冲突来源"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(230)
        self.table.setMinimumWidth(0)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        review_layout.addWidget(self.table)

        detail_group = QGroupBox("任务业务详情")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_title = QLabel("选择一条任务查看详情")
        self.detail_title.setProperty("role", "sectionTitle")
        self.detail_title.setWordWrap(True)
        detail_layout.addWidget(self.detail_title)
        self.detail_business = QLabel("")
        self.detail_business.setWordWrap(True)
        self.detail_business.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.detail_business)
        self.detail_issue = QLabel("")
        self.detail_issue.setWordWrap(True)
        self.detail_issue.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.detail_issue)
        self.detail_resource = QLabel("")
        self.detail_resource.setWordWrap(True)
        self.detail_resource.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.detail_resource)
        self.detail_outcome = QLabel("")
        self.detail_outcome.setWordWrap(True)
        self.detail_outcome.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.detail_outcome)

        self.technical_toggle = QToolButton()
        self.technical_toggle.setText("展开技术证据")
        self.technical_toggle.setToolTip("路线 ID、规则 ID、临时禁用集合与原始错误")
        self.technical_toggle.setCheckable(True)
        self.technical_toggle.setArrowType(Qt.RightArrow)
        self.technical_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        detail_layout.addWidget(self.technical_toggle)
        self.technical_text = QPlainTextEdit()
        self.technical_text.setReadOnly(True)
        self.technical_text.setMaximumHeight(145)
        self.technical_text.setVisible(False)
        detail_layout.addWidget(self.technical_text)
        # Compatibility alias for the original smoke probe; the visible business
        # summary above is now the primary task detail.
        self.detail_text = self.technical_text
        review_layout.addWidget(detail_group)
        content.addWidget(self.review_card)

        self.export_card, export_layout = self._section(
            "05 · 导出交付",
            "导出以真实 QGIS Layout/Atlas 事件为准；只有完整明确终态批次可生成图册。",
        )
        self.export_button = QPushButton("导出图册与 GeoPackage")
        self.export_button.setProperty("buttonRole", "success")
        self.export_button.setToolTip("导出完整设计图册，并刷新 GeoPackage 与配套校验清单")
        self.export_button.setEnabled(False)
        export_layout.addWidget(self.export_button)
        self.export_path_label = QLabel("尚无可导出结果")
        self.export_path_label.setProperty("role", "muted")
        self.export_path_label.setWordWrap(True)
        self.export_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        export_layout.addWidget(self.export_path_label)
        license_label = QLabel(
            "图册保留 © OpenStreetMap contributors / ODbL 1.0 署名，并标注“合成通信属性、竞赛样例、非正式施工图”。"
        )
        license_label.setProperty("role", "muted")
        license_label.setWordWrap(True)
        export_layout.addWidget(license_label)
        content.addWidget(self.export_card)
        content.addStretch(1)

        self.sample_button.clicked.connect(self.sample_requested.emit)
        self.browse_button.clicked.connect(self._browse)
        self.import_button.clicked.connect(
            lambda: self.import_requested.emit(self.path_edit.text().strip())
        )
        self.preview_button.clicked.connect(self.preview_requested.emit)
        self.execute_button.clicked.connect(
            lambda: self.execute_requested.emit(self._confirmed_fingerprint)
        )
        self.export_button.clicked.connect(self.export_requested.emit)
        self.filter_combo.currentIndexChanged.connect(
            lambda _index: self.filter_requested.emit(str(self.filter_combo.currentData()))
        )
        self.candidate_check.toggled.connect(self._emit_route_visibility)
        self.final_check.toggled.connect(self._emit_route_visibility)
        self.table.itemSelectionChanged.connect(self._focus_selection)
        self.path_edit.textChanged.connect(self._on_path_changed)
        self.technical_toggle.toggled.connect(self._toggle_technical)
        self._refresh_action_states()

    @staticmethod
    def _section(title: str, description: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setProperty("card", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(7)
        title_label = QLabel(title)
        title_label.setProperty("role", "sectionTitle")
        layout.addWidget(title_label)
        description_label = QLabel(description)
        description_label.setProperty("role", "muted")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        return frame, layout

    def _browse(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "选择批量任务 CSV",
            self.path_edit.text(),
            "CSV 文件 (*.csv)",
        )
        if path:
            self.path_edit.setText(path)

    def _on_path_changed(self, text: str) -> None:
        self.invalidate_confirmation()
        self.input_changed.emit(text.strip())

    def _focus_selection(self) -> None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return
        task_id = self.table.item(row, 0).data(Qt.UserRole) or self.table.item(row, 0).text()
        self._show_task_detail(str(task_id))
        self.focus_requested.emit(str(task_id))

    def _emit_route_visibility(self, *_args) -> None:
        self.route_visibility_requested.emit(
            self.candidate_check.isChecked(), self.final_check.isChecked()
        )

    def _toggle_technical(self, expanded: bool) -> None:
        self.technical_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.technical_text.setVisible(expanded)

    def configure_available_source(self, descriptor: dict) -> None:
        """Show a selectable source without activating or loading it."""

        self._descriptor = dict(descriptor)
        name = descriptor.get("name") or "内置样例"
        dataset_id = descriptor.get("dataset_id") or "未知 ID"
        self.dataset_meta_label.setText(
            f"可用内置样例：{name}\n数据集 ID：{dataset_id}\n"
            "状态：仅发现清单，尚未校验数据文件、尚未加载地图。"
        )
        self.dataset_source_label.setText(
            f"来源：{descriptor.get('source_summary', '公开 OSM 背景 + 合成通信属性')}\n"
            f"许可：{descriptor.get('attribution', '© OpenStreetMap contributors / ODbL 1.0')}"
        )
        self._refresh_action_states()

    def set_dataset(self, descriptor: dict, default_csv: str) -> None:
        """Activate one hash-verified dataset after an explicit user action."""

        self._descriptor = dict(descriptor)
        self._dataset_selected = True
        self.source_state_label.setText("已选择 · 文件哈希与数据合同通过")
        self.source_state_label.setProperty("state", "success")
        repolish(self.source_state_label)
        dataset_id = descriptor["dataset_id"]
        self.dataset_label.setText(
            f"当前操作数据集：{descriptor.get('name', dataset_id)}\nID：{dataset_id}"
        )
        counts = descriptor.get("counts", {})
        public_counts = descriptor.get("public_counts", {})
        self.dataset_meta_label.setText(
            "当前实际规模："
            f"{counts.get('nodes', '—')} 节点 / {counts.get('edges', '—')} 候选边 / "
            f"{counts.get('rooms', '—')} 合成机房 / {counts.get('sites', '—')} 合成接入设施\n"
            "公开背景："
            f"道路 {public_counts.get('roads', '—')} / 建筑 {public_counts.get('buildings', '—')} / "
            f"水体 {public_counts.get('water', '—')} / 用地 {public_counts.get('landuse', '—')} / "
            f"铁路 {public_counts.get('railways', '—')}"
        )
        self.dataset_source_label.setText(
            f"来源数据集：{descriptor.get('source_dataset_id', '—')}\n"
            f"许可与署名：{descriptor.get('attribution', '—')}"
        )
        self.path_edit.blockSignals(True)
        self.path_edit.setText(default_csv)
        self.path_edit.blockSignals(False)
        self.task_summary_label.setText("任务输入：尚未导入；路径仅在明确选择样例后填入。")
        self.preview_text.clear()
        self._confirmed_fingerprint = None
        self._run_gate_enabled = False
        self._export_gate_enabled = False
        self.clear_results()
        self.set_next_step("下一步：导入并校验任务表")
        self.set_block_reason("任务表尚未导入并确认")
        self._refresh_action_states()

    def clear_dataset(self, reason: str) -> None:
        self._dataset_selected = False
        self.source_state_label.setText("数据集加载失败")
        self.source_state_label.setProperty("state", "error")
        repolish(self.source_state_label)
        self.dataset_label.setText("当前操作数据集：无")
        self.dataset_meta_label.setText(reason)
        self.path_edit.blockSignals(True)
        self.path_edit.clear()
        self.path_edit.blockSignals(False)
        self.preview_text.clear()
        self._confirmed_fingerprint = None
        self._run_gate_enabled = False
        self._export_gate_enabled = False
        self.clear_results()
        self.set_map_context("QGIS 项目显示：未加载本插件数据", "error")
        self.set_next_step("修复数据错误后重新选择内置样例")
        self.set_block_reason("数据集未通过校验")
        self._refresh_action_states()

    def set_task_summary(self, summary: dict | None) -> None:
        if not summary:
            self.task_summary_label.setText("任务输入：未导入")
            return
        priorities = summary.get("priorities", {})
        self.task_summary_label.setText(
            f"已导入批次：{summary.get('batch_id', '—')} · 任务 {summary.get('task_count', 0)}\n"
            f"优先级分布：高 {priorities.get('high', 0)} / "
            f"中 {priorities.get('medium', 0)} / 低 {priorities.get('low', 0)}"
        )

    def invalidate_confirmation(self, *_args) -> None:
        self._confirmed_fingerprint = None
        self._run_gate_enabled = False
        self._export_gate_enabled = False
        if self._dataset_selected:
            self.preview_text.setPlainText("输入已变化；旧确认已失效。请重新导入并预览。")
            self.set_next_step("下一步：重新导入并预览当前任务表")
            self.set_block_reason("输入变化后尚未重新预览确认")
        self._refresh_action_states()

    def set_preview(self, text: str, fingerprint: str | None) -> None:
        self.preview_text.setPlainText(text)
        self._confirmed_fingerprint = fingerprint
        self._run_gate_enabled = bool(fingerprint)
        self._export_gate_enabled = False
        if fingerprint:
            self.set_next_step("下一步：核对以上摘要，然后确认并运行")
            self.set_block_reason("")
        self._refresh_action_states()

    def set_status(self, text: str, state: str = "idle") -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        repolish(self.status_label)

    def set_busy(self, busy: bool, stage: str = "") -> None:
        self._busy = bool(busy)
        if busy:
            stage_text = {
                "dataset": "正在校验并加载数据…",
                "import": "正在校验任务表…",
                "run": "正在运行确定性批量规划…",
                "export": "正在由 QGIS Layout/Atlas 导出…",
            }.get(stage, "正在处理…")
            self.set_status(stage_text, "running")
        self._refresh_action_states()

    def set_run_gate(self, enabled: bool, reason: str = "") -> None:
        self._run_gate_enabled = bool(enabled)
        self.set_block_reason(reason)
        self._refresh_action_states()

    def set_block_reason(self, reason: str) -> None:
        self.block_reason_label.setText(
            f"执行阻止原因：{reason}" if reason else "执行条件已满足：将使用上方已确认的数据与任务"
        )
        self.block_reason_label.setVisible(True)

    def set_next_step(self, text: str) -> None:
        self.next_step_label.setText(text)

    def show_stage(self, stage: str) -> None:
        cards = {
            "data": self.data_card,
            "tasks": self.task_card,
            "run": self.run_card,
            "review": self.review_card,
            "export": self.export_card,
        }
        card = cards.get(stage)
        if card is not None:
            self.scroll.ensureWidgetVisible(card, 0, 18)

    def set_map_context(self, text: str, state: str = "idle") -> None:
        self.map_context_label.setText(text)
        self.map_context_label.setProperty("state", state)
        repolish(self.map_context_label)

    def set_results(self, tasks: list[dict]) -> None:
        self._results = list(tasks)
        self._results_by_task_id = {
            item["task"]["task_id"]: item for item in self._results
        }
        self._has_results = True
        counts = Counter(item["status"] for item in self._results)
        for key, label in self.metric_labels.items():
            label.setText(f"{STATUS_META[key]['label']}\n{counts.get(key, 0)}")
        self.filter_results(str(self.filter_combo.currentData()))
        self.set_next_step("下一步：按状态复核；选择任务可定位地图并查看业务详情")
        self._refresh_action_states()

    def clear_results(self) -> None:
        self._results = []
        self._results_by_task_id = {}
        self._has_results = False
        if hasattr(self, "table"):
            self.table.setRowCount(0)
            self.result_count_label.setText("尚无运行结果")
            self._clear_detail()
            for key, label in self.metric_labels.items():
                label.setText(f"{STATUS_META[key]['label']}\n—")
        self._refresh_action_states()

    @staticmethod
    def _paint_item(item: QTableWidgetItem, meta: dict) -> None:
        item.setForeground(QBrush(QColor(meta["foreground"])))
        item.setBackground(QBrush(QColor(meta["background"])))

    def filter_results(self, status: str) -> None:
        allowed = {"all", *STATUS_META}
        if status not in allowed:
            raise ValueError(f"未知批量状态筛选：{status}")
        tasks = (
            self._results
            if status == "all"
            else [item for item in self._results if item["status"] == status]
        )
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(tasks))
        for row, result in enumerate(tasks):
            task = result["task"]
            status_meta = STATUS_META[result["status"]]
            priority_meta = PRIORITY_META[task["priority"]]
            values = (
                task["task_id"],
                priority_meta["label"],
                status_meta["label"],
                (
                    f"{result.get('repair_count', 0)} 次"
                    if result.get("repair_count", 0)
                    else "—"
                ),
                "—" if not result.get("bom") else f"{result['bom']['total_length_m']:.2f}",
                ", ".join(result.get("caused_by_task_ids", [])) or "—",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, task["task_id"])
                item.setToolTip(str(value))
                if column in {1, 2, 3, 4}:
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 1:
                    self._paint_item(item, priority_meta)
                elif column == 2:
                    self._paint_item(item, status_meta)
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 29)
        self.table.blockSignals(False)
        self.result_count_label.setText(f"当前显示 {len(tasks)} / {len(self._results)} 个任务")
        self._clear_detail()
        self._update_compact_columns()

    def _clear_detail(self) -> None:
        self.detail_title.setText("选择一条任务查看详情")
        self.detail_business.clear()
        self.detail_issue.clear()
        self.detail_resource.clear()
        self.detail_outcome.clear()
        self.technical_text.clear()
        self.technical_toggle.setChecked(False)

    def _show_task_detail(self, task_id: str) -> None:
        result = self._results_by_task_id.get(task_id)
        if result is None:
            self._clear_detail()
            return
        task = result["task"]
        status = result["status"]
        status_label = STATUS_META[status]["label"]
        candidate = result.get("candidate_route") or {}
        final = result.get("final_route") or {}
        validations = result.get("validation_history") or []
        violations = [
            item
            for validation in validations
            for item in validation.get("violations", [])
        ]
        causes = result.get("caused_by_task_ids") or []
        changes = result.get("resource_changes") or []
        bom = result.get("bom") or {}

        self.detail_title.setText(
            f"{task_id} · {status_label} · {task['site_id']} → {task['preferred_room_id']}"
        )
        if status == "completed_direct":
            business = "业务结论：候选路线首次校核通过，已按最终路线提交合成子管预占。"
        elif status == "completed_rerouted":
            business = (
                "业务结论：候选路线遇到可解释约束，系统执行 "
                f"{result.get('repair_count', 0)} 次有界改路；改路后校核通过并提交资源。"
            )
        elif status == "needs_review":
            business = "业务结论：现有信息不足以自动裁决，任务已分流给人工；未生成有效 BOM，也未扣减资源。"
        else:
            business = "业务结论：没有可行的已校核路线，任务明确失败；未伪造 PASS/BOM，也未扣减资源。"
        self.detail_business.setText(business)

        if violations:
            issue_parts = []
            for item in violations:
                rule_id = str(item.get("rule_id") or "UNKNOWN")
                label = _RULE_LABELS.get(rule_id, item.get("message") or "规则问题")
                issue_parts.append(f"{label}（{item.get('asset_id') or '无资产 ID'}）")
            issue_text = "；".join(issue_parts)
        else:
            issue_text = "无约束冲突，首次校核通过"
        cause_text = "、".join(causes) if causes else "无前序任务影响"
        self.detail_issue.setText(f"问题与来源：{issue_text}。冲突来源任务：{cause_text}。")

        if changes:
            preview = "；".join(
                f"{item['asset_id']} {item['free_subduct_before']}→{item['free_subduct_after']}"
                for item in changes[:5]
            )
            suffix = f"；另有 {len(changes) - 5} 段" if len(changes) > 5 else ""
            resource_text = f"最终 PASS 后预占 {len(changes)} 段：{preview}{suffix}。"
        else:
            resource_text = "资源变化：0 段（失败/待复核任务不扣减）。"
        self.detail_resource.setText(resource_text)

        if bom:
            outcome = (
                f"处理结果：路线 {bom['total_length_m']:.2f} m；建议光缆 "
                f"{bom['recommended_cable_length_m']:.2f} m；规格 {task['cable_fiber_cores']} 芯；"
                f"自动改路 {result.get('repair_count', 0)} 次。"
            )
        else:
            outcome = f"处理结果：{result.get('error') or '没有可批准结果'}"
        self.detail_outcome.setText(outcome)

        violation_lines = [
            f"  - {item.get('rule_id')} | asset={item.get('asset_id') or '-'} | "
            f"message={item.get('message') or '-'} | caused_by={','.join(item.get('caused_by_task_ids', [])) or '-'}"
            for item in violations
        ]
        technical = [
            f"task_id={task_id}",
            f"status={status}",
            f"candidate_route={','.join(candidate.get('edge_ids', [])) or '-'}",
            f"final_route={','.join(final.get('edge_ids', [])) or '-'}",
            f"temporary_forbidden={','.join(result.get('temporary_forbidden_asset_ids', [])) or '-'}",
            f"error={result.get('error') or '-'}",
            "validation_evidence:",
            *(violation_lines or ["  - PASS / no violations"]),
        ]
        self.technical_text.setPlainText("\n".join(technical))

    def select_task(self, task_id: str) -> bool:
        """Select a currently visible row; useful for keyboard/UI automation."""

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == task_id:
                self.table.selectRow(row)
                self.table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                return True
        return False

    def set_export_enabled(self, enabled: bool) -> None:
        self._export_gate_enabled = bool(enabled)
        self._refresh_action_states()

    def set_export_path(self, path: str | None) -> None:
        if path:
            self.export_path_label.setText(
                f"已生成：{path}\n同时输出 GeoPackage、CSV/GeoJSON、资源快照、BOM、日志与校验清单。"
            )
            self.set_next_step("导出完成：请打开图册和 GeoPackage 进行人工复核")
        else:
            self.export_path_label.setText("尚无可导出结果")

    def _refresh_action_states(self) -> None:
        available = not self._busy
        self.sample_button.setEnabled(available)
        self.task_controls.setEnabled(self._dataset_selected and available)
        self.execute_button.setEnabled(
            self._dataset_selected and self._run_gate_enabled and available
        )
        self.review_card.setEnabled(self._has_results and available)
        self.export_button.setEnabled(
            self._has_results and self._export_gate_enabled and available
        )

    def _update_compact_columns(self) -> None:
        if not hasattr(self, "table"):
            return
        compact = self.width() < 510
        very_narrow = self.width() < 400
        self.table.setColumnHidden(3, compact)
        self.table.setColumnHidden(5, compact)
        self.table.setColumnHidden(4, very_narrow)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API.
        super().resizeEvent(event)
        self._update_compact_columns()
