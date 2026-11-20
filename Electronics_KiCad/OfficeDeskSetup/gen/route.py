#!/usr/bin/env python3
"""Autoroute the board with Freerouting, then add GND pours on F.Cu and B.Cu and fill all zones.

Run with KiCad's own Python, after gen/pcbgen.py:

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/route.py --freerouting PATH/freerouting-2.5.0.jar --java PATH/java.exe

Freerouting: https://github.com/freerouting/freerouting (the .jar needs Java 25; the native freerouting-cli 2.5.0 for
Windows crashes when it starts routing). Freerouting does not connect pads to the planes itself, so every SMD pad on
GND or +3V3 first gets a via to its plane (gen/planevias.py). Then two stages:

0. Power first (default; --no-power-first skips it): the power nets (Power and Supply classes, not the plane nets) alone, on F.Cu and B.Cu; their
   tracks are locked for the next stages.
1. Signals on F.Cu and B.Cu only: the inner layers (GND and +3V3 planes from pcbgen.py) are marked as plane layers in
   the Specctra DSN, so Freerouting connects to them with vias but does not route through them.
2. The tracks of stage 1 are locked and Freerouting routes what is left with the inner layers open. Its tracks
   through the planes are kept only while the planes stay sound:
   - at most --max-plane mm (50) of plane track per net;
   - plane tracks closer together than --slot-gap mm (2) leave no plane between them and count as one slot, at most
     --max-plane mm long in total;
   - each plane stays one piece: filled with a minimum width of --neck mm (2, so a narrow neck counts as a cut), it
     has no more islands over 25 mm2 than after stage 1.
   While a rule is broken, the worst net loses its stage-2 tracks; then each removed net is tried back on its own.

--reuse imports the .ses files of an earlier run from the work directory instead of routing again (same placement
only), e.g. to try another --neck.

No GND stitching vias: they would be in the way of finishing the routing by hand. Add them once everything is
routed, with gen/planevias.py (or --stitch here if Freerouting routes everything). Net classes give the track widths.
Overwrites OfficeDeskSetup.kicad_pcb; the project file is left as it was.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import time

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import planevias      # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = 'OfficeDeskSetup'
POURS = {pcbnew.F_Cu: 'GND', pcbnew.B_Cu: 'GND'}   # added after routing, around the tracks


def mm(v):
    return pcbnew.FromMM(v)


def fix_dsn(dsn, board, planes, edge):
    """KiCad exports every copper layer as a signal layer, and Freerouting then routes through the inner planes too.
    Mark the given layers 'power' (no routing), and pull the board boundary in so that tracks keep the copper-to-edge
    clearance (Freerouting only keeps its normal clearance to the boundary)."""
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
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)    # solid to SMD pads, thermal reliefs on THT
    z.SetAssignedPriority(0)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()), (bb.GetRight(), bb.GetBottom()),
                 (bb.GetLeft(), bb.GetBottom())):
        ol.Append(x, y)
    board.Add(z)


def only_nets(dsn, keep):
    """Leave Freerouting only the nets for which keep(short name) is true: the others keep one pin in the DSN, so their
    pads are still obstacles but there is nothing to connect."""
    s = open(dsn, encoding='utf-8').read()
    n = [0, 0]

    def one(m):
        name = m.group(1).strip('"').split('/')[-1]
        pins = m.group(2).split()
        if keep(name) or len(pins) < 2:
            n[0] += 1
            return m.group(0)
        n[1] += 1
        return '(net %s\n      (pins %s)' % (m.group(1), pins[0])
    s = re.sub(r'\(net ("[^"]*"|\S+)\s+\(pins ([^)]*)\)', one, s)
    open(dsn, 'w', encoding='utf-8').write(s)
    print('DSN: %d nets to route, %d left out' % tuple(n), flush=True)


def power_nets(board):
    """Short names of the Power and Supply net class nets, without the plane nets."""
    ns = board.GetDesignSettings().m_NetSettings
    planes = {z.GetNetname().split('/')[-1] for z in zones(board)}
    out = set()
    for net in board.GetNetsByName().keys():
        name = str(net)
        cls = ns.GetEffectiveNetClass(name).GetName()
        if any(c in cls for c in ('Power', 'Supply')) and name.split('/')[-1] not in planes:
            out.add(name.split('/')[-1])
    return out


def route(board, args, name, closed, passes, keep=None):
    """Export the board, run Freerouting on it and import the result. `closed`: layers it may not route on. `keep`:
    route only the nets whose short name it accepts."""
    dsn, ses = (os.path.join(args.work, name + e) for e in ('.dsn', '.ses'))
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit('DSN export failed')
    fix_dsn(dsn, board, closed, pcbnew.ToMM(board.GetDesignSettings().m_CopperEdgeClearance) - 0.15)
    if keep:
        only_nets(dsn, keep)
    if not (args.reuse and os.path.exists(ses)):
        if os.path.exists(ses):
            os.remove(ses)
        t0 = time.time()
        cmd = [args.java, '-jar', args.freerouting] if args.freerouting.endswith('.jar') else [args.freerouting]
        subprocess.run(cmd + ['-de', dsn, '-do', ses, '-mp', str(passes), '-mt', str(args.threads)] + args.fr, check=True)
        print('%s: routed in %.0f s' % (name, time.time() - t0), flush=True)
    if not os.path.exists(ses) or not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit('SES import failed')


def zones(board):
    """board.Zones() sometimes yields untyped SWIG objects after an SES import; GetArea() does not."""
    return [board.GetArea(i) for i in range(board.GetAreaCount())]


def islands(board, planes, neck):
    """Plane pieces over 25 mm2 per plane layer, filled with minimum width `neck` mm and no island removal."""
    zs = [z for z in zones(board) if z.GetLayer() in planes]
    saved = [(z.GetMinThickness(), z.GetIslandRemovalMode()) for z in zs]
    for z in zs:
        z.SetMinThickness(mm(neck))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    pcbnew.ZONE_FILLER(board).Fill(zs)
    n = {}
    for z in zs:
        p = z.GetFilledPolysList(z.GetLayer())
        n[z.GetLayer()] = sum(1 for i in range(p.OutlineCount()) if p.Outline(i).Area() / 1e12 > 25)
    for z, (t, mode) in zip(zs, saved):
        z.SetMinThickness(t)
        z.SetIslandRemovalMode(mode)
    return n


def key(t):
    s, e = t.GetStart(), t.GetEnd()
    return t.Type(), t.GetLayer(), t.GetNetname(), s.x, s.y, e.x, e.y


def save(board, path, pro):
    """SaveBoard with the project's own .kicad_pro next to it: SaveBoard rewrites that file and drops the schematic
    sections, and a board loaded without it falls back to default rules and net classes. Routing changes no
    settings, so the project file is put back as it was."""
    base = os.path.splitext(path)[0]
    keep = {f: open(f, encoding='utf-8').read() for f in (pro, base + '.kicad_prl') if os.path.exists(f)}
    if '"name": "Power"' not in keep[pro]:     # a project file reset to KiCad's defaults (it happened once)
        sys.exit('%s has lost its net classes: restore it (git checkout) and run again' % pro)
    open(base + '.kicad_pro', 'w', encoding='utf-8').write(keep[pro])
    pcbnew.SaveBoard(path, board)
    open(base + '.kicad_pro', 'w', encoding='utf-8').write(keep[pro])
    if base + '.kicad_prl' in keep:
        open(base + '.kicad_prl', 'w', encoding='utf-8').write(keep[base + '.kicad_prl'])


def cleanup(board, plane_nets, keep):
    """Remove vias that reach their net on one layer only, and tracks with an end that touches nothing, until none
    are left (as KiCad's Cleanup Tracks & Vias). Plane nets are left alone: the planes connect them. Removed items
    go into the list `keep` (freeing them upsets pcbnew's SWIG types)."""
    removed = 0
    while True:
        items = [t for t in board.GetTracks() if t.GetNetname() not in plane_nets]
        pads, by_net = collections.defaultdict(list), collections.defaultdict(list)
        for p in board.GetPads():
            pads[p.GetNetCode()].append(p)
        for t in items:
            by_net[t.GetNetCode()].append(t)

        def touches(pos, layer, net, skip):
            for t in by_net[net]:
                if t is skip or not t.IsOnLayer(layer):
                    continue
                if t.Type() == pcbnew.PCB_VIA_T:
                    if (t.GetPosition() - pos).EuclideanNorm() <= t.GetWidth(layer) / 2:
                        return True
                elif min((t.GetStart() - pos).EuclideanNorm(), (t.GetEnd() - pos).EuclideanNorm()) <= t.GetWidth() / 2:
                    return True
            return any(p.IsOnLayer(layer) and p.HitTest(pos) for p in pads[net])

        gone = []
        for t in items:
            if t.Type() == pcbnew.PCB_VIA_T:
                if sum(touches(t.GetPosition(), l, t.GetNetCode(), t) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)) < 2:
                    gone.append(t)
            elif t.GetStart() == t.GetEnd() or not all(touches(e, t.GetLayer(), t.GetNetCode(), t)
                                                       for e in (t.GetStart(), t.GetEnd())):   # zero length: a DRC crossing
                gone.append(t)
        if not gone:
            return removed
        for t in gone:
            board.Remove(t)
        keep.extend(gone)
        removed += len(gone)


def pro(pcb):
    return os.path.splitext(pcb)[0] + '.kicad_pro'


def stage1(args, pcb):
    board = pcbnew.LoadBoard(pcb)
    refs = list(board.GetTracks())                     # removed items stay referenced (SWIG types, see finish)
    for t in refs:                                     # start from the bare placement
        board.Remove(t)
    for z in zones(board):                             # earlier pours from route.py
        if z.GetLayer() in POURS:
            refs.append(z)
            board.Remove(z)
    planes = sorted({z.GetLayer() for z in zones(board)})
    vias, missed = planevias.fanout(board, {z.GetNetname() for z in zones(board)})
    print('plane vias: %d; SMD pads without one: %s' % (vias, ' '.join(missed) or 'none'), flush=True)
    if args.stubs:                                     # power pins too fine for a full-width track
        power = power_nets(board)
        ns = board.GetDesignSettings().m_NetSettings
        widths = {code: pcbnew.ToMM(ns.GetEffectiveNetClass(n.GetNetname()).GetTrackWidth())
                  for code, n in board.GetNetsByNetcode().items() if n.GetNetname().split('/')[-1] in power}
        n, missed = planevias.stubs(board, widths)
        print('narrowing stubs: %d; fine-pitch power pads without one: %s' % (n, ' '.join(missed) or 'none'), flush=True)
    closed = [board.GetLayerName(l) for l in planes]
    if args.power_first:                               # stage 0: the power nets alone, then locked
        power = power_nets(board)
        route(board, args, PROJECT + '_0', closed, args.passes0, keep=lambda n: n in power)
        for t in board.GetTracks():
            t.SetLocked(True)
        save(board, os.path.join(args.work, 'stage0.kicad_pcb'), pro(pcb))
        if args.stage0_only:
            return
    route(board, args, PROJECT, closed, args.passes)
    for t in board.GetTracks():
        t.SetLocked(True)
    json.dump({'planes': planes, 'tracks': [key(t) for t in board.GetTracks()], 'islands': islands(board, planes, args.neck)},
              open(os.path.join(args.work, 'stage1.json'), 'w'))
    save(board, os.path.join(args.work, 'stage1.kicad_pcb'), pro(pcb))


def stage2(args, pcb):
    board = pcbnew.LoadBoard(os.path.join(args.work, 'stage1.kicad_pcb'))
    route(board, args, PROJECT + '_2', [], args.passes2)
    save(board, os.path.join(args.work, 'stage2.kicad_pcb'), pro(pcb))


def stage3(args, pcb):
    """The power nets that are left, at a narrow width: Freerouting has one width per net class and cannot neck a
    1 mm track down to a 0.4 mm pitch pin. finish() widens them again where there is room."""
    board = pcbnew.LoadBoard(os.path.join(args.work, 'stage2.kicad_pcb'))
    for t in board.GetTracks():
        t.SetLocked(True)
    ns = board.GetDesignSettings().m_NetSettings
    power = ns.GetNetClassByName('Power')
    power.SetTrackWidth(mm(args.power_narrow))
    if args.power_clearance:
        power.SetClearance(mm(args.power_clearance))
    ns.RecomputeEffectiveNetclasses()
    route(board, args, PROJECT + '_3', [], args.passes3)
    save(board, os.path.join(args.work, 'stage3.kicad_pcb'), pro(pcb))


def widen(board, keep, clr=0.2):
    """Power tracks narrower than their class width get as wide as their surroundings allow (in steps), except the
    last 0.8 mm at a pad, which keeps the width that fits the pin. Outer layers only (plane tracks stay narrow).
    Returns (tracks widened, tracks still narrow)."""
    ns = board.GetDesignSettings().m_NetSettings
    pads = collections.defaultdict(list)
    for p in board.GetPads():
        pads[p.GetNetCode()].append(p)
    narrow = []
    for t in list(board.GetTracks()):
        if t.Type() != pcbnew.PCB_TRACE_T or t.GetLayer() not in planevias.OUTER:
            continue
        full = ns.GetEffectiveNetClass(t.GetNetname()).GetTrackWidth()
        if 'Power' not in ns.GetEffectiveNetClass(t.GetNetname()).GetName() or t.GetWidth() >= full:
            continue
        for end, other in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            length = (other - end).EuclideanNorm()
            if length > mm(1.6) and any(p.IsOnLayer(t.GetLayer()) and p.HitTest(end) for p in pads[t.GetNetCode()]):
                cut = end + (other - end).Resize(mm(0.8))
                stub = pcbnew.PCB_TRACK(board)
                stub.SetStart(end)
                stub.SetEnd(cut)
                stub.SetWidth(t.GetWidth())
                stub.SetLayer(t.GetLayer())
                stub.SetNet(t.GetNet())
                board.Add(stub)
                keep.append(stub)
                if end == t.GetStart():
                    t.SetStart(cut)
                else:
                    t.SetEnd(cut)
        narrow.append((t, full))
    cu = planevias.Copper(board)
    done = 0
    for t, full in narrow:
        a, b = t.GetStart(), t.GetEnd()
        x, y = pcbnew.ToMM((a.x + b.x) // 2), pcbnew.ToMM((a.y + b.y) // 2)
        r = pcbnew.ToMM((b - a).EuclideanNorm()) / 2
        for w in (pcbnew.ToMM(full), 0.8, 0.6, 0.5):
            if mm(w) <= t.GetWidth():
                break
            shape = pcbnew.SHAPE_SEGMENT(a, b, mm(w))
            if cu.free(shape, x, y, r + w, t.GetNetCode(), (t.GetLayer(),), clr, None, holes=False):
                t.SetWidth(mm(w))
                cu.keep.append(shape)
                cu.add(shape, t.GetNetCode(), (t.GetLayer(),))
                done += 1
                break
    return done, len(narrow) - done


def prune(args, pcb):
    """Widen the power tracks and keep stage 2/3 tracks in the planes only while the planes stay sound."""
    board = pcbnew.LoadBoard(os.path.join(args.work, 'stage3.kicad_pcb'))
    refs = []                       # removed tracks stay referenced: freeing them upsets pcbnew's SWIG types
    print('power tracks widened: %d, still narrow: %d' % widen(board, refs))
    s1 = json.load(open(os.path.join(args.work, 'stage1.json')))
    planes, base = s1['planes'], {int(k): v for k, v in s1['islands'].items()}
    old = {tuple(k) for k in s1['tracks']}
    new = collections.defaultdict(list)
    for t in board.GetTracks():
        if tuple(key(t)) not in old:
            new[t.GetNetname()].append(t)

    def in_plane(net, layer):
        return sum(pcbnew.ToMM(t.GetLength()) for t in new[net] if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == layer)

    def slots(layer):
        """Plane tracks closer than --slot-gap mm leave no plane between them: one slot. [(length mm, {net: mm})]"""
        ts = [(n, t, t.GetEffectiveShape(layer)) for n in new for t in new[n]
              if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == layer]
        group = list(range(len(ts)))

        def root(i):
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                if root(i) != root(j) and ts[i][2].Collide(ts[j][2], mm(args.slot_gap)):
                    group[root(i)] = root(j)
        found = collections.defaultdict(lambda: collections.Counter())
        for i, (n, t, _) in enumerate(ts):
            found[root(i)][n] += pcbnew.ToMM(t.GetLength())
        return [(sum(c.values()), c) for c in found.values()]

    def problem():
        """The net to take out next (and why), or None when the planes are fine."""
        for n in new:
            if sum(in_plane(n, l) for l in planes) > args.max_plane:
                return n, 'over %g mm' % args.max_plane
        for l in planes:
            for length, nets in slots(l):
                if length > args.max_plane:
                    return nets.most_common(1)[0][0], 'slot of %.0f mm in %s' % (length, board.GetLayerName(l))
        now = islands(board, planes, args.neck)
        for l in planes:
            if now[l] > base[l]:
                n = max(new, key=lambda n: in_plane(n, l))
                if in_plane(n, l):
                    return n, 'cuts %s' % board.GetLayerName(l)
                print('plane %s is cut, but not by stage 2 tracks' % board.GetLayerName(l))
        return None

    out, why = {}, {}
    while new:                      # take out the worst net until the planes are fine
        p = problem()
        if not p:
            break
        net, why[net] = p
        for t in new[net]:
            board.Remove(t)
        out[net] = new.pop(net)
    for net in sorted(out, key=lambda n: sum(pcbnew.ToMM(t.GetLength()) for t in out[n])):
        new[net] = out.pop(net)     # then try each of them back on its own, shortest first
        for t in new[net]:
            board.Add(t)
        if problem():
            for t in new[net]:
                board.Remove(t)
            out[net] = new.pop(net)
    dropped = ['%s (%.0f mm, %s)' % (n.split('/')[-1], sum(pcbnew.ToMM(t.GetLength()) for t in ts if t.GetLayer() in planes), why[n])
               for n, ts in sorted(out.items())]
    kept = ['%s (%.0f mm)' % (n.split('/')[-1], sum(in_plane(n, l) for l in planes))
            for n in sorted(new) if any(in_plane(n, l) for l in planes)]
    print('plane pieces (over 25 mm2, %.1f mm neck) after stage 1: %s' % (args.neck, {board.GetLayerName(l): v for l, v in base.items()}))
    print('stage 2: %d nets with tracks in the planes: %s' % (len(kept), ', '.join(kept)))
    print('stage 2: %d nets taken out again: %s' % (len(dropped), ', '.join(dropped)))
    print('loose vias and track stubs removed: %d' % cleanup(board, {z.GetNetname() for z in zones(board)}, refs))
    for t in board.GetTracks():
        t.SetLocked(True)
    save(board, os.path.join(args.work, 'stage3p.kicad_pcb'), pro(pcb))


def stage4(args, pcb):
    """What the plane rules took out, and whatever else is left, on the outer layers only (planes closed)."""
    board = pcbnew.LoadBoard(os.path.join(args.work, 'stage3p.kicad_pcb'))
    planes = json.load(open(os.path.join(args.work, 'stage1.json')))['planes']
    route(board, args, PROJECT + '_4', [board.GetLayerName(l) for l in planes], args.passes4)
    save(board, os.path.join(args.work, 'stage4.kicad_pcb'), pro(pcb))


def finish(args, pcb):
    """Pour, fill and save."""
    board = pcbnew.LoadBoard(os.path.join(args.work, 'stage4.kicad_pcb'))
    refs = []
    print('loose vias and track stubs removed: %d' % cleanup(board, {z.GetNetname() for z in zones(board)}, refs))
    for t in board.GetTracks():
        t.SetLocked(False)
    if args.stitch:
        print('GND stitching vias: %d' % planevias.stitch(board, 'GND'))
    for layer, net in POURS.items():
        pour(board, layer, net)
    pcbnew.ZONE_FILLER(board).Fill(zones(board))
    save(board, pcb, pro(pcb))
    # refill with KiCad itself: pcbnew's ZONE_FILLER from Python left stale fill around a few vias
    keep = {f: open(f, encoding='utf-8').read() for f in (pro(pcb), os.path.splitext(pcb)[0] + '.kicad_prl') if os.path.exists(f)}
    cli = os.path.join(os.path.dirname(sys.executable), 'kicad-cli.exe' if os.name == 'nt' else 'kicad-cli')
    subprocess.run([cli, 'pcb', 'drc', '--refill-zones', '--save-board', '-o', os.path.join(args.work, 'drc.rpt'), pcb],
                   check=True, stdout=subprocess.DEVNULL)
    for f, text in keep.items():
        open(f, 'w', encoding='utf-8').write(text)
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    print('%d tracks (%.0f mm), %d vias -> %s' % (len(tracks), sum(pcbnew.ToMM(t.GetLength()) for t in tracks), len(vias), pcb))


STEPS = ('stage1', 'stage2', 'stage3', 'prune', 'stage4', 'finish')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--freerouting', required=True, help='freerouting .jar (or a native freerouting-cli)')
    ap.add_argument('--java', default='java', help='java executable for the .jar')
    # Freerouting 2.5.0 with more than one pass reports the best pass but saves a later, worse board (a power-only
    # test: 68 open power connections after 4 passes, 20 after 1, same reported score); use 1 pass with 2.5.0.
    # The 2.5.1 SNAPSHOT of 2026-11-19 saves the best pass and imports pad clearances correctly.
    ap.add_argument('--power-first', action=argparse.BooleanOptionalAction, default=True,
                    help='stage 0: route the power nets alone first (default; 33 open against 37 on rev 0.2)')
    ap.add_argument('--passes0', type=int, default=1, help='stage 0 (power nets alone)')
    ap.add_argument('--stubs', action=argparse.BooleanOptionalAction, default=True,
                    help='narrowing stubs on power pins too fine for a full-width track (planevias.stubs)')
    ap.add_argument('--stage0-only', action='store_true',
                    help='stop after stage 0 (work dir stage0.kicad_pcb; the board itself is left alone)')
    ap.add_argument('--fr', action='append', default=[], metavar='ARG',
                    help='extra Freerouting argument, e.g. --fr=--router.automatic_neckdown=true (repeatable)')
    ap.add_argument('--passes', type=int, default=3, help='stage 1 (Freerouting 2.5.0: use 1, see above)')
    ap.add_argument('--passes2', type=int, default=3, help='stage 2')
    ap.add_argument('--passes3', type=int, default=3, help='stage 3 (power nets, narrow)')
    ap.add_argument('--passes4', type=int, default=3, help='stage 4 (leftovers, outer layers)')
    ap.add_argument('--power-narrow', type=float, default=0.4, help='mm: Power class width in stage 3')
    ap.add_argument('--power-clearance', type=float, default=0.0, help='mm: Power class clearance in stage 3 (0: keep)')
    ap.add_argument('--neck', type=float, default=2.0, help='mm: a plane narrower than this counts as cut')
    ap.add_argument('--max-plane', type=float, default=50.0, help='mm of plane track per net, and per slot')
    ap.add_argument('--slot-gap', type=float, default=2.0, help='mm: plane tracks closer than this form one slot')
    ap.add_argument('--stitch', action='store_true', help='add GND stitching vias (only when everything is routed)')
    ap.add_argument('--reuse', action='store_true', help='import the .ses files of an earlier run, do not route')
    ap.add_argument('--threads', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument('--work', default=os.path.join(HERE, 'gen', 'route'))
    ap.add_argument('--step', choices=STEPS, help=argparse.SUPPRESS)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    pcb = os.path.join(HERE, PROJECT + '.kicad_pcb')
    if args.step:
        globals()[args.step](args, pcb)
        return
    # each step in its own process: after an SES import, pcbnew's SWIG objects come back untyped
    for step in STEPS[:1] if args.stage0_only else STEPS:
        subprocess.run([sys.executable, os.path.abspath(__file__)] + sys.argv[1:] + ['--step', step], check=True)


if __name__ == '__main__':
    main()
