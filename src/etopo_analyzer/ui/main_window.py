"""
ETOPO2022 Analyzer 主窗口。

当前阶段：
F02 基础地图浏览界面。
F03 单点高程 / 水深查询。
F04 经纬度矩形区域裁剪。
F05 地形与海底地形可视化。
F06 坡度与坡向分析。

已提供：
1. QgsMapCanvas 主地图
2. Pan
3. Zoom In
4. Zoom Out
5. Full Extent
6. Point Query
7. Rectangle Clip
8. Color Relief
9. Local UTM Hillshade
10. Slope
11. Aspect
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAction,
    QActionGroup,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qgis.core import QgsMapLayer, QgsProject

from etopo_analyzer.core.layer_manager import (
    add_raster_layer,
)

from etopo_analyzer.core.raster_clip import (
    clip_raster_by_bounds,
)

from etopo_analyzer.core.hillshade import (
    generate_hillshade,
    project_raster_to_local_utm,
)

from etopo_analyzer.core.terrain_analysis import (
    generate_aspect,
    generate_slope,
)

from etopo_analyzer.ui.map_canvas import (
    ETOPOMapCanvas,
)

from etopo_analyzer.ui.point_query_tool import (
    PointQueryMapTool,
)

from etopo_analyzer.ui.rectangle_selection_tool import (
    RectangleSelectionMapTool,
)

from etopo_analyzer.ui.theme import LIGHT_THEME

from etopo_analyzer.visualization.terrain_renderer import (
    apply_etopo_color_relief,
    configure_hillshade_overlay,
)

from etopo_analyzer.visualization.terrain_analysis_renderer import (
    apply_aspect_direction_colors,
    apply_slope_color_relief,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLIP_OUTPUT_DIR = PROJECT_ROOT / "outputs"
ICON_DIR = Path(__file__).resolve().parent / "icons"


class ETOPOAnalyzerMainWindow(QMainWindow):
    """
    ETOPO2022 Analyzer 主窗口。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "ETOPO2022 Analyzer - 基于 ETOPO2022 的全球地形与海底地形综合分析系统"
        )

        self.setWindowIcon(
            self._icon("app.svg")
        )

        self.setObjectName(
            "ETOPOAnalyzerMainWindow"
        )

        self.setStyleSheet(
            LIGHT_THEME
        )

        self.resize(
            1360,
            820,
        )

        self.setMinimumSize(
            1080,
            640,
        )

        # -------------------------------------------------
        # 主 GIS 地图
        # -------------------------------------------------

        self.map_canvas = ETOPOMapCanvas(
            self
        )

        self.map_canvas.setCanvasColor(
            QColor("#E9EDF2")
        )

        self.map_tabs = QTabWidget(self)
        self.map_tabs.setObjectName("MapTabs")
        self.map_tabs.setDocumentMode(True)
        self.map_tabs.addTab(
            self.map_canvas,
            "地图视图",
        )

        self.setCentralWidget(
            self.map_tabs
        )

        self._point_query_tool = None
        self._rectangle_selection_tool = None

        # active 保存 F03/F04 分析源；display 保存当前画面图层。
        self._active_raster_path = None
        self._active_raster_layer = None
        self._display_raster_layer = None
        self._hillshade_layer = None
        self._slope_layer = None
        self._aspect_layer = None
        self._clip_output_directory = (
            DEFAULT_CLIP_OUTPUT_DIR
        )
        self._layer_items = {}
        self._layer_groups = {}
        self._managed_layers = {}

        # -------------------------------------------------
        # 主窗口结构
        # -------------------------------------------------

        self._create_map_toolbar()
        self._create_menu_bar()
        self._create_layer_dock()
        self._create_analysis_dock()
        self._create_status_bar()

        self.resizeDocks(
            [
                self.layer_dock,
                self.analysis_dock,
            ],
            [260, 300],
            Qt.Horizontal,
        )

    @staticmethod
    def _icon(file_name: str) -> QIcon:
        """读取内置线性 SVG 图标。"""

        return QIcon(
            str(ICON_DIR / file_name)
        )

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

        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )

        self.addToolBar(
            toolbar
        )

        self.map_toolbar = toolbar

        # -------------------------------------------------
        # Open Raster
        # -------------------------------------------------

        self.open_raster_action = QAction(
            self._icon("open.svg"),
            "打开栅格",
            self,
        )

        self.open_raster_action.setToolTip(
            "打开 GeoTIFF 或 NetCDF 栅格"
        )

        self.open_raster_action.triggered.connect(
            self.open_raster
        )

        toolbar.addAction(
            self.open_raster_action
        )

        toolbar.addSeparator()

        # Pan / Zoom In / Zoom Out
        # 属于互斥地图工具。
        self._map_tool_group = QActionGroup(
            self
        )

        self._map_tool_group.setExclusive(
            True
        )

        # -------------------------------------------------
        # Pan
        # -------------------------------------------------

        self.pan_action = QAction(
            self._icon("pan.svg"),
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

        self._map_tool_group.addAction(
            self.pan_action
        )

        toolbar.addAction(
            self.pan_action
        )

        # -------------------------------------------------
        # Zoom In
        # -------------------------------------------------

        self.zoom_in_action = QAction(
            self._icon("zoom-in.svg"),
            "放大",
            self,
        )

        self.zoom_in_action.setCheckable(
            True
        )

        self.zoom_in_action.triggered.connect(
            self.map_canvas.activate_zoom_in
        )

        self._map_tool_group.addAction(
            self.zoom_in_action
        )

        toolbar.addAction(
            self.zoom_in_action
        )

        # -------------------------------------------------
        # Zoom Out
        # -------------------------------------------------

        self.zoom_out_action = QAction(
            self._icon("zoom-out.svg"),
            "缩小",
            self,
        )

        self.zoom_out_action.setCheckable(
            True
        )

        self.zoom_out_action.triggered.connect(
            self.map_canvas.activate_zoom_out
        )

        self._map_tool_group.addAction(
            self.zoom_out_action
        )

        toolbar.addAction(
            self.zoom_out_action
        )

        # -------------------------------------------------
        # Point Query
        # -------------------------------------------------

        self.point_query_action = QAction(
            self._icon("query.svg"),
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

        self._map_tool_group.addAction(
            self.point_query_action
        )

        toolbar.addAction(
            self.point_query_action
        )

        # -------------------------------------------------
        # Rectangle Clip
        # -------------------------------------------------

        self.rectangle_clip_action = QAction(
            self._icon("clip.svg"),
            "矩形裁剪",
            self,
        )

        self.rectangle_clip_action.setCheckable(
            True
        )

        self.rectangle_clip_action.setEnabled(
            False
        )

        self.rectangle_clip_action.triggered.connect(
            self.activate_rectangle_clip
        )

        self._map_tool_group.addAction(
            self.rectangle_clip_action
        )

        toolbar.addAction(
            self.rectangle_clip_action
        )

        # -------------------------------------------------
        # Color Relief
        # -------------------------------------------------

        self.color_relief_action = QAction(
            self._icon("color-relief.svg"),
            "分层设色",
            self,
        )

        self.color_relief_action.setEnabled(
            False
        )

        self.color_relief_action.triggered.connect(
            self.apply_color_relief
        )

        # -------------------------------------------------
        # Hillshade
        # -------------------------------------------------

        self.hillshade_action = QAction(
            self._icon("hillshade.svg"),
            "山体阴影",
            self,
        )

        self.hillshade_action.setEnabled(
            False
        )

        self.hillshade_action.triggered.connect(
            self.create_hillshade
        )

        # -------------------------------------------------
        # Slope
        # -------------------------------------------------

        self.slope_action = QAction(
            self._icon("slope.svg"),
            "坡度",
            self,
        )

        self.slope_action.setEnabled(
            False
        )

        self.slope_action.triggered.connect(
            self.create_slope
        )

        # -------------------------------------------------
        # Aspect
        # -------------------------------------------------

        self.aspect_action = QAction(
            self._icon("aspect.svg"),
            "坡向",
            self,
        )

        self.aspect_action.setEnabled(
            False
        )

        self.aspect_action.triggered.connect(
            self.create_aspect
        )

        # -------------------------------------------------
        # Full Extent
        # -------------------------------------------------

        self.full_extent_action = QAction(
            self._icon("full-extent.svg"),
            "全图",
            self,
        )

        self.full_extent_action.triggered.connect(
            self.map_canvas.zoom_to_full_extent
        )

        toolbar.insertAction(
            self.pan_action,
            self.full_extent_action
        )

        toolbar.insertSeparator(
            self.pan_action
        )

        toolbar.addSeparator()

        # 后台任务尚未实现，先保留不可用的取消入口。
        self.cancel_task_action = QAction(
            self._icon("cancel.svg"),
            "取消任务",
            self,
        )
        self.cancel_task_action.setEnabled(False)
        self.cancel_task_action.setToolTip(
            "后台任务功能将在后续阶段提供"
        )
        toolbar.addAction(
            self.cancel_task_action
        )

    def _create_menu_bar(self) -> None:
        """创建与功能阶段对应的主菜单。"""

        file_menu = self.menuBar().addMenu("文件(&F)")
        file_menu.addAction(self.open_raster_action)
        file_menu.addSeparator()

        self.exit_action = QAction(
            "退出",
            self,
        )
        self.exit_action.triggered.connect(
            self.close
        )
        file_menu.addAction(self.exit_action)

        data_menu = self.menuBar().addMenu("数据处理(&D)")
        data_menu.addAction(self.point_query_action)
        data_menu.addAction(self.rectangle_clip_action)

        terrain_menu = self.menuBar().addMenu("地形分析(&T)")
        terrain_menu.addAction(self.color_relief_action)
        terrain_menu.addAction(self.hillshade_action)
        terrain_menu.addSeparator()
        terrain_menu.addAction(self.slope_action)
        terrain_menu.addAction(self.aspect_action)

        for title in (
            "剖面分析(&P)",
            "统计分析(&S)",
            "导出(&E)",
        ):
            menu = self.menuBar().addMenu(title)
            placeholder = QAction(
                "将在后续功能阶段提供",
                self,
            )
            placeholder.setEnabled(False)
            menu.addAction(placeholder)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        self.about_action = QAction(
            "关于",
            self,
        )
        self.about_action.triggered.connect(
            self._show_about_dialog
        )
        help_menu.addAction(self.about_action)

    def _create_layer_dock(self) -> None:
        """创建左侧图层管理与属性面板。"""

        self.layer_dock = QDockWidget(
            "图层管理",
            self,
        )
        self.layer_dock.setObjectName(
            "LayerDock"
        )
        self.layer_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
        )
        self.layer_dock.setMinimumWidth(210)
        self.layer_dock.setMaximumWidth(340)

        splitter = QSplitter(
            Qt.Vertical,
            self.layer_dock,
        )
        splitter.setObjectName("LayerSplitter")

        tree_panel = QWidget(splitter)
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(0, 0, 0, 6)
        tree_layout.setSpacing(3)

        self.layer_tree = QTreeWidget(tree_panel)
        self.layer_tree.setObjectName(
            "LayerTree"
        )
        self.layer_tree.setHeaderHidden(True)
        self.layer_tree.setRootIsDecorated(True)
        self.layer_tree.setUniformRowHeights(True)
        self.layer_tree.setIndentation(16)
        self.layer_tree.setTextElideMode(
            Qt.ElideRight
        )
        self.layer_tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.layer_tree.itemChanged.connect(
            self._change_layer_visibility
        )
        self.layer_tree.currentItemChanged.connect(
            self._update_layer_properties
        )
        tree_layout.addWidget(self.layer_tree)

        hint = QLabel(
            "勾选控制地图可见性",
            tree_panel,
        )
        hint.setObjectName("LayerPanelHint")
        hint.setContentsMargins(10, 2, 10, 0)
        tree_layout.addWidget(hint)

        for group_name in (
            "源数据",
            "裁剪结果",
            "派生栅格",
            "辅助数据",
        ):
            group_item = QTreeWidgetItem(
                self.layer_tree,
                [group_name],
            )
            group_item.setIcon(
                0,
                self._icon("folder.svg"),
            )
            group_item.setFlags(
                Qt.ItemIsEnabled
            )
            group_font = group_item.font(0)
            group_font.setBold(True)
            group_item.setFont(0, group_font)
            group_item.setExpanded(True)
            self._layer_groups[group_name] = group_item

        properties_panel = QWidget(splitter)
        properties_panel.setObjectName(
            "LayerPropertiesPanel"
        )
        properties_layout = QVBoxLayout(
            properties_panel
        )
        properties_layout.setContentsMargins(0, 0, 0, 0)
        properties_layout.setSpacing(0)

        properties_title = QLabel(
            "图层属性",
            properties_panel,
        )
        properties_title.setObjectName(
            "PanelTitle"
        )
        properties_layout.addWidget(properties_title)

        self.layer_properties_table = QTableWidget(
            properties_panel
        )
        self.layer_properties_table.setObjectName(
            "LayerPropertiesTable"
        )
        self.layer_properties_table.setColumnCount(2)
        self.layer_properties_table.setRowCount(0)
        self.layer_properties_table.horizontalHeader().hide()
        self.layer_properties_table.verticalHeader().hide()
        self.layer_properties_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.layer_properties_table.setSelectionMode(
            QAbstractItemView.NoSelection
        )
        self.layer_properties_table.setFocusPolicy(
            Qt.NoFocus
        )
        self.layer_properties_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        self.layer_properties_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        properties_layout.addWidget(
            self.layer_properties_table
        )

        self._show_empty_layer_properties()

        splitter.addWidget(tree_panel)
        splitter.addWidget(properties_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([530, 210])

        self.layer_dock.setWidget(splitter)
        self.addDockWidget(
            Qt.LeftDockWidgetArea,
            self.layer_dock,
        )

    def _show_empty_layer_properties(self) -> None:
        """显示未选择图层时的属性占位内容。"""

        self._set_layer_properties(
            [("名称", "未选择图层")]
        )

    def _set_layer_properties(
        self,
        properties: list[tuple[str, str]],
    ) -> None:
        """更新左侧属性表。"""

        self.layer_properties_table.setRowCount(
            len(properties)
        )

        for row, (name, value) in enumerate(properties):
            name_item = QTableWidgetItem(name)
            value_item = QTableWidgetItem(value)
            value_item.setToolTip(value)
            self.layer_properties_table.setItem(
                row,
                0,
                name_item,
            )
            self.layer_properties_table.setItem(
                row,
                1,
                value_item,
            )

        self.layer_properties_table.resizeRowsToContents()

    def _update_layer_properties(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        """显示图层树当前选中栅格的基本属性。"""

        del previous

        if current is None:
            self._show_empty_layer_properties()
            return

        layer_id = current.data(
            0,
            Qt.UserRole,
        )
        layer = self._managed_layers.get(layer_id)

        if layer is None:
            self._show_empty_layer_properties()
            return

        layer_crs = layer.crs()
        horizontal_crs = layer_crs.horizontalCrs()
        display_crs = (
            horizontal_crs
            if horizontal_crs.isValid()
            else layer_crs
        )
        extent = layer.extent()
        provider = layer.dataProvider()
        data_type = str(
            provider.sourceDataType(1)
        ).removeprefix("DataType.")

        properties = [
            ("名称", layer.name()),
            ("类型", "栅格"),
            (
                "分辨率",
                f"{layer.rasterUnitsPerPixelX():.6g} × "
                f"{layer.rasterUnitsPerPixelY():.6g}",
            ),
            ("波段数", str(layer.bandCount())),
            ("数据类型", data_type),
            (
                "空间参考",
                display_crs.authid()
                or display_crs.description(),
            ),
            (
                "行列数",
                f"{layer.width()} × {layer.height()}",
            ),
            (
                "范围",
                f"W {extent.xMinimum():.4f}  "
                f"E {extent.xMaximum():.4f}\n"
                f"S {extent.yMinimum():.4f}  "
                f"N {extent.yMaximum():.4f}",
            ),
        ]
        self._set_layer_properties(properties)

    def _create_analysis_dock(self) -> None:
        """创建右侧 ArcGIS 风格地形分析面板。"""

        self.analysis_dock = QDockWidget(
            "地形分析",
            self,
        )
        self.analysis_dock.setObjectName(
            "AnalysisDock"
        )
        self.analysis_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
        )
        self.analysis_dock.setMinimumWidth(280)
        self.analysis_dock.setMaximumWidth(400)

        scroll_area = QScrollArea(
            self.analysis_dock
        )
        scroll_area.setObjectName(
            "AnalysisScrollArea"
        )
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        container = QWidget(scroll_area)
        container.setObjectName(
            "AnalysisPanel"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        source_content = QWidget(container)
        source_content.setObjectName("SectionBody")
        source_layout = QFormLayout(source_content)
        source_layout.setContentsMargins(10, 8, 10, 10)
        source_layout.setHorizontalSpacing(8)
        source_layout.setVerticalSpacing(7)
        source_layout.setRowWrapPolicy(
            QFormLayout.WrapLongRows
        )

        self.analysis_source_label = QLabel(
            "未加载",
            source_content,
        )
        self.analysis_source_label.setObjectName(
            "SourceValue"
        )
        self.analysis_source_label.setWordWrap(True)
        self.analysis_source_label.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        self.analysis_crs_label = QLabel(
            "--",
            source_content,
        )
        self.analysis_size_label = QLabel(
            "--",
            source_content,
        )
        source_layout.addRow(
            "分析源",
            self.analysis_source_label,
        )
        source_layout.addRow(
            "水平 CRS",
            self.analysis_crs_label,
        )
        source_layout.addRow(
            "行列数",
            self.analysis_size_label,
        )
        self._add_collapsible_section(
            layout,
            "当前数据",
            source_content,
        )

        visualization_content = QWidget(container)
        visualization_content.setObjectName(
            "SectionBody"
        )
        visualization_layout = QVBoxLayout(
            visualization_content
        )
        visualization_layout.setContentsMargins(
            10,
            8,
            10,
            10,
        )
        visualization_layout.setSpacing(6)
        visualization_layout.addWidget(
            self._panel_button(
                self.color_relief_action
            )
        )

        hillshade_form = QFormLayout()
        hillshade_form.setContentsMargins(0, 4, 0, 2)
        hillshade_form.setHorizontalSpacing(8)
        hillshade_form.setVerticalSpacing(6)

        self.hillshade_azimuth_spin = QDoubleSpinBox(
            visualization_content
        )
        self.hillshade_azimuth_spin.setRange(0.0, 360.0)
        self.hillshade_azimuth_spin.setDecimals(1)
        self.hillshade_azimuth_spin.setSingleStep(5.0)
        self.hillshade_azimuth_spin.setValue(315.0)
        self.hillshade_azimuth_spin.setSuffix("°")

        self.hillshade_altitude_spin = QDoubleSpinBox(
            visualization_content
        )
        self.hillshade_altitude_spin.setRange(1.0, 90.0)
        self.hillshade_altitude_spin.setDecimals(1)
        self.hillshade_altitude_spin.setSingleStep(5.0)
        self.hillshade_altitude_spin.setValue(45.0)
        self.hillshade_altitude_spin.setSuffix("°")

        hillshade_form.addRow(
            "方位角",
            self.hillshade_azimuth_spin,
        )
        hillshade_form.addRow(
            "高度角",
            self.hillshade_altitude_spin,
        )
        visualization_layout.addLayout(hillshade_form)
        visualization_layout.addWidget(
            self._panel_button(
                self.hillshade_action,
                primary=True,
            )
        )
        self._add_collapsible_section(
            layout,
            "地形可视化",
            visualization_content,
        )

        terrain_content = QWidget(container)
        terrain_content.setObjectName("SectionBody")
        terrain_layout = QVBoxLayout(
            terrain_content
        )
        terrain_layout.setContentsMargins(10, 8, 10, 10)
        terrain_layout.setSpacing(6)

        method_label = QLabel(
            "算法：GDAL Horn\n输出：角度制坡度 / 方位角坡向",
            terrain_content,
        )
        method_label.setObjectName("PanelHint")
        method_label.setWordWrap(True)
        method_label.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        terrain_layout.addWidget(method_label)
        terrain_layout.addWidget(
            self._panel_button(
                self.slope_action
            )
        )
        terrain_layout.addWidget(
            self._panel_button(
                self.aspect_action
            )
        )

        local_analysis_hint = QLabel(
            "坡度、坡向和阴影要求局部范围的经纬度跨度不超过 6°。",
            terrain_content,
        )
        local_analysis_hint.setObjectName(
            "PanelHint"
        )
        local_analysis_hint.setWordWrap(True)
        local_analysis_hint.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        terrain_layout.addWidget(local_analysis_hint)
        self._add_collapsible_section(
            layout,
            "坡度与坡向",
            terrain_content,
        )
        layout.addStretch(1)

        scroll_area.setWidget(container)
        self.analysis_dock.setWidget(scroll_area)
        self.addDockWidget(
            Qt.RightDockWidgetArea,
            self.analysis_dock,
        )

    def _add_collapsible_section(
        self,
        parent_layout: QVBoxLayout,
        title: str,
        content: QWidget,
    ) -> None:
        """向分析面板加入可折叠分段。"""

        header = QToolButton(self)
        header.setObjectName("SectionHeader")
        header.setText(title)
        header.setCheckable(True)
        header.setChecked(True)
        header.setArrowType(Qt.DownArrow)
        header.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )
        header.toggled.connect(
            lambda checked, button=header, body=content: (
                self._toggle_section(button, body, checked)
            )
        )
        parent_layout.addWidget(header)
        parent_layout.addWidget(content)

    @staticmethod
    def _toggle_section(
        header: QToolButton,
        content: QWidget,
        expanded: bool,
    ) -> None:
        """切换分析面板分段的展开状态。"""

        header.setArrowType(
            Qt.DownArrow
            if expanded
            else Qt.RightArrow
        )
        content.setVisible(expanded)

    def _panel_button(
        self,
        action: QAction,
        primary: bool = False,
    ) -> QToolButton:
        """创建与 QAction 状态同步的面板按钮。"""

        button = QToolButton(self)
        button.setObjectName(
            "PanelActionButton"
        )
        button.setDefaultAction(action)
        button.setProperty(
            "primary",
            primary,
        )
        button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )
        button.setIconSize(QSize(18, 18))
        button.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        return button

    def _create_status_bar(self) -> None:
        """创建地图信息与任务状态栏。"""

        status_bar = self.statusBar()
        status_bar.setObjectName("MainStatusBar")

        self.longitude_status_label = QLabel(
            "经度：--"
        )
        self.latitude_status_label = QLabel(
            "纬度：--"
        )
        self.elevation_status_label = QLabel(
            "高程/水深：--"
        )
        self.crs_status_label = QLabel(
            "CRS：--"
        )
        self.resolution_status_label = QLabel(
            "分辨率：--"
        )

        for label in (
            self.longitude_status_label,
            self.latitude_status_label,
            self.elevation_status_label,
            self.crs_status_label,
            self.resolution_status_label,
        ):
            status_bar.addPermanentWidget(label)

        status_bar.showMessage("就绪")

    def open_raster(self) -> None:
        """通过文件选择器加载 GeoTIFF 或 NetCDF 栅格。"""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开 ETOPO2022 栅格",
            str(PROJECT_ROOT / "data"),
            "栅格数据 (*.tif *.tiff *.nc);;所有文件 (*.*)",
        )

        if not file_path:
            return

        try:
            layer = add_raster_layer(file_path)
            self.show_layer(
                layer,
                layer_group="源数据",
            )
        except (
            FileNotFoundError,
            ValueError,
            RuntimeError,
        ) as exc:
            self.statusBar().showMessage(
                f"打开失败：{exc}"
            )
            return

        self.statusBar().showMessage(
            f"已加载：{Path(file_path).name}"
        )

    def _show_about_dialog(self) -> None:
        """显示简明系统信息。"""

        QMessageBox.about(
            self,
            "关于 ETOPO2022 Analyzer",
            "ETOPO2022 全球地形与海底地形综合分析系统\n"
            "基于 QGIS 3.44 LTR、PyQGIS 与 GDAL。",
        )

    def _register_layer(
        self,
        layer: QgsMapLayer,
        group_name: str,
    ) -> QTreeWidgetItem:
        """把 QGIS 图层登记到左侧图层树。"""

        if layer.id() in self._layer_items:
            return self._layer_items[layer.id()]

        group_item = self._layer_groups[group_name]
        self.layer_tree.blockSignals(True)

        try:
            layer_item = QTreeWidgetItem(
                group_item,
                [layer.name()],
            )
            layer_item.setData(
                0,
                Qt.UserRole,
                layer.id(),
            )
            layer_item.setFlags(
                Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
                | Qt.ItemIsUserCheckable
            )
            layer_item.setCheckState(
                0,
                Qt.Unchecked,
            )
            layer_item.setToolTip(
                0,
                layer.source(),
            )
            layer_item.setIcon(
                0,
                self._layer_icon(layer, group_name),
            )
        finally:
            self.layer_tree.blockSignals(False)

        self._layer_items[layer.id()] = layer_item
        self._managed_layers[layer.id()] = layer
        group_item.setExpanded(True)

        return layer_item

    def _layer_icon(
        self,
        layer: QgsMapLayer,
        group_name: str,
    ) -> QIcon:
        """按结果类型为图层树选择统一线性图标。"""

        if group_name == "裁剪结果":
            return self._icon("clip.svg")

        layer_key = (
            f"{layer.name()} {layer.source()}"
        ).lower()
        for result_key, icon_name in (
            ("hillshade", "hillshade.svg"),
            ("slope", "slope.svg"),
            ("aspect", "aspect.svg"),
        ):
            if result_key in layer_key:
                return self._icon(icon_name)

        return self._icon("raster.svg")

    def _sync_layer_tree_visibility(self) -> None:
        """按 Canvas 当前图层同步图层树勾选状态。"""

        visible_layer_ids = {
            layer.id()
            for layer in self.map_canvas.layers()
        }

        self.layer_tree.blockSignals(True)

        try:
            for layer_id, item in self._layer_items.items():
                state = (
                    Qt.Checked
                    if layer_id in visible_layer_ids
                    else Qt.Unchecked
                )
                item.setCheckState(0, state)
        finally:
            self.layer_tree.blockSignals(False)

    def _change_layer_visibility(
        self,
        item: QTreeWidgetItem,
        column: int,
    ) -> None:
        """应用图层树中的可见性变更。"""

        layer_id = item.data(
            column,
            Qt.UserRole,
        )

        if not layer_id:
            return

        layer = self._managed_layers.get(
            layer_id
        )

        if layer is None:
            return

        visible_layers = list(
            self.map_canvas.layers()
        )

        if item.checkState(column) == Qt.Checked:
            if layer not in visible_layers:
                visible_layers.insert(0, layer)
        else:
            visible_layers = [
                visible_layer
                for visible_layer in visible_layers
                if visible_layer.id() != layer_id
            ]

        if visible_layers:
            self.map_canvas.show_layers(
                visible_layers,
                zoom_to_layer=False,
            )
        else:
            self.map_canvas.clear_layers()

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
            status_value_text = "NoData"
        elif result["depth"] is not None:
            value_text = (
                f"近似水深：{result['depth']:.2f} m"
            )
            status_value_text = (
                f"水深 {result['depth']:.2f} m"
            )
        else:
            value_text = (
                f"高程：{result['elevation']:.2f} m"
            )
            status_value_text = (
                f"高程 {result['elevation']:.2f} m"
            )

        self.longitude_status_label.setText(
            f"经度：{abs(longitude):.6f}° {longitude_direction}"
        )
        self.latitude_status_label.setText(
            f"纬度：{abs(latitude):.6f}° {latitude_direction}"
        )
        self.elevation_status_label.setText(
            f"高程/水深：{status_value_text}"
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

    def activate_rectangle_clip(self) -> None:
        """激活经纬度矩形裁剪工具。"""

        if self._rectangle_selection_tool is None:
            return

        self.map_canvas.setMapTool(
            self._rectangle_selection_tool
        )

        self.statusBar().showMessage(
            "矩形裁剪：请按住左键拖拽选择范围。"
        )

    def _next_clip_output_path(self) -> Path:
        """生成不会覆盖已有文件的裁剪输出路径。"""

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        return (
            self._clip_output_directory
            / f"ETOPO2022_clip_{timestamp}.tif"
        )

    def _clip_selected_bounds(
        self,
        bounds: dict,
    ) -> None:
        """裁剪框选范围并自动加载结果图层。"""

        if self._active_raster_path is None:
            self.statusBar().showMessage(
                "裁剪失败：当前没有可裁剪的栅格图层。"
            )
            return

        output_path = self._next_clip_output_path()

        self.statusBar().showMessage(
            "正在裁剪，请稍候……"
        )

        try:
            result = clip_raster_by_bounds(
                self._active_raster_path,
                str(output_path),
                bounds["west"],
                bounds["south"],
                bounds["east"],
                bounds["north"],
            )

            output_layer = add_raster_layer(
                result["output_path"],
                output_path.stem,
            )
        except (
            FileNotFoundError,
            FileExistsError,
            KeyError,
            ValueError,
            RuntimeError,
        ) as exc:
            self.statusBar().showMessage(
                f"裁剪失败：{exc}"
            )
            return

        # 裁剪结果成为新的分析源，后续查询和分析都以它为准。
        self.show_layer(
            output_layer,
            layer_group="裁剪结果",
        )

        self.map_canvas.activate_pan()
        self.pan_action.setChecked(True)

        self.statusBar().showMessage(
            f"裁剪完成：{output_path.name} | "
            f"{result['width']} × {result['height']} 像元"
        )

    def _show_rectangle_selection_error(
        self,
        message: str,
    ) -> None:
        """在状态栏显示矩形框选错误。"""

        self.statusBar().showMessage(
            f"框选失败：{message}"
        )

    def apply_color_relief(self) -> None:
        """为当前高程图层应用固定陆海分层设色。"""

        if self._display_raster_layer is None:
            return

        try:
            apply_etopo_color_relief(
                self._display_raster_layer
            )
        except (ValueError, RuntimeError) as exc:
            self.statusBar().showMessage(
                f"分层设色失败：{exc}"
            )
            return

        self.map_canvas.refresh()
        self.statusBar().showMessage(
            "分层设色完成：已应用固定陆海地形色带。"
        )

    def _next_hillshade_output_paths(
        self,
    ) -> tuple[Path, Path]:
        """生成本次局部投影和 Hillshade 输出路径。"""

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        projected_path = (
            self._clip_output_directory
            / f"ETOPO2022_utm_{timestamp}.tif"
        )
        hillshade_path = (
            self._clip_output_directory
            / f"ETOPO2022_hillshade_{timestamp}.tif"
        )

        return projected_path, hillshade_path

    def create_hillshade(self) -> None:
        """生成局部米制 DEM，并与 Hillshade 组合显示。"""

        if self._active_raster_path is None:
            return

        projected_path, hillshade_path = (
            self._next_hillshade_output_paths()
        )
        projected_layer = None
        hillshade_layer = None
        azimuth = self.hillshade_azimuth_spin.value()
        altitude = self.hillshade_altitude_spin.value()

        self.statusBar().showMessage(
            "正在建立局部米制投影并生成 Hillshade……"
        )

        try:
            # 始终从活动分析 DEM 建立米制中间数据。
            projection_result = (
                project_raster_to_local_utm(
                    self._active_raster_path,
                    str(projected_path),
                )
            )
            hillshade_result = generate_hillshade(
                projection_result["output_path"],
                str(hillshade_path),
                azimuth=azimuth,
                altitude=altitude,
            )

            projected_layer = add_raster_layer(
                projection_result["output_path"],
                projected_path.stem,
            )
            hillshade_layer = add_raster_layer(
                hillshade_result["output_path"],
                hillshade_path.stem,
            )

            apply_etopo_color_relief(
                projected_layer
            )
            configure_hillshade_overlay(
                hillshade_layer
            )
        except (
            FileNotFoundError,
            FileExistsError,
            ValueError,
            RuntimeError,
        ) as exc:
            for layer in (
                hillshade_layer,
                projected_layer,
            ):
                if layer is not None:
                    QgsProject.instance().removeMapLayer(
                        layer.id()
                    )

            for path in (
                hillshade_path,
                projected_path,
            ):
                if path.exists():
                    path.unlink()

            self.statusBar().showMessage(
                f"Hillshade 生成失败：{exc}"
            )
            return

        # Hillshade 只改变显示组合，不替换 F03/F04 的分析源。
        self.map_canvas.show_layers(
            [
                hillshade_layer,
                projected_layer,
            ]
        )
        self._display_raster_layer = projected_layer
        self._hillshade_layer = hillshade_layer
        self._slope_layer = None
        self._aspect_layer = None
        self.color_relief_action.setEnabled(True)
        self._register_layer(
            projected_layer,
            "辅助数据",
        )
        hillshade_item = self._register_layer(
            hillshade_layer,
            "派生栅格",
        )
        self._sync_layer_tree_visibility()
        self.layer_tree.setCurrentItem(hillshade_item)
        self.map_canvas.activate_pan()
        self.pan_action.setChecked(True)

        self.statusBar().showMessage(
            "Hillshade 完成："
            f"EPSG:{projection_result['target_epsg']} | "
            f"{hillshade_result['width']} × "
            f"{hillshade_result['height']} 像元 | "
            f"方位角 {azimuth:.1f}° | 高度角 {altitude:.1f}°"
        )

    def _next_terrain_analysis_output_paths(
        self,
        analysis_key: str,
    ) -> tuple[Path, Path]:
        """生成坡度或坡向分析的输出路径。"""

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )
        projected_path = (
            self._clip_output_directory
            / f"ETOPO2022_{analysis_key}_utm_{timestamp}.tif"
        )
        analysis_path = (
            self._clip_output_directory
            / f"ETOPO2022_{analysis_key}_{timestamp}.tif"
        )

        return projected_path, analysis_path

    def _create_terrain_analysis(
        self,
        analysis_key: str,
        analysis_label: str,
        generate_analysis,
        apply_renderer,
    ) -> None:
        """生成、设色并显示一个局部地形分析结果。"""

        if self._active_raster_path is None:
            return

        projected_path, analysis_path = (
            self._next_terrain_analysis_output_paths(
                analysis_key
            )
        )
        analysis_layer = None

        self.statusBar().showMessage(
            f"正在建立局部米制投影并生成{analysis_label}……"
        )

        try:
            # 坡度和坡向都从当前活动分析 DEM 开始计算。
            projection_result = (
                project_raster_to_local_utm(
                    self._active_raster_path,
                    str(projected_path),
                )
            )
            analysis_result = generate_analysis(
                projection_result["output_path"],
                str(analysis_path),
            )
            analysis_layer = add_raster_layer(
                analysis_result["output_path"],
                analysis_path.stem,
            )
            apply_renderer(analysis_layer)
        except (
            FileNotFoundError,
            FileExistsError,
            ValueError,
            RuntimeError,
        ) as exc:
            if analysis_layer is not None:
                QgsProject.instance().removeMapLayer(
                    analysis_layer.id()
                )
                analysis_layer = None

            for path in (
                analysis_path,
                projected_path,
            ):
                if path.exists():
                    path.unlink()

            self.statusBar().showMessage(
                f"{analysis_label}生成失败：{exc}"
            )
            return

        # 只更新显示层，不调用 show_layer()，避免改写 F03/F04 数据源。
        self.map_canvas.show_layer(
            analysis_layer
        )
        self._display_raster_layer = analysis_layer
        self._hillshade_layer = None
        self._slope_layer = (
            analysis_layer
            if analysis_key == "slope"
            else None
        )
        self._aspect_layer = (
            analysis_layer
            if analysis_key == "aspect"
            else None
        )
        # 派生结果使用自己的色带，不能再套用 ETOPO 高程色带。
        self.color_relief_action.setEnabled(False)
        analysis_item = self._register_layer(
            analysis_layer,
            "派生栅格",
        )
        self._sync_layer_tree_visibility()
        self.layer_tree.setCurrentItem(analysis_item)
        self.map_canvas.activate_pan()
        self.pan_action.setChecked(True)

        self.statusBar().showMessage(
            f"{analysis_label}完成："
            f"EPSG:{projection_result['target_epsg']} | "
            f"{analysis_result['width']} × "
            f"{analysis_result['height']} 像元"
        )

    def create_slope(self) -> None:
        """生成局部坡度并应用固定分级色带。"""

        self._create_terrain_analysis(
            "slope",
            "坡度",
            generate_slope,
            apply_slope_color_relief,
        )

    def create_aspect(self) -> None:
        """生成局部坡向并应用循环方向色带。"""

        self._create_terrain_analysis(
            "aspect",
            "坡向",
            generate_aspect,
            apply_aspect_direction_colors,
        )

    def show_layer(
        self,
        layer: QgsMapLayer,
        layer_group: str = "源数据",
    ) -> None:
        """
        在主地图中显示图层。
        """

        self.map_canvas.show_layer(
            layer
        )

        layer_item = self._register_layer(
            layer,
            layer_group,
        )
        self._sync_layer_tree_visibility()
        self.layer_tree.setCurrentItem(layer_item)

        # 只有正式加载或裁剪结果才能更新活动分析数据。
        self._active_raster_path = layer.source()
        self._active_raster_layer = layer
        self._display_raster_layer = layer
        self._hillshade_layer = None
        self._slope_layer = None
        self._aspect_layer = None

        source_name = Path(layer.source()).name
        # 在下划线和扩展名前允许换行，避免长文件名撑宽参数面板。
        display_source_name = (
            source_name
            .replace("_", "_\u200b")
            .replace(".", ".\u200b")
        )
        self.analysis_source_label.setText(
            display_source_name
        )
        self.analysis_source_label.setAccessibleName(
            source_name
        )
        self.analysis_source_label.setToolTip(
            layer.source()
        )

        layer_crs = layer.crs()
        horizontal_crs = layer_crs.horizontalCrs()
        display_crs = (
            horizontal_crs
            if horizontal_crs.isValid()
            else layer_crs
        )
        self.crs_status_label.setText(
            f"CRS：{display_crs.authid() or display_crs.description()}"
        )
        self.analysis_crs_label.setText(
            display_crs.authid()
            or display_crs.description()
        )
        self.analysis_size_label.setText(
            f"{layer.width()} × {layer.height()}"
        )

        resolution_x = layer.rasterUnitsPerPixelX()
        resolution_y = layer.rasterUnitsPerPixelY()
        self.resolution_status_label.setText(
            "分辨率："
            f"{resolution_x:.6g} × {resolution_y:.6g}"
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

        self._rectangle_selection_tool = (
            RectangleSelectionMapTool(
                self.map_canvas
            )
        )

        self._rectangle_selection_tool.rectangle_selected.connect(
            self._clip_selected_bounds
        )

        self._rectangle_selection_tool.selection_failed.connect(
            self._show_rectangle_selection_error
        )

        self.rectangle_clip_action.setEnabled(
            True
        )

        self.color_relief_action.setEnabled(
            True
        )

        self.hillshade_action.setEnabled(
            True
        )

        self.slope_action.setEnabled(
            True
        )

        self.aspect_action.setEnabled(
            True
        )
