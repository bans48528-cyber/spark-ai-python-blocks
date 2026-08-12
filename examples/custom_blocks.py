# @sparkai-variable TargetPower_ => 目标功率
# @sparkai-variable LoopCount_ => 循环次数
# @sparkai-custom sensorDrive => 传感器巡线 左功率 %n 右功率 %n 执行 %b
# @sparkai-custom-arg sensorDrive LeftPower_ => 左功率
# @sparkai-custom-arg sensorDrive RightPower_ => 右功率
# @sparkai-custom-arg sensorDrive Enabled_ => 执行

TargetPower_ = 0
LoopCount_ = 0

def sensorDrive(LeftPower_, RightPower_, Enabled_):
    global TargetPower_, LoopCount_
    if Enabled_:
        _motor.mov_power(LeftPower_, RightPower_)
    else:
        _motor.mov_stop()

global TargetPower_, LoopCount_
TargetPower_ = 60
LoopCount_ = 0

_motor.pair(4, 5, 1)
_motor.mov_find_line_init()

for count in range(3):
    sensorDrive(TargetPower_, TargetPower_ * 0.8, not _touch.state(0))
    LoopCount_ += 1
    _matrix.show_roll(str(LoopCount_))
    _os.sleep_s(0.001)

_motor.mov_stop()
_matrix.show_roll(str('Done'))
