#pragma once
#include "vl53l7cx_api.h"

void initTofSensor();

VL53L7CX_ResultsData getToFData();

void tofSensorLoopPrintSerial();