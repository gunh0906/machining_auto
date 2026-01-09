# print_engine.py
"""
A4 세팅 시트 인쇄 전용 엔진

- 가로형 / 세로형 이미지 자동 판별
- ROTATE ON/OFF 배지 표시
- 상단 헤더 + 이미지 + 세팅 정보 + 특이사항 요약
"""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import QRectF, Qt, QDate, QUrl, QPointF
from PySide6.QtGui import QPainter, QFont, QColor, QPageSize, QPageLayout, QPixmap, QDesktopServices, QPen, QImage, QBrush
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import QMessageBox, QLabel, QLineEdit, QComboBox

from pathlib import Path
import sys

from .settings_manager import get_operator_for_machine, sanitize_for_filename


class PrintEngine:
    def __init__(self, main_window):
        """
        main_window: MainWindow 인스턴스 (main.py)
        """
        self.main = main_window

        # ★ 회사 로고 로딩 (없으면 None)
        self._logo_pixmap: Optional[QPixmap] = None
        try:
            base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            logo_path = base_dir / "assets" / "main-logo(pdf).png"
            if logo_path.exists():
                self._logo_pixmap = QPixmap(str(logo_path))
        except Exception:
            self._logo_pixmap = None


    def _collect_extra_lines_from_layout(self, layout) -> list[str]:
        """
        QVBoxLayout에 추가된 (라벨 + 입력칸) 행들을 읽어 '라벨: 값' 리스트로 만든다.
        """
        lines: list[str] = []
        if layout is None:
            return lines

        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is None:
                continue

            lbl_text = ""
            val_text = ""

            for child in w.findChildren(QLabel):
                t = child.text().strip()
                if t:
                    lbl_text = t
                    break

            for child in w.findChildren(QLineEdit):
                v = child.text().strip()
                if v:
                    val_text = v
                    break

            if lbl_text and val_text:
                lines.append(f"{lbl_text}: {val_text}")

        return lines

    def _get_machine_name_safe(self) -> str:
        """
        설비명을 안전하게 반환합니다.
        - 통합 쉘 구조에서는 SettingMainWindow에 combo_machine이 없을 수 있습니다.
        - 가능한 경우 제공자(get_current_machine) 우선, 그 다음 combo_machine 사용.
        """
        try:
            if hasattr(self.main, "get_current_machine") and callable(getattr(self.main, "get_current_machine")):
                return (self.main.get_current_machine() or "").strip()
        except Exception:
            pass

        try:
            if hasattr(self.main, "combo_machine") and self.main.combo_machine is not None:
                return (self.main.combo_machine.currentText() or "").strip()
        except Exception:
            pass

        return ""


    def export_to_pdf(self, layout_choice: str = "세로"):
        """
        현재 세팅 시트를 A4 레이아웃으로 PDF 파일로 저장하는 함수.
        - 프로젝트명이 비어 있으면 경고 후 중단
        - 배경 이미지가 없으면 경고 후 중단
        - 사용자가 지정한 경로로 PDF를 생성.
        """
        # 1) 프로젝트명 / 설비명 확인
        project = self.main.edit_project.text().strip()
        # ✅ 설비명은 통합 쉘/Setting UI 구조에 따라 공급원이 달라질 수 있으므로 안전하게 취득
        machine = ""
        if hasattr(self.main, "get_current_machine") and callable(getattr(self.main, "get_current_machine")):
            machine = (self.main.get_current_machine() or "").strip()
        elif hasattr(self.main, "combo_machine") and self.main.combo_machine is not None:
            machine = (self.main.combo_machine.currentText() or "").strip()

        if not project:
            QMessageBox.warning(
                self.main,
                "PDF 생성",
                "프로젝트명이 입력되지 않았습니다.\n먼저 프로젝트명을 입력해 주시기 바랍니다."
            )
            return

        # 2) 인쇄할 이미지(Scene) 확인
        scene = getattr(self.main, "annotation_scene", None)
        if scene is None:
            QMessageBox.information(
                self.main,
                "PDF 생성",
                "PDF로 저장할 장면(Scene)이 존재하지 않습니다."
            )
            return

        pix_item = getattr(scene, "_pixmap_item", None)
        if pix_item is None or pix_item.pixmap().isNull():
            QMessageBox.information(
                self.main,
                "PDF 생성",
                "PDF로 저장할 이미지가 없습니다.\n먼저 이미지를 불러오거나 붙여넣어 주시기 바랍니다."
            )
            return

        # 3) 기본 파일명 구성 (프로젝트명_설비명_YYYYMMDD.pdf 형태)
        safe_project = sanitize_for_filename(project)
        safe_machine = sanitize_for_filename(machine or "MACHINE")

        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        default_name = f"{safe_project}_{safe_machine}_{today}.pdf"

        # 4) 저장 경로 선택 (마지막 PDF 폴더 기억)
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtCore import QSettings
        import os

        settings = QSettings("GH", "SettingSheet")
        last_pdf_dir = settings.value("last_pdf_dir", "")

        # 기본 경로: 마지막 폴더 + 기본 파일명
        initial_path = os.path.join(last_pdf_dir, default_name) if last_pdf_dir else default_name

        path, _ = QFileDialog.getSaveFileName(
            self.main,
            "PDF로 저장",
            initial_path,
            "PDF 파일 (*.pdf)"
        )
        if not path:
            return  # 사용자가 취소

        # 선택한 폴더 저장
        try:
            settings.setValue("last_pdf_dir", os.path.dirname(path))
        except Exception:
            pass


        # 5) QPrinter를 PDF 모드로 설정
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setFullPage(True)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)

        # ─ 사용자가 선택한 레이아웃 우선 ─
        if layout_choice == "가로":
            printer.setPageOrientation(QPageLayout.Landscape)
        else:
            printer.setPageOrientation(QPageLayout.Portrait)


        painter = QPainter(printer)
        if not painter.isActive():
            QMessageBox.critical(
                self.main,
                "PDF 생성 오류",
                "PDF 파일을 생성하는 중 알 수 없는 오류가 발생하였습니다."
            )
            return

        try:
            page_rect = QRectF(printer.pageLayout().paintRectPixels(printer.resolution()))
            self._render_page(painter, page_rect, layout_choice)

        finally:
            painter.end()

        # ★ 저장된 PDF를 기본 프로그램으로 즉시 열기
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            # 열기 실패 시에는 조용히 넘어가고, 아래 메시지만 띄웁니다.
            pass

        QMessageBox.information(
            self.main,
            "PDF 생성 완료",
            f"PDF 파일이 다음 경로에 생성 완료!.\n{path}"
        )


    # ───────────────────────────────── 페이지 레이아웃 선택 ──────────────────────────────
    def _render_page(self, painter: QPainter, page_rect: QRectF, layout_choice: str = "세로"):

        """
        페이지 전체 렌더링
        - 헤더 / 정보표 / 이미지 / 특이사항(notes)
        - 내용 먼저 그리고, 프레임(테두리)은 마지막에 다시 그림
        """

        # -----------------------------
        # 여백 및 콘텐츠 영역
        # -----------------------------
        margin_x = page_rect.width() * 0.005
        margin_y = page_rect.height() * 0.005

        content = QRectF(
            page_rect.left() + margin_x,
            page_rect.top() + margin_y,
            page_rect.width() - 2 * margin_x,
            page_rect.height() - 2 * margin_y
        )

        if layout_choice == "가로":
            self._draw_horizontal_layout(painter, content)
            return


        # -----------------------------
        # 영역 높이 계산
        # -----------------------------
        total_h = content.height()
        header_h = max(total_h * 0.12, 170.0)
        table_h = max(total_h * 0.22, 240.0)
        notes_h = max(total_h * 0.08, 150.0)
        # 이미지 영역 최소 높이 보장 (음수/과소 방지)



        # -----------------------------
        # 영역 분할
        # -----------------------------
        y = content.top()

        header_rect = QRectF(
            content.left(),
            y,
            content.width(),
            header_h
        )
        y += header_h

        table_rect = QRectF(
            content.left(),
            y,
            content.width(),
            table_h
        )
        y += table_h

        notes_rect = QRectF(
            content.left(),
            content.bottom() - notes_h,
            content.width(),
            notes_h
        )

        image_rect = QRectF(
            content.left(),
            y,
            content.width(),
            notes_rect.top() - y
        )

        # -----------------------------
        # 1) 내용 먼저 그림
        # -----------------------------
        self._draw_header(painter, header_rect)
        self._draw_info_table_block(painter, table_rect)
        self._draw_image(painter, image_rect)
        self._draw_notes_block(painter, notes_rect)

        # -----------------------------
        # 2) 프레임(테두리) 마지막에 다시 그림
        #    → 이미지/노트가 덮지 못하게 함
        # -----------------------------
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        pen = QPen(Qt.black)
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawRect(content)
        painter.drawRect(header_rect)
        painter.drawRect(table_rect)
        painter.drawRect(image_rect)
        painter.drawRect(notes_rect)

        painter.restore()

#--------------------------가로 레이아웃 2 -------------------------------------(적용)
    def _draw_info_table_block_landscape(self, painter: QPainter, rect: QRectF):
        """
        가로 모드 좌표표 (전하 지시: '아래 칸' 구조 강제)

        - X/Y 아래칸  → 기타좌표
        - Z 아래칸    → Z 기타좌표
        """
        m = self.main

        # ─────────────────────────────
        # 값 수집
        # ─────────────────────────────
        x_center = m.edit_x_center.text().strip()
        y_center = m.edit_y_center.text().strip()
        x_minus = m.edit_x_minus.text().strip()
        x_plus = m.edit_x_plus.text().strip()
        y_minus = m.edit_y_minus.text().strip()
        y_plus = m.edit_y_plus.text().strip()

        z_bottom = m.edit_z_bottom.text().strip()
        z_top = (
            m.edit_z_top.text().strip()
            if hasattr(m, "edit_z_top") and m.edit_z_top is not None
            else ""
        )

        # 기타좌표(= X/Y 아래칸)
        xy_extra_lines = []
        xy_extra_lines += self._collect_extra_lines_from_layout(
            getattr(m, "coord_extra_layout", None)
        )
        xy_extra_lines += self._collect_extra_lines_from_layout(
            getattr(m, "outer_extra_layout", None)
        )

        # Z 기타좌표(= Z 아래칸)
        z_extra_lines = []
        z_extra_lines += self._collect_extra_lines_from_layout(
            getattr(m, "z_extra_layout", None)
        )

        painter.save()
        try:
            # ─────────────────────────────
            # Painter 상태 고정(검정)
            # ─────────────────────────────
            pen = QPen(Qt.black)
            pen.setWidthF(1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            # 바깥 테두리
            painter.drawRect(rect)

            # ─────────────────────────────
            # 전체를 "상단(XY+기타)" / "하단(Z+Z기타)" 2단 분할
            # ─────────────────────────────
            total_h = rect.height()
            top_h = total_h * 0.62
            bot_h = total_h - top_h

            top_rect = QRectF(rect.left(), rect.top(), rect.width(), top_h)
            bot_rect = QRectF(rect.left(), top_rect.bottom(), rect.width(), bot_h)

            painter.drawLine(rect.left(), top_rect.bottom(), rect.right(), top_rect.bottom())

            # ─────────────────────────────
            # (상단) X/Y + 기타좌표(아래칸)
            # ─────────────────────────────
            x_row_h = top_rect.height() * 0.28
            y_row_h = top_rect.height() * 0.28
            extra_row_h = top_rect.height() - (x_row_h + y_row_h)

            x_row = QRectF(top_rect.left(), top_rect.top(), top_rect.width(), x_row_h)
            y_row = QRectF(top_rect.left(), x_row.bottom(), top_rect.width(), y_row_h)
            extra_row = QRectF(top_rect.left(), y_row.bottom(), top_rect.width(), extra_row_h)

            painter.drawLine(top_rect.left(), x_row.bottom(), top_rect.right(), x_row.bottom())
            painter.drawLine(top_rect.left(), y_row.bottom(), top_rect.right(), y_row.bottom())

            # 열 분할(라벨 / 센터 / ±) — X행+Y행까지만 적용
            w = top_rect.width()
            col_label = w * 0.16
            col_center = w * 0.40

            x0 = top_rect.left()
            x1 = x0 + col_label
            x2 = x1 + col_center
            x3 = top_rect.right()

            painter.drawLine(x1, x_row.top(), x1, y_row.bottom())
            painter.drawLine(x2, x_row.top(), x2, y_row.bottom())

            pad = 6.0

            painter.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
            painter.drawText(QRectF(x0, x_row.top(), x1 - x0, x_row.height()), Qt.AlignCenter, "X")
            painter.drawText(QRectF(x0, y_row.top(), x1 - x0, y_row.height()), Qt.AlignCenter, "Y")

            painter.drawText(
                QRectF(x1, x_row.top(), x2 - x1, x_row.height()).adjusted(pad, 2, -pad, -2),
                Qt.AlignCenter,
                x_center or "0.000",
            )
            painter.drawText(
                QRectF(x1, y_row.top(), x2 - x1, y_row.height()).adjusted(pad, 2, -pad, -2),
                Qt.AlignCenter,
                y_center or "0.000",
            )

            painter.setFont(QFont("Malgun Gothic", 14, QFont.Bold))
           # ─────────────────────────────
            # ± 칸을 상/하 2칸으로 분리
            # ─────────────────────────────
            pm_w = x3 - x2

            # X행: 위(X-), 아래(X+)
            x_mid = x_row.top() + (x_row.height() / 2.0)
            painter.drawLine(x2, x_mid, x3, x_mid)

            painter.drawText(
                QRectF(x2, x_row.top(), pm_w, x_row.height() / 2.0).adjusted(pad, 2, -pad, -2),
                Qt.AlignHCenter | Qt.AlignVCenter,
                f"X- {x_minus or '0.000'}",
            )
            painter.drawText(
                QRectF(x2, x_mid, pm_w, x_row.height() / 2.0).adjusted(pad, 2, -pad, -2),
                Qt.AlignHCenter | Qt.AlignVCenter,
                f"X+ {x_plus or '0.000'}",
            )

            # Y행: 위(Y-), 아래(Y+)
            y_mid = y_row.top() + (y_row.height() / 2.0)
            painter.drawLine(x2, y_mid, x3, y_mid)

            painter.drawText(
                QRectF(x2, y_row.top(), pm_w, y_row.height() / 2.0).adjusted(pad, 2, -pad, -2),
                Qt.AlignHCenter | Qt.AlignVCenter,
                f"Y- {y_minus or '0.000'}",
            )
            painter.drawText(
                QRectF(x2, y_mid, pm_w, y_row.height() / 2.0).adjusted(pad, 2, -pad, -2),
                Qt.AlignHCenter | Qt.AlignVCenter,
                f"Y+ {y_plus or '0.000'}",
            )

           

            # ─ 기타좌표(= X/Y 아래칸) ─
            painter.setFont(QFont("Malgun Gothic", 14, QFont.Bold))
            title_h = painter.fontMetrics().height() + 4

            extra_title = QRectF(
                extra_row.left() + 8,
                extra_row.top() + 4,
                extra_row.width() - 16,
                title_h,
            )
            extra_body = QRectF(
                extra_row.left() + 8,
                extra_title.bottom() + 2,
                extra_row.width() - 16,
                extra_row.bottom() - (extra_title.bottom() + 4),
            )

            painter.drawText(extra_title, Qt.AlignLeft | Qt.AlignVCenter, "기타좌표")
            painter.setFont(QFont("Malgun Gothic", 11))
            painter.drawText(
                extra_body,
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                "\n".join(xy_extra_lines) if xy_extra_lines else "(기타좌표 없음)",
            )

            # ─────────────────────────────
            # (하단) Z + Z 기타좌표(아래칸)
            # ─────────────────────────────
            z_row_h = bot_rect.height() * 0.35
            z_extra_h = bot_rect.height() - z_row_h

            z_row = QRectF(bot_rect.left(), bot_rect.top(), bot_rect.width(), z_row_h)
            z_extra_row = QRectF(bot_rect.left(), z_row.bottom(), bot_rect.width(), z_extra_h)

            painter.drawLine(bot_rect.left(), z_row.bottom(), bot_rect.right(), z_row.bottom())

            painter.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
            painter.drawText(
                z_row.adjusted(8, 2, -8, -2),
                Qt.AlignHCenter | Qt.AlignVCenter,
                f"Z  바닥 {z_bottom or '0.000'}",
            )

            painter.setFont(QFont("Malgun Gothic", 14, QFont.Bold))
            zt_title = QRectF(
                z_extra_row.left() + 8,
                z_extra_row.top() + 4,
                z_extra_row.width() - 16,
                title_h,
            )
            zt_body = QRectF(
                z_extra_row.left() + 8,
                zt_title.bottom() + 2,
                z_extra_row.width() - 16,
                z_extra_row.bottom() - (zt_title.bottom() + 4),
            )

            painter.drawText(zt_title, Qt.AlignLeft | Qt.AlignVCenter, "Z 기타좌표")
            painter.setFont(QFont("Malgun Gothic", 11))
            painter.drawText(
                zt_body,
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                "\n".join(z_extra_lines) if z_extra_lines else "(Z 기타좌표 없음)",
            )

        finally:
            painter.restore()


    # ───────────────────────────────── 가로 레이아웃 ───────────────────────────────
    def _draw_horizontal_layout(self, painter: QPainter, rect: QRectF):
        """
        A4 가로 레이아웃 (기존 함수 재설계)
        - 상단: 헤더 (로고 / 제목 / VIEW + 설비/작업자/날짜)
        - 중단: 좌측 좌표표 / 우측 이미지
        - 하단: 특이사항 (전체 폭, 길게)
        """
        total_h = rect.height()

        # 1) 헤더 (기존 로직 재사용)
        header_h = max(total_h * 0.18, 160.0)
        header_rect = QRectF(rect.left(), rect.top(), rect.width(), header_h)
        self._compact_logo = True
        self._draw_header(painter, header_rect)
        self._compact_logo = False


        # 2) 헤더 아래 전체 영역
        body_top = header_rect.bottom() + 8.0
        body_rect = QRectF(
            rect.left(),
            body_top,
            rect.width(),
            rect.bottom() - body_top
        )

        # 3) 하단 특이사항 (전체 폭)
        notes_h = max(rect.height() * 0.1, 150.0)
        notes_rect = QRectF(
            body_rect.left(),
            body_rect.bottom() - notes_h,
            body_rect.width(),
            notes_h
        )

        # 4) 중단 영역 (좌표표 + 이미지)
        main_rect = QRectF(
            body_rect.left(),
            body_rect.top(),
            body_rect.width(),
            notes_rect.top() - body_rect.top()
        )

        # 좌/우 분할 (좌표표 28% / 이미지 72%)
        left_w = main_rect.width() * 0.45
        left_rect = QRectF(
            main_rect.left(),
            main_rect.top(),
            left_w,
            main_rect.height()
        )
        right_rect = QRectF(
            left_rect.right(),
            main_rect.top(),
            main_rect.right() - left_rect.right(),
            main_rect.height()
        )

        # 5) 내용 먼저 그리기 (기존 함수 재사용)
        self._draw_info_table_block_landscape(
            painter,
            left_rect.adjusted(6.0, 6.0, -6.0, -6.0)
        )

        self._draw_image(
            painter,
            right_rect.adjusted(6.0, 6.0, -6.0, -6.0)
        )
        self._draw_notes_block(painter, notes_rect)

        # 6) 테두리 (마지막에)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        pen = QPen(Qt.black)
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawRect(rect)
        painter.drawRect(header_rect)
        painter.drawRect(main_rect)
        painter.drawRect(left_rect)
        painter.drawRect(right_rect)
        painter.drawRect(notes_rect)

        painter.restore()



    # ───────────────────────────────── 세로 레이아웃 ─────────────────────────────────
    def _draw_vertical_layout(self, painter: QPainter, rect: QRectF):
        """
        A4 세로 모드:
        - 상단: 헤더
        - 그 아래: 좌표/치수/특이사항까지 포함한 큰 표
        - 그 아래: 이미지 카드
        """
        total_h = rect.height()

        header_h = total_h * 0.18
        table_h  = total_h * 0.32   # 좌표 + 특이사항 표
        image_h  = total_h - header_h - table_h

        header_rect = QRectF(rect.left(), rect.top(), rect.width(), header_h)
        table_rect  = QRectF(
            rect.left(),
            header_rect.bottom() + 6.0,
            rect.width(),
            table_h - 6.0,
        )
        image_rect  = QRectF(
            rect.left(),
            table_rect.bottom() + 6.0,
            rect.width(),
            image_h - 6.0,
        )

        # 헤더
        self._draw_header(painter, header_rect)

        # 상단: 좌표/외곽/Z/추가 + 특이사항까지 하나의 표
        self._draw_info_and_notes_block(painter, table_rect)

        # 하단: 이미지 카드
        self._draw_image(painter, image_rect)

    def _draw_header(self, painter: QPainter, rect: QRectF):
        """
        헤더 표:
        1행(3열): Logo / 제목 / ROTATE(배경색)
        2행: [왼쪽] 세팅 모드(CENTER / ONE-POINT) 컬러 박스 + [오른쪽] 설비/작업자/날짜

        바깥 테두리는 _render_page에서 이미 그림.
        """
        painter.save()

        # 값 수집
        project = self.main.edit_project.text().strip() or "제목 미입력"
        machine = self._get_machine_name_safe() or "설비 미지정"
        current_op = get_operator_for_machine(machine, getattr(self.main, "operator_map", {})) or "작업자 미지정"
        date_str = QDate.currentDate().toString("yyyy-MM-dd")

        # ✅ 통합 쉘에서는 rotate 상태가 주입될 수 있음(_shell_rotate_on 우선)
        rotate_on = bool(getattr(self.main, "_shell_rotate_on", False))
        rotate_text = "ROTATE ON" if rotate_on else "ROTATE OFF"

        # 모드(CENTER / ONE-POINT)
        mode_center = bool(getattr(self.main, "mode_center", True))
        mode_text = "세팅 : CENTER" if mode_center else "세팅 : ONE-POINT"

        # ROTATE 배경색(기존 컨셉 유지)
        # ROTATE 배경색 (복구: ON=빨강, OFF=연회색)
        rotate_bg = QColor(220, 50, 50) if rotate_on else QColor(235, 235, 235)
        rotate_fg = QColor(255, 255, 255) if rotate_on else QColor(0, 0, 0)

        # ★ MODE 배경색(ROTATE와 다르게)
        #   - CENTER: 청록 계열
        #   - ONE-POINT: 주황/노랑 계열
        mode_bg = QColor(0, 170, 170) if mode_center else QColor(230, 140, 0)

        # 내부 패딩(텍스트용)
        pad = 6.0
        inner = rect.adjusted(pad, pad, -pad, -pad)

        # 2행 구성
        row1_h = inner.height() * 0.65
        row2_h = inner.height() - row1_h
        row1 = QRectF(inner.left(), inner.top(), inner.width(), row1_h)
        row2 = QRectF(inner.left(), row1.bottom(), inner.width(), row2_h)

        # 내부 구분선
        pen = QPen(Qt.black)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(inner.left(), row1.bottom(), inner.right(), row1.bottom())

        # ─────────────────────
        # 1행(3열): 로고 / 제목 / ROTATE
        # ─────────────────────
        c1_w = row1.width() * 0.22   # Logo
        c3_w = row1.width() * 0.18   # ROTATE
        c2_w = row1.width() - c1_w - c3_w

        c1 = QRectF(row1.left(), row1.top(), c1_w, row1.height())
        c2 = QRectF(c1.right(), row1.top(), c2_w, row1.height())
        c3 = QRectF(c2.right(), row1.top(), c3_w, row1.height())

        # 세로 구분선
        painter.drawLine(c1.right(), row1.top(), c1.right(), row1.bottom())
        painter.drawLine(c2.right(), row1.top(), c2.right(), row1.bottom())

        # 로고
        if getattr(self, "_logo_pixmap", None) is not None and not self._logo_pixmap.isNull():
            lr = c1.adjusted(4, 4, -4, -4)
            painter.save()
            painter.setClipRect(lr)
            scaled_logo = self._logo_pixmap.scaled(
                int(lr.width()), int(lr.height()),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = lr.left() + (lr.width() - scaled_logo.width()) / 2.0
            y = lr.top() + (lr.height() - scaled_logo.height()) / 2.0
            painter.drawPixmap(QRectF(x, y, scaled_logo.width(), scaled_logo.height()), scaled_logo, QRectF(scaled_logo.rect()))
            painter.restore()

        # 제목
        painter.setPen(Qt.black)
        painter.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
        painter.drawText(c2.adjusted(6, 0, -6, 0), Qt.AlignHCenter | Qt.AlignVCenter, project)

        # ROTATE 박스
        painter.save()
        painter.setPen(QPen(Qt.black, 1.2))
        painter.setBrush(QBrush(rotate_bg))
        painter.drawRect(c3)

        painter.setPen(QPen(rotate_fg))
        painter.setFont(QFont("Malgun Gothic", 14, QFont.Bold))
        painter.drawText(c3, Qt.AlignCenter, rotate_text)
        painter.restore()


        # ─────────────────────
        # 2행: [왼쪽] MODE 박스 + [오른쪽] 설비/작업자/날짜
        # ─────────────────────
        # 왼쪽 MODE 칸 폭 (전하 요청: 왼쪽에 칸을 만들고 안에 표시)
        mode_w = row2.width() * 0.28
        mode_rect = QRectF(row2.left(), row2.top(), mode_w, row2.height())
        info_rect = QRectF(mode_rect.right(), row2.top(), row2.width() - mode_w, row2.height())

        # 세로 구분선
        painter.setPen(QPen(Qt.black, 1.2))
        painter.drawLine(mode_rect.right(), row2.top(), mode_rect.right(), row2.bottom())

        # MODE 박스(색상 표현)
        painter.save()
        painter.setPen(QPen(Qt.black, 1.2))
        painter.setBrush(QBrush(mode_bg))
        painter.drawRect(mode_rect)

        painter.setPen(Qt.white)  # 색 박스 위 흰 글씨
        painter.setFont(QFont("Malgun Gothic", 13, QFont.Bold))
        painter.drawText(mode_rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, mode_text)
        painter.restore()

        # 설비/작업자/날짜 (오른쪽 영역 안에서만 정렬)
        info_text = f"설비: {machine}    작업자: {current_op}    날짜: {date_str}"
        painter.setPen(Qt.black)
        painter.setFont(QFont("Malgun Gothic", 14))
        # ★ 기존처럼 전체 row2 기준 오른쪽 정렬이 아니라,
        #   info_rect 내부 기준으로 좌측 정렬(가독성↑, 치우침↓)
        painter.drawText(info_rect.adjusted(10.0, 0, -6.0, 0), Qt.AlignRight | Qt.AlignVCenter, info_text)

        painter.restore()


    # ───────────────────────────────── 헤더 + ROTATE 배지 ────────────────────────────────

    def _draw_rotate_badge(self, painter: QPainter, rect: QRectF):
        """
        상단 우측에 ROTATE ON / OFF 작은 배지를 그립니다.
        각도는 출력하지 않고, ON/OFF 여부만 표시.
        """
        painter.save()

        rotate_on = getattr(self.main.btn_rotate_on, "isChecked", lambda: False)()
        text = "ROTATE ON" if rotate_on else "ROTATE OFF"

        if rotate_on:
            bg_color = QColor(220, 60, 60)
            text_color = QColor(255, 255, 255)
        else:
            bg_color = QColor(200, 200, 200)
            text_color = QColor(30, 30, 30)

        painter.setBrush(bg_color)
        painter.setPen(bg_color.darker(140))
        painter.drawRoundedRect(rect, 6.0, 6.0)

        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.setPen(Qt.black)
        painter.drawText(rect, Qt.AlignCenter, text)

        painter.restore()

    # ───────────────────────────────── 이미지 렌더링 ──────────────────────────────
    def _draw_image(self, painter: QPainter, rect: QRectF, image: QImage = None):
        """
        중요:
        - 배경 pixmap만 출력하면 주석(QGraphicsItem)이 누락됨
        - Scene 전체를 QImage에 먼저 render한 뒤 printer에 drawImage로 출력
        """
        scene = getattr(self.main, "annotation_scene", None)
        if scene is None:
            return

        # Scene에 올라간 "전체 아이템"이 포함되도록 boundingRect 사용
        src_rect = scene.itemsBoundingRect()
        if src_rect.isEmpty():
            return

        # 여유(외곽선 잘림 방지)
        src_rect = src_rect.adjusted(-6.0, -6.0, 6.0, 6.0)

        img_w = max(1, int(rect.width()))
        img_h = max(1, int(rect.height()))

        # 1) 오프스크린 캔버스 생성(흰 배경)
        img = QImage(img_w, img_h, QImage.Format_ARGB32_Premultiplied)
        img.fill(0xFFFFFFFF)

        # 2) QImage에 Scene 렌더링(주석 포함)
        p_img = QPainter(img)
        try:
            p_img.setRenderHint(QPainter.Antialiasing, True)
            p_img.setRenderHint(QPainter.TextAntialiasing, True)
            p_img.setRenderHint(QPainter.SmoothPixmapTransform, True)

            src_ratio = src_rect.width() / src_rect.height() if src_rect.height() > 0 else 1.0
            dst_ratio = img_w / img_h if img_h > 0 else 1.0

            # contain: img 안에 비율 유지로 전부 들어오게
            if dst_ratio > src_ratio:
                fit_h = img_h
                fit_w = int(fit_h * src_ratio)
                fit_x = int((img_w - fit_w) / 2)
                fit_y = 0
            else:
                fit_w = img_w
                fit_h = int(fit_w / src_ratio) if src_ratio > 0 else img_h
                fit_x = 0
                fit_y = int((img_h - fit_h) / 2)

            fit_rect = QRectF(fit_x, fit_y, fit_w, fit_h)
            scene.render(p_img, fit_rect, src_rect)

        finally:
            p_img.end()

        # 3) 프린터에 출력(이미지는 rect 안에서만)
        painter.save()
        try:
            painter.setClipRect(rect)
            painter.drawImage(rect.topLeft(), img)
        finally:
            painter.restore()


    # ───────────────────────────────── 정보/특이사항 블록 ────────────────────────────────
    def _collect_info_text(self) -> str:
        """
        좌표 / 외곽 / Z / 추가 항목들을 한 번에 모아
        '표처럼' 보이도록 컴팩트한 멀티라인 문자열로 만들어 돌려줍니다.

        ※ Lx / Ly 줄은 표시하지 않습니다.
        """
        m = self.main

        # 모드
        mode = "CENTER" if m.btn_mode_center.isChecked() else "ONE-POINT"

        # 센터 좌표
        x_center = m.edit_x_center.text().strip()
        y_center = m.edit_y_center.text().strip()

        # 외곽 치수
        x_minus = m.edit_x_minus.text().strip()
        x_plus  = m.edit_x_plus.text().strip()
        y_minus = m.edit_y_minus.text().strip()
        y_plus  = m.edit_y_plus.text().strip()

        # Z 정보
        z_bottom = m.edit_z_bottom.text().strip()
        z_top    = m.edit_z_top.text().strip()
        z_height = m.lbl_z_height.text().strip()

        lines = []

        # ─ 기준 모드 ─
        lines.append("● 기준 모드")
        lines.append(f"   모드 : {mode}")
        if mode == "CENTER":
            lines.append(f"   X 센터 : {x_center or '-'}")
            lines.append(f"   Y 센터 : {y_center or '-'}")
        else:
            lines.append(f"   X 표시부 : {x_center or '-'}")
            lines.append(f"   Y 표시부 : {y_center or '-'}")

        # ─ 외곽 치수 ─
        lines.append("● 외곽 치수 (X/Y)")
        lines.append(f"   X- : {x_minus or '-'}   /   X+ : {x_plus or '-'}")
        lines.append(f"   Y- : {y_minus or '-'}   /   Y+ : {y_plus or '-'}")

        # ─ Z 정보 ─
        lines.append("● Z 정보")
        lines.append(f"   Z 바닥 : {z_bottom or '-'}")
        lines.append(f"   Z 상면 기준 : {z_top or '-'}")
        if z_height:
            lines.append(f"   {z_height}")

        # ─ 추가 좌표 / 치수 상세 ─
        from PySide6.QtWidgets import QLabel, QLineEdit

        coord_items = []
        for i in range(m.coord_extra_layout.count()):
            item = m.coord_extra_layout.itemAt(i)
            row = item.widget()
            if row is None:
                continue
            row_layout = row.layout()
            if row_layout is None or row_layout.count() < 2:
                continue
            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text().strip()
                value = edit.text().strip()
                if title or value:
                    coord_items.append(f"{title} : {value}")

        outer_items = []
        for i in range(m.outer_extra_layout.count()):
            item = m.outer_extra_layout.itemAt(i)
            row = item.widget()
            if row is None:
                continue
            row_layout = row.layout()
            if row_layout is None or row_layout.count() < 2:
                continue
            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text().strip()
                value = edit.text().strip()
                if title or value:
                    outer_items.append(f"{title} : {value} mm")

        z_items = []
        for i in range(m.z_extra_layout.count()):
            item = m.z_extra_layout.itemAt(i)
            row = item.widget()
            if row is None:
                continue
            row_layout = row.layout()
            if row_layout is None or row_layout.count() < 2:
                continue
            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text().strip()
                value = edit.text().strip()
                if title or value:
                    z_items.append(f"{title} : {value} mm")

        lines.append("● 추가 좌표 / 치수")
        if coord_items:
            lines.append("   - 추가 좌표")
            for s in coord_items:
                lines.append(f"       · {s}")
        if outer_items:
            lines.append("   - 외곽 추가 치수")
            for s in outer_items:
                lines.append(f"       · {s}")
        if z_items:
            lines.append("   - Z 추가 치수")
            for s in z_items:
                lines.append(f"       · {s}")
        if not (coord_items or outer_items or z_items):
            lines.append("   (등록된 추가 항목이 없습니다.)")

        # 중간중간 빈 줄 없이 꾸준히 이어지도록 구성
        return "\n".join(lines)

    def _collect_notes_text(self) -> str:
        """
        특이사항 텍스트를 가져옵니다.
        """
        notes = self.main.notes_edit.toPlainText().strip()
        return notes
    
    def _draw_info_block(self, painter: QPainter, rect: QRectF):
        """
        기준 모드 / 외곽 / Z / 추가 치수 정보를
        단일 박스 안에 표처럼 출력합니다.
        """
        info_text = self._collect_info_text()
        if not info_text:
            return

        painter.save()

        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))

        # 외곽 테두리
        painter.drawRect(rect)

        # 안쪽 여백
        inner = QRectF(
            rect.left() + 4.0,
            rect.top() + 4.0,
            rect.width() - 8.0,
            rect.height() - 8.0,
        )
        painter.setPen(Qt.black)

        painter.drawText(inner, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, info_text)

        painter.restore()

    def _draw_notes_block(self, painter: QPainter, rect: QRectF):
        notes = (self._collect_notes_text() or "").strip()

        painter.save()
        try:
            painter.setClipRect(rect)

            # 배경 덮기(묻힘/가림 방지)
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.white)
            painter.drawRect(rect)

            # 테두리
            pen = QPen(Qt.black)
            pen.setWidthF(2.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            # 내부 여백(위쪽 여백을 조금 더 줘서 제목이 clip에 닿지 않게)
            inner = rect.adjusted(10.0, 12.0, -10.0, -10.0)

            painter.setPen(Qt.black)
            painter.setBrush(Qt.NoBrush)

            # 제목: 폰트 메트릭 기반 높이로 계산(★ 제목 잘림 해결 핵심)
            title_font = QFont("Malgun Gothic", 11, QFont.Bold)
            painter.setFont(title_font)
            fm_title = painter.fontMetrics()
            title_h = float(fm_title.height() + 6)

            title_rect = QRectF(inner.left(), inner.top(), inner.width(), title_h)
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, "특이사항")

            # 본문 영역
            body_top = title_rect.bottom() + 6.0
            body_h = inner.bottom() - body_top
            if body_h <= 2.0 or not notes:
                return

            body_rect = QRectF(inner.left(), body_top, inner.width(), body_h)

            # C안: 폰트 자동 축소(10 → 6)
            def wrap_with_font(font_pt: int):
                painter.setFont(QFont("Malgun Gothic", font_pt))
                fm = painter.fontMetrics()
                line_h = max(1, fm.lineSpacing())

                def wrap_line(text: str, max_w: float):
                    words = text.replace("\r", "").split()
                    if not words:
                        return []
                    lines = []
                    cur = words[0]
                    for w in words[1:]:
                        cand = cur + " " + w
                        if fm.horizontalAdvance(cand) <= max_w:
                            cur = cand
                        else:
                            lines.append(cur)
                            cur = w
                    lines.append(cur)
                    return lines

                wrapped = []
                for para in notes.replace("\r", "").split("\n"):
                    para = para.strip()
                    if not para:
                        wrapped.append("")
                    else:
                        wrapped.extend(wrap_line(para, body_rect.width()))
                return wrapped, line_h

            final_lines = []
            for pt in range(10, 5, -1):
                lines, lh = wrap_with_font(pt)
                if len(lines) * lh <= body_h:
                    final_lines = lines
                    break

            if not final_lines:
                final_lines, _ = wrap_with_font(6)

            painter.setPen(Qt.black)
            painter.drawText(body_rect, Qt.AlignLeft | Qt.AlignTop, "\n".join(final_lines))

        finally:
            painter.restore()



    def _draw_info_table_block(self, painter: QPainter, rect: QRectF):
        """
        좌표 표(병합 셀 포함).
        - X/Y 센터값 칸은 세로로 2칸 병합
        - Z 바닥은 (센터+±) 영역 병합
        - 병합 셀 위로 가로선/세로선을 지나치게 그리지 않는다(병합 깨짐 방지)
        - 우측 기타 좌표는 추가 입력 레이아웃에서 실제 값을 읽어 표시한다
        """
        m = self.main

        x_center = m.edit_x_center.text().strip()
        y_center = m.edit_y_center.text().strip()
        x_minus = m.edit_x_minus.text().strip()
        x_plus = m.edit_x_plus.text().strip()
        y_minus = m.edit_y_minus.text().strip()
        y_plus = m.edit_y_plus.text().strip()
        z_bottom = m.edit_z_bottom.text().strip()

        # 추가 좌표/외곽 추가 치수/Z 기타좌표를 레이아웃에서 실제로 읽는다
        right_top_lines = []
        right_top_lines += self._collect_extra_lines_from_layout(getattr(m, "coord_extra_layout", None))
        right_top_lines += self._collect_extra_lines_from_layout(getattr(m, "outer_extra_layout", None))
        if not right_top_lines:
            right_top_lines = ["(기타 좌표 없음)"]

        right_z_lines = self._collect_extra_lines_from_layout(getattr(m, "z_extra_layout", None))
        if not right_z_lines:
            right_z_lines = ["(Z 기타좌표 없음)"]

        painter.save()

        pen = QPen(Qt.black)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # 컬럼 비율: [라벨][센터][±][기타]
        w = rect.width()
        col_label = w * 0.10
        col_center = w * 0.26
        col_pm = w * 0.22

        x0 = rect.left()
        x1 = x0 + col_label
        x2 = x1 + col_center
        x3 = x2 + col_pm
        x4 = rect.right()

        # 행: 상단 4칸(±), 하단 1칸(Z)
        h = rect.height()
        sub_h = h * 0.16
        y0 = rect.top()
        y1 = y0 + sub_h
        y2 = y1 + sub_h
        y3 = y2 + sub_h
        y4 = y3 + sub_h
        y5 = rect.bottom()

        # 세로선(전체 높이) - 단, x2(센터/± 경계)는 Z 병합 때문에 y0~y4까지만 그린다
        painter.drawLine(x1, y0, x1, y5)
        painter.drawLine(x2, y0, x2, y4)   # ★ Z 구간(y4~y5)에서는 그리지 않음(병합)
        painter.drawLine(x3, y0, x3, y5)

        # 가로선:
        # y1, y3는 ± 칸을 쪼개는 선이므로 (± 컬럼 x2~x3)에서만 그린다
        painter.drawLine(x2, y1, x3, y1)
        painter.drawLine(x2, y3, x3, y3)

        # y2는 X구간과 Y구간을 나누는 선 → 좌측 3컬럼(x0~x3) 전체에 필요
        painter.drawLine(x0, y2, x3, y2)

        # y4는 Z 시작선 → 전체 폭
        painter.drawLine(x0, y4, x4, y4)

        # 텍스트 패딩
        p = 6.0

        # 라벨 X/Y/Z
        painter.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
        painter.setPen(Qt.black)
        painter.drawText(QRectF(x0, y0, x1 - x0, y2 - y0), Qt.AlignCenter, "X")
        painter.drawText(QRectF(x0, y2, x1 - x0, y4 - y2), Qt.AlignCenter, "Y")
        painter.drawText(QRectF(x0, y4, x1 - x0, y5 - y4), Qt.AlignCenter, "Z")

        # 센터값(병합: X는 y0~y2, Y는 y2~y4)
        # 센터값 (Z 바닥과 동일: 16pt Bold, 가운데 정렬)
        painter.setFont(QFont("Malgun Gothic", 16, QFont.Bold))
        painter.setPen(Qt.black)

        x_center_rect = QRectF(
            x1,
            y0,
            x2 - x1,
            y2 - y0
        ).adjusted(p, p, -p, -p)

        y_center_rect = QRectF(
            x1,
            y2,
            x2 - x1,
            y4 - y2
        ).adjusted(p, p, -p, -p)

        painter.drawText(
            x_center_rect,
            Qt.AlignCenter,
            (x_center or "0.000")
        )
        painter.drawText(
            y_center_rect,
            Qt.AlignCenter,
            (y_center or "0.000")
        )


        # ± 값 (4칸: y0,y1,y2,y3)
        painter.setFont(QFont("Malgun Gothic", 14))

        def draw_pm(y_top: float, label: str, value: str):
            cell = QRectF(
                x2,
                y_top,
                x3 - x2,
                sub_h
            )

            # 폰트(값은 굵게)
            label_font = QFont("Malgun Gothic", 14)
            value_font = QFont("Malgun Gothic", 14, QFont.Bold)

            # 라벨 폭을 폰트 메트릭으로 계산(고정 36px 제거)
            painter.setFont(label_font)
            fm = painter.fontMetrics()
            label_w = float(fm.horizontalAdvance(label)) + 10.0  # 좌우 여유 포함

            # 셀 내부 패딩
            pad_l = 24.0
            pad_r = 8.0

            label_rect = QRectF(
                cell.left() + pad_l,
                cell.top(),
                label_w,
                cell.height()
            )

            # 값 영역은 경계선/라벨과 충분히 떨어지게 (★ '.' 잘림 방지 핵심)
            value_rect = QRectF(
                label_rect.right() + 16.0,
                cell.top(),
                cell.right() - (label_rect.right() + 16.0) - pad_r,
                cell.height()
            )

            painter.setPen(Qt.black)

            # 라벨
            painter.setFont(label_font)
            painter.drawText(
                label_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                label
            )

            # 값(굵게 + 가운데 정렬)
            painter.setFont(value_font)
            painter.drawText(
                value_rect,
                Qt.AlignCenter,
                value or "0.000"
            )



        draw_pm(y0, "X-", x_minus)
        draw_pm(y1, "X+", x_plus)
        draw_pm(y2, "Y-", y_minus)
        draw_pm(y3, "Y+", y_plus)

        # Z 바닥(센터+± 병합: x1~x3, y4~y5)
        painter.setFont(QFont("Malgun Gothic", 16, QFont.Bold))
        z_rect = QRectF(x1, y4, x3 - x1, y5 - y4).adjusted(p, p, -p, -p)
        painter.setPen(Qt.black)
        painter.drawText(z_rect, Qt.AlignCenter, f"바닥  {z_bottom}")

        # 우측 기타 좌표
        painter.setFont(QFont("Malgun Gothic", 13))
        rt = QRectF(x3, y0, x4 - x3, y4 - y0).adjusted(p, p, -p, -p)
        painter.setPen(Qt.black)
        painter.drawText(rt, Qt.AlignLeft | Qt.AlignTop, "기타 좌표\n" + "\n".join(right_top_lines))

        rz = QRectF(x3, y4, x4 - x3, y5 - y4).adjusted(p, p, -p, -p)
        painter.setPen(Qt.black)
        painter.drawText(rz, Qt.AlignLeft | Qt.AlignTop, "Z 기타좌표\n" + "\n".join(right_z_lines))

        painter.restore()




    def _draw_info_and_notes_block(self, painter: QPainter, rect: QRectF, draw_outer: bool = True):
        """
        좌표 / 치수 / 특이사항을 하나의 큰 표 안에서
        2열 × 2행 + 하단 특이사항 구조로 출력합니다.

        [좌 상] 기준 모드      [우 상] 외곽 치수
        [좌 중] Z 정보         [우 중] 기타 좌표/추가 치수
        [하단 전체] 특이사항
        """
        from PySide6.QtWidgets import QLabel, QLineEdit

        m = self.main

        # ─ 기본 값 수집 ─
        mode = "CENTER" if m.btn_mode_center.isChecked() else "ONE-POINT"
        x_center = m.edit_x_center.text().strip()
        y_center = m.edit_y_center.text().strip()

        x_minus = m.edit_x_minus.text().strip()
        x_plus  = m.edit_x_plus.text().strip()
        y_minus = m.edit_y_minus.text().strip()
        y_plus  = m.edit_y_plus.text().strip()

        z_bottom = m.edit_z_bottom.text().strip()
        z_top    = m.edit_z_top.text().strip()
        z_height = m.lbl_z_height.text().strip()

        # 추가 좌표 / 치수 수집
        coord_items = []
        for i in range(m.coord_extra_layout.count()):
            item = m.coord_extra_layout.itemAt(i)
            row = item.widget()
            if row is None:
                continue
            row_layout = row.layout()
            if row_layout is None or row_layout.count() < 2:
                continue
            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text().strip()
                value = edit.text().strip()
                if title or value:
                    coord_items.append(f"{title} : {value}")

        outer_items = []
        for i in range(m.outer_extra_layout.count()):
            item = m.outer_extra_layout.itemAt(i)
            row = item.widget()
            if row is None:
                continue
            row_layout = row.layout()
            if row_layout is None or row_layout.count() < 2:
                continue
            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text().strip()
                value = edit.text().strip()
                if title or value:
                    outer_items.append(f"{title} : {value} mm")

        z_items = []
        for i in range(m.z_extra_layout.count()):
            item = m.z_extra_layout.itemAt(i)
            row = item.widget()
            if row is None:
                continue
            row_layout = row.layout()
            if row_layout is None or row_layout.count() < 2:
                continue
            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text().strip()
                value = edit.text().strip()
                if title or value:
                    z_items.append(f"{title} : {value} mm")

        notes_text = m.notes_edit.toPlainText().strip()

        # ─ 각 칸에 들어갈 텍스트 구성 ─

        left_top = [
            "● 기준 모드",
            f"  모드 : {mode}",
        ]

        if mode == "CENTER":
            left_top.append(f"  X 센터 : {x_center or '-'}")
            left_top.append(f"  Y 센터 : {y_center or '-'}")
        else:
            left_top.append(f"  X 표시부 : {x_center or '-'}")
            left_top.append(f"  Y 표시부 : {y_center or '-'}")

        right_top = [
            "● 외곽 치수 (X/Y)",
            f"  X- : {x_minus or '-'}   /   X+ : {x_plus or '-'}",
            f"  Y- : {y_minus or '-'}   /   Y+ : {y_plus or '-'}",
        ]
        left_mid = [
            "● Z 정보",
            f"  Z 바닥 : {z_bottom or '-'}",
            f"  Z 상면 기준 : {z_top or '-'}",
        ]
        if z_height:
            left_mid.append(f"  {z_height}")

        right_mid = ["● 기타 좌표 / 치수"]
        if coord_items:
            right_mid.append("  - 추가 좌표")
            right_mid.extend([f"    · {s}" for s in coord_items])
        if outer_items:
            right_mid.append("  - 외곽 추가 치수")
            right_mid.extend([f"    · {s}" for s in outer_items])
        if z_items:
            right_mid.append("  - Z 추가 치수")
            right_mid.extend([f"    · {s}" for s in z_items])
        if len(right_mid) == 1:
            right_mid.append("  (등록된 추가 항목이 없습니다.)")

        # ─ 테이블 레이아웃 ─
        painter.save()

        # 바깥 테두리 (필요할 때만)
        if draw_outer:
            painter.setPen(Qt.black)
            painter.drawRect(rect)
            inner = rect.adjusted(4.0, 4.0, -4.0, -4.0)
        else:
            # 이미 바깥 프레임이 있는 경우, 그 안쪽 칸으로만 사용
            painter.setPen(Qt.black)
            inner = rect.adjusted(4.0, 4.0, -4.0, -4.0)

        mid_x = inner.left() + inner.width() / 2.0

        # 행 높이 비율: 상단 35%, 중단 35%, 하단 30%
        row1_h = inner.height() * 0.30
        row2_h = inner.height() * 0.30
        row3_h = inner.height() - row1_h - row2_h

        row1 = QRectF(inner.left(), inner.top(), inner.width(), row1_h)
        row2 = QRectF(inner.left(), row1.bottom(), inner.width(), row2_h)
        row3 = QRectF(inner.left(), row2.bottom(), inner.width(), row3_h)

        # 내부 구분선
        painter.drawLine(inner.left(), row1.bottom(), inner.right(), row1.bottom())
        painter.drawLine(inner.left(), row2.bottom(), inner.right(), row2.bottom())
        painter.drawLine(mid_x, inner.top(), mid_x, row2.bottom())

        # 폰트
        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)

        # ─ 각 셀에 텍스트 출력 ─
        def draw_lines(text_lines, r: QRectF):
            if not text_lines:
                return
            text = "\n".join(text_lines)
            painter.setPen(Qt.black)
            painter.drawText(
                r.adjusted(2.0, 2.0, -2.0, -2.0),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                text
            )

        # 1행 좌/우
        col1_r1 = QRectF(inner.left(), row1.top(), mid_x - inner.left(), row1.height())
        col2_r1 = QRectF(mid_x, row1.top(), inner.right() - mid_x, row1.height())
        draw_lines(left_top, col1_r1)
        draw_lines(right_top, col2_r1)

        # 2행 좌/우
        col1_r2 = QRectF(inner.left(), row2.top(), mid_x - inner.left(), row2.height())
        col2_r2 = QRectF(mid_x, row2.top(), inner.right() - mid_x, row2.height())
        draw_lines(left_mid, col1_r2)
        draw_lines(right_mid, col2_r2)

        # 3행: 특이사항
        if notes_text:
            title_font = QFont(font)
            title_font.setBold(True)
            painter.setFont(title_font)
            title_rect = QRectF(
                row3.left() + 2.0,
                row3.top() + 2.0,
                row3.width() - 4.0,
                16.0,
            )
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, "● 특이사항")

            painter.setFont(font)
            body_rect = QRectF(
                row3.left() + 2.0,
                title_rect.bottom() + 2.0,
                row3.width() - 4.0,
                row3.bottom() - title_rect.bottom() - 4.0,
            )
            painter.drawText(
                body_rect,
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                notes_text
            )

        painter.restore()



    def _draw_info_and_notes(self, painter: QPainter, rect: QRectF):
        """
        (이제는 사용하지 않아도 되지만, 호환을 위해 남겨 둔 함수)
        주어진 rect 안에 정보/특이사항을 위·아래 2단으로 배치합니다.
        """
        info_h = rect.height() * 0.55
        info_rect = QRectF(rect.left(), rect.top(), rect.width(), info_h)
        notes_rect = QRectF(
            rect.left(),
            info_rect.bottom() + 6.0,
            rect.width(),
            rect.bottom() - info_rect.bottom() - 6.0,
        )
        self._draw_info_block(painter, info_rect)
        self._draw_notes_block(painter, notes_rect)

    def _draw_info_tables_only(self, painter: QPainter, rect: QRectF):
        """세로 레이아웃 좌측 정보표 전용 (이제 공통 블록 호출)."""
        self._draw_info_block(painter, rect)

    def _draw_notes_only(self, painter: QPainter, rect: QRectF):
        """세로 레이아웃 하단 특이사항 전용 (이제 공통 블록 호출)."""
        self._draw_notes_block(painter, rect)

