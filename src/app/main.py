import multiprocessing
import sys
import os

# Ensure the src/ directory is on sys.path so "app.*" imports resolve
# both when running as a script and in a PyInstaller build.
if not getattr(sys, "frozen", False) and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse  # noqa: E402
import PySide6.QtWidgets as qt  # noqa: E402
from app.ui import MainWindow  # noqa: E402
from app.core.theme import apply_qt_theme  # noqa: E402
from app.core.preferences import get_theme  # noqa: E402


def main():
    multiprocessing.freeze_support()
    # Smoke Test
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    args, unknown = parser.parse_known_args()

    app = qt.QApplication(sys.argv)
    apply_qt_theme(app, get_theme())

    window = MainWindow()
    window.show()

    if args.smoke_test:
        print("Smoke test: UI initialized successfully. Exiting.")
        sys.exit(0)  # Exit before app.exec()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
