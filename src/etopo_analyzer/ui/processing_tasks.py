"""单个活动计算任务；GDAL 在工作线程，图层发布在 GUI 线程。"""

from pathlib import Path
from qgis.PyQt.QtCore import QObject, QThread, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QProgressBar, QLabel, QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox
from etopo_analyzer.core.processing_feedback import feedback_scope, ProcessingCancelled
from etopo_analyzer.core.export_service import file_signature, validate_sources


class ProcessingWorker(QThread):
    progress = pyqtSignal(int, str)

    def __init__(self, stages, source, paths, parent):
        super().__init__(parent)
        self.stages, self.source = stages, source
        self.paths = [Path(path) for path in paths]
        self.result = self.error = None
        self.owned_paths = []

    def run(self):
        try:
            signature = file_signature(self.source)
            self.signature = signature
            for path in self.paths:
                if path.exists():
                    raise FileExistsError(f"输出已存在：{path}")
            self.owned_paths = self.paths[:]
            results = []
            for index, (name, operation) in enumerate(self.stages):
                last_percent = [-1]
                def report(fraction):
                    value = min(99, int(100 * (index + fraction) / len(self.stages)))
                    if value != last_percent[0]:
                        last_percent[0] = value
                        self.progress.emit(value, name)
                with feedback_scope(report, self.isInterruptionRequested):
                    report(0)
                    results.append(operation(results))
            validate_sources([signature])
            self.result = results
        except Exception as exc:
            self.error = "任务已取消。" if self.isInterruptionRequested() or isinstance(exc, ProcessingCancelled) else str(exc)

    def cleanup(self):
        # 仅处理本任务事先确认不存在的输出及其辅助文件。
        for path in self.owned_paths:
            for candidate in (path, Path(str(path) + ".aux.xml"), Path(str(path) + ".msk"),
                              Path(str(path) + "-wal"), Path(str(path) + "-shm")):
                if candidate.exists():
                    candidate.unlink()


class TaskControls(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = None
        self.inputs = None
        self.progress = QProgressBar(window)
        self.progress.setMaximumWidth(180)
        self.label = QLabel(window)
        window.statusBar().addWidget(self.label)
        window.statusBar().addWidget(self.progress)
        window.cancel_task_action.triggered.connect(self.cancel)
        self.refresh()

    def busy(self):
        w = self.window
        return self.worker is not None or w._statistics_worker is not None or w._comparison_controls.worker is not None

    def update_progress(self, percent, phase):
        self.label.setText(phase)
        self.progress.setValue(percent)

    def refresh(self):
        w = self.window
        busy = self.busy()
        active = w._active_raster_path is not None and not w._closing
        w.cancel_task_action.setEnabled(busy and not w._closing)
        w.cancel_task_action.setToolTip("取消当前计算任务")
        self.progress.setVisible(busy)
        self.label.setVisible(busy)
        if busy and not self.label.text():
            self.update_progress(0, "正在计算")
        if not busy:
            self.label.clear()
            self.progress.setValue(0)
        for action in (w.rectangle_clip_action, w.profile_action, w.hillshade_action,
                       w.slope_action, w.aspect_action, w.contour_action):
            action.setEnabled(active and not busy)
        w.regenerate_profile_action.setEnabled(active and not busy and w._profile_result is not None)
        w.open_raster_action.setEnabled(not busy and not w._closing)
        w.statistics_action.setEnabled(active and not busy)
        w._comparison_controls.start_action.setEnabled(not busy and not w._closing and w._comparison_controls.selected_layers() is not None)
        w._update_analysis_source_action()
        w._update_style_action()
        if hasattr(w, "clip_controls"):
            w.clip_controls.set_busy(busy)
        if self.worker is not None and self.inputs is None:
            widgets = w._analysis_scroll.findChildren((QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox))
            self.inputs = [(widget, widget.isEnabled()) for widget in widgets]
            for widget, enabled in self.inputs:
                widget.setEnabled(False)
        elif self.worker is None and self.inputs is not None:
            for widget, enabled in self.inputs:
                widget.setEnabled(enabled)
            self.inputs = None

    def start(self, name, stages, paths, publish, source_layer=None):
        w = self.window
        if self.busy() or w._closing or not w._active_raster_path:
            w.statusBar().showMessage("请等待当前任务结束后再开始新的分析。")
            return
        active_path, active_layer = w._active_raster_path, w._active_raster_layer
        source_layer = source_layer or active_layer
        source = source_layer.source()
        source_id = source_layer.id()
        worker = ProcessingWorker(stages, source, paths, w)
        self.worker = worker
        self.update_progress(0, name)
        worker.progress.connect(self.update_progress)
        def finished():
            worker.wait()
            try:
                valid = (not w._closing and w._active_raster_path == active_path and
                         w._active_raster_layer is active_layer and source_id in w._managed_layers)
                if worker.error or worker.isInterruptionRequested() or not valid:
                    worker.cleanup()
                    message = worker.error or "任务已取消或分析源已变化，结果未加载。"
                    if worker.error and not worker.isInterruptionRequested():
                        message = f"{name}失败：{message}"
                    w.statusBar().showMessage(message)
                else:
                    validate_sources([worker.signature])
                    publish(worker.result)
            except Exception as exc:
                try:
                    worker.cleanup()
                except OSError as cleanup_error:
                    w.statusBar().showMessage(f"{name}失败：{exc}；临时成果清理失败：{cleanup_error}")
                else:
                    w.statusBar().showMessage(f"{name}失败：{exc}")
            finally:
                self.worker = None
                worker.deleteLater()
                self.refresh()
                if w._closing:
                    QTimer.singleShot(0, w.close)
        worker.finished.connect(finished)
        w.map_canvas.activate_pan()
        w.pan_action.setChecked(True)
        self.refresh()
        worker.start()

    def cancel(self):
        w = self.window
        if self.worker is not None:
            self.worker.requestInterruption()
        elif w._statistics_worker is not None:
            w.cancel_statistics()
        elif w._comparison_controls.worker is not None:
            w._comparison_controls.cancel()
        self.label.setText("正在取消…")
