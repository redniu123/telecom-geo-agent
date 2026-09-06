"""QGIS plugin lifecycle with injectable boundaries for ordinary Python tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .runtime import activate_runtime


PLUGIN_MENU = "&通信工程 Agent"


@dataclass(frozen=True)
class PluginBindings:
    action_type: type
    right_dock_area: Any


def _load_bindings() -> PluginBindings:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QAction

    return PluginBindings(QAction, Qt.RightDockWidgetArea)


def _create_components(iface, runtime_root: Path):
    from .controller import ChatController
    from .competition_controller import CompetitionController, PluginController
    from .batch_controller import BatchController
    from .dock_widget import AgentDockWidget
    from .map_adapter import QgisMapAdapter

    dock = AgentDockWidget(iface.mainWindow())
    map_adapter = QgisMapAdapter(iface)
    controller = PluginController(
        ChatController(dock, map_adapter, runtime_root),
        CompetitionController(dock, map_adapter, runtime_root),
        BatchController(dock, map_adapter, runtime_root),
    )
    return dock, map_adapter, controller


class TelecomGeoAgentPlugin:
    """Register one right-side Dock and remove every owned UI item on unload."""

    def __init__(
        self,
        iface,
        *,
        bindings: PluginBindings | None = None,
        component_factory: Callable[..., tuple[Any, Any, Any]] | None = None,
        runtime_preparer: Callable[[str | Path | None], Path] = activate_runtime,
    ) -> None:
        self.iface = iface
        self._bindings = bindings
        self._component_factory = component_factory
        self._runtime_preparer = runtime_preparer
        self.action = None
        self.dock = None
        self.map_adapter = None
        self.controller = None

    def initGui(self) -> None:  # noqa: N802 - QGIS lifecycle API.
        if self.action is not None:
            return
        runtime_root = self._runtime_preparer(Path(__file__).resolve().parent)
        bindings = self._bindings or _load_bindings()
        factory = self._component_factory or _create_components
        self.dock, self.map_adapter, self.controller = factory(
            self.iface, runtime_root
        )

        self.action = bindings.action_type("通信工程 Agent", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_dock)
        self.dock.visibilityChanged.connect(self.action.setChecked)
        self.dock.send_requested.connect(self.controller.handle_user_input)
        self.dock.command_requested.connect(self.controller.handle_user_input)
        if hasattr(self.dock, "competition_preview_requested") and hasattr(
            self.controller, "preview_competition"
        ):
            self.dock.competition_preview_requested.connect(
                self.controller.preview_competition
            )
            self.dock.competition_execute_requested.connect(
                self.controller.execute_competition
            )
            if hasattr(self.controller, "export_competition"):
                self.dock.competition_export_requested.connect(
                    self.controller.export_competition
                )
        if hasattr(self.dock, "batch_import_requested") and hasattr(
            self.controller, "import_batch"
        ):
            self.dock.batch_import_requested.connect(self.controller.import_batch)
            self.dock.batch_preview_requested.connect(self.controller.preview_batch)
            self.dock.batch_execute_requested.connect(self.controller.execute_batch)
            self.dock.batch_export_requested.connect(self.controller.export_batch)
            self.dock.batch_filter_requested.connect(self.controller.filter_batch)
            self.dock.batch_focus_requested.connect(self.controller.focus_batch)
            self.dock.batch_route_visibility_requested.connect(
                self.controller.set_batch_route_visibility
            )

        self.iface.addPluginToMenu(PLUGIN_MENU, self.action)
        self.iface.addToolBarIcon(self.action)
        self.iface.addDockWidget(bindings.right_dock_area, self.dock)
        self.dock.show()
        self.action.setChecked(True)

    def _toggle_dock(self, checked: bool) -> None:
        if self.dock is None:
            return
        if checked:
            self.dock.show()
            self.dock.raise_()
        else:
            self.dock.hide()

    def unload(self) -> None:
        if self.action is None:
            return
        try:
            self.action.triggered.disconnect(self._toggle_dock)
            self.dock.visibilityChanged.disconnect(self.action.setChecked)
            self.dock.send_requested.disconnect(self.controller.handle_user_input)
            self.dock.command_requested.disconnect(self.controller.handle_user_input)
            if hasattr(self.dock, "competition_preview_requested") and hasattr(
                self.controller, "preview_competition"
            ):
                self.dock.competition_preview_requested.disconnect(
                    self.controller.preview_competition
                )
                self.dock.competition_execute_requested.disconnect(
                    self.controller.execute_competition
                )
                if hasattr(self.controller, "export_competition"):
                    self.dock.competition_export_requested.disconnect(
                        self.controller.export_competition
                    )
            if hasattr(self.dock, "batch_import_requested") and hasattr(
                self.controller, "import_batch"
            ):
                self.dock.batch_import_requested.disconnect(self.controller.import_batch)
                self.dock.batch_preview_requested.disconnect(self.controller.preview_batch)
                self.dock.batch_execute_requested.disconnect(self.controller.execute_batch)
                self.dock.batch_export_requested.disconnect(self.controller.export_batch)
                self.dock.batch_filter_requested.disconnect(self.controller.filter_batch)
                self.dock.batch_focus_requested.disconnect(self.controller.focus_batch)
                self.dock.batch_route_visibility_requested.disconnect(
                    self.controller.set_batch_route_visibility
                )
        except (RuntimeError, TypeError):
            pass
        if self.map_adapter is not None:
            self.map_adapter.clear_layers()
        self.iface.removePluginMenu(PLUGIN_MENU, self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.close()
            self.dock.setParent(None)
            self.dock.deleteLater()
        self.action.deleteLater()
        self.action = None
        self.dock = None
        self.map_adapter = None
        self.controller = None
