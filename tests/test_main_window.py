"""
test_main_window.py

F03 单点查询主窗口集成测试。

运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from qgis.PyQt.QtCore import Qt

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
    QgsSingleBandGrayRenderer,
    QgsSingleBandPseudoColorRenderer,
)

from etopo_analyzer.core.layer_manager import (
    create_raster_layer,
)
from etopo_analyzer.core.point_query import (
    query_point_elevation,
)
from etopo_analyzer.core.raster_clip import (
    clip_raster_by_bounds,
)

from etopo_analyzer.ui.main_window import (
    ETOPOAnalyzerMainWindow,
)


RASTER_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "ETOPO_2022_v1_60s_N90W180_surface.tif"
)


class FakeMapMouseEvent:
    """测试用的最小 Canvas 左键事件。"""

    def __init__(self, map_point: QgsPointXY):
        self._map_point = map_point

    def mapPoint(self) -> QgsPointXY:
        return self._map_point

    def button(self):
        return Qt.LeftButton


class TestMainWindowPointQuery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not RASTER_PATH.is_file():
            raise FileNotFoundError(
                f"GeoTIFF 测试数据不存在：{RASTER_PATH}"
            )

        cls.qgs = QgsApplication.instance()

        if cls.qgs is None:
            cls.qgs = QgsApplication(
                [],
                True,
            )

            cls.qgs.initQgis()

        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)

    @classmethod
    def tearDownClass(cls):
        QgsProject.instance().clear()
        cls.temp_directory.cleanup()

    def setUp(self):
        QgsProject.instance().clear()

        self.layer = create_raster_layer(
            str(RASTER_PATH)
        )
        self.window = ETOPOAnalyzerMainWindow()

        self.window._clip_output_directory = (
            self.temp_path / self._testMethodName
        )

    def tearDown(self):
        self.window.close()
        self.window = None
        self.layer = None
        QgsProject.instance().clear()

    def test_point_query_is_enabled_after_show_layer(self):
        self.assertFalse(
            self.window.point_query_action.isEnabled()
        )

        self.window.show_layer(
            self.layer
        )

        self.assertTrue(
            self.window.point_query_action.isEnabled()
        )

        self.assertIsNotNone(
            self.window._point_query_tool
        )

    def test_point_query_action_activates_map_tool(self):
        self.window.show_layer(
            self.layer
        )

        self.window.point_query_action.trigger()

        self.assertIs(
            self.window.map_canvas.mapTool(),
            self.window._point_query_tool,
        )

        self.assertEqual(
            self.window.statusBar().currentMessage(),
            "单点查询：请在地图上单击。",
        )

    def test_real_map_click_displays_depth(self):
        self.window.show_layer(
            self.layer
        )

        event = FakeMapMouseEvent(
            QgsPointXY(
                73.631785,
                -29.311696,
            )
        )

        self.window._point_query_tool.canvasReleaseEvent(
            event
        )

        self.assertEqual(
            self.window.statusBar().currentMessage(),
            "经度：73.631785° E | "
            "纬度：29.311696° S | "
            "近似水深：3680.19 m",
        )

    def test_west_north_coordinates_display_directions(self):
        self.window._show_point_query_result(
            {
                "longitude": -74.0,
                "latitude": 40.7,
                "elevation": 13.46,
                "depth": None,
                "is_nodata": False,
            }
        )

        self.assertEqual(
            self.window.statusBar().currentMessage(),
            "经度：74.000000° W | "
            "纬度：40.700000° N | "
            "高程：13.46 m",
        )

    def test_query_error_is_displayed(self):
        self.window._show_point_query_error(
            "测试错误"
        )

        self.assertEqual(
            self.window.statusBar().currentMessage(),
            "查询失败：测试错误",
        )

    def test_rectangle_clip_is_enabled_after_show_layer(self):
        self.assertFalse(
            self.window.rectangle_clip_action.isEnabled()
        )

        self.window.show_layer(
            self.layer
        )

        self.assertTrue(
            self.window.rectangle_clip_action.isEnabled()
        )

        self.assertIsNotNone(
            self.window._rectangle_selection_tool
        )

    def test_rectangle_clip_action_activates_map_tool(self):
        self.window.show_layer(
            self.layer
        )

        self.window.rectangle_clip_action.trigger()

        self.assertIs(
            self.window.map_canvas.mapTool(),
            self.window._rectangle_selection_tool,
        )

        self.assertEqual(
            self.window.statusBar().currentMessage(),
            "矩形裁剪：请按住左键拖拽选择范围。",
        )

    def test_real_rectangle_clip_is_auto_loaded(self):
        self.window.show_layer(
            self.layer
        )

        self.window.rectangle_clip_action.trigger()

        rectangle_tool = (
            self.window._rectangle_selection_tool
        )

        rectangle_tool.canvasPressEvent(
            FakeMapMouseEvent(
                QgsPointXY(120.0, 30.0)
            )
        )

        rectangle_tool.canvasMoveEvent(
            FakeMapMouseEvent(
                QgsPointXY(121.0, 31.0)
            )
        )

        rectangle_tool.canvasReleaseEvent(
            FakeMapMouseEvent(
                QgsPointXY(121.0, 31.0)
            )
        )

        canvas_layers = self.window.map_canvas.layers()

        self.assertEqual(
            len(canvas_layers),
            1,
        )

        output_layer = canvas_layers[0]

        self.assertTrue(
            output_layer.isValid()
        )

        self.assertEqual(
            output_layer.width(),
            60,
        )

        self.assertEqual(
            output_layer.height(),
            60,
        )

        self.assertIn(
            output_layer.id(),
            QgsProject.instance().mapLayers(),
        )

        output_path = Path(
            output_layer.source()
        )

        self.assertTrue(
            output_path.is_file()
        )

        self.assertEqual(
            output_path.parent,
            self.window._clip_output_directory,
        )

        self.assertEqual(
            self.window.statusBar().currentMessage(),
            f"裁剪完成：{output_path.name} | "
            "60 × 60 像元",
        )

        self.assertTrue(
            self.window.pan_action.isChecked()
        )

    def test_color_relief_is_enabled_after_show_layer(self):
        self.assertFalse(
            self.window.color_relief_action.isEnabled()
        )

        self.window.show_layer(self.layer)

        self.assertTrue(
            self.window.color_relief_action.isEnabled()
        )

    def test_color_relief_action_applies_renderer(self):
        self.window.show_layer(self.layer)

        self.window.color_relief_action.trigger()

        self.assertIsInstance(
            self.layer.renderer(),
            QgsSingleBandPseudoColorRenderer,
        )
        self.assertEqual(
            self.window.statusBar().currentMessage(),
            "分层设色完成：已应用固定陆海地形色带。",
        )

    def test_hillshade_is_enabled_after_show_layer(self):
        self.assertFalse(
            self.window.hillshade_action.isEnabled()
        )

        self.window.show_layer(self.layer)

        self.assertTrue(
            self.window.hillshade_action.isEnabled()
        )

    def test_local_hillshade_is_combined_with_color_dem(self):
        self.window.show_layer(self.layer)
        self.window._clip_selected_bounds(
            {
                "west": 120.0,
                "south": 30.0,
                "east": 121.0,
                "north": 31.0,
            }
        )

        analysis_path = self.window._active_raster_path
        analysis_layer = self.window._active_raster_layer
        point_query_tool = self.window._point_query_tool
        rectangle_selection_tool = (
            self.window._rectangle_selection_tool
        )

        self.window.hillshade_action.trigger()

        canvas_layers = self.window.map_canvas.layers()
        self.assertEqual(len(canvas_layers), 2)

        hillshade_layer = canvas_layers[0]
        projected_layer = canvas_layers[1]

        self.assertIsInstance(
            hillshade_layer.renderer(),
            QgsSingleBandGrayRenderer,
        )
        self.assertIsInstance(
            projected_layer.renderer(),
            QgsSingleBandPseudoColorRenderer,
        )
        self.assertEqual(
            projected_layer.crs().authid(),
            "EPSG:32651",
        )
        self.assertEqual(
            self.window._active_raster_path,
            analysis_path,
        )
        self.assertIs(
            self.window._active_raster_layer,
            analysis_layer,
        )
        self.assertIs(
            self.window._display_raster_layer,
            projected_layer,
        )
        self.assertIs(
            self.window._hillshade_layer,
            hillshade_layer,
        )
        self.assertIs(
            self.window._point_query_tool,
            point_query_tool,
        )
        self.assertIs(
            self.window._rectangle_selection_tool,
            rectangle_selection_tool,
        )
        self.assertTrue(
            Path(projected_layer.source()).is_file()
        )
        self.assertTrue(
            Path(hillshade_layer.source()).is_file()
        )
        self.assertTrue(
            self.window.statusBar()
            .currentMessage()
            .startswith(
                "Hillshade 完成：EPSG:32651"
            )
        )

    def test_point_query_still_uses_analysis_raster_after_hillshade(self):
        self.window.show_layer(self.layer)
        self.window._clip_selected_bounds(
            {
                "west": 120.0,
                "south": 30.0,
                "east": 121.0,
                "north": 31.0,
            }
        )
        analysis_path = self.window._active_raster_path

        self.window.create_hillshade()

        self.assertEqual(
            self.window._point_query_tool._raster_path,
            analysis_path,
        )

        to_canvas_crs = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            self.window.map_canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )
        canvas_point = to_canvas_crs.transform(
            QgsPointXY(120.5, 30.5)
        )
        result = self.window._point_query_tool.query_map_point(
            canvas_point
        )
        expected = query_point_elevation(
            analysis_path,
            120.5,
            30.5,
        )

        self.assertAlmostEqual(
            result["longitude"],
            expected["longitude"],
            places=9,
        )
        self.assertAlmostEqual(
            result["latitude"],
            expected["latitude"],
            places=9,
        )
        self.assertEqual(
            result["column"],
            expected["column"],
        )
        self.assertEqual(
            result["row"],
            expected["row"],
        )
        self.assertEqual(
            result["elevation"],
            expected["elevation"],
        )
        self.assertEqual(
            result["depth"],
            expected["depth"],
        )
        self.assertEqual(
            result["is_nodata"],
            expected["is_nodata"],
        )

    def test_rectangle_clip_still_uses_analysis_raster_after_hillshade(self):
        self.window.show_layer(self.layer)
        self.window._clip_selected_bounds(
            {
                "west": 120.0,
                "south": 30.0,
                "east": 121.0,
                "north": 31.0,
            }
        )
        analysis_path = self.window._active_raster_path

        self.window.create_hillshade()

        with patch(
            "etopo_analyzer.ui.main_window.clip_raster_by_bounds",
            wraps=clip_raster_by_bounds,
        ) as clip_mock:
            self.window._clip_selected_bounds(
                {
                    "west": 120.25,
                    "south": 30.25,
                    "east": 120.75,
                    "north": 30.75,
                }
            )

        self.assertEqual(
            clip_mock.call_args.args[0],
            analysis_path,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
