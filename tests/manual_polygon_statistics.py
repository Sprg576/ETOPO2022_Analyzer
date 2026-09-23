"""人工验收：同一全球 DEM 上的台湾及近海 A/B 多边形，无需先裁剪。"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from qgis.core import QgsApplication, QgsProject, QgsRectangle
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QFontDatabase
from etopo_analyzer.core.layer_manager import add_raster_layer
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow


def main():
    app = QgsApplication([], True)
    app.initQgis()
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    window = ETOPOAnalyzerMainWindow()
    window.resize(1600, 1000)
    source = PROJECT_ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"
    layer = add_raster_layer(str(source))
    window.show_layer(layer)
    controls = window._comparison_controls
    for combo in (controls.region_a, controls.region_b):
        combo.setCurrentIndex(combo.findData(layer.id()))
    for key, points in (("a", [[120, 22], [121, 21.8], [122.2, 25.3], [121.3, 25.6], [120, 23.6]]),
                        ("b", [[122.5, 22], [125.3, 22.5], [125, 25.6], [122.8, 25.3]])):
        window.polygon_controls.set_polygon(key, dict(type="Polygon", coordinates=[points]))
    window.show()
    window.map_canvas.setExtent(QgsRectangle(118, 20, 128, 28))
    window._show_comparison_controls()
    QTimer.singleShot(100, controls.start)
    if "--snapshot" in sys.argv:
        attempts = [0]
        def capture():
            attempts[0] += 1
            if (controls.worker is not None or window.map_canvas.isDrawing()) and attempts[0] < 300:
                QTimer.singleShot(100, capture)
                return
            if controls.result is None:
                print(controls.message.text())
                window.close()
                app.exit(1)
                return
            print("A/B 有效像元：", [controls.result["regions"][key]["statistics"]["valid_count"] for key in ("a", "b")])
            path = PROJECT_ROOT / "outputs/polygon_comparison.png"
            window.grab().save(str(path))
            print(path)
            window.close()
            app.quit()
        QTimer.singleShot(1500, capture)
    print("可重新绘制 A/B、交换区域或取消多边形模式；CSV 导出附带 regions.geojson。")
    code = app.exec()
    window.map_canvas.stopRendering()
    window.map_canvas.setLayers([])
    QgsProject.instance().clear()
    app.exitQgis()
    return code


if __name__ == "__main__":
    sys.exit(main())
