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
