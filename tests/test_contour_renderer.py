"""F07-3 等值线矢量分类渲染测试。"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, osr


gdal.UseExceptions()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from qgis.PyQt import sip

from qgis.core import (
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsVectorLayer,
)

from etopo_analyzer.core.contour_analysis import (
    CONTOUR_LAYER_NAME,
    generate_contours,
)
from etopo_analyzer.visualization.contour_renderer import (
    CONTOUR_STYLE_CLASSES,
    apply_contour_classification,
)


class TestContourRenderer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qgs = QgsApplication.instance()

        if cls.qgs is None:
            cls.qgs = QgsApplication([], True)
            cls.qgs.initQgis()

        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_directory.name)
        cls.dem_path = cls.temp_path / "semantic_dem.tif"
        cls.contour_path = cls.temp_path / "contours.gpkg"
        cls._create_dem()
        generate_contours(
            str(cls.dem_path),
            str(cls.contour_path),
            interval=10.0,
            base=0.0,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    @classmethod
    def _create_dem(cls) -> None:
        values = np.array(
            [
                [-20.0, -10.0, 0.0, 10.0, 20.0],
                [-20.0, -10.0, 0.0, 10.0, 20.0],
                [-20.0, -10.0, 0.0, 10.0, 20.0],
            ],
            dtype=np.float32,
        )
        dataset = gdal.GetDriverByName("GTiff").Create(
            str(cls.dem_path),
            values.shape[1],
            values.shape[0],
            1,
            gdal.GDT_Float32,
        )
        dataset.SetGeoTransform(
            (100.0, 1.0, 0.0, 50.0, 0.0, -1.0)
        )
        spatial_reference = osr.SpatialReference()
        spatial_reference.ImportFromEPSG(9518)
        dataset.SetSpatialRef(spatial_reference)
        dataset.GetRasterBand(1).WriteArray(values)
        dataset = None

    def setUp(self):
        source = (
            f"{self.contour_path}"
            f"|layername={CONTOUR_LAYER_NAME}"
        )
        self.layer = QgsVectorLayer(
            source,
            "contours",
            "ogr",
        )
        self.assertTrue(self.layer.isValid())

    def tearDown(self):
        if self.layer is not None and not sip.isdeleted(self.layer):
            sip.delete(self.layer)

        self.layer = None

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_applies_three_type_categories(self):
        renderer = apply_contour_classification(
            self.layer
        )

        self.assertIsInstance(
            renderer,
            QgsCategorizedSymbolRenderer,
        )
        self.assertEqual(renderer.classAttribute(), "TYPE")

        categories = renderer.categories()
        self.assertEqual(len(categories), 3)
        self.assertEqual(
            [category.value() for category in categories],
            [item[0] for item in CONTOUR_STYLE_CLASSES],
        )
        self.assertEqual(
            [category.label() for category in categories],
            [item[3] for item in CONTOUR_STYLE_CLASSES],
        )

    def test_categories_use_expected_colors_and_widths(self):
        renderer = apply_contour_classification(
            self.layer
        )

        for category, expected in zip(
            renderer.categories(),
            CONTOUR_STYLE_CLASSES,
        ):
            with self.subTest(value=category.value()):
                self.assertEqual(
                    category.symbol().color().name().upper(),
                    expected[1],
                )
                self.assertAlmostEqual(
                    category.symbol().width(),
                    expected[2],
                )

    def test_renderer_does_not_modify_geopackage(self):
        before_hash = self._sha256(self.contour_path)

        apply_contour_classification(self.layer)

        self.assertEqual(
            self._sha256(self.contour_path),
            before_hash,
        )

    def test_missing_type_field_is_rejected(self):
        self.layer = QgsVectorLayer(
            "LineString?crs=EPSG:4326&field=ELEV:double",
            "missing_type",
            "memory",
        )

        with self.assertRaisesRegex(ValueError, "TYPE"):
            apply_contour_classification(self.layer)

    def test_non_line_layer_is_rejected(self):
        self.layer = QgsVectorLayer(
            "Polygon?crs=EPSG:4326"
            "&field=ELEV:double&field=TYPE:string",
            "polygon",
            "memory",
        )

        with self.assertRaisesRegex(ValueError, "线几何"):
            apply_contour_classification(self.layer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
