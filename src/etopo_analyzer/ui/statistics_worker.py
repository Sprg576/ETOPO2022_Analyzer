"""F09 专用后台任务；GDAL 数据集只在工作线程内使用。"""

from copy import deepcopy
from qgis.PyQt.QtCore import QThread, pyqtSignal
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics, StatisticsCancelled


class StatisticsWorker(QThread):
    succeeded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)
    cancelled = pyqtSignal(int)
    progress = pyqtSignal(int, int, str)

    def __init__(self, task_id, raster_path, bin_count, thresholds, parent=None, *, roi=None):
        super().__init__(parent)
        self.task_id = task_id
        self.raster_path = raster_path
        self.bin_count = bin_count
        self.thresholds = tuple(thresholds)
        self.roi = deepcopy(roi)

    def run(self):
        try:
            result = calculate_raster_statistics(
                self.raster_path, self.bin_count, self.thresholds,
                progress=lambda percent, phase: self.progress.emit(self.task_id, percent, phase),
                cancelled=self.isInterruptionRequested, roi=self.roi,
            )
            if self.isInterruptionRequested():
                raise StatisticsCancelled()
            self.succeeded.emit(self.task_id, result)
        except StatisticsCancelled:
            self.cancelled.emit(self.task_id)
        except Exception as exc:
            self.failed.emit(self.task_id, str(exc))
