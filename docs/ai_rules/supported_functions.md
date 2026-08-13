# Spark AI Python 支持函数摘要

本文件是给 AI 生成代码使用的紧凑函数清单。除非转换器扩展，否则只使用本文件列出的函数和 Python 结构。

端口在生成的 Python 中通常使用数字：

```text
A=0, B=1, C=2, D=3, E=4, F=5, G=6, H=7
```

## 电机

双电机设置和运动：

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

单电机：

```python
_motor.run_power(port, power)
_motor.run_for_power_seconds(port, power, seconds)
_motor.stop(port)
_motor.stop_module(port, mode)
_motor.reset_relative_position(port)
```

巡线：

```python
_motor.mov_find_line_init()
_motor.mov_find_line_run(left_sensor_value, right_sensor_value, left_power, right_power, kp, kd)
_color.set_color_threshold_value(port, threshold)
```

`_color.set_color_threshold_value(port, threshold)` 可用于灰度传感器阈值设置，例如 A 口阈值 1000 写作 `_color.set_color_threshold_value(0, 1000)`。

## 传感器与主机输入

颜色/灰度：

```python
_color.lux(port)
_color.lux_state(port)
_color.cmp_lux(port, ">" | "<" | "==" | ">=" | "<=", value)
```

触碰/按键：

```python
_touch.state(port)
_key.key_mast("left" | "right", 1)
_key.key_remote("up" | "down" | "left" | "right" | "Y" | "A" | "B" | "X" | "L1" | "R1", "press" | "unpress")
_key.key_remote("left" | "right", "x" | "y")
```

`_key.key_mast(...)` 是主机按键积木，不是手柄/遥控器积木。

`_key.key_remote(button, "press" | "unpress")` 是手柄按键布尔报告器。

`_key.key_remote("left" | "right", "x" | "y")` 是手柄摇杆轴数值报告器。

超声波：

```python
_ultrasion.value(port)
_ultrasion.cmp_value(port, ">" | "<" | "==" | ">=" | "<=", value)
```

运行时数值和复位：

```python
_os.timer()
_os.resetTimer()
_os.voic()
_mem.restyaw()
_os.stop_exit()
_os.sleep_s(seconds)
```

## 点阵屏

```python
_matrix.show(row0, row1, row2, row3, row4, row5, row6)
_matrix.show_roll(str(value))
_matrix.set_brightness(level)
_matrix.set_pixel_brightness(x, y, 0 | 1)
_matrix.clear()
```

`_matrix.show(...)` 使用 7 个行值，通常是十六进制数。

## 蜂鸣器

```python
_beep.play_muic("c" | "d" | "e" | "f" | "g" | "a" | "b", beats)
_beep.stop()
```

不要使用 `_beep.start`、`_beep.untildone`、`_beep.setvolumeto` 或其它未确认的声音积木。

## 变量和列表

变量：

```python
Name_ = 0
global Name_
Name_ = 10
Name_ += 1
```

列表：

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

## 控制与运算

支持的控制结构：

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

支持的表达式：

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

转换器允许一元负号变量或表达式，但 AI 生成代码时优先使用显式减法，便于阅读并更接近 Spark AI 积木结构。例如优先写 `0 - BasePower_`，而不是 `-BasePower_`。

## 推荐巡线小车模式

```python
_motor.mov_find_line_init()
_motor.pair(4, 5, 1)

while not (_touch.state(0)):
    _motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80, 45, 0.1, 0.6)
    _os.sleep_s(0.001)

_motor.mov_stop()
_beep.play_muic("c", 0.25)
```

## 推荐遥控小车模式

当用户要求遥控小车时，优先使用手柄/遥控器，不要使用主机左右按键：

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
