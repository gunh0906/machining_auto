# machining_auto/common/print/common_blocks.py
"""
공용 PDF 렌더 블록 모음.

- Setting/CAM 모두 동일한 헤더/특이사항 스타일을 유지하기 위한 공용 모듈
- UI 위젯을 직접 참조하지 않고, payload(값)로만 동작한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QPainter,
    QFont,
    QPen,
    QPixmap,
    QColor,
)


# =========================
# Payload (값 주입형)
# =========================

@dataclass(frozen=True)
class HeaderPayload:
    """
    공용 헤더에 표시할 값 묶음.
    - module_title: "SETTING SHEET", "CAM SHEET" 등 페이지 종류
    - project_title: 프로젝트/품명/파일명 등 상단 큰 제목
    - line1/line2: 정보 표시(작업번호, 설비, PG, 작업자, 날짜 등)
    """
    module_title: str
    project_title: str
    line1: str
    line2: str = ""


@dataclass(frozen=True)
class LogoSpec:
    """
    로고 로딩/표시 사양.
    - logo_path: 절대/상대 경로 모두 허용 (존재 시 출력)
    """
    logo_path: Optional[str] = None


# =========================
# Resource helpers
# =========================

def load_logo_pixmap(logo_spec: LogoSpec) -> Optional[QPixmap]:
    """
    로고 경로가 유효하면 QPixmap으로 로드한다.
    실패 시 None.
    """
    if not logo_spec.logo_path:
        return None

    try:
        p = Path(logo_spec.logo_path)
        if not p.exists():
            return None

        pm = QPixmap(str(p))
        if pm.isNull():
            return None

        return pm
    except Exception:
        return None


# =========================
# Common drawing blocks
# =========================

def draw_frame_rect(painter: QPainter, rect: QRectF, *, width: float = 2.0) -> None:
    """
    외곽 프레임/구획선을 그린다.
    - width는 PDF에서 선이 흐려 보이지 않도록 기본 2.0
    """
    painter.save()
    try:
        pen = QPen(Qt.black)
        pen.setWidthF(float(width))
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
    finally:
        painter.restore()


def draw_common_header(
    painter: QPainter,
    rect: QRectF,
    *,
    payload: HeaderPayload,
    logo_pixmap: Optional[QPixmap] = None,
) -> None:
    """
    공용 헤더 블록.

    레이아웃(고정):
    - 상단 풀폭 1줄: 모듈 타이틀 + 프로젝트 타이틀(굵게)
    - 하단 2줄: line1, line2
    - 좌측 로고 영역(있으면 출력)
    """
    painter.save()
    try:
        # 테두리
        pen = QPen(Qt.black)
        pen.setWidthF(1.6)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        inner = rect.adjusted(10.0, 10.0, -10.0, -10.0)

        # 좌: 로고 / 우: 텍스트
        logo_w = inner.width() * 0.22
        logo_rect = QRectF(inner.left(), inner.top(), logo_w, inner.height())
        text_rect = QRectF(logo_rect.right(), inner.top(), inner.width() - logo_w, inner.height())

        # 구분선
        painter.drawLine(logo_rect.right(), inner.top(), logo_rect.right(), inner.bottom())

        # 로고
        if logo_pixmap is not None and not logo_pixmap.isNull():
            lr = logo_rect.adjusted(6.0, 6.0, -6.0, -6.0)
            scaled = logo_pixmap.scaled(
                int(lr.width()),
                int(lr.height()),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            x = lr.left() + (lr.width() - scaled.width()) / 2.0
            y = lr.top() + (lr.height() - scaled.height()) / 2.0
            painter.drawPixmap(QRectF(x, y, scaled.width(), scaled.height()), scaled, QRectF(scaled.rect()))

        # 텍스트 배치
        title_rect = QRectF(
            text_rect.left() + 10.0,
            text_rect.top(),
            text_rect.width() - 20.0,
            text_rect.height() * 0.52
        )
        line1_rect = QRectF(
            text_rect.left() + 10.0,
            text_rect.top() + text_rect.height() * 0.52,
            text_rect.width() - 20.0,
            text_rect.height() * 0.24
        )
        line2_rect = QRectF(
            text_rect.left() + 10.0,
            text_rect.top() + text_rect.height() * 0.76,
            text_rect.width() - 20.0,
            text_rect.height() * 0.24
        )

        # 제목
        painter.setPen(Qt.black)
        painter.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
        title_text = f"{payload.module_title}  |  {payload.project_title}"
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title_text)

        # 정보 line1
        painter.setFont(QFont("Malgun Gothic", 12))
        painter.drawText(line1_rect, Qt.AlignLeft | Qt.AlignVCenter, payload.line1)

        # 정보 line2(없으면 빈 줄)
        painter.setFont(QFont("Malgun Gothic", 12))
        painter.drawText(line2_rect, Qt.AlignLeft | Qt.AlignVCenter, payload.line2 or "")

    finally:
        painter.restore()


def draw_common_notes(
    painter: QPainter,
    rect: QRectF,
    *,
    title: str = "특이사항",
    notes_text: str = "",
) -> None:
    """
    공용 특이사항 블록.
    - title: 블록 상단 타이틀
    - notes_text: 본문 텍스트(줄바꿈/워드랩)
    """
    painter.save()
    try:
        # 배경은 흰색(인쇄 가독성)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRect(rect)

        # 테두리
        pen = QPen(Qt.black)
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        inner = rect.adjusted(10.0, 10.0, -10.0, -10.0)

        # 타이틀
        header_h = 22.0
        title_rect = QRectF(inner.left(), inner.top(), inner.width(), header_h)
        body_rect = QRectF(inner.left(), inner.top() + header_h + 6.0, inner.width(), inner.height() - header_h - 6.0)

        painter.setPen(Qt.black)
        painter.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

        # 본문
        painter.setFont(QFont("Malgun Gothic", 10))
        painter.drawText(
            body_rect,
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            notes_text or ""
        )

    finally:
        painter.restore()
