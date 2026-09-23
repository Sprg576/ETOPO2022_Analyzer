"""多边形掩膜的独立手算、分块、边界和对比验收。"""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from osgeo import gdal
from test_raster_statistics import create_dem
from etopo_analyzer.core.polygon_roi import normalize_polygon
from etopo_analyzer.core.pixel_area import pixel_row_areas
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics, StatisticsCancelled
from etopo_analyzer.core.region_comparison import compare_regions
from etopo_analyzer.core.csv_export import export_csv


def polygon(points, *holes):
    return normalize_polygon(dict(type="Polygon", coordinates=[points, *holes]))


class TestPolygonStatistics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "dem.tif"
        self.values = np.arange(16, dtype=float).reshape(4, 4)
        create_dem(self.path, self.values, transform=(0, 1, 0, 4, 0, -1))
        self.triangle = polygon([[0, 0], [3.9, 0], [0, 3.9]])

    def tearDown(self):
        self.temp.cleanup()

    def calculate(self, **kwargs):
        return calculate_raster_statistics(self.path, thresholds=[10], roi=self.triangle, **kwargs)

    def test_triangle_excludes_bounding_box_and_preserves_source(self):
        signature = hashlib.sha256(self.path.read_bytes()).digest()
        result = self.calculate()
        expected = np.array([4, 8, 9, 12, 13, 14])
        self.assertEqual(result["statistics"]["total_count"], 6)
        self.assertEqual(result["statistics"]["invalid_count"], 0)
        self.assertAlmostEqual(result["statistics"]["mean_m"], expected.mean())
        self.assertAlmostEqual(result["statistics"]["std_m"], expected.std())
        self.assertEqual([c["count"] for c in result["classes"]], [3, 3])
        ds = gdal.Open(str(self.path))
        areas = pixel_row_areas(ds)
        ds = None
        self.assertAlmostEqual(result["area"]["valid_m2"], areas[1] + 2 * areas[2] + 3 * areas[3], places=3)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), signature)
        self.assertEqual(result["parameters"]["roi"], self.triangle)
        json.dumps(result, allow_nan=False)

    def test_block_size_independent_and_progress_finishes(self):
        results = []
        for size in (1, 2, 3, 512):
            progress = []
            result = self.calculate(block_size=size, progress=lambda n, s: progress.append(n))
            self.assertEqual(progress[-1], 100)
            self.assertEqual(progress, sorted(progress))
            results.append(result)
        for result in results[1:]:
            self.assertEqual(result["histogram"], results[0]["histogram"])
            self.assertEqual(result["statistics"], results[0]["statistics"])
            self.assertAlmostEqual(result["area"]["valid_m2"], results[0]["area"]["valid_m2"], places=3)

    def test_nodata_mask_and_scale_only_inside_roi(self):
        self.values[0, 0] = self.values[2, 0] = -9999
        mask = np.ones((4, 4), dtype=np.uint8) * 255
        mask[0, 1] = mask[2, 1] = 0
        create_dem(self.path, self.values, transform=(0, 1, 0, 4, 0, -1), mask=mask, scale=2, offset=-1)
        result = self.calculate()
        self.assertEqual(result["statistics"]["valid_count"], 4)
        self.assertEqual(result["statistics"]["invalid_count"], 2)
        self.assertEqual(result["statistics"]["invalid_reasons"],
                         dict(raw_nodata_or_nonfinite=1, mask_only=1, transformed_nonfinite=0))
        self.assertAlmostEqual(result["statistics"]["mean_m"], np.array([4, 12, 13, 14]).mean() * 2 - 1)
        self.assertAlmostEqual(sum(c["area_m2"] for c in result["classes"]), result["area"]["valid_m2"], places=3)

    def test_hole_and_partial_overlap(self):
        roi = polygon([[-1, -1], [5, -1], [5, 5], [-1, 5]], [[1, 1], [1, 3], [3, 3], [3, 1]])
        result = calculate_raster_statistics(self.path, roi=roi, block_size=1)
        self.assertEqual(result["statistics"]["total_count"], 12)
        self.assertAlmostEqual(result["statistics"]["mean_m"], 7.5)

    def test_empty_outside_and_subpixel_regions(self):
        for points in ([[5, 5], [6, 5], [5, 6]], [[0, 0], [.1, 0], [0, .1]]):
            with self.assertRaises(ValueError):
                calculate_raster_statistics(self.path, roi=polygon(points))
        create_dem(self.path, [[-9999] * 4] * 4, transform=(0, 1, 0, 4, 0, -1))
        with self.assertRaisesRegex(ValueError, "没有有效"):
            self.calculate()

    def test_invalid_geometry(self):
        for points in ([[0, 0], [1, 1]], [[0, 0], [1, 1], [2, 2]],
                       [[0, 0], [2, 2], [0, 2], [2, 0]], [[179, 1], [-179, 1], [179, 2]],
                       [[0, 0], [1, 1], [float("nan"), 0]]):
            with self.assertRaises(ValueError):
                polygon(points)

    def test_cancel_during_masked_scan(self):
        progress = []
        with self.assertRaises(StatisticsCancelled):
            self.calculate(block_size=1, progress=lambda n, s: progress.append(n), cancelled=lambda: bool(progress))

    def test_same_dem_two_polygons_common_bins_and_difference(self):
        right = polygon([[2, 0], [4, 0], [4, 4], [2, 4]])
        progress = []
        result = compare_regions(self.path, self.path, thresholds=[10], roi_a=self.triangle, roi_b=right,
                                 block_size=2, progress=lambda p, s: progress.append(p))
        a, b = result["regions"]["a"], result["regions"]["b"]
        self.assertEqual(a["histogram"]["bin_edges_m"], b["histogram"]["bin_edges_m"])
        self.assertEqual(a["statistics"]["valid_count"], 6)
        self.assertEqual(b["statistics"]["valid_count"], 8)
        self.assertAlmostEqual(result["differences"]["mean_m"], self.values[:, 2:].mean() - 10)
        self.assertAlmostEqual(sum(b["histogram"]["frequencies"]), 1)
        self.assertEqual(progress[-1], 100)
        self.assertEqual(progress, sorted(progress))
        export_csv(self.root, "comparison", result)
        features = json.loads((self.root / "regions.geojson").read_text(encoding="utf-8"))["features"]
        self.assertEqual([f["properties"]["region"] for f in features], ["a", "b"])
        self.assertEqual(features[0]["geometry"], self.triangle)

    def test_statistics_export_preserves_polygon(self):
        export_csv(self.root, "statistics", self.calculate())
        self.assertIn("多边形入选格网面积", (self.root / "summary.csv").read_text(encoding="utf-8-sig"))
        data = json.loads((self.root / "regions.geojson").read_text(encoding="utf-8"))
        self.assertEqual(data["features"][0]["geometry"], self.triangle)
