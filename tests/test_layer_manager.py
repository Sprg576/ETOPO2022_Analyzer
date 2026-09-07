"""
test_layer_manager.py

测试 QgsRasterLayer 创建和 QgsProject 图层管理。

运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


# ---------------------------------------------------------
# 项目路径
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------
# QGIS
# ---------------------------------------------------------

from qgis.core import (
    QgsApplication,
    QgsProject,
)


# ---------------------------------------------------------
# 待测试模块
# ---------------------------------------------------------

from etopo_analyzer.core.layer_manager import (
    add_raster_layer,
    create_raster_layer,
    remove_layer,
)


# ---------------------------------------------------------
# 测试数据
# ---------------------------------------------------------

GEOTIFF_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "ETOPO_2022_v1_60s_N90W180_surface.tif"
)

NETCDF_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "ETOPO_2022_v1_60s_N90W180_surface.nc"
)


class TestLayerManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        if not GEOTIFF_PATH.is_file():
            raise FileNotFoundError(
                f"GeoTIFF 不存在：{GEOTIFF_PATH}"
            )

        if not NETCDF_PATH.is_file():
            raise FileNotFoundError(
                f"NetCDF 不存在：{NETCDF_PATH}"
            )

        # 初始化 QGIS
        cls.qgs = QgsApplication(
            [],
            False,
        )

        cls.qgs.initQgis()

    @classmethod
    def tearDownClass(cls):

        QgsProject.instance().clear()

        cls.qgs.exitQgis()

    def tearDown(self):

        QgsProject.instance().clear()

    def test_create_geotiff_layer(self):

        layer = create_raster_layer(
            str(GEOTIFF_PATH)
        )

        self.assertTrue(
            layer.isValid()
        )

        self.assertEqual(
            layer.width(),
            21600,
        )

        self.assertEqual(
            layer.height(),
            10800,
        )

    def test_create_netcdf_layer(self):

        layer = create_raster_layer(
            str(NETCDF_PATH)
        )

        self.assertTrue(
            layer.isValid()
        )

        self.assertEqual(
            layer.width(),
            21600,
        )

        self.assertEqual(
            layer.height(),
            10800,
        )

    def test_add_layer_to_project(self):

        layer = add_raster_layer(
            str(GEOTIFF_PATH),
            "ETOPO2022 Test",
        )

        project_layers = (
            QgsProject.instance().mapLayers()
        )

        self.assertIn(
            layer.id(),
            project_layers,
        )

        self.assertEqual(
            layer.name(),
            "ETOPO2022 Test",
        )

    def test_remove_layer(self):

        layer = add_raster_layer(
            str(GEOTIFF_PATH)
        )

        layer_id = layer.id()

        self.assertIn(
            layer_id,
            QgsProject.instance().mapLayers(),
        )

        remove_layer(
            layer_id
        )

        self.assertNotIn(
            layer_id,
            QgsProject.instance().mapLayers(),
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )