"""
test_point_query.py

F03 单点高程 / 水深核心查询测试。

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from etopo_analyzer.core.point_query import (
    query_point_elevation,
)


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


class TestPointQuery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)

        cls.geographic_path = (
            cls.temp_path / "geographic.tif"
        )

        cls.projected_path = (
            cls.temp_path / "projected.tif"
        )

        cls._create_geographic_raster()
        cls._create_projected_raster()

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    @classmethod
    def _create_geographic_raster(cls):
        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(
            str(cls.geographic_path),
            3,
            2,
            1,
            gdal.GDT_Float32,
        )

        dataset.SetGeoTransform(
            (100.0, 1.0, 0.0, 12.0, 0.0, -1.0)
        )

        dataset.SetProjection(
            CRS.from_epsg(4326).to_wkt()
        )

        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(-99999.0)
        band.WriteArray(
            np.array(
                [
                    [10.0, -20.0, -99999.0],
                    [30.0, 40.0, 50.0],
                ],
                dtype=np.float32,
            )
        )

        dataset = None

    @classmethod
    def _create_projected_raster(cls):
        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(
            str(cls.projected_path),
            3,
            2,
            1,
            gdal.GDT_Float32,
        )

        dataset.SetGeoTransform(
            (0.0, 100000.0, 0.0, 200000.0, 0.0, -100000.0)
        )

        dataset.SetProjection(
            CRS.from_epsg(3857).to_wkt()
        )

        dataset.GetRasterBand(1).WriteArray(
            np.array(
                [
                    [10.0, 20.0, 30.0],
                    [40.0, 50.0, 60.0],
                ],
                dtype=np.float32,
            )
        )

        dataset = None

    def test_positive_elevation(self):
        result = query_point_elevation(
            str(self.geographic_path),
            100.5,
            11.5,
        )

        self.assertEqual(result["column"], 0)
        self.assertEqual(result["row"], 0)
        self.assertEqual(result["elevation"], 10.0)
        self.assertIsNone(result["depth"])
        self.assertFalse(result["is_nodata"])

    def test_negative_elevation_calculates_depth(self):
        result = query_point_elevation(
            str(self.geographic_path),
            101.5,
            11.5,
        )

        self.assertEqual(result["elevation"], -20.0)
        self.assertEqual(result["depth"], 20.0)
        self.assertFalse(result["is_nodata"])

    def test_nodata(self):
        result = query_point_elevation(
            str(self.geographic_path),
            102.5,
            11.5,
        )

        self.assertIsNone(result["elevation"])
        self.assertIsNone(result["depth"])
        self.assertTrue(result["is_nodata"])

    def test_projected_raster_coordinate_transform(self):
        result = query_point_elevation(
            str(self.projected_path),
            1.0,
            1.0,
        )

        self.assertEqual(result["column"], 1)
        self.assertEqual(result["row"], 0)
        self.assertEqual(result["elevation"], 20.0)

    def test_invalid_longitude(self):
        with self.assertRaisesRegex(
            ValueError,
            "经度必须位于",
        ):
            query_point_elevation(
                str(self.geographic_path),
                180.1,
                0.0,
            )

    def test_invalid_latitude(self):
        with self.assertRaisesRegex(
            ValueError,
            "纬度必须位于",
        ):
            query_point_elevation(
                str(self.geographic_path),
                0.0,
                -90.1,
            )

    def test_point_outside_raster_extent(self):
        with self.assertRaisesRegex(
            ValueError,
            "栅格有效范围之外",
        ):
            query_point_elevation(
                str(self.geographic_path),
                0.0,
                0.0,
            )

    def test_missing_file(self):
        missing_path = self.temp_path / "missing.tif"

        with self.assertRaises(FileNotFoundError):
            query_point_elevation(
                str(missing_path),
                0.0,
                0.0,
            )


class TestETOPO2022PointQuery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not GEOTIFF_PATH.is_file():
            raise FileNotFoundError(
                f"GeoTIFF 测试数据不存在：{GEOTIFF_PATH}"
            )

        if not NETCDF_PATH.is_file():
            raise FileNotFoundError(
                f"NetCDF 测试数据不存在：{NETCDF_PATH}"
            )

    def test_real_geotiff_query(self):
        result = query_point_elevation(
            str(GEOTIFF_PATH),
            0.0,
            0.0,
        )

        self.assertEqual(result["column"], 10800)
        self.assertEqual(result["row"], 5400)
        self.assertAlmostEqual(
            result["elevation"],
            -4934.4130859375,
            places=6,
        )
        self.assertAlmostEqual(
            result["depth"],
            4934.4130859375,
            places=6,
        )

    def test_real_netcdf_reads_direct_band(self):
        result = query_point_elevation(
            str(NETCDF_PATH),
            0.0,
            0.0,
        )

        self.assertEqual(result["column"], 10800)
        self.assertEqual(result["row"], 5400)
        self.assertAlmostEqual(
            result["elevation"],
            -4934.4130859375,
            places=6,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
