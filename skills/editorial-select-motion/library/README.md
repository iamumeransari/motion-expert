# Library

One HTML file per block, written to `~/motion-ui/library/CONTRACT.md`: scoped `.el-<name>` styles, a pure `render(props)`, and `animate(tl, el, t0, props)` using `fromTo` only, `immediateRender: false` on every tween after the entrance and no callbacks. Each block has a `.md` beside it and an entry in `../blocks.json`, and carries an identical copy of the shared runtime from `_runtime/` between its `es-runtime` markers; never edit a copy, change `_runtime/` and run `_runtime/inject.py`.

Never place a tween or a stepped key before time zero of the element's own range. A GSAP timeline that receives a child before its start pushes everything already on it later, which shifted one block five frames late; clamp every step to t0 or later.

Fonts and colours in general mode come from tokens (`var(--font-serif)`, `var(--color-*)`) or from props that default to tokens, so a style directory with another `tokens.css` re-skins every block. A block's replica preset holds only motion and geometry; the source-bound layer arrives as `props.replica` from `~/motion-expert/work/replica/presets/`.

`print-shrink.html` and `select-title.html` are the two elements from the first capture, kept because earlier replica sections still build with them; they are not blocks, carry no runtime, and new work uses card-wipe and camera-rig, and genre-word-card and select-handles, instead.
