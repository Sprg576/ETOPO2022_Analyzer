"""
ETOPO2022 固定陆海分层设色与 Hillshade 叠加样式。

本模块只修改 QGIS 图层渲染方式，不修改源栅格数据。
"""

from __future__ import annotations

from qgis.PyQt.QtGui import QColor, QPainter

from qgis.core import (
    QgsColorRampShader,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandGrayRenderer,
    QgsSingleBandPseudoColorRenderer,
)


ETOPO_COLOR_RELIEF = (
    (-11000.0, "#081D58", "深海沟"),
    (-6000.0, "#0B3C8C", "深海"),
    (-4000.0, "#1464A0", "深海平原"),
    (-2000.0, "#2B8CBE", "大陆坡"),
    (-200.0, "#7BCCC4", "大陆架"),
    (0.0, "#D7F0EF", "海平面"),
    (1.0, "#2D7F3E", "陆地"),
    (200.0, "#79B85A", "低地"),
    (1000.0, "#D9C36A", "丘陵"),
    (2000.0, "#A97C50", "山地"),
    (4000.0, "#7A5230", "高山"),
    (6000.0, "#D9D2C3", "极高山"),
    (9000.0, "#FFFFFF", "最高地形"),
)


def _validate_raster_layer(layer: QgsRasterLayer) -> None:
    """确认图层可用于单波段栅格渲染。"""

    if layer is None:
        raise ValueError("栅格图层不能为空。")

    if not layer.isValid():
        raise RuntimeError("栅格图层无效。")

    if layer.bandCount() < 1:
        raise ValueError("栅格图层不包含可渲染波段。")


def apply_etopo_color_relief(
    layer: QgsRasterLayer,
) -> QgsSingleBandPseudoColorRenderer:
    """为 ETOPO 高程第一波段应用固定陆海分层设色。"""

    _validate_raster_layer(layer)

    color_ramp_shader = QgsColorRampShader()
    color_ramp_shader.setColorRampType(
        QgsColorRampShader.Interpolated
    )
    color_ramp_shader.setColorRampItemList(
        [
            QgsColorRampShader.ColorRampItem(
                value,
                QColor(color),
                label,
            )
            for value, color, label
            in ETOPO_COLOR_RELIEF
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
    renderer.setClassificationMin(
        ETOPO_COLOR_RELIEF[0][0]
    )
    renderer.setClassificationMax(
        ETOPO_COLOR_RELIEF[-1][0]
    )

    layer.setRenderer(renderer)
    layer.triggerRepaint()

    return renderer


def configure_hillshade_overlay(
    layer: QgsRasterLayer,
    opacity: float = 0.60,
) -> QgsSingleBandGrayRenderer:
    """把 Hillshade 图层设置为半透明正片叠底覆盖层。"""

    _validate_raster_layer(layer)

    if not 0.0 <= opacity <= 1.0:
        raise ValueError("Hillshade 透明度必须位于 0 到 1 之间。")

    renderer = QgsSingleBandGrayRenderer(
        layer.dataProvider(),
        1,
    )
    renderer.setOpacity(opacity)

    layer.setRenderer(renderer)
    layer.setBlendMode(
        QPainter.CompositionMode_Multiply
    )
    layer.triggerRepaint()

    return renderer
