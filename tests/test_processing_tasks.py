"""真实后台线程、合作式取消和图层状态一致性。"""

import gc
import threading
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qgis.core import QgsApplication, QgsProject, QgsCoordinateReferenceSystem
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QTimer, Qt
from qgis.PyQt.QtTest import QTest
from test_raster_statistics import create_dem
from processing_test_support import wait_for_processing
from etopo_analyzer.core.layer_manager import create_raster_layer
from etopo_analyzer.core import processing_feedback as feedback
from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
from etopo_analyzer.core.hillshade import project_raster_to_local_utm
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
from etopo_analyzer.ui.layer_context_menu import set_visible_layers


class TestProcessingTasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], True)
            cls.app.initQgis()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "dem.tif"
        create_dem(self.path, [[-2, -1, 0, 1, 2]] * 3, transform=(120, .01, 0, 24, 0, -.01))
        self.layer = create_raster_layer(str(self.path))
        QgsProject.instance().addMapLayer(self.layer)
        self.window = ETOPOAnalyzerMainWindow()
        from processing_test_support import allow_unsaved_discard
        allow_unsaved_discard(self)
        self.window.map_canvas.freeze(True)
        self.window._clip_output_directory = self.root
        self.window.show_layer(self.layer)

    def tearDown(self):
        if self.window._task_controls.worker:
            self.window._task_controls.cancel()
            wait_for_processing(self.window)
        self.window.close()
        self.window.map_canvas.stopRendering()
        self.window.map_canvas.setLayers([])
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.window = None
        self.layer = None
        QgsProject.instance().clear()
        gc.collect()
        self.temp.cleanup()

    def slow_operation(self, results):
        while True:
            feedback.report(.3)
            time.sleep(.002)

    def test_real_clip_runs_off_gui_thread_and_publishes(self):
        main_id = threading.get_ident()
        worker_ids = []
        def clip(*args, **kwargs):
            worker_ids.append(threading.get_ident())
            return clip_raster_by_bounds(*args, **kwargs)
        with patch("etopo_analyzer.ui.main_window.clip_raster_by_bounds", side_effect=clip):
            self.window._clip_selected_bounds(dict(west=120, south=23.98, east=120.03, north=24))
            self.assertIsNotNone(self.window._task_controls.worker)
            self.assertFalse(self.window.slope_action.isEnabled())
            self.assertTrue(self.window.cancel_task_action.isEnabled())
            wait_for_processing(self.window)
        self.assertNotEqual(worker_ids, [main_id])
        self.assertNotEqual(self.window._active_raster_path, str(self.path))
        self.assertTrue(self.window.slope_action.isEnabled())
        self.assertFalse(self.window.cancel_task_action.isEnabled())

    def test_cancel_via_toolbar_keeps_old_results_and_cleans_partial(self):
        partial = self.root / "partial.tif"
        previous = {"old": True}
        self.window._profile_result = previous
        def operation(results):
            partial.write_bytes(b"partial")
            self.slow_operation(results)
        published = []
        self.window._task_controls.start("测试", [("第一阶段", operation)], [partial], published.append)
        heartbeat = []
        QTimer.singleShot(30, lambda: (heartbeat.append(True), self.window.cancel_task_action.trigger()))
        wait_for_processing(self.window)
        self.assertTrue(heartbeat)
        self.assertEqual(published, [])
        self.assertFalse(partial.exists())
        self.assertIs(self.window._profile_result, previous)
        self.assertTrue(self.window.profile_interval_spin.isEnabled())

    def test_failure_after_projection_preserves_map_and_removes_both_outputs(self):
        original = self.window.map_canvas.layers()
        with patch("etopo_analyzer.ui.main_window.generate_slope", side_effect=RuntimeError("模拟坡度失败")):
            self.window.create_slope()
            wait_for_processing(self.window)
        self.assertEqual(self.window.map_canvas.layers(), original)
        self.assertEqual(list(self.root.glob("ETOPO2022*")), [])
        self.assertIn("失败", self.window.statusBar().currentMessage())

    def test_existing_output_is_never_removed(self):
        path = self.root / "existing.tif"
        path.write_bytes(b"keep")
        self.window._task_controls.start("测试", [("阶段", lambda results: None)], [path], lambda result: None)
        wait_for_processing(self.window)
        self.assertEqual(path.read_bytes(), b"keep")

    def test_close_cancels_and_waits_for_worker(self):
        published = []
        self.window._task_controls.start("测试", [("阶段", self.slow_operation)], [], published.append)
        self.window.close()
        self.assertTrue(self.window._closing)
        self.assertIsNotNone(self.window._task_controls.worker)
        wait_for_processing(self.window)
        self.assertEqual(published, [])

    def test_external_layer_removal_cancels_and_drops_result(self):
        published = []
        layer_id = self.layer.id()
        self.window._task_controls.start("测试", [("阶段", self.slow_operation)], [], published.append)
        QgsProject.instance().removeMapLayer(layer_id)
        wait_for_processing(self.window)
        self.assertIsNone(self.window._active_raster_path)
        self.assertNotIn(layer_id, self.window._layer_items)
        self.assertEqual(published, [])

    def test_source_switch_discards_late_completion(self):
        gate = threading.Event()
        published = []
        self.window._task_controls.start("测试", [("阶段", lambda results: gate.wait(2))], [], published.append)
        other = create_raster_layer(str(self.path))
        QgsProject.instance().addMapLayer(other)
        self.window.show_layer(other)
        gate.set()
        wait_for_processing(self.window)
        self.assertEqual(published, [])

    def test_busy_rejects_statistics_comparison_and_duplicate_work(self):
        self.window._task_controls.start("测试", [("阶段", self.slow_operation)], [], lambda result: None)
        worker = self.window._task_controls.worker
        self.window.create_statistics()
        self.window._comparison_controls.start()
        self.window.create_slope()
        self.assertIs(self.window._task_controls.worker, worker)
        self.assertIsNone(self.window._statistics_worker)
        self.assertIsNone(self.window._comparison_controls.worker)

    def test_checkbox_and_context_visibility_preserve_projected_extent(self):
        canvas = self.window.map_canvas
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        extent = canvas.extent()
        item = self.window._layer_items[self.layer.id()]
        item.setCheckState(0, Qt.Unchecked)
        item.setCheckState(0, Qt.Checked)
        self.assertEqual(canvas.mapSettings().destinationCrs().authid(), "EPSG:3857")
        self.assertEqual(canvas.extent(), extent)
        set_visible_layers(self.window, [])
        set_visible_layers(self.window, [self.layer])
        self.assertEqual(canvas.extent(), extent)

    def test_color_relief_targets_selection_and_not_hidden_previous_display(self):
        other = create_raster_layer(str(self.path))
        QgsProject.instance().addMapLayer(other)
        self.window._register_layer(other, "源数据")
        original = self.layer.renderer()
        self.window.layer_tree.setCurrentItem(self.window._layer_items[other.id()])
        self.window.apply_color_relief()
        self.assertEqual(other.renderer().type(), "singlebandpseudocolor")
        self.assertIs(self.layer.renderer(), original)
        self.assertIs(self.window._active_raster_layer, self.layer)

    def test_gdal_callback_cancellation_removes_clip(self):
        cancelled = [False]
        def report(fraction):
            cancelled[0] = True
        output = self.root / "cancelled.tif"
        with self.assertRaises(Exception):
            with feedback.feedback_scope(report, lambda: cancelled[0]):
                clip_raster_by_bounds(str(self.path), str(output), 120, 23.97, 120.05, 24)
        self.assertFalse(output.exists())
