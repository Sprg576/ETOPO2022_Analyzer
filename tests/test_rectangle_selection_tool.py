"""
test_rectangle_selection_tool.py

F04 经纬度矩形框选地图工具测试。

运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from qgis.PyQt.QtCore import Qt

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsPointXY,
)

from qgis.gui import QgsMapCanvas

from etopo_analyzer.ui.rectangle_selection_tool import (
    RectangleSelectionMapTool,
)


class FakeMapMouseEvent:
    """测试用的最小 Canvas 鼠标事件。"""

    def __init__(
        self,
        map_point: QgsPointXY,
        button=Qt.LeftButton,
    ):
        self._map_point = map_point
        self._button = button

    def mapPoint(self) -> QgsPointXY:
        return self._map_point

    def button(self):
        return self._button


class TestRectangleSelectionMapTool(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qgs = QgsApplication.instance()

        if cls.qgs is None:
            cls.qgs = QgsApplication(
                [],
                True,
            )

            cls.qgs.initQgis()

    def setUp(self):
        self.canvas = QgsMapCanvas()

        self.canvas.setDestinationCrs(
            QgsCoordinateReferenceSystem(
                "EPSG:4326"
            )
        )

        self.map_tool = RectangleSelectionMapTool(
            self.canvas
        )

    def tearDown(self):
        self.map_tool.deactivate()
        self.map_tool = None
        self.canvas = None

    def _drag(
        self,
        start_point: QgsPointXY,
        end_point: QgsPointXY,
    ) -> None:
        self.map_tool.canvasPressEvent(
            FakeMapMouseEvent(start_point)
        )

        self.map_tool.canvasMoveEvent(
            FakeMapMouseEvent(end_point)
        )

        self.map_tool.canvasReleaseEvent(
            FakeMapMouseEvent(end_point)
        )

    def test_drag_emits_normalized_wgs84_bounds(self):
        selected_bounds = []

        self.map_tool.rectangle_selected.connect(
            selected_bounds.append
        )

        self._drag(
            QgsPointXY(121.0, 30.0),
            QgsPointXY(120.0, 31.0),
        )

        self.assertEqual(
            selected_bounds,
            [
                {
                    "west": 120.0,
                    "south": 30.0,
                    "east": 121.0,
                    "north": 31.0,
                }
            ],
        )

    def test_projected_canvas_is_transformed_to_wgs84(self):
        self.canvas.setDestinationCrs(
            QgsCoordinateReferenceSystem(
                "EPSG:3857"
            )
        )

        selected_bounds = []

        self.map_tool.rectangle_selected.connect(
            selected_bounds.append
        )

        self._drag(
            QgsPointXY(
                111319.49079327357,
                111325.1428663851,
            ),
            QgsPointXY(
                222638.98158654713,
                222684.20850554405,
            ),
        )

        self.assertEqual(
            len(selected_bounds),
            1,
        )

        bounds = selected_bounds[0]

        self.assertAlmostEqual(
            bounds["west"],
            1.0,
            places=8,
        )

        self.assertAlmostEqual(
            bounds["south"],
            1.0,
            places=8,
        )

        self.assertAlmostEqual(
            bounds["east"],
            2.0,
            places=8,
        )

        self.assertAlmostEqual(
            bounds["north"],
            2.0,
            places=8,
        )

    def test_drag_displays_rubber_band(self):
        self.map_tool.canvasPressEvent(
            FakeMapMouseEvent(
                QgsPointXY(120.0, 30.0)
            )
        )

        self.map_tool.canvasMoveEvent(
            FakeMapMouseEvent(
                QgsPointXY(121.0, 31.0)
            )
        )

        self.assertTrue(
            self.map_tool._rubber_band.isVisible()
        )

        self.map_tool.deactivate()

        self.assertFalse(
            self.map_tool._rubber_band.isVisible()
        )

    def test_zero_area_selection_emits_failure(self):
        failed_messages = []

        self.map_tool.selection_failed.connect(
            failed_messages.append
        )

        point = QgsPointXY(120.0, 30.0)

        self._drag(
            point,
            point,
        )

        self.assertEqual(
            failed_messages,
            ["请拖拽形成具有宽度和高度的矩形范围。"],
        )

    def test_right_button_is_ignored(self):
        selected_bounds = []

        self.map_tool.rectangle_selected.connect(
            selected_bounds.append
        )

        self.map_tool.canvasPressEvent(
            FakeMapMouseEvent(
                QgsPointXY(120.0, 30.0),
                Qt.RightButton,
            )
        )

        self.map_tool.canvasReleaseEvent(
            FakeMapMouseEvent(
                QgsPointXY(121.0, 31.0),
                Qt.RightButton,
            )
        )

        self.assertEqual(
            selected_bounds,
            [],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
