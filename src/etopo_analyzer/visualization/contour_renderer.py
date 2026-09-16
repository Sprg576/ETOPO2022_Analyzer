"""F07-3 等高线、等深线与零值线分类渲染。"""

from __future__ import annotations

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsLineSymbol,
    QgsRendererCategory,
    QgsVectorLayer,
    QgsWkbTypes,
)

from etopo_analyzer.core.contour_analysis import (
    CONTOUR_TYPE_DEPTH,
    CONTOUR_TYPE_ELEVATION,
    CONTOUR_TYPE_ZERO,
)


CONTOUR_STYLE_CLASSES = (
    (
        CONTOUR_TYPE_ELEVATION,
        "#8B5E3C",
        0.45,
        "等高线（> 0 m）",
    ),
    (
        CONTOUR_TYPE_DEPTH,
        "#2F6FED",
        0.45,
        "等深线（< 0 m）",
    ),
    (
        CONTOUR_TYPE_ZERO,
        "#26313D",
        0.8,
        "0 m 等值线",
    ),
)


def _validate_contour_layer(layer: QgsVectorLayer) -> None:
    """确认图层包含等值线分类渲染所需结构。"""

    if layer is None:
        raise ValueError("等值线图层不能为空。")

    if not layer.isValid():
        raise RuntimeError("等值线图层无效。")

    if (
        QgsWkbTypes.geometryType(layer.wkbType())
        != QgsWkbTypes.LineGeometry
    ):
        raise ValueError("等值线图层必须使用线几何。")

    field_names = set(layer.fields().names())
    missing_fields = {"ELEV", "TYPE"} - field_names

    if missing_fields:
        raise ValueError(
            "等值线图层缺少字段："
            + "、".join(sorted(missing_fields))
        )


def apply_contour_classification(
    layer: QgsVectorLayer,
) -> QgsCategorizedSymbolRenderer:
    """按 TYPE 字段应用固定的陆地、海底和零值线样式。"""

    _validate_contour_layer(layer)

    categories = []

    for value, color, width, label in CONTOUR_STYLE_CLASSES:
        symbol = QgsLineSymbol.createSimple(
            {
                "color": color,
                "width": str(width),
                "capstyle": "round",
                "joinstyle": "round",
            }
        )
        categories.append(
            QgsRendererCategory(
                value,
                symbol,
                label,
            )
        )

    renderer = QgsCategorizedSymbolRenderer(
        "TYPE",
        categories,
    )
    layer.setRenderer(renderer)
    layer.triggerRepaint()

    return renderer
