"""F08 理论 DEM 与采样语义测试。"""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from osgeo import gdal
from pyproj import CRS, Geod

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.core.profile_analysis import sample_elevation_profile, profile_path
from etopo_analyzer.core.point_query import query_point_elevation
from etopo_analyzer.core.raster_sampling import RasterSampler


class TestProfileAnalysis(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "dem.tif"
        self.create_dem()
        self.vertices = [(0.5, 0), (3.5, 0)]
        self.degree = Geod(ellps="WGS84").inv(0, 0, 1, 0)[2]

    def tearDown(self):
        self.temp.cleanup()

    def create_dem(self, values=None, epsg=9518, transform=(0, 1, 0, 1.5, 0, -1),
                   scale=None, offset=None):
        if values is None:
            values = [[100, 0, -100, -200]] * 3
        data = np.array(values, dtype=np.float32)
        ds = gdal.GetDriverByName("GTiff").Create(str(self.path), data.shape[1], data.shape[0], 1, gdal.GDT_Float32)
        ds.SetProjection(CRS.from_epsg(epsg).to_wkt())
        ds.SetGeoTransform(transform)
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-9999)
        if scale is not None:
            band.SetScale(scale)
        if offset is not None:
            band.SetOffset(offset)
        band.WriteArray(data)
        band = None
        ds = None

    def sample(self, vertices=None, interval=None):
        return sample_elevation_profile(str(self.path), vertices or self.vertices,
                                        self.degree if interval is None else interval)

    def test_theoretical_values_and_depth(self):
        result = self.sample()
        self.assertEqual(result["elevation_m"], [100, 0, -100, -200])
        self.assertEqual(result["depth_m"], [None, None, 100, 200])
        self.assertEqual(result["sample_count"], 4)
        self.assertEqual(result["distance_m"][0], 0)
        self.assertAlmostEqual(result["total_distance_m"], self.degree * 3)
        self.assertEqual(result["longitude"][-1], 3.5)

    def test_short_final_interval_and_large_interval(self):
        result = self.sample(interval=self.degree * 2)
        self.assertEqual(result["sample_count"], 3)
        self.assertEqual(result["distance_m"][-1], result["total_distance_m"])
        self.assertEqual(self.sample(interval=1e7)["sample_count"], 2)

    def test_polyline_uses_global_distance(self):
        vertices = [(0.5, 0), (1.2, 0), (1.2, 1)]
        result = self.sample(vertices, self.degree * 0.5)
        distances = result["distance_m"]
        self.assertTrue(all(b > a for a, b in zip(distances, distances[1:])))
        self.assertAlmostEqual(distances[2], self.degree)
        self.assertAlmostEqual(result["longitude"][2], 1.2)
        self.assertGreater(result["latitude"][2], 0)
        self.assertEqual(result["latitude"][-1], 1)

    def test_nodata_and_outside_are_gaps(self):
        self.create_dem([[100, -9999, float("nan"), -200]] * 3)
        result = self.sample([(-0.5, 0), (3.5, 0)])
        self.assertEqual(result["is_nodata"], [True, False, True, True, False])
        self.assertEqual(result["valid_sample_count"], 2)
        with self.assertRaises(ValueError):
            self.sample([(20, 0), (21, 0)])

    def test_scale_offset_and_point_query_match(self):
        self.create_dem(scale=2, offset=10)
        result = self.sample()
        self.assertEqual(result["elevation_m"], [210, 10, -190, -390])
        for lon, lat, value in zip(result["longitude"], result["latitude"], result["elevation_m"]):
            self.assertEqual(query_point_elevation(str(self.path), lon, lat)["elevation"], value)

    def test_projected_dem(self):
        self.create_dem(epsg=3857, transform=(0, 111319.49079327357, 0, 150000, 0, -100000))
        self.assertEqual(self.sample()["elevation_m"], [100, 0, -100, -200])

    def test_source_unchanged_and_opened_once(self):
        before = hashlib.sha256(self.path.read_bytes()).digest()
        with patch("etopo_analyzer.core.raster_sampling.gdal.Open", wraps=gdal.Open) as opened:
            self.sample()
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).digest())

    def test_invalid_parameters(self):
        for interval in (0, -1, float("nan"), float("inf"), 1e-20):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.sample(interval=interval)
        for vertices in ([(0, 0)], [(0, 0), (0, 0)], [(181, 0), (0, 0)],
                         [(0, 91), (0, 0)], [(float("nan"), 0), (1, 0)],
                         [(179, 0), (-179, 0)]):
            with self.subTest(vertices=vertices), self.assertRaises(ValueError):
                self.sample(vertices)

    def test_duplicates_and_sample_limit(self):
        self.assertEqual(len(profile_path([(0, 0), (0, 0), (1, 0)])[0]), 2)
        with patch("etopo_analyzer.core.profile_analysis.MAX_PROFILE_SAMPLES", 4):
            self.assertEqual(self.sample()["sample_count"], 4)
            with self.assertRaises(ValueError):
                self.sample(interval=self.degree * 0.9)

    def test_missing_file_and_invalid_metadata(self):
        with self.assertRaises(FileNotFoundError):
            sample_elevation_profile(str(self.path) + "missing", self.vertices)
        ds = gdal.GetDriverByName("GTiff").Create(str(self.path), 2, 2, 1)
        ds = None
        with self.assertRaises(RuntimeError):
            self.sample()

    def test_sampler_closes_dataset_and_preserves_f03_outside_error(self):
        with RasterSampler(str(self.path)) as sampler:
            with self.assertRaises(ValueError):
                sampler.sample(50, 0)
        self.assertIsNone(sampler.dataset)
        self.assertIsNone(sampler.band)


if __name__ == "__main__":
    unittest.main()
