from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt

LIGHT = "light"
DARK = "dark"

# Plotly restyle colors (used via JavaScript relayout in the plot viewer)
PLOT_COLORS = {
    LIGHT: {
        "paper_bgcolor": "white",
        "plot_bgcolor": "white",
        "font_color": "#2a3f5f",
        "grid_color": "#E5E5E5",
    },
    DARK: {
        "paper_bgcolor": "#1e1e1e",
        "plot_bgcolor": "#1e1e1e",
        "font_color": "#e0e0e0",
        "grid_color": "#3a3a3a",
    },
}


def _dark_palette() -> QPalette:
    p = QPalette()
    window = QColor("#2b2b2b")
    base = QColor("#1e1e1e")
    text = QColor("#e0e0e0")
    button = QColor("#3a3a3a")
    highlight = QColor("#2d7d9a")

    p.setColor(QPalette.Window, window)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, window)
    p.setColor(QPalette.ToolTipBase, base)
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, button)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.BrightText, QColor("#ff5555"))
    p.setColor(QPalette.Link, highlight)
    p.setColor(QPalette.Highlight, highlight)
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.PlaceholderText, QColor("#888888"))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor("#777777"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#777777"))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#777777"))
    return p


def apply_qt_theme(app, theme: str) -> None:
    """Apply the Fusion style plus a light or dark palette to the QApplication."""
    app.setStyle("Fusion")
    if theme == DARK:
        app.setPalette(_dark_palette())
    else:
        app.setPalette(app.style().standardPalette())
