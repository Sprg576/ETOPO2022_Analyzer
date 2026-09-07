"""
raster_reader.py

ETOPO2022 栅格读取模块。

当前阶段功能：
1. 使用 GDAL 打开栅格文件
2. 获取基本空间元数据
3. 获取波段元数据
4. 不读取完整栅格数组

正式运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

import os
import sys
from pprint import pprint

from osgeo import gdal

gdal.UseExceptions()

def _calculate_bounds(
    geotransform: tuple,
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    """
    根据 GeoTransform 和栅格尺寸计算空间范围。

    返回：
        (west, south, east, north)
    """

    def pixel_to_geo(col: int, row: int) -> tuple[float, float]:
        x = (
            geotransform[0]
            + col * geotransform[1]
            + row * geotransform[2]
        )

        y = (
            geotransform[3]
            + col * geotransform[4]
            + row * geotransform[5]
        )

        return x, y

    corners = [
        pixel_to_geo(0, 0),
        pixel_to_geo(width, 0),
        pixel_to_geo(0, height),
        pixel_to_geo(width, height),
    ]

    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]

    west = min(xs)
    east = max(xs)
    south = min(ys)
    north = max(ys)

    return west, south, east, north


def read_raster_metadata(file_path: str) -> dict:
    """
    使用 GDAL 读取栅格基本元数据。

    注意：
    本函数不会调用 ReadAsArray()，
    因此不会把整个 ETOPO2022 栅格加载进内存。

    Parameters
    ----------
    file_path : str
        栅格文件路径。

    Returns
    -------
    dict
        栅格元数据。
    """

    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"栅格文件不存在：{file_path}"
        )

    dataset = gdal.Open(
        file_path,
        gdal.GA_ReadOnly,
    )

    if dataset is None:
        raise RuntimeError(
            f"GDAL 无法打开文件：{file_path}"
        )

    try:
        driver = dataset.GetDriver()

        width = dataset.RasterXSize
        height = dataset.RasterYSize
        band_count = dataset.RasterCount

        geotransform = dataset.GetGeoTransform(
            can_return_null=True
        )

        if geotransform is not None:
            bounds = _calculate_bounds(
                geotransform,
                width,
                height,
            )

            pixel_size_x = geotransform[1]
            pixel_size_y = geotransform[5]

        else:
            bounds = None
            pixel_size_x = None
            pixel_size_y = None

        spatial_ref = dataset.GetSpatialRef()

        if spatial_ref is not None:
            crs_name = spatial_ref.GetName()

            authority_name = spatial_ref.GetAuthorityName(None)
            authority_code = spatial_ref.GetAuthorityCode(None)

            if authority_name and authority_code:
                crs_authority = (
                    f"{authority_name}:{authority_code}"
                )
            else:
                crs_authority = None
        else:
            crs_name = None
            crs_authority = None

        image_structure = dataset.GetMetadata(
            "IMAGE_STRUCTURE"
        )

        compression = image_structure.get(
            "COMPRESSION"
        )

        bands = []

        for band_index in range(
            1,
            band_count + 1,
        ):
            band = dataset.GetRasterBand(
                band_index
            )

            data_type = gdal.GetDataTypeName(
                band.DataType
            )

            nodata = band.GetNoDataValue()
            scale = band.GetScale()
            offset = band.GetOffset()
            unit = band.GetUnitType()

            block_size = band.GetBlockSize()

            bands.append(
                {
                    "band": band_index,
                    "data_type": data_type,
                    "nodata": nodata,
                    "scale": scale,
                    "offset": offset,
                    "unit": unit,
                    "block_size": block_size,
                }
            )

        metadata = {
            "file_name": os.path.basename(
                file_path
            ),
            "file_path": os.path.abspath(
                file_path
            ),
            "file_size_mb": round(
                os.path.getsize(file_path)
                / 1024
                / 1024,
                2,
            ),
            "driver_short_name": (
                driver.ShortName
                if driver
                else None
            ),
            "driver_long_name": (
                driver.LongName
                if driver
                else None
            ),
            "width": width,
            "height": height,
            "band_count": band_count,
            "geotransform": geotransform,
            "pixel_size_x": pixel_size_x,
            "pixel_size_y": pixel_size_y,
            "bounds": bounds,
            "crs_name": crs_name,
            "crs_authority": crs_authority,
            "compression": compression,
            "bands": bands,
        }

        return metadata

    finally:
        dataset = None


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "用法："
            "python raster_reader.py "
            "<raster_file>"
        )

        sys.exit(1)

    raster_path = sys.argv[1]

    try:
        raster_metadata = (
            read_raster_metadata(
                raster_path
            )
        )

        print(
            "\n===== Raster Metadata =====\n"
        )

        pprint(
            raster_metadata,
            sort_dicts=False,
        )

        print(
            "\nF01 metadata read OK"
        )

    except Exception as exc:
        print(
            f"\n读取失败：{exc}"
        )

        sys.exit(1)