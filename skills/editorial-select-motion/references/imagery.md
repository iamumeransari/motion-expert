# Imagery

The film is built on one photographer's campaign: editorial beauty photography shot in a daylight studio and on a glossy mauve set, then the same pictures shown back as printed pages under a slash of sunlight and as billboards on brownstone rooftops. Every photographic shot shares a soft, slightly hazy finish with lifted blacks, a rose cast through the midtones that warms skin and mauve set walls while the grey studio wall stays cool, and fine grain that survives the encode. Measured in `imagery.json` over shots 12 to 21, 23 to 25 and 29 to 30 (the `editorial` look) and 31 to 34 (the `city` look); shots 1 to 11 are an intro montage of other genres and are left out of both.

## Look

Editorial campaign photography for a print magazine, shot on medium-format film in a daylight studio, skin and surfaces rendered soft and luminous with their real texture, no retouched plastic sheen, quiet confident styling, a slightly hazy, airy finish as if shot through clean glass with a touch of diffusion, colour graded like a printed magazine page.

## Look city

Street photography of a dense old city shot on 35mm colour negative film in the 1970s, faded warm colour, a hazy cream sky, deep but soft shadows between brick buildings, the quiet grandeur of a fashion campaign seen out in the world.

## Shots

### close
scale: close
The subject seen close, a person from the shoulders up or an object filling the middle of the frame, turned three-quarters to camera, set against a plain wall or a smooth satin backdrop that falls softly out of focus.

### extreme-close
scale: extreme-close
The subject filling most of the frame and cropped by its edges, the nearest detail in critical focus and everything behind it dissolved.

### medium
scale: medium
The subject in its setting with room around it, a person from the waist up or an object on a tabletop, a large window or a studio wall behind, light raking in from one side.

### spread
scale: close
The piece's hero photograph printed as glossy magazine pages and loose prints fanned on a pale table, seen from above at an angle, a hard diagonal slash of afternoon sunlight and window shadow falling across the pages.

### billboard
scale: wide
A large rooftop billboard on an old brick walk-up building in a dense city, seen from street level looking up, water towers and fire escapes, the billboard face a plain blank pale panel so the piece's own photograph can be mapped onto it.

## How imagery is framed

Photographs never appear as plain full-frame footage for long; the hand keeps showing them as objects. They are tiles on grid paper (70 to 220 px on a side, placed on whole frames with no tween and never moved once placed), a single selected tile that grows in steps to the full width while revealing more of its own picture rather than stretching, cut-outs held still while their background is swapped behind them, blurred colour-split plates under a still line of type, the fill of a word, prints with a white paper border that shrink into the frame, and finally billboards and posters in streets, which is the same picture printed and put up. A new piece keeps that ladder: the image starts small and selected and ends large and public.

## Stand-ins while generation is off

Until image generation is switched back on, tests and pieces use existing frames: the replica takes its plates from the source through `imagery.py plates-from-source`, and anything novel uses the non-source stand-ins in `~/motion-expert/work/imagery-test/standins` or frames from other videos, graded towards the look above.

## Avoid

- text, lettering, words or numbers anywhere in the frame
- logos or brand marks
- watermarks
- glossy plastic CGI rendering
- oversaturated colour

## Never

The words a prompt may never contain are kept in `imagery.json` under its never list and cited in `references/sources.md`, because they name the source; `toolkit/imagery.py` refuses any prompt that contains one.

## Plates

Type sits behind the subject in about a third of the photographic shots (shots 20, 23 and 31 in `moves.md`), always a large white or near-white serif set across the frame at roughly a third of its height, with the subject's head, hand or object overlapping the letters. Plates are built so the space behind and above the subject is clear, which is `--room behind` in `toolkit/imagery.py prompt`.

## Gaps

The grain measured here is what survived the source's encode, so it reads low (0.42 grey levels) and `grade` calibrates added grain through an x264 round trip rather than to the eye. The diffusion or haze in the highlights is described in words only, since no measure separates it from low contrast. The mauve satin backdrop is part of the look's palette and of the source's set design; the prompt carries its colour through the grade and palette words but never asks for that set.
