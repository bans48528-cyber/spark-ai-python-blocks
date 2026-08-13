import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import sparkai_runtime  # noqa: E402


class RuntimePathTests(unittest.TestCase):
    def test_source_paths_use_repository_root(self):
        self.assertEqual(sparkai_runtime.resource_root(), ROOT)
        self.assertEqual(sparkai_runtime.application_root(), ROOT)

    def test_frozen_paths_split_resources_and_application_directory(self):
        with patch.object(sys, "_MEIPASS", "C:/bundle", create=True), patch.object(
            sys,
            "frozen",
            True,
            create=True,
        ), patch.object(sys, "executable", "C:/release/SparkAI-Generator.exe"):
            self.assertEqual(sparkai_runtime.resource_root(), Path("C:/bundle"))
            self.assertEqual(sparkai_runtime.application_root(), Path("C:/release"))
