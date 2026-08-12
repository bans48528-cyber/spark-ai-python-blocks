# Spark AI Hardware Overview

This file gives the AI enough hardware context to produce sensible Spark AI
Python. Keep it compact and include it with normal AI generation requests.

## Main Unit

The Spark AI main unit is a small programmable controller used with graphical
blocks. It can run Spark AI Python generated from blocks and control external
hardware through ports.

Built-in capabilities known to this project:

- matrix display
- buzzer capable of playing different notes
- buttons/keys on the main unit
- timer
- sound intensity value
- yaw reset/runtime orientation function

## Controller / Remote Handle

Spark AI also has a handheld controller/remote handle. It is a different
physical input device from the buttons on the main unit.

Use this distinction carefully:

- "main-unit buttons", "host buttons", "left/right key on the host" means the
  built-in buttons on the main unit and uses `_key.key_mast(...)`.
- "remote control", "controller", "handle", "gamepad", "joystick", "remote
  car" or Chinese phrases such as "遥控", "手柄", "遥控器", "摇杆" should be
  understood as the handheld controller and use `_key.key_remote(...)`, not
  `_key.key_mast(...)`.

Controller button names supported by confirmed blocks:

```text
up, down, left, right, Y, A, B, X, L1, R1
```

Controller rocker values supported by confirmed blocks:

```text
left x, left y, right x, right y
```

## Ports

Spark AI generated Python uses numeric port indexes:

```text
A=0
B=1
C=2
D=3
E=4
F=5
G=6
H=7
```

Typical interpretation:

- A-D are commonly used for sensors.
- E-H are commonly used for motors.
- Motor pair E/F is represented as `_motor.pair(4, 5, mode)`.

Do not confuse motor port menus with sensor port menus. If the user says a
motor uses E/F/G/H, use numeric ports 4/5/6/7.

## Common External Hardware

Commonly used parts:

- DC/geared motors connected to E-H.
- Grayscale/color reflected-light sensors connected to A-D.
- Ultrasonic sensor connected to A-D.
- Touch sensor connected to A-D.
- Handheld controller/remote handle for remote-control cars.

The hardware has no Scratch-style stage. Do not generate stage, sprite,
costume, coordinate or broadcast behavior unless the converter explicitly
supports it.

## Common Line-Following Car

A typical line-following car has:

- left motor on E
- right motor on F
- left grayscale/color sensor on A
- right grayscale/color sensor on B
- optional touch sensor on A-D as a stop input
- optional buzzer sound when finished
- optional matrix display status text

Default demo configuration when the user explicitly asks for a quick demo:

```text
left motor: E -> 4
right motor: F -> 5
pair mode: 1
left reflected-light sensor: A -> 0
right reflected-light sensor: B -> 1
stop touch sensor: A -> 0
max power: 80
base power: 45
line-following kp/kd: 0.1 / 0.6
```

Use this pattern:

```python
_motor.mov_find_line_init()
_motor.pair(4, 5, 1)

while not (_touch.state(0)):
    _motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80, 45, 0.1, 0.6)
    _os.sleep_s(0.001)

_motor.mov_stop()
_beep.play_muic("c", 0.25)
```

## Clarification Questions

Ask the user before generating final code when important hardware information
is missing and there is no clear default:

- Which ports are the left and right motors connected to?
- Which ports are the left and right grayscale/color sensors connected to?
- Which sensor or button should stop the program?
- If the user says "remote control", should it use the handheld controller
  buttons or joystick axes?
- Should the program use the buzzer, matrix display, or both?
- What speed/power range should be used?
- Does the program need custom blocks, variables or lists?

If using defaults, put them in the JSON `assumptions` field.

## Safety And Simplicity

- Keep motor power in a reasonable range, commonly 0-100 or -100 to 100 when the
  block supports reverse power.
- Prefer stopping motors at the end of a movement or loop.
- Use short matrix text.
- Use simple buzzer notes and short durations.
- Avoid indefinite full-power behavior unless the user explicitly asks for it
  and there is a clear stop condition.
