# machining_auto/splash_screen.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QTextEdit,
)

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QFontMetrics
from PySide6.QtWidgets import QWidget


class InsetProgressBar(QWidget):
    """
    스플래시 전용 인셋 프로그레스바
    - 흰 바(외곽 라운드) 안쪽에서 파란 바가만 이동
    - 파란 바 라운드 100% 보장 (QSS 의존 X)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0
        self._text = "0% (초기화 중...)"

        self.setFixedHeight(24)

        # 디자인 파라미터(필요시 수치만 조정)
        self._radius_outer = 12
        self._inset = 3
        self._radius_inner = 9

        self._c_border = QColor("#D7DCE6")
        self._c_bg = QColor("#FFFFFF")
        self._c_fill = QColor("#294392")
        self._c_text = QColor("#111827")

    def set_progress(self, value: int, text: str) -> None:
        self._value = max(0, min(100, int(value)))
        self._text = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self.rect()

        # 1) 외곽(흰 바 + 테두리)
        pen = QPen(self._c_border)
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(self._c_bg)
        p.drawRoundedRect(r.adjusted(0, 0, -1, -1), self._radius_outer, self._radius_outer)

        # 2) 내부(인셋 영역)
        inner = r.adjusted(self._inset, self._inset, -self._inset, -self._inset)
        if inner.width() <= 0 or inner.height() <= 0:
            return

        # 3) 채움(파란 바)
        fill_w = int(inner.width() * (self._value / 100.0))
        if fill_w > 0:
            fill = QRect(inner.left(), inner.top(), fill_w, inner.height())

            # 채움 폭이 너무 작을 때 라운드가 깨지지 않도록 반경 보정
            rad = min(self._radius_inner, fill.height() // 2, max(0, fill.width() // 2))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._c_fill)
            p.drawRoundedRect(fill, rad, rad)

        # 4) 텍스트(중앙)
        p.setPen(self._c_text)
        fm = QFontMetrics(p.font())
        text = self._text
        # 너무 길면 생략
        if fm.horizontalAdvance(text) > inner.width() - 12:
            while text and fm.horizontalAdvance(text + "…") > inner.width() - 12:
                text = text[:-1]
            text = (text + "…") if text else ""
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)


class AppSplash(QWidget):
    """
    앱 시작 스플래시 화면.
    - 로고 표시
    - 진행률(%) 표시
    - 상태 메시지 표시
    - 향후 패치 로그 출력용 텍스트 영역 포함
    """

    def __init__(self, *, logo_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # 프레임리스 + 스플래시 성격
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._build_ui(logo_path=logo_path)

    def _build_ui(self, *, logo_path: str) -> None:
        # ✅ 로고 + 프로그레스바만 보이도록 최소 크기
        self.setFixedSize(720, 260)

        # ✅ 배경/테두리 제거: 로고만 떠 있는 느낌
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ---- 로고 ----
        self.lbl_logo = QLabel(self)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo.setFixedHeight(200)

        pm = QPixmap(str(logo_path))
        if not pm.isNull():
            pm2 = pm.scaled(
                680, 200,  # ✅ 창 폭(720)보다 약간 작게
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_logo.setPixmap(pm2)
        else:
            self.lbl_logo.setText("LOGO")


        
        # ---- 진행률 ----
        self.progress = InsetProgressBar(self)
        self.progress.setObjectName("SplashProgress")

        # ✅ 로고 폭(680)에 정확히 맞춰 로딩바가 더 길어 보이지 않게
        self.progress.setFixedWidth(400)

        # ✅ 초기 텍스트
        self.progress.set_progress(0, "0% (초기화 중...)")


        # ✅ 바 자체는 흰 배경 위에 깔끔하게
        self.progress.setStyleSheet("""
            QProgressBar#SplashProgress {
                border: 1px solid #D7DCE6;
                border-radius: 12px;
                background: #FFFFFF;
                text-align: center;
                font-family: "Segoe UI", "Malgun Gothic";
                font-size: 12px;
                font-weight: 800;
                color: #111827;

                /* 바깥 흰 바 내부 여백 느낌(선택) */
                padding: 0px;
            }

            /* ✅ 핵심: 파란 진행영역을 안쪽으로 넣기 */
            QProgressBar#SplashProgress::chunk {
                background: #294392;

                /* 파란 바가 흰 바보다 살짝 작게, 안쪽에서만 움직이게 */
                margin: 3px;

                /* 파란 바는 자연스럽게 약간만 라운드 */
                border-radius: 9px;
            }
        """)


        root.addWidget(self.lbl_logo)
        root.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignHCenter)
        

    # -------------------------
    # Public API
    # -------------------------
    def set_progress(self, percent: int, message: str = "") -> None:
        p = int(max(0, min(100, percent)))
        msg = (message or "").strip()
        text = f"{p}% ({msg})" if msg else f"{p}%"

        self.progress.set_progress(p, text)

        try:
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
        except Exception:
            pass



    def append_log(self, line: str) -> None:
        return