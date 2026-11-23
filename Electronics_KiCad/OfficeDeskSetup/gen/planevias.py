"""Vias to the inner planes, placed with KiCad's own shape collision tests (run with KiCad's Python).

fanout(): Freerouting 2.5 treats the nets of a plane as connected by the plane and never adds the vias from SMD pads
down to it, so every SMD pad on a plane net gets one here, before routing: a via beside the pad with a short track,
or a few vias inside a large (exposed) pad.

escape(): escape vias for pads the router left unconnected (gen/route.py's rounds): a via beside the pad with a
short track, so the next round can reach the pin from the other outer layer.

stitch(): GND vias on a grid wherever there is room, so the GND pours on F.Cu and B.Cu are tied to the In1 GND plane
everywhere instead of hanging on single pads. Only once everything is routed (a via grid is in the way of routing by
hand), as a command:

    "C:/Program Files/KiCad/10.0/bin/python.exe" gen/planevias.py OfficeDeskSetup.kicad_pcb [--pitch 5]

It adds the vias, refills the zones with kicad-cli and saves the board; the project file is left as it was.
"""
import math

import pcbnew


def disc(x, y, d):
    """A round shape of diameter d mm (a zero-length segment: SHAPE_CIRCLE.Collide only takes a SEG in Python)."""
    p = pcbnew.VECTOR2I(mm(x), mm(y))
    return pcbnew.SHAPE_SEGMENT(p, p, mm(d))

OUTER = (pcbnew.F_Cu, pcbnew.B_Cu)
CELL = 2.0                                  # mm, spatial index


def mm(v):
    return pcbnew.FromMM(v)


class Copper:
    """Copper on the outer layers (pads, tracks, vias, holes, cutouts), indexed for collision tests."""

    def __init__(self, board):
        self.cells = {}
        bb = board.GetBoardEdgesBoundingBox()
        self.edge = tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
        for p in board.GetPads():
            for layer in OUTER:
                if p.IsOnLayer(layer):
                    self.add(p.GetEffectiveShape(layer), p.GetNetCode(), (layer,))
            if p.HasHole():
                self.add(p.GetEffectiveHoleShape(), -1, OUTER, hole=True)
        for t in board.GetTracks():
            for layer in OUTER:
                if t.IsOnLayer(layer):
                    self.add(t.GetEffectiveShape(layer), t.GetNetCode(), (layer,), hole=t.Type() == pcbnew.PCB_VIA_T)
        for fp in board.GetFootprints():                    # board cutouts drawn in footprints (SK6812MINI-E)
            for g in fp.GraphicalItems():
                if g.GetLayer() == pcbnew.Edge_Cuts:
                    self.add(g.GetEffectiveShape(), -1, OUTER, extra=0.5)
        self.keep = []                                      # shapes handed to KiCad must stay referenced

    def add(self, shape, net, layers, extra=0.0, hole=False):
        bb = shape.BBox()
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
        item = (shape, net, layers, mm(extra), hole)
        for cx in range(int(x0 // CELL) - 1, int(x1 // CELL) + 2):
            for cy in range(int(y0 // CELL) - 1, int(y1 // CELL) + 2):
                self.cells.setdefault((cx, cy), []).append(item)

    def near(self, x, y, r):
        seen = set()
        for cx in range(int((x - r) // CELL) - 1, int((x + r) // CELL) + 2):
            for cy in range(int((y - r) // CELL) - 1, int((y + r) // CELL) + 2):
                for item in self.cells.get((cx, cy), ()):
                    if id(item) not in seen:
                        seen.add(id(item))
                        yield item

    def free(self, shape, x, y, r, net, layers, clr, edge, holes=True, hole_at=None):
        """`shape` (around x, y, radius r mm) clears all copper of other nets on `layers` by clr mm, and the board
        edge by `edge` mm (None: no edge test). `holes`: also keep clear of holes of its own net (for a new via).
        `hole_at`: a through-hole pad position (VECTOR2I) whose hole does not count (a track ending on that pad)."""
        x0, y0, x1, y1 = self.edge
        if edge is not None and not (x0 + edge + r <= x <= x1 - edge - r and y0 + edge + r <= y <= y1 - edge - r):
            return False
        for s, n, ls, extra, hole in self.near(x, y, r + clr + 1):
            if n == net and n >= 0 and not (hole and holes):   # a via keeps hole spacing whatever the net
                continue
            if hole and hole_at is not None and s.BBox().Contains(hole_at):
                continue
            if any(l in layers for l in ls) and s.Collide(shape, mm(clr) + extra):
                return False
        return True


def add_via(board, cu, x, y, net, d, drill):
    v = pcbnew.PCB_VIA(board)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetWidth(mm(d))
    v.SetDrill(mm(drill))
    v.SetNet(net)
    v.SetLocked(True)
    board.Add(v)
    circle = disc(x, y, d)
    cu.keep.append(circle)
    cu.add(circle, net.GetNetCode(), OUTER, hole=True)
    return v


def _track(board, cu, p, x, y, width, layer):
    seg = pcbnew.SHAPE_SEGMENT(p.GetPosition(), pcbnew.VECTOR2I(mm(x), mm(y)), mm(width))
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(p.GetPosition())
    t.SetEnd(pcbnew.VECTOR2I(mm(x), mm(y)))
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(p.GetNet())
    t.SetLocked(True)
    board.Add(t)
    cu.keep.append(seg)
    cu.add(seg, p.GetNetCode(), (layer,))


def fanout(board, nets, d=0.6, drill=0.3, width=0.3, clr=0.2, edge=1.0, reach=2.5):
    """A via to the plane for every SMD pad on `nets`, or a short track to a through-hole pad of the same net within
    `reach` mm (a USB-C GND pin to its shield pad). Stacked pads (USB-C A1/B12) share one. Run it after the power
    nets are routed: a via beside a fine-pitch power pin can leave no room for the power track. Returns (vias and
    tracks, pads that got none)."""
    cu = Copper(board)
    vias, missed, done = 0, [], set()
    tht = {}
    for p in board.GetPads():
        if p.GetNetname() in nets and p.HasHole():
            tht.setdefault(p.GetNetCode(), []).append(p)
    for fp in board.GetFootprints():
        fc = fp.GetPosition()
        for p in fp.Pads():
            if p.GetNetname() not in nets or p.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN):
                continue
            net, code = p.GetNet(), p.GetNetCode()
            layer = pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) and not p.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Cu
            spot = (code, layer, p.GetPosition().x, p.GetPosition().y)
            if spot in done:                                # a stacked pad that already has its connection
                continue
            done.add(spot)
            bb = p.GetBoundingBox()
            px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
            if min(w, h) >= 1.6:                            # exposed pad: vias in the pad, at 1.2 mm
                cx, cy = pcbnew.ToMM(bb.GetCenter().x), pcbnew.ToMM(bb.GetCenter().y)
                nx, ny = max(1, min(3, int((w - d - 0.3) / 1.2) + 1)), max(1, min(3, int((h - d - 0.3) / 1.2) + 1))
                got = 0
                for i in range(nx):
                    for j in range(ny):
                        x, y = cx + (i - (nx - 1) / 2) * 1.2, cy + (j - (ny - 1) / 2) * 1.2
                        c = disc(x, y, d)
                        other = tuple(l for l in OUTER if l != layer)
                        if cu.free(c, x, y, d / 2, code, OUTER if p.GetAttribute() == pcbnew.PAD_ATTRIB_CONN else other, clr, edge):
                            add_via(board, cu, x, y, net, d, drill)
                            got += 1
                vias += got
                if got:
                    continue
            # a short track to a through-hole pad of the net (it reaches the planes)
            px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            near = sorted((math.hypot(pcbnew.ToMM(q.GetPosition().x) - px, pcbnew.ToMM(q.GetPosition().y) - py), i, q)
                          for i, q in enumerate(tht.get(code, ())) if q.IsOnLayer(layer))
            linked = False
            for dist, _, q in near:
                if dist > reach:
                    break
                if q.HitTest(p.GetPosition()):              # on top of it (a mounting hole's SMD ring): connected
                    linked = True
                    break
                x, y = pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y)
                seg = pcbnew.SHAPE_SEGMENT(p.GetPosition(), q.GetPosition(), mm(width))
                if cu.free(seg, (px + x) / 2, (py + y) / 2, dist / 2 + width, code, (layer,), clr, None, holes=False,
                           hole_at=q.GetPosition()):
                    _track(board, cu, p, x, y, width, layer)
                    vias += 1
                    linked = True
                    break
            if linked:
                continue
            # beside the pad, outwards from the footprint first
            ox, oy = px - pcbnew.ToMM(fc.x), py - pcbnew.ToMM(fc.y)
            r0 = math.hypot(w, h) / 2 + d / 2 + clr
            cands = []
            for k in range(16):
                a = k * math.pi / 8
                ux, uy = math.cos(a), math.sin(a)
                out = (ux * ox + uy * oy) / (math.hypot(ox, oy) or 1)
                for s in range(11):
                    cands.append((s, -out, px + ux * (r0 + 0.25 * s), py + uy * (r0 + 0.25 * s)))
            for _, _, x, y in sorted(cands):
                c = disc(x, y, d)
                if not cu.free(c, x, y, d / 2, code, OUTER, clr, edge):
                    continue
                seg = pcbnew.SHAPE_SEGMENT(p.GetPosition(), pcbnew.VECTOR2I(mm(x), mm(y)), mm(width))
                if not cu.free(seg, (px + x) / 2, (py + y) / 2, math.hypot(x - px, y - py) / 2 + width, code, (layer,), clr, edge):
                    continue
                _track(board, cu, p, x, y, width, layer)
                add_via(board, cu, x, y, net, d, drill)
                vias += 1
                break
            else:
                missed.append('%s.%s' % (fp.GetReference(), p.GetNumber()))
    return vias, missed


def stubs(board, widths, clr=0.2, edge=1.0, longest=3.0):
    """Narrowing stubs: Freerouting has one track width per net class, and a 1 mm power track cannot reach a pin with
    0.4-0.65 mm pitch neighbours. Every SMD pad on a net of `widths` ({net code: track width mm}) where a track of
    that width would not fit gets a short track of the pad's own width, straight out of the pin row (or another
    way when that is blocked), just long enough for a full-width track to end on it. Returns (stubs, pads that got
    none, as 'U6.22')."""
    cu = Copper(board)
    n, missed = 0, []
    for fp in board.GetFootprints():
        fc = fp.GetPosition()
        for p in fp.Pads():
            code = p.GetNetCode()
            if code not in widths or p.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN):
                continue
            full = widths[code]
            layer = pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) and not p.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Cu
            px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            bb = p.GetBoundingBox()
            w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
            if cu.free(disc(px, py, full), px, py, full / 2, code, (layer,), clr, None, holes=False):
                continue                                    # a full-width track fits on the pad itself
            ox, oy = px - pcbnew.ToMM(fc.x), py - pcbnew.ToMM(fc.y)
            if h > w * 1.2:                                 # a pin row: out along the pad's long side
                dirs = [(0, 1 if oy >= 0 else -1)]
            elif w > h * 1.2:
                dirs = [(1 if ox >= 0 else -1, 0)]
            else:
                dirs = [(1 if ox >= 0 else -1, 0) if abs(ox) >= abs(oy) else (0, 1 if oy >= 0 else -1)]
            dirs += [d for d in ((1, 0), (-1, 0), (0, 1), (0, -1)) if d not in dirs]
            done = False
            # no wider than the pad across it, so inside the pin row the pad covers the stub; first the whole stub
            # must clear, then (strict False) only the part beyond the pad, for footprints that are tighter than the
            # rules themselves (TPS25947 bars: 0.19 mm)
            tight = not cu.free(p.GetEffectiveShape(layer), px, py, max(w, h) / 2, code, (layer,), clr, None, holes=False)
            tries = [(strict, sw, d) for strict in ((True, False) if tight else (True,)) for d in dirs
                     for sw in sorted({max(0.15, min(full, h if d[0] else w, 0.6)), max(0.15, min(0.25, h if d[0] else w))},
                                      reverse=True)]
            for strict, sw, (ux, uy) in tries:
                half = (w if ux else h) / 2
                off = 0 if strict else half + sw / 2
                bx, by = px + ux * off, py + uy * off
                s = half + 0.3
                while s <= half + longest and not done:
                    ex, ey = px + ux * s, py + uy * s
                    seg = pcbnew.SHAPE_SEGMENT(p.GetPosition(), pcbnew.VECTOR2I(mm(ex), mm(ey)), mm(sw))
                    out = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(mm(bx), mm(by)), pcbnew.VECTOR2I(mm(ex), mm(ey)), mm(sw))
                    if not cu.free(out, (bx + ex) / 2, (by + ey) / 2, s / 2 + sw, code, (layer,), clr, edge, holes=False):
                        break                               # the stub itself runs into something: next direction
                    if cu.free(disc(ex, ey, full), ex, ey, full / 2, code, (layer,), clr, edge, holes=False):
                        t = pcbnew.PCB_TRACK(board)
                        t.SetStart(p.GetPosition())
                        t.SetEnd(pcbnew.VECTOR2I(mm(ex), mm(ey)))
                        t.SetWidth(mm(sw))
                        t.SetLayer(layer)
                        t.SetNet(p.GetNet())
                        t.SetLocked(True)
                        board.Add(t)
                        cu.keep.append(seg)
                        cu.add(seg, code, (layer,))
                        n += 1
                        done = True
                    s += 0.1
                if done:
                    break
            if not done:
                missed.append('%s.%s' % (fp.GetReference(), p.GetNumber()))
    return n, missed


def clusters(board, codes):
    """The pads of each net in `codes`, grouped by what connects them now (tracks, vias, zones): {net code: [[pad]]}."""
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    pads = {}
    for p in board.GetPads():
        if p.GetNetCode() in codes:
            pads.setdefault(p.GetNetCode(), []).append(p)
    out = {}
    for code, ps in pads.items():
        groups, seen = [], set()
        uid = {p.m_Uuid.AsString(): p for p in ps}         # SWIG hands out a new wrapper per call: match on UUIDs
        for p in ps:
            if p.m_Uuid.AsString() in seen:
                continue
            g = {p.m_Uuid.AsString()} | {q.m_Uuid.AsString() for q in conn.GetConnectedItems(p)
                                         if q.GetClass() == 'PAD' and q.GetNetCode() == code}
            seen |= g
            groups.append([uid[u] for u in g if u in uid])
        out[code] = groups
    return out


def pad_name(p):
    return '%s.%s' % (p.GetParentFootprint().GetReference(), p.GetNumber())


def open_pads(board, codes):
    """Pads of the nets in `codes` that are not connected to the rest of their net: every pad outside the net's
    largest connected group (both pads of a 2-pad net). Returns (open connections, [pad])."""
    n, out = 0, []
    for code, groups in clusters(board, codes).items():
        if len(groups) < 2:
            continue
        n += len(groups) - 1
        groups.sort(key=len, reverse=True)
        rest = groups if len(groups[0]) == len(groups[1]) else groups[1:]
        out += [p for g in rest for p in g]
    return n, out


def escape(board, pads, sizes, avoid=(), clr=0.2, edge=1.0, reach=3.0):
    """Escape vias: a locked via beside each SMD pad in `pads` (in that order: the first get the best spots), with a
    short locked track to it, so the router can reach the pin from the other outer layer (or, by hand, from an
    inner layer) when the space around it on its own layer is taken. `sizes`: {net code: (track width, via diameter,
    via drill) mm}; the track is as wide as that where it fits, else narrower (down to 0.2 mm, no wider than the pad
    across). It runs straight from the pad to the via, or else first straight out along the pin, past the pad's
    end, then to the via (a pin boxed in by its neighbours, like the middle pins of a TPS25947). `avoid`: BOX2I
    areas (chip keep-outs) where a via is no use. Returns ([(pad name, via, [tracks])], pads that got none)."""
    cu = Copper(board)
    done, missed = [], []
    for p in pads:
        if p.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN):
            continue                                    # a through-hole pad is on every layer already
        code, net = p.GetNetCode(), p.GetNet()
        full, d, drill = sizes[code]
        fp = p.GetParentFootprint()
        layer = pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) and not p.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Cu
        bb = p.GetBoundingBox()
        px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
        across = max(0.2, min(w, h))
        widths = sorted({min(full, max(w, h)), min(full, across), min(full, across, 0.6), min(full, across, 0.4), 0.2},
                        reverse=True)
        ox, oy = px - pcbnew.ToMM(fp.GetPosition().x), py - pcbnew.ToMM(fp.GetPosition().y)
        # exits for a bent track: straight out of both ends of a long pad
        if h > w * 1.2:
            axis = [(0, 1), (0, -1)]
        elif w > h * 1.2:
            axis = [(1, 0), (-1, 0)]
        else:
            axis = []
        exits = [(px + ux * ((w if ux else h) / 2 + k), py + uy * ((w if ux else h) / 2 + k))
                 for ux, uy in axis for k in (0.1, 0.25, 0.4, 0.6)]

        def ring(cx, cy, r0):
            out = []
            for k in range(16):
                a = k * math.pi / 8
                ux, uy = math.cos(a), math.sin(a)
                outw = (ux * ox + uy * oy) / (math.hypot(ox, oy) or 1)
                s = 0
                while 0.25 * s <= reach:
                    out.append((s, -outw, cx + ux * (r0 + 0.25 * s), cy + uy * (r0 + 0.25 * s)))
                    s += 1
            return out

        def fits(path, tw):
            for (x0, y0), (x1, y1) in zip(path, path[1:]):
                seg = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(mm(x0), mm(y0)), pcbnew.VECTOR2I(mm(x1), mm(y1)), mm(tw))
                if not cu.free(seg, (x0 + x1) / 2, (y0 + y1) / 2, math.hypot(x1 - x0, y1 - y0) / 2 + tw, code, (layer,),
                               clr, edge, holes=False):
                    return False
            return True

        def via_ok(x, y):
            at = pcbnew.VECTOR2I(mm(x), mm(y))
            return not any(b.Contains(at) for b in avoid) and cu.free(disc(x, y, d), x, y, d / 2, code, OUTER, clr, edge)

        got = None
        # first straight to a via around the pad, then bent through an exit to a via around that exit
        for x, y in [(x, y) for _, _, x, y in sorted(ring(px, py, math.hypot(w, h) / 2 + d / 2 + clr))]:
            if via_ok(x, y):
                tw = next((tw for tw in widths if fits([(px, py), (x, y)], tw)), None)
                if tw:
                    got = [(px, py), (x, y)], tw
                    break
        if not got:
            for ex, ey in exits:
                for x, y in [(x, y) for _, _, x, y in sorted(ring(ex, ey, d / 2 + 0.05))]:
                    if via_ok(x, y):
                        tw = next((tw for tw in widths if fits([(px, py), (ex, ey), (x, y)], tw)), None)
                        if tw:
                            got = [(px, py), (ex, ey), (x, y)], tw
                            break
                if got:
                    break
        if not got:
            missed.append(pad_name(p))
            continue
        path, tw = got
        tracks = []
        for (x0, y0), (x1, y1) in zip(path, path[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
            t.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
            t.SetWidth(mm(tw))
            t.SetLayer(layer)
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)
            seg = pcbnew.SHAPE_SEGMENT(t.GetStart(), t.GetEnd(), mm(tw))
            cu.keep.append(seg)
            cu.add(seg, code, (layer,))
            tracks.append(t)
        x, y = path[-1]
        done.append((pad_name(p), add_via(board, cu, x, y, net, d, drill), tracks))
    return done, missed


def unused_escapes(board, marks, keep):
    """Remove the escape vias (and their tracks) that the router did not use: nothing but their own tracks touch
    the via. `marks`: [(net name, via x, via y, [(x0, y0, x1, y1) of its tracks])] in nm; leave out the pads that are
    still open (their via stays, for finishing by hand or in a later stage). Removed items go into `keep`. Returns
    the number removed."""
    by_net = {}
    for t in board.GetTracks():
        by_net.setdefault(t.GetNetname(), []).append(t)
    n = 0
    for net, vx, vy, segs in marks:
        items = by_net.get(net, [])
        via = next((t for t in items if t.Type() == pcbnew.PCB_VIA_T and t.GetPosition().x == vx and t.GetPosition().y == vy), None)
        if via is None:
            continue
        r = via.GetWidth(pcbnew.F_Cu) / 2
        at = via.GetPosition()
        mine = {frozenset({(a, b), (c, e)}) for a, b, c, e in segs}
        own = [t for t in items if t.Type() == pcbnew.PCB_TRACE_T and
               frozenset({(t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)}) in mine]
        ends = {pt for a, b, c, e in segs for pt in ((a, b), (c, e))}
        others = [t for t in items if t.Type() == pcbnew.PCB_TRACE_T and t not in own and
                  (min((t.GetStart() - at).EuclideanNorm(), (t.GetEnd() - at).EuclideanNorm()) <= r or
                   any(abs(t.GetStart().x - x) + abs(t.GetStart().y - y) < 1000 or abs(t.GetEnd().x - x) + abs(t.GetEnd().y - y) < 1000
                       for x, y in ends - {(segs[0][0], segs[0][1])}))]
        if others:
            continue
        for t in [via] + own:
            board.Remove(t)
            keep.append(t)
        n += 1
    return n


def stitch(board, net, pitch=5.0, d=0.6, drill=0.3, clr=0.3, edge=1.5):
    """GND vias on a `pitch` mm grid wherever they clear everything else."""
    cu = Copper(board)
    ni = board.FindNet(net)
    x0, y0, x1, y1 = cu.edge
    n = 0
    y = y0 + pitch / 2
    while y < y1:
        x = x0 + pitch / 2
        while x < x1:
            c = disc(x, y, d)
            if cu.free(c, x, y, d / 2, -2, OUTER, clr, edge):     # -2: clears GND copper too, no via on a pad
                add_via(board, cu, x, y, ni, d, drill).SetLocked(False)
                n += 1
            x += pitch
        y += pitch
    return n


def main():
    import argparse
    import os
    import subprocess
    import sys
    ap = argparse.ArgumentParser(description='Add GND stitching vias to a fully routed board.')
    ap.add_argument('pcb')
    ap.add_argument('--pitch', type=float, default=5.0)
    args = ap.parse_args()
    base = os.path.splitext(args.pcb)[0]
    keep = {f: open(f, encoding='utf-8').read() for f in (base + '.kicad_pro', base + '.kicad_prl') if os.path.exists(f)}
    board = pcbnew.LoadBoard(args.pcb)
    print('GND stitching vias: %d' % stitch(board, 'GND', args.pitch))
    pcbnew.SaveBoard(args.pcb, board)
    cli = os.path.join(os.path.dirname(sys.executable), 'kicad-cli.exe' if os.name == 'nt' else 'kicad-cli')
    subprocess.run([cli, 'pcb', 'drc', '--refill-zones', '--save-board', '-o', base + '-stitch-drc.rpt', args.pcb],
                   check=True, stdout=subprocess.DEVNULL)
    os.remove(base + '-stitch-drc.rpt')
    for f, text in keep.items():                 # SaveBoard rewrites the project file and drops its schematic sections
        open(f, 'w', encoding='utf-8').write(text)


if __name__ == '__main__':
    main()
