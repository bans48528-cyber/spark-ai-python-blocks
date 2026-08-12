_motor.pair(4, 5, 1)
_motor.mov_set_stop_module(1)
_motor.mov_set_advance_offset(0, 0)
_motor.mov_set_retreat_offset(0, 0)

_motor.mov_dir_power("advance", 50)
_motor.mov_dir_power_seconds("retreat", 40, 1)
_motor.mov_for_power_seconds(30, 30, 0.5)

_motor.mov_for_degrees("advance", 90, "angle")
_motor.mov_for_degrees("retreat", 1, "circly")
_motor.mov_for_degrees("left", 1, "seconds")

_motor.mov_power(35, 35)
_motor.mov_power(-30, 30)
_motor.mov_stop()

_motor.run_power(4, 50)
_motor.run_for_power_seconds(5, 60, 1)
_motor.stop(6)
_motor.stop_module(7, 1)
_motor.reset_relative_position(4)
