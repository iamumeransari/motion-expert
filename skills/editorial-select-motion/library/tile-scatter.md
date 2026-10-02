# tile-scatter

Grid paper fills with picture tiles and loose words, and the words then become one sentence. Tiles pop onto the grid on whole pictures and drift the last part of a cell into place; each word lands on its own paper card (two grid cells by one, a shade lighter than the paper, which hides the rules under it) and walks across the grid a cell at a time, two or three pictures per step, waiting or turning when another card is in the way. On the gather the cards vanish and the words stand as one centred line, which swells on an ease-in while the grid grows with it and the tiles drop out a few per picture. Tiles sit above the cards, so a walking word can pass under a picture, as it does in the film. Everything steps on the film's sixteen pictures a second.

Signature: yes (`tile-scatter` in moves.md, shot 8 frames 79 to 127).

Source: s1 shot 8, film frames 79 to 127 (3.292 to 5.333 s), measured in `work/replica/s1` (paper-grid, scatter-words, tile-seq).

## Modes

`preset: "replica-s1-shot8"` replays the replica's measured per-frame keys: the paper tone, the grid rules with their two pixel ink profile and their growth from 1 to 1.017, 195 tile poses (rectangle and frames per held pose), five words with pen, baseline and card corner on every frame, and the sentence's scale, pen and baseline per frame with the three glyphs that drop on frame 127 as the next shot's scramble starts. Words are set in ES Serif, refitted from the s1 traced ink (sizes 83 to 84.5 px, tracking 1.5 to 2.5 px; the sentence 86.75 px, tracking 0.2 px, glyph rms 1.0 px). Keys are source frames counted from frame 79 and step at t0 + (f - 0.5) / 24. The plan supplies `paper` and `images` (one per tile pose, the s1 calibration crops, replica mode only).

General mode builds the same choreography from rules: a seeded layout on the grid, landing times from `beats`, cell steps on the snap curve sampled on the cadence, and the gather on an ease-in.

## Slots

| slot | kind | notes |
|---|---|---|
| `tiles[]` | image slot, any count | `{src, fit, focal: [x, y], zoom, cells: [cw, ch] or aspect, label}`. Size is whole grid cells (default cycle 2x2, 2x3, 3x2, 2x2, 4x2, 2x3, or the cell shape nearest `aspect`); the crop, focal point and drift are code. Without `src` a labelled placeholder draws. |
| `paper` | image slot, optional | a paper texture under the rules; flat `--color-paper-grid` otherwise. |
| `images[]` | preset only | one picture per held tile pose. |

## Text

| param | face | notes |
|---|---|---|
| `words` | ES Serif | array or string; each word gets a card as wide as its ink plus 0.6 cap height, rounded up to whole cells (two at least). |
| `cap` | | word cap height in px at the 1080 short side (default 58, the film's 84 px words). |
| `tracking` | | px (default 2). |
| `lineScale` | | line size relative to the words at the gather and at the end (default 1.14 to 1.34, the film's 1.102 to 1.294 on an 86.75 px line). The line wraps into up to three balanced rows when its swollen width would leave the 64 px margins, and only shrinks if three rows still do not fit. |

Colours: `ink` (default `ink`), `card` (default `paper`), `ground` (default `paper-grid`); rules are `--color-grid-rule`, one pixel at the source scale. Pitch `grid: [120, 121.5]` px at 1080 (tokens `--grid-x`, `--grid-y`), rules through the frame centre.

## Timing

`duration` (default 2.04 s, the shot) times `durScale`. Words land on `beats` (seconds after t0; evenly from 4 to 44 percent of the duration when absent), tiles pop on `tileTimes` (evenly over the first 45 percent) and drift home over `tileGlide` (0.75 s). `gatherAt` defaults to 67 percent of the duration; tiles leave across the back 65 percent of the gather, keeping `tilesKeep` (default 0). `gather: false` keeps the scatter to the end. `cadence` is "16" (default), "twos" or "ones". `exitAt` cuts the whole block one frame before it. Useful range: 1.5 to 4 s; below 1.5 s the walk loses its steps, above 4 s the walk reads as wandering.

Returns the last word's landing time.

## How it generalises, and what does not

Any word count, any tile count and image aspect, any frame aspect (proved at 1080 x 1920 with five words and seven stand-in tiles, three of them second crops of the same pictures by focal point and zoom). The general walk is a rule system, so it keeps the film's grammar (cell steps, waits, tiles over cards, a hard cut to the line, an ease-in swell, tiles leaving a few per picture) but not its exact paths: the film's tiles also swap their pictures while they sit, which general mode does not do, and its words take the long way round on purpose, which the shortest-path walk does not. Tiles never overlap the rows the swollen line will cover, measured from the centre, so a `lineY` away from 0.5 can let a tile sit under the line. The preset's glyphs are a little heavier than the film's sentence, which is lighter than ES Serif's main weight and grainy; it still scores 0.985 or better on the sentence frames.
