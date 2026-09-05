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
        self.setMinimumWidth(360)

        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        title = QLabel("通信工程 Agent · 离线设计")
        title.setObjectName("AgentTitle")
        subtitle = QLabel("参数化规划 · 可解释校核 · 公开背景与合成通信属性")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("AgentSubtitle")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.setObjectName("AgentTabs")
        chat_tab = QWidget()
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
        self._send_button.setDefault(True)
        send_row.addWidget(self._status, 1)
        send_row.addWidget(self._send_button)
        layout.addLayout(send_row)
        tabs.addTab(chat_tab, "对话式 P0")

        competition_tab = QWidget()
        competition_layout = QVBoxLayout(competition_tab)
        competition_layout.setContentsMargins(4, 8, 4, 4)
        competition_layout.setSpacing(8)
        boundary = QLabel(
            "公开 OSM 仅作地理背景；站点、候选通道身份、容量、状态和 BOM "
            "均为竞赛样例的派生/合成数据。"
        )
        boundary.setWordWrap(True)
        boundary.setObjectName("DataBoundary")
        competition_layout.addWidget(boundary)

        workflow_hint = QLabel("① 选择参数   →   ② 预览确认   →   ③ 执行并导出")
        workflow_hint.setObjectName("WorkflowHint")
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
        self._scenario_hint.setWordWrap(True)
        competition_layout.addWidget(self._scenario_hint)

        buttons = QHBoxLayout()
        self._preview_button = QPushButton("1. 预览参数")
        self._preview_button.setObjectName("PreviewButton")
        self._preview_button.setToolTip("校验字段并生成本次参数指纹")
        self._execute_button = QPushButton("2. 确认并执行")
        self._execute_button.setObjectName("ExecuteButton")
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
        self._export_button.setToolTip("仅在最终校核 PASS 且存在 BOM 时可用")
        self._export_button.setEnabled(False)
        export_row.addWidget(self._competition_status, 1)
        export_row.addWidget(self._export_button)
        competition_layout.addLayout(export_row)
        tabs.addTab(competition_tab, "参数化设计")
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
        self.setStyleSheet(
            """
            QDockWidget { color: #d7dde8; }
            QWidget { background: #171a21; color: #d7dde8; }
            QLabel#AgentTitle { font-size: 17px; font-weight: 650; color: #f3f6fb; }
            QLabel#AgentSubtitle { color: #8f9bad; font-size: 11px; }
            QLabel#DataBoundary { color: #e3bd67; background: #30291c; border: 1px solid #66542a; border-radius: 6px; padding: 7px; }
            QLabel#WorkflowHint { color: #8fc7ec; background: #182735; border-radius: 6px; padding: 7px; font-weight: 600; }
            QLabel#ScenarioHint { color: #aeb9c8; background: #20252e; border-left: 3px solid #3189c9; padding: 7px; }
            QLabel#AgentStatus { color: #9ca9ba; }
            QLabel#CompetitionStatus { background: #20252e; border-radius: 9px; padding: 4px 8px; font-weight: 600; }
            QTabWidget::pane { border: 1px solid #313947; border-radius: 7px; top: -1px; }
            QTabBar::tab { background: #20252e; color: #9faaba; border: 1px solid #313947; padding: 7px 12px; }
            QTabBar::tab:selected { background: #193b57; color: #f2f7fb; border-bottom-color: #3189c9; }
            QPlainTextEdit {
                background: #10131a; border: 1px solid #343b49;
                border-radius: 7px; padding: 7px; color: #eef2f8;
            }
            QPushButton {
                background: #252b36; border: 1px solid #3c4656;
                border-radius: 6px; padding: 6px 9px;
            }
            QPushButton:hover { background: #303847; }
            QPushButton:disabled { color: #687282; background: #20242c; }
            QPushButton#SendButton { background: #1769d2; border-color: #2780ed; font-weight: 600; }
            QPushButton#ExecuteButton { background: #1769d2; border-color: #2780ed; font-weight: 600; }
            QPushButton#PreviewButton { background: #214057; border-color: #376786; font-weight: 600; }
            QPushButton#ExportButton:enabled { background: #1f6649; border-color: #328462; font-weight: 600; }
            QComboBox, QSpinBox, QLineEdit { background: #10131a; border: 1px solid #343b49; border-radius: 5px; padding: 5px; }
            QComboBox:focus, QSpinBox:focus, QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #3189c9; }
            QCheckBox { spacing: 7px; }
            QFrame[messageKind="info"] { background: #222833; border-radius: 8px; }
            QFrame[messageKind="route"] { background: #1e3145; border: 1px solid #315c83; border-radius: 8px; }
            QFrame[messageKind="warning"] { background: #40341e; border: 1px solid #80652a; border-radius: 8px; }
            QFrame[messageKind="repair"] { background: #34294a; border: 1px solid #624a8b; border-radius: 8px; }
            QFrame[messageKind="success"] { background: #1e3b2e; border: 1px solid #317357; border-radius: 8px; }
            QFrame[messageKind="bom"] { background: #24362f; border: 1px solid #3d705b; border-radius: 8px; }
            QFrame[messageKind="map"] { background: #243746; border: 1px solid #416d8b; border-radius: 8px; }
            QFrame[messageKind="error"] { background: #482426; border: 1px solid #8b3e43; border-radius: 8px; }
            QFrame[messageRole="user"] { background: #193a63; border: 1px solid #2866a4; border-radius: 8px; }
            """
        )

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
        self._dataset.addItem("上海公开 GIS 竞赛样例 v1", catalog["dataset_id"])
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

    def set_export_enabled(self, enabled: bool) -> None:
        self._export_button.setEnabled(enabled)
