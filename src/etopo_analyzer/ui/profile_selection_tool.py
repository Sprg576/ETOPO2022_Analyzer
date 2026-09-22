"""F08 地图折线绘制与大地线路径覆盖。"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsCsException, QgsPointXY, QgsProject,
)
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker

from etopo_analyzer.core.profile_analysis import densify_profile_path, profile_path


class ProfileOverlay:
    """独立保存成功剖面，画布 CRS 变化后重新定位。"""

    def __init__(self, canvas):
        self.canvas = canvas
        self.vertices = []
        self.sample_point = None
        self.sample_marker = QgsVertexMarker(canvas)
        self.sample_marker.setColor(QColor("#E63946"))
        self.sample_marker.setIconSize(12)
        self.sample_marker.setPenWidth(3)
        self.sample_marker.hide()
        self.band = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self.band.setColor(QColor("#C94A38"))
        self.band.setWidth(2)
        self.markers = [QgsVertexMarker(canvas), QgsVertexMarker(canvas)]
        for marker in self.markers:
            marker.setColor(QColor("#C94A38"))
            marker.setIconSize(9)
            marker.setPenWidth(2)
            marker.hide()
        canvas.destinationCrsChanged.connect(self.refresh)

    def set_vertices(self, vertices):
        self.vertices = list(vertices)
        self.refresh()

    def refresh(self):
        self.show_sample(self.sample_point)
        self.band.reset(Qgis.GeometryType.Line)
        for marker in self.markers:
            marker.hide()
        if not self.vertices:
            return
        try:
            transform = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:4326"),
                self.canvas.mapSettings().destinationCrs(), QgsProject.instance(),
            )
            points = [transform.transform(QgsPointXY(*p))
                      for p in densify_profile_path(self.vertices)]
            for index, point in enumerate(points):
                self.band.addPoint(point, index == len(points) - 1)
            for marker, point in zip(self.markers, (points[0], points[-1])):
                marker.setCenter(point)
                marker.show()
        except (ValueError, RuntimeError, QgsCsException):
            self.band.reset(Qgis.GeometryType.Line)

    def clear(self):
        self.show_sample(None)
        self.set_vertices([])

    def show_sample(self, point):
        self.sample_point = point
        self.sample_marker.hide()
        if point is not None:
            try:
                transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                    self.canvas.mapSettings().destinationCrs(), QgsProject.instance())
                self.sample_marker.setCenter(transform.transform(QgsPointXY(*point)))
                self.sample_marker.show()
            except (ValueError, RuntimeError, QgsCsException):
                pass


class ProfileSelectionMapTool(QgsMapTool):
    """左键加点，右键或双击完成，Esc 取消。"""

    profile_selected = pyqtSignal(list)
    selection_failed = pyqtSignal(str)
    selection_cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.vertices = []
        self._finished = False
        self._rubber_band = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self._rubber_band.setColor(QColor("#C94A38"))
        self._rubber_band.setWidth(2)
        self.setCursor(Qt.CrossCursor)

    def activate(self):
        self.clear()
        self._finished = False
        super().activate()

    def clear(self):
        self.vertices = []
        self._rubber_band.reset(Qgis.GeometryType.Line)

    def _geographic_point(self, point):
        source = self.canvas().mapSettings().destinationCrs()
        if not source.isValid():
            raise ValueError("地图坐标系无效。")
        transform = QgsCoordinateTransform(
            source, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance(),
        )
        result = transform.transform(point)
        return result.x(), result.y()

    def _draw(self, vertices):
        self._rubber_band.reset(Qgis.GeometryType.Line)
        if len(vertices) < 2:
            return
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            self.canvas().mapSettings().destinationCrs(), QgsProject.instance(),
        )
        points = densify_profile_path(vertices)
        for index, point in enumerate(points):
            self._rubber_band.addPoint(
                transform.transform(QgsPointXY(*point)), index == len(points) - 1,
            )

    def _append(self, point):
        vertex = self._geographic_point(point)
        if not self.vertices or vertex != self.vertices[-1]:
            candidate = [*self.vertices, vertex]
            if len(candidate) > 1:
                profile_path(candidate)
            self.vertices = candidate
        self._draw(self.vertices)

    def finish(self):
        if self._finished:
            return
        try:
            points, _, _ = profile_path(self.vertices)
        except ValueError as exc:
            self.selection_failed.emit(str(exc))
            return
        self._finished = True
        self.clear()
        self.profile_selected.emit(points)

    def canvasReleaseEvent(self, event):
        if self._finished:
            return
        try:
            if event.button() == Qt.LeftButton:
                self._append(event.mapPoint())
            elif event.button() == Qt.RightButton:
                self.finish()
        except (ValueError, RuntimeError, QgsCsException) as exc:
            self.selection_failed.emit(str(exc))

    def canvasDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton or self._finished:
            return
        try:
            self._append(event.mapPoint())
            self.finish()
        except (ValueError, RuntimeError, QgsCsException) as exc:
            self.selection_failed.emit(str(exc))

    def canvasMoveEvent(self, event):
        if not self.vertices or self._finished:
            return
        try:
            vertex = self._geographic_point(event.mapPoint())
            self._draw([*self.vertices, vertex])
        except (ValueError, RuntimeError, QgsCsException):
            self._draw(self.vertices)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear()
            self.selection_cancelled.emit()

    def deactivate(self):
        self.clear()
        super().deactivate()
