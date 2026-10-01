#!/usr/bin/env bash
# Lint, check and render a HyperFrames project built by build-composition.mjs.
#
#   toolkit/render.sh <project-dir> <out.mp4>
#
# Stops before rendering on any lint or check error, because a lint error also
# switches off check's layout and contrast audits and a render spent on a
# rejected composition is wasted. After the render it confirms the file exists
# and that its duration matches the root data-duration to within one frame.
#
# Env: QUALITY (draft | looks | high, default high), STRICT=1 to run check
# --strict so warnings gate too, WORKERS to pin render workers.
set -euo pipefail

HF=(npx -y hyperframes@0.8.101)

die() { printf '\nrender.sh: %s\n' "$*" >&2; exit 1; }

[ $# -eq 2 ] || die "usage: toolkit/render.sh <project-dir> <out.mp4>"
dir=$(cd "$1" 2>/dev/null && pwd) || die "no such project directory: $1"
out=$2
case "$out" in /*) ;; *) out="$PWD/$out" ;; esac
[ -f "$dir/index.html" ] || die "$dir has no index.html"
mkdir -p "$(dirname "$out")"

echo "== lint $dir"
if ! "${HF[@]}" lint "$dir"; then
  die "hyperframes lint reported errors; nothing rendered"
fi

echo "== check $dir"
check_args=(check "$dir")
[ "${STRICT:-0}" = "1" ] && check_args+=(--strict)
if ! "${HF[@]}" "${check_args[@]}"; then
  die "hyperframes check failed; nothing rendered"
fi

echo "== render -> $out"
render_args=(render "$dir" --output "$out" --quality "${QUALITY:-high}" --strict)
[ -n "${WORKERS:-}" ] && render_args+=(--workers "$WORKERS")
"${HF[@]}" "${render_args[@]}" || die "hyperframes render failed"

[ -s "$out" ] || die "render produced no file at $out"

want=$(sed -n 's/.*data-composition-id="main"[^>]*data-duration="\([0-9.]*\)".*/\1/p' "$dir/index.html" | head -1)
fps=$(sed -n 's/.*data-composition-id="main"[^>]*data-fps="\([0-9/]*\)".*/\1/p' "$dir/index.html" | head -1)
got=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$out")
vdur=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 "$out")
astreams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$out" | wc -l | tr -d ' ')
echo "== $out: container ${got}s, video ${vdur}s, ${astreams} audio stream(s); plan ${want}s at ${fps:-30} fps"

if [ -n "$want" ]; then
  node -e '
    const [want, got, fps] = [Number(process.argv[1]), Number(process.argv[2]), process.argv[3] || "30"];
    const [n, d] = fps.split("/").map(Number);
    const frame = 1 / (n / (d || 1));
    if (Math.abs(got - want) > frame + 1e-6) {
      console.error(`video runs ${got}s, the plan ${want}s: off by more than one frame (${frame.toFixed(4)}s)`);
      process.exit(1);
    }
  ' "$want" "$vdur" "${fps:-30}" || die "duration check failed"
fi
echo "== ok"
