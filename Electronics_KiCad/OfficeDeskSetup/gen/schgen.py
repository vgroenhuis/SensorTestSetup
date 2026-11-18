"""Small KiCad schematic writer: parts are placed in titled blocks and connected by net name.

Every pin gets a short wire with a net label (or a power symbol); nets used on more than one
sheet become global labels. The block layout is automatic. Output: KiCad 10 files; `v7=True`
writes the same content in the KiCad 7 format (only used to run ERC with an older kicad-cli).
"""
import math
import os
import re
import uuid

NS = uuid.UUID('7d6f2201-bb16-433b-a012-f387f0c014ff')      # uuid of the root sheet
POWER_SYMBOLS = {'GND': 'power:GND', '+3V3': 'power:+3V3', '+5V': 'power:+5V'}
NC = 'NC'
DEBUG = bool(os.environ.get('SCHGEN_DEBUG'))
STUB = 2.54
CHAR = 1.0          # estimated label width per character, mm


class Sym(str):
    """A bare (unquoted) s-expression token."""


def parse(text):
    stack = [[]]
    for m in re.finditer(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+', text):
        s = m.group(0)
        if s == '(':
            stack.append([])
        elif s == ')':
            done = stack.pop()
            stack[-1].append(done)
        elif s[0] == '"':
            stack[-1].append(s[1:-1].replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\'))
        else:
            stack[-1].append(Sym(s))
    return stack[0][0]


def num(v):
    if isinstance(v, int):
        return str(v)
    s = ('%.4f' % v).rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def atom(x):
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, str):
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    return num(x)


def flat(x):
    return '(' + ' '.join(flat(e) for e in x) + ')' if isinstance(x, list) else atom(x)


def dump(x, ind=0):
    if not isinstance(x, list):
        return atom(x)
    if all(not isinstance(e, list) for e in x) or x[0] in ('pts', 'font', 'stroke', 'fill') and len(flat(x)) < 110:
        return flat(x)
    out = '(' + atom(x[0])
    for e in x[1:]:
        out += ('\n' + '\t' * (ind + 1) + dump(e, ind + 1)) if isinstance(e, list) else ' ' + atom(e)
    return out + '\n' + '\t' * ind + ')'


def find(x, name):
    return [e for e in x if isinstance(e, list) and e and e[0] == name]


def first(x, name):
    f = find(x, name)
    return f[0] if f else None


def S(name, *items):
    return [Sym(name), *items]


def yes(b):
    return Sym('yes' if b else 'no')


def uid(*key):
    return str(uuid.uuid5(NS, '/'.join(str(k) for k in key)))


def snap(v, grid=1.27):
    return round(round(v / grid) * grid, 4)


def font(size=1.27):
    return S('font', S('size', size, size))


# ---------------------------------------------------------------------------------------------
# Symbol libraries
# ---------------------------------------------------------------------------------------------

class Library:
    def __init__(self, kicad_symbols, espressif_sym, project_lib='OfficeDeskSetup'):
        self.dir = kicad_symbols
        self.esp_path = espressif_sym
        self.project_lib = project_lib
        self.custom = {}
        self.cache = {}
        self.esp = None

    def raw(self, lib, name):
        if lib == self.project_lib:
            return self.custom[name]
        if lib == 'PCM_Espressif':
            if self.esp is None:
                self.esp = parse(open(self.esp_path).read())
            sym = next(s for s in find(self.esp, 'symbol') if s[1] == name)
        else:
            path = os.path.join(self.dir, lib + '.kicad_symdir', name + '.kicad_sym')
            if os.path.exists(path):
                sym = first(parse(open(path).read()), 'symbol')
            else:
                whole = parse(open(os.path.join(self.dir, lib + '.kicad_sym')).read())
                sym = next(s for s in find(whole, 'symbol') if s[1] == name)
        ext = first(sym, 'extends')
        if not ext:
            return sym
        parent = self.raw(lib, ext[1])          # flatten a derived symbol: the parent's body, own properties
        props = {p[1]: p for p in find(sym, 'property')}
        out = [Sym('symbol'), name]
        for e in parent[2:]:
            if isinstance(e, list) and e[0] == 'property':
                out.append(props.pop(e[1], e))
            elif isinstance(e, list) and e[0] == 'symbol':
                out.append([e[0], name + e[1][len(parent[1]):], *e[2:]])
            else:
                out.append(e)
        at = next(i for i, e in enumerate(out) if isinstance(e, list) and e[0] == 'symbol')
        out[at:at] = list(props.values())
        return out

    def get(self, lib_id):
        if lib_id not in self.cache:
            lib, name = lib_id.split(':')
            self.cache[lib_id] = LibSymbol(lib_id, self.raw(lib, name))
        return self.cache[lib_id]

    def box(self, name, left, right, ref='U', footprint='', datasheet='', description=''):
        """A rectangular symbol; left/right: lists of (number, name, type) or None for a gap."""
        rows = max(len(left), len(right))
        width = snap(max(12.7, 6 + 1.1 * max(len(l[1]) if l else 0 for l in left)
                         + 1.1 * max([len(r[1]) if r else 0 for r in right] or [0])), 5.08)
        top = snap((rows - 1) * 2.54 / 2, 2.54)
        half = width / 2

        def prop(key, value, x, y, hide=False, just=None):
            p = S('property', key, value, S('at', x, y, 0), S('show_name', yes(False)), S('do_not_autoplace', yes(False)))
            if hide:
                p.append(S('hide', yes(True)))
            eff = S('effects', font())
            if just:
                eff.append(S('justify', Sym(just)))
            p.append(eff)
            return p

        pins = []
        for side, lst in ((-1, left), (1, right)):
            for i, p in enumerate(lst):
                if p:
                    pins.append(S('pin', Sym(p[2]), Sym('line'), S('at', side * (half + 2.54), top - i * 2.54, 0 if side < 0 else 180),
                                  S('length', 2.54), S('name', p[1], S('effects', font())), S('number', str(p[0]), S('effects', font()))))
        sym = S('symbol', name, S('pin_names', S('offset', 1.016)), S('exclude_from_sim', yes(False)), S('in_bom', yes(True)),
                S('on_board', yes(True)), S('in_pos_files', yes(True)), S('duplicate_pin_numbers_are_jumpers', yes(False)),
                prop('Reference', ref, -half, top + 5.08, just='left'), prop('Value', name, -half, top + 3.3, just='left'),
                prop('Footprint', footprint, 0, 0, hide=True), prop('Datasheet', datasheet, 0, 0, hide=True),
                prop('Description', description, 0, 0, hide=True),
                S('symbol', name + '_0_1', S('rectangle', S('start', -half, top + 2.54), S('end', half, top - rows * 2.54),
                                              S('stroke', S('width', 0.254), S('type', Sym('default'))), S('fill', S('type', Sym('background'))))),
                S('symbol', name + '_1_1', *pins), S('embedded_fonts', yes(False)))
        self.custom[name] = sym
        return self.project_lib + ':' + name

    def write_project_lib(self, path):
        tree = S('kicad_symbol_lib', S('version', 20251024), S('generator', 'schgen'), S('generator_version', '10.0'),
                 *[self.custom[k] for k in sorted(self.custom)])
        open(path, 'w').write(dump(tree) + '\n')


class LibSymbol:
    def __init__(self, lib_id, tree):
        self.lib_id = lib_id
        self.tree = [tree[0], lib_id, *tree[2:]]
        self.props = {p[1]: p for p in find(tree, 'property')}
        self.pins = []
        xs, ys = [], []
        for unit in find(tree, 'symbol'):
            u, style = (int(v) for v in unit[1].rsplit('_', 2)[1:])
            if style > 1:
                continue
            for p in find(unit, 'pin'):
                at = first(p, 'at')
                hide = first(p, 'hide')
                self.pins.append(dict(unit=u, type=str(p[1]), name=first(p, 'name')[1], num=first(p, 'number')[1],
                                      x=float(at[1]), y=float(at[2]), a=int(float(at[3])), len=float(first(p, 'length')[1]),
                                      hide=bool(hide and hide[1] == 'yes')))
            for g in unit[2:]:
                if isinstance(g, list) and g[0] != 'pin':
                    for pt in self._points(g):
                        xs.append(pt[0])
                        ys.append(pt[1])
        self.units = max([p['unit'] for p in self.pins] or [1])
        self.gx = (min(xs or [0]), max(xs or [0]))
        self.gy = (min(ys or [0]), max(ys or [0]))

    def _points(self, g):
        out = []
        for e in g[1:]:
            if isinstance(e, list):
                if e[0] in ('start', 'end', 'mid', 'xy', 'center', 'at'):
                    out.append((float(e[1]), float(e[2])))
                elif e[0] == 'pts':
                    out += self._points(e)
        return out


def rotate(x, y, rot):
    """Library coordinates (y up) to schematic offsets (y down) for a symbol rotation."""
    return {0: (x, -y), 90: (-y, -x), 180: (-x, y), 270: (y, x)}[rot]


# ---------------------------------------------------------------------------------------------
# Design, sheets and blocks
# ---------------------------------------------------------------------------------------------

class Design:
    def __init__(self, library, project, title, rev, date, company=''):
        self.lib = library
        self.project = project
        self.meta = dict(title=title, rev=rev, date=date, company=company)
        self.global_nets = set()
        self.reset()

    def reset(self):
        self.sheets = []
        self.refs = {}
        self.netlist = {}           # ref -> {pin number: net}
        self.net_sheets = {}        # net -> set of sheet names
        self.parts = []

    def sheet(self, name, title, paper='A3'):
        sh = Sheet(self, name, title, paper, len(self.sheets) + 2)
        self.sheets.append(sh)
        return sh

    def ref(self, prefix):
        self.refs[prefix] = self.refs.get(prefix, 0) + 1
        return prefix + str(self.refs[prefix])

    def settle_globals(self):
        self.global_nets = {n for n, s in self.net_sheets.items() if len(s) > 1 and n not in POWER_SYMBOLS}


PAPER = {'A4': (297, 210), 'A3': (420, 297), 'A2': (594, 420), 'A1': (841, 594)}


class Sheet:
    def __init__(self, design, name, title, paper, page):
        self.d = design
        self.name = name
        self.title = title
        self.paper = paper
        self.page = page
        self.uuid = uid('sheet', name)
        self.path = '/%s/%s' % (NS, self.uuid)
        self.blocks = []
        self.items = []
        self.used = {}
        self.count = 0

    def block(self, title):
        b = Block(self, title)
        self.blocks.append(b)
        return b

    def uid(self, kind):
        self.count += 1
        return uid(self.name, kind, self.count)

    # -- primitives ---------------------------------------------------------------------------
    def wire(self, a, b):
        self.items.append(S('wire', S('pts', S('xy', a[0], a[1]), S('xy', b[0], b[1])),
                            S('stroke', S('width', 0), S('type', Sym('default'))), S('uuid', self.uid('wire'))))

    def text(self, s, x, y, size=1.27, bold=False):
        f = font(size)
        if bold:
            f.append(S('bold', yes(True)))
        self.items.append(S('text', s, S('exclude_from_sim', yes(False)), S('at', x, y, 0),
                            S('effects', f, S('justify', Sym('left'), Sym('top'))), S('uuid', self.uid('text'))))

    def rect(self, x0, y0, x1, y1):
        self.items.append(S('rectangle', S('start', x0, y0), S('end', x1, y1), S('stroke', S('width', 0.15), S('type', Sym('dash'))),
                            S('fill', S('type', Sym('none'))), S('uuid', self.uid('rect'))))

    def label(self, net, x, y, d):
        angle = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[d]
        just = S('justify', Sym('right' if angle in (180, 270) else 'left'))
        if net in self.d.global_nets:
            self.items.append(S('global_label', net, S('shape', Sym('passive')), S('at', x, y, angle), S('fields_autoplaced', yes(True)),
                                S('effects', font(1.0), just), S('uuid', self.uid('glabel')),
                                S('property', 'Intersheetrefs', '${INTERSHEET_REFS}', S('at', x, y, 0), S('hide', yes(True)),
                                  S('show_name', yes(False)), S('do_not_autoplace', yes(False)), S('effects', font()))))
        else:
            just.append(Sym('bottom'))
            self.items.append(S('label', net, S('at', x, y, angle), S('effects', font(), just), S('uuid', self.uid('label'))))

    def label_len(self, net):
        return len(net) * CHAR * (0.85 if net in self.d.global_nets else 1) + (4 if net in self.d.global_nets else 1)

    def attach(self, pt, d, net, stub=STUB):
        """Connect a pin end to a net; returns how far the drawing reaches beyond the pin."""
        self.d.net_sheets.setdefault(net, set()).add(self.name)
        if net == NC:
            self.items.append(S('no_connect', S('at', pt[0], pt[1]), S('uuid', self.uid('nc'))))
            return 1.5
        end = (pt[0] + d[0] * stub, pt[1] + d[1] * stub)
        self.wire(pt, end)
        if net in POWER_SYMBOLS:
            up = net != 'GND'
            rot = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[d]
            if up:
                rot = (rot + 180) % 360
            self.place(POWER_SYMBOLS[net], '#PWR', net, end[0], end[1], rot=rot, power_dir=d)
            return STUB + 4 + (len(net) * CHAR if d[0] else 2.5)
        self.label(net, end[0], end[1], d)
        return stub + self.label_len(net)

    def place(self, lib_id, prefix, value, x, y, rot=0, unit=1, ref=None, fields=None, dnp=False, power_dir=None,
              text=None, in_bom=True):
        """Write one symbol instance; returns (ref, library symbol)."""
        sym = self.d.lib.get(lib_id)
        self.used[lib_id] = sym
        ref = ref or self.d.ref(prefix)
        fields = dict(fields or {})
        power = prefix == '#PWR'

        def prop(key, val, px, py, angle=0, hide=False, just=None):
            p = S('property', key, val, S('at', snap(px, 0.01), snap(py, 0.01), angle))
            if hide:
                p.append(S('hide', yes(True)))
            p += [S('show_name', yes(False)), S('do_not_autoplace', yes(False))]
            eff = S('effects', font())
            if just:
                eff.append(S('justify', Sym(just)))
            p.append(eff)
            return p

        def lib_at(key):
            at = first(sym.props[key], 'at')
            dx, dy = rotate(float(at[1]), float(at[2]), rot)
            return x + dx, y + dy

        def lib_just(key):
            j = first(first(sym.props[key], 'effects'), 'justify')
            return ' '.join(j[1:]) if j else None

        props = []
        if power:
            d = power_dir
            reach = 3.2 + (len(value) * CHAR / 2 if d[0] else 0.6)
            props.append(prop('Reference', ref, x, y, hide=True))
            props.append(prop('Value', value, x + d[0] * reach, y + d[1] * reach, 90 if rot in (90, 270) else 0,
                              hide=(value == 'GND' and d != (0, 1))))
        elif text:      # explicit (dx, dy, angle, justify) for reference and value
            props.append(prop('Reference', ref, x + text[0][0], y + text[0][1], text[0][2], just=text[0][3]))
            props.append(prop('Value', value, x + text[1][0], y + text[1][1], text[1][2], just=text[1][3]))
        else:
            props.append(prop('Reference', ref, *lib_at('Reference'), just=lib_just('Reference')))
            props.append(prop('Value', value, *lib_at('Value'), just=lib_just('Value')))
        for key in ('Footprint', 'Datasheet', 'Description'):
            val = fields.pop(key, sym.props[key][2] if key in sym.props else '')
            props.append(prop(key, val, x, y, hide=True))
        for key, val in fields.items():
            props.append(prop(key, val, x, y, hide=True))
        pins = [S('pin', p['num'], S('uuid', uid(self.name, ref, unit, p['num'], i)))
                for i, p in enumerate(sym.pins) if p['unit'] in (0, unit)]
        self.items.append(S('symbol', S('lib_id', lib_id), S('at', x, y, rot), S('unit', unit), S('body_style', 1),
                            S('exclude_from_sim', yes(False)), S('in_bom', yes(in_bom and not prefix.startswith('#'))), S('on_board', yes(True)),
                            S('in_pos_files', yes(True)), S('dnp', yes(dnp)), S('uuid', uid(self.name, 'sym', ref, unit)),
                            *props, *pins,
                            S('instances', S('project', self.d.project, S('path', self.path, S('reference', ref), S('unit', unit))))))
        if not prefix.startswith('#'):
            self.d.parts.append(dict(ref=ref, value=value, lib_id=lib_id, sheet=self.name, unit=unit, dnp=dnp,
                                     footprint=props[2][2], fields=fields))
        return ref, sym

    def part(self, lib_id, prefix, value, x, y, nets, rot=0, unit=1, ref=None, **kw):
        """Place a symbol and connect its pins. nets: {pin number or name: net}, or a list in pin-number order.
        Returns (ref, extents) with extents = how far the drawing reaches left, right, up, down of (x, y)."""
        sym = self.d.lib.get(lib_id)
        mine = [p for p in sym.pins if p['unit'] in (0, unit)]
        if isinstance(nets, (list, tuple)):
            nets = {str(i + 1): n for i, n in enumerate(nets)}
        nets = dict(nets)
        ref, _ = self.place(lib_id, prefix, value, x, y, rot=rot, unit=unit, ref=ref, **kw)
        ext = [-sym.gx[0], sym.gx[1], sym.gy[1], -sym.gy[0]] if rot == 0 else [3.0, 3.0, 3.0, 3.0]
        if rot == 0 and not kw.get('text'):
            for key, s in (('Reference', ref), ('Value', value)):       # room for the reference and value texts
                at = first(sym.props[key], 'at')
                just = first(first(sym.props[key], 'effects'), 'justify')
                just = just[1] if just and just[1] in ('left', 'right') else 'centre'
                w = len(s) * CHAR + 1
                tx = float(at[1])
                lo, hi = {'left': (tx, tx + w), 'right': (tx - w, tx), 'centre': (tx - w / 2, tx + w / 2)}[just]
                ext[0], ext[1] = max(ext[0], -lo), max(ext[1], hi)
                ext[2], ext[3] = max(ext[2], float(at[2]) + 1), max(ext[3], -float(at[2]) + 1)
        table = self.d.netlist.setdefault(ref, {})
        visible = {}
        for p in mine:
            if p['hide']:
                continue
            key = p['num'] if p['num'] in nets else p['name']
            if key not in nets:
                if p['type'] == 'no_connect':
                    nets[key] = NC
                else:
                    raise KeyError('%s %s: pin %s (%s) has no net' % (ref, value, p['num'], p['name']))
            if key == p['name'] and p['type'] != 'no_connect' and sum(1 for o in mine if o['name'] == key and not o['hide']) > 1:
                raise KeyError('%s %s: pin name %s is not unique, use numbers' % (ref, value, key))
            net = nets[key]
            nets.setdefault('_used', set()).add(key)
            dx, dy = rotate(p['x'], p['y'], rot)
            ax, ay = rotate(math.cos(math.radians(p['a'])), math.sin(math.radians(p['a'])), rot)
            d = (-round(ax), -round(ay))
            stub = STUB
            if d[0] and net != NC and net not in POWER_SYMBOLS and net not in self.d.global_nets:
                # a global label on the pin just above would cover this label's text: start beyond it
                for o in mine:
                    if o is not p and not o['hide'] and rotate(o['x'], o['y'], rot) == (dx, dy - 2.54):
                        other = nets.get(o['num'], nets.get(o['name']))
                        if other in self.d.global_nets:
                            stub = snap(STUB + self.label_len(other) + 1.27, 2.54)
            reach = self.attach((snap(x + dx, 0.01), snap(y + dy, 0.01)), d, net, stub)
            table[p['num']] = None if net == NC else net
            visible[(p['x'], p['y'])] = table[p['num']]
            i = 0 if d[0] < 0 else 1 if d[0] > 0 else 2 if d[1] < 0 else 3
            ext[i] = max(ext[i], abs(dx if d[0] else dy) + reach)
            for j, off in ((0, -dx), (1, dx), (2, -dy), (3, dy)):       # room for the label's height
                ext[j] = max(ext[j], off + (1.5 if j < 2 else 2.0))
        for p in mine:
            if p['hide']:
                if p['type'] == 'power_in' and (p['x'], p['y']) not in visible:
                    raise ValueError('%s: hidden power pin %s' % (ref, p['name']))
                table[p['num']] = visible.get((p['x'], p['y']))
        unknown = set(nets) - nets.get('_used', set()) - {'_used'}
        if unknown:
            raise KeyError('%s %s: no such pins %s' % (ref, value, sorted(unknown)))
        return ref, ext

    # -- output -------------------------------------------------------------------------------
    def layout(self):
        """Shelf-pack the blocks onto the sheet."""
        w, h = PAPER[self.paper]
        x, y, shelf = 12.7, 15.24, 0
        for b in self.blocks:
            bw, bh = b.size()
            if x + bw > w - 10 and x > 12.7:
                x, y, shelf = 12.7, y + shelf + 5.08, 0
            b.origin = (snap(x, 2.54), snap(y, 2.54))
            x += bw + 5.08
            shelf = max(shelf, bh)
            if DEBUG:
                print('   %-9s %-4s %4.0f x %4.0f  %s' % (self.name, self.paper, bw, bh, b.title))
            if y + bh > h - 30 or x - 5.08 > w - 8:
                raise ValueError('sheet %s: block "%s" does not fit on %s (x %.0f, y %.0f)' % (self.name, b.title, self.paper, x, y + bh))

    def render(self):
        self.items, self.used, self.count = [], {}, 0
        for paper in ('A3', 'A2', 'A1'):
            self.paper = paper
            try:
                self.layout()
                break
            except ValueError:
                if paper == 'A1':
                    raise
        for b in self.blocks:
            b.render()

    def tree(self):
        m = self.d.meta
        return S('kicad_sch', S('version', 20260306), S('generator', 'eeschema'), S('generator_version', '10.0'),
                 S('uuid', self.uuid), S('paper', self.paper),
                 S('title_block', S('title', '%s: %s' % (m['title'], self.title)), S('date', m['date']), S('rev', m['rev']),
                   S('company', m['company'])),
                 S('lib_symbols', *[self.used[k].tree for k in sorted(self.used)]),
                 *self.items, S('embedded_fonts', yes(False)))


class Block:
    """A titled frame; items stack downwards in columns."""

    def __init__(self, sheet, title):
        self.sh = sheet
        self.title = title
        self.cols = [[]]
        self.origin = (0, 0)
        self._size = None

    def col(self):
        self.cols.append([])
        return self

    def _add(self, item):
        self.cols[-1].append(item)
        self._size = None
        return item

    def _run(self, kind, **kw):
        """The current row table / strip, if the last item is one of that kind."""
        last = self.cols[-1][-1] if self.cols[-1] else None
        if isinstance(last, kind) and all(getattr(last, k) == v for k, v in kw.items()):
            return last
        return self._add(kind(self, **kw))

    # -- items --------------------------------------------------------------------------------
    def ic(self, lib_id, prefix, value, nets, flow=False, **kw):
        if flow:
            self._run(Flow).parts.append((lib_id, prefix, value, nets, kw))
        else:
            self._add(Ic(self, lib_id, prefix, value, nets, kw))

    def row(self, lib_id, prefix, value, a, b, **kw):
        """A two-pin part drawn horizontally: net a on pin 1, net b on pin 2."""
        self._run(Rows).parts.append((lib_id, prefix, value, a, b, kw))

    def strip(self, lib_id, prefix, value, a, b, **kw):
        """A two-pin part drawn vertically (pin 1 up), side by side with its neighbours."""
        self._run(Strip).parts.append((lib_id, prefix, value, a, b, kw))

    def note(self, text):
        self._add(Note(self, text))

    def gap(self, h=2.54):
        self._add(Gap(self, h))

    # -- layout -------------------------------------------------------------------------------
    def size(self):
        if self._size is None:
            self.sh.d.lib  # (sizes come from a dry render)
            saved = (self.sh.items, self.sh.d.refs.copy(), dict(self.sh.d.netlist), list(self.sh.d.parts), self.sh.count,
                     {k: set(v) for k, v in self.sh.d.net_sheets.items()})
            self.sh.items = []
            self._size = self.render(dry=True)
            self.sh.items, self.sh.d.refs, self.sh.d.netlist, self.sh.d.parts, self.sh.count, self.sh.d.net_sheets = saved
        return self._size

    def render(self, dry=False):
        ox, oy = self.origin
        x = ox + 2.54
        top = oy + 7.62
        bottom = top
        for col in self.cols:
            y = top
            width = 0
            for item in col:
                w, h = item.draw(snap(x, 2.54), snap(y, 2.54))
                y = snap(y, 2.54) + h + 2.54
                width = max(width, w)
            x = snap(x, 2.54) + width + 5.08
            bottom = max(bottom, y)
        w = max(x - 2.54 - ox, len(self.title) * 1.9 + 6)
        h = bottom - oy
        if not dry:
            self.sh.rect(ox, oy, ox + w, oy + h)
            self.sh.text(self.title, ox + 1.27, oy + 1.27, size=2.0, bold=True)
        return snap(w, 2.54) + 2.54, snap(h, 2.54) + 2.54


def measure(sh, lib_id, prefix, value, nets, kw):
    """Extents (left, right, up, down) of a part with its labels, from a dry placement at the origin."""
    saved = (sh.items, sh.d.refs.copy(), sh.count, list(sh.d.parts))
    sh.items = []
    _, ext = sh.part(lib_id, prefix, value, 0, 0, nets, **kw)
    sh.items, sh.d.refs, sh.count, sh.d.parts = saved
    left, right, up, down = (snap(e + 1.27, 2.54) for e in ext)
    return left, right, up + 1.27, down


class Ic:
    def __init__(self, block, lib_id, prefix, value, nets, kw):
        self.b, self.lib_id, self.prefix, self.value, self.nets, self.kw = block, lib_id, prefix, value, nets, kw

    def draw(self, x, y):
        sh = self.b.sh
        left, right, up, down = measure(sh, self.lib_id, self.prefix, self.value, self.nets, self.kw)
        sh.part(self.lib_id, self.prefix, self.value, x + left, y + up, self.nets, **self.kw)
        return left + right, up + down


class Flow:
    """Small parts side by side, wrapping to a new line."""

    def __init__(self, block, width=115):
        self.b = block
        self.width = width
        self.parts = []

    def draw(self, x, y):
        sh = self.b.sh
        cx, cy, line, widest = 0, 0, 0, 0
        for part in self.parts:
            left, right, up, down = measure(sh, *part)
            if cx and cx + left + right > self.width:
                cx, cy, line = 0, cy + line + 2.54, 0
            sh.part(part[0], part[1], part[2], x + cx + left, y + cy + up, part[3], **part[4])
            cx += left + right + 2.54
            line = max(line, up + down)
            widest = max(widest, cx)
        return widest, cy + line


TEXT_H = {0: ((0, -2.4, 90, None), (0, 2.6, 90, None)), 1: ((0, -2.4, 0, None), (0, 2.6, 0, None))}


class Rows:
    PITCH = 7.62

    def __init__(self, block):
        self.b = block
        self.parts = []

    def draw(self, x, y):
        sh = self.b.sh
        lmax = max(self._len(p[3]) for p in self.parts)
        rmax = max(self._len(p[4]) for p in self.parts)
        cx = snap(x + lmax + STUB + 5.08, 2.54)
        for i, (lib_id, prefix, value, a, b, kw) in enumerate(self.parts):
            sym = sh.d.lib.get(lib_id)
            native_h = len({p['y'] for p in sym.pins}) == 1
            rot = 0 if native_h else 90
            # pin 1 must end up on the left
            one = next(p for p in sym.pins if p['num'] in ('1', 'A', 'K') or p is sym.pins[0])
            if rotate(one['x'], one['y'], rot)[0] > 0:
                rot = (rot + 180) % 360
            ta = 90 if rot in (90, 270) else 0
            text = ((0, -2.5, ta, None), (0, 2.7, ta, None))
            nets = {sym.pins[0]['num']: a, sym.pins[1]['num']: b}
            sh.part(lib_id, prefix, value, cx, snap(y + 5.08 + i * self.PITCH, 2.54), nets, rot=rot, text=text, **kw)
        return (cx - x) + 5.08 + STUB + rmax, len(self.parts) * self.PITCH + 2.54

    def _len(self, net):
        if net in POWER_SYMBOLS:
            return 4 + len(net) * CHAR
        return self.b.sh.label_len(net)


class Strip:
    PITCH = 15.24
    WRAP = 10

    def __init__(self, block):
        self.b = block
        self.parts = []

    def draw(self, x, y):
        sh = self.b.sh
        total_h = 0
        for start in range(0, len(self.parts), self.WRAP):
            chunk = self.parts[start:start + self.WRAP]
            up = max(self._len(p[3]) for p in chunk)
            down = max(self._len(p[4]) for p in chunk)
            cy = snap(y + total_h + up + STUB + 5.08, 2.54)
            for i, (lib_id, prefix, value, a, b, kw) in enumerate(chunk):
                sym = sh.d.lib.get(lib_id)
                native_v = len({p['x'] for p in sym.pins}) == 1
                rot = 0 if native_v else 90
                one = sym.pins[0]
                if rotate(one['x'], one['y'], rot)[1] > 0:      # pin 1 must be up
                    rot = (rot + 180) % 360
                ta = 90 if rot in (90, 270) else 0
                text = ((2.3, -1.3, ta, None if ta else 'left'), (2.3, 1.3, ta, None if ta else 'left'))
                if ta:      # rotated symbols: centred text to the right of the body
                    w = max(len(value), 3) * CHAR / 2
                    text = ((2.3 + 1.5, -1.3, ta, None), (2.3 + w, 1.3, ta, None))
                nets = {sym.pins[0]['num']: a, sym.pins[1]['num']: b}
                sh.part(lib_id, prefix, value, snap(x + 2.54 + i * self.PITCH, 2.54), cy, nets, rot=rot, text=text, **kw)
            total_h = (cy - y) + 5.08 + STUB + down + 2.54
        return min(len(self.parts), self.WRAP) * self.PITCH, total_h

    def _len(self, net):
        if net in POWER_SYMBOLS:
            return 6
        return self.b.sh.label_len(net)


class Note:
    def __init__(self, block, text):
        self.b, self.text = block, text

    def draw(self, x, y):
        self.b.sh.text(self.text, x, y)
        lines = self.text.split('\n')
        return max(len(l) for l in lines) * 0.95 + 2, len(lines) * 2.1 + 1


class Gap:
    def __init__(self, block, h):
        self.h = h

    def draw(self, x, y):
        return 0, self.h


# ---------------------------------------------------------------------------------------------
# Root sheet and files
# ---------------------------------------------------------------------------------------------

def root_tree(design, notes):
    m = design.meta
    items = []
    n = [0]

    def nid(kind):
        n[0] += 1
        return uid('root', kind, n[0])

    def text(s, x, y, size=1.27, bold=False):
        f = font(size)
        if bold:
            f.append(S('bold', yes(True)))
        items.append(S('text', s, S('exclude_from_sim', yes(False)), S('at', x, y, 0),
                       S('effects', f, S('justify', Sym('left'), Sym('top'))), S('uuid', nid('text'))))

    text(m['title'], 20.32, 17.78, size=4, bold=True)
    text(notes, 20.32, 27.94)
    x, y = 20.32, 124.46
    for sh in design.sheets:
        def prop(key, val, py, just):
            return S('property', key, val, S('at', x, py, 0), S('show_name', yes(False)), S('do_not_autoplace', yes(False)),
                     S('effects', font(), S('justify', Sym('left'), Sym(just))))
        items.append(S('sheet', S('at', x, y), S('size', 50.8, 15.24), S('exclude_from_sim', yes(False)), S('in_bom', yes(True)),
                       S('on_board', yes(True)), S('dnp', yes(False)), S('fields_autoplaced', yes(True)),
                       S('stroke', S('width', 0.1524), S('type', Sym('solid'))), S('fill', S('color', 0, 0, 0, 0.0)),
                       S('uuid', sh.uuid), prop('Sheetname', '%d %s' % (sh.page - 1, sh.title), y - 0.7, 'bottom'),
                       prop('Sheetfile', sh.name + '.kicad_sch', y + 15.9, 'top'),
                       S('instances', S('project', design.project, S('path', '/%s' % NS, S('page', str(sh.page)))))))
        x += 60.96
        if x > 220:
            x, y = 20.32, y + 30.48
    return S('kicad_sch', S('version', 20260306), S('generator', 'eeschema'), S('generator_version', '10.0'), S('uuid', str(NS)),
             S('paper', 'A3'), S('title_block', S('title', m['title']), S('date', m['date']), S('rev', m['rev']), S('company', m['company'])),
             S('lib_symbols'), *items, S('sheet_instances', S('path', '/', S('page', '1'))), S('embedded_fonts', yes(False)))


DROP_V7 = {'show_name', 'do_not_autoplace', 'in_pos_files', 'duplicate_pin_numbers_are_jumpers', 'embedded_fonts',
           'exclude_from_sim', 'body_style', 'generator_version', 'embedded_files', 'jumper_pin_groups'}


def to_v7(x, parent=None):
    """The same tree in the KiCad 7 file format."""
    if not isinstance(x, list):
        return x
    head = x[0]
    out = []
    hidden = False
    for e in x:
        if isinstance(e, list) and e:
            if e[0] in DROP_V7 or (e[0] == 'property' and isinstance(e[1], Sym)):
                continue
            if head == 'sheet' and e[0] in ('in_bom', 'on_board', 'dnp'):
                continue
            if e[0] == 'hide':
                hidden = hidden or (len(e) > 1 and e[1] == 'yes')
                continue
            if e[0] in ('bold', 'italic'):
                if e[1] == 'yes':
                    out.append(Sym(e[0]))
                continue
            if e[0] == 'fields_autoplaced':
                out.append(S('fields_autoplaced'))
                continue
            if e[0] == 'power':
                out.append(S('power'))
                continue
            if e[0] == 'version' and head in ('kicad_sch', 'kicad_symbol_lib'):
                out.append(S('version', 20230121))
                continue
            if e[0] == 'generator':
                out.append(S('generator', Sym('eeschema')))
                continue
            out.append(to_v7(e, head))
        else:
            out.append(e)
    if hidden:
        if head == 'property':
            eff = first(out, 'effects')
            if eff is None:
                eff = S('effects', font())
                out.append(eff)
            eff.append(Sym('hide'))
        elif head == 'pin':
            at = next(i for i, e in enumerate(out) if isinstance(e, list) and e[0] == 'length')
            out.insert(at + 1, Sym('hide'))
        else:
            out.append(Sym('hide'))
    return out


def write(design, outdir, notes, v7=False):
    os.makedirs(outdir, exist_ok=True)
    def conv(tree):
        if not v7:
            return tree
        tree = to_v7(tree)
        for sym in find(first(tree, 'lib_symbols'), 'symbol'):       # KiCad 7 names a power net after the pin
            if first(sym, 'power'):
                value = next(p[2] for p in find(sym, 'property') if p[1] == 'Value')
                for unit in find(sym, 'symbol'):
                    for pin in find(unit, 'pin'):
                        if pin[1] == 'power_in':
                            first(pin, 'name')[1] = value
                            if 'hide' not in pin:
                                pin.insert(5, Sym('hide'))
        return tree
    for sh in design.sheets:
        open(os.path.join(outdir, sh.name + '.kicad_sch'), 'w').write(dump(conv(sh.tree())) + '\n')
    open(os.path.join(outdir, design.project + '.kicad_sch'), 'w').write(dump(conv(root_tree(design, notes))) + '\n')


def build(design, describe):
    """Two passes: the first finds which nets cross sheets (those become global labels)."""
    for _ in range(2):
        design.reset()
        describe(design)
        for sh in design.sheets:
            sh.render()
        design.settle_globals()
    return design
