#!/usr/bin/env python3
"""The open (unrouted) connections of the power nets on the board, per net: what KiCad's ratsnest shows for them.

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/openpower.py [board.kicad_pcb]

Power: the Pack, Power and Supply net classes; the plane nets (GND, +3V3) are left out, the planes connect them.
In pcbnew these classes have their own colours (orange, red, yellow), so their ratsnest lines stand out; to see only
them, hide the ratsnest of the Default class (Appearance panel, Nets tab, its eye icon).
"""
import collections
import json
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(os.path.dirname(sys.executable), 'kicad-cli.exe' if os.name == 'nt' else 'kicad-cli')


def main():
    pcb = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, route.PROJECT + '.kicad_pcb')
    board = pcbnew.LoadBoard(pcb)
    power = route.power_nets(board)
    for p in board.GetPads():                          # a copy with only the power nets: the DRC report lists at
        if p.GetNetCode() > 0 and p.GetNetname().split('/')[-1] not in power:   # most about 500 unconnected items
            p.SetNetCode(0)
    for t in [t for t in board.GetTracks() if t.GetNetname().split('/')[-1] not in power]:
        board.Remove(t)
    tmp = os.path.join(tempfile.gettempdir(), 'openpower.kicad_pcb')
    pcbnew.SaveBoard(tmp, board)
    out = os.path.join(tempfile.gettempdir(), 'openpower.json')
    subprocess.run([CLI, 'pcb', 'drc', '--format', 'json', '-o', out, tmp], stdout=subprocess.DEVNULL, check=False)
    nets = collections.defaultdict(list)
    for u in json.load(open(out, encoding='utf-8'))['unconnected_items']:
        ends = []
        for it in u['items']:
            d = it['description']
            m = re.search(r'\[(.*?)\]', d)
            net = m.group(1).split('/')[-1] if m else '?'
            what = re.sub(r'\s*\[.*?\]', '', d).replace(' on F.Cu', '').replace(' on B.Cu', '')
            ends.append('%s (%.1f, %.1f)' % (what, it['pos']['x'], it['pos']['y']))
        nets[net].append(' - '.join(ends))
    total = sum(len(v) for v in nets.values())
    print('%d open power connections in %d nets (%s)' % (total, len(nets), os.path.basename(pcb)))
    for net in sorted(nets, key=lambda n: (-len(nets[n]), n)):
        print('\n%s: %d' % (net, len(nets[net])))
        for line in nets[net]:
            print('  ' + line)


if __name__ == '__main__':
    main()
