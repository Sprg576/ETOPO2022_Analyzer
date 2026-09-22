"""裁剪确认、显示顺序、剖面联动、统计与导出预览的集成验收。"""

from pathlib import Path
from types import SimpleNamespace
import unittest
import time
from qgis.PyQt.QtTest import QTest
from qgis.core import QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY
from qgis.PyQt.QtCore import Qt, QSettings, QTimer
from qgis.PyQt.QtWidgets import QApplication, QTableWidgetSelectionRange
import test_processing_tasks as fixtures
from processing_test_support import wait_for_processing
from etopo_analyzer.core.raster_clip import preview_clip, clip_raster_by_bounds
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics
from etopo_analyzer.core.profile_analysis import sample_elevation_profile
from etopo_analyzer.ui.layer_context_menu import set_visible_layers
from etopo_analyzer.ui.statistics_panel import StatisticsPanel
from etopo_analyzer.ui.export_dialog import ExportDialog


class TestBatch34UI(unittest.TestCase):
    setUpClass = classmethod(fixtures.TestProcessingTasks.setUpClass.__func__)
    setUp = fixtures.TestProcessingTasks.setUp
    tearDown = fixtures.TestProcessingTasks.tearDown

    def test_preview_matches_real_pixel_window_and_rejects_outside(self):
        bounds = dict(west=119.99, south=23.981, east=120.025, north=24.01)
        preview = preview_clip(str(self.path), **bounds)
        result = clip_raster_by_bounds(str(self.path), str(self.root / "verify.tif"), **bounds)
        for key in ("source_window", "width", "height", "bounds"):
            self.assertEqual(preview[key], result[key])
        with self.assertRaises(ValueError):
            preview_clip(str(self.path), 0, 0, 1, 1)

    def test_consecutive_clips_keep_explicit_source_and_optional_analysis(self):
        controls = self.window.clip_controls
        controls.receive(dict(west=120, south=23.98, east=120.02, north=24))
        self.assertIsNone(self.window._task_controls.worker)
        controls.start()
        wait_for_processing(self.window)
        first = self.window._active_raster_layer
        self.assertIsNot(first, self.layer)
        self.assertEqual(controls.source.currentData(), self.layer.id())
        controls.activate_result.setChecked(False)
        controls.receive(dict(west=120.03, south=23.98, east=120.05, north=24))
        controls.start()
        wait_for_processing(self.window)
        self.assertIs(self.window._active_raster_layer, first)
        crops = self.window._layer_groups["裁剪结果"]
        self.assertEqual(crops.childCount(), 2)
        second = self.window._managed_layers[crops.child(1).data(0, Qt.UserRole)]
        self.assertGreater(second.extent().xMinimum(), first.extent().xMaximum())
        self.assertTrue(controls.start_button.isEnabled())

    def test_invalid_clip_keeps_previous_result_and_remembers_bounds(self):
        controls = self.window.clip_controls
        controls.receive(dict(west=121, south=23.98, east=122, north=24))
        self.assertFalse(controls.start_button.isEnabled())
        controls.hide()
        self.window.activate_rectangle_clip()
        self.assertEqual(controls.bounds()["west"], 121)
        self.assertIs(self.window._active_raster_layer, self.layer)

    def add_crop(self):
        self.window._clip_selected_bounds(dict(west=120, south=23.98, east=120.03, north=24))
        wait_for_processing(self.window)
        return self.window._active_raster_layer

    def test_order_survives_toggle_and_opacity_is_layer_specific(self):
        crop = self.add_crop()
        set_visible_layers(self.window, [crop, self.layer])
        controls = self.window.layer_order_controls
        self.window.layer_tree.setCurrentItem(self.window._layer_items[crop.id()])
        controls.move(1)
        self.assertEqual(self.window.map_canvas.layers(), [self.layer, crop])
        set_visible_layers(self.window, [crop])
        set_visible_layers(self.window, [crop, self.layer])
        self.assertEqual(self.window.map_canvas.layers(), [self.layer, crop])
        controls.opacity.setValue(35)
        self.assertAlmostEqual(crop.renderer().opacity(), .35)
        self.assertEqual(self.layer.renderer().opacity(), 1)
        self.window.apply_color_relief()
        self.assertAlmostEqual(crop.renderer().opacity(), .35)

    def test_profile_hover_marks_transformed_position_and_clears(self):
        result = sample_elevation_profile(str(self.path), [(120.005, 23.995), (120.045, 23.995)], 500)
        self.window._publish_profile(result)
        panel = self.window._profile_panel
        self.window.map_canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        index = 2
        panel.hover(SimpleNamespace(inaxes=panel.canvas.figure.axes[0], xdata=result["distance_m"][index]/1000))
        point = (result["longitude"][index], result["latitude"][index])
        self.assertEqual(self.window._profile_overlay.sample_point, point)
        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsCoordinateReferenceSystem("EPSG:3857"), QgsProject.instance())
        expected = transform.transform(QgsPointXY(*point))
        self.assertAlmostEqual(self.window._profile_overlay.sample_marker.center().x(), expected.x())
        self.assertIn("距离", panel.details.text())
        panel.leave()
        self.assertIsNone(self.window._profile_overlay.sample_point)
        self.window._reverse_profile()
        wait_for_processing(self.window)
        self.assertEqual(self.window._profile_result["vertices"][0], result["vertices"][-1])

    def test_statistics_percent_and_copy_do_not_change_counts(self):
        result = calculate_raster_statistics(str(self.path))
        counts = list(result["histogram"]["counts"])
        panel = StatisticsPanel(result)
        try:
            panel.histogram_mode.setCurrentIndex(1)
            self.assertAlmostEqual(sum(p.get_height() for p in panel.canvas.figure.axes[0].patches), 100)
            self.assertEqual(result["histogram"]["counts"], counts)
            table = panel.area_table
            table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 1), True)
            table.copy_selection()
            self.assertEqual(QApplication.clipboard().text(), "\n".join("\t".join(table.item(r, c).text() for c in (0, 1)) for r in (0, 1)))
        finally:
            panel.clear()
            panel.deleteLater()

    def test_map_preview_does_not_publish_or_change_map(self):
        dialog = ExportDialog(self.window, "map")
        try:
            dialog.directory.setText(str(self.root))
            dialog.name.setText("preview_only")
            dialog.pixels.setValue(1200)
            extent = self.window.map_canvas.extent()
            dialog.preview()
            self.assertIsNotNone(dialog.preview_label.pixmap())
            self.assertFalse(dialog.preview_label.pixmap().isNull())
            self.assertFalse((self.root / "preview_only").exists())
            self.assertEqual(self.window.map_canvas.extent(), extent)
            self.assertIs(self.window._active_raster_layer, self.layer)
            dialog.title.setText("新标题")
            self.assertIsNone(dialog.preview_label.pixmap())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_chart_preview_uses_percent_display(self):
        self.window._statistics_result = calculate_raster_statistics(str(self.path))
        self.window._statistics_result["histogram_mode"] = "percent"
        dialog = ExportDialog(self.window, "chart")
        try:
            dialog.preview()
            deadline = time.monotonic() + 20
            while dialog.worker is not None and time.monotonic() < deadline:
                self.app.processEvents()
                QTest.qWait(5)
            self.assertIsNone(dialog.worker)
            self.assertIsNotNone(dialog.preview_label.pixmap())
            self.assertIsNone(dialog.output)
            self.assertFalse(dialog.map_running)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_map_preview_cancel_leaves_no_output_and_can_retry(self):
        dialog = ExportDialog(self.window, "map")
        try:
            dialog.pixels.setValue(1200)
            QTimer.singleShot(0, dialog.reject)
            dialog.preview()
            self.assertIsNone(dialog.output)
            self.assertFalse(dialog.map_running)
            self.assertTrue(dialog.preview_button.isEnabled())
            self.assertIn("取消", dialog.message.text())
            dialog.preview()
            self.assertIsNotNone(dialog.preview_label.pixmap())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_threshold_presets_validate_and_restore_saved_values(self):
        from etopo_analyzer.ui.threshold_presets import ThresholdPresets
        edit = self.window.statistics_thresholds_edit
        presets = ThresholdPresets(edit, self.window)
        presets.settings = QSettings(str(self.root / "settings.ini"), QSettings.IniFormat)
        edit.setText("0, 200, 500")
        presets.save()
        edit.setText("500, 0")
        presets.save()
        presets.choice.setCurrentIndex(3)
        presets.apply()
        self.assertEqual(edit.text(), "0.0, 200.0, 500.0")

    def test_many_classes_keep_complete_labels_and_named_regions(self):
        from etopo_analyzer.core.region_comparison import compare_regions
        from etopo_analyzer.visualization.comparison_plot import create_area_comparison_figure
        result = compare_regions(str(self.path), str(self.path), thresholds=list(range(-10, 11)))
        result["regions"]["a"]["name"] = "区域一"
        figure = create_area_comparison_figure(result)
        try:
            axes = figure.axes[0]
            self.assertEqual(len(axes.get_yticklabels()), len(result["classes"]))
            self.assertIn("区域一", axes.get_legend().get_texts()[0].get_text())
            self.assertAlmostEqual(sum(p.get_width() for p in axes.patches[:len(result["classes"])]), 100)
        finally:
            figure.clear()
