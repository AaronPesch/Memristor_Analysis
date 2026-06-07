import PySide6.QtWidgets as qt
from PySide6.QtGui import QAction
from ..core import MenuAction


class MenuBar(qt.QMenuBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.menu_actions = {}
        self.setup_ui()

    def setup_ui(self):
        # Create Actions from enum
        for action in MenuAction:
            menu_action = QAction(action.text, self)
            if action.shortcut:
                menu_action.setShortcut(action.shortcut)
            if action.checkable:
                menu_action.setCheckable(True)
            # Store it so we can access it later
            self.menu_actions[action] = menu_action

        self.setup_file_menu()
        self.setup_help_menu()

    def setup_file_menu(self):
        self.file_menu = self.addMenu("File")

        self.file_menu.addSection("Import")
        self.file_menu.addAction(self.menu_actions[MenuAction.IMPORT_DEVICE])
        self.file_menu.addAction(self.menu_actions[MenuAction.IMPORT_STACK])
        self.file_menu.addSeparator()

        self.file_menu.addSection("Export")
        self.file_sub_menu_export_all = self.file_menu.addMenu("All To")
        self.file_sub_menu_export_current = self.file_menu.addMenu("Current To")
        # Populate "All To" submenu
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_PNG]
        )
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_JPEG]
        )
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_EPS]
        )
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_SVG]
        )
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_PDF]
        )
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_PDF_COMBINED]
        )
        self.file_sub_menu_export_all.addSeparator()
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_CSV]
        )
        self.file_sub_menu_export_all.addAction(
            self.menu_actions[MenuAction.EXPORT_ALL_TXT]
        )
        # Populate "Current To"
        self.file_sub_menu_export_current.addAction(
            self.menu_actions[MenuAction.EXPORT_CURRENT_PNG]
        )
        self.file_sub_menu_export_current.addAction(
            self.menu_actions[MenuAction.EXPORT_CURRENT_JPEG]
        )
        self.file_sub_menu_export_current.addAction(
            self.menu_actions[MenuAction.EXPORT_CURRENT_EPS]
        )
        self.file_sub_menu_export_current.addAction(
            self.menu_actions[MenuAction.EXPORT_CURRENT_SVG]
        )
        self.file_sub_menu_export_current.addAction(
            self.menu_actions[MenuAction.EXPORT_CURRENT_PDF]
        )
        self.file_sub_menu_export_current.addSeparator()
        self.file_sub_menu_export_current.addAction(
            self.menu_actions[MenuAction.EXPORT_CURRENT_CSV]
        )
        self.file_sub_menu_export_current.addAction(
            self.menu_actions[MenuAction.EXPORT_CURRENT_TXT]
        )
        self.file_menu.addAction(self.menu_actions[MenuAction.EXPORT_ALL])
        self.file_menu.addAction(self.menu_actions[MenuAction.EXPORT_CURRENT])
        self.file_menu.addSeparator()

        self.file_menu.addAction(self.menu_actions[MenuAction.EXIT])

    def setup_help_menu(self):
        self.help_menu = self.addMenu("Help")
        self.help_menu.addAction(self.menu_actions[MenuAction.VIEW_HELP])
