from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (
    QGraphicsSceneMouseEvent,
    QInputDialog,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsItem
)

from .annotations import AnnotationSet, Point2D, ShapeType
from .annotation_tools import AnnotationToolState, ToolKind


class AnnotationController:
    def __init__(self, scene, annotation_set: AnnotationSet, tool_state: AnnotationToolState) -> None:
        self.scene = scene
        self.annotation_set = annotation_set
        self.tool_state = tool_state

        self._is_drawing: bool = False
        self._start_scene_pos: QPointF | None = None

        # ★ 프리뷰(미리보기) 아이템
        self._preview_item = None  # type: object | None

    # ─────────────────────────────
    # 유틸
    # ─────────────────────────────
    @staticmethod
    def _clamp01(v: float) -> float:
        if v < 0.0:
            return 0.0
        if v > 1.0:
            return 1.0
        return v
    
    def _clamp_scene_point(self, pt: QPointF) -> QPointF:
        """
        드로잉 좌표를 SceneRect 안으로만 제한 (UI 창 내부에서 자유롭게)
        """
        r = self.scene.sceneRect()
        x = min(max(pt.x(), r.left()), r.right())
        y = min(max(pt.y(), r.top()), r.bottom())
        return QPointF(x, y)

    def _clear_preview(self) -> None:
        """프리뷰 아이템 제거"""
        if self._preview_item is not None:
            try:
                self.scene.removeItem(self._preview_item)
            except Exception:
                pass
            self._preview_item = None

    def _norm_to_scene_safe(self, p: Point2D) -> QPointF:
        """
        정규화 좌표(0~1) → Scene 좌표 (프리뷰용)
        - scene.normalized_to_scene()가 있으면 사용
        - 없으면 (임시로) _norm_to_scene를 호출
        """
        if hasattr(self.scene, "normalized_to_scene"):
            return self.scene.normalized_to_scene(p)

        # fallback: graphics_annotations.AnnotationScene 에 _norm_to_scene가 있음
        if hasattr(self.scene, "_norm_to_scene"):
            return self.scene._norm_to_scene(p)

        # 최후 fallback
        return QPointF(0, 0)

    def _preview_pen(self) -> QPen:
        """프리뷰용 펜(점선)"""
        # 색상은 도구 상태에 맞춤: 도형이면 stroke_color, 화살표면 arrow_color
        if self.tool_state.active_tool == ToolKind.ARROW:
            color_name = getattr(self.tool_state, "arrow_color", "White")
        else:
            color_name = getattr(self.tool_state, "stroke_color", "White")

        pen = QPen(QColor(color_name))
        pen.setWidthF(float(getattr(self.tool_state, "stroke_width", 1.5)))
        pen.setStyle(Qt.DashLine)
        return pen

    # ─────────────────────────────
    # Scene → Controller 마우스 이벤트
    # ─────────────────────────────
    def handle_mouse_press(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return

        if not hasattr(self.scene, "has_image") or not self.scene.has_image():
            return

        self._is_drawing = True
        self._start_scene_pos = event.scenePos()
        self._clear_preview()

    def handle_mouse_move(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        드래그 중 프리뷰 표시
        - clamp 기준: 이미지 ❌ / SceneRect ⭕
        - 프리뷰는 고대비(Magenta) + DashLine + 최상단 ZValue
        """
        if not self._is_drawing or self._start_scene_pos is None:
            return

        # TEXT 도구는 프리뷰 없음
        if self.tool_state.active_tool == ToolKind.TEXT:
            return

        # SceneRect 내부로만 제한
        end_pos = self._clamp_scene_point(event.scenePos())

        # ★ 프리뷰 펜(고대비)
        pen = QPen(QColor("Magenta"))
        pen.setWidthF(float(getattr(self.tool_state, "stroke_width", 1.5)))
        pen.setStyle(Qt.DashLine)

        # 프리뷰 아이템 생성
        if self._preview_item is None:
            if self.tool_state.active_tool == ToolKind.ARROW:
                self._preview_item = QGraphicsLineItem()
                self.scene.addItem(self._preview_item)

            elif self.tool_state.active_tool == ToolKind.SHAPE:
                if self.tool_state.shape_type in (ShapeType.CIRCLE, ShapeType.ELLIPSE):
                    self._preview_item = QGraphicsEllipseItem()
                else:
                    # RECT / TRIANGLE / STAR / POLYGON 등은 드래그 프리뷰를 bbox로 보여줌
                    self._preview_item = QGraphicsRectItem()
                self.scene.addItem(self._preview_item)

            else:
                # 예상치 못한 도구 상태면 프리뷰를 만들지 않음
                return

            # 공통 스타일
            self._preview_item.setPen(pen)
            if hasattr(self._preview_item, "setBrush"):
                self._preview_item.setBrush(Qt.NoBrush)

            # 최상단 표시
            self._preview_item.setZValue(10_000)

            # 프리뷰는 선택/이동 불필요
            if hasattr(self._preview_item, "setFlag"):
                self._preview_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
                self._preview_item.setFlag(QGraphicsItem.ItemIsMovable, False)

        else:
            # 기존 프리뷰 아이템도 펜이 유지되도록(도구/두께 변경 대응)
            try:
                self._preview_item.setPen(pen)
            except Exception:
                pass

        # 프리뷰 갱신
        if isinstance(self._preview_item, QGraphicsLineItem):
            self._preview_item.setLine(
                self._start_scene_pos.x(),
                self._start_scene_pos.y(),
                end_pos.x(),
                end_pos.y(),
            )
        else:
            x1, y1 = self._start_scene_pos.x(), self._start_scene_pos.y()
            x2, y2 = end_pos.x(), end_pos.y()
            rect = QRectF(
                min(x1, x2),
                min(y1, y2),
                abs(x1 - x2),
                abs(y1 - y2),
            )
            self._preview_item.setRect(rect)

    def handle_mouse_release(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        마우스 종료 시점에 실제 Annotation 생성

        TEXT 도구는 '클릭'만으로 생성
        SHAPE / ARROW는 기존대로 드래그 기반 생성
        """
        if not self._is_drawing or self._start_scene_pos is None:
            return

        if event.button() != Qt.LeftButton:
            return

        self._is_drawing = False

        # SceneRect 기준 clamp
        end_pos = self._clamp_scene_point(event.scenePos())

        if not hasattr(self.scene, "scene_to_normalized"):
            self._clear_preview()
            self._start_scene_pos = None
            return

        dist = (end_pos - self._start_scene_pos).manhattanLength()
        # 너무 작은 도형 생성 방지(Shape 전용)
        # 너무 작은/선 같은 도형 생성 방지(Shape 전용)
        # - 가로/세로 중 하나라도 너무 작으면(선 형태) 생성 금지
        MIN_SHAPE_SIZE_PX = 12.0
        if self.tool_state.active_tool == ToolKind.SHAPE:
            dx = abs(end_pos.x() - self._start_scene_pos.x())
            dy = abs(end_pos.y() - self._start_scene_pos.y())

            if dx < MIN_SHAPE_SIZE_PX or dy < MIN_SHAPE_SIZE_PX:
                self._clear_preview()
                self._start_scene_pos = None
                return



        # ─────────────────────────────
        # TEXT : 클릭 생성 (거리 무시)
        # ─────────────────────────────
        if self.tool_state.active_tool == ToolKind.TEXT:
            self._clear_preview()

            p = self.scene.scene_to_normalized(end_pos)
            self._create_text_at(p)

            if hasattr(self.scene, "set_annotation_set"):
                self.scene.set_annotation_set(self.annotation_set)

            self._start_scene_pos = None
            return

        # ─────────────────────────────
        # SHAPE / ARROW : 드래그 기반
        # ─────────────────────────────
        if dist < 3:
            self._clear_preview()
            self._start_scene_pos = None
            return

        p1: Point2D = self.scene.scene_to_normalized(self._start_scene_pos)
        p2: Point2D = self.scene.scene_to_normalized(end_pos)

        self._clear_preview()

        if self.tool_state.active_tool == ToolKind.SHAPE:
            self._create_shape_from_drag(p1, p2)
        elif self.tool_state.active_tool == ToolKind.ARROW:
            self._create_arrow_from_drag(p1, p2)

        if hasattr(self.scene, "set_annotation_set"):
            self.scene.set_annotation_set(self.annotation_set)

        self._start_scene_pos = None


    # ─────────────────────────────
    # 내부: 도형 / 화살표 / 텍스트 생성 로직
    # ─────────────────────────────
    def _create_shape_from_drag(self, p1: Point2D, p2: Point2D) -> None:
        shape_type: ShapeType = self.tool_state.shape_type

        # DATUM_L 특수 처리
        if shape_type == ShapeType.DATUM_L:
            self.annotation_set.add_shape(
                shape_type=ShapeType.DATUM_L,
                points=[p1],
                stroke_color=self.tool_state.stroke_color,
                fill_color=None,
                stroke_width=self.tool_state.stroke_width,
            )
            return

        # p1, p2 bbox
        x1, y1 = p1.x, p1.y
        x2, y2 = p2.x, p2.y
        left, right = min(x1, x2), max(x1, x2)
        top, bottom = min(y1, y2), max(y1, y2)
        cx, cy = (left + right) / 2.0, (top + bottom) / 2.0
        w, h = right - left, bottom - top
        r = min(w, h) / 2.0

        points: list[Point2D]

        if shape_type in (ShapeType.RECT, ShapeType.CIRCLE, ShapeType.ELLIPSE):
            points = [Point2D(left, top), Point2D(right, bottom)]

        elif shape_type == ShapeType.TRIANGLE:
            top_center = Point2D(cx, top)
            bottom_left = Point2D(left, bottom)
            bottom_right = Point2D(right, bottom)
            points = [top_center, bottom_right, bottom_left]

        elif shape_type == ShapeType.POLYGON:
            points = [Point2D(cx, top), Point2D(right, cy), Point2D(cx, bottom), Point2D(left, cy)]

        elif shape_type == ShapeType.STAR:
            import math
            points = []
            for i in range(10):
                angle = math.radians(-90 + i * 36)
                radius = r if i % 2 == 0 else r * 0.4
                points.append(Point2D(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        else:
            points = [Point2D(left, top), Point2D(right, bottom)]

        self.annotation_set.add_shape(
            shape_type=shape_type,
            points=points,
            stroke_color=self.tool_state.stroke_color,
            fill_color=self.tool_state.fill_color,
            stroke_width=self.tool_state.stroke_width,
        )

    def _create_text_at(self, p: Point2D) -> None:
        """
        TEXT 도구 클릭 시 텍스트 생성
        """
        text, ok = QInputDialog.getText(
            None,
            "텍스트 입력",
            "표시할 텍스트를 입력하십시오:",
        )

        if not ok:
            return

        value = (text or "").strip()
        if not value:
            return

        self.annotation_set.add_text(
            position=p,
            text=value,
            color=self.tool_state.text_color,
            font_size=int(self.tool_state.text_size),
        )


    def _create_arrow_from_drag(self, p1: Point2D, p2: Point2D) -> None:
        """
        - p1: 첫 클릭(화살촉 쪽)
        - p2: 드래그 종료(꼬리 쪽)
        - 텍스트는 TextAnnotation으로 별도 생성, parent_id = arrow.id 로 연동
        - 텍스트 입력 취소/공백이면 생성된 화살표도 제거(유령 화살표 방지)
        """
        # 1) 화살표 생성
        arrow = self.annotation_set.add_arrow(
            start=p1,
            end=p2,
            text="",
            color=self.tool_state.arrow_color,
            line_width=self.tool_state.stroke_width,
        )

        # 2) 텍스트 입력
        text, ok = QInputDialog.getText(
            None,
            "화살표 텍스트",
            "화살표 꼬리 위치에 표시할 텍스트를 입력하십시오:",
        )
        if not ok:
            # ★ 취소 → 방금 만든 화살표 제거
            if arrow in self.annotation_set.arrows:
                self.annotation_set.arrows.remove(arrow)
            return

        value = (text or "").strip()
        if not value:
            # ★ 공백 → 방금 만든 화살표 제거
            if arrow in self.annotation_set.arrows:
                self.annotation_set.arrows.remove(arrow)
            return

        # 3) 텍스트 생성(꼬리 위치)
        t = self.annotation_set.add_text(
            position=p2,
            text=value,
            color=self.tool_state.text_color,
            font_size=int(self.tool_state.text_size),
        )

        # 4) ★ 핵심: 묶음(연동)
        t.parent_id = arrow.id

        # 5) 생성 직후 외곽 스냅(있으면 호출)
        if hasattr(self.scene, "snap_linked_arrow_tails_to_text_edges"):
            self.scene.set_annotation_set(self.annotation_set)
            self.scene.snap_linked_arrow_tails_to_text_edges()
