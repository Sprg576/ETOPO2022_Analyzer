"""验证安装目录与可写用户成果目录解耦。"""

import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from etopo_analyzer.app_paths import output_directory


class TestAppPaths(unittest.TestCase):
    def test_explicit_user_output_created_and_used(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary) / '用户 成果' / 'outputs'
            with patch.dict(os.environ, {'ETOPO_USER_DIR': str(expected)}):
                self.assertEqual(output_directory(), expected)
                self.assertTrue(expected.is_dir())
                (output_directory() / 'test.txt').write_text('ok', encoding='utf-8')

    def test_development_default_is_project_outputs(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(output_directory(), Path(__file__).resolve().parents[1] / 'outputs')
