"""图层树常用操作；显示状态与分析数据源保持独立。"""

from pathlib import Path
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QMenu, QInputDialog, QApplication, QMessageBox
from qgis.core import QgsCoordinateTransform, QgsProject


def set_visible_layers(window, layers):
    # 显隐不改变当前地图坐标系或视野。
    layers = window.layer_order_controls.ordered(layers)
    window.map_canvas.setLayers(layers)
    window.map_canvas.refresh()
    window._sync_layer_tree_visibility()


def set_group_visibility(window, item, visible):
    group_layers = [window._managed_layers[item.child(i).data(0, Qt.UserRole)]
                    for i in range(item.childCount())]
    current = window.map_canvas.layers()
    if visible:
        layers = [layer for layer in group_layers if layer not in current] + current
    else:
        layers = [layer for layer in current if layer not in group_layers]
    set_visible_layers(window, layers)


def zoom_to_layer(window, layer):
    try:
        crs = layer.crs().horizontalCrs()
        if not crs.isValid():
            crs = layer.crs()
        transform = QgsCoordinateTransform(crs, window.map_canvas.mapSettings().destinationCrs(), QgsProject.instance())
        extent = transform.transformBoundingBox(layer.extent())
        if extent.isEmpty():
            raise ValueError("图层没有可缩放的有效范围。")
        window.map_canvas.setExtent(extent)
        window.map_canvas.refresh()
    except Exception as exc:
        window.statusBar().showMessage(f"缩放失败：{exc}")


def rename_layer(window, layer, item):
    name, accepted = QInputDialog.getText(window, "重命名图层", "图层名称", text=layer.name())
    if not accepted:
        return
    name = name.strip()
    if not name:
        window.statusBar().showMessage("图层名称不能为空。")
        return
    layer.setName(name)
    previous = window.layer_tree.blockSignals(True)
    try:
        item.setText(0, name)
    finally:
        window.layer_tree.blockSignals(previous)
    window._update_layer_properties(item, None)
    window._comparison_controls.refresh_sources()
    window.layer_order_controls.sync()
    window.clip_controls.refresh_sources()
    window.statusBar().showMessage(f"图层已重命名为：{name}")


def can_remove(window):
    return not window._task_controls.busy() and not window._closing


def remove_layer(window, layer, from_project=False):
    if not from_project and not can_remove(window):
        window.statusBar().showMessage("请等待当前任务完成，或取消任务后再移除图层。")
        return
    layer_id, name = layer.id(), layer.name()
    window.map_canvas.stopRendering()
    if layer is window._active_raster_layer:
        if window._task_controls.worker is not None:
            window._task_controls.cancel()
        window.map_canvas.activate_pan()
        window.pan_action.setChecked(True)
        window._invalidate_statistics("分析源已移除，请选择新的分析数据源。")
        window._clear_profile()
        window._active_raster_path = window._active_raster_layer = None
        window._point_query_tool = window._rectangle_selection_tool = None
        for action in (window.point_query_action, window.rectangle_clip_action, window.profile_action,
                       window.statistics_action, window.color_relief_action, window.hillshade_action,
                       window.slope_action, window.aspect_action, window.contour_action):
            action.setEnabled(False)
        window.analysis_source_label.setText("未选择分析数据源")
        window.analysis_source_label.setToolTip("")
        window.analysis_source_label.setAccessibleName("未选择分析数据源")
        window.analysis_crs_label.setText("--")
        window.analysis_size_label.setText("--")
        window.analysis_resolution_label.setText("--")
        window.analysis_unit_label.setText("--")
        window.longitude_status_label.setText("经度：--")
        window.latitude_status_label.setText("纬度：--")
        window.elevation_status_label.setText("高程/水深：--")
        window.resolution_status_label.setText("分辨率：--")
    for attr in ("_display_raster_layer", "_hillshade_layer", "_slope_layer", "_aspect_layer", "_contour_layer"):
        if getattr(window, attr) is layer:
            setattr(window, attr, None)
    if window._display_raster_layer is None:
        window.color_relief_action.setEnabled(False)
    remaining = [value for value in window.map_canvas.layers() if value.id() != layer_id]
    item = window._layer_items.pop(layer_id)
    window._managed_layers.pop(layer_id)
    window.layer_order_controls.sync()
    previous = window.layer_tree.blockSignals(True)
    try:
        item.parent().removeChild(item)
    finally:
        window.layer_tree.blockSignals(previous)
    set_visible_layers(window, remaining)
    if not from_project:
        QgsProject.instance().removeMapLayer(layer_id)
    window._comparison_controls.refresh_sources()
    window._update_analysis_source_action()
    window._update_style_action()
    window._update_layer_properties(window.layer_tree.currentItem(), None)
    window.statusBar().showMessage(f"已移除图层：{name}；磁盘文件保留。")
    window.clip_controls.refresh_sources()


def show_properties(window):
    table = window.layer_properties_table
    text = "\n".join(f"{table.item(row, 0).text()}：{table.item(row, 1).text()}"
                     for row in range(table.rowCount()))
    dialog = QMessageBox(window)
    dialog.setWindowTitle("图层属性")
    dialog.setTextFormat(Qt.PlainText)
    dialog.setText(text)
    dialog.exec_()


def build_layer_menu(window, item):
    menu = QMenu(window.layer_tree)
    layer = window._managed_layers.get(item.data(0, Qt.UserRole))
    if layer is None:
        if item in window._layer_groups.values():
            menu.addAction("显示本组图层", lambda: set_group_visibility(window, item, True))
            menu.addAction("隐藏本组图层", lambda: set_group_visibility(window, item, False))
            menu.addSeparator()
            menu.addAction("展开本组", lambda: item.setExpanded(True))
            menu.addAction("折叠本组", lambda: item.setExpanded(False))
        return menu
    visible = layer in window.map_canvas.layers()
    menu.addAction("缩放至图层", lambda: zoom_to_layer(window, layer))
    menu.addAction("隐藏图层" if visible else "显示图层",
                   lambda: set_visible_layers(window, [value for value in window.map_canvas.layers() if value is not layer]
                                              if visible else [layer, *window.map_canvas.layers()]))
    menu.addAction("仅显示此图层", lambda: set_visible_layers(window, [layer]))
    menu.addSeparator()
    menu.addAction(window.set_analysis_source_action)
    menu.addAction("重命名图层…", lambda: rename_layer(window, layer, item))
    menu.addAction("查看图层属性…", lambda: show_properties(window))
    menu.addSeparator()
    source = layer.source().split("|")[0]
    menu.addAction("复制数据源路径", lambda: QApplication.clipboard().setText(source))
    folder = Path(source).parent
    open_action = menu.addAction("打开所在文件夹", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))))
    open_action.setEnabled(folder.is_dir())
    menu.addSeparator()
    action = menu.addAction("移除图层（保留文件）", lambda: remove_layer(window, layer))
    action.setEnabled(can_remove(window))
    action.setToolTip("计算任务运行期间不能移除图层。")
    return menu
