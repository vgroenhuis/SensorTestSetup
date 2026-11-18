#!/usr/bin/env python3
"""Write the schematic files of the SensorTestSetup PCB from gen/design.py.

    python3 gen/make.py [--symbols DIR] [--espressif FILE] [--out DIR] [--v7] [--check NETLIST]

--symbols    KiCad 10 symbol library folder (default: $KICAD10_SYMBOL_DIR or /usr/share/kicad/symbols)
--espressif  Espressif.kicad_sym from github.com/espressif/kicad-libraries (default: $ESPRESSIF_SYM)
--v7         write the KiCad 7 file format (for ERC with an older kicad-cli); use with --out
--check      compare a netlist exported by kicad-cli (kicadsexpr format) with the design
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design          # noqa: E402
import schgen          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = 'OfficeDeskSetup'


def check(d, path):
    """Every pin of the exported netlist must be on the net the design gives it (and the other way round)."""
    tree = schgen.parse(open(path).read())
    got = {}
    for net in schgen.find(schgen.first(tree, 'nets'), 'net'):
        name = schgen.first(net, 'name')[1].lstrip('/')
        name = name.split('/')[-1] if name.startswith(tuple(s.name for s in d.sheets)) or '/' in name else name
        for node in schgen.find(net, 'node'):
            got[(schgen.first(node, 'ref')[1], schgen.first(node, 'pin')[1])] = name
    want = {(ref, pin): net for ref, pins in d.netlist.items() if not ref.startswith('#') for pin, net in pins.items()}
    errors = 0
    groups = {}
    for key, net in want.items():
        if net is None:
            if key in got and not got[key].startswith('unconnected-'):
                print('  %s pin %s: should be unconnected, is on %s' % (*key, got[key]))
                errors += 1
            continue
        if key not in got:
            print('  %s pin %s: missing from the netlist (wanted %s)' % (*key, net))
            errors += 1
            continue
        groups.setdefault(net, set()).add(got[key])
    for net, names in sorted(groups.items()):
        if len(names) > 1:
            print('  net %s is split into %s' % (net, sorted(names)))
            errors += 1
    merged = {}
    for net, names in groups.items():
        for n in names:
            merged.setdefault(n, set()).add(net)
    for n, nets in sorted(merged.items()):
        if len(nets) > 1:
            print('  nets %s are joined (as %s)' % (sorted(nets), n))
            errors += 1
    for key in sorted(set(got) - set(want)):
        print('  %s pin %s is in the netlist but not in the design' % key)
        errors += 1
    print('netlist check: %d pins, %d nets, %d problems' % (len(want), len(groups), errors))
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbols', default=os.environ.get('KICAD10_SYMBOL_DIR', '/usr/share/kicad/symbols'))
    ap.add_argument('--espressif', default=os.environ.get('ESPRESSIF_SYM', ''))
    ap.add_argument('--out', default=HERE)
    ap.add_argument('--v7', action='store_true')
    ap.add_argument('--check')
    args = ap.parse_args()

    lib = schgen.Library(args.symbols, args.espressif, PROJECT)
    d = schgen.Design(lib, PROJECT, 'SensorTestSetup PCB', design.REV, design.DATE, 'RaM, University of Twente')
    schgen.build(d, design.describe)
    if args.check:
        sys.exit(1 if check(d, args.check) else 0)

    schgen.write(d, args.out, design.ROOT_NOTES, v7=args.v7)
    if not args.v7:
        lib.write_project_lib(os.path.join(args.out, PROJECT + '.kicad_sym'))
        open(os.path.join(args.out, 'sym-lib-table'), 'w').write(
            '(sym_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "Symbols of this board"))\n)\n'
            % (PROJECT, PROJECT))
        open(os.path.join(args.out, 'fp-lib-table'), 'w').write(
            '(fp_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.pretty")(options "")(descr "Footprints imported from LCSC/EasyEDA, checked against the datasheets"))\n)\n'
            % (PROJECT, PROJECT))
        pro =os.path.join(args.out, PROJECT + '.kicad_pro')
        if os.path.exists(pro):
            data = json.load(open(pro))
            data['sheets'] = [[str(schgen.NS), 'Root']] + [[s.uuid, '%d %s' % (s.page - 1, s.title)] for s in d.sheets]
            json.dump(data, open(pro, 'w'), indent=2)
            open(pro, 'a').write('\n')
        with open(os.path.join(args.out, 'bom.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['Reference', 'Value', 'Footprint', 'LCSC', 'DNP', 'Sheet', 'Note'])
            seen = set()
            for p in d.parts:
                if p['ref'] in seen or p['ref'].startswith('H'):
                    continue
                seen.add(p['ref'])
                w.writerow([p['ref'], p['value'], p['footprint'], p['fields'].get('LCSC', ''), 'DNP' if p['dnp'] else '', p['sheet'],
                            p['fields'].get('Note', '')])
    single = sorted(n for n in {net for pins in d.netlist.values() for net in pins.values() if net}
                    if sum(1 for pins in d.netlist.values() for v in pins.values() if v == n) < 2)
    print('%d sheets, %d parts, %d nets%s' % (len(d.sheets), len({p['ref'] for p in d.parts}),
                                             len({net for pins in d.netlist.values() for net in pins.values() if net}),
                                             '; nets with one pin: ' + ', '.join(single) if single else ''))


if __name__ == '__main__':
    main()
