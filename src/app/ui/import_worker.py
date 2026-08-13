import os
import shutil
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from app.core.paths import DB_FILE, TEMP_DIR
from app.plotting.run import main as run_plotting_pipeline
from app.core.modes import Mode


class ImportWorker(QObject):
    progress = Signal(int)
    status_message = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, path: Path, mode: Mode, converter_class):
        super().__init__()
        self.path = path
        self.mode = mode
        self.converter_class = converter_class

    @Slot()
    def run(self):
        try:
            # set variable
            os.environ["MEMRISTOR_MODE"] = self.mode.value

            temp_dir = TEMP_DIR / self.mode.value
            # remove old temp data
            if temp_dir.exists():
                try:
                    # Attempt to delete the directory
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    # If deletion fails, raise a user-friendly error
                    raise RuntimeError(
                        f"Could not clear the temporary folder for {self.mode.value}.\n\n"
                        f"Reason: {str(e)}\n\n"
                        "Please ensure no plot files are currently open in your browser "
                        "or other applications, then try the import again."
                    )

            # recreate temp folder
            temp_dir.mkdir(parents=True, exist_ok=True)

            # --- STEP 1: Data Conversion (Importing to DuckDB) ---
            self.status_message.emit("Phase 1/2: Updating database from raw files...")
            self.progress.emit(10)

            converter = self.converter_class(DB_FILE)
            converter.convert(self.path)

            self.progress.emit(50)

            # --- STEP 2: Plotting (Generating HTMLs) ---
            self.status_message.emit(
                "Phase 2/2: Generating HTML plots (this may take a moment)..."
            )

            # This calls the 'main()' function from your plotting script exactly as it is.
            # It will load the config, read the DB, and write the files.
            run_plotting_pipeline()

            self.progress.emit(100)
            self.finished.emit()

        except Exception as e:
            # If anything fails in the converter OR the plotting script, catch it here
            tb = traceback.format_exc()
            print(tb)  # full traceback to console
            self.error.emit(f"{e}\n\n{tb}")
