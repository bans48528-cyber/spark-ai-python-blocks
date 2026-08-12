import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sparkai_reverse import (  # noqa: E402
    ReverseCodeError,
    SparkAIReverseCompiler,
    compile_project,
    unique_output_path,
)
from sparkai_tool import (  # noqa: E402
    PythonGenerator,
    load_project,
    normalize_code,
    sprite_targets,
    stage_lists,
    stage_variables,
    validate_project,
)


REFERENCE = """_motor.pair(4,5,3)
_motor.mov_set_stop_module(1)
while True:
  if _color.cmp_lux(0, ">", 50):
    _motor.mov_power(30, 80)
  else:
    _motor.mov_power(80, 30)
    _os.sleep_s(0.001)
"""
CUSTOM_REFERENCE = """# @sparkai-custom customFunc0 => display one %n %b label text
# @sparkai-custom customFunc1 => display two %n %b tail label
my_234 = 0

def customFunc0(number0, boolean1):
    global my_234
    while not (boolean1):
        _matrix.show_roll(str(number0))
        _os.sleep_s(0.001)
    _os.sleep_s(1)

def customFunc1(CeShiA_, CeShiB_):
    global my_234
    while not (CeShiB_):
        _os.sleep_s(0.001)
    my_234 = CeShiA_

global my_234
customFunc0(my_234, _key.key_mast("left", 1))
customFunc1(1, _key.key_mast("right", 1))
"""
ALL_BLOCKS_NO_THRESHOLD = (ROOT / "examples" / "all_blocks_no_threshold.py").read_text(encoding="utf-8")
TEMPLATE = ROOT / "templates" / "base.sparkai"


class SparkAIReverseTests(unittest.TestCase):
    def test_comprehensive_sample_without_threshold_loads_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "all-blocks-no-threshold.sparkai"
            result = compile_project(ALL_BLOCKS_NO_THRESHOLD, TEMPLATE, output)
            project = load_project(output)
            self.assertEqual(validate_project(project), [])
            sprite = sprite_targets(project)[0]
            opcodes = {block.get("opcode") for block in sprite["blocks"].values()}
            self.assertNotIn("set_color_threshold_value", opcodes)
            self.assertTrue(
                {"sound_play", "sound_playuntildone", "sound_setvolumeto"}.isdisjoint(opcodes)
            )

            generated = PythonGenerator(
                sprite,
                stage_variables(project),
                stage_lists(project),
            ).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertEqual(generated.warnings, [])
            self.assertIn(
                '_color.cmp_lux(0, ">", 300) and not _touch.state(2)',
                generated.code,
            )
            self.assertIn(
                '_ultrasion.cmp_value(3, "<", 20) or _color.lux_state(1)',
                generated.code,
            )
            self.assertIn('_matrix.show_roll(str(_os.voic()))', generated.code)
            self.assertIn('str("Spark AI").find(str("AI")) > -1', generated.code)
            ast.parse(generated.code)
            self.assertEqual(result.block_count, len(sprite["blocks"]))

    def test_directional_distance_uses_real_dropdown_values(self):
        source = """_motor.mov_for_degrees("advance", 90, "angle")
_motor.mov_for_degrees("retreat", 1, "circly")
_motor.mov_for_degrees("left", 2, "seconds")
_motor.mov_for_degrees("right", 45, "angle")
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "directional-distance.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            sprite = sprite_targets(project)[0]
            blocks = [
                block
                for block in sprite["blocks"].values()
                if block.get("opcode") == "combined_motor_line"
            ]
            self.assertEqual(
                [block["fields"]["line"][0] for block in blocks],
                ["Advance", "Retreat", "left", "right"],
            )
            generated = PythonGenerator(sprite).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertEqual(normalize_code(generated.code), normalize_code(source))

    def test_directional_distance_rejects_unknown_dropdown_values(self):
        sources = (
            '_motor.mov_for_degrees("forward", 90, "angle")\n',
            '_motor.mov_for_degrees("advance", 90, "degree")\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, source in enumerate(sources):
                with self.subTest(source=source):
                    output = Path(directory) / f"invalid-direction-{index}.sparkai"
                    with self.assertRaises(ReverseCodeError):
                        compile_project(source, TEMPLATE, output)
                    self.assertFalse(output.exists())

    def test_non_ui_sound_functions_are_rejected(self):
        sources = (
            '_beep.start("A Piano.wav")\n',
            '_beep.untildone("A Piano.wav")\n',
            "_beep.setvolumeto(80)\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, source in enumerate(sources):
                with self.subTest(source=source):
                    output = Path(directory) / f"unsupported-sound-{index}.sparkai"
                    with self.assertRaises(ReverseCodeError):
                        compile_project(source, TEMPLATE, output)
                    self.assertFalse(output.exists())

    def test_matrix_pattern_inside_control_flow(self):
        source = """_motor.pair(4,5,3)
_motor.mov_set_stop_module(1)
while True:
    if _color.cmp_lux(0, ">", 50):
        _matrix.show(0x1F,0x11,0x15,0x17,0x03,0x1F,0x1F)
        _motor.mov_power(30, 80)
    else:
        _motor.mov_power(80, 30)
        _matrix.show_roll(str('ABCD'))
    _os.sleep_s(0.001)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "matrix-line-follower.sparkai"
            compile_project(source, TEMPLATE, output)
            result = PythonGenerator(sprite_targets(load_project(output))[0]).generate()
            self.assertEqual(result.unsupported, [])
            self.assertEqual(normalize_code(result.code), normalize_code(source))

    def test_hardware_output_round_trip(self):
        source = """_motor.run_power(4,50)
_matrix.show_roll(str("HI"))
_matrix.set_brightness(3)
_matrix.set_pixel_brightness(0,0,1)
_matrix.clear()
_beep.play_muic("c",0.25)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "hardware.sparkai"
            compile_project(source, TEMPLATE, output)
            result = PythonGenerator(sprite_targets(load_project(output))[0]).generate()
            self.assertEqual(result.unsupported, [])
            self.assertEqual(normalize_code(result.code), normalize_code(source))

    def test_generated_blocks_use_null_for_unlinked_records(self):
        source = """_motor.run_power(4, 50)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "null-links.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]
            self.assertNotIn("", {block["next"] for block in blocks.values()})
            self.assertIn(None, {block["next"] for block in blocks.values()})
            self.assertNotIn("", {block["parent"] for block in blocks.values()})
            self.assertTrue(
                all(block["parent"] is None for block in blocks.values() if block["topLevel"])
            )
            self.assertTrue(
                all(block["parent"] for block in blocks.values() if not block["topLevel"])
            )

    def test_single_motor_ports_use_motor_menu(self):
        source = """_motor.run_power(6, 50)
_motor.run_for_power_seconds(7, 50, 1)
_motor.stop(4)
_motor.stop_module(5, 1)
_motor.reset_relative_position(6)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "single-motor-ports.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]
            motor_opcodes = {
                "motor_startWithPower",
                "motor_specifiedunit",
                "motor_stop",
                "motor_specified_manner",
                "motor_reset_operating_degree",
            }
            expected_ports = {
                "motor_startWithPower": "G",
                "motor_specifiedunit": "H",
                "motor_stop": "E",
                "motor_specified_manner": "F",
                "motor_reset_operating_degree": "G",
            }
            motor_blocks = [
                block for block in blocks.values() if block.get("opcode") in motor_opcodes
            ]
            self.assertEqual(len(motor_blocks), len(motor_opcodes))
            for block in motor_blocks:
                port_input = block["inputs"]["PORT"]
                self.assertEqual(len(port_input), 2)
                port_block = blocks[port_input[1]]
                self.assertEqual(port_block["opcode"], "motor_box")
                self.assertEqual(
                    port_block["fields"]["MOTOR"][0],
                    expected_ports[block["opcode"]],
                )

            generated = PythonGenerator(sprite).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertIn("_motor.run_power(6,50)", generated.code)
            self.assertIn("_motor.run_for_power_seconds(7, 50, 1)", generated.code)

    def test_remote_controller_buttons_and_rocker_compile(self):
        source = """_motor.pair(4,5,1)
while True:
    if _key.key_remote("up", "press"):
        _motor.mov_power(60, 60)
    elif _key.key_remote("down", "press"):
        _motor.mov_power(-40, -40)
    elif _key.key_remote("left", "press"):
        _motor.mov_power(-30, 30)
    elif _key.key_remote("right", "press"):
        _motor.mov_power(30, -30)
    else:
        _motor.mov_stop()
    _matrix.show_roll(str(_key.key_remote("left", "x")))
    _os.sleep_s(0.001)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "remote-controller.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]
            opcodes = {block.get("opcode") for block in blocks.values()}
            self.assertIn("sensing_isHandling", opcodes)
            self.assertIn("handShank_menu", opcodes)
            self.assertIn("sensing_Handling", opcodes)
            self.assertNotIn("sensing_mainIsPress", opcodes)

            button_blocks = [
                block for block in blocks.values()
                if block.get("opcode") == "sensing_isHandling"
            ]
            observed = set()
            for block in button_blocks:
                menu = blocks[block["inputs"]["PORT"][1]]
                observed.add((menu["fields"]["HAND_SHANK"][0], block["fields"]["BUTTON"][0]))
            self.assertTrue({
                ("up", "press"),
                ("down", "press"),
                ("left", "press"),
                ("right", "press"),
            }.issubset(observed))

            generated = PythonGenerator(sprite).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertIn('_key.key_remote("up", "press")', generated.code)
            self.assertIn('_key.key_remote("left", "x")', generated.code)

    def test_remote_controller_rejects_invalid_combinations(self):
        sources = (
            '_key.key_remote("center", "press")\n',
            '_key.key_remote("up", "z")\n',
            '_key.key_remote("up", "x")\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, source in enumerate(sources):
                with self.subTest(source=source):
                    output = Path(directory) / f"invalid-remote-{index}.sparkai"
                    with self.assertRaises(ReverseCodeError):
                        compile_project(source, TEMPLATE, output)
                    self.assertFalse(output.exists())

    def test_line_patrol_sensor_inputs_are_numeric_value_inputs(self):
        source = """_motor.mov_find_line_run(0, 1, 80, 80, 0.1, 0.6)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "line-patrol-value-inputs.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]
            line_block = next(
                block
                for block in blocks.values()
                if block.get("opcode") == "combined_linepatrol_ltr"
            )

            for name, expected in (("PORT_ONE", "0"), ("PORT_TWO", "1")):
                input_entry = line_block["inputs"][name]
                self.assertEqual(input_entry, [1, [4, expected]])

            opcodes = {block.get("opcode") for block in blocks.values()}
            self.assertNotIn("combined_motorOne_menu", opcodes)
            self.assertNotIn("combined_motorTwo_menu", opcodes)
            generated = PythonGenerator(sprite).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertIn(
                "_motor.mov_find_line_run(0, 1, 80, 80, 0.1, 0.6)",
                generated.code,
            )

    def test_line_patrol_dynamic_inputs_keep_numeric_fallbacks(self):
        source = """_motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80 * 0.5, 80 * 0.5, 0.1, 0.6)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "line-patrol-dynamic-inputs.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]
            line_block = next(
                block
                for block in blocks.values()
                if block.get("opcode") == "combined_linepatrol_ltr"
            )

            for name, expected_opcode in (
                ("PORT_ONE", "sensing_reflected_light_detection"),
                ("PORT_TWO", "sensing_reflected_light_detection"),
                ("LEFT", "operator_multiply"),
                ("RIGHT", "operator_multiply"),
            ):
                input_entry = line_block["inputs"][name]
                self.assertEqual(input_entry[0], 3)
                self.assertIsInstance(input_entry[1], str)
                self.assertEqual(blocks[input_entry[1]]["opcode"], expected_opcode)
                self.assertEqual(input_entry[2], [4, "0" if name.startswith("PORT") else "80"])

            self.assertEqual(line_block["inputs"]["KP"], [1, [4, "0.1"]])
            self.assertEqual(line_block["inputs"]["KD"], [1, [4, "0.6"]])
            generated = PythonGenerator(sprite).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertEqual(normalize_code(generated.code), normalize_code(source))

    def test_line_sample2_special_input_shapes(self):
        source = """_motor.mov_find_line_init()
_motor.pair(4,5,1)
_color.set_color_threshold_value(0, 500)
_color.set_color_threshold_value(1, 500)
while not (_color.lux_state(0) and _color.lux_state(1)):
    _motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80 * 0.5, 80 * 0.5, 0.1, 0.6)
    _os.sleep_s(0.001)
_matrix.show_roll(str('ABCD'))
_matrix.set_pixel_brightness(2, 0, 1)
for count in range(10):
    _matrix.show_roll(str(_random.randint(1, 10)))
    _os.sleep_s(0.001)
_motor.mov_for_power_seconds(50, 50, _random.randint(1, 10))
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "line-sample2-shapes.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]

            thresholds = [
                block for block in blocks.values()
                if block.get("opcode") == "set_color_threshold_value"
            ]
            self.assertEqual(len(thresholds), 2)
            self.assertEqual(
                {
                    blocks[block["inputs"]["PORT"][1]]["fields"]["SENSING_MENU"][0]
                    for block in thresholds
                },
                {"A", "B"},
            )
            self.assertTrue(all(block["inputs"]["THRESHOLD"] == [1, [4, "500"]] for block in thresholds))

            pixel = next(block for block in blocks.values() if block.get("opcode") == "matrix_lamp_single")
            self.assertEqual(blocks[pixel["inputs"]["x"][1]]["opcode"], "matrix_x")
            self.assertEqual(blocks[pixel["inputs"]["x"][1]]["fields"]["X"][0], "2")
            self.assertEqual(blocks[pixel["inputs"]["y"][1]]["opcode"], "matrix_y")
            self.assertEqual(blocks[pixel["inputs"]["y"][1]]["fields"]["Y"][0], "0")

            random_blocks = [block for block in blocks.values() if block.get("opcode") == "operator_random"]
            self.assertGreaterEqual(len(random_blocks), 2)
            for random_block in random_blocks:
                self.assertEqual(random_block["inputs"]["FROM"], [1, [4, "1"]])
                self.assertEqual(random_block["inputs"]["TO"], [1, [4, "10"]])

            repeat = next(block for block in blocks.values() if block.get("opcode") == "control_repeat")
            self.assertEqual(repeat["inputs"]["TIMES"], [1, [6, "10"]])

            timed_motor = next(
                block for block in blocks.values()
                if block.get("opcode") == "combined_motor_startWithPowerObj"
            )
            for name in ("POWER_ONE", "POWER_TWO"):
                child = blocks[timed_motor["inputs"][name][1]]
                self.assertEqual(child["opcode"], "math_-100to100_number")
            count = timed_motor["inputs"]["COUNT"]
            self.assertEqual(count[0], 3)
            self.assertEqual(count[2], [4, "1"])

            generated = PythonGenerator(sprite).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertEqual(normalize_code(generated.code), normalize_code(source))

    def test_custom_blocks_compile_definitions_arguments_and_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "custom-blocks.sparkai"
            result = compile_project(CUSTOM_REFERENCE, TEMPLATE, output)
            project = load_project(output)
            stage = next(target for target in project.data["targets"] if target.get("isStage"))
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]

            definitions = [
                block for block in blocks.values()
                if block.get("opcode") == "procedures_definition"
            ]
            self.assertEqual(len(definitions), 2)
            prototypes = [
                blocks[definition["inputs"]["custom_block"][1]]
                for definition in definitions
            ]
            proccodes = {
                prototype["mutation"]["proccode"]
                for prototype in prototypes
            }
            self.assertEqual(
                proccodes,
                {
                    "display one %n %b label text",
                    "display two %n %b tail label",
                },
            )
            for prototype in prototypes:
                mutation = prototype["mutation"]
                argument_ids = json.loads(mutation["argumentids"])
                argument_names = json.loads(mutation["argumentnames"])
                self.assertEqual(len(argument_ids), 2)
                self.assertEqual(len(argument_names), 2)
                for argument_id in argument_ids:
                    self.assertIn(argument_id, prototype["inputs"])
                    reporter_id = prototype["inputs"][argument_id][1]
                    self.assertIn(
                        blocks[reporter_id]["opcode"],
                        {"argument_reporter_number", "argument_reporter_boolean"},
                    )

            calls = [
                block for block in blocks.values()
                if block.get("opcode") == "procedures_call"
            ]
            self.assertEqual(len(calls), 2)
            self.assertEqual(
                {call["mutation"]["proccode"] for call in calls},
                proccodes,
            )
            key_blocks = [
                block for block in blocks.values()
                if block.get("opcode") == "sensing_mainIsPress"
            ]
            self.assertEqual(
                {(block["fields"]["KEYS"][0], block["fields"]["BUTTON"][0]) for block in key_blocks},
                {("left", "1"), ("right", "1")},
            )
            self.assertEqual(stage["variables"], {"variable-0001": ["my_234", 0]})

            generated = PythonGenerator(
                sprite,
                stage_variables(project),
                stage_lists(project),
            ).generate()
            self.assertEqual(generated.unsupported, [])
            ast.parse(generated.code)
            self.assertIn("def customFunc0(number0, boolean1):", generated.code)
            self.assertIn("customFunc0(my_234, _key.key_mast(\"left\", 1))", generated.code)
            self.assertIn("customFunc1(1, _key.key_mast(\"right\", 1))", generated.code)
            self.assertEqual(result.block_count, len(blocks))

    def test_custom_block_requires_template_mapping(self):
        source = """my_234 = 0
def customFunc0(number0):
    global my_234
    my_234 = number0
global my_234
customFunc0(1)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "missing-custom-mapping.sparkai"
            with self.assertRaises(ReverseCodeError):
                compile_project(source, TEMPLATE, output)
            self.assertFalse(output.exists())

    def test_line_follower_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "line-follower.sparkai"
            result = compile_project(REFERENCE, TEMPLATE, output)
            self.assertEqual(result.block_count, 14)
            project = load_project(output)
            generated = PythonGenerator(sprite_targets(project)[0]).generate()
            self.assertEqual(normalize_code(generated.code), normalize_code(REFERENCE))
            self.assertEqual(generated.unsupported, [])

    def test_runtime_sleep_is_not_a_wait_block(self):
        source = """_motor.mov_stop()\nwhile True:\n  _motor.mov_power(20, 20)\n  _os.sleep_s(0.001)\n"""
        blocks, count = SparkAIReverseCompiler().compile(source)
        self.assertEqual(count, 6)
        self.assertEqual({block["opcode"] for block in blocks.values()}, {
            "event_whenflagclicked",
            "combined_motor_stop",
            "control_forever",
            "combined_motor_startWithPower",
            "math_-100to100_number",
        })

    def test_variables_generate_real_spark_ai_variable_inputs(self):
        source = """ShiJian_ = 0

global ShiJian_
ShiJian_ = 0
_motor.pair(4,5,3)
_os.sleep_s(1)
ShiJian_ += 1
_motor.mov_dir_power_seconds("advance", 50, ShiJian_)
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "variables.sparkai"
            result = compile_project(source, TEMPLATE, output)
            project = load_project(output)
            stage = next(target for target in project.data["targets"] if target.get("isStage"))
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]

            self.assertEqual(stage["variables"], {"variable-0001": ["ShiJian_", 0]})
            set_block = next(block for block in blocks.values() if block.get("opcode") == "data_setvariableto")
            change_block = next(block for block in blocks.values() if block.get("opcode") == "data_changevariableby")
            drive_block = next(block for block in blocks.values() if block.get("opcode") == "combined_mov_dir_power_seconds")
            self.assertEqual(set_block["fields"]["VARIABLE"], ["ShiJian_", "variable-0001"])
            self.assertEqual(change_block["inputs"]["VALUE"], [1, [4, "1"]])
            seconds_input = drive_block["inputs"]["SECONDS"]
            self.assertEqual(seconds_input[:2], [3, [12, "ShiJian_", "variable-0001"]])
            self.assertIn(seconds_input[2], blocks)
            self.assertEqual(blocks[seconds_input[2]]["fields"]["NUM"], ["1", None])

            generated = PythonGenerator(sprite).generate()
            expected = """ShiJian_ = 0
_motor.pair(4,5,3)
_os.sleep_s(1)
ShiJian_ += 1
_motor.mov_dir_power_seconds("advance", 50, ShiJian_)
"""
            self.assertEqual(normalize_code(generated.code), normalize_code(expected))
            self.assertEqual(generated.unsupported, [])
            self.assertEqual(result.block_count, len(blocks))

    def test_variable_comments_restore_workspace_display_names(self):
        source = """# @sparkai-variable ShiJian_ => 时间
# @sparkai-variable ShuLiang_ => 数量
ShiJian_ = 0
ShuLiang_ = 0

global ShiJian_, ShuLiang_
ShuLiang_ = 60
ShiJian_ = 0
ShiJian_ += 1
_motor.mov_dir_power_seconds("advance", 50, ShiJian_)
ShuLiang_ += 1
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mapped-variables.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            stage = next(target for target in project.data["targets"] if target.get("isStage"))
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]

            self.assertEqual(
                stage["variables"],
                {
                    "variable-0001": ["时间", 0],
                    "variable-0002": ["数量", 0],
                },
            )
            display_names = {
                block["fields"]["VARIABLE"][0]
                for block in blocks.values()
                if block.get("opcode") in {"data_setvariableto", "data_changevariableby"}
            }
            self.assertEqual(display_names, {"时间", "数量"})
            drive = next(
                block
                for block in blocks.values()
                if block.get("opcode") == "combined_mov_dir_power_seconds"
            )
            self.assertEqual(drive["inputs"]["SECONDS"][1], [12, "时间", "variable-0001"])

    def test_short_mapping_comments_restore_workspace_display_names(self):
        source = """# @var Power_=MaxPower
# @list Speeds_=SpeedList
Power_ = 0
Speeds_ = PikaStdData.List()

global Power_, Speeds_
Power_ = 80
Speeds_.append('50')
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "short-mapped.sparkai"
            result = compile_project(source, TEMPLATE, output)
            project = load_project(output)
            stage = next(target for target in project.data["targets"] if target.get("isStage"))

            self.assertEqual(stage["variables"], {"variable-0001": ["MaxPower", 0]})
            self.assertEqual(stage["lists"], {"list-0001": ["SpeedList", []]})
            self.assertEqual(result.mapping_report.variables, (("Power_", "MaxPower"),))
            self.assertEqual(result.mapping_report.lists, (("Speeds_", "SpeedList"),))
            self.assertEqual(result.mapping_report.unmapped_variables, ())
            self.assertEqual(result.mapping_report.unmapped_lists, ())

    def test_lists_compile_all_supported_blocks_and_reporters(self):
        source = """# @sparkai-list WoDePaiXu_ => 我的排序
YunXingShiJian_ = 0
DianJiGongL_ = 0
WoDePaiXu_ = PikaStdData.List()

global YunXingShiJian_, DianJiGongL_, WoDePaiXu_
WoDePaiXu_.append('东西')
WoDePaiXu_.append('南北')
WoDePaiXu_.insert(1, '333')
WoDePaiXu_.set(1, '555')
_matrix.show_roll(str(WoDePaiXu_[1]))
WoDePaiXu_.remove_index(1)
_matrix.show_roll(str(WoDePaiXu_.dataToindex('南北')))
_matrix.show_roll(str(WoDePaiXu_.num()))
if WoDePaiXu_.list_if_data('东西'):
    WoDePaiXu_.remove_all()
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "lists.sparkai"
            result = compile_project(source, TEMPLATE, output)
            project = load_project(output)
            self.assertEqual(validate_project(project), [])
            stage = next(target for target in project.data["targets"] if target.get("isStage"))
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]

            self.assertEqual(stage["lists"], {"list-0001": ["我的排序", []]})
            opcodes = {block.get("opcode") for block in blocks.values()}
            self.assertTrue({
                "data_addtolist",
                "data_insertatlist",
                "data_replaceitemoflist",
                "data_deleteoflist",
                "data_deletealloflist",
                "data_itemoflist",
                "data_itemnumoflist",
                "data_lengthoflist",
                "data_listcontainsitem",
            }.issubset(opcodes))
            self.assertEqual(
                sum(block.get("opcode") == "data_addtolist" for block in blocks.values()),
                2,
            )

            condition = next(block for block in blocks.values() if block.get("opcode") == "control_if")
            condition_input = condition["inputs"]["CONDITION"]
            self.assertEqual(condition_input[0], 2)
            self.assertEqual(len(condition_input), 2)
            self.assertEqual(blocks[condition_input[1]]["opcode"], "data_listcontainsitem")

            matrix_blocks = [
                block for block in blocks.values() if block.get("opcode") == "matrix_lamp_text"
            ]
            self.assertEqual(len(matrix_blocks), 3)
            for block in matrix_blocks:
                matrix_input = block["inputs"]["matrix_text"]
                self.assertEqual(matrix_input[0], 3)
                self.assertEqual(matrix_input[2], [10, "ABCD"])

            generated = PythonGenerator(
                sprite,
                stage_variables(project),
                stage_lists(project),
            ).generate()
            self.assertEqual(generated.unsupported, [])
            self.assertIn("我的排序[1]", generated.code)
            self.assertIn("我的排序.dataToindex(\"南北\")", generated.code)
            self.assertIn("我的排序.list_if_data(\"东西\")", generated.code)
            self.assertEqual(result.block_count, len(blocks))

    def test_lists_restore_two_mapped_names_inside_motor_inputs(self):
        source = """# @sparkai-list SuDu_ => 速度
# @sparkai-list ShiJian_ => 时间
SuDu_ = PikaStdData.List()
ShiJian_ = PikaStdData.List()

global SuDu_, ShiJian_
SuDu_.append('50')
SuDu_.append('60')
SuDu_.append('70')
ShiJian_.append('1')
ShiJian_.append('2')
ShiJian_.append('3')
_motor.run_for_power_seconds(4, SuDu_[1], ShiJian_[1])
_motor.run_for_power_seconds(4, SuDu_[2], ShiJian_[2])
_motor.run_for_power_seconds(4, SuDu_[3], ShiJian_[3])
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "lists-two.sparkai"
            compile_project(source, TEMPLATE, output)
            project = load_project(output)
            stage = next(target for target in project.data["targets"] if target.get("isStage"))
            sprite = sprite_targets(project)[0]
            blocks = sprite["blocks"]

            self.assertEqual(stage["lists"], {
                "list-0001": ["速度", []],
                "list-0002": ["时间", []],
            })
            motor_blocks = [
                block for block in blocks.values() if block.get("opcode") == "motor_specifiedunit"
            ]
            self.assertEqual(len(motor_blocks), 3)
            observed_indices = []
            for motor in motor_blocks:
                for name, expected_list in (("POWER", "速度"), ("COUNT", "时间")):
                    entry = motor["inputs"][name]
                    self.assertEqual(entry[0], 3)
                    child_id = entry[1]
                    self.assertEqual(blocks[child_id]["opcode"], "data_itemoflist")
                    self.assertEqual(blocks[child_id]["fields"]["LIST"][0], expected_list)
                    observed_indices.append(blocks[child_id]["inputs"]["INDEX"][1][1])
            self.assertEqual(sorted(observed_indices), ["1", "1", "2", "2", "3", "3"])

            generated = PythonGenerator(
                sprite,
                stage_variables(project),
                stage_lists(project),
            ).generate()
            expected = """速度.append("50")
速度.append("60")
速度.append("70")
时间.append("1")
时间.append("2")
时间.append("3")
_motor.run_for_power_seconds(4, 速度[1], 时间[1])
_motor.run_for_power_seconds(4, 速度[2], 时间[2])
_motor.run_for_power_seconds(4, 速度[3], 时间[3])
"""
            self.assertEqual(normalize_code(generated.code), normalize_code(expected))
            self.assertEqual(generated.unsupported, [])

    def test_unknown_list_mapping_fails_without_writing_output(self):
        source = """# @sparkai-list Missing => 不存在
Items = PikaStdData.List()
global Items
Items.append('value')
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "unknown-list-mapping.sparkai"
            with self.assertRaises(ReverseCodeError):
                compile_project(source, TEMPLATE, output)
            self.assertFalse(output.exists())

    def test_invalid_variable_mapping_fails_without_writing_output(self):
        source = "# @sparkai-variable Missing => 不存在\n_motor.mov_stop()\n"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "invalid-mapping.sparkai"
            with self.assertRaises(ReverseCodeError):
                compile_project(source, TEMPLATE, output)
            self.assertFalse(output.exists())

    def test_unknown_variable_fails_without_writing_output(self):
        source = "_motor.mov_dir_power_seconds(\"advance\", 50, missing)\n"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "unknown-variable.sparkai"
            with self.assertRaises(ReverseCodeError):
                compile_project(source, TEMPLATE, output)
            self.assertFalse(output.exists())

    def test_unknown_python_fails_without_writing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "should-not-exist.sparkai"
            with self.assertRaises(ReverseCodeError):
                compile_project("print('hello')\n", TEMPLATE, output)
            self.assertFalse(output.exists())

    def test_template_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            compile_project(REFERENCE, TEMPLATE, TEMPLATE)

    def test_default_names_do_not_reuse_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            first = unique_output_path(folder)
            first.touch()
            second = unique_output_path(folder)
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
