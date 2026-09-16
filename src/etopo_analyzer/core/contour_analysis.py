"""F07-1 等值线生成与 F07-2 高程语义分类。"""

from __future__ import annotations

import math
from pathlib import Path

from osgeo import gdal, ogr


gdal.UseExceptions()
ogr.UseExceptions()


CONTOUR_LAYER_NAME = "contours"
CONTOUR_TYPE_ELEVATION = "等高线"
CONTOUR_TYPE_DEPTH = "等深线"
CONTOUR_TYPE_ZERO = "0 m 等值线"


def classify_contour_elevation(elevation: float) -> str:
    """按等值高程的正、负和零值返回语义类型。"""

    elevation = float(elevation)

    if not math.isfinite(elevation):
        raise ValueError(
            "等值高程必须是有限数值。"
        )

    if elevation > 0.0:
        return CONTOUR_TYPE_ELEVATION

    if elevation < 0.0:
        return CONTOUR_TYPE_DEPTH

    return CONTOUR_TYPE_ZERO


def _validate_source_and_output(
    input_path: str,
    output_path: str,
    interval: float,
    base: float,
) -> tuple[Path, Path]:
    """校验等值线输入、输出路径和数值参数。"""

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

    if destination_path.suffix.lower() != ".gpkg":
        raise ValueError(
            "等值线输出文件必须使用 .gpkg 扩展名。"
        )

    if destination_path.exists():
        raise FileExistsError(
            f"输出文件已存在：{destination_path}"
        )

    if not math.isfinite(interval) or interval <= 0.0:
        raise ValueError(
            "等值线间隔必须是大于 0 的有限数值。"
        )

    if not math.isfinite(base):
        raise ValueError(
            "等值线基准值必须是有限数值。"
        )

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return source_path, destination_path


def _horizontal_spatial_reference(dataset):
    """复制源栅格 CRS，并移除复合 CRS 中的垂直部分。"""

    source_srs = dataset.GetSpatialRef()

    if source_srs is None or not source_srs.ExportToWkt():
        raise ValueError(
            "源栅格缺少有效空间参考。"
        )

    vector_srs = source_srs.Clone()

    if vector_srs.IsCompound():
        if vector_srs.StripVertical() != 0:
            raise RuntimeError(
                "无法从源栅格复合 CRS 提取水平 CRS。"
            )

    return vector_srs


def _authority_id(spatial_reference) -> str | None:
    """返回 CRS 权威标识，例如 EPSG:4326。"""

    authority_name = spatial_reference.GetAuthorityName(None)
    authority_code = spatial_reference.GetAuthorityCode(None)

    if authority_name and authority_code:
        return f"{authority_name}:{authority_code}"

    return None


def _populate_contour_types(contour_layer) -> dict[str, int]:
    """根据 ELEV 为每条等值线写入 TYPE。"""

    type_counts = {
        CONTOUR_TYPE_ELEVATION: 0,
        CONTOUR_TYPE_DEPTH: 0,
        CONTOUR_TYPE_ZERO: 0,
    }

    if contour_layer.StartTransaction() != ogr.OGRERR_NONE:
        raise RuntimeError(
            "无法开始等值线语义分类事务。"
        )

    try:
        contour_layer.ResetReading()
        feature = contour_layer.GetNextFeature()

        while feature is not None:
            if not feature.IsFieldSetAndNotNull("ELEV"):
                raise RuntimeError(
                    "等值线要素缺少 ELEV 值。"
                )

            contour_type = classify_contour_elevation(
                feature.GetFieldAsDouble("ELEV")
            )
            feature.SetField("TYPE", contour_type)

            if contour_layer.SetFeature(feature) != ogr.OGRERR_NONE:
                raise RuntimeError(
                    "无法写入等值线 TYPE 字段。"
                )

            type_counts[contour_type] += 1
            feature = None
            feature = contour_layer.GetNextFeature()

        if contour_layer.CommitTransaction() != ogr.OGRERR_NONE:
            raise RuntimeError(
                "无法提交等值线语义分类结果。"
            )
    except Exception:
        contour_layer.RollbackTransaction()
        raise
    finally:
        contour_layer.ResetReading()

    return type_counts


def generate_contours(
    input_path: str,
    output_path: str,
    interval: float = 500.0,
    base: float = 0.0,
) -> dict:
    """从 DEM 波段 1 生成 LineString GeoPackage 等值线。"""

    source_path, destination_path = (
        _validate_source_and_output(
            input_path,
            output_path,
            float(interval),
            float(base),
        )
    )
    interval = float(interval)
    base = float(base)

    source_dataset = gdal.Open(
        str(source_path),
        gdal.GA_ReadOnly,
    )

    if source_dataset is None or source_dataset.RasterCount < 1:
        source_dataset = None
        raise RuntimeError(
            f"GDAL 无法打开有效栅格：{source_path}"
        )

    source_band = None
    output_dataset = None
    contour_layer = None

    try:
        source_band = source_dataset.GetRasterBand(1)
        vector_srs = _horizontal_spatial_reference(
            source_dataset
        )
        driver = ogr.GetDriverByName("GPKG")

        if driver is None:
            raise RuntimeError(
                "当前 GDAL 环境不支持 GeoPackage。"
            )

        output_dataset = driver.CreateDataSource(
            str(destination_path)
        )

        if output_dataset is None:
            raise RuntimeError(
                "GDAL 无法创建等值线 GeoPackage。"
            )

        contour_layer = output_dataset.CreateLayer(
            CONTOUR_LAYER_NAME,
            srs=vector_srs,
            geom_type=ogr.wkbLineString,
        )

        if contour_layer is None:
            raise RuntimeError(
                "GDAL 无法创建 contours 图层。"
            )

        if contour_layer.CreateField(
            ogr.FieldDefn("ID", ogr.OFTInteger64)
        ) != ogr.OGRERR_NONE:
            raise RuntimeError("无法创建 ID 字段。")

        if contour_layer.CreateField(
            ogr.FieldDefn("ELEV", ogr.OFTReal)
        ) != ogr.OGRERR_NONE:
            raise RuntimeError("无法创建 ELEV 字段。")

        type_field = ogr.FieldDefn("TYPE", ogr.OFTString)
        type_field.SetWidth(20)

        if contour_layer.CreateField(
            type_field
        ) != ogr.OGRERR_NONE:
            raise RuntimeError("无法创建 TYPE 字段。")

        options = [
            f"LEVEL_INTERVAL={interval:.17g}",
            f"LEVEL_BASE={base:.17g}",
            "ID_FIELD=0",
            "ELEV_FIELD=1",
        ]
        nodata = source_band.GetNoDataValue()

        if nodata is not None:
            options.append(f"NODATA={nodata:.17g}")

        error_code = gdal.ContourGenerateEx(
            source_band,
            contour_layer,
            options=options,
        )

        if error_code != gdal.CE_None:
            raise RuntimeError(
                "GDAL 无法生成等值线。"
            )

        type_counts = _populate_contour_types(
            contour_layer
        )
        feature_count = contour_layer.GetFeatureCount()
        contour_layer.SyncToDisk()
        output_dataset.FlushCache()

        result = {
            "output_path": str(destination_path),
            "layer_name": CONTOUR_LAYER_NAME,
            "feature_count": feature_count,
            "geometry_type": "LineString",
            "interval": interval,
            "base": base,
            "crs_authid": _authority_id(vector_srs),
            "type_counts": type_counts,
        }

        contour_layer = None
        output_dataset = None

        return result
    except Exception:
        contour_layer = None
        output_dataset = None

        # 只清理由本次调用创建的不完整 GeoPackage 及其临时文件。
        for partial_path in (
            destination_path,
            Path(f"{destination_path}-wal"),
            Path(f"{destination_path}-shm"),
        ):
            if partial_path.exists():
                partial_path.unlink()

        raise
    finally:
        source_band = None
        source_dataset = None
