"""F10 手算、统一箱界、兼容性和两遍扫描验收。"""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.core.region_comparison import compare_regions
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics, StatisticsCancelled
from test_raster_statistics import create_dem


class TestRegionComparison(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.a = Path(self.temp.name) / "a.tif"
        self.b = Path(self.temp.name) / "b.tif"
        create_dem(self.a, [[-2, 0, 2]])
        create_dem(self.b, [[0, 2, 4]])

    def tearDown(self):
        self.temp.cleanup()

    def compare(self, **kwargs):
        return compare_regions(str(self.a), str(self.b), **kwargs)

    def test_hand_values_common_bins_and_f09_compatibility(self):
        result = self.compare(bin_count=3, thresholds=[0, 2], block_size=2)
        self.assertEqual(result["parameters"]["bin_edges_m"], [-2, 0, 2, 4])
        self.assertEqual(result["regions"]["a"]["histogram"]["counts"], [1, 1, 1])
        self.assertEqual(result["regions"]["b"]["histogram"]["counts"], [0, 1, 2])
        self.assertEqual(result["differences"]["mean_m"], 2)
        self.assertAlmostEqual(result["differences"]["std_m"], 0)
        self.assertAlmostEqual(result["differences"]["negative_pp"], -100 / 3)
        single = calculate_raster_statistics(str(self.a), bin_count=3, thresholds=[0, 2], block_size=2)
        self.assertEqual(result["regions"]["a"]["statistics"], single["statistics"])
        self.assertEqual(result["regions"]["a"]["classes"], single["classes"])
        json.dumps(result, allow_nan=False)

    def test_self_comparison_zero_and_swap_sign(self):
        same = compare_regions(str(self.a), str(self.a))
        self.assertTrue(all(v == 0 for v in same["differences"].values()))
        self.assertTrue(all(c["area_difference_pp"] == 0 for c in same["classes"]))
        forward = self.compare()
        reverse = compare_regions(str(self.b), str(self.a))
        self.assertEqual(forward["parameters"]["bin_edges_m"], reverse["parameters"]["bin_edges_m"])
        for key, value in forward["differences"].items():
            self.assertEqual(value, -reverse["differences"][key])

    def test_different_sizes_same_distribution(self):
        create_dem(self.b, [[-2, 0, 2] * 2])
        result = self.compare()
        self.assertEqual(result["regions"]["a"]["histogram"]["frequencies"], result["regions"]["b"]["histogram"]["frequencies"])
        self.assertEqual(result["differences"]["valid_count"], 3)

    def test_constant_union_and_constant_single(self):
        create_dem(self.a, [[0, 0]])
        create_dem(self.b, [[0]])
        result = self.compare()
        self.assertEqual(result["parameters"]["bin_edges_m"], [-.5, .5])
        self.assertEqual(result["regions"]["a"]["histogram"]["frequencies"], [1])
        create_dem(self.b, [[2]])
        result = self.compare(bin_count=2)
        self.assertEqual(result["parameters"]["bin_edges_m"], [0, 1, 2])
        self.assertEqual(result["regions"]["b"]["histogram"]["counts"], [0, 1])

    def test_nodata_mask_and_scale_offset(self):
        create_dem(self.a, [[-9999, -1, 0, 1]], scale=-2, offset=2, mask=[[255, 255, 0, 255]])
        create_dem(self.b, [[4, 0]])
        result = self.compare(thresholds=[0, 4])
        self.assertEqual(result["regions"]["a"]["statistics"]["valid_count"], 2)
        self.assertEqual(result["regions"]["a"]["histogram"]["frequencies"], result["regions"]["b"]["histogram"]["frequencies"])
        self.assertEqual(result["differences"]["mean_m"], 0)
        self.assertAlmostEqual(result["regions"]["a"]["area"]["valid_coverage_fraction"], .5)

    def test_latitudes_area_not_pixel_ratio(self):
        create_dem(self.a, [[-1], [1]], transform=(0, 1, 0, 60, 0, -30))
        create_dem(self.b, [[-1], [1]], transform=(10, 1, 0, 30, 0, -30))
        result = self.compare(thresholds=[0])
        a, b = result["regions"]["a"], result["regions"]["b"]
        self.assertEqual(a["histogram"]["frequencies"], b["histogram"]["frequencies"])
        self.assertLess(a["classes"][0]["area_fraction"], b["classes"][0]["area_fraction"])

    def test_block_sizes_and_closure(self):
        create_dem(self.a, np.arange(35).reshape(5, 7) - 20)
        create_dem(self.b, np.arange(24).reshape(4, 6) - 5)
        reference = self.compare(block_size=512)
        for size in (1, 2, 3):
            result = self.compare(block_size=size)
            for key in ("a", "b"):
                region = result["regions"][key]
                self.assertEqual(region["histogram"], reference["regions"][key]["histogram"])
                self.assertAlmostEqual(sum(region["histogram"]["frequencies"]), 1)
                self.assertAlmostEqual(sum(c["area_fraction"] for c in region["classes"]), 1)
                self.assertEqual(sum(c["count"] for c in region["classes"]), region["statistics"]["valid_count"])
                self.assertTrue(math.isclose(sum(c["area_m2"] for c in region["classes"]), region["area"]["valid_m2"], rel_tol=1e-10))

    def test_reject_incompatible_sources(self):
        for kwargs, message in ((dict(epsg=4326), "垂直基准"), (dict(epsg=9707), "垂直基准"),
                                (dict(unit="feet"), "米制"), (dict(transform=(0, .5, 0, 2, 0, -1)), "分辨率"),
                                (dict(transform=(.2, 1, 0, 2, 0, -1)), "格网"), (dict(epsg=3857), "WGS84")):
            with self.subTest(kwargs=kwargs):
                create_dem(self.b, [[0, 1]], **kwargs)
                with self.assertRaisesRegex(ValueError, message):
                    self.compare()

    def test_grid_roundoff_is_allowed(self):
        create_dem(self.b, [[0, 1]], transform=(10 + 1e-8, 1, 0, 2, 0, -1))
        self.assertTrue(self.compare()["compatibility"]["aligned_grid"])

    def test_all_nodata_and_bad_parameters(self):
        create_dem(self.b, [[-9999]])
        with self.assertRaisesRegex(ValueError, "全部"):
            self.compare()
        for kwargs in (dict(bin_count=0), dict(thresholds=[0, 0]), dict(block_size=0)):
            with self.assertRaises(ValueError):
                self.compare(**kwargs)

    def test_exactly_two_bounded_reads_per_pixel(self):
        create_dem(self.a, [[-2, 0, 2]], nodata=None)
        create_dem(self.b, [[0, 2, 4]], nodata=None)
        calls = []
        original = gdal.Band.ReadAsArray
        def read(band, x, y, width, height, *args, **kwargs):
            calls.append((width, height))
            return original(band, x, y, width, height, *args, **kwargs)
        with patch.object(gdal.Band, "ReadAsArray", new=read):
            self.compare(block_size=2)
        self.assertEqual(len(calls), 8)
        self.assertTrue(all(w <= 2 and h <= 2 for w, h in calls))

    def test_cancel_and_progress(self):
        values = []
        with self.assertRaises(StatisticsCancelled):
            self.compare(block_size=1, progress=lambda p, s: values.append(p), cancelled=lambda: bool(values))
        self.assertEqual(values, [8])
        values.clear()
        self.compare(block_size=1, progress=lambda p, s: values.append(p))
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 100)
        # 取消后已关闭数据集，Windows 上也能重命名。
        self.a.rename(self.a.with_suffix(".renamed"))

    def test_source_mutation_and_readonly(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in self.a.parent.iterdir()}
        self.compare()
        after = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in self.a.parent.iterdir()}
        self.assertEqual(before, after)
        def mutate(percent, phase):
            if percent == 100:
                stat = self.a.stat()
                os.utime(self.a, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
        with self.assertRaisesRegex(RuntimeError, "变化"):
            self.compare(progress=mutate)


if __name__ == "__main__":
    unittest.main()
