# lockup-scramble

One line of serif type becomes the next without a transition. The old line loses its letters at random, a few per picture, the survivors staying exactly where they were, while the new line's letters appear at their final positions in violet among the leftovers. When the new line is complete it turns black in one step and holds with a breathing scale small enough to feel rather than see (a swell of 0.37 percent that peaks three frames in and eases to minus 0.30 percent). Then its tail changes typeface on every second picture, through mono, pixel, humanist, bitmap and grotesk faces, while the whole line steps up in size towards overflow, and the block ends on the next cut. It is the film's "announce the name" move: the scramble says something new has arrived, the hold lets it read, and the cycle says the name can take any shape.

Signature: yes (`glyph-scramble` and `font-cycle` in moves.md, shot 8, frames 127 to 179).

Source: frames 128 to 179 of the film (5.333 to 7.500 s), rebuilt in work/replica/s2. The scramble pictures fall on frames 129, 130, 132, 133, 135 and 136 (the 16 fps cadence), incoming letters are violet `#9B7FD8` on 133 to 135 and black on 136, the hold runs 137 to 164, the faces change on 165, 168, 171, 174 and 177 while the line grows 1.27 times, and the frame cuts on 180.

## Modes

`preset: "replica-s2-lockup"` reproduces the source range frame for frame. The block holds only its motion: the frame each of the 13 type states lands on, which of them are passing scramble pictures, the cycle's face order, the measured scale keys of the hold and the end frame. The glyphs of every state (each fitted to its source frame in ES Serif or the cycle face: characters, size, position, horizontal scale) and the two sampled colours belong to the source, so they live in the replica layer (work/replica/presets/lockup-scramble.json) and arrive as `props.replica`, which work/replica/presets/apply.py writes into a replica plan; the block reads the merged preset through the shared runtime's `preset()`. A preset named without its replica layer falls back to the general mode. The frame 128 leftovers, the grid rules and the last photo tile of the scatter, pass in as `grid` and `tile`. Steps land half a frame early, as in the replica.

Without a preset the general mode composes the same states arithmetically from glyph metrics (ES Serif from the shared table, the cycle faces from their own tables inside the block), so any words and any frame size work.

## Slots

| slot | kind | notes |
|---|---|---|
| `paper` | image, full frame | optional ground under everything (the replica uses the source's clean paper); leave out and the scene background shows |
| `tile` | image | `{ src, fit, focal, zoom, rect: [x, y, w, h], until }`, a photo tile left over from a previous block, removed at `until` |
| `grid` | code | `{ x0, dx, y0, dy, color, shade, until }`, one px rules in `color` (default the grid-rule token) with a soft neighbour in `shade` (default a 4 percent wash of the ink token), removed at `until` |

`until` is seconds after the block's start in the general mode and a frame index in the preset.

With no words and no slots at all the general mode shows its code-and-slots view: the tile is drawn as a labelled placeholder at its default rect (centred, 270 by 274 px from 0.63 of the height) until the font cycle starts. `placeholders: true` or `false` forces that view on or off; the paper is never drawn as a placeholder, since the scene background stands in for it.

Every colour and face the general mode draws comes from tokens or from props that default to tokens: the line in `ink` (ink token), arrivals in `incoming` (violet token), the faces through the `--font-serif`, `--font-mono`, `--font-pixel`, `--font-humanist`, `--font-bitmap` and `--font-grotesk` variables, the grid in `grid.color` and `grid.shade`, so another token set re-skins the block without touching it.

## Text parameters

| prop | default | notes |
|---|---|---|
| `from` | none | the outgoing line, ES Serif at `fromCap` (77.6 px cap); without it the block opens on the black lockup |
| `to` | "Headline Lockup 1.0" | the lockup, a neutral placeholder by default |
| `lead` | 1 | how many words stay in the serif; the rest is the tail that cycles faces |
| `cap` | 84.4 | lockup cap height in px at a 1080 short side; shrunk until the line fits inside `margin` (64) |
| `x`, `y` | 0.4975, 0.4907 | centre of the cap band as frame shares |
| `faces` | mono, pixel, humanist, bitmap, grotesk | the cycle, any of serif, mono, pixel, humanist, bitmap, grotesk |
| `tailMatch` | 0.97 | tail cap height against the serif's |
| `ink`, `incoming` | ink, violet | token names or CSS colours |

## Timing

All in seconds, multiplied by `durScale`, and every step is snapped to the film's 16 fps cadence (`cadence: "twos"` or `"ones"` to change it).

| prop | default | range that still reads |
|---|---|---|
| `scramble` | 0.333 (8 frames) | 0.25 to 0.6; under 4 pictures it reads as a cut |
| `hold` | 1.208 (29 frames) | 0.5 to 2.5 |
| `breathe`, `breathePeriod` | 0.0037, 1.667 | 0 turns it off; above 0.01 it reads as a zoom |
| `every` | 0.125 (3 frames) | 0.083 to 0.25 per face |
| `endScale` | 0.96 of the frame width | the source grows 1.273 times, to 0.96 of the width; set it to overflow on purpose or to 1 to keep the size |
| `seed` | 7 | the order letters drop and arrive in |
| `beats` | none | times (s after t0) for the cycle steps, one per face, overriding `every` |
| `exitAt` | after the last face | when the type goes |

Whole block: 1.2 to 4 s; the source runs 2.17 s.

## How it generalises and what does not

Any line in and any line out, any length, any aspect: widths come from metrics, so a long lockup shrinks to fit and a portrait frame keeps the source's type size. The scramble is generated, so it carries the hand (a seeded order, leftovers in place, violet arrivals, the black step) but not the source's particular pictures; the source's mid-scramble pictures also show letters at stray sizes, which only the preset reproduces. The font cycle is limited to the six faces the style ships, and the bitmap face (VT323) stands in for a bolder pixel display face the film uses. The humanist face's kerning is class based and is not in its metrics table, so its widths run a few px loose.

## Proof

work/blocks/lockup-scramble. The preset rebuilt from this block alone (`plan-replica.json` fed with the replica layer by apply.py, the clean paper plate and the frame 128 tile as slot fills, the grid's `shade` pinned to the source's measured wash) passes the replica bar against `source-replica-s2-lockup.mp4` at high quality: shot SSIM 0.9913 (worst frame 0.978 on frame 47), flow relative EPE 0.1187, both measurable moves within a frame, 52 of 52 frames, offset 0 (`co-2/cmp/report.md`). These are exactly the numbers of the earlier `replica-2` render re-scored with the current compare (`rescore-1`); 46 of 52 frames are bit-identical to it and frames 46 to 51 differ at 61 dB PSNR or better. `plan-demo.json` runs the general mode at 1080 by 1920 with other words and a stand-in tile (`demo-co-2/render.mp4`, draft), and `plan-noprops.json` runs it with no props at all, showing the labelled tile placeholder (`noprops-1/render.mp4`, draft).
