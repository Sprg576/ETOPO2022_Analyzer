"""
test_raster_reader.py

对 raster_reader.py 进行自动化测试。

测试数据：
ETOPO_2022_v1_60s_N90W180_surface.tif

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
# 导入待测试模块
# ---------------------------------------------------------

from etopo_analyzer.core.raster_reader import read_raster_metadata


# ---------------------------------------------------------
# 测试数据路径
# ---------------------------------------------------------

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "ETOPO_2022_v1_60s_N90W180_surface.tif"
)


class TestRasterReader(unittest.TestCase):
    """
    ETOPO2022 GeoTIFF 元数据读取测试。
    """

    @classmethod
    def setUpClass(cls):
        """
        全部测试开始前只读取一次元数据。
        """

        if not DATA_PATH.is_file():
            raise FileNotFoundError(
                f"测试数据不存在：{DATA_PATH}"
            )

        cls.metadata = read_raster_metadata(
            str(DATA_PATH)
        )

    def test_file_name(self):
        self.assertEqual(
            self.metadata["file_name"],
            "ETOPO_2022_v1_60s_N90W180_surface.tif",
        )

    def test_driver(self):
        self.assertEqual(
            self.metadata["driver_short_name"],
            "GTiff",
        )

        self.assertEqual(
            self.metadata["driver_long_name"],
            "GeoTIFF",
        )

    def test_dimensions(self):
        self.assertEqual(
            self.metadata["width"],
            21600,
        )

        self.assertEqual(
            self.metadata["height"],
            10800,
        )

        self.assertEqual(
            self.metadata["band_count"],
            1,
        )

    def test_geotransform(self):
        geotransform = self.metadata["geotransform"]

        self.assertIsNotNone(
            geotransform
        )

        expected = (
            -180.0,
            1.0 / 60.0,
            0.0,
            90.0,
            0.0,
            -1.0 / 60.0,
        )

        for actual, expected_value in zip(
            geotransform,
            expected,
        ):
            self.assertAlmostEqual(
                actual,
                expected_value,
                places=12,
            )

    def test_pixel_size(self):
        self.assertAlmostEqual(
            self.metadata["pixel_size_x"],
            1.0 / 60.0,
            places=12,
        )

        self.assertAlmostEqual(
            self.metadata["pixel_size_y"],
            -1.0 / 60.0,
            places=12,
        )

    def test_bounds(self):
        west, south, east, north = (
            self.metadata["bounds"]
        )

        self.assertAlmostEqual(
            west,
            -180.0,
            places=8,
        )

        self.assertAlmostEqual(
            south,
            -90.0,
            places=8,
        )

        self.assertAlmostEqual(
            east,
            180.0,
            places=8,
        )

        self.assertAlmostEqual(
            north,
            90.0,
            places=8,
        )

    def test_crs(self):
        self.assertEqual(
            self.metadata["crs_authority"],
            "EPSG:9518",
        )

        self.assertEqual(
            self.metadata["crs_name"],
            "WGS 84 + EGM2008 height",
        )

    def test_compression(self):
        self.assertEqual(
            self.metadata["compression"],
            "DEFLATE",
        )

    def test_band_metadata(self):
        bands = self.metadata["bands"]

        self.assertEqual(
            len(bands),
            1,
        )

        band = bands[0]

        self.assertEqual(
            band["band"],
            1,
        )

        self.assertEqual(
            band["data_type"],
            "Float32",
        )

        self.assertEqual(
            band["nodata"],
            -99999.0,
        )

        self.assertEqual(
            band["scale"],
            1.0,
        )

        self.assertEqual(
            band["offset"],
            0.0,
        )

        self.assertEqual(
            band["unit"],
            "metre",
        )

        self.assertEqual(
            band["block_size"],
            [256, 256],
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )