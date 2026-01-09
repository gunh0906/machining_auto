# main.py
import sys
import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QTransform, QPainter, QKeySequence, QShortcut, QIcon, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QGroupBox, QFormLayout,
    QGridLayout, QFrame, QStatusBar, QInputDialog, QTextEdit, QFileDialog,
    QMenuBar, QMenu, QMessageBox, QDialog, QDialogButtonBox, QListWidget,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QDoubleSpinBox,
    QSpinBox, 
)
from PySide6.QtCore import QSettings


from .calculations import (
    parse_float, format_signed,
    calc_outer_to_center, calc_center_to_outer, calc_z_height,
)

from .settings_manager import (
    generate_default_filename,
    load_global_settings,
    save_global_settings,
    get_operator_for_machine,
)


from .annotations import AnnotationSet, Point2D, ShapeType
from .graphics_annotations import AnnotationScene
from .annotation_tools import AnnotationToolState, ToolKind
from .annotation_controller import AnnotationController
from .print_engine import PrintEngine

# 색상 선택용 팔레트 (좌표 / 추가 치수 공통)
COLOR_CHOICES = [
    "Red", "Green", "Blue", "Yellow",
    "Magenta", "Cyan", "Orange", "Black", "Gray"
]

def create_color_combo(initial: str = "Red") -> QComboBox:
    """
    색상 아이콘 + 텍스트 콤보.
    - 전역 QSS 충돌을 막기 위해, 인라인 QSS를 제거하고 objectName 스코프로만 스타일을 건다.
    - (drop-down 폭/패딩은 20_inputs_safe.qss의 #ColorCombo로 제어)
    """
    combo = QComboBox()
    combo.setObjectName("ColorCombo")
    combo.setIconSize(QSize(14, 14))

    for name in COLOR_CHOICES:
        pix = QPixmap(14, 14)
        pix.fill(QColor(name))
        combo.addItem(QIcon(pix), name)

    if initial in COLOR_CHOICES:
        combo.setCurrentText(initial)

    # ✅ 폭 제한 제거(잘림 방지)
    combo.setMinimumWidth(120)
    combo.setMaximumWidth(200)

    # ✅ 인라인 setStyleSheet 제거 (QSS 파일에서만 관리)
    return combo



def apply_mono_font_safe(edit: QLineEdit, family: str = "Consolas", fallback_pt: int = 11):
    """
    QFont.pointSize()가 -1(미설정)일 수 있으므로 안전하게 고정합니다.
    - pointSize > 0 이면 pointSize 유지
    - 아니면 pixelSize > 0 이면 pixelSize 유지
    - 둘 다 아니면 fallback_pt 적용
    """
    base = edit.font()
    mono = QFont(family)
    if not mono.exactMatch():
        return

    pt = int(base.pointSize())
    if pt > 0:
        mono.setPointSize(pt)
    else:
        px = int(base.pixelSize())
        if px > 0:
            mono.setPixelSize(px)
        else:
            mono.setPointSize(int(fallback_pt))

    edit.setFont(mono)


class ImageView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageView")
        self.setScene(scene)

        # ▶ 이미지 영역만 흰색 배경
        self.setBackgroundBrush(Qt.white)

        # ✅ 인라인 테두리 제거: 00_base.qss의 QGraphicsView#ImageView 로 처리
        # self.setStyleSheet("QGraphicsView { border: 1px solid black; }")

        # 기존 설정
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setCursor(Qt.ArrowCursor)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)


    def resizeEvent(self, event):
        """창 크기 변경 시 현재 Scene 전체가 프레임에 맞게 보이도록"""
        super().resizeEvent(event)
        if self.scene() is not None and not self.scene().sceneRect().isNull():
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)


# ─────────────────────────────
# 설정 대화창 : 설비 목록 + 설비별 작업자명
# ─────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, parent=None, machine_list=None, operator_map=None):
        super().__init__(parent)
        self.setWindowTitle("설비 / 작업자 설정")

        self.machine_list = list(machine_list or [])
        self.operator_map = dict(operator_map or {})  # {설비명: 작업자명}

        layout = QVBoxLayout(self)

        # ─ 설비 목록 영역 ─
        group_m = QGroupBox("설비 목록")
        v_m = QVBoxLayout(group_m)

        self.list_machines = QListWidget()
        for name in self.machine_list:
            self.list_machines.addItem(name)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("추가")
        btn_del = QPushButton("삭제")
        btn_ren = QPushButton("이름변경")
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_ren)
        btn_row.addStretch(1)

        v_m.addWidget(self.list_machines)
        v_m.addLayout(btn_row)

        # ─ 선택 설비의 작업자 영역 ─
        group_op = QGroupBox("선택 설비의 작업자")
        v_op = QVBoxLayout(group_op)
        form_op = QFormLayout()
        form_op.setLabelAlignment(Qt.AlignRight)

        self.edit_operator = QLineEdit()
        form_op.addRow("작업자명:", self.edit_operator)
        v_op.addLayout(form_op)

        layout.addWidget(group_m)
        layout.addWidget(group_op)

        # 버튼
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 시그널
        btn_add.clicked.connect(self.add_machine)
        btn_del.clicked.connect(self.del_machine)
        btn_ren.clicked.connect(self.rename_machine)
        self.list_machines.currentRowChanged.connect(self.on_machine_selected)
        self.edit_operator.editingFinished.connect(self.on_operator_edited)

        # 초기 선택
        if self.machine_list:
            self.list_machines.setCurrentRow(0)
            self.on_machine_selected(0)

    # 현재 선택된 설비명
    def current_machine_name(self):
        row = self.list_machines.currentRow()
        if row < 0 or row >= len(self.machine_list):
            return None
        return self.machine_list[row]

    def on_machine_selected(self, row: int):
        name = self.current_machine_name()
        if not name:
            self.edit_operator.setText("")
            return
        op = self.operator_map.get(name, "")
        self.edit_operator.setText(op)

    def on_operator_edited(self):
        name = self.current_machine_name()
        if not name:
            return
        self.operator_map[name] = self.edit_operator.text().strip()

    def add_machine(self):
        text, ok = QInputDialog.getText(self, "설비 추가", "설비명을 입력하십시오:")
        if not ok or not text.strip():
            return
        name = text.strip()
        if name in self.machine_list:
            QMessageBox.warning(self, "중복", "이미 존재하는 설비명입니다.")
            return
        self.machine_list.append(name)
        self.list_machines.addItem(name)
        self.list_machines.setCurrentRow(self.list_machines.count() - 1)

    def del_machine(self):
        row = self.list_machines.currentRow()
        if row < 0:
            return
        name = self.machine_list[row]
        ret = QMessageBox.question(
            self, "삭제 확인",
            f"설비 '{name}' 을(를) 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        self.list_machines.takeItem(row)
        self.machine_list.pop(row)
        # 작업자 맵에서도 제거
        if name in self.operator_map:
            del self.operator_map[name]
        # 선택 이동
        if self.machine_list:
            new_row = min(row, len(self.machine_list) - 1)
            self.list_machines.setCurrentRow(new_row)
        else:
            self.edit_operator.setText("")

    def rename_machine(self):
        row = self.list_machines.currentRow()
        if row < 0:
            return
        old_name = self.machine_list[row]
        text, ok = QInputDialog.getText(
            self, "설비 이름 변경",
            "새 설비명을 입력하십시오:", text=old_name
        )
        if not ok or not text.strip():
            return
        new_name = text.strip()
        if new_name == old_name:
            return
        if new_name in self.machine_list:
            QMessageBox.warning(self, "중복", "이미 존재하는 설비명입니다.")
            return

        # 리스트 갱신
        self.machine_list[row] = new_name
        self.list_machines.item(row).setText(new_name)

        # 작업자 맵 키도 변경
        op = self.operator_map.get(old_name, "")
        if old_name in self.operator_map:
            del self.operator_map[old_name]
        self.operator_map[new_name] = op

        self.on_machine_selected(row)

    def get_values(self):
        return self.machine_list, self.operator_map


# ─────────────────────────────
# 메인 윈도우
# ─────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("세팅 시트 도구 (Ver1.0-20251223)")

        # EXE(PyInstaller)에서도 동작하는 base_dir
        from pathlib import Path
        import sys
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

        # 제목 표시줄 아이콘은 ico 사용 권장
        icon_path = base_dir / "assets" / "SettingSheetTool.ico"
        self.setWindowIcon(QIcon(str(icon_path)))

        self.resize(1200, 800)


        # ─ 주석 도구 상태 (기본값) ─
        self.current_shape_type = ShapeType.RECT      # 기본 도형 = 사각형
        self.current_stroke_width = 1.5               # 기본 선 두께 = 1.5

        # ★ ToolState + Annotation 데이터 + Scene + Controller 준비
        self.tool_state = AnnotationToolState(
            shape_type=self.current_shape_type,
            stroke_width=self.current_stroke_width,
        )

        self.annotation_set = AnnotationSet()
        self.annotation_scene = AnnotationScene(self)
        self.annotation_scene.set_annotation_set(self.annotation_set)
        
        self.annotation_controller = AnnotationController(
            self.annotation_scene,
            self.annotation_set,
            self.tool_state,
        )
        # Scene이 마우스 이벤트를 Controller로 넘길 수 있도록 연결
        self.annotation_scene.controller = self.annotation_controller

        # ★ 인쇄 / PDF 생성 엔진 준비
        self.print_engine = PrintEngine(self)


        # ─ 주석 삭제용 단축키 (Delete 키) 설정 ─
        self.delete_annotation_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self)
        self.delete_annotation_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.delete_annotation_shortcut.activated.connect(self.on_delete_selected_annotations)



        # 전역 설정에서 설비 목록 / 설비별 작업자 불러오기
        machines, op_map = load_global_settings()
        self.machine_list = machines or ["DINO 5AX", "STINGER", "RONIN"]
        self.operator_map = op_map or {}  # {설비명: 작업자명}

        # 모드: CENTER(True) / ONE-POINT(False)
        self.mode_center = True

        self._create_menu_bar()

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 10)
        central_layout.setSpacing(2)

        # ─ 1. 상단 : 프로젝트명 + MODE ─
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # ✅ 줄 사이 간격이 “두꺼운 상단”을 만들므로 0으로 고정
        top_layout.setSpacing(0)
        
        # 1-1. 프로젝트명 (+ MODE)
        line1 = QWidget()
        
        line1.setObjectName("TopControls")  # ✅ 구분선은 이 줄 아래에만 적용
        
        line1_layout = QHBoxLayout(line1)
        line1_layout.setContentsMargins(10, 4, 10, 4)  # ✅ 과도한 높이 방지용: 최소 상하 패딩
        line1_layout.setSpacing(10)
        
        lbl_project = QLabel("프로젝트명:")
        lbl_project.setStyleSheet("font-weight: bold;")  # ✅ 프로젝트명 라벨 굵게

        self.edit_project = QLineEdit()
        self.edit_project.setPlaceholderText("예: 작번 / 프로젝트 명")
        
        line1_layout.addWidget(lbl_project)
        line1_layout.addWidget(self.edit_project, 1)
        line1_layout.addStretch(1)
        
        lbl_mode = QLabel("MODE :")
        lbl_mode.setStyleSheet("font-weight: bold;")
        
        self.btn_mode_center = QPushButton("CENTER")
        self.btn_mode_onepoint = QPushButton("ONE-POINT")
        for btn in (self.btn_mode_center, self.btn_mode_onepoint):
            btn.setCheckable(True)
            btn.setMinimumWidth(90)
            btn.setMinimumHeight(28)
        
        self.btn_mode_center.setChecked(True)
        self.btn_mode_center.clicked.connect(self.on_mode_center)
        self.btn_mode_onepoint.clicked.connect(self.on_mode_onepoint)
        
        line1_layout.addWidget(lbl_mode)
        line1_layout.addWidget(self.btn_mode_center)
        line1_layout.addWidget(self.btn_mode_onepoint)
        
        # ✅ line2(빈 줄) 제거: “정의하지 않음” 방지를 위해 아예 생성하지 않음
        top_layout.addWidget(line1)
        # ✅ 프로젝트명 아래 구분선: TopBar 구분선과 동일하게 “Divider 위젯”으로 처리
        proj_div = QWidget()
        proj_div.setObjectName("ProjectDivider")
        proj_div.setFixedHeight(1)
        top_layout.addWidget(proj_div)
        
        # ─ 2. 중앙 : 좌측 정보 + 우측 A4 프레임 ─
        middle_widget = QWidget()
        middle_layout = QHBoxLayout(middle_widget)
        middle_layout.setContentsMargins(10, 6, 10, 6)
        middle_layout.setSpacing(10)

        # ─────────────────────────────
        # [UI] 그룹박스: 타이틀만 Bold, 본문은 Normal로 유지
        # ─────────────────────────────
        def _wrap_groupbox_title_bold(gb: QGroupBox, *, outer_margins=(8, 8, 8, 8), outer_spacing=6) -> QWidget:
            """
            QGroupBox 타이틀만 굵게 표시하기 위한 래퍼.
            - gb 폰트를 Bold로 설정 → 타이틀이 확실히 굵어짐
            - gb 내부에 body(QWidget)를 하나 두고 body 폰트를 Normal로 되돌림 → 본문 글씨 굵기 유지
            - 반환: 본문을 담을 body(QWidget)
            """
            title_font = gb.font()
            title_font.setBold(True)
            gb.setFont(title_font)

            body = QWidget(gb)
            body_font = body.font()
            body_font.setBold(False)
            body.setFont(body_font)

            gb_layout = QVBoxLayout(gb)
            gb_layout.setContentsMargins(*outer_margins)
            gb_layout.setSpacing(outer_spacing)
            gb_layout.addWidget(body)

            return body
        
        def _apply_group_title_pill(gb: QGroupBox) -> None:
            """
            특정 그룹박스 1개에만 '둥근 네모 배지' 타이틀을 적용한다.
            - QGroupBox 범용 선택자를 쓰면 자식 QGroupBox까지 전파되므로
              objectName(#id)로 스코프를 제한한다.
            """
            obj = gb.objectName().strip()
            if not obj:
                # objectName이 없으면 스코프 제한을 할 수 없으므로 적용하지 않는다.
                return

            gb.setStyleSheet(
                f"""
                QGroupBox#{obj} {{
                    margin-top: 18px;               /* 배지 상단 공간 확보 */
                }}
                QGroupBox#{obj}::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;

                    left: 12px;
                    top: 0px;                       /* 음수 이동 제거(클리핑/겹침 방지) */

                    padding: 4px 10px;
                    background: #FFFFFF;
                    border: 1px solid #D7DCE6;
                    border-radius: 10px;
                }}
                """
            )
        # ─────────────────────────────
        # [UI] 간격 표준값 (섹션 리듬 통일)
        # ─────────────────────────────
        CARD_OUTER_MARGINS = (8, 14, 8, 8)     # 좌/우 큰 카드(배지 포함)
        SECTION_OUTER_MARGINS = (5, 12, 5, 5)  # 내부 섹션 그룹(타이틀과 본문 간격 포함)
        SECTION_SPACING = 6                    # 섹션 내부 기본 간격
        FORM_V_SPACING = 6                     # QFormLayout 세로 간격


        left_group = QGroupBox("공작물 / 세팅 정보")
        left_group.setObjectName("PanelLeft")  # ✅ 좌측 카드 패널
        _apply_group_title_pill(left_group)    # ✅ 타이틀 둥근 배지 적용
        left_body = _wrap_groupbox_title_bold(left_group, outer_margins=(8, 14, 8, 8), outer_spacing=6)
        left_layout = QVBoxLayout(left_body)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # ─ 좌측 상단: 오퍼레이터 기준 / 표시부 + 색상 + 추가 좌표 ─
        self.operator_group = QGroupBox("오퍼레이터 기준 좌표 (양센터)")
        self.operator_group.setObjectName("operatorGroup")  # ★ 기존 유지

        # ✅ 타이틀만 Bold, 본문은 Normal 유지 (기존 함수 재사용)
        operator_body = _wrap_groupbox_title_bold(
            self.operator_group,
            outer_margins=SECTION_OUTER_MARGINS,
            outer_spacing=SECTION_SPACING,
        )


        op_layout = QVBoxLayout(operator_body)
        op_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.setSpacing(SECTION_SPACING)

        # ✅ form_widget / op_form 생성부 (반드시 addRow보다 위에 존재해야 함)
        form_widget = QWidget()
        op_form = QFormLayout(form_widget)
        op_form.setLabelAlignment(Qt.AlignRight)
        op_form.setVerticalSpacing(FORM_V_SPACING)
        # (이 아래는 기존 코드 그대로 이어가시면 됩니다)
        # 예: self.edit_x_center / self.edit_y_center 생성, op_form.addRow(...), 등등

        op_layout.addWidget(form_widget)
        # ✅ CENTER 입력 필드 (반드시 x_row/y_row에서 참조하기 전에 생성되어야 함)
        self.edit_x_center = QLineEdit()
        self.edit_y_center = QLineEdit()
        for e in (self.edit_x_center, self.edit_y_center):
            e.setMaximumWidth(120)
            e.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            apply_mono_font_safe(e)

        # 센터 좌표 색상 콤보 (기본값: Red / Blue, 필요 시 '없음' 선택 가능)
        self.combo_x_center_color = create_color_combo("Red")
        self.combo_x_center_color.setParent(self.operator_group)  # ★ 안전한 부모
        none_pix = QPixmap(14, 14)
        none_pix.fill(Qt.transparent)
        self.combo_x_center_color.insertItem(0, QIcon(none_pix), "없음")
        self.combo_x_center_color.setCurrentText("Red")
        self.combo_x_center_color.hide()  # ★ 추가

        self.combo_y_center_color = create_color_combo("Blue")
        self.combo_y_center_color.setParent(self.operator_group)  # ★ 안전한 부모
        none_pix2 = QPixmap(14, 14)
        none_pix2.fill(Qt.transparent)
        self.combo_y_center_color.insertItem(0, QIcon(none_pix2), "없음")
        self.combo_y_center_color.setCurrentText("Blue")
        self.combo_y_center_color.hide()  # ★ 추가


        x_row = QWidget()
        x_row_layout = QHBoxLayout(x_row)
        x_row_layout.setContentsMargins(0, 0, 0, 0)
        x_row_layout.setSpacing(4)
        x_row_layout.addWidget(self.edit_x_center)
        #x_row_layout.addWidget(self.combo_x_center_color)
        x_row_layout.addStretch(1)

        y_row = QWidget()
        y_row_layout = QHBoxLayout(y_row)
        y_row_layout.setContentsMargins(0, 0, 0, 0)
        y_row_layout.setSpacing(4)
        y_row_layout.addWidget(self.edit_y_center)
        #y_row_layout.addWidget(self.combo_y_center_color)
        y_row_layout.addStretch(1)

        self.lbl_center1 = QLabel("X 센터 (mm):")
        self.lbl_center2 = QLabel("Y 센터 (mm):")

        op_form.addRow(self.lbl_center1, x_row)
        op_form.addRow(self.lbl_center2, y_row)

        # 구분선 (✅ 1px Divider: 프레임 라인이 아닌 배경색으로 그려 검정 잔상 제거)
        coord_sep = QWidget()
        coord_sep.setFixedHeight(1)
        coord_sep.setProperty("divider", "true")
        op_layout.addWidget(coord_sep)

        # 추가 좌표 영역
        coord_extra_header = QWidget()
        coord_extra_header_layout = QHBoxLayout(coord_extra_header)
        coord_extra_header_layout.setContentsMargins(0, 0, 0, 0)
        coord_extra_header_layout.setSpacing(4)

        coord_extra_header_layout.addWidget(QLabel("추가 좌표:"))
        coord_extra_header_layout.addStretch(1)

        self.btn_add_coord = QPushButton("+")
        self.btn_add_coord.setObjectName("addCoordButton")
        self.btn_add_coord.setCursor(Qt.PointingHandCursor)
        self.btn_add_coord.setFocusPolicy(Qt.NoFocus)
        self.btn_add_coord.setFixedSize(36, 30)
        self.btn_add_coord.setToolTip("추가 좌표 입력")
        self.btn_add_coord.clicked.connect(self.add_coord_point)
        self.btn_add_coord.setFlat(False)

        coord_extra_header_layout.addWidget(self.btn_add_coord)
        op_layout.addWidget(coord_extra_header)

        self.coord_extra_layout = QVBoxLayout()
        self.coord_extra_layout.setSpacing(2)
        op_layout.addLayout(self.coord_extra_layout)

        # ─ 외곽 치수 (X/Y) ─
        outer_group = QGroupBox("외곽 치수 (X / Y)")

        outer_body = _wrap_groupbox_title_bold(
            outer_group,
            outer_margins=SECTION_OUTER_MARGINS,
            outer_spacing=SECTION_SPACING,
        )
        outer_layout = QGridLayout(outer_body)
        outer_layout.setContentsMargins(0, 0, 0, 0)     # ✅ 중복 패딩 제거
        outer_layout.setHorizontalSpacing(8)            # ✅ 좌우 필드 간격
        outer_layout.setVerticalSpacing(FORM_V_SPACING) # ✅ 행 간격

        self.edit_x_minus = QLineEdit()
        self.edit_x_plus = QLineEdit()
        self.edit_y_minus = QLineEdit()
        self.edit_y_plus = QLineEdit()
        for e in (self.edit_x_minus, self.edit_x_plus,
                  self.edit_y_minus, self.edit_y_plus):
            e.setMaximumWidth(120)

        outer_layout.addWidget(QLabel("X- (mm):"), 0, 0)
        outer_layout.addWidget(self.edit_x_minus, 0, 1)
        outer_layout.addWidget(QLabel("X+ (mm):"), 0, 2)
        outer_layout.addWidget(self.edit_x_plus, 0, 3)

        outer_layout.addWidget(QLabel("Y- (mm):"), 1, 0)
        outer_layout.addWidget(self.edit_y_minus, 1, 1)
        outer_layout.addWidget(QLabel("Y+ (mm):"), 1, 2)
        outer_layout.addWidget(self.edit_y_plus, 1, 3)

        self.lbl_x_info = QLabel()
        self.lbl_y_info = QLabel()
        outer_layout.addWidget(self.lbl_x_info, 2, 0, 1, 4)
        outer_layout.addWidget(self.lbl_y_info, 3, 0, 1, 4)

        outer_sep = QWidget()
        outer_sep.setFixedHeight(1)
        outer_sep.setProperty("divider", "true")  # ✅ QSS로 통일 (인라인 색상 고정 제거)
        outer_layout.addWidget(outer_sep, 4, 0, 1, 4)

        self.outer_extra_layout = QVBoxLayout()
        self.outer_extra_layout.setSpacing(2)
        outer_extra_row = QWidget()
        outer_extra_row_layout = QHBoxLayout(outer_extra_row)
        outer_extra_row_layout.setContentsMargins(0, 4, 0, 0)
        outer_extra_row_layout.setSpacing(4)

        btn_outer_add = QPushButton("+")
        btn_outer_add.setObjectName("addOuterButton")
        btn_outer_add.setCursor(Qt.PointingHandCursor)
        btn_outer_add.setFocusPolicy(Qt.NoFocus)
        btn_outer_add.setFlat(False)
        btn_outer_add.setFixedSize(36, 30)
        btn_outer_add.setToolTip("외곽 관련 치수 항목 추가")
        btn_outer_add.clicked.connect(self.add_outer_dimension)

        outer_extra_row_layout.addWidget(QLabel("추가 치수:"))
        outer_extra_row_layout.addStretch(1)
        outer_extra_row_layout.addWidget(btn_outer_add)

        outer_layout.addLayout(self.outer_extra_layout, 5, 0, 1, 4)
        outer_layout.addWidget(outer_extra_row, 6, 0, 1, 4)

        # ─ Z 정보 ─
        z_group = QGroupBox("Z 정보")

        z_body = _wrap_groupbox_title_bold(
            z_group,
            outer_margins=SECTION_OUTER_MARGINS,
            outer_spacing=SECTION_SPACING,
        )

        # ✅ 기존 코드가 z_form.addRow(...)를 사용하므로 QFormLayout을 반드시 생성
        z_form = QFormLayout(z_body)
        z_form.setLabelAlignment(Qt.AlignRight)
        z_form.setVerticalSpacing(FORM_V_SPACING)
        z_form.setContentsMargins(0, 0, 0, 0)

        self.edit_z_bottom = QLineEdit()
        self.edit_z_top = QLineEdit()
        self.lbl_z_height = QLabel()
        for e in (self.edit_z_bottom, self.edit_z_top):
            e.setMaximumWidth(120)

        z_form.addRow("Z 바닥 (mm):", self.edit_z_bottom)
        z_form.addRow("Z 상면 기준 (mm):", self.edit_z_top)
        z_form.addRow("", self.lbl_z_height)

        z_sep = QWidget()
        z_sep.setFixedHeight(1)
        outer_sep.setProperty("divider", "true")  # ✅ QSS로 통일 (인라인 색상 고정 제거)
        z_form.addRow("", z_sep)


        z_extra_container = QWidget()
        z_extra_layout_container = QVBoxLayout(z_extra_container)
        z_extra_layout_container.setContentsMargins(0, 4, 0, 0)
        z_extra_layout_container.setSpacing(2)

        btn_z_add = QPushButton("+")
        btn_z_add.setObjectName("addZButton")
        btn_z_add.setCursor(Qt.PointingHandCursor)
        btn_z_add.setFocusPolicy(Qt.NoFocus)
        btn_z_add.setFlat(False)
        btn_z_add.setFixedSize(36, 30)
        btn_z_add.setToolTip("Z 관련 치수 항목 추가")
        btn_z_add.clicked.connect(self.add_z_dimension)

        z_extra_top = QHBoxLayout()
        z_extra_top.addWidget(QLabel("추가 치수:"))
        z_extra_top.addStretch(1)
        z_extra_top.addWidget(btn_z_add)

        z_extra_layout_container.addLayout(z_extra_top)
        self.z_extra_layout = QVBoxLayout()
        self.z_extra_layout.setSpacing(2)
        z_extra_layout_container.addLayout(self.z_extra_layout)
        z_form.addRow(z_extra_container)

        # ─ 특이사항 ─
        notes_group = QGroupBox("특이사항")

        notes_body = _wrap_groupbox_title_bold(
            notes_group,
            outer_margins=SECTION_OUTER_MARGINS,
            outer_spacing=SECTION_SPACING,
        )
        notes_layout = QVBoxLayout(notes_body)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(SECTION_SPACING)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("현장 특이사항, 주의사항 등을 자유롭게 입력하십시오.")
        self.notes_edit.setMinimumHeight(80)
        notes_layout.addWidget(self.notes_edit)

        left_layout.addWidget(self.operator_group)
        left_layout.addWidget(outer_group)
        left_layout.addWidget(z_group)

        # ✅ 남는 공간은 특이사항 "위"에서만 흡수 (특이사항 아래 여백 증가 방지)
        left_layout.addStretch(1)

        left_layout.addWidget(notes_group)

        
        # ─ 우측 : A4 프레임 (이미지 + 치수 표기) ─
        right_group = QGroupBox("A4 프레임 (이미지 + 치수 표기)")
        right_group.setObjectName("PanelRight")  # ✅ 우측 카드 패널
        _apply_group_title_pill(right_group)     # ✅ 타이틀 둥근 배지 적용
        right_body = _wrap_groupbox_title_bold(right_group, outer_margins=(8, 14, 8, 8), outer_spacing=6)
        right_layout = QVBoxLayout(right_body)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # 상단: 이미지 불러오기 버튼
        img_top = QWidget()
        img_top_layout = QHBoxLayout(img_top)
        img_top_layout.setContentsMargins(0, 0, 0, 0)
        img_top_layout.setSpacing(4)

        self.btn_load_image = QPushButton("이미지 불러오기")
        self.btn_load_image.setObjectName("LoadImageButton")
        self.btn_load_image.setToolTip("스크린샷 또는 도면 이미지를 불러옵니다.")
        self.btn_load_image.clicked.connect(self.load_image_file)
        self.btn_load_image.setMinimumWidth(90)                # ✅ MODE와 동일
        self.btn_load_image.setMinimumHeight(28)

        self.btn_reset = QPushButton("초기화")
        self.btn_reset.setObjectName("ResetButton")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setFocusPolicy(Qt.NoFocus)
        self.btn_reset.setMinimumWidth(90)                # ✅ MODE와 동일
        self.btn_reset.setMinimumHeight(28)
        self.btn_reset.setToolTip("모든 주석과 이미지를 초기화합니다.")
        self.btn_reset.clicked.connect(self.reset_all)


        img_top_layout.addWidget(self.btn_reset)


        img_top_layout.addWidget(self.btn_load_image)
        img_top_layout.addStretch(1)

        # ✅ PDF 생성 버튼 - (세로/가로 선택) 콤보의 왼쪽에 배치
        self.btn_export_pdf = QPushButton("PDF 생성")
        self.btn_export_pdf.setObjectName("PdfButton")
        self.btn_export_pdf.setMinimumWidth(90)
        self.btn_export_pdf.setMinimumHeight(28)
        self.btn_export_pdf.setToolTip("현재 세팅 시트를 A4 레이아웃으로 PDF로 저장합니다.")
        self.btn_export_pdf.clicked.connect(self.on_export_pdf)
        img_top_layout.addWidget(self.btn_export_pdf)

        # ✅ PDF 레이아웃 선택(세로/가로) - A4 프레임 안쪽, 오른쪽 끝
        self.combo_pdf_layout = QComboBox()
        self.combo_pdf_layout.addItems(["세로", "가로"])

        # ❌ self.combo_pdf_layout.setFixedWidth(80)
        # ✅ 드롭다운/텍스트가 잘리지 않도록 최소 폭 확보
        self.combo_pdf_layout.setMinimumWidth(90)
        self.combo_pdf_layout.setMaximumWidth(140)

        # ✅ ▼ 영역 확보
        self.combo_pdf_layout.setStyleSheet("""
            QComboBox {
                padding-right: 18px;
            }
            QComboBox::drop-down {
                width: 18px;
                border-left: 0px;
            }
        """)

        self.combo_pdf_layout.setToolTip("PDF 출력 레이아웃을 선택합니다.")
        img_top_layout.addWidget(self.combo_pdf_layout)
        right_layout.addWidget(img_top)

        # 중간: 주석 도구 바 (도형 + 화살표/텍스트 + 두께/색상)
        anno_tools = QWidget()
        anno_layout = QVBoxLayout(anno_tools)
        anno_layout.setContentsMargins(0, 0, 0, 0)
        anno_layout.setSpacing(4)

        # ─ 1행: 도형 도구들 ─
        row_shape = QWidget()
        row_shape_layout = QHBoxLayout(row_shape)
        row_shape_layout.setContentsMargins(0, 0, 0, 0)
        row_shape_layout.setSpacing(4)

        lbl_shape = QLabel("도형:")
        row_shape_layout.addWidget(lbl_shape)

        # 사각형 도구
        self.btn_shape_rect = QPushButton("□")
        self.btn_shape_rect.setCheckable(True)
        self.btn_shape_rect.setToolTip("사각형 도형")
        self.btn_shape_rect.setProperty("toolButton", True)
        self.btn_shape_rect.clicked.connect(
            lambda checked: self.on_select_shape_tool(ShapeType.RECT)
        )
        row_shape_layout.addWidget(self.btn_shape_rect)

        # 원형 도구
        self.btn_shape_circle = QPushButton("○")
        self.btn_shape_circle.setCheckable(True)
        self.btn_shape_circle.setToolTip("원형 도형")
        self.btn_shape_circle.setProperty("toolButton", True)
        self.btn_shape_circle.clicked.connect(
            lambda checked: self.on_select_shape_tool(ShapeType.CIRCLE)
        )
        row_shape_layout.addWidget(self.btn_shape_circle)

        # 타원 도구
        self.btn_shape_ellipse = QPushButton("⊙")
        self.btn_shape_ellipse.setCheckable(True)
        self.btn_shape_ellipse.setToolTip("타원 도형")
        self.btn_shape_ellipse.setProperty("toolButton", True)
        self.btn_shape_ellipse.clicked.connect(
            lambda checked: self.on_select_shape_tool(ShapeType.ELLIPSE)
        )
        row_shape_layout.addWidget(self.btn_shape_ellipse)

        # 삼각형 도구
        self.btn_shape_triangle = QPushButton("△")
        self.btn_shape_triangle.setCheckable(True)
        self.btn_shape_triangle.setToolTip("삼각형 도형")
        self.btn_shape_triangle.setProperty("toolButton", True)
        self.btn_shape_triangle.clicked.connect(
            lambda checked: self.on_select_shape_tool(ShapeType.TRIANGLE)
        )
        row_shape_layout.addWidget(self.btn_shape_triangle)

        # 다이아(마름모) 도구 - POLYGON
        self.btn_shape_polygon = QPushButton("◇")
        self.btn_shape_polygon.setCheckable(True)
        self.btn_shape_polygon.setToolTip("마름모 도형")
        self.btn_shape_polygon.setProperty("toolButton", True)
        self.btn_shape_polygon.clicked.connect(
            lambda checked: self.on_select_shape_tool(ShapeType.POLYGON)
        )
        row_shape_layout.addWidget(self.btn_shape_polygon)

        # 별 도형
        self.btn_shape_star = QPushButton("★")
        self.btn_shape_star.setCheckable(True)
        self.btn_shape_star.setToolTip("별 도형")
        self.btn_shape_star.setProperty("toolButton", True)
        self.btn_shape_star.clicked.connect(
            lambda checked: self.on_select_shape_tool(ShapeType.STAR)
        )
        row_shape_layout.addWidget(self.btn_shape_star)

        # 기준면 L 도형
        self.btn_shape_datumL = QPushButton("L")
        self.btn_shape_datumL.setCheckable(True)
        self.btn_shape_datumL.setToolTip("기준면 표시용 L 도형")
        self.btn_shape_datumL.setProperty("toolButton", True)
        self.btn_shape_datumL.clicked.connect(
            lambda checked: self.on_select_shape_tool(ShapeType.DATUM_L)
        )
        row_shape_layout.addWidget(self.btn_shape_datumL)

        row_shape_layout.addStretch(1)
        anno_layout.addWidget(row_shape)

        # ─ 2행: 화살표 / 텍스트 도구 ─
        row_tools = QWidget()
        row_tools_layout = QHBoxLayout(row_tools)
        row_tools_layout.setContentsMargins(0, 0, 0, 0)
        row_tools_layout.setSpacing(4)

        lbl_arrow = QLabel("화살표:")
        row_tools_layout.addWidget(lbl_arrow)

        self.btn_tool_arrow = QPushButton("→")
        self.btn_tool_arrow.setCheckable(True)
        self.btn_tool_arrow.setToolTip("화살표 도구")
        self.btn_tool_arrow.setProperty("toolButton", True)
        self.btn_tool_arrow.clicked.connect(self.on_select_arrow_tool)
        row_tools_layout.addWidget(self.btn_tool_arrow)

        lbl_text_tool = QLabel("텍스트:")
        row_tools_layout.addWidget(lbl_text_tool)

        self.btn_tool_text = QPushButton("T")
        self.btn_tool_text.setCheckable(True)
        self.btn_tool_text.setToolTip("텍스트 도구")
        self.btn_tool_text.setProperty("toolButton", True)
        self.btn_tool_text.clicked.connect(self.on_select_text_tool)
        row_tools_layout.addWidget(self.btn_tool_text)

        row_tools_layout.addStretch(1)
        anno_layout.addWidget(row_tools)

        # ─ 3행: 두께 + 색상 설정 ─
        row_style = QWidget()
        row_style_layout = QHBoxLayout(row_style)
        row_style_layout.setContentsMargins(0, 0, 0, 0)
        row_style_layout.setSpacing(4)

        # 선 두께
        lbl_width = QLabel("두께:")
        row_style_layout.addWidget(lbl_width)

        self.spin_stroke_width = QDoubleSpinBox()
        self.spin_stroke_width.setRange(0.5, 15.0)
        self.spin_stroke_width.setSingleStep(0.5)

        # ✅ ToolState 값으로 UI 초기화 (하드코딩 금지)
        self.spin_stroke_width.blockSignals(True)
        self.spin_stroke_width.setValue(float(self.tool_state.stroke_width))
        self.spin_stroke_width.blockSignals(False)

        self.spin_stroke_width.setToolTip("도형 및 화살표의 선 두께")
        self.spin_stroke_width.valueChanged.connect(self.on_stroke_width_changed)
        row_style_layout.addWidget(self.spin_stroke_width)



        # 도형 선색
        lbl_shape_color = QLabel("도형선:")
        row_style_layout.addWidget(lbl_shape_color)
        self.combo_shape_stroke_color = create_color_combo(self.tool_state.stroke_color)
        self.combo_shape_stroke_color.currentTextChanged.connect(
            self.on_shape_stroke_color_changed
        )
        self.combo_shape_stroke_color.activated.connect(
            lambda *_: self.on_shape_stroke_color_changed(self.combo_shape_stroke_color.currentText())
        )

        row_style_layout.addWidget(self.combo_shape_stroke_color)

        # 도형 채움색 (없음 + 기본 색상) - 아이콘 포함
        lbl_fill_color = QLabel("채움:")
        row_style_layout.addWidget(lbl_fill_color)

        self.combo_shape_fill_color = QComboBox()
        self.combo_shape_fill_color.setIconSize(QSize(14, 14))

        # '없음' 은 투명 아이콘으로 표시
        none_pix = QPixmap(14, 14)
        none_pix.fill(Qt.transparent)
        self.combo_shape_fill_color.addItem(QIcon(none_pix), "없음")

        # 나머지 색상들은 COLOR_CHOICES 기준으로 색 네모 아이콘 생성
        for c in COLOR_CHOICES:
            pix = QPixmap(14, 14)
            pix.fill(QColor(c))
            self.combo_shape_fill_color.addItem(QIcon(pix), c)

        # 기본값: 채움 없음
        self.combo_shape_fill_color.setCurrentIndex(0)
        self.combo_shape_fill_color.setMaximumWidth(80)
        self.combo_shape_fill_color.currentTextChanged.connect(
            self.on_shape_fill_color_changed
        )
        self.combo_shape_fill_color.activated.connect(
            lambda *_: self.on_shape_fill_color_changed(self.combo_shape_fill_color.currentText())
        )

        row_style_layout.addWidget(self.combo_shape_fill_color)


        # 화살표 색상
        lbl_arrow_color = QLabel("화살표:")
        row_style_layout.addWidget(lbl_arrow_color)
        self.combo_arrow_color = create_color_combo(self.tool_state.arrow_color)
        self.combo_arrow_color.currentTextChanged.connect(
            self.on_arrow_color_changed
        )
        self.combo_arrow_color.activated.connect(
            lambda *_: self.on_arrow_color_changed(self.combo_arrow_color.currentText())
        )

        row_style_layout.addWidget(self.combo_arrow_color)

        # 텍스트 색상
        lbl_text_color = QLabel("텍스트:")
        row_style_layout.addWidget(lbl_text_color)
        self.combo_text_color = create_color_combo(self.tool_state.text_color)
        self.combo_text_color.currentTextChanged.connect(
            self.on_text_color_changed
        )
        self.combo_text_color.activated.connect(
            lambda *_: self.on_text_color_changed(self.combo_text_color.currentText())
        )

        row_style_layout.addWidget(self.combo_text_color)

        # ← 바로 여기 아래에 글자 크기 추가
        lbl_text_size = QLabel("크기:")
        row_style_layout.addWidget(lbl_text_size)

        self.spin_text_size = QSpinBox()
        self.spin_text_size.setRange(6, 72)
        self.spin_text_size.setSingleStep(2)
        self.spin_text_size.setValue(40)
        self.spin_text_size.setToolTip("텍스트 기본 크기 및 선택 텍스트 크기 조절")
        self.spin_text_size.valueChanged.connect(self.on_text_size_changed)
        row_style_layout.addWidget(self.spin_text_size)

        row_style_layout.addStretch(1)
        anno_layout.addWidget(row_style)

        # 우측 상단 도구 영역(도형/화살표/텍스트, 색상 등)
        right_layout.addWidget(anno_tools)

        # ─ 하단: AnnotationScene을 보여주는 이미지 뷰 (한 번만 생성) ─
        self.image_view = ImageView(self.annotation_scene)
        # 너무 큰 최소 사이즈는 지오메트리 경고를 유발하오니 약간 줄이겠사옵니다.
        self.image_view.setMinimumSize(600, 400)
        right_layout.addWidget(self.image_view, 1)

        # ★ Ctrl+V 로 클립보드 이미지 붙여넣기 단축키
        #   - 대상 위젯: self.image_view
        #   - 이미지 뷰에 포커스가 있을 때만 동작
        self.paste_image_shortcut = QShortcut(QKeySequence.Paste, self.image_view)
        self.paste_image_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.paste_image_shortcut.activated.connect(self.paste_image_from_clipboard)

        # ─ 가운데 영역: 왼쪽(좌표/치수) + 오른쪽(이미지/주석) ─
        middle_layout.addWidget(left_group)
        middle_layout.addWidget(right_group, 1)

        # ─ 중앙 전체 레이아웃 ─
        central_layout.addWidget(top_widget)
        central_layout.addWidget(middle_widget, 1)

        status = QStatusBar()
        status.showMessage("준비됨.")
        self.setStatusBar(status)
        self.setCentralWidget(central)

        # 왼쪽 영역 입력 변화 → 계산 연결
        self._connect_left_panel_signals()

        # ROTATE 버튼 스타일 초기화
        self.update_rotate_buttons()

        # 모드 UI 초기화
        self._update_mode_ui()

        # 초기값 세팅
        self.reset_all()

        self._load_ui_settings()



    def on_select_shape_tool(self, shape_type: ShapeType):
        """도형 도구 버튼 선택 시 현재 도형 타입을 갱신하고, 버튼 체크 상태를 정리합니다."""
        self.current_shape_type = shape_type
         # ★ ToolState에도 반영
        self.tool_state.use_shape_tool(shape_type)

        # 버튼 체크 상태 정리
        btn_map = {
            ShapeType.RECT: self.btn_shape_rect,
            ShapeType.CIRCLE: self.btn_shape_circle,
            ShapeType.ELLIPSE: self.btn_shape_ellipse,
            ShapeType.TRIANGLE: self.btn_shape_triangle,
            ShapeType.POLYGON: self.btn_shape_polygon,
            ShapeType.STAR: self.btn_shape_star,
            ShapeType.DATUM_L: self.btn_shape_datumL,
        }
        for st, btn in btn_map.items():
            btn.setChecked(st == shape_type)

        # 화살표/텍스트 도구 버튼은 해제
        if hasattr(self, "btn_tool_arrow"):
            self.btn_tool_arrow.setChecked(False)
        if hasattr(self, "btn_tool_text"):
            self.btn_tool_text.setChecked(False)

    def on_select_arrow_tool(self):
        """화살표 도구 버튼 선택 시 ToolState를 ARROW로 전환하고 버튼 상태를 정리합니다."""
        # 도구 상태 변경
        self.tool_state.use_arrow_tool()

        # 버튼 체크 상태: 화살표만 체크
        if hasattr(self, "btn_tool_arrow"):
            self.btn_tool_arrow.setChecked(True)
        if hasattr(self, "btn_tool_text"):
            self.btn_tool_text.setChecked(False)

        # 도형 버튼들은 모두 해제
        for btn in [
            getattr(self, "btn_shape_rect", None),
            getattr(self, "btn_shape_circle", None),
            getattr(self, "btn_shape_ellipse", None),
            getattr(self, "btn_shape_triangle", None),
            getattr(self, "btn_shape_polygon", None),
            getattr(self, "btn_shape_star", None),
            getattr(self, "btn_shape_datumL", None),
        ]:
            if btn is not None:
                btn.setChecked(False)

    def on_select_text_tool(self):
        """텍스트 도구 버튼 선택 시 ToolState를 TEXT로 전환하고 버튼 상태를 정리합니다."""
        # 도구 상태 변경
        self.tool_state.use_text_tool()

        # 버튼 체크 상태: 텍스트만 체크
        if hasattr(self, "btn_tool_arrow"):
            self.btn_tool_arrow.setChecked(False)
        if hasattr(self, "btn_tool_text"):
            self.btn_tool_text.setChecked(True)

        # 도형 버튼들은 모두 해제
        for btn in [
            getattr(self, "btn_shape_rect", None),
            getattr(self, "btn_shape_circle", None),
            getattr(self, "btn_shape_ellipse", None),
            getattr(self, "btn_shape_triangle", None),
            getattr(self, "btn_shape_polygon", None),
            getattr(self, "btn_shape_star", None),
            getattr(self, "btn_shape_datumL", None),
        ]:
            if btn is not None:
                btn.setChecked(False)

    def on_shape_stroke_color_changed(self, name: str):
        """도형 선색 콤보 변경 시 ToolState와 선택된 도형의 선색을 갱신합니다."""
        self.tool_state.stroke_color = name
        if self.annotation_scene is not None:
            self.annotation_scene.update_selected_shape_stroke_color(name)

    def on_shape_fill_color_changed(self, name: str):
        """도형 채움색 콤보 변경 시 ToolState와 선택된 도형의 채움색을 갱신합니다."""
        text = (name or "").strip()
        fill = None if text == "없음" else text
        self.tool_state.fill_color = fill
        if self.annotation_scene is not None:
            self.annotation_scene.update_selected_shape_fill_color(fill)

    def on_arrow_color_changed(self, name: str):
        """화살표 색 콤보 변경 시 ToolState와 선택된 화살표 색을 갱신합니다."""
        self.tool_state.arrow_color = name
        if self.annotation_scene is not None:
            self.annotation_scene.update_selected_arrow_color(name)

    def on_text_color_changed(self, name: str):
        """텍스트 색 콤보 변경 시 ToolState와 선택된 텍스트 색을 갱신합니다."""
        self.tool_state.text_color = name
        if self.annotation_scene is not None:
            self.annotation_scene.update_selected_text_color(name)

    def on_stroke_width_changed(self, value: float):
        """
        선 두께 변경 시:
        - 새로 그릴 도형 기준 두께(ToolState)
        - 선택된 도형/화살표 즉시 반영
        """
        width = float(value)

        # 내부 로직: 공백 8칸
        self.tool_state.stroke_width = width

        if self.annotation_scene is not None:
            self.annotation_scene.update_selected_stroke_width(width)

    def on_text_size_changed(self, value: int):
        """
        텍스트 크기 스핀박스 변경 시
        - ToolState.text_size (새로 그릴 텍스트/화살표의 기본 크기)
        - 선택된 텍스트/화살표 주석의 크기
        를 갱신합니다.
        """
        size = float(value)
        self.tool_state.text_size = size

        if hasattr(self, "annotation_scene") and self.annotation_scene is not None:
            self.annotation_scene.update_selected_text_font_size(size)


    def on_delete_selected_annotations(self):
        """선택된 주석(도형/텍스트/화살표)을 삭제합니다."""
        if self.annotation_scene is not None:
            self.annotation_scene.delete_selected_annotations()


    # ───────── 메뉴바 생성 ─────────
    def _create_menu_bar(self):
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        file_menu = QMenu("파일", self)
        menu_bar.addMenu(file_menu)

        act_new = file_menu.addAction("새로 만들기 / 초기화")
        act_save = file_menu.addAction("저장")
        act_load = file_menu.addAction("불러오기")
        file_menu.addSeparator()
        act_exit = file_menu.addAction("종료")

        act_new.triggered.connect(self.reset_all)
        act_save.triggered.connect(self.save_project)
        act_load.triggered.connect(self.load_project)
        act_exit.triggered.connect(self.close)

        settings_menu = QMenu("설정", self)
        menu_bar.addMenu(settings_menu)

        act_settings = settings_menu.addAction("설비 / 작업자 설정...")
        act_settings.triggered.connect(self.open_settings_dialog)

                # ─ 보기/테스트 메뉴 ─
        view_menu = QMenu("보기", self)
        menu_bar.addMenu(view_menu)

        act_demo_anno = view_menu.addAction("테스트 주석 추가")
        act_demo_anno.setToolTip("현재 이미지 위에 테스트용 텍스트/화살표/사각형 주석을 표시합니다.")
        act_demo_anno.triggered.connect(self.add_demo_annotations)

    def get_current_machine(self) -> str:
        """
        현재 설비명을 반환합니다.

        우선순위:
        1) 통합 쉘(app_shell)에서 주입한 값(_shell_machine)
        2) (레거시) combo_machine이 있는 경우 combo_machine 값
        """
        v = (getattr(self, "_shell_machine", "") or "").strip()
        if v:
            return v

        if hasattr(self, "combo_machine") and self.combo_machine is not None:
            return (self.combo_machine.currentText() or "").strip()

        return ""

    def set_shell_machine(self, machine_name: str):
        """
        통합 쉘에서 선택한 설비명을 SettingMainWindow에 주입합니다.
        """
        self._shell_machine = (machine_name or "").strip()

    def set_shell_rotate(self, rotate_on: bool):
        """
        통합 쉘에서 ROTATE ON/OFF 상태를 SettingMainWindow에 주입합니다.
        """
        self._shell_rotate_on = bool(rotate_on)

    # 설비 콤보 채우기
    def _populate_machine_combo(self, current=None):
        # ✅ 쉘에서 설비 콤보를 관리하는 경우(Setting 내부 combo_machine 제거) 크래시 방지
        if not hasattr(self, "combo_machine") or self.combo_machine is None:
            return

        self.combo_machine.clear()
        if not self.machine_list:
            return
        self.combo_machine.addItems(self.machine_list)
        if current and current in self.machine_list:
            idx = self.combo_machine.findText(current)
            if idx >= 0:
                self.combo_machine.setCurrentIndex(idx)
        else:
            self.combo_machine.setCurrentIndex(0)


    # 현재 설비 기준 작업자 상태 표시
    def _update_operator_status(self):
        if not self.statusBar():
            return
        if not hasattr(self, "combo_machine") or self.combo_machine is None:
            return
        ...

        current_machine = self.combo_machine.currentText()
        current_op = get_operator_for_machine(current_machine, self.operator_map)
        msg = f"설비 {len(self.machine_list)}개, 현재 설비: {current_machine or '미지정'} / 작업자: {current_op or '미지정'}"
        self.statusBar().showMessage(msg)

    # 설정창 호출 (전역 설정 저장)
    def open_settings_dialog(self):
        if not hasattr(self, "combo_machine") or self.combo_machine is None:
            QMessageBox.information(self, "설정", "통합 쉘에서 설비 선택을 관리하므로, 이 화면에서는 설비 콤보가 없습니다.")
            return
        current = self.combo_machine.currentText()
        dlg = SettingsDialog(
            self,
            machine_list=self.machine_list,
            operator_map=self.operator_map,
        )
        if dlg.exec() == QDialog.Accepted:
            new_list, new_map = dlg.get_values()
            self.machine_list = new_list or []
            self.operator_map = new_map or {}
            self._populate_machine_combo(current)
            save_global_settings(self.machine_list, self.operator_map)
            self._update_operator_status()

    # ROTATE 버튼 스타일

    def update_rotate_buttons(self):
        """
        ROTATE 버튼 스타일(레거시: ON/OFF 2버튼)을 갱신합니다.

        통합 쉘(app_shell)에서는 ROTATE가 상단바(1버튼 토글)로 이동하였으므로,
        SettingMainWindow 내부의 ON/OFF 버튼이 제거된 경우가 있습니다.
        이때는 아무것도 하지 않고 종료하여 크래시를 방지합니다.
        """
        if not hasattr(self, "btn_rotate_on") or not hasattr(self, "btn_rotate_off"):
            return

        if self.btn_rotate_on.isChecked():
            self.btn_rotate_on.setStyleSheet(
                "font-weight: bold; background-color: lightgray;"
            )
            self.btn_rotate_off.setStyleSheet("font-weight: bold;")
        elif self.btn_rotate_off.isChecked():
            self.btn_rotate_off.setStyleSheet(
                "font-weight: bold; background-color: lightgray;"
            )
            self.btn_rotate_on.setStyleSheet("font-weight: bold;")
        else:
            self.btn_rotate_off.setChecked(True)
            self.update_rotate_buttons()

    def on_rotate_on_clicked(self):
        if not self.btn_rotate_on.isChecked():
            self.btn_rotate_on.setChecked(True)
        self.btn_rotate_off.setChecked(False)
        self.update_rotate_buttons()

    def on_rotate_off_clicked(self):
        if not self.btn_rotate_off.isChecked():
            self.btn_rotate_off.setChecked(True)
        self.btn_rotate_on.setChecked(False)
        self.update_rotate_buttons()

    def on_export_pdf(self):
        """
        상단 'PDF 생성' 버튼 클릭 시 호출되는 슬롯.
        현재 화면 상태를 기반으로 PrintEngine을 통해 PDF를 생성.
        """
        if hasattr(self, "print_engine") and self.print_engine is not None:
            layout_choice = "세로"
            if hasattr(self, "combo_pdf_layout"):
                layout_choice = self.combo_pdf_layout.currentText().strip() or "세로"

            self.print_engine.export_to_pdf(layout_choice)




    # MODE 버튼 처리
    def on_mode_center(self):
        self.mode_center = True
        self.btn_mode_center.setChecked(True)
        self.btn_mode_onepoint.setChecked(False)
        self._update_mode_ui()
        self._update_outer_info()
        self._update_z_info()
        # setting_sheet_auto/main.py
        # (MODE 버튼 생성 직후에 추가)
        
        self.btn_mode_center.setObjectName("ModePill")
        self.btn_mode_center.setProperty("mode", "center")
        
        self.btn_mode_onepoint.setObjectName("ModePill")
        self.btn_mode_onepoint.setProperty("mode", "onepoint")

    def on_mode_onepoint(self):
        self.mode_center = False
        self.btn_mode_center.setChecked(False)
        self.btn_mode_onepoint.setChecked(True)
        self._update_mode_ui()
        self._update_outer_info()
        self._update_z_info()

    def _update_mode_ui(self):
        """
        CENTER 모드 / ONE-POINT 모드에 따라
        좌측 상단 그룹의 제목과 라벨, 필드 표시를 변경
        """
        if self.mode_center:
            # CENTER 모드
            self.operator_group.setTitle("오퍼레이터 기준 좌표 (양센터)")
            self.lbl_center1.setText("X 센터 (mm):")
            self.lbl_center2.setText("Y 센터 (mm):")
            self.lbl_center2.setVisible(True)
            self.edit_y_center.setVisible(True)
        else:
            # ONE-POINT 모드 (★ X표시부 / Y표시부로 분리)
            self.operator_group.setTitle("표시부 (X / Y)")
            self.lbl_center1.setText("X 표시부 (mm):")
            self.lbl_center2.setText("Y 표시부 (mm):")

            # ★ Y도 사용하므로 숨기지 않음
            self.lbl_center2.setVisible(True)
            self.edit_y_center.setVisible(True)


    # ───────── 왼쪽 패널 입력 변화 연결 ─────────
    def _connect_left_panel_signals(self):
        # 외곽 → 센터 or 길이
        self.edit_x_minus.editingFinished.connect(self._update_outer_info)
        self.edit_x_plus.editingFinished.connect(self._update_outer_info)
        self.edit_y_minus.editingFinished.connect(self._update_outer_info)
        self.edit_y_plus.editingFinished.connect(self._update_outer_info)

        # 센터 → 외곽 (CENTER 모드에서만 유효)
        self.edit_x_center.editingFinished.connect(self._update_center_info)
        self.edit_y_center.editingFinished.connect(self._update_center_info)

        # Z 계산
        self.edit_z_bottom.editingFinished.connect(self._update_z_info)
        self.edit_z_top.editingFinished.connect(self._update_z_info)

    # ───────── 레이아웃 비우기 ─────────
    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # ───────── 초기화 ─────────
    def reset_all(self):
        """
        새로 만들기 / 초기화

        - 프로젝트 내용(입력값/추가항목/특이사항) 초기화
        - 이미지/주석(Annotation) 완전 초기화
        - 도구 설정(ToolState: 두께/색/크기 등)은 유지
        - 초기화 후 UI는 현재 ToolState 값으로 다시 동기화
        """

        # ───────── 기본 입력 초기화 ─────────
        self.edit_project.clear()
        # ✅ combo_machine이 존재할 때만 콤보 초기화
        if hasattr(self, "combo_machine") and self.combo_machine is not None:
            self._populate_machine_combo()


        # ROTATE 버튼(레거시 ON/OFF)이 존재하는 경우에만 초기화
        if hasattr(self, "btn_rotate_off") and hasattr(self, "btn_rotate_on"):
            self.btn_rotate_off.setChecked(True)
            self.btn_rotate_on.setChecked(False)
            self.update_rotate_buttons()


        # 기본 모드는 CENTER
        self.mode_center = True
        self.btn_mode_center.setChecked(True)
        self.btn_mode_onepoint.setChecked(False)
        self._update_mode_ui()

        # 좌표/치수 입력값 초기화
        self.edit_x_center.setText("0.000")
        self.edit_y_center.setText("0.000")

        self.edit_x_minus.setText("0.000")
        self.edit_x_plus.setText("0.000")
        self.edit_y_minus.setText("0.000")
        self.edit_y_plus.setText("0.000")
        self.lbl_x_info.setText("")
        self.lbl_y_info.setText("")

        self.edit_z_bottom.setText("0.000")
        self.edit_z_top.setText("0.000")
        self.lbl_z_height.setText("")

        # 동적 추가 항목 초기화
        self._clear_layout(self.coord_extra_layout)
        self._clear_layout(self.outer_extra_layout)
        self._clear_layout(self.z_extra_layout)

        # 특이사항 초기화
        self.notes_edit.clear()

        # 계산 반영
        self._update_outer_info()
        self._update_z_info()

        # 상태바 갱신
        self._update_operator_status()

        # ───────── Annotation / 이미지 완전 초기화 ─────────
        self.annotation_set = AnnotationSet()
        self.annotation_scene.set_annotation_set(self.annotation_set)

        # ★ 핵심: 컨트롤러에도 새 AnnotationSet 연결
        self.annotation_controller.annotation_set = self.annotation_set
        
        # Scene 클리어
        self.annotation_scene.clear()
        self.annotation_scene._pixmap_item = None

        # ───────── ToolState는 유지 (여기서 색/두께/크기 덮어쓰지 않음) ─────────

        # ───────── UI 동기화: ToolState → UI ─────────
        if hasattr(self, "spin_stroke_width") and self.spin_stroke_width is not None:
            self.spin_stroke_width.blockSignals(True)
            self.spin_stroke_width.setValue(float(self.tool_state.stroke_width))
            self.spin_stroke_width.blockSignals(False)


        if hasattr(self, "spin_text_size") and self.spin_text_size is not None:
            self.spin_text_size.setValue(int(self.tool_state.text_size))

        if hasattr(self, "combo_text_color") and self.combo_text_color is not None:
            self.combo_text_color.setCurrentText(self.tool_state.text_color)

        if hasattr(self, "combo_shape_stroke_color") and self.combo_shape_stroke_color is not None:
            self.combo_shape_stroke_color.setCurrentText(self.tool_state.stroke_color)

        if hasattr(self, "combo_arrow_color") and self.combo_arrow_color is not None:
            self.combo_arrow_color.setCurrentText(self.tool_state.arrow_color)

        if hasattr(self, "combo_shape_fill_color") and self.combo_shape_fill_color is not None:
            if self.tool_state.fill_color:
                self.combo_shape_fill_color.setCurrentText(self.tool_state.fill_color)
            else:
                self.combo_shape_fill_color.setCurrentIndex(0)

        # PDF 레이아웃은 초기화 시 기본값으로
        if hasattr(self, "combo_pdf_layout") and self.combo_pdf_layout is not None:
            self.combo_pdf_layout.setCurrentText("세로")
  
    # ───────── 외곽 → 센터/길이 계산 ─────────
    def _update_outer_info(self):
        # X축
        xm = parse_float(self.edit_x_minus.text())
        xp = parse_float(self.edit_x_plus.text())
        Lx, Cx = calc_outer_to_center(xm, xp)
        if Lx is not None:
            if self.mode_center:
                # CENTER 모드: 길이 + 양센터
                if Cx is not None:
                    self.lbl_x_info.setText(
                        f"Lx = {Lx:.3f} mm, 양센터 = {format_signed(Cx)} mm"
                    )
                    self.edit_x_center.setText(format_signed(Cx))
                else:
                    self.lbl_x_info.setText(f"Lx = {Lx:.3f} mm")
            else:
                # ONE-POINT 모드: 길이만 표시, 센터는 건드리지 않음
                self.lbl_x_info.setText(f"Lx = {Lx:.3f} mm")
        else:
            self.lbl_x_info.setText("")

        # Y축
        ym = parse_float(self.edit_y_minus.text())
        yp = parse_float(self.edit_y_plus.text())
        Ly, Cy = calc_outer_to_center(ym, yp)
        if Ly is not None:
            if self.mode_center:
                if Cy is not None:
                    self.lbl_y_info.setText(
                        f"Ly = {Ly:.3f} mm, 양센터 = {format_signed(Cy)} mm"
                    )
                    self.edit_y_center.setText(format_signed(Cy))
                else:
                    self.lbl_y_info.setText(f"Ly = {Ly:.3f} mm")
            else:
                self.lbl_y_info.setText(f"Ly = {Ly:.3f} mm")
        else:
            self.lbl_y_info.setText("")

    # ───────── 센터 → 외곽 역산 (CENTER 모드에서만) ─────────
    def _update_center_info(self):
        if not self.mode_center:
            # ONE-POINT 모드에서는 센터 개념이 없으므로 계산 금지
            return

        # X축
        cx = parse_float(self.edit_x_center.text())
        xm = parse_float(self.edit_x_minus.text())
        xp = parse_float(self.edit_x_plus.text())
        Lx, _ = calc_outer_to_center(xm, xp)
        if cx is not None and Lx is not None:
            xm_new, xp_new = calc_center_to_outer(cx, Lx)
            if xm_new is not None and xp_new is not None:
                self.edit_x_minus.setText(format_signed(xm_new))
                self.edit_x_plus.setText(format_signed(xp_new))

        # Y축
        cy = parse_float(self.edit_y_center.text())
        ym = parse_float(self.edit_y_minus.text())
        yp = parse_float(self.edit_y_plus.text())
        Ly, _ = calc_outer_to_center(ym, yp)
        if cy is not None and Ly is not None:
            ym_new, yp_new = calc_center_to_outer(cy, Ly)
            if ym_new is not None and yp_new is not None:
                self.edit_y_minus.setText(format_signed(ym_new))
                self.edit_y_plus.setText(format_signed(yp_new))

        # 바뀐 외곽 기준으로 다시 라벨/센터 정합 체크
        self._update_outer_info()

    # ───────── Z 계산 ─────────
    def _update_z_info(self):
        zb = parse_float(self.edit_z_bottom.text())
        zt = parse_float(self.edit_z_top.text())
        zh = calc_z_height(zb, zt)
        if zh is not None:
            self.lbl_z_height.setText(f"Z 높이 = {zh:.3f} mm")
        else:
            self.lbl_z_height.setText("")

    def _auto_grow_window_height(self, add_px: int = 48):
        """
        동적 행(추가 좌표/치수) 추가 시, 최상위 창 높이를 자동으로 늘립니다.
        - 가로는 절대 줄이지 않습니다(폭 축소 방지).
        - 스크롤 없이 “예전처럼 창이 늘어나는” 동작을 재현합니다.
        """
        top = self.window()
        if top is None:
            return

        # ✅ 현재 폭을 먼저 고정(최소 폭 이하로 내려가지 않게)
        keep_w = top.width()
        if keep_w < 1600:
            keep_w = 1600

        # ✅ adjustSize() 호출 금지: sizeHint 재계산으로 폭이 줄어드는 원인
        new_h = top.height() + int(add_px)

        # ✅ 폭은 유지, 높이만 증가
        top.resize(keep_w, new_h)


    # ───────── 추가 좌표 ─────────
    def add_coord_point(self):
        title, ok = QInputDialog.getText(
            self, "추가 좌표 이름",
            "좌표 이름 또는 설명을 입력하십시오:"
        )
        if not ok or not title.strip():
            return

        value, ok = QInputDialog.getText(
            self, "추가 좌표 값",
            "좌표 값 또는 표시 텍스트를 입력하십시오:"
        )
        if not ok or not value.strip():
            return

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        # (1) 라벨: (mm) 명시 + 굵게
        lbl = QLabel(f"{title.strip()} (mm):")
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        lbl.setMinimumWidth(120)

        # (2) 값 입력: 오른쪽 정렬 + 고정폭 + 숫자 가독성
        edit = QLineEdit(value.strip())
        edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        edit.setMaximumWidth(120)
        apply_mono_font_safe(edit)
        row_layout.addWidget(lbl)
        row_layout.addWidget(edit)
        row_layout.addStretch(1)

        self.coord_extra_layout.addWidget(row)
        self._auto_grow_window_height(70)


    # ───────── 외곽 추가 치수 ─────────

    def add_outer_dimension(self):
        title, ok = QInputDialog.getText(
            self, "외곽 추가 치수 제목",
            "치수 제목을 입력하십시오 (예: 클램프 여유, 좌측 여유 등):"
        )
        if not ok or not title.strip():
            return

        value, ok = QInputDialog.getText(
            self, "외곽 추가 치수 값",
            "치수 값을 입력하십시오 (mm):"
        )
        if not ok or not value.strip():
            return

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        lbl = QLabel(f"{title.strip()} (mm):")
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        lbl.setMinimumWidth(120)

        edit = QLineEdit(value.strip())
        edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        edit.setMaximumWidth(120)
        apply_mono_font_safe(edit)
        row_layout.addWidget(lbl)
        row_layout.addWidget(edit)
        row_layout.addStretch(1)

        self.outer_extra_layout.addWidget(row)
        self._auto_grow_window_height(70)

    # ───────── Z 추가 치수 ─────────

    def add_z_dimension(self):
        title, ok = QInputDialog.getText(
            self, "Z 추가 치수 제목",
            "치수 제목을 입력하십시오 (예: 상판 여유, 하부 베이스 두께 등):"
        )
        if not ok or not title.strip():
            return

        value, ok = QInputDialog.getText(
            self, "Z 추가 치수 값",
            "치수 값을 입력하십시오 (mm):"
        )
        if not ok or not value.strip():
            return

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        lbl = QLabel(f"{title.strip()} (mm):")
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        lbl.setMinimumWidth(120)

        edit = QLineEdit(value.strip())
        edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        edit.setMaximumWidth(120)
        apply_mono_font_safe(edit)
        row_layout.addWidget(lbl)
        row_layout.addWidget(edit)
        row_layout.addStretch(1)

        self.z_extra_layout.addWidget(row)
        self._auto_grow_window_height(70)

    # ───────── 이미지 파일 불러오기 ─────────
    def load_image_file(self):
        from PySide6.QtCore import QSettings

        settings = QSettings("GH", "SettingSheet")
        last_dir = settings.value("last_image_dir", "")

        path, _ = QFileDialog.getOpenFileName(
            self,
            "이미지 불러오기",
            filter="이미지 파일 (*.png *.jpg *.jpeg *.bmp *.gif);;모든 파일 (*.*)"
        )
        if not path:
            return
        # ★ 마지막 폴더 저장
        try:
            settings.setValue("last_image_dir", str(Path(path).parent))
        except Exception:
            pass

        # ① 파일에서 이미지 로드
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "오류", "이미지를 불러올 수 없음.")
            return

        # ② AnnotationScene 쪽에 이미지 설정
        self.annotation_scene.set_image(pix)

        # ③ 현재 Scene 전체가 프레임에 맞게 보이도록 조정
        self.image_view.fitInView(self.annotation_scene.sceneRect(), Qt.KeepAspectRatio)

        # ④ 상태바 메시지
        if self.statusBar():
            self.statusBar().showMessage(f"이미지 로드: {path}")

    def paste_image_from_clipboard(self):
        """
        클립보드에 있는 이미지를 가져와서
        현재 AnnotationScene의 배경 이미지로 설정하는 함수
        (Ctrl+V 단축키에서 호출)
        """
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return

        # QClipboard.image() 는 QImage를 돌려주옵니다.
        image = clipboard.image()
        if image.isNull():
            QMessageBox.information(
                self,
                "붙여넣기",
                "클립보드에 이미지가 존재하지 않음."
            )
            return

        pix = QPixmap.fromImage(image)
        if pix.isNull():
            QMessageBox.warning(
                self,
                "오류",
                "클립보드의 이미지를 불러오기 실패."
            )
            return

        # AnnotationScene 쪽에 이미지 설정
        self.annotation_scene.set_image(pix)

        # A4 프레임에 맞게 보기 조정
        self.image_view.fitInView(self.annotation_scene.sceneRect(), Qt.KeepAspectRatio)

        # 상태바 메시지
        if self.statusBar():
            self.statusBar().showMessage("클립보드에서 이미지 삽입 완료.")

    

    # ───────── 상태 수집 (저장용) ─────────
    def _collect_state(self):
        data = {
            "project": self.edit_project.text(),
            "current_machine": (self.get_current_machine() or ""),
            "rotate": "ON" if (hasattr(self, "btn_rotate_on") and self.btn_rotate_on.isChecked()) else "OFF",
            "mode": "CENTER" if self.mode_center else "ONEPOINT",
            "x_center": self.edit_x_center.text(),
            "y_center": self.edit_y_center.text(),
            "x_center_color": self.combo_x_center_color.currentText(),
            "y_center_color": self.combo_y_center_color.currentText(),
            "x_minus": self.edit_x_minus.text(),
            "x_plus": self.edit_x_plus.text(),
            "y_minus": self.edit_y_minus.text(),
            "y_plus": self.edit_y_plus.text(),
            "x_info": self.lbl_x_info.text(),
            "y_info": self.lbl_y_info.text(),
            "z_bottom": self.edit_z_bottom.text(),
            "z_top": self.edit_z_top.text(),
            "z_height": self.lbl_z_height.text(),
            "notes": self.notes_edit.toPlainText(),
            "coord_extra": [],
            "outer_extra": [],
            "z_extra": [],
        }

        # 추가 좌표
        for i in range(self.coord_extra_layout.count()):
            item = self.coord_extra_layout.itemAt(i)
            row = item.widget()
            if not row:
                continue
            row_layout = row.layout()
            if not row_layout or row_layout.count() < 2:
                continue

            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text()
                if title.endswith(" (mm):"):
                    title = title[:-6]
                data["coord_extra"].append({
                    "title": title,
                    "value": edit.text(),
                })

        # 외곽 추가 치수
        for i in range(self.outer_extra_layout.count()):
            item = self.outer_extra_layout.itemAt(i)
            row = item.widget()
            if not row:
                continue
            row_layout = row.layout()
            if not row_layout or row_layout.count() < 2:
                continue

            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text()
                if title.endswith(" (mm):"):
                    title = title[:-6]
                data["outer_extra"].append({
                    "title": title,
                    "value": edit.text(),
                })

        # Z 추가 치수
        for i in range(self.z_extra_layout.count()):
            item = self.z_extra_layout.itemAt(i)
            row = item.widget()
            if not row:
                continue
            row_layout = row.layout()
            if not row_layout or row_layout.count() < 2:
                continue

            lbl = row_layout.itemAt(0).widget()
            edit = row_layout.itemAt(1).widget()
            if isinstance(lbl, QLabel) and isinstance(edit, QLineEdit):
                title = lbl.text()
                if title.endswith(" (mm):"):
                    title = title[:-6]
                data["z_extra"].append({
                    "title": title,
                    "value": edit.text(),
                })


        return data

    # ───────── 상태 적용 (불러오기용) ─────────
    def _apply_state(self, data: dict):
        self.edit_project.setText(data.get("project", ""))

        current_machine = data.get("current_machine", "")
        self._populate_machine_combo(current_machine)

        rotate = data.get("rotate", "OFF")

        # 레거시 ON/OFF 버튼이 존재할 때만 반영(통합 쉘에서는 상단바에서 관리)
        if hasattr(self, "btn_rotate_on") and hasattr(self, "btn_rotate_off"):
            if rotate == "ON":
                self.btn_rotate_on.setChecked(True)
                self.btn_rotate_off.setChecked(False)
            else:
                self.btn_rotate_off.setChecked(True)
                self.btn_rotate_on.setChecked(False)
            self.update_rotate_buttons()


        mode_str = data.get("mode", "CENTER")
        if mode_str.upper().startswith("ONE"):
            self.mode_center = False
            self.btn_mode_center.setChecked(False)
            self.btn_mode_onepoint.setChecked(True)
        else:
            self.mode_center = True
            self.btn_mode_center.setChecked(True)
            self.btn_mode_onepoint.setChecked(False)
        self._update_mode_ui()

        self.edit_x_center.setText(data.get("x_center", "0.000"))
        self.edit_y_center.setText(data.get("y_center", "0.000"))
        self.combo_x_center_color.setCurrentText(
            data.get("x_center_color", "Red")
        )
        self.combo_y_center_color.setCurrentText(
            data.get("y_center_color", "Blue")
        )

        self.edit_x_minus.setText(data.get("x_minus", "0.000"))
        self.edit_x_plus.setText(data.get("x_plus", "0.000"))
        self.edit_y_minus.setText(data.get("y_minus", "0.000"))
        self.edit_y_plus.setText(data.get("y_plus", "0.000"))

        self.lbl_x_info.setText(data.get("x_info", ""))
        self.lbl_y_info.setText(data.get("y_info", ""))

        self.edit_z_bottom.setText(data.get("z_bottom", "0.000"))
        self.edit_z_top.setText(data.get("z_top", "0.000"))
        self.lbl_z_height.setText(data.get("z_height", ""))

        self.notes_edit.setPlainText(data.get("notes", ""))

        self._clear_layout(self.coord_extra_layout)
        self._clear_layout(self.outer_extra_layout)
        self._clear_layout(self.z_extra_layout)

        # coord_extra 복원
        for item in data.get("coord_extra", []):
            title = (item.get("title", "") or "").strip()
            value = (item.get("value", "") or "").strip()

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            lbl = QLabel(f"{title} (mm):")
            f = lbl.font()
            f.setBold(True)
            lbl.setFont(f)
            lbl.setMinimumWidth(120)

            edit = QLineEdit(value)
            edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            edit.setMaximumWidth(120)

            apply_mono_font_safe(edit)

            row_layout.addWidget(lbl)
            row_layout.addWidget(edit)
            row_layout.addStretch(1)

            self.coord_extra_layout.addWidget(row)

        # outer_extra 복원
        for item in data.get("outer_extra", []):
            title = (item.get("title", "") or "").strip()
            value = (item.get("value", "") or "").strip()

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            lbl = QLabel(f"{title} (mm):")
            f = lbl.font()
            f.setBold(True)
            lbl.setFont(f)
            lbl.setMinimumWidth(120)

            edit = QLineEdit(value)
            edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            edit.setMaximumWidth(120)
            apply_mono_font_safe(edit)
            row_layout.addWidget(lbl)
            row_layout.addWidget(edit)
            row_layout.addStretch(1)

            self.outer_extra_layout.addWidget(row)


        # z_extra 복원
        for item in data.get("z_extra", []):
            title = (item.get("title", "") or "").strip()
            value = (item.get("value", "") or "").strip()

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            lbl = QLabel(f"{title} (mm):")
            f = lbl.font()
            f.setBold(True)
            lbl.setFont(f)
            lbl.setMinimumWidth(120)

            edit = QLineEdit(value)
            edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            edit.setMaximumWidth(120)

            apply_mono_font_safe(edit)

            row_layout.addWidget(lbl)
            row_layout.addWidget(edit)
            row_layout.addStretch(1)

            self.z_extra_layout.addWidget(row)


        # 불러온 값으로 다시 계산 정합 + 작업자 상태 갱신
        self._update_outer_info()
        self._update_z_info()
        self._update_operator_status()

    def add_demo_annotations(self):
        """테스트용 주석을 한 번에 추가하는 임시 함수이옵니다."""
        # 중앙 텍스트
        t = self.annotation_set.add_text(
            position=Point2D(0.5, 0.5),   # 정규화 좌표 (가로 50%, 세로 50%)
            text="CENTER POINT",
            color="Yellow",
            font_size=14,
        )
        t.z_index = 10

        # 좌상단 → 우하단 화살표
        a = self.annotation_set.add_arrow(
            start=Point2D(0.1, 0.1),
            end=Point2D(0.8, 0.8),
            text="가공 방향",
            color="Red",
            line_width=2.0,
        )
        a.z_index = 5

        # 우상단 사각형
        self.annotation_set.add_shape(
            shape_type=ShapeType.RECT,
            points=[Point2D(0.6, 0.1), Point2D(0.9, 0.3)],
            stroke_color="Cyan",
            fill_color="Blue",
            stroke_width=1.5,
        )

        # Scene에 반영
        self.annotation_scene.set_annotation_set(self.annotation_set)


    # ───────── 저장 ─────────
    def save_project(self):
        project = self.edit_project.text().strip()
        machine = (self.get_current_machine() or "").strip()

        if not project:
            QMessageBox.warning(self, "경고", "프로젝트명을 입력해야 합니다.")
            return

        default_name = generate_default_filename(project, machine)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "세팅 시트 저장",
            default_name,
            "JSON 파일 (*.json)"
        )
        if not path:
            return

        data = self._collect_state()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if self.statusBar():
                self.statusBar().showMessage(f"저장 완료: {path}")
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"저장 중 오류 발생:\n{e}")

    # ───────── 불러오기 ─────────
    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "세팅 시트 불러오기",
            filter="JSON 파일 (*.json);;모든 파일 (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_state(data)
            if self.statusBar():
                self.statusBar().showMessage(f"불러오기 완료: {path}")
        except Exception as e:
            QMessageBox.critical(self, "불러오기 오류", f"불러오기 중 오류 발생:\n{e}")

    def closeEvent(self, event):
        """
        프로그램 종료 시 UI 상태 저장
        """
        self._save_ui_settings()
        super().closeEvent(event)

    def _save_ui_settings(self):
        settings = QSettings("GH", "SettingSheet")

        settings.setValue("stroke_width", self.tool_state.stroke_width)
        settings.setValue("text_size", self.tool_state.text_size)
        settings.setValue("text_color", self.tool_state.text_color)

        settings.setValue("shape_stroke_color", self.tool_state.stroke_color)
        settings.setValue("shape_fill_color", self.tool_state.fill_color or "")
        settings.setValue("arrow_color", self.tool_state.arrow_color)

        if hasattr(self, "combo_pdf_layout"):
            settings.setValue("pdf_layout", self.combo_pdf_layout.currentText())

    def _load_ui_settings(self):
        settings = QSettings("GH", "SettingSheet")

        stroke = float(settings.value("stroke_width", 5.0))
        text_size = float(settings.value("text_size", 40.0))
        text_color = settings.value("text_color", "Black")

        shape_stroke_color = settings.value("shape_stroke_color", "Red")
        shape_fill_color = settings.value("shape_fill_color", "")
        arrow_color = settings.value("arrow_color", "Red")
        pdf_layout = settings.value("pdf_layout", "세로")

        # ToolState 반영
        self.tool_state.stroke_width = stroke
        self.tool_state.text_size = text_size
        self.tool_state.text_color = text_color
        self.tool_state.stroke_color = shape_stroke_color
        self.tool_state.fill_color = shape_fill_color or None
        self.tool_state.arrow_color = arrow_color

        # UI 반영 (✅ 시그널 차단: 로드/동기화 중 ToolState를 다시 덮지 않음)
        self.spin_stroke_width.blockSignals(True)
        self.spin_stroke_width.setValue(float(stroke))
        self.spin_stroke_width.blockSignals(False)

        self.spin_text_size.blockSignals(True)
        self.spin_text_size.setValue(int(text_size))
        self.spin_text_size.blockSignals(False)

        self.combo_text_color.blockSignals(True)
        self.combo_text_color.setCurrentText(text_color)
        self.combo_text_color.blockSignals(False)


        self.combo_shape_stroke_color.setCurrentText(shape_stroke_color)
        self.combo_arrow_color.setCurrentText(arrow_color)

        if shape_fill_color:
            self.combo_shape_fill_color.setCurrentText(shape_fill_color)
        else:
            self.combo_shape_fill_color.setCurrentIndex(0)

        if hasattr(self, "combo_pdf_layout"):
            self.combo_pdf_layout.setCurrentText(pdf_layout)

