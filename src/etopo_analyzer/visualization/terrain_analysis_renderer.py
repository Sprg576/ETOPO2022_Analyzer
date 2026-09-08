"""
F06-3 坡度与坡向栅格可视化。

本模块只修改 QGIS 栅格图层的渲染方式，不修改源 GeoTIFF。
坡向使用离散循环色带，Flat / NoData 保持为透明区域。
"""

from __future__ import annotations

from qgis.PyQt.QtGui import QColor

from qgis.core import (
    QgsColorRampShader,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
)


SLOPE_COLOR_CLASSES = (
    (2.0, "#1A9850", "0–2° 平坦"),
    (5.0, "#66BD63", "2–5° 缓坡"),
    (15.0, "#A6D96A", "5–15° 斜坡"),
    (25.0, "#FEE08B", "15–25° 陡坡"),
    (35.0, "#FDAE61", "25–35° 急坡"),
    (45.0, "#F46D43", "35–45° 极陡坡"),
    (90.0, "#A50026", ">45° 高陡坡"),
)


ASPECT_DIRECTION_CLASSES = (
    (22.5, "#E41A1C", "N"),
    (67.5, "#FF7F00", "NE"),
    (112.5, "#FFFF33", "E"),
    (157.5, "#4DAF4A", "SE"),
    (202.5, "#00BFC4", "S"),
    (247.5, "#377EB8", "SW"),
    (292.5, "#984EA3", "W"),
    (337.5, "#F781BF", "NW"),
    (360.0, "#E41A1C", "N"),
)


def _validate_raster_layer(layer: QgsRasterLayer) -> None:
    """确认图层可用于单波段栅格渲染。"""

    if layer is None:
        raise ValueError("栅格图层不能为空。")

    if not layer.isValid():
        raise RuntimeError("栅格图层无效。")

    if layer.bandCount() < 1:
        raise ValueError("栅格图层不包含可渲染波段。")


def _apply_discrete_renderer(
    layer: QgsRasterLayer,
    classes: tuple[tuple[float, str, str], ...],
    minimum: float,
    maximum: float,
) -> QgsSingleBandPseudoColorRenderer:
    """为第一波段应用固定离散分级色带。"""

    _validate_raster_layer(layer)

    layer.dataProvider().setUseSourceNoDataValue(
        1,
        True,
    )

    color_ramp_shader = QgsColorRampShader()
    color_ramp_shader.setColorRampType(
        QgsColorRampShader.Discrete
    )
    color_ramp_shader.setColorRampItemList(
        [
            QgsColorRampShader.ColorRampItem(
                upper_bound,
                QColor(color),
                label,
            )
            for upper_bound, color, label in classes
        ]
    )

    raster_shader = QgsRasterShader()
    raster_shader.setRasterShaderFunction(
        color_ramp_shader
    )

    renderer = QgsSingleBandPseudoColorRenderer(
        layer.dataProvider(),
        1,
        raster_shader,
    )
    renderer.setClassificationMin(minimum)
    renderer.setClassificationMax(maximum)

    layer.setRenderer(renderer)
    layer.triggerRepaint()

    return renderer


def apply_slope_color_relief(
    layer: QgsRasterLayer,
) -> QgsSingleBandPseudoColorRenderer:
    """为角度制坡度图层应用固定七级色带。"""

    return _apply_discrete_renderer(
        layer,
        SLOPE_COLOR_CLASSES,
        0.0,
        90.0,
    )


def apply_aspect_direction_colors(
    layer: QgsRasterLayer,
) -> QgsSingleBandPseudoColorRenderer:
    """为方位角制坡向图层应用八方向循环色带。"""

    return _apply_discrete_renderer(
        layer,
        ASPECT_DIRECTION_CLASSES,
        0.0,
        360.0,
    )
