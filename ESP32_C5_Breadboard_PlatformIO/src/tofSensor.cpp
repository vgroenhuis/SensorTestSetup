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

/* Setup ---------------------------------------------------------------------*/
void initTofSensor()
{
  // Initialize serial for output.
  //SerialPort.begin(115200);
//  SerialPort.setTimeout(1000);

/*
  pinMode(LED_BUILTIN, OUTPUT);
  for (int i=0;i<10;i++) {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
    digitalWrite(LED_BUILTIN, LOW);
    delay(100);
  }
*/
  /*

  int x = SerialPort.parseInt();
  SerialPort.printf("Received: %d\n", x);
  //while (!SerialPort) ;
  SerialPort.println("VL53L7CX Hello World Example");
  */

  // Initialize I2C bus.

//  DEV_I2C.setSDA(4);
//  DEV_I2C.setSCL(5);

  //DEV_I2C.setClock(400000);
  //DEV_I2C.begin();

  //Serial.println("ToF sensor initializing");
  
  //pinMode(I2C_RST_PIN, OUTPUT);
  //digitalWrite(I2C_RST_PIN, LOW);
  //pinMode(LPN_PIN, OUTPUT);
  //digitalWrite(LPN_PIN, LOW); // LOW: comms disabled, HIGH: comms enabled

  // Test the I2C bus by sending random data to a dummy address (e.g., 0x55)
  /*
  if (0) {
    for (int j=0;j<10;j++) {
      DEV_I2C.beginTransmission(0x55);
      for (int i = 0; i < 8; ++i) {
        DEV_I2C.write(random(0, 256));
      }
      uint8_t error = DEV_I2C.endTransmission();
      SerialPort.printf("I2C test write to 0x55, error code: %d\n", error);
      delay(1000);
    }
  }*/

  //SerialPort.println("I2C started\n");
  

  // Configure VL53L7CX component.
  sensor_vl53l7cx_top.begin();
  SerialPort.println("Initializing Time-of-Flight sensor");

  sensor_vl53l7cx_top.init_sensor();
  //SerialPort.println("ToF sensor initialized");

  //return;

  sensor_vl53l7cx_top.vl53l7cx_set_ranging_frequency_hz(60);
  sensor_vl53l7cx_top.vl53l7cx_set_ranging_mode(VL53L7CX_RANGING_MODE_CONTINUOUS);

  // Start Measurements
  sensor_vl53l7cx_top.vl53l7cx_start_ranging();
  //SerialPort.println("ToF sensor start ranging");
}

VL53L7CX_ResultsData getToFData() {
  VL53L7CX_ResultsData tofResults;
  uint8_t NewDataReady = 0;
  uint8_t status;

  do {
    status = sensor_vl53l7cx_top.vl53l7cx_check_data_ready(&NewDataReady);
  } while (!NewDataReady);

  if ((status == VL53L7CX_STATUS_OK) && (NewDataReady)) {
    status = sensor_vl53l7cx_top.vl53l7cx_get_ranging_data(&tofResults);
  }
  if (status != VL53L7CX_STATUS_OK) {
    Serial.printf("getToFData: invalid status: %d\n", status);
  }

  return tofResults;
}

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

/*/
  if (Serial.available()>0)
  {
    handle_cmd(Serial.read());
  }
*/
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