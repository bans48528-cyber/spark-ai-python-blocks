if _color.cmp_lux(0, ">", 300) and not _touch.state(2):
    _motor.mov_dir_power("advance", 50)
else:
    _motor.mov_dir_power_seconds("retreat", 40, 1)

if _ultrasion.cmp_value(3, "<", 20) or _color.lux_state(1):
    _motor.mov_for_power_seconds(30, 30, 0.5)

for count in range(3):
    _matrix.show_roll(str(_random.randint(1, 9)))
    _os.sleep_s(0.2)

while not (_key.key_mast("right", 1)):
    _matrix.show_roll(str(_ultrasion.value(3)))
    _os.sleep_s(0.001)
