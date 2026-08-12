# Spark AI Block Semantics

This file explains how user words map to Spark AI hardware blocks. Include it
with AI generation requests so the model shares the user's product context.

## Main Unit Versus Controller

Spark AI has a programmable main unit and may also use a handheld controller.
These are not the same input device.

Use main-unit buttons only when the user explicitly mentions:

- main unit button
- host button
- onboard left/right key
- Chinese: 主机按键, 主机左键, 主机右键

Python:

```python
_key.key_mast("left", 1)
_key.key_mast("right", 1)
```

Use the handheld controller when the user mentions:

- remote control car
- remote controller
- handle
- gamepad
- joystick
- Chinese: 遥控小车, 遥控器, 手柄, 摇杆

Python for controller buttons:

```python
_key.key_remote("up", "press")
_key.key_remote("down", "press")
_key.key_remote("left", "press")
_key.key_remote("right", "press")
```

Python for controller rocker axes:

```python
_key.key_remote("left", "x")
_key.key_remote("left", "y")
_key.key_remote("right", "x")
_key.key_remote("right", "y")
```

Never substitute `_key.key_mast(...)` for a remote-control car unless the user
explicitly says the car should be controlled by buttons on the main unit.

## Common Intent Mapping

Remote-control car:

- pair motors on E/F unless the user gives other motor ports
- controller up button: forward
- controller down button: backward
- controller left button: turn left
- controller right button: turn right
- no direction button pressed: stop
- use `_key.key_remote(...)`, not `_key.key_mast(...)`
- if the user mentions joystick/rocker/proportional control, use
  `_key.key_remote("left" | "right", "x" | "y")` numeric axis reporters

Line-following car:

- use reflected-light sensors on A/B unless the user gives other ports
- use `_motor.mov_find_line_run(...)`
- feed sensor value slots with `_color.lux(0)` and `_color.lux(1)` or similar
  numeric reporters
- do not generate `_color.set_color_threshold_value(...)` because it is a known
  Spark AI 1.1.9 load-failure block
- do not use controller or main-unit buttons unless the user asks for manual
  control or a stop button

Obstacle-avoidance car:

- use ultrasonic distance `_ultrasion.value(port)` or
  `_ultrasion.cmp_value(port, "<", value)`
- default motors are E/F
- when an obstacle is too close, stop, turn, or back up depending on the user
  request

Display or status prompt:

- matrix image: `_matrix.show(...)`
- scrolling text/value: `_matrix.show_roll(str(value))`
- clear display: `_matrix.clear()`

Sound prompt:

- use the built-in buzzer with `_beep.play_muic(note, beats)`
- stop buzzer/sounds with `_beep.stop()`
- do not use unconfirmed music/sound APIs

Button-controlled demo:

- if the user says "use the host/main-unit buttons", then `_key.key_mast(...)`
  is appropriate
- if the user just says "remote", ask or use the handheld controller default

Variable/list/custom-block prompt:

- preserve Chinese display names with mapping comments
- initialize variables and lists near the top of the code
- for custom blocks, include `# @sparkai-custom` and
  `# @sparkai-custom-arg` comments so the visible block can be restored

## Ask When Ambiguous

Ask a short clarification question when the hardware intent is genuinely
ambiguous, for example:

- "Do you want the car controlled by the handheld controller or by the main-unit
  buttons?"
- "Should the controller use direction buttons or joystick axis values?"
