# @sparkai-variable Power_ => 最大功率
# @sparkai-variable Counter_ => 运行次数
# @sparkai-list Speeds_ => 速度列表
# @sparkai-custom driveBySensor => 传感器控制 左功率 %n 右功率 %n 执行 %b
# @sparkai-custom-arg driveBySensor LeftPower_ => 左功率
# @sparkai-custom-arg driveBySensor RightPower_ => 右功率
# @sparkai-custom-arg driveBySensor Enabled_ => 执行

Power_ = 0
Counter_ = 0
Speeds_ = PikaStdData.List()

def driveBySensor(LeftPower_, RightPower_, Enabled_):
    global Power_, Counter_, Speeds_
    if Enabled_:
        _motor.mov_power(LeftPower_, RightPower_)
    else:
        _motor.mov_stop()

global Power_, Counter_, Speeds_
Power_ = 80
Counter_ = 0
Speeds_.append('30')
Speeds_.append('50')
Speeds_.insert(2, '40')
Speeds_.set(2, '45')

_motor.pair(4, 5, 1)
_motor.mov_set_stop_module(1)
_motor.mov_set_advance_offset(0, 0)
_motor.mov_set_retreat_offset(0, 0)
_motor.mov_find_line_init()
_motor.mov_find_line_run(_color.lux(0), _color.lux(1), Power_ * 0.5, Power_ * 0.5, 0.1, 0.6)
driveBySensor(Speeds_[1], Speeds_[2], _key.key_mast("left", 1))

if _color.cmp_lux(0, ">", 300) and not _touch.state(2):
    _motor.mov_dir_power("advance", 50)
else:
    _motor.mov_dir_power_seconds("retreat", 40, 1)

if _ultrasion.cmp_value(3, "<", 20) or _color.lux_state(1):
    _motor.mov_for_power_seconds(30, 30, 0.5)

for count in range(2):
    Counter_ += 1
    _matrix.show_roll(str(_random.randint(1, 9)))
    _os.sleep_s(0.2)

while not (_key.key_mast("right", 1)):
    _matrix.show_roll(str(_ultrasion.value(3)))
    _os.sleep_s(0.001)

_motor.mov_for_degrees("advance", 90, "angle")
_motor.mov_power(20, 20)
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
_matrix.show_roll(str(Speeds_.dataToindex('45')))
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
_os.stop_exit()
