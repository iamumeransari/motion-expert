# The loop

A piece is done when it measures inside the source's tolerance and the judge believes
the source's maker made it. The loop gets it there in at most five passes, and every
miss it finds is fixed twice: once in the piece, and once in whatever should have
stopped it, so the next piece starts ahead.

## Before the first pass

The storyboard is approved on the canvas, the script is voiced with `tts.py` against
the style's pause profile (`--retime` pointed at the style's `fingerprint.json`), and
`scene-plan.json` hangs every scene start and move off the word timings in
`words.json`. A replica comes before any novel piece, because a style that cannot
rebuild its own source has no business inventing new work. Each pass lives in
`examples/<piece>/pass-<n>/`, holding the render, its fingerprint, the compare folder
and the judgement, so the history of a piece can be read back pass by pass.

## One pass

Render with `toolkit/render.sh <project-dir> examples/<piece>/pass-<n>/render.mp4`,
which stops on any lint or check error before spending a render. Fingerprint the
render with `toolkit/measure/fingerprint.py` using the same settings the source was
measured with, since a setting changed between the two produces differences that are
artefacts of measurement. Then compare:

```
uv run --project toolkit python toolkit/compare.py \
  skills/<slug>-motion/fingerprint.json examples/<piece>/pass-<n>/fingerprint.json \
  --mode replica|novel \
  --source-video skills/<slug>-motion/assets/source/<file>.mp4 \
  --render-video examples/<piece>/pass-<n>/render.mp4 \
  --render-words examples/<piece>/vo/words.json \
  --out examples/<piece>/pass-<n>/compare
```

It exits 0 only when every metric passes, writes `report.md` with the blocking metrics
first and a concrete fix beside each, and writes the beat-matched sheets. Then judge the
sheets on `toolkit/judge.md` and save the judgement beside them. The pass is clean when
the exit code is 0 and every judge criterion is 8 or above, and the piece ships.

## The replica bar

A replica is a frame-exact rebuild of its source, so in `--mode replica` the
distribution metrics are not enough and `compare.py` also compares the two videos
frame by frame (it needs `--source-video` and `--render-video` at the same duration;
a render at another frame rate is resampled to the source's). The render fingerprint
is optional in this mode, and leaving it out runs the frame-exact checks alone in
about 22 seconds for a 47-second 1080p source. A replica ships only when all of these hold:

- every shot (bounded by the source fingerprint's cuts and dissolve midpoints) has a
  mean luma SSIM at 960 wide of at least **0.975** (`exact.ssim_shot_min`);
- every shot's optical-flow error relative to its motion, mean endpoint error in px at
  1920 divided by (flow px + 0.5), stays at or under **0.15**
  (`exact.flow_rel_epe_shot_max`), which catches a move that lands in the right place
  but travels on the wrong curve;
- no source hard cut is off by a frame in the render (`exact.cuts_off` is 0, band
  `--cut-band 0`);
- no source move's start, half-travel, peak or settle is more than 1 frame off
  (`exact.moves_off` is 0, `--move-band 1`);
- every source SFX onset is matched within 1 frame (42 ms at 24 fps) and 2 dB
  (`exact.sfx_off` is 0), and the bed's onset and the overall audio lag sit within a
  frame (`exact.bed_onset_ms`, `exact.audio_lag_ms`);
- frame count matches within a frame and the best global shift of the render is zero.

The report names the worst ten frame ranges, and `compare/flip/` holds a
source | render | difference triptych for every frame of each divergent range, which is
the first thing to open when a shot fails. `exact-curves.png` plots SSIM and flow error
per frame with the cuts marked.

The two flow bars were calibrated on `inbox/ideogram-4-5.mp4` (1136 frames, 42 shots),
rendered against copies of itself, and SSIM was set between the same two copies. A crf
23 x264 re-encode gives the codec ceiling: worst shot mean SSIM 0.986 (median shot
0.9945, worst single frame 0.965), worst shot relative EPE 0.069. A copy shifted one
frame late gives the cost of a single frame: median shot SSIM drops to 0.926 (worst
0.638, best 0.986 on the near-static opening), the per-shot SSIM cost of the shift is
0.009 to 0.36 with a median of 0.070, and the best shot's relative EPE rises to 0.183.
0.975 sits between the ceiling and 38 of the 42 shifted shots. The four that survive it
are near-static, which is why cut and move timing are separate gates. 0.15 sits between
0.069 and 0.183 on flow. A divergent frame, which starts a named range, is one under SSIM
0.95 or over relative EPE 0.25 (the re-encode's worst frames are 0.965 and 0.151).
Raw EPE in px is reported but not gated, because fast transitions carry several px of
error even on a clean re-encode (4.1 px at frame 911).

Expected results, all on that source. The re-encode passes every check. The one-frame
shift fails all 35 cuts by +1 frame, 38 shots on SSIM, flow on all 42 shots and the global
offset, while every move stays within a frame. A copy with frames 342-352 (14.25-14.71s)
retimed at 0.8x fails shot 16 on SSIM (0.958, worst frame 352 at 0.807) and on flow
(0.47, worst frames 342, 352 and 353), and names frames 342-353 as range r01. A copy
with the mix delayed 83 ms fails every SFX at 2.0 frames late, the bed onset and the
audio lag. A real rebuild will sit below the codec ceiling because its type and edges
are rasterised by a different renderer, so a shot that misses by under 0.005 SSIM with
clean flip sheets is a rendering difference to note in the log. It is never a reason to
lower the bar for the piece.

## Fixing a pass

Work the blocking list from the top, because it is sorted by how far outside its band
each metric sits, and fix at the cause rather than the symptom. Cuts landing late
against the voice mean the scene plan's word offsets are wrong, so recompute them from
`words.json` rather than nudging the render. A flat or misplaced energy curve means too
few elements move at once or a hold runs long in the section `energy_arc` names. A
curve miss means the element is using the wrong easing token or duration. A palette or
look miss is nearly always a token. A delivery miss is fixed in the tagged script or
with `tts.py --retime`, never by stretching video to fit. A sound miss is the clip, its
placement or its gain, in that order of likelihood. Make every fix the report and judge
call for in one pass, then render again, and if a fix moves a metric the wrong way,
revert that one fix rather than the pass.

After the fifth pass, stop. Hand Umer the latest `report.md`, the sheets and the
judgement, naming the blocking metric or criterion and what each pass changed, because
five passes without converging means the style, its bands or the brief are wrong, and
that is his call.

## Folding misses back

Every miss gets a dated entry in the style's `references/log.md`: the piece, the miss,
what caught it (the metric id, the judge criterion or Umer), and the file changed so it
cannot recur. Then change that file. Timing misses go to the style's
`references/scenes.md` (beat durations and holds) or the composition rules in
`references/grammar.md`, or to the scene-plan builder when the word offsets were
computed wrongly. Curve misses go to the easing token in `tokens.json` and
`tokens.css`, the library element in `library/`, or the primitive's envelope in the
grammar. Energy shape and arc misses go to the energy level per beat in `scenes.md` and
the grammar's rule on how many elements move at once. Look misses go to `tokens.json`
for colour, type and spacing, and to the density rule in the grammar. Delivery misses
go to the style's `references/delivery.md` (its pause profile and tagged example
script), to `toolkit/DELIVERY-V4.md` when an audio tag or punctuation behaves the same
way for every style, and to `tts.py` when the retime itself is wrong.

Sound misses route by what failed. A timbre miss (centroid, attack, decay or duration)
goes to the palette: replace or regenerate the clip in the style's `sound/`, keeping its
prompt beside it, and update `toolkit/SFX.md` when the prompting lesson holds for every
style. A sync, density or class-mix miss goes to the binding rules in the style's
`references/sound.md` (which moves sound, on which keyframe, with what lead or trail)
and from there to `toolkit/sound-plan.py` when placement ignored a rule. A level or duck
miss goes to the sound bands, either the style's fingerprint tolerance for that class or
`toolkit/measure/sound-bands.json` when the default was wrong for everyone.

A band is never widened to make a piece pass. It is tightened when a piece passes the
loop and still looks wrong to Umer, and widened only with the reason written in its
`why`. When the judge catches something every metric passed, the metric is missing
or its band is too loose, so add or tighten it in the fingerprint tolerance or in
`compare.py`, which makes the next miss of that kind a number rather than an opinion.
A miss that would hit every style is fixed in the toolkit or the method skill, and a
decision Umer makes about one piece, such as cutting a scene, stays in that piece and
never becomes a rule.
