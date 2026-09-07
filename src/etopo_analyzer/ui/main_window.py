"""
ETOPO2022 Analyzer 主窗口。

当前阶段：
F02 基础地图浏览界面。
F03 单点高程 / 水深查询。

已提供：
1. QgsMapCanvas 主地图
2. Pan
3. Zoom In
4. Zoom Out
5. Full Extent
6. Point Query
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QAction,
    QActionGroup,
    QMainWindow,
    QToolBar,
)

from qgis.core import QgsMapLayer

from etopo_analyzer.ui.map_canvas import (
    ETOPOMapCanvas,
)

from etopo_analyzer.ui.point_query_tool import (
    PointQueryMapTool,
)


class ETOPOAnalyzerMainWindow(QMainWindow):
    """
    ETOPO2022 Analyzer 主窗口。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "ETOPO2022 Analyzer"
        )

        self.resize(
            1200,
            700,
        )

        # -------------------------------------------------
        # 主 GIS 地图
        # -------------------------------------------------

        self.map_canvas = ETOPOMapCanvas(
            self
        )

        self.setCentralWidget(
            self.map_canvas
        )

        self._point_query_tool = None

        # -------------------------------------------------
        # 地图工具栏
        # -------------------------------------------------

        self._create_map_toolbar()

    def _create_map_toolbar(self) -> None:
        """
        创建 F02 基础地图工具栏。
        """

        toolbar = QToolBar(
            "地图工具",
            self,
        )

        toolbar.setObjectName(
            "MapToolbar"
        )

        self.addToolBar(
            toolbar
        )

        # Pan / Zoom In / Zoom Out
        # 属于互斥地图工具。
        tool_group = QActionGroup(
            self
        )

        tool_group.setExclusive(
            True
        )

        # -------------------------------------------------
        # Pan
        # -------------------------------------------------

        self.pan_action = QAction(
            "平移",
            self,
        )

        self.pan_action.setCheckable(
            True
        )

        self.pan_action.setChecked(
            True
        )

        self.pan_action.triggered.connect(
            self.map_canvas.activate_pan
        )

        tool_group.addAction(
            self.pan_action
        )

        toolbar.addAction(
            self.pan_action
        )

        # -------------------------------------------------
        # Zoom In
        # -------------------------------------------------

        self.zoom_in_action = QAction(
            "放大",
            self,
        )

        self.zoom_in_action.setCheckable(
            True
        )

        self.zoom_in_action.triggered.connect(
            self.map_canvas.activate_zoom_in
        )

        tool_group.addAction(
            self.zoom_in_action
        )

        toolbar.addAction(
            self.zoom_in_action
        )

        # -------------------------------------------------
        # Zoom Out
        # -------------------------------------------------

        self.zoom_out_action = QAction(
            "缩小",
            self,
        )

        self.zoom_out_action.setCheckable(
            True
        )

        self.zoom_out_action.triggered.connect(
            self.map_canvas.activate_zoom_out
        )

        tool_group.addAction(
            self.zoom_out_action
        )

        toolbar.addAction(
            self.zoom_out_action
        )

        # -------------------------------------------------
        # Point Query
        # -------------------------------------------------

        self.point_query_action = QAction(
            "单点查询",
            self,
        )

        self.point_query_action.setCheckable(
            True
        )

        self.point_query_action.setEnabled(
            False
        )

        self.point_query_action.triggered.connect(
            self.activate_point_query
        )

        tool_group.addAction(
            self.point_query_action
        )

        toolbar.addAction(
            self.point_query_action
        )

        toolbar.addSeparator()

        # -------------------------------------------------
        # Full Extent
        # -------------------------------------------------

        self.full_extent_action = QAction(
            "全图",
            self,
        )

        self.full_extent_action.triggered.connect(
            self.map_canvas.zoom_to_full_extent
        )

        toolbar.addAction(
            self.full_extent_action
        )

    def activate_point_query(self) -> None:
        """激活单点高程 / 水深查询工具。"""

        if self._point_query_tool is None:
            return

        self.map_canvas.setMapTool(
            self._point_query_tool
        )

        self.statusBar().showMessage(
            "单点查询：请在地图上单击。"
        )

    def _show_point_query_result(
        self,
        result: dict,
    ) -> None:
        """在状态栏显示单点查询结果。"""

        longitude = result["longitude"]
        latitude = result["latitude"]

        longitude_direction = (
            "E" if longitude >= 0.0 else "W"
        )

        latitude_direction = (
            "N" if latitude >= 0.0 else "S"
        )

        coordinate_text = (
            f"经度：{abs(longitude):.6f}° "
            f"{longitude_direction} | "
            f"纬度：{abs(latitude):.6f}° "
            f"{latitude_direction}"
        )

        if result["is_nodata"]:
            value_text = "无有效高程数据（NoData）"
        elif result["depth"] is not None:
            value_text = (
                f"近似水深：{result['depth']:.2f} m"
            )
        else:
            value_text = (
                f"高程：{result['elevation']:.2f} m"
            )

        self.statusBar().showMessage(
            f"{coordinate_text} | {value_text}"
        )

    def _show_point_query_error(
        self,
        message: str,
    ) -> None:
        """在状态栏显示单点查询错误。"""

        self.statusBar().showMessage(
            f"查询失败：{message}"
        )

    def show_layer(
        self,
        layer: QgsMapLayer,
    ) -> None:
        """
        在主地图中显示图层。
        """

        self.map_canvas.show_layer(
            layer
        )

        self._point_query_tool = (
            PointQueryMapTool(
                self.map_canvas,
                layer.source(),
            )
        )

        self._point_query_tool.query_succeeded.connect(
            self._show_point_query_result
        )

        self._point_query_tool.query_failed.connect(
            self._show_point_query_error
        )

        self.point_query_action.setEnabled(
            True
        )
