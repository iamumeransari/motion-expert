# card-wipe

The next photograph arrives through a window. A narrow tall slot of it opens over the current picture around the subject and widens in single steps; then the current picture is printed into a card on pale paper and the next one jumps in front as a big card and grows in two more steps until it fills the frame. Inside the window the next picture is held zoomed (1.38 falling to 1) so its subject lines up with the subject it replaces, which is what makes the change read as one object passing between two worlds. Signature.

Source: s5 shots 25 to 26, film frames 556 to 565, across the cut on 562 (moves.md; the frame strips are listed in references/sources.md). Window 796, 103 to 1120, 974 on 556, widening on 558, 559 and 561 to 722, 124 to 1219, 934; next card 462, 23 to 1629, 931 on 562 and 26, minus 30 to 1915, 1110 on 564; full frame on 565. The current picture steps to a card at 0.939 of the frame on 561 and 0.796 on 562 with more picture inside (content 0.849 and 0.721 about the centre). Every step is one picture update on the film's sixteen-a-second cadence (556, 558, 559, 561, 562, 564, 565; 557, 560 and 563 are repeats).

## Modes

`preset: "replica-s5-shot26"` replays the measured window rectangles and the next picture's per-step scale and offset (aligned on the object the two pictures share), with frame 556 as time zero. In the film the current picture belongs to giant-word-rise, so the preset is used with no `from` slot and the block draws only the window and the next card.

The general mode takes the same steps as shares of the frame, centred on `focus` (where the subject is), with the next picture zoomed about the focus so it always covers the window. The steps keep their frame offsets times `speed`, snapped to frames that show a new picture, and `beats[0]` places the jump (the moment the next card comes in front). With a `from` slot the block also prints the current picture into its card on paper, so it works on its own between any two images. The plain print shrink before a cut (film frames 843 to 846) stays in `print-shrink.html`.

## Slots

| prop | default | meaning |
|---|---|---|
| `to` | striped placeholder | slot for the next picture `{ src or frames, fit, focal, box }` |
| `from` | none | slot for the current picture; omit when another block owns it |
| `focus` | [0.5, 0.5] | where the window opens, as shares of the frame |
| `speed` | 1 | duration scale |
| `cadence` | `"16"` | `"16"`, `"twos"` or `"none"` |
| `beats` | [6 frames] | `[jump]` in seconds from the start |
| `paper` | `--color-paper` | margin colour behind the printed card |
| `skip`, `exitAt` | none | start part way into the preset; when the current picture goes (default one frame after the fill) |

No text. Duration 0.3 to 0.9 s (0.375 s in the film from window to full frame). A frame-sequence `to` starts playing on the fill frame.

## Proof

`work/blocks/card-wipe/co-1`: film frames 556 to 565 rebuilt from giant-word-rise (plate and word, `skip` 0.25 s, its source content fed through the replica layer), this block's preset and, on 562 to 565, the next shot's line drawn by the harness's traced glyph element (it belongs to another block). Shot 556 to 561 mean SSIM 0.9827, flow 0.047; shot 562 to 565 mean SSIM 0.9842, flow 0.106; cut on its frame; PASS. `work/blocks/card-wipe/demo`: a desk scene giving way to a portrait in 1080 by 1080, window on the face.

## What does not generalise

The film's window keys align the two pictures on a shared object, which a general pair of images does not have, so the general mode zooms about one focus point instead; it reads the same but the subjects only line up when both images put the subject at the focus. The next picture in the film covers more than the frame (its card steps leave no gap even when offset), so a replica fill needs an edge-extended plate; general mode never offsets the picture off its edges, so ordinary images work.
