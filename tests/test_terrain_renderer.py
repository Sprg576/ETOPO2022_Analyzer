"""
F05 固定陆海分层设色与 Hillshade 图层样式测试。

运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal
from pyproj import CRS


gdal.UseExceptions()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from qgis.PyQt.QtGui import QPainter

from qgis.core import (
    QgsApplication,
    QgsColorRampShader,
    QgsRasterLayer,
    QgsSingleBandGrayRenderer,
    QgsSingleBandPseudoColorRenderer,
)

from etopo_analyzer.visualization.terrain_renderer import (
    ETOPO_COLOR_RELIEF,
    apply_etopo_color_relief,
    configure_hillshade_overlay,
)


class TestTerrainRenderer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qgs = QgsApplication.instance()

        if cls.qgs is None:
            cls.qgs = QgsApplication([], True)
            cls.qgs.initQgis()

        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.raster_path = (
            Path(cls.temp_directory.name)
            / "terrain.tif"
        )

        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(
            str(cls.raster_path),
            4,
            3,
            1,
            gdal.GDT_Float32,
        )
        dataset.SetGeoTransform(
            (120.0, 0.1, 0.0, 31.0, 0.0, -0.1)
        )
        dataset.SetProjection(
            CRS.from_epsg(4326).to_wkt()
        )
        dataset.GetRasterBand(1).SetNoDataValue(
            -99999.0
        )
        dataset.GetRasterBand(1).WriteArray(
            np.array(
                [
                    [-6000.0, -2000.0, -200.0, 0.0],
                    [1.0, 200.0, 1000.0, 2000.0],
                    [3000.0, 4000.0, 6000.0, 8000.0],
                ],
                dtype=np.float32,
            )
        )
        dataset = None

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    def setUp(self):
        self.layer = QgsRasterLayer(
            str(self.raster_path),
            "terrain",
            "gdal",
        )
        self.assertTrue(self.layer.isValid())

    def tearDown(self):
        self.layer = None

    def test_fixed_color_relief_renderer(self):
        renderer = apply_etopo_color_relief(
            self.layer
        )

        self.assertIsInstance(
            renderer,
            QgsSingleBandPseudoColorRenderer,
        )
        self.assertEqual(renderer.band(), 1)
        self.assertEqual(
            renderer.classificationMin(),
            -11000.0,
        )
        self.assertEqual(
            renderer.classificationMax(),
            9000.0,
        )

        shader_function = (
            renderer.shader()
            .rasterShaderFunction()
        )
        self.assertIsInstance(
            shader_function,
            QgsColorRampShader,
        )

        items = shader_function.colorRampItemList()
        self.assertEqual(len(items), len(ETOPO_COLOR_RELIEF))
        self.assertEqual(
            [item.value for item in items],
            [item[0] for item in ETOPO_COLOR_RELIEF],
        )
        self.assertEqual(
            [item.color.name().upper() for item in items],
            [item[1] for item in ETOPO_COLOR_RELIEF],
        )

    def test_color_relief_does_not_modify_source(self):
        before = gdal.Open(
            str(self.raster_path),
            gdal.GA_ReadOnly,
        ).ReadAsArray()
        source_crs = self.layer.crs().authid()

        apply_etopo_color_relief(self.layer)

        after = gdal.Open(
            str(self.raster_path),
            gdal.GA_ReadOnly,
        ).ReadAsArray()

        np.testing.assert_array_equal(before, after)
        self.assertEqual(self.layer.crs().authid(), source_crs)

    def test_hillshade_overlay_style(self):
        renderer = configure_hillshade_overlay(
            self.layer
        )

        self.assertIsInstance(
            renderer,
            QgsSingleBandGrayRenderer,
        )
        self.assertEqual(renderer.grayBand(), 1)
        self.assertAlmostEqual(renderer.opacity(), 0.60)
        self.assertEqual(
            self.layer.blendMode(),
            QPainter.CompositionMode_Multiply,
        )

    def test_invalid_hillshade_opacity(self):
        with self.assertRaises(ValueError):
            configure_hillshade_overlay(
                self.layer,
                opacity=1.1,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
