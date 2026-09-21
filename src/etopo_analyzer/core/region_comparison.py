"""F10：同口径双区域统计，逐区扫描，不重采样 DEM。"""

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import math
import time

from osgeo import gdal
from pyproj import CRS

from etopo_analyzer.core.pixel_area import pixel_row_areas
from etopo_analyzer.core.raster_statistics import (
    DEFAULT_THRESHOLDS, StatisticsCancelled, validate_parameters, source_signature,
    _metre_unit, _statistics_scan, _finish_statistics_scan, histogram_edges,
)


def _source_info(path):
    """只读元数据；复合 CRS 或 NetCDF 明确元数据用于识别垂直基准。"""
    signature = source_signature(path)
    ds = band = None
    try:
        ds = gdal.Open(path, gdal.GA_ReadOnly)
        if ds is None or ds.RasterCount < 1:
            raise ValueError("区域没有可直接读取的 band 1。")
        pixel_row_areas(ds)
        band = ds.GetRasterBand(1)
        _metre_unit(ds, band)
        crs = CRS.from_wkt(ds.GetProjection())
        vertical = next((c for c in crs.sub_crs_list if c.is_vertical), None)
        if vertical is None:
            metadata = ds.GetMetadata() or {}
            code = next((v for k, v in metadata.items() if k.lower().endswith("#vert_crs_epsg")), None)
            if code is not None:
                vertical = CRS.from_user_input(code)
        if vertical is None or not vertical.is_vertical:
            raise ValueError("区域缺少可识别的垂直基准，不能进行统一口径对比。")
        gt = ds.GetGeoTransform()
        return dict(path=path, signature=signature, vertical=vertical,
                    transform=gt, width=ds.RasterXSize, height=ds.RasterYSize,
                    bounds=[gt[0], gt[3] + ds.RasterYSize * gt[5],
                            gt[0] + ds.RasterXSize * gt[1], gt[3]])
    finally:
        band = ds = None


def validate_comparison_sources(path_a, path_b):
    a, b = [_source_info(str(Path(path).resolve())) for path in (path_a, path_b)]
    if not a["vertical"].equals(b["vertical"]):
        raise ValueError("两个区域的垂直基准不同，不能直接比较高程。")
    ga, gb = a["transform"], b["transform"]
    for axis in (1, 5):
        if not math.isclose(ga[axis], gb[axis], rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("两个区域的分辨率不一致；F10 不自动重采样。")
    for origin, resolution in ((0, 1), (3, 5)):
        shift = (gb[origin] - ga[origin]) / ga[resolution]
        if not math.isclose(shift, round(shift), rel_tol=0, abs_tol=1e-6):
            raise ValueError("两个区域的像元边界未对齐到同一格网。")
    return a, b


def compare_regions(path_a, path_b, bin_count=50, thresholds=DEFAULT_THRESHOLDS,
                    *, block_size=512, progress=None, cancelled=None):
    """每区两遍读取，输出以 B−A 为方向的结构化比较结果。"""
    started = time.perf_counter()
    thresholds = validate_parameters(bin_count, thresholds)
    if isinstance(block_size, bool) or not isinstance(block_size, int) or not 1 <= block_size <= 512:
        raise ValueError("分块边长必须为 1～512 的整数。")
    def check_cancel():
        if cancelled is not None and cancelled():
            raise StatisticsCancelled("区域对比已取消。")
    check_cancel()
    sources = validate_comparison_sources(path_a, path_b)
    check_cancel()
    blocks = [math.ceil(s["width"] / block_size) * math.ceil(s["height"] / block_size) for s in sources]
    total = 2 * sum(blocks)
    completed = [0, 0]
    def report(index):
        def callback(percent, phase):
            # 扫描器每处理一块回调一次，避免整数百分比导致两区进度失真。
            completed[index] += 1
            if progress is not None:
                progress(int(100 * sum(completed) / total), f"区域 {'AB'[index]}：{phase}")
        return callback
    with ExitStack() as stack:
        scans = []
        extrema = []
        for i, source in enumerate(sources):
            scan = _statistics_scan(source["path"], bin_count, thresholds, block_size=block_size,
                                    progress=report(i), cancelled=cancelled)
            stack.callback(scan.close)
            scans.append(scan)
            extrema.append(next(scan))
        edges = histogram_edges(min(v[0] for v in extrema), max(v[1] for v in extrema), bin_count)
        results = [_finish_statistics_scan(scan, edges) for scan in scans]
    check_cancel()
    for source in sources:
        if source_signature(source["path"]) != source["signature"]:
            raise RuntimeError("对比期间区域文件发生变化，请重新计算。")
    for result, source in zip(results, sources):
        result["source"]["bounds"] = source["bounds"]
        result["source"]["vertical_crs"] = source["vertical"].to_string()
        result["parameters"]["scope"] = "selected_dem_full_extent"
        count = result["statistics"]["valid_count"]
        result["histogram"]["frequencies"] = [n / count for n in result["histogram"]["counts"]]
        result["area"]["valid_coverage_fraction"] = min(1.0, result["area"]["valid_m2"] / result["area"]["footprint_m2"])
        result["area"]["negative_fraction"] = result["sign_summary"][0]["area_m2"] / result["area"]["valid_m2"]
    a, b = results
    differences = {key: b["statistics"][key] - a["statistics"][key]
                   for key in ("total_count", "valid_count", "invalid_count", "min_m", "max_m", "mean_m", "std_m")}
    differences["valid_area_m2"] = b["area"]["valid_m2"] - a["area"]["valid_m2"]
    for key in ("valid_coverage_fraction", "negative_fraction"):
        differences[key.replace("fraction", "pp")] = 100 * (b["area"][key] - a["area"][key])
    classes = [dict(lower_m=x["lower_m"], upper_m=x["upper_m"], a=x, b=y,
                    area_difference_m2=y["area_m2"] - x["area_m2"],
                    area_difference_pp=100 * (y["area_fraction"] - x["area_fraction"]))
               for x, y in zip(a["classes"], b["classes"])]
    return dict(schema_version=1, regions=dict(a=a, b=b),
                parameters=dict(bin_edges_m=edges.tolist(), thresholds_m=thresholds.tolist(),
                                requested_bin_count=int(bin_count), difference_direction="B_minus_A",
                                distribution="valid_pixel_frequency", std_ddof=0,
                                area_method="wgs84_parallel_meridian_integral"),
                differences=differences, classes=classes,
                compatibility=dict(horizontal_crs="EPSG:4326", vertical_crs=sources[0]["vertical"].to_string(),
                                   same_resolution=True, aligned_grid=True, unit="m"),
                warnings=["负高程区不等同于真实海洋；统计兼容不代表产品版本相同。",
                          "两区分别统计，允许重叠；分布使用像元占比，分级面积使用面积占比。"],
                completed_at=datetime.now(timezone.utc).isoformat(), elapsed_s=time.perf_counter() - started)
