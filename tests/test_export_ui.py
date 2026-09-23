"""真实 QGIS 地图渲染、导出线程和界面状态集成。"""

import gc
from pathlib import Path
import tempfile
import time
import unittest
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QTimer
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtTest import QTest
from test_raster_statistics import create_dem
from etopo_analyzer.core.layer_manager import create_raster_layer
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
from etopo_analyzer.ui.export_dialog import ExportDialog
from etopo_analyzer.visualization.map_export import export_map
from etopo_analyzer.core.export_service import ExportCancelled
from etopo_analyzer.core.region_comparison import compare_regions


class TestExportUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], True)
            cls.app.initQgis()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "dem.tif"
        create_dem(self.source, [[-2, -1, 0, 1, 2]] * 3, transform=(120, .1, 0, 24, 0, -.1))
        self.layer = create_raster_layer(str(self.source))
        QgsProject.instance().addMapLayer(self.layer)
        self.window = ETOPOAnalyzerMainWindow()
        from processing_test_support import allow_unsaved_discard
        allow_unsaved_discard(self)
        from processing_test_support import wrap_processing_calls
        wrap_processing_calls(self.window)
        self.window.map_canvas.freeze(True)
        self.window.show_layer(self.layer)
        self.dialog = None

    def tearDown(self):
        if self.dialog:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        self.window.close()
        self.window.map_canvas.stopRendering()
        self.window.map_canvas.setLayers([])
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.window = None
        self.layer = None
        QgsProject.instance().clear()
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 30
        while self.dialog.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.assertIsNone(self.dialog.worker)

    def test_map_png_extent_and_profile(self):
        extent = self.window.map_canvas.extent()
        metadata = export_map(self.root, self.window.map_canvas, "中文地图", 1800, 300,
                              {"vertices": [(120.05, 23.75), (120.45, 23.95)]})
        image = QImage(str(self.root / "map.png"))
        self.assertFalse(image.isNull())
        self.assertEqual(image.width(), 1800)
        self.assertEqual(self.window.map_canvas.extent(), extent)
        self.assertEqual(len(metadata["layers"]), 1)
        self.assertEqual(metadata["profile_vertices"][0], (120.05, 23.75))
        for actual, expected in zip(metadata["extent"], [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]):
            self.assertAlmostEqual(actual, expected, delta=extent.width() / 500)

    def test_map_cancel(self):
        with self.assertRaises(ExportCancelled):
            export_map(self.root, self.window.map_canvas, "取消", cancelled=lambda: True)
        self.assertFalse((self.root / "map.png").exists())

    def test_csv_worker_and_no_source_switch(self):
        self.window._statistics_result = calculate_raster_statistics(str(self.source))
        self.dialog = ExportDialog(self.window, "csv")
        self.dialog.directory.setText(str(self.root))
        self.dialog.name.setText("result")
        self.dialog.start()
        self.wait()
        self.assertEqual(self.dialog.output, str(self.root / "result"))
        self.assertTrue((self.root / "result/summary.csv").exists())
        self.assertEqual(self.window._active_raster_path, str(self.source))

    def test_raster_default_active_not_display(self):
        self.dialog = ExportDialog(self.window, "raster")
        self.assertEqual(self.dialog.choice.currentData(), self.layer.id())
        self.dialog.directory.setText(str(self.root))
        self.dialog.name.setText("copy")
        self.dialog.start()
        self.wait()
        self.assertTrue((self.root / "copy/raster.tif").exists(), self.dialog.message.text())

    def test_stale_result_rejected(self):
        self.window._statistics_result = calculate_raster_statistics(str(self.source))
        self.window._statistics_result["source"]["mtime_ns"] -= 1
        self.dialog = ExportDialog(self.window, "csv")
        self.dialog.directory.setText(str(self.root))
        self.dialog.start()
        self.assertIsNone(self.dialog.worker)
        self.assertIn("来源文件已变化", self.dialog.message.text())

    def test_map_dialog_package(self):
        self.dialog = ExportDialog(self.window, "map")
        self.dialog.directory.setText(str(self.root))
        self.dialog.name.setText("map")
        self.dialog.start()
        self.assertTrue((self.root / "map/map.png").exists(), self.dialog.message.text())
        self.assertTrue((self.root / "map/manifest.json").exists())

    def test_hidden_options_and_busy_controls(self):
        self.dialog = ExportDialog(self.window, "raster")
        self.assertTrue(self.dialog.pixels.isHidden())
        self.assertTrue(self.dialog.dpi.isHidden())
        self.assertTrue(self.dialog.title.isHidden())
        self.assertTrue(self.dialog.include_profile.isHidden())
        self.dialog.set_busy(True)
        self.assertFalse(self.dialog.browse_button.isEnabled())

    def test_comparison_export_after_active_dem_switch(self):
        result = compare_regions(str(self.source), str(self.source))
        self.window._comparison_controls.result = result
        another = self.root / "another.tif"
        create_dem(another, [[1, 2, 3]])
        layer = create_raster_layer(str(another))
        QgsProject.instance().addMapLayer(layer)
        self.window.show_layer(layer)
        self.dialog = ExportDialog(self.window, "csv")
        self.dialog.choice.setCurrentIndex(self.dialog.choice.findData("comparison"))
        self.dialog.directory.setText(str(self.root))
        self.dialog.name.setText("compare")
        self.dialog.start()
        self.wait()
        self.assertTrue((self.root / "compare/distribution.csv").exists(), self.dialog.message.text())
        self.assertEqual(self.window._active_raster_path, str(another))

    def test_menu_availability_and_analysis_busy(self):
        menu = self.window.export_actions["map"].associatedWidgets()[0]
        menu.aboutToShow.emit()
        self.assertTrue(self.window.export_actions["map"].isEnabled())
        self.assertTrue(self.window.export_actions["raster"].isEnabled())
        self.assertFalse(self.window.export_actions["csv"].isEnabled())
        self.window._statistics_worker = object()
        try:
            menu.aboutToShow.emit()
            self.assertTrue(all(not action.isEnabled() for action in self.window.export_actions.values()))
        finally:
            self.window._statistics_worker = None

    def test_map_with_contours_and_rotation(self):
        self.window.contour_interval_spin.setValue(1)
        self.window.create_contours()
        self.assertIsNotNone(self.window._contour_layer)
        self.window.map_canvas.setRotation(12)
        metadata = export_map(self.root, self.window.map_canvas, "等高线与 DEM", 1800)
        self.assertEqual(metadata["rotation"], 12)
        self.assertEqual(len(metadata["layers"]), 2)
        self.assertIn("qgis", metadata["layers"][0]["style_xml"])

    def test_cancel_worker_keeps_dialog_alive_until_finished(self):
        self.window._statistics_result = calculate_raster_statistics(str(self.source))
        self.dialog = ExportDialog(self.window, "csv")
        self.dialog.directory.setText(str(self.root))
        self.dialog.name.setText("cancel")
        from unittest.mock import patch
        def until_cancelled(folder, kind, result, cancelled):
            while not cancelled():
                time.sleep(.001)
            raise ExportCancelled("导出已取消。")
        with patch("etopo_analyzer.ui.export_worker.export_csv", side_effect=until_cancelled):
            self.dialog.start()
            self.dialog.reject()
            self.assertIsNotNone(self.dialog.worker)
            self.wait()
        self.assertFalse((self.root / "cancel").exists())
        self.assertIn("取消", self.dialog.message.text())
