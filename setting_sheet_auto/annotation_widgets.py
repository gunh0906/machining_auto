# annotation_widgets.py

from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QComboBox
)

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
    combo.setMaximumWidth(90)
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
        layout.setSpacing(4)

        # ─ 도형 선택 ─
        lbl_shape = QLabel("도형:")
        layout.addWidget(lbl_shape)

        self.btn_rect = QPushButton("□")
        self.btn_rect.setCheckable(True)
        self.btn_rect.setToolTip("사각형 도형")
        self.btn_rect.clicked.connect(lambda checked: self._select_shape(ShapeType.RECT))
        layout.addWidget(self.btn_rect)

        self.btn_circle = QPushButton("○")
        self.btn_circle.setCheckable(True)
        self.btn_circle.setToolTip("원형 도형")
        self.btn_circle.clicked.connect(lambda checked: self._select_shape(ShapeType.CIRCLE))
        layout.addWidget(self.btn_circle)

        self.btn_datumL = QPushButton("L")
        self.btn_datumL.setCheckable(True)
        self.btn_datumL.setToolTip("기준면 표시용 L 도형")
        self.btn_datumL.clicked.connect(lambda checked: self._select_shape(ShapeType.DATUM_L))
        layout.addWidget(self.btn_datumL)

        layout.addSpacing(12)

        # ─ 선 두께 ─
        lbl_width = QLabel("두께:")
        layout.addWidget(lbl_width)

        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(0.5, 5.0)
        self.spin_width.setSingleStep(0.5)
        self.spin_width.setValue(self.tool_state.stroke_width)
        self.spin_width.setToolTip("도형/화살표 선 두께")
        self.spin_width.valueChanged.connect(self._width_changed)
        layout.addWidget(self.spin_width)

        layout.addSpacing(12)

        # ─ 선 색상 ─
        lbl_stroke = QLabel("선색:")
        layout.addWidget(lbl_stroke)

        self.combo_stroke = _create_color_combo(self.tool_state.stroke_color)
        self.combo_stroke.currentTextChanged.connect(self._stroke_color_changed)
        layout.addWidget(self.combo_stroke)

        layout.addSpacing(8)

        # ─ 채움 색상 ─
        lbl_fill = QLabel("채움:")
        layout.addWidget(lbl_fill)

        self.combo_fill = _create_color_combo(self.tool_state.fill_color or "Yellow")
        # '없음' 선택을 허용하려면 맨 앞에 하나 추가해도 되옵니다.
        self.combo_fill.insertItem(0, "(없음)")
        if self.tool_state.fill_color is None:
            self.combo_fill.setCurrentIndex(0)
        self.combo_fill.currentTextChanged.connect(self._fill_color_changed)
        layout.addWidget(self.combo_fill)

        layout.addStretch(1)

        # 초기 도형 버튼 상태 정렬
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
