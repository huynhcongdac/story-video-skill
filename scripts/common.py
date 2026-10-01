"""Shared helpers: config loading, paths, ffmpeg, JSON IO."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def load_env():
    """Load KEY=VALUE pairs from .env (skill dir, then current dir). Real env vars win."""
    for p in (SKILL_DIR / ".env", Path.cwd() / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


def env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        sys.exit(f"Missing config: {name}. Add it to .env (see .env.example).")
    return v


def ffmpeg():
    exe = env("FFMPEG_PATH") or shutil.which("ffmpeg")
    if not exe:
        sys.exit("ffmpeg not found. Install it or set FFMPEG_PATH in .env.")
    return exe


def audio_duration(path):
    """Duration in seconds, decoded with ffmpeg (no ffprobe needed)."""
    raw = subprocess.run([ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return len(raw) / 4 / 16000


def read_json(path, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def project_paths(project_dir):
    root = Path(project_dir).resolve()
    if not (root / "story.json").exists():
        sys.exit(f"{root / 'story.json'} not found.")
    d = {"root": root, "story": root / "story.json", "assets": root / "assets", "audio": root / "audio",
         "render": root / "render", "out": root / "out"}
    for k in ("assets", "audio", "render", "out"):
        d[k].mkdir(parents=True, exist_ok=True)
    return d
