"""目标设备离线自检：实际读取、分析和导出，失败返回非零退出码。"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def create_demo(path):
    import numpy as np
    from osgeo import gdal
    from pyproj import CRS
    x, y = np.meshgrid(np.linspace(-2, 2, 160), np.linspace(-1.5, 1.5, 120))
    values = (2400 * np.exp(-x*x-y*y) - 1000 + 500*x + 100*np.sin(4*y)).astype('float32')
    ds = gdal.GetDriverByName('GTiff').Create(str(path), 160, 120, 1, gdal.GDT_Float32,
                                            options=['COMPRESS=DEFLATE'])
    ds.SetGeoTransform((120, .01, 0, 24, 0, -.01))
    ds.SetProjection(CRS.from_epsg(9518).to_wkt())
    band = None
    try:
        band = ds.GetRasterBand(1)
        band.SetUnitType('metre')
        band.SetNoDataValue(-9999)
        band.WriteArray(values)
    finally:
        band = ds = None


def run_check(report_path=None):
    report = dict(time=datetime.now(timezone.utc).isoformat(), passed=False, checks=[])
    try:
        import qgis, numpy, matplotlib, pyproj, osgeo
        from osgeo import gdal
        from qgis.core import Qgis, QgsRasterLayer
        from qgis.PyQt.QtCore import QCoreApplication, QEvent
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from etopo_analyzer.core.raster_statistics import calculate_raster_statistics
        from etopo_analyzer.core.region_comparison import compare_regions
        from etopo_analyzer.core.raster_clip import clip_raster_by_bounds
        from etopo_analyzer.core.hillshade import project_raster_to_local_utm, generate_hillshade
        from etopo_analyzer.core.terrain_analysis import generate_slope, generate_aspect
        from etopo_analyzer.core.contour_analysis import generate_contours
        from etopo_analyzer.core.profile_analysis import sample_elevation_profile
        from etopo_analyzer.core.csv_export import export_csv
        from etopo_analyzer.core.raster_export import export_raster
        from etopo_analyzer.visualization.statistics_plot import create_statistics_figure
        from etopo_analyzer.ui.main_window import ETOPOAnalyzerMainWindow
        from etopo_analyzer.app_paths import output_directory
        runtime = Path(os.environ['OSGEO4W_ROOT']).resolve()
        report['runtime'] = str(runtime)
        from etopo_analyzer.version import VERSION
        report['product_version'] = VERSION
        report['versions'] = dict(qgis=Qgis.QGIS_VERSION, python=sys.version.split()[0],
            gdal=gdal.VersionInfo('RELEASE_NAME'), numpy=numpy.__version__,
            matplotlib=matplotlib.__version__, pyproj=pyproj.__version__)
        report['modules'] = {m.__name__: str(Path(m.__file__).resolve()) for m in (qgis, numpy, matplotlib, pyproj, osgeo)}
        for name, path in report['modules'].items():
            if not Path(path).is_relative_to(runtime):
                raise RuntimeError(f'{name} was loaded outside bundled runtime: {path}')
        report['checks'].append('bundled_runtime_imports')
        with tempfile.TemporaryDirectory(prefix='etopo-check-', dir=output_directory()) as temporary:
            folder = Path(temporary)
            dem = folder / 'demo.tif'
            create_demo(dem)
            layer = QgsRasterLayer(str(dem), 'demo', 'gdal')
            if not layer.isValid():
                raise RuntimeError('QGIS GDAL provider could not open demo')
            report['checks'].append('qgis_raster_provider')
            result = calculate_raster_statistics(dem, 10, [0, 500])
            assert result['statistics']['valid_count'] == 19200
            roi = dict(type='Polygon', coordinates=[[[120.1, 23], [120.8, 23], [120.4, 23.9], [120.1, 23]]])
            masked = calculate_raster_statistics(dem, roi=roi)
            assert 0 < masked['statistics']['valid_count'] < 19200
            comparison = compare_regions(dem, dem, roi_a=roi, roi_b=roi)
            assert comparison['differences']['mean_m'] == 0
            report['checks'].extend(['statistics', 'polygon_mask', 'ab_comparison'])
            clip = folder / 'clip.tif'
            clip_raster_by_bounds(str(dem), str(clip), west=120.2, east=121, south=23, north=23.8)
            utm = folder / 'utm.tif'
            project_raster_to_local_utm(str(clip), str(utm))
            for name, fn in [('hillshade', generate_hillshade), ('slope', generate_slope), ('aspect', generate_aspect)]:
                fn(str(utm), str(folder / f'{name}.tif'))
            generate_contours(str(clip), str(folder / 'contours.gpkg'), interval=100)
            profile = sample_elevation_profile(str(dem), [(120.2, 23.5), (121, 23.5)], 1000)
            assert profile['sample_count'] > 2
            report['checks'].extend(['clip', 'utm_projection', 'hillshade', 'slope', 'aspect', 'contours', 'profile'])
            export_csv(folder, 'statistics', masked)
            export_raster(folder, str(dem))
            figure = create_statistics_figure(masked)
            FigureCanvasAgg(figure).print_png(str(folder / 'histogram.png'))
            figure.clear()
            report['checks'].extend(['csv_geojson_export', 'geotiff_export', 'chart_export'])
            window = ETOPOAnalyzerMainWindow()
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            layer = None
            report['checks'].append('main_window')
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        if report_path:
            path = Path(report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
