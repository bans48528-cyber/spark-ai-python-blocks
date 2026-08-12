# @var ZuiDaGongL_=最大功率
# @var JiChuGongL_=基础功率
# @var XunXianCiShu_=巡线次数
# @list SuDuBiao_=速度表
# @list TiShiBiao_=提示表

ZuiDaGongL_ = 0
JiChuGongL_ = 0
XunXianCiShu_ = 0
SuDuBiao_ = PikaStdData.List()
TiShiBiao_ = PikaStdData.List()

global ZuiDaGongL_, JiChuGongL_, XunXianCiShu_, SuDuBiao_, TiShiBiao_
ZuiDaGongL_ = 80
JiChuGongL_ = 45
XunXianCiShu_ = 0

SuDuBiao_.append('30')
SuDuBiao_.append('50')
SuDuBiao_.append('70')
TiShiBiao_.append('Start')
TiShiBiao_.append('Line')
TiShiBiao_.append('Stop')

_motor.mov_find_line_init()
_motor.pair(4, 5, 1)
_matrix.show_roll(str(TiShiBiao_[1]))

while not (_touch.state(0)):
    _motor.mov_find_line_run(_color.lux(0), _color.lux(1), ZuiDaGongL_, JiChuGongL_, 0.1, 0.6)
    XunXianCiShu_ += 1
    if XunXianCiShu_ > 10:
        _matrix.show_roll(str(SuDuBiao_[2]))
    else:
        _matrix.show_roll(str(TiShiBiao_[2]))
    _os.sleep_s(0.001)

_motor.mov_for_power_seconds(0, 0, 0.2)
_matrix.show_roll(str(TiShiBiao_[3]))
_beep.play_muic("c", 0.25)
