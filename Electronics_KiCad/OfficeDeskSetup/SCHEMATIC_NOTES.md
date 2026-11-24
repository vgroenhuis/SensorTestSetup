# SensorTestSetup PCB: schematic notes (revision 0.2)

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
* **Power switch** (rev 0.2): black DPST rocker SS21-BBIWG2-B (C6775929) at the rear edge. Pole 1 takes both eFuse
  enables: it is fed through a diode-OR (2× SS14) from the charger's SYS output and from the 12 V jack (`SW_SUPPLY`),
  and drives two 1 M / 169 k dividers (`VBUS_EN`, `DC_EN`; on above about 8.7 V). Pole 2 breaks **CC1 only**, CC2
  goes straight to the HUSB238. With the switch off, a plug that lands on CC1 sees no Rd, so a power bank stays
  asleep; flip the plug (CC2) to charge with the switch off. Solder jumper JP4 (open) bypasses pole 2 if CC1 should
  never be switched. (Rev 0.1 had a DPDT toggle; both OFF contacts were unused, so DPST does.)
* **12 V input** (rev 0.2): DC jack 5.5 × 2.1 mm (DC007B, C17701683, 7 A) with an SMBJ15A TVS, 10 µF + 1 µF, and a
  second TPS259472 eFuse (5 A, ILM 665 Ω, DVDT 10 nF, OVCSEL jumper) from `DC_12V` into `VBUS_SW`, the same node as
  the pack's eFuse output. **12 V takes priority**: 100 k / 100 k from DC_12V drives an AO3400A that pulls the pack
  eFuse's EN low, so with 12 V present V_BUS comes from the jack and the pack is not used. Both eFuses block reverse
  current. There is **no charging from 12 V** (the charger's inputs stay the two USB-C ports).
* **GND banana hole**: a plated 4.1 mm hole with a 7 mm pad on GND (`BananaHole_4.1mm_Pad`, project library) for a
  4 mm banana plug, at the rear edge by the power switch.
* **V_BUS switch**: TPS259472 eFuse, current limit about 5 A; V_DXL: the same part at about 3 A.
* **Buttons** (rev 0.2): BTN0–3 are Omron B3F-4055 (12 × 12 mm, C84931) at 16 mm pitch, room for caps; the switch is
  between the diagonal pins 1 (BTNx) and 4 (GND), pins 2 and 3 are left open, which is right whichever way the pins
  pair inside.
* **Servo outputs** (rev 0.2): two banks of four at the right edge, each three 1×4 header rows (signal inside, V+,
  GND at the edge), so a servo plug spans the rows; black headers C42431808, rows marked S + G on the silkscreen.
* **TFT standoffs**: four M3 × 10 SMD standoffs (SMTSO30100CTJ, C2916370, pad on GND) at the module's holes; the
  module sits about 11 mm up on its socket, so add a 1 mm washer.
* **Charger inputs**: two back-to-back N-MOSFET pairs on ACDRV1/ACDRV2 (VAC1 = PD, VAC2 = PROG), **sources
  together** (ACFET drain to the input, RBFET drain to VBUS; BQ25798 datasheet Figure 7-4: ACDRV drives 5 V above the
  common source). The earlier drafts had the drains together.
* **MOSFETs**: all six (Q1–Q4 input, Q5–Q6 protection) are Infineon BSC0902NSI (C534382): 30 V, 2.8 mΩ at 10 V,
  ±20 V gate (the BQ77915 drives the gates to about VDD, up to 14 V), SuperSO8 = KiCad `TDSON-8-1` (1–3 S, 4 G,
  5–8 and pad D). One part number for all six keeps a single extended-part fee. Drop-in alternatives: BSC0902NS
  (C153230), WSD30160DN56 (C377870). The BQ25792 symbol
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
| Power switch 2MD1T1B1M1QES-5 (DPDT) | C496170 | SW-TH_2MD1T1B1M1QES-5 | poles 1-2-3 and 4-5-6, commons 2 and 5 |
| Inductor FXL0630-6R8-M (6.8 µH, 5 A / 6 A sat) | C167221 | IND-SMD_L7.0-W6.6 | 2 pads, 6.0 mm apart; replaces KiCad's Bourns SRP7028A footprint (that part is not stocked) |
| Tact switch TS-1187A-B-A-B (5.1 × 5.1 mm) | C318884 | SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5 | pads renumbered 1, 1, 2, 2: LCSC's symbol joins pads 1–2 and 3–4 inside, the switch is between the pairs; replaces the TL3342 (out of stock) |
| Inductor FXL1040-2R2-M (2.2 µH, 12 A / 18 A sat) | C167228 | IND-SMD_L11.5-W10.5 | 2 pads, 9.5 mm apart; 11.5 × 10 mm body, replaces the 10 × 10 SRP1038C footprint |
| Rocker SS21-BBIWG2-B (DPST, black) | C6775929 | SW-TH_SS21-BBIWG2-B | slotted pads; poles 1–1A and 2–2A (own symbol `SW_DPST`) |
| DC jack DC007B-2.0 | C17701683 | DC-IN-TH_HX-DC007B-2.5 | pad 1 centre pin, pad 2 sleeve, the four tabs "3" to GND; the footprint of the 2.5 mm version has the same body and pads |
| Omron B3F-4055 | C84931 | KEY-TH_4P-L12.0-W12.0-P5.00-LS13.4-EH | diagonal pins 1 and 4 used (own symbol `SW_B3F`) |
| Standoff SMTSO30100CTJ (M3 × 10, SMD) | C2916370 | SCREW-SMD_BD5.6-D4.1-H10 | 6 mm pad with a 4.2 mm plated hole, pad "1" on GND |

3D models only (the footprints stay KiCad's, the LCSC ones merge or renumber pins): the USB-C receptacle
(`USB-C_SMD-TYPE-C-31-M-12_1.wrl`, offset 0, −1.4 mm, rotated 180°) and the RK09K pot (`RES-TH_RK09K1130A6S.wrl`,
offset 4, −2.5 mm, rotated 90°); `MODELS` in `gen/pcbgen.py` attaches them.

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
| BQ25792 | PROG 13.7 k (3S, 750 kHz); ILIM_HIZ divider; TS divider 5.23 k / 30.1 k; inductor 2.2 µH; input FET wiring now per Figure 7-4 (common source) |
| HUSB238 | VSET resistors (14 k = 15 V, 10 k = 12 V, 6.04 k = 9 V, open = 20 V); ISET open = 3.25 A |
| WF100DPZ | Supply at 3.3 V; CSB left open (I2C mode) |
| TPS54331 (custom symbol) | Compensation (29.4 k, 1 nF, 47 pF) and the inductors: check with TI's design tool for 3.3 V and 5/6 V |
| CH334R | Whether the crystal load capacitors are internal (fitted as DNP) |
| AS5600 | 3.3 V mode (VDD5V and VDD3V3 tied) |
| MCP23017 | GPA7/GPB7 output-only |

## LCSC numbers

All resistors, capacitors, inductors, diodes, LEDs, the fuse, the NTCs, the crystal and the trimmer have an LCSC number
(`PASSIVES` in `gen/design.py`, picked by value; stock checked on 2026-11-18). JLCPCB **basic** parts where one exists,
so most of them add no extended-part fee: the common resistor values, all ceramics but the 4.7 µF 35 V, SS14/SS34,
AO3400A, the 600 Ω ferrite, the 12 MHz crystal and the red LED. The E96 resistor values, shunts, electrolytics, power
inductors, NTC, fuse, green/yellow LEDs and the SMAJ5.0A are extended parts.

* Ceramics without a voltage on the sheet are 50 V (0603) or 25 V (0805 4.7 µF); every part is rated at least the
  voltage in its value.
* The stocked electrolytics are rated higher: **100 µF 35 V** (was 25 V; Lelon RVE, 8 × 10) on V_BUS and **470 µF 25 V**
  (was 10 V; low-ESR, 10 × 10.5) on V_SERVO.
* Shunts: Ralec RLM25 10 mΩ 2 W (INA226) and RLP25 5 mΩ 3 W (pack).
* Pack fuse: Littelfuse NANO2 0451010.MRL (10 A fast, 2410 size, footprint `Fuse_Littelfuse-NANO2-451_453`); a
  1812 fuse is not made for 10 A.
* LEDs: Kento KT-0603: green for the rails, yellow for CHARGE, red for V_DXL and the four MCP23017 LEDs (red is the
  basic part; change `LED_LCSC` / the values for other colours).
* Crystal X322512MSB4SI: 20 pF load. Check against the CH334R (the 15 pF load capacitors are DNP).

Connectors, buttons and panel pots get theirs by footprint (`FP_LCSC` in `gen/design.py`):

| Part | LCSC | Notes |
| --- | --- | --- |
| Pin headers 1×3, 1×4, 1×5, 1×9, 2×4, 2×5 (2.54 mm, vertical) | C49257, C42431808, C32713271, C27985193, C32713277, C32713278 | plain headers, not boxed; the 1×4 (servo and analog-input rows) is black: no coloured 1×4 is stocked |
| Female headers 1×4, 1×8 | C2718488, C27438 | TFT, MH module, HC-SR04 |
| JST PH 4-pin, 6-pin (B4B/B6B-PH-K-S) | C131334, C131342 | load cell, motors |
| Screw terminal 2-pin 5.08 mm (WJ500V-5.08-2P) | C8465 | fits the Phoenix MKDS 1,5 footprint (same pitch); check the hole size at layout |
| Tact switch TS-1187A-B-A-B | C318884 | basic part; QON, RESET and BOOT ×2 |
| Omron B3F-4055 | C84931 | BTN0–3 |
| Rocker SS21-BBIWG2-B, DC jack DC007B-2.0, standoff SMTSO30100CTJ | C6775929, C17701683, C2916370 | power switch, 12 V input, TFT |
| TVS SMBJ15A | C435932 | 12 V input |
| Panel pot Alps RK09K1130A6S, 10 k linear | C209770 | 15 mm flatted shaft, 6 mm (from the board); the A70 before it stood about 30 mm tall |

Only test points, solder jumpers and net ties (copper only) and the DNP ISET resistor have no LCSC number.

## PCB: placement

The placement is generated by `gen/pcbgen.py` from the same design, run with KiCad's own Python:

```
"C:/Program Files/KiCad/10.0/bin/python.exe" gen/pcbgen.py --espressif <path to Espressif.kicad_sym>
```

* **200 × 150 mm**, 4 layers: F.Cu (signals, GND pour), In1 GND plane, In2 +3V3 plane, B.Cu (signals, GND pour);
  3 mm corner radius, **6× M3 holes** (the corners and two beside the upper TFT standoffs; none under the
  TFT module). Zones connect solidly to SMD pads, with thermal reliefs on THT. (Rev 0.2 was first placed
  on 270 × 200 mm with 5 mm between blocks; packed tighter to 200 × 150 on 2026-11-20.)
* Net classes by current: **Pack** (2.0 mm: the cells in series, BAT_N, the shunt and protection FETs, about 5 A),
  **Power** (1.0 mm tracks, 0.8/0.4 mm vias: USB-C VBUS, 12 V input, charger, BAT_P, V_BUS, V_SERVO, V_DXL, motors,
  buck switch nodes) and **Supply** (0.5 mm: +3V3, +5V); everything else Default (0.2 mm, clearance 0.15 mm),
  also the low-current supplies (CHG_REGN, HUB_3V3, AHT_VDD, BQ_VDD, HX_AVDD, MH_VCC). Minimum track width 0.15 mm.
  Net ties join the cell and sense taps to the holder and shunt pads (Kelvin connections).
* **Rear edge**: USB-C PD and PROG, 12 V jack, power rocker, GND banana hole, the power screw terminals (wire entries
  outwards) and 2×4 header, motor screw terminals and encoder connectors. **Left edge**: the 9 Qwiic connectors and
  the two pressure sensors. **Right edge**: the two servo banks, PWM 9–15, Dynamixel, the 16-bit analog inputs as
  one 3×4 bank like the servos (rows signal, +3V3, GND: a 3-pin plug spans the rows), then the MH and HC-SR04
  sockets, whose modules plug in facing out of the right edge (socket pins reversed: GND ECHO TRIG 5V and
  AO DO GND VCC; the HC-SR04 module, 45 mm wide, stands over the edge from y 110 to past the front edge).
  **Front edge**: 2 toggles, 4 B3F buttons (15 mm pitch), 4 pots, the 10-bit analog input and the load cell.
* Pin labels of connectors sit beyond the courtyard (not under the plastic body).
* Parts are named in the script by **stable keys** (`'J=USB-C POWER'`, `'RV=10k@RK09#2'`: prefix and value, `@` a
  footprint name part, `#n` the n-th match), not by references, which shift when parts are added.
* Each schematic block is packed into a **cluster**: parts 0.5 mm apart (1.2 mm around ICs for their fanout), and
  0603 resistors and capacitors **stacked in columns** of up to 6, courtyards touching, like the pins of an IC.
  Clusters are packed at 12 widths; among the tightest ones (up to 15 % larger) the one that lands nearest to the
  block's spot in `FLOORPLAN` wins, with **2 mm** between blocks (outline 0.5 mm around the parts). Blocks tied to
  edge parts (power switch, motor driver, USB-C, input selection, the ESPs, PCA9685, bucks, charger, pack, I2C mux,
  MCP23017, MCP3008, USB hub) and the sensors that must see out go first (`FIRST`), the rest largest first.
* Then the clusters are **spread** into the open room around them (`spread`): every part moves away from its block's
  centre, up to 1.5× its distance (`SPREAD`), as far as it can while keeping its packing gaps within the block and
  2 mm to other blocks, fixed parts and holes, and off the holder contacts on the back (a part over BT1's contact and
  its net tie made Freerouting crash). Each block is then outlined by a **polygon** around its parts (their union,
  0.4 mm around them, closed by 2.5 mm, traced on a 0.25 mm grid), not a rectangle: 0.25 mm wide with corners rounded
  at 1.5 mm, so outlines and connection lines (thin, corners cut at 45 degrees) are easy to tell apart. Its name is
  above it. (`OUTLINE_DASH` gives dashed outlines instead.)
* The three 18650 holders are on the back at the rear (y 19–86): no through-hole part or TFT standoff over them;
  their contacts are SMD, only their pegs (x 72, 128, 136) block the top. The TFT module lies over x 67–136,
  y 87–128 (outline on Dwgs.User) on 4 standoffs; the IR sensor, light/climate, LDR, ToF and UART0-header blocks are
  kept out from under it (`UNCOVERED`; the UART0 header stays reachable with the module on). The LDR sits at the
  front left by the VEML7700, about 40 mm from the module, out of its shadow. Parts under it are low (headers at most
  8.5 mm under the 10 mm standoffs).
* **Silkscreen**: no references. Each block has an outline and its function; ICs carry a short type (TPS54331,
  USBLC6, MCP3008; single-gate logic is BUF), only the first of identical ICs in a block; connectors and switches
  their function, test points their net, LEDs their rail, pots their wiper net (POT0–3), and connectors with 2 mm
  pitch or more the net of each pin; the 2-way screw terminals a large **+** (pin 1: the rail, a motor's +) and **−**
  (pin 2: GND, a motor's −) beyond the terminal body. The credits (revision, Vincent Groenhuis, RaM, and the layout and routing by
  Claude Opus 5.5) go in a free spot near the front, or on the back when there is none (as now).
* **Connection lines** between the blocks (`connection_lines`): one minimum spanning tree per bus (I2C per bus, SPI,
  UART, USB per port; labelled with the protocol), per power rail (0.35 mm, labelled with the rail; GND and +3V3
  left out, a motor's + and − as one line) and per other signal (0.12 mm, labelled with the net; signals between
  the same two blocks merged). They are drawn along the 2 mm channels between the blocks by an A* search on a
  0.25 mm grid that avoids blocks, parts and block names, and penalises turns and running along another line or
  close along an outline; each label goes where its line is least crowded. Corners are cut at 45 degrees (1 mm).
* The Qwiic connectors carry their bus only (main 1, ch 2, io), under one QWIIC heading.
* Footprints carry the schematic symbol paths and KiCad's net names, so "Update PCB from Schematic" works from here.
* DRC items expected before routing: the TPS259472 VQFN's own pad clearances, the servo rows' courtyards (2.54 mm
  apart on purpose), the SK6812MINI-E's own board cutout, the WF100DPZ footprints' odd courtyards.
* Running the script again **overwrites the board**: once parts are moved by hand in KiCad, stop using it.

## PCB: autorouting (partial)

The board is autorouted with [Freerouting](https://github.com/freerouting/freerouting) by `gen/route.py` (KiCad's
Python again; the .jar needs Java 25, the native freerouting-cli for Windows crashes):

```
"C:/Program Files/KiCad/10.0/bin/python.exe" gen/route.py --stage power --freerouting <freerouting .jar> --java <java.exe> --fr=--gui.enabled=false
```

**One stage at a time** (since 2026-11-20): `--stage` runs one stage on `OfficeDeskSetup.kicad_pcb` as it is, with
every track already on it (also tracks drawn or moved by hand) locked, and saves it back; the board from before goes
to `gen/route/before_<stage>.kicad_pcb`. After each stage: open it in KiCad, inspect, fix by hand what would get in
the way later, save, close KiCad, run the next stage. The stages in order: `power`, `vias`, `signals`, `planes`,
`narrow` (stage 3 and prune), `rest` (stage 4), `finish`. Without `--stage`, all of them run in a row in `gen/route/`
from the bare placement (for experiments). `route.py` stops when KiCad has the board open (its lock file).

**Open power connections**: the Pack, Power and Supply net classes have colours (red, orange, yellow), so with the
Appearance panel's net colours on *Ratsnest* (KiCad's default) their ratsnest lines stand out; hide the Default
class's ratsnest (Nets tab, eye icon) to see only them. `gen/openpower.py` lists them per net, with the pads and track
ends and their coordinates.

Use the **2.5.1 SNAPSHOT** (nightly of 2026-11-19 or later) or a later release, not 2.5.0. Release 2.5.0 has two
bugs that cost most of the power nets: with more than one pass it reports the best pass but saves a later, worse
board (a power-only test: 68 open power connections after 4 passes, 20 after 1, same reported score), and it imports
pad clearances wrongly when the DSN has an `smd_smd` rule and the `kicad_default` class (as KiCad's export does), so
pins at exactly the clearance count as violations and their nets are left alone. With 2.5.0, pass `--passes 1
--passes2 1 --passes3 1 --passes4 1`.

**Keep KiCad closed while it runs**: pcbnew's SaveBoard briefly writes a default project file, and an open KiCad picked
that up and saved it on exit (all net classes gone). `route.py` stops when the project file has lost its classes.

About 50–60 minutes (200 × 150 mm) to 70 minutes (270 × 200 mm). The work files go to `gen/route/` (ignored by git). Steps:

1. **Plane vias** (`gen/planevias.py`): Freerouting treats a plane's net as connected by the plane and never adds
   the vias from SMD pads down to it, so every SMD pad on GND or +3V3 first gets one: a 0.6/0.3 mm via beside the
   pad with a 0.3 mm track, outwards from the part, or up to 3 × 3 vias inside an exposed pad. Placed with KiCad's
   own shape collision tests (473 vias). The fine-pitch pads of U39, U23 and the TPS25947 GND pins get none.
   **Narrowing stubs** (`planevias.stubs`, the default; `--no-stubs` skips them): Freerouting has one track width
   per class, so a 1 mm power track cannot end on a pin with 0.4–0.65 mm pitch neighbours. Every SMD power pad where
   a full-width track does not fit gets a locked track no wider than the pad (at most 0.6 mm), straight out of the
   pin row, just long enough for a full-width track to end on it: 41 stubs. Only footprints that are themselves
   below the 0.2 mm clearance (TPS25947) may have a stub that clears beyond the pad only. None for U8.6, U9.6,
   U14.6 (boxed in by pins 7 and 10) and U6.9 (0.175 mm from pin 10).
2. **Stage 0** (power first, the default; `--no-power-first` skips it): only the power nets (Power and Supply
   classes, without the plane nets GND and +3V3) on F.Cu and B.Cu, 1 pass; every other net keeps one pin in the
   DSN, so its pads are obstacles but there is nothing to connect. The tracks are locked for the next stages, so
   the thin signal tracks can no longer take the narrow spaces that the wide power tracks need.
   `--stage power --bare` starts it again from the bare placement (all tracks and vias removed).
   * **Chip keep-outs** (stage 0 only, as rule areas in its DSN, never on the board; `--no-keepout` skips them):
     only against power tracks that cross a chip where they could go around it. Every `U` part with only SMD pads
     and a courtyard of at most 20 mm a side (`--keepout-refs`, `--keepout-max`; so not the ESP32 modules) gets a
     keep-out over its body, the area between the inner ends of its pins (`pin_body`; exposed pads do not count):
     on the other side of the board for tracks and vias, on its own side for tracks (shrunk until no pin on a power
     net is in it). Near and along the pin rows tracks and escape vias are free. No keep-out on the other side where
     it would cover a pad being routed there (U13 over battery holder contact BT2.2). The first version covered the
     whole courtyard: 15-18 open power connections, with trivial ones blocked (CELL1, SW_3V3 at U11); over the body
     only: 4. A pin with no room for its escape via outside the keep-out gets one under the chip, and that chip
     loses both keep-outs for the rest of the attempt (logged as "under the chip, its keep-outs dropped").
   * **Fan-out of dense chips** (new attempts only; `--fanout-pitch` 0.5 mm, 0 = off; `--fanout-refs`): before
     stage 0 every pin of a chip with that pitch or finer gets an escape track and via: other nets outwards (power
     first, with landing room), a power pin without room outside under the chip (the chip then has no keep-outs),
     GND and +3V3 inwards to the plane. Plane pads the vias step found no room for score in the pin ranking and get
     their plane via here first. First tries: 1 and 3 open power connections (U6.29; U6.2, U6.22) against 0 without
     it (attempt 10): the signal pins' vias around U6 take room the wide power tracks need. Not yet tried through
     the signal stage.
   * **Escape rounds** (`--escape-rounds`, default 0 = no limit): the power pads that a round leaves open each get an
     *escape via*: a via of the net class size beside the pad, where a class-width track can end on it (that
     landing room, plus 0.1 mm a side for Freerouting's octagonal track ends, is kept free for later escape vias;
     two vias 1.03 mm apart at U6 left a 1 mm track no way in, and 0.05 mm to spare was still too tight) (outwards from the part first, off the chip
     keep-outs; under the chip only when there is no room outside) with a short locked track at the class width where it fits, else down to 0.2 mm. They go on the
     stage's starting board and the stage is routed again, until nothing is open, no open pad gets a new via, or
     the rounds are used up. The round with the fewest open connections is kept, without the escape vias the router
     did not use; those at pads still open stay, so a short track on any layer finishes them by hand (the GND and
     +3V3 planes have room for one). Work files: `stage0_in.kicad_pcb`, `stage0_rN.kicad_pcb`, `stage0_rounds.json`.
     The track to the via runs straight from the pad, or else first straight out along the pin past its end, then to
     the via (a pin boxed in by its neighbours, like the middle pins of the TPS25947). An escape track never crosses
     a track of its own net (two pins of one net side by side, U6.22/23 BAT_P and U6.2/3 CHG_VBUS, each took the via
     in front of the other: crossing leads, narrower together than two separate ones); a pin with no spot of its own
     then runs straight to a nearby escape via of its net instead.
   * **Pin ranking** (`gen/route/pin_scores.json`, kept over all runs; `--scores` for another file): a pin scores a
     point every round it is left open and every time there is no room for its via (escape via, fan-out via, or
     plane via). Escape vias go in
     ranking order (the first get the best spots), and a new attempt starts by giving every pin that scored
     (`--pre-escape`, default 1 point; 0: off) its escape via before the first round, highest first. Delete the file
     to start the ranking over (after a new placement, say). Example on rev 0.2: the first attempt from the routed
     board has no room for U8.6, U6.2, U6.8 and U6.28 (U8.5's via took U8.6's only way out); the next attempt from
     the bare placement gives all 25 failed pins a via first, those four included.
   * **Mounting holes** (all stages): Freerouting keeps its clearance from the copper only, and the SCREW-SMD
     standoffs H2-H4 have a 0.05 mm ring (4.3 mm pad on a 4.2 mm hole), so tracks came 0.20-0.24 mm from the hole
     where KiCad wants 0.25 (hole clearance). Every through-hole pad with a ring thinner than the hole clearance that
     has no net or a hole of 2 mm or more gets a keep-out in the DSN (all copper layers, tracks and vias): a 16-gon
     around the hole radius + hole clearance + 0.05 mm. Not for pads with a net and a small hole: the keep-out would
     keep their own tracks off. Cut-outs in a footprint (Edge.Cuts inside it: reverse-mount LED D14) get a keep-out
     box too: the cut-out plus the copper-to-edge clearance + 0.05 mm, and every non-plated hole (BT3's pegs) a
     16-gon of hole radius + hole clearance + 0.05 mm.
3. **Stage 1**: all nets on F.Cu and B.Cu only. The inner layers are marked as plane layers in the Specctra DSN
   (KiCad exports them as signal layers, and Freerouting then routes straight through the planes), and the board
   outline is pulled in so tracks keep the 0.5 mm edge clearance. Escape rounds as in stage 0, for all nets but the
   plane nets (`--escape-rounds-signals`, default 2, 0 = no limit; each round is a full stage-1 run).
   Attempt 13 (run 12's plane vias, hole keep-outs, no round limit): 25, 23, 21, 25, 17, 19 open; round 4 kept.
4. **Stage 2**: the stage-1 tracks are locked and Freerouting routes what is left with the planes open. A track
   through a plane is kept only while the plane stays sound: at most 50 mm of plane track per net; plane tracks
   closer together than 2 mm count as one slot of at most 50 mm; and each plane stays one piece (filled with a
   2 mm minimum width, so a narrow neck counts as a cut). Otherwise the worst net loses its stage-2 tracks, and
   each removed net is then tried back on its own. Options `--max-plane`, `--slot-gap`, `--neck`; `--reuse`
   re-imports the routes of the previous run instead of routing again. To keep plane tracks short, the plane
   layers get a higher trace cost in the DSN (`--plane-cost`, default 5; the outer layers about 1: an
   `autoroute_settings` scope with a `layer_rule` per layer, after the layers in the structure), so Freerouting
   only dips into a plane for short hops and uses another via where the way is long; and prune takes out a net
   whose plane track has a piece (tracks joined end to end) longer than `--max-plane-run` mm (20).
5. **Stage 3**: the Power class at 0.4 mm (`--power-narrow`): Freerouting has one width per class and cannot neck a
   1 mm track down to a 0.4 mm pitch pin. Afterwards every narrow power track on F.Cu/B.Cu gets the widest of 1.0,
   0.8, 0.6, 0.5 mm that clears its surroundings, except its last 0.8 mm at a pad. `--power-clearance` lowers the
   Power clearance in this stage only (not used now).
6. **Prune**: the plane rules of stage 2, applied to the tracks of stages 2 and 3.
7. **Stage 4**: what the plane rules took out, and anything else left, on F.Cu and B.Cu only.
8. **Finish**: loose vias, track stubs and zero-length tracks are removed, the GND pours are added on F.Cu and B.Cu and KiCad refills all
   zones (kicad-cli; pcbnew's filler from Python left stale fill around a few vias).

**GND stitching vias** (tying the F.Cu and B.Cu pours to In1 on a 5 mm grid, about 500) come last, once everything
is routed, because a via grid is in the way of routing by hand:

```
"C:/Program Files/KiCad/10.0/bin/python.exe" gen/planevias.py OfficeDeskSetup.kicad_pcb
```

(`route.py --stitch` adds them too, for a board that Freerouting routes completely.)

Each step runs in its own Python process: after a session import, pcbnew's SWIG objects come back untyped. The
project file is left exactly as it was (SaveBoard rewrites it).

Result for rev 0.2 (200 × 150 mm, 2026-11-20, SNAPSHOT 2026-11-19, power first with stubs, 3 passes per stage;
3871 tracks, 15.4 m, 997 vias):

* **27 unconnected items** (power first without stubs: 34; all at once: 39; the same design on 270 × 200 mm: 20).
  Power: BAT_P 4; VBUS_PROG, VBUS_SW, CHG_SYS, CHG_VBUS 2 each; +3V3, VBUS_PD, V_DXL, CHG_SW1, CHG_PMID 1 each,
  nearly all at the BQ25792 (U6) and the eFuses. Signals: BQ_TS 2; MUX7_SDA, I2C2_SDA, MOT_AIN1, MOT_BIN1,
  CHG_PROG, BQ_CHG, BQ_VC2, BQ_LD 1 each. These are left for routing by hand.
* Connections routed per stage (`gen/routestats.py`; a net with n pads has n − 1 connections; GND and +3V3 left
  out, the planes connect them):

  | stage | all at once: power | signal | open | power first: power | signal | open | + stubs: power | signal | open |
  |---|---|---|---|---|---|---|---|---|---|
  | 0: power alone | – | – | – | 169 / 199 | 0 / 432 | 462 | 173 / 199 | 0 / 432 | 458 |
  | 1: all, outer layers | 165 / 199 | 402 / 432 | 64 | 178 / 199 | 394 / 432 | 59 | 178 / 199 | 400 / 432 | 53 |
  | 2: planes open | 173 / 199 | 431 / 432 | 27 | 179 / 199 | 422 / 432 | 30 | 178 / 199 | 426 / 432 | 27 |
  | 3: power narrow | 176 / 199 | 431 / 432 | 24 | 183 / 199 | 423 / 432 | 25 | 186 / 199 | 426 / 432 | 19 |
  | prune: plane rules | 171 / 199 | 408 / 432 | 52 | 178 / 199 | 410 / 432 | 43 | 182 / 199 | 411 / 432 | 38 |
  | 4: leftovers, outer layers | 172 / 199 | 428 / 432 | 31 | 182 / 199 | 423 / 432 | 26 | 183 / 199 | 424 / 432 | 24 |
  | finish: cleanup, pours | 171 / 199 | 423 / 432 | 37 | 180 / 199 | 418 / 432 | 33 | 183 / 199 | 422 / 432 | 26 |

  Power first leaves 9 fewer power connections open and 5 more signal ones; the stubs add 3 power and 4 signal
  connections at the end. In stage 0 the stubs gain only 4: 16 of the 26 still open there are around U6, where the
  stubs end but 1 mm tracks find no room between them (BAT_P on U6.22/23, CHG_VBUS on U6.2/3). Finish loses a few
  connections in every run (its cleanup removes tracks that it takes for loose ends): worth a look.
* 17 nets keep a track through a plane; 6 lost theirs to the plane rules and went to stage 4.
* Other DRC errors: 15 clearance errors inside the three TPS25947 footprints (pad pitch below 0.15 mm clearance, as
  drawn by TI); a DXL_EN track and the pads at the SK6812MINI-E cutout (**move that track**); 2 dangling SPI_MOSI
  stubs; the WF100DPZ courtyards; the servo courtyards; 7 starved thermals. Schematic parity: no differences.
* Earlier attempts: letting Freerouting use all four layers left 136 connections open but put 11 m of signal track
  through the planes; routing +3V3 as tracks (In2 as a signal layer) left 241–276 open.

A full run without `--stage` **overwrites all tracks**; `--stage` keeps them.
