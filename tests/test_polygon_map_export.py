"""多边形地图导出保留孔洞、颜色、投影及成果范围元数据。"""
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from qgis.PyQt.QtGui import QImage, QColor
from qgis.core import QgsCoordinateReferenceSystem, QgsUnitTypes
import test_export_ui as fixtures
from etopo_analyzer.ui.export_dialog import ExportDialog
from etopo_analyzer.visualization.map_export import export_map, polygon_layers


def polygon(west=120.05, east=120.25):
    return {"type": "Polygon", "coordinates": [[[west, 23.75], [east, 23.75],
        [east, 23.95], [west, 23.95], [west, 23.75]]]}


class TestPolygonMapExport(unittest.TestCase):
    setUpClass = classmethod(fixtures.TestExportUI.setUpClass.__func__)
    setUp = fixtures.TestExportUI.setUp
    tearDown = fixtures.TestExportUI.tearDown

    def test_enabled_completed_regions_only_and_dirty(self):
        w = self.window
        w.workspace_controls.mark_clean()
        c = w.polygon_controls
        c.set_polygon("a", polygon())
        self.assertTrue(w.workspace_controls.is_dirty())
        self.assertEqual([r["id"] for r in c.export_regions()], ["a"])
        c.checks["comparison"].setChecked(False)
        self.assertEqual(c.export_regions(), [])

    def test_holes_and_style_preserved(self):
        p = polygon()
        p["coordinates"].append([[120.1, 23.8], [120.1, 23.9], [120.2, 23.9],
                                  [120.2, 23.8], [120.1, 23.8]])
        self.window.polygon_controls.set_polygon("statistics", p)
        regions = self.window.polygon_controls.export_regions()
        layers = polygon_layers(regions)
        self.assertEqual(len(next(layers[0].getFeatures()).geometry().asPolygon()), 2)
        self.assertEqual(layers[0].renderer().symbol().color().alpha(), 30)
        self.assertTrue(layers[0].labelsEnabled())
        self.assertEqual(layers[0].labeling().settings().format().sizeUnit(), QgsUnitTypes.RenderPixels)

    def test_render_colors_projection_rotation_and_metadata(self):
        c = self.window.polygon_controls
        c.set_polygon("statistics", polygon(120.04, 120.16))
        c.set_polygon("a", polygon(120.2, 120.31))
        c.set_polygon("b", polygon(120.35, 120.46))
        canvas = self.window.map_canvas
        original_layers = canvas.layers()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        canvas.setRotation(12)
        original_extent = canvas.extent()
        regions = c.export_regions()
        metadata = export_map(self.root, canvas, "多边形统计范围", 1800, 150, polygons=regions)
        self.assertEqual(metadata["polygons"], regions)
        self.assertEqual(metadata["rotation"], 12)
        self.assertEqual(canvas.layers(), original_layers)
        self.assertEqual(canvas.extent(), original_extent)
        image = QImage(str(self.root / "map.png"))
        colors = {QColor(r["color"]).rgb() for r in regions}
        # 在地图主体而非右侧图例中查找三种边界颜色。
        seen = set()
        for y in range(int(image.height() * .8)):
            for x in range(int(image.width() * .65)):
                color = image.pixel(x, y)
                if color in colors:
                    seen.add(color)
        self.assertEqual(seen, colors)
        output = Path("outputs/polygon-map-export.png")
        image.save(str(output))

    def test_preview_and_export_checkbox_and_manifest(self):
        self.window.polygon_controls.set_polygon("a", polygon())
        self.dialog = ExportDialog(self.window, "map")
        self.assertTrue(self.dialog.include_polygons.isChecked())
        self.dialog.pixels.setValue(1200)
        self.dialog.directory.setText(str(self.root))
        self.dialog.name.setText("polygon-map")
        with patch("etopo_analyzer.visualization.map_export.export_map", wraps=export_map) as render:
            self.dialog.preview()
            self.dialog.start()
            self.assertEqual(render.call_args_list[0].kwargs["polygons"], render.call_args_list[1].kwargs["polygons"])
        manifest = json.loads((self.root / "polygon-map/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["metadata"]["polygons"][0]["geometry"], polygon())
        self.dialog.include_polygons.setChecked(False)
        with patch("etopo_analyzer.visualization.map_export.export_map", wraps=export_map) as render:
            self.dialog.preview()
            self.assertEqual(render.call_args.kwargs["polygons"], [])
