"""The "director": story.json + voice clips → render/timeline.json, render/audio.wav, render/kf/*.jpg

  python scripts/build_timeline.py <project>

- Shots: each narration line is split evenly across its shots (aim for a new visual every 3–5 s).
- Captions: word by word, ≤4 words on screen, keywords (character names, clue words) highlighted.
- Sensitive words are masked on screen only (chết → ch*t …) so platforms don't throttle reach;
  the voice is unchanged. Edit CENSOR below for your language.
- Audio: synthesized dark ambient bed + sound effects + voice, music ducks under the voice, -14 LUFS.
"""
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from common import ffmpeg, project_paths, read_json, write_json  # noqa: E402

FPS, SR, GAP = 30, 48000, 0.32
CENSOR = [("đầu độc", "đầu đ*c"), ("tự tử", "t* t*"), ("cờ bạc", "c* b*c"), ("chết", "ch*t"), ("giết", "gi*t"),
          ("xác", "x*c"), ("máu", "m*u"), ("độc", "đ*c"), ("đâm", "đ*m"), ("súng", "s*ng"),
          ("kill", "k*ll"), ("dead", "d*ad"), ("murder", "m*rder"), ("blood", "bl**d"), ("suicide", "s*icide")]
KEYWORDS = r"độc|manh|mối|hung|thủ|chết|clue|killer"


def censor(s):
    for a, b in CENSOR:
        s = re.sub(a, lambda m: b.capitalize() if m.group()[0].isupper() else b, s, flags=re.I)
    return s


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    P = project_paths(sys.argv[1])
    S = read_json(P["story"]); LINES = S["lines"]
    voice = read_json(P["audio"] / "manifest.json") or sys.exit("No audio yet — run scripts/tts.py first.")
    assets = read_json(P["assets"] / "manifest.json") or sys.exit("No images yet — run scripts/gen_assets.py first.")
    f = lambda s: int(round(s * FPS))

    # voice clips + per-character timing (real from ElevenLabs, estimated for Vbee)
    clips = []
    for i, l in enumerate(LINES, 1):
        m = voice.get(f"L{i:02d}") or sys.exit(f"Missing voice for line {i} — run scripts/tts.py.")
        if m.get("align"):
            a = m["align"]; clips.append({"file": m["file"], "dur": m["duration"], "chars": a["chars"], "st": a["st"], "en": a["en"]})
        else:
            t = l["t"]; d = m["duration"]
            w = [6 if ch in ".?!" else 3 if ch in ",:;" else 1 for ch in t]
            tot = sum(w); a0, a1 = 0.10, max(0.3, d - 0.20); acc = 0; st, en = [], []
            for wi in w:
                st.append(a0 + (a1 - a0) * acc / tot); acc += wi; en.append(a0 + (a1 - a0) * acc / tot)
            clips.append({"file": m["file"], "dur": d, "chars": list(t), "st": st, "en": en})

    # timing: lines in order, short gap; "pauseBefore"/"pauseAfter" seconds; "countdown": n adds n s after the line
    t = 0.5; L = []
    for l, c in zip(LINES, clips):
        t += l.get("pauseBefore", 0)
        L.append({"start": t, "dur": c["dur"]})
        t += c["dur"] + GAP + l.get("pauseAfter", 0) + (l["countdown"] + 0.3 if l.get("countdown") else 0)
    TOTAL = t + 2.2

    shots = []
    for i, (l, x) in enumerate(zip(LINES, L)):
        end = L[i + 1]["start"] if i + 1 < len(L) else TOTAL
        n = len(l["shots"]); seg = (end - x["start"]) / n
        for j, (img, fx) in enumerate(l["shots"]):
            s0 = 0.0 if i == 0 and j == 0 else x["start"] + j * seg
            s1 = x["start"] + (j + 1) * seg
            kind = fx.split(":", 1)[0]
            shot = {"from": f(s0), "dur": max(1, f(s1) - f(s0)), "img": f"kf/{img}.jpg", "fx": kind}
            if kind == "suspect":                       # suspect:<n>:<NAME>:<role>   (split limited: text may contain ":")
                _, num, title, sub = fx.split(":", 3); shot["card"] = {"n": num, "title": censor(title), "sub": censor(sub)}
            elif kind == "clue":                        # clue:<n>:<text>
                _, num, title = fx.split(":", 2); shot["card"] = {"n": num, "title": censor(title), "sub": ""}
            if kind == "question" and l.get("countdown"):
                shot["cd"] = {"start": f(x["start"] + x["dur"] + 0.15), "n": l["countdown"]}
            shots.append(shot)

    names = sorted({c["name"].split()[-1] for c in S["characters"].values()})
    key_cs = re.compile(r"^(" + "|".join(map(re.escape, names)) + r")$")           # names: case-sensitive
    key_ci = re.compile(r"^(" + (S.get("keywords") or KEYWORDS) + r")$", re.I)
    capt = []
    for l, c, x in zip(LINES, clips, L):
        s = "".join(c["chars"]); words = []
        for m in re.finditer(r"\S+", s):
            a, b = m.start(), m.end() - 1; raw = m.group().strip(".,:?!\"'")
            words.append({"w": censor(m.group()), "from": f(x["start"] + c["st"][a]), "to": f(x["start"] + c["en"][b]),
                          "hl": bool(key_cs.match(raw) or key_ci.match(raw))})
        chunk = []
        for k, w in enumerate(words):
            chunk.append(w)
            if len(chunk) >= 4 or re.search(r"[.,:?!]$", w["w"]) or k == len(words) - 1:
                capt.append({"from": chunk[0]["from"], "words": chunk}); chunk = []
    for k, cp in enumerate(capt):
        nxt = capt[k + 1]["from"] if k + 1 < len(capt) else cp["words"][-1]["to"] + 12
        cp["to"] = min(nxt, cp["words"][-1]["to"] + 10)

    # scene images → 1080x1920 jpg (center-crop to 9:16)
    kfdir = P["render"] / "kf"; kfdir.mkdir(exist_ok=True)
    for key in {sh["img"][3:-4] for sh in shots}:
        src = Path(assets.get(key, {}).get("path") or P["assets"] / f"{key}.png")
        if not src.exists(): sys.exit(f"Missing image {key} — run gen_assets.py keyframes.")
        dst = kfdir / f"{key}.jpg"
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            im = Image.open(src).convert("RGB"); w, h = im.size; tw = int(h * 9 / 16)
            if w > tw: im = im.crop(((w - tw) // 2, 0, (w - tw) // 2 + tw, h))
            im.resize((1080, 1920), Image.LANCZOS).save(dst, quality=90)

    write_json(P["render"] / "timeline.json", {"fps": FPS, "durationInFrames": f(TOTAL), "title": S["title"],
               "series": S.get("series", ""), "episode": S.get("episode", 1), "labels": S.get("labels", {}),
               "shots": shots, "captions": capt})
    mix_audio(P, LINES, L, clips, shots, TOTAL)
    print(f"{TOTAL:.1f}s · {len(shots)} shots · {len(capt)} caption chunks")


def mix_audio(P, LINES, L, clips, shots, TOTAL):
    N = int(SR * TOTAL); rng = np.random.default_rng(3)
    at = lambda s: int(s * SR)

    def add(buf, sig, s, g=1.0):
        a = at(s)
        if a >= N or a < 0: return
        e = min(N, a + len(sig)); buf[a:e] += sig[:e - a] * g

    def env(n, a, r):
        e = np.ones(n); ka, kr = min(int(a * SR), n // 2), min(int(r * SR), n // 2)
        if ka: e[:ka] = np.linspace(0, 1, ka)
        if kr: e[-kr:] *= np.linspace(1, 0, kr)
        return e

    def lp(x, k):            # moving average via cumsum: O(n) (np.convolve is far too slow on minutes of audio)
        c = np.cumsum(np.concatenate([np.zeros(k), x])); return np.roll((c[k:] - c[:-k]) / k, -(k // 2))

    note = lambda m: 440 * 2 ** ((m - 69) / 12)
    tt = np.arange(N) / SR
    music = 0.5 * np.sin(2 * np.pi * note(38) * tt) + 0.3 * np.sin(2 * np.pi * note(45) * tt + 1)
    prog = [[50, 53, 57], [46, 50, 53], [48, 51, 55], [45, 48, 52]]; s = 0.0; k = 0
    while s < TOTAL:
        n = min(int(9.5 * SR), N - at(s)); x = np.arange(n) / SR
        add(music, sum(np.sin(2 * np.pi * note(m) * x) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.15 * x)) for m in prog[k % 4]) * env(n, 1.5, 1.5) * 0.35, s)
        s += 8.0; k += 1
    music += lp(rng.standard_normal(N), 400) * 2.0
    music /= np.max(np.abs(music)); music *= env(N, 1.0, 2.5)

    sfx = np.zeros(N)
    def boom(g):
        n = int(1.4 * SR); x = np.arange(n) / SR
        return np.sin(2 * np.pi * np.cumsum(70 * np.exp(-x * 3) + 32) / SR) * np.exp(-x * 2.6) * g
    def hit(g):
        n = int(0.5 * SR); x = np.arange(n) / SR
        return (np.sin(2 * np.pi * np.cumsum(120 * np.exp(-x * 9) + 45) / SR) * np.exp(-x * 8) + rng.standard_normal(n) * np.exp(-x * 30) * 0.4) * g
    def bell(g):
        n = int(2.5 * SR); x = np.arange(n) / SR
        return sum(a * np.sin(2 * np.pi * fq * x) for fq, a in ((220, 1), (440.5, .5), (659, .3), (987, .15))) * np.exp(-x * 1.6) * g
    def click(g, d=0.03):
        n = int(d * SR); return rng.standard_normal(n) * np.exp(-np.arange(n) / (0.004 * SR)) * g
    def knock(g):
        n = int(0.18 * SR); x = np.arange(n) / SR
        return (np.sin(2 * np.pi * 180 * x) * np.exp(-x * 40) + lp(rng.standard_normal(n), 6) * np.exp(-x * 60)) * g
    def whoosh(g):
        n = int(0.35 * SR); x = np.arange(n) / SR
        return lp(rng.standard_normal(n), 30) * np.sin(np.pi * x / x[-1]) ** 2 * g * 3

    for l, x in zip(LINES, L):
        s0, d = x["start"], x["dur"]
        for name in l.get("sfx", []):
            if name == "chime":
                for r in range(3): add(sfx, bell(0.45), s0 + 0.05 + r * 1.1)
            elif name == "thunder":
                n = int(3 * SR); xx = np.arange(n) / SR
                add(sfx, lp(rng.standard_normal(n), 120) * np.exp(-xx * 1.3) * (1 - np.exp(-xx * 30)) * 3, s0 - 0.2)
            elif name == "hit": add(sfx, hit(0.55), s0 + 0.05)
            elif name == "boom": add(sfx, boom(0.8), s0 - 0.05); add(sfx, hit(0.4), s0 - 0.05)
            elif name == "lock": add(sfx, click(0.5, .04), s0 + d * .45); add(sfx, click(0.4), s0 + d * .45 + .12)
            elif name == "knock":
                for r in range(3): add(sfx, knock(0.7), s0 + d * .5 + r * .28)
            elif name == "crash":
                add(sfx, hit(0.9), s0 + .1); n = int(.6 * SR); add(sfx, lp(rng.standard_normal(n), 3) * np.exp(-np.arange(n) / (.12 * SR)) * .8, s0 + .1)
            elif name == "siren":
                n = int(2.4 * SR); xx = np.arange(n) / SR
                add(sfx, np.sin(2 * np.pi * np.cumsum(np.where((xx * 1.6) % 1 < .5, 660, 880)) / SR) * env(n, .3, .6) * .12, s0 - 0.4)
            elif name == "tick":
                for r in range(10): add(sfx, click(0.35 if r % 2 == 0 else 0.25, .02), s0 + r * .5)
            elif name == "riser":
                n = int(d * .8 * SR); xx = np.arange(n) / SR; dd = max(xx[-1], .1)
                add(sfx, lp(rng.standard_normal(n), 8) * (xx / dd) ** 2 * .5 + np.sin(2 * np.pi * np.cumsum(200 + 900 * (xx / dd) ** 2) / SR) * (xx / dd) ** 2 * .08, s0 + d * .2)
            elif name == "scream":
                n = int(1.3 * SR); xx = np.arange(n) / SR
                tone = np.sin(2 * np.pi * np.cumsum(1100 - 500 * xx / 1.3 + 40 * np.sin(2 * np.pi * 7 * xx)) / SR)
                add(sfx, (tone * .6 + (rng.standard_normal(n) - lp(rng.standard_normal(n), 6)) * .5) * env(n, .04, .7) * .35, s0 + .05)
            elif name == "rain":
                n = int((d + 1.5) * SR); add(sfx, (rng.standard_normal(n) - lp(rng.standard_normal(n), 3)) * env(n, .8, 1) * .06, s0 - .3)
            elif name == "shimmer":
                n = int(1.4 * SR); xx = np.arange(n) / SR
                add(sfx, sum(np.sin(2 * np.pi * fq * xx) for fq in (1318.5, 1760, 2637)) * np.exp(-xx * 3) * env(n, .02, .3) * .06, s0 + .2)
            elif name == "click":
                add(sfx, click(0.6, .025), s0 + d * .6); add(sfx, knock(0.25), s0 + d * .6 + .02)
        if l.get("countdown"):               # tick each second + heartbeat getting louder + whoosh into the reveal
            c0 = s0 + d + 0.15; n = l["countdown"]
            for k in range(n):
                add(sfx, click(0.55), c0 + k); add(sfx, knock(0.35), c0 + k)
                g = 0.35 + 0.2 * k
                add(sfx, boom(g * .5)[: int(.35 * SR)], c0 + k + .45); add(sfx, boom(g * .35)[: int(.3 * SR)], c0 + k + .68)
            add(sfx, whoosh(0.35), c0 + n - 0.25); add(sfx, hit(0.6), c0 + n + 0.05)
    for sh in shots:
        if sh["fx"] in ("shock", "punch", "glitch", "flashshock", "reveal"): add(sfx, whoosh(0.15), sh["from"] / FPS - 0.15)

    vo = np.zeros(N)
    for c, x in zip(clips, L):
        raw = subprocess.run([ffmpeg(), "-v", "error", "-i", c["file"], "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True).stdout
        add(vo, np.frombuffer(raw, dtype=np.float32).astype(np.float64), x["start"])
    duck = np.clip(lp((np.abs(vo) > 0.01).astype(float), int(0.3 * SR)) * 4, 0, 1)
    out = music * 0.16 * (1 - 0.5 * duck) + sfx * (1 - 0.3 * duck) + vo
    out /= max(1.0, np.max(np.abs(out)) / 0.95)
    raw = P["render"] / "audio_raw.wav"
    with wave.open(str(raw), "wb") as wv:
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(SR); wv.writeframes((out * 32767).astype(np.int16).tobytes())
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), "-ac", "2",
                    str(P["render"] / "audio.wav")], check=True)


if __name__ == "__main__":
    main()
