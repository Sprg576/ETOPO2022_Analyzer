"""分类树之外提供明确的全局叠放顺序；首项位于最上层。"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QLabel, QSizePolicy
from qgis.core import QgsRasterLayer


class LayerOrderControls(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.window = window
        self.order = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        layout.addWidget(QLabel("叠放顺序（上方覆盖下方）"))
        self.list = QListWidget(self)
        self.list.setMaximumHeight(60)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        self.up = QPushButton("上移")
        self.down = QPushButton("下移")
        self.up.clicked.connect(lambda: self.move(-1))
        self.down.clicked.connect(lambda: self.move(1))
        row.addWidget(self.up)
        row.addWidget(self.down)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("不透明度"))
        self.opacity = QSpinBox(self)
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(" %")
        row.addWidget(self.opacity)
        layout.addLayout(row)
        self.list.currentItemChanged.connect(self.select)
        self.opacity.valueChanged.connect(self.set_opacity)
        window.layer_tree.currentItemChanged.connect(self.select_tree)
        window.map_canvas.layersChanged.connect(self.sync)
        self.sync()

    def sync(self):
        w = self.window
        current = self.list.currentItem()
        selected = current.data(Qt.UserRole) if current else None
        self.order = [key for key in self.order if key in w._managed_layers]
        new = [key for key in w._managed_layers if key not in self.order]
        self.order = new + self.order
        visible = [layer.id() for layer in w.map_canvas.layers() if layer.id() in self.order]
        # 分析发布可以带来新的组合；列表即时反映画布实际顺序。
        positions = [i for i, key in enumerate(self.order) if key in visible]
        for i, key in zip(positions, visible):
            self.order[i] = key
        self.list.blockSignals(True)
        self.list.clear()
        for key in self.order:
            layer = w._managed_layers[key]
            from .data_summary import short_name
            item = QListWidgetItem(short_name(layer) + ("" if key in visible else "（隐藏）"))
            item.setToolTip(layer.name() + "\n" + layer.source())
            item.setData(Qt.UserRole, key)
            self.list.addItem(item)
            if key == selected:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self.select_tree(w.layer_tree.currentItem(), None)

    def ordered(self, layers):
        rank = {key: i for i, key in enumerate(self.order)}
        return sorted(layers, key=lambda layer: rank.get(layer.id(), -1))

    def select_tree(self, item, previous):
        key = item.data(0, Qt.UserRole) if item else None
        self.list.blockSignals(True)
        self.list.setCurrentRow(self.order.index(key) if key in self.order else -1)
        self.list.blockSignals(False)
        self.update_controls(key)

    def select(self, item, previous):
        key = item.data(Qt.UserRole) if item else None
        if key in self.window._layer_items:
            self.window.layer_tree.setCurrentItem(self.window._layer_items[key])
        self.update_controls(key)

    def update_controls(self, key):
        index = self.order.index(key) if key in self.order else -1
        self.up.setEnabled(index > 0)
        self.down.setEnabled(0 <= index < len(self.order) - 1)
        layer = self.window._managed_layers.get(key)
        self.opacity.setEnabled(layer is not None)
        self.opacity.blockSignals(True)
        if layer is not None:
            value = layer.renderer().opacity() if isinstance(layer, QgsRasterLayer) else layer.opacity()
            self.opacity.setValue(round(value * 100))
        self.opacity.blockSignals(False)

    def set_opacity(self, value):
        item = self.list.currentItem()
        layer = self.window._managed_layers.get(item.data(Qt.UserRole)) if item else None
        if layer is None:
            return
        target = layer.renderer() if isinstance(layer, QgsRasterLayer) else layer
        target.setOpacity(value / 100)
        layer.triggerRepaint()
        self.window.map_canvas.refresh()

    def move(self, delta):
        index = self.list.currentRow()
        target = index + delta
        if index < 0 or not 0 <= target < len(self.order):
            return
        self.order[index], self.order[target] = self.order[target], self.order[index]
        from .layer_context_menu import set_visible_layers
        set_visible_layers(self.window, self.window.map_canvas.layers())
        self.sync()
