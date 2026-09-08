"""
F06-3 坡度与坡向可视化独立测试。

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


from qgis.PyQt import sip
from qgis.PyQt.QtGui import QColor

from qgis.core import (
    QgsApplication,
    QgsColorRampShader,
    QgsRasterLayer,
    QgsSingleBandPseudoColorRenderer,
)

from etopo_analyzer.visualization.terrain_analysis_renderer import (
    ASPECT_DIRECTION_CLASSES,
    SLOPE_COLOR_CLASSES,
    apply_aspect_direction_colors,
    apply_slope_color_relief,
)


class TestTerrainAnalysisRenderer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qgs = QgsApplication.instance()

        if cls.qgs is None:
            cls.qgs = QgsApplication([], True)
            cls.qgs.initQgis()

        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)
        cls.slope_path = cls.temp_path / "slope.tif"
        cls.aspect_path = cls.temp_path / "aspect.tif"
        cls._create_raster(
            cls.slope_path,
            np.array(
                [[1.0, 3.0, 10.0, 20.0, 30.0, 40.0, 60.0]],
                dtype=np.float32,
            ),
        )
        cls._create_raster(
            cls.aspect_path,
            np.array(
                [[-9999.0, 0.0, 45.0, 90.0, 180.0, 270.0, 359.0]],
                dtype=np.float32,
            ),
            nodata=-9999.0,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    @classmethod
    def _create_raster(
        cls,
        path: Path,
        values: np.ndarray,
        nodata: float | None = None,
    ) -> None:
        dataset = gdal.GetDriverByName("GTiff").Create(
            str(path),
            values.shape[1],
            values.shape[0],
            1,
            gdal.GDT_Float32,
        )
        dataset.SetGeoTransform(
            (
                500000.0,
                10.0,
                0.0,
                3500000.0,
                0.0,
                -10.0,
            )
        )
        dataset.SetProjection(
            CRS.from_epsg(32651).to_wkt()
        )
        band = dataset.GetRasterBand(1)

        if nodata is not None:
            band.SetNoDataValue(nodata)

        band.WriteArray(values)
        dataset = None

    def setUp(self):
        self.slope_layer = QgsRasterLayer(
            str(self.slope_path),
            "slope",
            "gdal",
        )
        self.aspect_layer = QgsRasterLayer(
            str(self.aspect_path),
            "aspect",
            "gdal",
        )
        self.assertTrue(self.slope_layer.isValid())
        self.assertTrue(self.aspect_layer.isValid())

    def tearDown(self):
        for layer in (
            self.slope_layer,
            self.aspect_layer,
        ):
            if layer is not None and not sip.isdeleted(layer):
                sip.delete(layer)

        self.slope_layer = None
        self.aspect_layer = None

    @staticmethod
    def _shader_color(shader, value: float) -> str:
        success, red, green, blue, alpha = shader.shade(value)

        if not success:
            raise AssertionError(
                f"着色器无法渲染测试值：{value}"
            )

        return QColor(
            red,
            green,
            blue,
            alpha,
        ).name().upper()

    def test_slope_uses_fixed_seven_class_renderer(self):
        renderer = apply_slope_color_relief(
            self.slope_layer
        )

        self.assertIsInstance(
            renderer,
            QgsSingleBandPseudoColorRenderer,
        )
        self.assertEqual(renderer.band(), 1)
        self.assertEqual(renderer.classificationMin(), 0.0)
        self.assertEqual(renderer.classificationMax(), 90.0)

        shader = renderer.shader().rasterShaderFunction()
        self.assertIsInstance(shader, QgsColorRampShader)
        self.assertEqual(
            shader.colorRampType(),
            QgsColorRampShader.Discrete,
        )
        items = shader.colorRampItemList()
        self.assertEqual(len(items), 7)
        self.assertEqual(
            [item.value for item in items],
            [item[0] for item in SLOPE_COLOR_CLASSES],
        )
        self.assertEqual(
            [item.label for item in items],
            [item[2] for item in SLOPE_COLOR_CLASSES],
        )

    def test_slope_values_use_expected_classes(self):
        renderer = apply_slope_color_relief(
            self.slope_layer
        )
        shader = renderer.shader().rasterShaderFunction()

        for value, expected_class in zip(
            (1.0, 3.0, 10.0, 20.0, 30.0, 40.0, 60.0),
            SLOPE_COLOR_CLASSES,
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    self._shader_color(shader, value),
                    expected_class[1],
                )

    def test_aspect_uses_cyclic_direction_renderer(self):
        renderer = apply_aspect_direction_colors(
            self.aspect_layer
        )

        self.assertIsInstance(
            renderer,
            QgsSingleBandPseudoColorRenderer,
        )
        self.assertEqual(renderer.band(), 1)
        self.assertEqual(renderer.classificationMin(), 0.0)
        self.assertEqual(renderer.classificationMax(), 360.0)

        shader = renderer.shader().rasterShaderFunction()
        self.assertEqual(
            shader.colorRampType(),
            QgsColorRampShader.Discrete,
        )
        items = shader.colorRampItemList()
        self.assertEqual(len(items), 9)
        self.assertEqual(
            [item.label for item in items],
            ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"],
        )
        self.assertEqual(
            items[0].color.name().upper(),
            items[-1].color.name().upper(),
        )

    def test_aspect_values_use_expected_directions(self):
        renderer = apply_aspect_direction_colors(
            self.aspect_layer
        )
        shader = renderer.shader().rasterShaderFunction()
        expected_colors = {
            0.0: ASPECT_DIRECTION_CLASSES[0][1],
            10.0: ASPECT_DIRECTION_CLASSES[0][1],
            45.0: ASPECT_DIRECTION_CLASSES[1][1],
            90.0: ASPECT_DIRECTION_CLASSES[2][1],
            135.0: ASPECT_DIRECTION_CLASSES[3][1],
            180.0: ASPECT_DIRECTION_CLASSES[4][1],
            225.0: ASPECT_DIRECTION_CLASSES[5][1],
            270.0: ASPECT_DIRECTION_CLASSES[6][1],
            315.0: ASPECT_DIRECTION_CLASSES[7][1],
            350.0: ASPECT_DIRECTION_CLASSES[8][1],
            360.0: ASPECT_DIRECTION_CLASSES[8][1],
        }

        for value, expected_color in expected_colors.items():
            with self.subTest(value=value):
                self.assertEqual(
                    self._shader_color(shader, value),
                    expected_color,
                )

    def test_aspect_flat_nodata_stays_out_of_direction_classes(self):
        apply_aspect_direction_colors(
            self.aspect_layer
        )
        provider = self.aspect_layer.dataProvider()

        self.assertTrue(provider.sourceHasNoDataValue(1))
        self.assertTrue(provider.useSourceNoDataValue(1))
        self.assertEqual(
            provider.sourceNoDataValue(1),
            -9999.0,
        )
        self.assertNotIn(
            -9999.0,
            [item[0] for item in ASPECT_DIRECTION_CLASSES],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
