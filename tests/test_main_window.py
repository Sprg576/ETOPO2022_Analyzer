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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from qgis.PyQt.QtCore import Qt

from qgis.core import (
    QgsApplication,
    QgsPointXY,
    QgsProject,
)

from etopo_analyzer.core.layer_manager import (
    create_raster_layer,
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

        cls.layer = create_raster_layer(
            str(RASTER_PATH)
        )

        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)

    @classmethod
    def tearDownClass(cls):
        QgsProject.instance().clear()
        cls.temp_directory.cleanup()

    def setUp(self):
        QgsProject.instance().clear()

        self.window = ETOPOAnalyzerMainWindow()

        self.window._clip_output_directory = (
            self.temp_path / self._testMethodName
        )

    def tearDown(self):
        self.window.close()
        self.window = None
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
