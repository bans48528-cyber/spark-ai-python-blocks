# Spark AI 1.1.9 Split Load Tests

These files split feature groups so Spark AI load failures can be isolated by
feature family.

Recommended manual test order:

1. `01_motors_basic.py`
2. `02_matrix_buzzer_runtime.py`
3. `03_variables_lists.py`
4. `04_custom_blocks.py`
5. `05_sensors_controls.py`
6. `06_line_patrol_threshold.py` - known Spark AI 1.1.9 load-failure case
7. `07_remote_controller.py`
8. `08_threshold_remote_combo.py` - known Spark AI 1.1.9 load-failure case
9. `09_threshold_only_one.py` - known Spark AI 1.1.9 load-failure case
10. `10_threshold_only_two_500.py` - known Spark AI 1.1.9 load-failure case
11. `11_threshold_only_two_mixed.py` - known Spark AI 1.1.9 load-failure case
12. `12_threshold_line_no_variables.py` - known Spark AI 1.1.9 load-failure case

For each non-threshold file, generate a `.sparkai` project and test
open/save/reopen in Spark AI 1.1.9. Treat direct `.sparkai` results as the
reliability signal; clipboard XML is only for visual inspection.

Do not treat the threshold files as generator regressions. They document the
Spark AI 1.1.9 issue where `set_color_threshold_value` projects save but fail to
reload.
