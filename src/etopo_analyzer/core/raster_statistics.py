"""F09：固定内存、两遍扫描的只读 DEM 统计。"""

from datetime import datetime, timezone
from pathlib import Path
import math
import time

import numpy as np
from osgeo import gdal
from pyproj import CRS

from etopo_analyzer.core.pixel_area import pixel_row_areas
from etopo_analyzer.core.polygon_roi import PolygonMask


gdal.UseExceptions()

DEFAULT_THRESHOLDS = (-6000, -4000, -2000, -200, 0, 200, 1000, 2000, 4000, 6000)


class StatisticsCancelled(Exception):
    """用户取消，调用方不得发布部分结果。"""


def validate_parameters(bin_count, thresholds):
    if isinstance(bin_count, bool) or not isinstance(bin_count, (int, np.integer)) or not 1 <= bin_count <= 200:
        raise ValueError("直方图箱数必须为 1～200 的整数。")
    try:
        values = np.asarray(list(thresholds), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("分级阈值必须为数值。") from exc
    if values.ndim != 1 or not 1 <= len(values) <= 50:
        raise ValueError("请提供 1～50 个分级阈值。")
    if not np.all(np.isfinite(values)) or not np.all(np.diff(values) > 0):
        raise ValueError("分级阈值必须有限、严格递增且无重复。")
    return values


def source_signature(path):
    stat = Path(path).stat()
    return (stat.st_size, stat.st_mtime_ns)


def _metre_unit(dataset, band):
    unit = band.GetUnitType().strip().lower()
    if unit in {"m", "metre", "meter", "metres", "meters"}:
        return
    if not unit:
        crs = CRS.from_wkt(dataset.GetProjection())
        if any(axis.direction == "up" and axis.unit_name.lower() in {"metre", "meter"}
               for axis in crs.axis_info):
            return
    raise ValueError("F09 需要明确的米制高程单位；不自动转换未知或非米制单位。")


def calculate_raster_statistics(raster_path, bin_count=50, thresholds=DEFAULT_THRESHOLDS,
                                *, block_size=512, progress=None, cancelled=None, roi=None):
    """保持 F09 接口；两遍扫描使用本区域的自动箱界。"""
    scan = _statistics_scan(raster_path, bin_count, thresholds, block_size=block_size,
                            progress=progress, cancelled=cancelled, roi=roi)
    try:
        next(scan)
        return _finish_statistics_scan(scan)
    finally:
        scan.close()


def histogram_edges(minimum, maximum, bin_count):
    """生成公共或单区域箱界，常量区域使用一箱。"""
    edges = (np.array([minimum - 0.5, maximum + 0.5]) if minimum == maximum
             else np.linspace(minimum, maximum, bin_count + 1))
    if not np.all(np.isfinite(edges)) or not np.all(np.diff(edges) > 0):
        raise ValueError("直方图边界精度不足，请减少箱数或检查高程范围。")
    return edges


def _finish_statistics_scan(scan, edges=None):
    """向暂停的扫描传入箱界，取回第二遍完成后的完整结果。"""
    try:
        scan.send(edges)
    except StopIteration as finished:
        return finished.value
    raise RuntimeError("统计扫描未正确结束。")


def _statistics_scan(raster_path, bin_count=50, thresholds=DEFAULT_THRESHOLDS,
                     *, block_size=512, progress=None, cancelled=None, roi=None):
    """像元等权统计和椭球面积分级；回调不依赖 Qt。"""
    thresholds = validate_parameters(bin_count, thresholds)
    if isinstance(block_size, bool) or not isinstance(block_size, int) or not 1 <= block_size <= 512:
        raise ValueError("分块边长必须为 1～512 的整数。")
    path = str(Path(raster_path).resolve())
    signature = source_signature(path)
    started = time.perf_counter()
    dataset = band = mask_band = None

    def check_cancel():
        if cancelled is not None and cancelled():
            raise StatisticsCancelled("统计已取消。")

    try:
        check_cancel()
        dataset = gdal.Open(path, gdal.GA_ReadOnly)
        if dataset is None or dataset.RasterCount < 1:
            raise ValueError("DEM 没有可直接读取的 band 1；NetCDF 容器需先选择变量。")
        row_areas = pixel_row_areas(dataset)
        band = dataset.GetRasterBand(1)
        _metre_unit(dataset, band)
        scale = 1.0 if band.GetScale() is None else float(band.GetScale())
        offset = 0.0 if band.GetOffset() is None else float(band.GetOffset())
        if not math.isfinite(scale) or not math.isfinite(offset):
            raise ValueError("scale 和 offset 必须为有限数值。")
        nodata = band.GetNoDataValue()
        if not band.GetMaskFlags() & gdal.GMF_ALL_VALID:
            mask_band = band.GetMaskBand()
        width, height = dataset.RasterXSize, dataset.RasterYSize
        polygon_mask = PolygonMask(dataset, roi) if roi is not None else None
        x0, y0, x1, y1 = polygon_mask.window if polygon_mask else (0, 0, width, height)
        total_blocks = math.ceil((x1 - x0) / block_size) * math.ceil((y1 - y0) / block_size)
        total_count, footprint = 0, 0.0
        class_count = np.zeros(len(thresholds) + 1, dtype=np.int64)
        class_area = np.zeros(len(thresholds) + 1, dtype=np.float64)
        sign_count = np.zeros(2, dtype=np.int64)
        sign_area = np.zeros(2, dtype=np.float64)
        invalid = dict(raw_nodata_or_nonfinite=0, mask_only=0, transformed_nonfinite=0)
        count, mean, m2 = 0, 0.0, 0.0
        minimum, maximum = math.inf, -math.inf
        valid_area = 0.0
        histogram = edges = None
        second_count = 0
        for pass_index in range(2):
            block_index = 0
            for y in range(y0, y1, block_size):
                rows = min(block_size, y1 - y)
                for x in range(x0, x1, block_size):
                    check_cancel()
                    columns = min(block_size, x1 - x)
                    inside = (polygon_mask.block(x, y, columns, rows) if polygon_mask
                              else np.ones((rows, columns), dtype=bool))
                    raw = band.ReadAsArray(x, y, columns, rows)
                    if raw is None:
                        raise RuntimeError("GDAL 无法读取统计分块。")
                    raw_valid = np.isfinite(raw)
                    if nodata is not None:
                        raw_valid &= raw != nodata
                    valid = raw_valid.copy()
                    if mask_band is not None:
                        mask = mask_band.ReadAsArray(x, y, columns, rows)
                        if mask is None:
                            raise RuntimeError("GDAL 无法读取有效性掩膜。")
                        valid &= mask != 0
                        mask_band.FlushCache()
                    # 只释放本波段读取缓存，不改变进程全局 GDAL 缓存配置。
                    band.FlushCache()
                    with np.errstate(over="ignore", invalid="ignore"):
                        values = raw.astype(np.float64) * scale + offset
                    finite = np.isfinite(values)
                    if pass_index == 0:
                        total_count += int(np.count_nonzero(inside))
                        footprint += float(np.sum(row_areas[y:y + rows] * inside.sum(axis=1)))
                        invalid["raw_nodata_or_nonfinite"] += int(np.count_nonzero(inside & ~raw_valid))
                        invalid["mask_only"] += int(np.count_nonzero(inside & raw_valid & ~valid))
                        invalid["transformed_nonfinite"] += int(np.count_nonzero(inside & valid & ~finite))
                    valid &= finite & inside
                    z = values[valid]
                    if pass_index == 0 and z.size:
                        n = int(z.size)
                        block_mean = float(np.mean(z))
                        block_m2 = float(np.sum((z - block_mean) ** 2))
                        delta = block_mean - mean
                        new_count = count + n
                        m2 += block_m2 + delta * delta * count * n / new_count
                        mean += delta * n / new_count
                        count = new_count
                        minimum = min(minimum, float(z.min()))
                        maximum = max(maximum, float(z.max()))
                        weights = np.broadcast_to(row_areas[y:y + rows, None], valid.shape)[valid]
                        indexes = np.searchsorted(thresholds, z, side="right")
                        class_count += np.bincount(indexes, minlength=len(class_count))
                        class_area += np.bincount(indexes, weights=weights, minlength=len(class_count))
                        signs = (z >= 0).astype(np.int8)
                        sign_count += np.bincount(signs, minlength=2)
                        sign_area += np.bincount(signs, weights=weights, minlength=2)
                        valid_area += float(np.sum(weights))
                    elif pass_index == 1:
                        histogram += np.histogram(z, bins=edges)[0]
                        second_count += int(z.size)
                    block_index += 1
                    check_cancel()
                    if progress is not None:
                        progress(int(100 * (pass_index * total_blocks + block_index) / (2 * total_blocks)),
                                 "基础统计与分级面积" if pass_index == 0 else "高程直方图")
            if pass_index == 0:
                if count == 0:
                    if polygon_mask:
                        raise ValueError("多边形内没有有效 DEM 像元；请检查区域大小、位置及 NoData。")
                    raise ValueError("DEM 全部为 NoData 或无效值，无法统计。")
                if not all(math.isfinite(v) for v in (mean, m2)):
                    raise ValueError("高程数值过大，无法可靠计算统计量。")
                # 第一遍结束后只交出极值；F10 用双方极值生成同一组箱界。
                supplied_edges = yield minimum, maximum
                edges = (histogram_edges(minimum, maximum, bin_count) if supplied_edges is None
                         else np.asarray(supplied_edges, dtype=np.float64))
                if (edges.ndim != 1 or len(edges) < 2 or not np.all(np.isfinite(edges))
                        or not np.all(np.diff(edges) > 0) or edges[0] > minimum or edges[-1] < maximum):
                    raise ValueError("公共直方图箱界无效或未覆盖全部高程。")
                histogram = np.zeros(len(edges) - 1, dtype=np.int64)
        check_cancel()
        if source_signature(path) != signature:
            raise RuntimeError("统计期间源 DEM 发生变化，请重新计算。")
        if int(class_count.sum()) != count or int(histogram.sum()) != count or second_count != count:
            raise RuntimeError("统计像元数量未闭合，结果不予发布。")
        tolerance = max(1e-3, valid_area * 1e-10)
        if abs(float(class_area.sum()) - valid_area) > tolerance or abs(float(sign_area.sum()) - valid_area) > tolerance:
            raise RuntimeError("分级面积未闭合，结果不予发布。")
        if polygon_mask is None:
            footprint = float(np.sum(row_areas) * width)
        crs = CRS.from_wkt(dataset.GetProjection())
        classes = []
        for i, n in enumerate(class_count):
            classes.append(dict(lower_m=None if i == 0 else float(thresholds[i - 1]),
                                upper_m=None if i == len(thresholds) else float(thresholds[i]),
                                lower_inclusive=i != 0, upper_inclusive=False,
                                count=int(n), pixel_fraction=float(n / count),
                                area_m2=float(class_area[i]), area_fraction=float(class_area[i] / valid_area)))
        return dict(
            schema_version=1, raster_path=path,
            source=dict(band=1, width=width, height=height, geotransform=list(dataset.GetGeoTransform()),
                        crs_wkt=crs.to_wkt(), horizontal_crs=crs.to_2d().to_string(),
                        unit="m", size_bytes=signature[0], mtime_ns=signature[1]),
            parameters=dict(scope="polygon_pixel_centers" if polygon_mask else "active_dem_full_extent",
                            **({"roi": polygon_mask.polygon, "roi_crs": "EPSG:4326",
                                "roi_inclusion": "pixel_center", "roi_area": "selected_whole_pixels"} if polygon_mask else {}),
                            scale=scale, offset=offset,
                            validity="raw_nodata_nonfinite_then_mask_then_scale_offset_finite",
                            std_ddof=0, weighting="pixel_equal", requested_bin_count=int(bin_count),
                            thresholds_m=thresholds.tolist(), area_method="wgs84_parallel_meridian_integral"),
            statistics=dict(total_count=total_count, valid_count=count,
                            invalid_count=total_count - count, invalid_reasons=invalid,
                            min_m=minimum, max_m=maximum, mean_m=mean, std_m=math.sqrt(max(0.0, m2 / count))),
            histogram=dict(bin_edges_m=edges.tolist(), counts=histogram.tolist(),
                           interval_rule="left_closed_right_open_last_closed", ordinate="pixel_count"),
            classes=classes,
            area=dict(footprint_m2=footprint, valid_m2=valid_area, invalid_m2=max(0.0, footprint - valid_area)),
            sign_summary=[dict(label=label, count=int(sign_count[i]), area_m2=float(sign_area[i]))
                          for i, label in enumerate(("<0 m", ">=0 m"))],
            completed_at=datetime.now(timezone.utc).isoformat(), elapsed_s=time.perf_counter() - started,
            warnings=["按零高程划分仅为近似海陆分类；面积为椭球水平面积。"],
        )
    finally:
        mask_band = band = None
        dataset = None
