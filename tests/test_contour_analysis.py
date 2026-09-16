"""F07-1 等值线生成与 F07-2 高程语义分类测试。"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr


gdal.UseExceptions()
ogr.UseExceptions()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from etopo_analyzer.core.contour_analysis import (
    CONTOUR_LAYER_NAME,
    CONTOUR_TYPE_DEPTH,
    CONTOUR_TYPE_ELEVATION,
    CONTOUR_TYPE_ZERO,
    classify_contour_elevation,
    generate_contours,
)


class TestContourAnalysis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)
        cls.gradient_path = cls.temp_path / "gradient_dem.tif"
        cls.nodata_path = cls.temp_path / "nodata_dem.tif"
        cls.semantic_path = cls.temp_path / "semantic_dem.tif"
        cls._create_gradient_dem()
        cls._create_nodata_dem()
        cls._create_semantic_dem()

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    @classmethod
    def _create_raster(
        cls,
        path: Path,
        values: np.ndarray,
        nodata: float | None = None,
    ) -> None:
        height, width = values.shape
        dataset = gdal.GetDriverByName("GTiff").Create(
            str(path),
            width,
            height,
            1,
            gdal.GDT_Float32,
        )
        dataset.SetGeoTransform(
            (100.0, 1.0, 0.0, 50.0, 0.0, -1.0)
        )

        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(9518)
        dataset.SetSpatialRef(spatial_reference)

        band = dataset.GetRasterBand(1)
        band.WriteArray(values.astype(np.float32))

        if nodata is not None:
            band.SetNoDataValue(nodata)

        dataset = None

    @classmethod
    def _create_gradient_dem(cls) -> None:
        cls._create_raster(
            cls.gradient_path,
            np.array(
                [
                    [0.0, 10.0, 20.0],
                    [0.0, 10.0, 20.0],
                    [0.0, 10.0, 20.0],
                ]
            ),
        )

    @classmethod
    def _create_nodata_dem(cls) -> None:
        values = np.full((5, 5), 100.0)
        values[2, 2] = -9999.0
        cls._create_raster(
            cls.nodata_path,
            values,
            nodata=-9999.0,
        )

    @classmethod
    def _create_semantic_dem(cls) -> None:
        cls._create_raster(
            cls.semantic_path,
            np.array(
                [
                    [-20.0, -10.0, 0.0, 10.0, 20.0],
                    [-20.0, -10.0, 0.0, 10.0, 20.0],
                    [-20.0, -10.0, 0.0, 10.0, 20.0],
                ]
            ),
        )

    def _output_path(self, name: str) -> Path:
        return self.temp_path / f"{name}.gpkg"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as source_file:
            for chunk in iter(
                lambda: source_file.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    def test_generates_expected_geopackage_schema(self):
        output_path = self._output_path("schema")
        result = generate_contours(
            str(self.gradient_path),
            str(output_path),
            interval=10.0,
            base=0.0,
        )

        self.assertTrue(output_path.is_file())
        self.assertEqual(result["output_path"], str(output_path))
        self.assertEqual(result["layer_name"], CONTOUR_LAYER_NAME)
        self.assertEqual(result["geometry_type"], "LineString")

        dataset = ogr.Open(str(output_path), 0)

        try:
            self.assertIsNotNone(dataset)
            self.assertEqual(dataset.GetLayerCount(), 1)
            layer = dataset.GetLayerByName(CONTOUR_LAYER_NAME)
            self.assertIsNotNone(layer)
            self.assertEqual(
                ogr.GT_Flatten(layer.GetGeomType()),
                ogr.wkbLineString,
            )
            definition = layer.GetLayerDefn()
            id_field = definition.GetFieldDefn(0)
            elev_field = definition.GetFieldDefn(1)
            type_field = definition.GetFieldDefn(2)
            self.assertEqual(
                [
                    definition.GetFieldDefn(index).GetName()
                    for index in range(
                        definition.GetFieldCount()
                    )
                ],
                ["ID", "ELEV", "TYPE"],
            )
            self.assertEqual(
                id_field.GetType(),
                ogr.OFTInteger64,
            )
            self.assertEqual(
                elev_field.GetType(),
                ogr.OFTReal,
            )
            self.assertEqual(
                type_field.GetType(),
                ogr.OFTString,
            )
        finally:
            dataset = None

    def test_interval_generates_theoretical_vertical_contour(self):
        output_path = self._output_path("theoretical")
        result = generate_contours(
            str(self.gradient_path),
            str(output_path),
            interval=10.0,
            base=0.0,
        )
        dataset = ogr.Open(str(output_path), 0)

        try:
            layer = dataset.GetLayerByName(CONTOUR_LAYER_NAME)
            features = list(layer)
            elevations = {
                feature.GetFieldAsDouble("ELEV")
                for feature in features
            }

            self.assertIn(10.0, elevations)
            self.assertTrue(
                all(elevation % 10.0 == 0.0 for elevation in elevations)
            )
            self.assertEqual(
                result["feature_count"],
                len(features),
            )
            ten_meter_feature = next(
                feature
                for feature in features
                if feature.GetFieldAsDouble("ELEV") == 10.0
            )
            envelope = (
                ten_meter_feature.GetGeometryRef().GetEnvelope()
            )
            self.assertAlmostEqual(envelope[0], 101.5, places=6)
            self.assertAlmostEqual(envelope[1], 101.5, places=6)
            self.assertGreater(envelope[3], envelope[2])
        finally:
            dataset = None

    def test_output_uses_horizontal_part_of_compound_crs(self):
        output_path = self._output_path("horizontal_crs")
        result = generate_contours(
            str(self.gradient_path),
            str(output_path),
            interval=10.0,
        )
        dataset = ogr.Open(str(output_path), 0)

        try:
            spatial_reference = (
                dataset.GetLayerByName(CONTOUR_LAYER_NAME)
                .GetSpatialRef()
            )
            self.assertFalse(spatial_reference.IsCompound())
            self.assertEqual(
                spatial_reference.GetAuthorityCode(None),
                "4326",
            )
            self.assertEqual(result["crs_authid"], "EPSG:4326")
        finally:
            dataset = None

    def test_nodata_does_not_generate_contours(self):
        output_path = self._output_path("nodata")
        result = generate_contours(
            str(self.nodata_path),
            str(output_path),
            interval=100.0,
            base=50.0,
        )

        self.assertEqual(result["feature_count"], 0)

        dataset = ogr.Open(str(output_path), 0)

        try:
            self.assertEqual(
                dataset.GetLayerByName(CONTOUR_LAYER_NAME)
                .GetFeatureCount(),
                0,
            )
        finally:
            dataset = None

    def test_elevation_values_have_expected_semantics(self):
        expected_types = {
            -10.0: CONTOUR_TYPE_DEPTH,
            0.0: CONTOUR_TYPE_ZERO,
            10.0: CONTOUR_TYPE_ELEVATION,
        }

        for elevation, expected_type in expected_types.items():
            with self.subTest(elevation=elevation):
                self.assertEqual(
                    classify_contour_elevation(elevation),
                    expected_type,
                )

    def test_type_field_matches_elevation_semantics(self):
        output_path = self._output_path("semantics")
        result = generate_contours(
            str(self.semantic_path),
            str(output_path),
            interval=10.0,
            base=0.0,
        )
        dataset = ogr.Open(str(output_path), 0)

        try:
            layer = dataset.GetLayerByName(CONTOUR_LAYER_NAME)
            stored_types = set()

            for feature in layer:
                elevation = feature.GetFieldAsDouble("ELEV")
                contour_type = feature.GetFieldAsString("TYPE")
                self.assertEqual(
                    contour_type,
                    classify_contour_elevation(elevation),
                )
                stored_types.add(contour_type)

            self.assertEqual(
                stored_types,
                {
                    CONTOUR_TYPE_ELEVATION,
                    CONTOUR_TYPE_DEPTH,
                    CONTOUR_TYPE_ZERO,
                },
            )
            self.assertEqual(
                sum(result["type_counts"].values()),
                result["feature_count"],
            )
        finally:
            dataset = None

    def test_non_finite_elevation_cannot_be_classified(self):
        for elevation in (float("nan"), float("inf")):
            with self.subTest(elevation=elevation):
                with self.assertRaisesRegex(
                    ValueError,
                    "等值高程必须是有限数值",
                ):
                    classify_contour_elevation(elevation)

    def test_source_dem_is_not_modified(self):
        source_hash = self._sha256(self.gradient_path)

        generate_contours(
            str(self.gradient_path),
            str(self._output_path("source_unchanged")),
            interval=10.0,
        )

        self.assertEqual(
            self._sha256(self.gradient_path),
            source_hash,
        )

    def test_non_positive_or_non_finite_interval_is_rejected(self):
        for index, interval in enumerate(
            (0.0, -1.0, float("nan"), float("inf"))
        ):
            output_path = self._output_path(
                f"invalid_interval_{index}"
            )

            with self.subTest(interval=interval):
                with self.assertRaisesRegex(
                    ValueError,
                    "间隔必须是大于 0 的有限数值",
                ):
                    generate_contours(
                        str(self.gradient_path),
                        str(output_path),
                        interval=interval,
                    )

                self.assertFalse(output_path.exists())

    def test_existing_output_is_not_overwritten(self):
        output_path = self._output_path("existing")
        output_path.write_bytes(b"keep")

        with self.assertRaises(FileExistsError):
            generate_contours(
                str(self.gradient_path),
                str(output_path),
            )

        self.assertEqual(output_path.read_bytes(), b"keep")

    def test_missing_source_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            generate_contours(
                str(self.temp_path / "missing.tif"),
                str(self._output_path("missing")),
            )

    def test_source_cannot_be_overwritten(self):
        with self.assertRaisesRegex(
            ValueError,
            "输出路径不能与源栅格路径相同",
        ):
            generate_contours(
                str(self.gradient_path),
                str(self.gradient_path),
            )

    def test_output_must_be_geopackage(self):
        output_path = self.temp_path / "contours.shp"

        with self.assertRaisesRegex(ValueError, r"\.gpkg"):
            generate_contours(
                str(self.gradient_path),
                str(output_path),
            )

        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
