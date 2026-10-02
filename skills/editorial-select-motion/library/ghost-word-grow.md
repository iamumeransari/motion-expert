# ghost-word-grow

A giant ghost word fills the paper in pale grey, cropped by every edge, and a small black serif word sits on it at the centre. Photo tiles pop in around the word one picture at a time with no tween, the word steps up to twice its size in a single picture, and then violet chips land around a tile that has been pulled in behind the word. The tile holds for two frames and grows on an accelerating curve into the cut, showing more of its picture rather than stretching it, while its chips streak diagonally outward. The block ends mid-growth on purpose, because in the film the next shot (crop-select) catches the tile and keeps growing it. Signature: yes (`ghost-word` and `tile-pop` in moves.md, shots 31 and 32).

Source: s6 shots 1 and 2, film frames 733 to 759 (30.542 to 31.667 s). The replica keys come from the passing s6 replica in `work/replica/s6`.

## Slots

| slot | what fills it | notes |
|---|---|---|
| `paper` | optional image slot | flat `--color-paper` when absent; the replica uses the masked temporal median of the source |
| `tiles[]` | image slots `{ src, fit, focal: [x, y], box, art, label }` | cover-cropped by code at the box; `box` is `[x, y, w, h]` as fractions of the frame and overrides the default layout; `art` is an optional transparent overlay (SVG or PNG) riding the tile, which is how the replica draws the traced magazine print |
| `select` | image slot `{ src, focal }` | the picture pulled in behind the word; it is laid out at the final box size and the growing box is a window onto it |

With no `src` a slot draws a labelled hatched placeholder, which is the code-and-slots view.

## Text parameters

`word` (default "Big"), `ghost` (defaults to `word`; repeated across the row until it crosses both edges), `cap` (small word cap height in px at a 1080 short side, default 85), `stepRatio` (1.994), `tracking` (em), `font` (family, default "ES Serif"), `ink`, `ghostColor` (token names or CSS colours, defaults `ink` and `ghost`), `ghostCap` (0.867 of the short side), `ghostY` (baseline as a share of the height, 0.56), `wordY` (cap centre as a share of the height, 0.5), `wordDrop` (how far the word sinks with the growth, 0.094 of the grown cap). Every word is laid out from EditorialSelect Serif's glyph metrics (`__esShared.layout`) and centred on its ink, so any length works without reading the DOM.

## Timing

All times are source frames at 24 fps times `scale`, snapped forward onto the film's 16 fps cadence (frame l repeats l - 1 when l mod 3 equals `phase`, default 1, the source's phase). Defaults: tiles pop on frames 3, 6, 9 and 14 (a fifth and later tile every 3 frames after 14), the word steps up on 11, the selection lands on 18, grows from 21 to 26 on bezier (1, 0.019, 0.676, 0.248) from 0.81 x 0.85 to 2.08 x 2.45 of the grown cap, and the picture inside zooms 1.047 with it. `props.beats` (seconds after t0) replaces the pop times with the first beats and the step with the next one. `exitAt` hides the block in one picture. Duration 27 frames at scale 1 (1.125 s); the useful range is scale 0.75 to 2 (0.85 to 2.25 s). `animate` returns the end of frame 26.

Selection chips are 24 px squares (`chip`, colour `chipColor`, default `violet`) about 0.115 of the grown cap outside the tile's corners; when a chip moves more than its own size in one picture it is drawn as the square swept from its last position, the film's streak.

## Presets

`preset: "replica-s6-1-2"` plays the measured per-frame keys of the source shot (ghost and word glyph by glyph in Source Serif 4 on its wght and opsz axes, the four tile boxes and pop frames, the selected tile's window and picture placement, the traced chip shapes per picture). It needs the face "ES Source Serif", which `work/blocks/_style-s67/tokens.css` adds, and slot fills from `work/blocks/ghost-word-grow/calibration-only-plates/` (replica plans only). Rebuild the preset with `work/blocks/ghost-word-grow/tools/make_preset.py`; the growth curve fit is `tools/fit.py`.

## Layering

paper, ghost, tiles (in pop order), selected tile, chips, word. The word always sits over the tiles and the chips, as in the source.
