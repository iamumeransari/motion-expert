# genre-word-card

A run of hard-cut cards, each one serif word centred between four selection-handle chips over a full-bleed picture. On every cut the picture and the word change in the same frame. The word's letters arrive crowded or spread and snap to their set spacing over six frames on the snap ease, stepping on the film's sixteen pictures a second, while the handles glide from the last word's box to the new one, starting a frame before the cut and streaking as they travel. The cuts tighten as the run goes on. An optional step-up on a card scales its word by about 1.3 in one frame while a second set of handles lands on the bigger box and the old set lingers three frames, which is how the film turns the run into its next beat.

Signature: yes (`select-title` in moves.md, shots 2 to 7).

Source: s1 shots 1 to 7, film frames 0 to 78 (0.000 to 3.292 s), "Art", "Design", "Photography", "Editorial", "Film", "Ecommerce" and the "Ecommerce" step, measured per frame in `work/replica/s1` (title-words, chip-rects, plate-seq).

## Modes

`preset` replays the replica's measured keys. `"replica-s1-shot1"` to `"replica-s1-shot7"` play one shot with frames counted from that shot's first frame; `"replica-s1-cards"` plays all seven from frame 0. Each card keeps its glyph positions per frame, converted from the replica's traced-ink pens to ES Serif glyph boxes (each glyph's ES Serif ink centre sits on the traced ink centre, at the size whose cap matches the traced capital, 144.7 to 147.1 px, and 189 and 217.7 px on the two step poses). The fill colour of each word is the mean of the film's speckled fill under an eroded glyph mask, because the letterpress grain darkens it and the comparison's prefilter reads the mean. The handles are the measured chip rectangles of the shot (the same data `select-handles` carries, so this block stands alone) and the Film shot keeps its plate camera as per-frame matrices. Every key steps at t0 + (f - 0.5) / 24. The plan fills the picture with `image` (one shot) or `images[]` (one per card), each a still or a `seq` of `{f, src}` frames counted from the block's start, which is how the photo-sequence shots are fed in replica mode.

General mode builds the same choreography for any words and pictures. Glyph positions come from ES Serif's advance widths and kerning, so any word length lays out without reading layout. The cut lengths cycle the film's 10, 14, 13, 15, 12 and 8 frames (times `durScale`) unless a card gives `dur` or the plan gives `beats`, and every cut is moved off the film's repeated frame. The entry spread defaults to the ratio of the last word's ink width to this one's raised to 0.3 and held between 0.70 and 1.27, which reproduces the film's pattern (a longer word arrives condensed, a shorter one spread). Handles sit 0.5 cap outside the ink left and right and 0.58 cap above the cap line and below the baseline.

## Slots

| slot | kind | notes |
|---|---|---|
| `cards[].image` (or `images[]`, or `image` in a one-shot preset) | image slot per card | `{src, fit, focal: [x, y], zoom, label}` or `{seq: [{f or t, src}]}`. Full bleed by default, or inset by `imageBox` [x, y, w, h] as frame shares. Crop and focal point are code; without a `src` a labelled placeholder draws. |

## Text

| param | face | notes |
|---|---|---|
| `cards[].word` (or `words[]`) | ES Serif | any length; cap 102 px at 1080 (`cap`), centred on `wordX` (0.5) with the baseline at `wordY` (589/1080). Never `x` or `y`, which the runtime reads as the element's own position. `tracking` in em per card or for all. `color` is a token (type-light by default) or CSS. |

## Other props

`enter` (per card or for all; 1 turns the tracking snap off), `step: {at, scale}` per card, `chipColor` or `chipColors` [tl, tr, bl, br] per card or for all (the film samples them from the picture under each chip, so pass colours picked from the image), `chip` (24 px at 1080), `streak` (false or pieces, see select-handles), `pad` [x, y] in caps, `handles: false` to draw the cards alone, `durScale`, `beats` (cut times in seconds), `cadence` ("16", "twos" or "ones"), `exitAt`.

## Duration

0.3 to 0.9 s per card (the film runs 0.33 to 0.63 s); a run of five or six cards lasts 2.5 to 4 s. The tracking snap and handle glide take six frames each whatever the card length, so cards shorter than about eight frames show the word still moving at the cut, as the film's last card does.

## Proof

- Replica `replica-s1-shot2` (frames 10 to 23) passes the replica bar from this block alone: SSIM 0.992 (worst frame 0.991), flow relative error 0.077, moves within a frame (`work/blocks/genre-word-card/replica-2`).
- Replica `replica-s1-cards` over frames 0 to 71 (six cards, five cuts) lands all five cuts on the source's frame and every move within a frame. With the render's colour tags matched to the untagged source (pixels unchanged), every shot passes, SSIM 0.989 to 0.997 and flow at most 0.149 (`replica-cards-2/cmp-untagged`). As rendered it fails two gates: shot 6, the dark Ecommerce plate, reads 0.971, because compare.py decodes a bt709-tagged render to luma differently from the untagged source (the same pixels score 0.989 untagged), and shot 5's flow reads 0.153 where its motion is 0.24 px of grain.
- General-mode demo at 1080x1920 with five new words and stand-in pictures (`work/blocks/genre-word-card/demo`).

## What does not generalise

The film samples each chip's colour from the picture under it, and render() cannot read pixels, so general mode takes chip colours as props. The film's chips also never fully rest (they keep creeping outward and stretch a few frames before the next cut); general mode lands them and holds. The letterpress speckle in the film's fill is not drawn; the preset matches its mean tone instead.
