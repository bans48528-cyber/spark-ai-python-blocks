# @sparkai-variable Power_ => 最大功率
# @sparkai-variable BasePower_ => 基础功率
# @sparkai-variable Counter_ => 运行次数
# @sparkai-list Speeds_ => 速度列表
# @sparkai-list Messages_ => 提示列表
# @sparkai-custom driveBySensor => 传感器控制 左功率 %n 右功率 %n 执行 %b
# @sparkai-custom-arg driveBySensor LeftPower_ => 左功率
# @sparkai-custom-arg driveBySensor RightPower_ => 右功率
# @sparkai-custom-arg driveBySensor Enabled_ => 执行

Power_ = 0
BasePower_ = 0
Counter_ = 0
Speeds_ = PikaStdData.List()
Messages_ = PikaStdData.List()

def driveBySensor(LeftPower_, RightPower_, Enabled_):
    global Power_, BasePower_, Counter_, Speeds_, Messages_
    if Enabled_:
        _motor.mov_power(LeftPower_, RightPower_)
    else:
        _motor.mov_stop()

global Power_, BasePower_, Counter_, Speeds_, Messages_
Power_ = 80
BasePower_ = 45
Counter_ = 0
Speeds_.append('30')
Speeds_.append('50')
Speeds_.append('70')
Speeds_.insert(2, '40')
Speeds_.set(2, '45')
Messages_.append('START')
Messages_.append('LINE')
Messages_.append('STOP')

_motor.pair(4, 5, 1)
_motor.mov_set_stop_module(1)
_motor.mov_set_advance_offset(0, 0)
_motor.mov_set_retreat_offset(0, 0)
_motor.mov_find_line_init()
_matrix.show_roll(str(Messages_[1]))
driveBySensor(Speeds_[1], Speeds_[2], _key.key_mast("left", 1))

if _color.cmp_lux(0, ">", 300) and not _touch.state(2):
    _motor.mov_dir_power("advance", 50)
else:
    _motor.mov_dir_power_seconds("retreat", BasePower_, 1)

if _ultrasion.cmp_value(3, "<", 20) or _color.lux_state(1):
    _motor.mov_for_power_seconds(30, 30, 0.5)

while not (_touch.state(0)):
    _motor.mov_find_line_run(_color.lux(0), _color.lux(1), Power_ * 0.5, Power_ * 0.5, 0.1, 0.6)
    Counter_ += 1
    if Counter_ > 3:
        _matrix.show_roll(str(Speeds_.dataToindex('45')))
    else:
        _matrix.show_roll(str(Messages_[2]))
    _os.sleep_s(0.001)

for count in range(3):
    _matrix.show_roll(str(_random.randint(1, 9)))
    _os.sleep_s(0.2)

_motor.mov_for_degrees("advance", 90, "angle")
_motor.mov_for_degrees("retreat", 1, "circly")
_motor.mov_for_degrees("left", 1, "seconds")
_motor.mov_power(Power_, Power_)
_motor.mov_power(0 - BasePower_, 0 - BasePower_)
_motor.mov_stop()
_motor.run_power(4, 50)
_motor.run_for_power_seconds(5, Speeds_[1], 1)
_motor.stop(6)
_motor.stop_module(7, 1)
_motor.reset_relative_position(4)

_matrix.show(0x1F, 0x11, 0x15, 0x15, 0x15, 0x11, 0x1F)
_matrix.set_brightness(4)
_matrix.set_pixel_brightness(2, 3, 1)
_matrix.show_roll(str(len('Spark AI')))
_matrix.show_roll(str((8 + 2) - (9 / 3)))
_matrix.show_roll(str(_math.fmod(17, 5)))
_matrix.show_roll(str(_math.round(3.6)))
_matrix.show_roll(str(_os.timer()))
_matrix.show_roll(str(_os.voic()))
_matrix.show_roll(str(_ultrasion.value(3)))
_matrix.show_roll(str(Speeds_.num()))

if str('Spark AI').find(str('AI')) > -1:
    _beep.play_muic("c", 0.25)

if Power_ > 10 and Power_ < 100:
    _matrix.show_roll(str(Power_))

if Power_ == 80:
    _matrix.show_roll(str('OK'))

if Speeds_.list_if_data('45'):
    Speeds_.remove_index(2)

Speeds_.remove_all()
_beep.stop()
_os.resetTimer()
_mem.restyaw()
_matrix.clear()

while True:
    if _key.key_remote("up", "press"):
        _motor.mov_power(Power_, Power_)
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
