import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sparkai_clipboard import compile_clipboard, compile_clipboard_fragments  # noqa: E402


class SparkAIClipboardTests(unittest.TestCase):
    def test_main_stack_generates_pasteable_block_xml_without_event_hat(self):
        source = """# @var Power_=MaxPower
# @list Speeds_=SpeedList
Power_ = 0
Speeds_ = PikaStdData.List()
global Power_, Speeds_
Power_ = 80
Speeds_.append('50')
_motor.mov_for_degrees("advance", Power_, "angle")
"""
        result = compile_clipboard(source)
        self.assertEqual(result.mapping_report.variables, (("Power_", "MaxPower"),))
        self.assertEqual(result.mapping_report.lists, (("Speeds_", "SpeedList"),))
        self.assertEqual(result.mapping_report.unmapped_variables, ())
        self.assertEqual(result.mapping_report.unmapped_lists, ())

        self.assertEqual(len(result.fragments), 1)
        fragment = result.fragments[0]
        self.assertEqual(fragment.kind, "main")
        root = ET.fromstring(fragment.xml)
        self.assertEqual(root.tag.rsplit("}", 1)[-1], "block")
        self.assertEqual(root.get("type"), "data_setvariableto")
        self.assertNotIn("event_whenflagclicked", fragment.xml)
        self.assertNotIn(" x=", fragment.xml)
        self.assertNotIn(" y=", fragment.xml)
        self.assertNotIn('id="variable-0001"', fragment.xml)
        self.assertNotIn('id="list-0001"', fragment.xml)

        variable_fields = [
            field
            for field in root.findall('.//{*}field[@name="VARIABLE"]')
            if field.text == "MaxPower"
        ]
        self.assertGreaterEqual(len(variable_fields), 1)
        variable_ids = {field.get("id") for field in variable_fields}
        self.assertEqual(len(variable_ids), 1)
        variable_id = next(iter(variable_ids))
        self.assertIsNotNone(variable_id)
        self.assertTrue(variable_id.startswith("clipboard-variable-"))
        self.assertEqual(variable_fields[0].get("variabletype"), "")

        list_fields = [
            field
            for field in root.findall('.//{*}field[@name="LIST"]')
            if field.text == "SpeedList"
        ]
        self.assertEqual(len(list_fields), 1)
        list_id = list_fields[0].get("id")
        self.assertIsNotNone(list_id)
        self.assertTrue(list_id.startswith("clipboard-list-"))
        self.assertEqual(list_fields[0].get("variabletype"), "list")

        direction = root.find('.//{*}block[@type="combined_motor_line"]/{*}field[@name="line"]')
        self.assertIsNotNone(direction)
        self.assertEqual(direction.text, "Advance")

    def test_custom_definitions_are_separate_and_ordered_before_main(self):
        source = """# @sparkai-custom drive => drive power %n enabled %b
# @sparkai-custom-arg drive Power_ => power
# @sparkai-custom-arg drive Enabled_ => enabled
def drive(Power_, Enabled_):
    if Enabled_:
        _motor.mov_power(Power_, Power_)
drive(50, _key.key_mast("left", 1))
"""
        fragments = compile_clipboard_fragments(source)
        self.assertEqual([fragment.kind for fragment in fragments], ["custom", "main"])
        self.assertEqual(fragments[0].title, "自制积木：drive power %n enabled %b")
        definition = ET.fromstring(fragments[0].xml)
        main = ET.fromstring(fragments[1].xml)
        self.assertEqual(definition.get("type"), "procedures_definition")
        self.assertEqual(main.get("type"), "procedures_call")
        prototype = definition.find('.//{*}shadow[@type="procedures_prototype"]/{*}mutation')
        self.assertIsNotNone(prototype)
        self.assertEqual(prototype.get("proccode"), "drive power %n enabled %b")
        call = main.find("./{*}mutation")
        self.assertIsNotNone(call)
        self.assertEqual(call.get("proccode"), "drive power %n enabled %b")

    def test_remote_controller_clipboard_uses_handle_blocks(self):
        source = """_motor.pair(4, 5, 1)
while True:
    if _key.key_remote("up", "press"):
        _motor.mov_power(60, 60)
    else:
        _motor.mov_stop()
    _matrix.show_roll(str(_key.key_remote("left", "x")))
    _os.sleep_s(0.001)
"""
        result = compile_clipboard(source)
        self.assertEqual(len(result.fragments), 1)
        xml = result.fragments[0].xml
        self.assertIn('type="sensing_isHandling"', xml)
        self.assertIn('type="handShank_menu"', xml)
        self.assertIn('type="sensing_Handling"', xml)
        self.assertNotIn('type="sensing_mainIsPress"', xml)


if __name__ == "__main__":
    unittest.main()
