"""文件导出后台任务，信号只携带文件路径和消息。"""

from pathlib import Path
from qgis.PyQt.QtCore import QThread, pyqtSignal
from etopo_analyzer.core.export_service import export_package, ExportCancelled, check_cancelled
from etopo_analyzer.core.csv_export import export_csv
from etopo_analyzer.core.raster_export import export_raster


class ExportWorker(QThread):
    progress = pyqtSignal(int)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent_dir, name, mode, choice, result, sources, metadata, pixels=2400, dpi=300, parent=None):
        super().__init__(parent)
        self.parent_dir, self.name, self.mode, self.choice = parent_dir, name, mode, choice
        self.result, self.sources, self.metadata = result, sources, metadata
        self.pixels, self.dpi = pixels, dpi

    def run(self):
        try:
            with export_package(self.parent_dir, self.name, self.mode, self.sources, self.metadata,
                                self.isInterruptionRequested) as folder:
                if self.mode == "raster":
                    self.metadata["raster"] = export_raster(folder, self.choice, self.isInterruptionRequested, self.progress.emit)
                else:
                    kind = "comparison" if self.choice in ("distribution", "area") else self.choice
                    export_csv(folder, kind, self.result, self.isInterruptionRequested)
                    self.progress.emit(40)
                    if self.mode == "chart":
                        from etopo_analyzer.visualization.chart_export import export_chart
                        check_cancelled(self.isInterruptionRequested)
                        export_chart(folder, self.choice, self.result, self.pixels, self.dpi)
                    self.progress.emit(95)
            self.progress.emit(100)
            self.succeeded.emit(str(Path(self.parent_dir) / self.name))
        except ExportCancelled as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"导出失败：{exc}")
