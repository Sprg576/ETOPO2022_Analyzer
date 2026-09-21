"""F09 全球真实数据验收：耗时、内存、闭合、只读性及取消。"""

import ctypes
from ctypes import wintypes
import hashlib
import math
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from etopo_analyzer.core.raster_statistics import calculate_raster_statistics, StatisticsCancelled


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage")]


def memory_bytes():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.WorkingSetSize, counters.PeakWorkingSetSize


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    path = PROJECT_ROOT / "data/raw/ETOPO_2022_v1_60s_N90W180_surface.tif"
    before = {p.name: fingerprint(p) for p in path.parent.glob(path.name + "*")}
    baseline = memory_bytes()[0]
    last = [-1]
    def progress(percent, phase):
        if percent // 10 != last[0]:
            last[0] = percent // 10
            print(f"{percent}% {phase} RSS={memory_bytes()[0] / 2**20:.1f} MiB", flush=True)
    result = calculate_raster_statistics(str(path), progress=progress)
    # 包括首轮图表加载和渲染的内存，不启动真实桌面窗口。
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from etopo_analyzer.visualization.statistics_plot import create_statistics_figure
    figure = create_statistics_figure(result)
    FigureCanvasAgg(figure).draw()
    peak_delta = memory_bytes()[1] - baseline
    assert peak_delta <= 256 * 2**20, f"新增峰值内存超过 256 MiB：{peak_delta / 2**20:.1f}"
    stats = result["statistics"]
    assert stats["total_count"] == 21600 * 10800
    assert sum(result["histogram"]["counts"]) == stats["valid_count"]
    assert sum(c["count"] for c in result["classes"]) == stats["valid_count"]
    assert math.isclose(result["area"]["footprint_m2"], 510065621724088.5, rel_tol=1e-10)
    after = {p.name: fingerprint(p) for p in path.parent.glob(path.name + "*")}
    assert before == after, "源 DEM 或辅助文件发生变化"
    print(f"统计耗时 {result['elapsed_s']:.3f} s；新增峰值内存（含绘图）{peak_delta / 2**20:.1f} MiB")
    print(stats)
    print(result["area"])
    cancel_at = [None]
    def request_cancel(percent, phase):
        if cancel_at[0] is None:
            cancel_at[0] = time.perf_counter()
    try:
        calculate_raster_statistics(str(path), progress=request_cancel,
                                    cancelled=lambda: cancel_at[0] is not None)
        raise AssertionError("取消后不应返回结果")
    except StatisticsCancelled:
        print(f"分块边界取消响应 {(time.perf_counter() - cancel_at[0]) * 1000:.3f} ms")
    figure.clear()
    print("F09 全球数据验收通过。")


if __name__ == "__main__":
    main()
