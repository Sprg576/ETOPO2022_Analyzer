"""WGS84 多边形校验及按块栅格化，避免生成全球尺寸的掩膜。"""

import json
import math

from osgeo import gdal, ogr, osr


def normalize_polygon(value):
    """返回独立的二维 GeoJSON Polygon；不支持跨日期变更线的环。"""
    if not isinstance(value, dict) or value.get("type") != "Polygon":
        raise ValueError("统计区域必须为 Polygon 多边形。")
    rings = value.get("coordinates")
    if not isinstance(rings, (list, tuple)) or not rings:
        raise ValueError("多边形至少需要三个不同的顶点。")
    normalized = []
    for ring in rings:
        points = []
        try:
            for point in ring:
                if len(point) != 2:
                    raise ValueError()
                x, y = map(float, point)
                if not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90):
                    raise ValueError()
                if not points or [x, y] != points[-1]:
                    points.append([x, y])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("多边形顶点必须是有效的 WGS84 经度、纬度。") from exc
        if len({tuple(p) for p in points}) < 3:
            raise ValueError("多边形至少需要三个不同的顶点。")
        if points[0] != points[-1]:
            points.append(points[0][:])
        if any(abs(a[0] - b[0]) > 180 for a, b in zip(points, points[1:])):
            raise ValueError("暂不支持跨越日期变更线的多边形，请分别绘制两侧区域。")
        normalized.append(points)
    result = dict(type="Polygon", coordinates=normalized)
    geometry = ogr.CreateGeometryFromJson(json.dumps(result))
    if geometry is None or geometry.IsEmpty() or not geometry.IsValid() or geometry.GetArea() <= 0:
        raise ValueError("多边形存在自相交、退化边或无效内环，请重新绘制。")
    return result


class PolygonMask:
    """每次仅创建一块 Byte 掩膜；像元中心规则由 GDAL 栅格化实现。"""

    def __init__(self, dataset, polygon):
        self.polygon = normalize_polygon(polygon)
        self.transform = dataset.GetGeoTransform()
        self.projection = dataset.GetProjection()
        geometry = ogr.CreateGeometryFromJson(json.dumps(self.polygon))
        xmin, xmax, ymin, ymax = geometry.GetEnvelope()
        gx, dx, _, gy, _, dy = self.transform
        x0 = max(0, math.floor((xmin - gx) / dx))
        x1 = min(dataset.RasterXSize, math.ceil((xmax - gx) / dx))
        y0 = max(0, math.floor((ymax - gy) / dy))
        y1 = min(dataset.RasterYSize, math.ceil((ymin - gy) / dy))
        if x0 >= x1 or y0 >= y1:
            raise ValueError("多边形与所选 DEM 没有重叠区域。")
        self.window = (x0, y0, x1, y1)
        self.source = ogr.GetDriverByName("Memory").CreateDataSource("")
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        self.layer = self.source.CreateLayer("roi", srs, ogr.wkbPolygon)
        feature = ogr.Feature(self.layer.GetLayerDefn())
        feature.SetGeometry(geometry)
        self.layer.CreateFeature(feature)

    def block(self, x, y, columns, rows):
        gx, dx, rx, gy, ry, dy = self.transform
        mask = gdal.GetDriverByName("MEM").Create("", columns, rows, 1, gdal.GDT_Byte)
        mask.SetGeoTransform((gx + x * dx + y * rx, dx, rx, gy + x * ry + y * dy, ry, dy))
        mask.SetProjection(self.projection)
        self.layer.ResetReading()
        status = gdal.RasterizeLayer(mask, [1], self.layer, burn_values=[1], options=["ALL_TOUCHED=FALSE"])
        if status != 0:
            raise RuntimeError("无法生成多边形统计掩膜。")
        return mask.ReadAsArray() != 0
