"""第三、四批人工验收：真实区域、裁剪设置、剖面联动与导出预览。"""

from pathlib import Path
import sys
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QFontDatabase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from etopo_analyzer.core.layer_manager import add_raster_layer
from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
from etopo_analyzer.core.profile_analysis import sample_elevation_profile
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
from etopo_analyzer.ui.export_dialog import ExportDialog


def main():
    app = QgsApplication([], True)
    app.initQgis()
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    path = ROOT / "outputs/f10_region_a.tif"
    if not path.exists():
        clip_raster_by_bounds(str(ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"),
                              str(path), 120, 20, 123, 26)
    window = ETOPOAnalyzerMainWindow()
    window.resize(1440, 960)
    window.show_layer(add_raster_layer(str(path), "台湾周边高程"), "源数据")
    window.apply_color_relief()
    window.show()
    window.clip_controls.receive(dict(west=120.2, south=22.2, east=122.4, north=25))
    if "--snapshot" in sys.argv:
        output = ROOT / "outputs/batch34_review"
        output.mkdir(exist_ok=True)
        def capture():
            window.grab().save(str(output / "clip.png"))
            window.clip_controls.hide()
            result = sample_elevation_profile(str(path), [(120.2, 22), (122.8, 24)], 1000)
            window._publish_profile(result)
            def profile():
                from types import SimpleNamespace
                panel = window._profile_panel
                panel.hover(SimpleNamespace(inaxes=panel.canvas.figure.axes[0], xdata=120))
                window.grab().save(str(output / "profile.png"))
                dialog = ExportDialog(window, "map")
                dialog.pixels.setValue(1200)
                dialog.show()
                dialog.preview()
                dialog.grab().save(str(output / "preview.png"))
                dialog.close()
                window.close()
                app.quit()
            QTimer.singleShot(600, profile)
        QTimer.singleShot(800, capture)
    app.exec_()
    window.map_canvas.setLayers([])
    QgsProject.instance().clear()


if __name__ == "__main__":
    main()
