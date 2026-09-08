"""
F06-1 坡度与 F06-2 坡向分析独立测试。

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
    project_raster_to_local_utm,
)
from etopo_analyzer.core.terrain_analysis import (
    generate_aspect,
    generate_slope,
)


class TestTerrainAnalysis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)
        cls.geographic_path = (
            cls.temp_path / "local_dem.tif"
        )
        cls.planar_path = (
            cls.temp_path / "planar_utm_dem.tif"
        )
        cls.flat_path = (
            cls.temp_path / "flat_utm_dem.tif"
        )
        cls._create_geographic_dem()
        cls._create_planar_utm_dem()
        cls._create_flat_utm_dem()

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    @classmethod
    def _create_geographic_dem(cls):
        width = 100
        height = 100
        y, x = np.mgrid[0:height, 0:width]
        values = (
            100.0
            + x * 8.0
            + y * 4.0
            + 250.0 * np.sin(x / 10.0)
        ).astype(np.float32)

        dataset = gdal.GetDriverByName("GTiff").Create(
            str(cls.geographic_path),
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
        dataset.GetRasterBand(1).WriteArray(values)
        dataset = None

    @classmethod
    def _create_flat_utm_dem(cls):
        dataset = gdal.GetDriverByName("GTiff").Create(
            str(cls.flat_path),
            5,
            5,
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
        dataset.GetRasterBand(1).WriteArray(
            np.full((5, 5), 100.0, dtype=np.float32)
        )
        dataset = None

    @classmethod
    def _create_planar_utm_dem(cls):
        width = 5
        height = 5
        _y, x = np.mgrid[0:height, 0:width]
        values = (x * 10.0).astype(np.float32)

        dataset = gdal.GetDriverByName("GTiff").Create(
            str(cls.planar_path),
            width,
            height,
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
        dataset.GetRasterBand(1).WriteArray(values)
        dataset = None

    def _output_path(self, name: str) -> Path:
        return self.temp_path / f"{name}.tif"

    def test_local_dem_projection_and_slope_generation(self):
        projected_path = self._output_path(
            "projected_for_slope"
        )
        slope_path = self._output_path("slope")

        projected = project_raster_to_local_utm(
            str(self.geographic_path),
            str(projected_path),
        )
        result = generate_slope(
            str(projected_path),
            str(slope_path),
        )

        self.assertEqual(projected["target_epsg"], 32651)
        self.assertEqual(
            (result["width"], result["height"]),
            (projected["width"], projected["height"]),
        )
        self.assertEqual(result["band_count"], 1)
        self.assertEqual(result["slope_format"], "degree")
        self.assertEqual(result["algorithm"], "Horn")
        self.assertEqual(result["z_factor"], 1.0)
        self.assertTrue(slope_path.is_file())

        dataset = gdal.Open(
            str(slope_path),
            gdal.GA_ReadOnly,
        )

        try:
            self.assertEqual(
                dataset.GetSpatialRef().GetAuthorityCode(None),
                "32651",
            )
            self.assertEqual(
                dataset.GetRasterBand(1).DataType,
                gdal.GDT_Float32,
            )
            values = dataset.ReadAsArray()
            nodata = dataset.GetRasterBand(1).GetNoDataValue()
            valid_values = values[values != nodata]
            self.assertGreater(valid_values.size, 0)
            self.assertGreaterEqual(valid_values.min(), 0.0)
            self.assertLessEqual(valid_values.max(), 90.0)
            self.assertGreater(np.ptp(valid_values), 0.0)
        finally:
            dataset = None

    def test_planar_dem_returns_forty_five_degree_slope(self):
        slope_path = self._output_path("planar_slope")

        generate_slope(
            str(self.planar_path),
            str(slope_path),
        )

        dataset = gdal.Open(
            str(slope_path),
            gdal.GA_ReadOnly,
        )

        try:
            center_slope = float(
                dataset.GetRasterBand(1)
                .ReadAsArray(2, 2, 1, 1)[0, 0]
            )
            self.assertAlmostEqual(
                center_slope,
                45.0,
                places=5,
            )
        finally:
            dataset = None

    def test_geographic_dem_is_rejected(self):
        output_path = self._output_path(
            "invalid_geographic_slope"
        )

        with self.assertRaisesRegex(
            ValueError,
            "水平单位为米",
        ):
            generate_slope(
                str(self.geographic_path),
                str(output_path),
            )

        self.assertFalse(output_path.exists())

    def test_existing_output_is_not_overwritten(self):
        output_path = self._output_path(
            "existing_slope"
        )
        output_path.write_bytes(b"keep")

        with self.assertRaises(FileExistsError):
            generate_slope(
                str(self.planar_path),
                str(output_path),
            )

        self.assertEqual(
            output_path.read_bytes(),
            b"keep",
        )

    def test_slope_does_not_modify_source_dem(self):
        before_dataset = gdal.Open(
            str(self.planar_path),
            gdal.GA_ReadOnly,
        )
        before_values = before_dataset.ReadAsArray().copy()
        before_geotransform = before_dataset.GetGeoTransform()
        before_projection = before_dataset.GetProjection()
        before_dataset = None

        slope_path = self._output_path(
            "source_unchanged_slope"
        )

        generate_slope(
            str(self.planar_path),
            str(slope_path),
        )

        after_dataset = gdal.Open(
            str(self.planar_path),
            gdal.GA_ReadOnly,
        )
        after_values = after_dataset.ReadAsArray()
        after_geotransform = after_dataset.GetGeoTransform()
        after_projection = after_dataset.GetProjection()
        after_dataset = None

        np.testing.assert_array_equal(
            before_values,
            after_values,
        )
        self.assertEqual(
            before_geotransform,
            after_geotransform,
        )
        self.assertEqual(
            before_projection,
            after_projection,
        )

    def test_missing_source_is_rejected(self):
        missing_path = (
            self.temp_path / "missing_dem.tif"
        )

        with self.assertRaises(FileNotFoundError):
            generate_slope(
                str(missing_path),
                str(self._output_path("missing_slope")),
            )

    def test_source_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            generate_slope(
                str(self.planar_path),
                str(self.planar_path),
            )

    def test_local_dem_projection_and_aspect_generation(self):
        projected_path = self._output_path(
            "projected_for_aspect"
        )
        aspect_path = self._output_path("aspect")

        projected = project_raster_to_local_utm(
            str(self.geographic_path),
            str(projected_path),
        )
        result = generate_aspect(
            str(projected_path),
            str(aspect_path),
        )

        self.assertEqual(projected["target_epsg"], 32651)
        self.assertEqual(
            (result["width"], result["height"]),
            (projected["width"], projected["height"]),
        )
        self.assertEqual(result["band_count"], 1)
        self.assertEqual(
            result["aspect_convention"],
            "azimuth",
        )
        self.assertEqual(result["algorithm"], "Horn")
        self.assertFalse(result["zero_for_flat"])
        self.assertTrue(aspect_path.is_file())

        dataset = gdal.Open(
            str(aspect_path),
            gdal.GA_ReadOnly,
        )

        try:
            self.assertEqual(
                dataset.GetSpatialRef().GetAuthorityCode(None),
                "32651",
            )
            self.assertEqual(
                dataset.GetRasterBand(1).DataType,
                gdal.GDT_Float32,
            )
            values = dataset.ReadAsArray()
            nodata = dataset.GetRasterBand(1).GetNoDataValue()
            valid_values = values[values != nodata]
            self.assertGreater(valid_values.size, 0)
            self.assertGreaterEqual(valid_values.min(), 0.0)
            self.assertLessEqual(valid_values.max(), 360.0)
            self.assertGreater(np.ptp(valid_values), 0.0)
        finally:
            dataset = None

    def test_planar_dem_returns_west_facing_aspect(self):
        aspect_path = self._output_path("planar_aspect")

        generate_aspect(
            str(self.planar_path),
            str(aspect_path),
        )

        dataset = gdal.Open(
            str(aspect_path),
            gdal.GA_ReadOnly,
        )

        try:
            center_aspect = float(
                dataset.GetRasterBand(1)
                .ReadAsArray(2, 2, 1, 1)[0, 0]
            )
            self.assertAlmostEqual(
                center_aspect,
                270.0,
                places=5,
            )
        finally:
            dataset = None

    def test_flat_dem_aspect_is_nodata(self):
        aspect_path = self._output_path("flat_aspect")

        generate_aspect(
            str(self.flat_path),
            str(aspect_path),
        )

        dataset = gdal.Open(
            str(aspect_path),
            gdal.GA_ReadOnly,
        )

        try:
            band = dataset.GetRasterBand(1)
            nodata = band.GetNoDataValue()
            center_aspect = float(
                band.ReadAsArray(2, 2, 1, 1)[0, 0]
            )
            self.assertIsNotNone(nodata)
            self.assertEqual(center_aspect, nodata)
        finally:
            dataset = None

    def test_geographic_dem_cannot_generate_aspect(self):
        output_path = self._output_path(
            "invalid_geographic_aspect"
        )

        with self.assertRaisesRegex(
            ValueError,
            "水平单位为米",
        ):
            generate_aspect(
                str(self.geographic_path),
                str(output_path),
            )

        self.assertFalse(output_path.exists())

    def test_aspect_does_not_modify_source_dem(self):
        before_dataset = gdal.Open(
            str(self.planar_path),
            gdal.GA_ReadOnly,
        )
        before_values = before_dataset.ReadAsArray().copy()
        before_geotransform = before_dataset.GetGeoTransform()
        before_projection = before_dataset.GetProjection()
        before_dataset = None

        aspect_path = self._output_path(
            "source_unchanged_aspect"
        )

        generate_aspect(
            str(self.planar_path),
            str(aspect_path),
        )

        after_dataset = gdal.Open(
            str(self.planar_path),
            gdal.GA_ReadOnly,
        )
        after_values = after_dataset.ReadAsArray()
        after_geotransform = after_dataset.GetGeoTransform()
        after_projection = after_dataset.GetProjection()
        after_dataset = None

        np.testing.assert_array_equal(
            before_values,
            after_values,
        )
        self.assertEqual(
            before_geotransform,
            after_geotransform,
        )
        self.assertEqual(
            before_projection,
            after_projection,
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
