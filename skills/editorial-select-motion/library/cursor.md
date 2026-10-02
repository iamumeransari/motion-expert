# cursor

The film's pointer, which names what the next edit will touch. A rounded kite with its tip on the point, a white keyline 3.5 px wide outside a translucent grey body (rgba 60, 62, 58 at 0.31) that darkens whatever it crosses, about 180 px long at 1080 tall. It never glides: it travels in short ease-out hops of 4 to 10 frames on the film's sixteen-a-second picture, leans with the hand (resting at 36 degrees, ranging from 15 to 60), and squashes to 0.85 for one picture when it clicks. Signature.

The drawing and the travel live in the `es-cursor` kit inside `cursor.html`, which any block that carries a pointer copies verbatim (marquee-select does), so the pointer looks and moves the same everywhere. The source of the kit is `work/blocks/_shared/cursor-kit.js`, spliced in by `work/blocks/_shared/splice.py`.

## Modes

`preset: "replica-s4-shot18"` replays the measured tip position, rotation and scale of every frame of source frames 453 to 477 (two clicks, on 462 and on 469 to 470). `replica-s4-shot19` replays 478 to 491 and hides it on 492. These keys already carry the film's cadence, so they run at 24 fps with no extra stepping.

The general mode takes `stops`, each `{ x, y, at, click, th, hop }`. `x` and `y` are px, or a share of the frame when both are 1 or less. `at` is the arrival time in seconds after the move's start; leave it out and the stops take `props.beats` (or even beats across `exitAt`). Each hop leaves the previous stop `hop` seconds before arrival, by default 4 frames plus 6 frames per frame height travelled, on the `snap` curve (cubic-bezier 0.33, 1, 0.68, 1, the ease-out the film's hops fit), and is stepped on the cadence so it shows the same held pictures the film does. `click: true` squashes on arrival for `clickFrames` (2) frames, snapped to a frame that shows a new picture.

## Props

| prop | default | meaning |
|---|---|---|
| `preset` | none | a replica key set, as above |
| `stops` | [] | general-mode path |
| `cadence` | `"16"` | `"16"` (film), `"twos"`, or `"none"` |
| `size` | frame height / 1080 | pointer scale |
| `shape` | s4 fit | `{ L, half, k, r1, r2, sw }` kite length, half angle, notch depth, corner radii, keyline width |
| `fill`, `stroke` | s4 measured | body and keyline colours |
| `curve` | `"snap"` | any kit curve name or control points |
| `exitAt` | none | seconds after start when it is gone (a one-frame cut, as in the film) |

No image slots and no text. Duration: a hop is 0.17 to 0.42 s, a whole travel 0.5 to 4 s.

## Proof

`work/blocks/cursor/replica`: the preset over the clean plates of shot 18 scores mean SSIM 0.9984 (worst frame 0.998), relative flow error 0.094, PASS against source frames 453 to 477. `work/blocks/cursor/demo`: a 1080 by 1350 still of a teapot, the pointer arriving from the lower right, clicking the lid and the spout, and leaving right.

## What does not generalise

Rotation in the film is the hand's, not a rule: it leans the same way travelling left as on a fast run right, so the general mode's lean (up to 24 degrees with leftward travel, 20 with rightward) is a plausible fit and not a measurement. The body is a single alpha, which matches the film over grey and satin to a few levels but not exactly over every ground.
