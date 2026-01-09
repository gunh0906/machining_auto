# cam_sheet_app.py
import sys
from PySide6.QtWidgets import QApplication
from .ui import CamSheetApp


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CamSheetApp()
    window.show()
    sys.exit(app.exec())
