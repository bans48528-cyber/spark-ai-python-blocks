# @sparkai-variable Power_ => 最大功率

Power_ = 0

global Power_
Power_ = 70

_motor.pair(4, 5, 1)
_motor.mov_find_line_init()
_color.set_color_threshold_value(0, 500)
_color.set_color_threshold_value(1, 520)

if _key.key_remote("A", "press"):
    _matrix.show_roll(str("REMOTE"))

while not (_touch.state(0)):
    if _key.key_remote("up", "press"):
        _motor.mov_power(Power_, Power_)
    else:
        _motor.mov_find_line_run(_color.lux(0), _color.lux(1), 40, 40, 0.1, 0.6)
    _os.sleep_s(0.001)

_motor.mov_stop()
