"""
test_raster_clip.py

F04 经纬度矩形区域核心裁剪测试。

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
from pyproj import CRS, Transformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from etopo_analyzer.core.raster_clip import (
    clip_raster_by_bounds,
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


class TestRasterClip(unittest.TestCase):

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
            4,
            3,
            1,
            gdal.GDT_Float32,
        )

        dataset.SetGeoTransform(
            (100.0, 1.0, 0.0, 13.0, 0.0, -1.0)
        )

        dataset.SetProjection(
            CRS.from_epsg(4326).to_wkt()
        )

        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(-99999.0)
        band.WriteArray(
            np.array(
                [
                    [0.0, 1.0, 2.0, 3.0],
                    [4.0, 5.0, 6.0, 7.0],
                    [8.0, 9.0, 10.0, 11.0],
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
            4,
            3,
            1,
            gdal.GDT_Float32,
        )

        dataset.SetGeoTransform(
            (0.0, 100000.0, 0.0, 300000.0, 0.0, -100000.0)
        )

        dataset.SetProjection(
            CRS.from_epsg(3857).to_wkt()
        )

        dataset.GetRasterBand(1).WriteArray(
            np.arange(
                12,
                dtype=np.float32,
            ).reshape(3, 4)
        )

        dataset = None

    def _output_path(self, name: str) -> Path:
        return self.temp_path / f"{name}.tif"

    def test_exact_pixel_aligned_clip(self):
        output_path = self._output_path(
            "exact_pixel_aligned"
        )

        result = clip_raster_by_bounds(
            str(self.geographic_path),
            str(output_path),
            101.0,
            11.0,
            103.0,
            13.0,
        )

        self.assertEqual(result["width"], 2)
        self.assertEqual(result["height"], 2)
        self.assertEqual(result["band_count"], 1)
        self.assertEqual(
            result["source_window"],
            (1, 0, 2, 2),
        )
        self.assertEqual(
            result["bounds"],
            (101.0, 11.0, 103.0, 13.0),
        )

        dataset = gdal.Open(
            str(output_path),
            gdal.GA_ReadOnly,
        )

        try:
            np.testing.assert_array_equal(
                dataset.ReadAsArray(),
                np.array(
                    [
                        [1.0, 2.0],
                        [5.0, 6.0],
                    ],
                    dtype=np.float32,
                ),
            )

            band = dataset.GetRasterBand(1)
            self.assertEqual(
                band.GetNoDataValue(),
                -99999.0,
            )

            self.assertEqual(
                dataset.GetMetadata(
                    "IMAGE_STRUCTURE"
                ).get("COMPRESSION"),
                "DEFLATE",
            )
        finally:
            dataset = None

    def test_partial_intersection_is_clipped_to_source(self):
        result = clip_raster_by_bounds(
            str(self.geographic_path),
            str(self._output_path("partial")),
            99.0,
            12.0,
            101.0,
            14.0,
        )

        self.assertEqual(
            result["source_window"],
            (0, 0, 1, 1),
        )

        self.assertEqual(
            result["bounds"],
            (100.0, 12.0, 101.0, 13.0),
        )

    def test_outside_source_extent(self):
        with self.assertRaisesRegex(
            ValueError,
            "没有有效交集",
        ):
            clip_raster_by_bounds(
                str(self.geographic_path),
                str(self._output_path("outside")),
                0.0,
                0.0,
                1.0,
                1.0,
            )

    def test_invalid_bounds(self):
        invalid_bounds = [
            (-181.0, 0.0, 1.0, 1.0),
            (0.0, -91.0, 1.0, 1.0),
            (10.0, 0.0, -10.0, 1.0),
            (0.0, 10.0, 1.0, -10.0),
            (0.0, 0.0, float("nan"), 1.0),
        ]

        for index, bounds in enumerate(invalid_bounds):
            with self.subTest(bounds=bounds):
                with self.assertRaises(ValueError):
                    clip_raster_by_bounds(
                        str(self.geographic_path),
                        str(
                            self._output_path(
                                f"invalid_{index}"
                            )
                        ),
                        *bounds,
                    )

    def test_missing_source_file(self):
        with self.assertRaises(FileNotFoundError):
            clip_raster_by_bounds(
                str(self.temp_path / "missing.tif"),
                str(self._output_path("missing_source")),
                100.0,
                11.0,
                101.0,
                12.0,
            )

    def test_output_extension_must_be_geotiff(self):
        with self.assertRaisesRegex(
            ValueError,
            r"\.tif",
        ):
            clip_raster_by_bounds(
                str(self.geographic_path),
                str(self.temp_path / "output.png"),
                100.0,
                11.0,
                101.0,
                12.0,
            )

    def test_existing_output_is_not_overwritten(self):
        output_path = self._output_path(
            "existing"
        )
        output_path.touch()

        with self.assertRaises(FileExistsError):
            clip_raster_by_bounds(
                str(self.geographic_path),
                str(output_path),
                100.0,
                11.0,
                101.0,
                12.0,
            )

    def test_output_cannot_replace_source(self):
        with self.assertRaisesRegex(
            ValueError,
            "不能与源栅格路径相同",
        ):
            clip_raster_by_bounds(
                str(self.geographic_path),
                str(self.geographic_path),
                100.0,
                11.0,
                101.0,
                12.0,
            )

    def test_projected_source_crs(self):
        to_wgs84 = Transformer.from_crs(
            CRS.from_epsg(3857),
            CRS.from_epsg(4326),
            always_xy=True,
        )

        west, south = to_wgs84.transform(
            100000.0,
            100000.0,
        )

        east, north = to_wgs84.transform(
            300000.0,
            300000.0,
        )

        result = clip_raster_by_bounds(
            str(self.projected_path),
            str(self._output_path("projected_clip")),
            west,
            south,
            east,
            north,
        )

        self.assertEqual(
            result["source_window"],
            (1, 0, 2, 2),
        )

        self.assertEqual(result["width"], 2)
        self.assertEqual(result["height"], 2)


class TestETOPO2022RasterClip(unittest.TestCase):

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

        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    def test_real_geotiff_clip(self):
        output_path = self.temp_path / "real_geotiff.tif"

        result = clip_raster_by_bounds(
            str(GEOTIFF_PATH),
            str(output_path),
            120.0,
            30.0,
            121.0,
            31.0,
        )

        self.assertEqual(result["width"], 60)
        self.assertEqual(result["height"], 60)
        self.assertEqual(
            result["source_window"],
            (18000, 3540, 60, 60),
        )

        dataset = gdal.Open(
            str(output_path),
            gdal.GA_ReadOnly,
        )

        try:
            self.assertEqual(
                dataset.GetDriver().ShortName,
                "GTiff",
            )

            self.assertEqual(
                dataset.GetSpatialRef().GetAuthorityCode(None),
                "9518",
            )

            self.assertEqual(
                dataset.GetRasterBand(1).GetNoDataValue(),
                -99999.0,
            )
        finally:
            dataset = None

    def test_real_netcdf_direct_band_matches_geotiff(self):
        geotiff_output = (
            self.temp_path / "comparison_geotiff.tif"
        )

        netcdf_output = (
            self.temp_path / "comparison_netcdf.tif"
        )

        clip_raster_by_bounds(
            str(GEOTIFF_PATH),
            str(geotiff_output),
            120.0,
            30.0,
            121.0,
            31.0,
        )

        result = clip_raster_by_bounds(
            str(NETCDF_PATH),
            str(netcdf_output),
            120.0,
            30.0,
            121.0,
            31.0,
        )

        self.assertEqual(result["width"], 60)
        self.assertEqual(result["height"], 60)

        geotiff_dataset = gdal.Open(
            str(geotiff_output),
            gdal.GA_ReadOnly,
        )

        netcdf_dataset = gdal.Open(
            str(netcdf_output),
            gdal.GA_ReadOnly,
        )

        try:
            np.testing.assert_array_equal(
                geotiff_dataset.ReadAsArray(),
                netcdf_dataset.ReadAsArray(),
            )
        finally:
            geotiff_dataset = None
            netcdf_dataset = None


if __name__ == "__main__":
    unittest.main(verbosity=2)
