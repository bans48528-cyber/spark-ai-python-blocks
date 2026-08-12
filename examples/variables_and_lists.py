# @var Power_=最大功率
# @var Count_=运行次数
# @list Speeds_=速度列表

Power_ = 0
Count_ = 0
Speeds_ = PikaStdData.List()

global Power_, Count_, Speeds_
Power_ = 80
Count_ = 0

Speeds_.append('30')
Speeds_.append('50')
Speeds_.insert(2, '40')
Speeds_.set(2, '45')

_matrix.show_roll(str(Speeds_[1]))
_matrix.show_roll(str(Speeds_.dataToindex('45')))
_matrix.show_roll(str(Speeds_.num()))

if Speeds_.list_if_data('45'):
    Count_ += 1
    _motor.mov_for_power_seconds(Speeds_[1], Speeds_[2], 0.5)

Speeds_.remove_index(2)
_matrix.show_roll(str(Count_))
