# Generating sound effects on ElevenLabs

`sfx.py generate` calls `POST /v1/sound-generation` with `model_id: eleven_text_to_sound_v2`, `duration_seconds` between 0.5 and 30, and `prompt_influence` between 0 and 1, asking for `mp3_44100_128`. The house key is allowed to use it (confirmed 2026-10-01: a 0.5 s request returned 200 with a stereo 44.1 kHz MP3). Each candidate is trimmed to its onset and to the class's envelope, measured the way `measure/sound.py` measures events, and scored against the palette target, so a prompt is judged by the number that comes back rather than by how it reads.

## What held up

Concrete physical nouns beat mood words. "One single crisp UI click, very short, bright, dry, clean isolated sound effect, no music, no reverb" came back as a click with the right envelope, while asking for a "whoosh" with nothing else returned a dark, rounded swell near 1 kHz that scored 0.27 against a 2.5 kHz target. Rewriting it as "a fast swish of air passing close by", then naming the spectrum, the length in milliseconds and "smooth rise and fall", with "no low rumble", raised the score to 0.75 and landed the class, duration and envelope.

Brightness words map onto the spectrum coarsely and overshoot. "Bright high-frequency hiss" landed at 5.9 kHz when 2.5 kHz was wanted, so `words_for` grades them: "deep, low" under 600 Hz, "warm, soft" to 1.5 kHz, "airy, mid-range, not harsh" to 3.5 kHz, "bright airy hiss" to 5 kHz and "very bright, thin high-frequency hiss" above. When a class keeps missing its centroid, change the tone words before changing anything else.

The API's floor of 0.5 s means every short sound comes back padded with silence and sometimes a second hit, so the request is the target duration times 1.3 (plus 0.15 s for sounds with tails) and the trim does the rest. Keep "isolated" and "no music" in every prompt; without them the model tends to add a bed or a room.

Prompt influence is worth spreading rather than fixing. For the click, 0.55 scored 0.73 and 0.35 scored 0.27; for the rewritten whoosh, 0.35 scored 0.75 and 0.55 scored 0.64. So the default asks for four candidates at 0.35, 0.55, 0.75 and 0.9 and keeps the best, which costs four short calls per class and is cheap next to a render.

## Scoring

The match is a weighted mean of log-ratio closeness on duration, centroid, bandwidth, attack and decay, plus whether the analyser files the candidate in the intended class. When the palette holds a clean source clip of that class, the MFCC mean and spread distance to it joins with the largest weight, because sounding like the source's own sample matters more than matching summary numbers. A candidate under about 0.5 usually has the wrong envelope (a riser that ends in a hit, or a pop with a reverb tail), and rewording the shape ("stops at its peak", "dry") fixes it more often than raising influence.

## Music

`music.py generate` uses `POST /v1/music` with `model_id: music_v2_5` and a composition plan whose chunks follow the source's sections, scaled to the new length, each at least 3 s. A 5 s instrumental request and a 12 s plan both returned 200 on the house key, and the 12 s bed measured exactly the source's 136 BPM. `force_instrumental` only works with a plain prompt, so the plan keeps vocals out with negative styles instead. The scorer showed one failure worth knowing: with too few chunks for the length, sections merge and the arc flattens, which is why merging keeps the louder section's role.
