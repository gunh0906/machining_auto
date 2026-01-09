# annotation_tools.py

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from .annotations import ShapeType


class ToolKind(Enum):
    """어떤 종류의 도구가 활성화되어 있는지 구분하는 열거형이옵니다."""
    SELECT = auto()
    SHAPE = auto()
    ARROW = auto()
    TEXT = auto()


@dataclass
class AnnotationToolState:
    """
    주석 도구의 현재 상태를 보관하는 데이터 클래스이옵니다.

    - active_tool   : SHAPE / ARROW / TEXT / SELECT
    - shape_type    : RECT / CIRCLE / DATUM_L 등 (ShapeType)
    - stroke_width  : 선 두께
    - stroke_color  : 선 색상
    - fill_color    : 내부 채움 색상 (없으면 None)
    - arrow_color   : 화살표 색
    - text_color    : 텍스트 색
    """
    active_tool: ToolKind = ToolKind.SHAPE
    shape_type: ShapeType = ShapeType.RECT
    stroke_width: float = 5

    stroke_color: str = "Yellow"
    fill_color: Optional[str] = None

    arrow_color: str = "Red"
    text_color: str = "Black"
    text_size: float = 40.0  # 텍스트 기본 크기


    def use_shape_tool(self, shape_type: ShapeType) -> None:
        """도형 도구를 선택할 때 호출하는 헬퍼이옵니다."""
        self.active_tool = ToolKind.SHAPE
        self.shape_type = shape_type

    def use_arrow_tool(self) -> None:
        """화살표 도구 선택."""
        self.active_tool = ToolKind.ARROW

    def use_text_tool(self) -> None:
        """텍스트 도구 선택."""
        self.active_tool = ToolKind.TEXT

    def use_select_tool(self) -> None:
        """선택/이동 등의 셀렉트 도구."""
        self.active_tool = ToolKind.SELECT
