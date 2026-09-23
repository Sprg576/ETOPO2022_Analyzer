"""面向界面的简短数据名称与分辨率，不改变数据源。"""

import math
import re
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QLabel, QSizePolicy
from qgis.core import QgsUnitTypes
from osgeo import gdal


def short_name(layer):
    name = layer.name()
    match = re.fullmatch(r"ETOPO_(\d{4})_v[\d.]+_(\d+)s_N90W180_(surface|bed)(?:\.tif)?", name, re.I)
    if match:
        return f"ETOPO{match[1]} {match[2]}s {match[3].title()}"
    return name


def resolution_text(layer):
    x, y = abs(layer.rasterUnitsPerPixelX()), abs(layer.rasterUnitsPerPixelY())
    crs = layer.crs().horizontalCrs()
    if not crs.isValid():
        crs = layer.crs()
    if crs.isGeographic():
        x, y, unit = x * 3600, y * 3600, "″"
    else:
        unit = " " + QgsUnitTypes.toAbbreviatedString(crs.mapUnits())
    return f"{x:.6g}{unit}" if math.isclose(x, y, rel_tol=1e-8) else f"{x:.6g}{unit} × {y:.6g}{unit}"


def band_details(layer):
    dataset = None
    try:
        dataset = gdal.Open(layer.source())
        band = dataset.GetRasterBand(1)
        unit = band.GetUnitType() or "未声明"
        if unit.lower() in ("metre", "meter", "metres", "meters"):
            unit = "m"
        return gdal.GetDataTypeName(band.DataType), unit, band.GetNoDataValue()
    except (RuntimeError, AttributeError):
        return "未知", "未声明", None
    finally:
        dataset = None


class SummaryLabel(QLabel):
    """单行省略显示，完整内容由 Tooltip 提供。"""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.full_text = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):
        self.full_text = text
        super().setText(self.fontMetrics().elidedText(text, Qt.ElideRight, max(1, self.contentsRect().width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.full_text)
