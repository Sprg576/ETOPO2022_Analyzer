"""
ETOPO2022 系统主 GIS 地图画布。

当前阶段功能：
1. 封装 QgsMapCanvas
2. 显示单个图层或多个叠加图层
3. 自动缩放至图层范围
4. 对复合 CRS 使用水平 CRS 作为二维地图目标 CRS
5. 提供地图平移（Pan）工具
6. 提供地图放大（Zoom In）工具
7. 提供地图缩小（Zoom Out）工具
8. 提供全图（Full Extent）功能
9. 启用地图渲染缓存

正式运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

from qgis.core import QgsMapLayer
from qgis.gui import (
    QgsMapCanvas,
    QgsMapToolPan,
    QgsMapToolZoom,
)


class ETOPOMapCanvas(QgsMapCanvas):
    """
    ETOPO2022 Analyzer 主地图画布。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumSize(800, 500)

        # 启用地图渲染缓存。
        self.setCachingEnabled(True)

        # 平移工具。
        self._pan_tool = QgsMapToolPan(self)

        # 放大工具。
        self._zoom_in_tool = QgsMapToolZoom(
            self,
            False,
        )

        # 缩小工具。
        self._zoom_out_tool = QgsMapToolZoom(
            self,
            True,
        )

        # 默认启用平移。
        self.activate_pan()

    def show_layer(
        self,
        layer: QgsMapLayer,
        zoom_to_layer: bool = True,
    ) -> None:
        """
        在地图画布中显示一个图层。
        """

        self.show_layers(
            [layer],
            zoom_to_layer=zoom_to_layer,
        )

    def show_layers(
        self,
        layers: list[QgsMapLayer],
        zoom_to_layer: bool = True,
    ) -> None:
        """按从上到下的顺序显示一个或多个有效图层。"""

        if not layers:
            raise ValueError(
                "待显示图层不能为空。"
            )

        for layer in layers:
            if layer is None:
                raise ValueError(
                    "待显示图层不能为空。"
                )

            if not layer.isValid():
                raise RuntimeError(
                    f"无效图层：{layer.name()}"
                )

        self.setLayers(layers)

        reference_layer = layers[-1]

        # QgsMapCanvas 是二维地图画布。
        # 对 EPSG:9518 等复合 CRS，只使用其水平 CRS。
        layer_crs = reference_layer.crs()

        if layer_crs.isValid():
            horizontal_crs = (
                layer_crs.horizontalCrs()
            )

            if horizontal_crs.isValid():
                self.setDestinationCrs(
                    horizontal_crs
                )
            else:
                self.setDestinationCrs(
                    layer_crs
                )

        if zoom_to_layer:
            self.setExtent(
                reference_layer.extent()
            )

        self.refresh()

    def activate_pan(self) -> None:
        """
        激活地图平移工具。
        """

        self.setMapTool(
            self._pan_tool
        )

    def activate_zoom_in(self) -> None:
        """
        激活地图放大工具。
        """

        self.setMapTool(
            self._zoom_in_tool
        )

    def activate_zoom_out(self) -> None:
        """
        激活地图缩小工具。
        """

        self.setMapTool(
            self._zoom_out_tool
        )

    def zoom_to_full_extent(self) -> None:
        """
        缩放至当前地图全部图层的完整范围。
        """

        self.zoomToFullExtent()

    def clear_layers(self) -> None:
        """
        清空地图画布中的图层。
        """

        self.setLayers([])
        self.refresh()
