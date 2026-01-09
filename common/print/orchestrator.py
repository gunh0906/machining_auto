# machining_auto/common/print/orchestrator.py
"""
Setting 1페이지 + CAM N페이지 동시 출력(통합 PDF) 오케스트레이터.

- UI 버튼에서는 이 파일의 export_* 함수만 호출하면 된다.
- QPrinter/QPainter를 1회만 생성하여 다페이지 PDF를 만든다.
- 문서 방향(세로/가로)은 한 번 정하면 문서 전체에 동일하게 적용한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QPainter, QImage, QDesktopServices, QPageSize, QPageLayout
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QFileDialog, QMessageBox


@dataclass(frozen=True)
class CombinedExportOptions:
    """
    통합 출력 옵션.

    layout_choice:
      - "세로" 또는 "가로"
      - 문서 전체 방향을 결정한다(Setting/CAM 모두 동일).

    include_setting:
      - True면 1페이지에 Setting 출력

    cam_pages:
      - CAM 페이지 payload 목록(1개 이상 가능)
      - 2페이지부터 순차 출력
    """
    layout_choice: str = "세로"
    include_setting: bool = True


def _snapshot_setting_scene_to_image(setting_main_window) -> Optional[QImage]:
    """
    SettingSheet의 annotation_scene(주석 포함)를 QImage로 스냅샷 생성한다.

    반환:
      - 성공 시 QImage
      - 실패 시 None

    주의:
      - 이 함수는 'Setting 메인윈도우'에 annotation_scene가 존재한다는 전제이다.
      - 통합 UI에서는 setting_main_window가 동일 객체일 수 있다.
    """
    scene = getattr(setting_main_window, "annotation_scene", None)
    if scene is None:
        return None

    # 씬에 pixmap이 없으면 스냅샷 불가
    pix_item = getattr(scene, "_pixmap_item", None)
    if pix_item is None or pix_item.pixmap().isNull():
        return None

    sr = scene.sceneRect()
    if sr.isNull() or sr.width() <= 0 or sr.height() <= 0:
        return None

    # 출력 품질 확보를 위해 2배 스케일로 렌더(필요 시 추후 옵션화)
    scale = 2.0
    w = max(1, int(sr.width() * scale))
    h = max(1, int(sr.height() * scale))

    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.white)

    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.scale(scale, scale)
        scene.render(p)
    finally:
        p.end()

    return img


def export_setting_cam_combined_pdf(
    *,
    parent_widget,
    setting_print_engine,
    cam_print_engine,
    cam_payloads: Sequence,
    options: CombinedExportOptions,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    통합 PDF 생성(Setting 1p + CAM Np).

    파라미터:
      parent_widget:
        - QFileDialog/QMessageBox 부모 위젯(통합 UI의 메인 윈도우 권장)

      setting_print_engine:
        - setting_sheet의 PrintEngine 인스턴스 (기존 print_engine.py의 PrintEngine)
        - 내부의 _render_page(painter, page_rect, layout_choice)를 사용한다.

      cam_print_engine:
        - machining_auto/cam_sheet/cam_print_engine.py 의 CamPrintEngine 인스턴스
        - 내부의 _render_cam_page_portrait/_render_cam_page_landscape를 사용한다.

      cam_payloads:
        - CAM 페이지용 payload 목록
        - 1개면 CAM 1장, 2개면 CAM 2장...

      options:
        - CombinedExportOptions(레이아웃, Setting 포함 여부)

      output_path:
        - 지정되면 저장 대화상자 생략

    반환:
      - 생성된 PDF 경로(취소/실패 시 None)
    """
    if not cam_payloads:
        QMessageBox.warning(parent_widget, "통합 출력", "CAM 출력 데이터가 없습니다.")
        return None

    # 1) 저장 경로
    if not output_path:
        path, _ = QFileDialog.getSaveFileName(
            parent_widget,
            "Setting + CAM 통합 PDF로 저장",
            "Setting_CAM_Combined.pdf",
            "PDF 파일 (*.pdf)"
        )
        if not path:
            return None
    else:
        path = output_path

    # 2) 프린터 설정(문서 전체 방향 고정)
    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setFullPage(True)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)

    if options.layout_choice == "가로":
        printer.setPageOrientation(QPageLayout.Landscape)
    else:
        printer.setPageOrientation(QPageLayout.Portrait)

    painter = QPainter(printer)
    if not painter.isActive():
        QMessageBox.critical(parent_widget, "통합 출력 오류", "PDF 파일 생성 중 오류가 발생하였습니다.")
        return None

    try:
        # paintRectPixels는 페이지 방향이 확정된 후 얻는다.
        page_rect = QRectF(printer.pageLayout().paintRectPixels(printer.resolution()))

        # 3) Setting 스냅샷(가로 CAM 페이지에서 좌측에 보여줄 용도)
        #    - 통합 UI에서 setting_main_window는 setting_print_engine.main 으로 접근 가능하다는 전제
        setting_main = getattr(setting_print_engine, "main", None)
        setting_snapshot = _snapshot_setting_scene_to_image(setting_main) if setting_main is not None else None

        # 4) 1페이지: Setting(옵션)
        if options.include_setting:
            # 주의: 기존 코드를 바꾸지 않고 내부 렌더 함수를 호출한다.
            setting_print_engine._render_page(painter, page_rect, options.layout_choice)

            # CAM 페이지가 뒤에 오면 페이지 넘김
            printer.newPage()

        # 5) 2페이지~: CAM N페이지
        for idx, payload in enumerate(cam_payloads):
            if options.layout_choice == "가로":
                cam_print_engine._render_cam_page_landscape(
                    painter,
                    page_rect,
                    payload=payload,
                    setting_snapshot=setting_snapshot,
                )
            else:
                cam_print_engine._render_cam_page_portrait(
                    painter,
                    page_rect,
                    payload=payload,
                )

            # 마지막 페이지가 아니면 newPage()
            if idx != len(cam_payloads) - 1:
                printer.newPage()

    finally:
        painter.end()

    # 6) PDF 열기(실패 시 무시)
    try:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    except Exception:
        pass

    QMessageBox.information(parent_widget, "통합 출력 완료", f"통합 PDF 생성 완료.\n{path}")
    return path
