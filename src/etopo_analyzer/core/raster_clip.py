"""
raster_clip.py

ETOPO2022 经纬度矩形区域核心裁剪模块。

输入范围采用 WGS 84 经纬度（EPSG:4326），输出为新的 GeoTIFF。
裁剪使用 GDAL 像元窗口，不会把完整全球栅格加载进内存。
"""

from __future__ import annotations

import math
from pathlib import Path

from osgeo import gdal
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError


gdal.UseExceptions()


def _validate_bounds(
    west: float,
    south: float,
    east: float,
    north: float,
) -> tuple[float, float, float, float]:
    """校验并返回 WGS 84 经纬度范围。"""

    try:
        west = float(west)
        south = float(south)
        east = float(east)
        north = float(north)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "裁剪范围必须是数值。"
        ) from exc

    coordinates = (
        west,
        south,
        east,
        north,
    )

    if not all(
        math.isfinite(value)
        for value in coordinates
    ):
        raise ValueError(
            "裁剪范围必须是有限数值。"
        )

    if not -180.0 <= west <= 180.0:
        raise ValueError(
            "西边界必须位于 -180 到 180 度之间。"
        )

    if not -180.0 <= east <= 180.0:
        raise ValueError(
            "东边界必须位于 -180 到 180 度之间。"
        )

    if not -90.0 <= south <= 90.0:
        raise ValueError(
            "南边界必须位于 -90 到 90 度之间。"
        )

    if not -90.0 <= north <= 90.0:
        raise ValueError(
            "北边界必须位于 -90 到 90 度之间。"
        )

    if west >= east:
        raise ValueError(
            "西边界必须小于东边界；F04 首版不支持跨 180° 裁剪。"
        )

    if south >= north:
        raise ValueError(
            "南边界必须小于北边界。"
        )

    return west, south, east, north


def _open_source_dataset(
    input_path: Path,
    subdataset_name: str | None,
):
    """打开具有可读取栅格波段的源数据集。"""

    dataset = gdal.Open(
        str(input_path),
        gdal.GA_ReadOnly,
    )

    if dataset is None:
        raise RuntimeError(
            f"GDAL 无法打开文件：{input_path}"
        )

    if dataset.RasterCount > 0:
        return dataset

    subdatasets = dataset.GetSubDatasets() or []

    if not subdatasets:
        dataset = None
        raise RuntimeError(
            f"栅格数据集不包含可读取波段：{input_path}"
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


def _bounds_to_source_coordinates(
    dataset,
    west: float,
    south: float,
    east: float,
    north: float,
) -> list[tuple[float, float]]:
    """把经纬度矩形的四个角转换到源栅格二维水平 CRS。"""

    spatial_ref = dataset.GetSpatialRef()

    if spatial_ref is None:
        raise RuntimeError(
            "源栅格缺少 CRS，无法转换裁剪范围。"
        )

    try:
        source_crs = CRS.from_wkt(
            spatial_ref.ExportToWkt()
        ).to_2d()

        transformer = Transformer.from_crs(
            CRS.from_epsg(4326),
            source_crs,
            always_xy=True,
        )

        geographic_corners = [
            (west, north),
            (east, north),
            (west, south),
            (east, south),
        ]

        source_corners = [
            transformer.transform(
                longitude,
                latitude,
            )
            for longitude, latitude
            in geographic_corners
        ]
    except ProjError as exc:
        raise RuntimeError(
            "裁剪范围无法转换到源栅格水平 CRS。"
        ) from exc

    if not all(
        math.isfinite(x) and math.isfinite(y)
        for x, y in source_corners
    ):
        raise ValueError(
            "裁剪范围无法转换为有效的源栅格坐标。"
        )

    return source_corners


def _snap_pixel_coordinate(value: float) -> float:
    """消除 GeoTransform 逆变换在整数边界处的浮点误差。"""

    nearest_integer = round(value)

    if math.isclose(
        value,
        nearest_integer,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        return float(nearest_integer)

    return value


def _calculate_bounds(
    geotransform: tuple,
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    """计算输出栅格的实际空间范围。"""

    corners = [
        gdal.ApplyGeoTransform(
            geotransform,
            column,
            row,
        )
        for column, row in (
            (0, 0),
            (width, 0),
            (0, height),
            (width, height),
        )
    ]

    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]

    return (
        min(xs),
        min(ys),
        max(xs),
        max(ys),
    )


def clip_raster_by_bounds(
    input_path: str,
    output_path: str,
    west: float,
    south: float,
    east: float,
    north: float,
    subdataset_name: str | None = None,
) -> dict:
    """
    按 WGS 84 经纬度矩形范围裁剪栅格并生成 GeoTIFF。

    输出范围会对齐源栅格像元边界。若请求范围仅部分覆盖源栅格，
    则输出为请求范围与源栅格范围的交集。

    Returns
    -------
    dict
        包含输出路径、尺寸、波段数、实际范围和源像元窗口。
    """

    west, south, east, north = _validate_bounds(
        west,
        south,
        east,
        north,
    )

    source_path = Path(input_path).resolve()
    destination_path = Path(output_path).resolve()

    if not source_path.is_file():
        raise FileNotFoundError(
            f"源栅格文件不存在：{source_path}"
        )

    if destination_path == source_path:
        raise ValueError(
            "输出路径不能与源栅格路径相同。"
        )

    if destination_path.suffix.lower() not in {
        ".tif",
        ".tiff",
    }:
        raise ValueError(
            "输出文件必须使用 .tif 或 .tiff 扩展名。"
        )

    if destination_path.exists():
        raise FileExistsError(
            f"输出文件已存在：{destination_path}"
        )

    dataset = _open_source_dataset(
        source_path,
        subdataset_name,
    )

    output_dataset = None

    try:
        geotransform = dataset.GetGeoTransform(
            can_return_null=True
        )

        if geotransform is None:
            raise RuntimeError(
                "源栅格缺少 GeoTransform，无法定位裁剪窗口。"
            )

        inverse_geotransform = (
            gdal.InvGeoTransform(geotransform)
        )

        if inverse_geotransform is None:
            raise RuntimeError(
                "源栅格 GeoTransform 无法求逆。"
            )

        source_corners = _bounds_to_source_coordinates(
            dataset,
            west,
            south,
            east,
            north,
        )

        pixel_corners = [
            gdal.ApplyGeoTransform(
                inverse_geotransform,
                x,
                y,
            )
            for x, y in source_corners
        ]

        pixel_xs = [
            _snap_pixel_coordinate(point[0])
            for point in pixel_corners
        ]

        pixel_ys = [
            _snap_pixel_coordinate(point[1])
            for point in pixel_corners
        ]

        column_start = max(
            0,
            math.floor(min(pixel_xs)),
        )

        column_end = min(
            dataset.RasterXSize,
            math.ceil(max(pixel_xs)),
        )

        row_start = max(
            0,
            math.floor(min(pixel_ys)),
        )

        row_end = min(
            dataset.RasterYSize,
            math.ceil(max(pixel_ys)),
        )

        width = column_end - column_start
        height = row_end - row_start

        if width <= 0 or height <= 0:
            raise ValueError(
                "裁剪范围与源栅格没有有效交集。"
            )

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        translate_options = gdal.TranslateOptions(
            format="GTiff",
            srcWin=[
                column_start,
                row_start,
                width,
                height,
            ],
            creationOptions=[
                "COMPRESS=DEFLATE",
                "TILED=YES",
                "BLOCKXSIZE=256",
                "BLOCKYSIZE=256",
            ],
        )

        output_dataset = gdal.Translate(
            str(destination_path),
            dataset,
            options=translate_options,
        )

        if output_dataset is None:
            raise RuntimeError(
                f"GDAL 裁剪失败：{destination_path}"
            )

        output_dataset.FlushCache()

        output_geotransform = (
            output_dataset.GetGeoTransform(
                can_return_null=True
            )
        )

        if output_geotransform is None:
            raise RuntimeError(
                "裁剪结果缺少 GeoTransform。"
            )

        actual_bounds = _calculate_bounds(
            output_geotransform,
            output_dataset.RasterXSize,
            output_dataset.RasterYSize,
        )

        result = {
            "output_path": str(destination_path),
            "width": output_dataset.RasterXSize,
            "height": output_dataset.RasterYSize,
            "band_count": output_dataset.RasterCount,
            "bounds": actual_bounds,
            "source_window": (
                column_start,
                row_start,
                width,
                height,
            ),
        }

        return result
    except Exception:
        output_dataset = None

        if destination_path.exists():
            destination_path.unlink()

        raise
    finally:
        output_dataset = None
        dataset = None
