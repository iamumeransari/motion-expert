# Moves

Every move in the source, shot by shot, measured from the fingerprint and read from dense frame strips. Frame numbers are source frames at 24 fps counted from zero (frame f sits at f/24 s), and timecodes are seconds. A fitted bezier is quoted only where `fingerprint.json` has one, with its fit error and confidence; anything shorter than four frames is described by eye from the strip, because compression and the cadence below leave too few samples for a curve. Strips referred to below live outside the skill in `~/motion-expert/sources/editorial-select/frames/`, with the source video. Signature moves are marked SIGNATURE with the name the capture gave them; `blocks.json` lists which block now carries each one (select-title and baseline-settle are genre-word-card and select-handles, glyph-scramble and font-cycle are lockup-scramble, giant-word-pass is giant-type-pass, chromatic-cycle and gradient-type are chromatic-title, plate-drift is camera-rig, click-swap is cursor with camera-rig swaps, print-shrink is card-wipe and camera-rig, ghost-word and tile-pop are ghost-word-grow, select-grow is crop-select, type-on-select and logo-build are endcard-typeon).

## The cadence under every move

The whole film updates its picture sixteen times a second and is delivered at 24 fps, so every third frame repeats the one before it. Across the title cards, the grid scatter, the footage at 17.5 s and the billboards the repeated frame is the one with index f where f mod 3 equals 2 (frames 11, 14, 761, 764, 422 and 1037 all repeat their predecessor), and only the end card at frames 993 to 1003 runs on the other phase. A move that lasts six frames therefore shows four distinct pictures, which is why the handle snaps read as stepped rather than smooth. Rebuilds reproduce it by rendering at 24 fps and then replacing each frame with f mod 3 equal to 2 by frame f minus 1, never by changing the eases.

## Shots

The fingerprint finds 35 hard cuts and 6 soft transitions. A frame-difference pass finds six more hard cuts it missed (frames 532, 550, 562, 847, 938 and 958, at 22.167, 22.917, 23.417, 35.292, 39.083 and 39.917 s), so the film has 41 hard cuts and the 42 shots below. Two of the detected cuts sit inside one designed move (frame 72 is the title stepping up in size, and frame 760 is a selection jumping into a new layout), and three more hard changes of plate (frames 244, 312 and 911, 927) happen inside shots and are listed where they fall.

### Shot 1, frames 0 to 9 (0.000 to 0.417 s), first title card

A single serif word of three letters sits centred at the frame's middle in warm white with a letterpress grain in its fill, cap height 102 px (0.094 of frame height), over a photographic plate. Four square handle chips, 24 by 24 px, sit at the corners of a box whose chip centres are 48 px outside the word's left and right edges and at y 430 and 650, so the box is centred on the frame at 552 by 244 px including the chips. The chips are flat colour sampled from the plate (pale lilac top, rose and pink below), so the selection is tinted by the picture under it rather than by a brand colour. Nothing moves until frame 9, where the chips have begun travelling outward towards the next word's box (left chip at 798 px against 806 px on frame 8): the handles start moving one frame before the cut. Fingerprint moves 1 to 6 (translate, mask-wipe, opacity at 0.0 s, fit errors 0.05 to 0.14, low to medium) are the plate's own grain and a soft vignette breathing, not designed motion.

### Shot 2, frames 10 to 23 (0.417 to 1.000 s), second title card, SIGNATURE `select-title`

The word changes on the cut and the plate with it, and two things settle in the first six frames. The handles finish their glide from the previous box to the new one (left chip x 806 to 684, right chip 1086 to 1210) on a cubic ease-out over six frames counted from frame 9, so progress reads 0.49 on frame 10, 0.92 on frame 12, 0.98 on frame 13 and 1.0 on frame 15. While they move each chip is drawn as a streak along its path made of two or three overlapping copies with a visible gap between them (frame 10 left chip: pieces at 746 to 769 and 772 to 826 px), so the motion blur is segmented like a multi-sample shutter rather than smooth. At the same time the word opens its letter-spacing: its ink width is 358 px on frames 10 and 11, 386 on 12, 441 on 13 and 14, 455 on 15 and its final 458 px from frame 16, so it starts at 78 percent of its set width and lands on the same six-frame cubic ease-out as the handles. Measured cap height 102 px, x-height 75 px, baseline at y 591, descender to 629. Fingerprint move 7 (scale 0.458 to 0.667 s, ratio 1.11, bezier 0.536, 1.256, 0.0, 0.53, error 0.028, medium) is this tracking change read as scale. The handle chips on this card are tan (#cda784 to #bc906a), again sampled from the plate.

### Shot 3, frames 24 to 36 (1.000 to 1.542 s), third title card

Same move with a longer word (eleven letters): the word enters at 83 percent of its width with its letters crowding, reaches 98 percent on frame 25 and settles by frame 27, while the chips glide outward from the previous box to x 458 and 1436 px with the segmented streak on frames 24 to 26. The chips here are four different colours sampled from the plate (dark brown top left, pink top right and bottom, a pale blue on one frame), which shows the sampling is per chip. Fingerprint move 8 (mask-wipe 1.083 to 1.417 s, error 0.036) is the right-hand chips' streak, and move 9 (opacity, error 0.061) is plate flicker.

### Shot 4, frames 37 to 51 (1.542 to 2.167 s), fourth title card

The word enters the other way, with its letters spread to about 127 percent of set width on frame 37, 120 percent on frame 38 and 106 percent on frame 39, landing on frame 40 or 41, so tracking can close in as well as open. The chips glide inward to the narrower box (x 611 and 1283 px) with the same streak. Fingerprint move 10 (organic, 1.583 to 2.042 s) is a soft light change inside the plate.

### Shot 5, frames 52 to 63 (2.167 to 2.667 s), fifth title card

A four-letter word; its width does not change on entry, so the tracking snap is optional rather than automatic. The chips glide from the wide box to x 810 and 1112 px over frames 52 to 55 with the streak, and one chip carries a dark blue gradient as if a tiny crop of the photograph had been used as its fill. Fingerprint moves 11 to 13 (translate at 2.208 s, 0.17 to 0.33 s, errors 0.044 to 0.056, medium) are the chips' travel.

### Shot 6, frames 64 to 71 (2.667 to 3.000 s), sixth title card

A nine-letter word enters condensed at 70 percent of its set width (634 px against 911 px), opens to 93 percent on frame 66, 97 on 67 and 68, 99 on 69 and lands on frame 70. The white chips stretch to 62 px streaks on frames 64 and 65, split into two pieces on frame 66 and settle to 30 px wide on frame 70 (the chip is drawn a few px wider than tall for one more step before reaching 24). Fingerprint moves 14 to 18 (translate and opacity at 2.708 s, 0.17 to 0.21 s, two at error above 0.1) are the streaks; the curves are below the four-frame floor and are a gap.

### Shot 7, frames 72 to 78 (3.000 to 3.292 s), the title steps up and is invaded, SIGNATURE `select-title` (grow-with-target)

The detected cut at frame 72 is the same word stepping up in size by a factor of 1.29 in one frame, centred, with no interpolation. A second set of chips appears at once on the bigger box (x 370 and 1525 px, y 384 and 671 px), while the old chips stay on the old box for three frames (72 to 74) and disappear on frame 75, so for a moment the frame carries two nested selections. On frame 75 a square photo tile in rose and magenta drops in at the upper left and on frame 76 a second, larger tile overlaps the word's first letter from below; the word slides left by about 30 px across frames 76 to 78 and the inner chips are gone. Fingerprint move 19 (scale 3.042 to 3.208 s, ratio 1.10, bezier 0.763, -0.258, 0.451, 1.424, error 0.012, medium, few samples) is the step. On frame 79 the grid paper replaces the black plate with the tiles already in place.

### Shot 8, frames 79 to 251 (3.292 to 10.500 s), the paper sequence

This shot holds six designed beats on one paper ground, and the fingerprint's soft transition at 9.125 to 10.167 s is the last of them.

From frame 79 to 112 (3.29 to 4.70 s), SIGNATURE `tile-scatter`: the ground is pale grey paper (#e8e9e9) ruled with a 1 px grey grid (#d2d2d2 at full strength) every 120 px across and every 121.5 px down, aligned so a vertical rule runs through x 960 and a horizontal rule through y 540. Small photo tiles, between about 70 and 160 px on a side, appear one or two at a time on whole frames with no entrance tween (new tiles on frames 80, 85, 86, 89, 91 and 92), each a crop of a different photograph, and lowercase serif words at 40 px cap height appear beside them, one word per tile, black on the paper. Tiles never move once placed; the image inside a tile changes on some frames (a tile's crop is swapped while its rectangle stays), which is what fingerprint moves 20 to 22 (translate 3.333 to 5.667 s, errors 0.05 to 0.21) catch.

From frame 113 (4.71 s): the scattered words leave their tiles and are drawn as one sentence on one line centred at y 540, black serif at the same size, while the tiles stay. Two frames later the tiles start to disappear a few per frame (frames 120 to 128) until only the sentence remains on a plain paper ground; the grid goes with the last tile.

From frame 127 to 137 (5.29 to 5.71 s), SIGNATURE `glyph-scramble`: the sentence loses its letters at random, a few per frame, the survivors staying exactly where they were, while letters of the next line appear at their final positions in a light violet (#a27ae7) mixed with the leftovers; by frame 134 the new line is complete in violet and on frame 136 it turns black. The new line is a serif lockup at about 30 px cap height, centred.

From frame 137 to 163 (5.71 to 6.83 s), a still hold of 26 frames on the lockup.

From frame 164 to 179 (6.83 to 7.46 s), SIGNATURE `font-cycle`: the lockup's second part changes typeface on each picture update (every one or two frames) through a light monospace, a regular grotesk, a pixel face, a stencil-like bold display and a heavy grotesk, while the first word stays in the serif, and the whole line scales up from frame 166 so that by frame 178 it has overflowed the frame. Frame 180 is a hard change to a single flat violet tile.

From frame 180 to 220 (7.50 to 9.17 s), SIGNATURE `icon-tile`: a square violet tile (#a27ae7) about 160 px wide sits in the centre of the paper, with a faint darker mark printed inside it. On frame 183 its corners are notched out by small squares the colour of the paper, on frame 184 the mark turns white, on frame 187 it turns black, and on frame 190 the tile steps up to about twice its size in one frame (fingerprint move 23, scale 6.833 to 7.542 s, ratio 1.15, error 0.11, low, and move 24, scale 7.875 to 9.042 s, ratio 1.31, error 0.08, low; both are steps the fitter tried to read as curves). Small violet chips then appear at the tile's corners one at a time (frames 193 to 197), and from frame 201 to 210 a black chip lands on one corner after another, clockwise from top left, one per update, as if a cursor were clicking each handle. On frame 220 the tile fades to a pale lavender (#c4ade4) in one step while the corner chips stay.

From frame 216 to 245 (9.00 to 10.21 s), SIGNATURE `giant-word-pass`: a giant black serif word, cap height about 300 px, enters from the lower right corner and travels up and left across the frame on a slow ease, cropped by the frame edges, while the small tile and its chips drift left with it. From frame 228 a blurred photograph blooms up behind it from below as a soft radial mask, and where the photograph sits the giant type turns white, with a soft gradient edge running across the letters (frame 234 shows one letter half black and half white). The fingerprint marks this as a soft transition of kind motion from 9.125 to 10.167 s. By frame 242 the second giant word follows the first from the right, the paper is gone and the photograph fills the frame.

### Shot 9, frames 252 to 260 (10.500 to 10.875 s), the chromatic plates begin, SIGNATURE `chromatic-cycle`

Detected as a cut at 10.5 s, but frames 244 to 251 already show a hard change on frame 244 to a small white serif line at 40 px cap height over a heavily blurred, colour-split photograph. On frames 244 to 251 the line's words sit at different baselines (the third word 20 px above the line and the fourth and fifth 25 to 40 px below), and on frame 252 they snap onto one baseline (SIGNATURE `baseline-settle`). The plate is a photograph blurred by about 30 px with its red, green and blue channels offset from each other by 20 to 40 px, washed towards lilac and white, and it changes on every cut while the text holds still in the same place.

### Shot 10, frames 261 to 264 (10.875 to 11.042 s)

A four-frame plate of the same treatment (a face, deep blue and red channels) with the same line on top.

### Shot 11, frames 265 to 279 (11.042 to 11.667 s)

A plate of the same treatment (a flower, pink and cyan), then on frame 274 a one-step darkening of the whole plate to grey, then a darker version of the plate with the green channel pushed. The fingerprint's dissolve at 11.375 to 11.5 s is this darkening, three frames long. Fingerprint moves 27 and 28 (opacity at 11.083 s, errors 0.033 and 0.028, medium, ratio-only) are the text's anti-aliasing flickering over the changing plate.

### Shot 12, frames 280 to 339 (11.667 to 14.167 s)

A run of chromatic plates crossfading every six to nine frames (face, face, butterfly, a pink hand, a landscape), the fingerprint's motion transition at 11.875 to 13.0 s, and on frame 312 a hard change to plain paper where the same line sits in the same place, now with each word filled with a different gradient of the plates' colours (violet blue, magenta, blue to pink, steel blue, rose; SIGNATURE `gradient-type`). This holds still for 28 frames (13.0 to 14.17 s), the longest held graphic before the end card.

### Shot 13, frames 340 to 362 (14.167 to 15.125 s), footage

A medium shot in a daylight studio with a slow camera drift. Fingerprint move 29 (translate 14.208 to 15.042 s, 0.83 s, dx 0.035, dy 0.025 of frame, bezier 0.15, 0.11, 0.614, 0.796, error 0.019, high) and move 30 (rotate, -6.3 degrees, error 0.035, medium) are the camera; this is the `drift` curve (SIGNATURE `plate-drift`).

### Shot 14, frames 363 to 387 (15.125 to 16.167 s), footage

A closer shot with the same drift. Fingerprint move 31 (translate 15.167 to 16.083 s, 0.92 s, dx -0.073, bezier 0.385, 0.326, 0.732, 0.781, error 0.024, high) is nearly linear; move 32 (translate 0.42 s, error 0.034, high) and move 33 (opacity) are the subject's hand and a light flicker, organic.

### Shot 15, frames 388 to 397 (16.167 to 16.583 s), footage

A close-up, held. Fingerprint move 34 (translate 0.29 s, error 0.052, medium) is organic.

### Shot 16, frames 398 to 419 (16.583 to 17.500 s), footage

The subject holds an object towards the lens; move 35 (translate 0.79 s, error 0.021, medium) is a slow handheld drift.

### Shot 17, frames 420 to 452 (17.500 to 18.875 s), mask selection, SIGNATURE `cursor`, `marquee-select`, `type-behind-subject`

A frontal medium shot on a grey studio wall. A grey arrow cursor with a white outline, about 40 px tall, slides in from the top edge on frames 421 to 425 and drifts down towards the subject's head. On frame 427 a white serif line of two words at 80 px cap height appears centred at y 490 in one frame, with no entrance tween. On frame 433 the cursor sits at the top left of the subject's head and from frame 435 to 441 it drags down and right, drawing a translucent white rectangle (about 25 percent white) with small white corner chips that grows from its top left corner with the cursor at its lower right. On frame 442 the selection resolves: the subject is lifted out and placed in front of the type, brightened by about 15 percent for two frames, the rectangle and chips vanish, and the type now sits between the background and the subject. From frame 444 the type fades to a ghost at about 15 percent opacity behind the subject over about four frames and holds there; the cursor drifts to the lower right. Fingerprint move 36 (opacity 17.583 to 17.917 s, error 0.055) is the cursor's arrival, move 37 (organic) the subject, move 38 (opacity 18.375 s, error 0.032, medium) the lift-out brightening.

### Shot 18, frames 453 to 477 (18.875 to 19.917 s), click to edit, SIGNATURE `click-swap`

The background behind the cut-out subject is replaced in one frame (patterned wallpaper and a white door where the grey wall was), so the cut is a background swap with the subject held in place. The cursor sits at the lower right, then on frame 462 it clicks on the subject's clothing and the clothing changes colour over two frames (black to rose, a two-frame cross-dissolve), and on frame 468 it clicks on the face and the face is relit with a soft warm bloom that peaks on frame 469 and settles over four frames. Fingerprint moves 39 to 42 (organic and translate, errors 0.03 to 0.11) are the cursor's short hops between clicks, each about four to six frames with an ease-out.

### Shot 19, frames 478 to 492 (19.917 to 20.542 s), background swap

The background changes again in one frame to a grey studio sweep, and on frame 480 to a rose satin sweep, while the subject and cursor stay put. Fingerprint move 43 (scale 20.583 s) belongs to the next shot.

### Shot 20, frames 493 to 504 (20.542 to 21.042 s), giant type behind the subject, SIGNATURE `type-behind-subject`

A close shot with the subject lying on a table and an object standing beside the face. A giant white serif line of two words at about 240 px cap height (0.22 of frame height) appears in one frame centred at y 600, between the background and the object, so the object's silhouette cuts through the second letter of the second word. The plate zooms out slowly (fingerprint move 43, scale 20.583 to 20.917 s, ratio 0.92, bezier 0.213, 0.313, 0.759, 0.883, error 0.043, medium) and the cursor fades in near the face on frame 499. Moves 44 to 47 (translate at 20.583 s) are the same zoom read in four regions.

### Shot 21, frames 505 to 531 (21.042 to 22.167 s), the type leaves, then a push

The giant type is gone on frame 505 with no exit tween, the cursor stays on the face, and from frame 522 the frame pushes in (fingerprint move 48, scale 21.75 to 22.292 s, ratio 1.47, bezier 0.772, 0.446, 0.150, 0.453, error 0.039, medium, the `push-hard` curve; the fit runs past the cut at frame 532, so only its first ten frames are this shot's).

### Shot 22, frames 532 to 537 (22.167 to 22.417 s), the object on paper, SIGNATURE `click-swap` (plate cycle)

A cut the fingerprint missed: the object alone as a cut-out on white paper, centred, about 200 px wide, held six frames.

### Shot 23, frames 538 to 543 (22.417 to 22.667 s), background swap

The same cut-out stays exactly where it was while the background behind it changes to a photograph of a field of flowers.

### Shot 24, frames 544 to 549 (22.667 to 22.917 s), background swap

The background changes again (citrus slices) with the cut-out held, six frames.

### Shot 25, frames 550 to 561 (22.917 to 23.417 s), a giant rising word and the print shrink, SIGNATURE `giant-word-rise`, `print-shrink`

A cut the fingerprint missed, to the cut-out over long grass. From frame 552 to 560 a giant black serif word at about 330 px cap height rises from below the frame on an ease-out, cropped by the bottom edge and passing behind the cut-out, its first three letters showing. On frame 561 the whole frame shrinks to a card inset by about 30 px on each side with a white paper margin. The fingerprint's dip-to-black at 22.875 to 23.542 s is this run of changes and the next shot's wipe; it never dips to black.

### Shot 26, frames 562 to 636 (23.417 to 26.542 s), card wipe, staggered line, a rising object and a label edit, SIGNATURE `print-shrink` (card wipe), `cursor`

A cut the fingerprint missed: a second card carrying the next photograph slides in over the shrunken one from the right on frames 562 and 563, and on frame 564 the new photograph fills the frame. From frame 564 a white serif line of three words at 80 px cap height sits over a photograph of a reclining subject with an object balanced on the face, the second word dropped 20 px below the others (the same staggered baseline as shot 9, held rather than settled). On frame 586 the frame cuts closer and the object rises through the type from below (fingerprint move 50, translate 23.583 to 24.75 s, 1.17 s, dx -0.080, dy 0.072, bezier 1.0, 0.323, 0.621, 0.928, error 0.039, medium), so the type now reads behind the object. On frame 600 the type is gone and the cursor enters from the lower left, travels to the object's label and clicks; the frame pushes in (fingerprint move 52, scale 25.0 to 25.542 s, ratio 1.34, bezier 0.336, -0.065, 0.0, 0.821, error 0.032, high, the `push` curve) and on frame 616 one line of the label changes its wording in one frame, the edit landing on the click.

### Shot 27, frames 637 to 686 (26.542 to 28.625 s), type on paper, image fill and echo stack, SIGNATURE `type-fill-echo`

A dark grey (#343434) serif line of two words at 185 px cap height (0.171 of frame height) sits centred on plain paper and grows very slowly (about 3 percent over 1.5 s, fingerprint move 54, translate 26.583 to 27.042 s, bezier 0.034, 0.665, 0.702, 1.023, error 0.027, high, the `glide` curve, which here is the left edge moving as the line grows). On frame 679 the type's fill turns into a photograph (the image shows only inside the letters), and on frame 681 two more copies of the line appear at about 1.6 times the size, one cropped by the top edge and one by the bottom, also image-filled, stacked tight above and below it. Fingerprint move 55 (scale 28.208 s, ratio 1.04, error 0.27, low) is that step and is a gap as a curve.

### Shot 28, frames 687 to 701 (28.625 to 29.250 s), type over a spread

A cut to a photograph of printed pages under hard sunlight with the same two words in white serif at 70 px cap height centred, which shrinks in two steps (frame 691 and frame 694, to about 0.82 of its size) and is gone by frame 697. The fingerprint's motion transition at 28.75 to 28.917 s is the first step.

### Shot 29, frames 702 to 716 (29.250 to 29.875 s), footage

Printed pages in sunlight with a hand lifting the top sheet; fingerprint move 56 (organic, 0.5 s, error 0.050) is the hand and the paper.

### Shot 30, frames 717 to 732 (29.875 to 30.542 s), footage

Three people seen from behind looking at a wall of prints; moves 57 to 60 (opacity and translate around 30.0 s, errors 0.07 to 0.17) are people shifting their weight.

### Shot 31, frames 733 to 746 (30.542 to 31.125 s), ghost word and tile pops, SIGNATURE `ghost-word`, `tile-pop`

Pale paper with a giant ghosted serif word in light grey (#e1e1e1 on #eeeeee), cap height about 640 px, cropped by all four edges and set as a repeated row so the word runs off both sides. Over it, a small black serif word at 40 px cap height sits centred. Photo tiles of different shapes (about 190 by 110 to 130 by 150 px) appear on whole frames with no tween (frames 736, 738, 742 and 744), one at a time, around the small word.

### Shot 32, frames 747 to 759 (31.125 to 31.667 s), the small word grows and gets selected

On frame 744 the small word steps up to 80 px cap height in one frame, and one more tile appears on frame 747. On frame 751 violet chips (#a27be6) appear around the small word, and on frame 757 a tile is pulled in behind the word inside the selection, the chips jumping out to its corners on frame 759.

### Shot 33, frames 760 to 816 (31.667 to 34.042 s), select and grow, SIGNATURE `select-grow`

The other tiles and the ghost word are gone and the selected tile sits centred on plain paper at about 180 by 220 px, with the word, now one letter longer and set in the same black serif, overlapping its bottom edge. Its violet handles arrive as diagonal streaks flying out from the previous selection's corners to the tile's corners (frames 760 and 761, each streak about 80 by 90 px), land as 38 px chips on frame 763 and shrink to 26 px by frame 766. On frame 777 the tile grows in width to about 360 px, taking a wider crop of the same photograph rather than stretching it, its handles gliding out with the segmented streak (pieces 60 and 116 px wide on frame 777) and landing on frame 782; the word steps up in size with it. On frame 796 the tile grows again to the full width minus margins (about 1700 by 200 px, the photograph revealing more of itself), the handles streaking diagonally, and the word's letter-spacing opens to about 0.3 em while its size steps up, landing on frame 800 and holding to frame 816.

### Shot 34, frames 817 to 827 (34.042 to 34.500 s), type over a plate with the cursor

A full-frame photograph with a short white serif word and an ellipsis at 110 px cap height, set with its first letters overlapping the subject's head. The cursor hovers above it. Fingerprint move 64 (scale 34.083 to 34.417 s, ratio 1.14, bezier 0.0, 0.331, 0.0, 0.653, error 0.039, medium) is a slow push on the plate.

### Shot 35, frames 828 to 846 (34.500 to 35.292 s), shrink to print, SIGNATURE `print-shrink`

The type is gone and the plate holds with the cursor; on frame 844 the plate shrinks to about 0.95 of the frame with a white paper border, on frame 845 to about 0.92 and on frame 846 to about 0.85, each a single step. Fingerprint move 65 (scale 35.083 to 36.0 s, ratio 0.73, bezier 0.30, 0.465, 0.0, -0.012, error 0.044, medium) spans this shrink and the next shot, across the missed cut, so its curve is not usable.

### Shot 36, frames 847 to 865 (35.292 to 36.083 s), the print on a billboard

A cut the fingerprint missed, to a street-level photograph of a rooftop billboard showing the same picture, so the shrink reads as the picture being printed and put up; a slow drift.

### Shot 37, frames 866 to 881 (36.083 to 36.750 s), billboard drift

A wider street view of the billboard with a passer-by crossing in the foreground; fingerprint move 66 (translate 36.125 to 36.667 s, dy -0.06, bezier 1.0, 0.937, 0.874, 0.965, error 0.014, medium) is a slow tilt up.

### Shot 38, frames 882 to 897 (36.750 to 37.417 s), second billboard

A billboard on a dark brick wall with a two-word serif headline on the poster. Fingerprint move 67 (scale 36.792 to 37.333 s, ratio 0.82, bezier 0.420, 0.543, 1.0, 1.076, error 0.012, high, the `settle` curve) is a slow pull-back, and move 68 (translate 37.042 to 37.333 s, bezier 0.548, 0.202, 0.334, 0.620, error 0.028, high) the drift that goes with it.

### Shot 39, frames 898 to 937 (37.417 to 39.083 s), night posters and a skyline

Three plates in one detected shot: a lit poster at a night bus stop with a car passing (frames 898 to 910, fingerprint moves 69 and 70, organic and translate, errors 0.024 and 0.047), a hard change on frame 911 to a street poster at night among crowds, and a hard change on frame 927 to a wide skyline at dusk with a distant billboard, nearly still. The fingerprint's motion transition at 37.917 to 38.625 s is the night-plate change.

### Shot 40, frames 938 to 957 (39.083 to 39.917 s), billboard under an overpass

A cut the fingerprint missed: a long billboard under an overpass with a two-word headline, held almost still.

### Shot 41, frames 958 to 992 (39.917 to 41.375 s), the pull-back, SIGNATURE `plate-drift` (pull)

A cut the fingerprint missed, to a rooftop billboard on a brick building, and the film's longest real camera move: a pull-back that takes the billboard from filling most of the frame to about half its size, landing about frame 982 (40.92 s) and holding. Fingerprint move 71 (scale 38.667 to 41.167 s, 2.5 s, ratio 0.31, bezier 0.924, 0.668, 0.604, 0.958, error 0.013, high) spans this shot and the two before it across two missed cuts, so it is a tracking artefact as one move; its curve shape is kept as the `pull` easing because the part inside this shot carries most of its travel, and the pull is a gap until it is refitted on frames 958 to 992 alone.

### Shot 42, frames 993 to 1135 (41.375 to 47.381 s), end card, SIGNATURE `type-on-select`, `logo-build`

Plain paper (#eeeeee). A black serif sentence at 26 px cap height types on word by word from the centre, one word per picture update or two (frames 993, 994, 996, 998, 999, 1000), always centred, so the line grows outward from both sides. Violet selection handles (#a17ae7) track the line: on each new word they streak outward to the new width with the segmented trail and settle to 8 px chips, landing on frame 1004 with the box about 340 by 54 px. Fingerprint move 72 (scale 41.458 to 42.0 s, ratio 1.29, error 0.042, medium) is the box growing. The line holds until frame 1020, then on frame 1021 the words vanish, the handles collapse diagonally inward as four streaks pointing at the centre (frames 1021 to 1026, move 73, scale 42.5 to 42.917 s, error 0.055, low), and a small black mark about 30 px wide appears at the centre on frame 1022. The handles, now 6 px chips, hover around the mark at a short distance and fade by frame 1034. On frame 1035 the product name appears beside the mark in a high-contrast serif wordmark at about 40 px cap height and the pair slides left so the lockup is centred (fingerprint move 74, translate 43.083 to 43.792 s, dx -0.123, bezier 0.081, -0.525, 0.0, 0.951, error 0.034, high, the `reveal` curve: a slight backward drift then a fast settle). On frame 1063 a small 12 px line of type appears under it in one frame, and the card holds to the end with no further motion.

## Soft transitions

The fingerprint's six soft transitions, each placed against the shots above: 9.125 to 10.167 s (motion, the giant word passing over the paper and the photograph blooming in, shot 8); 11.375 to 11.500 s (dissolve, a three-frame darkening between two chromatic plates, shot 11); 11.875 to 13.000 s (motion, the run of crossfading chromatic plates, shot 12); 22.875 to 23.542 s (reported as dip-to-black, actually the rising word, print shrink and card wipe, shots 25 and 26); 28.750 to 28.917 s (motion, the type over the spread stepping down, shot 28); 37.917 to 38.625 s (motion, the night plates changing, shot 39).
