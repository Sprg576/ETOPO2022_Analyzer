"""统计与对比共用的分级预设，保存一组用户阈值。"""

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QComboBox, QPushButton, QLabel, QVBoxLayout
from etopo_analyzer.core.raster_statistics import DEFAULT_THRESHOLDS, validate_parameters


class ThresholdPresets(QWidget):
    def __init__(self, edit, parent=None):
        super().__init__(parent)
        self.edit = edit
        self.settings = QSettings("ETOPOAnalyzer", "Preferences")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.choice = QComboBox(self)
        self.choice.addItems(["默认地形分级", "陆地细分", "海底细分", "已保存的分级"])
        layout.addWidget(self.choice)
        self.apply_button = QPushButton("应用", self)
        self.save_button = QPushButton("保存", self)
        row.addWidget(self.apply_button)
        row.addWidget(self.save_button)
        layout.addLayout(row)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.apply_button.clicked.connect(self.apply)
        self.save_button.clicked.connect(self.save)

    def apply(self):
        values = [DEFAULT_THRESHOLDS, [0, 200, 500, 1000, 2000, 3000, 4000, 6000],
                  [-6000, -4000, -3000, -2000, -1000, -500, -200, 0]]
        index = self.choice.currentIndex()
        text = ", ".join(map(str, values[index])) if index < 3 else self.settings.value("statistics/thresholds", "")
        if text:
            self.edit.setText(text)
            self.message.setText("已应用分级；需要重新计算。")
        else:
            self.message.setText("尚未保存自定义分级。")

    def save(self):
        try:
            values = [float(v.strip()) for v in self.edit.text().replace("，", ",").split(",")]
            validate_parameters(50, values)
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        self.settings.setValue("statistics/thresholds", ", ".join(map(str, values)))
        self.message.setText("已保存，可在统计和区域对比中复用。")
