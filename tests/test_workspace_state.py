"""工作状态往返、失效来源、损坏文件与成果历史恢复。"""

import json
import os
import unittest
from unittest.mock import patch
from qgis.core import QgsCoordinateReferenceSystem, QgsProject
from qgis.PyQt.QtCore import Qt
import test_processing_tasks as fixtures
from processing_test_support import wait_for_processing
from etopo_analyzer.core.workspace_state import write_state, read_state
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics
from etopo_analyzer.core.profile_analysis import sample_elevation_profile
from etopo_analyzer.ui.layer_context_menu import set_visible_layers, remove_layer
from etopo_analyzer.ui.workspace_controls import HistoryDialog


class TestWorkspaceState(unittest.TestCase):
    setUpClass = classmethod(fixtures.TestProcessingTasks.setUpClass.__func__)
    setUp = fixtures.TestProcessingTasks.setUp
    tearDown = fixtures.TestProcessingTasks.tearDown

    def crop(self):
        self.window._clip_selected_bounds(dict(west=120, south=23.98, east=120.03, north=24))
        wait_for_processing(self.window)
        return self.window._active_raster_layer

    def test_roundtrip_layers_style_order_source_and_parameters(self):
        w = self.window
        crop = self.crop()
        crop.setName("研究区甲")
        w.layer_order_controls.opacity.setValue(45)
        w.layer_order_controls.move(1)
        set_visible_layers(w, [self.layer, crop])
        w.map_canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        w.hillshade_azimuth_spin.setValue(123)
        w.clip_controls.activate_result.setChecked(False)
        filename = self.root / "中文工作状态.etopo.json"
        controls = w.workspace_controls
        controls.save(filename)
        saved = read_state(filename)
        self.assertEqual(controls.load(filename), [])
        self.assertEqual(len(w._managed_layers), 2)
        self.assertEqual(w._active_raster_layer.name(), "研究区甲")
        self.assertAlmostEqual(w._active_raster_layer.renderer().opacity(), .45)
        self.assertEqual([l.source() for l in w.map_canvas.layers()], [saved["layers"][0]["source"], saved["layers"][1]["source"]])
        self.assertEqual(w.hillshade_azimuth_spin.value(), 123)
        self.assertEqual(w.map_canvas.mapSettings().destinationCrs().authid(), "EPSG:3857")
        self.assertFalse(w.clip_controls.activate_result.isChecked())
        self.assertEqual(len(controls.history), 1)

    def test_roundtrip_completed_profile_and_statistics_remain_exportable(self):
        w = self.window
        profile = sample_elevation_profile(str(self.path), [(120.005, 23.995), (120.045, 23.995)], 500)
        w._publish_profile(profile)
        stats = calculate_raster_statistics(str(self.path), 7, [-1, 0, 1])
        stats["histogram_mode"] = "percent"
        w.statistics_bins_spin.setValue(7)
        w._statistics_succeeded(w._statistics_task_id, stats)
        filename = self.root / "results.etopo.json"
        w.workspace_controls.save(filename)
        self.assertEqual(w.workspace_controls.load(filename), [])
        self.assertEqual(w._profile_result["distance_m"], profile["distance_m"])
        self.assertEqual(w._statistics_result["histogram_mode"], "percent")
        self.assertTrue(w.show_profile_action.isEnabled())
        self.assertTrue(w.show_statistics_action.isEnabled())
        self.assertEqual(len(w.workspace_controls.history), 2)

    def test_changed_source_is_skipped_and_results_not_restored(self):
        w = self.window
        crop = self.crop()
        result = calculate_raster_statistics(crop.source())
        w._statistics_succeeded(w._statistics_task_id, result)
        filename = self.root / "changed.etopo.json"
        w.workspace_controls.save(filename)
        path = crop.source()
        stat = os.stat(path)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10000000))
        warnings = w.workspace_controls.load(filename)
        self.assertTrue(warnings)
        self.assertEqual(len(w._managed_layers), 1)
        self.assertIsNone(w._active_raster_layer)
        self.assertIsNone(w._statistics_result)
        self.assertFalse(w.statistics_action.isEnabled())

    def test_malformed_and_future_version_leave_current_session_intact(self):
        w = self.window
        original = w._active_raster_layer
        filename = self.root / "bad.etopo.json"
        for state in ({"format": "etopo-workspace", "version": 999}, {**w.workspace_controls.capture(), "parameters": {"clip_bounds": {"bad": 1}}}):
            filename.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(ValueError):
                w.workspace_controls.load(filename)
            self.assertIs(w._active_raster_layer, original)

    def test_atomic_save_failure_keeps_previous_file(self):
        controls = self.window.workspace_controls
        filename = self.root / "atomic.etopo.json"
        controls.save(filename)
        previous = filename.read_bytes()
        with patch("etopo_analyzer.core.workspace_state.os.replace", side_effect=OSError("磁盘错误")):
            with self.assertRaises(OSError):
                controls.save(filename)
        self.assertEqual(filename.read_bytes(), previous)
        self.assertEqual(list(self.root.glob(".etopo-state-*")), [])

    def test_history_recovers_removed_layer_without_deleting_file(self):
        w = self.window
        crop = self.crop()
        path = crop.source()
        remove_layer(w, crop)
        dialog = HistoryDialog(w.workspace_controls)
        try:
            dialog.table.setCurrentCell(0, 0)
            dialog.restore()
            self.assertIn(path, [layer.source() for layer in w._managed_layers.values()])
            self.assertEqual(len(w.workspace_controls.history), 1)
        finally:
            dialog.deleteLater()

    def test_history_rejects_changed_source(self):
        w = self.window
        result = calculate_raster_statistics(str(self.path))
        w._statistics_succeeded(w._statistics_task_id, result)
        stat = os.stat(self.path)
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10000000))
        dialog = HistoryDialog(w.workspace_controls)
        try:
            dialog.table.setCurrentCell(0, 0)
            dialog.restore()
            self.assertIn("无法恢复", dialog.message.text())
        finally:
            dialog.deleteLater()

    def test_busy_save_is_rejected(self):
        w = self.window
        w._task_controls.start("测试", [("等待", lambda results: fixtures.TestProcessingTasks.slow_operation(self, results))], [], lambda results: None)
        with self.assertRaises(RuntimeError):
            w.workspace_controls.save(self.root / "busy.etopo.json")
        w._task_controls.cancel()
        wait_for_processing(w)

    def test_comparison_sources_and_results_roundtrip(self):
        from etopo_analyzer.core.region_comparison import compare_regions
        w = self.window
        crop = self.crop()
        c = w._comparison_controls
        c.region_a.setCurrentIndex(c.region_a.findData(self.layer.id()))
        c.region_b.setCurrentIndex(c.region_b.findData(crop.id()))
        result = compare_regions(self.layer.source(), crop.source(), 4, [-1, 0, 1])
        c.succeeded(c.task_id, result)
        filename = self.root / "comparison.etopo.json"
        w.workspace_controls.save(filename)
        self.assertEqual(w.workspace_controls.load(filename), [])
        self.assertEqual(c.result["differences"], result["differences"])
        self.assertEqual([layer.source() for layer in c.selected_layers()],
                         [result["regions"][key]["raster_path"] for key in ("a", "b")])
        self.assertTrue(c.show_action.isEnabled())

    def test_contour_layer_roundtrip(self):
        w = self.window
        w.contour_interval_spin.setValue(1)
        w.create_contours()
        wait_for_processing(w)
        self.assertIsNotNone(w._contour_layer)
        count = w._contour_layer.featureCount()
        filename = self.root / "contour.etopo.json"
        w.workspace_controls.save(filename)
        self.assertEqual(w.workspace_controls.load(filename), [])
        group = w._layer_groups["等值线"]
        self.assertEqual(group.childCount(), 1)
        layer = w._managed_layers[group.child(0).data(0, Qt.UserRole)]
        self.assertEqual(layer.featureCount(), count)

    def test_no_available_sources_does_not_clear_current_work(self):
        w = self.window
        state = w.workspace_controls.capture()
        state["layers"][0]["signature"]["path"] = str(self.root / "gone.tif")
        filename = self.root / "missing.etopo.json"
        write_state(filename, state)
        with self.assertRaises(ValueError):
            w.workspace_controls.load(filename)
        self.assertIs(w._active_raster_layer, self.layer)

    def test_history_restores_statistics_parameters_without_duplicate_entry(self):
        w = self.window
        result = calculate_raster_statistics(str(self.path), 7, [-1, 0, 1])
        w._statistics_succeeded(w._statistics_task_id, result)
        w.statistics_bins_spin.setValue(9)
        dialog = HistoryDialog(w.workspace_controls)
        try:
            dialog.table.setCurrentCell(0, 0)
            dialog.restore()
            self.assertEqual(w.statistics_bins_spin.value(), 7)
            self.assertEqual(w._statistics_result["statistics"], result["statistics"])
            self.assertEqual(len(w.workspace_controls.history), 1)
        finally:
            dialog.deleteLater()
