# type-fill-echo

A dark grey serif line on paper glides in from the right and settles dead centre, holds, creeps larger, punches up on a hard ease-out, and on the punch its letters turn into windows onto a picture that stays fixed to the frame. Two frames later echo rows of the same line, about 1.66 times the punched size and filled from the same picture, land above and below it, cropped by the frame. It is the film's "Launch it" beat: the line is the promise and the fill is the payoff, so give it the word that names the result.

Signature: yes. Source: s5 shot 27, film frames 637 to 686 (26.542 to 28.625 s).

## Slots

| slot | what fills it | notes |
|---|---|---|
| `paper` | `{ src | frames | color }` | behind the line; default `--color-paper` |
| `fill` | `{ src, fit, focal: [x, y] }` | seen only inside the letters of the line and every echo; fixed to the frame, so the letters move over it and the picture never moves |

An empty `fill` renders the hatched placeholder, which is the code-and-slots view.

## Text parameters

`text` (any length), `cap` (cap height as a share of frame height, 0.171), `baseline` (share of height, 0.594), `maxWidth` (largest ink width at the punch as a share of frame width, 0.9; longer words are set smaller), `ink` (colour token, `--color-ink-grey`). Set in ES Serif as SVG text; widths come from the font's own metrics through `__esKit.measure`, so the line is centred on its ink before paint.

## Timing

Default run about 2.1 s (50 frames) to the echoes, then it holds until `exitAt` or the scene ends. `speed` scales the glide, the creep and the punch's start (0.6 to 1.6 tested in the envelope; the punch itself stays 10 frames because its snap is the point). `beats: [punch, creep]` in seconds from t0 puts the punch on a beat; the fill lands on the next cadence frame and the echoes two and three frames later. Every change is a per-frame key sampled on the film's sixteen-a-second picture (`cadence` "16", or "twos", or "none").

Curves: glide cubic-bezier 0, 0.6, 0, 1 over 18 frames from 0.19 of the width to the right, starting a frame before t0; creep 1 to 1.064 about the frame centre on 0.5, 0, 1, 1.1 from 0.79 s for 21 frames; punch to 1.251 on 0, 0.8, 0.1, 1 over 10 frames.

## Echo rows

`echoes` is a maximum (default 2) and `echoScale` the size against the punched line (1.66). The first row goes below, shifted left by 1.30 em of the punched line, as in the film; each later row takes the side with more room, stacked on the film's gaps (main cap top to upper baseline 0.53 em, main baseline to lower cap top 0.395 em, scaled by the echo size between echo rows). A line with descenders opens each gap by 0.22 em, since the film's line has none. A row the frame would crop to under 35 percent of its cap height is dropped. Echoes keep creeping 0.25 percent a frame.

## Presets

`replica-s5-shot27`: the measured per-frame transform of the traced line (dark, fill, both echoes) over ES Serif "Launch it" set at pen 290, baseline 660, 316 px, which overlays the traced outline at IoU 0.94. Rebuilt from the block alone with `paper.png` and `fill-launch.png` as slot fills it scores mean SSIM 0.985 and relative flow 0.115 (bar 0.975 and 0.15), so no glyph override was needed.

The white phase that follows on the magazine plate (s5 shots 28 and 29, frames 687 to 701: the punched line in white steps to 0.704 on 693 and is gone on 697) is not a preset here; it is a hard cut to a new plate with a one-frame scale step, which a plate block and a type step carry.

## Not generalised

The bottom echo's left shift is the film's single measurement and is kept as a share of the punched line, so narrow frames crop it harder than the source. The fill picture is a frame-fixed slot; the film's picture also stays put, so nothing here pans it.
