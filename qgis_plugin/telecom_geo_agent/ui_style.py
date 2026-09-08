"""Shared visual tokens for the native Qt/QGIS dock."""

from __future__ import annotations


STATUS_META = {
    "completed_direct": {
        "label": "直接成功",
        "foreground": "#8FE3B1",
        "background": "#183A2B",
    },
    "completed_rerouted": {
        "label": "绕行成功",
        "foreground": "#86CCFF",
        "background": "#17364E",
    },
    "needs_review": {
        "label": "待人工复核",
        "foreground": "#FFD37A",
        "background": "#45361D",
    },
    "failed": {
        "label": "明确失败",
        "foreground": "#FF969B",
        "background": "#4A2428",
    },
}

PRIORITY_META = {
    "high": {"label": "高", "foreground": "#FFB0A0", "background": "#442723"},
    "medium": {"label": "中", "foreground": "#FFD17A", "background": "#3D321F"},
    "low": {"label": "低", "foreground": "#AAB8C9", "background": "#29313D"},
}


APP_STYLE_SHEET = """
QDockWidget {
    color: #E5EAF1;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 9pt;
}
QWidget {
    background: #141922;
    color: #E5EAF1;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 9pt;
}
QLabel#AgentTitle {
    color: #F8FAFD;
    font-size: 15pt;
    font-weight: 700;
}
QLabel#AgentSubtitle, QLabel[role="muted"] {
    color: #98A6B8;
}
QLabel[role="sectionTitle"] {
    color: #F6F8FC;
    font-size: 10pt;
    font-weight: 700;
}
QLabel[role="eyebrow"] {
    color: #72C5F5;
    font-size: 8pt;
    font-weight: 700;
}
QLabel[role="nextStep"] {
    color: #CFEAFF;
    background: #172B3B;
    border: 1px solid #28516D;
    border-radius: 7px;
    padding: 7px 9px;
    font-weight: 600;
}
QLabel[role="boundary"] {
    color: #F1CE7A;
    background: #302719;
    border: 1px solid #675126;
    border-radius: 7px;
    padding: 8px;
}
QLabel[role="mapContext"] {
    color: #B8DFF7;
    background: #192B38;
    border-left: 3px solid #42A5DD;
    padding: 7px 8px;
}
QLabel[role="blocking"] {
    color: #E8B66B;
    padding: 3px 1px;
}
QLabel[role="metric"] {
    color: #A7B4C5;
    background: #151B24;
    border: 1px solid #303947;
    border-radius: 6px;
    padding: 6px 7px;
}
QLabel[state="idle"] { color: #A6B2C2; }
QLabel[state="running"] { color: #FFD071; }
QLabel[state="success"] { color: #82DAA6; }
QLabel[state="error"] { color: #FF8D94; }
QLabel[state="selected"] { color: #82D6FF; }
QFrame[card="true"] {
    background: #1B222D;
    border: 1px solid #303A49;
    border-radius: 9px;
}
QFrame[card="true"] QLabel { background: transparent; }
QFrame[messageKind="info"] { background: #222A36; border-radius: 8px; }
QFrame[messageKind="route"] { background: #1E3448; border: 1px solid #315F86; border-radius: 8px; }
QFrame[messageKind="warning"] { background: #40351F; border: 1px solid #80662C; border-radius: 8px; }
QFrame[messageKind="repair"] { background: #342A49; border: 1px solid #654E8D; border-radius: 8px; }
QFrame[messageKind="success"] { background: #1D3B2D; border: 1px solid #327459; border-radius: 8px; }
QFrame[messageKind="bom"] { background: #24372F; border: 1px solid #3E715C; border-radius: 8px; }
QFrame[messageKind="map"] { background: #243846; border: 1px solid #42708E; border-radius: 8px; }
QFrame[messageKind="error"] { background: #482528; border: 1px solid #8D4146; border-radius: 8px; }
QFrame[messageRole="user"] { background: #1A3C65; border: 1px solid #2A68A7; border-radius: 8px; }
QTabWidget::pane {
    border: 1px solid #303A49;
    border-radius: 7px;
    top: -1px;
}
QTabBar::tab {
    background: #1B222D;
    color: #A5B1C1;
    border: 1px solid #303A49;
    padding: 8px 10px;
    min-width: 58px;
}
QTabBar::tab:selected {
    background: #173B55;
    color: #F3F8FC;
    border-bottom: 2px solid #49B6F2;
}
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: #141922; }
QPlainTextEdit, QLineEdit, QComboBox, QSpinBox {
    background: #10151D;
    color: #EDF2F8;
    border: 1px solid #374252;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #286B98;
}
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #4BB7F1;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QPlainTextEdit:disabled {
    color: #697687;
    background: #171C24;
}
QPushButton {
    background: #293240;
    color: #E9EDF3;
    border: 1px solid #445064;
    border-radius: 6px;
    padding: 7px 10px;
    min-height: 18px;
}
QPushButton:hover { background: #354153; border-color: #596A81; }
QPushButton:pressed { background: #202936; }
QPushButton:disabled { color: #6D7888; background: #1C222B; border-color: #303844; }
QPushButton[buttonRole="primary"]:enabled {
    background: #176FA7;
    border-color: #2B92CC;
    color: white;
    font-weight: 700;
}
QPushButton[buttonRole="primary"]:hover { background: #2084C2; }
QPushButton[buttonRole="success"]:enabled {
    background: #206848;
    border-color: #398766;
    color: white;
    font-weight: 700;
}
QPushButton[buttonRole="secondary"]:enabled {
    background: #243E52;
    border-color: #3D657F;
    font-weight: 600;
}
QToolButton {
    color: #AEDCF7;
    background: transparent;
    border: 0;
    padding: 4px 1px;
    font-weight: 600;
}
QToolButton:hover { color: #D9F0FF; }
QCheckBox { spacing: 7px; color: #CFD6E0; }
QTableWidget {
    background: #111720;
    alternate-background-color: #171E28;
    color: #E8EDF4;
    border: 1px solid #344052;
    border-radius: 6px;
    gridline-color: #2B3441;
    selection-background-color: #245C80;
    selection-color: #FFFFFF;
}
QTableWidget::item { padding: 5px; }
QTableWidget::item:selected { background: #245C80; color: #FFFFFF; }
QHeaderView::section {
    background: #202936;
    color: #C5CFDC;
    border: 0;
    border-right: 1px solid #344052;
    border-bottom: 1px solid #344052;
    padding: 6px;
    font-weight: 600;
}
QGroupBox {
    border: 1px solid #303A49;
    border-radius: 7px;
    margin-top: 10px;
    padding-top: 7px;
    color: #C7D1DD;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QSplitter::handle { background: #2B3441; height: 2px; }
QScrollBar:vertical { background: #151B24; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #3B485A; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #F3F6FA; color: #17202B; border: 1px solid #8E9BAD; padding: 5px; }
"""


def repolish(widget) -> None:
    """Refresh QSS selectors after a dynamic property changes."""

    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
