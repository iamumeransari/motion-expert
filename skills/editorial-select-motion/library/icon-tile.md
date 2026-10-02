# icon-tile

A flat violet tile carrying a mark arrives on paper and is handled like an object in an editor. The mark is printed faintly into the tile, a slow push carries it in, the corners notch out, the mark turns white and then black, the tile steps up to about twice its size, and four handle chips arrive one corner at a time. The chips glide out, are pressed black one after another while they are pulled in, and glide out again. Then the tile steps to lavender and the accelerating camera pan of the giant pass carries the whole group off. It reads as a tool being picked up. Signature move.

Source: replica s2 frames 180 to 218 and s3 frames 219 to 243 (7.500 to 10.167 s), strips `~/motion-expert/sources/editorial-select/frames/icon-tile-dense.jpg`, `lockup-icon-dense.jpg` and `giant-word-pass-dense.jpg`. The film holds this move on its 16 fps picture cadence: source frames 3k+1 and 3k+2 show one picture.

## Modes

`preset: "replica-s2-tile"` replays the measured per-frame keys of the passing replica for 64 frames from source frame 180 (s2 frames 180 to 218, the tile beat, and s3 shot 1, frames 219 to 243, the rush): the tile's side and centre on every frame (the pan included), each chip's centre, size and pressed state, the mark's scale dip on frames 7 to 9, the notch, look and colour-change frames. The skill holds only that motion and geometry. The measured colours (tile, fade, chips, notches, ink, white, faint) were sampled from the source's plates, so they live outside the skill and arrive as `props.replica` (apply.py sets them from the replica layer). Rebuilt from the block alone over source frames 180 to 215 it scores mean SSIM 0.994 and relative flow error 0.085 (`work/blocks/icon-tile/co-1/cmp/report.md`). Over the full shot 180 to 243, composed with `giant-type-pass` and the ground sequence, it scores 0.989 and 0.135 (`work/blocks/tile-rush/co-1/cmp/report.md`). Both pass.

General mode (no preset) builds the same per-frame state from fitted curves, at any size, any frame and any duration scale, then holds it on the chosen cadence. All values are in frames at 24 fps, multiplied by `scale`:

- the side runs 0.4245 S to 0.4635 S over 7 frames on the snap curve; the notches show pale on 3 and paper from 4; the mark is faint to 4, white from 4 and black from 7;
- the tile steps to 0.849 S on 10, then grows to S over 22 frames on snap;
- the chips are 0.0838 of the current side. They arrive 10 px out from the corners (px at S 384) on 13, 16, 18 and 19, glide out to 43 px from 18, 19.5, 20.5 and 21 over 6 frames, and are pressed black from 27, 28, 28 and 30 for 3 frames while pulled in to 12 px. They glide out to 45 px from 32, 33, 33 and 34 over 6.5 frames;
- the tile steps to lavender on 40;
- the pan starts on 32.5 and follows dx (e^(4.032 u) - 1) / (e^4.032 - 1) over 31.5 frames, with dx = -1.088 W. It was fitted on the tile and the giant word together (rms 15 px).

Every step lands half a frame early, so the step frame shows the new state. Steps are clamped to time zero, because a GSAP timeline that receives a child before zero shifts every child already on it later.

## Slots

| Slot | Shape | Notes |
|---|---|---|
| `mark` | inline SVG markup, an image path, `{ svg }` or `{ src, fit, scale, x, y }` | An SVG should paint in `currentColor`, which the block sets per look: faint (ink at 13 percent), white (`type-light`) and black (`ink`). An image is used as an alpha mask over the look's colour, so it takes the same token colours as an SVG. `scale` is the mark's share of the side (0.5 in the film), and `x` and `y` place its centre as shares of the tile. With the slot empty the block draws a neutral four-lobed placeholder, never a logo. |

## Parameters

| Prop | Default | Notes |
|---|---|---|
| `size` | 0.3556 H | final side in px (384 at 1080) |
| `cx`, `cy` | frame centre | tile centre in px |
| `colors` | tokens | `tile` violet, `fade` lavender, `chip` violet, `chip_fade` violet, `chip_press` ink, `notch` paper, `notch_pale` lavender, `ink`, `white` type-light; palette names (resolved from the tokens.css `--color-*` variables) or any CSS colour |
| `scale` | 1 | duration scale on every default time |
| `keys` | | `{ white, black, step, chips, press, release, lavender, pan }` in s from t0, each one snappable to a beat |
| `beats` | | s from t0; when `keys` is absent they drive `step`, `chips`, `press` and `pan` in that order |
| `pan` | `{ dx: -1.088 W, dy: 0, frames: 31.5, K: 4.032 }` | `false` for no pan; give `giant-type-pass` the same pan to keep the two locked |
| `chips` | true | `false` hides the handles |
| `cadence` | `"16fps"` | `"twos"` or `"ones"` |
| `phase` | 0 | source frame index at t0 mod 3, for the 16 fps grid |
| `duration` | until the pan ends | s |
| `exitAt` | | s from t0, hard out |

Duration range: 1.3 to 3.5 s at scale 1 (the film's run is 2.67 s from arrival to the cut); `scale` stretches it from about 0.75 to 1.5.

## Proofs

- Replica: `work/blocks/icon-tile/plan-replica.json`, render `work/blocks/icon-tile/co-1/render.mp4`, report `co-1/cmp/report.md`, and the composed shot in `work/blocks/tile-rush/co-1/`.
- Demo: `work/blocks/icon-tile/plan-demo.json`, render `work/blocks/icon-tile/co-1-demo/render.mp4`. It runs at 1080 x 1920 with a stand-in spark mark, orchid fading to mist, timing scaled 1.25, cadence on twos, the four main events on beats and the pan turned vertical.

## What did not generalise

The chip timings come from one take, so the per-corner offsets are the film's rhythm rather than a rule. The faint first look is ink at 13 percent; with a light tile colour it can vanish. A raster mark keeps only its alpha, so a mark that relies on inner colours should come in as SVG. The pan's default dx is set for a landscape frame, so in a narrow frame pass the same pan the giant pass uses.
