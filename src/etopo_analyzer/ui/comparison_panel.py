"""F10 四个结果标签页，只呈现核心已算好的数据。"""

from pathlib import Path
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from etopo_analyzer.visualization.comparison_plot import create_distribution_figure, create_area_comparison_figure, class_label


def _table(headers, rows):
    table = QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(False)
    table.horizontalHeader().setMinimumSectionSize(105)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            if c > 0:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(r, c, item)
    return table


class ComparisonPanel(QWidget):
    def __init__(self, result, parent=None):
        # 图表失败时不构造部分结果控件。
        figures = [create_distribution_figure(result), create_area_comparison_figure(result)]
        super().__init__(parent)
        self.canvases = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        a, b = [result["regions"][key] for key in ("a", "b")]
        label = QLabel(f"A：{Path(a['raster_path']).name}    B：{Path(b['raster_path']).name}    差值方向：B−A")
        label.setToolTip(f"A：{a['raster_path']}\nB：{b['raster_path']}")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)
        rows = []
        for key, title in (("valid_count", "有效像元数"), ("invalid_count", "无效像元数"),
                           ("min_m", "最小高程（m）"), ("max_m", "最大高程（m）"),
                           ("mean_m", "平均高程（m，像元等权）"), ("std_m", "总体标准差（m）")):
            fmt = ",.0f" if key.endswith("count") else ",.6f"
            rows.append((title, format(a["statistics"][key], fmt), format(b["statistics"][key], fmt),
                         format(result["differences"][key], "+" + fmt)))
        rows.append(("有效面积（km²）", f"{a['area']['valid_m2']/1e6:,.6f}", f"{b['area']['valid_m2']/1e6:,.6f}",
                     f"{result['differences']['valid_area_m2']/1e6:+,.6f}"))
        for key, title in (("valid_coverage_fraction", "有效面积覆盖率"), ("negative_fraction", "负高程面积占比")):
            rows.append((title, f"{a['area'][key]:.4%}", f"{b['area'][key]:.4%}",
                         f"{result['differences'][key.replace('fraction', 'pp')]:+.4f} 百分点"))
        self.summary_table = _table(["指标", "区域 A", "区域 B", "B−A"], rows)
        self.tabs.addTab(self.summary_table, "基本统计对比")
        for index, figure in enumerate(figures):
            canvas = FigureCanvasQTAgg(figure)
            # 面积图的区间标签较长，保留足够绘图区高度。
            canvas.setMinimumSize(320, 320 if index == 1 else 240)
            self.canvases.append(canvas)
        self.tabs.addTab(self.canvases[0], "高程分布对比")
        rows = [(f"{i+1}. {class_label(c)}", f"{c['a']['area_m2']/1e6:,.6f}", f"{c['b']['area_m2']/1e6:,.6f}",
                 f"{c['a']['area_fraction']:.4%}", f"{c['b']['area_fraction']:.4%}", f"{c['area_difference_pp']:+.4f}")
                for i, c in enumerate(result["classes"])]
        self.area_table = _table(["高程区间（m）", "A 面积（km²）", "B 面积（km²）", "A 面积占比", "B 面积占比", "B−A（百分点）"], rows)
        self.tabs.addTab(self.area_table, "分级面积表")
        self.tabs.addTab(self.canvases[1], "分级面积占比图")
        hint = QLabel("分布使用有效像元占比；分级使用有效面积占比。两区分别归一化；负高程不等同于真实海洋。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def clear(self):
        for canvas in self.canvases:
            canvas.figure.clear()
