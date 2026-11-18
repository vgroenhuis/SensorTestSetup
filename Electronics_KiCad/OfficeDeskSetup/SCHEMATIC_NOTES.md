# SensorTestSetup PCB: schematic notes (revision 0.1)

The schematic follows [`../PCB_SPEC.md`](../PCB_SPEC.md) (draft 0.7). It replaces the breadboard schematic that was in
`OfficeDeskSetup.kicad_sch` (still in the git history). KiCad 10.

## Files

| File | What |
| --- | --- |
| `OfficeDeskSetup.kicad_sch` | Root sheet: overview, I2C address list, the seven sheets |
| `usb_pd.kicad_sch` | 1: USB-C POWER (HUSB238 PD sink), USB-C PROG, CH334R hub |
| `battery.kicad_sch` | 2: BQ25792 charger with input FETs, 3S pack, BQ77915 protection and balancing |
| `rails.kicad_sch` | 3: power switch, V_BUS eFuse + INA226, 3.3 V, 5 V, V_SERVO, V_DXL, LEDs, exposed power |
| `mcu_main.kicad_sch` | 4: ESP32-C5 'main', main I2C bus, TFT, UART0 header, RGB LED, mounting holes |
| `mcu_io.kicad_sch` | 5: ESP32-C5 'io', TB6612FNG with two motor ports, Dynamixel port, VL53L7CX |
| `i2c_parts.kicad_sch` | 6: MCP23017, PCA9685 (servos, buzzer), TCA9548A (pressure sensors, Qwiic) |
| `sensors.kicad_sch` | 7: MCP3008, ADS1115, pot, LDR, MH socket, IR sensor, IMU, AHT20, VEML7700, AS5600, HX711, HC-SR04 |
| `OfficeDeskSetup.kicad_sym`, `sym-lib-table` | Symbols drawn for this board (parts not in the KiCad library) |
| `OfficeDeskSetup.pretty`, `.3dshapes`, `fp-lib-table` | Footprints and 3D models (VRML) imported from LCSC, see below |
| `bom.csv` | Parts list with LCSC numbers, written with the schematic |
| `gen/` | The generator: `design.py` describes the board, `schgen.py` writes KiCad files, `make.py` runs it |

Symbols: KiCad 10 standard libraries, plus the Espressif library (`PCM_Espressif`, as before) for the
ESP32-C5-WROOM-1U. Connections are made by net labels at every pin; nets that cross sheets have global labels.

## Regenerating

Edit `gen/design.py`, then:

```bash
python3 gen/make.py --symbols /usr/share/kicad/symbols --espressif <path>/Espressif.kicad_sym
```

The symbol folder must be KiCad 10's (`*.kicad_symdir`); `Espressif.kicad_sym` comes from
github.com/espressif/kicad-libraries. Regenerating overwrites the sheets: once the schematic is edited by hand in KiCad
(moving parts for readability, adding wires), stop using the generator.

## Checks done

* Each sheet was converted to the KiCad 7 format, loaded by `kicad-cli` 7, and its exported netlist compared pin by pin
  with the design: 1395 pins, 268 nets, no differences. The sheets were plotted and looked over for overlaps.
* Every footprint named exists in the KiCad 10 footprint library, the project library or the Espressif library.
* ERC with `kicad-cli` 10: 0 errors; 2 warnings (LSM6DS3TR-C SDO/SA0 and SDX strapped to GND), excluded in the project.
* Pads: every symbol pin has a pad with the same number in its footprint (all 426 parts with a footprint).

## Choices made in the schematic (not spelled out in the specification)

* **MCP23017 bank B**: GPB0–3 buttons (internal pull-ups), GPB4 MH module DO, GPB5 IR sensor DO, GPB6 **V_DXL enable**
  (100 k pull-down), GPB7 **PCA9685 OE** (10 k pull-up). GPB7 and GPA7 are outputs only. All of bank B is also on the
  2×5 header. Bank A: GPA0–3 4 LEDs with 1 k (the TFT shows the rest), GPA4–5 2 toggle switches (internal pull-ups),
  GPA6–7 free.
* **Potentiometers**: 4 on the MCP3008, pots 0–3 on ch 0–3 (the breadboard had its one pot on ch 7: the
  firmware's channel numbers change); ch 7 is on an analog input header (the ADS1115 header keeps 4 inputs).
* **Dynamixel DIR**: pulled **up** (10 k), not down as in section 5: the 74AHCT1G125 enable is active low, so a pulled-up
  DIR keeps the transmitter off at reset. Firmware: transmit with DIR low (invert RTS).
* **Power switch**: a 4-pole slide switch (3 poles used): pole 1 takes the eFuse EN (through a 1 M / 169 k divider from
  the charger's SYS output), poles 2 and 3 break CC1 and CC2, each bypassed by a solder jumper that is **closed** by
  default, so by default the switch does not break CC (section 6). The part is still to be chosen.
* **V_BUS switch**: TPS259472 eFuse, current limit about 5 A; V_DXL: the same part at about 3 A.
* **Charger inputs**: two back-to-back N-MOSFET pairs on ACDRV1/ACDRV2 (VAC1 = PD, VAC2 = PROG). The BQ25792 symbol
  is KiCad's BQ25798 (same package and pins); the value and LCSC number say BQ25792.
* **Battery protection**: BQ77915 with low-side charge and discharge FETs and a 5 mΩ sense resistor: the pack's minus
  (`BAT_N`) is **not** GND. The 10 k NTC for the charger (TS) and the one for the protector are separate parts.
* **HX711**: the on-chip regulator is not used; AVDD and the load-cell excitation are a ferrite-filtered 3.3 V.
  RATE on a 3-pad solder jumper (10 Hz default).
* **TFT backlight**: BLK pulled down, so the backlight is off until the firmware drives it.
* **MH module**: VCC 3.3 V by default (3-pad jumper to 5 V); with 5 V, fit the DNP 20 k so AO is divided to 3.3 V.
* **IR sensor**: LM393 with a threshold trimmer; DO goes to the MCP23017, AO to MCP3008 ch 4. The IR LED's jumper is
  closed by default.
* Series resistors and ESD arrays (USBLC6-2SC6) on the encoder lines and on every Qwiic connector's SDA/SCL.
* Pins are as in section 5; `firmware/main/board.h` needs no change for this schematic.

## Imported footprints

Imported from LCSC/EasyEDA with `easyeda2kicad --footprint --3d --project-relative` (only the `.wrl` models are kept;
the footprints reference them). Each was checked against the datasheet, and the symbol's pin numbers against it:

| Part | LCSC | Footprint | Checked |
| --- | --- | --- | --- |
| MLT-8530 buzzer | C94599 | BUZ-SMD_4P-L8.5-W8.5-P8.50-BR | coil on pads 1 (+) and 4 (-), pads 2 and 3 dummy (Huaneng spec, 2017): own symbol, KiCad's buzzer put "-" on a dummy pad |
| TPS259472ARPW | C3662789 | VQFN-10_L2.0-W2.0-P0.45-TL | TI datasheet Table 5-1: pin 10 is **ITIMER** (not AUXOFF, that is the TPS259470's pin 3), now open (fastest overcurrent response; it was tied to GND) |
| VL53L7CX | C5270520 | LGA-16_L6.4-W3.0_VL53L5CXV0GC-1 | DS13865 Rev 8 Table 3: RSVD1-4 (A6, A7, C6, A2) to GND, RSVD5 (C5) open, RSVD6 (C2) 47 k pull-up; **C6 and C2 were left open** |
| WF100DPZ | C22388673 | SOP-6_L7.0-W7.0-P2.54-LS10.3-TL | pins match the LCSC symbol |
| ITR20001/T | C264269 | OPTO-TH_4P_ITR20001-T-F316 | Everlight Rev 6: 1 A, 2 K, **3 E, 4 C** (emitter and collector were swapped) |
| AHT20 | C2757850 | SENSOR-SMD_L3.0-W3.0-P1.00-BR | Aosong V1.0 Table 5: 1 NC, 2 VDD, 3 SCL, 4 SDA, 5 GND, 6 NC (**the symbol was wrong**); land pattern as Figure 8; VDD through 330 R with 10 uF, as the datasheet asks |
| VEML7700-TT | C1850416 | SENSOR-SMD_EML7700-TT | pins match the LCSC symbol |
| Toggle switch 2MS1T1B1M1QES-5 | C496169 | SW-TH_2MS1T1B1M1QES-5 | pad 2 (middle) is the common |

Also found by the pad check: the INA226 shunt used KiCad's 4-terminal `R_Shunt` on a 2-pad 2512 footprint, so the
sense lines had no pads. Now a 2-terminal 2512 with two net ties (NT1, NT2) for the Kelvin sense lines: place them on
the shunt's pads.

## To verify against the datasheets before layout

The datasheets of ti.com, st.com and pololu.com could not be fetched from the environment used, so these come from
the specification, distributor summaries and reference designs. Items are also marked "verify" on the sheets.

| Part | What |
| --- | --- |
| TPS259472ARPW (custom symbol) | The ILM resistors (665 Ω for 5 A, 1.1 kΩ for 3 A); OVCSEL for the 13.8 V clamp |
| BQ77915 (custom symbol) | Pin numbers 1–14 (15–24 confirmed); CCFG for 3 cells; VC3–VC5 tied; filter, gate and LD values; -04 thresholds |
| BQ25792 | PROG 13.7 k (3S, 750 kHz); ILIM_HIZ divider; TS divider 5.23 k / 30.1 k; inductor 2.2 µH; input FET wiring |
| HUSB238 | VSET resistors (14 k = 15 V, 10 k = 12 V, 6.04 k = 9 V, open = 20 V); ISET open = 3.25 A |
| WF100DPZ | Supply at 3.3 V; CSB left open (I2C mode) |
| TPS54331 (custom symbol) | Compensation (29.4 k, 1 nF, 47 pF) and the inductors: check with TI's design tool for 3.3 V and 5/6 V |
| CH334R | Whether the crystal load capacitors are internal (fitted as DNP) |
| AS5600 | 3.3 V mode (VDD5V and VDD3V3 tied) |
| MCP23017 | GPA7/GPB7 output-only |

Parts still to choose (no footprint yet): the four charger input MOSFETs, the two protection MOSFETs and the power
switch. Import their footprints the same way once chosen.
