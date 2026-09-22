"""F09 统计表、直方图与分级面积；首次使用时加载绘图库。"""

from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTabWidget, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QComboBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from etopo_analyzer.visualization.statistics_plot import create_statistics_figure
from .copy_table import CopyTable


def interval_label(item):
    lower, upper = item["lower_m"], item["upper_m"]
    if lower is None:
        return f"< {upper:g}"
    if upper is None:
        return f"≥ {lower:g}"
    return f"[{lower:g}, {upper:g})"


def _table(headers, rows):
    table = CopyTable(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(str(value)))
    return table


class StatisticsPanel(QWidget):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        label = QLabel(f"分析源：{result['raster_path']}")
        label.setWordWrap(True)
        label.setToolTip(result["raster_path"])
        layout.addWidget(label)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)
        stat, area = result["statistics"], result["area"]
        rows = [("统计范围", "活动 DEM 全部像元；有效像元参与统计"),
                ("计算口径", "高程单位 m；像元等权；总体标准差 ddof=0")]
        for key, title in (("total_count", "总像元数"), ("valid_count", "有效像元数"),
                           ("invalid_count", "无效像元数（含 NoData）")):
            rows.append((title, f"{stat[key]:,}"))
        for key, title in (("min_m", "最小高程（m）"), ("max_m", "最大高程（m）"),
                           ("mean_m", "平均高程（m）"), ("std_m", "总体标准差（m）")):
            rows.append((title, f"{stat[key]:.6f}"))
        for key, title in (("footprint_m2", "完整格网面积（km²）"),
                           ("valid_m2", "有效面积（km²）"), ("invalid_m2", "无效面积（km²）")):
            rows.append((title, f"{area[key] / 1e6:.6f}"))
        for item in result["sign_summary"]:
            rows.append((f"{item['label']} 像元数 / 面积（km²）",
                         f"{item['count']:,} / {item['area_m2'] / 1e6:.6f}"))
        self.summary_table = _table(["项目", "结果"], rows)
        self.tabs.addTab(self.summary_table, "基本统计")
        self.canvas = FigureCanvasQTAgg(create_statistics_figure(result))
        self.canvas.setMinimumSize(320, 220)
        chart = QWidget(self)
        chart_layout = QVBoxLayout(chart)
        self.histogram_mode = QComboBox(chart)
        self.histogram_mode.addItem("像元数", "count")
        self.histogram_mode.addItem("像元占比（%）", "percent")
        self.histogram_mode.setCurrentIndex(1 if result.get("histogram_mode") == "percent" else 0)
        chart_layout.addWidget(self.histogram_mode)
        chart_layout.addWidget(self.canvas)
        def change_mode():
            result["histogram_mode"] = self.histogram_mode.currentData()
            figure = create_statistics_figure(result)
            old = self.canvas
            self.canvas = FigureCanvasQTAgg(figure)
            self.canvas.setMinimumSize(320, 220)
            chart_layout.replaceWidget(old, self.canvas)
            old.figure.clear()
            old.deleteLater()
            self.canvas.draw_idle()
        self.histogram_mode.currentIndexChanged.connect(change_mode)
        self.tabs.addTab(chart, "高程直方图")
        class_rows = [(interval_label(c), f"{c['count']:,}", f"{c['pixel_fraction']:.4%}",
                       f"{c['area_m2'] / 1e6:.6f}", f"{c['area_fraction']:.4%}")
                      for c in result["classes"]]
        class_rows.append(("合计", f"{stat['valid_count']:,}", "100%",
                           f"{area['valid_m2'] / 1e6:.6f}", "100%"))
        self.area_table = _table(["高程区间（m）", "像元数", "像元占比", "面积（km²）", "面积占比"], class_rows)
        # 五列均分可用宽度，避免最后一列独占剩余空间。
        area_header = self.area_table.horizontalHeader()
        area_header.setStretchLastSection(False)
        area_header.setSectionResizeMode(QHeaderView.Stretch)
        self.tabs.addTab(self.area_table, "分级面积")
        hint = QLabel("面积为 WGS84 椭球水平面积；占比以有效像元为分母。负高程不等同于真实海洋。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.canvas.draw_idle()

    def clear(self):
        self.canvas.figure.clear()
