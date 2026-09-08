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

from qgis.PyQt.QtWidgets import (
    QAction,
    QActionGroup,
    QMainWindow,
    QToolBar,
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
        self._rectangle_selection_tool = None
        self._active_raster_path = None
        self._active_raster_layer = None
        self._display_raster_layer = None
        self._hillshade_layer = None
        self._slope_layer = None
        self._aspect_layer = None
        self._clip_output_directory = (
            DEFAULT_CLIP_OUTPUT_DIR
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

        # -------------------------------------------------
        # Rectangle Clip
        # -------------------------------------------------

        self.rectangle_clip_action = QAction(
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

        tool_group.addAction(
            self.rectangle_clip_action
        )

        toolbar.addAction(
            self.rectangle_clip_action
        )

        toolbar.addSeparator()

        # -------------------------------------------------
        # Color Relief
        # -------------------------------------------------

        self.color_relief_action = QAction(
            "分层设色",
            self,
        )

        self.color_relief_action.setEnabled(
            False
        )

        self.color_relief_action.triggered.connect(
            self.apply_color_relief
        )

        toolbar.addAction(
            self.color_relief_action
        )

        # -------------------------------------------------
        # Hillshade
        # -------------------------------------------------

        self.hillshade_action = QAction(
            "山体阴影",
            self,
        )

        self.hillshade_action.setEnabled(
            False
        )

        self.hillshade_action.triggered.connect(
            self.create_hillshade
        )

        toolbar.addAction(
            self.hillshade_action
        )

        # -------------------------------------------------
        # Slope
        # -------------------------------------------------

        self.slope_action = QAction(
            "坡度",
            self,
        )

        self.slope_action.setEnabled(
            False
        )

        self.slope_action.triggered.connect(
            self.create_slope
        )

        toolbar.addAction(
            self.slope_action
        )

        # -------------------------------------------------
        # Aspect
        # -------------------------------------------------

        self.aspect_action = QAction(
            "坡向",
            self,
        )

        self.aspect_action.setEnabled(
            False
        )

        self.aspect_action.triggered.connect(
            self.create_aspect
        )

        toolbar.addAction(
            self.aspect_action
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

        self.show_layer(
            output_layer
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

        self.statusBar().showMessage(
            "正在建立局部米制投影并生成 Hillshade……"
        )

        try:
            projection_result = (
                project_raster_to_local_utm(
                    self._active_raster_path,
                    str(projected_path),
                )
            )
            hillshade_result = generate_hillshade(
                projection_result["output_path"],
                str(hillshade_path),
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
        self.map_canvas.activate_pan()
        self.pan_action.setChecked(True)

        self.statusBar().showMessage(
            "Hillshade 完成："
            f"EPSG:{projection_result['target_epsg']} | "
            f"{hillshade_result['width']} × "
            f"{hillshade_result['height']} 像元"
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
        self.color_relief_action.setEnabled(False)
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
    ) -> None:
        """
        在主地图中显示图层。
        """

        self.map_canvas.show_layer(
            layer
        )

        self._active_raster_path = layer.source()
        self._active_raster_layer = layer
        self._display_raster_layer = layer
        self._hillshade_layer = None
        self._slope_layer = None
        self._aspect_layer = None

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
