#!/usr/bin/env python3
"""Rough PCB placement of the SensorTestSetup board, from gen/design.py (no routing).

Run with KiCad's own Python (it needs the pcbnew module):

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/pcbgen.py --symbols DIR --espressif FILE [--fp-espressif DIR]

Writes OfficeDeskSetup.kicad_pcb: board outline, 4 copper layers, mounting holes, every footprint with its nets,
edge parts on their edges and each schematic block packed as a cluster in its region. Footprints carry the schematic
symbol paths, so "Update PCB from Schematic" in KiCad matches them. Overwrites the board file: use it for the first
placement, then move parts by hand in KiCad (and stop running this script).
"""
import argparse
import contextlib
import io
import json
import os
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

W, H = 200.0, 150.0          # board size, mm; the front edge (user side) is y = H
SX, SY = W / 180.0, H / 125.0   # the plan below was drawn for 180 x 125 mm and is scaled to W x H
GAP = 0.6                    # space between courtyards when packing
EDGE = 1.0                   # keep courtyards this far from the board edge

# ---------------------------------------------------------------------------------------------------------------
# Edge parts, as rows along an edge: (refs, edge, start, gap, rotation[, pitch]). Parts follow each other from
# `start` (mm along the edge) with `gap` between courtyards, or at a fixed `pitch`. Rotations put mouths outwards.
EDGE_ROWS = [
    # rear edge (y = 0): USB-C PD and PROG, power screw terminals and header, motors
    (['J1', 'J2'], 'top', 30, 4, 180),
    (['J3', 'J4', 'J5', 'J6', 'J7'], 'top', 59, 1.0, 0),
    (['J13', 'J12', 'J15', 'J14'], 'top', 121, 1.0, 0),
    # left edge (x = 0): Qwiic (main bus x2, TCA9548 ch 2-7, ToF) and the two pressure sensors
    (['J8', 'J9', 'J29', 'J30', 'J31', 'J32', 'J33', 'J34', 'J18'], 'left', 12, 1.5, 270),
    (['U27', 'U28'], 'left', 92, 1.5, 0),
    # right edge (x = W): 8 servo headers at 2.54 mm (a 3 x 8 block), PWM 9-15, Dynamixel, analog inputs
    (['J20', 'J21', 'J22', 'J23', 'J24', 'J25', 'J26', 'J27'], 'right', 14, 0, 90, 2.54),
    (['J28', 'J16', 'J17'], 'right', 38, 2.0, 0),
    (['J37', 'J38', 'J39', 'J40', 'J35', 'J41'], 'right', 84, 0.6, 90),
    # front edge (y = H): power switch, toggles, buttons, pots; ultrasonic, MH module and load cell at the right
    (['SW2', 'SW11', 'SW12'], 'bottom', 10, 2.0, 0),
    (['SW7', 'SW8', 'SW9', 'SW10'], 'bottom', 40, 2.0, 0),
    (['RV1', 'RV2', 'RV3', 'RV4'], 'bottom', 78, 1.5, 0),
    (['J42', 'J36'], 'bottom', 150, 3.0, 0),
]
# placed inside (not on an edge, but fixed)
FIXED = {
    'U14': dict(x=24, y=34, rot=0, side='F'),       # ESP32 'main', left
    'U16': dict(x=152, y=34, rot=0, side='F'),      # ESP32 'io', right
    'J10': dict(x=44, y=88, rot=0, side='F'),       # TFT socket, left of the holders' pads; the module lies to its right
    'U41': dict(x=166, y=110, rot=0, side='F'),     # AS5600 under the knob, front right
    'U22': dict(x=104, y=60, rot=0, side='F'),      # VL53L7CX facing up, clear of the TFT
    'BT1': dict(x=90, y=50, rot=0, side='B'),       # 18650 holders on the back
    'BT2': dict(x=90, y=72.5, rot=0, side='B'),
    'BT3': dict(x=90, y=95, rot=0, side='B'),
}
HOLES = {'H1': (4, 4), 'H2': (W - 4, 4), 'H3': (4, H - 4), 'H4': (W - 4, H - 4)}

# block (title prefix) -> region (x0, y0, x1, y1); parts are packed left to right, top to bottom
REGIONS = [
    ('USB-C POWER', (30, 9, 52, 22)),
    ('USB-C PROG', (52, 9, 64, 22)),
    ('USB hub', (40, 22, 60, 34)),
    ('Input selection', (60, 9, 80, 22)),
    ('Buck-boost charger', (36, 34, 62, 58)),
    ('3S pack', (62, 34, 100, 52)),
    ('Power switch', (80, 11, 112, 30)),
    ('3.3 V buck', (100, 30, 122, 46)),
    ('5 V buck', (112, 11, 124, 30)),
    ('V_SERVO buck', (124, 11, 146, 26)),
    ('V_DXL', (146, 46, 168, 56)),
    ('Power-good LEDs', (100, 46, 116, 56)),
    ('Exposed power', (112, 11, 124, 30)),
    ("ESP32-C5 'main'", (8, 46, 36, 60)),
    ('Main I2C bus', (8, 60, 24, 72)),
    ('TFT', (40, 100, 62, 110)),
    ('UART0 header', (8, 72, 24, 84)),
    ("ESP32-C5 'io'", (140, 46, 168, 56)),
    ('Motor driver', (124, 26, 140, 44)),
    ('Motor A', (124, 44, 140, 52)),
    ('Motor B', (124, 52, 140, 60)),
    ('Dynamixel', (150, 60, 168, 72)),
    ('VL53L7CX', (104, 60, 132, 68)),
    ('MCP23017', (8, 84, 40, 110)),
    ('PCA9685', (142, 18, 166, 46)),
    ('TCA9548A', (8, 18, 16, 46)),
    ('MCP3008', (64, 96, 132, 108)),
    ('LDR', (132, 96, 140, 108)),
    ('MH sensor', (140, 98, 150, 110)),
    ('IR reflective', (150, 98, 168, 110)),
    ('ADS1115', (150, 72, 168, 88)),
    ('IMU', (98, 82, 110, 94)),
    ('AHT20', (112, 82, 132, 94)),
    ('HX711', (132, 72, 150, 96)),
    ('HC-SR04', (64, 66, 96, 76)),
    ('Mounting holes', None),
]


def region(block):
    for prefix, r in REGIONS:
        if block.startswith(prefix):
            return r and (r[0] * SX, r[1] * SY, r[2] * SX, r[3] * SY)
    return None


# ---------------------------------------------------------------------------------------------------------------
def mm(v):
    return pcbnew.FromMM(v)


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
    return m


def box(m):
    """Bounding box of a placed footprint (courtyard and pads: some imported courtyards leave pads out), mm."""
    bb = m.GetBoundingBox(False)
    c = m.GetCourtyard(pcbnew.B_CrtYd if m.IsFlipped() else pcbnew.F_CrtYd)
    if not c.IsEmpty():
        bb.Merge(c.BBox())
    return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def place_row(mods, refs, edge, start, gap, rot, pitch=None):
    pos = start
    for ref in refs:
        m = mods[ref]
        put(m, 0, 0, rot=rot)
        x0, y0, x1, y1 = box(m)
        size = (x1 - x0) if edge in ('top', 'bottom') else (y1 - y0)
        c = pos + (pitch / 2 if pitch else size / 2)
        at = {'top': (c, 0), 'bottom': (c, H), 'left': (0, c), 'right': (W, c)}[edge]
        put(m, at[0], at[1], rot=rot, align=edge)
        pos += pitch if pitch else size + gap


def put(m, x, y, rot=0, side='F', align=None):
    """Place so that the courtyard centre (or the aligned courtyard edge) lands on x/y."""
    m.SetOrientationDegrees(rot)
    if side == 'B' and not m.IsFlipped():
        m.Flip(m.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    m.SetPosition(pcbnew.VECTOR2I(0, 0))
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
    m.SetPosition(pcbnew.VECTOR2I(mm(dx), mm(dy)))


class Grid:
    """Occupancy of the top side at RES mm; parts are placed in the first free spot of a window."""
    RES = 0.5

    def __init__(self):
        self.nx, self.ny = int(W / self.RES) + 1, int(H / self.RES) + 1
        self.rows = [bytearray(self.nx) for _ in range(self.ny)]

    def cells(self, x0, y0, x1, y1):
        r = self.RES
        return (max(0, int(x0 / r)), max(0, int(y0 / r)), min(self.nx, int(x1 / r + 0.999)), min(self.ny, int(y1 / r + 0.999)))

    def mark(self, x0, y0, x1, y1):
        c0, r0, c1, r1 = self.cells(x0, y0, x1, y1)
        for r in range(r0, r1):
            self.rows[r][c0:c1] = b'' * (c1 - c0)

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
        c0, r0, c1, r1 = self.cells(max(x0, EDGE), max(y0, EDGE), min(x1, W - EDGE), min(y1, H - EDGE))
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


def occupy(grid, m):
    """Mark a placed part: its courtyard if on top, only its through-hole pads and holes if on the back."""
    if not m.IsFlipped():
        x0, y0, x1, y1 = box(m)
        grid.mark(x0 - GAP / 2, y0 - GAP / 2, x1 + GAP / 2, y1 + GAP / 2)
        return
    for pad in m.Pads():                 # SMD pads too: through-hole parts on top must clear them
        if True:
            bb = pad.GetBoundingBox()
            grid.mark(pcbnew.ToMM(bb.GetLeft()) - 1, pcbnew.ToMM(bb.GetTop()) - 1,
                      pcbnew.ToMM(bb.GetRight()) + 1, pcbnew.ToMM(bb.GetBottom()) + 1)


def pack(grid, mods, r):
    """Place footprints (largest first) in the first free spots of region r, growing it until they fit."""
    mods = sorted(mods, key=lambda m: -(lambda b: (b[2] - b[0]) * (b[3] - b[1]))(box(m)))
    moved = []
    for m in mods:
        best = None
        for rot in (0, 90):
            put(m, 0, 0, rot=rot)
            b = box(m)
            w, h = b[2] - b[0] + GAP, b[3] - b[1] + GAP
            grow = 0
            while grow <= max(W, H):
                win = (r[0] - grow, r[1] - grow, r[2] + grow, r[3] + grow)
                spot = grid.find(w, h, win)
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
        import tempfile
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

    # outline with 3 mm corner radius
    def seg(a, b):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        s.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    def arc(c, start, mid, end):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(pcbnew.VECTOR2I(mm(start[0]), mm(start[1])), pcbnew.VECTOR2I(mm(mid[0]), mm(mid[1])),
                         pcbnew.VECTOR2I(mm(end[0]), mm(end[1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    R = 3.0
    k = R * (1 - 0.7071)
    seg((R, 0), (W - R, 0)); seg((W, R), (W, H - R)); seg((W - R, H), (R, H)); seg((0, H - R), (0, R))
    arc(None, (W - R, 0), (W - k, k), (W, R))
    arc(None, (W, H - R), (W - k, H - k), (W - R, H))
    arc(None, (R, H), (k, H - k), (0, H - R))
    arc(None, (0, R), (k, k), (R, 0))

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
    mods, blocks = {}, {}
    for p in d.parts:
        ref = p['ref']
        if ref in mods or not p['footprint']:
            continue
        m = load(p['footprint'], esp_fp)
        m.SetReference(ref)
        m.SetValue(p['value'])
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
        mods[ref] = m
        blocks.setdefault(p['block'], []).append(m)

    # fixed and edge parts
    for ref, (x, y) in HOLES.items():
        put(mods[ref], x, y)
    for ref, a in FIXED.items():
        put(mods[ref], a['x'] * SX, a['y'] * SY, a['rot'], a.get('side', 'F'), a.get('align'))
    for refs, edge, start, *rest in EDGE_ROWS:
        place_row(mods, refs, edge, start * (SX if edge in ('top', 'bottom') else SY), *rest)
    placed = set(HOLES) | set(FIXED) | {r for spec in EDGE_ROWS for r in spec[0]}
    grid = Grid()
    problems = []
    tops = [r for r in sorted(placed) if not mods[r].IsFlipped()]
    for i, a in enumerate(tops):                   # fixed parts must not collide with each other
        for b in tops[i + 1:]:
            p, q = box(mods[a]), box(mods[b])
            if p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3] and not (a[:2] == b[:2] == 'J2' and a < 'J28' and b < 'J28'):
                problems.append('fixed parts %s and %s overlap' % (a, b))
    for ref in placed:
        occupy(grid, mods[ref])

    # blocks
    for title, ms in blocks.items():
        r = region(title)
        ms = [m for m in ms if m.GetReference() not in placed]
        if not ms:
            continue
        if r is None:
            problems.append('no region for block "%s": %s' % (title, ' '.join(m.GetReference() for m in ms)))
            continue
        over = pack(grid, ms, r)
        if over:
            problems.append('block "%s": %d parts outside its region: %s' % (title[:40], len(over), ' '.join(m.GetReference() for m in over)))

    # GND planes on In1 and B.Cu
    for layer in (pcbnew.In1_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(nets['GND'])
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in ((0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)):
            ol.Append(mm(x), mm(y))
        board.Add(z)

    # board text
    t = pcbnew.PCB_TEXT(board)
    t.SetText('SensorTestSetup PCB rev %s  -  RaM, University of Twente' % design.REV)
    t.SetPosition(pcbnew.VECTOR2I(mm(W / 2), mm(H - 26)))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(mm(1.5), mm(1.5)))
    board.Add(t)
    # TFT module outline (the module lies over this area: low parts only)
    tx, ty = FIXED['J10']['x'] * SX, FIXED['J10']['y'] * SY
    tft = ((tx, ty - 22), (tx + 70, ty - 22), (tx + 70, ty + 22), (tx, ty + 22))
    for a, b in zip(tft, tft[1:] + tft[:1]):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        s.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        s.SetLayer(pcbnew.Dwgs_User)
        s.SetWidth(mm(0.15))
        board.Add(s)
    t = pcbnew.PCB_TEXT(board)
    t.SetText('TFT module (2.4", over this area)')
    t.SetPosition(pcbnew.VECTOR2I(mm(tx + 35), mm(ty - 20)))
    t.SetLayer(pcbnew.Dwgs_User)
    board.Add(t)

    # SaveBoard also rewrites the project files from the board's settings, dropping the schematic, ERC and sheet
    # sections: keep the old project file and take only its board section (and the default clearance) from KiCad
    pro, prl = (os.path.splitext(args.out)[0] + e for e in ('.kicad_pro', '.kicad_prl'))
    keep = {f: open(f, encoding='utf-8').read() for f in (pro, prl) if os.path.exists(f)}
    pcbnew.SaveBoard(args.out, board)
    if pro in keep:
        old, new = json.loads(keep[pro]), json.load(open(pro, encoding='utf-8'))
        old['board'] = new['board']
        for c in old.get('net_settings', {}).get('classes', []):
            if c.get('name') == 'Default':
                c['clearance'] = 0.15
        with open(pro, 'w', encoding='utf-8') as f:
            json.dump(old, f, indent=2)
            f.write('\n')
    if prl in keep:
        open(prl, 'w', encoding='utf-8').write(keep[prl])
    print('%d footprints, %d nets, board %.0f x %.0f mm -> %s' % (len(mods), len(nets), W, H, args.out))
    for p in problems:
        print('  ' + p)


if __name__ == '__main__':
    main()
