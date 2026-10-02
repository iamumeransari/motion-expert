# EditorialSelect Serif: coverage

EditorialSelect Serif Regular is a static TrueType face (1000 units per em, cap height 690, x-height 499, space 238) built for this style. Its letters come from the film itself wherever the film shows them, and from Source Serif 4 wherever it does not, so the file is a derivative of an OFL font and ships under the SIL Open Font License 1.1 (`OFL-sourceserif4.txt` in this folder).

## Traced from the film (36)

`. 4 5 A B D E F I L M O P T W a b c d e g h i k l m n o p r s t u v w y`

Each glyph is the source's own ink, normalised to the common cap height, shifted on a distance field to one weight (the film's main weight, which matches Exposure at about -20), smoothed by about one source pixel (two and a half for O and W, which came from one-bit masks), then traced. Where one line holds several instances of a letter they are aligned and averaged. The instance used per glyph:

| glyph | source instance (film frame or shot) | source cap height |
|---|---|---|
| E d i t | s4 shot 20 trace | 432 px |
| O | frame 825, point-symmetric repair where a highlight crossed it | 270 px |
| M a s k | s4 shot 17 trace | 205 px |
| W | frame 590 | 191 px |
| L c h n u | frame 655 | 186 px |
| e m o r | frame 76, the 1.5x title step | 157 px |
| A D F P g l y | s1 title card traces, frames 0 to 71 | 103 px |
| T | s3 traced line, frames 244 to 339 | 89 px |
| I 4 5 . | frame 160 | 85 px |
| B | frame 740, thickened from the lighter Exposure 0 weight | 84 px |
| w | frame 1004 | 73 px |
| b v | frame 112 | 67 px |

Advance widths come from a least-squares fit of every measured gap between neighbouring letters in eleven lines (rms residual 12.9 units after a per-line tracking term), with Source Serif 4's proportions as a weak prior. Fifteen kerning pairs whose measured gap departs from that fit by 8 units or more are in the `kern` feature: il ll el gh Tr ry at id rt ho ap hy al Fi lm.

## Filled from Source Serif 4 (65)

Capitals `C G H J K N Q R S U V X Y Z`, lowercase `f j q x z`, figures `0 1 2 3 6 7 8 9`, and punctuation and symbols `! " # $ % & ' ( ) * + , - / : ; < = > ? @ [ \ ] ^ _ { | } ~ and the backtick`, plus curly quotes, en dash, em dash and ellipsis. Lowercase fills use opsz 17 at wght 550, scaled to the traced x-height and narrowed to 0.969 of their width; capitals, figures and punctuation use wght 475, scaled to the cap height at 1.013 width. Those weights make the fills' stems equal the traced stems (lowercase 113 units, capitals 116), and their sidebearings carry the median difference between the traced and the scaled Source Serif sidebearings.

Space and no-break space are 238 units, measured from the film's word gaps.
