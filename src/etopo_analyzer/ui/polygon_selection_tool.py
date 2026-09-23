"""地图多边形绘制；坐标保存为 WGS84，经纬度平面直线连接。"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (Qgis, QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsProject)
from qgis.gui import QgsMapTool, QgsRubberBand
from etopo_analyzer.core.polygon_roi import normalize_polygon


class PolygonOverlay:
    def __init__(self, canvas, color):
        self.canvas = canvas
        self.polygon = None
        self.band = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self.band.setStrokeColor(QColor(color))
        fill = QColor(color)
        fill.setAlpha(30)
        self.band.setFillColor(fill)
        self.band.setWidth(2)
        canvas.destinationCrsChanged.connect(self.refresh)

    def set_polygon(self, polygon):
        self.polygon = polygon
        self.refresh()

    def refresh(self):
        self.band.reset(Qgis.GeometryType.Polygon)
        if self.polygon is None:
            return
        geometry = QgsGeometry.fromPolygonXY([
            [QgsPointXY(*point) for point in ring] for ring in self.polygon["coordinates"]])
        # 在经纬度平面加密，投影后的边界与实际统计多边形一致。
        geometry = geometry.densifyByDistance(.1)
        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
            self.canvas.mapSettings().destinationCrs(), QgsProject.instance())
        try:
            geometry.transform(transform)
            self.band.setToGeometry(geometry, None)
        except RuntimeError:
            self.band.reset(Qgis.GeometryType.Polygon)


class PolygonSelectionMapTool(QgsMapTool):
    polygon_selected = pyqtSignal(object)
    selection_failed = pyqtSignal(str)
    selection_cancelled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.vertices = []
        self.finished = False
        self.preview = PolygonOverlay(canvas, "#D09818")
        self.setCursor(Qt.CrossCursor)

    def activate(self):
        self.vertices = []
        self.finished = False
        self.preview.set_polygon(None)
        super().activate()

    def geographic_point(self, point):
        transform = QgsCoordinateTransform(self.canvas().mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        point = transform.transform(point)
        return [point.x(), point.y()]

    def draw(self, points):
        self.preview.set_polygon(dict(type="Polygon", coordinates=[points + points[:1]]) if points else None)

    def append(self, point):
        vertex = self.geographic_point(point)
        if not self.vertices or vertex != self.vertices[-1]:
            self.vertices.append(vertex)
        self.draw(self.vertices)

    def finish(self):
        if self.finished:
            return
        try:
            polygon = normalize_polygon(dict(type="Polygon", coordinates=[self.vertices]))
        except ValueError as exc:
            self.selection_failed.emit(str(exc))
            return
        self.finished = True
        self.preview.set_polygon(None)
        self.polygon_selected.emit(polygon)

    def canvasReleaseEvent(self, event):
        if self.finished:
            return
        try:
            if event.button() == Qt.LeftButton:
                self.append(event.mapPoint())
            elif event.button() == Qt.RightButton:
                self.finish()
        except (ValueError, RuntimeError) as exc:
            self.selection_failed.emit(str(exc))

    def canvasDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self.finished:
            try:
                self.append(event.mapPoint())
                self.finish()
            except (ValueError, RuntimeError) as exc:
                self.selection_failed.emit(str(exc))

    def canvasMoveEvent(self, event):
        if self.vertices and not self.finished:
            try:
                self.draw(self.vertices + [self.geographic_point(event.mapPoint())])
            except (ValueError, RuntimeError):
                pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
        elif event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self.vertices = self.vertices[:-1]
            self.draw(self.vertices)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.finish()

    def deactivate(self):
        self.vertices = []
        self.preview.set_polygon(None)
        super().deactivate()
