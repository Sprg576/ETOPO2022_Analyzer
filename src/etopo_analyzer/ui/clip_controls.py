"""裁剪范围确认：选择来源、框选/输入同步、像元窗口预览。"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDockWidget, QWidget, QFormLayout, QComboBox,
    QDoubleSpinBox, QCheckBox, QPushButton, QLabel, QScrollArea)
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject, Qgis
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtGui import QColor
from etopo_analyzer.core.raster_clip import preview_clip


class ClipControls(QDockWidget):
    def __init__(self, window):
        super().__init__("裁剪设置", window)
        self.window = window
        self.setObjectName("ClipSettingsDock")
        body = QWidget(self)
        layout = QFormLayout(body)
        self.source = QComboBox(body)
        layout.addRow("裁剪数据源", self.source)
        self.coordinates = {}
        for key, title in (("west", "西经度"), ("south", "南纬度"), ("east", "东经度"), ("north", "北纬度")):
            spin = QDoubleSpinBox(body)
            limit = 180 if key in ("west", "east") else 90
            spin.setRange(-limit, limit)
            spin.setDecimals(7)
            spin.setSingleStep(.1)
            spin.valueChanged.connect(self.preview)
            self.coordinates[key] = spin
            layout.addRow(title + "（°）", spin)
        self.activate_result = QCheckBox("裁剪后设为分析源", body)
        self.activate_result.setChecked(True)
        layout.addRow(self.activate_result)
        self.message = QLabel("框选或输入经纬度范围后，确认并开始裁剪。", body)
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(125)
        layout.addRow(self.message)
        self.draw_button = QPushButton("在地图上框选", body)
        self.draw_button.clicked.connect(window.activate_rectangle_clip)
        layout.addRow(self.draw_button)
        self.start_button = QPushButton("确认范围并裁剪", body)
        self.start_button.clicked.connect(self.start)
        layout.addRow(self.start_button)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.setWidget(scroll)
        self.band = QgsRubberBand(window.map_canvas, Qgis.GeometryType.Polygon)
        self.band.setColor(QColor(0, 120, 215, 70))
        self.band.setWidth(2)
        self.source.currentIndexChanged.connect(self.preview)
        self.visibilityChanged.connect(self.update_outline)
        window.map_canvas.destinationCrsChanged.connect(self.update_outline)
        window.addDockWidget(Qt.RightDockWidgetArea, self)
        window.tabifyDockWidget(window.analysis_dock, self)
        self.hide()

    def refresh_sources(self):
        old = self.source.currentData()
        self.source.blockSignals(True)
        self.source.clear()
        for group in ("源数据", "裁剪结果"):
            parent = self.window._layer_groups[group]
            for i in range(parent.childCount()):
                layer_id = parent.child(i).data(0, Qt.UserRole)
                layer = self.window._managed_layers[layer_id]
                self.source.addItem(layer.name(), layer_id)
        index = self.source.findData(old)
        if index < 0 and self.window._active_raster_layer is not None:
            index = self.source.findData(self.window._active_raster_layer.id())
        self.source.setCurrentIndex(max(0, index))
        self.source.blockSignals(False)
        self.preview()

    def bounds(self):
        return {key: spin.value() for key, spin in self.coordinates.items()}

    def receive(self, bounds):
        for key, value in bounds.items():
            self.coordinates[key].blockSignals(True)
            self.coordinates[key].setValue(value)
            self.coordinates[key].blockSignals(False)
        self.show()
        self.raise_()
        self.preview()

    def preview(self, *args):
        layer = self.window._managed_layers.get(self.source.currentData())
        self.start_button.setEnabled(False)
        try:
            if layer is None:
                raise ValueError("请先加载裁剪数据源。")
            result = preview_clip(layer.source(), **self.bounds())
            crs = QgsCoordinateReferenceSystem(result["crs"])
            if crs.horizontalCrs().isValid():
                crs = crs.horizontalCrs()
            self.message.setText(f"预计 {result['height']:,} 行 × {result['width']:,} 列\n"
                f"实际边界（{crs.authid()}，{'°' if crs.isGeographic() else '源坐标单位'}）：\n"
                + "\n".join(f"{title}：{value:.7f}" for title, value in zip(("西", "南", "东", "北"), result["bounds"])))
            self.start_button.setEnabled(not self.window._task_controls.busy())
        except (OSError, ValueError, RuntimeError) as exc:
            self.message.setText(str(exc))
        self.update_outline()

    def update_outline(self, *args):
        self.band.reset(Qgis.GeometryType.Polygon)
        b = self.bounds()
        if not self.isVisible() or b["west"] >= b["east"] or b["south"] >= b["north"]:
            return
        try:
            transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                self.window.map_canvas.mapSettings().destinationCrs(), QgsProject.instance())
            points = [(b["west"], b["south"]), (b["east"], b["south"]),
                      (b["east"], b["north"]), (b["west"], b["north"]), (b["west"], b["south"])]
            for i, point in enumerate(points):
                self.band.addPoint(transform.transform(QgsPointXY(*point)), i == 4)
        except Exception:
            self.band.reset(Qgis.GeometryType.Polygon)

    def set_busy(self, busy):
        self.widget().setEnabled(not busy)
        if not busy:
            self.preview()

    def start(self):
        self.preview()
        if self.start_button.isEnabled():
            layer = self.window._managed_layers.get(self.source.currentData())
            self.window._clip_selected_bounds(self.bounds(), layer, self.activate_result.isChecked())
