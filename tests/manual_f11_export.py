"""F11 人工验收入口；--snapshot 生成真实数据的导出样例。"""

from datetime import datetime
from pathlib import Path
import sys
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QFontDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from etopo_analyzer.core.layer_manager import add_raster_layer
from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics
from etopo_analyzer.core.region_comparison import compare_regions
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
from etopo_analyzer.ui.export_dialog import ExportDialog


def main():
    app = QgsApplication([], True)
    app.initQgis()
    if not QFontDatabase().families():
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    window = ETOPOAnalyzerMainWindow()
    from processing_test_support import wrap_processing_calls
    wrap_processing_calls(window)
    original = PROJECT_ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"
    paths, layers = [], []
    for key, west, east in (("a", 120, 123), ("b", 123, 126)):
        path = PROJECT_ROOT / "outputs" / f"f10_region_{key}.tif"
        if not path.is_file():
            clip_raster_by_bounds(str(original), str(path), west=west, south=20, east=east, north=26)
        paths.append(path)
        layer = add_raster_layer(str(path), f"区域 {key.upper()} 高程（m）")
        window.show_layer(layer, layer_group="裁剪结果")
        layers.append(layer)
    window.show_layer(layers[0], layer_group="裁剪结果")
    window.apply_color_relief()
    window.create_profile([(120.2, 22), (122.8, 24)])
    window._statistics_result = calculate_raster_statistics(str(paths[0]))
    controls = window._comparison_controls
    for combo, layer in zip((controls.region_a, controls.region_b), layers):
        combo.setCurrentIndex(combo.findData(layer.id()))
    controls.result = compare_regions(str(paths[0]), str(paths[1]))
    window.show()
    if "--snapshot" in sys.argv:
        parent = PROJECT_ROOT / "outputs" / f"f11_review_{datetime.now():%Y%m%d_%H%M%S_%f}"
        parent.mkdir()
        jobs = [("map", None), ("csv", "profile"), ("csv", "statistics"), ("csv", "comparison"),
                ("raster", None), ("chart", "profile"), ("chart", "statistics"),
                ("chart", "distribution"), ("chart", "area")]
        def capture(index=0):
            if index == len(jobs):
                print(f"F11 样例导出完成：{parent}")
                window.close()
                app.quit()
                return
            mode, key = jobs[index]
            dialog = ExportDialog(window, mode)
            dialog.directory.setText(str(parent))
            dialog.name.setText(mode + ("_" + key if key else ""))
            if key:
                dialog.choice.setCurrentIndex(dialog.choice.findData(key))
            dialog.include_profile.setChecked(True)
            dialog.show()
            def start():
                dialog.grab().save(str(parent / f"dialog_{mode}.png"))
                dialog.start()
                def done():
                    if dialog.worker is not None:
                        QTimer.singleShot(50, done)
                        return
                    if not dialog.output:
                        print(dialog.message.text())
                        dialog.close()
                        window.close()
                        app.exit(1)
                        return
                    dialog.close()
                    dialog.deleteLater()
                    QTimer.singleShot(0, lambda: capture(index + 1))
                done()
            QTimer.singleShot(100, start)
        QTimer.singleShot(300, capture)
    print("打开“导出”菜单验收地图、CSV、GeoTIFF 和分析图。样例已准备 F08/F09/F10 结果。")
    code = app.exec()
    window.map_canvas.stopRendering()
    window.map_canvas.setLayers([])
    QgsProject.instance().clear()
    return code


if __name__ == "__main__":
    sys.exit(main())
