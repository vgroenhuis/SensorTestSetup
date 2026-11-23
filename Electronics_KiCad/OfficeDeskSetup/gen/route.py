#!/usr/bin/env python3
"""Autoroute the board with Freerouting, then add GND pours on F.Cu and B.Cu and fill all zones.

Run with KiCad's own Python, after gen/pcbgen.py:

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/route.py --freerouting PATH/freerouting-2.5.0.jar --java PATH/java.exe

Freerouting: https://github.com/freerouting/freerouting (the .jar needs Java 25; the native freerouting-cli 2.5.0 for
Windows crashes when it starts routing).

One stage at a time (the normal way): --stage NAME routes that stage on OfficeDeskSetup.kicad_pcb as it is now,
with the tracks already on it (also those drawn or moved by hand) locked, and saves it back; a copy of the board
from before goes to the work directory (before_NAME.kicad_pcb). Inspect, adjust and save in KiCad, close it, then
run the next stage:

    power -> vias -> signals -> planes -> narrow -> rest -> finish

Without --stage, all stages run in a row in the work directory from the bare placement (old way, for experiments),
and only finish writes the board. Stages:

0. power: the power nets (Power, Pack and Supply classes, not the plane nets) alone, on F.Cu and B.Cu; their tracks
   are locked for the next stages (--no-power-first skips it in a full run). --bare: from the bare placement.
   Chip keep-outs (in the DSN of this stage only, --no-keepout skips them): no power tracks or vias on the far side
   of a chip's courtyard, where its signals fan out, and no power tracks in the area its pins enclose (U parts with
   SMD pads only, no larger than --keepout-max mm: not the modules).
   Escape rounds (--escape-rounds, 0 = no limit): the power pads left open get an escape via (a via beside the pad
   with a short track, at the class width where it fits) on the stage's starting board, and the stage is routed
   again; until nothing is open, no pad gets a new via, or the rounds (if limited) are used up. The round with the fewest open
   connections is kept, without the escape vias it did not use (those at pads still open stay, to finish by hand:
   from the via a short track on any layer, the planes have room for it). Work files: stage0_in.kicad_pcb (the
   starting board with the escape vias), stage0_rN.kicad_pcb (each round), stage0_rounds.json.
   Pin ranking (--scores, pin_scores.json in the work directory, kept over all runs): a pin scores a point every
   round it is left open and every time there is no room for its escape via. Escape vias go in ranking order, and
   a new attempt first gives every pin with at least --pre-escape points (1) its via, highest first.
   vias: Freerouting does not connect pads to the planes itself, so every SMD pad on GND or +3V3 gets a
   via to its plane, or a short track to a through-hole pad of its net (gen/planevias.py). They come after the
   power tracks: a via beside a fine-pitch power pin can leave no room for a full-width track (USB-C VBUS).
1. signals: on F.Cu and B.Cu only: the inner layers (GND and +3V3 planes from pcbgen.py) are marked as plane layers in
   the Specctra DSN, so Freerouting connects to them with vias but does not route through them. Escape rounds as in
   stage 0, for every net that is not a plane net (--escape-rounds-signals, 2).
2. planes: the tracks so far are locked and Freerouting routes what is left with the inner layers open. Its tracks
   through the planes are kept only while the planes stay sound:
   - at most --max-plane mm (50) of plane track per net;
   - plane tracks closer together than --slot-gap mm (2) leave no plane between them and count as one slot, at most
     --max-plane mm long in total;
   - each plane stays one piece: filled with a minimum width of --neck mm (2, so a narrow neck counts as a cut), it
     has no more islands over 25 mm2 than after stage 1.
   While a rule is broken, the worst net loses its stage-2 tracks; then each removed net is tried back on its own.
3. narrow: the power nets that are left at --power-narrow mm, then the plane rules above (prune) and widening.
4. rest: whatever is left, on the outer layers only. finish: GND pours on F.Cu and B.Cu, zones filled.

--reuse imports the .ses files of an earlier run from the work directory instead of routing again (same placement
only), e.g. to try another --neck.

No GND stitching vias: they would be in the way of finishing the routing by hand. Add them once everything is
routed, with gen/planevias.py (or --stitch here if Freerouting routes everything). Net classes give the track widths.
The project file is left as it was.
"""
import argparse
import collections
import json
import os
import re
import shutil
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
    """Short names of the Power, Pack and Supply net class nets, without the plane nets."""
    ns = board.GetDesignSettings().m_NetSettings
    planes = {z.GetNetname().split('/')[-1] for z in zones(board)}
    out = set()
    for net in board.GetNetsByName().keys():
        name = str(net)
        cls = ns.GetEffectiveNetClass(name).GetName()
        if any(c in cls for c in ('Power', 'Pack', 'Supply')) and name.split('/')[-1] not in planes:
            out.add(name.split('/')[-1])
    return out


def route(board, args, name, closed, passes, keep=None, areas=()):
    """Export the board, run Freerouting on it and import the result. `closed`: layers it may not route on. `keep`:
    route only the nets whose short name it accepts. `areas`: rule areas that are in the DSN only (taken off the board
    again right after the export)."""
    dsn, ses = (os.path.join(args.work, name + e) for e in ('.dsn', '.ses'))
    for z in areas:
        board.Add(z)
    ok = pcbnew.ExportSpecctraDSN(board, dsn)
    for z in areas:
        board.Remove(z)
    if not ok:
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


def bare(pcb):
    """The board without tracks and route.py's pours. Returns (board, removed items: keep them referenced)."""
    board = pcbnew.LoadBoard(pcb)
    refs = list(board.GetTracks())                     # removed items stay referenced (SWIG types, see finish)
    for t in refs:                                     # start from the bare placement
        board.Remove(t)
    for z in zones(board):                             # earlier pours from route.py
        if z.GetLayer() in POURS:
            refs.append(z)
            board.Remove(z)
    return board, refs


def load(args, pcb, prev):
    """The board a step starts from: the board itself (--stage), else the previous step's board in the work dir."""
    return pcbnew.LoadBoard(pcb if args.stage else os.path.join(args.work, prev + '.kicad_pcb'))


def store(args, pcb, board, name):
    save(board, pcb if args.stage else os.path.join(args.work, name + '.kicad_pcb'), pro(pcb))


def rule_area(board, layer, box, vias):
    """A keep-out for tracks (and vias) of every net over `box` on `layer`."""
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    ls = pcbnew.LSET()
    ls.AddLayer(layer)
    z.SetLayerSet(ls)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowZoneFills(False)
    z.SetDoNotAllowFootprints(False)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((box.GetLeft(), box.GetTop()), (box.GetRight(), box.GetTop()), (box.GetRight(), box.GetBottom()),
                 (box.GetLeft(), box.GetBottom())):
        ol.Append(x, y)
    return z


def chips(board, args):
    """The footprints that get a keep-out in stage 0: references with a prefix of --keepout-refs, SMD pads only,
    courtyard no larger than --keepout-max mm a side (not the modules)."""
    out = []
    prefixes = [x for x in args.keepout_refs.split(',') if x]
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not any(ref.startswith(x) and ref[len(x):].isdigit() for x in prefixes) or not len(fp.Pads()):
            continue
        if any(p.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN) for p in fp.Pads()):
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
        if max(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) <= args.keepout_max:
            out.append((fp, bb))
    return out


def keepouts(board, args, codes, clr=0.2, relaxed=()):
    """Chip keep-outs for stage 0, so the power tracks leave the space under and between a chip's pins to its own
    signals: on the other side of the board no tracks and no vias over the courtyard (the chip's signals fan out
    there), on its own side no tracks in the area its pins enclose, as far as no pin on a net of `codes` (the nets
    being routed) is in it. `relaxed`: chips without keep-outs (one of their pins had room for an escape via only
    under the chip, with its track between the pins). Returns (rule areas, {reference: courtyard box})."""
    zs, boxes = [], {}
    if not args.keepout:
        return zs, boxes
    for fp, bb in chips(board, args):
        if fp.GetReference() in relaxed:
            continue
        side = fp.GetLayer()
        other = pcbnew.B_Cu if side == pcbnew.F_Cu else pcbnew.F_Cu
        zs.append(rule_area(board, other, bb, vias=True))
        boxes[fp.GetReference()] = bb
        pb = None
        for p in fp.Pads():
            b = p.GetBoundingBox()
            if pb is None:
                pb = pcbnew.BOX2I(b.GetPosition(), b.GetSize())
            else:
                pb.Merge(b)
        routed = [p for p in fp.Pads() if p.GetNetCode() in codes]
        k = 0
        while True:
            x0, y0, x1, y1 = pb.GetLeft() + k, pb.GetTop() + k, pb.GetRight() - k, pb.GetBottom() - k
            if min(x1 - x0, y1 - y0) < mm(0.5):
                break
            rect = pcbnew.SHAPE_RECT(x0, y0, x1 - x0, y1 - y0)
            if not any(p.GetEffectiveShape(side).Collide(rect, mm(clr)) for p in routed):
                inner = pcbnew.BOX2I(pcbnew.VECTOR2I(x0, y0), pcbnew.VECTOR2L(x1 - x0, y1 - y0))
                zs.append(rule_area(board, side, inner, vias=False))
                break
            k += mm(0.05)
    return zs, boxes


def nets_of(board, args, s):
    """Stage s ('0' or '1'): (net codes it routes, filter on short names for only_nets or None, passes, keep-outs)."""
    planes = {z.GetNetname() for z in zones(board)}
    if s == '0':
        power = power_nets(board)
        codes = {c for c, n in board.GetNetsByNetcode().items() if n.GetNetname().split('/')[-1] in power}
        return codes, (lambda n: n in power), args.passes0, True
    codes = {c for c, n in board.GetNetsByNetcode().items() if c > 0 and n.GetNetname() not in planes}
    return codes, None, args.passes, False


def sizes(board, codes):
    """{net code: (track width, via diameter, via drill) mm} from the net classes."""
    ns = board.GetDesignSettings().m_NetSettings
    out = {}
    for c, n in board.GetNetsByNetcode().items():
        if c in codes:
            nc = ns.GetEffectiveNetClass(n.GetNetname())
            out[c] = tuple(pcbnew.ToMM(v) for v in (nc.GetTrackWidth(), nc.GetViaDiameter(), nc.GetViaDrill()))
    return out


def wpath(args, *parts):
    return os.path.join(args.work, ''.join(str(p) for p in parts))


def load_scores(args):
    """The pin ranking kept over all runs (--scores): {pad name: {'net', 'open', 'no_via', 'score'}}. A pin scores a
    point every round it is left open and every time there is no room for its escape via."""
    try:
        return json.load(open(args.scores, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def add_scores(args, board, open_names, no_via):
    scores = load_scores(args)
    nets = {planevias.pad_name(p): p.GetNetname().split('/')[-1] for p in board.GetPads()}
    for names, what in ((open_names, 'open'), (no_via, 'no_via')):
        for n in set(names):
            e = scores.setdefault(n, {'net': nets.get(n, '?'), 'open': 0, 'no_via': 0, 'score': 0})
            e[what] += 1
            e['score'] += 1
    os.makedirs(os.path.dirname(os.path.abspath(args.scores)), exist_ok=True)
    json.dump(dict(sorted(scores.items(), key=lambda kv: (-kv[1]['score'], kv[0]))), open(args.scores, 'w', encoding='utf-8'), indent=1)


def ranked(args, pads):
    """`pads` with the highest scoring pins first (the escape vias go in this order: the first get the best spots)."""
    scores = load_scores(args)
    return sorted(pads, key=lambda p: (-scores.get(planevias.pad_name(p), {}).get('score', 0), planevias.pad_name(p)))


def escape_vias(args, board, codes, pads, state, ko):
    """Escape vias at `pads` (planevias.escape), off the chip keep-outs. A pad that has no room outside its chip's
    keep-out tries again with that keep-out gone: the via may then go under the chip, and the chip loses its keep-outs
    for the rounds after (state['relaxed']), so the tracks to and from the via are allowed there. The keep-out only
    keeps power tracks off a chip where they can go around it. Returns (done, missed, chips relaxed now)."""
    relaxed = state.setdefault('relaxed', [])
    boxes = keepouts(board, args, codes, relaxed=relaxed)[1] if ko else {}
    sz = sizes(board, codes)
    done, missed = planevias.escape(board, pads, sz, list(boxes.values()))
    still, now = [], []
    for name in missed:
        ref = name.rsplit('.', 1)[0]
        p = next((q for q in pads if planevias.pad_name(q) == name), None)
        if p is None or ref not in boxes:
            still.append(name)
            continue
        d2, _ = planevias.escape(board, [p], sz, [b for r, b in boxes.items() if r != ref])
        if d2:
            done += d2
            del boxes[ref]
            relaxed.append(ref)
            now.append(ref)
        else:
            still.append(name)
    return done, still, now


def record(state, done):
    for name, via, tracks in done:
        pad = tracks[0].GetStart()
        state['escapes'].append({'pad': [name, pad.x, pad.y], 'net': via.GetNetname(),
                                 'via': [via.GetPosition().x, via.GetPosition().y],
                                 'tracks': [[t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y] for t in tracks]})


def pre_escape(args, board, s):
    """A new attempt starts with escape vias at the pins that failed before (score at least --pre-escape), highest
    score first, so they get their spot before anything else. Writes the stage's rounds file."""
    state = {'rounds': [], 'escapes': [], 'stop': False}
    if args.pre_escape > 0:
        codes, _, _, ko = nets_of(board, args, s)
        scores = load_scores(args)
        pads = ranked(args, [p for p in board.GetPads() if p.GetNetCode() in codes and
                             scores.get(planevias.pad_name(p), {}).get('score', 0) >= args.pre_escape])
        if pads:
            done, missed, now = escape_vias(args, board, codes, pads, state, ko)
            record(state, done)
            add_scores(args, board, [], missed)
            print('escape vias first, at the pins that failed before: %d (%s); no room for one: %s; under the chip, its '
                  'keep-outs dropped: %s' % (len(done), ' '.join(d[0] for d in done) or '-', ' '.join(missed) or 'none',
                                            ' '.join(now) or 'none'), flush=True)
    json.dump(state, open(wpath(args, 'stage%s_rounds.json' % s), 'w'), indent=1)


def prep0(args, pcb):
    """Stage 0's starting board: the board as it is (--stage; tracks drawn by hand stay, locked) or the bare placement,
    with narrowing stubs on the power pins too fine for a full-width track. The plane vias come after stage 0: a via
    beside a fine-pitch power pin can leave no room for a full-width track."""
    if args.stage and not args.bare:
        board, refs = pcbnew.LoadBoard(pcb), []
        for t in board.GetTracks():
            t.SetLocked(True)
    else:
        board, refs = bare(pcb)
    if args.stubs:
        power = power_nets(board)
        ns = board.GetDesignSettings().m_NetSettings
        widths = {code: pcbnew.ToMM(ns.GetEffectiveNetClass(n.GetNetname()).GetTrackWidth())
                  for code, n in board.GetNetsByNetcode().items() if n.GetNetname().split('/')[-1] in power}
        n, missed = planevias.stubs(board, widths)
        print('narrowing stubs: %d; fine-pitch power pads without one: %s' % (n, ' '.join(missed) or 'none'), flush=True)
    if args.keepout:
        print('chip keep-outs: %s' % ' '.join(sorted((fp.GetReference() for fp, _ in chips(board, args)),
                                                     key=lambda r: (re.sub(r'\d', '', r), int(re.sub(r'\D', '', r) or 0)))))
    pre_escape(args, board, '0')
    save(board, wpath(args, 'stage0_in.kicad_pcb'), pro(pcb))


def prep1(args, pcb):
    """Stage 1's starting board: the plane vias step's board, all tracks locked."""
    board = load(args, pcb, 'vias')
    for t in board.GetTracks():
        t.SetLocked(True)
    pre_escape(args, board, '1')
    save(board, wpath(args, 'stage1_in.kicad_pcb'), pro(pcb))


def run_round(args, pcb, s):
    """One routing round of stage s on its starting board (with the escape vias of the rounds before)."""
    board = pcbnew.LoadBoard(wpath(args, 'stage%s_in.kicad_pcb' % s))
    codes, keep, passes, ko = nets_of(board, args, s)
    relaxed = json.load(open(wpath(args, 'stage%s_rounds.json' % s))).get('relaxed', [])
    areas = keepouts(board, args, codes, relaxed=relaxed)[0] if ko else []
    closed = [board.GetLayerName(l) for l in sorted({z.GetLayer() for z in zones(board)})]
    route(board, args, '%s_%s_r%d' % (PROJECT, s, args.round), closed, passes, keep=keep, areas=areas)
    for t in board.GetTracks():
        t.SetLocked(True)
    save(board, wpath(args, 'stage%s_r%d.kicad_pcb' % (s, args.round)), pro(pcb))


def escape_round(args, pcb, s):
    """Count what round r of stage s left open; unless that is nothing (or this was the last round), give the open
    pads escape vias on the starting board for the next round. Writes stage<s>_rounds.json."""
    log = wpath(args, 'stage%s_rounds.json' % s)
    state = json.load(open(log))
    board = pcbnew.LoadBoard(wpath(args, 'stage%s_r%d.kicad_pcb' % (s, args.round)))
    codes = nets_of(board, args, s)[0]
    n, pads = planevias.open_pads(board, codes)
    names = sorted({planevias.pad_name(p) for p in pads})
    state['rounds'].append({'round': args.round, 'open': n, 'pads': names})
    print('stage %s round %d: %d open connections; open pads: %s' % (s, args.round, n, ' '.join(names) or 'none'), flush=True)
    add_scores(args, board, names, [])
    limit = args.escape_rounds if s == '0' else args.escape_rounds_signals
    if n == 0 or 0 < limit <= args.round:             # limit 0: until no pad gets a new via
        state['stop'] = True
    else:
        start = pcbnew.LoadBoard(wpath(args, 'stage%s_in.kicad_pcb' % s))
        # a pad by name and position, within 1 um: the recorded position comes back through mm and can be 1 nm off;
        # an exact match missed it and gave the same pad a new via every round, without end
        recorded = [tuple(e['pad']) for e in state['escapes']]

        def key(p):
            name, x, y = planevias.pad_name(p), p.GetPosition().x, p.GetPosition().y
            return next(((n, a, b) for n, a, b in recorded if n == name and abs(a - x) <= 1000 and abs(b - y) <= 1000),
                        (name, x, y))
        want = {key(p) for p in pads}
        had = set(recorded)
        todo = ranked(args, [p for p in start.GetPads() if key(p) in want - had])
        done, missed, now = escape_vias(args, start, codes, todo, state, nets_of(start, args, s)[3])
        print('escape vias: %d (%s); no room for one: %s; under the chip, its keep-outs dropped: %s; already had one: %s' % (
            len(done), ' '.join(d[0] for d in done) or '-', ' '.join(missed) or 'none', ' '.join(now) or 'none',
            ' '.join(sorted(name for name, _, _ in want & had)) or 'none'), flush=True)
        record(state, done)
        add_scores(args, start, [], missed)
        if done:
            save(start, wpath(args, 'stage%s_in.kicad_pcb' % s), pro(pcb))
        else:
            state['stop'] = True
    json.dump(state, open(log, 'w'), indent=1)


def pick_round(args, pcb, s, name):
    """Keep the round of stage s with the fewest open connections (the earliest of equals), without the escape vias it
    did not use."""
    state = json.load(open(wpath(args, 'stage%s_rounds.json' % s)))
    best = min(state['rounds'], key=lambda r: (r['open'], r['round']))
    print('stage %s rounds (open connections): %s; keeping round %d' % (
        s, ', '.join('%d: %d' % (r['round'], r['open']) for r in state['rounds']), best['round']), flush=True)
    board = pcbnew.LoadBoard(wpath(args, 'stage%s_r%d.kicad_pcb' % (s, best['round'])))
    refs = []
    still = set(best['pads'])                          # pads still open keep their via
    marks = [(e['net'], e['via'][0], e['via'][1], e['tracks']) for e in state['escapes'] if e['pad'][0] not in still]
    print('escape vias the router did not use, removed: %d (kept at the pads still open)' %
          planevias.unused_escapes(board, marks, refs), flush=True)
    top = list(load_scores(args).items())[:15]
    print('pin ranking (%s): %s' % (args.scores, ', '.join('%s %s %d' % (n, e['net'], e['score']) for n, e in top) or 'empty'), flush=True)
    store(args, pcb, board, name)


def stage0(args, pcb):
    run_round(args, pcb, '0')


def escape0(args, pcb):
    escape_round(args, pcb, '0')


def pick0(args, pcb):
    pick_round(args, pcb, '0', 'stage0')


def vias(args, pcb):
    """Plane vias (and short tracks to through-hole pads) for the SMD pads on the plane nets."""
    if args.stage or args.power_first:                 # stage 0's board: its tracks are locked
        board, refs = load(args, pcb, 'stage0'), []
    else:
        board, refs = bare(pcb)
    n, missed = planevias.fanout(board, {z.GetNetname() for z in zones(board)})
    print('plane vias and tracks: %d; SMD pads without one: %s' % (n, ' '.join(missed) or 'none'), flush=True)
    for t in board.GetTracks():
        t.SetLocked(True)
    store(args, pcb, board, 'vias')


def stage1(args, pcb):
    """Signals on the outer layers (planes closed), one round."""
    run_round(args, pcb, '1')


def escape1(args, pcb):
    escape_round(args, pcb, '1')


def pick1(args, pcb):
    pick_round(args, pcb, '1', 'stage1')


def stage2(args, pcb):
    """What is left, with the planes open. The tracks from before (and the plane pieces) are recorded for prune."""
    board = load(args, pcb, 'stage1')
    for t in board.GetTracks():
        t.SetLocked(True)
    planes = sorted({z.GetLayer() for z in zones(board)})
    json.dump({'planes': planes, 'tracks': [key(t) for t in board.GetTracks()], 'islands': islands(board, planes, args.neck)},
              open(os.path.join(args.work, 'stage1.json'), 'w'))
    route(board, args, PROJECT + '_2', [], args.passes2)
    store(args, pcb, board, 'stage2')


def stage3(args, pcb):
    """The power nets that are left, at a narrow width: Freerouting has one width per net class and cannot neck a
    1 mm track down to a 0.4 mm pitch pin. finish() widens them again where there is room."""
    board = load(args, pcb, 'stage2')
    for t in board.GetTracks():
        t.SetLocked(True)
    ns = board.GetDesignSettings().m_NetSettings
    power = ns.GetNetClassByName('Power')
    power.SetTrackWidth(mm(args.power_narrow))
    if args.power_clearance:
        power.SetClearance(mm(args.power_clearance))
    ns.RecomputeEffectiveNetclasses()
    route(board, args, PROJECT + '_3', [], args.passes3)
    store(args, pcb, board, 'stage3')


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
    board = load(args, pcb, 'stage3')
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
    store(args, pcb, board, 'stage3p')


def stage4(args, pcb):
    """What the plane rules took out, and whatever else is left, on the outer layers only (planes closed)."""
    board = load(args, pcb, 'stage3p')
    for t in board.GetTracks():
        t.SetLocked(True)
    planes = sorted({z.GetLayer() for z in zones(board) if z.GetLayer() not in POURS})
    route(board, args, PROJECT + '_4', [board.GetLayerName(l) for l in planes], args.passes4)
    store(args, pcb, board, 'stage4')


def finish(args, pcb):
    """Pour, fill and save."""
    board = load(args, pcb, 'stage4')
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


STEPS = ('stage0', 'vias', 'stage1', 'stage2', 'stage3', 'prune', 'stage4', 'finish')
STAGES = {'power': ('stage0',), 'vias': ('vias',), 'signals': ('stage1',), 'planes': ('stage2',),
          'narrow': ('stage3', 'prune'), 'rest': ('stage4',), 'finish': ('finish',)}
ROUNDS = {'stage0': '0', 'stage1': '1'}       # steps that route in rounds, with escape vias in between
HELPERS = ('prep0', 'escape0', 'pick0', 'prep1', 'escape1', 'pick1')


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
    ap.add_argument('--bare', action='store_true',
                    help='with --stage power: start from the bare placement (all tracks and vias on the board removed)')
    ap.add_argument('--escape-rounds', type=int, default=0,
                    help='stage 0: route again up to this many times, each time with escape vias at the pads left open '
                         '(0: no limit, until no pad gets a new via)')
    ap.add_argument('--escape-rounds-signals', type=int, default=2, help='the same for stage 1 (0: no limit)')
    ap.add_argument('--scores', help='pin ranking kept over all runs (default: pin_scores.json in the work directory)')
    ap.add_argument('--pre-escape', type=int, default=1,
                    help='a new attempt gives pins with at least this score an escape via before routing (0: off)')
    ap.add_argument('--keepout', action=argparse.BooleanOptionalAction, default=True,
                    help='stage 0: no power tracks under the chips (rule areas in the DSN only)')
    ap.add_argument('--keepout-refs', default='U', help='reference prefixes of the chips that get a keep-out (comma list)')
    ap.add_argument('--keepout-max', type=float, default=20.0,
                    help='mm: no keep-out for parts with a larger courtyard side (modules)')
    ap.add_argument('--stage', choices=STAGES,
                    help='run this one stage on the board itself (keeps the tracks on it), then stop')
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
    ap.add_argument('--step', choices=STEPS + HELPERS, help=argparse.SUPPRESS)
    ap.add_argument('--round', type=int, default=0, help=argparse.SUPPRESS)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    args.scores = args.scores or os.path.join(args.work, 'pin_scores.json')
    pcb = os.path.join(HERE, PROJECT + '.kicad_pcb')
    if args.step:
        globals()[args.step](args, pcb)
        return
    if args.stage:
        lock = os.path.join(HERE, '~%s.kicad_pcb.lck' % PROJECT)
        if os.path.exists(lock):
            sys.exit('the board is open in KiCad (%s): save it, close KiCad and run again' % lock)
        shutil.copy(pcb, os.path.join(args.work, 'before_%s.kicad_pcb' % args.stage))
    # each step in its own process: after an SES import, pcbnew's SWIG objects come back untyped
    def run(step, *extra):
        subprocess.run([sys.executable, os.path.abspath(__file__)] + sys.argv[1:] + ['--step', step] + list(extra), check=True)

    for step in STAGES[args.stage] if args.stage else STEPS:
        if step not in ROUNDS:
            run(step)
            continue
        s = ROUNDS[step]
        if s == '0' and not args.power_first and not args.stage:
            continue
        run('prep' + s)
        log = os.path.join(args.work, 'stage%s_rounds.json' % s)
        for r in range(1000):
            run(step, '--round', str(r))
            run('escape' + s, '--round', str(r))
            if json.load(open(log))['stop']:
                break
        run('pick' + s)


if __name__ == '__main__':
    main()
