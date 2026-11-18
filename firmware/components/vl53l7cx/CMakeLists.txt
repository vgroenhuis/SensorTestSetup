# ST's VL53L7CX driver (ULD) as packaged by STM32duino (https://github.com/stm32duino/VL53L7CX, commit 7b21bdb,
# BSD-3-Clause: LICENSE.md), with the Arduino platform layer replaced by ESP-IDF i2c_master (vl53l7cx_platform.*)
# and the class constructor taking an i2c_master device. Everything else is ST's code, unchanged.
idf_component_register(SRCS "vl53l7cx_api.cpp" "vl53l7cx_platform.cpp" "vl53l7cx_plugin_detection_thresholds.cpp"
                            "vl53l7cx_plugin_motion_indicator.cpp" "vl53l7cx_plugin_xtalk.cpp"
                       INCLUDE_DIRS "."
                       REQUIRES esp_driver_i2c freertos)
# (ST's code compares signed and unsigned values in places)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-sign-compare -Wno-unused-variable)
