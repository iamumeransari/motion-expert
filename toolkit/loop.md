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
