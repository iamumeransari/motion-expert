# select-handles

The four-chip selection of the film, reusable around anything. Flat square chips sit on the corners of a box and move from one box to the next in one of four ways: a glide on the snap ease that starts a frame before its time, a jump that drops a new set on a bigger box while the old set lingers three frames (the grow-with-target nest), a pop that lands the chips at once, optionally large and settling, and a collapse that streaks all four inward to the box centre and vanishes. While a chip travels it is drawn as a segmented streak: a leading piece and a trailing smear with a two pixel gap, each the chip swept between two earlier sample times and turned along the path, the way a multi-sample shutter breaks a fast move. Every glide is sampled on the film's sixteen pictures a second, so the handles step rather than slide.

The engine is the select module of the shared runtime (`window.__esRuntime.select`), so `genre-word-card` and any later block wrap their own targets with the same code; `select.around(rect, pad)` turns a target rectangle into chip-centre corners.

Signature: yes (the handles of `select-title`, `select-grow`, `icon-tile` and `type-on-select` in moves.md).

Source: s1 shots 1 to 7, film frames 0 to 78, chip rectangles measured per frame: 24 px chips with their colours sampled from the plate under each, the glide from frame 9 landing by frame 15, streak pieces such as 746 to 771 and 773 to 828 px on frame 10, the nested jump on frame 72.

## Modes

`preset` replays the measured rectangles: `"replica-s1-shot1"` to `"replica-s1-shot7"` play one shot with frames counted from its first frame, `"replica-s1-cards"` the whole run. Each frame carries its own list of rectangles (a chip and its streak pieces), stepped at t0 + (f - 0.5) / 24. In another frame size the rectangles scale from 1920 wide. The skill holds the rectangles only; the top and bottom colour measured for each one arrives as `props.replica` from `work/replica/presets/select-handles.json` (fed by `work/replica/presets/apply.py`), and without it every rectangle takes `color` (type-light by default).

General mode takes `keys` (or `targets`), a list of boxes over time, and builds the moves from the fitted values: glide six frames on the snap ease from a frame before `t`, jump with a three frame linger, pop with a three frame settle from `chip_from`, collapse with a two frame hold.

## Slots

None. The block draws only chips, so it sits over any picture or element.

## Text

None.

## Props

| prop | notes |
|---|---|
| `keys` or `targets` | `[{ t, box: [x0, y0, x1, y1] }]` with chip centres in px, or `{ t, rect: [x, y, w, h], pad }` with the chips `pad` px (or [px, py]) outside the rectangle. Per key: `mode` (`pop` first, `glide` after by default, `jump`, `collapse`), `dur`, `lead`, `linger`, `settle`, `chip`, `chip_from`, `color` or `colors`. |
| `chip` | px, 24 at 1080 (`--chip`). The film lands select-grow chips at 38 and settles them at 26: `chip: 26, chip_from: 38`. |
| `color`, `colors` | a token name (`violet`, `type-light`) or any CSS colour or gradient, or four of them for the corners tl, tr, bl, br. The film samples them from the picture under each chip; render() cannot read pixels, so pass the sampled colours. |
| `streak` | `false` for plain squares, or `{ pieces: [[a, b], ...] }` in frames of lag (default `[[0, 0.5], [0.75, 1.5]]`). |
| `cadence` | `"16"` (default), `"twos"` or `"ones"`. |
| `ease` | a tokens.json curve, `snap` by default. |
| `durScale` | multiplies every key time and duration. |
| `beats` | key times in seconds when the keys give none. |
| `exitAt` | seconds after t0 when the last set disappears. |

## Duration

A glide takes six frames (0.25 s) and a jump lands in one; a selection can hold as long as the plan wants. The film's runs hold a box for 0.3 to 1.4 s between moves.

## Proof

- Replica `replica-s1-shot3` (s1 shot 3, frames 24 to 36, the card with four different chip colours and the outward glide) passes the replica bar through the replica layer: SSIM 0.9915 (worst frame 0.9912), flow relative error 0.056, moves within a frame (`work/blocks/select-handles/co-1`, byte-identical to the runtime proof `rt-1`; the published 0.990 and 0.054 of `replica-2` read 0.9915 and 0.056 under the current compare.py). The picture and the word come from `genre-word-card` with its own handles off, so every handle pixel in the score is this block's.
- General-mode demo at 1080x1080: violet handles select a picture, glide to the word under it, nest onto the word as it steps up 1.29x, glide back and collapse (`work/blocks/select-handles/demo-co-1`, identical to the earlier demo).

## What does not generalise

The film's chips never fully rest: they creep outward between cuts and stretch a few frames before the next one, which only the preset reproduces. Colours sampled from the picture have to be passed in. The measured streak geometry varies frame to frame in ways the two-piece model only approximates (on frame 10 the leading piece is a near square, by frame 12 it is twice as long).
