# Routing: handoff notes (2026-11-23)

Notes for continuing the autorouting work in a local Claude Code session. The full pipeline description is in
`SCHEMATIC_NOTES.md` ("PCB: autorouting"); this file says where things stand and what to do next.

## Goal

Route the board (rev 0.2, 200 × 150 mm, 4 layers: GND on In1, +3V3 on In2) 100 % automatically with
Freerouting via `gen/route.py`, so later boards and revisions need no hand routing. The last committed board
(a529ab5) has stage 0 (power) routed with 148/166 power connections; signals are not routed yet.

## Branch and commits

Branch `claude/eloquent-hawking-07riyu` (based on main a529ab5):

* 3c89dbd: chip keep-outs in stage 0, escape vias with routing rounds in stages 0 and 1, `--bare`.
* 5d7f40b: pin ranking over all runs (`pin_scores.json`), ranked escape vias first, bent escape tracks.

Changed files: `gen/route.py`, `gen/planevias.py`, `SCHEMATIC_NOTES.md`. The board itself is unchanged.

## What is new (user's ideas, implemented)

1. **Escape vias + rounds**: after a routing round, every pad still open (`planevias.open_pads`, from pcbnew
   connectivity: pads outside their net's largest connected group) gets an escape via (`planevias.escape`): a
   via of the net class size beside the pad with a short locked track at the class width where it fits (down to
   0.2 mm). Straight from the pad, or else out along the pin past its end, then to the via. The stage is routed
   again from its starting board (`gen/route/stage0_in.kicad_pcb`) plus the vias, up to `--escape-rounds` (now 0 = until no pad gets a new via) for
   power, `--escape-rounds-signals` (2) for stage 1. The best round is kept; unused escape vias are removed
   except at pads still open (to connect by hand later).
2. **Pin ranking** (`gen/route/pin_scores.json`, persists across runs): +1 per round a pin stays open, +1 each
   time it gets no room for a via. Escape vias are placed highest score first; a new attempt pre-places vias for
   every pin with score ≥ `--pre-escape` (1) before round 0. Delete the file after a placement change.
3. **Chip keep-outs** (stage 0 only, written into the DSN, never saved on the board): for all-SMD `U` parts with
   courtyard ≤ 20 mm a side (41 chips; not the ESP32 modules or U37): no tracks/vias over the courtyard on the
   other side, no tracks inside the area the pins enclose on the chip's own side. `--no-keepout` to disable.
   They are only meant to keep power tracks off a chip where they can go around it: a pin with no room for its
   escape via outside the keep-out gets one under the chip, and that chip loses both keep-outs for the rest of the
   attempt (`state['relaxed']` in stage0_rounds.json).
4. `--stage power --bare` restarts stage 0 from the bare placement.

## Testing status: IMPORTANT

**Not tested with Freerouting.** The cloud container could not download Freerouting (GitHub releases and GHCR
blobs blocked, Maven Central rate-limited). Everything around it was tested with KiCad 10.0.8's pcbnew (Docker
image `kicad/kicad:10.0.8`) and a stand-in router that returns an empty `.ses`:

* open-pad count on the current board: 18 open power connections (matches 148/166);
* 24 of 26 open pads get an escape via on the first attempt; with the ranking, the next attempt from `--bare`
  gives all 25 previously failed pins a via (U8.6, U6.2, U6.8, U6.28 included);
* KiCad DRC: no new clearance violations from escape vias, bent tracks or narrowing stubs;
* the DSN contains 41 B.Cu `keepout`s and 33 F.Cu `wire_keepout`s; the saved board contains none; the
  `.kicad_pro` stays unchanged;
* the full `--stage power` and `--stage signals` loops run end to end (rounds, escape, pick).

So the first real run may still find bugs in the parts that depend on real routes: `unused_escapes` (deciding
whether the router used a via), the open-count improvement per round, and Freerouting's handling of the keepouts
and of fixed vias.

## First real runs (local, 2026-11-23, Freerouting SNAPSHOT-20261119)

* Attempts 1 and 2 (`--bare`): 22 open power connections, worse than the old 18. Freerouting reported every escape
  via near a chip as an unfixable clearance violation against an `ObstacleArea` (the chip keep-outs): `via_ok`
  only kept the via's centre out of the keep-out box, so the via itself overlapped it and the router never used it.
* Fix: `planevias.escape` keeps the whole via plus clearance off the keep-outs. Pin ranking reset.
* Attempt 3 (`--bare`, fresh ranking): rounds 25 → 20 → 17 → 16 open; round 3 kept. 16 open power connections in
  10 nets (V_BUS 7). KiCad DRC: 15 clearance violations, all pad-to-pad inside the TPS25947 footprints (U8, U9,
  U14); no track or via clearance violations (a529ab5 had 45). U6.28 (CHG_SW1) never gets room for a via.
* Attempt 4 (`--bare`, no round limit, ranking from attempt 3: 70 vias placed in advance): 17 open after round 0;
  every open pad but U6.26 already had a via, so it stopped. An exact position match had first made it loop
  (U13.2's recorded position 1 nm off, a new via every round); pads now match within 1 um. Board kept: attempt 3.
* Attempts 5-8 (all `--bare`, `inspect/run5` ... `run8`): 18, 18 (3 Freerouting passes), 15, **4** open.
  - The cleanup removed escape vias the router had used when its track ended on the middle of the escape track
    (J2.A4 VBUS_PROG left 0.7 mm short); fixed, and stacked pads get one escape via.
  - The far-side keep-out of U13 covered battery holder pad BT2.2 (CELL1 unreachable); now none where it would
    cover a pad being routed there.
  - The keep-outs covered the whole courtyard, blocking short hops beside the pins (SW_3V3 at U11, V_BUS at U18);
    now only the body between the pins. Run 8: 4 open (VBUS_SW at U8.6 and U9.6, CHG_SW1 U6.28, CHG_SW2 U6.26),
    no track or via clearance violations. The board on main is run 8.
* Attempt 9: escape vias need room for a class-width track to end on them (the U6.26/U6.28 vias were 1.03 mm
  apart, a 1 mm track needs 1.1 mm to the other via). **2 open**: CHG_SW1 (U6 to L1.1), CHG_SYS (near U8.5).
  VBUS_SW at U8.6/U9.6 routed. No track or via clearance violations. The board on main is run 9.
* Attempt 10: 0.1 mm extra landing margin a side (the CHG_SW1 via had 0.05 mm to spare between U6 pins 27
  and 29, too tight for Freerouting's octagonal track ends). **0 open power connections**, in round 0. DRC: no
  track or via clearance violations. 2440 mm power track, 102 vias; 74 mm (62 pieces, at most 3.2 mm long)
  narrower than the class width, mostly 0.2 mm escape tracks from fine-pitch pins (CHG_SW2 3.2 mm at 0.2 mm:
  check the current). The board on main is run 10.
* After attempt 10: `--stage vias` (451 plane vias/tracks; no room at C117.1, C117.2, U8.8, R31.2, C17.2,
  U23.A7, U23.C7, U39.3/5/6/8/12, U14.8, U6.27, U9.8), then `--stage signals`: rounds 35 -> 26 -> 25 open signal
  connections (10.5, 22.5, 18 min); round 2 kept. 3731 tracks, 15.6 m, 1017 vias. DRC: 2 hole clearance
  violations (tracks too close to mounting holes H3, H4), otherwise only TPS25947 pad-to-pad. Escape vias found
  no room at several U6 pins (5, 10, 14, 19, 20, 21). Saved in inspect/run10_vias and inspect/run10_signals.
* Fan-out of dense chips (U2 U6 U8 U9 U10 U14 U38 U39, pitch <= 0.5 mm) before stage 0, and plane pads without
  room in the pin ranking. Attempt 11: 1 open power connection (U6.29 had no room); with power pins under the
  chip first, attempt 12: 3 open (CHG_VBUS at U6.2, BAT_P at U6.22). Worse than attempt 10 (0) so far; boards in
  inspect/run11 and run12. Main keeps attempt 10 with plane vias and signals (c5598ca). Not yet run through the
  signal stage, where the fan-out should help most. Fan-out vias are not escape-round vias, so the rounds stop
  when the only open pads have fan-out vias (U6.22, U6.23 in attempt 12).
* Attempt 12 with the three open power connections drawn by hand (CHG_VBUS at 0.95 mm between L1.2 and a CHG_SW1
  track, where 1.0 mm does not fit; BAT_P at 0.2 mm from U6.22), then plane vias (439; 11 pads without room) and
  signals: rounds 26 -> 22 -> 29, round 1 kept: **22 open signal connections** (attempt 10 without fan-out: 25).
  3871 tracks, 16.5 m, 1073 vias. DRC outside the TPS25947 footprints: track-to-hole at mounting holes H2 and H3
  (as in attempt 10: the mounting holes need a keep-out for Freerouting) and one clearance at JP8 pad 2.
  Saved in inspect/run12_vias and inspect/run12_signals; on main.
* Mounting holes H2-H4 now get a keep-out ring in the DSN at every stage (hole clearance 0.25 mm + 0.05 mm), and
  pads without room for a via score a point in the fan-out and the pre-placed plane vias too. Not yet run.
* Attempt 13: run 12's plane-vias board again, with the hole keep-outs, signal rounds without a limit
  (`--escape-rounds-signals 0`): 25, 23, 21, 25, 17, 19 open; round 4 kept: **17 open signal connections**. Left over
  DRC: the TPS25947 pad-to-pad items, D14's cut-out (now a keep-out too) and one locked I2C_SDA track on B.Cu
  (x = 67.56, y 33-117, already on the plane-vias board) 0.239 mm from the H2 hole. inspect/run13/stage2_signals.
  Stage 2 now keeps plane tracks short (`--plane-cost`, `--max-plane-run`).
* Attempt 13, planes -> narrow -> rest -> finish: stage 2 leaves 6 unconnected (after a zone refill); only BSV_RC
  (8 mm) and SERVO1 (4 mm) use a plane. The first finish ended with 17: `cleanup()` took a track end on the middle
  of another track as loose and removed 259 items in prune (hand-drawn power links at U6 among them). Fixed (an
  end may touch any part of a track; locked items stay). Again from the planes board (13b): **6 unconnected**
  (U6: GND pad 27, CHG_BTST1, CHG_CE, CHG_PROG; USB_UP_DP J2.A6-B6; PD_VSET at U2), 4528 tracks, 17.4 m, 1142 vias.
  DRC besides TPS25947 and placement items: the locked I2C_SDA track at H2, CHG_VBUS 0.225 mm from BT3's
  non-plated hole (keep-outs for those now too), 8 starved thermals of the B.Cu GND pour. inspect/run13b/stage6_finish.
* Overnight 2026-11-24 (boards in inspect/runN/stageK_<stage>/, each with a DRC after a zone refill):
  - Attempt 14 (`--bare`, fan-out): power 3 open (rounds stop: the open pads have fan-out vias); signals 22, 30,
    26, 29, 33 ... stopped by hand. Worse than without the fan-out.
  - Attempt 15 (`--bare --fanout-pitch 0`): power 2 open (U6.25 CHG_SYS, U8.5); signals 27, 33, 29, 29, 33 (stopped);
    planes 13; finish **11 unconnected**. In stage 2 the plane cost did not stop runs of 94-193 mm (TFT_RES, DXL_EN,
    US_TRIG): prune's 20 mm limit took them out and stage 4 routed most of them outside.
  - Attempt 16 (run 12's plane vias, `--pre-escape 3`, 6 rounds): signals 24, 23, 26, 37, 22, 26, 24; planes 10;
    finish **8 unconnected**.
  - Attempt 17 (run 12's plane vias, `--pre-escape 3`, **`--passes 8`**): signals 7, 6 (round 1 kept, then no new
    escape vias); stage 2 needs no plane tracks; finish **6 unconnected**, 4609 tracks, 17.3 m, 1104 vias. More
    Freerouting passes per round help far more than more escape rounds (3 passes: 22-37 open per round; 8: 6-7).
  - The same six stay open in every attempt: U6 GND pad 27 (no room for a plane via), CHG_BTST1 (U6.4-C10.1),
    CHG_CE (U6.13-R12.1), CHG_PROG (U6.20-R7.1), USB_UP_DP (J2.A6-B6) and PD_VSET (U2.8). Local congestion around
    U6 and at J2/U2: placement, or by hand.
  - DRC left besides TPS25947 and placement items: locked tracks from run 12's hand edits (I2C_SDA at H2, CHG_VBUS at
    BT3's peg hole, a Battery track at D14's cut-out) and 0.1475 mm at IR_DO (rounding).
* Still dropping at the last round: `--escape-rounds` now defaults to 0 (no limit), the rounds go on until no open pad gets a new via.

## Routing workflow (agreed 2026-11-24)

1. route.py routes the board (power, plane vias, signal rounds with `--passes 8`, planes, narrow, rest, finish) and
   hands over: a KiCad board with all escape tracks and vias but no routes, a description of the problem areas
   (rev 0.2: U6 BQ25792 with CHG_BTST1, CHG_CE, CHG_PROG and GND pin 27; J2 USB_UP_DP; U2 PD_VSET), and an example
   routing with few unconnected items (run 17: 6).
2. The user adds and moves vias around the problem areas on that board.
3. route.py restarts from the user's board (`--stage power` without `--bare`: hand-drawn items stay, locked). Stage 0's
   chip keep-outs must not forbid vias the user put under a chip (Freerouting ignores fixed vias in a keep-out).
4. The user completes the last connections by hand.
5. Finish: pours, voids connected to GND filled with via arrays (stitching), then a full DRC.

Saved boards: `inspect/runN/stageK_<stage>/` (stage0_power, stage1_vias, stage2_signals, stage3_planes,
stage4_narrow, stage5_rest, stage6_finish).

## Next steps

1. Run stage 0 from scratch (KiCad closed):

   ```
   "C:/Program Files/KiCad/10.0/bin/python.exe" gen/route.py --stage power --bare --freerouting <freerouting .jar> --java <java.exe> --fr=--gui.enabled=false
   ```

   Read the log: per round "stage 0 round N: X open connections", which pads got escape vias / no room, the
   rounds summary, unused vias removed, and the pin ranking (top 15).
2. Compare with the old result (18 open power connections). Check in KiCad: escape vias around U6 (BQ25792,
   0.4 mm pitch) may crowd its signal pins; power tracks should no longer pass under chips.
3. Run the attempt again (the ranking now pre-places vias); see whether the open count keeps dropping.
4. Then continue with `--stage vias`, `--stage signals` (escape rounds there too), `planes`, `narrow`, `rest`,
   `finish` as described in SCHEMATIC_NOTES.md.

Things to watch / ideas not done yet:

* A single escape via (0.8/0.4 for Power/Pack) is thin for battery and motor currents: consider two vias for
  nets with class width ≥ 1 mm, or check by hand.
* U8.6 / U9.6 / U14.6 (TPS25947 VBUS_SW / V_DXL pin 6) can only leave along a 0.2 mm track between pins 5 and
  10: too narrow for the current; a footprint/pin-out issue rather than a routing one.
* Scoring weights are 1/1 (open / no via); weigh "no via" higher if needed.
* Keep-out scope (`--keepout-refs U`, `--keepout-max 20`) may need tuning, e.g. also the TDSON MOSFETs.

## KiCadRoutingTools evaluation (earlier in the same session)

https://github.com/drandyhaas/KiCadRoutingTools was tried as an alternative router (on the stripped board):

* `autoroute.py` ran out of memory (10–14 GB at its default 0.05 mm grid); `route.py --grid-step 0.1` worked:
  about 1 h, 4.9 GB.
* Result with net-class widths: open 7 power / 19 signal / 2 plane connections, 1311 vias, its own DRC OK.
* But it silently narrows power tracks to 0.15–0.2 mm where the class width does not fit: CELL3 and BQ_SRN
  (Pack, 2 mm) entirely 0.2 mm, V_BUS 81 mm, V_SERVO 73 mm, V_DXL 75 mm at 0.2 mm; a third of the Power class
  track below 1 mm. Not usable for the power stage.
* Pitfalls: `--track-width` overrides all net classes; `autoroute.py` overrides some power nets to 0.3 mm.
* Possible use: signals only, after the Freerouting power stage. Not tried.

## Tools used in the cloud session (for reference)

* KiCad 10 without installing: `docker run --rm -v $PWD:/w -w /w kicad/kicad:10.0.8 python3 gen/route.py ...`
  (pcbnew and kicad-cli are in the image; on Linux the scripts find `kicad-cli` next to `python3`).
* Stand-in router for testing the pipeline without Freerouting: a script given as `--freerouting` that writes
  an empty session to the `-do` path:

  ```
  (session x (base_design x) (placement (resolution um 10)) (was_is)
    (routes (resolution um 10) (parser (host_cad "KiCad's Pcbnew") (host_version "10")) (library_out) (network_out)))
  ```
* Use `--work <dir>` and `--scores <file>` to keep experiments apart from `gen/route/`.
