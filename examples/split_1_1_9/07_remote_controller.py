# @sparkai-variable MaxPower_ => 最大功率
# @sparkai-variable BasePower_ => 基础功率

MaxPower_ = 0
BasePower_ = 0

global MaxPower_, BasePower_
MaxPower_ = 80
BasePower_ = 45

_motor.pair(4, 5, 1)

while True:
    if _key.key_remote("up", "press"):
        _motor.mov_power(MaxPower_, MaxPower_)
    elif _key.key_remote("down", "press"):
        _motor.mov_power(0 - BasePower_, 0 - BasePower_)
    elif _key.key_remote("left", "press"):
        _motor.mov_power(-35, 35)
    elif _key.key_remote("right", "press"):
        _motor.mov_power(35, -35)
    elif _key.key_remote("A", "unpress"):
        _matrix.show_roll(str(_key.key_remote("left", "x")))
    elif _key.key_remote("B", "press"):
        _matrix.show_roll(str(_key.key_remote("right", "y")))
    else:
        _motor.mov_stop()
    _os.sleep_s(0.001)
