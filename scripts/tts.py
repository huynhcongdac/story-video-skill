"""Voiceover, one clip per narration line.

  python scripts/tts.py <project>          # provider from TTS_PROVIDER (vbee | elevenlabs)
  add --force to redo lines that already have audio

Writes <project>/audio/L01.mp3 … and <project>/audio/manifest.json.
ElevenLabs also returns per-character timestamps → captions land exactly on each word.
Vbee has no timestamps → word timing is estimated from text length (good enough for captions).
"""
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import audio_duration, env, project_paths, read_json, write_json  # noqa: E402


def http(method, url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method=method,
                                 headers={**headers, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def vbee(text, out):
    """Vbee 'direct' mode returns the audio link in the same response — no callback server needed."""
    body = {"app_id": env("VBEE_APP_ID", required=True), "response_type": "direct", "input_text": text,
            "voice_code": env("VBEE_VOICE", "n_hn_male_ngankechuyen_ytstable_vc"), "audio_type": "mp3",
            "bitrate": 128, "speed_rate": float(env("VBEE_SPEED", "1.1"))}
    for attempt in range(4):
        try:
            r = http("POST", "https://vbee.vn/api/v1/tts", body, {"Authorization": "Bearer " + env("VBEE_TOKEN", required=True)})
            link = (r.get("result") or {}).get("audio_link")
            if not link:
                raise RuntimeError(json.dumps(r, ensure_ascii=False)[:300])
            with urllib.request.urlopen(urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as a:
                out.write_bytes(a.read())
            return None
        except (urllib.error.URLError, RuntimeError) as e:
            if attempt == 3: raise SystemExit(f"Vbee failed: {e}")
            time.sleep(5)


def elevenlabs(text, out):
    voice = env("ELEVENLABS_VOICE_ID", required=True)
    body = {"text": text, "model_id": env("ELEVENLABS_MODEL", "eleven_v3"), "language_code": env("ELEVENLABS_LANGUAGE", "vi"),
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}
    try:
        d = http("POST", f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128",
                 body, {"xi-api-key": env("ELEVENLABS_API_KEY", required=True)}, timeout=300)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ElevenLabs HTTP {e.code}: {e.read()[:300]}")
    out.write_bytes(base64.b64decode(d["audio_base64"]))
    a = d.get("alignment") or d.get("normalized_alignment")
    return {"chars": a["characters"], "st": a["character_start_times_seconds"], "en": a["character_end_times_seconds"]}


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    P = project_paths(sys.argv[1]); force = "--force" in sys.argv
    provider = (env("TTS_PROVIDER", "vbee") or "vbee").lower()
    fn = {"vbee": vbee, "elevenlabs": elevenlabs}.get(provider) or sys.exit(f"Unknown TTS_PROVIDER '{provider}'")
    story = read_json(P["story"]); mpath = P["audio"] / "manifest.json"; manifest = read_json(mpath, {})
    for i, line in enumerate(story["lines"], 1):
        key = f"L{i:02d}"; out = P["audio"] / f"{key}.mp3"
        if not force and key in manifest and manifest[key].get("text") == line["t"] and out.exists():
            continue
        align = fn(line["t"], out)
        manifest[key] = {"file": str(out), "text": line["t"], "duration": round(audio_duration(out), 3),
                         "provider": provider, **({"align": align} if align else {})}
        write_json(mpath, manifest)
        print(f"  {key} {manifest[key]['duration']:.2f}s", flush=True)
    print(f"total voice: {sum(v['duration'] for v in manifest.values()):.1f}s")


if __name__ == "__main__":
    main()
