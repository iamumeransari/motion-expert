# Toolkit

Python runs through `uv run --project ~/motion-expert/toolkit python <script>`, and every path below is relative to `toolkit/`.

## Measurement

| Script | CLI | Writes |
| --- | --- | --- |
| `ingest.sh` | `ingest.sh <url-or-file> <slug>` | `work/<slug>/source.mp4` and `probe.json` (duration, fps, size, codecs, has_audio, sha256); exits 3 with a GATED message when a post needs a login it cannot reuse |
| `measure/cuts.py` | `cuts.py <video> [--out cuts.json]` | hard cuts, soft transitions with kind (flash, dip-to-black, dissolve, wipe, motion), shot lengths, cuts per 10 s, holds, hold share |
| `measure/motion.py` | `motion.py <video> [--out motion.json] [--no-timing]` | 10 Hz flow energy curve (normalised and raw), moves with region, property, travel, cubic-bezier, overshoot, start/peak/land keyframes, fit_error and confidence |
| `measure/look.py` | `look.py <video> [--out look.json]` | Lab k-means palette with shares, 16-bin luma histogram, safe margins, edge density, sharpness, grain, aspect |
| `measure/delivery.py` | `delivery.py <video-or-audio> [--out delivery.json] [--model ggml.bin]` | words with timings, wpm, pauses, emphasis, VO and music loudness; null with a reason when there is no speech |
| `measure/fingerprint.py` | `fingerprint.py <video> --out fingerprint.json [--bands overrides.json] [--no-delivery] [--no-sound] [--sound-device cpu]` | one deterministic JSON: version, source, timing, motion, look, delivery, sound, tolerance |
| `measure/bands.json` | edited, or overridden per style with `--bands` | default "same hand" band widths, each with its reason |
| `frames.py` | `frames.py contact <video> --out sheet.png [--n 24]`, `frames.py cuts <video> --fingerprint fp.json --out DIR`, `frames.py moves <video> --fingerprint fp.json --out DIR [--min-confidence medium]`, `frames.py at <video> <t>... --out DIR [--sheet s.png]` | contact sheet, a strip from 2 frames before to 4 after every cut and across every transition, a strip of every source frame around each move with its region outlined and keyframes labelled, and frames at given times (`from frames import frames_at` in Python) |

A capture starts with `ingest.sh`, then `fingerprint.py` on the source, then `frames.py cuts` and `frames.py moves` against that fingerprint, because the numbers find where things happen and the strips explain what happened. Every measure decodes through ffmpeg at a fixed analysis size, so results do not depend on resolution, and the fingerprint rounds to four places and sorts its keys so the same file always writes the same bytes. The tolerance block turns `bands.json` into absolute `lo` and `hi` bounds around the source's own values (each tagged `"kind": "absolute"`), merging `measure/sound-bands.json` when present and any per-style override passed with `--bands`, and `compare.py` scores a render against exactly those bounds. Confidence matters more than precision when reading the output. Hard cuts and soft transitions are reliable, wpm, pauses and loudness are good to a few percent, but a move's bezier is only worth copying when its confidence is high, organic motion (faces, hands, footage) never gets a curve, word-level emphasis can land one short word off, and move counts swing with segmentation, so the frame strips are the ground truth whenever a number and a picture disagree.

## Imagery

Imagery is generated as stills and moved by HyperFrames, and `IMAGERY.md` explains the method and each threshold behind these commands.

| Script | CLI | Writes |
| --- | --- | --- |
| `measure/imagery.py` | `imagery.py <video> --cuts <fingerprint.json \| cuts.json \| none> --out <style>/imagery.json [--frames DIR] [--group name=12-21,23-25] [--regroup]` | the sharpest still of every shot under `frames/`, each measured for tone, split toning, white balance, curves, chroma, grain, depth of field, composition, light and vignette, and a look profile (median and 10th to 90th percentile band) for the union and for each named group |
| `imagery.py prompt` | `imagery.py prompt <style> --subject "..." --shot close [--look g] [--room behind] [--json]` | the generation prompt built from the profile and `references/imagery.md`, refused with exit 2 when it contains a Never term |
| `imagery.py generate` | `imagery.py generate <style> --subject ... --shot ... --n 4 --size 1920x1080 --out DIR [--quality low\|medium\|high] [--seed N] [--style-ref 13,20] [--queue-only]`, then `imagery.py generate --resume DIR` | `jobs.json`, `prompt.txt` and one candidate PNG with a sidecar JSON per job, run on fal (Ideogram v4.5, Flux 2 Pro fallback); exits 3 leaving jobs queued when fal refuses the account or key |
| `imagery.py score` | `imagery.py score <candidates-dir> --style-dir <style> [--look g] [--shot close]` | `score.json` ranking candidates by distance to the profile and `sheet.jpg` of source frames over the best candidates |
| `imagery.py grade` | `imagery.py grade <image> --style-dir <style> [--look g] [--shot s] --out graded.png [--strength 1] [--encode-crf 18] [--no-grain]` | the still pulled into the profile's tolerance on tone, split toning, saturation and grain, with a report of what still sits outside its band |
| `imagery.py matte` | `imagery.py matte <image> --out DIR [--engine auto\|local\|fal]` | `fg.png` (subject with alpha), `bg.png`, `bg-clean.png` (subject inpainted for parallax), `mask.png` and `matte.json` with a quality verdict |
| `imagery.py compose` | `imagery.py compose --bg bg.png --fg fg.png --text "Throw it" [--font f.ttf] [--size 0.32] [--x 0.5] [--y 0.62] [--color #fff] [--front] --out still.jpg` | a Pillow proof of the bg, type, fg stack for a still review |
| `imagery.py plates-from-source` | `imagery.py plates-from-source <style> --shots 13,20 --out DIR [--video src.mp4] [--matte] [--engine local]` | `calibration-only-shot-NN.png` from the source's own frames (with matte folders under `--matte`) and a `CALIBRATION-ONLY.json` marker, usable only by a replica plan |
| `lib/plate.html` | copied into a style's `library/`, props `bg`, `fg`, `bgClean`, `text`, `order`, `push`, `parallax` and the rest in `lib/plate.md` | the three-layer plate element with type between the subject and its background, a push-in and optional parallax |

## Plan, board and render

Node scripts run as `node toolkit/<script>`, and `STORYBOARD.md` is the method they belong to. All three take `--style-dir` for a style outside `skills/`, and `--beats` for a beat grid that overrides `music.beats` in the plan.

| Script | CLI | Writes |
| --- | --- | --- |
| `validate-plan.mjs` | `validate-plan.mjs <plan.json> [--style-dir DIR] [--beats grid.json] [--sfx sfx-plan.json] [--json]` | the gate report, exiting 1 on any error: moves resolve, times land inside their scene, `word:` references need voice-over words and `beat:` or `downbeat:` references need a grid, media resolves, and a piece (any plan without `"mode": "replica"`) references no calibration-only file |
| `storyboard.mjs` | `storyboard.mjs <plan.json> --out BOARD [--name N] [--style-dir DIR] [--sfx sfx-plan.json] [--beats grid.json] [--register] [--force]` | one HTML frame per scene, `board.json`, `gsap.min.js` and every referenced image or video under `assets/plates/` with content-hashed names, rewriting only what changed |
| `build-composition.mjs` | `build-composition.mjs <plan.json> --out PROJECT [--style-dir DIR] [--sfx sfx-plan.json] [--beats grid.json]` | `index.html`, `build.json` and `assets/` holding the voice-over when there is one, the bed (ducked under the voice, or with no voice left as the timing spine), the effects and the plates, after re-checking the calibration guard over every file it copies |
| `render.sh` | `render.sh PROJECT out.mp4` with `QUALITY=draft\|looks\|high`, `STRICT=1`, `WORKERS=N` | the MP4 after lint and check pass, confirming its duration matches the root `data-duration` to within one frame |
