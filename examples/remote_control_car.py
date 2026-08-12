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
