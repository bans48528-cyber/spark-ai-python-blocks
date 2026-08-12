# Supported Spark AI Python Summary

This is the compact function list for AI code generation. Only use these
functions and Python constructs unless the converter is extended.

Ports are usually numeric in generated Python:

```text
A=0, B=1, C=2, D=3, E=4, F=5, G=6, H=7
```

## Motors

Paired motor setup and movement:

```python
_motor.pair(left_motor_port, right_motor_port, pair_mode)
_motor.mov_set_stop_module(mode)
_motor.mov_set_advance_offset(left_offset, right_offset)
_motor.mov_set_retreat_offset(left_offset, right_offset)
_motor.mov_power(left_power, right_power)
_motor.mov_for_power_seconds(left_power, right_power, seconds)
_motor.mov_dir_power("advance" | "retreat" | "left" | "right", power)
_motor.mov_dir_power_seconds("advance" | "retreat" | "left" | "right", power, seconds)
_motor.mov_for_degrees("advance" | "retreat" | "left" | "right", distance, "angle" | "circly" | "seconds")
_motor.mov_stop()
```

Single motor:

```python
_motor.run_power(port, power)
_motor.run_for_power_seconds(port, power, seconds)
_motor.stop(port)
_motor.stop_module(port, mode)
_motor.reset_relative_position(port)
```

Line following:

```python
_motor.mov_find_line_init()
_motor.mov_find_line_run(left_sensor_value, right_sensor_value, left_power, right_power, kp, kd)
```

Do not use `_color.set_color_threshold_value(...)`. In Spark AI 1.1.9, projects
containing the gray-sensor threshold setting block can be saved but fail to
reload. Use `_color.lux(port)` and `_color.lux_state(port)` inside line-follower
logic instead.

## Sensors And Main Unit

Color/grayscale:

```python
_color.lux(port)
_color.lux_state(port)
_color.cmp_lux(port, ">" | "<" | "==" | ">=" | "<=", value)
```

Touch/key:

```python
_touch.state(port)
_key.key_mast("left" | "right", 1)
_key.key_remote("up" | "down" | "left" | "right" | "Y" | "A" | "B" | "X" | "L1" | "R1", "press" | "unpress")
_key.key_remote("left" | "right", "x" | "y")
```

`_key.key_mast(...)` is the main-unit button block. It is not a handheld
controller block.

`_key.key_remote(button, "press" | "unpress")` is a handheld controller button
boolean reporter.

`_key.key_remote("left" | "right", "x" | "y")` is a handheld controller rocker
axis numeric reporter.

Ultrasonic:

```python
_ultrasion.value(port)
_ultrasion.cmp_value(port, ">" | "<" | "==" | ">=" | "<=", value)
```

Runtime values and resets:

```python
_os.timer()
_os.resetTimer()
_os.voic()
_mem.restyaw()
_os.stop_exit()
_os.sleep_s(seconds)
```

## Matrix Display

```python
_matrix.show(row0, row1, row2, row3, row4, row5, row6)
_matrix.show_roll(str(value))
_matrix.set_brightness(level)
_matrix.set_pixel_brightness(x, y, 0 | 1)
_matrix.clear()
```

`_matrix.show(...)` uses seven row values, often hexadecimal.

## Buzzer

```python
_beep.play_muic("c" | "d" | "e" | "f" | "g" | "a" | "b", beats)
_beep.stop()
```

Do not use `_beep.start`, `_beep.untildone`, `_beep.setvolumeto` or other
unconfirmed sound blocks.

## Variables And Lists

Variables:

```python
Name_ = 0
global Name_
Name_ = 10
Name_ += 1
```

Lists:

```python
Items_ = PikaStdData.List()
global Items_
Items_.append('text')
Items_.insert(index, 'text')
Items_.set(index, 'text')
Items_.remove_index(index)
Items_.remove_all()
Items_[index]
Items_.dataToindex('text')
Items_.num()
Items_.list_if_data('text')
```

## Control And Operators

Supported control:

```python
if condition:
    ...

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

Supported expressions:

```python
a + b
a - b
a * b
a / b
_math.fmod(a, b)
_math.round(value)
_random.randint(start, end)
len(text)
str(a).find(str(b)) > -1
not condition
condition1 and condition2
condition1 or condition2
a > b
a < b
a == b
```

Unary negative variables or expressions are allowed by the converter, but AI
code should prefer explicit subtraction for readability and Spark AI
compatibility, for example `0 - BasePower_` instead of `-BasePower_`.

## Good Line Follower Pattern

```python
_motor.mov_find_line_init()
_motor.pair(4, 5, 1)

while not (_touch.state(0)):
    _motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80, 45, 0.1, 0.6)
    _os.sleep_s(0.001)

_motor.mov_stop()
_beep.play_muic("c", 0.25)
```

## Good Remote-Control Car Pattern

When the user asks for a remote-control car, prefer the handheld controller,
not the main-unit left/right buttons:

```python
_motor.pair(4, 5, 1)

while True:
    if _key.key_remote("up", "press"):
        _motor.mov_power(60, 60)
    elif _key.key_remote("down", "press"):
        _motor.mov_power(-45, -45)
    elif _key.key_remote("left", "press"):
        _motor.mov_power(-35, 35)
    elif _key.key_remote("right", "press"):
        _motor.mov_power(35, -35)
    else:
        _motor.mov_stop()
    _os.sleep_s(0.001)
```
