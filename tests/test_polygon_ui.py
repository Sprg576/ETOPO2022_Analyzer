"""多边形绘制、真实后台任务、范围失效、保存恢复及历史。"""

from copy import deepcopy
import json
import time
from types import SimpleNamespace
import unittest

from qgis.PyQt.QtCore import Qt, QPoint
from qgis.PyQt.QtTest import QTest
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject, QgsRectangle
import test_processing_tasks as fixtures
from test_polygon_statistics import polygon


class TestPolygonUI(unittest.TestCase):
    setUpClass = classmethod(fixtures.TestProcessingTasks.setUpClass.__func__)

    def setUp(self):
        fixtures.TestProcessingTasks.setUp(self)
        self.controls = self.window.polygon_controls
        self.a = polygon([[120, 23.97], [120.02, 23.97], [120.02, 24], [120, 24]])
        self.b = polygon([[120.03, 23.97], [120.05, 23.97], [120.05, 24], [120.03, 24]])

    def tearDown(self):
        self.window.cancel_statistics()
        self.window._comparison_controls.cancel()
        self.wait_finished()
        fixtures.TestProcessingTasks.tearDown(self)

    def wait_finished(self):
        deadline = time.monotonic() + 20
        while self.window._task_controls.busy() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.app.processEvents()
        self.assertFalse(self.window._task_controls.busy())

    def select_ab(self):
        c = self.window._comparison_controls
        for combo in (c.region_a, c.region_b):
            combo.setCurrentIndex(combo.findData(self.window._active_raster_layer.id()))
        return c

    def test_statistics_worker_scope_disable_and_stale_result(self):
        w = self.window
        self.controls.set_polygon("statistics", self.a)
        w.create_statistics()
        self.assertFalse(self.controls.panels[0].isEnabled())
        self.wait_finished()
        old_result = w._statistics_result
        self.assertIsNotNone(old_result, w.statistics_message.text())
        self.assertEqual(old_result["statistics"]["valid_count"], 6)
        self.assertAlmostEqual(old_result["statistics"]["mean_m"], -1.5)
        self.assertIn("多边形", w._statistics_panel.summary_table.item(0, 1).text())
        old_id = w._statistics_task_id
        self.controls.set_polygon("statistics", self.b)
        self.assertIsNone(w._statistics_result)
        w._statistics_succeeded(old_id, old_result)
        self.assertIsNone(w._statistics_result)
        self.controls.checks["statistics"].setChecked(False)
        self.assertIsNone(self.controls.overlays["statistics"].polygon)
        w.create_statistics()
        self.wait_finished()
        self.assertEqual(w._statistics_result["statistics"]["valid_count"], 15)

    def test_missing_geometry_does_not_fall_back_to_full_dem(self):
        self.controls.checks["statistics"].setChecked(True)
        self.window.create_statistics()
        self.assertIsNone(self.window._statistics_worker)
        self.assertIn("请先绘制", self.window.statistics_message.text())
        c = self.select_ab()
        self.controls.set_polygon("a", self.a)
        c.start()
        self.assertIsNone(c.worker)
        self.assertIn("请先绘制", c.message.text())

    def test_same_dem_comparison_swap_and_roundtrip(self):
        w = self.window
        c = self.select_ab()
        self.controls.set_polygon("a", self.a)
        self.controls.set_polygon("b", self.b)
        c.start()
        self.wait_finished()
        self.assertIsNotNone(c.result, c.message.text())
        self.assertAlmostEqual(c.result["differences"]["mean_m"], 3)
        c.swap()
        self.assertEqual(self.controls.roi("a"), self.b)
        self.assertIsNone(c.result)
        c.start()
        self.wait_finished()
        self.assertAlmostEqual(c.result["differences"]["mean_m"], -3)
        filename = self.root / "polygon.etopo.json"
        w.workspace_controls.save(filename)
        self.controls.set_polygon("b", None)
        self.assertEqual(w.workspace_controls.load(filename), [])
        self.assertEqual(self.controls.roi("a"), self.b)
        self.assertEqual(self.controls.roi("b"), self.a)
        self.assertAlmostEqual(c.result["differences"]["mean_m"], -3)

    def test_statistics_history_and_disabled_polygon_roundtrip(self):
        w = self.window
        self.controls.set_polygon("statistics", self.a)
        w.create_statistics()
        self.wait_finished()
        result = deepcopy(w._statistics_result)
        self.controls.set_polygon("statistics", self.b)
        w.workspace_controls.restore_result("statistics", result)
        self.assertEqual(self.controls.roi("statistics"), self.a)
        self.assertEqual(w._statistics_result["statistics"]["valid_count"], 6)
        self.controls.checks["statistics"].setChecked(False)
        w.create_statistics()
        self.wait_finished()
        filename = self.root / "disabled.etopo.json"
        w.workspace_controls.save(filename)
        self.assertEqual(w.workspace_controls.load(filename), [])
        self.assertIsNone(self.controls.roi("statistics"))
        self.assertEqual(self.controls.polygons["statistics"], self.a)
        self.assertEqual(w._statistics_result["statistics"]["valid_count"], 15)

    def test_bad_workspace_polygon_preserves_session(self):
        self.controls.set_polygon("statistics", self.a)
        state = self.window.workspace_controls.capture()
        state["roi"]["polygons"]["statistics"] = dict(type="Polygon", coordinates=[[[0, 0], [1, 1]]])
        filename = self.root / "invalid.etopo.json"
        filename.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.window.workspace_controls.load(filename)
        self.assertIs(self.window._active_raster_layer, self.layer)
        self.assertEqual(self.controls.roi("statistics"), self.a)

    def test_projected_map_drawing_undo_invalid_and_escape(self):
        canvas = self.window.map_canvas
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
            canvas.mapSettings().destinationCrs(), QgsProject.instance())
        self.controls.set_polygon("statistics", self.a)
        self.controls.start_drawing("statistics")
        tool = self.controls.tool
        tool.append(transform.transform(QgsPointXY(120, 24)))
        tool.append(transform.transform(QgsPointXY(120.01, 24)))
        tool.finish()
        self.assertEqual(self.controls.roi("statistics"), self.a)
        self.assertIn("三个", self.window.statistics_message.text())
        tool.keyPressEvent(SimpleNamespace(key=lambda: Qt.Key_Backspace))
        self.assertEqual(len(tool.vertices), 1)
        tool.keyPressEvent(SimpleNamespace(key=lambda: Qt.Key_Escape))
        self.assertIsNot(canvas.mapTool(), tool)
        self.assertEqual(self.controls.roi("statistics"), self.a)
        self.controls.start_drawing("statistics")
        for point in self.b["coordinates"][0][:-1]:
            tool.append(transform.transform(QgsPointXY(*point)))
        tool.finish()
        for expected, actual in zip(self.b["coordinates"][0], self.controls.roi("statistics")["coordinates"][0]):
            for x, y in zip(expected, actual):
                self.assertAlmostEqual(x, y, places=8)
        self.assertEqual(tool.preview.band.numberOfVertices(), 0)

    def test_real_mouse_clicks_finish_polygon(self):
        w = self.window
        w.show()
        self.app.processEvents()
        canvas = w.map_canvas
        canvas.setExtent(QgsRectangle(119.99, 23.96, 120.06, 24.01))
        self.controls.start_drawing("statistics")
        for point in self.a["coordinates"][0][:-1]:
            pixel = canvas.getCoordinateTransform().transform(QgsPointXY(*point))
            QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(round(pixel.x()), round(pixel.y())))
        QTest.mouseClick(canvas.viewport(), Qt.RightButton)
        self.assertIsNotNone(self.controls.roi("statistics"))
        self.assertEqual(len(self.controls.roi("statistics")["coordinates"][0]), 5)
        self.assertIsNot(canvas.mapTool(), self.controls.tool)
