# Spark AI 积木语义映射

本文件说明用户自然语言如何映射到 Spark AI 硬件积木。后端应在 AI 生成请求中携带它，让模型理解产品语境。

## 主机按键与手柄

Spark AI 有可编程主机，也可以使用手柄/遥控器。二者不是同一个输入设备。

只有当用户明确提到以下内容时，才使用主机按键：

- 主机按键
- 主机左键
- 主机右键
- 机身按键
- host button
- onboard left/right key

对应 Python：

```python
_key.key_mast("left", 1)
_key.key_mast("right", 1)
```

当用户提到以下内容时，使用手柄/遥控器：

- 遥控小车
- 遥控器
- 手柄
- 游戏手柄
- 摇杆
- remote control car
- remote controller
- handle
- gamepad
- joystick

手柄按键 Python：

```python
_key.key_remote("up", "press")
_key.key_remote("down", "press")
_key.key_remote("left", "press")
_key.key_remote("right", "press")
```

手柄摇杆轴 Python：

```python
_key.key_remote("left", "x")
_key.key_remote("left", "y")
_key.key_remote("right", "x")
_key.key_remote("right", "y")
```

除非用户明确说“用主机按键控制小车”，否则不要把 `_key.key_mast(...)` 用在遥控小车上。

## 常见需求映射

遥控小车：

- 默认电机接 E/F，除非用户给出其它电机端口。
- 手柄上键：前进。
- 手柄下键：后退。
- 手柄左键：左转。
- 手柄右键：右转。
- 没有方向键按下：停止。
- 使用 `_key.key_remote(...)`，不要使用 `_key.key_mast(...)`。
- 如果用户提到摇杆、摇杆轴、比例控制，使用 `_key.key_remote("left" | "right", "x" | "y")` 数值报告器。

巡线小车：

- 默认反射光/灰度传感器接 A/B，除非用户给出其它端口。
- 使用 `_motor.mov_find_line_run(...)`。
- 巡线运行积木的传感器值输入槽应放 `_color.lux(0)`、`_color.lux(1)` 或类似数值报告器。
- 不要生成 `_color.set_color_threshold_value(...)`，这是 Spark AI 1.1.9 的已知加载失败积木。
- 除非用户要求手动控制或停止按键，否则不要加入手柄或主机按键。

避障小车：

- 使用超声波距离 `_ultrasion.value(port)` 或 `_ultrasion.cmp_value(port, "<", value)`。
- 默认电机接 E/F。
- 障碍太近时，根据用户要求停止、转向或后退。

显示或状态提示：

- 点阵图案：`_matrix.show(...)`
- 滚动文字/数值：`_matrix.show_roll(str(value))`
- 清屏：`_matrix.clear()`

声音提示：

- 使用主机蜂鸣器 `_beep.play_muic(note, beats)`。
- 停止蜂鸣器/声音：`_beep.stop()`。
- 不要使用未确认的音乐/声音 API。

主机按键演示：

- 如果用户说“使用主机按键”，则 `_key.key_mast(...)` 合适。
- 如果用户只说“遥控”，优先按手柄理解；不确定时提问。

变量、列表、自制积木：

- 使用映射注释保留中文显示名称。
- 变量和列表在代码顶部附近初始化。
- 自制积木必须包含 `# @sparkai-custom` 和 `# @sparkai-custom-arg` 注释，以便复原可见积木文本和参数名。

## 需要提问的情况

当硬件意图确实模糊时，提出简短澄清问题。例如：

- “小车是用手柄控制，还是用主机左右按键控制？”
- “手柄控制要用方向按键，还是用摇杆轴？”
- “左右电机和左右灰度传感器分别接在哪些端口？”
