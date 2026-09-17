"""F03 / F08 共用的只读栅格采样器。"""

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



class RasterSampler:
    """一次打开数据集，复用坐标转换和波段元数据。"""

    def __init__(self, file_path: str, subdataset_name: str | None = None):
        self.dataset = None
        self.band = None
        try:
            self.dataset = _open_query_dataset(file_path, subdataset_name)
            srs = self.dataset.GetSpatialRef()
            if srs is None:
                raise RuntimeError("栅格缺少 CRS，无法转换查询坐标。")
            self.transformer = Transformer.from_crs(
                4326, CRS.from_wkt(srs.ExportToWkt()).to_2d(),
                always_xy=True,
            )
            transform = self.dataset.GetGeoTransform(can_return_null=True)
            if transform is None:
                raise RuntimeError("栅格缺少 GeoTransform，无法定位像元。")
            self.inverse = gdal.InvGeoTransform(transform)
            if self.inverse is None:
                raise RuntimeError("栅格 GeoTransform 无法求逆。")
            self.band = self.dataset.GetRasterBand(1)
            self.nodata = self.band.GetNoDataValue()
            scale = self.band.GetScale()
            offset = self.band.GetOffset()
            self.scale = 1.0 if scale is None else float(scale)
            self.offset = 0.0 if offset is None else float(offset)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """先释放波段，再关闭数据集。"""
        self.band = None
        self.dataset = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def sample(self, longitude: float, latitude: float, *,
               outside_as_nodata: bool = False) -> dict:
        """读取目标像元；剖面允许将范围外位置标为缺测。"""
        longitude, latitude = _validate_longitude_latitude(longitude, latitude)
        try:
            x, y = self.transformer.transform(longitude, latitude, errcheck=True)
        except ProjError as exc:
            raise RuntimeError("经纬度无法转换到栅格水平 CRS。") from exc
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("查询点无法转换为有效的栅格坐标。")
        px, py = gdal.ApplyGeoTransform(self.inverse, x, y)
        column, row = _floor_pixel_coordinate(px), _floor_pixel_coordinate(py)
        inside = (0 <= column < self.dataset.RasterXSize
                  and 0 <= row < self.dataset.RasterYSize)
        elevation = None
        if not inside:
            if not outside_as_nodata:
                raise ValueError("查询点位于栅格有效范围之外。")
        else:
            values = self.band.ReadAsArray(column, row, 1, 1)
            if values is None or values.size != 1:
                raise RuntimeError("GDAL 无法读取查询点的 1×1 像元。")
            raw = float(values[0, 0])
            if math.isfinite(raw) and not _is_nodata(raw, self.nodata):
                value = raw * self.scale + self.offset
                if math.isfinite(value):
                    elevation = value
        return {
            "longitude": longitude, "latitude": latitude,
            "column": column, "row": row, "elevation": elevation,
            "depth": -elevation if elevation is not None and elevation < 0 else None,
            "is_nodata": elevation is None,
        }
