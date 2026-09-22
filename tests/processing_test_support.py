"""旧界面断言在真实后台计算结束后继续，不替换或模拟计算线程。"""

import time
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtTest import QTest


def wait_for_processing(window, timeout=60):
    deadline = time.monotonic() + timeout
    while window._task_controls.worker is not None:
        QCoreApplication.processEvents()
        QTest.qWait(5)
        if time.monotonic() > deadline:
            raise AssertionError("后台计算未按时结束")
    QCoreApplication.processEvents()


def wrap_processing_calls(window):
    for action in (window.hillshade_action, window.slope_action, window.aspect_action, window.contour_action):
        action.triggered.connect(lambda checked=False: wait_for_processing(window))
    for name in ("_clip_selected_bounds", "create_hillshade", "create_slope", "create_aspect", "create_contours", "create_profile"):
        original = getattr(window, name)
        def run(*args, _original=original, **kwargs):
            value = _original(*args, **kwargs)
            wait_for_processing(window)
            return value
        setattr(window, name, run)
