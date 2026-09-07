"""
ETOPO2022 Analyzer 主窗口。

当前阶段：
F02 基础地图浏览界面。

已提供：
1. QgsMapCanvas 主地图
2. Pan
3. Zoom In
4. Zoom Out
5. Full Extent
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