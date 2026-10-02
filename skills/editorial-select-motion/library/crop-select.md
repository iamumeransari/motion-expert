# crop-select

A photograph is picked out as a small tile on paper and its crop grows in steps, each step a wider view of the same picture rather than a stretch of it, while violet handles streak out to the new corners and the word under the tile steps up in size and then opens its tracking. Then a hard cut to the same picture full bleed: paper bars close, the camera pushes, an exclamation sits over the photograph and the pointer slides in across it. It is the film's joke about overreach, a selection that keeps growing until it becomes the whole frame, and it reads in any story where something is made bigger than it should be. Signature: yes (`select-grow` in `references/moves.md`).

Source: s6 shots 3 and 4, film frames 760 to 827 (31.667 to 34.500 s), rebuilt and passed in `work/replica/s6`. Strip: `assets/frames/select-grow-dense.jpg`.

## Modes

`preset: "replica-s6-3-4"` plays the replica's measured keys per source frame: the crop box and the photo's scale and offset on every unique frame, the word glyph by glyph (Source Serif 4 at wght 550 and 450, opsz 16, the family the replica was fitted in, which needs the `ES Source Serif` face from `work/blocks/_style-s67`), the handles as swept chips refitted from the traced violet shapes (median IoU 0.96), the pointer's position, roll and scale. Its slot fills are the calibration plates in `work/blocks/crop-select/calibration-only-plates/`. A `word.text` of the same length swaps the letters and keeps the keys.

With no preset the block builds the same tables from the measurements as shares and fitted curves, so any picture, any word and any frame shape work. Timing is in source frames scaled by `scale`, and every state lands on a picture of the 16 fps cadence (local frames 1, 4, 7 repeat by default; `phase` shifts that, `cadence` takes `twos` or `ones`).

## Slots

| slot | what | notes |
|---|---|---|
| `photo` | `{ src, w, h, focal: [x, y], focalB, zoomB, cutout }` | `w` and `h` are the picture's natural pixels; size, crop and motion are code. `focal` is what the first tile shows; the crop opens towards the picture's centre as it grows. `focalB` is the point the full-bleed plate holds and pushes on. `cutout` (the subject on transparency, same size) is drawn above the exclamation after the cut, for type behind the subject. Without `src` the slot draws a labelled placeholder. |
| `art` | `{ src, rect: [x, y, w, h], on }` | Artwork riding the photograph (a logotype, layout copy), in the picture's own pixels or as shares of it; it appears on the last step's jump unless `on` (seconds) says otherwise and goes at the cut. |
| `paper` | `{ src }` or a colour token | The ground; default `--color-paper`. |

## Text

| param | default | notes |
|---|---|---|
| `word.text` | `Bigger` | Set in ES Serif from the font's own metrics (`__esShared.layout`), centred under the crop and overlapping its bottom edge by 0.6 of its cap height, then 0.36, then 0.03 as the crop grows. |
| `word.cap` | 102 px at 1080 | Steps to 1.5 times on the first widen, as measured. |
| `word.tracking` | 0.19 em | Opens on the last step (measured from the x-span, 547 to 764 px). |
| `word2.text` | `Oops...` | The exclamation after the cut, centred, cap 254 px at 1080 or narrower to fit 0.86 of the width; `word2.y` is the share of height for its cap centre. Colour `type-light`. |

Colours take token names (`ink`, `type-light`, `violet`) or any CSS colour.

## Timing

Measured at 24 fps: tile lands on frame 0 and settles over 8 frames (bezier 0.444 0.554 0 0.887); first widen frames 9 to 26 (0.802 0.013 0 1.063), second 29 to 44 (0.909 -0.045 0 0.991), each a slow creep then a two-picture jump; artwork on frame 35; cut on frame 57; bars of 0.044 H close over 5 frames; push from es-camera's `push` preset (x1.10 over 12 frames); pointer 9 frames on 0.465 0.352 0 0.744, rolling +10 to -15 degrees. `steps` takes any number of steps (`w`, `h` in px at 1080 or `"0.8W"`, `zoom` of the final cover scale, `frames`, `delay`), `hold` adds frames before the cut and `tail` sets the frames after it. Duration range: about 2.4 to 4.5 s (`scale` 0.85 to 1.6); outside that the jump frames stop reading as a snap or the creep drags.

## Composition notes

The block owns the whole frame (its root is the frame size) and the cut happens inside it, so it suits a scene of its own. It returns the time its last frame ends. `exitAt` hides it. `push: false` holds the full-bleed plate still and `cursor: false` drops the pointer.

## What does not generalise

The handles are generated as swept chips from the crop's motion (a leading piece over the last half frame and a trailing smear from 0.75 to 1.5 frames back, the model in `es-select`), with the arrival drawn from a template measured on frames 0 to 6; a selection arriving from somewhere other than the tile's own centre would need a `from` box the block does not take yet. In a tall frame the default steps have little width to grow into, so the crop reads as getting wider and shorter rather than bigger; pass taller `steps` there. The default general mode moves the crop about the frame centre, where the replica's crop drifts 8 px left on the first widen.

## Proofs

`work/blocks/crop-select/`: `plan-replica.json` is the preset alone (built with `--style-dir work/blocks/_style-s67`), scored with `compare.py --mode replica` against `source-760-827.mp4` (film frames 760 to 827) and the film's fingerprint sliced to the range: shot 3 SSIM 0.9846 and relative flow error 0.121, shot 4 SSIM 0.9822 and 0.100, the cut on its frame, all four moves within a frame (`out/r08`). It also passes against the clip's own fingerprint, which splits shot 4 in two. Two corrections to the s6 keys got it there: the crop is drawn as an antialiased `clip-path` inset rather than an overflow box, because a pixel-snapped edge jumps a whole pixel where the film's creeps, and the crop keys are inset by about a pixel (left 0.3, top 0.8, right 1.3, bottom 0.8) because the s6 fits read the outside of the antialiased edge; without them the handles' landing move settled two frames late. `plan-demo.json` is 1080 x 1350 with a teapot stand-in, "Brew" growing and "Too strong!" after the cut, scale 1.15 (`out/demo2/render.mp4`, lint and `check --strict` clean).
