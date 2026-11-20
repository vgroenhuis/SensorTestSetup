#!/usr/bin/env python3
"""Routed connections per stage of gen/route.py, power and signal nets apart (a Markdown table).

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/routestats.py gen/route [gen/route_pf ...]

For each work directory, the stage boards it holds (stage0 ... stage4, and the final board for 'finish'). A net with
n pads has n - 1 connections; the open ones are KiCad's unconnected items (kicad-cli DRC, on a copy of the board with only
power or only signal nets connected: the DRC report stops listing them at about 500). Power: the Power and
Supply net classes; the plane nets (GND, +3V3) are left out, the planes connect them.
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
STAGES = [('stage0', 'stage 0: power alone'), ('stage1', 'stage 1: all, outer layers'),
          ('stage2', 'stage 2: planes open'), ('stage3', 'stage 3: power narrow'),
          ('stage3p', 'prune: plane rules, cleanup'), ('stage4', 'stage 4: leftovers, outer layers')]
CLI = os.path.join(os.path.dirname(sys.executable), 'kicad-cli.exe' if os.name == 'nt' else 'kicad-cli')


def open_count(pcb, kind):
    """Unconnected items of `kind` ('power' or 'signal') on a copy of the board where only those nets keep their
    connections: KiCad's DRC report stops listing unconnected items at about 500. Run in its own process (a second
    board in one process comes back as untyped SWIG objects)."""
    r = subprocess.run([sys.executable, '-u', os.path.abspath(__file__), '--count', kind, pcb], capture_output=True,
                       text=True, errors='replace')
    m = re.search(r'^open (\d+)$', r.stdout, re.M)
    if not m:
        sys.exit('count failed (%s): %s' % (r.returncode, (r.stdout + r.stderr)[-1500:]))
    return int(m.group(1))


def count(kind, pcb):
    board = pcbnew.LoadBoard(pcb)
    power = route.power_nets(board)
    planes = {z.GetNetname().split('/')[-1] for z in route.zones(board)}
    keep = (lambda n: n in power) if kind == 'power' else (lambda n: n not in power and n not in planes)
    for p in board.GetPads():
        if p.GetNetCode() > 0 and not keep(p.GetNetname().split('/')[-1]):
            p.SetNetCode(0)
    gone = [t for t in board.GetTracks() if not keep(t.GetNetname().split('/')[-1])]
    for t in gone:
        board.Remove(t)
    tmp = os.path.join(tempfile.gettempdir(), 'routestats_%s.kicad_pcb' % kind)
    pcbnew.SaveBoard(tmp, board)
    out = os.path.join(tempfile.gettempdir(), 'routestats_%s.json' % kind)
    subprocess.run([CLI, 'pcb', 'drc', '--format', 'json', '-o', out, tmp], stdout=subprocess.DEVNULL, check=False)
    n = len(json.load(open(out, encoding='utf-8'))['unconnected_items'])
    if n >= 490:
        print('warning: %d unconnected items, the DRC report may be cut off' % n, file=sys.stderr)
    print('open %d' % n)


def stats(pcb):
    board = pcbnew.LoadBoard(pcb)
    power = route.power_nets(board)
    planes = {z.GetNetname().split('/')[-1] for z in route.zones(board)}
    pads = collections.Counter(p.GetNetname().split('/')[-1] for p in board.GetPads()
                               if p.GetNetname() and not p.GetNetname().startswith('unconnected'))
    total = collections.Counter()
    for net, n in pads.items():
        if net not in planes and n > 1:
            total['power' if net in power else 'signal'] += n - 1
    open_ = {k: open_count(pcb, k) for k in ('power', 'signal')}
    return {k: (total[k] - open_[k], total[k]) for k in ('power', 'signal')}


def main():
    if sys.argv[1] == '--count':
        count(sys.argv[2], sys.argv[3])
        return
    for work in sys.argv[1:]:
        print('\n%s\n' % work)
        print('| stage | power routed | signal routed | open (power + signal) |')
        print('|---|---|---|---|')
        rows = [(os.path.join(work, f + '.kicad_pcb'), label) for f, label in STAGES]
        rows.append((os.path.join(HERE, route.PROJECT + '.kicad_pcb') if len(sys.argv) == 2 or work == sys.argv[-1]
                     else '', 'finish: cleanup, pours'))
        for pcb, label in rows:
            if not pcb or not os.path.exists(pcb):
                continue
            s = stats(pcb)
            (pr, pt), (sr, st) = s['power'], s['signal']
            print('| %s | %d / %d | %d / %d | %d (%d + %d) |' % (label, pr, pt, sr, st, pt - pr + st - sr, pt - pr, st - sr),
                  flush=True)


if __name__ == '__main__':
    main()
