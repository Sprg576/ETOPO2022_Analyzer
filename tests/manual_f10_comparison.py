"""F10 人工验收：台湾及东侧海域两个独立区域，自动开始对比。"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QTimer
from etopo_analyzer.core.layer_manager import add_raster_layer
from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow


def main():
    app = QgsApplication([], True)
    app.initQgis()
    try:
        original = PROJECT_ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"
        window = ETOPOAnalyzerMainWindow()
        layers = []
        for key, west, east in (("a", 120, 123), ("b", 123, 126)):
            path = PROJECT_ROOT / "outputs" / f"f10_region_{key}.tif"
            if not path.is_file():
                clip_raster_by_bounds(str(original), str(path), west=west, south=20, east=east, north=26)
            layer = add_raster_layer(str(path), f"区域 {key.upper()}：{'台湾及近海' if key == 'a' else '东侧海域'}")
            window.show_layer(layer, layer_group="裁剪结果")
            layers.append(layer)
        controls = window._comparison_controls
        for combo, layer in zip((controls.region_a, controls.region_b), layers):
            combo.setCurrentIndex(combo.findData(layer.id()))
        window.show()
        QTimer.singleShot(0, controls.start)
        if "--snapshot" in sys.argv:
            def capture(index=0):
                if controls.worker is not None:
                    QTimer.singleShot(100, capture)
                    return
                if controls.result is None:
                    print(controls.message.text())
                    window.close()
                    app.exit(1)
                    return
                controls.panel.tabs.setCurrentIndex(index)
                def save():
                    window.grab().save(str(PROJECT_ROOT / "outputs" / f"f10_layout_{index}.png"))
                    if index < 3:
                        capture(index + 1)
                    else:
                        print("F10 四个标签页截图已保存至 outputs。")
                        window.close()
                        app.quit()
                QTimer.singleShot(300, save)
            QTimer.singleShot(500, capture)
        print("检查四个对比标签页、交换 A/B 和公共分级；切换活动 DEM 不应改变 A/B。")
        print("分布纵轴是像元占比；分级图纵轴是面积占比；差值方向始终为 B−A。")
        return app.exec()
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
