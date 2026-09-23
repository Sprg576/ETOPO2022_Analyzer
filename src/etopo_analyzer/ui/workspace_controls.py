"""工作状态保存/恢复与可复核成果历史。"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QAction, QFileDialog, QMessageBox, QDialog, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QPushButton, QLabel, QTextEdit)
from qgis.core import (QgsProject, QgsRasterLayer, QgsVectorLayer, QgsMapLayerStyle,
    QgsCoordinateReferenceSystem, QgsRectangle)
from etopo_analyzer.core.workspace_state import FORMAT, VERSION, read_state, write_state
from etopo_analyzer.core.export_service import file_signature, validate_sources, result_sources, layer_processing


PARAMETERS = ("hillshade_azimuth_spin", "hillshade_altitude_spin", "contour_interval_spin",
              "contour_base_spin", "profile_interval_spin", "statistics_bins_spin")
REFERENCES = ("_display_raster_layer", "_hillshade_layer", "_slope_layer", "_aspect_layer", "_contour_layer")
KIND_NAMES = {"layer": "图层成果", "export": "导出成果", "profile": "剖面", "statistics": "统计", "comparison": "区域对比"}


class WorkspaceControls:
    def __init__(self, window):
        self.window = window
        self.path = None
        self.history = []
        self.restoring = False
        menu = window._file_menu
        self.open_action = QAction("打开工作状态…", window)
        self.save_action = QAction("保存工作状态", window)
        self.save_as_action = QAction("工作状态另存为…", window)
        self.history_action = QAction("成果历史…", window)
        self.open_action.triggered.connect(self.open_dialog)
        self.save_action.triggered.connect(self.save_dialog)
        self.save_as_action.triggered.connect(lambda: self.save_dialog(True))
        self.history_action.triggered.connect(self.show_history)
        for action in (self.open_action, self.save_action, self.save_as_action, self.history_action):
            menu.insertAction(window.exit_action, action)
        menu.aboutToShow.connect(self.refresh)
        self.mark_clean()

    def snapshot(self):
        state = self.capture()
        # 浏览位置、当前页签与选择不视为成果修改。
        for key in ("saved_at", "view", "selected", "visible_result"):
            state.pop(key, None)
        return state

    def mark_clean(self):
        self._saved_snapshot = self.snapshot()

    def is_dirty(self):
        try:
            return self.snapshot() != self._saved_snapshot
        except (OSError, ValueError, RuntimeError):
            # 源文件被移走时仍须允许用户取消关闭。
            return True

    def ask_unsaved(self):
        box = QMessageBox(QMessageBox.Question, "尚有未保存的工作",
            "图层、参数或分析成果已修改。是否保存工作状态？\n工作状态保存引用与设置，不复制源数据。", parent=self.window)
        save = box.addButton("保存", QMessageBox.AcceptRole)
        discard = box.addButton("不保存", QMessageBox.DestructiveRole)
        cancel = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec_()
        return QMessageBox.Save if box.clickedButton() is save else (
            QMessageBox.Discard if box.clickedButton() is discard else QMessageBox.Cancel)

    def confirm_discard(self):
        if not self.is_dirty():
            return True
        choice = self.ask_unsaved()
        return self.save_dialog() if choice == QMessageBox.Save else choice == QMessageBox.Discard

    def refresh(self):
        idle = not self.window._task_controls.busy() and not self.window._closing
        for action in (self.open_action, self.save_action, self.save_as_action, self.history_action):
            action.setEnabled(idle)

    def require_idle(self):
        if self.window._task_controls.busy() or self.window._closing:
            raise RuntimeError("请等待当前任务完成或取消后，再操作工作状态。")

    def record(self, kind, label, sources, files=(), result=None, parameters=None):
        if self.restoring:
            return
        self.history.append({"id": str(uuid4()), "kind": kind, "label": label,
            "time": datetime.now(timezone.utc).isoformat(), "sources": deepcopy(sources),
            "files": [file_signature(path) for path in files], "result": deepcopy(result),
            "parameters": deepcopy(parameters or {})})

    def record_layer(self, layer):
        raw = layer.customProperty("etopo/export_processing", "")
        if raw:
            processing = json.loads(raw)
            style = QgsMapLayerStyle()
            style.readFromLayer(layer)
            self.record("layer", layer.name(), [processing["input"]], [layer.source().split("|")[0]],
                        parameters={"processing": processing, "source": layer.source(),
                                    "vector": isinstance(layer, QgsVectorLayer), "style": style.xmlData()})

    def record_result(self, kind, result):
        parameters = dict(result.get("parameters", {}))
        if kind == "profile":
            parameters["sample_interval_m"] = result["sample_interval_m"]
        self.record(kind, {"profile": "地形 / 海底剖面", "statistics": "区域统计", "comparison": "区域对比"}[kind],
                    result_sources(result), result=result, parameters=parameters)

    def capture(self):
        w = self.window
        records = []
        for key, layer in w._managed_layers.items():
            style = QgsMapLayerStyle()
            style.readFromLayer(layer)
            records.append({"id": key, "source": layer.source(), "name": layer.name(),
                "type": "raster" if isinstance(layer, QgsRasterLayer) else "vector",
                "group": w._layer_items[key].parent().text(0), "style": style.xmlData(),
                "signature": file_signature(layer.source().split("|")[0]),
                "processing": layer.customProperty("etopo/export_processing", "")})
        bounds = w.map_canvas.extent()
        parameters = {key: getattr(w, key).value() for key in PARAMETERS}
        parameters.update(statistics_thresholds=w.statistics_thresholds_edit.text(),
            comparison_bins=w._comparison_controls.bins.value(),
            comparison_thresholds=w._comparison_controls.thresholds.text(),
            a=w._comparison_controls.region_a.currentData(), b=w._comparison_controls.region_b.currentData(),
            clip_source=w.clip_controls.source.currentData(), clip_bounds=w.clip_controls.bounds(),
            clip_activate=w.clip_controls.activate_result.isChecked())
        visible_result = next((key for key, dock in (("profile", w._profile_dock),
            ("statistics", w._statistics_dock), ("comparison", w._comparison_controls.dock))
            if dock is not None and not dock.isHidden()), None)
        return {"format": FORMAT, "version": VERSION, "saved_at": datetime.now(timezone.utc).isoformat(),
            "layers": records, "active": w._active_raster_layer.id() if w._active_raster_layer else None,
            "order": list(w.layer_order_controls.order), "visible": [layer.id() for layer in w.map_canvas.layers()],
            "selected": w.layer_tree.currentItem().data(0, Qt.UserRole) if w.layer_tree.currentItem() else None,
            "view": {"crs": w.map_canvas.mapSettings().destinationCrs().toWkt(),
                     "extent": [bounds.xMinimum(), bounds.yMinimum(), bounds.xMaximum(), bounds.yMaximum()],
                     "rotation": w.map_canvas.rotation()}, "parameters": parameters,
            "results": deepcopy({"profile": w._profile_result, "statistics": w._statistics_result,
                                 "comparison": w._comparison_controls.result}),
            "visible_result": visible_result, "history": deepcopy(self.history),
            "roi": w.polygon_controls.capture()}


    def save(self, path):
        self.require_idle()
        state = self.capture()
        state["references"] = {key: getattr(self.window, key).id() if getattr(self.window, key) is not None else None
                               for key in REFERENCES}
        write_state(path, state)
        self.path = str(Path(path).resolve())
        self.mark_clean()
        self.window.statusBar().showMessage(f"工作状态已保存：{self.path}")

    def save_dialog(self, save_as=False):
        path = None if save_as else self.path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self.window, "保存工作状态", self.path or "工作状态.etopo.json", "ETOPO 工作状态 (*.etopo.json)")
        if not path:
            return False
        if not path.endswith(".etopo.json"):
            path += ".etopo.json"
        try:
            self.save(path)
        except Exception as exc:
            QMessageBox.warning(self.window, "保存失败", str(exc))
            return False
        return True

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self.window, "打开工作状态", self.path or "", "ETOPO 工作状态 (*.etopo.json)")
        if not path:
            return
        try:
            warnings = self.load(path, confirm=True)
            if warnings:
                QMessageBox.warning(self.window, "工作状态已恢复，部分内容不可用", "\n".join(warnings))
        except Exception as exc:
            QMessageBox.warning(self.window, "打开失败", str(exc))

    def load(self, path, confirm=False):
        self.require_idle()
        state = read_state(path)
        # 先检查并构造独立图层，损坏文件不清空当前工作。
        prepared, warnings = {}, []
        for record in state["layers"]:
            try:
                validate_sources([record["signature"]])
                if record.get("processing"):
                    processing = json.loads(record["processing"])
                    validate_sources([processing["input"]])
                layer = (QgsRasterLayer(record["source"], record["name"], "gdal") if record["type"] == "raster"
                         else QgsVectorLayer(record["source"], record["name"], "ogr"))
                if not layer.isValid():
                    raise ValueError("图层无法读取。")
                style = QgsMapLayerStyle(record["style"])
                if not style.isValid():
                    raise ValueError("图层样式无效。")
                style.writeToLayer(layer)
                layer.setCustomProperty("etopo/export_processing", record.get("processing", ""))
                prepared[record["id"]] = layer
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                warnings.append(f"跳过图层 {record['name']}：{exc}")
        if state["layers"] and not prepared:
            raise ValueError("所有数据源均缺失或已变化；保留当前工作状态。\n" + "\n".join(warnings))
        crs = QgsCoordinateReferenceSystem(state["view"]["crs"])
        if state["layers"] and not crs.isValid():
            raise ValueError("保存的地图坐标系无效。")
        if confirm:
            if not self.confirm_discard():
                return []
            # 保存可能刚刚改写同一个目标文件，重新读取最新内容。
            return self.load(path)
        self.restoring = True
        try:
            self.apply(state, prepared, warnings)
            self.path = str(Path(path).resolve())
        finally:
            self.restoring = False
        self.mark_clean()
        self.window.statusBar().showMessage(f"工作状态已恢复：{self.path}；{len(warnings)} 项提示。")
        return warnings

    def apply(self, state, prepared, warnings):
        w = self.window
        from .layer_context_menu import remove_layer, set_visible_layers
        w.map_canvas.stopRendering()
        for layer in list(w._managed_layers.values()):
            remove_layer(w, layer)
        w._clear_profile()
        w._invalidate_statistics("工作状态已切换。")
        w._comparison_controls.invalidate("工作状态已切换。")
        for record in state["layers"]:
            layer = prepared.get(record["id"])
            if layer is not None:
                QgsProject.instance().addMapLayer(layer)
                w._register_layer(layer, record["group"])
        active = prepared.get(state["active"])
        if active is not None:
            w.show_layer(active, w._layer_items[active.id()].parent().text(0))
        p = state["parameters"]
        for key in PARAMETERS:
            if key in p:
                getattr(w, key).setValue(p[key])
        w.statistics_thresholds_edit.setText(p.get("statistics_thresholds", w.statistics_thresholds_edit.text()))
        c = w._comparison_controls
        c.bins.setValue(p.get("comparison_bins", 50))
        c.thresholds.setText(p.get("comparison_thresholds", c.thresholds.text()))
        for combo, key in ((c.region_a, "a"), (c.region_b, "b"), (w.clip_controls.source, "clip_source")):
            layer = prepared.get(p.get(key))
            combo.setCurrentIndex(combo.findData(layer.id()) if layer else -1)
        for key, value in p.get("clip_bounds", {}).items():
            w.clip_controls.coordinates[key].setValue(value)
        w.clip_controls.activate_result.setChecked(p.get("clip_activate", True))
        w.polygon_controls.restore(state.get("roi", {}))
        for kind, result in state["results"].items():
            if result is not None:
                try:
                    self.restore_result(kind, result, switch_source=False)
                except Exception as exc:
                    warnings.append(f"未恢复 {kind} 结果：{exc}")
        for dock in (w._profile_dock, w._statistics_dock, c.dock):
            if dock:
                dock.hide()
        visible = state.get("visible_result")
        if visible == "profile" and w._profile_result is not None:
            w.show_profile()
        elif visible == "statistics":
            w.show_statistics()
        elif visible == "comparison" and c.result is not None:
            c.show_result()
        w.layer_order_controls.order = [prepared[key].id() for key in state["order"] if key in prepared]
        set_visible_layers(w, [prepared[key] for key in state["visible"] if key in prepared])
        for key in REFERENCES:
            setattr(w, key, prepared.get(state.get("references", {}).get(key)))
        w.map_canvas.setDestinationCrs(QgsCoordinateReferenceSystem(state["view"]["crs"]))
        w.map_canvas.setRotation(state["view"].get("rotation", 0))
        w.map_canvas.setExtent(QgsRectangle(*state["view"]["extent"]))
        selected = prepared.get(state.get("selected"))
        if selected:
            w.layer_tree.setCurrentItem(w._layer_items[selected.id()])
        w.map_canvas.refresh()
        self.history = deepcopy(state["history"])
        w._task_controls.refresh()

    def restore_result(self, kind, result, switch_source=True):
        w = self.window
        validate_sources(result_sources(result))
        def find(path):
            return next((layer for layer in w._managed_layers.values()
                         if str(Path(layer.source()).resolve()) == str(Path(path).resolve()) and
                         w._layer_items[layer.id()].parent().text(0) in ("源数据", "裁剪结果")), None)
        result = deepcopy(result)
        if kind in ("profile", "statistics"):
            layer = find(result["raster_path"])
            if layer is None or (not switch_source and layer is not w._active_raster_layer):
                raise ValueError("结果对应的分析源未加载或与当前分析源不一致。")
            if layer is not w._active_raster_layer:
                w.show_layer(layer, w._layer_items[layer.id()].parent().text(0))
            if kind == "profile":
                w.profile_interval_spin.setValue(result["sample_interval_m"] / 1000)
                w._publish_profile(result)
                if w._profile_result is not result:
                    raise ValueError("剖面无法恢复。")
            else:
                if switch_source:
                    w.statistics_bins_spin.setValue(result["parameters"]["requested_bin_count"])
                    w.statistics_thresholds_edit.setText(", ".join(map(str, result["parameters"]["thresholds_m"])))
                if switch_source:
                    w.polygon_controls.restore_result("statistics", result)
                elif w.polygon_controls.roi("statistics") != result["parameters"].get("roi"):
                    raise ValueError("保存的统计多边形与结果范围不一致。")
                w._statistics_succeeded(w._statistics_task_id, result)
                if w._statistics_result is not result:
                    raise ValueError("统计结果无法恢复。")
        elif kind == "comparison":
            c = w._comparison_controls
            if switch_source:
                c.bins.setValue(result["parameters"]["requested_bin_count"])
                c.thresholds.setText(", ".join(map(str, result["parameters"]["thresholds_m"])))
                for key, combo in (("a", c.region_a), ("b", c.region_b)):
                    layer = find(result["regions"][key]["raster_path"])
                    if layer is None:
                        raise ValueError("对比区域图层未加载。")
                    combo.setCurrentIndex(combo.findData(layer.id()))
            if switch_source:
                w.polygon_controls.restore_result("comparison", result)
            elif any(w.polygon_controls.roi(key) != result["regions"][key]["parameters"].get("roi") for key in ("a", "b")):
                raise ValueError("保存的对比多边形与结果范围不一致。")
            c.succeeded(c.task_id, result)
            if c.result is not result:
                raise ValueError("对比结果无法恢复。")
        else:
            raise ValueError("未知的历史成果类型。")

    def show_history(self):
        HistoryDialog(self).exec_()


class HistoryDialog(QDialog):
    def __init__(self, controls):
        super().__init__(controls.window)
        self.controls = controls
        self.setWindowTitle("成果历史")
        self.resize(880, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("记录随工作状态保存；恢复前会重新校验来源和成果文件。"))
        self.entries = list(reversed(controls.history))
        self.table = QTableWidget(len(self.entries), 4, self)
        self.table.setHorizontalHeaderLabels(["完成时间", "成果", "类型", "状态"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, entry in enumerate(self.entries):
            try:
                validate_sources(entry["sources"] + entry["files"])
                status = "可用"
            except (OSError, ValueError, KeyError, TypeError):
                status = "文件缺失或变化"
            for col, value in enumerate((datetime.fromisoformat(entry["time"]).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                                        entry["label"], KIND_NAMES[entry["kind"]], status)):
                self.table.setItem(row, col, QTableWidgetItem(value))
        layout.addWidget(self.table)
        self.details = QTextEdit(self)
        self.details.setReadOnly(True)
        layout.addWidget(self.details)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.restore_button = QPushButton("恢复所选成果", self)
        self.restore_button.clicked.connect(self.restore)
        layout.addWidget(self.restore_button)
        self.table.currentCellChanged.connect(self.select)
        self.select(-1, 0, -1, 0)

    def select(self, row, column, previous_row, previous_column):
        self.restore_button.setEnabled(row >= 0)
        if row >= 0:
            entry = self.entries[row]
            parameters = entry["parameters"].get("processing", {}).get("parameters", entry["parameters"])
            labels = {"requested_bin_count": "直方图分箱数", "thresholds_m": "高程分级（m）",
                      "sample_interval_m": "剖面采样间距（m）", "azimuth": "光照方位角（°）",
                      "altitude": "光照高度角（°）", "interval": "等值线间隔（m）", "base": "等值线基准（m）",
                      "requested_bounds": "裁剪范围", "width": "列数", "height": "行数",
                      "title": "标题", "pixels": "图片像素", "dpi": "印刷分辨率（DPI）"}
            text = "数据来源：\n" + "\n".join(value["path"] for value in entry["sources"])
            text += "\n\n成果文件：\n" + ("\n".join(value["path"] for value in entry["files"]) or "分析结果保存在工作状态文件中。")
            values = [f"{title}：{parameters[key]}" for key, title in labels.items() if key in parameters]
            if values:
                text += "\n\n处理参数：\n" + "\n".join(values)
            self.details.setPlainText(text)

    def restore(self):
        entry = self.entries[self.table.currentRow()]
        c, w = self.controls, self.controls.window
        try:
            c.require_idle()
            validate_sources(entry["sources"] + entry["files"])
            c.restoring = True
            if entry["kind"] == "export":
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(entry["files"][0]["path"]).parent)))
            elif entry["kind"] == "layer":
                info = entry["parameters"]
                source = info["source"]
                layer = next((layer for layer in w._managed_layers.values() if layer.source() == source), None)
                if layer is None:
                    layer = QgsVectorLayer(source, entry["label"], "ogr") if info["vector"] else QgsRasterLayer(source, entry["label"], "gdal")
                    if not layer.isValid():
                        raise ValueError("成果图层无法打开。")
                    if info.get("style"):
                        QgsMapLayerStyle(info["style"]).writeToLayer(layer)
                    layer.setCustomProperty("etopo/export_processing", json.dumps(info["processing"], ensure_ascii=False))
                    QgsProject.instance().addMapLayer(layer)
                    group = "等值线" if info["vector"] else ("裁剪结果" if info["processing"]["operation"] == "pixel_aligned_clip" else "派生栅格")
                    w._register_layer(layer, group)
                from .layer_context_menu import set_visible_layers
                set_visible_layers(w, list(dict.fromkeys([layer, *w.map_canvas.layers()])))
                w.layer_tree.setCurrentItem(w._layer_items[layer.id()])
            else:
                c.restore_result(entry["kind"], entry["result"])
            self.message.setText("成果已恢复。")
        except Exception as exc:
            self.message.setText(f"无法恢复：{exc}")
        finally:
            c.restoring = False
