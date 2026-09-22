"""F11 全球 GeoTIFF 导出性能及来源只读验证。"""

from datetime import datetime
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from etopo_analyzer.core.export_service import export_package, file_signature
from etopo_analyzer.core.raster_export import export_raster
from benchmark_f09_statistics import memory_bytes, fingerprint


def main():
    source = PROJECT_ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"
    name = f"f11_global_{datetime.now():%Y%m%d_%H%M%S_%f}"
    before = fingerprint(source)
    baseline = memory_bytes()[0]
    started = time.perf_counter()
    previous = [-1]
    def progress(value):
        if value // 10 != previous[0]:
            previous[0] = value // 10
            print(f"{value}% RSS={memory_bytes()[0]/2**20:.1f} MiB", flush=True)
    metadata = {}
    with export_package(PROJECT_ROOT / "outputs", name, "raster", [file_signature(source)], metadata) as folder:
        metadata.update(export_raster(folder, source, progress=progress))
    delta = memory_bytes()[1] - baseline
    assert before == fingerprint(source), "源文件发生变化"
    print(f"耗时 {time.perf_counter()-started:.3f}s；新增峰值内存 {delta/2**20:.1f} MiB", flush=True)
    assert delta <= 256 * 2**20, "新增峰值内存超过 256 MiB"
    print(f"F11 全球 GeoTIFF 导出通过：{PROJECT_ROOT / 'outputs' / name}")


if __name__ == "__main__":
    main()
