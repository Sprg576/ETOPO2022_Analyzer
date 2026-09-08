"""
point_query.py

ETOPO2022 单点高程 / 水深查询模块。

输入为 WGS 84 经纬度（EPSG:4326）。本模块只读取目标位置的
1×1 像元，不会把完整全球栅格加载进内存。
"""

from __future__ import annotations

import math
from pathlib import Path

from osgeo import gdal
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError


gdal.UseExceptions()


def _validate_longitude_latitude(
    longitude: float,
    latitude: float,
) -> tuple[float, float]:
    """校验并返回浮点型经纬度。"""

    try:
        longitude = float(longitude)
        latitude = float(latitude)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "经度和纬度必须是数值。"
        ) from exc

    if not math.isfinite(longitude):
        raise ValueError("经度必须是有限数值。")

    if not math.isfinite(latitude):
        raise ValueError("纬度必须是有限数值。")

    if not -180.0 <= longitude <= 180.0:
        raise ValueError(
            "经度必须位于 -180 到 180 度之间。"
        )

    if not -90.0 <= latitude <= 90.0:
        raise ValueError(
            "纬度必须位于 -90 到 90 度之间。"
        )

    return longitude, latitude


def _open_query_dataset(
    file_path: str,
    subdataset_name: str | None,
):
    """打开具有可读取栅格波段的数据集。"""

    path = Path(file_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"栅格文件不存在：{path}"
        )

    dataset = gdal.Open(
        str(path),
        gdal.GA_ReadOnly,
    )

    if dataset is None:
        raise RuntimeError(
            f"GDAL 无法打开文件：{path}"
        )

    # GeoTIFF 通常可直接读取；部分 NetCDF 需要打开指定子数据集。
    if dataset.RasterCount > 0:
        return dataset

    subdatasets = dataset.GetSubDatasets() or []

    if not subdatasets:
        dataset = None
        raise RuntimeError(
            f"栅格数据集不包含可读取波段：{path}"
        )

    if subdataset_name is None:
        dataset = None
        raise ValueError(
            "该数据集没有直接栅格波段，请指定 subdataset_name。"
        )

    available_names = {
        name for name, _description in subdatasets
    }

    if subdataset_name not in available_names:
        dataset = None
        raise ValueError(
            f"无效的 subdataset_name：{subdataset_name}"
        )

    dataset = None
    subdataset = gdal.Open(
        subdataset_name,
        gdal.GA_ReadOnly,
    )

    if subdataset is None or subdataset.RasterCount == 0:
        subdataset = None
        raise RuntimeError(
            f"GDAL 无法打开有效子数据集：{subdataset_name}"
        )

    return subdataset


def _to_raster_coordinates(
    dataset,
    longitude: float,
    latitude: float,
) -> tuple[float, float]:
    """把 EPSG:4326 经纬度转换为栅格的二维水平 CRS。"""

    spatial_ref = dataset.GetSpatialRef()

    if spatial_ref is None:
        raise RuntimeError(
            "栅格缺少 CRS，无法转换查询坐标。"
        )

    try:
        # 查询只涉及水平位置，忽略复合 CRS 中的垂直分量。
        raster_crs = CRS.from_wkt(
            spatial_ref.ExportToWkt()
        ).to_2d()

        transformer = Transformer.from_crs(
            CRS.from_epsg(4326),
            raster_crs,
            always_xy=True,
        )

        raster_x, raster_y = transformer.transform(
            longitude,
            latitude,
        )
    except ProjError as exc:
        raise RuntimeError(
            "经纬度无法转换到栅格水平 CRS。"
        ) from exc

    if not (
        math.isfinite(raster_x)
        and math.isfinite(raster_y)
    ):
        raise ValueError(
            "查询点无法转换为有效的栅格坐标。"
        )

    return raster_x, raster_y


def _floor_pixel_coordinate(value: float) -> int:
    """消除 GeoTransform 逆变换在整数边界处的浮点误差。"""

    nearest_integer = round(value)

    if math.isclose(
        value,
        nearest_integer,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        value = float(nearest_integer)

    return math.floor(value)


def _is_nodata(
    value: float,
    nodata: float | None,
) -> bool:
    """判断一个波段值是否为 NoData。"""

    if math.isnan(value):
        return True

    if nodata is None:
        return False

    if math.isnan(float(nodata)):
        return math.isnan(value)

    return value == float(nodata)


def query_point_elevation(
    file_path: str,
    longitude: float,
    latitude: float,
    subdataset_name: str | None = None,
) -> dict:
    """
    查询一个 WGS 84 经纬度位置的高程或近似水深。

    当 elevation 小于 0 时，depth 等于 -elevation；这只是课程
    项目中的近似海洋筛选，不等同于严格海岸线判定。

    Returns
    -------
    dict
        包含 longitude、latitude、column、row、elevation、depth
        和 is_nodata。
    """

    longitude, latitude = (
        _validate_longitude_latitude(
            longitude,
            latitude,
        )
    )

    dataset = _open_query_dataset(
        file_path,
        subdataset_name,
    )

    try:
        raster_x, raster_y = _to_raster_coordinates(
            dataset,
            longitude,
            latitude,
        )

        geotransform = dataset.GetGeoTransform(
            can_return_null=True
        )

        if geotransform is None:
            raise RuntimeError(
                "栅格缺少 GeoTransform，无法定位像元。"
            )

        inverse_geotransform = (
            gdal.InvGeoTransform(geotransform)
        )

        if inverse_geotransform is None:
            raise RuntimeError(
                "栅格 GeoTransform 无法求逆。"
            )

        # 逆 GeoTransform 把地图坐标转换为浮点像元行列号。
        pixel_x, pixel_y = gdal.ApplyGeoTransform(
            inverse_geotransform,
            raster_x,
            raster_y,
        )

        column = _floor_pixel_coordinate(pixel_x)
        row = _floor_pixel_coordinate(pixel_y)

        if not (
            0 <= column < dataset.RasterXSize
            and 0 <= row < dataset.RasterYSize
        ):
            raise ValueError(
                "查询点位于栅格有效范围之外。"
            )

        band = dataset.GetRasterBand(1)
        # 仅读取目标 1×1 像元，避免加载全球栅格。
        values = band.ReadAsArray(
            column,
            row,
            1,
            1,
        )

        if values is None or values.size != 1:
            raise RuntimeError(
                "GDAL 无法读取查询点的 1×1 像元。"
            )

        raw_value = float(values[0, 0])
        nodata = band.GetNoDataValue()
        is_nodata = _is_nodata(
            raw_value,
            nodata,
        )

        if is_nodata:
            elevation = None
            depth = None
        else:
            scale = band.GetScale()
            offset = band.GetOffset()

            if scale is None:
                scale = 1.0

            if offset is None:
                offset = 0.0

            # 应用波段自带的比例和偏移得到真实高程值。
            elevation = (
                raw_value * float(scale)
                + float(offset)
            )

            depth = (
                -elevation
                if elevation < 0.0
                else None
            )

        return {
            "longitude": longitude,
            "latitude": latitude,
            "column": column,
            "row": row,
            "elevation": elevation,
            "depth": depth,
            "is_nodata": is_nodata,
        }
    finally:
        dataset = None
