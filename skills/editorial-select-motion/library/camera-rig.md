# camera-rig

The film's camera as a block. It takes one image slot, a still or an image sequence, places it in a box in frame pixels and moves the picture inside that box with one of the source's own camera moves: the push that leans in on a figure at rest, the punch-in on a cut, the long pull-back off a billboard, the steady pull the city shots ride on, the settle, the drift and the tilt. Every preset is a measurement, so a push looks like this film's push and not a generic zoom, and the moves run on the film's cadences: the push on a still steps on the sixteen-a-second picture, while the pulls, measured on real footage, run on ones.

Not signature on its own: the camera is what the signature moves sit on. crop-select uses it for its closing push and billboard uses it to move a picture and its board as one.

## Modes

**Replica.** `preset: "replica-s7-A"` holds the measured per-frame homographies of film 828 to 843 (s7 shot A, the push landing and the handheld hold after it), one row-major 3x3 per unique picture, mapping the clean plate (2220 by 1380, frame 828 coordinates padded by 150 px) to the frame. The preset is geometry only (plate size, homographies, clip rects); the plan supplies the plate as `slot.src` and the picture change at frame 7 as `swaps: [{ frame: 7, src }]`, and any `props.replica` it carries is merged over the preset by `window.__esRuntime.preset`.

**General.** `preset` names a camera preset, or `cam` gives one move or a list. Scale interpolates in log space, which is how every preset was fitted, so a pull from 1 to 0.4 reads as an even move.

| preset | measured from | default |
|---|---|---|
| `push` | film 822 to 834 (shots 34 and 35), punch removed | x1.100 over 12 frames, bezier 0.587 -0.033 0.263 1.135 (rms 0.026), cadence 16 |
| `punch` | the cut at film 828 | x1.097 in one frame |
| `push-soft` | fingerprint move 52 (shot 27) | x1.34 over 13 frames, `push` curve |
| `push-hard` | fingerprint move 48 (shot 21) | x1.47 over 13 frames, `push-hard` curve |
| `pull-back` | s7 shot I tracked board plane (film 958 to 992) | x0.407 over 35 frames, log-scale bezier 0.473 0.464 0.332 0.974 (rms 0.003), travel -33, +26 px, on ones |
| `pull-steady` | s7 shots B to H, median | -1.99 percent per frame (range -0.92 to -2.39), linear, on ones |
| `pull-settle` | fingerprint move 67 (shot 38) | x0.82 over 13 frames, `settle` curve |
| `drift` | fingerprint move 29 (shot 14) | 0.035 W by 0.025 H over 20 frames, `drift` curve, on ones |
| `tilt` | fingerprint move 66 (shot 37) | -0.06 H over 13 frames, bezier 1.0 0.937 0.874 0.965 |
| `hold` | | no motion |

A move takes `at` (seconds after the block starts; a move with no `at` starts on `props.beats[i]` when beats are given, else where the last move ended), `dur` or `frames`, `scale` (duration multiplier), `from` and `to` (absolute scale), `dx`, `dy` (px at 1920 or `"0.05W"`, `"-0.03H"`), `r` (degrees), `origin` ([fx, fy] of the box, default the slot's focal point), `ease` (token name or bezier), `cadence` (`"16"`, `"twos"`, `"ones"`) and `phase`. Exact keys go in as `keys: [[frame, s, x, y, r]]` or `mats: [[frame, [m0..m8]]]`.

## Slots

`slot`: `{ src, fit, focal: [x, y], zoom, frames: [src...], fps, label }` or a src string. `frames` makes it an image sequence; `swaps: [{ frame | t, src }]` changes the picture inside the shot on a whole frame. With no src the slot draws a labelled placeholder, the code-and-slots view. `box: [x, y, w, h]` places the slot (default the full frame), `ground` paints behind it (token name or CSS).

## Text parameters

None. The camera carries no type. Its only colours are the placeholder's tokens (`--color-mist`, `--color-ghost`, `--color-ink-grey`, `--font-mono` for the label) and `ground`, a token name or CSS colour.

## Timing

Durations come from the presets and scale with `durationScale` or a move's `scale`. Practical range: 0 (punch) to about 2 s per move; the measured pull-back is 1.46 s and the push 0.5 s. Moves snap to beats through `props.beats`. `exitAt` cuts the layer.

## Shared code

The move engine is `window.__esRuntime.camera` (the old global `window.__esCamera` remains as an alias), the camera module of the shared runtime kept in `library/_runtime/50-camera.js` and spliced verbatim between the `BEGIN es-runtime` and `END es-runtime` markers of every block by `library/_runtime/inject.py`; the first copy in a document wins. `window.__esRuntime.camera.sample(cam, t, props)` returns the camera state at a time, for anything that must follow the camera without sitting inside the moved node.

## Source shots

Frames 822 to 843 of the film (shots 34 and 35; s6 shot 4 and s7 shot A) for the push, the punch and the replica preset; film 847 to 992 (s7 shots B to I) for the pulls, from the per-frame board homographies tracked in s7; fingerprint moves 29, 48, 52, 66 and 67 for drift, push-hard, push-soft, tilt and pull-settle.

## Proof

`work/blocks/camera-rig/`. `plan-replica.json` rebuilds s7 shot A (film 828 to 846) from this block: one camera-rig carries the plate with `replica-s7-A` and the frame 7 swap, a second holds the paper under the print, and the shot's traced cursor rides on top as the replica's own element (`library/s7a-cursor.html` beside the plan), because the pointer is in the shot and is not the camera. Scored against the section's cut list (cut at frame 1, the push landing), it passes: shot SSIM 0.9967 and 0.9955, relative flow 0.130, the same as the passing s7 section render. The clip's own fingerprint also calls the print's first step at frame 16 a cut, which leaves frames 1 to 15 as a shot with about 1 px of motion per frame; there the flow error is grain-bound at 0.160, and the passing s7 render scores 0.159 on the same window, so that window cannot separate a right move from a wrong one.

`plan-demo.json` runs push, drift (at 1.5x duration), pull-back and a placeholder punch plus steady pull at 1080 by 1350 on stand-in pictures.
