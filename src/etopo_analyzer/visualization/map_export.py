"""QGIS 原生异步地图渲染与图例；仅在 GUI 线程调用。"""

import math
import os
from pathlib import Path
from qgis.PyQt.QtCore import QSize, Qt, QEventLoop, QTimer, QRectF
from qgis.PyQt.QtGui import QImage, QPainter, QColor, QFont, QPolygonF, QPen, QFontDatabase
from qgis.core import (QgsMapSettings, QgsMapRendererParallelJob, QgsLayerTree,
                       QgsLayerTreeModel, QgsLegendSettings, QgsLegendRenderer, QgsLegendStyle,
                       QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject, QgsUnitTypes,
                       QgsRenderContext, QgsMapLayerStyle)
from etopo_analyzer.core.export_service import check_cancelled, layer_processing


def export_map(folder, canvas, title, pixels=2400, dpi=300, profile=None, cancelled=None, progress=None):
    check_cancelled(cancelled)
    # 某些 Windows 无界面会话没有系统字体枚举；显式加载已安装字体。
    if "Microsoft YaHei" not in QFontDatabase().families():
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    settings = QgsMapSettings(canvas.mapSettings())
    clones = [layer.clone() for layer in settings.layers()]
    if not clones:
        raise ValueError("当前地图没有可导出的图层。")
    settings.setLayers(clones)
    tree = QgsLayerTree()
    for layer in clones:
        tree.addLayer(layer)
    model = QgsLayerTreeModel(tree)
    legend_settings = QgsLegendSettings()
    legend_settings.setTitle("图例")
    for style in (QgsLegendStyle.Title, QgsLegendStyle.Group, QgsLegendStyle.Subgroup, QgsLegendStyle.SymbolLabel):
        legend_style = legend_settings.style(style)
        legend_style.setFont(QFont("Microsoft YaHei", 10))
        legend_settings.setStyle(style, legend_style)
    scale = pixels / 260.0  # 稳定的版面毫米到像素比，独立于印刷 DPI。
    legend_settings.setDpi(round(scale * 25.4))
    legend = QgsLegendRenderer(model, legend_settings)
    legend_size = legend.minimumSize()
    margin = int(6 * scale)
    legend_width = max(int(55 * scale), math.ceil(legend_size.width() * scale))
    map_width = pixels - legend_width - 3 * margin
    if map_width < pixels * .4:
        raise ValueError("图例名称过长，请缩短图层名称后导出。")
    old_size = settings.outputSize()
    map_height = max(1, round(map_width * old_size.height() / max(1, old_size.width())))
    settings.setOutputSize(QSize(map_width, map_height))
    settings.setOutputDpi(canvas.mapSettings().outputDpi() * map_width / max(1, old_size.width()))
    header = int(18 * scale)
    footer = int(30 * scale)
    body_height = max(map_height, math.ceil(legend_size.height() * scale))
    height = header + body_height + footer
    if height > 16000 or height * pixels > 60_000_000:
        raise ValueError("地图或图例过高，请调整地图窗口比例或减少可见图层。")
    job = QgsMapRendererParallelJob(settings)
    loop = QEventLoop()
    job.finished.connect(loop.quit)
    timer = QTimer()
    timer.setInterval(50)
    def poll():
        if cancelled and cancelled():
            job.cancelWithoutBlocking()
    timer.timeout.connect(poll)
    check_cancelled(cancelled)
    if progress:
        progress(10)
    timer.start()
    job.start()
    if job.isActive():
        loop.exec_()
    timer.stop()
    check_cancelled(cancelled)
    if job.errors():
        raise RuntimeError("地图渲染失败：" + "; ".join(error.message for error in job.errors()))
    map_image = job.renderedImage()
    image = QImage(pixels, height, QImage.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise RuntimeError("无法分配地图图片内存，请降低输出尺寸。")
    image.fill(Qt.white)
    image.setDotsPerMeterX(round(dpi / .0254))
    image.setDotsPerMeterY(round(dpi / .0254))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont("Microsoft YaHei")
        font.setPixelSize(round(5 * scale))
        painter.setFont(font)
        painter.setPen(QColor("#202D3A"))
        painter.drawText(QRectF(margin, 0, pixels - 2 * margin, header), Qt.AlignCenter | Qt.TextWordWrap, title)
        painter.drawImage(margin, header, map_image)
        if profile is not None:
            from etopo_analyzer.core.profile_analysis import densify_profile_path
            transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                                settings.destinationCrs(), QgsProject.instance())
            painter.save()
            painter.setClipRect(QRectF(margin, header, map_width, map_height))
            painter.translate(margin, header)
            points = []
            from qgis.PyQt.QtCore import QPointF
            for lon, lat in densify_profile_path(profile["vertices"]):
                point = transform.transform(QgsPointXY(lon, lat))
                pixel = settings.mapToPixel().transform(point)
                points.append(QPointF(pixel.x(), pixel.y()))
            painter.setPen(QPen(QColor("#C94A38"), max(2, scale * .5)))
            painter.drawPolyline(QPolygonF(points))
            for point, label in ((points[0], "A"), (points[-1], "B")):
                painter.drawText(point, label)
            painter.restore()
        painter.save()
        painter.translate(map_width + 2 * margin, header)
        painter.scale(scale, scale)
        context = QgsRenderContext.fromQPainter(painter)
        context.setScaleFactor(scale)
        legend.drawLegend(context)
        painter.restore()
        extent = settings.visibleExtent()
        crs = settings.destinationCrs()
        font.setPixelSize(round(3.2 * scale))
        painter.setFont(font)
        units = "°" if crs.isGeographic() else QgsUnitTypes.toString(crs.mapUnits())
        text = (f"坐标系：{crs.authid()} {crs.description()}\n"
                f"范围（{units}）：X {extent.xMinimum():.8g} ～ {extent.xMaximum():.8g}；"
                f"Y {extent.yMinimum():.8g} ～ {extent.yMaximum():.8g}\n"
                "高程/等高线：m；坡度/坡向：°；阴影：灰度值" + ("；红线 A→B：已完成剖面" if profile else ""))
        painter.drawText(QRectF(margin, header + body_height + margin, pixels - 2 * margin, footer - margin),
                         Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, text)
    finally:
        painter.end()
    check_cancelled(cancelled)
    path = folder / "map.png"
    if not image.save(str(path), "PNG") or QImage(str(path)).isNull():
        raise RuntimeError("地图 PNG 写入或重新打开失败。")
    if progress:
        progress(95)
    layer_records = []
    for layer in clones:
        style = QgsMapLayerStyle()
        style.readFromLayer(layer)
        layer_records.append({"name": layer.name(), "source": layer.source(), "style_xml": style.xmlData(),
                              "processing": layer_processing(layer)})
    return {"title": title, "crs_wkt": crs.toWkt(), "extent": [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
            "rotation": settings.rotation(), "pixels": [pixels, height], "dpi": dpi,
            "layers": layer_records,
            "profile_vertices": profile["vertices"] if profile else None}
