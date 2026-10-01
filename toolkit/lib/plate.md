# Plate

`plate.html` is a library element following `~/motion-ui/library/CONTRACT.md` that turns one graded, matted still into three stacked layers: the background plate, the type, and the subject cut out on top. Type set in the middle layer sits behind the subject, which is the "Edit it" move in the pilot, where the letters run across the frame and the subject's head and the object it holds overlap them. A style copies the file into its own `library/` (as `plate.html`, or under a move name such as `type-behind.html` once its type, entrance and push are fixed to the source's measured values), because the validator resolves elements from the style's library and a plan names them there.

The props come from `toolkit/imagery.py matte`: `bg` is `bg.png`, `fg` is `fg.png`, and `bgClean` is `bg-clean.png`. `text` is the word or line, `order` puts it behind the subject (the default) or in front, `typeX` and `typeY` place its centre as frame shares (never `x` and `y`, which the runtime reads as the element's own position), and `size` is the cap height as a share of the frame height. The look of the type should come from the style's tokens through `var(--font-display)`, so a style specialising the element changes its font, weight, colour and tracking in the element's scoped CSS rather than in props.

```json
{ "name": "plate", "target": "hero", "t": 0,
  "props": { "bg": "plates/teapot/bg.png", "fg": "plates/teapot/fg.png", "bgClean": "plates/teapot/bg-clean.png",
             "text": "Throw it", "typeX": 0.5, "typeY": 0.42, "size": 0.27,
             "push": 0.06, "origin": [0.7, 0.6], "parallax": 0, "typeAt": 2, "typeUnits": 4, "typeEase": "out" } }
```

The camera is a push-in: every layer scales from 1 to `1 + push` across the whole scene, linearly, around `origin` (the subject's centre as frame shares), which is how a still breathes like footage. With `parallax` at 0 all three layers scale together, so the cutout stays registered on its own pixels in `bg` and nothing can reveal a hole. With `parallax` above 0 the fg gains `push * (1 + parallax)` and the bg `push * (1 - parallax / 2)`, the type sits between them, and the element switches to `bgClean` so the strip of background the subject uncovers is filled; that fill is soft, so parallax stays around 0.3 to 0.6 on a push of 0.06 to 0.1, which reveals a few pixels rather than a region. The type enters with a `fromTo` from `typeFrom` (default a fade and a rise of 3 % of the frame height) over `typeUnits` timing units starting `typeAt` units after the move's time, eased by a named curve from the style's tokens. Every tween is `fromTo`, there are no callbacks, and the runtime's `finish` writes the resting from-states, so the element seeks cleanly in the board and the render.

Selection handles, cursors and spotlight boxes are separate elements layered over the plate in the same scene, so they can be timed to the voice and bound to sounds on their own; a cursor that should pass behind the subject is the one case that needs the fg duplicated above it, which a style does by rendering a second plate with only `fg` and no `bg` or `text`.

A smoke test of the element (one locked scene, one with parallax) lives in `work/imagery-test/plate-smoke/` and passes `hyperframes lint` with no errors.

## Getting the images into the board and the render

The plan names the matte files by path, relative to the plan file or the style folder (`"bg": "../imagery-test/matte-05/bg.png"`), and `storyboard.mjs` and `build-composition.mjs` copy each one into `assets/plates/` beside the frames or the composition under a content-hashed name, rewriting the prop to that relative path, so nothing needs placing by hand. With `order` behind (the default) the element marks the word `data-layout-allow-occlusion`, because the cutout covering the type is the move and `hyperframes check` would otherwise fail it as hidden text. A piece refuses plates that came from `imagery.py plates-from-source`, which only a plan in `"mode": "replica"` may use.
