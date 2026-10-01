# Validation

The loop exists because a piece can be right in every frame and wrong in feel, and feel lives in timing, curves and sequence, which only show up when measured against the source. `toolkit/loop.md` holds the procedure and `toolkit/judge.md` the rubric; this file covers how to set it up and what to do when it stalls.

Two modes apply. Replica mode compares a rebuild of the source's structure against the source at matching times, including each signature move's curve against its source fit, and its bands are tight because the content length matches. Novel mode compares a piece about something else against the source's distributions (shot-length spread, cuts per ten seconds, energy shape after time-normalisation, palette, pace and pause profile), since subject and length differ and frame-for-frame matching would be meaningless.

Tolerance bands start from `toolkit/measure/bands.json` and are tuned per style in its `fingerprint.json`. Tighten a band when pieces pass the loop and still look wrong to Umer, and widen one only with a reason written beside it, because a band widened to make a piece pass hides the miss it was meant to catch.

When the loop stalls, read which metric blocks and in which direction, then fix the cause upstream. Late hits mean the scene plan's word offsets are wrong, not the curve. A flat energy curve usually means too few elements moving at once or holds that run too long. A palette miss is usually a token, not the piece. A delivery miss is fixed in the tagged script or with `tts.py --retime`, never by stretching the video. After five passes without converging the loop stops and Umer gets the report and the beat-matched sheets with the blocking metric named.
