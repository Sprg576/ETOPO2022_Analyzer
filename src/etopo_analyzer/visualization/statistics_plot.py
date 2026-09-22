"""F09 直方图，仅使用已经完成的统计结果。"""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties


def create_statistics_figure(result):
    edges = np.asarray(result["histogram"]["bin_edges_m"], dtype=float)
    counts = np.asarray(result["histogram"]["counts"], dtype=np.int64)
    percent = result.get("histogram_mode") == "percent"
    if len(edges) != len(counts) + 1 or not len(counts) or not np.all(np.diff(edges) > 0):
        raise ValueError("直方图边界和数量不匹配。")
    # 明确区分标题、轴标签和刻度字号，保持与统计表的阅读尺度协调。
    font = FontProperties(family=["Microsoft YaHei", "SimHei", "DejaVu Sans"], size=14)
    title_font = font.copy()
    title_font.set_size(16)
    figure = Figure(figsize=(8, 2.8), dpi=100, layout="constrained")
    axes = figure.add_subplot(111)
    values = counts / result["statistics"]["valid_count"] * 100 if percent else counts
    axes.bar(edges[:-1], values, width=np.diff(edges), align="edge",
             color="#3B79B7", edgecolor="white", linewidth=0.3)
    axes.set_xlabel("高程（m）", fontproperties=font, labelpad=8)
    axes.set_ylabel("有效像元占比（%）" if percent else "有效像元数", fontproperties=font, labelpad=8)
    axes.set_title("活动 DEM 全范围高程直方图", fontproperties=title_font, pad=10)
    axes.tick_params(axis="both", labelsize=12)
    axes.set_xlim(edges[0], edges[-1])
    axes.set_axisbelow(True)
    axes.grid(axis="y", color="#E4E7EC", linewidth=0.6)
    return figure
