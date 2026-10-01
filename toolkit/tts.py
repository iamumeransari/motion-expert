#!/usr/bin/env python3
"""Voice a script with ElevenLabs eleven_v4 and return per-word and per-line timings.

    tts.py script.txt --out DIR [--voice ID] [--model eleven_v4] [--stability 0.5]
                      [--similarity 0.75] [--seed N] [--align auto|eleven|whisper]
                      [--retime PROFILE] [--wpm N --pause-median S --pause-p90 S --pauses-per-min N]
    tts.py --retime-only DIR --retime PROFILE      (re-time an earlier take, no API call)

The script is one line per spoken line; blank lines are ignored. Audio tags in square
brackets ([calm], [short pause], [excited]) steer delivery and are masked out of the
alignment, so a tag can never be mistaken for the line that follows it. Eleven v4 has
no SSML and no speed slider (see DELIVERY-V4.md), so pace comes from tags,
punctuation and, when a style asks for a measured pace, the --retime pass, which
re-sets the silence at word boundaries and applies a pitch-preserving tempo only when
silence alone cannot reach the target words per minute.

Outputs in DIR: vo.mp3, words.json [{w,start,end}], lines.json [{text,raw,start,end}],
vo.json (settings, alignment source, delivery stats). A retime keeps vo.raw.mp3 and
words.raw.json so every retime starts from the untouched take.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
WHISPER = "/opt/homebrew/bin/whisper-cli"
WHISPER_MODEL = Path.home() / ".whisper-models" / "ggml-medium.en.bin"
CHAR_LIMIT = 10_000
SR = 44_100
PUNCT_END = re.compile(r"[,.;:!?…\-]+[\"')\]]*$")
SENT_END = re.compile(r"[.!?…]+[\"')\]]*$")


# ---------------------------------------------------------------- env and API

def load_env() -> dict:
    env = {}
    for p in (ROOT / ".env", Path.home() / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def synthesize(text: str, voice: str, model: str, stability: float, similarity: float,
               seed: int | None, key: str) -> dict:
    body = {"text": text, "model_id": model,
            "voice_settings": {"stability": stability, "similarity_boost": similarity}}
    if seed is not None:
        body["seed"] = seed
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            res = json.loads(r.read())
            res["_request_id"] = r.headers.get("request-id")
            return res
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ElevenLabs HTTP {e.code}: {e.read()[:500].decode(errors='replace')}")


# ---------------------------------------------------------------- alignment

def words_from_eleven(alignment: dict, lines: list[str]) -> list[dict]:
    """Character alignment to word spans, skipping bracketed tags."""
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    keep, depth = [], 0
    for i, c in enumerate(chars):
        if c == "[":
            depth += 1
        elif c == "]":
            depth = max(0, depth - 1)
        elif depth == 0:
            keep.append(i)
    spoken = "".join(chars[i] for i in keep).lower()

    def walk(cursor, probe):
        idx, j = [], cursor
        for ch in probe:
            while j < len(spoken) and spoken[j] != ch:
                j += 1
            if j >= len(spoken):
                return None, cursor
            idx.append(j)
            j += 1
        return idx, j

    cursor, words = 0, []
    for li, ln in enumerate(lines):
        for w in ln.split():
            probe = re.sub(r"[^\w]", "", w).lower()
            if not probe:
                continue
            idx, nxt = walk(cursor, probe)
            if idx is None:
                words.append({"w": w, "start": None, "end": None, "line": li})
                continue
            cursor = nxt
            words.append({"w": w, "start": float(starts[keep[idx[0]]]),
                          "end": float(ends[keep[idx[-1]]]), "line": li})
    return words


def whisper_words(audio: Path) -> list[dict]:
    """Word timings from whisper-cli (one token per segment)."""
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(audio), "-ar", "16000", "-ac", "1",
                        str(wav)], check=True)
        subprocess.run([WHISPER, "-m", str(WHISPER_MODEL), "-f", str(wav), "-ml", "1", "-sow",
                        "-oj", "-of", str(Path(td) / "w"), "-np"],
                       check=True, capture_output=True)
        data = json.loads((Path(td) / "w.json").read_text())
    out = []
    for seg in data.get("transcription", []):
        t = seg["text"].strip()
        if re.sub(r"[^\w]", "", t):
            out.append({"w": t, "start": seg["offsets"]["from"] / 1000,
                        "end": seg["offsets"]["to"] / 1000})
    return out


def words_from_whisper(audio: Path, lines: list[str]) -> list[dict]:
    """Map whisper tokens onto the script's words so spelling and punctuation stay the script's."""
    heard = whisper_words(audio)
    script = [(li, w) for li, ln in enumerate(lines) for w in ln.split() if re.sub(r"[^\w]", "", w)]
    norm = lambda s: re.sub(r"[^\w]", "", s).lower()
    sm = SequenceMatcher(a=[norm(w) for _, w in script], b=[norm(h["w"]) for h in heard],
                         autojunk=False)
    words = [{"w": w, "start": None, "end": None, "line": li} for li, w in script]
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            words[a + k]["start"] = heard[b + k]["start"]
            words[a + k]["end"] = heard[b + k]["end"]
    return words


def fill_gaps(words: list[dict], total: float) -> list[dict]:
    """Interpolate any word the aligner lost between its timed neighbours."""
    n = len(words)
    i = 0
    while i < n:
        if words[i]["start"] is not None:
            i += 1
            continue
        j = i
        while j < n and words[j]["start"] is None:
            j += 1
        t0 = words[i - 1]["end"] if i > 0 else 0.0
        t1 = words[j]["start"] if j < n else total
        step = (t1 - t0) / (j - i)
        for k in range(i, j):
            words[k]["start"] = t0 + step * (k - i)
            words[k]["end"] = t0 + step * (k - i + 1)
        i = j
    return words


# ---------------------------------------------------------------- audio helpers

def decode(path: Path) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def encode(samples: np.ndarray, path: Path, tempo: float = 1.0):
    af = ["-af", f"atempo={tempo:.5f}"] if abs(tempo - 1) > 1e-4 else []
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    *af, "-b:a", "192k", str(path)], input=samples.astype(np.float32).tobytes(),
                   check=True)


def snap_quiet(x: np.ndarray, words: list[dict]) -> int:
    """Set word edges to the quiet runs between them, measured exactly as
    measure/delivery.py measures them (speech-band energy on 10 ms hops, threshold 35%
    of the way from the floor to the speech level, longest quiet run between word
    midpoints), so the gaps the retime sets are the gaps the measure will read."""
    from scipy.signal import butter, sosfiltfilt
    hop = int(SR * 0.01)
    xb = sosfiltfilt(butter(4, [200, 4000], btype="band", fs=SR, output="sos"), x.astype(np.float64))
    n = len(xb) // hop
    if n < 3 or not words:
        return 0
    db = 20 * np.log10(np.sqrt(np.mean(xb[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12) + 1e-9)
    db = np.convolve(db, np.ones(3) / 3, mode="same")
    fr = lambda t: int(np.clip(round(t / 0.01), 0, n - 1))  # noqa: E731
    inside = np.concatenate([db[fr(w["start"]):max(fr(w["end"]), fr(w["start"]) + 1)] for w in words])
    floor = float(np.percentile(db, 10))
    thr = floor + 0.35 * (float(np.median(inside)) - floor)
    moved = 0
    for i in range(1, len(words)):
        a, b = words[i - 1], words[i]
        lo, hi = fr((a["start"] + a["end"]) / 2), fr((b["start"] + b["end"]) / 2)
        best, cur, best_end = 0, 0, None
        for k, q in enumerate(db[lo:hi + 1] < thr):
            cur = cur + 1 if q else 0
            if cur > best:
                best, best_end = cur, k
        if best_end is not None and best * 0.01 >= 0.05:
            ps, pe = (lo + best_end - best + 1) * 0.01, (lo + best_end + 1) * 0.01
            if a["start"] < ps:
                a["end"] = ps
            if pe < b["end"]:
                b["start"] = pe
            moved += 1
    w0, wl = words[0], words[-1]
    k = fr(w0["start"])
    while k < fr(w0["end"]) - 5 and db[k] < thr:
        k += 1
    w0["start"] = k * 0.01
    k = fr(wl["end"])
    while k > fr(wl["start"]) + 5 and db[k] < thr:
        k -= 1
    wl["end"] = (k + 1) * 0.01
    return moved


def pauses_of(words: list[dict], min_pause: float) -> list[float]:
    return [words[i + 1]["start"] - words[i]["end"] for i in range(len(words) - 1)
            if words[i + 1]["start"] - words[i]["end"] >= min_pause]


def delivery_stats(words: list[dict], min_pause: float) -> dict:
    if not words:
        return {}
    span = words[-1]["end"] - words[0]["start"]
    p = pauses_of(words, min_pause)
    return {"words": len(words), "span": round(span, 3),
            "wpm": round(len(words) / span * 60, 1) if span > 0 else None,
            "pauses": {"median": round(float(np.median(p)), 3) if p else 0.0,
                       "p90": round(float(np.percentile(p, 90)), 3) if p else 0.0,
                       "per_min": round(len(p) / span * 60, 2) if span > 0 else 0.0,
                       "count": len(p)}}


# ---------------------------------------------------------------- retime

def load_profile(arg: str | None, overrides: dict) -> dict:
    """A pause profile from a fingerprint.json (its delivery block), a JSON file with
    {wpm, pauses:{median,p90,per_min}}, or a delivery.md carrying a ```json block."""
    prof: dict = {}
    if arg:
        p = Path(arg)
        text = p.read_text()
        if p.suffix == ".md":
            m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
            if not m:
                raise SystemExit(f"{p} has no ```json block with wpm/pauses")
            data = json.loads(m.group(1))
        else:
            data = json.loads(text)
        data = data.get("delivery") or data
        prof = {"wpm": data.get("wpm"), **(data.get("pauses") or {})}
    for k, v in overrides.items():
        if v is not None:
            prof[k] = v
    if not any(prof.get(k) for k in ("wpm", "median", "p90", "per_min")):
        raise SystemExit("retime needs a profile or at least one of --wpm/--pause-median/--pause-p90")
    return prof


def target_pauses(n: int, median: float | None, p90: float | None, current: list[float],
                  floor: float) -> list[float]:
    """n sorted target pause lengths whose linear-interpolated median and p90 (numpy's
    default, which the measure scripts use) land exactly on the profile. Values run
    linearly in rank through the two anchors, so even four pauses hit both numbers."""
    if n == 0:
        return []
    cur = sorted(current) if current else [0.3] * n
    med = median if median else float(np.median(cur))
    hi = p90 if p90 else (float(np.percentile(cur, 90)) * med / max(float(np.median(cur)), 1e-3))
    if n == 1:
        return [med]
    r50, r90 = 0.5 * (n - 1), 0.9 * (n - 1)
    slope = (hi - med) / (r90 - r50)
    return [max(floor, med + (k - r50) * slope) for k in range(n)]


def retime(out: Path, prof: dict, min_pause: float, allow_tempo: bool, log=print) -> dict:
    raw_mp3, raw_words = out / "vo.raw.mp3", out / "words.raw.json"
    if not raw_mp3.exists():
        shutil.copy(out / "vo.mp3", raw_mp3)
        shutil.copy(out / "words.json", raw_words)
    x = decode(raw_mp3)
    words = json.loads(raw_words.read_text())
    lines_meta = json.loads((out / "lines.json").read_text())
    line_of = []
    for li, ln in enumerate(lines_meta):
        line_of += [li] * sum(1 for w in ln["text"].split() if re.sub(r"[^\w]", "", w))
    before = delivery_stats(words, min_pause)

    # 1. Choose which boundaries carry a pause. Existing pauses stay pauses. When the
    #    profile wants more pauses per minute, promote unpaused punctuation boundaries,
    #    sentence ends first; when it wants fewer, demote the shortest mid-phrase ones.
    gaps = [words[i + 1]["start"] - words[i]["end"] for i in range(len(words) - 1)]
    is_pause = [g >= min_pause for g in gaps]
    punct = [bool(PUNCT_END.search(words[i]["w"])) or line_of[i] != line_of[i + 1]
             for i in range(len(gaps))]
    sent = [bool(SENT_END.search(words[i]["w"])) or line_of[i] != line_of[i + 1]
            for i in range(len(gaps))]
    if prof.get("per_min"):
        est_span = len(words) / prof["wpm"] * 60 if prof.get("wpm") else before["span"]
        want = int(round(prof["per_min"] * est_span / 60))
        have = sum(is_pause)
        if want > have:
            cands = sorted([i for i in range(len(gaps)) if not is_pause[i] and punct[i]],
                           key=lambda i: (not sent[i], -gaps[i]))
            for i in cands[: want - have]:
                is_pause[i] = True
        elif want < have:
            cands = sorted([i for i in range(len(gaps)) if is_pause[i] and not punct[i]],
                           key=lambda i: gaps[i])
            for i in cands[: have - want]:
                is_pause[i] = False
    idx = [i for i in range(len(gaps)) if is_pause[i]]
    demoted = {i for i in range(len(gaps)) if gaps[i] >= min_pause and not is_pause[i]}
    speech = sum(w["end"] - w["start"] for w in words) + sum(
        (min(g, 0.08) if i in demoted else g) for i, g in enumerate(gaps) if not is_pause[i])

    # 2. Target lengths, rank-matched so the longest pause stays the longest.
    cur = [gaps[i] for i in idx]
    tgt = target_pauses(len(idx), prof.get("median"), prof.get("p90"), cur, min_pause + 0.02)
    order = sorted(range(len(idx)), key=lambda k: cur[k])
    new_gap = {idx[k]: float(tgt[r]) for r, k in enumerate(order)}

    # 3. Tempo, only for what silence cannot reach. atempo scales speech and the fixed
    #    gaps; the chosen pauses are set after it, so they land exactly on target.
    tempo = 1.0
    if prof.get("wpm"):
        want_span = len(words) / prof["wpm"] * 60
        free = want_span - sum(new_gap.values())
        fixed = speech
        need = fixed / free if free > 0 else 9.9
        if abs(need - 1) > 0.02:
            if allow_tempo:
                tempo = float(np.clip(need, 0.85, 1.25))
            else:
                log(f"wpm target needs tempo {need:.3f}; pass --tempo to allow it")

    # A slowing tempo stretches short gaps too, and one stretched past the threshold
    # would become an unplanned pause; pin every unselected gap that could cross it.
    guard = min_pause - 0.03
    demoted |= {i for i in range(len(gaps)) if not is_pause[i] and gaps[i] / tempo >= guard}

    # 4. Rebuild the audio: speech chunks (sped by tempo) joined by exact silences.
    pad = 0.03
    chunks = []
    bounds = []  # (cut_at_end_of_word_i_plus_pad, resume_at_start_of_next_minus_pad, new_len)
    for i in range(len(gaps)):
        g = gaps[i]
        if i in new_gap or i in demoted:
            ng = new_gap.get(i, min(g, 0.08 if g >= min_pause else guard))
            p = min(pad, g / 2, ng / 2)
            bounds.append((i, words[i]["end"] + p, words[i + 1]["start"] - p, max(0.0, ng - 2 * p)))
    t_src = 0.0
    seg_starts = []  # (src_start, src_end, out_start) for time mapping
    out_t = 0.0
    with tempfile.TemporaryDirectory() as td:
        for (i, cut, resume, sil) in bounds + [(None, len(x) / SR, None, 0.0)]:
            seg = x[int(t_src * SR): int(cut * SR)]
            if abs(tempo - 1) > 1e-4 and len(seg) > SR * 0.02:
                tmp = Path(td) / "s.wav"
                subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                                "-i", "-", "-af", f"atempo={tempo:.5f}", "-f", "f32le", str(tmp)],
                               input=seg.astype(np.float32).tobytes(), check=True)
                seg = np.frombuffer(tmp.read_bytes(), np.float32)
            seg_starts.append((t_src, cut, out_t, len(seg) / SR))
            chunks.append(seg)
            out_t += len(seg) / SR
            if i is not None:
                chunks.append(np.zeros(int(round(sil * SR)), np.float32))
                out_t += sil
                t_src = resume
        y = np.concatenate(chunks)
    # every cut sits inside a silence, so the joins need no crossfade
    encode(y, out / "vo.mp3")

    def remap(t: float) -> float:
        for s0, s1, o0, olen in seg_starts:
            if s0 - 1e-6 <= t <= s1 + 1e-6:
                return o0 + (t - s0) / max(s1 - s0, 1e-9) * olen
        for s0, s1, o0, olen in seg_starts:  # inside a replaced gap: clamp to next chunk start
            if t < s0:
                return o0
        return out_t

    new_words = [{"w": w["w"], "start": round(remap(w["start"]), 3), "end": round(remap(w["end"]), 3)}
                 for w in words]
    (out / "words.json").write_text(json.dumps(new_words, indent=1))
    write_lines(out, lines_meta, new_words)
    after = delivery_stats(new_words, min_pause)
    res = {"tempo": round(tempo, 4), "target": prof, "before": before, "after": after,
           "duration": round(len(y) / SR, 3)}
    if prof.get("wpm") and after.get("wpm") and abs(after["wpm"] - prof["wpm"]) / prof["wpm"] > 0.03:
        res["wpm_miss"] = (f"wpm {after['wpm']} vs target {prof['wpm']}: tempo is clamped to "
                           "0.85..1.25 to keep the voice clean, so rewrite the script "
                           "(fewer or more words per line) or pick a slower or faster voice")
    return res


def write_lines(out: Path, lines_meta: list[dict], words: list[dict]):
    k = 0
    for ln in lines_meta:
        n = sum(1 for w in ln["text"].split() if re.sub(r"[^\w]", "", w))
        if n:
            ln["start"], ln["end"] = words[k]["start"], words[k + n - 1]["end"]
        k += n
    (out / "lines.json").write_text(json.dumps(lines_meta, indent=1))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?", help="script.txt, one spoken line per line, audio tags in []")
    ap.add_argument("--out", help="output directory")
    ap.add_argument("--voice")
    ap.add_argument("--model")
    ap.add_argument("--stability", type=float, default=0.5)
    ap.add_argument("--similarity", type=float, default=0.75)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--align", choices=["auto", "eleven", "whisper"], default="auto",
                    help="auto uses the API alignment and falls back to whisper-cli when it is missing")
    ap.add_argument("--retime", metavar="PROFILE",
                    help="fingerprint.json, delivery JSON, or delivery.md with a ```json block")
    ap.add_argument("--retime-only", metavar="DIR", help="retime an existing take in DIR, no API call")
    ap.add_argument("--wpm", type=float)
    ap.add_argument("--pause-median", type=float)
    ap.add_argument("--pause-p90", type=float)
    ap.add_argument("--pauses-per-min", type=float)
    ap.add_argument("--min-pause", type=float, default=0.25,
                    help="gap that counts as a pause (s); 0.25 matches measure/delivery.py")
    ap.add_argument("--no-tempo", action="store_true", help="never apply atempo; silence edits only")
    a = ap.parse_args()

    overrides = {"wpm": a.wpm, "median": a.pause_median, "p90": a.pause_p90, "per_min": a.pauses_per_min}
    wants_retime = a.retime or any(v is not None for v in overrides.values())

    if a.retime_only:
        out = Path(a.retime_only)
        info = retime(out, load_profile(a.retime, overrides), a.min_pause, not a.no_tempo)
        meta = json.loads((out / "vo.json").read_text())
        meta["retime"] = info
        (out / "vo.json").write_text(json.dumps(meta, indent=1))
        print(json.dumps({k: info[k] for k in ("tempo", "before", "after", "duration", "wpm_miss")
                          if k in info}, indent=1))
        return

    if not (a.script and a.out):
        ap.error("script and --out are required unless --retime-only is used")
    env = load_env()
    key = env.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY missing from ~/motion-expert/.env and ~/.env")
    voice = a.voice or env.get("HOUSE_VOICE_ID") or "pqHfZKP75CvOlQylNhV4"
    model = a.model or env.get("ELEVEN_MODEL") or "eleven_v4"

    raw = [l.strip() for l in Path(a.script).read_text().splitlines() if l.strip()]
    spoken = [re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", " ", l)).strip() for l in raw]
    text = "\n".join(raw)
    if len(text) > CHAR_LIMIT:
        raise SystemExit(f"script is {len(text)} chars; {model} takes {CHAR_LIMIT}. Split it.")
    if re.search(r"<break|<phoneme|<speak", text):
        raise SystemExit("SSML found; eleven_v4 ignores it. Use [short pause], ellipses or line breaks.")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("vo.raw.mp3", "words.raw.json"):
        (out / stale).unlink(missing_ok=True)

    res = synthesize(text, voice, model, a.stability, a.similarity, a.seed, key)
    (out / "vo.mp3").write_bytes(base64.b64decode(res["audio_base64"]))
    x = decode(out / "vo.mp3")
    total = len(x) / SR

    source = None
    words = None
    if a.align in ("auto", "eleven") and res.get("alignment"):
        words = words_from_eleven(res["alignment"], spoken)
        source = "eleven"
        lost = sum(w["start"] is None for w in words)
        if a.align == "auto" and lost > max(1, 0.1 * len(words)):
            words, source = None, None
    if words is None:
        if a.align == "eleven":
            raise SystemExit("API returned no usable alignment and --align eleven forbids the fallback")
        words = words_from_whisper(out / "vo.mp3", spoken)
        source = "whisper"
    words = fill_gaps(words, total)
    snapped = snap_quiet(x, words)

    clean = [{"w": w["w"], "start": round(w["start"], 3), "end": round(w["end"], 3)} for w in words]
    (out / "words.json").write_text(json.dumps(clean, indent=1))
    lines_meta = [{"text": s, "raw": r, "start": None, "end": None} for s, r in zip(spoken, raw)]
    write_lines(out, lines_meta, clean)
    if res.get("alignment"):
        (out / "alignment.json").write_text(json.dumps(
            {"alignment": res["alignment"], "normalized_alignment": res.get("normalized_alignment")}))

    meta = {"voice": voice, "model": model,
            "settings": {"stability": a.stability, "similarity": a.similarity, "seed": a.seed},
            "chars": len(text), "duration": round(total, 3), "align_source": source,
            "snapped_boundaries": snapped, "request_id": res.get("_request_id"),
            "delivery": delivery_stats(clean, a.min_pause)}
    if wants_retime:
        meta["retime"] = retime(out, load_profile(a.retime, overrides), a.min_pause, not a.no_tempo)
    (out / "vo.json").write_text(json.dumps(meta, indent=1))

    final = json.loads((out / "words.json").read_text())
    print(f"{model} {voice} align={source} {meta.get('retime', {}).get('duration', meta['duration'])}s "
          f"{len(final)} words")
    print(json.dumps(meta.get("retime", {}).get("after", meta["delivery"])))
    for ln in json.loads((out / "lines.json").read_text()):
        print(f"{ln['start']:6.2f} -> {ln['end']:6.2f}  {ln['text'][:70]}")


if __name__ == "__main__":
    main()
