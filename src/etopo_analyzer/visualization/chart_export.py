"""从已完成结果建立独立 Agg 画布，不修改屏幕上的 Figure。"""

from matplotlib.backends.backend_agg import FigureCanvasAgg
from .profile_plot import create_profile_figure
from .statistics_plot import create_statistics_figure
from .comparison_plot import create_distribution_figure, create_area_comparison_figure


def export_chart(folder, kind, result, pixels=2400, dpi=300):
    factories = {"profile": create_profile_figure, "statistics": create_statistics_figure,
                 "distribution": create_distribution_figure, "area": create_area_comparison_figure}
    figure = factories[kind](result)
    try:
        FigureCanvasAgg(figure)
        # 固定版面物理尺寸，DPI 只控制输出密度，避免 300 DPI 时标签挤满图面。
        width = 10
        height = 5 if kind == "area" else 4.5
        figure.set_size_inches(width, height)
        figure.savefig(str(folder / "chart.png"), dpi=pixels / width)
        # PNG 中记录用户选择的印刷 DPI，不改变实际像素尺寸。
        from PIL import Image
        with Image.open(folder / "chart.png") as image:
            image.load()
            image.save(folder / "chart.png", dpi=(dpi, dpi))
        with Image.open(folder / "chart.png") as image:
            image.verify()
    finally:
        figure.clear()
