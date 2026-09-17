"""F03 单点高程 / 水深查询，复用只读栅格采样规则。"""

from etopo_analyzer.core.raster_sampling import RasterSampler, _validate_longitude_latitude


def query_point_elevation(
    file_path: str,
    longitude: float,
    latitude: float,
    subdataset_name: str | None = None,
) -> dict:
    """查询一个 WGS84 位置，返回高程及负高程对应的近似水深。"""
    longitude, latitude = _validate_longitude_latitude(longitude, latitude)
    with RasterSampler(file_path, subdataset_name) as sampler:
        return sampler.sample(longitude, latitude)
