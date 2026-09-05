from pathlib import Path

from qgis_plugin.telecom_geo_agent.plugin import (
    PLUGIN_MENU,
    PluginBindings,
    TelecomGeoAgentPlugin,
)


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        self.slots.remove(slot)


class FakeAction:
    def __init__(self, text, parent):
        self.text = text
        self.parent = parent
        self.triggered = FakeSignal()
        self.checked = False
        self.deleted = False

    def setCheckable(self, value):
        self.checkable = value

    def setChecked(self, value):
        self.checked = value

    def deleteLater(self):
        self.deleted = True


class FakeDock:
    def __init__(self):
        self.visibilityChanged = FakeSignal()
        self.send_requested = FakeSignal()
        self.command_requested = FakeSignal()
        self.shown = False
        self.hidden = False
        self.closed = False
        self.deleted = False

    def show(self):
        self.shown = True

    def hide(self):
        self.hidden = True

    def raise_(self):
        pass

    def close(self):
        self.closed = True

    def setParent(self, parent):
        self.parent = parent

    def deleteLater(self):
        self.deleted = True


class FakeMap:
    def __init__(self):
        self.cleared = False

    def clear_layers(self):
        self.cleared = True


class FakeController:
    def handle_user_input(self, text):
        self.last_text = text


class FakeIface:
    def __init__(self):
        self.added_menu = []
        self.removed_menu = []
        self.toolbar = []
        self.removed_toolbar = []
        self.docks = []
        self.removed_docks = []

    def mainWindow(self):
        return self

    def addPluginToMenu(self, menu, action):
        self.added_menu.append((menu, action))

    def removePluginMenu(self, menu, action):
        self.removed_menu.append((menu, action))

    def addToolBarIcon(self, action):
        self.toolbar.append(action)

    def removeToolBarIcon(self, action):
        self.removed_toolbar.append(action)

    def addDockWidget(self, area, dock):
        self.docks.append((area, dock))

    def removeDockWidget(self, dock):
        self.removed_docks.append(dock)


def test_plugin_registers_right_dock_and_unload_removes_every_owned_item():
    iface = FakeIface()
    dock = FakeDock()
    map_adapter = FakeMap()
    controller = FakeController()
    prepared = []

    plugin = TelecomGeoAgentPlugin(
        iface,
        bindings=PluginBindings(FakeAction, "RIGHT"),
        component_factory=lambda _iface, _root: (dock, map_adapter, controller),
        runtime_preparer=lambda plugin_dir: prepared.append(plugin_dir) or Path.cwd(),
    )

    plugin.initGui()

    action = plugin.action
    assert prepared
    assert iface.added_menu == [(PLUGIN_MENU, action)]
    assert iface.toolbar == [action]
    assert iface.docks == [("RIGHT", dock)]
    assert dock.shown and action.checked
    assert len(dock.send_requested.slots) == 1
    assert len(dock.command_requested.slots) == 1

    plugin.unload()

    assert map_adapter.cleared
    assert iface.removed_menu == [(PLUGIN_MENU, action)]
    assert iface.removed_toolbar == [action]
    assert iface.removed_docks == [dock]
    assert dock.closed and dock.deleted
    assert action.deleted
    assert plugin.action is plugin.dock is plugin.map_adapter is plugin.controller is None
