"""credits.py BOARD [OUT]: put the credit texts (pcbgen.place_credits) on a finished board."""
import os, shutil, sys
G = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, G)
import pcbnew, pcbgen, route
src = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else src
b = pcbnew.LoadBoard(src)
pcbgen.remove_credits(b)
tft = None
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Dwgs_User and isinstance(d, pcbnew.PCB_SHAPE):     # the TFT outline: 4 segments
        q = pcbgen.bbox_mm(d.GetBoundingBox())
        tft = q if tft is None else (min(tft[0], q[0]), min(tft[1], q[1]), max(tft[2], q[2]), max(tft[3], q[3]))
print('tft', tft)
print(pcbgen.place_credits(b, tft) or 'credits placed')
for d in b.GetDrawings():
    if isinstance(d, pcbnew.PCB_TEXT) and d.GetText() in [pcbgen.CREDITS_FRONT] + pcbgen.CREDITS_BACK:
        print(repr(d.GetText()), [round(v, 1) for v in pcbgen.bbox_mm(d.GetBoundingBox())])
pro = os.path.splitext(src)[0] + '.kicad_pro'
if out != src:
    shutil.copy(pro, os.path.splitext(out)[0] + '.kicad_pro'); pro = os.path.splitext(out)[0] + '.kicad_pro'
route.save(b, out, pro)
