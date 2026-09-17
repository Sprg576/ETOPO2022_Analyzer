"""F08 人工验收：台湾陆地至邻近深海剖面，随后可自行绘制。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from qgis.core import QgsApplication, QgsProject
from etopo_analyzer.core.layer_manager import add_raster_layer
from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow


def main():
    app = QgsApplication([], True)
    app.initQgis()
    try:
        preview = PROJECT_ROOT / "outputs" / "f08_manual_preview.tif"
        if not preview.is_file():
            clip_raster_by_bounds(
                str(PROJECT_ROOT / "data" / "raw" / "ETOPO_2022_v1_60s_N90W180_surface.tif"),
                str(preview), west=120, south=20, east=126, north=26,
            )
        window = ETOPOAnalyzerMainWindow()
        window.show_layer(add_raster_layer(str(preview), "F08 台湾及邻近海域 DEM"))
        window.apply_color_relief()
        window.create_profile([(120.8, 23.5), (123.5, 23.5)])
        window.show()
        print("F08：左键加点，右键或双击完成；Esc 取消。")
        print("修改右侧间隔后重新生成，并复查单点查询、裁剪和派生图层显示。")
        return app.exec()
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
