"""F10 区域选择、任务版本和结果发布；不修改活动分析 DEM。"""

from pathlib import Path
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QSpinBox, QLineEdit, QLabel, QProgressBar, QAction, QDockWidget, QSizePolicy
from qgis.core import QgsRasterLayer, QgsProject

from etopo_analyzer.core.raster_statistics import DEFAULT_THRESHOLDS, validate_parameters, source_signature
from etopo_analyzer.ui.comparison_worker import ComparisonWorker


class ComparisonControls(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = self.result = self.panel = self.dock = None
        self.task_id = 0
        self.start_action = QAction("开始区域对比", self)
        self.cancel_action = QAction("取消区域对比", self)
        self.show_action = QAction("显示对比结果", self)
        self.swap_action = QAction("交换 A/B", self)
        self.start_action.triggered.connect(self.start)
        self.cancel_action.triggered.connect(self.cancel)
        self.show_action.triggered.connect(self.show_result)
        self.swap_action.triggered.connect(self.swap)
        self.cancel_action.setEnabled(False)
        self.show_action.setEnabled(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        form = QFormLayout()
        self.region_a, self.region_b = QComboBox(self), QComboBox(self)
        for combo, title in ((self.region_a, "区域 A"), (self.region_b, "区域 B")):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            form.addRow(title, combo)
            combo.currentIndexChanged.connect(self.selection_changed)
        self.bins = QSpinBox(self)
        self.bins.setRange(1, 200)
        self.bins.setValue(50)
        self.thresholds = QLineEdit(", ".join(map(str, DEFAULT_THRESHOLDS)), self)
        self.thresholds.setToolTip("1～50 个严格递增的米制高程阈值，以逗号分隔。")
        form.addRow("公共箱数", self.bins)
        form.addRow("分级阈值（m）", self.thresholds)
        layout.addLayout(form)
        self.source_summary = QLabel(self)
        self.source_summary.setWordWrap(True)
        self.source_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.source_summary)
        for action in (self.swap_action, self.start_action, self.cancel_action, self.show_action):
            layout.addWidget(window._panel_button(action))
        self.progress = QProgressBar(self)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.message = QLabel("选择两个 DEM；A/B 独立于当前活动分析源。", self)
        self.message.setWordWrap(True)
        self.message.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.message)
        self.bins.valueChanged.connect(self.selection_changed)
        self.thresholds.textChanged.connect(self.selection_changed)
        QgsProject.instance().layersRemoved.connect(self.refresh_sources)
        self.refresh_sources()

    def selected_layers(self):
        layers = [self.window._managed_layers.get(c.currentData()) for c in (self.region_a, self.region_b)]
        if any(layer is None or sip.isdeleted(layer) or not layer.isValid() for layer in layers):
            return None
        return layers

    def refresh_sources(self, *args):
        previous = [c.currentData() for c in (self.region_a, self.region_b)]
        options = []
        for layer_id, item in self.window._layer_items.items():
            layer = self.window._managed_layers.get(layer_id)
            if layer is None or sip.isdeleted(layer) or not isinstance(layer, QgsRasterLayer) or not layer.isValid():
                continue
            group = item.parent().text(0)
            if group in ("源数据", "裁剪结果"):
                options.append((f"{layer.name()} [{group}]", layer_id, layer.source()))
        for combo, selected in zip((self.region_a, self.region_b), previous):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("请选择 DEM", None)
            for name, layer_id, path in options:
                combo.addItem(name, layer_id)
                combo.setItemData(combo.count() - 1, path, Qt.ToolTipRole)
            combo.setCurrentIndex(max(0, combo.findData(selected)))
            combo.blockSignals(False)
        if previous != [c.currentData() for c in (self.region_a, self.region_b)]:
            self.invalidate("已选区域不可用，请重新选择。")
        self.update_summary()
        self.update_actions()

    def update_summary(self):
        layers = self.selected_layers()
        if layers is None:
            self.source_summary.setText("区域使用所选 DEM 全范围；不随地图视野变化。")
            return
        lines = []
        for key, layer in zip("AB", layers):
            extent = layer.extent()
            lines.append(f"{key}：{layer.width()}×{layer.height()}；分辨率 {layer.rasterUnitsPerPixelX():.6g}×{layer.rasterUnitsPerPixelY():.6g}\n"
                         f"范围 {extent.xMinimum():.4f}, {extent.yMinimum():.4f} — {extent.xMaximum():.4f}, {extent.yMaximum():.4f}")
        self.source_summary.setText("\n".join(lines))
        self.source_summary.setToolTip("\n".join(layer.source() for layer in layers))

    def update_actions(self):
        idle = self.worker is None and self.window._statistics_worker is None and not self.window._closing
        self.start_action.setEnabled(idle and self.selected_layers() is not None)
        self.window.statistics_action.setEnabled(idle and self.window._active_raster_path is not None)

    def selection_changed(self, *args):
        self.invalidate("区域或参数已修改，请重新计算对比。")
        self.update_summary()
        self.update_actions()

    def swap(self):
        a, b = self.region_a.currentIndex(), self.region_b.currentIndex()
        self.region_a.blockSignals(True)
        self.region_b.blockSignals(True)
        self.region_a.setCurrentIndex(b)
        self.region_b.setCurrentIndex(a)
        self.region_a.blockSignals(False)
        self.region_b.blockSignals(False)
        self.selection_changed()

    def invalidate(self, message):
        self.task_id += 1
        if self.worker is not None:
            self.worker.requestInterruption()
        self.result = None
        self.show_action.setEnabled(False)
        self.cancel_action.setEnabled(False)
        self.hide_result()
        if self.panel is not None:
            self.panel.clear()
            self.panel.deleteLater()
            self.panel = None
        self.message.setText(message)

    def start(self):
        layers = self.selected_layers()
        if layers is None or self.worker is not None or self.window._statistics_worker is not None or self.window._closing:
            return
        self.invalidate("正在校验两区域……")
        try:
            thresholds = [float(v.strip()) for v in self.thresholds.text().replace("，", ",").split(",")]
            validate_parameters(self.bins.value(), thresholds)
        except ValueError as exc:
            self.message.setText(f"参数无效：{exc}")
            return
        self.worker = ComparisonWorker(self.task_id, layers[0].source(), layers[1].source(), self.bins.value(), thresholds, self)
        self.worker.succeeded.connect(self.succeeded)
        self.worker.failed.connect(self.failed)
        self.worker.progress.connect(self.progress_changed)
        self.worker.finished.connect(self.finished)
        self.cancel_action.setEnabled(True)
        self.progress.setValue(0)
        self.progress.show()
        self.update_actions()
        self.window._analysis_scroll.ensureWidgetVisible(self)
        self.worker.start()

    def cancel(self):
        if self.worker is not None:
            self.invalidate("已请求取消，等待当前分块读取结束。")

    def progress_changed(self, task_id, percent, phase):
        if task_id == self.task_id and not self.window._closing:
            self.progress.setValue(percent)
            self.message.setText(f"{phase}：{percent}%")

    def failed(self, task_id, message):
        if task_id == self.task_id and not self.window._closing:
            self.invalidate(f"对比未完成：{message}")

    def _check_result_sources(self, result):
        layers = self.selected_layers()
        if layers is None:
            raise RuntimeError("区域图层已不可用。")
        for layer, key in zip(layers, ("a", "b")):
            region = result["regions"][key]
            if (str(Path(layer.source()).resolve()) != region["raster_path"] or
                    source_signature(region["raster_path"]) != (region["source"]["size_bytes"], region["source"]["mtime_ns"])):
                raise RuntimeError("区域文件已变化，请重新计算。")

    def succeeded(self, task_id, result):
        if task_id != self.task_id or self.window._closing:
            return
        panel = None
        try:
            self._check_result_sources(result)
            from etopo_analyzer.ui.comparison_panel import ComparisonPanel
            panel = ComparisonPanel(result, self.window)
            for canvas in panel.canvases:
                canvas.draw()
            if self.dock is None:
                self.dock = QDockWidget("区域对比", self.window)
                self.dock.setObjectName("ComparisonDock")
                self.dock.setMinimumHeight(420)
                self.dock.setFeatures(QDockWidget.DockWidgetClosable)
                self.window.map_splitter.addWidget(self.dock)
            self.dock.setWidget(panel)
            # QDockWidget 安装内容后会重算约束，此时再设置高度，避免图表被裁切。
            self.dock.setMinimumHeight(max(420, panel.minimumSizeHint().height() + 30))
        except Exception as exc:
            if panel is not None:
                panel.clear()
                panel.deleteLater()
            self.failed(task_id, str(exc))
            return
        self.panel, self.result = panel, result
        self.show_action.setEnabled(True)
        self.message.setText(f"对比完成，用时 {result['elapsed_s']:.2f} 秒；差值方向 B−A。")
        self.show_result()

    def finished(self):
        worker = self.sender()
        if worker is not self.worker:
            return
        worker.wait()
        self.worker = None
        worker.deleteLater()
        self.cancel_action.setEnabled(False)
        self.progress.hide()
        if self.message.text().startswith("已请求取消"):
            self.message.setText("区域对比已取消。")
        self.update_actions()
        if self.window._closing:
            QTimer.singleShot(0, self.window.close)

    def hide_result(self):
        if self.dock is not None:
            self.dock.hide()

    def show_result(self):
        if self.result is None:
            return
        try:
            self._check_result_sources(self.result)
        except (OSError, RuntimeError) as exc:
            self.invalidate(str(exc))
            return
        for dock in (self.window._profile_dock, self.window._statistics_dock):
            if dock is not None:
                dock.hide()
        self.dock.show()
        QTimer.singleShot(0, self.resize_result)

    def resize_result(self):
        if self.result is None or self.dock.isHidden():
            return
        splitter = self.window.map_splitter
        height = max(splitter.height(), 600)
        result_height = max(int(height * .5), self.dock.minimumHeight())
        splitter.setSizes([max(100, height - result_height) if i == 0 else result_height if splitter.widget(i) is self.dock else 0
                           for i in range(splitter.count())])
