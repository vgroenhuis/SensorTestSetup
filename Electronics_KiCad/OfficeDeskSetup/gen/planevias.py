"""Vias to the inner planes, placed with KiCad's own shape collision tests (run with KiCad's Python).

fanout(): Freerouting 2.5 treats the nets of a plane as connected by the plane and never adds the vias from SMD pads
down to it, so every SMD pad on a plane net gets one here, before routing: a via beside the pad with a short track,
or a few vias inside a large (exposed) pad.

stitch(): GND vias on a grid wherever there is room, after routing, so the GND pours on F.Cu and B.Cu are tied to
the In1 GND plane everywhere instead of hanging on single pads.
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

    def free(self, shape, x, y, r, net, layers, clr, edge):
        """`shape` (around x, y, radius r mm) clears all copper of other nets on `layers` by clr mm."""
        x0, y0, x1, y1 = self.edge
        if not (x0 + edge + r <= x <= x1 - edge - r and y0 + edge + r <= y <= y1 - edge - r):
            return False
        for s, n, ls, extra, hole in self.near(x, y, r + clr + 1):
            if n == net and n >= 0 and not hole:       # holes keep their spacing whatever the net
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


def fanout(board, nets, d=0.6, drill=0.3, width=0.3, clr=0.2, edge=1.0):
    """A via to the plane for every SMD pad on `nets`. Returns (vias, pads that got none)."""
    cu = Copper(board)
    vias, missed = 0, []
    for fp in board.GetFootprints():
        fc = fp.GetPosition()
        for p in fp.Pads():
            if p.GetNetname() not in nets or p.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN):
                continue
            net, code = p.GetNet(), p.GetNetCode()
            layer = pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) and not p.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Cu
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
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(p.GetPosition())
                t.SetEnd(pcbnew.VECTOR2I(mm(x), mm(y)))
                t.SetWidth(mm(width))
                t.SetLayer(layer)
                t.SetNet(net)
                t.SetLocked(True)
                board.Add(t)
                cu.keep.append(seg)
                cu.add(seg, code, (layer,))
                add_via(board, cu, x, y, net, d, drill)
                vias += 1
                break
            else:
                missed.append('%s.%s' % (fp.GetReference(), p.GetNumber()))
    return vias, missed


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
