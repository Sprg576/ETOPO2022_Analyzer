"""F10 共用坐标轴的频率分布和分级面积占比图。"""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties


def _figure(title, xlabel, ylabel):
    font = FontProperties(family=["Microsoft YaHei", "SimHei", "DejaVu Sans"], size=14)
    title_font = font.copy()
    title_font.set_size(16)
    figure = Figure(figsize=(9, 3.2), dpi=100, layout="constrained")
    axes = figure.add_subplot(111)
    axes.set_title(title, fontproperties=title_font, pad=10)
    axes.set_xlabel(xlabel, fontproperties=font, labelpad=8)
    axes.set_ylabel(ylabel, fontproperties=font, labelpad=8)
    axes.tick_params(labelsize=12)
    axes.set_axisbelow(True)
    axes.grid(axis="y", color="#E4E7EC", linewidth=.6)
    return figure, axes


def class_label(item):
    lo, hi = item["lower_m"], item["upper_m"]
    if lo is None:
        return f"< {hi:g}"
    if hi is None:
        return f"≥ {lo:g}"
    return f"[{lo:g}, {hi:g})"


def create_distribution_figure(result):
    figure, axes = _figure("两区域高程分布对比", "高程（m）", "有效像元占比（%）")
    edges = result["parameters"]["bin_edges_m"]
    for key, color, style in (("a", "#347CB5", "-"), ("b", "#D77D27", "--")):
        values = np.asarray(result["regions"][key]["histogram"]["frequencies"]) * 100
        axes.stairs(values, edges, label=key.upper(), color=color, linestyle=style, linewidth=1.8)
    axes.set_xlim(edges[0], edges[-1])
    axes.set_ylim(bottom=0)
    axes.legend(fontsize=12)
    return figure


def create_area_comparison_figure(result):
    figure, axes = _figure("两区域分级面积占比", "高程区间（m）", "有效面积占比（%）")
    positions = np.arange(len(result["classes"]))
    for key, color, offset in (("a", "#347CB5", -.2), ("b", "#D77D27", .2)):
        values = [item[key]["area_fraction"] * 100 for item in result["classes"]]
        axes.bar(positions + offset, values, width=.4, color=color, label=key.upper())
    labels = [class_label(item) for item in result["classes"]]
    # 多分级时使用编号，面板中的同序表格给出完整区间，避免标签堆叠。
    if len(labels) > 12:
        labels = [str(i + 1) for i in positions]
        axes.set_xlabel("分级编号（对应面积表行序）", fontproperties=axes.xaxis.label.get_fontproperties())
    step = max(1, int(np.ceil(len(labels) / 12)))
    axes.set_xticks(positions[::step], labels[::step], rotation=45 if len(labels) <= 12 else 0,
                   ha="right" if len(labels) <= 12 else "center")
    axes.legend(fontsize=12)
    return figure
