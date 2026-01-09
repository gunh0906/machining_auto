# machining_auto/app_shell.py
"""
통합 UI 쉘:
- 좌측 세로 아이콘(Setting / CAM)으로 페이지 전환
- 상단 메뉴바는 고정(공유)
- 설비/작업자 설정은 setting_sheet_auto의 global_settings.json을 공유
"""

from __future__ import annotations
import os
from machining_auto.common.qss_loader import load_qss_files
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QEvent, QPointF
from PySide6.QtGui import QIcon, QPainter, QPolygonF, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QToolButton, QButtonGroup, QStackedWidget, QMenuBar, QMenu, QMessageBox, QFrame, QProxyStyle, QStyle
)

# ✅ Setting쪽 설정(JSON) 공유
from machining_auto.setting_sheet_auto.settings_manager import (
    load_global_settings,
)

# ✅ Setting UI / CAM UI 불러오기
from machining_auto.setting_sheet_auto.main import MainWindow as SettingMainWindow
from machining_auto.cam_sheet_auto.ui import CamSheetApp


class ShellMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ✅ 타이틀바 제거(프레임리스)
        self.setWindowFlag(Qt.FramelessWindowHint, True)

        # ✅ 드래그 이동용 변수
        self._drag_pos = None

        self.setWindowTitle("Machining Auto (Setting + CAM)")
        self.resize(1600, 900)
        self.setMinimumHeight(900)

        # ----- 공유 설정 로드 -----
        machines, op_map = load_global_settings()
        self.machine_list = machines or []
        self.operator_map = op_map or {}

        # ----- 상단 메뉴(공유) -----
        self.menubar = self._build_menu_bar()
        self.setMenuBar(None)


        # ✅ QMainWindow 기본 메뉴바 영역을 명시적으로 제거
        self.setMenuBar(None)

        # ----- 중앙 UI: 좌측 사이드바(전체 높이) + 우측(상단바 + 페이지) -----
        central = QWidget(self)

        hroot = QHBoxLayout(central)
        hroot.setContentsMargins(0, 0, 0, 0)
        hroot.setSpacing(0)

        # 1) 좌측 사이드바 (전체 높이 사용)
        self.sidebar = self._build_sidebar()
        hroot.addWidget(self.sidebar)

        # 2) 우측 영역: 상단바 + 페이지 스택
        right = QWidget(self)
        vright = QVBoxLayout(right)
        vright.setContentsMargins(0, 0, 0, 0)
        vright.setSpacing(0)

        self.topbar = self._build_topbar()
        vright.addWidget(self.topbar)

        self.stack = QStackedWidget()
        vright.addWidget(self.stack, 1)



        hroot.addWidget(right, 1)

        self.setCentralWidget(central)



        # ----- 페이지 구성 -----
        self.page_setting = SettingMainWindow()

        # 통합 쉘이 메뉴를 가지므로, Setting 내부 메뉴/상태바는 숨김(기능은 유지)
        try:
            mb = self.page_setting.menuBar()
            if mb is not None:
                mb.hide()
        except Exception:
            pass
        try:
            sb = self.page_setting.statusBar()
            if sb is not None:
                sb.hide()
        except Exception:
            pass
        # ✅ 초기 설비/ROTATE 상태를 SettingMainWindow에 주입 (PDF 헤더/작업자 매핑용)
        try:
            init_machine = (self.cb_machine.currentText() or "").strip()
        except Exception:
            init_machine = ""

        try:
            if hasattr(self.page_setting, "set_shell_machine"):
                self.page_setting.set_shell_machine(init_machine)
        except Exception:
            pass

        try:
            if hasattr(self.page_setting, "set_shell_rotate"):
                self.page_setting.set_shell_rotate(bool(getattr(self.btn_rotate, "isChecked", lambda: False)()))
        except Exception:
            pass

        self.page_cam = CamSheetApp()

        # ✅ CAM PDF 헤더는 SettingSheet PrintEngine의 헤더를 그대로 사용
        # (로테이트/설비/모드/작업자/날짜가 Setting과 완전히 동일해짐)
        if hasattr(self.page_cam, "_cam_printer") and hasattr(self.page_setting, "print_engine"):
            self.page_cam._cam_printer.set_header_drawer(self.page_setting.print_engine._draw_header)

        # ✅ CAM 헤더 데이터 공급자 주입(Setting 설정 공유)
        self.page_cam.set_header_provider(self._get_setting_header_info)
        self.page_cam.use_setting_header = True  # 기본 ON
        # ✅ TopBar 프로젝트명 표시: 페이지 생성 이후에 신호를 바인딩
        self.stack.addWidget(self.page_setting)  # index 0
        self.stack.addWidget(self.page_cam)      # index 1

        # 초기 페이지: Setting
        self._select_page(0)
        # ✅ show 직후 레이아웃 재계산으로 창이 줄어드는 현상 방지(초기 크기 복원)
        QTimer.singleShot(0, self._enforce_initial_geometry)
        # ✅ DPI/스크린 이동 진단(모니터 이동 시 들쑥날쑥 원인 확정용)
        QTimer.singleShot(0, self._install_dpi_diagnostics)

    def _enforce_initial_geometry(self):
        """
        프레임리스 + 레이아웃 재계산(DPI/폰트 반영) 후 창이 축소되는 현상을 방지합니다.
        - 시작 크기는 반드시 1600×820 이상을 유지
        - 사용자가 이후 수동으로 키우는 것은 그대로 허용
        """
        if self.width() < 1600 or self.height() < 820:
            self.resize(max(self.width(), 1600), max(self.height(), 820))

    # ============================================================
    # DPI/스크린 이동 진단용(콘솔 출력)
    # ============================================================
    def _dpi_dump(self, reason: str):
        """
        현재 창이 붙은 화면(Screen)과 DPI/스케일, 창 크기 변화를 출력합니다.
        - 모니터 이동 시 '들쑥날쑥' 원인(Per-Monitor DPI)을 확정하기 위한 진단용입니다.
        """
        try:
            wh = self.windowHandle()
            scr = wh.screen() if wh is not None else self.screen()
        except Exception:
            scr = None

        geo = self.geometry()
        pos = self.pos()

        if scr is not None:
            try:
                name = scr.name()
            except Exception:
                name = "unknown"

            try:
                ldpi = float(scr.logicalDotsPerInch())
            except Exception:
                ldpi = -1.0

            try:
                pdpi = float(scr.physicalDotsPerInch())
            except Exception:
                pdpi = -1.0

            try:
                dpr = float(scr.devicePixelRatio())
            except Exception:
                dpr = -1.0

            try:
                sgeo = scr.geometry()
                ageo = scr.availableGeometry()
                sgeo_txt = f"{sgeo.width()}x{sgeo.height()}@({sgeo.x()},{sgeo.y()})"
                ageo_txt = f"{ageo.width()}x{ageo.height()}@({ageo.x()},{ageo.y()})"
            except Exception:
                sgeo_txt = "n/a"
                ageo_txt = "n/a"

            print(
                f"[DPI] {reason} | "
                f"win={geo.width()}x{geo.height()} pos=({pos.x()},{pos.y()}) | "
                f"screen={name} ldpi={ldpi:.1f} pdpi={pdpi:.1f} dpr={dpr:.2f} | "
                f"screenGeo={sgeo_txt} availGeo={ageo_txt}"
            )
        else:
            print(
                f"[DPI] {reason} | "
                f"win={geo.width()}x{geo.height()} pos=({pos.x()},{pos.y()}) | screen=None"
            )

    def _install_dpi_diagnostics(self):
        """
        show 이후 windowHandle/screenChanged가 유효해지는 시점에 신호 연결 및 초기 덤프를 수행합니다.
        """
        # 초기 상태 1회 덤프
        self._dpi_dump("install")

        # 창 핸들에서 screenChanged 신호를 잡습니다(모니터 이동 감지).
        try:
            wh = self.windowHandle()
            if wh is not None:
                wh.screenChanged.connect(
                    lambda s: self._dpi_dump(f"screenChanged->{getattr(s, 'name', lambda: 'unknown')()}")
                )
        except Exception as e:
            print(f"[DPI] screenChanged hook failed: {e}")

        # 이벤트 기반 감지(Resize/Move/DPI 변화)
        try:
            self.installEventFilter(self)
        except Exception as e:
            print(f"[DPI] installEventFilter failed: {e}")

    def eventFilter(self, obj, event):
        """
        DPI/스크린 이동 관련 이벤트를 가로채 콘솔로 출력합니다.
        """
        try:
            et = event.type()

            if et == QEvent.Type.ScreenChangeInternal:
                self._dpi_dump("event:ScreenChangeInternal")
            elif et == QEvent.Type.DpiChange:
                self._dpi_dump("event:DpiChange")
            elif et == QEvent.Type.Resize:
                # 리사이즈는 너무 많이 뜰 수 있으니 핵심만
                self._dpi_dump("event:Resize")
            elif et == QEvent.Type.Move:
                self._dpi_dump("event:Move")
        except Exception:
            pass

        return super().eventFilter(obj, event)


    # -------------------------
    # 상단 메뉴바(공유)
    # -------------------------
    def _build_menu_bar(self) -> QMenuBar:
        """
        상단 메뉴바(공유)
        - 기존 setMenuBar()를 쓰지 않고,
          topbar 내부에 삽입하기 위한 QMenuBar를 반환합니다.
        """
        menubar = QMenuBar(self)
        menubar.setNativeMenuBar(False)

        menu_file = QMenu("파일", self)
        menubar.addMenu(menu_file)

        act_quit = menu_file.addAction("종료")
        act_quit.triggered.connect(self.close)

        menu_settings = QMenu("설정", self)
        menubar.addMenu(menu_settings)

        # ✅ CAM 출력 헤더 데이터 소스 옵션(기본: Setting 설정 사용)
        self.act_cam_header_from_setting = menu_settings.addAction("CAM 출력 헤더: Setting 설정 사용")
        self.act_cam_header_from_setting.setCheckable(True)
        self.act_cam_header_from_setting.setChecked(True)
        self.act_cam_header_from_setting.toggled.connect(self._on_toggle_cam_header_source)

        # ✅ SettingSheet의 설비/작업자 설정 창을 그대로 호출(Setting 기능 공유)
        act_machine = menu_settings.addAction("설비 / 작업자 설정...")
        act_machine.triggered.connect(self._open_setting_machine_dialog)

        menu_help = QMenu("도움말", self)
        menubar.addMenu(menu_help)

        act_about = menu_help.addAction("정보")
        act_about.triggered.connect(
            lambda: QMessageBox.information(self, "정보", "Machining Auto 통합 UI (Setting + CAM)")
        )

        return menubar


    def _open_setting_machine_dialog(self):
        """
        SettingSheet 쪽에 이미 구현된 설정창을 그대로 사용.
        - SettingMainWindow.open_settings_dialog()가 내부에서 load/save_global_settings를 처리함
        """
        if hasattr(self.page_setting, "open_settings_dialog"):
            self.page_setting.open_settings_dialog()
            # 설정 저장 후 쉘 캐시를 갱신(다른 페이지에서 공유용)
            machines, op_map = load_global_settings()
            self.machine_list = machines or []
            self.operator_map = op_map or {}
        else:
            QMessageBox.warning(self, "설정", "SettingSheet 설정 기능을 찾지 못했습니다.")

    def _on_toggle_cam_header_source(self, checked: bool):
        """
        CAM PDF 헤더 데이터 소스를 Setting 설정(JSON)으로 쓸지 여부 토글
        """
        if hasattr(self, "page_cam") and self.page_cam is not None:
            self.page_cam.use_setting_header = bool(checked)

    def _get_setting_header_info(self) -> dict:
        """
        SettingSheet의 현재 상태 + 전역 설정을 기반으로
        CAM 헤더용 (설비/작업자/날짜) 정보를 반환합니다.
        """
        from datetime import datetime
        machine = ""
        try:
            machine = (self.page_setting.combo_machine.currentText() or "").strip()
        except Exception:
            machine = ""

        # Setting 쪽 operator_map(=global_settings.json 기반)에서 작업자 추출
        op = ""
        try:
            # Setting이 갖고 있는 operator_map을 그대로 사용(가장 안전)
            op = (self.page_setting.operator_map.get(machine, "") or "").strip()
        except Exception:
            op = ""

        date = datetime.now().strftime("%m-%d")
        return {
            "machine": machine,
            "operator": op,
            "date": date,
        }

    def _build_topbar(self) -> QWidget:
        """
        상단 공유 바(2단):
        - 1행: 메뉴(파일/설정/도움말) + (우측) 닫기(X)
        - 2행: 설비명 + (우측) ROTATE

        구분선 규칙:
        - 1행 아래 / 2행 아래(TopBar 바닥) 모두 "끝까지" 표시
        - 각 행 높이는 2행(설비/ROTATE)의 컨트롤 높이에 맞춰 통일

        ✅ 핵심:
        - Divider가 끝까지 가도록 TopBar의 바깥 레이아웃 좌우 마진은 0
        - 콘텐츠 들여쓰기는 각 row 레이아웃(h1/h2)에서 좌우 패딩으로 처리
        """
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton
        )

        w = QWidget(self)
        w.setObjectName("TopBar")

        v = QVBoxLayout(w)
        # ✅ Divider를 full-width로 만들기 위해 좌우 마진을 0으로 둠
        # 프로젝트명 위 구분선 간격 
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(0)

        side_pad = 12
        row_vpad = 4  # ✅ 구분선 ↔ 콘텐츠(버튼/메뉴/콤보) 상하 거리 통일값

        # =========================
        # 1행: 메뉴 + 닫기(X)
        # =========================
        row1 = QWidget(w)
        row1.setObjectName("TopBarRow1")
        h1 = QHBoxLayout(row1)
        # ✅ 콘텐츠 패딩은 row 내부에서만 적용
        h1.setContentsMargins(side_pad, 0, side_pad, 0)
        h1.setSpacing(10)

        h1.addWidget(self.menubar, 1)
        h1.addStretch(1)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setToolTip("닫기")
        btn_close.clicked.connect(self.close)
        btn_close.setObjectName("ClosePill")
        h1.addWidget(btn_close)

        v.addWidget(row1)

        # ✅ 1행 아래 구분선(끝까지)
        div1 = QWidget(w)
        div1.setObjectName("TopBarMenuDivider")
        div1.setFixedHeight(1)
        v.addWidget(div1)

        # =========================
        # 2행: 설비명 + ROTATE
        # =========================
        row2 = QWidget(w)
        row2.setObjectName("TopBarRow2")
        h2 = QHBoxLayout(row2)
        # ✅ 콘텐츠 패딩은 row 내부에서만 적용
        h2.setContentsMargins(side_pad, row_vpad, side_pad, row_vpad)
        h2.setSpacing(10)

        lbl_machine = QLabel("설비명:")
        lbl_machine.setStyleSheet("color: #222; font-weight: bold;")

        self.cb_machine = QComboBox()
        self.cb_machine.setMinimumWidth(240)

        for m in (self.machine_list or []):
            self.cb_machine.addItem(str(m))

        self.cb_machine.currentTextChanged.connect(self._on_machine_changed)

        self.btn_rotate = QPushButton("ROTATE OFF")
        self.btn_rotate.setCheckable(True)
        self.btn_rotate.setChecked(False)
        self.btn_rotate.setObjectName("RotatePill")
        self.btn_rotate.setProperty("rotateOn", "false")

        self._apply_rotate_button_style(False)
        self.btn_rotate.toggled.connect(self._on_rotate_toggled)

        h2.addWidget(lbl_machine)
        h2.addWidget(self.cb_machine)
        h2.addStretch(1)
        h2.addWidget(self.btn_rotate)

        v.addWidget(row2)

        # ✅ 2행 아래(TopBar 바닥) 구분선(끝까지)
        div2 = QWidget(w)
        div2.setObjectName("TopBarBottomDivider")
        div2.setFixedHeight(1)
        v.addWidget(div2)

        # ✅ 행 높이/TopBar 높이 동기화(2행 컨트롤 기준, 하드코딩 최소화)
        def _sync():
            try:
                h_btn = int(self.btn_rotate.sizeHint().height())
                h_cb = int(self.cb_machine.sizeHint().height())
                h_mb = int(self.menubar.sizeHint().height())
                base_h = max(h_btn, h_cb, h_mb, 28)

                row1.setFixedHeight(base_h)
                row2.setFixedHeight(base_h)

                top_h = (
                    v.contentsMargins().top()
                    + v.contentsMargins().bottom()
                    + (base_h * 2)
                    + (1 * 2)
                )
                w.setFixedHeight(int(top_h))
            except Exception:
                pass

        QTimer.singleShot(0, _sync)

        return w


    def _apply_rotate_button_style(self, on: bool):
        """
        로테이트 버튼 표시
        - 색상은 전역 테마(QSS)에서 처리
        - 여기서는 텍스트와 property만 갱신
        """
        if on:
            self.btn_rotate.setText("ROTATE ON")
            self.btn_rotate.setProperty("rotateOn", "true")
        else:
            self.btn_rotate.setText("ROTATE OFF")
            self.btn_rotate.setProperty("rotateOn", "false")

        # property 변경 후 스타일 재적용
        self.btn_rotate.style().unpolish(self.btn_rotate)
        self.btn_rotate.style().polish(self.btn_rotate)

    # -------------------------
    # 좌측 사이드바
    # -------------------------

    def _build_sidebar(self) -> QWidget:
        """
        좌측 사이드바(전체 높이)
        - 로고: 잘림 없는 비율 유지(KeepAspectRatio) + PNG 투명 여백 자동 제거
        - Setting / CAM 아이콘: 크기/정렬 고정
        - 배경색은 QSS(#SideBar)에서 처리
        """

        from PySide6.QtWidgets import (
            QWidget, QLabel, QVBoxLayout, QToolButton, QButtonGroup
        )
        from PySide6.QtGui import QPixmap, QImage, QIcon
        from PySide6.QtCore import Qt, QSize
        from pathlib import Path

        def _trim_transparent_margins(pix: QPixmap) -> QPixmap:
            """
            PNG 로고에 포함된 투명 여백을 자동으로 제거합니다.
            - 알파(투명) 픽셀을 기준으로 유효 영역 bounding box를 계산
            - 유효 영역이 없으면 원본 유지
            """
            if pix.isNull():
                return pix

            img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
            w_ = img.width()
            h_ = img.height()

            left = w_
            right = -1
            top = h_
            bottom = -1

            for y in range(h_):
                for x in range(w_):
                    if img.pixelColor(x, y).alpha() > 0:
                        if x < left:
                            left = x
                        if x > right:
                            right = x
                        if y < top:
                            top = y
                        if y > bottom:
                            bottom = y

            if right < left or bottom < top:
                return pix

            return pix.copy(left, top, (right - left + 1), (bottom - top + 1))

        w = QWidget(self)
        w.setObjectName("SideBar")
        w.setFixedWidth(140)
        w.setAttribute(Qt.WA_StyledBackground, True)

        vroot = QVBoxLayout(w)
        vroot.setContentsMargins(0, 0, 0, 0)
        vroot.setSpacing(0)
        vroot.setAlignment(Qt.AlignTop)

        base = Path(__file__).resolve().parent
        icon_dir = base / "assets" / "sidebar"

        logo_png = icon_dir / "Atech_AI.png"
        setting_png = icon_dir / "shtting_sheet_icon.png"
        cam_png = icon_dir / "cam_sheet_icon.png"

        # =========================
        # 1) 로고 영역 (여백 0)
        # =========================
        logo_box = QWidget(w)
        logo_box.setObjectName("SideLogoBox")
        logo_box.setAttribute(Qt.WA_StyledBackground, True)

        logo_lay = QVBoxLayout(logo_box)
        logo_lay.setContentsMargins(0, 0, 0, 0)
        logo_lay.setSpacing(0)

        lbl_logo = QLabel(logo_box)
        lbl_logo.setObjectName("SideLogo")
        lbl_logo.setAlignment(Qt.AlignCenter)
        lbl_logo.setFixedHeight(70)

        if logo_png.exists():
            pm = QPixmap(str(logo_png))
            if not pm.isNull():
                pm = _trim_transparent_margins(pm)

                target_w = w.width()          # ✅ 폭 여유 제거(꽉 차게)
                target_h = lbl_logo.height()  # 높이 70

                pm2 = pm.scaled(
                    target_w,
                    target_h,
                    Qt.KeepAspectRatio,        # ✅ contain (잘림 없음)
                    Qt.SmoothTransformation,
                )
                lbl_logo.setPixmap(pm2)
            else:
                lbl_logo.setText("LOGO")
        else:
            lbl_logo.setText("LOGO")

        logo_lay.addWidget(lbl_logo)
        vroot.addWidget(logo_box)

        # =========================
        # 2) 버튼 영역
        # =========================
        btn_area = QWidget(w)
        btn_area.setObjectName("SideButtons")
        btn_area.setAttribute(Qt.WA_StyledBackground, True)

        v = QVBoxLayout(btn_area)
        v.setContentsMargins(10, 14, 10, 14)
        v.setSpacing(18)
        v.setAlignment(Qt.AlignTop)

        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)

        # Setting 버튼
        self.btn_setting = QToolButton(btn_area)
        self.btn_setting.setObjectName("SideIcon")
        self.btn_setting.setProperty("toolButton", True)
        self.btn_setting.setCheckable(True)
        self.btn_setting.setAutoRaise(True)
        self.btn_setting.setToolTip("Setting Sheet")
        self.btn_setting.setFixedSize(96, 96)

        if setting_png.exists():
            self.btn_setting.setIcon(QIcon(str(setting_png)))
            self.btn_setting.setIconSize(QSize(88, 88))
        else:
            self.btn_setting.setText("S")

        btn_group.addButton(self.btn_setting, 0)
        v.addWidget(self.btn_setting, alignment=Qt.AlignHCenter)

        # CAM 버튼
        self.btn_cam = QToolButton(btn_area)
        self.btn_cam.setObjectName("SideIcon")
        self.btn_cam.setProperty("toolButton", True)
        self.btn_cam.setCheckable(True)
        self.btn_cam.setAutoRaise(True)
        self.btn_cam.setToolTip("CAM Sheet")
        self.btn_cam.setFixedSize(96, 96)

        if cam_png.exists():
            self.btn_cam.setIcon(QIcon(str(cam_png)))
            self.btn_cam.setIconSize(QSize(88, 88))
        else:
            self.btn_cam.setText("C")

        btn_group.addButton(self.btn_cam, 1)
        v.addWidget(self.btn_cam, alignment=Qt.AlignHCenter)

        v.addStretch(1)

        # 페이지 전환
        self.btn_setting.clicked.connect(lambda: self._select_page(0))
        self.btn_cam.clicked.connect(lambda: self._select_page(1))

        # 기본 선택
        self.btn_setting.setChecked(True)

        vroot.addWidget(btn_area, 1)

        # ✅ 반드시 QWidget 반환
        return w


    def _select_page(self, idx: int):
        self.stack.setCurrentIndex(idx)
        if idx == 0:
            self.btn_setting.setChecked(True)
        else:
            self.btn_cam.setChecked(True)
        # ✅ 프로젝트명 표시 업데이트(현재 페이지 기준)
        self._update_topbar_project_label()

    def _bind_topbar_project_source(self):
        """
        TopBar의 프로젝트명 표시용 라벨을 페이지 입력칸과 연결한다.
        - Setting/CAM 페이지 생성 이후에만 호출한다.
        - 신호 중복 연결을 방지한다.
        """
        if getattr(self, "_project_label_bound", False):
            self._update_topbar_project_label()
            return

        self._project_label_bound = True

        # Setting 페이지 프로젝트명
        try:
            if hasattr(self.page_setting, "edit_project") and hasattr(self.page_setting.edit_project, "textChanged"):
                self.page_setting.edit_project.textChanged.connect(self._update_topbar_project_label)
        except Exception:
            pass

        # CAM 페이지(프로젝트명 입력칸이 존재하는 경우만)
        try:
            if hasattr(self.page_cam, "project_input") and hasattr(self.page_cam.project_input, "textChanged"):
                self.page_cam.project_input.textChanged.connect(self._update_topbar_project_label)
        except Exception:
            pass

        # 초기 표시 갱신
        self._update_topbar_project_label()

    def _update_topbar_project_label(self):
        """
        현재 활성 페이지 기준으로 TopBar의 프로젝트명 라벨을 갱신한다.
        - 입력칸이 없거나 비어 있으면 "—"로 표시한다.
        """
        try:
            if not hasattr(self, "lbl_project_value"):
                return

            page = None
            try:
                page = self.stack.currentWidget()
            except Exception:
                page = None

            candidates = []
            if page is not None:
                candidates.extend([
                    getattr(page, "edit_project", None),
                    getattr(page, "project_input", None),
                ])

            # fallback: Setting 페이지
            candidates.append(getattr(self, "page_setting", None) and getattr(self.page_setting, "edit_project", None))

            text_val = ""
            for w in candidates:
                if w is None:
                    continue
                if hasattr(w, "text") and callable(w.text):
                    text_val = (w.text() or "").strip()
                    if text_val:
                        break

            self.lbl_project_value.setText(text_val if text_val else "—")
        except Exception:
            pass


    def _on_machine_changed(self, machine_name: str):
        """
        공유 설비명 변경:
        - Setting 페이지에도 반영(가능하면 combo_machine 설정)
        - CAM 페이지에도 반영(상단 입력칸 또는 헤더 provider에서 사용)
        """
        # Setting 반영
        try:
            if hasattr(self.page_setting, "combo_machine"):
                idx = self.page_setting.combo_machine.findText(machine_name)
                if idx >= 0:
                    self.page_setting.combo_machine.setCurrentIndex(idx)
        except Exception:
            pass

        # CAM 반영(기존 입력칸 유지하되 자동 채움)
        try:
            if hasattr(self.page_cam, "machine_input"):
                self.page_cam.machine_input.setText(machine_name)
        except Exception:
            pass
        # ✅ SettingMainWindow에 설비명 주입( PDF 헤더/작업자 매핑용 )
        try:
            if hasattr(self.page_setting, "set_shell_machine"):
                self.page_setting.set_shell_machine(machine_name)
        except Exception:
            pass

    def _on_rotate_toggled(self, checked: bool):
        """
        공유 로테이트 ON/OFF 변경:
        - Setting 페이지의 로테이트 상태에 반영(해당 API가 있으면 호출)
        - CAM 쪽은 출력 헤더/표시에서 사용(추후)
        """
        self._apply_rotate_button_style(bool(checked))
        # ✅ SettingMainWindow에 ROTATE 상태 주입(PDF 헤더 ROTATE ON/OFF용)
        try:
            if hasattr(self.page_setting, "set_shell_rotate"):
                self.page_setting.set_shell_rotate(bool(checked))
        except Exception:
            pass

        # Setting 반영: SettingMainWindow에 rotate 토글 함수/버튼이 있으면 동기화
        try:
            if hasattr(self.page_setting, "btn_rotate"):
                # 버튼이 checkable이면 동일 상태로 맞춘다(무한루프 방지 위해 blockSignals)
                self.page_setting.btn_rotate.blockSignals(True)
                self.page_setting.btn_rotate.setChecked(bool(checked))
                self.page_setting.btn_rotate.blockSignals(False)
        except Exception:
            pass

        # CAM 반영: 지금은 상태만 저장(출력 안정화 2단계에서 헤더에 넣을지 결정)
        try:
            self.page_cam.rotate_on = bool(checked)
        except Exception:
            pass
    def mousePressEvent(self, event):
        """
        프레임리스 창에서 상단 영역 드래그 이동을 가능하게 합니다.
        """
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        프레임리스 창 드래그 이동
        """
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        드래그 종료
        """
        self._drag_pos = None
        super().mouseReleaseEvent(event)

# ===============================
# QSS Loader / Theme (전역 단일 적용)
# ===============================
def load_qss(app, qss_path: str):
    """
    (Deprecated)
    과거 단일 QSS 파일을 직접 app.setStyleSheet로 적용하던 경로.
    - 전역 QSS는 load_qss_bundle()로만 단일 적용한다.
    - 이 함수는 덮어쓰기 방지를 위해 no-op로 둔다.
    """
    return


def _read_text_safe(path: str) -> str:
    """
    QSS 파일을 안전하게 읽어옵니다.
    - 파일이 없거나 읽기 실패 시 빈 문자열 반환
    """
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def load_qss_bundle(app: QApplication) -> None:
    """
    전역 QSS 적용 경로(단일화).
    - styles 폴더의 QSS를 순서대로 합쳐 app.setStyleSheet 1회만 호출합니다.
    """
    base_dir = Path(__file__).resolve().parent
    styles_dir = base_dir / "styles"

    parts = [
        styles_dir / "00_base.qss",
        styles_dir / "10_toolbar.qss",
        styles_dir / "20_inputs_safe.qss",
        styles_dir / "90_experimental.qss",
    ]

    merged = []
    for p in parts:
        merged.append(_read_text_safe(str(p)))

    app.setStyleSheet("\n\n".join([s for s in merged if s.strip()]))


def apply_brand_light_theme(app: QApplication) -> None:
    """
    [전역 테마 단일 적용 지점]
    - 전역 QSS는 파일로 분리(styles/*.qss)
    - QComboBox ▼(down-arrow)는 QSS가 아닌 ProxyStyle로 직접 그려 QSS 충돌을 회피합니다.
    - app.setStyleSheet 호출은 load_qss_bundle() 단 1회만 수행합니다.
    """
    app.setStyle("Fusion")

    # ✅ QComboBox ▼(down-arrow)를 QSS가 아니라 Style 엔진으로 "직접 그리기"
    class _ComboArrowProxyStyle(QProxyStyle):
        def drawPrimitive(self, element, option, painter, widget=None):
            if element == QStyle.PE_IndicatorArrowDown:
                painter.save()
                try:
                    painter.setRenderHint(QPainter.Antialiasing, True)

                    r = option.rect.adjusted(0, 0, 0, 0)
                    cx = r.center().x()
                    cy = r.center().y()

                    # ▼ 삼각형 크기(픽셀) - DPI에서도 무난
                    w = max(8.0, r.width() * 0.35)
                    h = max(5.0, r.height() * 0.22)

                    p1 = QPointF(cx - w / 2.0, cy - h / 2.0)
                    p2 = QPointF(cx + w / 2.0, cy - h / 2.0)
                    p3 = QPointF(cx,           cy + h / 2.0)

                    poly = QPolygonF([p1, p2, p3])

                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor("#111827"))
                    painter.drawPolygon(poly)
                finally:
                    painter.restore()
                return

            return super().drawPrimitive(element, option, painter, widget)

    app.setStyle(_ComboArrowProxyStyle(app.style()))

    # ✅ 전역 QSS는 bundle(00/10/20/90)로 1회만 적용
    load_qss_bundle(app)

def main():
    app = QApplication(sys.argv)
    apply_brand_light_theme(app)

    win = ShellMainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
