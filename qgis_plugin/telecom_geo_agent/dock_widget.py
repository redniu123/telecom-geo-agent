"""Qt widgets for the right-side conversational Agent Dock."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QKeyEvent
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDockWidget,
)

from .batch_widget import BatchDesignWidget
from .ui_style import APP_STYLE_SHEET, repolish


class MessageInput(QPlainTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API.
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (
            event.modifiers() & Qt.ControlModifier
        ):
            self.send_requested.emit()
            return
        super().keyPressEvent(event)


class AgentDockWidget(QDockWidget):
    """Compact chat surface with deterministic command shortcuts."""

    send_requested = pyqtSignal(str)
    command_requested = pyqtSignal(str)
    competition_preview_requested = pyqtSignal(object)
    competition_execute_requested = pyqtSignal(object, object)
    competition_export_requested = pyqtSignal()
    batch_import_requested = pyqtSignal(str)
    batch_sample_requested = pyqtSignal()
    batch_input_changed = pyqtSignal(str)
    batch_preview_requested = pyqtSignal()
    batch_execute_requested = pyqtSignal(object)
    batch_export_requested = pyqtSignal()
    batch_filter_requested = pyqtSignal(str)
    batch_focus_requested = pyqtSignal(str)
    batch_route_visibility_requested = pyqtSignal(bool, bool)

    QUICK_COMMANDS = (
        ("运行示例规划", "从A到B规划24芯光缆"),
        ("重新运行", "重新运行"),
        ("当前状态", "当前状态"),
        ("解释失败", "解释失败"),
        ("定位 D017", "定位问题段"),
        ("第一次路线", "显示第一次路线"),
        ("最终路线", "显示最终路线"),
        ("查看 BOM", "查看 BOM"),
        ("清空对话", "清空对话"),
        ("帮助", "帮助"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__("通信工程 Agent", parent)
        self.setObjectName("TelecomGeoAgentDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(340)

        root = QWidget(self)
        root.setMinimumWidth(0)
        root.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        title = QLabel("通信工程设计 Agent")
        title.setObjectName("AgentTitle")
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        subtitle = QLabel("QGIS 侧边工作台 · 批量接入 / 单任务回归 / 可解释校核")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("AgentSubtitle")
        subtitle.setMinimumWidth(0)
        subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.setObjectName("AgentTabs")
        tabs.setMinimumWidth(0)
        tabs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        tabs.setElideMode(Qt.ElideRight)
        tabs.setUsesScrollButtons(True)
        tabs.tabBar().setExpanding(False)
        self._tabs = tabs
        chat_tab = QWidget()
        chat_tab.setMinimumWidth(0)
        chat_tab.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        layout = QVBoxLayout(chat_tab)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._message_host = QWidget()
        self._message_layout = QVBoxLayout(self._message_host)
        self._message_layout.setContentsMargins(2, 2, 2, 2)
        self._message_layout.setSpacing(8)
        self._message_layout.addStretch(1)
        self._scroll.setWidget(self._message_host)
        layout.addWidget(self._scroll, 1)

        quick_layout = QGridLayout()
        self._result_buttons: list[QPushButton] = []
        for index, (label, command) in enumerate(self.QUICK_COMMANDS):
            button = QPushButton(label)
            button.setProperty("quickAction", True)
            button.clicked.connect(
                lambda _checked=False, value=command: self.command_requested.emit(value)
            )
            quick_layout.addWidget(button, index // 2, index % 2)
            if command in {
                "重新运行",
                "解释失败",
                "定位问题段",
                "显示第一次路线",
                "显示最终路线",
                "查看 BOM",
            }:
                self._result_buttons.append(button)
        layout.addLayout(quick_layout)

        self._input = MessageInput()
        self._input.setPlaceholderText(
            "输入：从A到B规划24芯光缆\nCtrl+Enter 发送"
        )
        self._input.setMinimumHeight(76)
        self._input.setMaximumHeight(130)
        layout.addWidget(self._input)

        send_row = QHBoxLayout()
        self._status = QLabel("就绪")
        self._status.setObjectName("AgentStatus")
        self._send_button = QPushButton("发送")
        self._send_button.setObjectName("SendButton")
        self._send_button.setProperty("buttonRole", "primary")
        self._send_button.setDefault(True)
        send_row.addWidget(self._status, 1)
        send_row.addWidget(self._send_button)
        layout.addLayout(send_row)

        competition_tab = QWidget()
        competition_tab.setMinimumWidth(0)
        competition_tab.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        competition_layout = QVBoxLayout(competition_tab)
        competition_layout.setContentsMargins(4, 8, 4, 4)
        competition_layout.setSpacing(8)
        boundary = QLabel(
            "公开 OSM 仅作地理背景；站点、候选通道身份、容量、状态和 BOM "
            "均为竞赛样例的派生/合成数据。"
        )
        boundary.setWordWrap(True)
        boundary.setObjectName("DataBoundary")
        boundary.setProperty("role", "boundary")
        competition_layout.addWidget(boundary)

        workflow_hint = QLabel("① 选择参数   →   ② 预览确认   →   ③ 执行并导出")
        workflow_hint.setObjectName("WorkflowHint")
        workflow_hint.setProperty("role", "nextStep")
        workflow_hint.setAlignment(Qt.AlignCenter)
        competition_layout.addWidget(workflow_hint)

        form = QFormLayout()
        self._dataset = QComboBox()
        self._scenario = QComboBox()
        self._start_site = QComboBox()
        self._end_site = QComboBox()
        self._fiber_cores = QSpinBox()
        self._fiber_cores.setRange(1, 576)
        self._fiber_cores.setValue(24)
        self._prefer_existing = QCheckBox("优先使用已有管道")
        self._prefer_existing.setChecked(True)
        self._forbidden_assets = QLineEdit()
        self._forbidden_assets.setPlaceholderText("例如 C1-009；多个 ID 用逗号分隔")
        form.addRow("数据集", self._dataset)
        form.addRow("场景", self._scenario)
        form.addRow("起点", self._start_site)
        form.addRow("终点", self._end_site)
        form.addRow("光缆芯数", self._fiber_cores)
        form.addRow("偏好", self._prefer_existing)
        form.addRow("禁用资产", self._forbidden_assets)
        competition_layout.addLayout(form)

        self._scenario_hint = QLabel()
        self._scenario_hint.setObjectName("ScenarioHint")
        self._scenario_hint.setProperty("role", "mapContext")
        self._scenario_hint.setWordWrap(True)
        competition_layout.addWidget(self._scenario_hint)

        buttons = QHBoxLayout()
        self._preview_button = QPushButton("1. 预览参数")
        self._preview_button.setObjectName("PreviewButton")
        self._preview_button.setProperty("buttonRole", "secondary")
        self._preview_button.setToolTip("校验字段并生成本次参数指纹")
        self._execute_button = QPushButton("2. 确认并执行")
        self._execute_button.setObjectName("ExecuteButton")
        self._execute_button.setProperty("buttonRole", "primary")
        self._execute_button.setToolTip("仅执行当前已预览且未变化的参数")
        self._execute_button.setEnabled(False)
        buttons.addWidget(self._preview_button)
        buttons.addWidget(self._execute_button)
        competition_layout.addLayout(buttons)

        self._competition_preview = QPlainTextEdit()
        self._competition_preview.setReadOnly(True)
        self._competition_preview.setMinimumHeight(150)
        self._competition_preview.setPlaceholderText("先预览结构化参数；修改任一字段后必须重新预览。")
        competition_layout.addWidget(self._competition_preview, 1)

        export_row = QHBoxLayout()
        self._competition_status = QLabel("等待参数")
        self._competition_status.setObjectName("CompetitionStatus")
        self._export_button = QPushButton("导出 A3 标准图纸 PDF")
        self._export_button.setObjectName("ExportButton")
        self._export_button.setProperty("buttonRole", "success")
        self._export_button.setToolTip("仅在最终校核 PASS 且存在 BOM 时可用")
        self._export_button.setEnabled(False)
        export_row.addWidget(self._competition_status, 1)
        export_row.addWidget(self._export_button)
        competition_layout.addLayout(export_row)
        self._batch = BatchDesignWidget()
        tabs.addTab(self._batch, "批量设计")
        tabs.addTab(competition_tab, "单任务")
        tabs.addTab(chat_tab, "P0 对话")
        tabs.setTabToolTip(0, "批量接入设计与自动成册（主要工作流）")
        tabs.setTabToolTip(1, "原参数化单任务回归入口")
        tabs.setTabToolTip(2, "原冻结 P0 对话式回归入口")
        tabs.setCurrentWidget(self._batch)
        self._batch.sample_requested.connect(self.batch_sample_requested.emit)
        self._batch.input_changed.connect(self.batch_input_changed.emit)
        self._batch.import_requested.connect(self.batch_import_requested.emit)
        self._batch.preview_requested.connect(self.batch_preview_requested.emit)
        self._batch.execute_requested.connect(self.batch_execute_requested.emit)
        self._batch.export_requested.connect(self.batch_export_requested.emit)
        self._batch.filter_requested.connect(self.batch_filter_requested.emit)
        self._batch.focus_requested.connect(self.batch_focus_requested.emit)
        self._batch.route_visibility_requested.connect(self.batch_route_visibility_requested.emit)
        root_layout.addWidget(tabs, 1)
        self.setWidget(root)

        self._send_button.clicked.connect(self._emit_input)
        self._input.send_requested.connect(self._emit_input)
        self._preview_button.clicked.connect(self._emit_competition_preview)
        self._execute_button.clicked.connect(self._emit_competition_execute)
        self._export_button.clicked.connect(self.competition_export_requested.emit)
        self._scenario.currentIndexChanged.connect(self._apply_scenario_defaults)
        for signal in (
            self._dataset.currentIndexChanged,
            self._start_site.currentIndexChanged,
            self._end_site.currentIndexChanged,
            self._fiber_cores.valueChanged,
            self._prefer_existing.toggled,
            self._forbidden_assets.textChanged,
        ):
            signal.connect(self._invalidate_competition_confirmation)
        self._confirmed_fingerprint: str | None = None
        self._scenario_defaults: dict[str, dict] = {}
        self._apply_style()
        self.append_message(
            "assistant",
            "输入“从A到B规划24芯光缆”，我会真实运行冻结的 P0 Workflow。",
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(APP_STYLE_SHEET)

    def _emit_input(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self.send_requested.emit(text)

    def append_message(self, role: str, text: str, kind: str = "info") -> None:
        frame = QFrame()
        frame.setProperty("messageKind", kind)
        frame.setProperty("messageRole", role)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        card_layout = QVBoxLayout(frame)
        card_layout.setContentsMargins(10, 8, 10, 8)
        label = QLabel(("你\n" if role == "user" else "Agent\n") + text)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(label)
        self._message_layout.insertWidget(self._message_layout.count() - 1, frame)
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        )

    def clear_conversation(self) -> None:
        while self._message_layout.count() > 1:
            item = self._message_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_status(self, text: str, state: str = "idle") -> None:
        colors = {
            "idle": "#9ca9ba",
            "running": "#e1b85b",
            "success": "#65c18c",
            "error": "#ef7379",
        }
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {colors.get(state, colors['idle'])};")

    def set_actions_enabled(self, enabled: bool) -> None:
        for button in self._result_buttons:
            button.setEnabled(enabled)

    def configure_competition(self, catalog: dict) -> None:
        self._scenario_defaults = dict(catalog["scenarios"])
        self._dataset.clear()
        self._dataset.addItem("内置单任务回归样例 · 上海公开 GIS", catalog["dataset_id"])
        self._scenario.blockSignals(True)
        self._scenario.clear()
        for scenario_id, scenario in catalog["scenarios"].items():
            self._scenario.addItem(scenario["name"], scenario_id)
        self._scenario.blockSignals(False)
        self._start_site.clear()
        self._start_site.addItem("A · 样例机房", "A")
        self._start_site.addItem("B · 样例基站", "B")
        self._end_site.clear()
        self._end_site.addItem("A · 样例机房", "A")
        self._end_site.addItem("B · 样例基站", "B")
        self._apply_scenario_defaults()

    def _apply_scenario_defaults(self, _index: int = -1) -> None:
        scenario_id = self._scenario.currentData()
        scenario = self._scenario_defaults.get(scenario_id)
        if not scenario:
            return
        self._start_site.setCurrentIndex(self._start_site.findData(scenario["start_site_id"]))
        self._end_site.setCurrentIndex(self._end_site.findData(scenario["end_site_id"]))
        self._fiber_cores.setValue(scenario["fiber_cores"])
        self._prefer_existing.setChecked(scenario["prefer_existing_duct"])
        self._forbidden_assets.setText("，".join(scenario["forbidden_asset_ids"]))
        expected = "成功" if scenario.get("expected_status") == "completed" else "明确失败"
        self._scenario_hint.setText(
            f"场景说明：{scenario['description']}\n预期验证结果：{expected}（以实际执行结果为准）"
        )
        self._invalidate_competition_confirmation()

    def _competition_parameters(self) -> dict:
        forbidden = [
            value.strip()
            for value in self._forbidden_assets.text().replace("，", ",").split(",")
            if value.strip()
        ]
        return {
            "dataset_id": self._dataset.currentData(),
            "scenario_id": self._scenario.currentData(),
            "start_site_id": self._start_site.currentData(),
            "end_site_id": self._end_site.currentData(),
            "fiber_cores": self._fiber_cores.value(),
            "prefer_existing_duct": self._prefer_existing.isChecked(),
            "forbidden_asset_ids": forbidden,
        }

    def _invalidate_competition_confirmation(self, *_args) -> None:
        self._confirmed_fingerprint = None
        self._execute_button.setEnabled(False)
        self._export_button.setEnabled(False)

    def _emit_competition_preview(self) -> None:
        self.competition_preview_requested.emit(self._competition_parameters())

    def _emit_competition_execute(self) -> None:
        self.competition_execute_requested.emit(
            self._competition_parameters(), self._confirmed_fingerprint
        )

    def set_competition_preview(self, text: str, fingerprint: str | None) -> None:
        self._competition_preview.setPlainText(text)
        self._confirmed_fingerprint = fingerprint
        self._execute_button.setEnabled(bool(fingerprint))

    def set_competition_status(self, text: str, state: str = "idle") -> None:
        colors = {
            "idle": "#9ca9ba",
            "running": "#e1b85b",
            "success": "#65c18c",
            "error": "#ef7379",
        }
        self._competition_status.setText(text)
        self._competition_status.setStyleSheet(
            f"color: {colors.get(state, colors['idle'])};"
        )
        self._competition_status.setProperty("state", state)
        repolish(self._competition_status)

    def set_export_enabled(self, enabled: bool) -> None:
        self._export_button.setEnabled(enabled)

    def configure_batch(self, descriptor: dict) -> None:
        self._batch.configure_available_source(descriptor)

    def set_batch_dataset(self, descriptor: dict, default_csv: str) -> None:
        self._batch.set_dataset(descriptor, default_csv)

    def clear_batch_dataset(self, reason: str) -> None:
        self._batch.clear_dataset(reason)

    def batch_csv_path(self) -> str:
        return self._batch.path_edit.text().strip()

    def set_batch_preview(self, text: str, fingerprint: str | None) -> None:
        self._batch.set_preview(text, fingerprint)

    def set_batch_status(self, text: str, state: str = "idle") -> None:
        self._batch.set_status(text, state)

    def set_batch_busy(self, busy: bool, stage: str = "") -> None:
        self._batch.set_busy(busy, stage)

    def set_batch_task_summary(self, summary: dict | None) -> None:
        self._batch.set_task_summary(summary)

    def set_batch_run_gate(self, enabled: bool, reason: str = "") -> None:
        self._batch.set_run_gate(enabled, reason)

    def set_batch_map_context(self, text: str, state: str = "idle") -> None:
        self._batch.set_map_context(text, state)

    def show_batch_stage(self, stage: str) -> None:
        self._batch.show_stage(stage)

    def set_batch_results(self, tasks: list[dict]) -> None:
        self._batch.set_results(tasks)

    def clear_batch_results(self) -> None:
        self._batch.clear_results()

    def filter_batch_results(self, status: str) -> None:
        self._batch.filter_results(status)

    def set_batch_export_enabled(self, enabled: bool) -> None:
        self._batch.set_export_enabled(enabled)

    def set_batch_export_path(self, path: str | None) -> None:
        self._batch.set_export_path(path)
