/*
 * [1] VL53L7CX brief datasheet: https://www.st.com/resource/en/datasheet/vl53l7cx.pdf
 * [2] VL53L7CX communication datasheet: https://www.st.com/resource/en/user_manual/um3038-a-guide-to-using-the-vl53l7cx-timeofflight-multizone-ranging-sensor-with-90-fov-stmicroelectronics.pdf
 * [3] Breakout board datasheet: https://www.mouser.lt/datasheet/2/389/satel_vl53l7cx-3073828.pdf
 * 60° x 60° square FOV
 * 4x4 (max 60 Hz) or 8x8 (max 15 Hz) grid
 * Ranging distance: up to 3500 mm in dark, around 500 mm outdoors in shadow (a bit less for 8x8 and in corner), accuracy +/- 10 mm
 * Continuous ranging is recommended.
 * Target status: 5 and 9 are valid. Rest can be discarded. See 5.5 Results interpretation [3].
 * 
 * Connection
 * INT
 * I2C_RST --> GND (leave unconnected, is pulled up down with 47K to GND)
 * SDA --> SDA
 * SCL --> SCL
 * LPn (leave unconnected, is pulled up high with 47K)
 * PWREN (connect to 3.3V, there is no 47K pullup resistor soldered on R3 by default)
 * AVDD --> 5V (or 3.3V but then solder SB1)
 * DVDD --> 3.3V
 * GND --> GND
*/

#include "tofSensor.h"

#include <array>
#include <Preferences.h>
#include <math.h>


/**
 ******************************************************************************
 * @file    VL53L7CX_HelloWorld.ino
 * @author  STMicroelectronics
 * @version V1.0.0
 * @date    16 January 2023
 * @brief   Arduino test application for STMicroelectronics VL53L7CX
 *          proximity sensor satellite based on FlightSense.
 *          This application makes use of C++ classes obtained from the C
 *          components' drivers.
 ******************************************************************************
 * @attention
 *
 * <h2><center>&copy; COPYRIGHT(c) 2021 STMicroelectronics</center></h2>
 *
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the following conditions are met:
 *   1. Redistributions of source code must retain the above copyright notice,
 *      this list of conditions and the following disclaimer.
 *   2. Redistributions in binary form must reproduce the above copyright notice,
 *      this list of conditions and the following disclaimer in the documentation
 *      and/or other materials provided with the distribution.
 *   3. Neither the name of STMicroelectronics nor the names of its contributors
 *      may be used to endorse or promote products derived from this software
 *      without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 ******************************************************************************
 */
/*
 * To use these examples you need to connect the VL53L7CX satellite sensor directly to the Nucleo board with wires as explained below:
 * pin 1 (GND) of the VL53L7CX satellite connected to GND of the Nucleo board
 * pin 2 (IOVDD) of the VL53L7CX satellite connected to 3V3 pin of the Nucleo board
 * pin 3 (AVDD) of the VL53L7CX satellite connected to 5V pin of the Nucleo board
 * pin 4 (PWREN) of the VL53L7CX satellite connected to pin A5 of the Nucleo board
 * pin 5 (LPn) of the VL53L7CX satellite connected to pin A3 of the Nucleo board
 * pin 6 (SCL) of the VL53L7CX satellite connected to pin D15 (SCL) of the Nucleo board
 * pin 7 (SDA) of the VL53L7CX satellite connected to pin D14 (SDA) of the Nucleo board
 * pin 8 (I2C_RST) of the VL53L7CX satellite connected to pin A1 of the Nucleo board
 * pin 9 (INT) of the VL53L7CX satellite connected to pin A2 of the Nucleo board
 */


/*
0 Ranging data are not updated
1 Signal rate too low on SPAD array
2 Target phase
3 Sigma estimator too high
4 Target consistency failed
5 Range valid
6 Wrap around not performed (typically the first range)
7 Rate consistency failed
8 Signal rate too low for the current target
9 Range valid with large pulse (may be due to a merged target)
10 Range valid, but no target detected at previous range
11 Measurement consistency failed
12 Target blurred by another one, due to sharpener
13 Target detected but inconsistent data. Frequently happens for secondary targets.

16 No target
17 Negative distance
18 Distance above threshold

255 No target detected (only if number of targets detected is enabled)


*/

/* Includes ------------------------------------------------------------------*/
#include <vl53l7cx_class.h>


#define DEV_I2C Wire
#define SerialPort Serial

#define LPN_PIN -1
#define I2C_RST_PIN -1

void print_result(VL53L7CX_ResultsData *Result);
void clear_screen(void);
void handle_cmd(uint8_t cmd);
void display_commands_banner(void);

// Components.
VL53L7CX sensor_vl53l7cx_top(&DEV_I2C, LPN_PIN, I2C_RST_PIN);

bool EnableAmbient = false;
bool EnableSignal = false;
uint8_t res = VL53L7CX_RESOLUTION_4X4;
char report[256];

namespace {
  static const char *TOF_SETTINGS_NAMESPACE = "tof_cfg";
  static const char *KEY_OUTLIER_ENABLED = "out_en";
  static const char *KEY_OUTLIER_MM = "out_mm";
  static const char *KEY_RESOLUTION = "res";
  static const uint16_t defaultOutlierThresholdMm = 350;
  static const uint16_t minOutlierThresholdMm = 20;
  static const uint16_t maxOutlierThresholdMm = 2000;

  TofServerSettings tofSettings = {
    true,
    defaultOutlierThresholdMm,
    VL53L7CX_RESOLUTION_8X8
  };

  VL53L7CX_ResultsData latestRawResults = {};
  VL53L7CX_ResultsData latestFilteredResults = {};
  bool hasLatestRaw = false;
  bool hasLatestFiltered = false;
  uint8_t activeResolution = VL53L7CX_RESOLUTION_4X4;
  bool resolutionSwitchPending = false;
  unsigned long lastResolutionSwitchAttemptMs = 0;
  const unsigned long resolutionSwitchRetryIntervalMs = 500;

  static const uint8_t TOF_STATUS_FILTER_NO_TARGET = 16;
  static const uint8_t TOF_STATUS_FILTER_NON_POSITIVE_DISTANCE = 17;
  static const uint8_t TOF_STATUS_FILTER_DISTANCE_ABOVE_THRESHOLD = 18;

  uint8_t clampResolution(uint8_t resolution) {
    return resolution == VL53L7CX_RESOLUTION_8X8 ? VL53L7CX_RESOLUTION_8X8 : VL53L7CX_RESOLUTION_4X4;
  }

  uint8_t gridSideForResolution(uint8_t resolution) {
    return clampResolution(resolution) == VL53L7CX_RESOLUTION_8X8 ? 8 : 4;
  }

  uint8_t zoneCountForResolution(uint8_t resolution) {
    const uint8_t side = gridSideForResolution(resolution);
    return side * side;
  }

  uint8_t rangingFrequencyForResolution(uint8_t resolution) {
    return clampResolution(resolution) == VL53L7CX_RESOLUTION_8X8 ? 15 : 60;
  }

  bool applySensorResolution(uint8_t resolution) {
    const uint8_t clamped = clampResolution(resolution);
    const uint8_t safeFrequencyHz = 15;
    const uint8_t targetFrequencyHz = rangingFrequencyForResolution(clamped);

    auto resetAndApplyResolution = [&]() -> bool {
      Serial.println("ToF: attempting sensor re-init for resolution switch");

      sensor_vl53l7cx_top.vl53l7cx_stop_ranging();
      yield();
      sensor_vl53l7cx_top.init_sensor();
      yield();

      if (sensor_vl53l7cx_top.vl53l7cx_set_resolution(clamped) != VL53L7CX_STATUS_OK) {
        Serial.println("ToF: re-init path failed to set resolution");
        return false;
      }
      if (sensor_vl53l7cx_top.vl53l7cx_set_ranging_frequency_hz(targetFrequencyHz) != VL53L7CX_STATUS_OK) {
        Serial.println("ToF: re-init path failed to set frequency");
        return false;
      }
      if (sensor_vl53l7cx_top.vl53l7cx_set_ranging_mode(VL53L7CX_RANGING_MODE_CONTINUOUS) != VL53L7CX_STATUS_OK) {
        Serial.println("ToF: re-init path failed to set ranging mode");
        return false;
      }
      if (sensor_vl53l7cx_top.vl53l7cx_start_ranging() != VL53L7CX_STATUS_OK) {
        Serial.println("ToF: re-init path failed to start ranging");
        return false;
      }
      return true;
    };

    if (clamped == VL53L7CX_RESOLUTION_8X8) {
      // Some driver paths reject setting frequency once ranging is stopped.
      if (sensor_vl53l7cx_top.vl53l7cx_set_ranging_frequency_hz(safeFrequencyHz) != VL53L7CX_STATUS_OK) {
        Serial.println("ToF: failed to set safe frequency before stopping ranging");
        return false;
      }
    }

    if (sensor_vl53l7cx_top.vl53l7cx_stop_ranging() != VL53L7CX_STATUS_OK) {
      Serial.println("ToF: failed to stop ranging before resolution switch");
      return false;
    }

    if (sensor_vl53l7cx_top.vl53l7cx_set_resolution(clamped) != VL53L7CX_STATUS_OK) {
      Serial.println("ToF: failed to set resolution");
      if (!resetAndApplyResolution()) {
        sensor_vl53l7cx_top.vl53l7cx_start_ranging();
        return false;
      }

      res = clamped;
      hasLatestRaw = false;
      hasLatestFiltered = false;
      return true;
    }

    if (sensor_vl53l7cx_top.vl53l7cx_set_ranging_frequency_hz(targetFrequencyHz) != VL53L7CX_STATUS_OK) {
      Serial.println("ToF: failed to set target frequency after resolution switch");
      sensor_vl53l7cx_top.vl53l7cx_start_ranging();
      return false;
    }

    if (sensor_vl53l7cx_top.vl53l7cx_start_ranging() != VL53L7CX_STATUS_OK) {
      Serial.println("ToF: failed to restart ranging after resolution switch");
      return false;
    }

    res = clamped;
    activeResolution = clamped;
    hasLatestRaw = false;
    hasLatestFiltered = false;
    return true;
  }

  bool tofStatusIsValidForFilter(uint8_t status) {
    return status == 5 || status == 9;
  }

  uint16_t clampOutlierThresholdMm(uint16_t thresholdMm) {
    if (thresholdMm < minOutlierThresholdMm) {
      return minOutlierThresholdMm;
    }
    if (thresholdMm > maxOutlierThresholdMm) {
      return maxOutlierThresholdMm;
    }
    return thresholdMm;
  }

  bool saveTofSettingsToNvs() {
    Preferences preferences;
    if (!preferences.begin(TOF_SETTINGS_NAMESPACE, false)) {
      Serial.println("NVS open failed for writing ToF settings");
      return false;
    }

    bool okOutlierEnabled = preferences.putBool(KEY_OUTLIER_ENABLED, tofSettings.outlierEnabled) > 0;
    bool okOutlier = preferences.putUInt(KEY_OUTLIER_MM, tofSettings.outlierThresholdMm) > 0;
    bool okResolution = preferences.putUChar(KEY_RESOLUTION, clampResolution(tofSettings.resolution)) > 0;
    preferences.end();
    return okOutlierEnabled && okOutlier && okResolution;
  }

  void loadTofSettingsFromNvs() {
    Preferences preferences;
    if (!preferences.begin(TOF_SETTINGS_NAMESPACE, true)) {
      Serial.println("NVS open failed for reading ToF settings");
      if (!saveTofSettingsToNvs()) {
        Serial.println("NVS also failed for writing ToF settings");
      }
      return;
    }

    tofSettings.outlierEnabled = preferences.getBool(KEY_OUTLIER_ENABLED, tofSettings.outlierEnabled);
    const uint32_t storedOutlierMm = preferences.getUInt(KEY_OUTLIER_MM, defaultOutlierThresholdMm);
    const uint8_t storedResolution = preferences.getUChar(KEY_RESOLUTION, VL53L7CX_RESOLUTION_8X8);
    preferences.end();

    tofSettings.outlierThresholdMm = clampOutlierThresholdMm((uint16_t)storedOutlierMm);
    tofSettings.resolution = clampResolution(storedResolution);
  }

  void applyFilteringToResults(const VL53L7CX_ResultsData &rawResults, unsigned long nowMs) {
    int32_t previousDistanceMm[64];
    uint8_t previousStatus[64];
    uint8_t previousTargetCount[64];

    for (size_t zone = 0; zone < 64; ++zone) {
      const size_t targetIndex = zone * VL53L7CX_NB_TARGET_PER_ZONE;
      previousDistanceMm[zone] = latestFilteredResults.distance_mm[targetIndex];
      previousStatus[zone] = latestFilteredResults.target_status[targetIndex];
      previousTargetCount[zone] = latestFilteredResults.nb_target_detected[zone];
    }

    latestFilteredResults = rawResults;

    const size_t zoneCount = zoneCountForResolution(activeResolution);

    if (!hasLatestFiltered) {
      hasLatestFiltered = true;

      return;
    }

    for (size_t zone = 0; zone < zoneCount; ++zone) {
      const size_t targetIndex = zone * VL53L7CX_NB_TARGET_PER_ZONE;

      /*
      const bool rawHasTarget = rawResults.nb_target_detected[zone] > 0;
      if (!rawHasTarget) {
        latestFilteredResults.target_status[targetIndex] = TOF_STATUS_FILTER_NO_TARGET;
        continue;
      }*/

      const uint8_t rawStatus = rawResults.target_status[targetIndex];
      if (!tofStatusIsValidForFilter(rawStatus)) {
        continue;
      }

      const int32_t rawDistanceMm = rawResults.distance_mm[targetIndex];
      if (rawDistanceMm <= 0) {
        latestFilteredResults.target_status[targetIndex] = TOF_STATUS_FILTER_NON_POSITIVE_DISTANCE;
        continue;
      }

      if (tofSettings.outlierEnabled && (rawDistanceMm > tofSettings.outlierThresholdMm)) {
        latestFilteredResults.target_status[targetIndex] = TOF_STATUS_FILTER_DISTANCE_ABOVE_THRESHOLD;
        continue;
      }

      /*
      const bool prevHasTarget = previousTargetCount[zone] > 0;
      const uint8_t prevStatus = previousStatus[zone];
      const int32_t prevDistanceMm = previousDistanceMm[zone];
      const bool hasComparablePrevious = prevHasTarget && tofStatusIsValidForFilter(prevStatus) && prevDistanceMm > 0;
      if (!hasComparablePrevious) {
        latestFilteredResults.target_status[targetIndex] = TOF_STATUS_FILTER_NO_COMPARABLE_PREVIOUS;
        continue;
      }*/

      /*
      const int32_t deltaMm = rawDistanceMm - prevDistanceMm;
      const int32_t absDeltaMm = deltaMm >= 0 ? deltaMm : -deltaMm;
      const bool exceedsOutlierThreshold = (uint16_t)absDeltaMm > tofSettings.outlierThresholdMm;

      int32_t postOutlierDistanceMm = rawDistanceMm;
      if (tofSettings.outlierEnabled && exceedsOutlierThreshold) {
        // Reject outliers by keeping the previous trusted value.
        postOutlierDistanceMm = prevDistanceMm;
        latestFilteredResults.target_status[targetIndex] = TOF_STATUS_FILTER_OUTLIER_REPLACED;
      }
    */

      latestFilteredResults.distance_mm[targetIndex] = rawDistanceMm;
    }
  }

  bool tryReadTofPacket(VL53L7CX_ResultsData &outResults) {
    uint8_t newDataReady = 0;
    const uint8_t statusReady = sensor_vl53l7cx_top.vl53l7cx_check_data_ready(&newDataReady);
    if (statusReady != VL53L7CX_STATUS_OK || !newDataReady) {
      return false;
    }

    const uint8_t statusData = sensor_vl53l7cx_top.vl53l7cx_get_ranging_data(&outResults);
    if (statusData != VL53L7CX_STATUS_OK) {
      Serial.printf("tryReadTofPacket: invalid status: %d\n", statusData);
      return false;
    }

    return true;
  }
}

/* Setup ---------------------------------------------------------------------*/
void initTofSensor()
{
  // Configure VL53L7CX component.
  sensor_vl53l7cx_top.begin();
  SerialPort.println("Initializing Time-of-Flight sensor");

  sensor_vl53l7cx_top.init_sensor();
  //SerialPort.println("ToF sensor initialized");

  //return;

  loadTofSettingsFromNvs();

  const uint8_t initialResolution = clampResolution(tofSettings.resolution);
  tofSettings.resolution = initialResolution;
  activeResolution = initialResolution;
  res = initialResolution;
  sensor_vl53l7cx_top.vl53l7cx_set_resolution(initialResolution);
  sensor_vl53l7cx_top.vl53l7cx_set_ranging_frequency_hz(rangingFrequencyForResolution(initialResolution));
  sensor_vl53l7cx_top.vl53l7cx_set_ranging_mode(VL53L7CX_RANGING_MODE_CONTINUOUS);

  // Start Measurements
  sensor_vl53l7cx_top.vl53l7cx_start_ranging();
  //SerialPort.println("ToF sensor start ranging");
}

VL53L7CX_ResultsData getToFData() {
  VL53L7CX_ResultsData tofResults;
  uint8_t newDataReady = 0;
  uint8_t status;

  do {
    status = sensor_vl53l7cx_top.vl53l7cx_check_data_ready(&newDataReady);
  } while (!newDataReady);

  if ((status == VL53L7CX_STATUS_OK) && (newDataReady)) {
    status = sensor_vl53l7cx_top.vl53l7cx_get_ranging_data(&tofResults);
  }
  if (status != VL53L7CX_STATUS_OK) {
    Serial.printf("getToFData: invalid status: %d\n", status);
  }

  latestRawResults = tofResults;
  hasLatestRaw = true;

  applyFilteringToResults(tofResults, millis());

  return tofResults;
}

void tofSensorLoop() {
  if (resolutionSwitchPending) {
    const unsigned long nowMs = millis();
    if ((nowMs - lastResolutionSwitchAttemptMs) >= resolutionSwitchRetryIntervalMs) {
      lastResolutionSwitchAttemptMs = nowMs;
      if (applySensorResolution(tofSettings.resolution)) {
        resolutionSwitchPending = false;
        Serial.println("ToF: resolution switch applied");
      } else {
        Serial.println("ToF: resolution switch attempt failed; retrying");
      }
    }
  }

  VL53L7CX_ResultsData packet;
  if (!tryReadTofPacket(packet)) {
    return;
  }

  latestRawResults = packet;
  hasLatestRaw = true;

  applyFilteringToResults(packet, millis());
}

bool getLatestTofDataForPublish(VL53L7CX_ResultsData &outResults) {
  if (hasLatestFiltered) {
    outResults = latestFilteredResults;
    return true;
  }

  if (hasLatestRaw) {
    outResults = latestRawResults;
    return true;
  }

  return false;
}

TofServerSettings getTofServerSettings() {
  return tofSettings;
}

bool setTofOutlierEnabled(bool enabled) {
  tofSettings.outlierEnabled = enabled;
  return saveTofSettingsToNvs();
}

bool setTofOutlierThresholdMm(uint16_t thresholdMm) {
  tofSettings.outlierThresholdMm = clampOutlierThresholdMm(thresholdMm);
  return saveTofSettingsToNvs();
}

bool setTofResolution(uint8_t resolution) {
  const uint8_t clamped = clampResolution(resolution);
  if (tofSettings.resolution == clamped && !resolutionSwitchPending) {
    return true;
  }

  tofSettings.resolution = clamped;
  resolutionSwitchPending = (activeResolution != clamped);
  if (!saveTofSettingsToNvs()) {
    Serial.println("Failed to persist ToF resolution");
    return false;
  }

  if (resolutionSwitchPending) {
    Serial.println("ToF: resolution switch queued");
  }

  return true;
}

uint8_t getTofZoneCount() {
  return zoneCountForResolution(activeResolution);
}

uint8_t getTofGridSide() {
  return gridSideForResolution(activeResolution);
}

/*
void tofSensorLoopPrintSerial()
{
  static int counter = 0;
  static unsigned long lastTime = 0;
  static unsigned long iterations = 0;
  static float ips = 0.0;

  counter++;
  iterations++;
  unsigned long now = millis();
  if (now - lastTime >= 1000) {
    ips = iterations * 1000.0 / (now - lastTime);
    iterations = 0;
    lastTime = now;
  }

  VL53L7CX_ResultsData Results;
  uint8_t NewDataReady = 0;
  uint8_t status;

  do {
    status = sensor_vl53l7cx_top.vl53l7cx_check_data_ready(&NewDataReady);
  } while (!NewDataReady);

  if ((!status) && (NewDataReady != 0)) {
    status = sensor_vl53l7cx_top.vl53l7cx_get_ranging_data(&Results);
    //if (counter%10==0) {
      print_result(&Results);
    //}
  }

  //if (counter%10==0) {
    SerialPort.print("Iterations per second: ");
    SerialPort.println(ips, 2);
//    }

/* /
  if (Serial.available()>0)
  {
    handle_cmd(Serial.read());
  }
* /
  //delay(1000);
}

void print_result(VL53L7CX_ResultsData *Result)
{
  int8_t i, j, k, l;
  uint8_t zones_per_line;
  uint8_t number_of_zones = res;

  zones_per_line = (number_of_zones == 16) ? 4 : 8;

  //display_commands_banner();

  //SerialPort.print("Cell Format :\n\n");
  
  for (l = 0; l < VL53L7CX_NB_TARGET_PER_ZONE; l++)
  {
    //snprintf(report, sizeof(report)," \033[38;5;10m%20s\033[0m : %20s\n", "Distance [mm]", "Status");
    //SerialPort.print(report);

    if(EnableAmbient || EnableSignal)
    {
      //snprintf(report, sizeof(report)," %20s : %20s\n", "Signal [kcps/spad]", "Ambient [kcps/spad]");
      //SerialPort.print(report);
    }
  }

  //SerialPort.print("\n\n");

  for (j = 0; j < number_of_zones; j += zones_per_line) // normally 16 zones (4 zones per line)
  {
    //for (i = 0; i < zones_per_line; i++) 
      //SerialPort.print(" -----------------");
    //SerialPort.print("\n");
    
    //for (i = 0; i < zones_per_line; i++)
    //  SerialPort.print("|                 ");
    //SerialPort.print("|\n");
  
    for (l = 0; l < VL53L7CX_NB_TARGET_PER_ZONE; l++) // normally one target per zone
    {
      // Print distance and status 
      for (k = (zones_per_line - 1); k >= 0; k--)
      {
        if (Result->nb_target_detected[j+k]>0)
        {
          snprintf(report, sizeof(report),"%5ld : %5ld ",
              (long)Result->distance_mm[(VL53L7CX_NB_TARGET_PER_ZONE * (j+k)) + l],
              (long)Result->target_status[(VL53L7CX_NB_TARGET_PER_ZONE * (j+k)) + l]);
              SerialPort.print(report);
        }
        else
        {
          snprintf(report, sizeof(report),"%5s : %5s ", "X", "X");
          SerialPort.print(report);
        }
      }
      SerialPort.print("\n");

      if (EnableAmbient || EnableSignal )
      {
        // Print Signal and Ambient 
        for (k = (zones_per_line - 1); k >= 0; k--)
        {
          if (Result->nb_target_detected[j+k]>0)
          {
            if (EnableSignal)
            {
              snprintf(report, sizeof(report),"%5ld : ", (long)Result->signal_per_spad[(VL53L7CX_NB_TARGET_PER_ZONE * (j+k)) + l]);
              SerialPort.print(report);
            }
            else
            {
              snprintf(report, sizeof(report),"%5s : ", "X");
              SerialPort.print(report);
            }
            if (EnableAmbient)
            {
              snprintf(report, sizeof(report),"%5ld ", (long)Result->ambient_per_spad[j+k]);
              SerialPort.print(report);
            }
            else
            {
              snprintf(report, sizeof(report),"%5s ", "X");
              SerialPort.print(report);
            }
          }
          else
          {
            snprintf(report, sizeof(report),"%5s  :  %5s ", "X", "X");
            SerialPort.print(report);
          }
        }
        SerialPort.print("\n");
      }
    }
  }
  //for (i = 0; i < zones_per_line; i++)
   //SerialPort.print(" -----------------");
  SerialPort.print("\n");
}
*/

void toggle_resolution(void)
{
  sensor_vl53l7cx_top.vl53l7cx_stop_ranging();

  switch (res)
  {
    case VL53L7CX_RESOLUTION_4X4:
      res = VL53L7CX_RESOLUTION_8X8;
      break;

    case VL53L7CX_RESOLUTION_8X8:
      res = VL53L7CX_RESOLUTION_4X4;
      break;

    default:
      break;
  }
  sensor_vl53l7cx_top.vl53l7cx_set_resolution(res);
  sensor_vl53l7cx_top.vl53l7cx_start_ranging();
}

void toggle_signal_and_ambient(void)
{
  EnableAmbient = (EnableAmbient) ? false : true;
  EnableSignal = (EnableSignal) ? false : true;
}

void clear_screen(void)
{
  snprintf(report, sizeof(report),"%c[2J", 27); /* 27 is ESC command */
  SerialPort.print(report);
}

void display_commands_banner(void)
{
  snprintf(report, sizeof(report),"%c[2H", 27); /* 27 is ESC command */
  SerialPort.print(report);

  Serial.print("53L7A1 Simple Ranging demo application\n");
  Serial.print("--------------------------------------\n\n");

  Serial.print("Use the following keys to control application\n");
  Serial.print(" 'r' : change resolution\n");
  Serial.print(" 's' : enable signal and ambient\n");
  Serial.print(" 'c' : clear screen\n");
  Serial.print("\n");
}

void handle_cmd(uint8_t cmd)
{
  switch (cmd)
  {
    case 'r':
      toggle_resolution();
      clear_screen();
      break;

    case 's':
      toggle_signal_and_ambient();
      clear_screen();
      break;

    case 'c':
      clear_screen();
      break;

    default:
      break;
  }
}

