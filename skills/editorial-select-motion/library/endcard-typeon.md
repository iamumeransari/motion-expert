# endcard-typeon

The end card. A sentence types on word by word inside violet pixel-bar handles that open out past the line with each word and then pull in to four corner chips. The line cuts out, the handles come back as diagonal pixel-step brackets around a chip where the mark will be, the mark grows inside them while the brackets shrink to corner chips, blink faint and go. The lockup (mark plus wordmark) cuts in already sliding left on an exponential ease, and the tagline drops in under it on a single frame. Signature: yes, it is how the film closes.

Source: replica s8, film frames 993 to 1135 (41.375 to 47.381 s), strip `assets/frames/end-card-dense.jpg`. Measurement and preset tables: `work/blocks/endcard-typeon/tools` (`extract.py`, `fit_diag2.py`, `fit_curves.py`, `make_preset.py`, `inject.py`).

## How it is built

One driver tween runs a frame index from one frame before `t0` to the end, and a `modifiers` function paints the state for that frame, so seeking either way is exact and nothing depends on callbacks. A state is a list of violet rectangles (bars, bracket steps, chips), a word count and position for the line, a box for the mark slot, a box for the wordmark slot and a position for the tagline. Text is SVG text in EditorialSelect Serif placed by its ink edge and baseline, with the ink edge read from canvas glyph metrics at paint time, and the metrics are taken again once `document.fonts` reports loaded, so a different sentence of any length lands in the same place. Everything steps on the film's 16 fps cadence (film frames 3k+2 repeat 3k+1) unless `cadence` says otherwise.

## Modes

`preset: "replica-s8-endcard"` reads the measured keys embedded in the element: per frame word count and ink left (frames 0 to 27), the top-row bar segments (rows 25 px tall at y 417 and 636), the bracket steps on frames 28 to 30 as measured pixel-step rectangles, the brackets on 31 to 35 as fitted staircases of squares, the chips on 34 to 42 (faint at half alpha on 39 and 42), the mark box on 30 to 41, the lockup's mark x on 42 to 142 and the tagline from frame 70. It reproduces s8 at mean SSIM 0.992 and relative flow error 0.037 (compare.py replica mode, `work/blocks/endcard-typeon/cmp-2`). The preset scales uniformly into another frame size and centres, but its geometry belongs to the s8 sentence and lockup, so new words need the general mode.

General mode rebuilds the same states from curves fitted on s8, in units of the body size `s` (chip `c` = 0.236 s, mark width `M` = 1.645 s):

- each word's arrival shows one of four measured dashed bar patterns, cycling, with the handles opened out by a measured pad (1.81, 0.57, 2.19, 0.70 s); a gap of three frames or more shows the solid bar (5.2 c, pad 1.48 s) on the next picture;
- after the last word a solid bar of 4 c shrinks to one chip on 1 minus e^(-0.605 f) from one frame after the word, while its outer edge moves from 0.10 s to 0.51 s past the line on 1 minus e^(-0.715 f);
- at the collapse the brackets follow eleven measured keys (frames 0, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15 after the cut) in units of M and c: coarse steps with a 2 c centre chip, an opened smooth bracket, shrinking brackets, corner chips, faint, off, faint, off;
- the mark appears two frames after the collapse at width M times 1 minus e^(-0.45 (f - 0.25));
- the lockup cuts in 14 frames after the collapse, already sliding from the mark's centred position to the centred lockup on 1 minus e^(-0.25 (f + 2.5));
- the tagline cuts in 42 frames after the collapse.

`scale` stretches every one of those offsets and rates, and every time snaps to the next new picture of the cadence.

## Slots

- `mark`: `{ svg }` inline markup taking `currentColor` (ink), or `{ src, fit, focal: [x, y] }`; `aspect` (width over height, default the s8 mark's 1.084).
- `wordmark`: `{ src, fit, focal, aspect, h, cap: [top, bottom] }` for artwork (h in body sizes, default 1.79; cap is the fraction of its height the cap band spans, default 0.071 to 0.729, which is how it centres on the mark), or `{ text, size, tracking }` set in the serif (size in body sizes, default 1.71). Leave it out for a mark-only lockup.
- `paper`: `{ src, fit, focal }`, or omit for `--color-paper`, or `false` for no ground.

## Text parameters

`sentence` (any words), `tagline` (string or `false`), `size` (body px; default sizes the line to 0.766 of the frame width within 0.5 to 1.6 of the film's size scaled to the frame, then fits it inside the margins), `tracking` (em, default -0.0076), `font` (canvas family string, default `"ES Serif"`), `cx`, `cy` (fractions of the frame). The tagline is 0.63 s tracked 0.0225 em, 1.40 s below the wordmark's baseline. The lockup shrinks as a unit if it would pass the 64 px margins.

## Timing

All in seconds from `t0`: `wordTimes` (one per word, snap them to beats) or `wordGap` (default 0.073, the film's 1.75 frames), `collapseAt` (default last word + 0.875), `lockupAt` (collapse + 0.583), `taglineAt` (collapse + 1.75), `exitAt` (everything off; default the scene end), `scale` (default 1), `cadence` (`"16"` default, `"twos"`, `"ones"`) and `abs0` (the cadence phase, the film frame index at `t0`, default 0). Duration from first word to tagline: about 2.9 s at scale 1, workable from about 2 s (scale 0.7, fewer words) to 6 s (scale 2). Returns the settle time, when the lockup has stopped.

## Colours

Bars and brackets `--color-violet`, ink `--color-ink-soft`, ground `--color-paper`.

## Did not generalise

The bracket pulse after the collapse is a measured sequence of discrete pixel states, so in general mode it is the s8 keys rescaled rather than a continuous curve. The partial lines in the film sit slightly left of centre while typing, by amounts that follow no rule found; general mode centres each partial line. The wordmark artwork needs its cap band given, since an image's letterforms cannot be measured at render.
