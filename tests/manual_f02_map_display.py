"""
F02 / F03 人工 GUI 测试。

验证链路：

ETOPO2022 GeoTIFF
    ↓
QgsRasterLayer
    ↓
QgsProject
    ↓
ETOPOAnalyzerMainWindow
    ↓
ETOPOMapCanvas
    ↓
Pan / Zoom In / Zoom Out / Full Extent
    ↓
Point Query / Status Bar Result

本文件属于人工 GUI 测试，
不参与 unittest 自动发现。
"""

from __future__ import annotations

import sys
from pathlib import Path


# ---------------------------------------------------------
# 项目路径
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


# ---------------------------------------------------------
# QGIS
# ---------------------------------------------------------

from qgis.core import (
    QgsApplication,
    QgsProject,
)


# ---------------------------------------------------------
# 项目模块
# ---------------------------------------------------------

from etopo_analyzer.core.layer_manager import (
    add_raster_layer,
)

from etopo_analyzer.ui.main_window import (
    ETOPOAnalyzerMainWindow,
)


# ---------------------------------------------------------
# 数据路径
# ---------------------------------------------------------

RASTER_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "ETOPO_2022_v1_60s_N90W180_surface.tif"
)


def main() -> int:
    """
    执行 F02 / F03 主窗口与地图工具人工测试。
    """

    if not RASTER_PATH.is_file():
        raise FileNotFoundError(
            f"测试栅格不存在：{RASTER_PATH}"
        )

    # -----------------------------------------------------
    # 初始化独立 QGIS 应用
    # -----------------------------------------------------

    app = QgsApplication(
        [],
        True,
    )

    app.initQgis()

    try:

        # -------------------------------------------------
        # 创建 QGIS 图层
        # -------------------------------------------------

        layer = add_raster_layer(
            str(RASTER_PATH),
            "ETOPO2022 60s Surface",
        )

        print(
            "Raster layer valid:",
            layer.isValid(),
        )

        print(
            "Layer name:",
            layer.name(),
        )

        print(
            "Layer size:",
            layer.width(),
            "x",
            layer.height(),
        )

        print(
            "Layer CRS:",
            layer.crs().authid(),
        )

        print(
            "Layer extent:",
            layer.extent().toString(),
        )

        # -------------------------------------------------
        # 创建正式主窗口
        # -------------------------------------------------

        window = ETOPOAnalyzerMainWindow()

        # -------------------------------------------------
        # 显示真实 ETOPO2022 图层
        # -------------------------------------------------

        window.show_layer(
            layer
        )

        print(
            "Canvas destination CRS:",
            window.map_canvas
            .mapSettings()
            .destinationCrs()
            .authid(),
        )

        # -------------------------------------------------
        # 显示窗口
        # -------------------------------------------------

        window.show()

        print(
            "\nF02 / F03 main window started."
        )

        print(
            "请先点击“单点查询”，再在地图上单击一次；"
            "查询结果将显示在窗口底部状态栏。"
        )

        print(
            "关闭窗口后程序将退出。\n"
        )

        return app.exec()

    finally:

        QgsProject.instance().clear()

        app.exitQgis()


if __name__ == "__main__":
    sys.exit(
        main()
    )
