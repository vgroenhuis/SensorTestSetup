"""The SensorTestSetup PCB schematic (PCB_SPEC.md, draft 0.7), described part by part.

Run `python3 gen/make.py` to (re)write the .kicad_sch files. Changes belong here, not in the generated files
(or stop using the generator once the schematic is edited by hand in KiCad).
"""
from schgen import NC

REV = '0.2'
DATE = '2026-11-20'

# footprints (KiCad standard libraries); '' = to be chosen at layout
FP = dict(
    R='Resistor_SMD:R_0603_1608Metric', C='Capacitor_SMD:C_0603_1608Metric', C0805='Capacitor_SMD:C_0805_2012Metric',
    C1206='Capacitor_SMD:C_1206_3216Metric', CP8='Capacitor_SMD:CP_Elec_8x10', CP10='Capacitor_SMD:CP_Elec_10x10',
    LED='LED_SMD:LED_0603_1608Metric', SMA='Diode_SMD:D_SMA', SMB='Diode_SMD:D_SMB', L7='OfficeDeskSetup:IND-SMD_L7.0-W6.6',
    L10='OfficeDeskSetup:IND-SMD_L11.5-W10.5', R2512='Resistor_SMD:R_2512_6332Metric',
    BTN='OfficeDeskSetup:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5', TP='TestPoint:TestPoint_Pad_D1.5mm',
    JPO='Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm', JPB='Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm',
    JP3='Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm', FUSE='Fuse:Fuse_Littelfuse-NANO2-451_453',
    QWIIC='Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal', USBC='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',
    SCREW2='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal',
    PH4='Connector_JST:JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical', PH6='Connector_JST:JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical',
    EH3='Connector_JST:JST_EH_B3B-EH-A_1x03_P2.50mm_Vertical', SOIC8='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
    SOIC16='Package_SO:SOIC-16_3.9x9.9mm_P1.27mm', TSSOP24='Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm',
    SOT235='Package_TO_SOT_SMD:SOT-23-5', SOT353='Package_TO_SOT_SMD:SOT-353_SC-70-5', SOT23='Package_TO_SOT_SMD:SOT-23',
    XTAL='Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm', POT='Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical',
    TRIM='Potentiometer_SMD:Potentiometer_Bourns_3314G_Vertical', LDR='OptoDevice:R_LDR_5.1x4.3mm_P3.4mm_Vertical',
    HOLE='MountingHole:MountingHole_3.2mm_M3_Pad', HOLDER='Battery:BatteryHolder_Keystone_1042_1x18650',
)
# footprints imported from LCSC/EasyEDA with easyeda2kicad into OfficeDeskSetup.pretty (+ .3dshapes); pads checked against
# the datasheets (SCHEMATIC_NOTES.md, "Imported footprints")
FP.update({k: 'OfficeDeskSetup:' + v for k, v in dict(
    MLT8530='BUZ-SMD_4P-L8.5-W8.5-P8.50-BR', TPS25947='VQFN-10_L2.0-W2.0-P0.45-TL', VL53L7CX='LGA-16_L6.4-W3.0_VL53L5CXV0GC-1',
    WF100DPZ='SOP-6_L7.0-W7.0-P2.54-LS10.3-TL', ITR20001='OPTO-TH_4P_ITR20001-T-F316', AHT20='SENSOR-SMD_L3.0-W3.0-P1.00-BR',
    VEML7700='SENSOR-SMD_EML7700-TT', TOGGLE='SW-TH_2MS1T1B1M1QES-5', TOGGLE2='SW-TH_2MD1T1B1M1QES-5',
    ROCKER='SW-TH_SS21-BBIWG2-B', DCJACK='DC-IN-TH_HX-DC007B-2.5', B3F='KEY-TH_4P-L12.0-W12.0-P5.00-LS13.4-EH',
    STANDOFF='SCREW-SMD_BD5.6-D4.1-H10', BANANA='BananaHole_4.1mm_Pad').items()})
FP['TDSON8'] = 'Package_TO_SOT_SMD:TDSON-8-1'


def fet(b, s, g, d, note):
    """BSC0902NSI: 30 V, 2.8 mOhm at 10 V, +-20 V gate (Infineon SuperSO8: 1-3 S, 4 G, 5-8 and pad D)."""
    b.ic('Transistor_FET:BSC028N06LS3', 'Q', 'BSC0902NSI', {'1': s, '4': g, '5': d},   # pins 2, 3 stacked under 1
         fields=fields(FP['TDSON8'], 'C534382', Note=note))


def header(n):
    return 'Connector_PinHeader_2.54mm:PinHeader_1x%02d_P2.54mm_Vertical' % n


def socket(n):
    return 'Connector_PinSocket_2.54mm:PinSocket_1x%02d_P2.54mm_Vertical' % n


# LCSC numbers of the connectors, buttons and panel pots, by footprint (stock checked 2026-11-18)
FP_LCSC = {
    header(3): 'C49257', header(4): 'C42431808', header(5): 'C32713271', header(9): 'C27985193',
    'Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical': 'C32713277',
    'Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical': 'C32713278',
    socket(4): 'C2718488', socket(8): 'C27438',
    FP['PH4']: 'C131334', FP['PH6']: 'C131342',              # JST B4B/B6B-PH-K-S
    FP['SCREW2']: 'C8465',                                     # WJ500V-5.08-2P screw terminal
    FP['BTN']: 'C318884',                                      # XKB TS-1187A-B-A-B, 5.1 x 5.1 mm tact switch
    FP['POT']: 'C351173',                                      # Alps RK09K1130A70, 10 k linear
}


def fields(fp='', lcsc=None, **more):
    f = {'Footprint': fp}
    if lcsc is None:
        lcsc = FP_LCSC.get(fp)
    if lcsc:
        f['LCSC'] = lcsc
    f.update(more)
    return f


TWO = {  # kind: (symbol, reference prefix, default footprint)
    'R': ('Device:R', 'R', FP['R']), 'C': ('Device:C', 'C', FP['C']), 'CP': ('Device:C_Polarized', 'C', FP['CP8']),
    'L': ('Device:L', 'L', FP['L7']), 'LED': ('Device:LED', 'D', FP['LED']), 'D': ('Device:D_Schottky', 'D', FP['SMA']),
    'TVS': ('Device:D_TVS', 'D', FP['SMB']), 'NTC': ('Device:Thermistor_NTC', 'TH', FP['R']), 'LDR': ('Device:R_Photo', 'R', FP['LDR']),
    'FUSE': ('Device:Fuse', 'F', FP['FUSE']), 'JPO': ('Jumper:SolderJumper_2_Open', 'JP', FP['JPO']),
    'JPB': ('Jumper:SolderJumper_2_Bridged', 'JP', FP['JPB']), 'SW': ('Switch:SW_Push', 'SW', FP['BTN']),
}


# LCSC numbers of the two-terminal parts by value (JLCPCB basic parts where there is one; stock checked 2026-11-18).
# Resistors: UNI-ROYAL 0603WAF, 1 %. Ceramics: Samsung/Yageo X5R/X7R, voltage at least the value's.
PASSIVES = {
    'R': {'100R': 'C22775', '150R': 'C22808', '220R': 'C22962', '330R': 'C23138', '665R': 'C218112', '1k': 'C21190',
          '1.1k': 'C22764', '1.91k': 'C22853', '2.2k': 'C4190', '3.24k': 'C22994', '4.53k': 'C25971', '4.7k': 'C23162',
          '5.1k': 'C23186', '5.23k': 'C23068', '6.04k': 'C25977', '7.87k': 'C23236', '10k': 'C25804', '10.2k': 'C22772',
          '13.7k': 'C22793', '14k': 'C22803', '20k': 'C4184', '29.4k': 'C22974', '30.1k': 'C23000', '47k': 'C25819',
          '100k': 'C25803', '169k': 'C22817', '453k': 'C25818', '1M': 'C22935', '3.3M': 'C26096',
          '10mR 2W': 'C192580', '5mR 1W': 'C393074'},          # Ralec RLM25 2 W / RLP25 3 W shunts
    'C': {'15pF': 'C1644', '47pF': 'C1671', '1nF': 'C1588', '1nF 50V': 'C1588', '10nF': 'C57112', '22nF': 'C21122',
          '47nF 50V': 'C1622', '100nF': 'C14663', '100nF 50V': 'C14663', '1uF': 'C15849', '1uF 25V': 'C15849',
          '1uF 35V': 'C28323', '4.7uF': 'C1779', '4.7uF 16V': 'C1779', '4.7uF 35V': 'C76651', '10uF 16V': 'C15850',
          '10uF 25V': 'C13585', '10uF 35V': 'C13585', '22uF 10V': 'C12891', '22uF 25V': 'C12891', '47uF 10V': 'C96123'},
    'CP': {'100uF 35V elec': 'C2895269', '470uF 25V elec': 'C3445246'},
    'L': {'2.2uH 10A': 'C167228', '6.8uH 5A': 'C167221', '6.8uH 3A': 'C167221', 'ferrite 600R': 'C1002'},
    'D': {'SS14': 'C2480', 'SS34': 'C8678'}, 'TVS': {'SMAJ5.0A': 'C19077523', 'SMBJ15A': 'C435932'},
    'NTC': {'10k B3435': 'C525660'}, 'FUSE': {'10A': 'C44479'},
}
LED_LCSC = {'red': 'C2286', 'green': 'C12624', 'yellow': 'C2287'}     # Kento KT-0603R/G/Y


def part_lcsc(kind, value):
    if kind == 'LED':
        return LED_LCSC[value.split()[-1] if value.split()[-1] in LED_LCSC else 'red']
    return PASSIVES.get(kind, {}).get(value)


def two(b, kind, value, a, c, strip=False, fp=None, lcsc=None, dnp=False):
    sym, prefix, default = TWO[kind]
    if lcsc is None:
        lcsc = part_lcsc(kind, value)
    (b.strip if strip else b.row)(sym, prefix, value + (' DNP' if dnp else ''), a, c,
                                  fields=fields(default if fp is None else fp, lcsc), dnp=dnp)


def R(b, value, a, c, **kw):
    two(b, 'R', value, a, c, **kw)


def C(b, value, a, c='GND', fp=None, **kw):
    """Capacitor, drawn in a strip (decoupling style)."""
    if fp is None and 'elec' in value:
        fp = FP['CP8']
    if fp is None:
        big = value.split()[0] in ('10uF', '22uF', '4.7uF', '47uF')
        fp = FP['C1206'] if value.startswith(('22uF', '47uF')) else FP['C0805'] if big else FP['C']
    two(b, 'CP' if 'elec' in value else 'C', value, a, c, strip=True, fp=fp, **kw)


def tp(b, net, name=None):
    b.ic('Connector:TestPoint', 'TP', name or net, {'1': net}, flow=True, fields=fields(FP['TP']))


def flag(b, net):
    b.ic('power:PWR_FLAG', '#FLG', 'PWR_FLAG', {'1': net}, flow=True)


def conn(b, value, nets, fp, prefix='J', lcsc=None, mounting=False, flow=False):
    lib = 'Connector_Generic_MountingPin:Conn_01x%02d_MountingPin' if mounting else 'Connector_Generic:Conn_01x%02d'
    n = len(nets) - (1 if mounting else 0)
    table = {str(i + 1): net for i, net in enumerate(nets[:n])}
    if mounting:
        table['MP'] = nets[-1]
    b.ic(lib % n, prefix, value, table, flow=flow, fields=fields(fp, lcsc))


def esd(b, line1, line2, rail='+3V3'):
    b.ic('Power_Protection:USBLC6-2SC6', 'U', 'USBLC6-2SC6', {'1': line1, '6': line1, '3': line2, '4': line2, '5': rail, '2': 'GND'},
         flow=True, fields=fields('Package_TO_SOT_SMD:SOT-23-6', 'C2827654'))


def qwiic(b, name, sda, scl):
    conn(b, 'Qwiic ' + name, ['GND', '+3V3', sda, scl, 'GND'], FP['QWIIC'], lcsc='C51940130', mounting=True, flow=True)


def custom_symbols(lib):
    P, I, PW, NCT = 'passive', 'passive', 'power_in', 'no_connect'
    s = {}
    s['TPS54331'] = lib.box('TPS54331D', [(2, 'VIN', PW), (3, 'EN', I), (4, 'SS', P), (6, 'COMP', P), (7, 'GND', PW)],
                            [(1, 'BOOT', P), (8, 'PH', P), None, (5, 'VSENSE', I)], footprint=FP['SOIC8'],
                            datasheet='https://www.ti.com/lit/ds/symlink/tps54331.pdf', description='3 A, 28 V step-down converter, 570 kHz')
    s['TPS25947'] = lib.box('TPS259472ARPW', [(5, 'IN', PW), (1, 'EN/UVLO', I), (2, 'OVCSEL', I), (10, 'ITIMER', P), (8, 'GND', PW)],
                            [(6, 'OUT', P), (3, 'PG', P), (4, 'PGTH', I), (7, 'DVDT', P), (9, 'ILM', P)],
                            footprint=FP['TPS25947'], datasheet='https://www.ti.com/lit/ds/symlink/tps25947.pdf',
                            description='eFuse 2.7-23 V, 5.5 A, reverse current blocking, overvoltage clamp (TPS259472x pinout, datasheet Table 5-1)')
    s['BQ77915'] = lib.box('BQ7791504PW', [(1, 'VDD', PW), (2, 'AVDD', P), (3, 'VC5', I), (4, 'VC4', I), (5, 'VC3', I), (6, 'VC2', I),
                                           (7, 'VC1', I), (8, 'VC0', I), (9, 'VSS', PW), (10, 'SRP', I), (11, 'SRN', I), (12, 'DSG', P)],
                           [(24, 'CTRD', I), (23, 'CTRC', I), (22, 'PRES', I), (21, 'CBO', P), (20, 'CCFG', I), (19, 'VTB', P),
                            (18, 'TS', I), (17, 'OCDP', P), (16, 'CBI', I), (15, 'LPWR', P), (14, 'LD', I), (13, 'CHG', P)],
                           footprint=FP['TSSOP24'], datasheet='https://www.ti.com/lit/ds/symlink/bq77915.pdf',
                           description='3-5S Li-ion protector with cell balancing (pin numbers: verify)')
    s['VL53L7CX'] = lib.box('VL53L7CX', [('B1', 'AVDD', PW), ('B7', 'AVDD', PW), ('A4', 'IOVDD', PW), ('A5', 'LPn', I), ('A1', 'I2C_RST', I),
                                         ('C1', 'GND', PW), ('C7', 'GND', PW), ('B4', 'THERMALPAD', PW)],
                            [('C3', 'SDA', P), ('C4', 'SCL', P), ('A3', 'INT', P), ('C2', 'RSVD6', P), ('A6', 'RSVD1', P), ('A7', 'RSVD2', P),
                             ('C6', 'RSVD3', P), ('A2', 'RSVD4', P), ('C5', 'RSVD5', NCT)],
                            footprint=FP['VL53L7CX'], datasheet='https://www.st.com/resource/en/datasheet/vl53l7cx.pdf',
                            description='Time-of-flight 8x8 multizone sensor, 90 deg FoV (DS13865 Rev 8, Table 3)')
    s['WF100DPZ'] = lib.box('WF100DPZ', [(5, 'VDD', PW), (4, 'CSB', NCT), (6, 'NC', NCT), (1, 'GND', PW)], [(3, 'SDA', P), (2, 'SCL', P)],
                            footprint=FP['WF100DPZ'], description='Digital gauge pressure sensor, I2C 0x6D (pin numbers: verify)')
    s['AHT20'] = lib.box('AHT20', [(2, 'VDD', PW), (1, 'NC', NCT), (6, 'NC', NCT), (5, 'GND', PW)], [(4, 'SDA', P), (3, 'SCL', P)],
                         footprint=FP['AHT20'], description='Temperature and humidity sensor, I2C 0x38 (datasheet V1.0 Table 5)')
    s['VEML7700'] = lib.box('VEML7700-TT', [(2, 'VDD', PW), (3, 'GND', PW)], [(4, 'SDA', P), (1, 'SCL', P)],
                            footprint=FP['VEML7700'], description='Ambient light sensor, I2C 0x10')
    s['AS5600'] = lib.box('AS5600-ASOT', [(1, 'VDD5V', PW), (2, 'VDD3V3', PW), (8, 'DIR', I), (5, 'PGO', I), (4, 'GND', PW)],
                          [(6, 'SDA', P), (7, 'SCL', P), None, (3, 'OUT', P)], footprint=FP['SOIC8'],
                          description='12-bit magnetic rotary position sensor, I2C 0x36')
    s['ITR20001'] = lib.box('ITR20001/T', [(1, 'A', P), (2, 'K', P)], [(4, 'C', P), (3, 'E', P)], footprint=FP['ITR20001'],
                            description='Reflective optical sensor: IR LED and phototransistor (datasheet Rev 6: 1 A, 2 K, 3 E, 4 C)')
    s['MLT8530'] = lib.box('MLT-8530', [(1, '+', P), (4, '-', P)], [(2, 'dummy', NCT), (3, 'dummy', NCT)], ref='BZ',
                           footprint=FP['MLT8530'], description='Magnetic buzzer 2.7 kHz, 16 ohm; coil on pads 1 (+) and 4 (-), pads 2 and 3 are dummies')
    s['SWDPDT'] = lib.box('SW_DPDT', [(2, 'COM1', P), (5, 'COM2', P)], [(1, '1 ON', P), (3, '1 OFF', P), (4, '2 ON', P), (6, '2 OFF', P)],
                          ref='SW', footprint=FP['TOGGLE2'],
                          description='Miniature DPDT toggle switch (Dailywell 2MD1T1B1M1QES-5): poles 1-2-3 and 4-5-6, commons 2 and 5')
    s['ROCKER'] = lib.box('SW_DPST', [(1, '1', P), (2, '2', P)], [('1A', '1A', P), ('2A', '2A', P)], ref='SW', footprint=FP['ROCKER'],
                          description='Rocker switch DPST (SS21-BBIWG2-B): poles 1-1A and 2-2A')
    s['DCJACK'] = lib.box('DC_JACK', [(1, 'PIN', P)], [(2, 'SLEEVE', P), (3, 'MOUNT', P)], ref='J', footprint=FP['DCJACK'],
                          description='DC barrel jack 5.5 x 2.1 mm, 7 A (DC007B): centre pin 1, sleeve 2, mounting tabs 3')
    s['B3F'] = lib.box('SW_B3F', [(1, '1', P), (2, '2', P)], [(4, '4', P), (3, '3', P)], ref='SW', footprint=FP['B3F'],
                       description='Tact switch 12 x 12 mm (Omron B3F-4055): the switch is between diagonal pins 1 and 4')
    return s


def describe(d):
    X = custom_symbols(d.lib)
    usb_and_pd(d, X)
    battery(d, X)
    rails(d, X)
    mcu_main(d, X)
    mcu_io(d, X)
    i2c_parts(d, X)
    sensors(d, X)


# ---------------------------------------------------------------------------------------------
def usb_and_pd(d, X):
    sh = d.sheet('usb_pd', 'USB-C: PD input, programming port, USB hub')

    b = sh.block('USB-C POWER: PD sink, 15 V (HUSB238, I2C 0x08)')
    b.ic('Connector:USB_C_Receptacle_USB2.0_16P', 'J', 'USB-C POWER',
         {'A4': 'VBUS_PD', 'A5': 'PD_CC1_CONN', 'B5': 'PD_CC2', 'A6': 'PD_DP', 'B6': 'PD_DP', 'A7': 'PD_DM', 'B7': 'PD_DM',
          'A8': NC, 'B8': NC, 'A1': 'GND', 'SH': 'GND'}, fields=fields(FP['USBC'], 'C165948'))
    b.note('CC1 reaches the HUSB238 through the power\nswitch (sheet 3); CC2 is direct.')
    b.col()
    b.ic('Interface_USB:HUSB238_xxxDD', 'U', 'HUSB238_002DD',
         {'VIN': 'VBUS_PD', 'D+': 'PD_DP', 'D-': 'PD_DM', 'CC1': 'PD_CC1', 'CC2': 'PD_CC2', 'SDA': 'I2C_SDA', 'SCL': 'I2C_SCL',
          'VSET': 'PD_VSET', 'ISET': 'PD_ISET', 'GATE': NC, 'GND': 'GND'}, fields=fields('Package_DFN_QFN:WDFN-10-1EP_3x3mm_P0.5mm_EP1.8x2.5mm', 'C7471904'))
    esd(b, 'PD_DP', 'PD_DM', rail=NC)
    b.note('USBLC6 pin 5 open: VBUS_PD is up to 20 V.')
    b.col()
    two(b, 'JPB', '15V', 'PD_VSET', 'PD_VSET_15')
    R(b, '14k', 'PD_VSET_15', 'GND')
    two(b, 'JPO', '12V', 'PD_VSET', 'PD_VSET_12')
    R(b, '10k', 'PD_VSET_12', 'GND')
    two(b, 'JPO', '9V', 'PD_VSET', 'PD_VSET_9')
    R(b, '6.04k', 'PD_VSET_9', 'GND')
    R(b, 'ISET', 'PD_ISET', 'GND', dnp=True)
    b.note('VSET: close ONE jumper; all open = 20 V.\nResistor values: verify (HUSB238 datasheet).\nISET open = 3.25 A.')
    two(b, 'TVS', 'SMBJ22A', 'VBUS_PD', 'GND', lcsc='C10214')
    C(b, '1uF 35V', 'VBUS_PD', fp=FP['C0805'])
    C(b, '100nF 50V', 'VBUS_PD')
    tp(b, 'VBUS_PD')

    b = sh.block('USB-C PROG: USB 2.0 + 5 V')
    b.ic('Connector:USB_C_Receptacle_USB2.0_16P', 'J', 'USB-C PROG',
         {'A4': 'VBUS_PROG', 'A5': 'PROG_CC1', 'B5': 'PROG_CC2', 'A6': 'USB_UP_DP', 'B6': 'USB_UP_DP', 'A7': 'USB_UP_DM', 'B7': 'USB_UP_DM',
          'A8': NC, 'B8': NC, 'A1': 'GND', 'SH': 'GND'}, fields=fields(FP['USBC'], 'C165948'))
    b.col()
    R(b, '5.1k', 'PROG_CC1', 'GND')
    R(b, '5.1k', 'PROG_CC2', 'GND')
    two(b, 'TVS', 'SMAJ5.0A', 'VBUS_PROG', 'GND', fp=FP['SMA'])
    esd(b, 'USB_UP_DP', 'USB_UP_DM', rail='VBUS_PROG')
    C(b, '10uF 16V', 'VBUS_PROG')
    C(b, '100nF', 'VBUS_PROG')
    tp(b, 'VBUS_PROG')

    b = sh.block('USB hub: PROG to both ESP32-C5 (native USB: serial + JTAG)')
    b.ic('Interface_USB:CH334R', 'U', 'CH334R',
         {'V5': 'VBUS_PROG', 'VDD33_{LDO}': 'HUB_3V3', 'GND': 'GND', 'XI': 'HUB_XI', 'XO': 'HUB_XO', '~{RESET}/CDP': NC,
          'DPU+': 'USB_UP_DP', 'DMU-': 'USB_UP_DM', 'DP1+': 'USB_MAIN_DP', 'DM1-': 'USB_MAIN_DM', 'DP2+': 'USB_IO_DP', 'DM2-': 'USB_IO_DM',
          'DP3+': NC, 'DM3-': NC, 'DP4+': NC, 'DM4-': NC}, fields=fields('Package_SO:QSOP-16_3.9x4.9mm_P0.635mm', 'C4154405'))
    b.col()
    b.ic('Device:Crystal_GND24', 'Y', '12MHz', {'1': 'HUB_XI', '3': 'HUB_XO', '2': 'GND'}, fields=fields(FP['XTAL'], 'C9002'))
    C(b, '100nF', 'HUB_3V3')
    C(b, '1uF', 'HUB_3V3')
    C(b, '100nF', 'VBUS_PROG')
    C(b, '15pF', 'HUB_XI', dnp=True)
    C(b, '15pF', 'HUB_XO', dnp=True)
    b.note('Port 1: ESP main, port 2: ESP io.\nCrystal load capacitors: the CH334 has\nthem built in (verify), so DNP.')


# ---------------------------------------------------------------------------------------------
def battery(d, X):
    sh = d.sheet('battery', 'Battery 3S: charger with power path, protection, balancing')

    b = sh.block('Input selection: PD (input 1) and PROG (input 2)')
    for n, src in ((1, 'VBUS_PD'), (2, 'VBUS_PROG')):
        fet(b, 'CHG_IN%d_MID' % n, 'CHG_ACDRV%d' % n, src, 'ACFET%d: drain to the input' % n)
        fet(b, 'CHG_IN%d_MID' % n, 'CHG_ACDRV%d' % n, 'CHG_VBUS', 'RBFET%d: drain to the charger VBUS' % n)
        if n == 1:
            b.col()
    b.note('Back-to-back N-MOSFETs, SOURCES together\n(ACDRVx drives 5 V above the common source;\nBQ25798 datasheet Figure 7-4).')

    b = sh.block('Buck-boost charger BQ25792 (I2C 0x6B): 3S, 750 kHz, NVDC power path')
    b.ic('Battery_Management:BQ25798', 'U', 'BQ25792RQMR',
         {'VBUS': 'CHG_VBUS', 'VAC1': 'VBUS_PD', 'VAC2': 'VBUS_PROG', 'ACDRV1': 'CHG_ACDRV1', 'ACDRV2': 'CHG_ACDRV2', 'D+': NC, 'D-': NC,
          'SCL': 'I2C_SCL', 'SDA': 'I2C_SDA', '~{INT}': 'CHG_INT', '~{CE}': 'CHG_CE', '~{QON}': 'CHG_QON', 'ILIM_HIZ': 'CHG_ILIM',
          'PROG': 'CHG_PROG', 'TS': 'CHG_TS', 'PMID': 'CHG_PMID', 'BTST1': 'CHG_BTST1', 'SW1': 'CHG_SW1', 'SW2': 'CHG_SW2',
          'BTST2': 'CHG_BTST2', 'STAT': 'CHG_STAT', 'REGN': 'CHG_REGN', 'SYS': 'CHG_SYS', 'BAT': 'BAT_P', 'SDRV': 'CHG_SDRV',
          'BATP': 'BAT_P', 'GND': 'GND'},
         fields=fields('Package_DFN_QFN:Texas_RQM0029A_VQFN-29_4x4mm_P0.4mm', 'C2862876'))
    b.note('Symbol: BQ25798 (same package and pinout).')
    b.col()
    two(b, 'L', '2.2uH 10A', 'CHG_SW1', 'CHG_SW2', fp=FP['L10'])
    two(b, 'C', '47nF 50V', 'CHG_BTST1', 'CHG_SW1')
    two(b, 'C', '47nF 50V', 'CHG_BTST2', 'CHG_SW2')
    two(b, 'C', '1nF 50V', 'CHG_SDRV', 'BAT_P')
    R(b, '13.7k', 'CHG_PROG', 'GND')
    R(b, '47k', 'CHG_REGN', 'CHG_ILIM')
    R(b, '100k', 'CHG_ILIM', 'GND')
    R(b, '5.23k', 'CHG_REGN', 'CHG_TS')
    R(b, '30.1k', 'CHG_TS', 'GND')
    two(b, 'NTC', '10k B3435', 'CHG_TS', 'GND')
    R(b, '10k', 'CHG_CE', 'GND')
    R(b, '10k', '+3V3', 'CHG_INT')
    R(b, '2.2k', 'CHG_REGN', 'CHG_LED_A')
    two(b, 'LED', 'CHARGE yellow', 'CHG_STAT', 'CHG_LED_A')
    two(b, 'SW', 'QON', 'CHG_QON', 'GND')
    b.col()
    C(b, '4.7uF 35V', 'CHG_VBUS')
    C(b, '100nF 50V', 'CHG_VBUS')
    C(b, '10uF 35V', 'CHG_PMID', fp=FP['C1206'])
    C(b, '10uF 35V', 'CHG_PMID', fp=FP['C1206'])
    C(b, '100nF 50V', 'CHG_PMID')
    C(b, '4.7uF 16V', 'CHG_REGN')
    C(b, '22uF 25V', 'CHG_SYS')
    C(b, '22uF 25V', 'CHG_SYS')
    C(b, '22uF 25V', 'CHG_SYS')
    C(b, '100nF 50V', 'CHG_SYS')
    C(b, '10uF 25V', 'BAT_P', fp=FP['C1206'])
    C(b, '10uF 25V', 'BAT_P', fp=FP['C1206'])
    C(b, '100nF 50V', 'BAT_P')
    b.note('PROG 13.7k: 3 cells, 750 kHz (verify). ILIM_HIZ divider: about 3 A input limit (verify);\n'
           'firmware sets the input current by source (PD contract, or 0.5 A on PROG).\n'
           'TS: 5.23k / 30.1k with a 10k NTC at the cells. CE low: charging enabled.\n'
           'CHARGE LED on REGN, so it also works with the board switched off.')
    tp(b, 'CHG_SYS')
    tp(b, 'BAT_P')
    tp(b, 'CHG_INT')
    tp(b, 'CHG_REGN')

    b = sh.block('3S pack: 3x 18650, protection + balancing BQ77915 (low-side FETs)')
    for i in (3, 2, 1):
        b.ic('Device:Battery_Cell', 'BT', '18650', {'1': 'CELL%d' % i, '2': 'CELL%d' % (i - 1) if i > 1 else 'BAT_N'},
             flow=True, fields=fields(FP['HOLDER'], 'C2979183', Note='holder MY-18650-01: footprint to check'))
    two(b, 'FUSE', '10A', 'CELL3', 'BAT_P')
    # The pack current takes CELL1..3, BAT_N, BQ_SRN (2 mm tracks); the BQ77915 and its small parts hang off thin
    # nets that leave through net ties: each cell tap at its holder contact, VSS/SRP and SRN on the sense resistor's
    # pads (Kelvin). Tie: the value of the part whose pad the net tie sits on (gen/pcbgen.py places it there).
    for i in (1, 2, 3):
        b.ic('Device:NetTie_2', 'NT', 'CELL%d tap' % i, {'1': 'CELL%d' % i, '2': 'CELL%d_TAP' % i}, flow=True,
             fields=fields('NetTie:NetTie-2_SMD_Pad0.5mm', Tie='18650'))
    b.ic('Device:NetTie_2', 'NT', 'Kelvin BAT-', {'1': 'BAT_N', '2': 'BQ_VSS'}, flow=True,
         fields=fields('NetTie:NetTie-2_SMD_Pad0.5mm', Tie='5mR 1W'))
    b.ic('Device:NetTie_2', 'NT', 'Kelvin SRN', {'1': 'BQ_SRN', '2': 'BQ_SRN_K'}, flow=True,
         fields=fields('NetTie:NetTie-2_SMD_Pad0.5mm', Tie='5mR 1W'))
    b.col()
    b.ic(X['BQ77915'], 'U', 'BQ7791504PWR',
         {'VDD': 'BQ_VDD', 'AVDD': 'BQ_AVDD', 'VC5': 'BQ_VC3', 'VC4': 'BQ_VC3', 'VC3': 'BQ_VC3', 'VC2': 'BQ_VC2', 'VC1': 'BQ_VC1',
          'VC0': 'BQ_VC0', 'VSS': 'BQ_VSS', 'SRP': 'BQ_VSS', 'SRN': 'BQ_SRN_K', 'DSG': 'BQ_DSG', 'CHG': 'BQ_CHG', 'LD': 'BQ_LD',
          'LPWR': NC, 'CBI': 'BQ_VSS', 'OCDP': 'BQ_OCDP', 'TS': 'BQ_TS', 'VTB': 'BQ_VTB', 'CCFG': 'BQ_AVDD', 'CBO': NC,
          'PRES': 'BQ_PRES', 'CTRC': 'BQ_VSS', 'CTRD': 'BQ_VSS'}, fields=fields(FP['TSSOP24'], 'C2873309'))
    b.note('CCFG to AVDD: 3 cells; VC3..VC5 together (verify).\nCBI low: balancing on. Battery minus (BAT_N) is NOT GND:\nthe FETs sit between them.')
    b.col()
    R(b, '1k', 'CELL3_TAP', 'BQ_VDD')
    R(b, '100R', 'CELL3_TAP', 'BQ_VC3')
    R(b, '100R', 'CELL2_TAP', 'BQ_VC2')
    R(b, '100R', 'CELL1_TAP', 'BQ_VC1')
    R(b, '100R', 'BQ_VSS', 'BQ_VC0')
    two(b, 'C', '100nF', 'BQ_VC3', 'BQ_VC2')
    two(b, 'C', '100nF', 'BQ_VC2', 'BQ_VC1')
    two(b, 'C', '100nF', 'BQ_VC1', 'BQ_VC0')
    two(b, 'C', '1uF 25V', 'BQ_VDD', 'BQ_VSS')
    two(b, 'C', '1uF', 'BQ_AVDD', 'BQ_VSS')
    R(b, '10k', 'BQ_VTB', 'BQ_TS')
    two(b, 'NTC', '10k B3435', 'BQ_TS', 'BQ_VSS')
    R(b, '100k', 'BQ_PRES', 'BQ_VDD')
    R(b, '100k', 'BQ_OCDP', 'BQ_VSS')
    b.col()
    two(b, 'R', '5mR 1W', 'BAT_N', 'BQ_SRN', fp=FP['R2512'])
    fet(b, 'BQ_SRN', 'BQ_DSG_G', 'BQ_FET_MID', 'discharge FET')
    fet(b, 'GND', 'BQ_CHG_G', 'BQ_FET_MID', 'charge FET')
    R(b, '4.53k', 'BQ_DSG', 'BQ_DSG_G')
    R(b, '1M', 'BQ_CHG', 'BQ_CHG_G')
    R(b, '3.3M', 'BQ_CHG_G', 'GND')
    R(b, '453k', 'BQ_LD', 'GND')
    b.note('Values after the BQ77905/15 reference circuit; cell filter,\nsense resistor, PRES and OCDP: verify for the -04 variant.')
    for n in ('CELL1', 'CELL2', 'CELL3'):
        tp(b, n + '_TAP', n)
    tp(b, 'BQ_VSS', 'BAT_N')


# ---------------------------------------------------------------------------------------------
def buck54331(b, name, vin, out, fb_top, fb_bot, sw, tag):
    b.ic(name, 'U', 'TPS54331DR', {'VIN': vin, 'EN': NC, 'SS': tag + '_SS', 'COMP': tag + '_COMP', 'GND': 'GND', 'BOOT': tag + '_BOOT',
                                   'PH': sw, 'VSENSE': tag + '_FB'}, fields=fields(FP['SOIC8'], 'C9865'))
    b.col()
    two(b, 'C', '100nF 50V', tag + '_BOOT', sw)
    two(b, 'L', '6.8uH 5A', sw, out)
    two(b, 'D', 'SS34', 'GND', sw)
    two(b, 'C', '10nF', tag + '_SS', 'GND')
    R(b, '29.4k', tag + '_COMP', tag + '_RC')
    two(b, 'C', '1nF', tag + '_RC', 'GND')
    two(b, 'C', '47pF', tag + '_COMP', 'GND')
    R(b, fb_top, out, tag + '_FB')
    R(b, fb_bot, tag + '_FB', 'GND')


def rails(d, X):
    sh = d.sheet('rails', 'Power switch, V_BUS, 3.3 V, 5 V, V_SERVO, V_DXL')

    b = sh.block('Power switch, V_BUS eFuse (5 A), INA226 (I2C 0x40)')
    b.ic(X['ROCKER'], 'SW', 'POWER', {'1': 'SW_SUPPLY', '1A': 'VBUS_EN_SW', '2': 'PD_CC1_CONN', '2A': 'PD_CC1'},
         fields=fields(FP['ROCKER'], 'C6775929'))
    two(b, 'JPO', 'CC1 always', 'PD_CC1_CONN', 'PD_CC1')
    two(b, 'D', 'SS14', 'SW_SUPPLY', 'CHG_SYS')
    two(b, 'D', 'SS14', 'SW_SUPPLY', 'DC_12V')
    R(b, '1M', 'VBUS_EN_SW', 'VBUS_EN')
    R(b, '169k', 'VBUS_EN', 'GND')
    R(b, '1M', 'VBUS_EN_SW', 'DC_EN')
    R(b, '169k', 'DC_EN', 'GND')
    b.ic('Transistor_FET:AO3400A', 'Q', 'AO3400A', {'G': 'DC_DET', 'S': 'GND', 'D': 'VBUS_EN'}, flow=True, fields=fields(FP['SOT23'], 'C20917'))
    R(b, '100k', 'DC_12V', 'DC_DET')
    R(b, '100k', 'DC_DET', 'GND')
    b.note('Switch off: both EN low, nothing draws from the pack. The\nswitch is fed from the pack side (CHG_SYS) or the 12 V jack\nthrough a diode-OR. Pole 2 breaks CC1 (PD renegotiates at\nswitch-on); CC2 is direct, so with the plug the other way round\nthe charger also works with the switch off. Bridge the CC1\njumper to leave CC1 unswitched. EN dividers: on above about\n8.7 V. 12 V present: the FET holds the pack eFuse off, so\nV_BUS comes from the jack (no charging from 12 V).')
    b.col()
    b.ic(X['TPS25947'], 'U', 'TPS259472ARPWR',
         {'IN': 'CHG_SYS', 'EN/UVLO': 'VBUS_EN', 'OVCSEL': 'VBUS_OVCSEL', 'ITIMER': NC, 'GND': 'GND', 'OUT': 'VBUS_SW',
          'PG': NC, 'PGTH': 'GND', 'DVDT': 'VBUS_DVDT', 'ILM': 'VBUS_ILM'}, fields=fields(FP['TPS25947'], 'C3662789'))
    R(b, '665R', 'VBUS_ILM', 'GND')
    two(b, 'C', '10nF', 'VBUS_DVDT', 'GND')
    two(b, 'JPO', 'OVCSEL', 'VBUS_OVCSEL', 'GND')
    C(b, '1uF 25V', 'CHG_SYS')
    C(b, '1uF 25V', 'VBUS_SW')
    b.note('ILM 665R: 5 A. OVCSEL: the setting for the\n13.8 V clamp (open or GND): verify.')
    b.col()
    b.ic(X['DCJACK'], 'J', 'DC 12V', {'PIN': 'DC_12V', 'SLEEVE': 'GND', 'MOUNT': 'GND'}, fields=fields(FP['DCJACK'], 'C17701683'))
    two(b, 'TVS', 'SMBJ15A', 'DC_12V', 'GND')
    C(b, '10uF 25V', 'DC_12V', fp=FP['C1206'])
    C(b, '1uF 25V', 'DC_12V')
    tp(b, 'DC_12V')
    b.ic(X['TPS25947'], 'U', 'TPS259472ARPWR',
         {'IN': 'DC_12V', 'EN/UVLO': 'DC_EN', 'OVCSEL': 'DC_OVCSEL', 'ITIMER': NC, 'GND': 'GND', 'OUT': 'VBUS_SW',
          'PG': NC, 'PGTH': 'GND', 'DVDT': 'DC_DVDT', 'ILM': 'DC_ILM'}, fields=fields(FP['TPS25947'], 'C3662789'))
    R(b, '665R', 'DC_ILM', 'GND')
    two(b, 'C', '10nF', 'DC_DVDT', 'GND')
    two(b, 'JPO', 'OVCSEL', 'DC_OVCSEL', 'GND')
    b.note('12 V input: second eFuse (5 A) into VBUS_SW.\nBoth eFuses block reverse current.')
    b.ic('Mechanical:MountingHole_Pad', 'H', 'GND banana', {'1': 'GND'}, flow=True, fields=fields(FP['BANANA']), in_bom=False)
    b.col()
    # Shunt: a 2-terminal 2512; the sense lines leave its pads through net ties (Kelvin connection, placed on the pads)
    R(b, '10mR 2W', 'VBUS_SW', 'V_BUS', fp=FP['R2512'])
    b.ic('Device:NetTie_2', 'NT', 'Kelvin +', {'1': 'VBUS_SW', '2': 'INA_INP'}, flow=True,
         fields=fields('NetTie:NetTie-2_SMD_Pad0.5mm', Tie='10mR 2W'))
    b.ic('Device:NetTie_2', 'NT', 'Kelvin -', {'1': 'V_BUS', '2': 'INA_INN'}, flow=True,
         fields=fields('NetTie:NetTie-2_SMD_Pad0.5mm', Tie='10mR 2W'))
    b.ic('Sensor_Energy:INA226', 'U', 'INA226AIDGSR',
         {'VS': '+3V3', 'GND': 'GND', 'Vbus': 'V_BUS', 'Vin+': 'INA_INP', 'Vin-': 'INA_INN', 'A0': 'GND', 'A1': 'GND',
          'SDA': 'I2C_SDA', 'SCL': 'I2C_SCL', '~{Alert}': 'INA_ALERT'}, fields=fields('Package_SO:TSSOP-10_3x3mm_P0.5mm', 'C49851'))
    R(b, '10k', '+3V3', 'INA_ALERT')
    b.col()
    C(b, '100nF', '+3V3')
    C(b, '100uF 35V elec', 'V_BUS')
    C(b, '100uF 35V elec', 'V_BUS')
    C(b, '22uF 25V', 'V_BUS')
    tp(b, 'V_BUS')
    tp(b, 'INA_ALERT')
    tp(b, 'GND')
    tp(b, 'GND')

    b = sh.block('3.3 V buck (3 A)')
    buck54331(b, X['TPS54331'], 'V_BUS', '+3V3', '10.2k', '3.24k', 'SW_3V3', 'B33')
    b.col()
    C(b, '10uF 25V', 'V_BUS', fp=FP['C1206'])
    C(b, '100nF 50V', 'V_BUS')
    C(b, '47uF 10V', '+3V3')
    C(b, '47uF 10V', '+3V3')
    tp(b, '+3V3')

    b = sh.block('5 V buck (2 A)')
    b.ic('Regulator_Switching:AP63205WU', 'U', 'AP63205WU-7', {'IN': 'V_BUS', 'EN': 'V_BUS', 'GND': 'GND', 'SW': 'SW_5V', 'BST': 'B5_BST', 'FB': '+5V'},
         fields=fields('Package_TO_SOT_SMD:TSOT-23-6', 'C2071056'))
    b.col()
    two(b, 'C', '100nF', 'B5_BST', 'SW_5V')
    two(b, 'L', '6.8uH 3A', 'SW_5V', '+5V')
    C(b, '10uF 25V', 'V_BUS', fp=FP['C1206'])
    C(b, '22uF 10V', '+5V')
    C(b, '22uF 10V', '+5V')
    tp(b, '+5V')

    b = sh.block('V_SERVO buck (3 A): 5 V, 6 V with the jumper closed')
    buck54331(b, X['TPS54331'], 'V_BUS', 'V_SERVO', '10k', '1.91k', 'SW_SERVO', 'BSV')
    two(b, 'JPO', '6V', 'BSV_FB', 'BSV_FB6')
    R(b, '7.87k', 'BSV_FB6', 'GND')
    b.col()
    C(b, '10uF 25V', 'V_BUS', fp=FP['C1206'])
    C(b, '10uF 25V', 'V_BUS', fp=FP['C1206'])
    C(b, '100nF 50V', 'V_BUS')
    C(b, '47uF 10V', 'V_SERVO')
    C(b, '47uF 10V', 'V_SERVO')
    C(b, '470uF 25V elec', 'V_SERVO', fp=FP['CP10'])
    tp(b, 'V_SERVO')

    b = sh.block('V_DXL: eFuse 3 A, enabled by the MCP23017 (off at reset)')
    b.ic(X['TPS25947'], 'U', 'TPS259472ARPWR',
         {'IN': 'V_BUS', 'EN/UVLO': 'DXL_EN', 'OVCSEL': 'DXL_OVCSEL', 'ITIMER': NC, 'GND': 'GND', 'OUT': 'V_DXL',
          'PG': NC, 'PGTH': 'GND', 'DVDT': 'DXL_DVDT', 'ILM': 'DXL_ILM'}, fields=fields(FP['TPS25947'], 'C3662789'))
    b.col()
    R(b, '1.1k', 'DXL_ILM', 'GND')
    R(b, '100k', 'DXL_EN', 'GND')
    two(b, 'C', '22nF', 'DXL_DVDT', 'GND')
    two(b, 'JPO', 'OVCSEL', 'DXL_OVCSEL', 'GND')
    C(b, '1uF 25V', 'V_BUS')
    C(b, '10uF 25V', 'V_DXL', fp=FP['C1206'])
    tp(b, 'V_DXL')

    b = sh.block('Power-good LEDs')
    for rail, res, colour in (('V_BUS', '4.7k', 'green'), ('+3V3', '1k', 'green'), ('+5V', '2.2k', 'green'),
                              ('V_SERVO', '2.2k', 'green'), ('V_DXL', '4.7k', 'red')):
        tag = 'LED_' + rail.strip('+')
        R(b, res, rail, tag)
        two(b, 'LED', rail + ' ' + colour, 'GND', tag)

    b = sh.block('Exposed power: screw terminals and header')
    for rail in ('V_BUS', 'V_SERVO', '+5V', '+3V3'):
        b.ic('Connector:Screw_Terminal_01x02', 'J', rail.strip('+'), {'1': rail, '2': 'GND'}, flow=True, fields=fields(FP['SCREW2']))
    b.col()
    b.ic('Connector_Generic:Conn_02x04_Odd_Even', 'J', 'POWER',
         {'1': 'V_BUS', '2': 'GND', '3': 'V_SERVO', '4': 'GND', '5': '+5V', '6': 'GND', '7': '+3V3', '8': 'GND'},
         fields=fields('Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical'))

    # Not flagged: nets already driven by a power-output pin (CHG_SYS: BQ25792 SYS, BAT_P: BQ25792 BAT,
    # HUB_3V3: CH334 VDD33 LDO); a flag there is a power output against a power output.
    b = sh.block('Power flags (for the electrical rules check)')
    for net in ('GND', '+3V3', '+5V', 'V_BUS', 'V_SERVO', 'V_DXL', 'VBUS_PD', 'VBUS_PROG', 'CHG_VBUS', 'BAT_N',
                'BQ_VSS', 'BQ_VDD', 'VBUS_SW', 'HX_AVDD', 'AHT_VDD', 'DC_12V'):
        flag(b, net)


# ---------------------------------------------------------------------------------------------
def esp32(b, name, tag, gpio, usb):
    nets = {'3V3': '+3V3', 'GND': 'GND', 'EN/CHIP_PU': tag + '_EN', 'GPIO13/USB_D-': usb + '_DM', 'GPIO14/USB_D+': usb + '_DP',
            'GPIO15': NC, 'ANT2': NC}
    names = {11: 'U0TXD/GPIO11', 12: 'U0RXD/GPIO12'}
    for n, net in gpio.items():
        nets[names.get(n, 'GPIO%d' % n)] = net
    b.ic('OfficeDeskSetup:ESP32-C5-WROOM-1U', 'U', 'ESP32-C5-WROOM-1U-N16R8 ' + name, nets,
         fields=fields('PCM_Espressif:ESP32-C5-WROOM-1U', 'C54951857'))
    b.col()
    R(b, '10k', '+3V3', tag + '_EN')
    two(b, 'C', '1uF', tag + '_EN', 'GND')
    two(b, 'SW', 'RESET ' + name, tag + '_EN', 'GND')
    R(b, '1k', gpio[28], tag + '_BOOT')
    two(b, 'SW', 'BOOT ' + name, tag + '_BOOT', 'GND')
    C(b, '22uF 10V', '+3V3')
    C(b, '100nF', '+3V3')
    b.note('GPIO28 is a strapping pin (high at reset = normal boot)\nand an output afterwards: the BOOT button pulls it low\nthrough 1k. GPIO15: PSRAM. Antenna: U.FL on the module.')


def mcu_main(d, X):
    sh = d.sheet('mcu_main', "ESP32-C5 'main': Wi-Fi, web, display, SPI, main I2C bus")

    b = sh.block("ESP32-C5 'main'")
    esp32(b, 'main', 'MAIN', {0: 'SPI_MISO', 1: 'HX_SCK', 2: 'I2C_SDA', 3: 'I2C_SCL', 4: 'US_ECHO', 5: 'HX_DOUT', 6: 'US_TRIG',
                              7: 'SPI_SCLK', 8: 'SPI_MOSI', 9: 'TFT_DC', 10: 'TFT_RES', 11: 'MAIN_TX0', 12: 'MAIN_RX0', 23: 'LINK_M2I',
                              24: 'TFT_BLK', 25: 'TFT_CS', 26: 'LINK_I2M', 27: 'RGB_DIN', 28: 'MCP3008_CS'}, 'USB_MAIN')

    b = sh.block('Main I2C bus: pull-ups, Qwiic x2')
    R(b, '2.2k', '+3V3', 'I2C_SDA')
    R(b, '2.2k', '+3V3', 'I2C_SCL')
    tp(b, 'I2C_SDA')
    tp(b, 'I2C_SCL')
    b.col()
    qwiic(b, 'main 1', 'I2C_SDA', 'I2C_SCL')
    qwiic(b, 'main 2', 'I2C_SDA', 'I2C_SCL')
    b.col()
    esd(b, 'I2C_SDA', 'I2C_SCL')

    b = sh.block('TFT 2.4" ST7789 (8-pin socket)')
    conn(b, 'TFT', ['GND', '+3V3', 'SPI_SCLK', 'SPI_MOSI', 'TFT_RES', 'TFT_DC', 'TFT_CS', 'TFT_BLK'], socket(8))
    b.col()
    R(b, '10k', 'TFT_BLK', 'GND')
    b.note('Module pins: GND VCC SCL SDA RES DC CS BLK.\nBacklight off until firmware drives BLK (PWM).')
    for n in ('SPI_SCLK', 'SPI_MOSI', 'SPI_MISO'):
        tp(b, n)

    b = sh.block('UART0 header, link UART, status LED')
    conn(b, 'UART0 main', ['GND', 'MAIN_TX0', 'MAIN_RX0', 'MAIN_EN', 'MAIN_BOOT'], header(5))
    b.col()
    b.ic('LED:SK6812MINI-E', 'D', 'SK6812MINI-E', {'VDD': '+3V3', 'VSS': 'GND', 'DIN': 'RGB_DIN', 'DOUT': NC},
         fields=fields('LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount', 'C5149201'))
    C(b, '100nF', '+3V3')
    b.col()
    tp(b, 'LINK_M2I')
    tp(b, 'LINK_I2M')
    b.note("Link UART: main TX (GPIO23) to io RX (GPIO23),\nio TX (GPIO26) to main RX (GPIO26).")

    b = sh.block('TFT standoffs: M3 x 10 SMD, at the module holes')
    for i in range(4):
        b.ic('Mechanical:MountingHole_Pad', 'H', 'TFT standoff', {'1': 'GND'}, flow=True, fields=fields(FP['STANDOFF'], 'C2916370'))

    b = sh.block('Mounting holes (M3)')
    for i in range(6):
        b.ic('Mechanical:MountingHole', 'H', 'M3', {}, flow=True, fields=fields('MountingHole:MountingHole_3.2mm_M3'), in_bom=False)
        if i == 2:
            b.col()


# ---------------------------------------------------------------------------------------------
def mcu_io(d, X):
    sh = d.sheet('mcu_io', "ESP32-C5 'io': motors, encoders, Dynamixel, ToF")

    b = sh.block("ESP32-C5 'io'")
    esp32(b, 'io', 'IO', {0: 'MOT_PWMA', 1: 'MOT_PWMB', 2: 'I2C2_SDA', 3: 'I2C2_SCL', 4: 'TOF_INT', 5: 'MOT_AIN1', 6: 'MOT_AIN2',
                          7: 'MOT_BIN1', 8: 'MOT_BIN2', 9: 'ENCA_A', 10: 'ENCA_B', 11: 'DXL_DIR', 12: 'DXL_RX', 23: 'LINK_M2I',
                          24: 'ENCB_A', 25: 'ENCB_B', 26: 'LINK_I2M', 27: 'DXL_TX', 28: 'MOT_STBY'}, 'USB_IO')

    b = sh.block('Motor driver TB6612FNG (VM = V_BUS)')
    b.ic('Driver_Motor:TB6612FNG', 'U', 'TB6612FNG',
         {'VM1': 'V_BUS', 'VM2': 'V_BUS', 'VM3': 'V_BUS', 'VCC': '+3V3', 'GND': 'GND', 'PGND1': 'GND', 'PGND2': 'GND', 'STBY': 'MOT_STBY',
          'PWMA': 'MOT_PWMA', 'AIN1': 'MOT_AIN1', 'AIN2': 'MOT_AIN2', 'PWMB': 'MOT_PWMB', 'BIN1': 'MOT_BIN1', 'BIN2': 'MOT_BIN2',
          'AO1': 'MOTA_P', 'AO2': 'MOTA_N', 'BO1': 'MOTB_P', 'BO2': 'MOTB_N'}, fields=fields('Package_SO:SSOP-24_5.3x8.2mm_P0.65mm', 'C141517'))
    b.col()
    for n in ('PWMA', 'PWMB', 'AIN1', 'AIN2', 'BIN1', 'BIN2'):
        R(b, '10k', 'MOT_' + n, 'GND')
    b.col()
    C(b, '100uF 35V elec', 'V_BUS')
    C(b, '10uF 25V', 'V_BUS', fp=FP['C1206'])
    C(b, '100nF 50V', 'V_BUS')
    C(b, '100nF', '+3V3')
    b.note('STBY (GPIO28) is high at reset; the motors stay\noff because PWM and direction are pulled down.')

    for m, ea, eb in (('A', 'ENCA', 'ENCA'), ('B', 'ENCB', 'ENCB')):
        b = sh.block('Motor %s + encoder' % m)
        conn(b, 'MOTOR %s' % m, ['MOT%s_P' % m, 'MOT%s_N' % m, '+3V3', 'GND', ea + '_A_CONN', ea + '_B_CONN'], FP['PH6'])
        b.ic('Connector:Screw_Terminal_01x02', 'J', 'MOTOR %s' % m, {'1': 'MOT%s_P' % m, '2': 'MOT%s_N' % m}, fields=fields(FP['SCREW2']))
        b.col()
        R(b, '100R', ea + '_A_CONN', ea + '_A')
        R(b, '100R', ea + '_B_CONN', ea + '_B')
        esd(b, ea + '_A_CONN', ea + '_B_CONN')
        C(b, '1nF', ea + '_A', dnp=True)
        C(b, '1nF', ea + '_B', dnp=True)

    b = sh.block('Dynamixel port (half-duplex TTL, 5 V): 2x JST EH')
    b.ic('74xGxx:74AHCT1G125', 'U', '74AHCT1G125GV', {'1': 'DXL_DIR', '2': 'DXL_TX', '4': 'DXL_DATA', '5': '+5V', '3': 'GND'},
         fields=fields(FP['SOT235'], 'C52140417'))
    b.ic('74xGxx:74LVC1G34', 'U', '74LVC1G34GW', {'1': NC, '2': 'DXL_DATA', '4': 'DXL_RX', '5': '+3V3', '3': 'GND'},
         fields=fields(FP['SOT353'], 'C52140426'))
    b.col()
    R(b, '10k', '+5V', 'DXL_DATA')
    R(b, '10k', '+3V3', 'DXL_DIR')
    C(b, '100nF', '+5V')
    C(b, '100nF', '+3V3')
    b.note('Transmit when DIR is LOW (RTS inverted in the UART).\nDIR pulled up: the buffer is off at reset.')
    b.col()
    conn(b, 'DXL 1', ['GND', 'V_DXL', 'DXL_DATA'], FP['EH3'], lcsc='C160259')
    conn(b, 'DXL 2', ['GND', 'V_DXL', 'DXL_DATA'], FP['EH3'], lcsc='C160259')
    tp(b, 'DXL_DATA')

    b = sh.block('VL53L7CX time-of-flight (I2C 2, 0x29), Qwiic')
    b.ic(X['VL53L7CX'], 'U', 'VL53L7CXV0GC/1',
         {'B1': '+3V3', 'B7': '+3V3', 'A4': '+3V3', 'A5': 'TOF_LPN', 'A1': 'TOF_RST', 'C1': 'GND', 'C7': 'GND', 'B4': 'GND',
          'C3': 'I2C2_SDA', 'C4': 'I2C2_SCL', 'A3': 'TOF_INT', 'C2': 'TOF_RSVD6', 'A6': 'GND', 'A7': 'GND', 'C6': 'GND', 'A2': 'GND',
          'C5': NC}, fields=fields(FP['VL53L7CX'], 'C5270520'))
    b.col()
    R(b, '2.2k', '+3V3', 'I2C2_SDA')
    R(b, '2.2k', '+3V3', 'I2C2_SCL')
    R(b, '47k', '+3V3', 'TOF_LPN')
    R(b, '47k', '+3V3', 'TOF_INT')
    R(b, '47k', 'TOF_RST', 'GND')
    R(b, '47k', '+3V3', 'TOF_RSVD6')     # RSVD6 (C2): 47 k pull-up to IOVDD required (DS13865 Table 3)
    C(b, '4.7uF', '+3V3')
    C(b, '100nF', '+3V3')
    C(b, '4.7uF', '+3V3')
    C(b, '100nF', '+3V3')
    b.col()
    qwiic(b, 'io', 'I2C2_SDA', 'I2C2_SCL')
    esd(b, 'I2C2_SDA', 'I2C2_SCL')
    tp(b, 'I2C2_SDA')
    tp(b, 'I2C2_SCL')


# ---------------------------------------------------------------------------------------------
def i2c_parts(d, X):
    sh = d.sheet('i2c_parts', 'Main I2C bus: MCP23017, PCA9685, TCA9548 with pressure sensors')

    b = sh.block('MCP23017 (0x20): LEDs and toggle switches on bank A, buttons and controls on bank B')
    nets = {'V_{DD}': '+3V3', 'V_{SS}': 'GND', 'SCK': 'I2C_SCL', 'SDA': 'I2C_SDA', 'A0': 'GND', 'A1': 'GND', 'A2': 'GND',
            '~{RESET}': 'MCP_RESET', 'INTA': NC, 'INTB': NC, 'GPA4': 'TOGGLE0', 'GPA5': 'TOGGLE1', 'GPA6': NC, 'GPA7': NC}
    for i in range(4):
        nets['GPA%d' % i] = 'LED%d' % i
    for i, n in enumerate(['BTN0', 'BTN1', 'BTN2', 'BTN3', 'MH_DO', 'IR_DO', 'DXL_EN', 'PCA_OE']):
        nets['GPB%d' % i] = n
    b.ic('Interface_Expansion:MCP23017x-x-SO', 'U', 'MCP23017-E/SO', nets, fields=fields('Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm', 'C47023'))
    R(b, '10k', '+3V3', 'MCP_RESET')
    C(b, '100nF', '+3V3')
    b.col()
    for i in range(4):
        R(b, '1k', 'LED%d' % i, 'LED%d_A' % i)
    b.col()
    for i in range(4):
        two(b, 'LED', 'LED%d' % i, 'GND', 'LED%d_A' % i)
    b.col()
    for i in range(4):      # Omron B3F-4055, 12 x 12 mm: room for a cap
        b.ic(X['B3F'], 'SW', 'BTN%d' % i, {'1': 'BTN%d' % i, '4': 'GND', '2': NC, '3': NC}, flow=True, fields=fields(FP['B3F'], 'C84931'))
    for i in range(2):      # Dailywell 2MS1T1B1M1QES-5: miniature SPDT toggle, PCB pins (footprint: EasyEDA, C496169)
        b.ic('Switch:SW_SPDT', 'SW', 'TOGGLE%d' % i, {'A': 'TOGGLE%d' % i, 'B': 'GND', 'C': NC}, fields=fields(FP['TOGGLE'], 'C496169'))
    b.ic('Connector_Generic:Conn_02x05_Odd_Even', 'J', 'MCP23017 bank B',
         {'1': 'BTN0', '2': 'BTN1', '3': 'BTN2', '4': 'BTN3', '5': 'MH_DO', '6': 'IR_DO', '7': 'DXL_EN', '8': 'PCA_OE', '9': 'GND', '10': '+3V3'},
         fields=fields('Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical'))
    b.note('Buttons and toggle switches use the MCP23017\npull-ups. GPB7 is output only (PCA_OE); GPA6\nand GPA7 are free (GPA7 output only).')

    b = sh.block('PCA9685 (0x41): 8 servos, buzzer, 7 spare channels')
    nets = {'VDD': '+3V3', 'VSS': 'GND', 'SCL': 'I2C_SCL', 'SDA': 'I2C_SDA', 'A0': '+3V3', 'A1': 'GND', 'A2': 'GND', 'A3': 'GND', 'A4': 'GND',
            'A5': 'GND', 'EXTCLK': 'GND', '~{OE}': 'PCA_OE'}
    for i in range(16):
        nets['LED%d' % i] = 'PWM%d' % i
    b.ic('Driver_LED:PCA9685PW', 'U', 'PCA9685PW', nets, fields=fields('Package_SO:TSSOP-28_4.4x9.7mm_P0.65mm', 'C2678753'))
    R(b, '10k', '+3V3', 'PCA_OE')
    C(b, '100nF', '+3V3')
    C(b, '10uF 16V', '+3V3')
    b.note('OE pulled high: outputs off until\nthe firmware drives PCA_OE low.')
    b.col()
    for i in range(8):
        R(b, '220R', 'PWM%d' % i, 'SERVO%d' % i)
    b.col()
    for k in range(2):      # two banks of 4: rows of 1x4 headers (signal, V+, GND); a servo plug spans the three rows
        s = range(4 * k, 4 * k + 4)
        conn(b, 'SERVO %d-%d SIG' % (s[0], s[-1]), ['SERVO%d' % i for i in s], header(4), flow=True)
        conn(b, 'SERVO %d-%d V+' % (s[0], s[-1]), ['V_SERVO'] * 4, header(4), flow=True)
        conn(b, 'SERVO %d-%d GND' % (s[0], s[-1]), ['GND'] * 4, header(4), flow=True)
    R(b, '100R', 'PWM8', 'BUZ_G')
    R(b, '100k', 'BUZ_G', 'GND')
    two(b, 'D', 'SS14', '+3V3', 'BUZ_N')
    b.ic('Transistor_FET:AO3400A', 'Q', 'AO3400A', {'G': 'BUZ_G', 'S': 'GND', 'D': 'BUZ_N'}, flow=True, fields=fields(FP['SOT23'], 'C20917'))
    b.ic(X['MLT8530'], 'BZ', 'MLT-8530', {'+': '+3V3', '-': 'BUZ_N'}, flow=True, fields=fields(FP['MLT8530'], 'C94599'))
    b.col()
    for i in range(9, 16):
        R(b, '220R', 'PWM%d' % i, 'PWM%d_H' % i)
    conn(b, 'PWM 9-15', ['+5V', 'GND'] + ['PWM%d_H' % i for i in range(9, 16)], header(9))

    b = sh.block('TCA9548A (0x71): pressure sensors on ch 0-1, Qwiic on ch 2-7')
    nets = {'VCC': '+3V3', 'GND': 'GND', 'SCL': 'I2C_SCL', 'SDA': 'I2C_SDA', 'A0': '+3V3', 'A1': 'GND', 'A2': 'GND', '~{RESET}': 'TCA_RESET'}
    for i in range(8):
        nets['SD%d' % i] = 'MUX%d_SDA' % i
        nets['SC%d' % i] = 'MUX%d_SCL' % i
    b.ic('Interface_Expansion:TCA9548APWR', 'U', 'TCA9548APWR', nets, fields=fields(FP['TSSOP24'], 'C130026'))
    R(b, '10k', '+3V3', 'TCA_RESET')
    C(b, '100nF', '+3V3')
    b.col()
    for i in range(8):
        R(b, '4.7k' if i < 2 else '10k', '+3V3', 'MUX%d_SDA' % i)
        R(b, '4.7k' if i < 2 else '10k', '+3V3', 'MUX%d_SCL' % i)
    b.col()
    for i in range(2):
        b.ic(X['WF100DPZ'], 'U', 'WF100DPZ 10BG S6 DT', {'VDD': '+3V3', 'GND': 'GND', 'SDA': 'MUX%d_SDA' % i, 'SCL': 'MUX%d_SCL' % i},
             fields=fields(FP['WF100DPZ'], 'C22388673'))
    C(b, '100nF', '+3V3')
    C(b, '100nF', '+3V3')
    b.note('WF100DPZ: fixed address 0x6D.')
    b.col()
    for i in range(2, 8):
        qwiic(b, 'ch %d' % i, 'MUX%d_SDA' % i, 'MUX%d_SCL' % i)
    for i in range(2, 8):
        esd(b, 'MUX%d_SDA' % i, 'MUX%d_SCL' % i)


# ---------------------------------------------------------------------------------------------
def sensors(d, X):
    sh = d.sheet('sensors', 'Sensors: analog inputs, ADCs, IMU, climate, light, angle, load cell, ultrasonic')

    b = sh.block('MCP3008 10-bit ADC (SPI): 4 pots, MH, LDR, IR, 1 input')
    b.ic('Analog_ADC:MCP3008', 'U', 'MCP3008T-I/SL',
         {'Vdd': '+3V3', 'Vref': '+3V3', 'AGND': 'GND', 'DGND': 'GND', 'CLK': 'SPI_SCLK', 'Din': 'SPI_MOSI', 'Dout': 'SPI_MISO',
          '~{CS}/SHDN': 'MCP3008_CS', 'CH0': 'POT0', 'CH1': 'POT1', 'CH2': 'POT2', 'CH3': 'POT3', 'CH4': 'IR_AO', 'CH5': 'LDR_AO',
          'CH6': 'MH_AO', 'CH7': 'A10_7'}, fields=fields(FP['SOIC16'], 'C2651321'))
    C(b, '100nF', '+3V3')
    C(b, '1uF', '+3V3')
    R(b, '10k', '+3V3', 'MCP3008_CS')
    b.col()
    for i in range(4):      # POT0-3 on ch 0-3
        b.ic('Device:R_Potentiometer', 'RV', '10k', {'1': '+3V3', '2': 'POT%d' % i, '3': 'GND'}, fields=fields(FP['POT']))
    b.col()
    for i in range(4):
        C(b, '100nF', 'POT%d' % i)
    R(b, '1k', 'A10_7_CONN', 'A10_7')
    C(b, '10nF', 'A10_7')
    b.col()
    conn(b, 'AIN 7 (10 bit)', ['GND', '+3V3', 'A10_7_CONN'], header(3))

    b = sh.block('LDR')
    two(b, 'LDR', 'GL5528', '+3V3', 'LDR_AO', lcsc='C125627')
    R(b, '10k', 'LDR_AO', 'GND')

    b = sh.block('MH sensor module socket')
    conn(b, 'MH module', ['MH_AO_CONN', 'MH_DO_CONN', 'GND', 'MH_VCC'], socket(4))     # reversed: the module
                                                                                     # faces out at the right edge
    b.ic('Jumper:SolderJumper_3_Bridged12', 'JP', 'MH VCC', {'1': '+3V3', '2': 'MH_VCC', '3': '+5V'}, fields=fields(FP['JP3']))
    b.col()
    R(b, '10k', 'MH_DO_CONN', 'MH_DO')
    R(b, '10k', 'MH_AO_CONN', 'MH_AO')
    R(b, '20k', 'MH_AO', 'GND', dnp=True)
    b.note('Module pins VCC GND DO AO (socket pins 4-1).\n3.3 V by default.\nWith VCC at 5 V: fit the 20k (AO divided to 3.3 V);\nDO is limited by its 10k.')

    b = sh.block('IR reflective sensor ITR20001/T + LM393')
    b.ic(X['ITR20001'], 'U', 'ITR20001/T', {'A': 'IR_LED_A', 'K': 'GND', 'C': 'IR_AO', 'E': 'GND'}, fields=fields(FP['ITR20001'], 'C264269'))
    two(b, 'JPB', 'IR LED', '+3V3', 'IR_LED_R')
    R(b, '150R', 'IR_LED_R', 'IR_LED_A')
    R(b, '10k', '+3V3', 'IR_AO')
    b.col()
    b.ic('Device:R_Potentiometer_Trim', 'RV', '10k', {'1': '+3V3', '2': 'IR_THR', '3': 'GND'}, fields=fields(FP['TRIM'], 'C780220'))
    ref = d.ref('U')
    lm = dict(fields=fields(FP['SOIC8'], 'C7955'), ref=ref)
    b.ic('Comparator:LM393', 'U', 'LM393DR2G', {'3': 'IR_THR', '2': 'IR_AO', '1': 'IR_DO'}, unit=1, **lm)
    b.col()
    b.ic('Comparator:LM393', 'U', 'LM393DR2G', {'5': 'GND', '6': 'GND', '7': NC}, unit=2, **lm)
    b.ic('Comparator:LM393', 'U', 'LM393DR2G', {'8': '+3V3', '4': 'GND'}, unit=3, **lm)
    R(b, '10k', '+3V3', 'IR_DO')
    C(b, '100nF', '+3V3')
    b.note('IR_DO high = reflection (AO below the threshold).')

    b = sh.block('ADS1115 16-bit ADC (0x48): 4 inputs')
    b.ic('Analog_ADC:ADS1115IDGS', 'U', 'ADS1115IDGSR',
         {'VDD': '+3V3', 'GND': 'GND', 'ADDR': 'GND', 'ALERT/RDY': 'ADS_ALERT', 'SDA': 'I2C_SDA', 'SCL': 'I2C_SCL',
          'AIN0': 'A16_0', 'AIN1': 'A16_1', 'AIN2': 'A16_2', 'AIN3': 'A16_3'}, fields=fields('Package_SO:TSSOP-10_3x3mm_P0.5mm', 'C37593'))
    R(b, '10k', '+3V3', 'ADS_ALERT')
    C(b, '100nF', '+3V3')
    b.col()
    for i in range(4):
        R(b, '1k', 'A16_%d_CONN' % i, 'A16_%d' % i)
    for i in range(4):
        C(b, '10nF', 'A16_%d' % i)
    b.col()
    # one 3x4 bank of 1x4 headers at the right edge (like the servo banks): signal, +3V3, GND rows; a 3-pin plug
    # spans the three rows
    conn(b, 'AIN 0-3 SIG', ['A16_%d_CONN' % i for i in range(4)], header(4), flow=True)
    conn(b, 'AIN 0-3 3V3', ['+3V3'] * 4, header(4), flow=True)
    conn(b, 'AIN 0-3 GND', ['GND'] * 4, header(4), flow=True)

    b = sh.block('IMU LSM6DS3TR-C (0x6A)')
    b.ic('Sensor_Motion:LSM6DS3', 'U', 'LSM6DS3TR-C',
         {'VDD': '+3V3', 'VDDIO': '+3V3', 'GND': 'GND', 'SDO/SA0': 'GND', 'CS': '+3V3', 'SCL': 'I2C_SCL', 'SDA': 'I2C_SDA',
          'SDX': 'GND', 'SCX': 'GND', 'INT1': NC, 'INT2': NC}, fields=fields('Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y', 'C967633'))
    C(b, '100nF', '+3V3')
    C(b, '100nF', '+3V3')

    b = sh.block('AHT20 (0x38), VEML7700 (0x10), AS5600 (0x36)')
    b.ic(X['AHT20'], 'U', 'AHT20', {'VDD': 'AHT_VDD', 'GND': 'GND', 'SDA': 'I2C_SDA', 'SCL': 'I2C_SCL'}, fields=fields(FP['AHT20'], 'C2757850'))
    b.ic(X['VEML7700'], 'U', 'VEML7700-TT', {'VDD': '+3V3', 'GND': 'GND', 'SDA': 'I2C_SDA', 'SCL': 'I2C_SCL'},
         fields=fields(FP['VEML7700'], 'C1850416'))
    R(b, '330R', '+3V3', 'AHT_VDD')     # AHT20 datasheet: RC filter in VDD (330-390 R) and 10 uF at the sensor
    C(b, '10uF 16V', 'AHT_VDD')
    b.col()
    b.ic(X['AS5600'], 'U', 'AS5600-ASOT', {'VDD5V': '+3V3', 'VDD3V3': '+3V3', 'DIR': 'GND', 'PGO': NC, 'GND': 'GND', 'SDA': 'I2C_SDA',
                                           'SCL': 'I2C_SCL', 'OUT': 'AS5600_OUT'}, fields=fields(FP['SOIC8'], 'C55240803'))
    tp(b, 'AS5600_OUT')
    for _ in range(3):
        C(b, '100nF', '+3V3')
    C(b, '1uF', '+3V3')
    b.note('AS5600 in 3.3 V mode: VDD5V and VDD3V3 together.\nDiametric magnet in the knob above the chip.')

    b = sh.block('HX711 load cell amplifier')
    b.ic('Analog_ADC:HX711', 'U', 'HX711',
         {'VSUP': '+3V3', 'DVDD': '+3V3', 'AVDD': 'HX_AVDD', 'BASE': NC, 'VFB': 'GND', 'AGND': 'GND', 'VBG': 'HX_VBG', 'INA+': 'HX_INP',
          'INA-': 'HX_INN', 'INB+': 'GND', 'INB-': 'GND', 'PD_SCK': 'HX_SCK', 'DOUT': 'HX_DOUT', 'XI': 'GND', 'XO': NC, 'RATE': 'HX_RATE'},
         fields=fields(FP['SOIC16'], 'C6705483'))
    b.ic('Jumper:SolderJumper_3_Bridged12', 'JP', 'RATE 10/80 Hz', {'1': 'GND', '2': 'HX_RATE', '3': '+3V3'}, fields=fields(FP['JP3']))
    b.col()
    two(b, 'L', 'ferrite 600R', '+3V3', 'HX_AVDD', fp=FP['R'])
    R(b, '100R', 'HX_AP_CONN', 'HX_INP')
    R(b, '100R', 'HX_AN_CONN', 'HX_INN')
    two(b, 'C', '100nF', 'HX_INP', 'HX_INN')
    two(b, 'C', '100nF', 'HX_VBG', 'GND')
    C(b, '10uF 16V', 'HX_AVDD')
    C(b, '100nF', 'HX_AVDD')
    C(b, '100nF', '+3V3')
    b.col()
    conn(b, 'LOAD CELL', ['HX_AVDD', 'GND', 'HX_AP_CONN', 'HX_AN_CONN'], FP['PH4'])
    b.note('Pins: E+ E- A+ A-. The on-chip regulator is not\nused: excitation = filtered 3.3 V. RATE jumper:\nGND = 10 Hz (default), 3.3 V = 80 Hz.')

    b = sh.block('HC-SR04 ultrasonic (5 V, ECHO level-shifted)')
    conn(b, 'HC-SR04', ['GND', 'US_ECHO_5V', 'US_TRIG_CONN', '+5V'], socket(4))      # reversed: the module
                                                                                     # faces out at the right edge
    b.col()
    b.ic('74xGxx:74LVC1G34', 'U', '74LVC1G34GW', {'1': NC, '2': 'US_ECHO_5V', '4': 'US_ECHO', '5': '+3V3', '3': 'GND'},
         fields=fields(FP['SOT353'], 'C52140426'))
    R(b, '100R', 'US_TRIG', 'US_TRIG_CONN')
    R(b, '100k', 'US_ECHO_5V', 'GND')
    C(b, '100nF', '+3V3')
    C(b, '10uF 16V', '+5V')
    b.note('Module pins VCC TRIG ECHO GND (socket pins 4-1).')


ROOT_NOTES = """SensorTestSetup PCB, schematic revision %s: after Electronics_KiCad/PCB_SPEC.md (draft 0.7).

Sheets
  1  USB-C: PD input (HUSB238), programming port, USB hub (CH334R)
  2  Battery 3S: charger with power path (BQ25792), protection and balancing (BQ77915)
  3  Power switch, V_BUS (eFuse, INA226), 3.3 V, 5 V, V_SERVO, V_DXL
  4  ESP32-C5 'main': Wi-Fi, web, TFT, SPI, main I2C bus
  5  ESP32-C5 'io': motors, encoders, Dynamixel, VL53L7CX on its own I2C bus
  6  Main I2C bus: MCP23017 (LEDs, buttons, toggle switches), PCA9685 (servos, buzzer), TCA9548 (pressure, Qwiic)
  7  Sensors: MCP3008, ADS1115, IMU, AHT20, VEML7700, AS5600, HX711, HC-SR04, IR reflective, MH socket

Nets that cross sheets have global labels; power rails: GND, +3V3, +5V (symbols), V_BUS, V_SERVO, V_DXL (labels).

Main I2C bus (ESP 'main' GPIO2/3): 0x08 HUSB238, 0x10 VEML7700, 0x20 MCP23017, 0x36 AS5600, 0x38 AHT20, 0x40 INA226,
0x41 PCA9685, 0x48 ADS1115, 0x6A LSM6DS3TR-C, 0x6B BQ25792, 0x71 TCA9548A (0x70 kept free: PCA9685 All-Call).
Behind the TCA9548A: 0x6D WF100DPZ on ch 0 and 1; ch 2-7 Qwiic. I2C 2 (ESP 'io' GPIO2/3): 0x29 VL53L7CX + Qwiic.

The files are written by gen/make.py from gen/design.py. Values and pin numbers marked "verify" (see SCHEMATIC_NOTES.md)
have to be checked against the datasheets before layout.""" % REV
