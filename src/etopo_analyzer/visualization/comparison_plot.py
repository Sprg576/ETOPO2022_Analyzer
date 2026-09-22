"""F10 共用坐标轴的频率分布和分级面积占比图。"""

import numpy as np
from pathlib import Path
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
        axes.stairs(values, edges, label=region_label(result, key), color=color, linestyle=style, linewidth=1.8)
    axes.set_xlim(edges[0], edges[-1])
    axes.set_ylim(bottom=0)
    axes.legend(prop=FontProperties(family=["Microsoft YaHei", "SimHei", "DejaVu Sans"], size=11))
    return figure


def create_area_comparison_figure(result):
    figure, axes = _figure("两区域分级面积占比", "高程区间（m）", "有效面积占比（%）")
    positions = np.arange(len(result["classes"]))
    horizontal = len(positions) > 12
    for key, color, offset in (("a", "#347CB5", -.2), ("b", "#D77D27", .2)):
        values = [item[key]["area_fraction"] * 100 for item in result["classes"]]
        if horizontal:
            axes.barh(positions + offset, values, height=.4, color=color, label=region_label(result, key))
        else:
            axes.bar(positions + offset, values, width=.4, color=color, label=region_label(result, key))
    labels = [class_label(item) for item in result["classes"]]
    if horizontal:
        figure.set_size_inches(10, max(5, len(labels) * .28 + 1.5))
        axes.set_yticks(positions, labels)
        axes.invert_yaxis()
        axes.set_xlabel("有效面积占比（%）", fontproperties=axes.xaxis.label.get_fontproperties())
        axes.set_ylabel("高程区间（m）", fontproperties=axes.yaxis.label.get_fontproperties())
        axes.grid(False, axis="y")
        axes.grid(axis="x", color="#E4E7EC", linewidth=.6)
    else:
        axes.set_xticks(positions, labels, rotation=45, ha="right")
    axes.legend(prop=FontProperties(family=["Microsoft YaHei", "SimHei", "DejaVu Sans"], size=11))
    return figure


def region_label(result, key):
    region = result["regions"][key]
    name = region.get("name") or Path(region.get("raster_path", "")).stem
    # 长名称分行，导出后仍能独立识别 A/B。
    return key.upper() + ("：" + "\n".join(name[i:i+28] for i in range(0, len(name), 28)) if name else "")
