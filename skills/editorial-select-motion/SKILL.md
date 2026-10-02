---
name: editorial-select-motion
description: A subject-agnostic motion and visual design system for HyperFrames videos in the editorial-select hand: a single serif set large and claimed by a four-chip selection, pictures treated as objects that are selected, grown, printed and put up in the world, everything changing on single pictures of a 16 fps cadence, calm paper beats alternating with energetic photographic ones. Eighteen reusable blocks with image slots and text parameters, one shared runtime, measured tokens and grammar, a film-level arc template that scales to 15, 30 or 60 s, sound binding rules and formats from 16:9 to 9:16. Load for "editorial-select style", "in the editorial-select hand", "editorial-select motion", or any new piece, animation, story or re-skin Umer asks for in this hand.
---

# The editorial-select motion system

The hand is a magazine art director working with a selection tool. A single high-contrast serif is set large, centred on its ink, and claimed by four small square handles that glide to it, so every word on screen reads as chosen. Pictures are never just footage: they are tiles on grid paper, a selected crop that grows by revealing more of itself, the fill of a word, a print with a paper border, and finally a board in the street. Almost nothing eases. Words, tiles, colours and sizes change on a single picture, the picture itself updates sixteen times a second inside 24 fps, and continuous motion is kept for a few gestures (the handles' six-frame glide, a giant word rising, the camera), which is why each of those reads as deliberate. Calm paper beats alternate with energetic photographic beats in a slow burn with three swells and a still ending. When a situation is not covered here, cut rather than dissolve, step rather than ease, select rather than decorate, and let the picture be an object rather than a background.

Every value comes from the source film measured on 2026-10-01; `references/sources.md` holds the citation and the gaps, and it is the only file that names the source. Use the method in `~/motion-expert/skills/motion-expert/SKILL.md` for storyboarding, rendering and the loop.

## Principles

### 1. Change things on a picture, not over time

Most changes are zero-duration steps, and every sampled motion holds on the 16 fps cadence (frame f with f mod 3 equal to 2 repeats f minus 1). A six-frame handle glide therefore shows four pictures, a word lands crowded and snaps to its spacing, a tile pops in fully formed. This exists because the stepping is the single most recognisable trait in a still sequence; without it the same layouts read as generic smooth motion graphics in the right colours. The trade-off is that very small moves can look jerky, so continuous motion is reserved for the measured gestures in `grammar.json` and small corrections are made as steps, never as slow drifts on a graphic frame.

### 2. The selection claims what matters

Four square chips (24 px at 1080, set 34 px outside the ink and 59 px above the cap line and below the baseline at a 102 px cap height, scaled with the cap) mark the one thing a beat is about, glide between targets as segmented streaks, nest when a target steps up, and collapse inward to sign off. It exists because it turns typography into an act of choosing, which is the hand's whole attitude. Without it the type is just captions. The trade-off is that it becomes interface chrome if it is everywhere, so a beat carries one selection at a time, and its colour comes from the picture under it, the accent token, or the brand's token in a re-skin.

### 3. Type is as large as the picture

One serif, EditorialSelect Serif, set by its cap height (font-size is cap / 0.69) from 17 px for a small line to 928 px for a ghost word that runs off all four edges. Giant type rises from below, sits between a picture and its cut-out subject, fills with a photograph and echoes. This exists because scale contrast between a word and the frame carries the energy that the restrained motion does not. Without it the piece is quiet to the point of flat. The trade-off is legibility: a giant word is read by its first letters, so giant beats carry one or two short words, and longer copy waits for a held card.

### 4. Pictures climb a ladder

A picture starts small and selected (a tile, a crop), grows in steps while revealing more of itself, is printed into a card with a paper border, and ends large and public on a board. Plates are cut out so type can sit behind the subject, and the background behind a held subject is swapped on single pictures. This exists because it makes any subject feel like work being made and shown, which is the story the hand tells. Without it, photographs read as stock filler between type cards. The trade-off is that every picture needs room to be cropped and matted, so stills are chosen or generated with clear space around the subject (`--room behind` in `toolkit/imagery.py prompt`).

### 5. Holds are measured; length comes from items

Paper beats are calm and photographic beats carry the energy. A word card holds 8 to 15 frames, a statement 28 frames, the end card about three seconds. A longer or shorter piece repeats the arc and changes the number of items inside elastic beats (cards, tiles, plates, boards) rather than stretching any hold. This exists because the measured holds are what make the pacing feel confident. Without it a 60 s cut sags and a 15 s cut gabbles. The trade-off is that copy must fit its hold, which in practice means one to four words per beat.

### 6. The hand is in the blocks; the content is the customer's

Blocks own size, crop, focal point, timing, curves and cadence. They own no words, no pictures and no brand: those arrive as props, and fonts and colours come from tokens or props. This exists so the same blocks can carry a bike co-op, a product launch or a brand film without inheriting anything from the source. Without it, every new piece drifts towards a remake. The trade-off is that a block's exact replica of its source shot now needs the replica layer from outside the skill (`~/motion-expert/work/replica/presets/`), which is deliberate.

## The blocks

Each block is `library/<block>.html`, a HyperFrames element to `~/motion-ui/library/CONTRACT.md` (`render(props)`, `animate(tl, el, t0, props)`, `fromTo` only, `immediateRender: false` after the entrance, no callbacks, nothing before t0), with `library/<block>.md` beside it and an entry in `blocks.json` listing every slot, text parameter, colour and font prop, timing parameter, duration range and proof. Every block has a general mode (fitted curves, any word, any image aspect, any duration inside its range, any frame format) and a replica mode (`preset` plus `props.replica` from outside the skill) that reproduces its source shot frame for frame. With no props at all a block draws its slots as labelled placeholders, which is the code-and-slots view of what it is.

| Block | What it does | Image slots | Text | Duration | Signature |
|---|---|---|---|---|---|
| genre-word-card | A run of hard-cut cards, one word centred in four chips over a full-bleed picture; letters snap to their spacing and the handles glide to each new word; optional nested step-up | `cards[].image` | `cards[].word`, cap, wordX, wordY, tracking, color | 0.3 to 0.9 s per card | yes |
| select-handles | The four-chip selection around any box: glide with segmented streaks, jump with a lingering nest, pop, collapse | none | none (keys of boxes, chip size, colour) | 0.25 s per glide, holds as long as needed | yes |
| tile-scatter | Grid paper fills with picture tiles and lowercase words that land one per beat, then the words gather into one line as tiles drop out | `tiles[]`, `paper` | `words`, line scale | 1.5 to 4 s | yes |
| lockup-scramble | One line turns into the next by losing letters while the new letters arrive in the accent; it holds, then its tail cycles faces as the line steps up | `paper`, `tile` | `from`, `to`, `faces`, lead | 1.2 to 4 s | yes |
| icon-tile | An accent tile builds a mark in steps, doubles in one picture, collects handles one click at a time, and is carried off by an accelerating pan | `mark` (SVG or image) | none | 1.3 to 3.5 s | yes |
| giant-type-pass | A giant line rises and crosses under the pan while a picture blooms behind it and the letters turn white along a sweeping edge | `ground` | `text`, size, baseline | 0.8 to 2 s | yes |
| chromatic-title | A line slides in and settles word by word over colour fields cut on the cadence, then sits on paper with a gradient per word | `fields[]`, `card` | `words`, size, leading | 2.5 to 6 s | yes |
| camera-rig | The film's camera on any slot: push, punch, push-soft, push-hard, pull-back, pull-steady, pull-settle, drift, tilt, with picture swaps | `slot`, `swaps[]` | none | 0 to 2.5 s per move | no |
| marquee-select | The pointer slides in, a word lands over the picture, a translucent selection is dragged with streaking chips, the subject lifts in front of the word | `plate`, `cutout` | `word`, cap, wordX, wordY, color | 0.8 to 2.6 s | yes |
| cursor | The pointer: a rounded kite that hops 4 to 10 frames on the cadence, leans with travel and squashes on a click | none | none (stops, fill, stroke) | 0.17 to 4 s | yes |
| type-behind-subject | A word lands between a picture and its cut-out subject in one picture, with an optional lift and a parallax push | `plate`, `cutout` | `word`, cap, wordX, wordY, color | 0.4 to 3 s | yes |
| giant-word-rise | A giant word rises from below over a drifting picture, then the picture prints into a card in two steps while the word stays | `image` | `text`, cap, left, middle | 0.4 to 1.2 s | yes |
| card-wipe | The next picture opens as a window around the subject, widens in steps, the current picture prints into a card and the next jumps in front and fills | `to`, `from` | none | 0.3 to 0.9 s | yes |
| type-fill-echo | A dark line glides in, creeps, punches up, fills with a picture fixed to the frame, then picture-filled echoes land above and below | `paper`, `fill` | `text`, cap, baseline | 1.3 to 3.4 s | yes |
| ghost-word-grow | A giant ghost word behind tiles that pop in, a small word that doubles in one picture, chips landing round a tile that grows into the cut | `paper`, `tiles[]`, `select` | `word`, `ghost`, cap | 0.85 to 2.25 s | yes |
| crop-select | A selected tile grows its crop in steps with handles streaking to each corner and its word stepping up and tracking open, then cuts to the picture full bleed with an interjection and the pointer | `photo`, `art`, `paper` | `word.text`, `word2.text` | 2.4 to 4.5 s | yes |
| billboard | Artwork (a word, small lines, rules) mapped onto a plane in a photograph by homography, ink and glow matched to the plate, cut-outs over it, under a camera move | `slot`, `panel`, `fgs[]` | `word` or `art.logo`, `art.lines` | 0.45 to 6 s | no |
| endcard-typeon | A sentence types on inside handles that collapse onto a mark; the name slides out beside it and a small line drops in; still hold | `mark`, `wordmark`, `paper` | `sentence`, `tagline` | 2 to 6 s | yes |

Blocks that hand off without a cut: icon-tile into giant-type-pass (shared pan), giant-word-rise into card-wipe, ghost-word-grow into crop-select, chromatic-title's paper card into the next beat. `blocks.json` names each block's colour and font props (`color`, `ink`, `paper`, chip colours, `font` and so on); every one defaults to a token.

## The runtime

All blocks share one runtime, `library/_runtime/` (version in `inject.py`): `core` (the fitted curves, one bezier solver, EditorialSelect Serif's glyph metrics from `es-serif-metrics.json`), `shared` (frame scale `k`, quantised cadence times, steps, seeded random, glyph-metric layout, background slots), `kit` (cadence as an ease, unit-metric measure, image and sequence slots, per-frame keys), `select` (the selection engine), `camera` (the camera presets and homographies), `cursor` (the pointer) and `preset` (named motion preset merged with `props.replica`). Each block carries a byte-identical copy between `/* BEGIN es-runtime */` and `/* END es-runtime */` and reaches it as `window.__esRuntime.<module>`; the first copy in a document wins, so copies must never be edited by hand. Change a module, bump the version, run `python3 library/_runtime/inject.py`, then re-prove the blocks; `inject.py --check` fails if any copy has drifted. After a font change, run `metrics.py` first. A new block gets the runtime by putting the empty markers at the top of its first script and running `inject.py`.

## Slots, text and the customization layer

An image slot is `{ src, fit, focal: [x, y], zoom, cutout }` (or `frames` for a sequence); the block decides the box, crop and motion, so a portrait, a square or a panorama all work, and the focal point is the only framing decision the plan makes. Pictures come from three places and all go through the same grade: web images, generated stills (`toolkit/imagery.py prompt`, `generate`, `score`), or a client's own photography. `imagery.py grade <image> --style-dir <this skill> [--look city]` pulls any of them into the measured look (lifted blacks, a rose cast through the midtones, soft haze, fine grain; `references/imagery.md`), and `imagery.py matte` cuts the subject out for type-behind-subject, marquee-select and the background swaps. A slot left empty draws a labelled placeholder.

Words are set in EditorialSelect Serif (`assets/fonts`, `--font-serif`) from its own glyph metrics, so any word at any size is laid out before paint and fits the block's measure; the font cycle in lockup-scramble uses the style's mono, pixel, humanist, bitmap and grotesk faces. Colours are token names (`ink`, `paper`, `violet`, `type-light`) or CSS colours passed through props.

A re-skin, such as a brand film in another face and palette, is a style directory whose `tokens.css` redefines `--font-serif` and the `--color-*` variables (and whose `library` symlinks this one), built with `--style-dir`. Because every block takes its fonts and colours from tokens or props, the motion, cadence and selection come across unchanged while the look becomes the brand's. `~/motion-expert/work/replica/presets/style/` is a working example of such an overlay.

## The film arc

`templates/film-arc.json` holds the whole piece as sixteen beats in four movements (the catalogue, the claim, the demonstrations, the scale-up and sign-off), each with its share of the runtime, cut rhythm, the blocks that carry it, how it enters and leaves, its energy level and the feeling it lands, all without source content. Follow it in order, scale it with its `lengths` entries (60, 30 and two 15 s variants, each summing to its target) or its elastic rules for any other length, or borrow one movement alone (each movement says how). `examples/novel/plan.json` is a 30 s piece about a bike repair co-op built straight from the 30 s length, with every slot a labelled placeholder.

## The grammar for new moves and scenes

`references/grammar.md` and `grammar.json` hold the measured envelope for every animated property in the timing unit of 62.5 ms (x 2.7 to 32 units on snap, glide, reveal, drift or pass; y 2.7 to 19 on rise; scale as camera moves of 0.41 to 1.47 or one-picture steps of 1.15 to 2.0; opacity steps and fades of at most four frames; letter-spacing snaps; clip windows in steps; rotation, skew and 3D absent) and the composition rules (85 percent hard cuts, at most three movers, measured holds, alternating grounds, copy that fits its hold). A new move is legal when every primitive is inside its envelope; build it as a library element with the runtime spliced in and mark it `novel` in the plan with a grammar note naming its primitives, which `toolkit/validate-plan.mjs` checks. A new scene is a new combination of blocks inside a beat's role in the arc.

## Sound

The source is music only, so a piece defaults to music plus on-screen type, with the house voice added only when Umer asks (`references/delivery.md`). The bed is a driving electronic cue at about 140 BPM whose sections follow the arc: dense hits under the titles, ticks under the scatter, drive under the lockup and the statement, pads under footage and demonstrations, full density from the image-fill beat through the boards, and a dead stop on the end card. `sound/generated/bed-01.wav` is a fully generated bed in that shape for new pieces (never the source's music); a new bed comes from `toolkit/music.py generate` against the measured profile. The binding rules (`references/sound.md`) are: a tick on every tile or word pop and every handle landing, a sub-drop where type turns into image or a card shuffles, an impact under the biggest growth step and the start of a long pull-back, a pop about 5 ms before a cut, and the music carries the rest, never past the source's density of about 18 events per 10 s. The style's palette is built with `toolkit/sfx.py palette` from the measured `sound.json` in `~/motion-expert/work/sound-replica/` (not yet built into `sound/`), generated effects come from `sfx.py generate`, and `toolkit/sound-plan.py <plan.json> --style-dir <this skill> --out sfx-plan.json --music <bed> --beats <grid>` places them from the plan, snapping card cuts to the bed's beats.

## Formats

Every block scales pixel values by the frame's short side over 1080 (`shared.k`), so type keeps its size relative to the frame and layout re-derives as shares. 16:9 (1920 x 1080) is the source. 9:16 (1080 x 1920), 4:5 (1080 x 1350) and 1:1 (1080 x 1080) are carried by the block demos: a single word keeps its cap height as a share of the width and shrinks to leave 0.08 of the width clear for the chips, giant type fills about 0.9 of the width and runs off the top or bottom, scatter beats need about 1.6 times the tiles in 9:16 and 1.3 times in 1:1 to reach the same density, plates crop to the subject's focal point rather than letterboxing, and the end card stays centred. The timing unit, curves, cadence and arc never change with format. `references/formats.md` has the detail.

## Making a new piece

1. Read the brief and choose a length and shape: the full arc, a `lengths` entry, or one movement. Write down the feeling each kept beat must land.
2. Map each beat to its blocks from the arc and the catalogue; where nothing fits, compose a novel move inside the grammar.
3. Write the copy under `~/agent-core/voice.md`, cut to the holds: one word per card, a two or three word imperative per demonstration, four to six words for the statement, one sentence for the end card.
4. Fill the slots: pick or generate stills per beat with the subject named and room around it, grade every one with `imagery.py grade`, matte the ones that need a cut-out. Use placeholders while the structure is still under review.
5. Choose or generate the bed and its beat grid, and decide whether the house voice is on.
6. Write `scene-plan.json` (copy `examples/novel/plan.json`), with card cuts on beats, and run `node toolkit/validate-plan.mjs <plan>` until the gate opens.
7. Place sound with `sound-plan.py`, build the board with `node toolkit/storyboard.mjs <plan> --register` and load the `storyboard-canvas` skill; nothing renders until Umer approves the board.
8. Build with `node toolkit/build-composition.mjs <plan> --out <project> --sfx sfx-plan.json`, render with `QUALITY=high toolkit/render.sh <project> out.mp4`, then score with `toolkit/compare.py` in novel mode and the judge (`toolkit/judge.md`); fix and repeat, and after five passes without converging hand Umer the report with the blocking metric named.
9. Log every miss in `references/log.md` and fix it in the token, block, runtime module, grammar entry or arc rule that should have prevented it.

## Checks

On top of `compare.py` and the judge, check what a viewer would notice first. The cadence holds: every third frame repeats its predecessor in a graphic beat (compare frame hashes). Nothing fades in, and no fade lasts longer than four frames. Chips are square, at the measured size and offsets, and land with the word. Type sits centred on its ink with cap heights from the scale in `tokens.json`. Hard cuts carry about 85 percent of transitions and every hold sits inside its block's range. Paper and photographic beats alternate, and the three swells rise in order. Copy fits its hold. `python3 library/_runtime/inject.py --check` passes, the plan gate is open, and no source word appears anywhere in the piece or the skill (`references/sources.md` lists them).

## Reference index

| File | Read when |
|---|---|
| `blocks.json` | Planning any piece: every block's slots, text, colour and font props, timing, duration range and proof |
| `library/<block>.md` | Using a block: its parameters, modes, limits and proof |
| `library/_runtime/` | Changing shared behaviour, adding a block, or after a font change |
| `templates/film-arc.json` | Planning a piece's structure, length or a borrowed movement |
| `examples/novel/plan.json` | Starting a new plan |
| `grammar.json`, `references/grammar.md` | Composing a move, scene or format the blocks do not cover |
| `tokens.css`, `tokens.json` | Colours, faces, the type scale, spacing, the timing unit and curves; the base for a re-skin |
| `references/scenes.md` | The feeling and structure of each beat in prose |
| `references/moves.md` | The measured move inventory behind every block and envelope |
| `references/imagery.md`, `imagery.json` | Choosing, generating or grading stills |
| `references/sound.md`, `sound/` | The bed, the effect classes and the binding rules |
| `references/delivery.md` | Writing on-screen copy, or adding the house voice |
| `references/formats.md` | Any format other than 16:9 |
| `references/sources.md` | Where a value came from, what could not be recovered, and the source citation |
| `references/log.md` | Before starting, to avoid repeating a miss |
| `fingerprint.json` | The measured numbers the loop's tolerance bands come from |
