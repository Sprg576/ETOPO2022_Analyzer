"""保留数值和空间参考的分块 GeoTIFF 复制及回读检查。"""

import math
import numpy as np
from osgeo import gdal
from .export_service import check_cancelled


def _equal(a, b):
    return a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))


def verify_raster(source, output, cancelled=None):
    if (source.RasterXSize, source.RasterYSize, source.RasterCount) != (output.RasterXSize, output.RasterYSize, output.RasterCount):
        raise ValueError("导出栅格尺寸不一致。")
    if source.GetGeoTransform() != output.GetGeoTransform():
        raise ValueError("导出栅格空间变换不一致。")
    a, b = source.GetSpatialRef(), output.GetSpatialRef()
    if (a is None) != (b is None) or (a is not None and not a.IsSame(b)):
        raise ValueError("导出栅格坐标系不一致。")
    width, height = source.RasterXSize, source.RasterYSize
    if width * height <= 1024 * 1024:
        positions = [(x, y) for y in range(0, height, 256) for x in range(0, width, 256)]
    else:
        positions = sorted({(int(x * max(0, width - 256) / 4), int(y * max(0, height - 256) / 4))
                            for x in range(5) for y in range(5)})
    for index in range(1, source.RasterCount + 1):
        a, b = source.GetRasterBand(index), output.GetRasterBand(index)
        if a.DataType != b.DataType or any(not _equal(getattr(a, method)(), getattr(b, method)())
                for method in ("GetNoDataValue", "GetScale", "GetOffset", "GetUnitType")):
            raise ValueError("导出波段类型、NoData、比例或单位不一致。")
        for x, y in positions:
            check_cancelled(cancelled)
            args = (x, y, min(256, width - x), min(256, height - y))
            for left, right in ((a, b), (a.GetMaskBand(), b.GetMaskBand())):
                if not np.array_equal(left.ReadAsArray(*args), right.ReadAsArray(*args), equal_nan=True):
                    raise ValueError("导出栅格像元或有效性掩膜不一致。")
        source.FlushCache()
        output.FlushCache()


def export_raster(folder, path, cancelled=None, progress=None):
    check_cancelled(cancelled)
    source = gdal.Open(str(path), gdal.GA_ReadOnly)
    if source is None:
        raise ValueError("无法打开导出来源。")
    output = None
    try:
        def callback(fraction, message, data):
            if cancelled and cancelled():
                return 0
            source.FlushCache()
            if progress:
                progress(int(fraction * 85))
            return 1
        # 使用线程局部配置，避免影响正在显示的 QGIS 数据源。
        previous = gdal.GetThreadLocalConfigOption("GDAL_TIFF_INTERNAL_MASK")
        previous_swath = gdal.GetThreadLocalConfigOption("GDAL_SWATH_SIZE")
        gdal.SetThreadLocalConfigOption("GDAL_TIFF_INTERNAL_MASK", "YES")
        gdal.SetThreadLocalConfigOption("GDAL_SWATH_SIZE", str(8 * 2**20))
        try:
            output = gdal.GetDriverByName("GTiff").CreateCopy(
                str(folder / "raster.tif"), source, strict=1,
                options=["TILED=YES", "COMPRESS=DEFLATE", "BIGTIFF=IF_SAFER"], callback=callback)
        finally:
            gdal.SetThreadLocalConfigOption("GDAL_TIFF_INTERNAL_MASK", previous)
            gdal.SetThreadLocalConfigOption("GDAL_SWATH_SIZE", previous_swath)
        check_cancelled(cancelled)
        if output is None:
            raise RuntimeError("GeoTIFF 写入失败。")
        output.FlushCache()
        output.Close()
        output = None
        output = gdal.Open(str(folder / "raster.tif"), gdal.GA_ReadOnly)
        if output is None:
            raise RuntimeError("GeoTIFF 重新打开失败。")
        verify_raster(source, output, cancelled)
        if progress:
            progress(95)
        bands = []
        for index in range(1, source.RasterCount + 1):
            band = source.GetRasterBand(index)
            nodata = band.GetNoDataValue()
            if isinstance(nodata, float) and not math.isfinite(nodata):
                nodata = str(nodata)
            bands.append({"data_type": gdal.GetDataTypeName(band.DataType), "nodata": nodata,
                          "scale": band.GetScale(), "offset": band.GetOffset(), "unit": band.GetUnitType(),
                          "metadata": band.GetMetadata()})
        band = None
        return {"width": source.RasterXSize, "height": source.RasterYSize,
                "bands": source.RasterCount, "crs_wkt": source.GetProjection(),
                "geotransform": list(source.GetGeoTransform()), "compression": "DEFLATE",
                "band_metadata": bands, "source_metadata": source.GetMetadata(), "method": "lossless_copy_no_resampling"}
    except Exception:
        check_cancelled(cancelled)
        raise
    finally:
        # 显式关闭原生句柄：异常回溯可能仍引用数据集，仅赋 None 无法保证 Windows 解锁。
        if output is not None:
            output.Close()
        if source is not None:
            source.Close()
        output = None
        source = None
