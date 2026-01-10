# annotation_widgets.py

from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QComboBox, QSpinBox
)
from PySide6.QtCore import Qt
from annotations import ShapeType
from annotation_tools import AnnotationToolState


# main.py 에서 사용하시는 색상 팔레트와 맞추고 싶다면
DEFAULT_COLORS = [
    "Red", "Green", "Blue", "Yellow",
    "Magenta", "Cyan", "Orange", "Black", "Gray"
]

def _create_color_combo(initial: str = "Yellow") -> QComboBox:
    combo = QComboBox()
    combo.addItems(DEFAULT_COLORS)

    if initial in DEFAULT_COLORS:
        combo.setCurrentText(initial)


    return combo


class AnnotationToolBar(QWidget):
    """
    우측 A4 프레임 상단/중단에 들어가는
    도형/선두께/색상 도구 바를 하나의 위젯으로 묶은 클래스이옵니다.

    - tool_state    : AnnotationToolState 참조
    - on_shape_changed(shape_type)
    - on_width_changed(width)
    - on_stroke_color_changed(color)
    - on_fill_color_changed(color_or_None)
    를 콜백으로 받아 main.py 와 느슨하게 연결할 수 있사옵니다.
    """

    def __init__(
        self,
        tool_state: AnnotationToolState,
        on_shape_changed: Optional[Callable[[ShapeType], None]] = None,
        on_width_changed: Optional[Callable[[float], None]] = None,
        on_stroke_color_changed: Optional[Callable[[str], None]] = None,
        on_fill_color_changed: Optional[Callable[[Optional[str]], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.tool_state = tool_state

        self._on_shape_changed = on_shape_changed
        self._on_width_changed = on_width_changed
        self._on_stroke_color_changed = on_stroke_color_changed
        self._on_fill_color_changed = on_fill_color_changed

        self._build_ui()

    # ─────────────────────
    # UI 구성
    # ─────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
    
        # =========================
        # 1) 도구 모드 버튼(실제로 보이게)
        # =========================
        layout.addWidget(QLabel("도구:"))
    
        self.btn_mode_shape = QPushButton("도형")
        self.btn_mode_shape.setCheckable(True)
        self.btn_mode_shape.clicked.connect(self._use_shape_tool)
        self.btn_mode_shape.setFixedHeight(28)
        self.btn_mode_shape.setMinimumWidth(54)
        layout.addWidget(self.btn_mode_shape)
    
        self.btn_mode_arrow = QPushButton("화살표")
        self.btn_mode_arrow.setCheckable(True)
        self.btn_mode_arrow.clicked.connect(self._use_arrow_tool)
        self.btn_mode_arrow.setFixedHeight(28)
        self.btn_mode_arrow.setMinimumWidth(64)
        layout.addWidget(self.btn_mode_arrow)
    
        self.btn_mode_text = QPushButton("텍스트")
        self.btn_mode_text.setCheckable(True)
        self.btn_mode_text.clicked.connect(self._use_text_tool)
        self.btn_mode_text.setFixedHeight(28)
        self.btn_mode_text.setMinimumWidth(64)
        layout.addWidget(self.btn_mode_text)
    
        self.btn_mode_select = QPushButton("선택")
        self.btn_mode_select.setCheckable(True)
        self.btn_mode_select.clicked.connect(self._use_select_tool)
        self.btn_mode_select.setFixedHeight(28)
        self.btn_mode_select.setMinimumWidth(54)
        layout.addWidget(self.btn_mode_select)
    
        layout.addSpacing(10)
    
        # =========================
        # 2) 도형 타입(도형 모드에서 의미)
        # =========================
        layout.addWidget(QLabel("도형:"))
    
        self.btn_rect = QPushButton("□")
        self.btn_rect.setCheckable(True)
        self.btn_rect.clicked.connect(lambda checked: self._select_shape(ShapeType.RECT))
        self.btn_rect.setFixedSize(34, 28)
        layout.addWidget(self.btn_rect)
    
        self.btn_circle = QPushButton("○")
        self.btn_circle.setCheckable(True)
        self.btn_circle.clicked.connect(lambda checked: self._select_shape(ShapeType.CIRCLE))
        self.btn_circle.setFixedSize(34, 28)
        layout.addWidget(self.btn_circle)
    
        self.btn_datumL = QPushButton("L")
        self.btn_datumL.setCheckable(True)
        self.btn_datumL.clicked.connect(lambda checked: self._select_shape(ShapeType.DATUM_L))
        self.btn_datumL.setFixedSize(34, 28)
        layout.addWidget(self.btn_datumL)
    
        layout.addSpacing(10)
    
        # =========================
        # 3) 두께
        # =========================
        layout.addWidget(QLabel("두께:"))
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setObjectName("AnnoSpinBox")  # ✅ 추가: 두께/크기 스핀 공통 타겟
        self.spin_width.setRange(0.5, 10.0)
        self.spin_width.setSingleStep(0.5)
        self.spin_width.setValue(float(self.tool_state.stroke_width))
        self.spin_width.setFixedHeight(28)
        self.spin_width.setMinimumWidth(90)
        self.spin_width.valueChanged.connect(self._width_changed)
        layout.addWidget(self.spin_width)
    
        layout.addSpacing(10)
    
        # =========================
        # 4) 색상(▼는 Qt 기본 렌더)
        # =========================
        layout.addWidget(QLabel("도형선:"))
        self.combo_stroke = _create_color_combo(self.tool_state.stroke_color)
        self.combo_stroke.setObjectName("AnnoStrokeCombo")  # ✅ 추가
        self.combo_stroke.currentTextChanged.connect(self._stroke_color_changed)
        layout.addWidget(self.combo_stroke)
    
        layout.addWidget(QLabel("채움:"))
        self.combo_fill = _create_color_combo(self.tool_state.fill_color or "Yellow")
        self.combo_fill.setObjectName("AnnoFillCombo")      # ✅ 추가
        self.combo_fill.insertItem(0, "(없음)")
        if self.tool_state.fill_color is None:
            self.combo_fill.setCurrentIndex(0)
        self.combo_fill.currentTextChanged.connect(self._fill_color_changed)
        layout.addWidget(self.combo_fill)
    
        layout.addWidget(QLabel("화살표:"))
        self.combo_arrow = _create_color_combo(getattr(self.tool_state, "arrow_color", "Yellow"))
        self.combo_arrow.setObjectName("AnnoArrowCombo")    # ✅ 추가
        self.combo_arrow.currentTextChanged.connect(self._arrow_color_changed)
        layout.addWidget(self.combo_arrow)
    
        layout.addWidget(QLabel("텍스트:"))
        self.combo_text = _create_color_combo(getattr(self.tool_state, "text_color", "Yellow"))
        self.combo_text.setObjectName("AnnoTextCombo")      # ✅ 추가
        self.combo_text.currentTextChanged.connect(self._text_color_changed)
        layout.addWidget(self.combo_text)
    
        layout.addWidget(QLabel("크기:"))
        self.spin_text = QSpinBox()
        self.spin_text.setObjectName("AnnoSpinBox")   # ✅ 추가: 두께/크기 스핀 공통 타겟
        self.spin_text.setRange(8, 200)
        self.spin_text.setValue(int(getattr(self.tool_state, "text_size", 30)))
        self.spin_text.setFixedHeight(28)
        self.spin_text.setMinimumWidth(70)
        self.spin_text.valueChanged.connect(self._text_size_changed)
        layout.addWidget(self.spin_text)
    
        layout.addStretch(1)
    
        # 초기 동기화
        self._sync_tool_buttons()
        self._sync_shape_buttons(self.tool_state.shape_type)
    
    

    # ─────────────────────
    # 내부: 버튼/스핀박스 → tool_state 반영
    # ─────────────────────
    def _select_shape(self, shape_type: ShapeType) -> None:
        self.tool_state.use_shape_tool(shape_type)
        self._sync_shape_buttons(shape_type)

        if self._on_shape_changed:
            self._on_shape_changed(shape_type)

    def _sync_shape_buttons(self, current: ShapeType) -> None:
        btn_map = {
            ShapeType.RECT: self.btn_rect,
            ShapeType.CIRCLE: self.btn_circle,
            ShapeType.DATUM_L: self.btn_datumL,
        }
        for st, btn in btn_map.items():
            btn.setChecked(st == current)

    def _width_changed(self, value: float) -> None:
        self.tool_state.stroke_width = float(value)
        if self._on_width_changed:
            self._on_width_changed(self.tool_state.stroke_width)

    def _use_shape_tool(self) -> None:
        self.tool_state.use_shape_tool(self.tool_state.shape_type)
        self._sync_tool_buttons()

    def _use_arrow_tool(self) -> None:
        self.tool_state.use_arrow_tool()
        self._sync_tool_buttons()

    def _use_text_tool(self) -> None:
        self.tool_state.use_text_tool()
        self._sync_tool_buttons()

    def _use_select_tool(self) -> None:
        self.tool_state.use_select_tool()
        self._sync_tool_buttons()

    def _sync_tool_buttons(self) -> None:
        # tool_state.active_tool에 맞춰 체크 표시
        try:
            from .annotation_tools import ToolKind
        except Exception:
            return

        cur = self.tool_state.active_tool
        self.btn_tool_shape.setChecked(cur == ToolKind.SHAPE)
        self.btn_tool_arrow.setChecked(cur == ToolKind.ARROW)
        self.btn_tool_text.setChecked(cur == ToolKind.TEXT)
        self.btn_tool_select.setChecked(cur == ToolKind.SELECT)

    def _arrow_color_changed(self, color: str) -> None:
        self.tool_state.arrow_color = color

    def _text_color_changed(self, color: str) -> None:
        self.tool_state.text_color = color

    def _text_size_changed(self, value: int) -> None:
        self.tool_state.text_size = float(value)


    def _stroke_color_changed(self, color: str) -> None:
        self.tool_state.stroke_color = color
        self.tool_state.arrow_color = color  # 화살표도 동일 색으로 사용하는 예
        if self._on_stroke_color_changed:
            self._on_stroke_color_changed(color)

    def _fill_color_changed(self, text: str) -> None:
        if text == "(없음)":
            self.tool_state.fill_color = None
        else:
            self.tool_state.fill_color = text
        if self._on_fill_color_changed:
            self._on_fill_color_changed(self.tool_state.fill_color)
