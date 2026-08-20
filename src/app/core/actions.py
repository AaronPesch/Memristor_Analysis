from enum import Enum


class MenuAction(Enum):
    # FILE MENU
    # IMPORT
    IMPORT_DEVICE = ("Device", "Ctrl+O", False)
    IMPORT_STACK = ("Stack", "Ctrl+Shift+O", False)

    # EXPORT
    EXPORT_ALL = ("All", "Ctrl+Shift+E", False)
    EXPORT_ALL_PNG = ("PNG", None, False)
    EXPORT_ALL_JPEG = ("JPEG", None, False)
    EXPORT_ALL_EPS = ("EPS", None, False)
    EXPORT_ALL_SVG = ("SVG", None, False)
    EXPORT_ALL_PDF = ("PDF", None, False)
    EXPORT_ALL_PDF_COMBINED = ("PDF (combined)", None, False)
    EXPORT_ALL_PPTX = ("PowerPoint", None, False)
    EXPORT_ALL_CSV = ("CSV", None, False)
    EXPORT_ALL_TXT = ("TXT", None, False)

    EXPORT_CURRENT = ("Current", "Ctrl+E", False, 1)
    EXPORT_CURRENT_PNG = ("PNG", None, False, 1)
    EXPORT_CURRENT_JPEG = ("JPEG", None, False, 1)
    EXPORT_CURRENT_EPS = ("EPS", None, False, 1)
    EXPORT_CURRENT_SVG = ("SVG", None, False, 1)
    EXPORT_CURRENT_PDF = ("PDF", None, False, 1)
    EXPORT_CURRENT_CSV = ("CSV", None, False, 1)
    EXPORT_CURRENT_TXT = ("TXT", None, False, 1)

    # EXIT
    EXIT = ("Exit", "Ctrl+Q", False)

    # VIEW MENU
    TOGGLE_DARK_MODE = ("Dark Mode", None, True)

    # HELP MENU
    VIEW_HELP = ("View Help", "F1", False)

    def __init__(self, text, shortcut=None, checkable=False, _scope=None):
        self.text = text
        self.shortcut = shortcut
        self.checkable = checkable
