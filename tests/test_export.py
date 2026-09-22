"""F11 文件回读、数值口径、来源变化与事务失败验收。"""

import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from osgeo import gdal
from test_raster_statistics import create_dem
from etopo_analyzer.core.export_service import (export_package, file_signature, result_sources,
    result_metadata, validate_sources, ExportCancelled)
from etopo_analyzer.core.csv_export import export_csv
from etopo_analyzer.core.raster_export import export_raster, verify_raster
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics
from etopo_analyzer.core.region_comparison import compare_regions
from etopo_analyzer.core.profile_analysis import sample_elevation_profile


class TestExport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "中文源.tif"
        create_dem(self.source, [[-2, -1, 0, 1, 2, -9999]])
        self.signature = file_signature(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def rows(self, name, file):
        with (self.root / name / file).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_statistics_csv_and_manifest(self):
        result = calculate_raster_statistics(str(self.source), bin_count=2, thresholds=[0])
        with export_package(self.root, "中文统计", "csv", result_sources(result), result_metadata(result)) as folder:
            export_csv(folder, "statistics", result)
        data = self.rows("中文统计", "histogram.csv")
        self.assertEqual([int(row["像元数"]) for row in data], [2, 3])
        self.assertEqual([row["包含上界"] for row in data], ["False", "True"])
        classes = self.rows("中文统计", "classes.csv")
        self.assertEqual(classes[0]["下界(m)"], "-inf")
        self.assertEqual(classes[-1]["上界(m)"], "+inf")
        self.assertAlmostEqual(sum(float(row["面积占比(%)"]) for row in classes), 100)
        self.assertTrue((self.root / "中文统计/summary.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        record = json.loads((self.root / "中文统计/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(record["files"]), 3)
        self.assertEqual(record["metadata"]["parameters"]["std_ddof"], 0)

    def test_comparison_csv_direction_and_pp(self):
        other = self.root / "B.tif"
        create_dem(other, [[0, 1, 2, 3, 4, -9999]])
        result = compare_regions(str(self.source), str(other), bin_count=2, thresholds=[0])
        with export_package(self.root, "compare", "csv", result_sources(result), result_metadata(result)) as folder:
            export_csv(folder, "comparison", result)
        rows = {r["指标"]: r for r in self.rows("compare", "summary.csv")}
        self.assertEqual(float(rows["平均高程"]["B−A"]), 2)
        self.assertEqual(rows["负高程面积占比"]["差值单位"], "百分点")
        self.assertAlmostEqual(float(rows["负高程面积占比"]["B−A"]), -40)
        self.assertAlmostEqual(sum(float(row["A像元占比(%)"]) for row in self.rows("compare", "distribution.csv")), 100)

    def test_profile_missing_land_and_provenance(self):
        result = sample_elevation_profile(str(self.source), [(.5, 1.5), (5.5, 1.5)], 100000)
        self.assertIn("completed_at", result)
        with export_package(self.root, "profile", "csv", result_sources(result), result_metadata(result)) as folder:
            export_csv(folder, "profile", result)
        rows = self.rows("profile", "profile.csv")
        self.assertEqual(rows[-1]["是否无效"], "True")
        self.assertEqual(rows[-1]["高程(m)"], "")
        self.assertEqual(rows[0]["水深(m)"], "2.0")
        self.assertTrue(any(row["水深(m)"] == "" and row["是否无效"] == "False" for row in rows))

    def test_raster_roundtrip_scale_mask_and_compound_crs(self):
        create_dem(self.source, [[-9999, -2, 0, 2, np.nan]], scale=2, offset=1, mask=[[255, 255, 0, 255, 255]])
        before = self.source.read_bytes()
        with export_package(self.root, "raster", "raster", [file_signature(self.source)], {}) as folder:
            export_raster(folder, self.source)
        source = gdal.Open(str(self.source))
        output = gdal.Open(str(self.root / "raster/raster.tif"))
        verify_raster(source, output)
        self.assertEqual(output.GetRasterBand(1).GetScale(), 2)
        self.assertEqual(output.GetRasterBand(1).GetOffset(), 1)
        np.testing.assert_equal(output.GetRasterBand(1).ReadAsArray(), [[-9999, -2, 0, 2, np.nan]])
        source = output = None
        self.assertEqual(before, self.source.read_bytes())

    def test_reject_changed_source_before_and_after_write(self):
        os.utime(self.source, ns=(self.signature["mtime_ns"], self.signature["mtime_ns"] + 1000000))
        with self.assertRaises(ValueError):
            validate_sources([self.signature])
        signature = file_signature(self.source)
        with self.assertRaises(ValueError):
            with export_package(self.root, "bad", "csv", [signature], {}) as folder:
                (folder / "x.csv").write_text("x")
                os.utime(self.source, ns=(signature["mtime_ns"], signature["mtime_ns"] + 1000000))
        self.assertFalse((self.root / "bad").exists())
        self.assertFalse(list(self.root.glob(".etp-export-*")))

    def test_failure_cancel_and_existing_target_preserved(self):
        for failure in (OSError("disk full"), ExportCancelled("cancel")):
            with self.assertRaises(type(failure)):
                with export_package(self.root, "bad", "csv", [self.signature], {}) as folder:
                    (folder / "partial.csv").write_text("x")
                    raise failure
            self.assertFalse((self.root / "bad").exists())
            self.assertFalse(list(self.root.glob(".etp-export-*")))
        target = self.root / "existing"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        with self.assertRaises(FileExistsError):
            with export_package(self.root, "existing", "csv", [], {}):
                self.fail("must not overwrite")
        self.assertEqual((target / "keep.txt").read_text(), "keep")

    def test_cancel_raster_during_copy_leaves_no_package(self):
        cancelled = [False]
        with self.assertRaises(ExportCancelled):
            with export_package(self.root, "cancel", "raster", [self.signature], {}, lambda: cancelled[0]) as folder:
                export_raster(folder, self.source, lambda: cancelled[0], lambda progress: cancelled.__setitem__(0, True))
        self.assertFalse((self.root / "cancel").exists())
        self.assertFalse(list(self.root.glob(".etp-export-*")))

    def test_invalid_names(self):
        for name in ("../bad", "CON", "a/b", "a.", "", " x", "C:\\file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                with export_package(self.root, name, "csv", [], {}):
                    self.fail("invalid name")

    def test_unwritable_directory_does_not_publish(self):
        with patch("etopo_analyzer.core.export_service.tempfile.mkdtemp", side_effect=PermissionError("directory readonly")):
            with self.assertRaises(PermissionError):
                with export_package(self.root, "readonly", "csv", [], {}):
                    self.fail("cannot write")
        self.assertFalse((self.root / "readonly").exists())

    def test_validation_failure_cleans_up_and_closes_output(self):
        with patch("etopo_analyzer.core.raster_export.verify_raster", side_effect=ValueError("mismatch")):
            with self.assertRaises(ValueError):
                with export_package(self.root, "invalid", "raster", [self.signature], {}) as folder:
                    export_raster(folder, self.source)
        self.assertFalse((self.root / "invalid").exists())
        self.assertFalse(list(self.root.glob(".etp-export-*")))

    def test_verifier_rejects_value_and_mask_changes(self):
        other = self.root / "other.tif"
        create_dem(other, [[-2, -1, 0, 1, 3, -9999]])
        source, output = gdal.Open(str(self.source)), gdal.Open(str(other))
        try:
            with self.assertRaisesRegex(ValueError, "像元"):
                verify_raster(source, output)
        finally:
            source = output = None
        create_dem(other, [[-2, -1, 0, 1, 2, -9999]], mask=[[255, 255, 0, 255, 255, 0]])
        source, output = gdal.Open(str(self.source)), gdal.Open(str(other))
        try:
            with self.assertRaisesRegex(ValueError, "掩膜"):
                verify_raster(source, output)
        finally:
            source = output = None

    def test_nan_nodata_and_geotiff_metadata(self):
        create_dem(self.source, [[np.nan, -2, 3]], nodata=np.nan)
        with export_package(self.root, "nan", "raster", [file_signature(self.source)], {}) as folder:
            metadata = export_raster(folder, self.source)
            json.dumps(metadata, allow_nan=False)
        self.assertEqual(metadata["band_metadata"][0]["nodata"], "nan")

    def test_thread_local_configuration_restored(self):
        keys = ("GDAL_SWATH_SIZE", "GDAL_TIFF_INTERNAL_MASK")
        previous = {key: gdal.GetThreadLocalConfigOption(key) for key in keys}
        export_raster(self.root, self.source)
        self.assertEqual(previous, {key: gdal.GetThreadLocalConfigOption(key) for key in keys})

    def test_chart_all_types_independent_png_and_dpi(self):
        from PIL import Image
        from etopo_analyzer.visualization.chart_export import export_chart
        stats = calculate_raster_statistics(str(self.source), thresholds=[0])
        comparison = compare_regions(str(self.source), str(self.source), thresholds=[0])
        profile = sample_elevation_profile(str(self.source), [(.5, 1.5), (4.5, 1.5)], 100000)
        for kind, result in (("profile", profile), ("statistics", stats), ("distribution", comparison), ("area", comparison)):
            with self.subTest(kind=kind):
                export_chart(self.root, kind, result, 1800, 300)
                with Image.open(self.root / "chart.png") as image:
                    self.assertEqual(image.width, 1800)
                    self.assertAlmostEqual(image.info["dpi"][0], 300, delta=.02)
                    self.assertGreater(len(image.getcolors(image.width * image.height)), 20)
