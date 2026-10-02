# giant-type-pass

A giant serif line rushes past the camera. The first word rises in from below the frame on an exponential ease-out while the accelerating camera pan carries the whole line left, and the next words rise in behind it one at a time. As a picture blooms in behind the type, the letters turn from black to white along a soft edge that sweeps left to right on a 20 degree axis, so the line leaves the frame white over the picture. It is the film's turn from paper to spectacle. Signature move.

Source: replica s2 frames 216 to 218 and s3 frames 219 to 243 (9.000 to 10.167 s), strip `~/motion-expert/sources/editorial-select/frames/giant-word-pass-dense.jpg`, on the film's 16 fps picture cadence.

## Modes

`preset: "replica-s3-rush"` replays the measured per-frame motion for 28 frames from source frame 216 (s2 frames 216 to 218 and s3 shot 1, frames 219 to 243, the rush beat): the line origin on every frame (frames 216 and 217 fitted against the film at IoU 0.98, the rest from the s3 rush tables), the second word's rise, the whiteness axis and which whiteness field shows on each frame, and the frame the ground sequence starts on. The skill holds only that motion and geometry. The source-bound part, which is the words with their per-glyph x positions, the replica face, the measured ink and white colours and the whiteness fields themselves (120 x 68 grey images measured from the film, filled outward from the glyphs), lives outside the skill and arrives as `props.replica` (apply.py sets it from the replica layer). Composed with `icon-tile` and the ground sequence over source frames 180 to 243 it scores mean SSIM 0.9885 and relative flow error 0.135; its own range, 216 to 243, scores 0.9815 and 0.140 (`work/blocks/tile-rush/co-1/cmp/report.md` and `co-1/cmp-216/report.md`). Both pass.

General mode (no preset) builds the same state from the fitted curves for any words, frame and duration scale, set in `var(--font-serif)` unless `font` says otherwise, so a re-skin that changes the token changes the face. The replica face holds only the source line's letters, so never use it for new words. The curves, in frames at 24 fps multiplied by `scale`:

- the first word rises 0.674 H on R (e^(-k t) - e^(-k T)) / (1 - e^(-k T)) with k 0.157 and T 24, which is the film's decay of about 0.79 per picture;
- each later word enters 18 frames after the first (then every 6), from 0.343 H with k 0.27 and T 15, which is 0.667 per picture; until it enters it waits 0.556 H below, out of frame;
- the pan is the icon-tile pan, (e^(4.032 u) - 1) / (e^4.032 - 1) over 31.5 frames, starting 3.5 frames before the type enters. Its default dx is the larger of 1.088 W and 0.39 x size x character count, because the camera carries about three quarters of the line through the frame (2089 of about 2790 px in the film);
- the line starts at 0.747 W and its baseline settles at 0.722 H;
- the white edge sweeps from 0.45 W to 1.15 W (projected through the frame's centre line) between frames 12 and 22 with a softness of 0.18 W, on a -20 degree axis fixed to the frame, so the line moves under it.

## Slots

| Slot | Shape | Notes |
|---|---|---|
| `ground` | a path, or `{ src or frames: [...], fit, x, y, at, fps, blur, bloom }` | The picture the type passes into. `frames` is an image sequence played at `fps` (16 by default, one image per picture) from `at` seconds. In general mode it is revealed as a bloom, a soft radial mask from `bloom.x`, `bloom.y` (shares, default 0.3 and 0.85) growing over `bloom.frames` (15) on the cadence. `blur` in px treats the slot like the film's out-of-focus fields. The preset takes the source's own photo sequence from frame 12 with the bloom baked in. |

## Parameters

| Prop | Default | Notes |
|---|---|---|
| `text` | `"Short line"` | string or word list, any length; the default is a placeholder |
| `font` | `var(--font-serif)` | any CSS family |
| `size` | 0.62 H | font-size px (669.5 at 1080) |
| `x`, `baseline` | 0.747, 0.722 | shares of W and H |
| `rise`, `rise_next` | 0.674, 0.343 | shares of H |
| `keys` | | `{ stagger, stagger_next, white, white_end, pan }` in s from t0, beat-snappable |
| `pan` | see above | `{ dx, dy, frames, K, at }` or `false`; pass the same to `icon-tile` |
| `white` | true | `false` keeps the type black |
| `white_from`, `white_to`, `white_soft`, `axis_deg` | 0.45, 1.15, 0.18, -20 | the edge |
| `colors` | `{ black: "ink", white: "type-light" }` | palette names (resolved from the tokens.css `--color-*` variables) or CSS colours; `black` is the type before the turn, `white` after it |
| `scale` | 1 | duration scale |
| `cadence`, `phase` | `"16fps"`, 0 | `"twos"` or `"ones"` |
| `duration` | 28 frames x scale | s |
| `exitAt` | | s from t0 |

Duration range: 0.8 to 2 s (the film's pass is 1.17 s from entry to the cut).

The root carries `data-layout-ignore`, because white type over a pale bloom is the film's own contrast and the audit would fail it. Check legibility on composited stills instead.

## Proofs

- Replica: `work/blocks/tile-rush/plan-replica.json` (paper stills, this block, icon-tile), render `work/blocks/tile-rush/co-1/render.mp4`.
- Demo: `work/blocks/giant-type-pass/plan-demo.json`, render `work/blocks/giant-type-pass/co-1-demo/render.mp4`. It runs at 1080 x 1350 with "Every frame" in the serif token at 640 px, a blurred stand-in portrait as the ground, and icon-tile carrying a stand-in mark on the same pan.

## What did not generalise

The bloom is a radial mask growing over a still. The film's bloom is the photograph's own morph, which a still cannot carry, so the preset uses the source sequence and the general bloom reads cleaner and rounder than the film. Word spacing in general mode comes from the font's own space, so it matches the film only as closely as ES Serif's metrics do. The stagger after the second word (every 6 frames) is a guess, because the film shows only two words. The pan's character-count estimate is coarse: very wide or very narrow letters need an explicit `pan.dx`.
