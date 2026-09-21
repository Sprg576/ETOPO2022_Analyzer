"""F09 图表仅显示像元数，覆盖非等宽边界和常量情况。"""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.visualization.statistics_plot import create_statistics_figure


class TestStatisticsPlot(unittest.TestCase):
    def test_bars_use_supplied_counts_and_widths(self):
        figure = create_statistics_figure(dict(histogram=dict(bin_edges_m=[-2, 0, 3], counts=[2, 3])))
        axes = figure.axes[0]
        self.assertEqual([p.get_height() for p in axes.patches], [2, 3])
        self.assertEqual([p.get_width() for p in axes.patches], [2, 3])
        self.assertEqual(axes.get_ylabel(), "有效像元数")
        self.assertEqual(axes.get_xlim(), (-2, 3))
        figure.clear()

    def test_constant_and_invalid_edges(self):
        figure = create_statistics_figure(dict(histogram=dict(bin_edges_m=[-.5, .5], counts=[5])))
        self.assertEqual(len(figure.axes[0].patches), 1)
        figure.clear()
        with self.assertRaises(ValueError):
            create_statistics_figure(dict(histogram=dict(bin_edges_m=[0, 0], counts=[1])))


if __name__ == "__main__":
    unittest.main()
