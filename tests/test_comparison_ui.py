"""F10 真实 Qt 线程与独立区域状态验收。"""

import gc
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QPoint
from qgis.PyQt.QtTest import QTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.core.layer_manager import add_raster_layer
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
from test_raster_statistics import create_dem


class TestComparisonUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], True)
            cls.app.initQgis()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_a = Path(self.temp.name) / "a.tif"
        self.path_b = Path(self.temp.name) / "b.tif"
        create_dem(self.path_a, [[-2, 0, 2]] * 3, transform=(120, .1, 0, 24, 0, -.1))
        create_dem(self.path_b, [[0, 2, 4]] * 3, transform=(121, .1, 0, 24, 0, -.1))
        self.a, self.b = [add_raster_layer(str(p)) for p in (self.path_a, self.path_b)]
        self.window = ETOPOAnalyzerMainWindow()
        from processing_test_support import allow_unsaved_discard
        allow_unsaved_discard(self)
        from processing_test_support import wrap_processing_calls
        wrap_processing_calls(self.window)
        self.window.map_canvas.freeze(True)
        self.window.show_layer(self.a)
        self.window.show_layer(self.b, layer_group="裁剪结果")
        self.controls = self.window._comparison_controls
        self.controls.region_a.setCurrentIndex(self.controls.region_a.findData(self.a.id()))
        self.controls.region_b.setCurrentIndex(self.controls.region_b.findData(self.b.id()))

    def wait_finished(self):
        deadline = time.monotonic() + 20
        while (self.controls.worker is not None or self.window._statistics_worker is not None) and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.app.processEvents()
        self.assertIsNone(self.controls.worker)
        self.assertIsNone(self.window._statistics_worker)

    def start(self):
        self.controls.start()
        self.wait_finished()

    def tearDown(self):
        self.controls.cancel()
        self.window.cancel_statistics()
        self.wait_finished()
        self.window.close()
        self.window.map_canvas.stopRendering()
        self.window.map_canvas.setLayers([])
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.window = self.controls = self.a = self.b = None
        QgsProject.instance().clear()
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.temp.cleanup()

    def test_real_worker_panel_and_active_source_unchanged(self):
        self.window.show()
        self.start()
        self.assertIsNotNone(self.controls.result, self.controls.message.text())
        self.assertEqual(self.controls.result["differences"]["mean_m"], 2)
        self.assertEqual(self.controls.panel.tabs.count(), 4)
        self.assertIs(self.window._active_raster_layer, self.b)
        self.assertTrue(self.controls.show_action.isEnabled())
        self.assertFalse(self.controls.cancel_action.isEnabled())
        self.controls.panel.tabs.setCurrentIndex(3)
        for width, height in ((1360, 820), (1080, 640)):
            self.window.resize(width, height)
            self.controls.resize_result()
            QTest.qWait(50)
            canvas = self.controls.panel.canvases[1]
            bottom = canvas.mapTo(self.window.map_splitter, QPoint(0, canvas.height())).y()
            self.assertLessEqual(bottom, self.window.map_splitter.height())

    def test_source_switch_new_layer_and_display_keep_selection(self):
        self.start()
        result = self.controls.result
        self.window.show_layer(self.a)
        self.assertIs(self.controls.result, result)
        new = add_raster_layer(str(self.path_a), "另一裁剪结果")
        self.window.show_layer(new, layer_group="裁剪结果")
        self.assertIs(self.controls.result, result)
        self.assertEqual(self.controls.region_a.currentData(), self.a.id())
        self.assertEqual(self.controls.region_b.currentData(), self.b.id())
        self.window.map_canvas.setLayers([])
        self.assertIs(self.controls.result, result)

    def test_swap_and_parameter_invalidation(self):
        self.start()
        self.controls.swap()
        self.assertIsNone(self.controls.result)
        self.start()
        self.assertEqual(self.controls.result["differences"]["mean_m"], -2)
        self.controls.bins.setValue(3)
        self.assertIsNone(self.controls.result)
        self.assertTrue(self.controls.dock.isHidden())
        self.start()
        self.assertEqual(len(self.controls.result["parameters"]["bin_edges_m"]), 4)
        self.controls.thresholds.setText("0,0")
        self.start()
        self.assertIn("参数无效", self.controls.message.text())
        self.assertIsNone(self.controls.result)

    def test_tasks_mutually_exclusive(self):
        self.controls.start()
        self.assertFalse(self.window.statistics_action.isEnabled())
        self.window.create_statistics()
        self.assertIsNone(self.window._statistics_worker)
        self.wait_finished()
        self.window.create_statistics()
        self.assertFalse(self.controls.start_action.isEnabled())
        self.controls.start()
        self.assertIsNone(self.controls.worker)
        self.wait_finished()
        self.assertTrue(self.controls.start_action.isEnabled())
        self.assertTrue(self.window.statistics_action.isEnabled())

    def test_cancel_and_stale_signals(self):
        self.start()
        old = self.controls.result
        task_id = self.controls.task_id
        self.controls.swap()
        self.controls.succeeded(task_id, old)
        self.assertIsNone(self.controls.result)
        self.controls.start()
        self.controls.cancel()
        self.wait_finished()
        self.assertIsNone(self.controls.result)
        self.assertIn("取消", self.controls.message.text())

    def test_compute_and_plot_failure_do_not_publish(self):
        with patch("etopo_analyzer.ui.comparison_worker.compare_regions", side_effect=RuntimeError("读取失败")):
            self.start()
        self.assertIn("读取失败", self.controls.message.text())
        self.assertIsNone(self.controls.result)
        with patch("etopo_analyzer.ui.comparison_panel.create_distribution_figure", side_effect=RuntimeError("绘图失败")):
            self.start()
        self.assertIn("绘图失败", self.controls.message.text())
        self.assertIsNone(self.controls.result)

    def test_recompute_failure_keeps_valid_comparison(self):
        self.start()
        previous, panel = self.controls.result, self.controls.panel
        with patch("etopo_analyzer.ui.comparison_worker.compare_regions", side_effect=RuntimeError("失败")):
            self.start()
        self.assertIs(self.controls.result, previous)
        self.assertIs(self.controls.panel, panel)
        self.assertTrue(self.controls.show_action.isEnabled())
        with patch("etopo_analyzer.ui.comparison_panel.create_distribution_figure", side_effect=RuntimeError("绘图失败")):
            self.start()
        self.assertIn("绘图失败", self.controls.message.text())
        self.assertIs(self.controls.result, previous)

    def test_derived_layers_excluded_and_removal_invalidates(self):
        derived = add_raster_layer(str(self.path_a), "坡度显示")
        self.window._register_layer(derived, "派生栅格")
        self.assertEqual(self.controls.region_a.findData(derived.id()), -1)
        self.start()
        QgsProject.instance().removeMapLayer(self.a.id())
        self.app.processEvents()
        self.assertIsNone(self.controls.result)
        self.assertFalse(self.controls.start_action.isEnabled())

    def test_modified_source_blocks_display(self):
        self.start()
        stat = self.path_a.stat()
        os.utime(self.path_a, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
        self.controls.show_result()
        self.assertIsNone(self.controls.result)
        self.assertIn("变化", self.controls.message.text())

    def test_results_switch_and_close_running(self):
        self.start()
        self.window.create_statistics()
        self.wait_finished()
        self.assertTrue(self.controls.dock.isHidden())
        self.controls.show_result()
        self.assertTrue(self.window._statistics_dock.isHidden())
        self.window.create_profile([(121.05, 23.95), (121.25, 23.95)])
        self.assertTrue(self.controls.dock.isHidden())
        self.controls.show_result()
        self.assertTrue(self.window._profile_dock.isHidden())
        self.controls.start()
        self.window.close()
        self.wait_finished()
        self.assertTrue(self.window._closing)
        self.assertIsNone(self.controls.result)


if __name__ == "__main__":
    unittest.main()
