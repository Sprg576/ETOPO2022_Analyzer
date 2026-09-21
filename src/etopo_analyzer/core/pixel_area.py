"""F09：WGS84 规则经纬度格网的椭球水平面积。"""

import numpy as np
from pyproj import CRS


def pixel_row_areas(dataset):
    """返回逐行单像元面积（m²），不读取高程、不重采样。"""
    srs = dataset.GetSpatialRef()
    transform = dataset.GetGeoTransform(can_return_null=True)
    if srs is None or transform is None:
        raise ValueError("统计需要有效的 CRS 和 GeoTransform。")
    crs = CRS.from_wkt(srs.ExportToWkt()).to_2d()
    if not crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
        raise ValueError("F09 首版仅支持 WGS84 经纬度 DEM，不支持投影 DEM。")
    west, dx, rx, north, ry, dy = transform
    if not all(np.isfinite(transform)) or rx != 0 or ry != 0 or dx <= 0 or dy >= 0:
        raise ValueError("F09 需要北向上、无旋转的规则经纬度格网。")
    east = west + dataset.RasterXSize * dx
    south = north + dataset.RasterYSize * dy
    if west < -180 - 1e-9 or east > 180 + 1e-9 or south < -90 - 1e-9 or north > 90 + 1e-9:
        raise ValueError("DEM 像元边界超出合法经纬度范围。")
    # 积分采用像元外边界；纬线边界不替换成两角点之间的大地线。
    lat = np.clip(north + np.arange(dataset.RasterYSize + 1) * dy, -90, 90)
    u = np.sin(np.deg2rad(lat))
    a = crs.ellipsoid.semi_major_metre
    f = 1.0 / crs.ellipsoid.inverse_flattening
    e2 = f * (2 - f)
    e = np.sqrt(e2)
    primitive = u / (2 * (1 - e2 * u * u)) + np.arctanh(e * u) / (2 * e)
    areas = a * a * (1 - e2) * np.deg2rad(dx) * np.abs(np.diff(primitive))
    if not np.all(np.isfinite(areas) & (areas > 0)):
        raise ValueError("像元面积无法可靠计算，请检查格网分辨率。")
    return areas
