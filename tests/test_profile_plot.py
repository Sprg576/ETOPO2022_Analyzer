"""F08 曲线单位、负高程和缺测断线测试。"""

import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from etopo_analyzer.visualization.profile_plot import create_profile_figure


class TestProfilePlot(unittest.TestCase):
    def test_units_negative_values_and_gaps(self):
        result = {"distance_m": [0, 1000, 2000, 3000],
                  "elevation_m": [100, None, -100, -200],
                  "is_nodata": [False, True, False, False]}
        figure = create_profile_figure(result)
        axes = figure.axes[0]
        np.testing.assert_equal(axes.lines[0].get_xdata(), [0, 1, 2, 3])
        np.testing.assert_equal(axes.lines[0].get_ydata(), [100, np.nan, -100, -200])
        self.assertEqual(axes.get_xlabel(), "距离（km）")
        self.assertEqual(axes.get_ylabel(), "高程（m）")
        self.assertEqual(list(axes.lines[1].get_ydata()), [0, 0])
        self.assertEqual([text.get_text() for text in axes.texts], ["A", "B"])
        self.assertIsNone(result["elevation_m"][1])
        figure.clear()

    def test_invalid_lengths(self):
        with self.assertRaises(ValueError):
            create_profile_figure({"distance_m": [0, 1], "elevation_m": [1], "is_nodata": [False]})
