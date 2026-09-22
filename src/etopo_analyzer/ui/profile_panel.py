"""F08 延迟加载的 Qt 剖面图面板。"""

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg


class ProfilePanel(QWidget):
    """替换曲线时释放旧画布，避免反复生成积累窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = None

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
        if self.canvas is not None:
            self._layout.removeWidget(self.canvas)
            self.canvas.figure.clear()
            self.canvas.deleteLater()
            self.canvas = None
