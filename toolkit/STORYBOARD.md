# Storyboard and render

A piece moves from plan to board to approval to render through one shared generator, so the frames Umer approves on the canvas run the same element code, the same timings and the same sounds as the video HyperFrames writes. Nothing renders until he says the board is approved.

## The plan

`scene-plan.json` follows `schema/scene-plan.schema.json`: the style slug, a title, the format, the duration, the voice-over with its word timings from `tts.py`, and the scenes that tile the piece. Each scene names the feeling it must land, its voice-over line, a layout (center, stack, split, free or full, or a `.me-stage.layout-<name>` rule in the style's `tokens.css`) and its moves. A move names a library element, a target node and a start time given in seconds or as `word:<index>` with an optional offset (`word:12-0.08` leads the word by 80ms). The first move on a target renders it and later moves on that target animate the same node. A move the source never showed is marked `novel` with a `grammar_note`, and it runs either as an element written beside the plan in `library/<name>.html` or as `props.tweens` built from the style's primitives, which the validator checks against the envelopes in the style's `grammar.json` (each entry follows `schema/move.schema.json`). A move may carry `sfx: false` to silence its sound or an `sfx` object to override it.

```
node toolkit/validate-plan.mjs <plan.json> [--style-dir <dir>]
```

The validator fails a move that is neither in the library nor marked novel with a note, a time outside its scene, a word index that does not exist, overlapping scenes, a composed tween outside its envelope or on a property the source never animates, and a missing audio or clip file. `--style-dir` points at a style outside `skills/<slug>-motion`, which is how the throwaway test style under `work/test-style` runs.

## The board

```
node toolkit/storyboard.mjs <plan.json> --out work/<piece>/board --name <piece> \
  [--sfx work/<piece>/sfx-plan.json] [--style-dir <dir>] --register
```

This writes `01-<id>.html` per scene, `board.json` and a local `gsap.min.js`. Each frame inlines the style's fonts, tokens and the library elements its moves use, builds a paused GSAP timeline through each element's `animate()` and registers it as `window.__timelines = { main: tl }`, which the canvas plays and scrubs. Every element carrying a move has `data-move` and `data-target`, novel ones add `data-novel`, and the scene root has `data-scene`, so a pinned comment names the move it means. A review overlay docked at the foot of each frame shows the feeling, the voice-over line, a ruler with the words, one bar per move spanning the tweens it actually placed (blue for signature, hatched amber for novel), the sound markers with class and clip, and a playhead that follows the scrubber. The pill or the O key hides it, `?clean` drops it for stills, and it never reaches a render. `board.json` notes repeat the feeling, the line, the moves and the sounds for each frame.

`--register` runs `canvas add` and prints the URL and the monitor to arm, `~/storyboard-canvas/bin/canvas watch <piece>` with a timeout of 1800000, re-armed whenever it expires while review continues. Load the `storyboard-canvas` skill before reviewing.

## Handling comments

A comment arrives naming the frame, the element's `data-move` and target, and the paused time. Read the timeline at that time, then fix the source: the plan for timing, props or sound, the style's library element or tokens for the move itself. Re-run `storyboard.mjs` with the same arguments, which rewrites only the frames whose content changed and keeps the canvas's `.canvas/` comment state, so those frames hot-reload in place and nothing asks him to refresh. Patching a frame file by hand would let the board drift from what the composition renders, so the frame is always regenerated. Close each comment with `canvas resolve <piece>#<n> "the slam on fewer now lands 60ms earlier with a harder overshoot"`, written in his terms. When a comment could mean two things, ask with `canvas reply <piece>#<n> "question"` rather than guessing.

## The composition and the render

Once he approves the board:

```
node toolkit/build-composition.mjs <plan.json> --out work/<piece>/project [--sfx <sfx-plan.json>] [--style-dir <dir>]
toolkit/render.sh work/<piece>/project work/<piece>/out.mp4
```

The build refuses a plan that fails the gate, a novel move not yet built, a missing voice-over and any sound file not on disk. It writes `index.html` with every scene as a clip on one paused timeline at `window.__timelines["main"]`, the voice-over as `<audio id="vo">`, the music bed with its level as a gain stage whose automation ducks it by `duck_db_under_vo` across each spoken phrase and fades the tail, and each sound effect as its own clip at its planned time and gain. A panned effect is rendered to a derived stereo file first, since HyperFrames has no pan control. `build.json` records what was built from what.

`render.sh` runs `npx hyperframes@0.8.101` lint, then check, then render at high quality, stopping on any error before spending render time. `STRICT=1` makes check fail on warnings too and `QUALITY=draft` speeds iteration. It then confirms the video's duration matches the root `data-duration` to within one frame and reports the audio streams.
