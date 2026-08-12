# @sparkai-variable Power_ => 最大功率
# @sparkai-variable Count_ => 运行次数
# @sparkai-list Speeds_ => 速度列表
# @sparkai-list Messages_ => 提示列表

Power_ = 0
Count_ = 0
Speeds_ = PikaStdData.List()
Messages_ = PikaStdData.List()

global Power_, Count_, Speeds_, Messages_
Power_ = 80
Count_ = 0

Speeds_.append("30")
Speeds_.append("50")
Speeds_.append("70")
Speeds_.insert(2, "40")
Speeds_.set(2, "45")

Messages_.append("START")
Messages_.append("LINE")
Messages_.append("STOP")

_matrix.show_roll(str(Speeds_[1]))
_matrix.show_roll(str(Speeds_.dataToindex("45")))
_matrix.show_roll(str(Speeds_.num()))
_matrix.show_roll(str(Messages_[2]))

if Speeds_.list_if_data("45"):
    Count_ += 1
    _motor.mov_power(Power_, Power_)

Speeds_.remove_index(2)
Speeds_.remove_all()
_matrix.show_roll(str(Count_))
