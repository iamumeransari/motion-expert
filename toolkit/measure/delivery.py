"""Delivery: word timings, pace, pauses, emphasis and VO-to-music loudness.

Works on a video or on an audio file alone (wav, mp3, m4a ...), so it measures the
source's voiceover and our own TTS the same way.

Words come from whisper-cli (medium.en by default) with one word per segment
(-ml 1 -sow). Whisper's word spans run edge to edge and sometimes sit inside a
silence, so timing is rebuilt from the audio: short-time energy in the 200-4000 Hz
speech band is computed on 10 ms hops, a threshold is set at 35 % of the way from the
quiet floor (10th percentile) to the speech level (75th percentile), never lower than
28 dB under the speech level (so clean TTS tails do not count), and the audio is
split into speech islands wherever it stays below the threshold for 0.25 s or more.
Each whisper word goes to the island its midpoint falls in or sits nearest, islands
that receive no words (music hits, breaths) are dropped, and the words of each island
are linearly rescaled to fill it, with the island clamped to 0.3 s beyond whisper's own
estimate so a music bed touching the voice cannot stretch the words. Pauses are the gaps between consecutive islands.

wpm counts words over the span from the first word's start to the last word's end.
Pauses are gaps of at least 0.25 s between words; median and p90 are over those
pauses and per_min is their count per minute of that span. Emphasis words come from
RMS peaks: the speech-band envelope smoothed to syllable scale (150 ms) is compared
with the running mean energy of voiced audio over +-1.5 s, peaks at least 4 dB above
it and 0.5 s apart are kept, and each is attached to the word whose span holds it
(word attribution inherits the island alignment, so it can be off by one short word). vo_lufs is the loudness of the speech
spans, music_lufs the loudness of the gaps inside
the speech span (the bed under the voice), falling back to the head and tail when
the gaps add up to under a second, and null when that is silent; overall_lufs is the
whole file. overall_lufs is ffmpeg ebur128 integrated loudness; vo_lufs and
music_lufs are ungated BS.1770 K-weighted loudness on the LUFS scale, because the
R128 relative gate would report only the loud fragments of a mix of short gaps.

If the audio holds fewer than three recognisable words, delivery is null with a
reason.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import FFMPEG, emit, pct, probe  # noqa: E402

WHISPER = "/opt/homebrew/bin/whisper-cli"
DEFAULT_MODEL = str(Path.home() / ".whisper-models/ggml-medium.en.bin")
SR = 16000
HOP = 0.01
PAUSE_MIN = 0.25
EMPH_DB = 4.0
THR_BELOW_SPEECH_DB = 28.0
ISLAND_SLACK = 0.3
NOISE_WORD = re.compile(r"^[\[\(\*♪].*|^[^\w%$€£]+$")


def decode_mono(path, sr=SR) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def ebur128_lufs(samples: np.ndarray, sr: int, ch: int) -> float | None:
    if samples.size < sr * ch * 0.5:
        return None
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(sr), "-ac", str(ch),
                        "-i", "-", "-af", "ebur128", "-f", "null", "-"],
                       input=samples.astype(np.float32).tobytes(), capture_output=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr.decode(errors="ignore"))
    if not m:
        return None
    v = float(m[-1])
    return None if v <= -69.9 else v


K_SHELF = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
K_HP = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def k_weight(st48: np.ndarray) -> np.ndarray:
    """BS.1770 K-weighting at 48 kHz, applied per channel over the whole signal."""
    from scipy.signal import lfilter
    y = lfilter(*K_SHELF, st48.astype(np.float64), axis=0)
    return lfilter(*K_HP, y, axis=0)


def ungated_lufs(kw: np.ndarray, mask: np.ndarray) -> float | None:
    """Loudness of the masked samples on the LUFS scale, without the R128 gates (the
    relative gate would hide a quiet bed behind the few loud blocks in a gap mix)."""
    if mask.sum() < 4800:
        return None
    ms = float((kw[mask] ** 2).mean(axis=0).sum())
    if ms <= 1e-10:
        return None
    v = -0.691 + 10 * np.log10(ms)
    return None if v < -70 else v


def whisper_words(wav: Path, model: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as td:
        of = Path(td) / "w"
        subprocess.run([WHISPER, "-m", model, "-f", str(wav), "-ml", "1", "-sow", "-oj", "-of", str(of),
                        "-np", "-t", "4", "-l", "en" if model.endswith(".en.bin") else "auto"],
                       capture_output=True, check=True)
        data = json.loads((of.with_suffix(".json")).read_text())
    words = []
    for seg in data.get("transcription", []):
        w = seg["text"].strip()
        if not w or NOISE_WORD.match(w):
            continue
        words.append({"w": w, "t0": seg["offsets"]["from"] / 1000, "t1": seg["offsets"]["to"] / 1000})
    return words


def measure(path: str, model: str = DEFAULT_MODEL) -> tuple[dict | None, str | None]:
    pr = probe(path)
    if not pr["has_audio"]:
        return None, "no audio stream"
    x = decode_mono(path)
    dur = len(x) / SR
    if dur < 0.5 or float(np.abs(x).max(initial=0)) < 1e-4:
        return None, "audio is silent"
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
                        "-c:a", "pcm_s16le", str(wav)], check=True)
        words = whisper_words(wav, model)
    if len(words) < 3:
        return None, f"no speech recognised ({len(words)} words)"

    # speech-band energy on 10 ms hops
    sos = butter(4, [200, 4000], btype="band", fs=SR, output="sos")
    xb = sosfiltfilt(sos, x.astype(np.float64))
    hop = int(SR * HOP)
    nfr = len(xb) // hop
    e = np.sqrt(np.mean(xb[:nfr * hop].reshape(nfr, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(e + 1e-9)
    db = np.convolve(db, np.ones(3) / 3, mode="same")
    fr = lambda t: int(np.clip(round(t / HOP), 0, nfr - 1))  # noqa: E731
    speech_lvl = float(np.percentile(db, 75))
    floor = float(np.percentile(db, 10))
    # 35 % of the way from floor to speech, but never more than 28 dB under the speech
    # level: with digital silence (clean TTS) the floor sits near -120 dB and a purely
    # relative threshold would count reverb tails as speech
    thr = max(floor + 0.35 * (speech_lvl - floor), speech_lvl - THR_BELOW_SPEECH_DB)

    # speech islands: voiced runs split by silences of at least PAUSE_MIN (shorter dips,
    # stop consonants and breaths between words, stay inside an island)
    voiced = db >= thr
    min_sil = int(round(PAUSE_MIN / HOP))
    islands, k = [], 0
    while k < nfr:
        if voiced[k]:
            j = k
            while True:
                while j + 1 < nfr and voiced[j + 1]:
                    j += 1
                nxt = j + 1
                while nxt < nfr and not voiced[nxt] and nxt - j <= min_sil:
                    nxt += 1
                if nxt < nfr and voiced[nxt] and nxt - j <= min_sil:
                    j = nxt
                    continue
                break
            islands.append([k * HOP, (j + 1) * HOP, []])
            k = j + 1
        else:
            k += 1
    if not islands:
        return None, "no voiced audio above the adaptive threshold"
    # each word goes to the island its midpoint is in or nearest to
    for wi, w in enumerate(words):
        mid = (w["t0"] + w["t1"]) / 2
        best = min(range(len(islands)), key=lambda i: (0 if islands[i][0] <= mid <= islands[i][1]
                                                      else min(abs(mid - islands[i][0]), abs(mid - islands[i][1])), i))
        islands[best][2].append(wi)
    # keep word order monotone across islands, then rescale whisper timings in each
    islands = [isl for isl in islands if isl[2]]
    last = -1
    for isl in islands:
        isl[2] = [wi for wi in isl[2] if wi > last] or isl[2]
        last = max(isl[2])
    for isl in islands:
        ws = [words[wi] for wi in isl[2]]
        a0, a1 = ws[0]["t0"], ws[-1]["t1"]
        # music or noise touching the speech can inflate an island; never let it
        # reach more than ISLAND_SLACK past whisper's own estimate of the words
        isl[0] = max(isl[0], min(a0, isl[1]) - ISLAND_SLACK)
        isl[1] = min(isl[1], max(a1, isl[0]) + ISLAND_SLACK)
        sc = (isl[1] - isl[0]) / (a1 - a0) if a1 > a0 else 0.0
        for w in ws:
            w["t0"], w["t1"] = isl[0] + (w["t0"] - a0) * sc, isl[0] + (w["t1"] - a0) * sc
    island_gaps = [islands[i][0] - islands[i - 1][1] for i in range(1, len(islands))]
    pauses = [g for g in island_gaps if g >= PAUSE_MIN]
    span = words[-1]["t1"] - words[0]["t0"]
    minutes = span / 60 if span > 0 else 1e-9

    # emphasis: peaks of the syllable-scale envelope (150 ms) over the running mean
    # energy of voiced audio (+-1.5 s), at least 0.5 s apart, attached to the word
    # whose span holds the peak
    from scipy.ndimage import uniform_filter1d
    from scipy.signal import find_peaks
    e_lin = e ** 2
    env = 10 * np.log10(uniform_filter1d(e_lin, 15) + 1e-12)
    vmask = env >= thr
    num = uniform_filter1d(np.where(vmask, e_lin, 0.0), 301)
    den = uniform_filter1d(vmask.astype(np.float64), 301)
    run = 10 * np.log10(np.maximum(num / np.maximum(den, 1e-6), 1e-12))
    rel = np.where(vmask, env - run, -99.0)
    pk, props = find_peaks(rel, height=EMPH_DB, distance=int(0.5 / HOP))
    for i, w in enumerate(words):
        seg = db[fr(w["t0"]):max(fr(w["t1"]), fr(w["t0"]) + 1)]
        w["level_db"] = float(np.percentile(seg, 90)) - speech_lvl
    emphasis = []
    for p_, h_ in zip(pk, props["peak_heights"]):
        t = p_ * HOP
        if not (words[0]["t0"] <= t <= words[-1]["t1"]):
            continue
        wi = min(range(len(words)), key=lambda i: (0 if words[i]["t0"] <= t <= words[i]["t1"]
                                                  else min(abs(t - words[i]["t0"]), abs(t - words[i]["t1"])), i))
        if emphasis and emphasis[-1]["index"] == wi:
            continue
        emphasis.append({"w": words[wi]["w"], "t": t, "gain_db": float(h_), "index": wi})

    # loudness: speech spans vs everything else, on the original stereo mix
    ch = 2 if pr.get("audio_codec") else 1
    raw = subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", str(ch), "-ar", "48000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    st = np.frombuffer(raw, np.float32).reshape(-1, ch)
    n48 = len(st)
    speech_mask = np.zeros(n48, bool)
    for w in words:
        speech_mask[int(w["t0"] * 48000):int(w["t1"] * 48000)] = True
    # close sub-pause gaps so the VO measure is continuous speech
    for i in range(1, len(words)):
        if words[i]["t0"] - words[i - 1]["t1"] < PAUSE_MIN:
            speech_mask[int(words[i - 1]["t1"] * 48000):int(words[i]["t0"] * 48000)] = True
    pad = int(0.05 * 48000)
    non = ~speech_mask
    if pad:
        from scipy.ndimage import maximum_filter1d
        grown = maximum_filter1d(speech_mask.astype(np.uint8), size=2 * pad + 1) > 0
        non = ~grown
    overall = ebur128_lufs(st.ravel(), 48000, ch)
    kw = k_weight(st)
    vo = ungated_lufs(kw, speech_mask)
    # the bed under the voice: gaps inside the speech span; head and tail (intros,
    # outro stings) only when the gaps are too short to measure
    s0, s1 = int(words[0]["t0"] * 48000), int(words[-1]["t1"] * 48000)
    inner = non.copy()
    inner[:s0] = False
    inner[s1:] = False
    if inner.sum() >= 48000:
        music, music_src = ungated_lufs(kw, inner), "gaps_inside_speech"
    elif non.sum() >= 48000:
        music, music_src = ungated_lufs(kw, non), "all_non_speech"
    else:
        music, music_src = None, "not_enough_non_speech"

    return {
        "words": [{"w": w["w"], "t0": w["t0"], "t1": w["t1"], "level_db": w.get("level_db", 0.0)} for w in words],
        "word_count": len(words),
        "speech_span": [words[0]["t0"], words[-1]["t1"]],
        "wpm": len(words) / minutes,
        "pauses": {"median": pct(pauses, 50) if pauses else 0.0, "p90": pct(pauses, 90) if pauses else 0.0,
                   "per_min": len(pauses) / minutes, "count": len(pauses), "min_s": PAUSE_MIN},
        "emphasis": emphasis,
        "vo_lufs": vo,
        "music_lufs": music,
        "overall_lufs": overall,
        "music_source": music_src,
        "vo_minus_music_db": (vo - music) if (vo is not None and music is not None) else None,
        "model": Path(model).name,
    }, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("media", help="video or audio file")
    ap.add_argument("--out")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    a = ap.parse_args()
    d, reason = measure(a.media, a.model)
    emit({"delivery": d, "reason": reason}, a.out)


if __name__ == "__main__":
    main()
