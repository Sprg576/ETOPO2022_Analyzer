"""F08 延迟加载的 Qt 剖面图面板。"""

from bisect import bisect_left
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg


class ProfilePanel(QWidget):
    """替换曲线时释放旧画布，避免反复生成积累窗口。"""

    sample_hovered = pyqtSignal(object)
    reverse_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = None
        self.result = None
        self.details = QLabel("在曲线上移动鼠标，查看采样点及地图位置。", self)
        self.details.setWordWrap(True)
        self._layout.addWidget(self.details)
        self.reverse_button = QPushButton("反转 A/B 并重新计算", self)
        self.reverse_button.setMaximumWidth(210)
        self.reverse_button.clicked.connect(self.reverse_requested)
        self._layout.addWidget(self.reverse_button)

    def set_result(self, result):
        self.result = result
        self.summary = (f"有效采样：{result['valid_sample_count']}/{result['sample_count']}"
                        f"（{result['valid_sample_count']/result['sample_count']:.1%}）；断线表示缺测。")
        self.details.setText(self.summary + " 在图上移动鼠标查看地图位置。")
        axes = self.canvas.figure.axes[0]
        self.cursor = axes.axvline(0, color="#C94A38", linewidth=.8, visible=False)
        self.canvas.mpl_connect("motion_notify_event", self.hover)
        self.canvas.mpl_connect("figure_leave_event", self.leave)

    def leave(self, event=None):
        self.sample_hovered.emit(None)
        if self.result is not None and self.canvas is not None:
            self.cursor.set_visible(False)
            self.details.setText(self.summary)
            self.canvas.draw_idle()

    def hover(self, event):
        if self.result is None or event.inaxes is not self.canvas.figure.axes[0] or event.xdata is None:
            self.leave()
            return
        result = self.result
        distances = result["distance_m"]
        distance = event.xdata * 1000
        index = min(bisect_left(distances, distance), len(distances) - 1)
        if index > 0 and abs(distances[index - 1] - distance) < abs(distances[index] - distance):
            index -= 1
        elevation, depth = result["elevation_m"][index], result["depth_m"][index]
        value = "缺测" if result["is_nodata"][index] else f"高程 {elevation:.2f} m"
        if depth is not None:
            value += f"；水深 {depth:.2f} m"
        lon, lat = result["longitude"][index], result["latitude"][index]
        self.details.setText(f"距离 {distances[index]/1000:.3f} km；经纬度 {lon:.6f}°, {lat:.6f}°；{value}")
        self.cursor.set_xdata([distances[index]/1000] * 2)
        self.cursor.set_visible(True)
        self.canvas.draw_idle()
        self.sample_hovered.emit((lon, lat))

    def hideEvent(self, event):
        self.leave()
        super().hideEvent(event)

    def set_figure(self, figure):
        canvas = FigureCanvasQTAgg(figure)
        canvas.setMinimumSize(320, 180)
        try:
            canvas.draw()
        except Exception:
            canvas.deleteLater()
            raise
        if self.canvas is not None:
            self._layout.removeWidget(self.canvas)
            self.canvas.figure.clear()
            self.canvas.deleteLater()
        self.canvas = canvas
        self._layout.addWidget(canvas)
        canvas.draw_idle()

    def clear(self):
        self.sample_hovered.emit(None)
        self.result = None
        if self.canvas is not None:
            self._layout.removeWidget(self.canvas)
            self.canvas.figure.clear()
            self.canvas.deleteLater()
            self.canvas = None
