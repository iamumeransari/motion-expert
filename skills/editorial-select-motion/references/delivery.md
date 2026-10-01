# Delivery

The source has no voice. `toolkit/measure/delivery.py` recognised two words in the whole film, both music bleed, and the separated voice stem sits at -40.4 LUFS against a -10.8 LUFS bed, so there is no pace, pause profile or emphasis to measure. Every word the viewer reads is on screen, and the timing spine is the music: cuts and word changes land on its phrases and strongest hits, about a third of them within 70 ms of a beat on the 136 BPM grid in `work/ideogram/music-beats.json`, and the sections of the track (dense hits, ticks, drive, pads, drive, silence) shape the piece.

So a piece in this style defaults to music plus on-screen type. The on-screen words carry the script, written under `~/agent-core/voice.md` and cut to the style's rhythm: one word or a two or three word imperative per card, a single short sentence for the statement beats, and a single line for the end card. A card holds about 13 frames (0.54 s) at the fast end and up to 28 frames on a held statement, so the copy for a beat has to be readable inside that, which in practice means one to four words.

## When the house voice is used

The house voice on eleven_v4 is optional and only goes on when Umer asks for it. If it is used, the voice takes the role the on-screen words play now, and the type keeps its own rhythm rather than turning into captions: the voice speaks the beat's idea in a short plain sentence and the card shows only its key word, landing the word change on the stressed syllable rather than the sentence start. The voice sits out the opening titles (they are a visual inventory and work as a cold open over music) and the end card's first beat, and enters on the statement beat, the way the chromatic plates in the source are the first place the film says something in a sentence. Keep sentences short and level, with a falling end on each claim and a clear breath between ideas, since the picture holds its graphic beats for 0.5 to 1.2 s and a long sentence would run over two of them. The bed ducks under the voice by the margin `toolkit/sound-plan.py` applies, and its sectional shape stays, including the drop into the end card.

An example script on an unrelated subject (a neighbourhood bike repair co-op), tagged for eleven_v4 and written to sit over the statement beat, the demonstration beats and the end card:

```
[calm] One bench, every tool, and someone who has fixed it before.
[warm] Bring the wheel. [short pause] We true it with you.
[matter-of-fact] Brakes, chains, gears. [short pause] Learn it once.
[softly] Open Saturdays.
```

`toolkit/DELIVERY-V4.md` holds the tags that steer v4, and `tts.py --retime` adjusts the pauses after generation so each sentence ends before the next card.
