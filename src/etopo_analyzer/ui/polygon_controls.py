"""单区域及 A/B 多边形范围，与现有 DEM 全范围模式共用计算入口。"""

from copy import deepcopy
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel, QAction
from etopo_analyzer.core.polygon_roi import normalize_polygon
from .polygon_selection_tool import PolygonOverlay, PolygonSelectionMapTool

REGION_STYLES = {"statistics": ("统计区", "#8256B0"),
                 "a": ("区域 A", "#D66B24"), "b": ("区域 B", "#237CBD")}

class PolygonControls:
    def __init__(self, window):
        self.window = window
        self.polygons = dict(statistics=None, a=None, b=None)
        self.overlays = {key: PolygonOverlay(window.map_canvas, color)
                         for key, (_, color) in REGION_STYLES.items()}
        self.tool = PolygonSelectionMapTool(window.map_canvas)
        self.tool.polygon_selected.connect(self.receive)
        self.tool.selection_failed.connect(self.message)
        self.tool.selection_cancelled.connect(self.cancel_drawing)
        self.slot = None
        self.checks, self.panels, self.labels, self.actions = {}, [], {}, []
        for group, parent, slots in (("statistics", window._statistics_controls, [("statistics", "统计区域（紫）")]),
                                    ("comparison", window._comparison_controls, [("a", "区域 A（橙）"), ("b", "区域 B（蓝）")])):
            panel = QWidget(parent)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(0, 4, 0, 4)
            check = QCheckBox("仅统计绘制的多边形" if group == "statistics" else "使用 A/B 多边形范围", panel)
            layout.addWidget(check)
            self.checks[group] = check
            for key, title in slots:
                row = QHBoxLayout()
                draw = QPushButton("绘制" if key == "statistics" else f"绘制 {key.upper()}", panel)
                clear = QPushButton("清除", panel)
                row.addWidget(draw)
                row.addWidget(clear)
                layout.addLayout(row)
                label = QLabel(f"{title}：未绘制", panel)
                label.setWordWrap(True)
                layout.addWidget(label)
                self.labels[key] = (label, title)
                draw.clicked.connect(lambda checked=False, k=key: self.start_drawing(k))
                clear.clicked.connect(lambda checked=False, k=key: self.set_polygon(k, None))
                action = QAction(f"绘制{title}多边形", window)
                action.triggered.connect(lambda checked=False, k=key: self.start_drawing(k))
                window._statistics_menu.addAction(action)
                self.actions.append(action)
            hint = QLabel("左键加点，右键完成；退格撤回，Esc 取消。", panel)
            hint.setWordWrap(True)
            hint.setToolTip("按像元中心确定范围；面积为入选整像元的椭球水平面积。排除 NoData。\n"
                            "支持 WGS84 经纬度 DEM；暂不支持跨日期变更线。A/B 可选同一 DEM，可重叠。")
            layout.addWidget(hint)
            check.toggled.connect(lambda checked, g=group: self.changed(g))
            parent.layout().insertWidget(0, panel)
            self.panels.append(panel)

    def message(self, text):
        self.window.statusBar().showMessage(text)
        if self.slot == "statistics":
            self.window.statistics_message.setText(text)
        else:
            self.window._comparison_controls.message.setText(text)

    def start_drawing(self, key):
        w = self.window
        if w._task_controls.busy() or w._closing:
            return
        if key == "statistics" and w._active_raster_path is None:
            w.statusBar().showMessage("请先加载并选择分析 DEM。")
            return
        if key != "statistics" and w._comparison_controls.selected_layers() is None:
            w.statusBar().showMessage("请先选择 A、B 的 DEM；可以选择同一份数据。")
            w._show_comparison_controls()
            return
        self.slot = key
        self.tool.deactivate()
        w.map_canvas.setMapTool(self.tool)
        self.tool.activate()
        self.message(f"正在绘制{self.labels[key][1]}：左键加点，右键或 Enter 完成，Esc 取消。")

    def cancel_drawing(self):
        self.message("已取消绘制，保留原多边形。")
        self.window.map_canvas.activate_pan()
        self.window.pan_action.setChecked(True)
        self.slot = None

    def receive(self, polygon):
        if self.slot is None:
            return
        self.set_polygon(self.slot, polygon)
        self.message("多边形已就绪，可开始统计或对比。")
        self.window.map_canvas.activate_pan()
        self.window.pan_action.setChecked(True)
        self.slot = None

    def set_polygon(self, key, polygon):
        polygon = normalize_polygon(polygon) if polygon is not None else None
        self.polygons[key] = polygon
        group = "statistics" if key == "statistics" else "comparison"
        if polygon is not None:
            self.checks[group].blockSignals(True)
            self.checks[group].setChecked(True)
            self.checks[group].blockSignals(False)
        self.changed(group)

    def changed(self, group):
        if group == "statistics":
            self.window._invalidate_statistics("统计范围已修改，请重新计算。")
        else:
            self.window._comparison_controls.invalidate("A/B 范围已修改，请重新计算。")
        self.refresh()

    def refresh(self):
        self.window.statistics_scope_hint.setText(
            "仅统计多边形内有效 DEM；按像元中心入选。" if self.checks["statistics"].isChecked()
            else "统计当前分析 DEM 全范围，与地图视野无关。")
        for key, polygon in self.polygons.items():
            enabled = self.checks["statistics" if key == "statistics" else "comparison"].isChecked()
            self.overlays[key].set_polygon(polygon if enabled else None)
            label, title = self.labels[key]
            status = f"{len(polygon['coordinates'][0]) - 1} 个顶点" if polygon else "未绘制"
            label.setText(f"{title}：{status}" + ("（未启用）" if polygon and not enabled else ""))
        self.window._comparison_controls.update_summary()

    def roi(self, key):
        group = "statistics" if key == "statistics" else "comparison"
        if not self.checks[group].isChecked():
            return None
        if self.polygons[key] is None:
            raise ValueError(f"请先绘制{self.labels[key][1]}，或取消多边形范围。")
        return deepcopy(self.polygons[key])

    def swap(self):
        self.polygons["a"], self.polygons["b"] = self.polygons["b"], self.polygons["a"]
        self.refresh()

    def set_busy(self, busy):
        for panel in self.panels:
            panel.setEnabled(not busy)
        for action in self.actions:
            action.setEnabled(not busy)
        if busy and self.window.map_canvas.mapTool() is self.tool:
            self.cancel_drawing()

    def capture(self):
        return dict(polygons=deepcopy(self.polygons), enabled={key: check.isChecked() for key, check in self.checks.items()})

    def export_regions(self):
        return [{"id": key, "name": REGION_STYLES[key][0], "color": REGION_STYLES[key][1],
                 "geometry": deepcopy(polygon)} for key, polygon in self.polygons.items()
                if polygon is not None and self.checks[
                    "statistics" if key == "statistics" else "comparison"].isChecked()]

    def restore(self, state):
        self.polygons = {key: normalize_polygon(value) if value is not None else None
                         for key, value in ((k, state.get("polygons", {}).get(k)) for k in self.polygons)}
        for group, check in self.checks.items():
            check.blockSignals(True)
            check.setChecked(state.get("enabled", {}).get(group, False))
            check.blockSignals(False)
        self.changed("statistics")
        self.changed("comparison")

    def restore_result(self, kind, result):
        keys = ["statistics"] if kind == "statistics" else ["a", "b"]
        for key in keys:
            source = result if key == "statistics" else result["regions"][key]
            polygon = source["parameters"].get("roi")
            self.polygons[key] = normalize_polygon(polygon) if polygon else None
        self.checks[kind].blockSignals(True)
        self.checks[kind].setChecked(any(self.polygons[k] is not None for k in keys))
        self.checks[kind].blockSignals(False)
        self.changed(kind)
