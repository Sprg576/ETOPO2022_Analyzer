"""
F05 局部米制投影与 Hillshade 独立测试。

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


from etopo_analyzer.core.hillshade import (
    generate_hillshade,
    project_raster_to_local_utm,
)


class TestHillshade(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)
        cls.source_path = cls.temp_path / "local_dem.tif"
        cls._create_local_dem()

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    @classmethod
    def _create_local_dem(cls):
        width = 100
        height = 100
        y, x = np.mgrid[0:height, 0:width]
        values = (
            100.0
            + x * 8.0
            + y * 4.0
            + 250.0 * np.sin(x / 10.0)
        ).astype(np.float32)
        values[0, 0] = -99999.0

        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(
            str(cls.source_path),
            width,
            height,
            1,
            gdal.GDT_Float32,
        )
        dataset.SetGeoTransform(
            (120.0, 0.01, 0.0, 31.0, 0.0, -0.01)
        )
        dataset.SetProjection(
            CRS.from_epsg(4326).to_wkt()
        )
        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(-99999.0)
        band.WriteArray(values)
        dataset = None

    def _output_path(self, name: str) -> Path:
        return self.temp_path / f"{name}.tif"

    def test_project_local_raster_to_utm(self):
        output_path = self._output_path("projected")

        result = project_raster_to_local_utm(
            str(self.source_path),
            str(output_path),
        )

        self.assertEqual(result["target_epsg"], 32651)
        self.assertTrue(output_path.is_file())
        self.assertGreater(result["width"], 0)
        self.assertGreater(result["height"], 0)

        dataset = gdal.Open(
            str(output_path),
            gdal.GA_ReadOnly,
        )

        try:
            spatial_ref = dataset.GetSpatialRef()
            self.assertTrue(spatial_ref.IsProjected())
            self.assertEqual(
                spatial_ref.GetAuthorityCode(None),
                "32651",
            )
            self.assertAlmostEqual(
                spatial_ref.GetLinearUnits(),
                1.0,
            )
            self.assertEqual(
                dataset.GetRasterBand(1).GetNoDataValue(),
                -99999.0,
            )
        finally:
            dataset = None

    def test_global_raster_is_rejected(self):
        global_path = self.temp_path / "global.tif"
        dataset = gdal.GetDriverByName("GTiff").Create(
            str(global_path),
            36,
            18,
            1,
            gdal.GDT_Float32,
        )
        dataset.SetGeoTransform(
            (-180.0, 10.0, 0.0, 90.0, 0.0, -10.0)
        )
        dataset.SetProjection(
            CRS.from_epsg(4326).to_wkt()
        )
        dataset = None

        with self.assertRaisesRegex(
            ValueError,
            "请先使用矩形裁剪",
        ):
            project_raster_to_local_utm(
                str(global_path),
                str(self._output_path("global_projected")),
            )

    def test_longitude_span_over_six_degrees_is_rejected(self):
        wide_path = self.temp_path / "wide_local.tif"
        dataset = gdal.GetDriverByName("GTiff").Create(
            str(wide_path),
            70,
            10,
            1,
            gdal.GDT_Float32,
        )
        dataset.SetGeoTransform(
            (120.0, 0.1, 0.0, 31.0, 0.0, -0.1)
        )
        dataset.SetProjection(
            CRS.from_epsg(4326).to_wkt()
        )
        dataset = None

        with self.assertRaisesRegex(
            ValueError,
            "不超过 6°",
        ):
            project_raster_to_local_utm(
                str(wide_path),
                str(self._output_path("wide_projected")),
            )

    def test_generate_hillshade_from_projected_dem(self):
        projected_path = self._output_path(
            "hillshade_projected"
        )
        hillshade_path = self._output_path("hillshade")

        projected = project_raster_to_local_utm(
            str(self.source_path),
            str(projected_path),
        )
        result = generate_hillshade(
            str(projected_path),
            str(hillshade_path),
        )

        self.assertEqual(
            (result["width"], result["height"]),
            (projected["width"], projected["height"]),
        )
        self.assertEqual(result["azimuth"], 315.0)
        self.assertEqual(result["altitude"], 45.0)

        dataset = gdal.Open(
            str(hillshade_path),
            gdal.GA_ReadOnly,
        )

        try:
            self.assertEqual(
                dataset.GetRasterBand(1).DataType,
                gdal.GDT_Byte,
            )
            values = dataset.ReadAsArray()
            valid_values = values[values > 0]
            self.assertGreater(valid_values.size, 0)
            self.assertGreater(
                np.ptp(valid_values),
                0,
            )
        finally:
            dataset = None

    def test_geographic_dem_cannot_generate_hillshade(self):
        with self.assertRaisesRegex(
            ValueError,
            "水平单位为米",
        ):
            generate_hillshade(
                str(self.source_path),
                str(self._output_path("invalid_hillshade")),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
