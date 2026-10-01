# Library

One HTML file per move, written to `~/motion-ui/library/CONTRACT.md`: scoped `.el-<name>` styles, a pure `render(props)`, and `animate(tl, el, t0, props)` using `fromTo` only, `immediateRender: false` on every tween after the entrance and no callbacks. Each signature element's header comment names its source strip and measured values so a later agent can check it against the source.
