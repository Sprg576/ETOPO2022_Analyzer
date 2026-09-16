"""F07 等高线 / 等深线人工 GUI 验收。

首次运行会从全球 ETOPO2022 栅格裁剪台湾及邻近海域的 6° × 6°
样例，随后直接生成 500 m 等值线，便于检查陆地、海底和 0 m 分类。
本文件不参与 unittest 自动发现。
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from qgis.core import QgsApplication, QgsProject

from etopo_analyzer.core.layer_manager import add_raster_layer
from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow


SOURCE_RASTER_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "ETOPO_2022_v1_60s_N90W180_surface.tif"
)
PREVIEW_RASTER_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "f07_manual_preview.tif"
)


def _ensure_preview_raster() -> Path:
    """准备同时包含陆地与海底的局部验收 DEM。"""

    if PREVIEW_RASTER_PATH.is_file():
        return PREVIEW_RASTER_PATH

    if not SOURCE_RASTER_PATH.is_file():
        raise FileNotFoundError(
            f"测试栅格不存在：{SOURCE_RASTER_PATH}"
        )

    clip_raster_by_bounds(
        str(SOURCE_RASTER_PATH),
        str(PREVIEW_RASTER_PATH),
        west=120.0,
        south=20.0,
        east=126.0,
        north=26.0,
    )

    return PREVIEW_RASTER_PATH


def main() -> int:
    """启动已加载局部 DEM 和等值线结果的正式主窗口。"""

    app = QgsApplication([], True)
    app.initQgis()

    try:
        preview_path = _ensure_preview_raster()
        layer = add_raster_layer(
            str(preview_path),
            "F07 台湾及邻近海域 DEM",
        )
        window = ETOPOAnalyzerMainWindow()
        window.show_layer(layer)
        window.apply_color_relief()
        window.contour_interval_spin.setValue(500.0)
        window.contour_base_spin.setValue(0.0)
        window.create_contours()
        window.show()

        print("\nF07 contour GUI started.")
        print("当前已显示 500 m 等值线，可在右侧调整间隔和基准值后重新生成。")
        print("请同时检查图层显隐、地图交互、单点查询和矩形裁剪。")
        print("关闭窗口后程序将退出。\n")

        return app.exec()
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
