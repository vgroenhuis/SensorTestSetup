# The web pages are gzipped at configure time and embedded, so one firmware image (and one OTA update) has everything.
set(WEB_SRC "${PROJECT_DIR}/web")
set(WEB_OUT "${CMAKE_CURRENT_BINARY_DIR}/web")
if(NOT CMAKE_BUILD_EARLY_EXPANSION)     # (ESP-IDF first reads this file in script mode, for the requirements only)
    # A changed page or packer re-runs CMake, and with it the packer.
    file(GLOB_RECURSE WEB_INPUTS CONFIGURE_DEPENDS "${WEB_SRC}/*")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${WEB_INPUTS} "${PROJECT_DIR}/tools/pack_web.py")
    execute_process(COMMAND ${PYTHON} "${PROJECT_DIR}/tools/pack_web.py" "${WEB_SRC}" "${WEB_OUT}"
                    RESULT_VARIABLE PACK_RESULT OUTPUT_VARIABLE PACK_OUT ERROR_VARIABLE PACK_ERR)
    if(NOT PACK_RESULT EQUAL 0)
        message(FATAL_ERROR "pack_web.py failed: ${PACK_OUT} ${PACK_ERR}")
    endif()
    file(GLOB WEB_GZ "${WEB_OUT}/*.gz")
endif()

idf_component_register(SRCS "main.c" "display.c" "sensors.c" "i2cbus.c" "gpioparts.c" "tof.cpp" "matrix.c" "web.c"
                       INCLUDE_DIRS "." "${WEB_OUT}"
                       EMBED_FILES ${WEB_GZ}
                       REQUIRES closer_demo u8g2 vl53l7cx esp_http_server esp_driver_spi esp_driver_gpio esp_driver_i2c
                                esp_driver_ledc esp_driver_pcnt esp_timer nvs_flash cjson)
