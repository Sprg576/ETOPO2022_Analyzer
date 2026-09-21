"""F10 图表口径和同轴显示检查。"""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.core.region_comparison import compare_regions
from etopo_analyzer.visualization.comparison_plot import create_distribution_figure, create_area_comparison_figure
from test_raster_statistics import create_dem


class TestComparisonPlot(unittest.TestCase):
    def test_shared_edges_frequency_and_area_units(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a.tif", Path(temp) / "b.tif"
            create_dem(a, [[-2, 0, 2]])
            create_dem(b, [[0, 2, 4]])
            result = compare_regions(str(a), str(b), bin_count=3, thresholds=[0, 2])
            distribution = create_distribution_figure(result)
            ax = distribution.axes[0]
            self.assertEqual(ax.get_ylabel(), "有效像元占比（%）")
            self.assertEqual(ax.get_xlim(), (-2, 4))
            self.assertEqual(len(ax.patches), 2)
            self.assertEqual(list(ax.patches[0].get_data().edges), [-2, 0, 2, 4])
            self.assertEqual(list(ax.patches[1].get_data().edges), [-2, 0, 2, 4])
            self.assertAlmostEqual(sum(ax.patches[0].get_data().values), 100)
            area = create_area_comparison_figure(result)
            self.assertEqual(area.axes[0].get_ylabel(), "有效面积占比（%）")
            self.assertEqual(len(area.axes[0].patches), 6)
            self.assertAlmostEqual(sum(p.get_height() for p in area.axes[0].patches[:3]), 100)
            distribution.clear()
            area.clear()


if __name__ == "__main__":
    unittest.main()
