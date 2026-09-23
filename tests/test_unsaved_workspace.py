"""关闭与切换工作状态的真实保存、失败、取消和恢复检查。"""
import unittest
from unittest.mock import patch
from qgis.PyQt.QtGui import QCloseEvent
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QTimer
from processing_test_support import wait_for_processing
from etopo_analyzer.ui.workspace_controls import WorkspaceControls
import test_processing_tasks as fixtures
from etopo_analyzer.core.workspace_state import read_state


class TestUnsavedWorkspace(unittest.TestCase):
    setUpClass = classmethod(fixtures.TestProcessingTasks.setUpClass.__func__)
    setUp = fixtures.TestProcessingTasks.setUp
    tearDown = fixtures.TestProcessingTasks.tearDown

    def close_event(self, choice):
        self.window.workspace_controls.ask_unsaved.return_value = choice
        event = QCloseEvent()
        self.window.closeEvent(event)
        return event.isAccepted()

    def test_save_dirty_revert_load_and_view_only(self):
        w = self.window
        c = w.workspace_controls
        self.assertTrue(c.is_dirty())
        path = self.root / "状态.etopo.json"
        c.save(path)
        self.assertFalse(c.is_dirty())
        value = w.hillshade_azimuth_spin.value()
        w.hillshade_azimuth_spin.setValue(value + 1)
        self.assertTrue(c.is_dirty())
        w.hillshade_azimuth_spin.setValue(value)
        self.assertFalse(c.is_dirty())
        w.map_canvas.setRotation(20)
        self.assertFalse(c.is_dirty())
        self.layer.setName("改名")
        self.assertTrue(c.is_dirty())
        c.load(path)
        self.assertFalse(c.is_dirty())

    def test_close_cancel_then_discard(self):
        self.assertFalse(self.close_event(QMessageBox.Cancel))
        self.assertFalse(self.window._closing)
        self.assertTrue(self.window.workspace_controls.is_dirty())
        self.assertTrue(self.close_event(QMessageBox.Discard))

    def test_close_save_writes_state(self):
        path = self.root / "保存.etopo.json"
        with patch("etopo_analyzer.ui.workspace_controls.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            self.assertTrue(self.close_event(QMessageBox.Save))
        self.assertEqual(len(read_state(path)["layers"]), 1)
        self.assertFalse(self.window.workspace_controls.is_dirty())

    def test_save_cancel_and_failure_block_close(self):
        with patch("etopo_analyzer.ui.workspace_controls.QFileDialog.getSaveFileName", return_value=("", "")):
            self.assertFalse(self.close_event(QMessageBox.Save))
        self.window.workspace_controls.path = str(self.root / "state.etopo.json")
        with patch("etopo_analyzer.ui.workspace_controls.write_state", side_effect=OSError("磁盘已满")), patch(
                "etopo_analyzer.ui.workspace_controls.QMessageBox.warning"):
            self.assertFalse(self.close_event(QMessageBox.Save))
        self.assertTrue(self.window.workspace_controls.is_dirty())
        self.assertIs(self.window._active_raster_layer, self.layer)

    def test_switch_cancel_and_save_same_file_use_latest_state(self):
        c = self.window.workspace_controls
        path = self.root / "state.etopo.json"
        c.save(path)
        self.layer.setName("新名称")
        c.ask_unsaved.return_value = QMessageBox.Cancel
        c.load(path, confirm=True)
        self.assertIs(self.window._active_raster_layer, self.layer)
        self.assertTrue(c.is_dirty())
        c.ask_unsaved.return_value = QMessageBox.Save
        c.load(path, confirm=True)
        self.assertEqual(self.window._active_raster_layer.name(), "新名称")
        self.assertFalse(c.is_dirty())

    def test_clean_close_never_prompts(self):
        c = self.window.workspace_controls
        c.mark_clean()
        self.assertTrue(self.close_event(QMessageBox.Cancel))
        c.ask_unsaved.assert_not_called()

    def test_real_prompt_defaults_to_cancel(self):
        def cancel_dialog():
            box = self.app.activeModalWidget()
            self.assertIsInstance(box, QMessageBox)
            self.assertEqual(box.defaultButton().text(), "取消")
            box.defaultButton().click()
        QTimer.singleShot(0, cancel_dialog)
        self.assertEqual(WorkspaceControls.ask_unsaved(self.window.workspace_controls), QMessageBox.Cancel)

    def test_close_running_then_cancel_prompt_restores_actions(self):
        self.window.workspace_controls.ask_unsaved.return_value = QMessageBox.Cancel
        self.window._task_controls.start("测试", [("等待", lambda results: fixtures.TestProcessingTasks.slow_operation(self, results))], [], lambda result: None)
        self.window.close()
        wait_for_processing(self.window)
        self.app.processEvents()
        self.assertFalse(self.window._closing)
        self.assertFalse(getattr(self.window, "_close_approved", False))
        self.assertTrue(self.window.workspace_controls.save_action.isEnabled())
        self.assertTrue(self.window.slope_action.isEnabled())
        self.assertTrue(self.window.workspace_controls.is_dirty())
