# Grammar

The grammar is how this hand animates something the source never showed. It sits under the blocks: every block is built from these primitives, and a new move, scene or format is legal when each primitive it drives stays inside its measured envelope and every composition rule holds. `grammar.json` holds the same envelopes as data in the `toolkit/schema/move.schema.json` shape, which `toolkit/validate-plan.mjs` checks every grammar-composed tween against, so the two files change together.

The timing unit is 62.5 ms, a frame and a half at 24 fps, and a duration of zero units is a step: a property changes on one picture with no tween. Steps are the hand's main verb. Most things in this style appear, change colour, grow or vanish in a single picture, and continuous motion is kept for a few specific gestures, so the eye reads every continuous move as deliberate.

## The cadence under everything

Pictures update sixteen times a second inside a 24 fps file: frame f with f mod 3 equal to 2 repeats frame f minus 1, so a six-frame glide shows four pictures and reads as stepped. Blocks sample their motion on this cadence through the runtime (`kit.stepped`, `shared.pictures`, the camera's cadence option) rather than rendering smooth and dropping frames afterwards. Real footage and the camera on real footage run on ones. A tween or a step may never be placed before time zero of its block, because a GSAP timeline that receives a child before zero pushes everything already on it later.

## Primitives

Horizontal travel (`x`) is either short and exact or giant. Handles glide 6 frames on the snap curve (0.33, 1, 0.68, 1), the pointer hops 4 to 10 frames on snap, a lockup slides to centre over 17 frames on the reveal curve (a slight backward drift, then a fast settle), a held line slides in over 2 s and settles word by word, the camera drifts 0.035 of the width over 20 frames, and the giant pass pans about 1.09 of the width. That gives 2.7 to 32 units, travel from 0.004 to 1.09 of the width, at most 3 percent overshoot, and word staggers of 0.7 to 2.7 units moving forward through the line.

Vertical travel (`y`) is the rise. Giant words come up from below the frame on the rise curve (0.15, 0.85, 0.3, 1), 8 frames for a single word and up to 29 frames for the pass, travelling up to 0.68 of the height and cropped by the frame edge. The camera tilts 0.06 of the height over 13 frames. Words never fall in from above, and a staggered baseline is either held or settles in one picture, never bounces.

Scale comes in two kinds and nothing in between. A camera move on a picture interpolates in log space: push 1.10 over 12 frames, push-soft 1.34 and push-hard 1.47 over 13, pull-settle 0.82 over 13, and the long pull-back 0.407 over 35 frames, on the push, push-hard, pull and settle curves. Type and tiles scale only by steps, 1.15 to 2.0 in one picture, apart from the 3 percent creep of a held line on the glide curve.

Opacity is a step. Plates crossfade for two or three frames, a type layer ghosts to 0.15 behind a lifted subject over four frames, and an edited colour cross-dissolves over two, and that is the whole list; fades longer than four frames and fading entrances are outside the hand.

Letter-spacing snaps with the handles: a word lands at 0.70 to 1.27 of its set width and reaches it over six frames on snap, and tracking opens to 0.19 to 0.3 em in one step as a selection grows. Clip windows open in single steps, except the white edge sweeping across the giant pass over 14 frames and the radial bloom behind it. Width and height grow a selected picture by revealing more of it, a creep and then a two-picture jump over 15 to 17 frames, never by stretching. Colour changes are steps between token colours (accent to ink, faint to white to ink). Filters flash brightness for one to four frames; blur is a fixed property of a plate.

Rotation, skew and 3D turns are absent. The pointer's lean lives inside the cursor block, the camera's measured roll belongs to real footage, and a plane in a photograph is mapped by a homography (billboard) rather than turned.

## Composition

Hard cuts carry 85 percent of transitions, shots run 4 to 144 frames with a median of 15, and a word card lasts 8 to 15 frames. Soft transitions belong only to the giant pass, a statement's plate run and night pictures. Entrances are a cut or a one-picture appearance, and exits are a cut, a one-picture vanish, or a hand-off that carries into the next block (a shared pan, a print into a card, a selection growing into full bleed). At most three things move at once, and about half of every graphic card is a held frame. A held statement holds 28 frames and the end card about three seconds, and no hold is stretched past its block's duration range, because a stretched hold reads as a stall.

Paper beats are the calm ones and photographic beats carry the energy, so a piece alternates the two grounds and builds as a slow burn with three swells, each higher than the last, separated by near-still graphic beats and ending still. `templates/film-arc.json` holds that shape beat by beat. Type sits centred on its ink, the selection frames whatever matters, and giant type runs off the frame and is read by its first letters. Copy is what can be read in a hold: one word on a half-second card, two or three on an imperative, four to six on a held statement, one sentence on the end card.

## Composing a new move or scene

Choose primitives inside their envelopes, check the composition rules, and build the move as a library element to `~/motion-ui/library/CONTRACT.md` with the runtime spliced in (`library/_runtime/inject.py`). In the plan, mark it `novel` with a one-line grammar note naming its primitives, for example "x snap 4u travel 0.12 W, letterSpacing snap 4u, color step", so the loop checks it against envelopes rather than against a source shot. A chart reveal in this hand, for instance, is bars that appear on single pictures with a selection gliding to the value that matters and the figure stepping up once, not bars growing on a smooth ease. A novel move that passes three pieces is promoted into the library and `blocks.json`.
