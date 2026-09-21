"""F09 人工验收：台湾及邻近海域统计，随后可切换派生显示复测。"""

import sys
from pathlib import Path

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
        preview = PROJECT_ROOT / "outputs" / "f09_manual_preview.tif"
        if not preview.is_file():
            clip_raster_by_bounds(
                str(PROJECT_ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"),
                str(preview), west=120, south=20, east=126, north=26,
            )
        window = ETOPOAnalyzerMainWindow()
        window.show_layer(add_raster_layer(str(preview), "F09 台湾及邻近海域 DEM"))
        window.apply_color_relief()
        window.show()
        QTimer.singleShot(0, window.create_statistics)
        if "--snapshot" in sys.argv:
            # 离屏布局检查，仍需另行进行真实窗口人工验收。
            output = PROJECT_ROOT / "outputs"
            def capture(index=0):
                if window._statistics_worker is not None:
                    QTimer.singleShot(100, capture)
                    return
                if window._statistics_result is None:
                    print(window.statistics_message.text())
                    window.close()
                    app.exit(1)
                    return
                window._statistics_panel.tabs.setCurrentIndex(index)
                def save():
                    window.grab().save(str(output / f"f09_layout_{index}.png"))
                    if index < 2:
                        capture(index + 1)
                    else:
                        print("F09 三个标签页布局截图已保存至 outputs。")
                        window.close()
                        app.quit()
                QTimer.singleShot(300, save)
            QTimer.singleShot(500, capture)
        print("F09：检查底部三个标签页；更改右侧箱数和阈值后重新计算。")
        print("切换坡度/坡向/Hillshade 后统计值应不变；裁剪或打开新 DEM 后旧统计失效。")
        print("全球数据可验证进度与取消；区域对比与成果导出不属于 F09。")
        return app.exec()
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
