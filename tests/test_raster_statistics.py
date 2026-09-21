"""F09 手算数据、分块、面积和只读性验收。"""

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from osgeo import gdal
from pyproj import CRS, Transformer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.core.pixel_area import pixel_row_areas
from etopo_analyzer.core.raster_statistics import (
    calculate_raster_statistics, StatisticsCancelled,
)


def create_dem(path, values, *, epsg=9518, transform=(0, 1, 0, 2, 0, -1),
               nodata=-9999, scale=None, offset=None, unit="metre", mask=None):
    values = np.asarray(values, dtype=np.float64)
    ds = gdal.GetDriverByName("GTiff").Create(str(path), values.shape[1], values.shape[0], 1, gdal.GDT_Float64)
    ds.SetProjection(CRS.from_epsg(epsg).to_wkt())
    ds.SetGeoTransform(transform)
    band = ds.GetRasterBand(1)
    if nodata is not None:
        band.SetNoDataValue(nodata)
    if scale is not None:
        band.SetScale(scale)
    if offset is not None:
        band.SetOffset(offset)
    band.SetUnitType(unit)
    band.WriteArray(values)
    if mask is not None:
        band.CreateMaskBand(gdal.GMF_PER_DATASET)
        band.GetMaskBand().WriteArray(np.asarray(mask, dtype=np.uint8))
    band = None
    ds = None


class TestRasterStatistics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "dem.tif"

    def tearDown(self):
        self.temp.cleanup()

    def calculate(self, **kwargs):
        return calculate_raster_statistics(str(self.path), **kwargs)

    def test_hand_calculation_boundary_and_serialization(self):
        create_dem(self.path, [[-2, -1, 0, 1, 2]])
        result = self.calculate(bin_count=2, thresholds=[0], block_size=2)
        s = result["statistics"]
        self.assertEqual((s["valid_count"], s["invalid_count"]), (5, 0))
        self.assertEqual((s["min_m"], s["max_m"], s["mean_m"]), (-2, 2, 0))
        self.assertAlmostEqual(s["std_m"], math.sqrt(2))
        self.assertEqual(result["histogram"]["counts"], [2, 3])
        self.assertEqual(result["histogram"]["bin_edges_m"], [-2, 0, 2])
        self.assertEqual([c["count"] for c in result["classes"]], [2, 3])
        self.assertEqual([c["count"] for c in result["sign_summary"]], [2, 3])
        json.dumps(result, allow_nan=False)

    def test_invalid_values_scale_and_explicit_mask(self):
        create_dem(self.path, [[-9999, np.nan, np.inf, -np.inf, -2, 0, 2, 4]],
                   scale=-2, offset=1, mask=[[255, 255, 255, 255, 255, 255, 255, 0]])
        result = self.calculate(thresholds=[0])
        s = result["statistics"]
        self.assertEqual(s["valid_count"], 3)
        self.assertEqual(s["invalid_count"], 5)
        self.assertEqual(s["invalid_reasons"], dict(raw_nodata_or_nonfinite=4, mask_only=1, transformed_nonfinite=0))
        self.assertEqual((s["min_m"], s["max_m"], s["mean_m"]), (-3, 5, 1))
        self.assertEqual([c["count"] for c in result["classes"]], [1, 2])

    def test_overflow_after_scale_is_invalid(self):
        create_dem(self.path, [[1e308, 1]], scale=2)
        result = self.calculate()
        self.assertEqual(result["statistics"]["invalid_reasons"]["transformed_nonfinite"], 1)
        self.assertEqual(result["statistics"]["mean_m"], 2)

    def test_all_nodata_and_nan_nodata(self):
        for values, nodata in (([[-9999, -9999]], -9999), ([[np.nan, np.inf]], np.nan)):
            with self.subTest(nodata=nodata):
                create_dem(self.path, values, nodata=nodata)
                with self.assertRaisesRegex(ValueError, "全部"):
                    self.calculate()

    def test_single_and_constant(self):
        for values in ([[0]], [[-3] * 5] * 3):
            create_dem(self.path, values)
            result = self.calculate()
            value = values[0][0]
            self.assertEqual(result["histogram"]["bin_edges_m"], [value - .5, value + .5])
            self.assertEqual(result["histogram"]["counts"], [np.size(values)])
            self.assertEqual(result["statistics"]["std_m"], 0)

    def test_invalid_parameters(self):
        create_dem(self.path, [[0, 1]])
        for kwargs in (dict(bin_count=0), dict(bin_count=201), dict(bin_count=1.5),
                       dict(thresholds=[]), dict(thresholds=[0, 0]), dict(thresholds=[1, 0]),
                       dict(thresholds=[float("nan")]), dict(thresholds=[float("inf")]),
                       dict(thresholds=list(range(51))), dict(block_size=513)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.calculate(**kwargs)

    def test_threshold_extremes_and_empty_classes(self):
        create_dem(self.path, [[-20000, -1, 0, 1, 20000]])
        result = self.calculate(thresholds=[-1, 0, 1, 2, 3])
        self.assertEqual([c["count"] for c in result["classes"]], [1, 1, 1, 1, 0, 1])
        self.assertIsNone(result["classes"][0]["lower_m"])
        self.assertIsNone(result["classes"][-1]["upper_m"])

    def test_chunk_sizes_and_direct_numpy_agree(self):
        values = np.arange(77, dtype=float).reshape(7, 11) - 40
        values[2, 5] = -9999
        create_dem(self.path, values)
        direct = values[values != -9999]
        reference = self.calculate(bin_count=13, block_size=512)
        for size in (1, 2, 3, 5):
            result = self.calculate(bin_count=13, block_size=size)
            for key, expected in (("mean_m", direct.mean()), ("std_m", direct.std()),
                                  ("min_m", direct.min()), ("max_m", direct.max())):
                self.assertAlmostEqual(result["statistics"][key], expected, places=10)
            self.assertEqual(result["histogram"], reference["histogram"])
            for actual, expected in zip(result["classes"], reference["classes"]):
                self.assertEqual(actual["count"], expected["count"])
                self.assertTrue(math.isclose(actual["area_m2"], expected["area_m2"], rel_tol=1e-10, abs_tol=1e-3))

    def test_latitude_area_and_independent_cea_reference(self):
        create_dem(self.path, [[1], [2]], transform=(10, 1, 0, 60, 0, -30))
        result = self.calculate(thresholds=[2])
        self.assertLess(result["classes"][0]["area_m2"], result["classes"][1]["area_m2"])
        self.assertEqual(result["classes"][0]["pixel_fraction"], .5)
        self.assertLess(result["classes"][0]["area_fraction"], .5)
        transformer = Transformer.from_crs(4326, "+proj=cea +lat_ts=0 +ellps=WGS84 +units=m", always_xy=True)
        for index, (south, north) in enumerate(((30, 60), (0, 30))):
            x0, y0 = transformer.transform(10, south)
            x1, y1 = transformer.transform(11, north)
            expected = abs((x1 - x0) * (y1 - y0))
            self.assertTrue(math.isclose(result["classes"][index]["area_m2"], expected, rel_tol=1e-8))

    def test_global_poles_and_symmetry(self):
        create_dem(self.path, np.ones((180, 360)), transform=(-180, 1, 0, 90, 0, -1))
        result = self.calculate()
        a, b = 6378137., 6356752.314245179
        e = math.sqrt(1 - b * b / (a * a))
        expected = 2 * math.pi * a * a * (1 + (1 - e * e) * math.atanh(e) / e)
        self.assertTrue(math.isclose(result["area"]["valid_m2"], expected, rel_tol=1e-10))
        ds = gdal.Open(str(self.path))
        areas = pixel_row_areas(ds)
        ds = None
        np.testing.assert_allclose(areas, areas[::-1], rtol=1e-10)
        self.assertTrue(np.all(areas > 0))

    def test_rejected_crs_grid_units_and_scale(self):
        for kwargs in (dict(epsg=3857), dict(transform=(0, 1, .1, 2, 0, -1)),
                       dict(transform=(0, 1, 0, 91, 0, -1)), dict(unit="feet"),
                       dict(epsg=4326, unit=""), dict(scale=float("inf"))):
            with self.subTest(kwargs=kwargs):
                create_dem(self.path, [[0, 1]], **kwargs)
                with self.assertRaises(ValueError):
                    self.calculate()

    def test_vertical_crs_supplies_metres(self):
        create_dem(self.path, [[0, 1]], unit="")
        self.assertEqual(self.calculate()["source"]["unit"], "m")

    def test_cancel_progress_and_source_change(self):
        create_dem(self.path, [[0, 1, 2, 3]])
        progress = []
        with self.assertRaises(StatisticsCancelled):
            self.calculate(block_size=1, progress=lambda p, s: progress.append(p), cancelled=lambda: bool(progress))
        self.assertEqual(progress, [12])
        def change_source(percent, phase):
            if percent == 100:
                stat = self.path.stat()
                os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
        with self.assertRaisesRegex(RuntimeError, "发生变化"):
            self.calculate(progress=change_source)

    def test_source_and_sidecars_unchanged_and_open_once(self):
        create_dem(self.path, [[0, 1, 2]])
        before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in self.path.parent.iterdir()}
        with patch("etopo_analyzer.core.raster_statistics.gdal.Open", wraps=gdal.Open) as opened:
            self.calculate()
            self.assertEqual(opened.call_count, 1)
        after = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in self.path.parent.iterdir()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
