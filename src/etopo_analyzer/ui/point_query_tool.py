"""
F03 鼠标单点高程 / 水深查询地图工具。

处理流程：
1. 接收 QgsMapCanvas 左键点击
2. 获取 Canvas 地图坐标
3. 转换为 WGS 84 经纬度（EPSG:4326）
4. 调用核心 query_point_elevation()
5. 通过 Qt 信号返回查询结果或错误信息
"""

from __future__ import annotations

from qgis.PyQt.QtCore import (
    Qt,
    pyqtSignal,
)

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsPointXY,
    QgsProject,
)

from qgis.gui import QgsMapTool

from etopo_analyzer.core.point_query import (
    query_point_elevation,
)


WGS84_CRS = QgsCoordinateReferenceSystem(
    "EPSG:4326"
)


class PointQueryMapTool(QgsMapTool):
    """
    在 QgsMapCanvas 上通过左键点击执行单点查询。
    """

    query_succeeded = pyqtSignal(dict)
    query_failed = pyqtSignal(str)

    def __init__(
        self,
        canvas,
        raster_path: str,
    ):
        super().__init__(canvas)

        self._raster_path = raster_path

        self.setCursor(
            Qt.CrossCursor
        )

    def _to_longitude_latitude(
        self,
        map_point: QgsPointXY,
    ) -> tuple[float, float]:
        """把 Canvas 地图坐标转换为 EPSG:4326 经纬度。"""

        canvas_crs = (
            self.canvas()
            .mapSettings()
            .destinationCrs()
        )

        if not canvas_crs.isValid():
            raise RuntimeError(
                "Canvas destination CRS 无效。"
            )

        if canvas_crs == WGS84_CRS:
            longitude = map_point.x()
            latitude = map_point.y()
        else:
            coordinate_transform = (
                QgsCoordinateTransform(
                    canvas_crs,
                    WGS84_CRS,
                    QgsProject.instance(),
                )
            )

            geographic_point = (
                coordinate_transform.transform(
                    map_point
                )
            )

            longitude = geographic_point.x()
            latitude = geographic_point.y()

        return longitude, latitude

    def query_map_point(
        self,
        map_point: QgsPointXY,
    ) -> dict:
        """查询一个 Canvas 地图坐标并返回核心查询结果。"""

        longitude, latitude = (
            self._to_longitude_latitude(
                map_point
            )
        )

        return query_point_elevation(
            self._raster_path,
            longitude,
            latitude,
        )

    def canvasReleaseEvent(self, event) -> None:
        """处理 Canvas 鼠标释放事件。"""

        if event.button() != Qt.LeftButton:
            return

        try:
            result = self.query_map_point(
                event.mapPoint()
            )
        except (
            FileNotFoundError,
            ValueError,
            RuntimeError,
            QgsCsException,
        ) as exc:
            self.query_failed.emit(
                str(exc)
            )
            return

        self.query_succeeded.emit(
            result
        )
