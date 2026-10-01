#!/usr/bin/env bash
# ingest.sh <url-or-file> <slug>
#
# Pulls the best available video and audio into work/<slug>/source.mp4 and writes
# work/<slug>/probe.json (duration, fps, width, height, codecs, has_audio, sha256).
# URLs go through yt-dlp (best video + best audio merged to mp4). LinkedIn is retried
# with cookies from Chrome; if the post is still gated the script prints GATED and
# exits 3 so the caller can ask for the file in inbox/. A local path is copied as is
# (remuxed to mp4 when it is another container, never re-encoded).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FFPROBE=/opt/homebrew/bin/ffprobe
FFMPEG=/opt/homebrew/bin/ffmpeg
YTDLP="$(command -v yt-dlp || echo /opt/homebrew/bin/yt-dlp)"

if [[ $# -lt 2 ]]; then
  echo "usage: ingest.sh <url-or-file> <slug>" >&2
  exit 2
fi
SRC="$1"
SLUG="$2"
OUT="$ROOT/work/$SLUG"
mkdir -p "$OUT"
DEST="$OUT/source.mp4"

gated() {
  cat >&2 <<EOF
GATED: could not download $SRC
The post needs a login yt-dlp cannot reuse (or it was removed). Download the video
yourself, drop the file into $ROOT/inbox/, then run:
  $0 $ROOT/inbox/<file> $SLUG
EOF
  exit 3
}

download() {
  # $@: extra yt-dlp args
  "$YTDLP" --no-playlist --no-progress \
    -f "bv*+ba/b" -S "res,fps,vcodec:h264,acodec:aac" \
    --merge-output-format mp4 --remux-video mp4 \
    -o "$OUT/download.%(ext)s" "$@" "$SRC"
}

if [[ -f "$SRC" ]]; then
  case "${SRC##*.}" in
    mp4|MP4) cp -f "$SRC" "$DEST" ;;
    *) "$FFMPEG" -v error -y -i "$SRC" -map 0 -c copy -movflags +faststart "$DEST" \
         || "$FFMPEG" -v error -y -i "$SRC" -c:v libx264 -crf 12 -preset slow -c:a aac -b:a 320k "$DEST" ;;
  esac
elif [[ "$SRC" =~ ^https?:// ]]; then
  rm -f "$OUT"/download.*
  ok=0
  if [[ "$SRC" =~ linkedin\.com ]]; then
    download 2>"$OUT/ytdlp.log" && ok=1
    if [[ $ok -eq 0 ]]; then
      echo "LinkedIn refused an anonymous download, retrying with Chrome cookies" >&2
      download --cookies-from-browser chrome 2>>"$OUT/ytdlp.log" && ok=1
    fi
  else
    download 2>"$OUT/ytdlp.log" && ok=1
    if [[ $ok -eq 0 ]] && grep -qiE "login|logged|cookies|private|sensitive|age|NSFW|authorization" "$OUT/ytdlp.log"; then
      echo "download needs a login, retrying with Chrome cookies" >&2
      download --cookies-from-browser chrome 2>>"$OUT/ytdlp.log" && ok=1
    fi
  fi
  got="$(ls "$OUT"/download.* 2>/dev/null | head -1 || true)"
  if [[ $ok -eq 0 || -z "$got" ]]; then
    tail -5 "$OUT/ytdlp.log" >&2 || true
    gated
  fi
  mv -f "$got" "$DEST"
  echo "$SRC" > "$OUT/source-url.txt"
else
  echo "not a file or URL: $SRC" >&2
  exit 2
fi

# probe.json
SHA="$(shasum -a 256 "$DEST" | cut -d' ' -f1)"
"$FFPROBE" -v error -show_streams -show_format -of json "$DEST" | python3 -c '
import json, sys
from fractions import Fraction
info = json.load(sys.stdin)
dest, sha, out = sys.argv[1:4]
v = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
fps = float(Fraction(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1")) if v else None
res = {
  "path": dest, "sha256": sha,
  "duration": round(float(info["format"].get("duration", 0)), 4),
  "fps": round(fps, 4) if fps else None,
  "width": int(v["width"]) if v else None, "height": int(v["height"]) if v else None,
  "video_codec": v.get("codec_name") if v else None,
  "audio_codec": a.get("codec_name") if a else None,
  "audio_channels": int(a.get("channels", 0)) if a else 0,
  "has_audio": a is not None,
  "bit_rate": int(info["format"].get("bit_rate", 0) or 0),
}
open(out, "w").write(json.dumps(res, indent=1, sort_keys=True) + "\n")
print(json.dumps(res, indent=1, sort_keys=True))
' "$DEST" "$SHA" "$OUT/probe.json"
echo "$DEST"
