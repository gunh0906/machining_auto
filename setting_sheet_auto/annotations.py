# annotations.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Any, Optional
import uuid


class AnnotationKind(Enum):
    TEXT = auto()
    ARROW = auto()
    SHAPE = auto()


class ShapeType(Enum):
    RECT = auto()
    TRIANGLE = auto()
    CIRCLE = auto()
    ELLIPSE = auto()
    STAR = auto()
    POLYGON = auto()
    DATUM_L = auto()   # 기준면 표시용 L형 도형


@dataclass
class Point2D:
    """정규화 좌표 (0.0 ~ 1.0) 기준의 2D 포인트"""
    x: float
    y: float


@dataclass
class AnnotationBase:
    """모든 주석의 공통 베이스"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: AnnotationKind = field(init=False)
    label: str = ""
    visible: bool = True
    z_index: int = 0


@dataclass
class TextAnnotation(AnnotationBase):
    position: Point2D = field(default_factory=lambda: Point2D(0.5, 0.5))
    text: str = ""
    color: str = "Red"
    font_size: int = 30
    parent_id: Optional[str] = None   # ★ 도형/화살표와 그룹을 이루는 부모 ID
    
    def __post_init__(self):
        self.kind = AnnotationKind.TEXT
        if not self.label:
            self.label = "TEXT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.name,
            "label": self.label,
            "visible": self.visible,
            "z_index": self.z_index,
            "position": {"x": self.position.x, "y": self.position.y},
            "text": self.text,
            "color": self.color,
            "font_size": self.font_size,
            "parent_id": self.parent_id,   # ★ 추가
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TextAnnotation":
        ann = TextAnnotation(
            position=Point2D(data["position"]["x"], data["position"]["y"]),
            text=data.get("text", ""),
            color=data.get("color", "Red"),
            font_size=data.get("font_size", 30),
        )
        ann.id = data.get("id", ann.id)
        ann.label = data.get("label", ann.label)
        ann.visible = data.get("visible", True)
        ann.z_index = data.get("z_index", 0)
        ann.parent_id = data.get("parent_id")  # ★ 추가
        return ann


@dataclass
class ArrowAnnotation(AnnotationBase):
    start: Point2D = field(default_factory=lambda: Point2D(0.4, 0.4))
    end: Point2D = field(default_factory=lambda: Point2D(0.6, 0.6))
    text: str = ""
    color: str = "Red"
    line_width: float = 1.5
    head_size: float = 0.02  # 화살촉 크기 (정규화 비율)
    text_size: int = 30      # 화살표 텍스트 크기

    def __post_init__(self):
        self.kind = AnnotationKind.ARROW
        if not self.label:
            self.label = "ARROW"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.name,
            "label": self.label,
            "visible": self.visible,
            "z_index": self.z_index,
            "start": {"x": self.start.x, "y": self.start.y},
            "end": {"x": self.end.x, "y": self.end.y},
            "text": self.text,
            "color": self.color,
            "line_width": self.line_width,
            "head_size": self.head_size,
            "text_size": self.text_size,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ArrowAnnotation":
        ann = ArrowAnnotation(
            start=Point2D(data["start"]["x"], data["start"]["y"]),
            end=Point2D(data["end"]["x"], data["end"]["y"]),
            text=data.get("text", ""),
            color=data.get("color", "Red"),
            line_width=data.get("line_width", 1.5),
            head_size=data.get("head_size", 0.02),
            text_size=data.get("text_size", 30),  # ← 추가
        )
        ann.id = data.get("id", ann.id)
        ann.label = data.get("label", ann.label)
        ann.visible = data.get("visible", True)
        ann.z_index = data.get("z_index", 0)
        return ann


@dataclass
class ShapeAnnotation(AnnotationBase):
    shape_type: ShapeType = ShapeType.RECT
    points: List[Point2D] = field(default_factory=list)
    stroke_color: str = "Red"
    fill_color: Optional[str] = None  # None이면 채우지 않음
    stroke_width: float = 1.5

    def __post_init__(self):
        self.kind = AnnotationKind.SHAPE
        if not self.label:
            self.label = f"SHAPE_{self.shape_type.name}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.name,
            "label": self.label,
            "visible": self.visible,
            "z_index": self.z_index,
            "shape_type": self.shape_type.name,
            "points": [{"x": p.x, "y": p.y} for p in self.points],
            "stroke_color": self.stroke_color,
            "fill_color": self.fill_color,
            "stroke_width": self.stroke_width,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ShapeAnnotation":
        points = [Point2D(p["x"], p["y"]) for p in data.get("points", [])]
        shape_type = ShapeType[data.get("shape_type", "RECT")]
        ann = ShapeAnnotation(
            shape_type=shape_type,
            points=points,
            stroke_color=data.get("stroke_color", "Red"),
            fill_color=data.get("fill_color"),
            stroke_width=data.get("stroke_width", 1.5),
        )
        ann.id = data.get("id", ann.id)
        ann.label = data.get("label", ann.label)
        ann.visible = data.get("visible", True)
        ann.z_index = data.get("z_index", 0)
        return ann


@dataclass
class AnnotationSet:
    """한 이미지(스크린샷)에 대한 전체 주석 묶음"""
    main_point: Optional[TextAnnotation] = None
    texts: List[TextAnnotation] = field(default_factory=list)
    arrows: List[ArrowAnnotation] = field(default_factory=list)
    shapes: List[ShapeAnnotation] = field(default_factory=list)

    # 생성 편의 메서드들
    def add_text(self, position: Point2D, text: str,
                 color: str = "Red", font_size: int = 12,
                 label: str = "") -> TextAnnotation:
        ann = TextAnnotation(position=position, text=text, color=color, font_size=font_size)
        if label:
            ann.label = label
        self.texts.append(ann)
        return ann

    def add_arrow(self, start: Point2D, end: Point2D, text: str = "",
                  color: str = "Red", line_width: float = 1.5,
                  text_size: int = 30,
                  label: str = "") -> ArrowAnnotation:
        ann = ArrowAnnotation(
            start=start,
            end=end,
            text=text,
            color=color,
            line_width=line_width,
            text_size=text_size,
        )
        if label:
            ann.label = label
        self.arrows.append(ann)
        return ann


    def add_shape(self, shape_type: ShapeType, points: List[Point2D],
                  stroke_color: str = "Red", fill_color: Optional[str] = None,
                  stroke_width: float = 1.5, label: str = "") -> ShapeAnnotation:
        ann = ShapeAnnotation(shape_type=shape_type, points=points,
                              stroke_color=stroke_color,
                              fill_color=fill_color,
                              stroke_width=stroke_width)
        if label:
            ann.label = label
        self.shapes.append(ann)
        return ann

    # 직렬화
    def to_dict(self) -> Dict[str, Any]:
        return {
            "main_point": self.main_point.to_dict() if self.main_point else None,
            "texts": [t.to_dict() for t in self.texts],
            "arrows": [a.to_dict() for a in self.arrows],
            "shapes": [s.to_dict() for s in self.shapes],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AnnotationSet":
        aset = AnnotationSet()
        if data.get("main_point"):
            aset.main_point = TextAnnotation.from_dict(data["main_point"])
        for td in data.get("texts", []):
            aset.texts.append(TextAnnotation.from_dict(td))
        for ad in data.get("arrows", []):
            aset.arrows.append(ArrowAnnotation.from_dict(ad))
        for sd in data.get("shapes", []):
            aset.shapes.append(ShapeAnnotation.from_dict(sd))
        return aset
