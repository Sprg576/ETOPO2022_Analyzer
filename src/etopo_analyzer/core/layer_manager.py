"""
layer_manager.py

QGIS 图层管理模块。

当前阶段功能：
1. 根据文件路径创建 QgsRasterLayer
2. 检查图层是否有效
3. 将图层加入 QgsProject
4. 返回创建后的 QgsRasterLayer

正式运行环境：
QGIS Python 3.12
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsProject,
    QgsRasterLayer,
)


def create_raster_layer(
    file_path: str,
    layer_name: str | None = None,
) -> QgsRasterLayer:
    """
    根据栅格文件路径创建 QgsRasterLayer。

    Parameters
    ----------
    file_path : str
        GeoTIFF、NetCDF 等 GDAL 支持的栅格文件路径。

    layer_name : str | None
        QGIS 图层名称。
        如果为 None，则使用文件名作为图层名称。

    Returns
    -------
    QgsRasterLayer
        已创建且有效的 QGIS 栅格图层。

    Raises
    ------
    FileNotFoundError
        文件不存在。

    RuntimeError
        QgsRasterLayer 创建失败或图层无效。
    """

    path = Path(file_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"栅格文件不存在：{path}"
        )

    if layer_name is None:
        layer_name = path.stem

    layer = QgsRasterLayer(
        str(path),
        layer_name,
        "gdal",
    )

    if not layer.isValid():
        raise RuntimeError(
            "QGIS 无法创建有效的栅格图层："
            f"{path}"
        )

    return layer


def add_raster_layer(
    file_path: str,
    layer_name: str | None = None,
) -> QgsRasterLayer:
    """
    创建 QgsRasterLayer 并加入当前 QgsProject。

    Parameters
    ----------
    file_path : str
        栅格文件路径。

    layer_name : str | None
        图层名称。

    Returns
    -------
    QgsRasterLayer
        已加入 QgsProject 的栅格图层。
    """

    layer = create_raster_layer(
        file_path=file_path,
        layer_name=layer_name,
    )

    QgsProject.instance().addMapLayer(
        layer
    )

    return layer


def remove_layer(
    layer_id: str,
) -> None:
    """
    根据图层 ID 从 QgsProject 中移除图层。

    Parameters
    ----------
    layer_id : str
        QgsMapLayer.id() 返回的图层 ID。
    """

    QgsProject.instance().removeMapLayer(
        layer_id
    )