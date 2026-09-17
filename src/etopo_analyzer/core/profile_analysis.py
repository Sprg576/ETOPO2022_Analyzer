"""F08 按 WGS84 大地线累计距离采样地形 / 海底剖面。"""

from bisect import bisect_right
import math
from pathlib import Path

from pyproj import Geod

from etopo_analyzer.core.raster_sampling import (
    RasterSampler, _validate_longitude_latitude,
)


MAX_PROFILE_SAMPLES = 10000
GEOD = Geod(ellps="WGS84")


def profile_path(vertices):
    """校验折线并计算各节点累计距离与各段方位角。"""
    if len(vertices) < 2:
        raise ValueError("剖面至少需要两个节点。")
    points, distances, azimuths = [], [0.0], []
    for vertex in vertices:
        if len(vertex) != 2:
            raise ValueError("每个节点必须包含经度和纬度。")
        point = _validate_longitude_latitude(*vertex)
        if points:
            if abs(point[0] - points[-1][0]) > 180:
                raise ValueError("第一版暂不支持跨日期变更线剖面。")
            azimuth, _, length = GEOD.inv(*points[-1], *point)
            if length <= 1e-8:
                continue
            if not math.isfinite(length):
                raise ValueError("无法计算有效大地线距离。")
            distances.append(distances[-1] + length)
            azimuths.append(azimuth)
        points.append(point)
    if len(points) < 2:
        raise ValueError("剖面总长度必须大于零。")
    return points, distances, azimuths


def point_at_distance(points, distances, azimuths, distance):
    """把全局累计距离定位到对应的大地线段。"""
    if distance <= 0:
        return points[0]
    if distance >= distances[-1]:
        return points[-1]
    index = min(bisect_right(distances, distance) - 1, len(azimuths) - 1)
    lon, lat, _ = GEOD.fwd(
        *points[index], azimuths[index], distance - distances[index],
    )
    return lon, lat


def densify_profile_path(vertices):
    """按最多约 10 km 加密显示路径，并保留全部折点。"""
    points, distances, azimuths = profile_path(vertices)
    step = max(10000.0, distances[-1] / 4000)
    result = [points[0]]
    for index, azimuth in enumerate(azimuths):
        length = distances[index + 1] - distances[index]
        count = max(1, math.ceil(length / step))
        for j in range(1, count):
            lon, lat, _ = GEOD.fwd(*points[index], azimuth, length * j / count)
            result.append((lon, lat))
        result.append(points[index + 1])
    return result


def sample_elevation_profile(
    raster_path: str,
    vertices: list[tuple[float, float]],
    sample_interval_m: float = 1000.0,
) -> dict:
    """沿折线等距读取原 DEM；保留不足一个间隔的终点。"""
    try:
        interval = float(sample_interval_m)
    except (TypeError, ValueError) as exc:
        raise ValueError("采样间隔必须为正数。") from exc
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("采样间隔必须为大于零的有限数值。")
    points, vertex_distances, azimuths = profile_path(vertices)
    total = vertex_distances[-1]
    ratio = total / interval
    if not math.isfinite(ratio) or ratio > MAX_PROFILE_SAMPLES - 1 + 1e-8:
        minimum = total / (MAX_PROFILE_SAMPLES - 1)
        raise ValueError(f"采样点超过 {MAX_PROFILE_SAMPLES} 个，请增大采样间隔至至少 {minimum:.3f} m。")
    count = math.floor(ratio)
    distances = [i * interval for i in range(count + 1)]
    if count > 0 and math.isclose(distances[-1], total, rel_tol=1e-12, abs_tol=1e-8):
        distances[-1] = total
    else:
        distances.append(total)
    if len(distances) > MAX_PROFILE_SAMPLES:
        raise ValueError("采样点超过上限，请增大采样间隔。")

    result = {
        "raster_path": str(Path(raster_path).resolve()),
        "vertices": points, "vertex_distance_m": vertex_distances,
        "distance_m": distances, "longitude": [], "latitude": [],
        "elevation_m": [], "depth_m": [], "is_nodata": [],
        "total_distance_m": total, "sample_count": len(distances),
        "sample_interval_m": interval,
    }
    # 所有采样共用一次打开的数据集与坐标转换器。
    with RasterSampler(raster_path) as sampler:
        for distance in distances:
            lon, lat = point_at_distance(points, vertex_distances, azimuths, distance)
            value = sampler.sample(lon, lat, outside_as_nodata=True)
            for target, source in (
                ("longitude", "longitude"), ("latitude", "latitude"),
                ("elevation_m", "elevation"), ("depth_m", "depth"),
                ("is_nodata", "is_nodata"),
            ):
                result[target].append(value[source])
    result["valid_sample_count"] = sum(not flag for flag in result["is_nodata"])
    if result["valid_sample_count"] == 0:
        raise ValueError("整条剖面没有有效高程，请在 DEM 覆盖范围内绘制。")
    return result
