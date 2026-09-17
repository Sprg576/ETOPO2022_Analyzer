"""F08 绘制事件、取消与坐标转换测试。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsPointXY, QgsProject,
)
from qgis.gui import QgsMapCanvas
from etopo_analyzer.ui.profile_selection_tool import ProfileSelectionMapTool, ProfileOverlay


def event(x=0, y=0, button=Qt.LeftButton):
    result = Mock()
    result.button.return_value = button
    result.mapPoint.return_value = QgsPointXY(x, y)
    return result


class TestProfileSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], True)
            cls.app.initQgis()

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.tool = ProfileSelectionMapTool(self.canvas)
        self.canvas.setMapTool(self.tool)
        self.results = []
        self.errors = []
        self.tool.profile_selected.connect(self.results.append)
        self.tool.selection_failed.connect(self.errors.append)

    def tearDown(self):
        self.canvas.unsetMapTool(self.tool)
        self.tool = None
        self.canvas.close()
        self.canvas.deleteLater()
        self.canvas = None

    def test_right_click_finishes_confirmed_nodes(self):
        self.tool.canvasReleaseEvent(event(120, 24))
        self.tool.canvasMoveEvent(event(121, 24))
        self.assertGreater(self.tool._rubber_band.numberOfVertices(), 1)
        self.tool.canvasReleaseEvent(event(121, 24))
        self.tool.canvasReleaseEvent(event(122, 25, Qt.RightButton))
        self.assertEqual(self.results, [[(120, 24), (121, 24)]])
        self.assertEqual(self.tool._rubber_band.numberOfVertices(), 0)

    def test_double_click_release_does_not_repeat_result(self):
        self.tool.canvasReleaseEvent(event(120, 24))
        self.tool.canvasReleaseEvent(event(121, 24))
        self.tool.canvasDoubleClickEvent(event(121, 24))
        self.tool.canvasReleaseEvent(event(121, 24))
        self.assertEqual(len(self.results), 1)
        self.assertEqual(len(self.results[0]), 2)

    def test_too_few_nodes_and_cancel(self):
        self.tool.canvasReleaseEvent(event(120, 24))
        self.tool.finish()
        self.assertEqual(len(self.errors), 1)
        cancelled = []
        self.tool.selection_cancelled.connect(lambda: cancelled.append(True))
        key = Mock()
        key.key.return_value = Qt.Key_Escape
        self.tool.keyPressEvent(key)
        self.assertEqual(cancelled, [True])
        self.assertEqual(self.tool.vertices, [])
        self.assertEqual(self.results, [])

    def test_projected_canvas_emits_wgs84(self):
        target = QgsCoordinateReferenceSystem("EPSG:32651")
        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), target, QgsProject.instance())
        self.canvas.setDestinationCrs(target)
        for lon, lat in ((120, 24), (121, 25)):
            point = transform.transform(QgsPointXY(lon, lat))
            self.tool.canvasReleaseEvent(event(point.x(), point.y()))
        self.tool.finish()
        for got, expected in zip(self.results[0], ((120, 24), (121, 25))):
            self.assertAlmostEqual(got[0], expected[0], places=7)
            self.assertAlmostEqual(got[1], expected[1], places=7)

    def test_deactivate_clears_draft_but_keeps_result_overlay(self):
        overlay = ProfileOverlay(self.canvas)
        overlay.set_vertices([(120, 24), (121, 25)])
        self.tool.canvasReleaseEvent(event(120, 24))
        self.tool.deactivate()
        self.assertEqual(self.tool.vertices, [])
        self.assertGreater(overlay.band.numberOfVertices(), 2)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:32651"))
        self.assertGreater(overlay.band.asGeometry().boundingBox().xMinimum(), 1000)
        overlay.clear()
        self.assertEqual(overlay.band.numberOfVertices(), 0)
