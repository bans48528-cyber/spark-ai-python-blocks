_matrix.show(0x1F, 0x11, 0x15, 0x15, 0x15, 0x11, 0x1F)
_matrix.set_brightness(4)
_matrix.set_pixel_brightness(2, 3, 1)

_matrix.show_roll(str("Spark AI"))
_matrix.show_roll(str(len("Spark AI")))
_matrix.show_roll(str((8 + 2) - (9 / 3)))
_matrix.show_roll(str(_math.fmod(17, 5)))
_matrix.show_roll(str(_math.round(3.6)))
_matrix.show_roll(str(_random.randint(1, 9)))
_matrix.show_roll(str(_os.timer()))
_matrix.show_roll(str(_os.voic()))

if str("Spark AI").find(str("AI")) > -1:
    _beep.play_muic("c", 0.25)

_beep.stop()
_os.resetTimer()
_mem.restyaw()
_matrix.clear()
