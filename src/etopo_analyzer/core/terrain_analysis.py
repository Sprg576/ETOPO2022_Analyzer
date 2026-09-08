"""
F06 地形分析核心算法。

当前实现 F06-1 坡度分析和 F06-2 坡向分析。输入必须是水平单位
为米的投影 DEM，结果输出为单波段 GeoTIFF。
"""

from __future__ import annotations

import math
from pathlib import Path

from osgeo import gdal


gdal.UseExceptions()


def _validate_source_and_output(
    input_path: str,
    output_path: str,
) -> tuple[Path, Path]:
    """校验地形分析的输入与输出路径。"""

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


def _open_projected_meter_dem(
    source_path: Path,
    analysis_name: str,
):
    """打开并校验水平单位为米的投影 DEM。"""

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

    # 坡度和坡向必须在水平单位为米的投影坐标系中计算。
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
            f"{analysis_name}输入必须是水平单位为米的投影栅格。"
        )

    return dataset


def generate_slope(
    input_path: str,
    output_path: str,
) -> dict:
    """从米制投影 DEM 生成角度制坡度 GeoTIFF。"""

    source_path, destination_path = (
        _validate_source_and_output(
            input_path,
            output_path,
        )
    )

    dataset = _open_projected_meter_dem(
        source_path,
        "坡度分析",
    )

    output_dataset = None

    try:
        # 水平和垂直单位均为米，因此固定 zFactor=1。
        options = gdal.DEMProcessingOptions(
            format="GTiff",
            band=1,
            computeEdges=True,
            alg="Horn",
            slopeFormat="degree",
            zFactor=1.0,
            creationOptions=[
                "COMPRESS=DEFLATE",
                "TILED=YES",
            ],
        )

        output_dataset = gdal.DEMProcessing(
            str(destination_path),
            dataset,
            "slope",
            options=options,
        )

        if output_dataset is None:
            raise RuntimeError(
                "GDAL 无法生成坡度栅格。"
            )

        result = {
            "output_path": str(destination_path),
            "width": output_dataset.RasterXSize,
            "height": output_dataset.RasterYSize,
            "band_count": output_dataset.RasterCount,
            "slope_format": "degree",
            "algorithm": "Horn",
            "z_factor": 1.0,
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


def generate_aspect(
    input_path: str,
    output_path: str,
) -> dict:
    """从米制投影 DEM 生成方位角制坡向 GeoTIFF。"""

    source_path, destination_path = (
        _validate_source_and_output(
            input_path,
            output_path,
        )
    )

    dataset = _open_projected_meter_dem(
        source_path,
        "坡向分析",
    )
    output_dataset = None

    try:
        # 使用方位角：北为 0°，顺时针增加；平地写入 NoData。
        options = gdal.DEMProcessingOptions(
            format="GTiff",
            band=1,
            computeEdges=True,
            alg="Horn",
            trigonometric=False,
            zeroForFlat=False,
            creationOptions=[
                "COMPRESS=DEFLATE",
                "TILED=YES",
            ],
        )

        output_dataset = gdal.DEMProcessing(
            str(destination_path),
            dataset,
            "aspect",
            options=options,
        )

        if output_dataset is None:
            raise RuntimeError(
                "GDAL 无法生成坡向栅格。"
            )

        result = {
            "output_path": str(destination_path),
            "width": output_dataset.RasterXSize,
            "height": output_dataset.RasterYSize,
            "band_count": output_dataset.RasterCount,
            "aspect_convention": "azimuth",
            "algorithm": "Horn",
            "zero_for_flat": False,
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
