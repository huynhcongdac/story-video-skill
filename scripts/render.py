"""Render the video with Remotion.

  python scripts/render.py <project> [--still 1200 2400 …]

Copies render/timeline.json, render/kf and render/audio.wav into the Remotion app, bundles once,
then renders <project>/out/<project-name>.mp4 (or a few still frames for checking).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import SKILL_DIR, ffmpeg, project_paths  # noqa: E402

APP = SKILL_DIR / "remotion"
NPX = "npx.cmd" if os.name == "nt" else "npx"
NPM = "npm.cmd" if os.name == "nt" else "npm"


def run(cmd):
    print("$", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, cwd=APP, check=True)


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    P = project_paths(sys.argv[1])
    for need in ("timeline.json", "audio.wav", "kf"):
        if not (P["render"] / need).exists(): sys.exit(f"render/{need} missing — run scripts/build_timeline.py first.")
    free_gb = shutil.disk_usage(P["out"]).free / 2 ** 30
    if free_gb < 3:
        print(f"WARNING: only {free_gb:.1f} GB free. Rendering needs a few GB of temp space; "
              "a full disk shows up as a confusing browser error ('spawn EFTYPE').", flush=True)
    if not (APP / "node_modules").exists():
        run([NPM, "install", "--no-audit", "--no-fund"])
    # Make sure Remotion's headless browser is fully downloaded/extracted (an interrupted
    # first download leaves a broken browser that fails with 'spawn EFTYPE').
    run([NPX, "remotion", "browser", "ensure"])
    shutil.copy(P["render"] / "timeline.json", APP / "src" / "timeline.json")
    pub = APP / "public"
    if pub.exists(): shutil.rmtree(pub)
    shutil.copytree(P["render"] / "kf", pub / "kf")
    shutil.copy(P["render"] / "audio.wav", pub / "audio.wav")
    run([NPX, "remotion", "bundle", "src/index.ts", "--out-dir", "build", "--log=error"])

    if "--still" in sys.argv:
        for fr in sys.argv[sys.argv.index("--still") + 1:]:
            out = P["out"] / f"still_{fr}.jpg"
            run([NPX, "remotion", "still", "build", "Story", str(out), f"--frame={fr}", "--log=error"])
        return
    raw = P["out"] / "render_raw.mp4"
    conc = max(2, (os.cpu_count() or 4) // 2)
    run([NPX, "remotion", "render", "build", "Story", str(raw), f"--concurrency={conc}", "--log=error"])
    final = P["out"] / f"{P['root'].name}.mp4"
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-i", str(raw), "-c:v", "libx264", "-crf", "23", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)], check=True)
    raw.unlink(missing_ok=True)
    print("video:", final)


if __name__ == "__main__":
    main()
