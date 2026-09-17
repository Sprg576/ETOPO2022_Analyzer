"""F08 剖面 Figure；不创建 GUI，也不修改全局绘图配置。"""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties


def create_profile_figure(profile_result) -> Figure:
    """保留海底负高程，并在缺测位置断开曲线。"""
    distances = np.asarray(profile_result["distance_m"], dtype=float) / 1000.0
    elevations = np.asarray([
        np.nan if missing or elevation is None else elevation
        for elevation, missing in zip(
            profile_result["elevation_m"], profile_result["is_nodata"],
        )
    ], dtype=float)
    if len(distances) != len(elevations) or not len(distances):
        raise ValueError("剖面距离与高程数组长度不一致或为空。")
    font = FontProperties(family=["Microsoft YaHei", "SimHei", "DejaVu Sans"], size=9)
    figure = Figure(figsize=(8, 2.8), dpi=100, layout="constrained")
    axes = figure.add_subplot(111)
    axes.plot(distances, elevations, color="#294A7C", linewidth=1.2,
              marker=".", markersize=2)
    axes.axhline(0, color="#8994A3", linewidth=0.8, linestyle="--")
    axes.set_xlabel("距离（km）", fontproperties=font)
    axes.set_ylabel("高程（m）", fontproperties=font)
    axes.set_title("地形 / 海底剖面", fontproperties=font)
    axes.grid(True, color="#E4E7EC", linewidth=0.6)
    axes.set_xlim(0, max(float(distances[-1]), 1e-9))
    # A/B 标明沿线方向，即使端点缺测也保留标记。
    for distance, text, alignment in ((distances[0], "A", "left"),
                                      (distances[-1], "B", "right")):
        axes.text(distance, 0.97, text, transform=axes.get_xaxis_transform(),
                  ha=alignment, va="top", color="#C94A38")
    return figure
