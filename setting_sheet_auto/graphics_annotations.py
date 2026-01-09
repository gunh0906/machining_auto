# graphics_annotations.py
from typing import Optional, List

from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsTextItem, QGraphicsLineItem,
    QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsRectItem,
    QGraphicsPathItem, QGraphicsItem, 
)
from PySide6.QtGui import QPen, QBrush, QColor, QPolygonF, QPainterPath, QTransform, QKeyEvent, QFont, QPainterPathStroker
from PySide6.QtCore import QPointF, Qt, QRectF

from .annotations import (
    AnnotationSet, TextAnnotation, ArrowAnnotation, ShapeAnnotation,
    Point2D, ShapeType
)
from .annotation_tools import ToolKind 

class ClickableLineItem(QGraphicsLineItem):
    """
    화살표 라인의 클릭 영역을 두껍게 만들어,
    꼬리/중간 어디를 클릭해도 잘 선택되도록 하는 아이템입니다.
    """
    def shape(self):
        path = super().shape()
        stroker = QPainterPathStroker()
        stroker.setWidth(max(20.0, self.pen().widthF() * 3.0))  # 클릭 허용 폭 크게
        return stroker.createStroke(path)


class EditableTextItem(QGraphicsTextItem):
    """
    TextAnnotation과 연결된 편집 가능한 텍스트 아이템.
    - 기본은 편집 불가(드래그만 가능)
    - 오른쪽 클릭 시 편집 모드 진입
    - Enter / 포커스 아웃 시 Annotation에 내용 반영 + Scene 다시 그리기
    """
    def __init__(self, ann: TextAnnotation, scene: "AnnotationScene"):
        super().__init__()
        self.annotation = ann
        self._scene_ref = scene

        # 기본은 아직 내용/HTML을 설정하지 않음
        # (내용/스타일은 _draw_text 에서 setHtml(...)로 설정)

        # 기본 상태: 편집 불가 + 선택/이동 가능
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)

    # 오른쪽 클릭 시 부를 편집 시작 함수
    def start_edit(self):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus()

    # ★ 오른쪽 클릭을 여기서 직접 가로챔
    def mousePressEvent(self, event):
        """
        EditableTextItem 전용 mousePressEvent
        - 우클릭: 편집 시작
        - 그 외: 기본(선택/드래그)
        """
        if event.button() == Qt.RightButton:
            self.start_edit()
            event.accept()
            return

        super().mousePressEvent(event)



        # 오른쪽 버튼: 도형이면 묶음 해제 메뉴
        if event.button() == Qt.RightButton:
            view = self.views()[0] if self.views() else None
            transform = view.transform() if view is not None else QTransform()
            item = self.itemAt(event.scenePos(), transform)

            if item is not None and hasattr(item, "annotation"):
                ann = item.annotation
                from .annotations import ShapeAnnotation
                if isinstance(ann, ShapeAnnotation) and self._annotation_set is not None:
                    from PySide6.QtWidgets import QMenu
                    menu = QMenu()
                    ungroup_action = menu.addAction("묶음 해제")

                    chosen = menu.exec(event.screenPos())
                    if chosen == ungroup_action:
                        for t in self._annotation_set.texts:
                            if t.parent_id == ann.id:
                                t.parent_id = None
                        self._redraw_annotations()
                        event.accept()
                        return

            # 도형이 아니면 기본 우클릭 처리
            super().mousePressEvent(event)
            return

        # 그 외 버튼은 기본 처리
        super().mousePressEvent(event)


    def _commit_and_stop(self):
        from .annotations import TextAnnotation
        if isinstance(self.annotation, TextAnnotation):
            # 텍스트 내용 반영
            self.annotation.text = self.toPlainText().strip()

            # 현재 아이템의 중심(Scene 좌표) 계산
            rect = self.boundingRect()
            center_scene = QPointF(
                self.x() + rect.width() / 2.0,
                self.y() + rect.height() / 2.0,
            )

            # 중심을 정규화 좌표로 저장하여 위치도 함께 반영
            if self._scene_ref is not None:
                self.annotation.position = self._scene_ref.scene_to_normalized(center_scene)

        # 다시 편집 불가 상태
        self.setTextInteractionFlags(Qt.NoTextInteraction)

        # Scene 다시 그리기
        if self._scene_ref is not None:
            self._scene_ref._redraw_annotations()


    def keyPressEvent(self, event):
        # 엔터 → 편집 종료 + 내용 저장
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() == Qt.NoModifier:
            self._commit_and_stop()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        # 포커스가 빠져나갈 때도 편집 중이었다면 저장
        if self.textInteractionFlags() & Qt.TextEditorInteraction:
            self._commit_and_stop()
        super().focusOutEvent(event)

    def mouseDoubleClickEvent(self, event):
        # 더블클릭하면 편집 모드 활성화
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus()
        event.accept()

    def contextMenuEvent(self, event):
        """우클릭 시 묶음 해제 메뉴 제공"""
        from PySide6.QtWidgets import QMenu

        menu = QMenu()

        ungroup_action = menu.addAction("묶음 해제")

        chosen = menu.exec(event.screenPos())
        if chosen == ungroup_action:
            # parent_id 초기화 → 묶음 해제
            self.annotation.parent_id = None

            # 다시 그리기
            if self._scene_ref is not None:
                self._scene_ref._redraw_annotations()

        event.accept()


class _ResizeMixin:
    """
    코너 드래그로 크기 조절(리사이즈) 공통 믹스인
    - 도형(RECT/ELLIPSE/POLYGON)에만 사용 (화살표 제외)
    """
    RESIZE_MARGIN_PX = 8.0
    MIN_SIZE_PX = 12.0

    def _hit_corner(self, rect, pos):
        # rect/pos: item-local 좌표계
        tl = rect.topLeft()
        tr = rect.topRight()
        bl = rect.bottomLeft()
        br = rect.bottomRight()

        def near(a, b):
            return (a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2 <= (self.RESIZE_MARGIN_PX ** 2)

        if near(pos, tl):
            return "TL"
        if near(pos, tr):
            return "TR"
        if near(pos, bl):
            return "BL"
        if near(pos, br):
            return "BR"
        return None

    def _opposite_corner(self, corner):
        return {"TL": "BR", "TR": "BL", "BL": "TR", "BR": "TL"}[corner]

    def _draw_selection_outline(self, painter):
        """
        선택 점선을 더 명확하게 표시.
        - 흰색(굵게) 한 번 + 검정(얇게) 한 번 겹쳐 그려 어떤 배경에서도 보이게 함
        - Cosmetic pen: 확대/축소해도 두께 일정
        """
        r = self.boundingRect().adjusted(-1.5, -1.5, 1.5, 1.5)

        painter.save()

        # 바깥 흰색 점선 (굵게)
        pen1 = QPen(QColor(255, 255, 255), 2.0, Qt.DashLine)
        pen1.setCosmetic(True)
        painter.setPen(pen1)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(r)

        # 안쪽 검정 점선 (얇게)
        pen2 = QPen(QColor(0, 0, 0), 1.0, Qt.DashLine)
        pen2.setCosmetic(True)
        painter.setPen(pen2)
        painter.drawRect(r)

        painter.restore()


class ResizableRectItem(QGraphicsRectItem, _ResizeMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resizing = False
        self._resize_corner = None
        self._press_rect = None
        self._press_pos = None

    def hoverMoveEvent(self, event):
        rect = self.rect()
        corner = self._hit_corner(rect, event.pos())
        if self.isSelected() and corner:
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isSelected():
            rect = self.rect()
            corner = self._hit_corner(rect, event.pos())
            if corner:
                self._resizing = True
                self._resize_corner = corner
                self._press_rect = QRectF(rect)
                self._press_pos = QPointF(event.pos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._press_rect is not None and self._press_pos is not None:
            r = QRectF(self._press_rect)
            dp = event.pos() - self._press_pos

            # 코너별 조정
            if self._resize_corner == "TL":
                r.setTopLeft(r.topLeft() + dp)
            elif self._resize_corner == "TR":
                r.setTopRight(r.topRight() + dp)
            elif self._resize_corner == "BL":
                r.setBottomLeft(r.bottomLeft() + dp)
            elif self._resize_corner == "BR":
                r.setBottomRight(r.bottomRight() + dp)

            # 최소 크기 제한
            if r.width() < self.MIN_SIZE_PX:
                if self._resize_corner in ("TL", "BL"):
                    r.setLeft(r.right() - self.MIN_SIZE_PX)
                else:
                    r.setRight(r.left() + self.MIN_SIZE_PX)
            if r.height() < self.MIN_SIZE_PX:
                if self._resize_corner in ("TL", "TR"):
                    r.setTop(r.bottom() - self.MIN_SIZE_PX)
                else:
                    r.setBottom(r.top() + self.MIN_SIZE_PX)

            self.setRect(r.normalized())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_corner = None
            self._press_rect = None
            self._press_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            self._draw_selection_outline(painter)


class ResizableEllipseItem(QGraphicsEllipseItem, _ResizeMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resizing = False
        self._resize_corner = None
        self._press_rect = None
        self._press_pos = None

    def shape(self):
        """
        ✅ 타원도 동일 원칙:
        shape() 안에서 self.boundingRect() 대신 self.rect() 기반으로 rect를 만든다.
        """
        base = super().shape()

        r = self.rect().adjusted(
            -self.RESIZE_MARGIN_PX,
            -self.RESIZE_MARGIN_PX,
            self.RESIZE_MARGIN_PX,
            self.RESIZE_MARGIN_PX,
        )

        extra = QPainterPath()
        extra.addRect(r)
        return base.united(extra)


    def hoverMoveEvent(self, event):
        rect = self.rect()
        corner = self._hit_corner(rect, event.pos())
        if self.isSelected() and corner:
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isSelected():
            rect = self.rect()
            corner = self._hit_corner(rect, event.pos())
            if corner:
                self._resizing = True
                self._resize_corner = corner
                self._press_rect = QRectF(rect)
                self._press_pos = QPointF(event.pos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._press_rect is not None and self._press_pos is not None:
            r = QRectF(self._press_rect)
            dp = event.pos() - self._press_pos

            if self._resize_corner == "TL":
                r.setTopLeft(r.topLeft() + dp)
            elif self._resize_corner == "TR":
                r.setTopRight(r.topRight() + dp)
            elif self._resize_corner == "BL":
                r.setBottomLeft(r.bottomLeft() + dp)
            elif self._resize_corner == "BR":
                r.setBottomRight(r.bottomRight() + dp)

            if r.width() < self.MIN_SIZE_PX:
                if self._resize_corner in ("TL", "BL"):
                    r.setLeft(r.right() - self.MIN_SIZE_PX)
                else:
                    r.setRight(r.left() + self.MIN_SIZE_PX)
            if r.height() < self.MIN_SIZE_PX:
                if self._resize_corner in ("TL", "TR"):
                    r.setTop(r.bottom() - self.MIN_SIZE_PX)
                else:
                    r.setBottom(r.top() + self.MIN_SIZE_PX)

            self.setRect(r.normalized())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_corner = None
            self._press_rect = None
            self._press_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            self._draw_selection_outline(painter)


class ResizablePolygonItem(QGraphicsPolygonItem, _ResizeMixin):
    def __init__(self, poly: QPolygonF):
        super().__init__(poly)
        self._resizing = False
        self._resize_corner = None
        self._press_pos = None
        self._press_poly = None
        self._press_rect = None
    def shape(self):
        """
        ✅ 재귀 방지:
        shape() 안에서 self.boundingRect() 호출 금지.
        polygon().boundingRect()를 사용하여 hit 영역을 확장한다.
        """
        base = super().shape()

        # ❌ self.boundingRect() 사용 금지 (shape↔boundingRect 재귀 가능)
        r = self.polygon().boundingRect().adjusted(
            -self.RESIZE_MARGIN_PX,
            -self.RESIZE_MARGIN_PX,
            self.RESIZE_MARGIN_PX,
            self.RESIZE_MARGIN_PX,
        )

        extra = QPainterPath()
        extra.addRect(r)
        return base.united(extra)


    def hoverMoveEvent(self, event):
        rect = self.boundingRect()
        corner = self._hit_corner(rect, event.pos())
        if self.isSelected() and corner:
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isSelected():
            rect = self.boundingRect()
            corner = self._hit_corner(rect, event.pos())
            if corner:
                self._resizing = True
                self._resize_corner = corner
                self._press_pos = QPointF(event.pos())
                self._press_poly = QPolygonF(self.polygon())
                self._press_rect = QRectF(rect)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._press_poly is not None and self._press_rect is not None and self._press_pos is not None:
            r = QRectF(self._press_rect)
            dp = event.pos() - self._press_pos

            if self._resize_corner == "TL":
                r.setTopLeft(r.topLeft() + dp)
            elif self._resize_corner == "TR":
                r.setTopRight(r.topRight() + dp)
            elif self._resize_corner == "BL":
                r.setBottomLeft(r.bottomLeft() + dp)
            elif self._resize_corner == "BR":
                r.setBottomRight(r.bottomRight() + dp)

            if r.width() < self.MIN_SIZE_PX:
                if self._resize_corner in ("TL", "BL"):
                    r.setLeft(r.right() - self.MIN_SIZE_PX)
                else:
                    r.setRight(r.left() + self.MIN_SIZE_PX)
            if r.height() < self.MIN_SIZE_PX:
                if self._resize_corner in ("TL", "TR"):
                    r.setTop(r.bottom() - self.MIN_SIZE_PX)
                else:
                    r.setBottom(r.top() + self.MIN_SIZE_PX)

            r = r.normalized()

            old = self._press_rect
            new = r
            sx = (new.width() / old.width()) if old.width() > 1e-9 else 1.0
            sy = (new.height() / old.height()) if old.height() > 1e-9 else 1.0

            oc = old.center()
            nc = new.center()

            new_poly = QPolygonF()
            for p in self._press_poly:
                vx = (p.x() - oc.x()) * sx
                vy = (p.y() - oc.y()) * sy
                new_poly.append(QPointF(nc.x() + vx, nc.y() + vy))

            self.setPolygon(new_poly)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_corner = None
            self._press_pos = None
            self._press_poly = None
            self._press_rect = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            self._draw_selection_outline(painter)


class ClickableLineItem(QGraphicsLineItem):
    """
    화살표 라인의 클릭 판정을 넓혀서,
    꼬리/중간 어디를 클릭해도 쉽게 선택되도록 하는 클래스.
    """
    def shape(self):
        # 기존 라인의 shape()을 두꺼운 경계로 확장하여 반환
        path = super().shape()
        stroker = QPainterPathStroker()
        stroker.setWidth(max(20, self.pen().widthF() * 3))  # 클릭 허용 폭 확대
        return stroker.createStroke(path)


class AnnotationScene(QGraphicsScene):
    """
    - 배경 이미지(QGraphicsPixmapItem)
    - AnnotationSet(텍스트, 화살표, 도형)을 실제로 그려주는 Scene
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._annotation_set: Optional[AnnotationSet] = None
        self._image_rect = None  # 실제 이미지 영역
        # AnnotationController가 연결될 자리
        self.controller = None

    # ─ 이미지 설정 ─
    def set_image(self, pixmap):
        if self._pixmap_item is not None:
            self.removeItem(self._pixmap_item)
            self._pixmap_item = None

        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self.addItem(self._pixmap_item)

        # 이미지 자체 영역(item-local)
        img_rect = self._pixmap_item.boundingRect()
        self._image_rect = img_rect  # 기준 L 계산 등에 사용

        # 기본 여백(이미지 최대 변의 10% + 최소 120px 보장)
        base_margin = max(img_rect.width(), img_rect.height()) * 0.10
        base_margin = max(base_margin, 120.0)

        # ✅ 핵심: 뷰포트 비율에 맞춰 "가로/세로 여백"을 추가로 확보
        extra_x = 0.0
        extra_y = 0.0

        views = self.views()
        if views:
            view = views[0]
            vp = view.viewport().size()
            vw = float(vp.width())
            vh = float(vp.height())

            # 뷰포트 크기가 유효할 때만 적용
            if vw > 10 and vh > 10:
                img_w = float(img_rect.width())
                img_h = float(img_rect.height())

                # 화면 비율(가로/세로)
                vp_aspect = vw / vh

                # "현재 이미지 높이"에 화면 비율을 적용했을 때 필요한 scene 폭
                desired_scene_w = img_h * vp_aspect
                if desired_scene_w > img_w:
                    extra_x = (desired_scene_w - img_w) * 0.5

                # 반대로 "현재 이미지 폭"에 화면 비율을 적용했을 때 필요한 scene 높이
                desired_scene_h = img_w / vp_aspect
                if desired_scene_h > img_h:
                    extra_y = (desired_scene_h - img_h) * 0.5

        # 최종 여백(기본 여백 vs 뷰포트 보정 여백 중 큰 값)
        margin_x = max(base_margin, extra_x)
        margin_y = max(base_margin, extra_y)

        # Scene 전체 영역 = 이미지 + (가로/세로 여백)
        scene_rect = img_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        self.setSceneRect(scene_rect)

        self._redraw_annotations()

    # ─ AnnotationSet 설정 ─
    def set_annotation_set(self, aset: AnnotationSet):
        self._annotation_set = aset
        self._redraw_annotations()

    # ─ 정규화 좌표 → 실제 Scene 좌표 ─
    def _norm_to_scene(self, p: Point2D) -> QPointF:
        if self._pixmap_item is None:
            return QPointF(0, 0)

        rect = self._pixmap_item.boundingRect()
        x = rect.left() + p.x * rect.width()
        y = rect.top() + p.y * rect.height()
        return QPointF(x, y)

    # ─ 현재 이미지 유무 확인 ─
    def has_image(self) -> bool:
        """배경 이미지가 로드되어 있는지 여부."""
        return self._pixmap_item is not None

    def image_scene_rect(self):
        """
        현재 배경 이미지의 Scene 좌표 기준 Rect를 반환합니다.
        이미지가 없으면 None.
        """
        if self._pixmap_item is None:
            return None
        # QGraphicsPixmapItem의 boundingRect는 item-local이므로 mapRectToScene으로 변환
        return self._pixmap_item.mapRectToScene(self._pixmap_item.boundingRect())

    def is_point_inside_image(self, pt: QPointF) -> bool:
        """
        Scene 좌표 pt가 이미지 영역 내부인지 여부
        """
        r = self.image_scene_rect()
        if r is None:
            return False
        return r.contains(pt)


    # ─ Scene 좌표 → 정규화 좌표(0~1) 변환 ─
    def scene_to_normalized(self, pt: QPointF) -> Point2D:
        """
        QGraphicsScene 좌표를 0~1 범위의 Point2D로 변환하여
        AnnotationSet에 저장할 때 사용.
        """
        if self._pixmap_item is None:
            return Point2D(0.0, 0.0)

        rect = self._pixmap_item.boundingRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return Point2D(0.0, 0.0)

        x = (pt.x() - rect.left()) / rect.width()
        y = (pt.y() - rect.top()) / rect.height()
        return Point2D(x, y)

    # ─ 전체 다시 그리기 ─
    def _redraw_annotations(self):
        # 배경 이미지는 남기고 나머지 제거
        for item in list(self.items()):
            if item is self._pixmap_item:
                continue
            # ★ 이미 다른 Scene 으로 옮겨졌거나 제거된 아이템은 건너뜀
            if item.scene() is not self:
                continue
            self.removeItem(item)

        if self._pixmap_item is None or self._annotation_set is None:
            return

        aset = self._annotation_set

        # main_point
        if aset.main_point and aset.main_point.visible:
            self._draw_text(aset.main_point)

        # texts
        for t in aset.texts:
            if t.visible:
                self._draw_text(t)

        # arrows
        for a in aset.arrows:
            if a.visible:
                self._draw_arrow(a)

        # shapes
        for s in aset.shapes:
            if s.visible:
                self._draw_shape(s)

    # ─ Text 그리기 ─ #
    def _draw_text(self, ann: TextAnnotation):
        """
        TextAnnotation을 화면에 그립니다.
        HTML 대신 QFont 기반으로 렌더링하여
        - 더블클릭 수정시 글자 크기 유지
        - 텍스트 중심 정렬 정확
        - 색상/스타일 깨짐 방지
        """
        # 기준점(정규화 → Scene)
        anchor = self._norm_to_scene(ann.position)

        # EditableTextItem 사용
        item = EditableTextItem(ann, self)

        # 텍스트 설정
        item.setPlainText(ann.text)

        # 폰트 크기 유지
        font = QFont()
        font.setPointSize(int(ann.font_size))
        item.setFont(font)

        # 색상 유지
        item.setDefaultTextColor(QColor(ann.color))

        # Z index
        item.setZValue(ann.z_index + 30)

        # 위치 계산 (boundingRect 기반)
        rect = item.boundingRect()
        x = anchor.x() - rect.width() / 2.0
        y = anchor.y() - rect.height() / 2.0
        item.setPos(x, y)

        # Annotation 연결
        item.annotation = ann
        self.addItem(item)


    # ─ Arrow 그리기 ─
    def _draw_arrow(self, ann: ArrowAnnotation):
        """
        ArrowAnnotation을 화면 전체가 클릭 가능한 하나의 QGraphicsPathItem 으로 그립니다.
        (선 + 화살촉 합친 단일 객체 → 꼬리/중간/어디 클릭해도 선택 가능)
        """
        from PySide6.QtGui import QPainterPath, QPen, QBrush, QColor, QPainterPathStroker
        from PySide6.QtWidgets import QGraphicsPathItem

        # ─ 1) 정규화 좌표 → Scene 좌표
        start = self._norm_to_scene(ann.start)
        end = self._norm_to_scene(ann.end)

        # ─ 2) 화살선 Path 생성
        path = QPainterPath()
        path.moveTo(end)
        path.lineTo(start)

        # ─ 3) 화살촉 계산
        dx = start.x() - end.x()
        dy = start.y() - end.y()
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / length, dy / length

        rect = self._pixmap_item.boundingRect()
        diag = (rect.width() ** 2 + rect.height() ** 2) ** 0.5
        head_len = ann.head_size * diag
        head_width = head_len * 0.6

        bx = start.x() - ux * head_len
        by = start.y() - uy * head_len

        nx, ny = -uy, ux

        p1 = start
        p2 = QPointF(bx + nx * head_width / 2.0, by + ny * head_width / 2.0)
        p3 = QPointF(bx - nx * head_width / 2.0, by - ny * head_width / 2.0)

        # 화살촉도 Path에 포함
        path.moveTo(p1)
        path.lineTo(p2)
        path.lineTo(p3)
        path.closeSubpath()

        # ─ 4) 단일 Path Item 생성
        arrow_item = QGraphicsPathItem(path)

        pen = QPen(QColor(ann.color))
        pen.setWidthF(max(2.0, ann.line_width))
        arrow_item.setPen(pen)
        arrow_item.setBrush(QBrush(QColor(ann.color)))
        arrow_item.setZValue(ann.z_index + 20)

        # Annotation 연결
        arrow_item.annotation = ann
        arrow_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        arrow_item.setFlag(QGraphicsItem.ItemIsMovable, True)

        # ─ 5) 클릭 판정 확장 (선+화살촉 전체를 클릭 가능하게)
        class ClickableArrowItem(QGraphicsPathItem):
            def shape(self):
                stroker = QPainterPathStroker()
                stroker.setWidth(max(20, pen.widthF() * 3))  # 꼬리/중간 클릭 허용 폭 확대
                return stroker.createStroke(super().shape())

        click_item = ClickableArrowItem(path)
        click_item.setPen(pen)
        click_item.setBrush(QBrush(QColor(ann.color)))
        click_item.setZValue(ann.z_index + 20)
        click_item.annotation = ann
        click_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        click_item.setFlag(QGraphicsItem.ItemIsMovable, True)

        self.addItem(click_item)




    # ─ Shape 그리기 ─
    def _draw_shape(self, ann: ShapeAnnotation):
        # 펜 생성
        pen = QPen(QColor(ann.stroke_color))
        pen.setWidthF(ann.stroke_width)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)

        # 브러시 생성
        brush = QBrush()
        if ann.fill_color:
            brush = QBrush(QColor(ann.fill_color))

        # 정규화 좌표 → Scene 좌표
        pts_scene: List[QPointF] = [self._norm_to_scene(p) for p in ann.points]

        # ─ 1) 기준면 L (DATUM_L) : 이미지 모서리 바로 바깥에서 안쪽으로 향하는 두 화살표 ─
        if ann.shape_type == ShapeType.DATUM_L:
            if len(ann.points) < 1:
                return

            p_norm = ann.points[0]
            nx, ny = p_norm.x, p_norm.y

            # 이미지 표시 영역
            if self._image_rect is not None:
                img_rect = self._image_rect
            elif self._pixmap_item is not None:
                img_rect = self._pixmap_item.boundingRect()
            else:
                img_rect = self.sceneRect()

            L = img_rect.left()
            R = img_rect.right()
            T = img_rect.top()
            B = img_rect.bottom()

            corners = {
                "TL": (0.0, 0.0, QPointF(L, T)),
                "TR": (1.0, 0.0, QPointF(R, T)),
                "BL": (0.0, 1.0, QPointF(L, B)),
                "BR": (1.0, 1.0, QPointF(R, B)),
            }

            # 가장 가까운 코너 선택
            best_key = None
            best_d2 = None
            best_corner = None
            for key, (cx, cy, cpt) in corners.items():
                dx, dy = nx - cx, ny - cy
                d2 = dx * dx + dy * dy
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    best_key = key
                    best_corner = cpt

            # 이미지 크기 정보
            page_w = img_rect.width()
            page_h = img_rect.height()
            base = min(page_w, page_h)

            # 비율 설정 (두께 5~15에서도 자연스럽게)
            offset = ann.stroke_width * 3                      # 코너 밖으로 나가는 거리
            arm_len = max(base * 0.10, ann.stroke_width * 10)  # 화살표 길이
            head_len = ann.stroke_width * 4                    # 화살촉 길이
            head_w = head_len * 0.6                            # 화살촉 폭

            cx, cy = best_corner.x(), best_corner.y()

            # 코너별 origin과 두 화살표 방향 (origin → end 방향으로 화살표 머리)
            if best_key == "TL":
                origin = QPointF(cx - offset, cy - offset)
                h_end = QPointF(cx + arm_len, cy - offset)   # →
                v_end = QPointF(cx - offset, cy + arm_len)   # ↓
            elif best_key == "TR":
                origin = QPointF(cx + offset, cy - offset)
                h_end = QPointF(cx - arm_len, cy - offset)   # ←
                v_end = QPointF(cx + offset, cy + arm_len)   # ↓
            elif best_key == "BL":
                origin = QPointF(cx - offset, cy + offset)
                h_end = QPointF(cx + arm_len, cy + offset)   # →
                v_end = QPointF(cx - offset, cy - arm_len)   # ↑
            else:  # BR
                origin = QPointF(cx + offset, cy + offset)
                h_end = QPointF(cx - arm_len, cy + offset)   # ←
                v_end = QPointF(cx + offset, cy - arm_len)   # ↑

            def draw_arrow(start: QPointF, end: QPointF):
                line_item = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
                line_item.setPen(pen)
                line_item.setZValue(ann.z_index)

                line_item.annotation = ann
                line_item.setFlag(QGraphicsItem.ItemIsSelectable, True)

                self.addItem(line_item)

                dx = end.x() - start.x()
                dy = end.y() - start.y()
                length = (dx * dx + dy * dy) ** 0.5 or 1.0
                ux, uy = dx / length, dy / length

                bx = end.x() - ux * head_len
                by = end.y() - uy * head_len

                nx2, ny2 = -uy, ux

                p1 = end
                p2 = QPointF(bx + nx2 * head_w / 2, by + ny2 * head_w / 2)
                p3 = QPointF(bx - nx2 * head_w / 2, by - ny2 * head_w / 2)

                poly = QPolygonF([p1, p2, p3])
                head_item = QGraphicsPolygonItem(poly)
                head_item.setBrush(QBrush(QColor(ann.stroke_color)))
                head_item.setPen(pen)
                head_item.setZValue(ann.z_index)

                head_item.annotation = ann
                head_item.setFlag(QGraphicsItem.ItemIsSelectable, True)

                self.addItem(head_item)

            # 두 방향 화살표 생성
            draw_arrow(origin, h_end)
            draw_arrow(origin, v_end)
            return

        # ─ 2) 일반 사각 / 원 / 타원 ─
        if ann.shape_type in (ShapeType.RECT, ShapeType.CIRCLE, ShapeType.ELLIPSE):
            if len(pts_scene) < 2:
                return
            p1, p2 = pts_scene[0], pts_scene[1]
            x = min(p1.x(), p2.x())
            y = min(p1.y(), p2.y())
            w = abs(p1.x() - p2.x())
            h = abs(p1.y() - p2.y())

            if ann.shape_type == ShapeType.RECT:
                item = ResizableRectItem(x, y, w, h)
            elif ann.shape_type == ShapeType.CIRCLE:
                d = min(w, h)
                item = ResizableEllipseItem(x, y, d, d)
            else:  # ELLIPSE
                item = ResizableEllipseItem(x, y, w, h)

            item.setPen(pen)
            if ann.fill_color:
                item.setBrush(brush)

            item.setZValue(ann.z_index +10)

            item.annotation = ann
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            item.setFlag(QGraphicsItem.ItemIsMovable, True)

            # ★ 추가 (드래그 안 끊기게)
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            item.setAcceptHoverEvents(True)

            self.addItem(item)
            return

        # ─ 3) 그 외 (TRIANGLE, STAR, POLYGON 등) ─
        if len(pts_scene) < 3:
            return
        poly = QPolygonF(pts_scene)
        item = ResizablePolygonItem(poly)
        item.setPen(pen)
        if ann.fill_color:
            item.setBrush(brush)
        item.setZValue(ann.z_index + 10)

        item.annotation = ann
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.ItemIsMovable, True)

        
        # ★ 추가 (드래그 유지 보정)
        item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        item.setAcceptHoverEvents(True)

        self.addItem(item)

    # ─ 선택된 Annotation 삭제 ─
    def snap_linked_arrow_tails_to_text_edges(self):
        """
        parent_id로 연결된(묶인) 텍스트의 '실제 박스 외곽'에
        화살표 꼬리(end)를 스냅시켜 텍스트를 가리지 않게 합니다.
        - 최초 생성 직후에도 호출하면 '중앙→외곽 점프'가 사라집니다.
        """
        if self._annotation_set is None or self._pixmap_item is None:
            return

        from PySide6.QtWidgets import QGraphicsTextItem, QGraphicsItem
        from PySide6.QtCore import QRectF
        from .annotations import TextAnnotation

        def edge_point_on_rect_towards(rect: QRectF, toward: QPointF, pad_px: float = 3.0) -> QPointF:
            c = rect.center()
            dx = toward.x() - c.x()
            dy = toward.y() - c.y()

            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                return c

            half_w = rect.width() / 2.0
            half_h = rect.height() / 2.0

            sx = half_w / abs(dx) if abs(dx) > 1e-9 else float("inf")
            sy = half_h / abs(dy) if abs(dy) > 1e-9 else float("inf")
            s = min(sx, sy)

            px = c.x() + dx * s
            py = c.y() + dy * s
            p = QPointF(px, py)

            length = (dx * dx + dy * dy) ** 0.5 or 1.0
            ux, uy = dx / length, dy / length
            return QPointF(p.x() + ux * pad_px, p.y() + uy * pad_px)

        changed = False

        for item in self.items():
            if not isinstance(item, QGraphicsTextItem):
                continue

            ann = getattr(item, "annotation", None)
            if not isinstance(ann, TextAnnotation):
                continue
            if not getattr(ann, "parent_id", None):
                continue

            # 부모 화살표 찾기
            parent_arrow = None
            for a in self._annotation_set.arrows:
                if a.id == ann.parent_id:
                    parent_arrow = a
                    break
            if parent_arrow is None:
                continue

            # 텍스트 박스 Scene rect
            text_rect_scene = item.mapRectToScene(item.boundingRect())
            # 화살표 시작점(Scene)
            start_scene = self._norm_to_scene(parent_arrow.start)

            attach_scene = edge_point_on_rect_towards(text_rect_scene, start_scene, pad_px=3.0)
            parent_arrow.end = self.scene_to_normalized(attach_scene)
            changed = True

        if changed:
            self._redraw_annotations()


    def delete_selected_annotations(self):
        """
        선택된 QGraphicsItem 들에 연결된 Annotation(Text/Arrow/Shape)을
        AnnotationSet에서 제거하고, 장면을 다시 그립니다.

        - TextAnnotation 단독 선택 시: 해당 텍스트만 삭제
        - ShapeAnnotation 삭제 시: 해당 도형 + parent_id == 도형.id 인 텍스트도 함께 삭제
        - ArrowAnnotation 삭제 시: 해당 화살표 + parent_id == 화살표.id 인 텍스트도 함께 삭제
        """
        if self._annotation_set is None:
            return

        selected_items = self.selectedItems()
        if not selected_items:
            return

        from .annotations import TextAnnotation, ArrowAnnotation, ShapeAnnotation

        # 중복 없이 삭제할 Annotation 수집
        to_delete: List[object] = []
        for item in selected_items:
            ann = getattr(item, "annotation", None)
            if ann is not None and ann not in to_delete:
                to_delete.append(ann)

        if not to_delete:
            return

        # 실제 삭제 처리
        for ann in to_delete:

            # 1) 텍스트 단독 삭제
            if isinstance(ann, TextAnnotation):
                if ann in self._annotation_set.texts:
                    self._annotation_set.texts.remove(ann)

            # 2) 도형 삭제 시 → 도형 + 묶인 텍스트 삭제
            elif isinstance(ann, ShapeAnnotation):
                shape_id = ann.id

                if ann in self._annotation_set.shapes:
                    self._annotation_set.shapes.remove(ann)

                # 이 도형에 parent_id 로 묶인 텍스트들 삭제
                texts_to_remove = [
                    t for t in self._annotation_set.texts
                    if t.parent_id == shape_id
                ]
                for t in texts_to_remove:
                    self._annotation_set.texts.remove(t)

            # 3) 화살표 삭제 시 → 화살표 + 묶인 텍스트 삭제
            elif isinstance(ann, ArrowAnnotation):
                arrow_id = ann.id

                if ann in self._annotation_set.arrows:
                    self._annotation_set.arrows.remove(ann)

                # 이 화살표에 parent_id 로 묶인 텍스트들 삭제
                texts_to_remove = [
                    t for t in self._annotation_set.texts
                    if t.parent_id == arrow_id
                ]
                for t in texts_to_remove:
                    self._annotation_set.texts.remove(t)

        # 다시 그리기
        self._redraw_annotations()



    def _update_shape_annotation_from_item(self, item: QGraphicsItem, ann: ShapeAnnotation):
        """
        화면에서 실제로 이동된 도형(QGraphicsItem)의 최신 기하를 읽어
        AnnotationSet.ShapeAnnotation.points 에 정확히 저장한다.
        RECT / CIRCLE / ELLIPSE / TRIANGLE / POLYGON / STAR 모두 오차 없이 처리한다.
        """
        from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem

        # ─ RECT / CIRCLE / ELLIPSE ─
        if ann.shape_type in (ShapeType.RECT, ShapeType.CIRCLE, ShapeType.ELLIPSE):
            if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                rect_scene = item.mapRectToScene(item.rect())
                p1 = self.scene_to_normalized(rect_scene.topLeft())
                p2 = self.scene_to_normalized(rect_scene.bottomRight())
                ann.points = [p1, p2]
            return

        # ─ TRIANGLE / STAR / POLYGON (모든 폴리곤 계열) ─
        if ann.shape_type in (ShapeType.TRIANGLE, ShapeType.POLYGON, ShapeType.STAR):
            if isinstance(item, QGraphicsPolygonItem):
                poly = item.polygon()
                pts = [item.mapToScene(p) for p in poly]
                ann.points = [self.scene_to_normalized(p) for p in pts]
            return

        # ─ DATUM_L 등 기타는 안 건드림 ─
        return

    def _edge_point_on_rect_towards(self, rect: QRectF, toward: QPointF, pad_px: float = 3.0) -> QPointF:
        """
        rect(텍스트 박스)의 중심에서 toward(화살표 시작점) 방향으로 나아갈 때,
        rect의 외곽선과 만나는 점을 계산하여 반환합니다.
        - pad_px 만큼 rect 바깥쪽으로 살짝 빼서 텍스트 테두리와 겹치지 않게 합니다.
        """
        c = rect.center()
        dx = toward.x() - c.x()
        dy = toward.y() - c.y()

        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return c

        # 중심→toward 방향으로 rect 경계에 닿는 스케일 계산
        half_w = rect.width() / 2.0
        half_h = rect.height() / 2.0

        sx = half_w / abs(dx) if abs(dx) > 1e-9 else float("inf")
        sy = half_h / abs(dy) if abs(dy) > 1e-9 else float("inf")
        s = min(sx, sy)

        px = c.x() + dx * s
        py = c.y() + dy * s
        p = QPointF(px, py)

        # 경계에서 pad_px 만큼 바깥으로(화살표가 박스 테두리를 파고들지 않게)
        length = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / length, dy / length
        return QPointF(p.x() + ux * pad_px, p.y() + uy * pad_px)

    def _sync_text_annotations_from_items(self):
        """
        Scene 상에서 이동된 텍스트(QGraphicsTextItem)의 위치를
        AnnotationSet의 TextAnnotation.position(정규화)로 반영.

        복구 규칙:
        - 텍스트 이동 시:
            · parent_id가 ArrowAnnotation이면: 화살표 end를 텍스트 외곽으로 스냅(기존 규칙)
            · parent_id가 ShapeAnnotation이면: 부모 도형도 같은 dx,dy로 함께 이동(묶음 동작 복구)
        """
        if self._annotation_set is None or self._pixmap_item is None:
            return

        from PySide6.QtWidgets import QGraphicsItem
        from PySide6.QtCore import QPointF
        from .annotations import TextAnnotation, ShapeAnnotation, ArrowAnnotation

        # id → 객체 빠른 조회
        arrows_by_id = {a.id: a for a in self._annotation_set.arrows}
        shapes_by_id = {s.id: s for s in self._annotation_set.shapes}

        for item in self.items():
            ann = getattr(item, "annotation", None)
            if not isinstance(ann, TextAnnotation):
                continue
            if not (item.flags() & QGraphicsItem.ItemIsMovable):
                continue

            # 이동 전 텍스트 중심(Scene) (데이터 기준)
            old_center_scene = self._norm_to_scene(ann.position)

            # 이동 후 텍스트 중심(Scene) (아이템 기준)
            text_rect_scene = item.mapRectToScene(item.boundingRect())
            new_center_scene = text_rect_scene.center()

            dx = new_center_scene.x() - old_center_scene.x()
            dy = new_center_scene.y() - old_center_scene.y()

            # 1) 텍스트 위치 갱신(정규화)
            ann.position = self.scene_to_normalized(new_center_scene)

            parent_id = getattr(ann, "parent_id", None)
            if not parent_id:
                continue

            # 2-A) parent가 화살표인 경우: 기존 규칙 유지(외곽 스냅)
            parent_arrow = arrows_by_id.get(parent_id)
            if isinstance(parent_arrow, ArrowAnnotation):
                # 텍스트 박스(Scene) 외곽에 화살표 end를 붙임
                bbox = text_rect_scene  # 이미 SceneRect
                end_scene = self._norm_to_scene(parent_arrow.end)

                # 네 변 중 가장 가까운 점 계산
                left = bbox.left()
                right = bbox.right()
                top = bbox.top()
                bottom = bbox.bottom()

                candidates = [
                    QPointF(left, min(max(end_scene.y(), top), bottom)),
                    QPointF(right, min(max(end_scene.y(), top), bottom)),
                    QPointF(min(max(end_scene.x(), left), right), top),
                    QPointF(min(max(end_scene.x(), left), right), bottom),
                ]
                snap = min(candidates, key=lambda p: (p.x() - end_scene.x()) ** 2 + (p.y() - end_scene.y()) ** 2)
                parent_arrow.end = self.scene_to_normalized(snap)
                continue

            # 2-B) parent가 도형인 경우: 텍스트 이동량만큼 도형도 같이 이동(묶음 복구)
            parent_shape = shapes_by_id.get(parent_id)
            if isinstance(parent_shape, ShapeAnnotation):
                if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                    continue

                moved_points = []
                for p in parent_shape.points:
                    ps = self._norm_to_scene(p)
                    ps2 = QPointF(ps.x() + dx, ps.y() + dy)
                    moved_points.append(self.scene_to_normalized(ps2))
                parent_shape.points = moved_points

    def _redraw_annotations_preserve_selection(self) -> None:
        """
        _redraw_annotations()는 아이템을 전부 제거/재생성하므로 선택이 풀립니다.
        따라서 redraw 전 선택된 annotation id를 저장하고,
        redraw 후 동일 id를 가진 아이템을 다시 선택 상태로 복원합니다.
        """
        selected_ids = set()
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            ann_id = getattr(ann, "id", None)
            if ann_id:
                selected_ids.add(ann_id)

        self._redraw_annotations()

        if not selected_ids:
            return

        for item in self.items():
            ann = getattr(item, "annotation", None)
            ann_id = getattr(ann, "id", None)
            if ann_id and ann_id in selected_ids:
                item.setSelected(True)


    def update_selected_text_font_size(self, size: float):
        """선택된 텍스트의 글씨 크기를 변경합니다. (선택 유지)"""
        if self._annotation_set is None:
            return

        from .annotations import TextAnnotation

        changed = False
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if isinstance(ann, TextAnnotation):
                ann.font_size = size
                changed = True

        if changed:
            self._redraw_annotations_preserve_selection()


    def update_selected_stroke_width(self, width: float):
        """선택된 도형/화살표의 선 두께를 변경합니다. (선택 유지)"""
        if self._annotation_set is None:
            return

        from .annotations import ShapeAnnotation, ArrowAnnotation

        w = float(width)
        changed = False

        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)

            # 도형: stroke_width가 실제 렌더링에 사용됨
            if isinstance(ann, ShapeAnnotation):
                ann.stroke_width = w
                changed = True

            # 화살표: 렌더링은 line_width를 사용함 (width 아님)
            elif isinstance(ann, ArrowAnnotation):
                ann.line_width = w
                changed = True

        if changed:
            self._redraw_annotations_preserve_selection()



    def update_selected_shape_stroke_color(self, color: str):
        """선택된 도형의 선색을 변경합니다. (선택 유지)"""
        if self._annotation_set is None:
            return

        from .annotations import ShapeAnnotation

        changed = False
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if isinstance(ann, ShapeAnnotation):
                ann.stroke_color = color
                changed = True

        if changed:
            self._redraw_annotations_preserve_selection()

    def update_selected_shape_fill_color(self, fill_color: Optional[str]):
        """선택된 도형의 채움색을 변경합니다. (선택 유지)"""
        if self._annotation_set is None:
            return

        from .annotations import ShapeAnnotation

        changed = False
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if isinstance(ann, ShapeAnnotation):
                ann.fill_color = fill_color
                changed = True

        if changed:
            self._redraw_annotations_preserve_selection()

    def update_selected_text_color(self, color: str):
        """선택된 텍스트의 색상을 변경합니다. (선택 유지)"""
        if self._annotation_set is None:
            return

        from .annotations import TextAnnotation

        changed = False
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if isinstance(ann, TextAnnotation):
                ann.color = color
                changed = True

        if changed:
            self._redraw_annotations_preserve_selection()


    def update_selected_arrow_color(self, color: str):
        """선택된 화살표의 색상을 변경합니다. (선택 유지)"""
        if self._annotation_set is None:
            return

        from .annotations import ArrowAnnotation

        changed = False
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if isinstance(ann, ArrowAnnotation):
                ann.color = color
                changed = True

        if changed:
            self._redraw_annotations_preserve_selection()


    def mousePressEvent(self, event):
        """
        - 왼쪽 클릭:
            · 빈 공간 → AnnotationController 에 넘겨서 새 도형/화살표 드로잉 시작
            · 도형/화살표/텍스트 위 → Qt 기본 동작(선택/이동)
        - 오른쪽 클릭:
            · 기본 동작(아이템 쪽 처리 또는 Qt 기본 메뉴)
            (텍스트 편집은 EditableTextItem 내부 mousePressEvent가 직접 처리)
        """
        # 왼쪽 버튼 : 그리기 / 선택
        if event.button() == Qt.LeftButton and self.controller is not None:
            view = self.views()[0] if self.views() else None
            transform = view.transform() if view is not None else QTransform()
            item = self.itemAt(event.scenePos(), transform)

            if item is None or not hasattr(item, "annotation"):
                # 빈 공간 클릭 → 새 도형/화살표 드로잉 시작
                self.controller.handle_mouse_press(event)
                return  # Qt 기본 처리 호출하지 않음

        # 그 외(오른쪽 클릭 등)는 기본 동작(선택/이동/컨텍스트 메뉴)
        super().mousePressEvent(event)

        # ─ 도형 우클릭 시 묶음 해제 메뉴 ─
        if event.button() == Qt.RightButton:
            item = self.itemAt(event.scenePos(), QTransform())
            if item is not None and hasattr(item, "annotation"):
                ann = item.annotation

                # 도형인 경우 → parent_id 가진 텍스트들을 해제할 수 있어야 함
                from .annotations import ShapeAnnotation
                if isinstance(ann, ShapeAnnotation):

                    from PySide6.QtWidgets import QMenu
                    menu = QMenu()
                    ungroup_action = menu.addAction("묶음 해제")

                    chosen = menu.exec(event.screenPos())
                    if chosen == ungroup_action:

                        # 이 도형을 parent_id 로 가진 모든 텍스트 해제
                        for t in self._annotation_set.texts:
                            if t.parent_id == ann.id:
                                t.parent_id = None

                        self._redraw_annotations()
                        return

            # 도형이 아니면 기본 동작
            return super().mousePressEvent(event)




    def mouseMoveEvent(self, event):
        """
        드로잉 중이면 → Controller에 전달,
        아니면 → Qt 기본으로 도형 이동/선택 박스 등 처리.
        """
        if self.controller is not None and getattr(self.controller, "_is_drawing", False):
            self.controller.handle_mouse_move(event)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        드로잉 중이면 → Controller에 드래그 종료 전달,
        아니면 → Qt 기본 처리 후,
        이동된 도형/텍스트의 위치를 AnnotationSet에 반영하되,
        ★ 텍스트 편집 중일 때는 절대로 redraw 하지 않는다 ★
        """

        # 0) 텍스트 편집 중이면 redraw 금지
        for item in self.selectedItems():
            if isinstance(item, EditableTextItem):
                if item.textInteractionFlags() & Qt.TextEditorInteraction:
                    super().mouseReleaseEvent(event)
                    return

        # 1) 드로잉 중이면 컨트롤러로 넘김
        if self.controller is not None and getattr(self.controller, "_is_drawing", False):
            self.controller.handle_mouse_release(event)
            return

        # 2) Qt 기본 처리(선택, 이동 등)
        super().mouseReleaseEvent(event)

        # 3) 선택된 Annotation들의 id 저장
        selected_ids = set()
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if ann is not None and hasattr(ann, "id"):
                selected_ids.add(ann.id)

        # 4) 동기화 순서가 핵심 (덮어쓰기 방지)
        #    - 텍스트(직접 이동) 먼저 반영
        #    - 그 다음 도형 이동을 반영하며 parent_id 텍스트도 같이 이동
        #    - 마지막에 화살표 이동 반영
        self._sync_text_annotations_from_items()
        self._sync_shape_annotations_from_items()
        self._sync_arrow_annotations_from_items()

        # 5) redraw
        self._redraw_annotations()

        # 6) 선택 상태 복원
        if selected_ids:
            for item in self.items():
                ann = getattr(item, "annotation", None)
                if ann is not None and hasattr(ann, "id") and ann.id in selected_ids:
                    item.setSelected(True)



    def _sync_shape_annotations_from_items(self):
        """
        Scene 상에서 이동된 도형(선택된 ShapeAnnotation)의 위치를
        AnnotationSet.ShapeAnnotation.points에 반영하고,
        해당 도형을 parent_id 로 가진 TextAnnotation 들도 동일한 이동량(dx, dy) 만큼 함께 이동시킵니다.

        - 여러 도형이 선택된 경우, 선택된 도형들만 처리합니다.
        - RECT / CIRCLE / ELLIPSE / TRIANGLE / POLYGON / STAR 모두
          꼭짓점의 bounding box 중심을 기준으로 이동량을 계산합니다.
        """
        if self._annotation_set is None or self._pixmap_item is None:
            return

        from .annotations import ShapeAnnotation, TextAnnotation
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem

        # 선택된 아이템들만 처리
        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if not isinstance(ann, ShapeAnnotation):
                continue
            if not (item.flags() & QGraphicsItem.ItemIsMovable):
                continue

            # ─ 1) 이동 전 도형 중심(Scene) : Annotation.points 기반 bounding box
            pts_old_scene = [self._norm_to_scene(p) for p in ann.points]
            if not pts_old_scene:
                continue

            min_x_old = min(p.x() for p in pts_old_scene)
            max_x_old = max(p.x() for p in pts_old_scene)
            min_y_old = min(p.y() for p in pts_old_scene)
            max_y_old = max(p.y() for p in pts_old_scene)
            old_center = QPointF(
                (min_x_old + max_x_old) / 2.0,
                (min_y_old + max_y_old) / 2.0,
            )

            # ─ 2) 이동 후 도형 중심(Scene) : 실제 item 기하 기반 bounding box
            pts_new_scene: List[QPointF] = []

            if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                rect_scene = item.mapRectToScene(item.boundingRect())
                pts_new_scene = [rect_scene.topLeft(), rect_scene.bottomRight()]
            elif isinstance(item, QGraphicsPolygonItem):
                poly = item.polygon()
                pts_new_scene = [item.mapToScene(p) for p in poly]
            else:
                continue  # 그 외는 현재 묶음 이동 대상에서 제외

            if not pts_new_scene:
                continue

            min_x_new = min(p.x() for p in pts_new_scene)
            max_x_new = max(p.x() for p in pts_new_scene)
            min_y_new = min(p.y() for p in pts_new_scene)
            max_y_new = max(p.y() for p in pts_new_scene)
            new_center = QPointF(
                (min_x_new + max_x_new) / 2.0,
                (min_y_new + max_y_new) / 2.0,
            )

            dx = new_center.x() - old_center.x()
            dy = new_center.y() - old_center.y()

            # ─ 3) 도형 자체 Annotation.points 를 새 위치로 업데이트
            self._update_shape_annotation_from_item(item, ann)

            if abs(dx) < 1e-3 and abs(dy) < 1e-3:
                continue

            # ─ 4) 이 도형을 parent_id 로 가진 텍스트들만 dx,dy 만큼 이동
            for t in self._annotation_set.texts:
                if t.parent_id != ann.id:
                    continue

                t_old_scene = self._norm_to_scene(t.position)
                t_new_scene = QPointF(
                    t_old_scene.x() + dx,
                    t_old_scene.y() + dy
                )
                t.position = self.scene_to_normalized(t_new_scene)

    def _sync_arrow_annotations_from_items(self):
        """
        선택된 화살표 아이템 이동을 ArrowAnnotation.start/end에 반영.
        - 화살표가 여러 QGraphicsItem으로 구성될 수 있으므로,
          같은 ArrowAnnotation에 대해 중복 적용되지 않도록 ann.id로 1회만 반영합니다.
        """
        if self._annotation_set is None or self._pixmap_item is None:
            return

        from .annotations import ArrowAnnotation, TextAnnotation

        # ann.id -> (item, movement_score)
        moved_map = {}

        for item in self.selectedItems():
            ann = getattr(item, "annotation", None)
            if not isinstance(ann, ArrowAnnotation):
                continue
            if not (item.flags() & QGraphicsItem.ItemIsMovable):
                continue

            dx = item.pos().x()
            dy = item.pos().y()
            score = abs(dx) + abs(dy)

            if score < 1e-6:
                continue

            prev = moved_map.get(ann.id)
            if prev is None or score > prev[1]:
                moved_map[ann.id] = (item, score)

        if not moved_map:
            return

        for ann_id, (item, _) in moved_map.items():
            ann = getattr(item, "annotation", None)
            if not isinstance(ann, ArrowAnnotation):
                continue

            dx = item.pos().x()
            dy = item.pos().y()

            start_scene = self._norm_to_scene(ann.start)
            end_scene = self._norm_to_scene(ann.end)

            new_start_scene = QPointF(start_scene.x() + dx, start_scene.y() + dy)
            new_end_scene = QPointF(end_scene.x() + dx, end_scene.y() + dy)

            ann.start = self.scene_to_normalized(new_start_scene)
            ann.end = self.scene_to_normalized(new_end_scene)

            # 자식 텍스트는 end에 붙여서 같이 이동(연동)
            for t in self._annotation_set.texts:
                if isinstance(t, TextAnnotation) and getattr(t, "parent_id", None) == ann.id:
                    t.position = ann.end

            # 중복 이동 방지: 이동된 아이템만 원점 복귀
            item.setPos(0, 0)

        # 이동 후에도 외곽 스냅 유지
        if hasattr(self, "snap_linked_arrow_tails_to_text_edges"):
            self.snap_linked_arrow_tails_to_text_edges()



    def mouseDoubleClickEvent(self, event):
        """
        - 텍스트: 더블클릭 시 QGraphicsItem(EditableTextItem)의 기본 동작(편집 모드)을 사용
        - 도형: 더블클릭 시 도형 중앙에 텍스트 입력
        """
        # 클릭 위치에서 실제 아이템 찾기 (뷰의 transform 반영)
        view = self.views()[0] if self.views() else None
        transform = view.transform() if view is not None else QTransform()
        item = self.itemAt(event.scenePos(), transform)

        if item is not None and hasattr(item, "annotation"):
            from .annotations import ShapeAnnotation
            from PySide6.QtWidgets import QInputDialog
            ann = item.annotation

            # 도형 더블클릭만 여기서 처리
            if isinstance(ann, ShapeAnnotation):
                text, ok = QInputDialog.getText(
                    None,
                    "도형 텍스트 입력",
                    "도형 중앙에 표시할 텍스트를 입력하십시오:",
                )
                if not ok or not (text.strip()):
                    return

                value = text.strip()

                # 도형 중앙(scene 좌표) 계산
                br = item.boundingRect()
                center_local = br.center()
                center_scene = item.mapToScene(center_local)
                center_norm = self.scene_to_normalized(center_scene)

                # 현재 UI 설정에서 텍스트 색/크기 가져오기
                color = "Yellow"
                font_size = 14
                ctrl = getattr(self, "controller", None)
                if ctrl is not None:
                    ts = getattr(ctrl, "tool_state", None)
                    if ts is not None:
                        if getattr(ts, "text_color", None):
                            color = ts.text_color
                        if getattr(ts, "text_size", None) is not None:
                            try:
                                font_size = int(ts.text_size)
                            except (TypeError, ValueError):
                                pass

                # 텍스트 추가 + 도형과 그룹으로 연결
                new_text = self._annotation_set.add_text(
                    position=center_norm,
                    text=value,
                    color=color,
                    font_size=font_size,
                )
                new_text.parent_id = ann.id  # 이 텍스트는 이 도형에 묶임

                self._redraw_annotations()
                return

        # 텍스트나 다른 아이템의 더블클릭은 기본 동작에 맡기기
        # → EditableTextItem.mouseDoubleClickEvent 가 호출되어 편집 모드로 진입함
        super().mouseDoubleClickEvent(event)


