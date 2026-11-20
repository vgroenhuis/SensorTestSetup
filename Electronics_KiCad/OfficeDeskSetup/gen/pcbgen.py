#!/usr/bin/env python3
"""PCB placement of the SensorTestSetup board, from gen/design.py (no routing: gen/route.py does that).

Run with KiCad's own Python (it needs the pcbnew module):

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/pcbgen.py --symbols DIR --espressif FILE [--fp-espressif DIR]

Writes OfficeDeskSetup.kicad_pcb: board outline, 4 copper layers, mounting holes, every footprint with its nets,
edge parts on their edges and each schematic block packed as a cluster in its region, 5 mm from the other blocks,
with an outline and its function on the silkscreen. Footprints carry the schematic symbol paths, so "Update PCB from
Schematic" in KiCad matches them. Overwrites the board file.

Parts are named by stable keys rather than references (which shift when parts are added): 'PREFIX=value', with
'@text' to require a footprint name containing text, and '#n' for the n-th match in schematic order.
"""
import argparse
import contextlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design          # noqa: E402
import schgen          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = 'OfficeDeskSetup'
IO = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)

W, H = 200.0, 150.0          # board size, mm; the rear edge is y = 0, the front edge (user side) is y = H
GAP = 0.5                    # space between courtyards when packing (routing channels)
GAP_IC = 1.2                 # around parts with 8 or more pads, for their fanout
EDGE = 1.0                   # keep courtyards this far from the board edge
BLOCK_GAP = 2.0              # between the blocks (their outlines are drawn 0.5 mm around the parts)
OUTLINE = 0.5
FILL = 1.0                   # a block's cluster: width sqrt(FILL x aspect x the parts' area)
ASPECTS = (0.2, 0.3, 0.45, 0.6, 0.8, 1.0, 1.25, 1.6, 2.0, 2.6, 3.5, 5.0)
SLACK = 1.15                 # clusters up to this much larger than the tightest one may be chosen to land nearer
COLUMN = 6                   # passives per column
SPREAD = 1.5                 # after packing, a block's parts spread out up to this factor about its centre, into the
                             # free room around it (the open areas between the tight clusters)
CLOSE = 1.5                  # block outlines: the union of the parts (0.4 mm around them), closed by this much (mm)

# ---------------------------------------------------------------------------------------------------------------
# Edge parts, as rows along an edge: (keys, edge, start, gap, rotation[, pitch]). Parts follow each other from
# `start` (mm along the edge; None: after the previous row on that edge) with `gap` between courtyards, or at a fixed
# `pitch`. A key may be (key, rotation) to override the row's rotation. Rotations put mouths and wire entries outwards.
SCREW = 180                  # Phoenix MKDS horizontal: wire entries at +y, so 180 on the rear edge
EDGE_ROWS = [
    # rear edge (y = 0): USB-C PD and PROG, 12 V jack, power switch, GND banana hole, power terminals, motors
    (['J=USB-C POWER', 'J=USB-C PROG'], 'top', 11, 2, 180),
    (['J=DC 12V'], 'top', None, 1.5, 270),
    (['SW=POWER'], 'top', None, 1.0, 0),
    (['H=GND banana'], 'top', None, 1.0, 0),
    (['J=V_BUS', 'J=V_SERVO', 'J=5V', 'J=3V3', ('J=POWER', 0)], 'top', None, 1.0, SCREW),
    ([('J=MOTOR A@Terminal', SCREW), 'J=MOTOR A@PH', ('J=MOTOR B@Terminal', SCREW), 'J=MOTOR B@PH'], 'top', None, 1.0, 0),
    # left edge (x = 0): Qwiic (main bus x2, TCA9548 ch 2-7, ToF bus) and the two pressure sensors
    (['J=Qwiic main 1', 'J=Qwiic main 2'] + ['J=Qwiic ch %d' % i for i in range(2, 8)] + ['J=Qwiic io'], 'left', 13, 0.8, 270),
    (['U=WF100DPZ 10BG S6 DT#1', 'U=WF100DPZ 10BG S6 DT#2'], 'left', None, 1.0, 0),
    # right edge (x = W): servo banks (SERVO_BANKS), PWM 9-15, Dynamixel, 16-bit analog inputs
    (['J=PWM 9-15', 'J=DXL 1', 'J=DXL 2'], 'right', 44, 1.5, 0),
    (['J=AIN %d (16 bit)' % i for i in range(4)], 'right', None, 0.6, 90),
    # front edge (y = H): toggles, buttons (15 mm pitch: room for 12 mm caps), pots; ultrasonic, MH module, 10-bit
    # analog input and load cell at the right
    (['SW=TOGGLE0', 'SW=TOGGLE1'], 'bottom', 8, 2.0, 0),
    (['SW=BTN%d' % i for i in range(4)], 'bottom', None, 0, 0, 15),
    (['RV=10k@RK09#%d' % i for i in range(1, 5)], 'bottom', None, 1.0, 0),
    (['J=HC-SR04', 'J=MH module', ('J=AIN 7 (10 bit)', 0), ('J=LOAD CELL', 0)], 'bottom', None, 1.5, 0),
]
# servo outputs: two banks of 4 at the right edge, three 1x4 rows each (GND outside, V+, signal inside); pin 1 of the
# first bank at y = SERVO_Y, the second bank SERVO_BANK further
SERVO_BANKS = [('SERVO 0-3', 'J=SERVO 0-3 SIG', 'J=SERVO 0-3 V+', 'J=SERVO 0-3 GND'),
               ('SERVO 4-7', 'J=SERVO 4-7 SIG', 'J=SERVO 4-7 V+', 'J=SERVO 4-7 GND')]
SERVO_Y, SERVO_BANK = 12.0, 16.0
# TFT module (ZhongJingYuan 2.4" ST7789): pin 1 of its 8-pin socket, and its holes and outline relative to pin 1
# (from the module's footprint in mamri/PCBs/Mamri UI V5); the module lies to the left of the socket
TFT_PIN1 = (134.0, 99.0)
TFT_HOLES = [(-64, -8.61), (-64, 26.39), (-1, -8.61), (-1, 26.39)]
TFT_OUTLINE = (-67.05, -11.66, 2.05, 29.44)
FIRST = ('Power switch', 'Motor driver', 'USB-C POWER', 'USB-C PROG', 'Input selection', "ESP32-C5 'main'", "ESP32-C5 'io'", 'PCA9685', 'V_SERVO buck',
         '3.3 V buck', '5 V buck',
         'Buck-boost charger', '3S pack', 'TCA9548A', 'MCP23017', 'MCP3008', 'USB hub', 'IR reflective', 'VL53L7CX', 'AHT20',
         'LDR')
UNCOVERED = ('IR reflective', 'AHT20', 'LDR', 'VL53L7CX')    # blocks with sensors that must not be under the TFT
# placed inside (not on an edge, but fixed): key -> (x, y, rotation, side)
FIXED = {
    'U=AS5600-ASOT': (172, 126, 0, 'F'),                      # under the knob
    'BT=18650#1': (100, 30, 0, 'B'),                         # 18650 holders on the back, at the rear (no through-
    'BT=18650#2': (100, 52.5, 180, 'B'),                     # hole parts and TFT standoffs over them); their pads
    'BT=18650#3': (100, 75, 0, 'B'),                         # have pegs at x 72, 128 and 136
}
# the four corners and two beside the upper TFT standoffs (none under the TFT module)
HOLES = {'H=M3#1': (4, 4), 'H=M3#2': (W - 4, 4), 'H=M3#3': (4, H - 4), 'H=M3#4': (W - 4, H - 4),
         'H=M3#5': (60.3, 91), 'H=M3#6': (142, 91)}
# net classes: (track width, clearance, via diameter, via drill, nets by their short name)
NETCLASSES = {
    'Power': (1.0, 0.2, 0.8, 0.4, ['VBUS_PD', 'VBUS_PROG', 'CHG_VBUS', 'CHG_PMID', 'CHG_SYS', 'CHG_SW1', 'CHG_SW2',
                                    'CHG_IN1_MID', 'CHG_IN2_MID', 'BAT_P', 'VBUS_SW',
                                    'V_BUS', 'V_SERVO', 'SW_SERVO', 'SW_3V3', 'V_DXL', 'MOTA_P', 'MOTA_N', 'MOTB_P',
                                    'MOTB_N', 'DC_12V',
                                    'SW_5V']),                      # 3 A buck switch node
    'Pack': (2.0, 0.2, 0.8, 0.4, ['CELL1', 'CELL2', 'CELL3', 'BAT_N', 'BQ_SRN', 'BQ_FET_MID']),   # the cells in series
                                                                    # and the protection FETs: the full pack current
    'Supply': (0.5, 0.15, 0.6, 0.3, ['+3V3', '+5V']),
}
# low-current supplies stay in the Default class (0.2 mm): CHG_REGN (BQ25792 gate-drive LDO, tens of mA), HUB_3V3
# (CH334R LDO), AHT_VDD (330 R in series), BQ_VDD (1 k in series), VBUS_EN_SW (1 M pull-downs), HX_AVDD (HX711 and
# the load cell bridge), MH_VCC (MH sensor module)
PLANES = {'In1.Cu': 'GND', 'In2.Cu': '+3V3'}   # signals route on F.Cu and B.Cu (GND pours after routing), with only
                                                # a few short hops through the planes (gen/route.py)
MIN_TRACK = 0.15               # Freerouting necks down to 0.15 mm at fine-pitch pins; JLCPCB does 0.1 mm
# 3D models from LCSC (OfficeDeskSetup.3dshapes) for KiCad footprints: (file, offset, rotation), KiCad axes (y up)
MODELS = {
    'USB_C_Receptacle_HRO_TYPE-C-31-M-12': ('USB-C_SMD-TYPE-C-31-M-12_1.wrl', (0, -1.4, 0), (0, 0, 180)),
    'Potentiometer_Alps_RK09K_Single_Vertical': ('RES-TH_RK09K1130A70.wrl', (4.0, -2.5, 0), (0, 0, 90)),
}

# block (title prefix) -> (x, y, silkscreen name). Each block is packed into an about square cluster, then placed
# (BLOCK_GAP from everything else) at the free spot nearest to (x, y): power at the rear, MCUs and buses at the sides,
# sensors and controls at the front, charger and pack in the middle over the holders (pegs at x 72, 128 and 136, y 22-83),
# low parts only under the TFT module (x 67-136, y 87-128)
FLOORPLAN = [
    # rear: USB-C, 12 V input and power switch, bucks, motors, PCA9685 and V_SERVO by the servo banks
    ('USB-C POWER', 15, 22, 'USB-C PD'),
    ('USB-C PROG', 31, 22, 'USB-C PROG'),
    ('Power switch', 52, 24, 'POWER SWITCH, 12 V IN, V_BUS'),
    ('5 V buck', 86, 22, '5 V'),
    ('3.3 V buck', 106, 22, '3.3 V'),
    ('Power-good LEDs', 126, 22, 'RAILS'),
    ('Motor driver', 155, 22, 'MOTOR DRIVER'),
    ('Motor A', 148, 40, 'ENCODER A'),
    ('Motor B', 165, 40, 'ENCODER B'),
    ('PCA9685', 174, 50, 'SERVO / PWM PCA9685'),
    ('V_SERVO buck', 160, 62, 'V_SERVO'),
    # left column: USB hub, input selection, ESP 'main', buses
    ('USB hub', 22, 38, 'USB HUB'),
    ('Input selection', 45, 40, 'INPUT SELECT'),
    ("ESP32-C5 'main'", 25, 70, 'ESP32 MAIN'),
    ('Main I2C bus', 50, 62, 'I2C MAIN'),
    ('UART0 header', 50, 85, 'UART0'),
    ('TCA9548A', 25, 105, 'I2C MUX, PRESSURE'),
    ('MCP23017', 42, 125, 'BUTTONS, LEDS MCP23017'),
    # middle: charger and pack
    ('Buck-boost charger', 86, 62, 'CHARGER BQ25792'),
    ('3S pack', 116, 64, '3S PACK BQ77915'),
    # front middle: sensors that must stay uncovered, ADC by the pots
    ('IMU', 72, 128, 'IMU'),
    ('AHT20', 92, 128, 'CLIMATE, LIGHT'),
    ('LDR', 108, 128, 'LDR'),
    ('MCP3008', 124, 128, 'ADC MCP3008'),
    # right: ESP 'io', ToF, TFT socket parts, Dynamixel, ADS1115, load cell, IR, HC-SR04, MH
    ("ESP32-C5 'io'", 165, 86, 'ESP32 IO'),
    ('TFT 2.4', 126, 100, 'TFT'),
    ('VL53L7CX', 152, 110, 'TOF'),
    ('V_DXL', 176, 72, 'V_DXL'),
    ('Dynamixel', 178, 86, 'DYNAMIXEL'),
    ('ADS1115', 176, 110, 'ADC ADS1115'),
    ('HX711', 182, 128, 'LOAD CELL'),
    ('IR reflective', 155, 126, 'IR SENSOR'),
    ('HC-SR04', 148, 134, 'HC-SR04'),
    ('MH sensor', 163, 134, 'MH MODULE'),
]


def region(block):
    for prefix, x, y, name in FLOORPLAN:
        if block.startswith(prefix):
            return (x, y), name
    return None, ''


# ---------------------------------------------------------------------------------------------------------------
def mm(v):
    return pcbnew.FromMM(v)


def V(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def load(fp, espressif_fp):
    nick, name = fp.split(':', 1)
    if nick == PROJECT:
        path = os.path.join(HERE, PROJECT + '.pretty')
    elif nick == 'PCM_Espressif':
        path = espressif_fp
    else:
        path = os.path.join(FP_STD, nick + '.pretty')
    m = IO.FootprintLoad(path, name)
    if m is None:
        raise KeyError('footprint not found: ' + fp)
    m.SetFPID(pcbnew.LIB_ID(nick, name))
    if name in MODELS:
        f, off, rot = MODELS[name]
        m.Models().clear()
        m3 = pcbnew.FP_3DMODEL()
        m3.m_Filename = '${KIPRJMOD}/%s.3dshapes/%s' % (PROJECT, f)
        m3.m_Offset = pcbnew.VECTOR3D(*off)
        m3.m_Rotation = pcbnew.VECTOR3D(*rot)
        m.Models().push_back(m3)
    return m


def bbox_mm(bb):
    return [pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())]


def box(m):
    """Bounding box of a placed footprint, mm: courtyard, pads (some imported courtyards leave pads out) and the
    silkscreen labels added here (so packing leaves room for them)."""
    bb = m.GetBoundingBox(False)
    c = m.GetCourtyard(pcbnew.B_CrtYd if m.IsFlipped() else pcbnew.F_CrtYd)
    if not c.IsEmpty():
        bb.Merge(c.BBox())
    for t in m.GraphicalItems():
        if isinstance(t, pcbnew.PCB_TEXT) and t.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            bb.Merge(t.GetBoundingBox())
    return tuple(bbox_mm(bb))


def put(m, x, y, rot=0, side='F', align=None):
    """Place so that the box centre (or the aligned box edge) lands on x/y."""
    m.SetOrientationDegrees(rot)
    if side == 'B' and not m.IsFlipped():
        m.Flip(m.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    m.SetPosition(V(0, 0))
    x0, y0, x1, y1 = box(m)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x - cx, y - cy
    if align == 'top':
        dy = y + EDGE - y0
    elif align == 'bottom':
        dy = y - EDGE - y1
    elif align == 'left':
        dx = x + EDGE - x0
    elif align == 'right':
        dx = x - EDGE - x1
    m.SetPosition(V(dx, dy))


def place_row(mods, keys, edge, pos, gap, rot, pitch=None):
    """Place a row of parts along an edge from pos; returns the position after the row."""
    for key in keys:
        key, r = key if isinstance(key, tuple) else (key, rot)
        m = mods[key]
        put(m, 0, 0, rot=r)
        x0, y0, x1, y1 = box(m)
        size = (x1 - x0) if edge in ('top', 'bottom') else (y1 - y0)
        c = pos + (pitch / 2 if pitch else size / 2)
        at = {'top': (c, 0), 'bottom': (c, H), 'left': (0, c), 'right': (W, c)}[edge]
        put(m, at[0], at[1], rot=r, align=edge)
        pos += pitch if pitch else size + gap
    return pos


class Grid:
    """Occupancy of the top side at RES mm; parts are placed in the first free spot of a window."""
    RES = 0.5

    def __init__(self, w=W, h=H, edge=EDGE):
        self.w, self.h, self.edge = w, h, edge
        self.nx, self.ny = int(w / self.RES) + 1, int(h / self.RES) + 1
        self.rows = [bytearray(self.nx) for _ in range(self.ny)]

    def cells(self, x0, y0, x1, y1):
        r = self.RES
        return (max(0, int(x0 / r)), max(0, int(y0 / r)), min(self.nx, int(x1 / r + 0.999)), min(self.ny, int(y1 / r + 0.999)))

    def mark(self, x0, y0, x1, y1):
        c0, r0, c1, r1 = self.cells(x0, y0, x1, y1)
        for r in range(r0, r1):
            self.rows[r][c0:c1] = b'\x01' * (c1 - c0)

    def near(self, w, h, target):
        """Top-left (mm) of the free w x h spot whose centre is nearest to target, or None."""
        import numpy as np
        e = self.edge
        occ = np.array([list(r) for r in self.rows], dtype=np.int32)
        sat = np.zeros((self.ny + 1, self.nx + 1), dtype=np.int32)
        sat[1:, 1:] = occ.cumsum(0).cumsum(1)
        cw, ch = int(w / self.RES + 0.999), int(h / self.RES + 0.999)
        lo, hi_x, hi_y = int(e / self.RES + 0.999), int((self.w - e) / self.RES) - cw, int((self.h - e) / self.RES) - ch
        if hi_x < lo or hi_y < lo:
            return None
        cnt = sat[ch:, cw:] - sat[:-ch, cw:] - sat[ch:, :-cw] + sat[:-ch, :-cw]     # [r, c]: cells used in the window
        cnt = cnt[lo:hi_y + 1, lo:hi_x + 1]
        rr, cc = np.nonzero(cnt == 0)
        if not len(rr):
            return None
        cx = (cc + lo) * self.RES + w / 2
        cy = (rr + lo) * self.RES + h / 2
        i = int(np.argmin((cx - target[0]) ** 2 + (cy - target[1]) ** 2))
        return float((cc[i] + lo) * self.RES), float((rr[i] + lo) * self.RES)

    def free(self, c0, r0, c1, r1):
        if c0 < 0 or r0 < 0 or c1 > self.nx or r1 > self.ny:
            return False
        for r in range(r0, r1):
            if self.rows[r].find(1, c0, c1) != -1:
                return False
        return True

    def find(self, w, h, win):
        """Top-left (mm) of the first free w x h spot scanning the window row by row, or None."""
        x0, y0, x1, y1 = win
        cw, ch = int(w / self.RES + 0.999), int(h / self.RES + 0.999)
        e = self.edge
        c0, r0, c1, r1 = self.cells(max(x0, e), max(y0, e), min(x1, self.w - e), min(y1, self.h - e))
        for r in range(r0, r1 - ch + 1):
            c = c0
            while c <= c1 - cw:
                row = self.rows[r]
                hit = row.find(1, c, c + cw)
                if hit != -1:
                    c = hit + 1
                    continue
                if self.free(c, r, c + cw, r + ch):
                    return c * self.RES, r * self.RES
                c += 1
        return None


def gap(m):
    return GAP_IC if m.GetPadCount() >= 8 else GAP


def place_tie(board, m, host_value):
    """A net tie onto the pad of its pad-1 net on a part with value `host_value` (the one nearest the parts of its
    pad-2 net): pad 1 just inside that pad's edge, pad 2 outside it, towards those parts. Returns an error or None."""
    p1, p2 = (next(p for p in m.Pads() if p.GetNumber() == n) for n in ('1', '2'))
    n1, n2 = p1.GetNetCode(), p2.GetNetCode()
    hosts = [p for p in board.GetPads() if p.GetNetCode() == n1 and p.GetParentFootprint().GetValue() == host_value]
    far = [p for p in board.GetPads() if p.GetNetCode() == n2 and p.GetParentFootprint() is not m]
    if not hosts or not far:
        return 'net tie %s: no %s pad on its net' % (m.GetReference(), host_value)
    tx = sum(pcbnew.ToMM(p.GetPosition().x) for p in far) / len(far)
    ty = sum(pcbnew.ToMM(p.GetPosition().y) for p in far) / len(far)
    def mm_xy(p):
        return pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    host = min(hosts, key=lambda p: math.hypot(mm_xy(p)[0] - tx, mm_xy(p)[1] - ty))
    hx, hy = mm_xy(host)
    dx, dy = tx - hx, ty - hy
    d = (1 if dx >= 0 else -1, 0) if abs(dx) >= abs(dy) else (0, 1 if dy >= 0 else -1)
    if host.IsOnLayer(pcbnew.B_Cu) and not host.IsOnLayer(pcbnew.F_Cu) and not m.IsFlipped():
        m.Flip(m.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    best = None
    for rot in (0, 90, 180, 270):                  # pad 1 -> pad 2 along d
        m.SetOrientationDegrees(rot)
        (ax, ay), (bx, by) = mm_xy(p1), mm_xy(p2)
        dot = (bx - ax) * d[0] + (by - ay) * d[1]
        if best is None or dot > best[0]:
            best = (dot, rot)
    m.SetOrientationDegrees(best[1])
    bb = host.GetBoundingBox()
    half = pcbnew.ToMM(bb.GetWidth() if d[0] else bb.GetHeight()) / 2
    r1 = pcbnew.ToMM(p1.GetBoundingBox().GetWidth() if d[0] else p1.GetBoundingBox().GetHeight()) / 2
    ax, ay = mm_xy(p1)
    want = (hx + d[0] * (half - r1 - 0.05), hy + d[1] * (half - r1 - 0.05))
    pos = m.GetPosition()
    m.SetPosition(V(pcbnew.ToMM(pos.x) + want[0] - ax, pcbnew.ToMM(pos.y) + want[1] - ay))
    return None


def occupy(grid, m):
    """Mark a placed part: its box if on top, only its holes if on the back."""
    if not m.IsFlipped():
        x0, y0, x1, y1 = box(m)
        g = gap(m) / 2
        grid.mark(x0 - g, y0 - g, x1 + g, y1 + g)
        return
    for pad in m.Pads():                   # holes only: SMD pads on the back leave the top free
        if pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            continue
        x0, y0, x1, y1 = bbox_mm(pad.GetBoundingBox())
        grid.mark(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)


def dump(grid, path):
    """The occupancy grid as a PGM picture (white = free), for debugging."""
    with open(os.path.splitext(path)[0] + '.pgm', 'wb') as f:
        f.write(b'P5 %d %d 1\n' % (grid.nx, grid.ny))
        for row in grid.rows:
            f.write(bytes(1 - v for v in row))


def cluster(grid, mods, r, avoid=None):
    """Pack a block's parts into a cluster, then place it (BLOCK_GAP / 2 fence around it) at the free spot nearest to
    r. Clusters of several aspect ratios are tried (about square first); the one that lands nearest wins. Returns how
    far (mm) the cluster centre ended up from r."""
    area = sum((b[2] - b[0] + gap(m)) * (b[3] - b[1] + gap(m)) for m, b in ((m, box(m)) for m in mods))
    least = max(min(b[2] - b[0], b[3] - b[1]) + GAP_IC for b in map(box, mods))
    f = BLOCK_GAP / 2
    cands = []
    for aspect in ASPECTS:                 # pack at several widths, keep the positions of each
        width = max(math.sqrt(FILL * area * aspect), least)
        local = Grid(width, 400, edge=0)
        pack(local, mods, (0, 0, width, 400))
        bs = [box(m) for m in mods]
        bx = (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
        w, h = bx[2] - bx[0] + 2 * f, bx[3] - bx[1] + 2 * f + 1.5     # 1.5: the block name above the outline
        cands.append((w * h, w, h, bx, [(m.GetPosition(), m.GetOrientationDegrees()) for m in mods]))
    least_area = min(c[0] for c in cands)
    best = None
    saved = [bytearray(row) for row in grid.rows]
    if avoid:                              # kept out of this area (the TFT module, for sensors that must see out)
        grid.mark(*avoid)
    for a_, w, h, bx, pos in sorted(cands, key=lambda c: c[0]):
        if a_ > SLACK * least_area and best:   # only the tight packings, unless none of them fits
            break
        spot = grid.near(w, h, r)
        if spot:
            d = math.hypot(spot[0] + w / 2 - r[0], spot[1] + h / 2 - r[1])
            if best is None or d < best[0] - 2:
                best = (d, pos, spot, w, h, bx)
    grid.rows = saved
    if not best:
        dump(grid, os.path.join(tempfile.gettempdir(), 'pcbgen_grid.png'))
        for m in mods:                     # left below the board, for a look at what did not fit
            m.Move(V(0, H + 30))
        return None
    d, pos, spot, w, h, bx = best
    dx, dy = spot[0] + f - bx[0], spot[1] + f + 1.5 - bx[1]
    for m, (p, rot) in zip(mods, pos):
        m.SetOrientationDegrees(rot)
        m.SetPosition(p)
        m.Move(V(dx, dy))
    grid.mark(spot[0], spot[1], spot[0] + w, spot[1] + h)
    return d


def passive(m):
    """Small two-pad SMD resistors and capacitors without a label: stacked into columns."""
    if m.GetPadCount() != 2 or not re.match(r'[RC]\d', m.GetReference()) or any(
            p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in m.Pads()):
        return False
    put(m, 0, 0)
    b = box(m)
    return (b[2] - b[0]) * (b[3] - b[1]) < 12


def units(mods):
    """Packing units: single parts, and columns of up to COLUMN passives of one size, courtyards touching (like the
    pins of an IC: a real space saver). Each unit is (parts, place(x, y, vertical) -> None, size(vertical))."""
    def ref_key(m):
        r = m.GetReference()
        return (r[0], int(re.sub(r'\D', '', r) or 0))
    single, groups = [], {}
    for m in mods:
        if passive(m):
            put(m, 0, 0)
            b = box(m)
            groups.setdefault((round(b[2] - b[0], 1), round(b[3] - b[1], 1)), []).append(m)
        else:
            single.append([m])
    cols = []
    for (bw, bh), ms in groups.items():
        ms.sort(key=ref_key)
        n = math.ceil(len(ms) / COLUMN)
        size = math.ceil(len(ms) / n)
        cols += [ms[i:i + size] for i in range(0, len(ms), size)]
    return single + cols


def pack(grid, mods, r):
    """Place the units (largest first) in the first free spots of region r, growing it until they fit. A unit of
    several passives is a column (parts unrotated, stacked in y) or a row (parts at 90 degrees, side by side in x)."""
    def dims(u, rot):
        bs = []
        for m in u:
            put(m, 0, 0, rot=rot)
            bs.append(box(m))
        if len(u) == 1:
            b = bs[0]
            return b[2] - b[0], b[3] - b[1]
        if rot == 0:
            return max(b[2] - b[0] for b in bs), sum(b[3] - b[1] for b in bs)
        return sum(b[2] - b[0] for b in bs), max(b[3] - b[1] for b in bs)
    us = sorted(units(mods), key=lambda u: -(lambda d: d[0] * d[1])(dims(u, 0)))
    moved = []
    for u in us:
        g = gap(u[0])
        best = None
        for rot in (0, 90):
            w, h = dims(u, rot)
            w, h = w + g, h + g
            grow, spot = 0, None
            while grow <= max(W, H):
                spot = grid.find(w, h, (r[0] - grow, r[1] - grow, r[2] + grow, r[3] + grow))
                if spot:
                    break
                grow += 4
            if spot and (best is None or grow < best[0]):
                best = (grow, rot, spot, w, h)
            if best and best[0] == 0:
                break
        grow, rot, (x, y), w, h = best
        cx, cy = x + g / 2, y + g / 2
        for m in u:
            put(m, 0, 0, rot=rot)
            b = box(m)
            if len(u) == 1:
                put(m, x + w / 2, y + h / 2, rot=rot)
            elif rot == 0:
                put(m, x + w / 2, cy + (b[3] - b[1]) / 2, rot=rot)
                cy += b[3] - b[1]
            else:
                put(m, cx + (b[2] - b[0]) / 2, y + h / 2, rot=rot)
                cx += b[2] - b[0]
        grid.mark(x, y, x + w, y + h)
        if grow:
            moved += u
    return moved


# ---------------------------------------------------------------------------------------------------------------
# spreading the packed blocks into the free room, and outlining each block with a polygon around its parts
def _sep(B, b):
    """Separation of box b from each of the boxes B: the largest axis gap (negative: they overlap)."""
    import numpy as np
    return np.maximum(np.maximum(B[:, 0] - b[2], b[0] - B[:, 2]), np.maximum(B[:, 1] - b[3], b[1] - B[:, 3]))


PART, NAME, HOLE, BACK_SMD, KEEPOUT = range(5)


def spread(items, scale=SPREAD, step=0.05):
    """Move the movable items away from their block's centre, up to `scale` times their distance from it, wherever
    the room is: in steps, each item as far as it can go (or along x or y alone). Items are dicts: box, block (index;
    -1: none), kind, gap, move, cut (a part with a cutout: keeps off SMD pads on the back), uncovered (keeps out of
    KEEPOUT). Gaps: as packed within a block, BLOCK_GAP between blocks; never less than at the start. Returns the
    (dx, dy) of each item."""
    import numpy as np
    n = len(items)
    B = np.array([it['box'] for it in items], dtype=float)
    blk = np.array([it['block'] for it in items])
    kind = np.array([it['kind'] for it in items])
    g = np.array([it.get('gap', 0.0) for it in items])
    B0 = B.copy()
    R = np.empty((n, n))
    for i, it in enumerate(items):
        same = (blk == blk[i]) & (blk[i] >= 0)
        if kind[i] == NAME:
            r = np.where((kind == PART) | (kind == NAME), np.where(same, 0.9, 1.2), np.where(kind == HOLE, 0.5, -1e9))
        else:
            r = np.where(same, (g[i] + g) / 2, BLOCK_GAP)
            r = np.where(kind == NAME, np.where(same, 0.9, 1.2), r)
            r = np.where(kind == HOLE, 1.0, r)
            r = np.where(kind == BACK_SMD, 0.5 if it.get('cut') else -1e9, r)
            r = np.where(kind == KEEPOUT, 0.0 if it.get('uncovered') else -1e9, r)
        r = np.minimum(r, _sep(B0, B0[i]) - 1e-6)     # never worse than at the start
        r[i] = -1e9
        R[i] = r
    mov = [i for i, it in enumerate(items) if it.get('move')]
    cent = {}
    for b in set(blk[mov].tolist()):
        bs = B0[[i for i in mov if blk[i] == b and kind[i] == PART]]
        cent[b] = ((bs[:, 0].min() + bs[:, 2].max()) / 2, (bs[:, 1].min() + bs[:, 3].max()) / 2)
    c0 = np.column_stack(((B0[:, 0] + B0[:, 2]) / 2, (B0[:, 1] + B0[:, 3]) / 2))
    order = sorted(mov, key=lambda i: -math.hypot(c0[i, 0] - cent[blk[i]][0], c0[i, 1] - cent[blk[i]][1]))

    def ok(i, b):
        return (b[0] >= EDGE and b[1] >= EDGE and b[2] <= W - EDGE and b[3] <= H - EDGE
                and bool((_sep(B, b) >= R[i]).all()))
    s = 1.0
    while s < scale - 1e-9:
        s = min(scale, s + step)
        for _ in range(2):
            for i in order:
                cx, cy = cent[blk[i]]
                dx = cx + s * (c0[i, 0] - cx) - (B[i, 0] + B[i, 2]) / 2
                dy = cy + s * (c0[i, 1] - cy) - (B[i, 1] + B[i, 3]) / 2
                if abs(dx) < 0.01 and abs(dy) < 0.01:
                    continue
                for fx, fy in ((1, 1), (0.5, 0.5), (1, 0), (0, 1), (0.25, 0.25)):
                    b = B[i] + (dx * fx, dy * fy, dx * fx, dy * fy)
                    if ok(i, b):
                        B[i] = b
                        break
    return [(float(B[i, 0] - B0[i, 0]), float(B[i, 1] - B0[i, 1])) for i in range(n)]


def _dilate(a, k):
    """Square dilation of a boolean array by k cells."""
    b = a.copy()
    for d in range(1, k + 1):
        b[:, d:] |= a[:, :-d]
        b[:, :-d] |= a[:, d:]
    c = b.copy()
    for d in range(1, k + 1):
        c[d:, :] |= b[:-d, :]
        c[:-d, :] |= b[d:, :]
    return c


def _fill_holes(m):
    import numpy as np
    bg = ~m
    reach = np.zeros_like(m)
    reach[0, :], reach[-1, :], reach[:, 0], reach[:, -1] = bg[0, :], bg[-1, :], bg[:, 0], bg[:, -1]
    while True:
        nxt = _dilate(reach, 1) & bg
        if (nxt == reach).all():
            return ~reach
        reach = nxt


def block_mask(own, avoid):
    """The cells (LINK_RES) inside a block's outline polygon: its parts' boxes (0.4 mm around), closed by CLOSE,
    holes filled, without the `avoid` boxes ((box, grow): other blocks' parts, the names). Board-sized bool array."""
    import numpy as np
    r = LINK_RES
    nx, ny = int(W / r), int(H / r)
    k = int(round(CLOSE / r))
    pad = 2 * k + 4
    i0 = max(0, int(min(b[0] for b in own) / r) - pad)
    j0 = max(0, int(min(b[1] for b in own) / r) - pad)
    i1 = min(nx, int(max(b[2] for b in own) / r) + pad)
    j1 = min(ny, int(max(b[3] for b in own) / r) + pad)
    win = np.zeros((j1 - j0, i1 - i0), dtype=bool)

    def paint(a, b, grow, val):
        a0, a1 = max(i0, math.floor((b[0] - grow) / r)), min(i1, math.ceil((b[2] + grow) / r))
        c0, c1 = max(j0, math.floor((b[1] - grow) / r)), min(j1, math.ceil((b[3] + grow) / r))
        if a1 > a0 and c1 > c0:
            a[c0 - j0:c1 - j0, a0 - i0:a1 - i0] = val
    for b in own:
        paint(win, b, 0.4, True)
    core = win.copy()
    m = ~_dilate(~_dilate(win, k), k)
    m = _fill_holes(m)
    for b, grow in avoid:
        paint(m, b, grow, False)
    m |= core
    full = np.zeros((ny, nx), dtype=bool)
    full[j0:j1, i0:i1] = m
    e = int(math.ceil(0.5 / r))
    full[:e, :] = False
    full[-e:, :] = False
    full[:, :e] = False
    full[:, -e:] = False
    return full


def trace(mask):
    """The boundary loops of a cell mask as rectilinear polygons (mm, corners only), interior on the right."""
    import numpy as np
    r = LINK_RES
    p = np.pad(mask, 1)
    inner = p[1:-1, 1:-1]
    out = {}
    for (dj, di), (a, b) in (((-1, 0), ((0, 0), (1, 0))), ((0, 1), ((1, 0), (1, 1))),
                             ((1, 0), ((1, 1), (0, 1))), ((0, -1), ((0, 1), (0, 0)))):
        nb = p[1 + dj:p.shape[0] - 1 + dj, 1 + di:p.shape[1] - 1 + di]
        js, is_ = np.nonzero(inner & ~nb)
        for j, i in zip(js.tolist(), is_.tolist()):
            out.setdefault((i + a[0], j + a[1]), []).append((i + b[0], j + b[1]))
    loops = []
    while out:
        start = next(iter(out))
        v, cur, heading = start, [start], None
        while True:
            ends = out[v]
            if heading is None or len(ends) == 1:
                w = ends[0]
            else:                              # prefer a right turn: diagonal neighbours stay apart
                rank = {(-heading[1], heading[0]): 0, heading: 1, (heading[1], -heading[0]): 2}
                w = min(ends, key=lambda e: rank.get((e[0] - v[0], e[1] - v[1]), 3))
            ends.remove(w)
            if not ends:
                del out[v]
            heading = (w[0] - v[0], w[1] - v[1])
            v = w
            if v == start:
                break
            cur.append(v)
        n = len(cur)
        pts = [q for k, q in enumerate(cur) if (cur[k - 1][0] - q[0]) * (cur[(k + 1) % n][1] - q[1])
               != (cur[k - 1][1] - q[1]) * (cur[(k + 1) % n][0] - q[0])]
        loops.append([(x * r, y * r) for x, y in pts])
    return loops


# ---------------------------------------------------------------------------------------------------------------
# silkscreen connection lines between the blocks: a minimum spanning tree per bus or rail (I2C, SPI, UART, USB, each
# power rail but GND and +3V3) and per other signal, drawn along the channels between the blocks (A* on a grid)
LINK_RES = 0.25
BLOCK_COST = 150             # per cell across a block or part (lines go round them where they can)
USED_COST = 12               # per cell along another line or over a label (crossing one costs little)
LINK_WIDTH = {'power': 0.35, 'bus': 0.12, 'signal': 0.12}
BUSES = [(r'SCL|SDA', 'I2C'), (r'SPI_|MOSI|MISO|SCLK|_CS$', 'SPI'), (r'LINK_|UART|_TXD?$|_RXD?$', 'UART'),
         (r'_D[PM]$|^USB', 'USB')]


def link_groups(byref, block_of, outlines):
    """{key: [kind, label, blocks]} for the nets that join two or more outlined blocks."""
    power = {n for cls in NETCLASSES.values() for n in cls[4]} - {'+3V3'}
    groups = {}
    for ref, m in byref.items():
        t = block_of.get(ref)
        if t not in outlines:
            continue
        for pad in m.Pads():
            net = pad.GetNetname()
            name = net.split('/')[-1]
            if not net or net.startswith('unconnected') or name in ('GND', '+3V3'):
                continue
            kind, key, label = 'signal', name, short(name)
            if name in power:                  # a motor's + and - as one line
                kind, label = 'power', re.sub(r'_[PN]$', '', name.lstrip('+'))
                key = label
            else:
                for pattern, bus in BUSES:
                    if re.search(pattern, name):
                        kind, label = 'bus', bus
                        key = bus if bus in ('SPI', 'UART') else re.sub(pattern, '', name) + bus
                        break
            groups.setdefault(key, [kind, label, set()])[2].add(t)
    return {k: g for k, g in groups.items() if len(g[2]) > 1}


def rect_gap(a, b):
    return math.hypot(max(0, a[0] - b[2], b[0] - a[2]), max(0, a[1] - b[3], b[1] - a[3]))


def link_edges(groups, outlines):
    """Edges (a, b, kind, label): a minimum spanning tree per group; signals between the same two blocks merged."""
    edges = {}
    for kind, label, blocks in groups.values():
        todo, done = set(blocks), set()
        done.add(todo.pop())
        while todo:
            a, b = min(((a, b) for a in done for b in todo), key=lambda ab: rect_gap(outlines[ab[0]], outlines[ab[1]]))
            todo.discard(b)
            done.add(b)
            pair = tuple(sorted((a, b)))
            edges.setdefault((pair, kind, label if kind != 'signal' else ''), set()).add(label)
    out = []
    for (pair, kind, label), labels in edges.items():
        if kind == 'signal':                   # merged signals: their common prefix (HX_DOUT, HX_SCK: HX), or none
            heads = {lb.split('_')[0] for lb in labels}
            label = labels.pop() if len(labels) == 1 else heads.pop() if len(heads) == 1 else ''
        out.append((pair[0], pair[1], kind, label))
    order = {'power': 0, 'bus': 1, 'signal': 2}
    return sorted(out, key=lambda e: (order[e[2]], rect_gap(outlines[e[0]], outlines[e[1]])))


def _edge_point(mask, j, i):
    """The midpoint of the side that cell (j, i), just outside a block, shares with the block."""
    r = LINK_RES
    for dj, di in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        jj, ii = j + dj, i + di
        if 0 <= jj < mask.shape[0] and 0 <= ii < mask.shape[1] and mask[jj, ii]:
            return ((i + 0.5 + di * 0.5) * r, (j + 0.5 + dj * 0.5) * r)
    return ((i + 0.5) * r, (j + 0.5) * r)


def route_link(cost, used, ma, mb):
    """Cheapest 4-connected path (turns and used cells cost extra) from just outside block mask ma to just outside mb."""
    import heapq
    import numpy as np
    r, ny, nx = LINK_RES, cost.shape[0], cost.shape[1]

    def ring(m):
        a = m.copy()
        a[1:, :] |= m[:-1, :]
        a[:-1, :] |= m[1:, :]
        a[:, 1:] |= m[:, :-1]
        a[:, :-1] |= m[:, 1:]
        js, is_ = np.nonzero(a & ~m & (cost < 1e6))
        return set(zip(js.tolist(), is_.tolist()))
    starts, goals = ring(ma), ring(mb)
    if not starts or not goals:
        return None
    gy0, gy1 = min(j for j, _ in goals), max(j for j, _ in goals)
    gx0, gx1 = min(i for _, i in goals), max(i for _, i in goals)

    def h(j, i):
        return max(0, gx0 - i, i - gx1) + max(0, gy0 - j, j - gy1)
    dist, prev, heap = {}, {}, []
    for (j, i) in starts:
        for d in range(4):
            dist[(j, i, d)] = 0.0
            heapq.heappush(heap, (h(j, i), 0.0, j, i, d))
    steps = ((0, 1), (1, 0), (0, -1), (-1, 0))
    end = None
    while heap:
        f, g, j, i, d = heapq.heappop(heap)
        if g > dist.get((j, i, d), 1e18):
            continue
        if (j, i) in goals:
            end = (j, i, d)
            break
        for nd, (dj, di) in enumerate(steps):
            if nd == (d + 2) % 4:
                continue
            nj, ni = j + dj, i + di
            if not (0 <= nj < ny and 0 <= ni < nx):
                continue
            c = float(cost[nj, ni])
            if c >= 1e6:
                continue
            ng = g + c + USED_COST * float(used[nj, ni]) + (3.0 if nd != d else 0.0)
            if ng < dist.get((nj, ni, nd), 1e18):
                dist[(nj, ni, nd)] = ng
                prev[(nj, ni, nd)] = (j, i, d)
                heapq.heappush(heap, (ng + h(nj, ni), ng, nj, ni, nd))
    if end is None:
        return None
    cells = [end]
    while cells[-1] in prev:
        cells.append(prev[cells[-1]])
    cells.reverse()
    pts = [((i + 0.5) * r, (j + 0.5) * r) for j, i, d in cells]
    pts = [_edge_point(ma, *cells[0][:2])] + pts + [_edge_point(mb, *cells[-1][:2])]
    simple = [pts[0]]                          # keep the corners only
    for k in range(1, len(pts) - 1):
        a, b, c = simple[-1], pts[k], pts[k + 1]
        if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) > 1e-6:
            simple.append(b)
    simple.append(pts[-1])
    return simple, [(j, i) for j, i, d in cells]


def _seg(board, a, b, width):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.F_SilkS)
    s.SetWidth(mm(width))
    s.SetStart(V(*a))
    s.SetEnd(V(*b))
    board.Add(s)


def connection_lines(board, byref, block_of, masks, obstacles, names):
    """Draw the links on F.SilkS between the block outlines (masks: title -> cells); returns the number of links that
    found no path."""
    import numpy as np
    r = LINK_RES
    outlines = {}
    for t, mk in masks.items():
        js, is_ = np.nonzero(mk)
        outlines[t] = (is_.min() * r, js.min() * r, (is_.max() + 1) * r, (js.max() + 1) * r)
    nx, ny = int(W / r), int(H / r)
    cost = np.ones((ny, nx), dtype=np.float32)

    def fill(rc, val, grow):
        i0, i1 = max(0, math.ceil((rc[0] - grow) / r - 0.5)), min(nx, math.floor((rc[2] + grow) / r - 0.5) + 1)
        j0, j1 = max(0, math.ceil((rc[1] - grow) / r - 0.5)), min(ny, math.floor((rc[3] + grow) / r - 0.5) + 1)
        cost[j0:j1, i0:i1] = np.maximum(cost[j0:j1, i0:i1], val)
    e = int(1.0 / r)
    cost[:e, :] = 1e9
    cost[-e:, :] = 1e9
    cost[:, :e] = 1e9
    cost[:, -e:] = 1e9
    for mk in masks.values():
        near = _dilate(mk, 2) & ~mk                # lines keep a little off the outlines (not along them)
        cost[near] = np.maximum(cost[near], 6)
        cost[mk] = np.maximum(cost[mk], BLOCK_COST)
    for rc in obstacles:
        fill(rc, BLOCK_COST, 0.2)
    used = np.zeros((ny, nx), dtype=np.float32)
    for rc in names:                           # block names: no lines over them
        fill(rc, BLOCK_COST, 0.1)

    def window(mx, my, hw, hh):
        return slice(max(0, int((my - hh) / r)), int((my + hh) / r) + 1), slice(max(0, int((mx - hw) / r)), int((mx + hw) / r) + 1)
    failed = 0
    for a, b, kind, label in link_edges(link_groups(byref, block_of, outlines), outlines):
        res = route_link(cost, used, masks[a], masks[b])
        if not res:
            failed += 1
            continue
        pts, cells = res
        k = 2 if kind == 'power' else 1
        for j, i in cells:
            used[max(0, j - k):j + k + 1, max(0, i - k):i + k + 1] += 1
        segs = list(zip(pts, pts[1:]))
        size = 0.9 if kind == 'power' else 0.8
        tl = 0.75 * size * len(label) + 0.8 if label else 0
        best = None                            # the label: where its box is the least crowded along the line
        for q, (p0, p1) in enumerate(segs):
            ln = math.dist(p0, p1)
            if not label or ln < tl + 1.0:
                continue
            ux, uy = (p1[0] - p0[0]) / ln, (p1[1] - p0[1]) / ln
            vert = abs(uy) > abs(ux)
            hw, hh = (size / 2 + 0.3, tl / 2) if vert else (tl / 2, size / 2 + 0.3)
            t = tl / 2 + 0.5
            while t <= ln - tl / 2 - 0.5 + 1e-6:
                mx, my = p0[0] + ux * t, p0[1] + uy * t
                w_ = window(mx, my, hw, hh)
                score = float(used[w_].sum()) + 20.0 * float((cost[w_] > 1).sum()) + 0.02 * abs(t - ln / 2)
                if best is None or score < best[0]:
                    best = (score, q, t, mx, my, ux, uy, vert, hw, hh)
                t += 0.5
        for q, (p0, p1) in enumerate(segs):
            if best and q == best[1]:
                _, _, t, mx, my, ux, uy, vert, hw, hh = best
                _seg(board, p0, (mx - ux * tl / 2, my - uy * tl / 2), LINK_WIDTH[kind])
                _seg(board, (mx + ux * tl / 2, my + uy * tl / 2), p1, LINK_WIDTH[kind])
                silk(board, label, mx, my, size=size, angle=90 if vert else 0)
                used[window(mx, my, hw, hh)] += 3
            elif math.dist(p0, p1) > 0.01:
                _seg(board, p0, p1, LINK_WIDTH[kind])
    return failed

# ---------------------------------------------------------------------------------------------------------------
# silkscreen: no references; parts that matter carry a label (function, type or net), connectors their pin names
def silk(parent, text, x, y, size=0.8, angle=0, justify=0, layer=None):
    t = pcbnew.PCB_TEXT(parent)
    t.SetText(text)
    t.SetLayer(layer if layer is not None else pcbnew.F_SilkS)
    t.SetTextSize(V(size, size))
    t.SetTextThickness(mm(max(0.1, size * 0.15)))
    t.SetTextAngleDegrees(angle)
    t.SetHorizJustify({-1: pcbnew.GR_TEXT_H_ALIGN_RIGHT, 0: pcbnew.GR_TEXT_H_ALIGN_CENTER, 1: pcbnew.GR_TEXT_H_ALIGN_LEFT}[justify])
    t.SetPosition(V(x, y))
    t.SetKeepUpright(True)
    parent.Add(t)
    return t


def short(net):
    n = net.split('/')[-1].replace('_CONN', '').lstrip('+')
    for suffix in ('_5V', '_H'):
        if n.endswith(suffix):
            n = n[:-len(suffix)]
    if '_' in n and len(n) > 6:
        n = n.split('_', 1)[1]
    return n


# short IC labels (no package and grade suffixes): (value regex, label); single-gate logic is BUF
IC_LABELS = [(r'74\w*1G(34|125)', 'BUF'), (r'ADS1115', 'ADS1115'), (r'AP63205', 'AP63205'), (r'AS5600', 'AS5600'),
             (r'BQ25792', 'BQ25792'), (r'BQ77915', 'BQ77915'), (r'HUSB238', 'HUSB238'), (r'INA226', 'INA226'),
             (r'ITR20001', 'ITR20001'), (r'LM393', 'LM393'), (r'LSM6DS3', 'LSM6DS3'), (r'MCP23017', 'MCP23017'),
             (r'MCP3008', 'MCP3008'), (r'PCA9685', 'PCA9685'), (r'TB6612', 'TB6612'), (r'TCA9548', 'TCA9548'),
             (r'TPS25947', 'TPS25947'), (r'TPS54331', 'TPS54331'), (r'USBLC6', 'USBLC6'), (r'VEML7700', 'VEML7700'),
             (r'VL53L7CX', 'VL53L7CX'), (r'WF100DP', 'WF100DP')]


def part_label(m, value, fpname):
    """The silkscreen label of a part (None: none)."""
    prefix = re.match(r'[A-Z]+', m.GetReference()).group()
    if prefix == 'TP':
        return value
    if prefix == 'D' and fpname.startswith('LED_'):
        return 'RGB' if 'SK6812' in value else value.split()[0]
    if prefix == 'RV':
        return short(m.FindPadByNumber('2').GetNetname()) if 'RK09' in fpname else 'THRESHOLD'
    if prefix == 'U':
        if value.startswith('ESP32'):
            return 'ESP32-C5 ' + value.split()[-1]
        v = value.split()[0]
        for pattern, label in IC_LABELS:
            if re.match(pattern, v):
                return label
        return v
    if prefix in ('J', 'SW', 'JP'):
        return value
    if prefix == 'BZ':
        return 'BUZZER'
    return None


def label_part(m, text):
    """Label at the footprint's value position (below the body), before the part is placed (orientation 0)."""
    v = m.Value().GetPosition()
    size = 1.0 if m.GetPadCount() > 3 or re.match(r'(J|SW|U|RV)\d', m.GetReference()) else 0.8
    silk(m, text, pcbnew.ToMM(v.x), pcbnew.ToMM(v.y) + 0.2, size=size)


def pin_labels(m, side=None):
    """Net names beside the pads of a connector with 2 mm pitch or more (rows of pads), in board coordinates of the
    part as it is now. side: (dx, dy) towards the board inside for edge parts; else -x (vertical rows) or -y."""
    pads = [p for p in m.Pads() if p.GetNumber() and p.GetNetname() and not p.GetNetname().startswith('unconnected')
            and p.GetNumber() not in ('MP',)]
    if len(pads) < 2:
        return
    pts = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p) for p in pads]
    xs, ys = sorted({round(x, 2) for x, _, _ in pts}), sorted({round(y, 2) for _, y, _ in pts})
    vertical = len(ys) >= len(xs)          # pads in rows along y
    across = xs if vertical else ys
    if len(across) > 2:
        return
    pitch = min(abs(a - b) for a in (ys if vertical else xs) for b in (ys if vertical else xs) if a != b) if len(pts) > 1 else 0
    if pitch < 1.9:
        return
    # 2-way screw terminals: a large + at pin 1 (the rail, or a motor's +) and - at pin 2 (GND, or a motor's -)
    signs = {'1': '+', '2': '-'} if len(pts) == 2 and 'TerminalBlock' in m.GetFPID().GetLibItemName().wx_str() else {}
    for x, y, p in pts:
        bb = bbox_mm(p.GetBoundingBox())
        sign = signs.get(p.GetNumber())
        if len(across) == 2:
            s = -1 if round(x if vertical else y, 2) == across[0] else 1
        elif side is not None:
            s = side[0] if vertical else side[1]
        else:
            s = -1
        name = short(p.GetNetname())
        off = 0.5
        if sign:                               # beyond the body (silkscreen under it cannot be seen): the sign, then
            c = bbox_mm(m.GetCourtyard(pcbnew.F_CrtYd).BBox())      # the net name
            bb = [c[0], c[1], c[2], c[3]] if vertical else [bb[0], c[1], bb[2], c[3]]
            if vertical:
                bb[1] = bb[3] = y
                silk(m, sign, (bb[0] - 1.2) if s < 0 else (bb[2] + 1.2), y, size=1.8)
            else:
                silk(m, sign, x, (bb[1] - 1.2) if s < 0 else (bb[3] + 1.2), size=1.8)
            off = 2.4
        if vertical:
            silk(m, name, (bb[0] - off) if s < 0 else (bb[2] + off), y, angle=0, justify=-s)
        else:
            silk(m, name, x, (bb[1] - off) if s < 0 else (bb[3] + off), angle=90, justify=-s)


# ---------------------------------------------------------------------------------------------------------------
def main():
    global FP_STD
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbols', default=os.environ.get('KICAD10_SYMBOL_DIR', 'C:/Program Files/KiCad/10.0/share/kicad/symbols'))
    ap.add_argument('--espressif', default=os.environ.get('ESPRESSIF_SYM', ''))
    ap.add_argument('--footprints', default='C:/Program Files/KiCad/10.0/share/kicad/footprints')
    ap.add_argument('--fp-espressif', default='')
    ap.add_argument('--out', default=os.path.join(HERE, PROJECT + '.kicad_pcb'))
    args = ap.parse_args()
    FP_STD = args.footprints
    esp_fp = args.fp_espressif or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(args.espressif))), 'footprints',
                                               os.path.basename(os.path.dirname(args.espressif)), 'Espressif.pretty')

    lib = schgen.Library(args.symbols, args.espressif, PROJECT)
    d = schgen.Design(lib, PROJECT, 'SensorTestSetup PCB', design.REV, design.DATE, 'RaM, University of Twente')
    schgen.build(d, design.describe)
    with contextlib.redirect_stdout(io.StringIO()):          # the render assigns references and blocks
        schgen.write(d, tempfile.mkdtemp(), design.ROOT_NOTES)

    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))
    ds.m_NetSettings.GetDefaultNetclass().SetClearance(mm(0.15))     # fine-pitch pads (VQFN 0.45, LGA 0.5)
    tb = board.GetTitleBlock()
    tb.SetTitle('SensorTestSetup PCB')
    tb.SetRevision(design.REV)
    tb.SetDate(design.DATE)
    tb.SetCompany('RaM, University of Twente')

    def shape(kind, layer, width, *pts):
        s = pcbnew.PCB_SHAPE(board, kind)
        if kind == pcbnew.SHAPE_T_ARC:
            s.SetArcGeometry(*(V(*p) for p in pts))
        else:
            s.SetStart(V(*pts[0]))
            s.SetEnd(V(*pts[1]))
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        board.Add(s)

    def rect(x0, y0, x1, y1, layer, width):
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            shape(pcbnew.SHAPE_T_SEGMENT, layer, width, a, b)

    # outline with 3 mm corner radius
    R = 3.0
    k = R * (1 - 0.7071)
    E, S, A = pcbnew.Edge_Cuts, pcbnew.SHAPE_T_SEGMENT, pcbnew.SHAPE_T_ARC
    shape(S, E, 0.1, (R, 0), (W - R, 0)); shape(S, E, 0.1, (W, R), (W, H - R))
    shape(S, E, 0.1, (W - R, H), (R, H)); shape(S, E, 0.1, (0, H - R), (0, R))
    shape(A, E, 0.1, (W - R, 0), (W - k, k), (W, R)); shape(A, E, 0.1, (W, H - R), (W - k, H - k), (W - R, H))
    shape(A, E, 0.1, (R, H), (k, H - k), (0, H - R)); shape(A, E, 0.1, (0, R), (k, k), (R, 0))

    # nets and fields as KiCad names them (sheet-local nets get their sheet path), from its exported netlist
    sch = os.path.join(HERE, PROJECT + '.kicad_sch')
    netfile = os.path.join(tempfile.mkdtemp(), 'board.net')
    cli = os.path.join(os.path.dirname(sys.executable), 'kicad-cli.exe' if os.name == 'nt' else 'kicad-cli')
    subprocess.run([cli, 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', netfile, sch], check=True,
                   stdout=subprocess.DEVNULL)
    nl = schgen.parse(open(netfile, encoding='utf-8').read())
    pin_net, comp = {}, {}
    nets = {}
    for net in schgen.find(schgen.first(nl, 'nets'), 'net'):
        name = schgen.first(net, 'name')[1]
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
        for node in schgen.find(net, 'node'):
            pin_net[(schgen.first(node, 'ref')[1], schgen.first(node, 'pin')[1])] = name
    for c in schgen.find(schgen.first(nl, 'components'), 'comp'):
        fl = schgen.first(c, 'fields')
        fields = {schgen.first(f, 'name')[1]: (f[2] if len(f) > 2 else '') for f in schgen.find(fl, 'field')} if fl else {}
        props = {schgen.first(q, 'name')[1] for q in schgen.find(c, 'property')}
        comp[schgen.first(c, 'ref')[1]] = (fields, 'exclude_from_bom' in props)

    sheets = {s.name: s for s in d.sheets}
    byref, blocks, plist = {}, {}, []
    for p in d.parts:
        ref = p['ref']
        if ref in byref or not p['footprint']:
            continue
        m = load(p['footprint'], esp_fp)
        m.SetReference(ref)
        m.SetValue(p['value'])
        m.Reference().SetVisible(False)
        fields, no_bom = comp.get(ref, ({}, False))
        for k, v in fields.items():
            if k not in ('Footprint', 'Reference', 'Value'):
                m.SetField(k, v)
                m.GetField(k).SetVisible(False)
        m.SetExcludedFromBOM(no_bom)
        if p['dnp']:
            m.SetDNP(True)
        sh = sheets[p['sheet']]
        m.SetPath(pcbnew.KIID_PATH('/%s/%s' % (sh.uuid, schgen.uid(sh.name, 'sym', ref, 1))))
        m.SetSheetname('%d %s' % (sh.page - 1, sh.title))
        m.SetSheetfile(sh.name + '.kicad_sch')
        for pad in m.Pads():
            n = pin_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(nets[n])
        board.Add(m)
        byref[ref] = m
        blocks.setdefault(p['block'], []).append(m)
        plist.append((ref, p['value'], p['footprint']))

    def resolve(key):
        k, _, n = key.partition('#')
        k, _, fpsub = k.partition('@')
        prefix, value = k.split('=', 1)
        hits = [r for r, v, fp in plist if re.fullmatch(prefix + r'\d+', r) and v == value and fpsub in fp]
        if not hits or (not n and len(hits) > 1) or int(n or 1) > len(hits):
            raise KeyError('key %r matches %s' % (key, hits))
        return hits[int(n or 1) - 1]

    class Mods(dict):
        def __missing__(self, key):
            return byref[resolve(key)]
    mods = Mods()

    ties = {ref: comp[ref][0]['Tie'] for ref in byref if ref in comp and comp[ref][0].get('Tie')}
    servo_rows = {resolve(k) for bank in SERVO_BANKS for k in bank[1:]}
    tft_ref = resolve('J=TFT')
    block_of = {m.GetReference(): title for title, ms in blocks.items() for m in ms}
    ic_seen = set()                        # identical ICs in one block: only the first one is labelled
    for ref, m in sorted(byref.items(), key=lambda kv: (re.sub(r'\d', '', kv[0]), int(re.sub(r'\D', '', kv[0]) or 0))):
        fpname = m.GetFPID().GetLibItemName().wx_str()
        text = None if ref in servo_rows or ref == tft_ref else part_label(m, m.GetValue(), fpname)
        if text and ref.startswith('U') and not text.startswith('ESP32'):
            key = (block_of.get(ref), m.GetValue())
            if key in ic_seen:
                text = None
            ic_seen.add(key)
        if ref.startswith('H') and 'Banana' in fpname:
            text = 'GND'
        if text:
            label_part(m, text)

    # fixed and edge parts
    placed = set()
    for key, (x, y) in HOLES.items():
        put(mods[key], x, y)
        placed.add(resolve(key))
    for key, (x, y, rot, side) in FIXED.items():
        put(mods[key], x, y, rot, side)
        placed.add(resolve(key))
    tft = byref[tft_ref]
    tft.SetOrientationDegrees(0)
    tft.SetPosition(V(*TFT_PIN1))
    placed.add(tft_ref)
    for i, (dx, dy) in enumerate(TFT_HOLES):
        key = 'H=TFT standoff#%d' % (i + 1)
        mods[key].SetPosition(V(TFT_PIN1[0] + dx, TFT_PIN1[1] + dy))
        placed.add(resolve(key))
    servo_text = []
    for b, (name, *keys) in enumerate(SERVO_BANKS):
        y0 = SERVO_Y + b * SERVO_BANK
        for i, key in enumerate(keys):            # SIG inside, then V+, GND at the edge
            m = mods[key]
            m.SetOrientationDegrees(0)
            m.SetPosition(V(W - 3.0 - 2.54 * (2 - i), y0))
            placed.add(resolve(key))
        xs = W - 3.0 - 5.08
        servo_text.append((name, xs - 2.0, y0 + 3 * 2.54 / 2, 90))
        for j in range(4):
            servo_text.append(('%d' % (4 * b + j), xs - 1.6, y0 + 2.54 * j, 0))
    cursor = {}
    for keys, edge, start, *rest in EDGE_ROWS:
        cursor[edge] = place_row(mods, keys, edge, cursor[edge] if start is None else start, *rest)
        inward = {'top': (0, 1), 'bottom': (0, -1), 'left': (1, 0), 'right': (-1, 0)}[edge]
        for key in keys:
            key = key[0] if isinstance(key, tuple) else key
            if resolve(key).startswith('J'):
                pin_labels(mods[key], inward)
            placed.add(resolve(key))
    grid = Grid()
    problems = []
    tops = [r for r in sorted(placed) if not byref[r].IsFlipped()]
    for i, a in enumerate(tops):                   # fixed parts must not collide with each other
        for b in tops[i + 1:]:
            p, q = box(byref[a]), box(byref[b])
            if p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3] and not (a in servo_rows and b in servo_rows):
                problems.append('fixed parts %s and %s overlap' % (a, b))
    for ref in placed:                              # fixed and edge parts, with half the block gap around them
        m = byref[ref]
        occupy(grid, m)
        if not m.IsFlipped() and not ref.startswith('H'):
            x0, y0, x1, y1 = box(m)
            grid.mark(x0 - BLOCK_GAP / 2, y0 - BLOCK_GAP / 2, x1 + BLOCK_GAP / 2, y1 + BLOCK_GAP / 2)
    tx, ty = TFT_PIN1
    x0, y0, x1, y1 = TFT_OUTLINE
    tft_area = (tx + x0, ty + y0, tx + x1, ty + y1)

    # blocks: packed in their regions and fenced off (BLOCK_GAP), then spread and outlined (below)
    edge_refs = {resolve(k[0] if isinstance(k, tuple) else k) for spec in EDGE_ROWS for k in spec[0]} | servo_rows
    def area(ms):
        return sum((b[2] - b[0] + 1) * (b[3] - b[1] + 1) for b in (box(m) for m in ms if m.GetReference() not in placed))
    def order(kv):                         # the FIRST blocks in that order (tied to their edge parts), then large first
        hit = [i for i, f in enumerate(FIRST) if kv[0].startswith(f)]
        return (hit[0] if hit else len(FIRST), -area(kv[1]))
    groups = []
    for title, ms in sorted(blocks.items(), key=order):
        r, name = region(title)
        free = [m for m in ms if m.GetReference() not in placed and m.GetReference() not in ties]
        if free:
            for m in free:
                if m.GetReference().startswith('J'):
                    pin_labels(m)
            if r is None:
                problems.append('no region for block "%s": %s' % (title, ' '.join(m.GetReference() for m in free)))
                continue
            # a part with a cutout through the board (SK6812MINI-E) must also keep clear of SMD pads on the back
            cut = [m for m in free if any(g.GetLayer() == pcbnew.Edge_Cuts for g in m.GraphicalItems())]
            extra = []
            if cut:
                for ref in placed:
                    if byref[ref].IsFlipped():
                        for pad in byref[ref].Pads():
                            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                                c0, r0, c1, r1 = grid.cells(*(v + g for v, g in zip(bbox_mm(pad.GetBoundingBox()),
                                                                                    (-0.5, -0.5, 0.5, 0.5))))
                                extra += [(rr, cc) for rr in range(r0, r1) for cc in range(c0, c1) if not grid.rows[rr][cc]]
                for rr, cc in extra:
                    grid.rows[rr][cc] = 1
            d = cluster(grid, free, r, tft_area if title.startswith(UNCOVERED) else None)
            if extra:                              # free those cells again, but keep the block itself and its gap
                for rr, cc in extra:
                    grid.rows[rr][cc] = 0
                bs = [box(m) for m in free]
                grid.mark(min(q[0] for q in bs) - BLOCK_GAP / 2, min(q[1] for q in bs) - BLOCK_GAP / 2,
                          max(q[2] for q in bs) + BLOCK_GAP / 2, max(q[3] for q in bs) + BLOCK_GAP / 2)
            if d is None:
                problems.append('NO ROOM for block "%s"' % title[:40])
            elif d > 12:
                problems.append('block "%s": %.0f mm from its spot' % (title[:40], d))
        if not free or not name:
            continue
        bs = [box(m) for m in free]
        bx = (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
        size = min(1.0, (bx[2] - bx[0] + 2 * OUTLINE - 0.3) / (0.85 * len(name)))   # names no wider than their block
        size = max(size, 0.8)               # the minimum text height
        tx, ty = bx[0] - OUTLINE + 0.3, bx[1] - OUTLINE - 0.9
        groups.append({'title': title, 'name': name, 'free': free, 'ms': ms, 'size': size, 'cut': {m.GetReference() for m in cut},
                       'name_box': (tx - 0.1, ty - size / 2 - 0.1, tx + 0.8 * size * len(name), ty + size / 2 + 0.1)})

    # spread the parts of each block into the room around it (the packing leaves open areas), then outline each block
    # with a polygon around its parts (and its fixed parts next to them: an ESP32 module, not a far sensor)
    items = []
    gi = {gr['title']: k for k, gr in enumerate(groups)}
    for k, gr in enumerate(groups):
        unc = gr['title'].startswith(UNCOVERED)
        for m in gr['free']:
            items.append({'box': box(m), 'block': k, 'kind': PART, 'gap': gap(m), 'move': True, 'mod': m,
                          'cut': m.GetReference() in gr['cut'], 'uncovered': unc})
        items.append({'box': gr['name_box'], 'block': k, 'kind': NAME, 'move': True, 'group': gr})
    for ref in placed:
        m = byref[ref]
        if m.IsFlipped():
            for pad in m.Pads():
                th = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
                items.append({'box': tuple(bbox_mm(pad.GetBoundingBox())), 'block': -1, 'kind': HOLE if th else BACK_SMD})
        elif ref.startswith('H'):
            items.append({'box': box(m), 'block': -1, 'kind': HOLE})
        else:
            items.append({'box': box(m), 'block': gi.get(block_of.get(ref), -1), 'kind': PART, 'gap': gap(m)})
    items.append({'box': tft_area, 'block': -1, 'kind': KEEPOUT})
    for it, (dx, dy) in zip(items, spread(items)):
        if it.get('mod') is not None and (dx or dy):
            it['mod'].Move(V(dx, dy))
        elif it['kind'] == NAME:
            b = it['group']['name_box']
            it['group']['name_box'] = (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)
    masks, names = {}, [gr['name_box'] for gr in groups]
    for gr in groups:
        own = [box(m) for m in gr['free']]
        fb = (min(b[0] for b in own), min(b[1] for b in own), max(b[2] for b in own), max(b[3] for b in own))
        mine = {m.GetReference() for m in gr['free']}
        for m in gr['ms']:
            ref = m.GetReference()
            if ref in placed and ref not in edge_refs and not m.IsFlipped() and not ref.startswith('H'):
                b = box(m)
                if max(b[0] - fb[2], fb[0] - b[2], b[1] - fb[3], fb[1] - b[3]) < 8:
                    own.append(b)
                    mine.add(ref)
        avoid = [(nb, 0.2) for nb in names]
        avoid += [(box(m), 0.5) for m in byref.values() if m.GetReference() not in mine and not m.IsFlipped()
                  and m.GetReference() not in ties]
        mk = block_mask(own, avoid)
        masks[gr['title']] = mk
        for loop in trace(mk):
            for a, b in zip(loop, loop[1:] + loop[:1]):
                _seg(board, a, b, 0.15)
        nb = gr['name_box']
        silk(board, gr['name'], nb[0] + 0.1, (nb[1] + nb[3]) / 2, size=gr['size'], justify=1)
    import numpy as np
    grid = Grid()                          # what is taken now (for the credits)
    union = np.zeros_like(next(iter(masks.values())))
    for mk in masks.values():
        union |= mk
    coarse = union.reshape(union.shape[0] // 2, 2, union.shape[1] // 2, 2).any(axis=(1, 3))
    for rr in range(coarse.shape[0]):
        grid.rows[rr][:coarse.shape[1]] = bytes(coarse[rr].astype(np.uint8))
    for m in byref.values():
        if not m.IsFlipped():
            x0_, y0_, x1_, y1_ = box(m)
            grid.mark(x0_ - 1, y0_ - 1, x1_ + 1, y1_ + 1)
    for nb in names:
        grid.mark(*nb)

    for ref, host in sorted(ties.items()):
        err = place_tie(board, byref[ref], host)
        if err:
            problems.append(err)
    obstacles = [box(byref[r]) for r in placed if not byref[r].IsFlipped()]
    failed = connection_lines(board, byref, block_of, masks, obstacles, names)
    if failed:
        problems.append('%d connection lines found no path' % failed)

    # servo bank labels, TFT module outline (low parts only under it), credits
    for text, x, y, angle in servo_text:
        silk(board, text, x, y, size=1.0, angle=angle, justify=-1 if angle == 0 else 0)
    for i, ch in enumerate('S+G'):
        silk(board, ch, W - 3.0 - 2.54 * (2 - i), SERVO_Y - 2.4, size=1.0)
    rect(tx + x0, ty + y0, tx + x1, ty + y1, pcbnew.Dwgs_User, 0.15)
    t = pcbnew.PCB_TEXT(board)
    t.SetText('TFT module 2.4" (over this area, on 10 mm standoffs)')
    t.SetPosition(V(tx + (x0 + x1) / 2, ty + y0 + 2))
    t.SetLayer(pcbnew.Dwgs_User)
    board.Add(t)
    credits = ['SensorTestSetup PCB rev %s, %s' % (design.REV, design.DATE), 'Vincent Groenhuis, RaM, University of Twente',
               'layout and routing: Claude Opus 5.5']
    spot = grid.near(50, 10, (W / 2, H - 30))
    if spot:
        for i, line in enumerate(credits):
            silk(board, line, spot[0] + 1, spot[1] + 1.5 + 3 * i, size=1.2 if i == 0 else 1.0, justify=1)
    else:
        for i, line in enumerate(credits):
            silk(board, line, W / 2, H - 20 + 3 * i, size=1.5, layer=pcbnew.B_SilkS).SetMirrored(True)
        problems.append('credits on the back: no room on the front')

    # inner planes
    board.GetDesignSettings().m_TrackMinWidth = mm(MIN_TRACK)
    for lname, net in PLANES.items():
        z = pcbnew.ZONE(board)
        z.SetLayer(board.GetLayerID(lname))
        z.SetNet(nets[net])
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)    # solid to SMD pads (vias), thermal reliefs on THT
        ol = z.Outline()
        ol.NewOutline()
        for x, y in ((0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)):
            ol.Append(mm(x), mm(y))
        board.Add(z)

    # SaveBoard also rewrites the project files from the board's settings, dropping the schematic, ERC and sheet
    # sections: keep the old project file and take only its board section (and the default clearance) from KiCad
    pro, prl = (os.path.splitext(args.out)[0] + e for e in ('.kicad_pro', '.kicad_prl'))
    keep = {f: open(f, encoding='utf-8').read() for f in (pro, prl) if os.path.exists(f)}
    if pro in keep and '"name": "Power"' not in keep[pro] and '"erc"' not in keep[pro]:
        sys.exit('%s looks reset to defaults (KiCad open?): restore it (git checkout) and run again' % pro)
    pcbnew.SaveBoard(args.out, board)
    if pro in keep:
        old, new = json.loads(keep[pro]), json.load(open(pro, encoding='utf-8'))
        old['board'] = new['board']
        ns = old.setdefault('net_settings', {})
        default = next(c for c in ns['classes'] if c.get('name') == 'Default')
        default['clearance'] = 0.15
        ns['classes'] = [default]
        ns['netclass_patterns'] = []
        for i, (cls, (w, clr, vd, vdr, members)) in enumerate(NETCLASSES.items()):
            c = dict(default, name=cls, track_width=w, clearance=clr, via_diameter=vd, via_drill=vdr, priority=i)
            ns['classes'].append(c)
            ns['netclass_patterns'] += [{'netclass': cls, 'pattern': n} for n in sorted(nets) if n.split('/')[-1] in members]
        with open(pro, 'w', encoding='utf-8') as f:
            json.dump(old, f, indent=2)
            f.write('\n')
    if prl in keep:
        open(prl, 'w', encoding='utf-8').write(keep[prl])
    print('%d footprints, %d nets, board %.0f x %.0f mm -> %s' % (len(byref), len(nets), W, H, args.out))
    for p in problems:
        print('  ' + p)


if __name__ == '__main__':
    main()
