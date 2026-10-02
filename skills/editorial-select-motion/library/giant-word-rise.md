# giant-word-rise

A giant solid black serif word rises into the frame from below its bottom edge over a photograph, cropped by the frame on the right and at first on the bottom, drifting left the whole time, and then the photograph is printed into a card on pale paper in two single steps while the word stays full size over it. It is the film's way of shouting the first syllable of the next line before the line itself arrives. Signature.

Source: s5 shot 25, film frames 550 to 562 (moves.md). The word never scales: its baseline climbs 1492, 1339, 1191, 1106, 1050, 1010, 979 px on frames 552, 553, 555, 556, 558, 559, 561 (cubic-bezier 0, 0.5, 0.4, 1 over nine frames) while its left edge steps 38 px left on every picture update. Its cap height is 678 px, 0.628 of the frame height, so only the first three letters of the word fit. The photograph pushes 0.18 percent while the word rises, pulls back to 0.977 on 558 and 559, and is printed to a card at 0.939 of the frame on 561 and 0.796 on 562, showing more picture inside the card than the frame did (content 0.849 and 0.721 about the centre). The word is cut on 562.

## Modes

`preset: "replica-s5-shot25"` replays the measured keys for frames 550 to 562: the camera matrix of every frame, the two card steps, and the word's translate per frame, with the line set in ES Serif at 982 px on baseline 984. The preset holds motion and geometry only. The source's word, its glyph pens, the stroke weight, the sampled paper and ink colours and the outline traced from frame 561 live in the replica layer outside the skill and arrive as `props.replica` (references/sources.md). With a traced outline the block draws it and uses its own fitted keys; with `glyph: false` it sets the word in ES Serif instead, which is close (ink IoU 0.917) but below the replica bar (see Proof). Without a replica layer the preset still runs, setting `text` (default "Word") in the tokens' ink and paper. `skip` starts a preset part way in, which is how card-wipe's replica starts this block at frame 556.

The general mode rebuilds the same envelope for any word, picture and aspect. The word is set in ES Serif with its cap height a share of the frame's shorter side, its first ink edge at `left`, and its middle settling at `middle` of the frame height; it enters with 0.39 of its cap height already above the bottom edge, rises over 9 frames on the fitted curve, and drifts left 0.9 of its cap height a second, all stepped on the film's sixteen-a-second picture. The shrink lands on the first beat.

`layer: "plate"` or `"word"` renders only that half, so another block can sit between the photograph and the word: the film's own shot is `giant-word-rise` (plate), then `card-wipe` (the window of the next picture), then `giant-word-rise` (word).

## Slots and text

| prop | default | meaning |
|---|---|---|
| `image` | striped placeholder | slot `{ src or frames, fit, focal, box }` for the photograph |
| `text` | `"Word"` | the word, any length; the frame crops it |
| `cap` | 0.628 | cap height as a share of the frame's shorter side |
| `left` | 0.134 | first ink edge as a share of the width |
| `middle` | 0.59 | where the word's middle settles, as a share of the height |
| `weight` | 0.0061 | an ink-coloured stroke in em that thickens the face to the film's weight |
| `color`, `paper` | `--color-ink`, `--color-paper` | tokens or literals |
| `speed` | 1 | duration scale |
| `cadence` | `"16"` | `"16"`, `"twos"` or `"none"` |
| `beats` | [9 frames] | `[shrink]` in seconds from the start, snapped to a frame that shows a new picture |
| `shrink` | true | false keeps the photograph full frame |
| `layer` | `"all"` | `"plate"` or `"word"` to interleave another block |
| `glyph` | none | `{ d, x0, y0 }` a traced outline drawn instead of the text; `false` forces the text when the replica layer carries an outline |
| `replica` | none | the replica layer's data for a preset (word, pens, weight, colours, outline), merged over the preset |
| `skip`, `exitAt` | none | start part way into a preset; when the block is gone |

Duration 0.4 to 1.2 s (0.5 s in the film, speed 0.8 to 2.4). The giant word carries `data-layout-ignore`, because it is cropped by the frame on purpose and reads as shape (black on grass in the film, under the AA contrast ratio), so the composited still is its check.

## Proof

`work/blocks/giant-word-rise/co-1`: plate, card-wipe window and word from the blocks alone with the traced outline from the replica layer, against film frames 550 to 561, mean SSIM 0.9882 (worst frame 0.975), relative flow error 0.041, PASS. `work/blocks/giant-word-rise/co-1-es` is the same plan with `glyph: false`, set in ES Serif: mean SSIM 0.9636 (worst 0.937), flow 0.077, FAIL on SSIM alone, which is why the replica layer carries the traced outline. `work/blocks/giant-word-rise/demo`: "Pour" rising over a teapot in 1080 by 1920, printed to a card on the beat.

## What does not generalise

The face. ES Serif's W, r and i come from the film but at a different size and with different spacing, so a giant setting differs from the film's cut by a few pixels of edge, which the replica bar sees at this size; new work sets the word in ES Serif and accepts that. The black of the film reads as luma 1.1, so the replica layer inks with its sampled near-black rather than the token. The window that opens behind the subject belongs to card-wipe, not to this block.
