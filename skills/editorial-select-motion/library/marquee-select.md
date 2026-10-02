# marquee-select

The film's "Mask it" beat as a block. The pointer slides in from above the frame, a white serif word lands over the picture in one frame, a large corner bracket marks the anchor for two frames, then the pointer drags a translucent white selection whose three moving corner chips streak along their path. On the landing frame the subject lifts in front of the word, so the word ends up between the picture and the cut-out, and the selection fades behind the subject over three frames. Signature: yes.

Source: s4 shot 17, film frames 420 to 452 (17.500 to 18.875 s). Measured at 1920 x 1080: word cap height 205 px, selection fill 21 percent white, chips 24 px at 0.8 while moving and 1.0 settled, each streaked back 0.42 of its last picture step, afterglow 0.18, 0.18, 0.12 behind the subject, drag on the glide curve over 8 frames from the frame after the bracket (fit error 0.004 against the measured corner), pointer entry linear over 10 frames (fit error 0.015), all on the film's sixteen-a-second picture.

## Slots

| slot | what | notes |
|---|---|---|
| `plate` | the picture | `{ src or frames, fit, focal: [x, y], box }`; frames play one per frame |
| `cutout` | the subject alone on transparency, aligned to the plate | same fit, focal and box as the plate; omit it and the word simply stays in front |

## Text and layout

`word` (any length, measured from ES Serif's own metrics at render), `cap` (cap height, px or a share of the frame height, default 0.19), `wordX`, `wordY` (ink centre, share or px, default the frame centre), `color` (token name such as `--color-type-light`, the default, or a colour), `select: [x0, y0, x1, y1]` (anchor, then the corner the pointer drags to; shares or px). Pointer and chips scale with the shorter frame side.

## Timing

General mode keeps the source's beat lengths in frames and scales them by `scale` (0.6 to 2): pointer arrives on the anchor at 13 frames, word 6 frames before that, bracket for 2 frames, drag over the next 8, landing 9 frames after the anchor, afterglow 3 frames, then the pointer drifts off the subject for 6. `beats: [anchor, landing, word]` (seconds from t0) override those and are snapped onto frames that show a new picture. `cadence` is `"16"` (the film's), `"twos"` or `"none"`. Duration 0.8 to 2.6 s, default 1.3 s. Returns the landing time.

## Presets

`replica-s4-shot17` holds the measured per-frame keys of the whole shot (word placement fitted to the traced line at IoU 0.975, the ten selection states, the bracket, every pointer pose). Fill `plate` with the shot's clean photo sequence and `cutout` with its per-frame mattes. Rebuilt from the block alone it scores mean SSIM 0.9942 (min 0.990), relative flow error 0.108: pass (work/blocks/marquee-select/replica/cmp-1).

## Notes

The bracket is a fixed shape traced from frame 433 (IoU 0.91 where the pointer does not cover it). The word carries `data-layout-allow-occlusion` because the subject is meant to cover it; in the preset it is also marked set dressing, since the film's white type on a pale wall fails the contrast audit by design. In a new piece pick a plate the word reads against.
