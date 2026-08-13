# Spark AI 支持积木表

本文件描述 AI 写 Spark AI Python 时可以面向哪些积木形态。它应与 `supported_functions.md` 一起使用：`supported_functions.md` 是紧凑函数清单，本文件解释用户意图、硬件含义和输入槽形态。

## 状态标签

- 稳定：可以为正常 `.sparkai` 输出生成。
- 仅检查：项目检查器可以识别，但 AI 不得生成。
- 不支持：不要生成。

## 输入槽类型

- 电机端口菜单：使用电机端口 E-H，在 Python 中表示为数字 4-7。
- 传感器端口菜单：使用传感器端口 A-D，在 Python 中表示为数字 0-3。
- 数值槽：可以放数字字面量、变量、列表项、运算或数值报告器。
- 电机功率滑条：Spark AI 的电机功率输入槽。可以放字面量、变量或运算；除非用户另有说明，值保持在 -100 到 100。
- 布尔槽：可以放传感器/按键判断或逻辑运算。
- 文本槽：可以放文本字面量、变量、列表项、用 `str(...)` 包裹的数值报告器，或产生文本的运算。

## 电机

### 双电机设置

状态：稳定

当用户使用两轮小车或左右驱动电机时使用。

```python
_motor.pair(4, 5, 1)
```

- `_motor.pair(left_port, right_port, pair_mode)`
- 默认：左电机 E -> 4，右电机 F -> 5，双电机模式 1。
- 输入：两个电机端口菜单，加一个模式下拉。
- 不要使用 A-D 作为电机端口，除非用户明确说明硬件这样连接，且 Spark AI 软件中确实提供这个选项。

### 双电机停止模式

状态：稳定

```python
_motor.mov_set_stop_module(1)
```

- 设置双电机停止时的刹车/滑行方式。
- 输入是 Spark AI 生成 Python 中的固定模式值。

### 双电机功率

状态：稳定

```python
_motor.mov_power(left_power, right_power)
```

- 用于双电机连续驱动。
- 输入是电机功率滑条。
- 正负号通过功率方向控制前进/后退。
- 变量反向时，AI 代码优先写 `0 - BasePower_`。

### 双电机按时间运行

状态：稳定

```python
_motor.mov_for_power_seconds(left_power, right_power, seconds)
```

- 让左右电机以独立功率运行指定时间。
- 功率输入是电机功率滑条。
- 时间输入是数值槽。

### 方向运动

状态：稳定

```python
_motor.mov_dir_power("advance", power)
_motor.mov_dir_power_seconds("retreat", power, seconds)
_motor.mov_for_degrees("left", distance, "angle")
```

- 方向：`"advance"`、`"retreat"`、`"left"`、`"right"`。
- `_motor.mov_for_degrees` 的单位：`"angle"`、`"circly"`、`"seconds"`。
- 适合生成初学者容易理解的移动命令。
- Spark AI 界面里方向可能显示为中文“前进/后退”等标签；Python 中仍使用以上英文字符串。

### 双电机停止和校准

状态：稳定

```python
_motor.mov_stop()
_motor.mov_set_advance_offset(left_offset, right_offset)
_motor.mov_set_retreat_offset(left_offset, right_offset)
```

- 没有遥控方向键按下时，或运动序列结束后，使用 `_motor.mov_stop()`。
- 校准输入是数值槽。

### 单电机

状态：稳定

```python
_motor.run_power(port, power)
_motor.run_for_power_seconds(port, power, seconds)
_motor.stop(port)
_motor.stop_module(port, mode)
_motor.reset_relative_position(port)
```

- 用于接在 E-H 的单个电机。
- 端口输入是电机端口菜单。
- 功率输入是电机功率滑条。

## 巡线

### 巡线初始化

状态：稳定

```python
_motor.mov_find_line_init()
```

- 巡线逻辑开始前调用一次。

### 巡线运行

状态：稳定

```python
_motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80, 45, 0.1, 0.6)
```

- 这是主要巡线积木。
- 左传感器值和右传感器值是数值槽，不是端口下拉栏。这里可以放 `_color.lux(...)`、变量、列表项或算术表达式。
- 左功率、右功率也是该积木的数值槽，不是单电机端口选择器。
- 常见传感器：A/B -> `_color.lux(0)` 和 `_color.lux(1)`。
- 重复巡线循环中应保留 `_os.sleep_s(0.001)`。

### 灰度传感器阈值设置

状态：稳定

```python
_color.set_color_threshold_value(port, threshold)
```

- 用于设置灰度传感器阈值，例如 `_color.set_color_threshold_value(0, 1000)` 表示 A 口阈值设为 1000。
- `port` 是传感器端口菜单，通常 A-D 对应 0-3。
- `threshold` 是普通数值槽，可以使用数字字面量、变量或算术表达式。
- 用户明确要求设置灰度阈值时，可以生成这个函数。

## 传感器和输入

### 反射光

状态：稳定

```python
_color.lux(port)
_color.cmp_lux(port, ">", value)
```

- 端口是传感器端口菜单，通常 A-D -> 0-3。
- `_color.lux(port)` 是数值报告器。
- `_color.cmp_lux(...)` 是布尔报告器。
- 比较符：`">"`、`"<"`、`"=="`、`">="`、`"<="`。

### 灰度状态

状态：稳定

```python
_color.lux_state(port)
```

- 灰度/颜色传感器状态布尔报告器。
- 可作为停止条件或巡线检测条件。

### 超声波

状态：稳定

```python
_ultrasion.value(port)
_ultrasion.cmp_value(port, "<", value)
```

- 端口是传感器端口菜单。
- 用于避障和距离显示。

### 触碰传感器

状态：稳定

```python
_touch.state(port)
```

- 外接触碰传感器布尔报告器，端口通常为 A-D。

### 主机按键

状态：稳定

```python
_key.key_mast("left", 1)
_key.key_mast("right", 1)
```

- 表示 Spark AI 主机上的物理按键。
- 除非用户明确要求主机按键控制小车，否则不要用于遥控小车。

### 手柄/遥控器

状态：稳定

```python
_key.key_remote("up", "press")
_key.key_remote("down", "press")
_key.key_remote("left", "press")
_key.key_remote("right", "press")
_key.key_remote("left", "x")
```

- 用于遥控器、手柄、游戏手柄、摇杆、遥控小车等需求。
- 按键名称：`up`、`down`、`left`、`right`、`Y`、`A`、`B`、`X`、`L1`、`R1`。
- 按键状态：`press`、`unpress`。
- 摇杆：`left` 或 `right`；轴：`x` 或 `y`。

## 主机输出

### 点阵屏

状态：稳定

```python
_matrix.show(0x1F, 0x11, 0x15, 0x15, 0x15, 0x11, 0x1F)
_matrix.show_roll(str(value))
_matrix.set_brightness(4)
_matrix.set_pixel_brightness(2, 3, 1)
_matrix.clear()
```

- `_matrix.show(...)` 接收 7 个整数行值，通常是 `0x00` 到 `0x1F` 的十六进制值。
- `_matrix.show_roll(str(value))` 滚动显示文本或转换后的值。
- 点亮单点的 x/y 必须是 Spark AI 点阵 UI 支持的字面坐标。
- 显示文字尽量短。

### 蜂鸣器

状态：稳定

```python
_beep.play_muic("c", 0.25)
_beep.stop()
```

- 主机有蜂鸣器，可以播放不同音调。
- 已确认音符：`"c"`、`"d"`、`"e"`、`"f"`、`"g"`、`"a"`、`"b"`。
- 不要使用未确认的声音 API，例如 `_beep.start(...)`、`_beep.untildone(...)`、`_beep.setvolumeto(...)`。

## 运行时数值

状态：稳定

```python
_os.timer()
_os.resetTimer()
_os.voic()
_mem.restyaw()
_os.stop_exit()
_os.sleep_s(seconds)
```

- `_os.timer()` 是计时器数值报告器。
- `_os.voic()` 是声音强度。
- `_os.sleep_s(0.001)` 常用于循环中，作为 Spark AI 的运行时协作等待。

## 变量、列表和自制积木

状态：稳定，需要映射注释

```python
# @var Power_=最大功率
# @list Speeds_=速度列表
Power_ = 0
Speeds_ = PikaStdData.List()

global Power_, Speeds_
Power_ = 80
Speeds_.append('50')
```

- 变量在代码顶部附近初始化，并写入舞台元数据。
- 列表必须用 `PikaStdData.List()` 初始化。
- 显示名称通过映射注释复原。

自制积木：

```python
# @sparkai-custom drive => 控制小车 左功率 %n 右功率 %n 执行 %b
# @sparkai-custom-arg drive LeftPower_ => 左功率
# @sparkai-custom-arg drive RightPower_ => 右功率
# @sparkai-custom-arg drive Enabled_ => 执行
def drive(LeftPower_, RightPower_, Enabled_):
    if Enabled_:
        _motor.mov_power(LeftPower_, RightPower_)
```

- `%n` 是数字输入项。
- `%b` 是布尔输入项。
- 占位符之外的文字会成为自制积木上的固定标签文本。

## 控制和运算

状态：稳定

支持的控制形态：

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

支持的运算：

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

- 表达式应保持简单，接近积木结构。
- 避免任意 Python 函数、推导式、类、导入、文件 IO。
