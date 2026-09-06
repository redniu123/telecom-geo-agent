"""QGIS batch-design tab: import, confirm, filter, locate and export."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BatchDesignWidget(QWidget):
    import_requested = pyqtSignal(str)
    preview_requested = pyqtSignal()
    execute_requested = pyqtSignal(object)
    export_requested = pyqtSignal()
    filter_requested = pyqtSignal(str)
    focus_requested = pyqtSignal(str)
    route_visibility_requested = pyqtSignal(bool, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        boundary = QLabel("真实公开 OSM 仅作背景；设施、候选通道身份、子管资源、状态与成本均为合成竞赛属性。单进程、固定排序、最终 PASS 后预占、每任务最多改路一次。")
        boundary.setWordWrap(True)
        boundary.setObjectName("DataBoundary")
        layout.addWidget(boundary)
        self.dataset_label = QLabel("数据集：等待运行时")
        self.dataset_label.setWordWrap(True)
        layout.addWidget(self.dataset_label)

        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择 UTF-8 CSV 批量任务表")
        browse = QPushButton("浏览")
        import_button = QPushButton("导入并校验")
        file_row.addWidget(self.path_edit, 1)
        file_row.addWidget(browse)
        file_row.addWidget(import_button)
        layout.addLayout(file_row)

        action_row = QHBoxLayout()
        self.preview_button = QPushButton("1. 预览批次")
        self.execute_button = QPushButton("2. 确认并运行")
        self.execute_button.setEnabled(False)
        self.export_button = QPushButton("3. 导出完整图册")
        self.export_button.setEnabled(False)
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.execute_button)
        action_row.addWidget(self.export_button)
        layout.addLayout(action_row)

        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(112)
        self.preview_text.setPlaceholderText("导入 CSV 后预览字段、排序和确认指纹。")
        layout.addWidget(self.preview_text)

        result_row = QHBoxLayout()
        self.status_label = QLabel("等待导入")
        self.filter_combo = QComboBox()
        for label, value in (
            ("全部状态", "all"),
            ("直接成功", "completed_direct"),
            ("绕行成功", "completed_rerouted"),
            ("待人工复核", "needs_review"),
            ("明确失败", "failed"),
        ):
            self.filter_combo.addItem(label, value)
        result_row.addWidget(self.status_label, 1)
        result_row.addWidget(QLabel("筛选"))
        result_row.addWidget(self.filter_combo)
        layout.addLayout(result_row)

        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel("路线图层"))
        self.candidate_check = QCheckBox("约束前候选路线")
        self.candidate_check.setChecked(False)
        self.final_check = QCheckBox("最终 PASS 路线")
        self.final_check.setChecked(True)
        layer_row.addWidget(self.candidate_check)
        layer_row.addWidget(self.final_check)
        layer_row.addStretch(1)
        layout.addLayout(layer_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["任务", "优先级", "状态", "改路", "路线(m)", "冲突来源"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(150)
        self.detail_text.setPlaceholderText("选择任务后显示候选/最终路线、冲突因果与资源预占前后值。")
        layout.addWidget(self.detail_text)

        browse.clicked.connect(self._browse)
        import_button.clicked.connect(lambda: self.import_requested.emit(self.path_edit.text().strip()))
        self.preview_button.clicked.connect(self.preview_requested.emit)
        self.execute_button.clicked.connect(lambda: self.execute_requested.emit(self._confirmed_fingerprint))
        self.export_button.clicked.connect(self.export_requested.emit)
        self.filter_combo.currentIndexChanged.connect(lambda _index: self.filter_requested.emit(str(self.filter_combo.currentData())))
        self.candidate_check.toggled.connect(self._emit_route_visibility)
        self.final_check.toggled.connect(self._emit_route_visibility)
        self.table.itemSelectionChanged.connect(self._focus_selection)
        self.path_edit.textChanged.connect(self.invalidate_confirmation)
        self._confirmed_fingerprint: str | None = None
        self._results: list[dict] = []
        self._results_by_task_id: dict[str, dict] = {}

    def _browse(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(self, "选择批量任务 CSV", self.path_edit.text(), "CSV 文件 (*.csv)")
        if path:
            self.path_edit.setText(path)

    def _focus_selection(self) -> None:
        row = self.table.currentRow()
        if row >= 0 and self.table.item(row, 0) is not None:
            task_id = self.table.item(row, 0).text()
            self._show_task_detail(task_id)
            self.focus_requested.emit(task_id)

    def _emit_route_visibility(self, *_args) -> None:
        self.route_visibility_requested.emit(
            self.candidate_check.isChecked(), self.final_check.isChecked()
        )

    def _show_task_detail(self, task_id: str) -> None:
        result = self._results_by_task_id.get(task_id)
        if result is None:
            self.detail_text.clear()
            return
        candidate = result.get("candidate_route") or {}
        final = result.get("final_route") or {}
        validations = result.get("validation_history") or []
        issues = [
            f"{item.get('rule_id')}:{item.get('asset_id')}"
            for validation in validations
            for item in validation.get("violations", [])
        ]
        changes = result.get("resource_changes") or []
        resource_lines = [
            f"{item['asset_id']} {item['free_subduct_before']}→{item['free_subduct_after']}"
            for item in changes
        ]
        self.detail_text.setPlainText(
            f"任务：{task_id}    终态：{result.get('status')}    自动改路：{result.get('repair_count', 0)} 次\n"
            f"候选路线：{','.join(candidate.get('edge_ids', [])) or '-'}\n"
            f"最终路线：{','.join(final.get('edge_ids', [])) or '-'}\n"
            f"冲突/问题：{'; '.join(issues) or '-'}\n"
            f"冲突来源任务：{','.join(result.get('caused_by_task_ids', [])) or '-'}\n"
            f"最终 PASS 后资源预占：{'; '.join(resource_lines) or '无（失败/待复核不扣减）'}"
        )

    def configure(self, dataset_id: str, default_csv: str) -> None:
        self.dataset_label.setText(f"数据集：{dataset_id}\n主展示：411 节点 / 444 边 / 3 机房 / 30 任务")
        self.path_edit.setText(default_csv)

    def invalidate_confirmation(self, *_args) -> None:
        self._confirmed_fingerprint = None
        self.execute_button.setEnabled(False)
        self.export_button.setEnabled(False)

    def set_preview(self, text: str, fingerprint: str | None) -> None:
        self.preview_text.setPlainText(text)
        self._confirmed_fingerprint = fingerprint
        self.execute_button.setEnabled(fingerprint is not None)

    def set_status(self, text: str, state: str = "idle") -> None:
        colors = {"idle": "#9ca9ba", "running": "#e1b85b", "success": "#65c18c", "error": "#ef7379"}
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {colors.get(state, colors['idle'])};")

    def set_results(self, tasks: list[dict]) -> None:
        self._results = list(tasks)
        self._results_by_task_id = {
            item["task"]["task_id"]: item for item in self._results
        }
        self.filter_results(str(self.filter_combo.currentData()))
        self.export_button.setEnabled(True)

    def filter_results(self, status: str) -> None:
        allowed = {"all", "completed_direct", "completed_rerouted", "needs_review", "failed"}
        if status not in allowed:
            raise ValueError(f"未知批量状态筛选：{status}")
        tasks = self._results if status == "all" else [
            item for item in self._results if item["status"] == status
        ]
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(tasks))
        for row, result in enumerate(tasks):
            task = result["task"]
            values = (
                task["task_id"], task["priority"], result["status"], str(result["repair_count"]),
                "" if not result.get("bom") else f"{result['bom']['total_length_m']:.2f}",
                ",".join(result["caused_by_task_ids"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {3, 4}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.detail_text.clear()

    def set_export_enabled(self, enabled: bool) -> None:
        self.export_button.setEnabled(enabled)
