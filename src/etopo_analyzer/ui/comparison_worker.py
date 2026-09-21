"""F10 后台对比任务，Qt 控件与图表均留在主线程。"""

from qgis.PyQt.QtCore import QThread, pyqtSignal
from etopo_analyzer.core.region_comparison import compare_regions
from etopo_analyzer.core.raster_statistics import StatisticsCancelled


class ComparisonWorker(QThread):
    succeeded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)
    progress = pyqtSignal(int, int, str)

    def __init__(self, task_id, path_a, path_b, bins, thresholds, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.arguments = (path_a, path_b, bins, tuple(thresholds))

    def run(self):
        try:
            result = compare_regions(*self.arguments,
                                     cancelled=self.isInterruptionRequested,
                                     progress=lambda p, s: self.progress.emit(self.task_id, p, s))
            if self.isInterruptionRequested():
                raise StatisticsCancelled()
            self.succeeded.emit(self.task_id, result)
        except StatisticsCancelled:
            self.failed.emit(self.task_id, "区域对比已取消。")
        except Exception as exc:
            self.failed.emit(self.task_id, str(exc))
