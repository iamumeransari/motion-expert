# Delivery

The source voice is never reused, cloned or matched; what transfers is how it speaks. Measure the delivery with `toolkit/measure/delivery.py` (words per minute, the pause distribution, pauses per minute, where emphasis lands relative to the sentence, and how loud the voice sits over any music bed), then listen to the source and write what the numbers miss: whether sentences fall or lift at the end, whether emphasis comes from volume or from a pause before the word, how much air there is between ideas, and the energy arc across the piece.

The style's `references/delivery.md` holds those measures and an example script about an unrelated subject, tagged for eleven_v4 so the house voice lands the same delivery. Eleven v4 takes only stability and similarity settings, has no speed control and ignores SSML, so delivery is steered with audio tags and punctuation as `toolkit/DELIVERY-V4.md` describes, and pace is corrected after generation with `tts.py --retime`, which inserts or trims silence at punctuation to hit the style's pause profile and updates the word timings.

Every voice-over is measured with the same script before the storyboard is built, since scene timings hang off its word timings and a miss found after rendering costs a full loop.
