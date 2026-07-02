#pragma once
#include "vl53l7cx_api.h"
#include <array>

struct TofServerSettings {
	bool outlierEnabled;
	uint16_t outlierThresholdMm;
	uint8_t resolution;
};

void initTofSensor();

VL53L7CX_ResultsData getToFData();

void tofSensorLoop();

bool getLatestTofDataForPublish(VL53L7CX_ResultsData &outResults);

TofServerSettings getTofServerSettings();

uint8_t getTofZoneCount();
uint8_t getTofGridSide();

bool setTofOutlierEnabled(bool enabled);
bool setTofOutlierThresholdMm(uint16_t thresholdMm);
bool setTofResolution(uint8_t resolution);

void tofSensorLoopPrintSerial();