"""
F04 经纬度矩形框选地图工具。

处理流程：
1. 在 QgsMapCanvas 上左键拖拽矩形
2. 使用 QgsRubberBand 显示框选范围
3. 将矩形四角从 Canvas CRS 转换为 EPSG:4326
4. 通过 Qt 信号返回 west / south / east / north
"""

from __future__ import annotations

import math

from qgis.PyQt.QtCore import (
    Qt,
    pyqtSignal,
)

from qgis.PyQt.QtGui import QColor

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsPointXY,
    QgsProject,
)

from qgis.gui import (
    QgsMapTool,
    QgsRubberBand,
)


WGS84_CRS = QgsCoordinateReferenceSystem(
    "EPSG:4326"
)


class RectangleSelectionMapTool(QgsMapTool):
    """在 QgsMapCanvas 上通过左键拖拽选择矩形范围。"""

    rectangle_selected = pyqtSignal(dict)
    selection_failed = pyqtSignal(str)

    def __init__(self, canvas):
        super().__init__(canvas)

        self._start_point = None
        self._dragging = False

        self._rubber_band = QgsRubberBand(
            canvas,
            Qgis.GeometryType.Polygon,
        )

        self._rubber_band.setStrokeColor(
            QColor(0, 120, 215, 220)
        )

        self._rubber_band.setFillColor(
            QColor(0, 120, 215, 50)
        )

        self._rubber_band.setWidth(2)

        self.setCursor(
            Qt.CrossCursor
        )

    def _rectangle_corners(
        self,
        start_point: QgsPointXY,
        end_point: QgsPointXY,
    ) -> list[QgsPointXY]:
        """返回 Canvas CRS 中矩形的四个角。"""

        return [
            QgsPointXY(
                start_point.x(),
                start_point.y(),
            ),
            QgsPointXY(
                end_point.x(),
                start_point.y(),
            ),
            QgsPointXY(
                end_point.x(),
                end_point.y(),
            ),
            QgsPointXY(
                start_point.x(),
                end_point.y(),
            ),
        ]

    def _update_rubber_band(
        self,
        end_point: QgsPointXY,
    ) -> None:
        """按当前拖拽终点更新矩形橡皮筋。"""

        corners = self._rectangle_corners(
            self._start_point,
            end_point,
        )

        self._rubber_band.reset(
            Qgis.GeometryType.Polygon
        )

        # 重复首点以闭合矩形边界。
        closed_corners = corners + [corners[0]]

        for index, point in enumerate(closed_corners):
            self._rubber_band.addPoint(
                point,
                index == len(closed_corners) - 1,
            )

        self._rubber_band.show()

    def _clear_selection(self) -> None:
        """清除当前拖拽状态和矩形橡皮筋。"""

        self._start_point = None
        self._dragging = False

        self._rubber_band.reset(
            Qgis.GeometryType.Polygon
        )

        self._rubber_band.hide()

    def _to_longitude_latitude_bounds(
        self,
        corners: list[QgsPointXY],
    ) -> dict:
        """把 Canvas 矩形四角转换为 WGS 84 经纬度范围。"""

        canvas_crs = (
            self.canvas()
            .mapSettings()
            .destinationCrs()
        )

        if not canvas_crs.isValid():
            raise RuntimeError(
                "Canvas destination CRS 无效。"
            )

        # 派生图层可能使用 UTM，框选结果仍统一返回经纬度。
        if canvas_crs == WGS84_CRS:
            geographic_corners = corners
        else:
            coordinate_transform = (
                QgsCoordinateTransform(
                    canvas_crs,
                    WGS84_CRS,
                    QgsProject.instance(),
                )
            )

            geographic_corners = [
                coordinate_transform.transform(point)
                for point in corners
            ]

        longitudes = [
            point.x()
            for point in geographic_corners
        ]

        latitudes = [
            point.y()
            for point in geographic_corners
        ]

        coordinates = longitudes + latitudes

        if not all(
            math.isfinite(value)
            for value in coordinates
        ):
            raise ValueError(
                "框选范围无法转换为有效经纬度。"
            )

        west = min(longitudes)
        east = max(longitudes)
        south = min(latitudes)
        north = max(latitudes)

        if not (
            -180.0 <= west < east <= 180.0
            and -90.0 <= south < north <= 90.0
        ):
            raise ValueError(
                "框选结果不是有效的经纬度矩形范围。"
            )

        return {
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        }

    def canvasPressEvent(self, event) -> None:
        """记录左键拖拽起点。"""

        if event.button() != Qt.LeftButton:
            return

        self._clear_selection()
        self._start_point = event.mapPoint()
        self._dragging = True

    def canvasMoveEvent(self, event) -> None:
        """拖拽过程中更新矩形橡皮筋。"""

        if not self._dragging:
            return

        self._update_rubber_band(
            event.mapPoint()
        )

    def canvasReleaseEvent(self, event) -> None:
        """完成左键矩形框选并发送经纬度范围。"""

        # 单击或直线拖拽没有可裁剪面积。
        if (
            event.button() != Qt.LeftButton
            or not self._dragging
        ):
            return

        end_point = event.mapPoint()
        self._dragging = False

        if (
            self._start_point.x() == end_point.x()
            or self._start_point.y() == end_point.y()
        ):
            self._clear_selection()
            self.selection_failed.emit(
                "请拖拽形成具有宽度和高度的矩形范围。"
            )
            return

        self._update_rubber_band(
            end_point
        )

        corners = self._rectangle_corners(
            self._start_point,
            end_point,
        )

        try:
            bounds = self._to_longitude_latitude_bounds(
                corners
            )
        except (
            ValueError,
            RuntimeError,
            QgsCsException,
        ) as exc:
            self._clear_selection()
            self.selection_failed.emit(
                str(exc)
            )
            return

        self.rectangle_selected.emit(
            bounds
        )

    def deactivate(self) -> None:
        """停用地图工具时清除矩形。"""

        self._clear_selection()
        super().deactivate()
