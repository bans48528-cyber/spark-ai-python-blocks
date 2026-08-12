# Spark AI Supported Blocks

This file describes the block shapes that the AI may target when writing Spark
AI Python. Use it together with `supported_functions.md`: that file is the
compact function list, while this file explains user intent, hardware meaning
and input-slot shape.

## Status Labels

- Stable: may be generated for normal `.sparkai` output.
- Inspect only: the project inspector may recognize it, but AI must not generate
  it.
- Unsupported: do not generate.

## Slot Types

- Motor port menu: use motor ports E-H, represented as numbers 4-7.
- Sensor port menu: use sensor ports A-D, represented as numbers 0-3.
- Number slot: can contain a literal number, variable, list item, operator or
  numeric reporter.
- Motor power slider: Spark AI's motor power slot. It can contain literals,
  variables or operators; keep values in -100 to 100 unless the user says
  otherwise.
- Boolean slot: can contain sensor/button comparisons or logical operators.
- Text slot: can contain text literals, variables, list items, numeric reporters
  wrapped by `str(...)`, or operators that produce text.

## Motors

### Paired Motor Setup

Status: Stable

Use when the user has a two-wheel car or left/right drive motors.

```python
_motor.pair(4, 5, 1)
```

- `_motor.pair(left_port, right_port, pair_mode)`
- Typical default: left motor E -> 4, right motor F -> 5, pair mode 1.
- Inputs: two motor port menus plus a mode dropdown.
- Do not use A-D as motor ports unless the user explicitly says the hardware is
  wired that way and Spark AI exposes that option.

### Paired Motor Stop Mode

Status: Stable

```python
_motor.mov_set_stop_module(1)
```

- Sets brake/coast style for the paired motor stop behavior.
- Input is a fixed mode value from Spark AI generated Python.

### Paired Motor Power

Status: Stable

```python
_motor.mov_power(left_power, right_power)
```

- Use for continuous two-motor driving.
- Inputs are motor power sliders.
- Positive/negative values control direction through power sign.
- For reverse variables, prefer `0 - BasePower_` in AI code.

### Paired Motor Timed Power

Status: Stable

```python
_motor.mov_for_power_seconds(left_power, right_power, seconds)
```

- Use for driving both motors at independent powers for a duration.
- Power inputs are motor power sliders.
- Duration is a number slot.

### Directional Movement

Status: Stable

```python
_motor.mov_dir_power("advance", power)
_motor.mov_dir_power_seconds("retreat", power, seconds)
_motor.mov_for_degrees("left", distance, "angle")
```

- Directions: `"advance"`, `"retreat"`, `"left"`, `"right"`.
- Distance units for `_motor.mov_for_degrees`: `"angle"`, `"circly"`,
  `"seconds"`.
- Use these blocks for beginner-friendly movement commands.
- In the Spark AI UI, directions display as localized labels such as forward or
  backward; Python still uses the English string values above.

### Paired Motor Stop And Offsets

Status: Stable

```python
_motor.mov_stop()
_motor.mov_set_advance_offset(left_offset, right_offset)
_motor.mov_set_retreat_offset(left_offset, right_offset)
```

- Use `_motor.mov_stop()` when no remote-control direction is pressed or after a
  movement sequence ends.
- Offset inputs are number slots.

### Single Motor

Status: Stable

```python
_motor.run_power(port, power)
_motor.run_for_power_seconds(port, power, seconds)
_motor.stop(port)
_motor.stop_module(port, mode)
_motor.reset_relative_position(port)
```

- Use for one motor on E-H.
- Port input is a motor port menu.
- Power input is a motor power slider.

## Line Following

### Line Patrol Init

Status: Stable

```python
_motor.mov_find_line_init()
```

- Use once before line-following behavior.

### Line Patrol Run

Status: Stable

```python
_motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80, 45, 0.1, 0.6)
```

- This is the main line-following block.
- The left-sensor and right-sensor inputs are number slots, not port dropdowns.
  They may contain `_color.lux(...)`, variables, list items or arithmetic.
- Left and right power are also number slots for this block, not the single
  motor port selector.
- Typical sensors: A/B -> `_color.lux(0)` and `_color.lux(1)`.
- Always keep `_os.sleep_s(0.001)` inside a repeated line-following loop.

### Gray-Sensor Threshold Setting

Status: Inspect only

```python
_color.set_color_threshold_value(port, threshold)
```

- Do not generate this function.
- Spark AI 1.1.9 can save projects containing this block, but saved projects
  fail to reload.
- If a user asks to set a grayscale threshold, explain that this block is
  disabled for file reliability and use reflected-light readings or
  `_color.lux_state(...)` instead.

## Sensors And Inputs

### Reflected Light

Status: Stable

```python
_color.lux(port)
_color.cmp_lux(port, ">", value)
```

- Port is a sensor port menu, typically A-D -> 0-3.
- `_color.lux(port)` is a numeric reporter.
- `_color.cmp_lux(...)` is a boolean reporter.
- Comparison operators: `">"`, `"<"`, `"=="`, `">="`, `"<="`.

### Grayscale State

Status: Stable

```python
_color.lux_state(port)
```

- Boolean reporter for grayscale/color sensor state.
- Useful as a stop condition or line-detection condition.

### Ultrasonic

Status: Stable

```python
_ultrasion.value(port)
_ultrasion.cmp_value(port, "<", value)
```

- Port is a sensor port menu.
- Use for obstacle detection and distance display.

### Touch Sensor

Status: Stable

```python
_touch.state(port)
```

- Boolean reporter for an external touch sensor on A-D.

### Main Unit Buttons

Status: Stable

```python
_key.key_mast("left", 1)
_key.key_mast("right", 1)
```

- This means physical buttons on the Spark AI main unit.
- Do not use it for remote-control cars unless the user explicitly says the main
  unit buttons should control the car.

### Handheld Controller

Status: Stable

```python
_key.key_remote("up", "press")
_key.key_remote("down", "press")
_key.key_remote("left", "press")
_key.key_remote("right", "press")
_key.key_remote("left", "x")
```

- Use this for remote controller, handle, gamepad, joystick or remote-control
  car requests.
- Button names: `up`, `down`, `left`, `right`, `Y`, `A`, `B`, `X`, `L1`, `R1`.
- Button states: `press`, `unpress`.
- Rockers: `left` or `right`; axes: `x` or `y`.

## Main Unit Output

### Matrix Display

Status: Stable

```python
_matrix.show(0x1F, 0x11, 0x15, 0x15, 0x15, 0x11, 0x1F)
_matrix.show_roll(str(value))
_matrix.set_brightness(4)
_matrix.set_pixel_brightness(2, 3, 1)
_matrix.clear()
```

- `_matrix.show(...)` takes seven integer row values, often hex values from
  `0x00` to `0x1F`.
- `_matrix.show_roll(str(value))` scrolls text or converted values.
- Pixel x/y must be literal coordinates supported by the Spark AI matrix UI.
- Keep display text short.

### Buzzer

Status: Stable

```python
_beep.play_muic("c", 0.25)
_beep.stop()
```

- The main unit has a buzzer and can play different notes.
- Confirmed notes: `"c"`, `"d"`, `"e"`, `"f"`, `"g"`, `"a"`, `"b"`.
- Do not use unconfirmed sound APIs such as `_beep.start(...)`,
  `_beep.untildone(...)` or `_beep.setvolumeto(...)`.

## Runtime Values

Status: Stable

```python
_os.timer()
_os.resetTimer()
_os.voic()
_mem.restyaw()
_os.stop_exit()
_os.sleep_s(seconds)
```

- `_os.timer()` is a numeric reporter.
- `_os.voic()` is sound intensity.
- `_os.sleep_s(0.001)` is commonly used inside loops as Spark AI's cooperative
  runtime sleep.

## Variables, Lists And Custom Blocks

Status: Stable with mapping comments

```python
# @var Power_=最大功率
# @list Speeds_=速度列表
Power_ = 0
Speeds_ = PikaStdData.List()

global Power_, Speeds_
Power_ = 80
Speeds_.append('50')
```

- Variables are initialized near the top and represented in stage metadata.
- Lists must be initialized with `PikaStdData.List()`.
- Display names are restored from mapping comments.

Custom blocks:

```python
# @sparkai-custom drive => 控制小车 左功率 %n 右功率 %n 执行 %b
# @sparkai-custom-arg drive LeftPower_ => 左功率
# @sparkai-custom-arg drive RightPower_ => 右功率
# @sparkai-custom-arg drive Enabled_ => 执行
def drive(LeftPower_, RightPower_, Enabled_):
    if Enabled_:
        _motor.mov_power(LeftPower_, RightPower_)
```

- `%n` is a number input.
- `%b` is a boolean input.
- Text outside placeholders becomes fixed label text on the custom block.

## Control And Operators

Status: Stable

Supported control shapes:

```python
if condition:
    ...
else:
    ...

while True:
    ...

while not (condition):
    ...

for count in range(times):
    ...
```

Supported operators:

```python
a + b
a - b
a * b
a / b
_math.fmod(a, b)
_math.round(value)
_random.randint(start, end)
len(text)
str(text).find(str(part)) > -1
not condition
condition1 and condition2
condition1 or condition2
a > b
a < b
a == b
```

- Keep expressions simple and block-like.
- Avoid arbitrary Python functions, comprehensions, classes, imports or file IO.
