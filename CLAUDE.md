# Motion expert

Turns a found video into a style skill that makes new work in the same hand. The
method lives in `skills/motion-expert/SKILL.md`; read it before capturing a style or
making a piece. Every style is listed in `registry.json`, the shared toolkit is in
`toolkit/` (Python via `uv run --project toolkit`, Node for storyboard and render),
and renders go through HyperFrames.

Storyboards go on the review canvas through the `storyboard-canvas` skill, one HTML
per scene, and nothing renders until Umer approves the board.

`.env` holds `ELEVENLABS_API_KEY`, `HOUSE_VOICE_ID` and `ELEVEN_MODEL=eleven_v4`.
Raw scratch goes in `work/`, which is gitignored; each style skill commits its full
source video under `assets/source/`.

This is a personal repo, so commit and push to `main` without asking.
`skills/*` is symlinked into `~/.claude/skills`, so this repo is the source of truth.
