# ui.py
import os
import re
import sys
from datetime import datetime
from .cam_core import update_tool_call_in_folder
import chardet  # 기존 코드 호환을 위해 유지(직접 사용하지 않아도 무방)
from .encoding_utils import safe_decode
from .excel_utils import export_to_excel_with_auto_filename
from .functions import extract_tool_data, extract_job_number
from .cam_core import scan_cam_rows
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QSizePolicy,
    QGroupBox,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QMenu,
    QAbstractItemView,
)
# ===== [PDF 출력/동시출력] 공용/출력 엔진 =====
from machining_auto.common.print.common_blocks import HeaderPayload
from .cam_print_engine import CamPrintEngine, CamPrintPayload
from machining_auto.common.print.orchestrator import (
    export_setting_cam_combined_pdf,
    CombinedExportOptions,
)


def natural_sort_key(text: str):
    """
    파일명을 자연스럽게 정렬하기 위한 키를 생성합니다.
    예: T1, T2, ..., T10 순서 유지
    """
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", text)]


class FileLoaderThread(QThread):
    """
    백그라운드에서 폴더 내 .h 파일을 로드하는 스레드.
    """
    files_loaded = Signal(list, list)  # (files_data, cam_rows)


    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        """
        폴더에서 .h 파일을 스캔하여 CamRow 리스트로 가져온 뒤,
        UI 테이블 입력용 튜플 리스트로 변환하여 시그널로 전달합니다.
        """
        try:
            rows = scan_cam_rows(self.folder_path)

            if not rows:
                print("⚠ 선택한 폴더에 .H 파일이 없습니다!")
                self.files_loaded.emit([], [])
                return

            files_data = []
            for r in rows:
                files_data.append(
                    (
                        r.file_name,
                        r.tool_db,
                        r.tool_no,
                        r.allowance_xy,
                        r.pg_name,
                        r.equip_name,
                        r.job_number,
                        r.date,
                        r.coolant,
                    )
                )
            self.files_loaded.emit(files_data, rows)


        except Exception as e:
            print(f"❌ 폴더 로딩 오류: {e}")
            self.files_loaded.emit([], [])



class CamSheetApp(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_folder = ""
        self.loader_thread = None
        self.initUI()

        # ===== [PDF 출력 엔진] =====
        base_path = os.path.dirname(os.path.abspath(__file__))
        # CAM 쪽 로고를 우선 사용(공용 로고로 교체는 통합 단계에서 진행)
        logo_path = os.path.join(base_path, "main-logo.png")
        self._cam_printer = CamPrintEngine(parent=self, logo_path=logo_path)

        # ===== [CAM 원본 데이터 캐시] =====
        # FileLoaderThread에서 스캔한 CamRow 원본을 보관하여 PDF 출력에 사용합니다.
        self._cam_rows_cache = []
        self._header_provider = None
        self.use_setting_header = False

    def handle_tool_number_change(self, item):
        """
        툴번호(3열) 변경 시 .h 파일 내 TOOL CALL의 숫자만 교체합니다.
        - 실제 파일 수정 로직은 cam_core로 이관되어, 여기서는 호출만 수행합니다.
        """
        if item.column() != 2:
            return

        row = item.row()
        new_tool_number = item.text().strip()

        file_item = self.table.item(row, 0)
        if not file_item:
            return

        if not new_tool_number.isdigit():
            return

        if not self.selected_folder:
            return

        file_name = file_item.text().strip()

        ok, msg = update_tool_call_in_folder(self.selected_folder, file_name, new_tool_number)
        if ok:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")

    def set_header_provider(self, fn):
        """
        통합 쉘에서 Setting 정보를 가져오기 위한 콜백을 주입합니다.
        fn() -> {"machine": str, "operator": str, "date": str}
        """
        self._header_provider = fn

    def keyPressEvent(self, event):
        """
        F5 키를 누르면 폴더 내 파일 목록을 새로고침합니다.
        """
        if event.key() == Qt.Key.Key_F5:
            print("🔄 새로고침: 폴더 내 파일 목록 다시 로드")
            if self.selected_folder:
                self._start_loading_folder(self.selected_folder)
            return
        super().keyPressEvent(event)

    def initUI(self):
        """
        UI를 구성합니다.
        - 로고/아이콘은 파일이 존재할 때만 적용합니다.
        - 테이블: 드래그 이동/우클릭 삽입·삭제/툴번호 수정 기능 유지
        """
        self.setWindowTitle("CAM SHEET 자동화")

        # 현재 파일 위치 기준으로 리소스 경로를 잡습니다. (폴더 이동에 안전)
        base_path = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_path, "main-logo.png")
        ico_path = os.path.join(base_path, "main-logo.ico")

        # 아이콘은 파일이 존재할 때만 적용합니다.
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))

        screen = QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()
        screen_width, screen_height = screen_rect.width(), screen_rect.height()

        window_width = int(screen_width * 0.47)
        window_height = int(screen_height * 0.65)
        self.setGeometry(100, 100, window_width, window_height)

        # 배경색은 기존 코드 취지 유지(추후 스타일은 통합 단계에서 처리)
        # 전역 스타일 충돌로 글씨가 안 보이는 문제를 방지하기 위해
        # CAM 페이지 범위에서만 기본 글자색/입력칸 스타일을 안전하게 고정합니다.
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                color: #111111;
            }
            QLabel {
                color: #111111;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #111111;
                border: 1px solid #cfcfcf;
                border-radius: 4px;
                padding: 4px 6px;
            }
            QGroupBox {
                color: #111111;
                border: 1px solid #d9dee8;
                border-radius: 8px;
                margin-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #0050B0;
                font-weight: bold;
            }
        """)

        main_layout = QVBoxLayout()
        container = QGroupBox(self)
        container_layout = QVBoxLayout(container)

        # =========================
        # 헤더(로고 + 타이틀)
        # =========================
        #header_layout = QHBoxLayout()
        #self.logo = QLabel(self)

        #if os.path.exists(logo_path):
        #    pix = QPixmap(logo_path)
        #    if not pix.isNull():
        #        self.logo.setPixmap(pix)

        #self.logo.setFixedSize(150, 70)
        #header_layout.addWidget(self.logo)

        #self.title = QLabel("CAM SHEET 자동화", self)
        #self.title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        #self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        #self.title.setStyleSheet("color: #333; padding: 10px;")
        #header_layout.addWidget(self.title)

        #container_layout.addLayout(header_layout)

        # =========================
        # 상단 입력 필드
        # =========================
        input_layout = QHBoxLayout()
        self.worker_label = QLabel("작업자:")
        self.worker_input = QLineEdit()

        self.job_label = QLabel("작업번호:")
        self.job_input = QLineEdit()

        self.machine_label = QLabel("설비명:")
        self.machine_input = QLineEdit()

        self.date_label = QLabel("날짜:")
        self.date_input = QLineEdit()

        input_layout.addWidget(self.worker_label)
        input_layout.addWidget(self.worker_input)
        input_layout.addWidget(self.job_label)
        input_layout.addWidget(self.job_input)
        input_layout.addWidget(self.machine_label)
        input_layout.addWidget(self.machine_input)
        input_layout.addWidget(self.date_label)
        input_layout.addWidget(self.date_input)

        container_layout.addLayout(input_layout)

        # =========================
        # 테이블
        # =========================
        self.table = QTableWidget(self)
        # ===== [FIX] 테이블 글씨/헤더가 안 보이는 문제 방지 =====
        # (전역 팔레트/스타일 영향으로 글씨가 흰색이 되는 경우를 강제로 차단)
        self.table.setStyleSheet("""
            QTableWidget {
                color: #000000;
                background-color: #ffffff;
                gridline-color: #cfcfcf;
            }
            QHeaderView::section {
                color: #000000;
                background-color: #f2f2f2;
                border: 1px solid #cfcfcf;
                padding: 4px;
                font-weight: bold;
            }
        """)
        self.table.horizontalHeader().setVisible(True)
        self.table.verticalHeader().setVisible(True)

        self.table.setColumnCount(6)
        self.table.setRowCount(24)
        self.table.setHorizontalHeaderLabels(["FILE명", "TOOL D / B", "공구 번호", "여유량(XY)", "작업 내용", "냉각수"])
        self.table.setFont(QFont("Arial", 12))
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 선택/드래그/편집 설정
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDragDropOverwriteMode(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        # 우클릭 메뉴
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        # 드롭 이벤트 커스텀 적용
        self.table.dropEvent = self.dropEvent

        # 툴번호 셀 변경 감지(.h 파일 TOOL CALL 수정)
        self.table.itemChanged.connect(self.handle_tool_number_change)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        for i, width_ratio in enumerate([0.07, 0.3, 0.07, 0.07, 0.35, 0.07]):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(i, int(self.width() * width_ratio))

        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        container_layout.addWidget(self.table)

        # =========================
        # 하단 버튼
        # =========================
        button_layout = QHBoxLayout()

        self.btn_folder = QPushButton("폴더 선택", self)
        self.btn_folder.setStyleSheet(
            "background-color: #0078D7; color: white; font-size: 18px; padding: 10px; border-radius: 5px;"
        )
        self.btn_folder.clicked.connect(self.select_folder)

        self.btn_export = QPushButton("SHEET 추출", self)
        self.btn_export.setStyleSheet(
            "background-color: #28A745; color: white; font-size: 18px; padding: 10px; border-radius: 5px;"
        )
        self.btn_export.clicked.connect(self.export_sheet)

        self.btn_export_pdf = QPushButton("PDF 추출", self)
        self.btn_export_pdf.setStyleSheet(
            "background-color: #6F42C1; color: white; font-size: 18px; padding: 10px; border-radius: 5px;"
        )
        self.btn_export_pdf.clicked.connect(self.export_pdf_cam_only)

        self.btn_export_both = QPushButton("동시 출력(Setting+CAM)", self)
        self.btn_export_both.setStyleSheet(
            "background-color: #FF8C00; color: white; font-size: 18px; padding: 10px; border-radius: 5px;"
        )
        self.btn_export_both.clicked.connect(self.export_pdf_combined_hook)


        button_layout.addWidget(self.btn_folder)
        button_layout.addWidget(self.btn_export)
        button_layout.addWidget(self.btn_export_pdf)
        button_layout.addWidget(self.btn_export_both)
        container_layout.addLayout(button_layout)

        main_layout.addWidget(container)
        self.setLayout(main_layout)

    # =========================
    # 폴더 로딩
    # =========================

    def _start_loading_folder(self, folder_path: str):
        """
        폴더 로딩 스레드를 시작합니다.
        """
        self._warned_jobno_missing = False  # ✅ 3-3: 폴더마다 경고 1회 정책 초기화

        self.selected_folder = folder_path
        self.btn_folder.setEnabled(False)

        self.loader_thread = FileLoaderThread(folder_path)
        self.loader_thread.files_loaded.connect(self.load_files_into_table)
        self.loader_thread.start()

    def select_folder(self):
        """
        폴더 선택 후 백그라운드 스레드로 .h 파일을 읽어 테이블에 반영합니다.
        """
        folder_path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if folder_path:
            print(f"🛠 선택된 폴더: {folder_path}")
            self._start_loading_folder(folder_path)
        else:
            self.btn_folder.setEnabled(True)

    def load_files_into_table(self, file_data, cam_rows):
        print(f"[DEBUG] load_files_into_table called: rows={len(file_data) if file_data else 0}")
        if file_data:
            print(f"[DEBUG] sample_row0={file_data[0]}")
        """
        파일 데이터를 UI 테이블에 로드합니다.
        """
        self.btn_folder.setEnabled(True)

        # ===== [CAM 원본 캐시 저장] =====
        self._cam_rows_cache = cam_rows or []

        if not file_data:
            QMessageBox.warning(self, "경고", "선택한 폴더에 .h 파일이 없습니다!")
            return

        # 툴번호 변경 시그널 차단(불필요한 파일 수정 방지)
        self.table.blockSignals(True)

        self.table.setRowCount(len(file_data))

        for row, (file, tool_db, tool_number, allowance, pg_name, equip_name, job_number, date, coolant) in enumerate(
            file_data
        ):
            try:
                equip_name = equip_name or "N/A"
                job_number = job_number or "N/A"
                date = date or datetime.now().strftime("%m-%d")

                # UI 표시 전 디코딩 적용
                file = safe_decode(file)
                tool_db = safe_decode(tool_db)
                tool_number = safe_decode(tool_number)
                allowance = safe_decode(allowance)
                pg_name = safe_decode(pg_name)
                equip_name = safe_decode(equip_name)
                job_number = safe_decode(job_number)
                date = safe_decode(date)
                coolant = safe_decode(coolant)

                for col, value in enumerate([file, tool_db, tool_number, allowance, pg_name, coolant]):
                    it = QTableWidgetItem(value if value else "N/A")
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row, col, it)

                # =========================
                # 상단 입력칸 자동 반영
                # - 작업번호가 자동 검출되지 않으면(N/A) 입력을 요구합니다.
                # =========================
                if job_number and job_number != "N/A":
                    self.job_input.setText(job_number)
                else:
                    # 자동 검출 실패 → 비워두고 사용자 입력 요구(폴더당 1회만)
                    self.job_input.setText("")
                    if not getattr(self, "_warned_jobno_missing", False):
                        self._warned_jobno_missing = True
                        QMessageBox.warning(
                            self,
                            "작업번호 필요",
                            "폴더명에서 작업번호를 자동 검출하지 못했습니다.\n"
                            "작업번호 입력칸에 작업번호를 직접 입력해 주시옵소서."
                        )

                self.date_input.setText(date)
                self.machine_input.setText(equip_name)


            except Exception as e:
                print(f"❌ 데이터 처리 오류: {e}")

        self.table.blockSignals(False)

    # =========================
    # 드래그 드롭/행 조작
    # =========================
    def dropEvent(self, event):
        """
        드래그 앤 드롭으로 행 이동 시 데이터가 덮어씌워지지 않고 순서만 변경되도록 처리합니다.
        """
        selected_rows = sorted(set(index.row() for index in self.table.selectedIndexes()))
        target_row = self.table.indexAt(event.position().toPoint()).row()

        if target_row == -1 or not selected_rows:
            return

        if target_row in selected_rows:
            return

        # 현재 데이터 저장
        row_data = []
        for row in selected_rows:
            row_items = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None:
                    new_item = QTableWidgetItem(item.text())
                else:
                    new_item = QTableWidgetItem("")
                new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                row_items.append(new_item)
            row_data.append(row_items)

        # 기존 행 삭제 후 새로운 위치에 삽입
        for row in reversed(selected_rows):
            self.table.removeRow(row)

        for row_items in row_data:
            self.table.insertRow(target_row)
            for col, item in enumerate(row_items):
                self.table.setItem(target_row, col, item)
            target_row += 1

        self.update_row_numbers()

    def update_row_numbers(self):
        """
        행 이동/삽입/삭제 시 기본 제공되는 행 번호 표시를 정리합니다.
        """
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.verticalHeader().setVisible(True)

    def show_context_menu(self, position):
        """
        오른쪽 클릭 시 삽입 및 삭제 메뉴를 표시합니다.
        """
        menu = QMenu(self)
        insert_action = menu.addAction("삽입")
        delete_action = menu.addAction("삭제")

        action = menu.exec(self.table.viewport().mapToGlobal(position))

        if action == insert_action:
            self.insert_new_row()
        elif action == delete_action:
            self.delete_selected_row()

    def insert_new_row(self):
        """
        선택한 행 위에 새로운 빈 행을 삽입합니다.
        """
        selected_rows = sorted(set(index.row() for index in self.table.selectedIndexes()))
        if selected_rows:
            row_position = selected_rows[0]
        else:
            row_position = self.table.rowCount()

        self.table.insertRow(row_position)
        self.update_row_numbers()
        QMessageBox.information(self, "삽입 완료", "새로운 행이 추가되었습니다.")

    def delete_selected_row(self):
        """
        선택된 행을 삭제합니다.
        """
        selected_rows = sorted(set(index.row() for index in self.table.selectedIndexes()), reverse=True)

        if selected_rows:
            reply = QMessageBox.question(
                self,
                "삭제 확인",
                "선택한 행을 삭제하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                for row in selected_rows:
                    self.table.removeRow(row)
                self.update_row_numbers()
        else:
            QMessageBox.warning(self, "경고", "삭제할 행을 선택하세요!")

    def export_sheet(self):
        """
        'SHEET 추출' 버튼 클릭 시 실행합니다.
        """
        job_number = self.job_input.text().strip()
        machine_name = self.machine_input.text().strip()
        date = self.date_input.text().strip()

        if not job_number:
            QMessageBox.warning(self, "경고", "작업번호를 입력해주세요!")
            return

        folder_path = self.selected_folder if self.selected_folder else None
        if not folder_path:
            QMessageBox.warning(self, "경고", "데이터 폴더를 먼저 선택해주세요!")
            return

        try:
            save_path = export_to_excel_with_auto_filename(
                job_number, machine_name, date, self.table, folder_path
            )
            if save_path:
                QMessageBox.information(self, "저장 완료", f"엑셀 파일이 저장되었습니다!\n{save_path}")
            else:
                QMessageBox.warning(self, "저장 실패", "파일 저장 중 오류가 발생했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", f"파일 저장 중 오류 발생: {e}")

    # =========================
    # PDF 출력(CAM only / Combined Hook)
    # =========================

    def _collect_cam_rows_from_table(self):
        """
        테이블 내용을 CAM PDF 표 출력용 dict 리스트로 변환합니다.
        (표 그리기는 cam_print_engine이 담당)
        """
        rows = []
        for r in range(self.table.rowCount()):
            file_name = self.table.item(r, 0).text().strip() if self.table.item(r, 0) else ""
            tool_db = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            tool_no = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
            allowance = self.table.item(r, 3).text().strip() if self.table.item(r, 3) else ""
            work_desc = self.table.item(r, 4).text().strip() if self.table.item(r, 4) else ""
            coolant = self.table.item(r, 5).text().strip() if self.table.item(r, 5) else ""

            # 빈 행 스킵(파일명/공구번호 둘 다 없으면 의미 없음)
            if not file_name and not tool_no:
                continue

            # cam_print_engine 기본 키(표 헤더)와 매핑
            rows.append({
                "ToolNo": tool_no,
                "ToolName": work_desc,
                "Holder": tool_db,
                "RPM": "",
                "Feed": "",
                "DOC": allowance,
                "WOC": "",
                "Coolant": coolant,
                "FILE": file_name,
            })
        return rows

    def _collect_cam_rows_from_cache(self):
        """
        CamRow 원본 캐시(self._cam_rows_cache)를 PDF 표 출력용 dict 리스트로 변환합니다.
        """
        rows = []
        for r in (self._cam_rows_cache or []):
            rows.append({
                "ToolNo": (r.tool_no or "").strip(),
                "ToolName": (r.pg_name or "").strip(),
                "Holder": (r.tool_db or "").strip(),
                "RPM": "",
                "Feed": "",
                "DOC": (r.allowance_xy or "").strip(),
                "WOC": "",
                "Coolant": (r.coolant or "").strip(),
                "FILE": (r.file_name or "").strip(),
            })
        return rows

    def export_pdf_cam_only(self):
        """
        CAM만 PDF 출력.
        - 엑셀 제거는 후순위이므로, 기존 export_sheet(엑셀)은 유지
        - PDF 출력은 SettingSheet의 헤더를 그대로 사용
        - 설비/작업자/날짜는 Setting 전역 설정(JSON)을 우선 사용
        - 특이사항은 SettingSheet의 notes_edit를 그대로 사용
        """

        # =========================
        # 1) 기본 값(CAM 입력칸)
        # =========================
        job_number = self.job_input.text().strip()
        machine_name = self.machine_input.text().strip()
        date = self.date_input.text().strip()
        worker = self.worker_input.text().strip()

        # =========================
        # 2) 헤더 데이터 소스: Setting 설정(JSON) 우선
        # =========================
        if getattr(self, "use_setting_header", False) and callable(getattr(self, "_header_provider", None)):
            try:
                info = self._header_provider() or {}
                machine_name = (info.get("machine") or machine_name).strip()
                worker = (info.get("operator") or worker).strip()
                date = (info.get("date") or date).strip()
            except Exception:
                pass

        # =========================
        # 3) 필수 값 체크
        # =========================
        if not job_number:
            QMessageBox.warning(self, "경고", "작업번호를 입력해주세요!")
            return

        # =========================
        # 4) CAM 데이터 수집 (원본 CamRow 기준)
        # =========================
        cam_rows = self._collect_cam_rows_from_cache()
        if not cam_rows:
            QMessageBox.warning(self, "경고", "출력할 CAM 표 데이터가 없습니다.")
            return

        # =========================
        # 5) 특이사항: SettingSheet에서 그대로 가져오기
        # =========================
        notes_text = ""
        try:
            shell = self.window()  # 통합 쉘
            setting_page = getattr(shell, "page_setting", None)
            if setting_page is not None and hasattr(setting_page, "notes_edit"):
                notes_text = (setting_page.notes_edit.toPlainText() or "").strip()
        except Exception:
            notes_text = ""

        # =========================
        # 6) 헤더 Payload (fallback 용)
        # ※ 실제 헤더는 Setting PrintEngine._draw_header가 그림
        # =========================
        header = HeaderPayload(
            module_title="CAM SHEET",
            project_title=job_number,
            line1=f"설비: {machine_name or '-'}    작업자: {worker or '-'}    날짜: {date or '-'}",
            line2="",  # 폴더/기타 문구 제거
        )

        payload = CamPrintPayload(
            header=header,
            notes_text=notes_text,
            cam_rows=cam_rows,
        )

        # =========================
        # 7) PDF 출력 (세로 고정)
        # =========================
        self._cam_printer.export_cam_pdf(payload, layout="세로")


    def export_pdf_combined_hook(self):
        """
        동시 출력 버튼용 훅.
        - 최종 목표: Setting 1p + CAM 1p 이상을 한 PDF로 출력
        - 현재 CAM 단독 앱에서는 Setting 메인 윈도우 인스턴스가 없으므로,
          통합 UI에서 이 함수를 '대체/연결'할 예정.
        """
        QMessageBox.information(
            self,
            "동시 출력",
            "동시 출력(Setting+CAM)은 통합 UI에서 동작하도록 연결 예정입니다.\n"
            "현재 CAM 단독 실행에서는 Setting 화면 인스턴스가 없어 실행할 수 없습니다."
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CamSheetApp()
    window.show()
    sys.exit(app.exec())
