#!/usr/bin/env python3
"""Routed connections per stage of gen/route.py, power and signal nets apart (a Markdown table).

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/routestats.py gen/route [gen/route_pf ...]

For each work directory, the stage boards it holds (stage0 ... stage4, and the final board for 'finish'). A net with
n pads has n - 1 connections; the open ones are KiCad's unconnected items (kicad-cli DRC). Power: the Power and
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
    out = os.path.join(tempfile.gettempdir(), 'routestats.json')
    subprocess.run([CLI, 'pcb', 'drc', '--format', 'json', '-o', out, pcb], stdout=subprocess.DEVNULL, check=False)
    open_ = collections.Counter()
    for item in json.load(open(out, encoding='utf-8'))['unconnected_items']:
        m = re.search(r'\[(.*?)\]', item['items'][0]['description'])
        net = m.group(1).split('/')[-1] if m else ''
        if net and net not in planes:
            open_['power' if net in power else 'signal'] += 1
    return {k: (total[k] - open_[k], total[k]) for k in ('power', 'signal')}


def main():
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
