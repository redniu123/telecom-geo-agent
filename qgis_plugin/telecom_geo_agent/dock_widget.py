"""Qt widgets for the right-side conversational Agent Dock."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QKeyEvent
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("通信工程 Agent · 离线 P0")
        title.setObjectName("AgentTitle")
        subtitle = QLabel("确定性规划 · 合成测试数据 · 无模型 / 无在线服务")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("AgentSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

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
        self.setWidget(root)

        self._send_button.clicked.connect(self._emit_input)
        self._input.send_requested.connect(self._emit_input)
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
            QLabel#AgentStatus { color: #9ca9ba; }
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
