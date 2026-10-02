# chromatic-title

One serif line slides in from the right and settles word by word over a run of colour fields that cut on the film's 16 fps picture cadence, then the fields cut away to a paper card where every word takes its own gradient and a slow exponential push carries the frame in. It is the film's moment of spectacle resolving into calm: colour breaks loose for about three seconds and comes to rest in one sentence. Signature move.

Source: replica section s3, shots 2 to 9 (source frames 244 to 339, 10.167 to 14.167 s). Rebuilt from this block alone it scores mean SSIM 0.980 or better on every shot and relative flow error 0.143 at worst, with all 7 cuts on the source frame (`work/blocks/chromatic-title/replica/cmp-1/report.md`).

## Modes

`preset: "replica-s3-line"` replays the measured per-frame keys from `work/replica/s3`: per-letter x positions of "The most precise edit model", the line's x, y and per-word drop on every frame, the card's push scale, the 13-stop gradient of every word and the field schedule (six fields, one two-frame dissolve at 0.4). It is set in **ES Line** (`var(--font-line)`), the face traced from the film's own line, because no open face matched it. It reproduces the source at 1920 x 1080 and ignores the general props below except `images`, `card`, `white` and `exitAt`.

General mode (no preset) rebuilds the same motion from fitted curves, so any words, any number of fields, any duration scale and any aspect work. It is set in **EditorialSelect Serif** (`"ES Serif"`, the style's face) unless `font` says otherwise. ES Line only carries the 14 letters of the source line, so never use it for new words.

## Slots

| Slot | Shape | Notes |
|---|---|---|
| `fields` | array of `{ frames: [src...] or src, dur, at, fit, focal, rate, loop, dissolve }` | Each field is an image sequence (or a still). `dur` in seconds (scaled), `at` an absolute start in seconds that overrides the running sum and is how a cut snaps to a beat. `rate` is `"picture"` (default: one image per new picture, so the 16 fps holds repeat), `"frame"` (one image per 24 fps frame) or a number of images per second. `loop: true` cycles a short sequence. `dissolve: { dur, op }` lays the incoming field at `op` (0.4 in the source, or `"ramp"`) over the outgoing field's frozen last picture. `fit` is `cover` or `contain`, `focal` is `[x, y]` from 0 to 1 and sets the crop. |
| `images` | array of src | Preset only: the 66 field pictures the preset's schedule indexes. |
| `card` | `{ src, fit, focal, color, at, hold, palette, gradients }` | The paper under everything. `src` is an optional paper texture, `color` defaults to `var(--color-paper)`. `at` (seconds, absolute) is the cut to the card, defaulting to the end of the last field; `hold` (seconds, scaled) how long it runs, 1.17 s in the source. |

The block expands nothing at render time: a sequence must be listed frame by frame in the plan, because `build-composition.mjs` copies only the paths it sees in props.

## Text parameters

- `words`: the line, a string with `\n` for a row break (portrait frames want two rows). Default "The most precise edit model".
- `font`: CSS family list, default `"ES Serif", Georgia, serif`.
- `size`: px at the frame's width. When absent the block measures the widest row from the face's glyph metrics (canvas `measureText`, re-run once on `document.fonts.ready`) and takes the largest size that keeps it inside `fill` (0.84 of the width, the source's measure), capped at the source size (125.7 px at 1920 x 1080) scaled by the larger of the width and height ratios, times `size_scale`, so a portrait frame with two rows sets larger type.
- `leading` (row pitch in ems, 1.12), `y` (block centre as a share of the height, 0.504).
- `white`: the line colour over the fields, default `var(--color-type-light)` (the preset uses the measured #F0ECF0).
- `card.palette`: colours for the per-word gradients on the card, word k running from `palette[k]` to `palette[k+1]`. Default is tokens: steel-blue, violet, orchid, lavender, cycled. `card.gradients` gives explicit per-word stop lists `[[offset, colour], ...]` instead.

## Timing

All in seconds at 24 fps. `scale` (default 1) stretches every duration and rate: the slide, the word settles, the push and each field's `dur`; absolute `at` times and `beats` are not scaled, so cuts stay on the music. With `props.beats` and no `at`, field j starts on beat j-1 and the card lands on the beat after the last field.

- `line_in`: when the line appears (0). `slide_dur`: the glide home, 2.01 s at scale 1; `slide_dist`: entry offset as a share of the width (0.0767).
- `settle_amp`: multiplies every word's drop (1).
- `push: false` holds the card still.
- `cadence: false` turns off the 16 fps holds; `cadence_phase` (1) sets which local frames hold (frames where (f + phase) mod 3 = 2 repeat the frame before).
- `exitAt`: the line and fields are gone from this time.

Duration range: about 2.5 to 6 s. Below 2.5 s the slide cannot finish before the card; above 6 s the line has long settled and the move reads as a hold. The source runs 4.0 s (2.83 s of fields, 1.17 s of card).

## Fitted curves (general mode)

- Slide: offset `D * g(t / T)`, `g(u) = 0.80 (e^(-17.04u) - e^-17.04) / (1 - e^-17.04) + 0.20 (1 - u)`, T = 48.3 frames, D = 0.0767 W (rms 0.98 px on the source). A fast exponential settle rides a slow linear drift that stops dead, which is what makes the line feel carried rather than eased.
- Settle: word k drops `size * A(c) * e^(-r(c) n)` with c the word's centre along its row (from character counts, so no layout read), A = 0, 0.017, 0.143, 0.569, 0.937 and r = 0.41, 0.41, 0.196, 0.145, 0.152 per frame at c = 0.05, 0.23, 0.46, 0.67, 0.88, interpolated. The right end trails and lands last.
- Push: `s(m) = 1.0162 - 0.0405 e^(-0.1336 m)`, m in frames since the card, about the frame centre (measured 962.7, 544.2).

## What did not generalise

The card gradients in the source were sampled from the plates (each word carries the colours of the fields behind it); general mode takes a palette instead, because reading pixels at render is impure. The per-word settle is fitted on one five-word line, so lines of one or two words settle with almost no stagger, and long lines put more words in the heavy trailing range. With stacked rows the trailing words of the first row drop into the second row for the first few frames, as in the demo; pass `settle_amp: 0.6` when that reads as a collision. The 8.8 px offset between the white line's rest and the card line's rest in the source is dropped in general mode.
