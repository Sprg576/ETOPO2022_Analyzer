"""图层右键操作与分析状态隔离回归测试。"""

import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qgis.core import QgsApplication, QgsProject, QgsCoordinateReferenceSystem
from qgis.PyQt.QtCore import QCoreApplication, QEvent, Qt
from qgis.PyQt.QtWidgets import QApplication
from test_raster_statistics import create_dem
from etopo_analyzer.core.layer_manager import create_raster_layer
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
from etopo_analyzer.ui.layer_context_menu import (build_layer_menu, rename_layer, remove_layer,
    set_group_visibility, zoom_to_layer)


class TestLayerContextMenu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance()
        if cls.app is None:
            cls.app = QgsApplication([], True)
            cls.app.initQgis()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = ETOPOAnalyzerMainWindow()
        from processing_test_support import wrap_processing_calls
        wrap_processing_calls(self.window)
        self.window.map_canvas.freeze(True)
        self.layers = []
        for name in ("a", "b"):
            path = self.root / f"{name}.tif"
            create_dem(path, [[-2, -1, 0, 1, 2]] * 3, transform=(120, .1, 0, 24, 0, -.1))
            layer = create_raster_layer(str(path))
            QgsProject.instance().addMapLayer(layer)
            self.window.show_layer(layer)
            self.layers.append(layer)

    def tearDown(self):
        self.window.close()
        self.window.map_canvas.stopRendering()
        self.window.map_canvas.setLayers([])
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.window = None
        self.layers = []
        QgsProject.instance().clear()
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.temp.cleanup()

    def menu(self, layer):
        item = self.window._layer_items[layer.id()]
        self.window.layer_tree.setCurrentItem(item)
        self.window._update_analysis_source_action()
        menu = build_layer_menu(self.window, item)
        return {action.text(): action for action in menu.actions() if not action.isSeparator()}

    def test_visibility_and_copy_do_not_change_analysis_or_extent(self):
        active = self.window._active_raster_layer
        extent = self.window.map_canvas.extent()
        actions = self.menu(self.layers[0])
        actions["仅显示此图层"].trigger()
        self.assertEqual(self.window.map_canvas.layers(), [self.layers[0]])
        self.assertIs(self.window._active_raster_layer, active)
        self.assertEqual(self.window.map_canvas.extent(), extent)
        self.assertEqual(self.window._layer_items[self.layers[0].id()].checkState(0), Qt.Checked)
        actions["复制数据源路径"].trigger()
        self.assertEqual(QApplication.clipboard().text(), self.layers[0].source())
        self.menu(self.layers[0])["隐藏图层"].trigger()
        self.assertEqual(self.window.map_canvas.layers(), [])
        self.menu(self.layers[0])["显示图层"].trigger()
        self.assertEqual(self.window.map_canvas.layers(), [self.layers[0]])

    def test_group_visibility(self):
        group = self.window._layer_groups["源数据"]
        set_group_visibility(self.window, group, True)
        self.assertEqual(len(self.window.map_canvas.layers()), 2)
        set_group_visibility(self.window, group, False)
        self.assertEqual(self.window.map_canvas.layers(), [])
        self.assertIs(self.window._active_raster_layer, self.layers[1])

    def test_rename_preserves_source_and_comparison_selection(self):
        layer = self.layers[0]
        controls = self.window._comparison_controls
        controls.region_a.setCurrentIndex(controls.region_a.findData(layer.id()))
        item = self.window._layer_items[layer.id()]
        source = layer.source()
        with patch("etopo_analyzer.ui.layer_context_menu.QInputDialog.getText", return_value=("新名称", True)):
            rename_layer(self.window, layer, item)
        self.assertEqual(layer.name(), "新名称")
        self.assertEqual(item.text(0), "新名称")
        self.assertEqual(layer.source(), source)
        self.assertEqual(controls.region_a.currentData(), layer.id())
        self.assertIn("新名称", controls.region_a.currentText())
        with patch("etopo_analyzer.ui.layer_context_menu.QInputDialog.getText", return_value=("  ", True)):
            rename_layer(self.window, layer, item)
        self.assertEqual(layer.name(), "新名称")

    def test_zoom_transforms_crs_without_switching_source(self):
        self.window.map_canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        zoom_to_layer(self.window, self.layers[0])
        self.assertGreater(self.window.map_canvas.extent().center().x(), 1e7)
        self.assertIs(self.window._active_raster_layer, self.layers[1])

    def test_remove_inactive_invalidates_comparison_but_keeps_active(self):
        layer = self.layers[0]
        layer_id = layer.id()
        controls = self.window._comparison_controls
        controls.region_a.setCurrentIndex(controls.region_a.findData(layer_id))
        controls.result = {"existing": True}
        remove_layer(self.window, layer)
        self.assertNotIn(layer_id, self.window._managed_layers)
        self.assertIs(self.window._active_raster_layer, self.layers[1])
        self.assertIsNone(controls.result)
        self.assertTrue((self.root / "a.tif").is_file())

    def test_remove_active_clears_results_and_allows_new_source(self):
        self.window._statistics_result = calculate_raster_statistics(self.layers[1].source())
        self.window.create_profile([(120.05, 23.85), (120.4, 23.85)])
        remove_layer(self.window, self.layers[1])
        self.assertIsNone(self.window._active_raster_path)
        self.assertIsNone(self.window._statistics_result)
        self.assertIsNone(self.window._profile_result)
        self.assertFalse(self.window.point_query_action.isEnabled())
        self.assertFalse(self.window.statistics_action.isEnabled())
        self.assertTrue((self.root / "b.tif").is_file())
        self.window.layer_tree.setCurrentItem(self.window._layer_items[self.layers[0].id()])
        self.window.set_selected_analysis_source()
        self.assertIs(self.window._active_raster_layer, self.layers[0])
        self.assertTrue(self.window.point_query_action.isEnabled())

    def test_running_analysis_blocks_removal(self):
        self.window._statistics_worker = object()
        try:
            actions = self.menu(self.layers[0])
            self.assertFalse(actions["移除图层（保留文件）"].isEnabled())
            remove_layer(self.window, self.layers[0])
            self.assertIn(self.layers[0].id(), self.window._managed_layers)
        finally:
            self.window._statistics_worker = None
