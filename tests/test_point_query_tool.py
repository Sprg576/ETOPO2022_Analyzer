"""
test_point_query_tool.py

F03 鼠标单点查询地图工具测试。

运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

import sys
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
    QgsPointXY,
)

from qgis.gui import QgsMapCanvas

from etopo_analyzer.ui.point_query_tool import (
    PointQueryMapTool,
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


class TestPointQueryMapTool(unittest.TestCase):

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

        self.map_tool = PointQueryMapTool(
            self.canvas,
            "test_raster.tif",
        )

    def tearDown(self):
        self.canvas.setLayers([])
        self.map_tool = None
        self.canvas = None

    @patch(
        "etopo_analyzer.ui.point_query_tool."
        "query_point_elevation"
    )
    def test_left_click_calls_core_query(
        self,
        mock_query,
    ):
        expected_result = {
            "longitude": 121.5,
            "latitude": 31.2,
            "elevation": 2.3,
            "depth": None,
            "is_nodata": False,
        }

        mock_query.return_value = expected_result

        succeeded_results = []

        self.map_tool.query_succeeded.connect(
            succeeded_results.append
        )

        event = FakeMapMouseEvent(
            QgsPointXY(
                121.5,
                31.2,
            )
        )

        self.map_tool.canvasReleaseEvent(
            event
        )

        mock_query.assert_called_once_with(
            "test_raster.tif",
            121.5,
            31.2,
        )

        self.assertEqual(
            succeeded_results,
            [expected_result],
        )

    @patch(
        "etopo_analyzer.ui.point_query_tool."
        "query_point_elevation"
    )
    def test_canvas_coordinate_is_transformed_to_wgs84(
        self,
        mock_query,
    ):
        self.canvas.setDestinationCrs(
            QgsCoordinateReferenceSystem(
                "EPSG:3857"
            )
        )

        mock_query.return_value = {
            "elevation": 10.0,
            "depth": None,
            "is_nodata": False,
        }

        event = FakeMapMouseEvent(
            QgsPointXY(
                111319.49079327357,
                111325.1428663851,
            )
        )

        self.map_tool.canvasReleaseEvent(
            event
        )

        mock_query.assert_called_once()

        _path, longitude, latitude = (
            mock_query.call_args.args
        )

        self.assertAlmostEqual(
            longitude,
            1.0,
            places=8,
        )

        self.assertAlmostEqual(
            latitude,
            1.0,
            places=8,
        )

    @patch(
        "etopo_analyzer.ui.point_query_tool."
        "query_point_elevation"
    )
    def test_right_click_is_ignored(
        self,
        mock_query,
    ):
        event = FakeMapMouseEvent(
            QgsPointXY(
                121.5,
                31.2,
            ),
            Qt.RightButton,
        )

        self.map_tool.canvasReleaseEvent(
            event
        )

        mock_query.assert_not_called()

    @patch(
        "etopo_analyzer.ui.point_query_tool."
        "query_point_elevation"
    )
    def test_query_error_emits_failed_signal(
        self,
        mock_query,
    ):
        mock_query.side_effect = ValueError(
            "查询点位于栅格有效范围之外。"
        )

        failed_messages = []
        succeeded_results = []

        self.map_tool.query_failed.connect(
            failed_messages.append
        )

        self.map_tool.query_succeeded.connect(
            succeeded_results.append
        )

        event = FakeMapMouseEvent(
            QgsPointXY(
                121.5,
                31.2,
            )
        )

        self.map_tool.canvasReleaseEvent(
            event
        )

        self.assertEqual(
            failed_messages,
            ["查询点位于栅格有效范围之外。"],
        )

        self.assertEqual(
            succeeded_results,
            [],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
