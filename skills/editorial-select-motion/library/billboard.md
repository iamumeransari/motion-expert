# billboard

Puts artwork up in the world. A logotype and a few lines of small type, with a rule or two, are laid out in the board's own flat space and carried onto a plane inside a photograph by a homography, so the type sits in the plate's perspective, takes the plate's light and softness, and moves with the picture when the camera moves. Anything that stands in front of the board (a passer-by, a car, a branch) is drawn again over the type from a cut-out, which is what makes the type read as printed on the board rather than laid over the frame. In the film this is the run of street billboards after the print shrinks (s7, shots B to I): the picture becomes a poster and the poster is suddenly everywhere.

Not signature in the sense of a graphic move the film invented, but it is the film's device for "this goes out into the world", and every shot of it pulls back.

## Two modes

`preset: "replica-s7-B"` to `"replica-s7-I"` replays a source shot exactly. The block holds that shot's measured keys: the board's flat size, its per-frame board-to-frame homography (tracked by SIFT then ECC against the flat median), the per-frame ink colour sampled from the plate, the glow and the edge blur. The plan supplies only content: the shot's inpainted frames as the slot sequence, its per-frame cut-outs, and the board artwork (traced logotype paths and small type set with per-glyph x) from `work/blocks/billboard/tools/make_replica_plan.py`. The small type in those shots is set in Montserrat, Josefin Sans and Playfair Display Italic, which the style does not carry, so a replica build passes `--style-dir work/blocks/_style-s67`.

With no preset the block is general. The plane is four corners `quad` (top left, top right, bottom right, bottom left) in frame px, or in the picture's own px with `quadSpace: "image"` and `slot.size`, in which case the corners follow the slot's crop and focal point. The homography is solved in `render()` from those corners, the board's flat height follows the quad's aspect, and the artwork is laid out from ES Serif glyph metrics, so a word of any length is centred on its ink and shrunk until it fits. Glow defaults to the film's 0.45 at 0.6 percent of the board width, and the edge blur to about 0.6 frame px whatever the board's size on screen, which is what the replica measured.

## Slots

| slot | what | notes |
|---|---|---|
| `slot` | the photograph: `{ src, fit, focal: [x, y], zoom, size: [w, h], cutout }`, or `{ frames: [src, ...] }` for a photo sequence played one picture per film frame | without a src it draws the labelled placeholder |
| `slot.cutout` | the same picture on transparency, the subject only, cropped exactly like the slot and drawn over the type | one still cut-out; a moving occluder uses `fgs` |
| `fgs` | per-frame cut-outs `[src or null, ...]`, aligned with the frames | the replica's passing car (E) and crowd (F) |
| `panel` | a printed ground on the plane: `{ color }` or an image slot `{ src, focal, light }` | `light` is a brightness multiplier to sit the print in the plate's light; `scrim` (0 to 1) prints a dark shade rising from the foot so light small type stays legible over a busy print |

## Text parameters

| prop | default | meaning |
|---|---|---|
| `word` or `art.logo.text` | none | the logotype, in ES Serif, cap height `art.logo.cap` (share of board height, 0.3), shrunk to fit `art.logo.width` (0.84), baseline `art.logo.y` (0.56), `align: "left"` to set it at the pad |
| `art.logo.d`, `art.logo.box` | none | a traced or drawn path set with its box, fitted to the board instead of a word |
| `art.lines` | [] | blocks of small type: `{ at: "below" or "tl", "tr", "bl", "br", "above", text (string or lines), face: "mono", "grotesk", "humanist", "serif", size (share of board height, 0.045), leading, tracking, weight }`; SVG anchors the alignment, so nothing is measured for placement |
| `art.rules` | [] | rectangles `[x, y, w, h]` as shares of the board |
| `art.items` | none | the replica's own item list (path, text with per-glyph `xs`, rect), which bypasses the layout |
| `ink` | `type-light` | token name or CSS colour (the replica takes it per frame from the plate) |
| `glow` | `[0.006 W, 0.45]` | `[blur px in board space, opacity]`, `null` for none (use none for dark ink on a pale board) |
| `soften` | about 0.6 frame px | edge blur in board space |
| `boardW` | 1000 | the flat board's width in its own units |

## Timing

The board cuts in with no entrance, which is how every billboard in the film arrives, and performs through its camera. `cam` is an es-camera move or list of moves (see `camera-rig.md`), applied to one container holding the picture, the plane and the cut-outs, so they move as one: the film's billboards all pull back, so `{ preset: "pull-back", from: 2.457 }` (2.457 is 1 / 0.407, so the pull lands at scale 1 and never shows the picture's edge) is the default reading, `pull-steady` the mid-move slice of shots B to H. Camera presets on footage run on ones; on a still, the film's graphic hand is the 16 fps cadence, so pass `cadence: "16"` when that is the read wanted. On a still the preset's measured travel is dropped unless the move sets `dx` or `dy`, because the picture has nothing past its edge to travel into. `scale` stretches every camera move; a move whose `at` is `{ beat: i }` starts on `props.beats[i]`. A photo sequence or per-frame keys advance one source frame per film frame from `t0`. `exitAt` cuts it out.

Duration: 0.45 s (shot G) to 1.46 s (shot I) in the film; any length in general mode, the default pull taking 35 frames and then holding.

## Source shots

s7 shots B to I, film frames 847 to 992 (35.292 to 41.375 s): B rooftop VELORA, C wider street, D Think it on brick, E bus shelter at night with a car crossing, F night poster in a crowd, G aerial Own it, H Own it under the rail bridge, I the long pull-back on the brownstone. Proof renders live in `work/blocks/billboard/` (out/B, out/E, out/BI for the replica, out/demo for the general mode).

## What does not generalise

The film's billboards are real footage with real parallax, so the replica needs the shot's own frames as a photo sequence; a still plate moved by the camera cannot reproduce them (s7 measured 0.75 to 0.95 SSIM that way). In general mode a still picture moves as one flat layer, which reads as a camera move on a photograph rather than a camera in a street. Board lighting is one ink colour plus glow; there is no per-pixel shading, so a board under strong raking light will look flat unless the panel's `light` and the ink are tuned by hand. Small type in grotesk and humanist faces is anchored by SVG, not measured, so it cannot be shrunk to fit; keep lines short.
