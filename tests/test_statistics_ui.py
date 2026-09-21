"""F09 真实后台线程、来源状态和结果面板集成测试。"""

from pathlib import Path
import gc
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtCore import QCoreApplication, QEvent

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.core.layer_manager import create_raster_layer
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
from test_raster_statistics import create_dem


class TestStatisticsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], True)
            cls.app.initQgis()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "dem.tif"
        create_dem(self.path, [[-2, -1, 0, 1, 2]] * 3,
                   transform=(120, .1, 0, 24, 0, -.1))
        self.layer = create_raster_layer(str(self.path))
        QgsProject.instance().addMapLayer(self.layer)
        self.window = ETOPOAnalyzerMainWindow()
        # 本组验证统计状态，暂停无关地图渲染，避免渲染线程延迟释放临时 DEM。
        self.window.map_canvas.freeze(True)

    def tearDown(self):
        self.window.cancel_statistics()
        self.wait_finished()
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

    def wait_finished(self):
        deadline = time.monotonic() + 20
        while self.window._statistics_worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.app.processEvents()
        self.assertIsNone(self.window._statistics_worker, "统计线程未正常退出")

    def start(self):
        self.window.create_statistics()
        self.wait_finished()

    def test_actions_real_worker_and_panel(self):
        self.assertFalse(self.window.statistics_action.isEnabled())
        self.window.show_layer(self.layer)
        self.assertTrue(self.window.statistics_action.isEnabled())
        self.start()
        result = self.window._statistics_result
        self.assertIsNotNone(result, self.window.statistics_message.text())
        self.assertEqual(result["statistics"]["mean_m"], 0)
        self.assertEqual(self.window._statistics_panel.tabs.count(), 3)
        self.assertTrue(self.window.show_statistics_action.isEnabled())
        self.assertFalse(self.window.cancel_statistics_action.isEnabled())
        self.assertIs(self.window._active_raster_layer, self.layer)

    def test_derived_displays_and_visibility_preserve_source(self):
        self.window.show_layer(self.layer)
        self.window._clip_output_directory = Path(self.temp.name) / "derived"
        for method in (self.window.create_slope, self.window.create_aspect, self.window.create_hillshade):
            method()
            self.start()
            result = self.window._statistics_result
            self.assertIsNotNone(result, self.window.statistics_message.text())
            self.assertEqual(result["raster_path"], str(self.path.resolve()))
            self.assertEqual(result["statistics"]["mean_m"], 0)
            self.assertEqual(result["statistics"]["valid_count"], 15)
        self.window.map_canvas.setLayers([])
        self.assertIs(self.window._statistics_result, result)
        self.assertEqual(self.window._active_raster_path, str(self.path))

    def test_parameter_change_invalidates_and_recompute(self):
        self.window.show_layer(self.layer)
        self.start()
        self.window.statistics_bins_spin.setValue(2)
        self.assertIsNone(self.window._statistics_result)
        self.assertTrue(self.window._statistics_dock.isHidden())
        self.assertFalse(self.window.show_statistics_action.isEnabled())
        self.start()
        self.assertEqual(self.window._statistics_result["histogram"]["counts"], [6, 9])
        self.window.statistics_thresholds_edit.setText("0,0")
        self.start()
        self.assertIsNone(self.window._statistics_result)
        self.assertIn("参数无效", self.window.statistics_message.text())

    def test_switch_source_and_stale_result_rejected(self):
        self.window.show_layer(self.layer)
        self.start()
        old = self.window._statistics_result
        task_id = self.window._statistics_task_id
        self.window.show_layer(self.layer)
        self.window._statistics_succeeded(task_id, old)
        self.assertIsNone(self.window._statistics_result)
        self.assertFalse(self.window.show_statistics_action.isEnabled())
        self.window.create_statistics()
        self.window.show_layer(self.layer)
        self.wait_finished()
        self.assertIsNone(self.window._statistics_result)

    def test_cancel_and_compute_failure_leave_no_result(self):
        self.window.show_layer(self.layer)
        self.window.create_statistics()
        self.window.cancel_statistics()
        self.wait_finished()
        self.assertIsNone(self.window._statistics_result)
        with patch("etopo_analyzer.ui.statistics_worker.calculate_raster_statistics", side_effect=RuntimeError("读取失败")):
            self.start()
        self.assertIsNone(self.window._statistics_result)
        self.assertIn("读取失败", self.window.statistics_message.text())
        self.assertTrue(self.window.statistics_action.isEnabled())

    def test_plot_failure_is_not_published(self):
        self.window.show_layer(self.layer)
        with patch("etopo_analyzer.ui.statistics_panel.create_statistics_figure", side_effect=RuntimeError("绘图失败")):
            self.start()
        self.assertIsNone(self.window._statistics_result)
        self.assertFalse(self.window.show_statistics_action.isEnabled())
        self.assertIn("绘图失败", self.window.statistics_message.text())

    def test_profile_and_statistics_switch_both_creation_orders(self):
        self.window.show_layer(self.layer)
        self.start()
        result = self.window._statistics_result
        self.window.create_profile([(120.05, 23.95), (120.45, 23.95)])
        self.app.processEvents()
        self.assertTrue(self.window._statistics_dock.isHidden())
        self.assertIs(self.window._statistics_result, result)
        profile = self.window._profile_result
        self.window.show_statistics()
        self.app.processEvents()
        self.assertTrue(self.window._profile_dock.isHidden())
        self.assertIs(self.window._profile_result, profile)
        self.window.show_layer(self.layer)
        self.window.create_profile([(120.05, 23.95), (120.45, 23.95)])
        self.start()
        self.assertTrue(self.window._profile_dock.isHidden())

    def test_close_waits_for_worker_without_publishing(self):
        self.window.show_layer(self.layer)
        self.window.create_statistics()
        self.window.close()
        self.wait_finished()
        self.assertTrue(self.window._closing)
        self.assertIsNone(self.window._statistics_result)


if __name__ == "__main__":
    unittest.main()
