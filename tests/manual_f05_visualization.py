"""
F05 彩色地形与 Hillshade 组合显示人工 GUI 测试。

默认使用真实 ETOPO2022 60 角秒 GeoTIFF，自动裁剪
120°E～125°E、30°N～35°N，随后通过主窗口完成局部 UTM
投影、Hillshade 生成和彩色 DEM 组合显示。

本文件不参与 unittest 自动发现。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from qgis.PyQt.QtCore import QEventLoop, QTimer

from qgis.core import QgsApplication, QgsProject

from etopo_analyzer.core.layer_manager import (
    add_raster_layer,
)
from etopo_analyzer.ui.main_window import (
    ETOPOAnalyzerMainWindow,
)


RASTER_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "ETOPO_2022_v1_60s_N90W180_surface.tif"
)


def _wait_for_render(window) -> None:
    """等待地图渲染完成，最长 15 秒。"""

    event_loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(event_loop.quit)
    window.map_canvas.renderComplete.connect(
        event_loop.quit
    )

    timer.start(15000)
    window.map_canvas.refresh()
    event_loop.exec()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="保存 GUI 验证截图后自动退出。",
    )
    args = parser.parse_args()

    if not RASTER_PATH.is_file():
        raise FileNotFoundError(
            f"测试栅格不存在：{RASTER_PATH}"
        )

    app = QgsApplication([], True)
    app.initQgis()
    temp_directory = tempfile.TemporaryDirectory()

    try:
        layer = add_raster_layer(
            str(RASTER_PATH),
            "ETOPO2022 60s Surface",
        )
        window = ETOPOAnalyzerMainWindow()
        window._clip_output_directory = Path(
            temp_directory.name
        )
        window.show_layer(layer)
        window._clip_selected_bounds(
            {
                "west": 120.0,
                "south": 30.0,
                "east": 125.0,
                "north": 35.0,
            }
        )
        window.create_hillshade()

        status_message = (
            window.statusBar().currentMessage()
        )
        canvas_layers = window.map_canvas.layers()

        if (
            not status_message.startswith(
                "Hillshade 完成："
            )
            or len(canvas_layers) != 2
        ):
            raise RuntimeError(
                "F05 GUI 验证准备失败："
                f"{status_message} | "
                f"Canvas 图层数：{len(canvas_layers)}"
            )

        window.show()

        print(status_message)
        print(
            "Canvas layers:",
            [
                layer.name()
                for layer in canvas_layers
            ],
        )

        if args.screenshot is None:
            print(
                "请检查彩色 DEM、Hillshade 明暗与地图交互；"
                "关闭窗口后程序退出。"
            )
            return app.exec()

        args.screenshot.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        _wait_for_render(window)
        screenshot_saved = window.grab().save(
            str(args.screenshot)
        )
        QgsApplication.processEvents()

        if (
            not screenshot_saved
            or not args.screenshot.is_file()
        ):
            raise RuntimeError(
                "主窗口未生成 GUI 验证截图。"
            )

        print(
            "Screenshot:",
            args.screenshot,
        )
        window.close()
        return 0
    finally:
        QgsProject.instance().clear()
        temp_directory.cleanup()
        app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
