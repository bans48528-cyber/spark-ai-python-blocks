_motor.mov_find_line_init()
_motor.pair(4, 5, 1)
_color.set_color_threshold_value(0, 500)
_color.set_color_threshold_value(1, 500)

while not (_color.lux_state(0) and _color.lux_state(1)):
    _motor.mov_find_line_run(_color.lux(0), _color.lux(1), 80, 80, 0.1, 0.6)
    _os.sleep_s(0.001)
