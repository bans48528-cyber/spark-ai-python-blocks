import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sparkai_tool import PythonGenerator, load_project, validate_project  # noqa: E402


PROJECT_ENV = os.environ.get("SPARKAI_SAMPLE_PROJECT")
PROJECT = Path(PROJECT_ENV) if PROJECT_ENV else None


@unittest.skipUnless(
    PROJECT is not None and PROJECT.exists(),
    "set SPARKAI_SAMPLE_PROJECT to run project inspection tests",
)
class LineFollowerProjectTests(unittest.TestCase):
    def setUp(self):
        assert PROJECT is not None
        project = load_project(PROJECT)
        self.assertEqual(validate_project(project), [])
        targets = [target for target in project.data["targets"] if not target.get("isStage")]
        self.generator = PythonGenerator(targets[0])

    def test_supported_project_generates_expected_code(self):
        result = self.generator.generate()
        expected = """_motor.pair(4,5,3)
_motor.mov_set_stop_module(1)
while True:
  if _color.cmp_lux(0, ">", 50):
    _motor.mov_power(30, 80)
  else:
    _motor.mov_power(80, 30)
    _os.sleep_s(0.001)
"""
        self.assertEqual(result.code, expected)
        self.assertEqual(result.unsupported, [])
        self.assertEqual(result.warnings, [])

    def test_opcode_inventory(self):
        opcodes = {block["opcode"] for block in self.generator.blocks.values()}
        self.assertIn("sensing_reflected_light_judgment", opcodes)
        self.assertIn("control_forever", opcodes)
        self.assertIn("combined_motor_startWithPower", opcodes)


if __name__ == "__main__":
    unittest.main()
