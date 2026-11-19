#!/usr/bin/env python3
"""Autoroute the board with Freerouting, then add GND pours on F.Cu and B.Cu and fill all zones.

Run with KiCad's own Python, after gen/pcbgen.py:

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/route.py --freerouting PATH/freerouting-2.5.0.jar --java PATH/java.exe

Freerouting: https://github.com/freerouting/freerouting (the .jar needs Java 21 or later; the native freerouting-cli
2.5.0 for Windows crashes when it starts routing). The board is
exported as Specctra DSN (net classes give the track widths; the inner GND and +3V3 zones are planes), routed, and
the session (.ses) is imported back. Overwrites OfficeDeskSetup.kicad_pcb; keeps the rest of the project file.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import pcbnew

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = 'OfficeDeskSetup'
POURS = {pcbnew.F_Cu: 'GND', pcbnew.In2_Cu: '+3V3', pcbnew.B_Cu: 'GND'}   # added after routing, around the tracks


def mm(v):
    return pcbnew.FromMM(v)


def fix_dsn(dsn, board, planes, edge):
    """KiCad exports every copper layer as a signal layer, and Freerouting then routes through the inner planes too,
    cutting them up. Mark the plane layers 'power' (no routing), and pull the board boundary in so that tracks keep
    the copper-to-edge clearance (Freerouting only keeps its normal clearance to the boundary)."""
    import re
    s = open(dsn, encoding='utf-8').read()
    for layer in planes:
        s = s.replace('(layer %s\n      (type signal)' % layer, '(layer %s\n      (type power)' % layer)
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0, x1, y1 = (pcbnew.ToMM(v) * 1000 for v in (bb.GetLeft(), -bb.GetTop(), bb.GetRight(), -bb.GetBottom()))
    d = edge * 1000                                    # um

    def inset(m):
        nums = [float(v) for v in m.group(2).split()]
        pts = []
        for x, y in zip(nums[0::2], nums[1::2]):
            pts += [x0 + d + (x - x0) * (x1 - x0 - 2 * d) / (x1 - x0), y0 - d + (y - y0) * (y0 - y1 - 2 * d) / (y0 - y1)]
        return m.group(1) + ' '.join('%.1f' % v for v in pts) + ')'

    s, n = re.subn(r'(\(boundary\s+\(path pcb 0\s+)([-\d.\s]+)\)', inset, s, count=1)
    if n != 1:
        sys.exit('no board boundary in the DSN')
    open(dsn, 'w', encoding='utf-8').write(s)


def pour(board, layer, net):
    """A pour over the whole board on one layer, behind the tracks."""
    bb = board.GetBoardEdgesBoundingBox()
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetAssignedPriority(0)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()), (bb.GetRight(), bb.GetBottom()),
                 (bb.GetLeft(), bb.GetBottom())):
        ol.Append(x, y)
    board.Add(z)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--freerouting', required=True, help='freerouting .jar (or a native freerouting-cli)')
    ap.add_argument('--java', default='java', help='java executable for the .jar')
    ap.add_argument('--passes', type=int, default=12)   # later passes only oscillated on this board
    ap.add_argument('--threads', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument('--work', default=os.path.join(HERE, 'gen', 'route'))
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    pcb = os.path.join(HERE, PROJECT + '.kicad_pcb')
    dsn, ses = os.path.join(args.work, PROJECT + '.dsn'), os.path.join(args.work, PROJECT + '.ses')

    board = pcbnew.LoadBoard(pcb)
    for t in list(board.GetTracks()):                  # start from the bare placement
        board.Remove(t)
    planes = [board.GetLayerName(z.GetLayer()) for z in board.Zones() if z.GetLayer() not in POURS]
    for z in list(board.Zones()):                      # earlier pours from route.py
        if z.GetLayer() in POURS:
            board.Remove(z)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit('DSN export failed')
    fix_dsn(dsn, board, planes, pcbnew.ToMM(board.GetDesignSettings().m_CopperEdgeClearance) - 0.15)
    if os.path.exists(ses):
        os.remove(ses)

    t0 = time.time()
    cmd = [args.java, '-jar', args.freerouting] if args.freerouting.endswith('.jar') else [args.freerouting]
    subprocess.run(cmd + ['-de', dsn, '-do', ses, '-mp', str(args.passes), '-mt', str(args.threads)],
                   check=True)
    print('routed in %.0f s' % (time.time() - t0))
    if not os.path.exists(ses) or not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit('SES import failed')

    for layer, net in POURS.items():
        pour(board, layer, net)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    pro, prl = (os.path.join(HERE, PROJECT + e) for e in ('.kicad_pro', '.kicad_prl'))
    keep = {f: open(f, encoding='utf-8').read() for f in (pro, prl) if os.path.exists(f)}
    pcbnew.SaveBoard(pcb, board)
    if pro in keep:                                    # SaveBoard drops the schematic sections: keep them
        old, new = json.loads(keep[pro]), json.load(open(pro, encoding='utf-8'))
        old['board'] = new['board']
        with open(pro, 'w', encoding='utf-8') as f:
            json.dump(old, f, indent=2)
            f.write('\n')
    if prl in keep:
        open(prl, 'w', encoding='utf-8').write(keep[prl])
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    print('%d tracks (%.0f mm), %d vias -> %s' % (len(tracks), sum(pcbnew.ToMM(t.GetLength()) for t in tracks), len(vias), pcb))


if __name__ == '__main__':
    main()
