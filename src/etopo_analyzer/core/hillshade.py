"""
F05 局部米制投影与 Hillshade 生成。

输入栅格先重投影到局部 UTM 坐标系，再使用 GDAL 生成山体阴影。
经纬度单位不会直接参与以米为单位的地形计算。
"""

from __future__ import annotations

import math
from pathlib import Path

from osgeo import gdal
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError


gdal.UseExceptions()


MAX_LOCAL_SPAN_DEGREES = 6.0


def _validate_source_and_output(
    input_path: str,
    output_path: str,
) -> tuple[Path, Path]:
    """校验输入与输出路径。"""

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

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return source_path, destination_path


def _wgs84_bounds(dataset) -> tuple[float, float, float, float]:
    """返回栅格四角在 EPSG:4326 下的外包范围。"""

    geotransform = dataset.GetGeoTransform(
        can_return_null=True
    )
    spatial_ref = dataset.GetSpatialRef()

    if geotransform is None:
        raise RuntimeError(
            "源栅格缺少 GeoTransform。"
        )

    if spatial_ref is None:
        raise RuntimeError(
            "源栅格缺少 CRS。"
        )

    # 使用四角而不是只取对角点，以兼容旋转 GeoTransform。
    source_corners = [
        gdal.ApplyGeoTransform(
            geotransform,
            column,
            row,
        )
        for column, row in (
            (0, 0),
            (dataset.RasterXSize, 0),
            (0, dataset.RasterYSize),
            (dataset.RasterXSize, dataset.RasterYSize),
        )
    ]

    try:
        # 局部投影只处理水平坐标，保留高程数值但不转换垂直基准。
        source_crs = CRS.from_wkt(
            spatial_ref.ExportToWkt()
        ).to_2d()
        transformer = Transformer.from_crs(
            source_crs,
            CRS.from_epsg(4326),
            always_xy=True,
        )
        geographic_corners = [
            transformer.transform(x, y)
            for x, y in source_corners
        ]
    except ProjError as exc:
        raise RuntimeError(
            "源栅格范围无法转换为 WGS 84 经纬度。"
        ) from exc

    if not all(
        math.isfinite(longitude)
        and math.isfinite(latitude)
        for longitude, latitude
        in geographic_corners
    ):
        raise RuntimeError(
            "源栅格包含无效地理坐标。"
        )

    longitudes = [
        point[0] for point in geographic_corners
    ]
    latitudes = [
        point[1] for point in geographic_corners
    ]

    return (
        min(longitudes),
        min(latitudes),
        max(longitudes),
        max(latitudes),
    )


def _local_utm_epsg(
    bounds: tuple[float, float, float, float],
) -> int:
    """根据局部范围中心点选择 WGS 84 UTM EPSG。"""

    west, south, east, north = bounds
    longitude_span = east - west
    latitude_span = north - south

    # 单个 UTM 分区宽约 6°，超过该范围应先裁剪。
    if (
        longitude_span > MAX_LOCAL_SPAN_DEGREES
        or latitude_span > MAX_LOCAL_SPAN_DEGREES
    ):
        raise ValueError(
            "Hillshade 仅支持经纬度跨度不超过 6° 的局部栅格；"
            "请先使用矩形裁剪。"
        )

    center_longitude = (west + east) / 2.0
    center_latitude = (south + north) / 2.0

    if not -80.0 <= center_latitude <= 84.0:
        raise ValueError(
            "当前局部米制投影使用 UTM，范围中心纬度必须位于 "
            "80°S 到 84°N 之间。"
        )

    zone = math.floor(
        (center_longitude + 180.0) / 6.0
    ) + 1
    zone = min(60, max(1, zone))

    return (
        32600 + zone
        if center_latitude >= 0.0
        else 32700 + zone
    )


def project_raster_to_local_utm(
    input_path: str,
    output_path: str,
) -> dict:
    """把局部栅格重投影为中心点所在的 WGS 84 UTM CRS。"""

    source_path, destination_path = (
        _validate_source_and_output(
            input_path,
            output_path,
        )
    )

    dataset = gdal.Open(
        str(source_path),
        gdal.GA_ReadOnly,
    )

    if dataset is None or dataset.RasterCount < 1:
        dataset = None
        raise RuntimeError(
            f"GDAL 无法打开有效栅格：{source_path}"
        )

    output_dataset = None

    try:
        bounds = _wgs84_bounds(dataset)
        target_epsg = _local_utm_epsg(bounds)
        source_crs = CRS.from_wkt(
            dataset.GetSpatialRef().ExportToWkt()
        ).to_2d()
        nodata = (
            dataset.GetRasterBand(1)
            .GetNoDataValue()
        )

        # 高程连续变化，投影重采样采用双线性插值。
        warp_options = {
            "format": "GTiff",
            "srcSRS": source_crs.to_wkt(),
            "dstSRS": f"EPSG:{target_epsg}",
            "resampleAlg": gdal.GRA_Bilinear,
            "multithread": True,
            "creationOptions": [
                "COMPRESS=DEFLATE",
                "TILED=YES",
                "BIGTIFF=IF_SAFER",
            ],
        }

        # 保留源 NoData，防止无效区域参与后续地形计算。
        if nodata is not None:
            warp_options["dstNodata"] = nodata

        output_dataset = gdal.Warp(
            str(destination_path),
            dataset,
            **warp_options,
        )

        if output_dataset is None:
            raise RuntimeError(
                "GDAL 无法生成局部米制投影栅格。"
            )

        result = {
            "output_path": str(destination_path),
            "width": output_dataset.RasterXSize,
            "height": output_dataset.RasterYSize,
            "band_count": output_dataset.RasterCount,
            "target_epsg": target_epsg,
            "source_wgs84_bounds": bounds,
        }

        output_dataset.FlushCache()
        output_dataset = None

        return result
    except Exception:
        output_dataset = None

        if destination_path.exists():
            destination_path.unlink()

        raise
    finally:
        dataset = None


def generate_hillshade(
    input_path: str,
    output_path: str,
    azimuth: float = 315.0,
    altitude: float = 45.0,
) -> dict:
    """从米制投影 DEM 生成固定参数 Hillshade GeoTIFF。"""

    source_path, destination_path = (
        _validate_source_and_output(
            input_path,
            output_path,
        )
    )

    if not 0.0 <= azimuth <= 360.0:
        raise ValueError(
            "Hillshade 方位角必须位于 0 到 360 度之间。"
        )

    if not 0.0 < altitude <= 90.0:
        raise ValueError(
            "Hillshade 高度角必须大于 0 且不超过 90 度。"
        )

    dataset = gdal.Open(
        str(source_path),
        gdal.GA_ReadOnly,
    )

    if dataset is None or dataset.RasterCount < 1:
        dataset = None
        raise RuntimeError(
            f"GDAL 无法打开有效栅格：{source_path}"
        )

    spatial_ref = dataset.GetSpatialRef()

    # 经纬度的“度”不能直接作为 Hillshade 的水平距离单位。
    if (
        spatial_ref is None
        or not spatial_ref.IsProjected()
        or not math.isclose(
            spatial_ref.GetLinearUnits(),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        dataset = None
        raise ValueError(
            "Hillshade 输入必须是水平单位为米的投影栅格。"
        )

    output_dataset = None

    try:
        # zFactor=1 表示水平距离和高程都使用米。
        options = gdal.DEMProcessingOptions(
            format="GTiff",
            computeEdges=True,
            azimuth=float(azimuth),
            altitude=float(altitude),
            zFactor=1.0,
            creationOptions=[
                "COMPRESS=DEFLATE",
                "TILED=YES",
            ],
        )

        output_dataset = gdal.DEMProcessing(
            str(destination_path),
            dataset,
            "hillshade",
            options=options,
        )

        if output_dataset is None:
            raise RuntimeError(
                "GDAL 无法生成 Hillshade 栅格。"
            )

        result = {
            "output_path": str(destination_path),
            "width": output_dataset.RasterXSize,
            "height": output_dataset.RasterYSize,
            "band_count": output_dataset.RasterCount,
            "azimuth": float(azimuth),
            "altitude": float(altitude),
        }

        output_dataset.FlushCache()
        output_dataset = None

        return result
    except Exception:
        output_dataset = None

        if destination_path.exists():
            destination_path.unlink()

        raise
    finally:
        dataset = None
