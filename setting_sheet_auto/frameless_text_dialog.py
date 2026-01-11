# setting_sheet_auto/frameless_text_dialog.py
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class FramelessTextDialog(QDialog):
    """
    타이틀바 없는(Frameless) 텍스트 입력 다이얼로그.
    반환: (text, ok)
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        prompt: str,
        placeholder: str = "",
        default: str = "",
    ) -> None:
        super().__init__(parent)

        self._result_text = ""

        # ✅ 타이틀바 제거
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)

        self._build_ui(prompt=prompt, placeholder=placeholder, default=default)

    def _build_ui(self, *, prompt: str, placeholder: str, default: str) -> None:
        self.setFixedSize(420, 160)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        lbl = QLabel(prompt, self)
        lbl.setWordWrap(True)

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(default)
        self.edit.setClearButtonEnabled(True)

        btns = QHBoxLayout()
        btns.addStretch(1)

        self.btn_cancel = QPushButton("취소", self)
        self.btn_ok = QPushButton("확인", self)
        self.btn_ok.setDefault(True)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)

        # ✅ 로컬 스타일(전역 QSS와 충돌 없이 안전)
        self.setStyleSheet("""
            QDialog {
                background: #FFFFFF;
                border: 1px solid #D7DCE6;
                border-radius: 12px;
            }
            QLabel {
                color: #111827;
                font-family: "Segoe UI", "Malgun Gothic";
                font-size: 13px;
                font-weight: 800;
            }
            QLineEdit {
                background: #FFFFFF;
                border: 1px solid #D7DCE6;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 14px;
            }
            QPushButton {
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 800;
            }
            QPushButton#OkBtn {
                background: #294392;
                border: 1px solid #294392;
                color: #FFFFFF;
            }
            QPushButton#OkBtn:hover {
                background: #1F347A;
                border-color: #1F347A;
            }
            QPushButton#CancelBtn {
                background: #F2F4F8;
                border: 1px solid #D7DCE6;
                color: #111827;
            }
        """)

        self.btn_ok.setObjectName("OkBtn")
        self.btn_cancel.setObjectName("CancelBtn")

        root.addWidget(lbl)
        root.addWidget(self.edit)
        root.addLayout(btns)

        self.edit.setFocus()
        self.edit.selectAll()

    def _on_ok(self) -> None:
        self._result_text = (self.edit.text() or "").strip()
        self.accept()

    @staticmethod
    def get_text(
        parent: QWidget,
        *,
        prompt: str,
        placeholder: str = "",
        default: str = "",
    ) -> Tuple[str, bool]:
        dlg = FramelessTextDialog(parent, prompt=prompt, placeholder=placeholder, default=default)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return (dlg._result_text, ok)
