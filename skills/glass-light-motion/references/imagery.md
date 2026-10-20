# Imagery

{{What the source's photography is, in a sentence or two: the kind of shoot, the settings, how the pictures are shown back (prints, spreads, billboards, screens) and the finish every photographic shot shares. Then which shots the profile in imagery.json measures, by group name and shot indices from `toolkit/measure/imagery.py --group`, and which shots were left out and why.}}

## Look

{{One paragraph a photographer would recognise, written about the photography and never about the source's subject: camera and stock, the light, the finish, how skin and surfaces render, the colour handling. The prompt builder passes it to the generator verbatim, so it must hold for any subject.}}

## Look {{group}}

{{Optional. The same, for a named look group whose photography differs (a city exterior against a studio, say). Delete when there is one look.}}

## Shots

### close
scale: close
{{How a close shot in this hand is framed, written so it works for a person or an object.}}

### medium
scale: medium
{{How a medium shot is framed.}}

### wide
scale: wide
{{How a wide shot is framed.}}

### {{device}}
scale: {{close|medium|wide}}
{{Any presentation device the source repeats (a printed spread, a billboard, a phone in hand), written so the piece's own photograph can be mapped into it by HyperFrames, which usually means asking for a blank surface.}}

## Avoid

- text, lettering, words or numbers anywhere in the frame
- logos or brand marks
- watermarks
- {{anything else that breaks the look}}

## Never

These name the source's product, brand and people, and a prompt that contains one is refused.

- {{brand name}}
- {{product name or category word}}
- {{any other term that would pull the source's content into a plate}}

## Plates

{{How the source layers its photographs with type and UI: how often type sits behind the subject, its size and colour, which part of the subject overlaps it, any push-in or parallax measured on the photographic shots, and the `--room` the prompt should ask for.}}

## Gaps

{{What the measures could not recover about the photography (grain lost to compression, haze with no measure, a lens look the numbers cannot separate) and what was done instead.}}
