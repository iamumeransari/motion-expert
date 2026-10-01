# Imagery

Some sources carry their hand in photography rather than in drawn shapes: an editorial campaign, a product film, a run of magazine spreads. A new piece in that hand needs photographs of its own subject that look as if the same photographer shot them on the same stock and the same grade, and it needs them as layers HyperFrames can move. So imagery is generated as stills, never as AI video, and HyperFrames does every move: the push-in, the parallax, the selection handles and cursors, and type set between the subject and its background through a cut-out matte. A still is cheap to iterate, measurable against the source frame by frame, and stays deterministic once it is a plate, while a generated clip brings its own motion, which is exactly the part of the hand the style already owns.

Everything below runs through `uv run --project ~/motion-expert/toolkit python`, and every image is measured by the same function at a long side of 1920 px, so a source frame, a candidate and a graded plate are read by identical code.

## Measure the source's photography

```
measure/imagery.py <video> --cuts <fingerprint.json | cuts.json | none> --out <style>/imagery.json \
  [--group editorial=12-21,23-25 --group city=31-34] [--regroup]
```

For every shot it picks the frame that is sharpest and stillest inside the middle of the shot, saves it under `frames/` beside the JSON, and measures the photograph: tone (black and white points, contrast, mean lightness, the Lab L percentiles), split toning as mean a* and b* in shadows, midtones and highlights, the white balance read off near-neutral pixels, per-channel curves and their offsets from luma, saturation as Lab chroma, grain amount and size from the high-pass residual in flat areas, depth of field from a tile grid of focus, the subject's position, headroom and shot scale from YuNet faces or the in-focus region, the lighting key and side, and vignette. The module docstring holds every threshold.

The profile is the median and the 10th to 90th percentile band of each feature over the shots it names. The capturing agent names them with `--group` after looking at the frames, because a classifier cannot tell an intro montage of other genres from the body of a film, and a film that cuts between a studio and a city is two looks that would average into neither. `look` is the union and `looks` holds each group, so every command below takes `--look <group>`. `--regroup` rebuilds the profiles from the measured shots without decoding again.

## Write the look down

`references/imagery.md` in the style holds what numbers cannot say, and the prompt builder reads it. The `## Look` paragraph is the photographer's description in a photographer's words, a `## Look <group>` paragraph overrides it for one group, each `### <name>` under `## Shots` is a framing recipe whose first line is `scale: <close|medium|wide|...>`, `## Avoid` lists what never appears in a plate (text, logos, watermarks), and `## Never` lists the source's product, brand and people. A prompt that contains any Never term is refused with exit 2, which is how content stays on its side of the line even when the subject a piece asks for drifts toward the source.

## Prompt and generate

```
imagery.py prompt   <style> --subject "a hand-thrown teapot on a wedging table" --shot close [--look editorial] [--room behind]
imagery.py generate <style> --subject ... --shot close --n 4 --size 1920x1080 --out <dir> [--queue-only] [--style-ref 13,20]
imagery.py generate --resume <dir>
```

The prompt is the subject, the shot recipe, then the numbers turned into words (scale, placement and headroom, lens and depth of field, key and light side, the grade as contrast, black and white handling and a tint per zone, the palette by name, the grain) with the look paragraph and the Avoid list. It never describes the source's people or product, because the words come from measurements and from a paragraph written to be about the photography. `--room behind` asks for clear background behind and above the subject, which is what the type-behind-subject move needs.

`generate` writes `jobs.json` (one job per candidate with its model, seed, size and exact arguments) and `prompt.txt`, then runs the jobs on fal: Ideogram v4.5 (`ideogram/v4.5`, prompt expansion off so the prompt is what runs) at the smallest supported size that covers the frame, cover-cropped and downscaled to the exact size, with Flux 2 Pro (`fal-ai/flux-2-pro`) as the fallback when Ideogram fails for a reason other than the account. Each candidate gets a sidecar JSON with its prompt, seed, model and request id. Ideogram v4.5 takes no reference image, so `--style-ref <shots>` routes to Ideogram v3 (`fal-ai/ideogram/v3`), whose `image_urls` are documented as style references and carry the aesthetic only; the source frames still show the source's people and product, so a style-referenced candidate is looked at for leakage before it is scored. When fal refuses the account (402, 403, or a body naming balance or credit) or the key (401), the command prints `fal: no credits` or `fal: key rejected`, leaves every unfinished job queued and exits 3, and `--resume <dir>` runs exactly those jobs later with the same seeds. `--queue-only` writes the jobs without calling fal. On fal in October 2026 an Ideogram v4.5 still costs $0.03 at low quality, $0.06 at medium (the default) and $0.22 at high whatever its size, Ideogram v3 with style references $0.03, Flux 2 Pro $0.03 per processed megapixel (about $0.06 at 1920 by 1080), and a BiRefNet matte well under a cent, so four medium candidates and one high re-run of the winner's seed come to about $0.46 per plate.

## Score and grade

```
imagery.py score <candidates-dir> --style-dir <style> [--look editorial] [--shot close]
imagery.py grade <image> --style-dir <style> [--look editorial] [--shot close] --out graded.png [--strength 1] [--encode-crf 18]
```

`score` measures each candidate and ranks it by weighted distance to the profile, where each feature contributes how far it sits outside its band in half-band units and nothing inside it, with composition compared against the medians for the shot's scale. It writes `score.json` and `sheet.jpg`, source frames over the best candidates, which is what to look at before trusting the ranking.

`grade` pulls one still into tolerance deterministically. A smooth monotone curve on Lab L moves the black and white ends to the source and the middle halfway, because mid-grey is mostly the subject's own brightness; it may lift blacks and roll off whites freely but stretch them only a few L units, and crowded percentiles are merged and the whole move shrunk until no segment's slope leaves 0.7 to 1.4, since a flat backdrop otherwise puts a cliff in the curve and skin crossing it posterises. Split toning and saturation then close the loop over four damped passes, each zone's tint capped at 9 Lab units because a bigger swing is a recolour and belongs in the prompt. Grain is calibrated through an x264 round trip at CRF 18, so the grain that survives the render's encode matches the grain the source measured after its own encode; a still noisier than the source is cleaned first with non-local means, capped at a strength that still leaves skin as skin. The report lists every feature still outside its band. Composition and depth of field are never corrected, because that is reframing, so a candidate that fails on those is a prompt or selection problem.

## Matte and plates

```
imagery.py matte <image> --out <dir> [--engine auto|local|fal]
imagery.py compose --bg bg.png --fg fg.png --text "Throw it" [--font f.ttf] [--size 0.27] [--x 0.5] [--y 0.52] --out still.jpg
```

`matte` cuts the subject out with HyperFrames' local remove-background first, which is free and good on people and on simple objects, and falls back to fal BiRefNet v2 (`fal-ai/birefnet/v2`, the heavy general model at 2048 px) when the local verdict is not good. The local model is a human segmentation network, so an object a person holds against themselves is cut away; the quality report catches that as an in-focus pocket inside the matte's outline that differs in colour from the surface around it, alongside coverage, pieces, holes, edge softness, raggedness and background kept along the inner edge. It writes `fg.png` (the still with alpha), `bg.png` (the untouched still), `bg-clean.png` (the subject inpainted, soft, for parallax) and `mask.png`. With `bg.png` under the type and `fg.png` on top the subject occludes the type exactly while both move together; parallax, where the fg grows faster than the bg, needs `bg-clean.png` and stays small enough that the soft fill never shows. `compose` is a Pillow proof of the stack for a still review.

`lib/plate.html` is the library element that does the same in a scene, and `lib/plate.md` explains its props, the push-in and parallax, and how a style specialises it.

```
imagery.py plates-from-source <style> --shots 13,20 --out <dir> [--matte]
```

The replica rebuilds the source's own structure, so it may use the source's own frames as plates to prove the moves and the layering match the source. These plates are written as `calibration-only-shot-NN.png` with a `CALIBRATION-ONLY.json` marker and never enter a novel piece.

## What it cannot do yet

The grain the source shows is what survived its encode, so the grade matches a measurement rather than the film stock, and haze or highlight diffusion has no measure of its own and lives in the look paragraph. The prompt builder turns numbers into words, and how faithfully a model follows "a faint rose tint in the shadows" varies, which is why the grade exists. Face-based composition needs a face; without one the subject is the in-focus region, which can mistake a sharp table for the subject.
