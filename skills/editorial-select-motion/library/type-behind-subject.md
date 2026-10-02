# type-behind-subject

A word in depth between a picture and its own subject: the plate at the back, the serif word in the middle, the cut-out subject in front, so the subject's silhouette cuts through the letters. The word lands in one frame with no tween, the subject can lift in front of an already visible word with a two-frame 15 percent brightening, and an optional camera push scales the three layers about a focal point, the nearer layer a little more, on the push curve stepped on the film's cadence. Signature: yes.

Source: s4 shot 17 frames 442 to 452 ("Mask it" behind the subject, cap height 205 px, ink #F1F1F0, the marquee's afterglow under the word) for the layering, and s4 shots 20 and 21 for the camera (zoom 0.92 on cubic-bezier 0.213, 0.313, 0.759, 0.883; push 1.47 on push-hard).

## Slots

| slot | what | notes |
|---|---|---|
| `plate` | the picture | `{ src or frames, fit, focal: [x, y], box }` |
| `cutout` | the subject alone on transparency, aligned to the plate | same fit, focal and box; scaled slightly more than the plate under a push, so it always covers its own place in the plate |

## Text and layout

`word`, `cap` (px or share of height, default 0.19), `wordX`, `wordY` (ink centre), `color` (token or colour, default `--color-type-light`). Place the word so it straddles the subject's edge: a subject that fills the frame swallows the word whole.

## Timing

`wordAt` and `liftAt` (seconds, default 0 and the word's time; a later `liftAt` shows the word in front first, then lifts the subject over it), `push: { from, to, at, dur, curve, focal, parallax }` (default 1 to 1.08 over the whole duration on `push`, parallax 0.15 of the push; `false` for none), `duration` (0.4 to 3 s, default 1), `scale`, `beats: [word, lift]` snapped to the cadence, `cadence`, `cursor: { at, stops }` for a pointer through the es-cursor kit, `exitAt`. Returns the lift time.

## Presets

`replica-s4-shot17-behind` holds the word placement, the afterglow states and the pointer poses of frames 442 to 452. Rebuilt from the block alone (plate and cut-out frames as slot fills) it scores mean SSIM 0.9963 (min 0.996), relative flow error 0.097: pass (work/blocks/type-behind-subject/replica/cmp-1). The push is general mode only: no source shot holds type behind a subject under a push (in shot 20 "Edit it" sits in front of the face and bottle, verified on frame 500).
