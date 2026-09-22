"""F11 导出选择、来源预览、进度和取消。"""

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QSpinBox, QCheckBox, QLabel, QPushButton, QFileDialog, QProgressBar, QHBoxLayout, QAction)
from qgis.core import QgsRasterLayer
from etopo_analyzer.core.export_service import (export_package, file_signature, result_sources,
    result_metadata, validate_sources, layer_processing)
from .export_worker import ExportWorker


TITLES = {"map": "导出当前地图", "chart": "导出分析图", "csv": "导出分析数据 CSV", "raster": "导出栅格 GeoTIFF"}


def results(window):
    return {"profile": window._profile_result, "statistics": window._statistics_result,
            "comparison": window._comparison_controls.result if window._comparison_controls else None}


def install_export_menu(window):
    menu = window.menuBar().addMenu("导出(&E)")
    window.export_actions = {}
    for mode, title in TITLES.items():
        action = QAction(title + "…", window)
        action.triggered.connect(lambda checked=False, mode=mode: ExportDialog(window, mode).exec_())
        menu.addAction(action)
        window.export_actions[mode] = action
    def refresh():
        idle = window._statistics_worker is None and not window._closing and (
            window._comparison_controls is None or window._comparison_controls.worker is None)
        idle = idle and not (window._task_controls and window._task_controls.busy())
        available = results(window)
        for mode, action in window.export_actions.items():
            has_data = bool(window.map_canvas.layers()) if mode == "map" else (
                any(isinstance(layer, QgsRasterLayer) and layer.isValid() for layer in window._managed_layers.values())
                if mode == "raster" else any(result is not None for result in available.values()))
            action.setEnabled(idle and has_data)
            action.setToolTip("" if idle and has_data else "没有可导出的数据，或分析任务尚未完成。")
    menu.aboutToShow.connect(refresh)
    refresh()


class ExportDialog(QDialog):
    def __init__(self, window, mode):
        super().__init__(window)
        self.window, self.mode = window, mode
        self.worker = None
        self.map_running = self.cancelled = False
        self.output = None
        self.setWindowTitle(TITLES[mode])
        self.resize(640, 460)
        layout = QVBoxLayout(self)
        self.fields = QFormLayout()
        self.choice = QComboBox(self)
        self.items = {}
        available = results(window)
        if mode == "raster":
            for layer in window._managed_layers.values():
                if isinstance(layer, QgsRasterLayer) and layer.isValid():
                    self.choice.addItem(layer.name(), layer.id())
                    self.items[layer.id()] = layer
            if window._active_raster_layer:
                self.choice.setCurrentIndex(max(0, self.choice.findData(window._active_raster_layer.id())))
        elif mode in ("csv", "chart"):
            choices = [("profile", "F08 地形 / 海底剖面"), ("statistics", "F09 高程统计")]
            choices += [("comparison", "F10 区域对比")] if mode == "csv" else [("distribution", "F10 高程分布对比"), ("area", "F10 分级面积对比")]
            for key, label in choices:
                result = available["comparison" if key in ("distribution", "area") else key]
                if result is not None:
                    self.choice.addItem(label, key)
                    self.items[key] = deepcopy(result)
        else:
            self.choice.addItem("当前地图范围与可见图层", "map")
        self.fields.addRow("导出对象", self.choice)
        self.source_label = QLabel(self)
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fields.addRow("来源", self.source_label)
        self.directory = QLineEdit(str(Path.cwd() / "outputs") if (Path.cwd() / "outputs").is_dir() else str(Path.cwd()), self)
        self.browse_button = QPushButton("选择目录…", self)
        self.browse_button.clicked.connect(self.browse)
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory)
        directory_row.addWidget(self.browse_button)
        self.fields.addRow("输出目录", directory_row)
        self.name = QLineEdit(f"ETP_{mode.upper()}_{datetime.now():%Y%m%d_%H%M%S}", self)
        self.fields.addRow("成果文件夹名称", self.name)
        self.title = QLineEdit("ETOPO 地形分析地图", self)
        self.title.setMaxLength(80)
        self.pixels, self.dpi = QSpinBox(self), QSpinBox(self)
        self.pixels.setRange(1200, 6000)
        self.pixels.setValue(2400)
        self.dpi.setRange(72, 600)
        self.dpi.setValue(300)
        self.include_profile = QCheckBox("包含已完成剖面线和 A/B 端点", self)
        self.include_profile.setEnabled(window._profile_result is not None)
        if mode == "map":
            self.fields.addRow("标题", self.title)
            self.fields.addRow(self.include_profile)
        if mode in ("map", "chart"):
            self.fields.addRow("图片宽度（像素）", self.pixels)
            self.fields.addRow("印刷分辨率（DPI）", self.dpi)
        else:
            self.pixels.hide()
            self.dpi.hide()
        if mode != "map":
            self.title.hide()
            self.include_profile.hide()
        layout.addLayout(self.fields)
        self.message = QLabel("每次生成独立成果目录和 manifest.json；同名成果不会被覆盖。", self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.progress = QProgressBar(self)
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("开始导出", self)
        self.cancel_button = QPushButton("关闭", self)
        self.open_button = QPushButton("打开输出文件夹", self)
        self.open_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.reject)
        self.open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.output)))
        for button in (self.start_button, self.open_button, self.cancel_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.choice.currentIndexChanged.connect(self.update_source)
        self.update_source()

    def browse(self):
        selected = QFileDialog.getExistingDirectory(self, "选择输出目录", self.directory.text())
        if selected:
            self.directory.setText(selected)

    def update_source(self):
        key = self.choice.currentData()
        if self.mode == "raster" and key is not None:
            layer = self.items[key]
            from osgeo import gdal
            try:
                ds = gdal.Open(layer.source())
            except RuntimeError:
                ds = None
            unit = ds.GetRasterBand(1).GetUnitType() if ds else "未知"
            dtype = gdal.GetDataTypeName(ds.GetRasterBand(1).DataType) if ds else "未知"
            ds = None
            self.source_label.setText(f"{layer.source()}\n{layer.width()} × {layer.height()}；{layer.crs().authid()}；"
                                      f"类型 {dtype}；单位 {unit or '未声明'}\n导出完整栅格范围；局部范围请先裁剪。")
        elif self.mode == "map":
            self.source_label.setText("\n".join(layer.name() for layer in self.window.map_canvas.layers()))
        elif key is not None:
            result = self.items[key]
            paths = [r["raster_path"] for r in result["regions"].values()] if "regions" in result else [result["raster_path"]]
            self.source_label.setText("\n".join(paths))
        self.start_button.setEnabled(key is not None)

    def set_busy(self, busy):
        for widget in (self.choice, self.directory, self.browse_button, self.name, self.title, self.pixels, self.dpi, self.include_profile, self.start_button):
            widget.setEnabled(not busy)
        self.include_profile.setEnabled(not busy and self.window._profile_result is not None)
        self.cancel_button.setText("取消导出" if busy else "关闭")

    def start(self):
        if self.worker is not None or self.map_running:
            return
        self.output = None
        self.open_button.setEnabled(False)
        self.cancelled = False
        self.progress.setValue(0)
        try:
            key = self.choice.currentData()
            metadata = {"label": self.choice.currentText()}
            result = None
            if self.mode == "raster":
                metadata["processing"] = layer_processing(self.items[key])
                key = self.items[key].source()
                sources = [file_signature(key)]
            elif self.mode == "map":
                sources = []
                for layer in self.window.map_canvas.layers():
                    path = layer.source().split("|")[0]
                    sources.append(file_signature(path))
                profile = deepcopy(self.window._profile_result) if self.include_profile.isChecked() else None
                if profile:
                    sources.extend(result_sources(profile))
            else:
                result = deepcopy(self.items[key])
                sources = result_sources(result)
                metadata.update(result_metadata(result))
                metadata.update(pixels=self.pixels.value(), dpi=self.dpi.value())
            validate_sources(sources)
            self.set_busy(True)
            self.message.setText("正在导出，关闭窗口将请求取消。")
            if self.mode == "map":
                from etopo_analyzer.visualization.map_export import export_map
                self.map_running = True
                try:
                    with export_package(self.directory.text(), self.name.text(), "map", sources, metadata,
                                        lambda: self.cancelled) as folder:
                        metadata.update(export_map(folder, self.window.map_canvas, self.title.text(),
                            self.pixels.value(), self.dpi.value(), profile, lambda: self.cancelled, self.progress.setValue))
                    self.succeeded(str(Path(self.directory.text()) / self.name.text()))
                finally:
                    self.map_running = False
                    self.set_busy(False)
            else:
                self.worker = ExportWorker(self.directory.text(), self.name.text(), self.mode, key, result,
                    sources, metadata, self.pixels.value(), self.dpi.value(), self)
                self.worker.progress.connect(self.progress.setValue)
                self.worker.succeeded.connect(self.succeeded)
                self.worker.failed.connect(self.message.setText)
                self.worker.finished.connect(self.finished)
                self.worker.start()
        except Exception as exc:
            self.message.setText(str(exc))
            self.set_busy(False)

    def succeeded(self, path):
        self.output = path
        self.progress.setValue(100)
        self.message.setText(f"导出完成：{path}")
        self.open_button.setEnabled(True)

    def finished(self):
        self.worker.wait()
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)

    def reject(self):
        if self.worker is not None or self.map_running:
            self.cancelled = True
            if self.worker is not None:
                self.worker.requestInterruption()
            self.message.setText("已请求取消，正在清理临时成果……")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None or self.map_running:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
