"""F10 真实数据性能验收；--global 用全球 DEM 自比较验证完整扫描。"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from etopo_analyzer.core.region_comparison import compare_regions
from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
from benchmark_f09_statistics import memory_bytes, fingerprint


def main():
    original = PROJECT_ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"
    if "--global" in sys.argv:
        paths = [original, original]
    else:
        paths = []
        for key, west, east in (("a", 120, 123), ("b", 123, 126)):
            path = PROJECT_ROOT / "outputs" / f"f10_region_{key}.tif"
            if not path.is_file():
                clip_raster_by_bounds(str(original), str(path), west=west, south=20, east=east, north=26)
            paths.append(path)
    files = {f for path in paths for f in path.parent.glob(path.name + "*")}
    before = {str(f): fingerprint(f) for f in files}
    baseline = memory_bytes()[0]
    previous = [-1]
    def progress(percent, phase):
        if percent // 10 != previous[0]:
            previous[0] = percent // 10
            print(f"{percent}% {phase} RSS={memory_bytes()[0]/2**20:.1f} MiB", flush=True)
    result = compare_regions(*map(str, paths), progress=progress)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from etopo_analyzer.visualization.comparison_plot import create_distribution_figure, create_area_comparison_figure
    for make in (create_distribution_figure, create_area_comparison_figure):
        figure = make(result)
        FigureCanvasAgg(figure).draw()
        figure.clear()
    delta = memory_bytes()[1] - baseline
    assert delta <= 256 * 2**20, f"新增峰值内存超标：{delta/2**20:.1f} MiB"
    after_files = {f for path in paths for f in path.parent.glob(path.name + "*")}
    assert before == {str(f): fingerprint(f) for f in after_files}, "来源或辅助文件发生变化"
    if "--global" in sys.argv:
        assert all(value == 0 for value in result["differences"].values())
    print(f"耗时 {result['elapsed_s']:.3f} s；新增峰值内存（含绘图）{delta/2**20:.1f} MiB")
    print("差值 B-A：", result["differences"])
    print("F10 真实数据验收通过。")


if __name__ == "__main__":
    main()
