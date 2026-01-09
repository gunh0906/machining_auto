# machining_auto/cam_sheet/cam_print_engine.py
"""
CAM SHEET PDF 출력 엔진.

- 공용 헤더/특이사항은 machining_auto/common/print/common_blocks.py 를 사용한다.
- CAM 표(본문)는 CAM 전용으로 그린다.
- 가로모드에서는 좌측에 Setting 이미지 스냅샷(QImage)을 함께 배치할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, List

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import (
    QPainter,
    QFont,
    QPen,
    QImage,
    QPixmap,
    QPageSize,
    QPageLayout,
    QDesktopServices,
)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QMessageBox, QFileDialog

from machining_auto.common.print.common_blocks import (
    HeaderPayload,
    LogoSpec,
    load_logo_pixmap,
    draw_common_header,
    draw_common_notes,
    draw_frame_rect,
)


# =========================
# CAM Print Payload
# =========================

@dataclass(frozen=True)
class CamPrintPayload:
    """
    CAM 페이지 출력에 필요한 값 묶음.
    - header: 공용 헤더 payload
    - notes_text: 특이사항
    - cam_rows: 표에 들어갈 행 목록(딕셔너리)
    """
    header: HeaderPayload
    notes_text: str
    cam_rows: Sequence[Mapping[str, Any]]


# =========================
# Main Engine
# =========================

class CamPrintEngine:
    def __init__(self, parent=None, *, logo_path: Optional[str] = None):
        """
        parent: QMessageBox/QFileDialog 부모로 사용할 위젯(없어도 동작은 가능)
        logo_path: 공용 로고 경로(없으면 로고 없이 출력)
        """
        self._parent = parent
        self._logo_pixmap: Optional[QPixmap] = load_logo_pixmap(LogoSpec(logo_path=logo_path))
        self._header_drawer = None  # type: object | None

    # -------------------------
    # Public API
    # -------------------------
    def set_header_drawer(self, fn):
        """
        fn(painter: QPainter, rect: QRectF) 형태의 헤더 그리기 함수를 주입합니다.
        보통 setting_sheet_auto.print_engine.PrintEngine._draw_header 를 넣습니다.
        """
        self._header_drawer = fn

    def export_cam_pdf(
        self,
        payload: CamPrintPayload,
        *,
        output_path: Optional[str] = None,
        layout: str = "세로",
        setting_snapshot: Optional[QImage] = None,
    ) -> Optional[str]:
        """
        CAM PDF 1페이지 출력.

        layout:
          - "세로": CAM 표 중심
          - "가로": 좌측에 setting_snapshot(있으면) + 우측 CAM 표

        setting_snapshot:
          - 가로모드에서 좌측에 같이 넣을 Setting 이미지(QImage)
          - 없으면 가로에서도 좌측은 빈 박스만 그림
        """
        # 1) 저장 경로
        if not output_path:
            default_name = f"{payload.header.project_title}_CAM.pdf"
            path, _ = QFileDialog.getSaveFileName(
                self._parent,
                "CAM PDF로 저장",
                default_name,
                "PDF 파일 (*.pdf)"
            )
            if not path:
                return None
        else:
            path = output_path

        # 2) QPrinter 설정
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setFullPage(True)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)

        if layout == "가로":
            printer.setPageOrientation(QPageLayout.Landscape)
        else:
            printer.setPageOrientation(QPageLayout.Portrait)

        # 3) 렌더링
        painter = QPainter(printer)
        if not painter.isActive():
            QMessageBox.critical(self._parent, "PDF 생성 오류", "PDF 파일 생성 중 오류가 발생하였습니다.")
            return None

        try:
            page_rect = QRectF(printer.pageLayout().paintRectPixels(printer.resolution()))
            if layout == "가로":
                self._render_cam_page_landscape(painter, page_rect, payload=payload, setting_snapshot=setting_snapshot)
            else:
                self._render_cam_page_portrait(painter, page_rect, payload=payload)
        finally:
            painter.end()

        # 4) PDF 열기(실패 무시)
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            pass

        QMessageBox.information(self._parent, "PDF 생성 완료", f"CAM PDF 생성 완료.\n{path}")
        return path

    # -------------------------
    # Layout: Portrait
    # -------------------------

    def _render_cam_page_portrait(self, painter: QPainter, page_rect: QRectF, *, payload: CamPrintPayload) -> None:
        """
        세로 A4:
        - 헤더(상단)
        - CAM 표(중앙)
        - 특이사항(하단)
        """
        # 여백
        margin_x = page_rect.width() * 0.01
        margin_y = page_rect.height() * 0.01

        content = QRectF(
            page_rect.left() + margin_x,
            page_rect.top() + margin_y,
            page_rect.width() - 2.0 * margin_x,
            page_rect.height() - 2.0 * margin_y
        )

        total_h = content.height()
        header_h = max(total_h * 0.14, 160.0)
        notes_h = max(total_h * 0.10, 140.0)
        table_h = total_h - header_h - notes_h

        header_rect = QRectF(content.left(), content.top(), content.width(), header_h)
        table_rect = QRectF(content.left(), header_rect.bottom(), content.width(), table_h)
        notes_rect = QRectF(content.left(), content.bottom() - notes_h, content.width(), notes_h)

        # 공용 헤더
        if callable(self._header_drawer):
            self._header_drawer(painter, header_rect)
        else:
            draw_common_header(painter, header_rect, payload=payload.header, logo_pixmap=self._logo_pixmap)


        # CAM 표
        self._draw_cam_table(painter, table_rect, cam_rows=payload.cam_rows)

        # 공용 특이사항
        draw_common_notes(painter, notes_rect, title="특이사항", notes_text=payload.notes_text)

        # 프레임(마지막에 다시)
        draw_frame_rect(painter, content, width=2.0)
        draw_frame_rect(painter, header_rect, width=2.0)
        draw_frame_rect(painter, table_rect, width=2.0)
        draw_frame_rect(painter, notes_rect, width=2.0)

    # -------------------------
    # Layout: Landscape
    # -------------------------

    def _render_cam_page_landscape(
        self,
        painter: QPainter,
        page_rect: QRectF,
        *,
        payload: CamPrintPayload,
        setting_snapshot: Optional[QImage],
    ) -> None:
        """
        가로 A4:
        - 헤더(상단 풀폭)
        - 본문(좌/우): 좌=Setting 이미지 / 우=CAM 표
        - 특이사항(하단 풀폭)
        """
        # 여백
        margin_x = page_rect.width() * 0.01
        margin_y = page_rect.height() * 0.01

        content = QRectF(
            page_rect.left() + margin_x,
            page_rect.top() + margin_y,
            page_rect.width() - 2.0 * margin_x,
            page_rect.height() - 2.0 * margin_y
        )

        total_h = content.height()
        header_h = max(total_h * 0.16, 170.0)
        notes_h = max(total_h * 0.12, 150.0)
        body_h = total_h - header_h - notes_h

        header_rect = QRectF(content.left(), content.top(), content.width(), header_h)
        body_rect = QRectF(content.left(), header_rect.bottom(), content.width(), body_h)
        notes_rect = QRectF(content.left(), content.bottom() - notes_h, content.width(), notes_h)

        # 좌/우 분할
        gap = 10.0
        left_w = body_rect.width() * 0.52
        left_rect = QRectF(body_rect.left(), body_rect.top(), left_w - gap * 0.5, body_rect.height())
        right_rect = QRectF(left_rect.right() + gap, body_rect.top(), body_rect.width() - left_w - gap * 0.5, body_rect.height())

        # 공용 헤더
        if callable(self._header_drawer):
            self._header_drawer(painter, header_rect)
        else:
            draw_common_header(painter, header_rect, payload=payload.header, logo_pixmap=self._logo_pixmap)


        # 좌: Setting 이미지
        self._draw_setting_snapshot(painter, left_rect, setting_snapshot=setting_snapshot)

        # 우: CAM 표
        self._draw_cam_table(painter, right_rect, cam_rows=payload.cam_rows)

        # 공용 특이사항
        draw_common_notes(painter, notes_rect, title="특이사항", notes_text=payload.notes_text)

        # 프레임(마지막)
        draw_frame_rect(painter, content, width=2.0)
        draw_frame_rect(painter, header_rect, width=2.0)
        draw_frame_rect(painter, body_rect, width=2.0)
        draw_frame_rect(painter, left_rect, width=2.0)
        draw_frame_rect(painter, right_rect, width=2.0)
        draw_frame_rect(painter, notes_rect, width=2.0)

    # -------------------------
    # Blocks: Setting Snapshot
    # -------------------------

    def _draw_setting_snapshot(self, painter: QPainter, rect: QRectF, *, setting_snapshot: Optional[QImage]) -> None:
        """
        Setting 이미지(QImage)를 rect 안에 '비율 유지'로 출력한다.
        """
        painter.save()
        try:
            # 외곽
            pen = QPen(Qt.black)
            pen.setWidthF(1.6)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            inner = rect.adjusted(8.0, 8.0, -8.0, -8.0)

            # 타이틀
            title_h = 24.0
            title_rect = QRectF(inner.left(), inner.top(), inner.width(), title_h)
            img_rect = QRectF(inner.left(), inner.top() + title_h + 6.0, inner.width(), inner.height() - title_h - 6.0)

            painter.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
            painter.setPen(Qt.black)
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, "SETTING 이미지")

            # 이미지
            if setting_snapshot is None or setting_snapshot.isNull():
                painter.setFont(QFont("Malgun Gothic", 10))
                painter.drawText(img_rect, Qt.AlignCenter, "Setting 이미지 스냅샷 없음")
                return

            pm = QPixmap.fromImage(setting_snapshot)
            scaled = pm.scaled(
                int(img_rect.width()),
                int(img_rect.height()),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            x = img_rect.left() + (img_rect.width() - scaled.width()) / 2.0
            y = img_rect.top() + (img_rect.height() - scaled.height()) / 2.0
            painter.drawPixmap(QRectF(x, y, scaled.width(), scaled.height()), scaled, QRectF(scaled.rect()))
        finally:
            painter.restore()

    # -------------------------
    # Blocks: CAM Table
    # -------------------------

    def _draw_cam_table(self, painter: QPainter, rect: QRectF, *, cam_rows: Sequence[Mapping[str, Any]]) -> None:
        """
        CAM 표 출력(엑셀 템플릿 느낌으로 고정 행수로 출력).

        - 항상 24행(기본) 그려서 표 영역을 꽉 채웁니다.
        - 데이터가 부족하면 빈 행을 그립니다.
        - 표가 너무 위에만 “얇게” 보이는 현상을 방지합니다.
        """
        painter.save()
        try:
            # 외곽
            pen = QPen(Qt.black)
            pen.setWidthF(1.6)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            inner = rect.adjusted(8.0, 8.0, -8.0, -8.0)

            # ===== 열 정의 =====
            headers: List[str] = ["ToolNo", "ToolName", "Holder", "RPM", "Feed", "DOC", "WOC", "Coolant"]
            col_weights: List[float] = [0.08, 0.22, 0.20, 0.10, 0.10, 0.10, 0.10, 0.10]

            # x 좌표 계산
            xs: List[float] = [inner.left()]
            for w in col_weights:
                xs.append(xs[-1] + inner.width() * float(w))

            # ===== 고정 행수(엑셀 템플릿 느낌) =====
            fixed_rows = 24

            # 헤더/바디 높이 계산(표 영역을 꽉 채움)
            header_h = 34.0  # 헤더는 조금 두껍게
            body_h_total = max(0.0, inner.height() - header_h)
            row_h = body_h_total / float(fixed_rows) if fixed_rows > 0 else 28.0
            row_h = max(18.0, row_h)  # 너무 얇아지지 않게 최소 보장

            # 데이터는 최대 fixed_rows까지만 사용
            src_rows = list(cam_rows)[:fixed_rows]

            # ===== 헤더 그리기 =====
            painter.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
            for i, h in enumerate(headers):
                cell = QRectF(xs[i], inner.top(), xs[i + 1] - xs[i], header_h)
                painter.drawRect(cell)
                painter.drawText(cell.adjusted(4.0, 0.0, -4.0, 0.0), Qt.AlignCenter, h)

            # ===== 바디 그리기(고정 24행) =====
            painter.setFont(QFont("Malgun Gothic", 10))
            y = inner.top() + header_h

            for ridx in range(fixed_rows):
                row_dict = src_rows[ridx] if ridx < len(src_rows) else {}

                for i, key in enumerate(headers):
                    cell = QRectF(xs[i], y, xs[i + 1] - xs[i], row_h)
                    painter.drawRect(cell)

                    val = "" if row_dict.get(key) is None else str(row_dict.get(key))
                    # 숫자 계열은 가운데 정렬, 텍스트는 좌측 정렬(가독성)
                    if key in ("ToolNo", "RPM", "Feed", "DOC", "WOC"):
                        painter.drawText(cell.adjusted(4.0, 0.0, -4.0, 0.0), Qt.AlignCenter, val)
                    else:
                        painter.drawText(cell.adjusted(4.0, 0.0, -4.0, 0.0), Qt.AlignLeft | Qt.AlignVCenter, val)

                y += row_h

        finally:
            painter.restore()

