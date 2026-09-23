"""发行版入口。由 Start.cmd 配置随包运行环境后启动。"""

import argparse
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--smoke-gui", action="store_true")
    parser.add_argument("--create-demo", action="store_true")
    parser.add_argument("--verify-window", type=Path)
    args = parser.parse_args()
    runtime = Path(os.environ.get("OSGEO4W_ROOT", ""))
    # 保持 DLL 句柄存活到整个应用退出；不依赖开发电脑的 PATH。
    dll_handles = [os.add_dll_directory(str(path)) for path in
                   (runtime / "bin", runtime / "apps/Qt5/bin", runtime / "apps/qgis-ltr/bin") if path.is_dir()]
    from osgeo import gdal, osr
    gdal.UseExceptions()
    # GDAL/PROJ 的 Windows 环境变量读取可能使用本地代码页；显式传入 UTF-8 路径。
    osr.SetPROJSearchPaths([str(runtime / "share/proj")])
    from qgis.core import QgsApplication, QgsProject
    from qgis.PyQt.QtCore import QTimer, QCoreApplication, QEvent
    from qgis.PyQt.QtGui import QFontDatabase
    app = QgsApplication([], True)
    app.setOrganizationName("ETOPOAnalyzer")
    app.setApplicationName("ETOPO2022 Analyzer")
    app.initQgis()
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
    window = None
    try:
        if args.create_demo:
            from etopo_analyzer.release_check import create_demo
            path = ROOT / "data/demo.tif"
            path.parent.mkdir(exist_ok=True)
            if path.exists():
                raise FileExistsError(path)
            create_demo(path)
            return 0
        if args.self_check:
            from etopo_analyzer.release_check import run_check
            run_check(args.report)
            return 0
        from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
        from etopo_analyzer.core.layer_manager import add_raster_layer
        window = ETOPOAnalyzerMainWindow()
        if args.demo or args.smoke_gui:
            window.show_layer(add_raster_layer(str(ROOT / "data/demo.tif"), "示例地形（合成数据）"))
            window.apply_color_relief()
        window.show()
        if args.verify_window:
            def verify_window():
                import ctypes
                import json
                is_visible = ctypes.windll.user32.IsWindowVisible
                is_visible.argtypes = [ctypes.c_void_p]
                visible = bool(is_visible(int(window.winId())))
                result = dict(passed=visible and window.isVisible(), native_visible=visible,
                              platform=app.platformName(), demo=args.demo,
                              loaded_layers=len(window.map_canvas.layers()), pid=os.getpid())
                from etopo_analyzer.version import VERSION
                result.update(version=VERSION, title=window.windowTitle())
                if args.demo and result["loaded_layers"] == 0:
                    result["passed"] = False
                args.verify_window.parent.mkdir(parents=True, exist_ok=True)
                args.verify_window.write_text(json.dumps(result, indent=2), encoding="utf-8")
                window.grab().save(str(args.verify_window.with_suffix(".png")))
                window.workspace_controls.mark_clean()
                window.close()
                app.exit(0 if result["passed"] else 1)
            QTimer.singleShot(1500, verify_window)
        if args.smoke_gui:
            def finish_smoke():
                window.workspace_controls.mark_clean()
                window.close()
            QTimer.singleShot(1500, finish_smoke)
        return app.exec()
    finally:
        if window is not None:
            window.map_canvas.stopRendering()
            window.map_canvas.setLayers([])
            window.close()
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
