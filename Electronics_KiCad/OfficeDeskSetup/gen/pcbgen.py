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

W, H = 270.0, 200.0          # board size, mm; the rear edge is y = 0, the front edge (user side) is y = H
GAP = 1.0                    # space between courtyards when packing (routing channels)
GAP_IC = 3.0                 # around parts with 8 or more pads, for their fanout
EDGE = 1.0                   # keep courtyards this far from the board edge
BLOCK_GAP = 5.0              # between the blocks (their outlines are drawn 1 mm around the parts)

# ---------------------------------------------------------------------------------------------------------------
# Edge parts, as rows along an edge: (keys, edge, start, gap, rotation[, pitch]). Parts follow each other from
# `start` (mm along the edge; None: after the previous row on that edge) with `gap` between courtyards, or at a fixed
# `pitch`. A key may be (key, rotation) to override the row's rotation. Rotations put mouths and wire entries outwards.
SCREW = 180                  # Phoenix MKDS horizontal: wire entries at +y, so 180 on the rear edge
EDGE_ROWS = [
    # rear edge (y = 0): USB-C PD and PROG, 12 V jack, power switch, GND banana hole, power terminals, motors
    (['J=USB-C POWER', 'J=USB-C PROG'], 'top', 12, 4, 180),
    (['J=DC 12V'], 'top', 40, 0, 270),
    (['SW=POWER'], 'top', 58, 0, 0),
    (['H=GND banana'], 'top', 77, 0, 0),
    (['J=V_BUS', 'J=V_SERVO', 'J=5V', 'J=3V3', ('J=POWER', 0)], 'top', 91, 1.0, SCREW),
    ([('J=MOTOR A@Terminal', SCREW), 'J=MOTOR A@PH', ('J=MOTOR B@Terminal', SCREW), 'J=MOTOR B@PH'], 'top', 157, 1.5, 0),
    # left edge (x = 0): Qwiic (main bus x2, TCA9548 ch 2-7, ToF bus) and the two pressure sensors
    (['J=Qwiic main 1', 'J=Qwiic main 2'] + ['J=Qwiic ch %d' % i for i in range(2, 8)] + ['J=Qwiic io'], 'left', 12, 1.5, 270),
    (['U=WF100DPZ 10BG S6 DT#1', 'U=WF100DPZ 10BG S6 DT#2'], 'left', 120, 1.5, 0),
    # right edge (x = W): servo banks (SERVO_BANKS), PWM 9-15, Dynamixel, analog inputs, load cell
    (['J=PWM 9-15', 'J=DXL 1', 'J=DXL 2'], 'right', 54, 2.0, 0),
    (['J=AIN 7 (10 bit)'] + ['J=AIN %d (16 bit)' % i for i in range(4)] + ['J=LOAD CELL'], 'right', 100, 0.6, 90),
    # front edge (y = H): toggles, buttons (16 mm pitch: room for caps), pots; ultrasonic and MH module at the right
    (['SW=TOGGLE0', 'SW=TOGGLE1'], 'bottom', 12, 3.0, 0),
    (['SW=BTN%d' % i for i in range(4)], 'bottom', 38, 0, 0, 16),
    (['RV=10k@RK09#%d' % i for i in range(1, 5)], 'bottom', 116, 2.0, 0),
    (['J=HC-SR04', 'J=MH module'], 'bottom', 186, 4.0, 0),
]
# servo outputs: two banks of 4 at the right edge, three 1x4 rows each (GND outside, V+, signal inside); pin 1 of the
# first bank at y = SERVO_Y, the second bank SERVO_BANK further
SERVO_BANKS = [('SERVO 0-3', 'J=SERVO 0-3 SIG', 'J=SERVO 0-3 V+', 'J=SERVO 0-3 GND'),
               ('SERVO 4-7', 'J=SERVO 4-7 SIG', 'J=SERVO 4-7 V+', 'J=SERVO 4-7 GND')]
SERVO_Y, SERVO_BANK = 12.0, 16.0
# TFT module (ZhongJingYuan 2.4" ST7789): pin 1 of its 8-pin socket, and its holes and outline relative to pin 1
# (from the module's footprint in mamri/PCBs/Mamri UI V5); the module lies to the left of the socket
TFT_PIN1 = (152.0, 100.0)
TFT_HOLES = [(-64, -8.61), (-64, 26.39), (-1, -8.61), (-1, 26.39)]
TFT_OUTLINE = (-67.05, -11.66, 2.05, 29.44)
# placed inside (not on an edge, but fixed): key -> (x, y, rotation, side)
FIXED = {
    'U=AS5600-ASOT': (182, 176, 0, 'F'),                      # under the knob
    'BT=18650#1': (118, 72, 0, 'B'),                         # 18650 holders on the back, under the TFT
    'BT=18650#2': (118, 94.5, 0, 'B'),
    'BT=18650#3': (118, 117, 0, 'B'), 
}
HOLES = {'H=M3#1': (4, 4), 'H=M3#2': (W - 4, 4), 'H=M3#3': (4, H - 4), 'H=M3#4': (W - 4, H - 4),
         'H=M3#5': (151, 4), 'H=M3#6': (109, H - 4), 'H=M3#7': (4, 112), 'H=M3#8': (W - 4, 46)}
# net classes: (track width, clearance, via diameter, via drill, nets by their short name)
NETCLASSES = {
    'Power': (1.0, 0.2, 0.8, 0.4, ['VBUS_PD', 'VBUS_PROG', 'CHG_VBUS', 'CHG_PMID', 'CHG_SYS', 'CHG_SW1', 'CHG_SW2',
                                    'CHG_IN1_MID', 'CHG_IN2_MID', 'BAT_P', 'BAT_N', 'BQ_SRN', 'BQ_FET_MID', 'VBUS_SW',
                                    'V_BUS', 'V_SERVO', 'SW_SERVO', 'SW_3V3', 'V_DXL', 'MOTA_P', 'MOTA_N', 'MOTB_P',
                                    'MOTB_N', 'DC_12V']),
    'Supply': (0.5, 0.15, 0.6, 0.3, ['+3V3', '+5V', 'SW_5V', 'CELL1', 'CELL2', 'CELL3', 'HUB_3V3', 'HX_AVDD', 'MH_VCC',
                                     'AHT_VDD', 'CHG_REGN', 'BQ_VDD', 'VBUS_EN_SW']),
}
PLANES = {'In1.Cu': 'GND', 'In2.Cu': '+3V3'}   # signals route on F.Cu and B.Cu (GND pours after routing), with only
                                                # a few short hops through the planes (gen/route.py)
MIN_TRACK = 0.15               # Freerouting necks down to 0.15 mm at fine-pitch pins; JLCPCB does 0.1 mm
# 3D models from LCSC (OfficeDeskSetup.3dshapes) for KiCad footprints: (file, offset, rotation), KiCad axes (y up)
MODELS = {
    'USB_C_Receptacle_HRO_TYPE-C-31-M-12': ('USB-C_SMD-TYPE-C-31-M-12_1.wrl', (0, -1.4, 0), (0, 0, 180)),
    'Potentiometer_Alps_RK09K_Single_Vertical': ('RES-TH_RK09K1130A70.wrl', (4.0, -2.5, 0), (0, 0, 90)),
}

# block (title prefix) -> (x, y, width, height, silkscreen name). Each block is packed into a cluster of that width,
# then placed (5 mm from everything else) at the free spot nearest to the rectangle's centre. The sizes are about those
# of the clusters, so the rectangles form the floor plan: power at the rear, MCUs and buses at the sides, sensors and
# controls at the front, low parts under the TFT module (x 85-154, y 88-130)
FLOORPLAN = [
    # rear: USB-C, 12 V input and power switch, bucks, motors, PCA9685 and V_SERVO by the servo banks
    ('USB-C POWER', 12, 24, 23, 35, 'USB-C PD'),
    ('USB-C PROG', 40, 28, 17, 24, 'USB-C PROG'),
    ('Power switch', 62, 26, 60, 33, 'POWER SWITCH, 12 V IN, V_BUS'),
    ('5 V buck', 127, 22, 20, 23, '5 V'),
    ('Power-good LEDs', 127, 50, 20, 19, 'RAILS'),
    ('3.3 V buck', 152, 22, 31, 24, '3.3 V'),
    ('Motor A', 152, 51, 17, 18, 'ENCODER A'),
    ('Motor B', 174, 51, 17, 18, 'ENCODER B'),
    ('Motor driver', 188, 22, 33, 21, 'MOTOR DRIVER'),
    ('PCA9685', 214, 48, 37, 29, 'SERVO / PWM PCA9685'),
    ('V_SERVO buck', 214, 82, 34, 31, 'V_SERVO'),
    # left column (the holders' pads: x 72-94 and 141-162, y 60-135): USB hub, input selection, ESP 'main', buses
    ('USB hub', 12, 62, 24, 19, 'USB HUB'),
    ('Input selection', 40, 62, 23, 21, 'INPUT SELECT'),
    ("ESP32-C5 'main'", 12, 88, 36, 45, 'ESP32 MAIN'),
    ('Main I2C bus', 52, 88, 20, 17, 'I2C MAIN'),
    ('UART0 header', 50, 110, 22, 24, 'UART0'),
    ('TCA9548A', 12, 138, 39, 34, 'I2C MUX, PRESSURE'),
    ('MCP23017', 56, 150, 59, 28, 'BUTTONS, LEDS MCP23017'),
    # middle, between the holder pads and under the TFT module: charger and pack
    ('Buck-boost charger', 96, 66, 40, 34, 'CHARGER BQ25792'),
    ('3S pack', 96, 104, 40, 30, '3S PACK BQ77915'),
    # front middle: sensors that must stay uncovered, ADC by the pots
    ('IMU', 120, 138, 17, 15, 'IMU'),
    ('AHT20', 140, 138, 31, 17, 'CLIMATE, LIGHT'),
    ('LDR', 100, 163, 15, 11, 'LDR'),
    ('MCP3008', 120, 163, 54, 20, 'ADC MCP3008'),
    # right: ESP 'io', ToF, TFT socket parts, Dynamixel, ADS1115, load cell, IR, HC-SR04, MH
    ("ESP32-C5 'io'", 166, 74, 31, 45, 'ESP32 IO'),
    ('TFT 2.4', 166, 124, 18, 15, 'TFT'),
    ('VL53L7CX', 188, 124, 26, 26, 'TOF'),
    ('V_DXL', 216, 118, 32, 19, 'V_DXL'),
    ('Dynamixel', 216, 142, 29, 16, 'DYNAMIXEL'),
    ('ADS1115', 216, 163, 32, 17, 'ADC ADS1115'),
    ('HX711', 180, 155, 31, 20, 'LOAD CELL'),
    ('IR reflective', 176, 142, 33, 21, 'IR SENSOR'),
    ('HC-SR04', 186, 172, 21, 14, 'HC-SR04'),
    ('MH sensor', 216, 182, 23, 11, 'MH MODULE'),
]


def region(block):
    for prefix, x, y, w, h, name in FLOORPLAN:
        if block.startswith(prefix):
            return (x, y, x + w, y + h), name
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


def occupy(grid, m):
    """Mark a placed part: its box if on top, only its pads (through-hole ones reach the top) if on the back."""
    if not m.IsFlipped():
        x0, y0, x1, y1 = box(m)
        g = gap(m) / 2
        grid.mark(x0 - g, y0 - g, x1 + g, y1 + g)
        return
    for pad in m.Pads():
        x0, y0, x1, y1 = bbox_mm(pad.GetBoundingBox())
        grid.mark(x0 - 1, y0 - 1, x1 + 1, y1 + 1)


def dump(grid, path):
    """The occupancy grid as a PGM picture (white = free), for debugging."""
    with open(os.path.splitext(path)[0] + '.pgm', 'wb') as f:
        f.write(b'P5 %d %d 1\n' % (grid.nx, grid.ny))
        for row in grid.rows:
            f.write(bytes(1 - v for v in row))


def cluster(grid, mods, r):
    """Pack a block's parts into a compact cluster (as wide as region r), then place the cluster with BLOCK_GAP around
    it in the first free spot of r (growing r when needed). Returns the parts outside r (empty or all)."""
    width = max(r[2] - r[0], max(max(b[2] - b[0], b[3] - b[1]) + GAP_IC for b in map(box, mods)))
    local = Grid(width, 400, edge=0)
    pack(local, mods, (0, 0, width, 400))
    bs = [box(m) for m in mods]
    bx = (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
    f = BLOCK_GAP / 2              # fence: half the block gap (parts of two blocks 5 mm apart, outlines 1 mm out)
    w, h = bx[2] - bx[0] + 2 * f, bx[3] - bx[1] + 2 * f + 1.5     # 1.5: the block name above the outline
    spot = grid.near(w, h, ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2))
    if not spot:
        dump(grid, os.path.join(tempfile.gettempdir(), 'pcbgen_grid.png'))
        raise RuntimeError('no room for a %.0f x %.0f block of %s' % (w, h, ' '.join(m.GetReference() for m in mods)))
    inside = r[0] - 1 <= spot[0] and spot[0] + w <= r[2] + 1 and r[1] - 1 <= spot[1] and spot[1] + h <= r[3] + 1
    dx, dy = spot[0] + f - bx[0], spot[1] + f + 1.5 - bx[1]
    for m in mods:
        m.Move(V(dx, dy))
    grid.mark(spot[0], spot[1], spot[0] + w, spot[1] + h)
    return [] if inside else mods


def pack(grid, mods, r):
    """Place footprints (largest first) in the first free spots of region r, growing it until they fit."""
    mods = sorted(mods, key=lambda m: -(lambda b: (b[2] - b[0]) * (b[3] - b[1]))(box(m)))
    moved = []
    for m in mods:
        best = None
        for rot in (0, 90):
            put(m, 0, 0, rot=rot)
            b = box(m)
            w, h = b[2] - b[0] + gap(m), b[3] - b[1] + gap(m)
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
        put(m, x + w / 2, y + h / 2, rot=rot)
        occupy(grid, m)
        if grow:
            moved.append(m)
    return moved


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
        return value.split()[0]
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
    for x, y, p in pts:
        bb = bbox_mm(p.GetBoundingBox())
        if len(across) == 2:
            s = -1 if round(x if vertical else y, 2) == across[0] else 1
        elif side is not None:
            s = side[0] if vertical else side[1]
        else:
            s = -1
        name = short(p.GetNetname())
        if vertical:
            silk(m, name, (bb[0] - 0.5) if s < 0 else (bb[2] + 0.5), y, angle=0, justify=-s)
        else:
            silk(m, name, x, (bb[1] - 0.5) if s < 0 else (bb[3] + 0.5), angle=90, justify=-s)


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

    servo_rows = {resolve(k) for bank in SERVO_BANKS for k in bank[1:]}
    tft_ref = resolve('J=TFT')
    for ref, m in byref.items():
        fpname = m.GetFPID().GetLibItemName().wx_str()
        text = None if ref in servo_rows or ref == tft_ref else part_label(m, m.GetValue(), fpname)
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

    # blocks: packed in their regions, then fenced off (BLOCK_GAP) and outlined on the silkscreen
    edge_refs = {resolve(k[0] if isinstance(k, tuple) else k) for spec in EDGE_ROWS for k in spec[0]} | servo_rows
    def area(ms):
        return sum((b[2] - b[0] + 1) * (b[3] - b[1] + 1) for b in (box(m) for m in ms if m.GetReference() not in placed))
    for title, ms in sorted(blocks.items(), key=lambda kv: -area(kv[1])):     # large blocks first
        r, name = region(title)
        free = [m for m in ms if m.GetReference() not in placed]
        if free:
            for m in free:
                if m.GetReference().startswith('J'):
                    pin_labels(m)
            if r is None:
                problems.append('no region for block "%s": %s' % (title, ' '.join(m.GetReference() for m in free)))
                continue
            over = cluster(grid, free, r)
            if over:
                problems.append('block "%s": outside its region' % title[:40])
        # outline: the cluster, with the block's fixed parts that are next to it (an ESP32 module, not a far sensor)
        if not free or not name:
            continue
        bs = [box(m) for m in free]
        bx = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
        for m in ms:
            if m.GetReference() in placed and m.GetReference() not in edge_refs and not m.IsFlipped()                     and not m.GetReference().startswith('H'):
                b = box(m)
                if max(b[0] - bx[2], bx[0] - b[2], b[1] - bx[3], bx[1] - b[3]) < 8:
                    bx = [min(bx[0], b[0]), min(bx[1], b[1]), max(bx[2], b[2]), max(bx[3], b[3])]
        bx = (bx[0] - 1, bx[1] - 1, bx[2] + 1, bx[3] + 1)
        rect(*bx, pcbnew.F_SilkS, 0.15)
        silk(board, name, bx[0] + 0.5, bx[1] - 1.1, size=1.2, justify=1)

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
