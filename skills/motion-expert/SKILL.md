---
name: motion-expert
description: Turn a video found on X, LinkedIn or anywhere else into a reusable motion-style skill, then make new HyperFrames videos about unrelated subjects in that same hand, voiced by the house voice on ElevenLabs eleven_v4. Load when Umer shares a video link or file and wants its motion, look or feel captured, says "make a style from this", "capture this video's style", "do this in the style of", "same motion as", names an existing style skill (any <slug>-motion skill listed in ~/motion-expert/registry.json), or asks for a new video in a captured style. Covers ingest, measurement, signature moves, the grammar that generates new moves, the storyboard canvas gate, the render and compare loop, and where every miss gets folded back.
---

# Motion expert

This is the method behind every `<slug>-motion` skill in `~/motion-expert/skills/`. It has two jobs: capturing a style from a source video, and making a new piece in a captured style. Both fail in two opposite directions. A remake copies the source's script, product and shots and is plagiarism with a new title, and a reinterpretation keeps the palette and loses the hand, so the result looks like generic motion graphics in the right colours. Most of this file is about holding the line between them: the moves and look come across exactly, the content never does.

Read `~/motion-expert/registry.json` first to see which styles exist, and `~/motion-expert/toolkit/README.md` for every script's CLI. Python runs through `uv run --project ~/motion-expert/toolkit`, renders go through HyperFrames (`npx hyperframes@0.8.101`), and the HyperFrames skills (`hyperframes-core`, `hyperframes-animation`, `hyperframes-cli`) are the authority on composition rules.

## The source is the video, measured

Work from the full video file at its best available quality, never from a description, a thumbnail or memory. `toolkit/ingest.sh` pulls it (X directly, LinkedIn through browser cookies) and anything it cannot reach is reported as gated, at which point Umer drops the file into `~/motion-expert/inbox/` and nothing is approximated meanwhile. The full source is committed into the style skill under `assets/source/`, because every later comparison needs the original and a re-download may not exist.

Measure before reading, then read before writing. `toolkit/measure/fingerprint.py` produces the numbers (cuts, shot lengths, holds, the optical-flow energy curve, every detected move with a fitted cubic-bezier, palette, margins, density, and the voice's pace, pauses and emphasis), and `toolkit/frames.py` produces the contact sheet, the cut strips and dense strips at twice the source frame rate around every move. The numbers find where things happen and the frames explain what happened, so a move is only written into the skill after its strip has been looked at as images. A fit the measurement flags as low confidence is checked by eye on the strip and either confirmed with a timecode or listed as a gap.

Everything that cannot be recovered goes into the style's `references/sources.md` under Gaps, named specifically: a font identified only by measured x-height, cap height and set width; a curve smeared by compression below a few frames; a 3D or footage-only effect; music that cannot be identified. A gap is never filled quietly, because the next agent will treat a guess as a measurement.

## Two layers: signature moves and the grammar under them

Signature moves are the things a viewer would recognise in a still frame or a half-second clip, such as a specific word slam, a mask wipe, a card rise with a particular overshoot, or a camera push on the beat. They are copied exactly, curve, duration, overshoot, stagger, direction and frame-level detail included, and each lives in the style's `library/` as a seek-safe HyperFrames element following `~/motion-ui/library/CONTRACT.md` (`render(props)` plus `animate(tl, el, t0, props)`, `fromTo` only, `immediateRender: false` after the entrance, no callbacks). A signature move is checked against its source strip frame by frame, which is why the replica exists.

The grammar sits one level down and is what makes the style generative. Every move decomposes into primitives: the property it drives, its curve family, its duration in the style's timing unit, its offset from the voice-over word it answers, its stagger, and its travel as a share of the frame. `references/grammar.md` records the measured range for each primitive across all the source's moves, and the composition rules that sit above them: how scenes enter and exit, what a cut lands on, how dense a frame is allowed to get, where energy peaks across the piece and which feeling each structural beat carries. A new move, scene or format is legal when every primitive stays inside its envelope and every rule holds, so the system can invent a chart reveal or a vertical format the source never showed while still measuring as the same hand. When a novel move is used it is marked `novel` in the scene plan with a one-line grammar note naming the primitives it was built from.

Moves are code plus written rules and never a fixed vocabulary of named verbs, because a verb list caps quality at its own size; the Prism reels system dropped one for exactly that reason.

The look follows the same split. Tokens carry the measured palette, type scale, spacing, timing unit and named easings, and `SKILL.md` carries the identity in one paragraph plus four to six principles, each with the reason it exists, what breaks without it, and its trade-off, so an agent facing a format nobody anticipated can reason its way to the answer.

## Content never crosses over

Nothing from the source's script, product, claims, people or shots enters a style skill or a piece. Footage slots in the source are rebuilt as designed HTML and CSS scenes in the captured identity, which keeps every render self-contained. The voice is captured as delivery only: pace in words per minute, the pause profile, where emphasis lands, energy across the piece, and an example script written about an unrelated subject with eleven_v4 audio tags showing how to steer the house voice into that delivery (`references/delivery.md`, and `toolkit/DELIVERY-V4.md` for the tags). The source voice itself is never cloned or matched.

## Capturing a style

Run the steps in order and commit after each style passes. Ingest and fingerprint the source, read the strips and write the move inventory with timecodes into `references/moves.md`, then copy `_template/` to `skills/<slug>-motion/` and fill it: tokens, signature elements, `grammar.md`, `scenes.md` (the structure of the source as beats, each with the feeling it lands and how long it holds), `delivery.md`, `sources.md` with gaps, and `SKILL.md`. The slug names the visual hand in a word or two, never the source's product.

Then prove it in two stages. The replica rebuilds the source's structure with neutral placeholder copy of matching length and runs the loop in replica mode, where every fingerprint metric and every signature curve must land inside tolerance of the source's own; this proves the skill reproduces the hand before it is trusted on anything new, and it is never shipped. After the replica passes, make two novel pieces on unrelated subjects, one of them in a format or length the source never used, and run them through the loop in novel mode. Add the style to `registry.json` with its source URL, capture date and status, symlink it into `~/.claude/skills`, then commit and push.

## Making a piece

Write the script under `~/agent-core/voice.md`, voice it with `toolkit/tts.py` (house voice, eleven_v4, word timings returned, `--retime` to hit the style's pause profile since v4 has no speed control), and write `scene-plan.json` against the style's grammar and scenes. `toolkit/validate-plan.mjs` rejects any move that is neither in the library nor marked novel with a grammar note.

The storyboard is the gate. `toolkit/storyboard.mjs --register` writes one scrubbable HTML per scene with `data-scene` and `data-move` tags and a paused GSAP timeline on `window.__timelines.main`, registers the board on Umer's canvas, and prints the URL and the monitor command; load the `storyboard-canvas` skill and follow it, fixing frames in place as his comments arrive and closing each with `canvas resolve`. Nothing renders until he approves the board, and `toolkit/build-composition.mjs` builds the HyperFrames project from the same scene code so what he approved is what renders.

## The loop decides when it is done

Render, measure the render, compare, judge, fix, repeat. `toolkit/compare.py` scores the render's fingerprint against the source's tolerance bands (timing and sequencing, curves, the energy curve's shape after time-normalisation, look and delivery) and writes beat-matched source and render sheets; the vision judge then scores those sheets on `toolkit/judge.md`, including whether each beat produces the feeling `scenes.md` names for it. A piece ships when every metric is inside tolerance and every judge criterion is 8 or above. After five passes without converging, stop and hand Umer the report and sheets with the blocking metric named rather than polishing blind. `toolkit/loop.md` holds the full procedure.

Fold every miss back. A fix that only touches the piece will recur on the next one, so each miss is logged in the style's `references/log.md` and corrected in the token, element, grammar rule or tolerance band that should have prevented it; a miss that would hit every style is fixed in the toolkit or in this file. A decision Umer makes for one piece, such as cutting a scene, stays in that piece and never becomes a rule.

## Reference index

| File | Read when |
|---|---|
| `references/extraction.md` | Ingesting and measuring a new source, or a measurement looks wrong |
| `references/grammar.md` | Writing a style's grammar, or composing a move the library does not have |
| `references/storyboard.md` | Building the board and handling canvas comments |
| `references/validation.md` | Running the loop, setting tolerance bands, or the loop will not converge |
| `references/delivery.md` | Capturing a voice's delivery or voicing a piece |
| `_template/` | Starting a new style skill |
