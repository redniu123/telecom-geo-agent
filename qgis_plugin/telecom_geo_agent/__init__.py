"""QGIS entry point for the TelecomGeoAgent P1A plugin."""


def classFactory(iface):  # noqa: N802 - QGIS requires this exact name.
    """Return the plugin instance expected by the QGIS plugin loader."""

    from .plugin import TelecomGeoAgentPlugin

    return TelecomGeoAgentPlugin(iface)


__all__ = ["classFactory"]

