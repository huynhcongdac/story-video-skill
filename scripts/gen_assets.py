"""Generate reference sheets and scene images for a story project.

  python scripts/gen_assets.py <project> sheets            # character / location / prop sheets
  python scripts/gen_assets.py <project> keyframes         # every scene image (uses the sheets as references)
  python scripts/gen_assets.py <project> keyframes k_cup   # (re)generate only some scenes
  add --force to regenerate images that already exist

Results are recorded in <project>/assets/manifest.json, so re-running only creates what is missing.
"""
import sys
from pathlib import Path

from common import project_paths, read_json, write_json
from providers import get_provider

# ── Prompt templates ────────────────────────────────────────────────────────────
# Multi-panel sheets give the model every angle of a character / place / object, so a scene shot from
# behind or from above still matches. Sheets are landscape on purpose, whatever the video ratio:
# squeezing four panels into 9:16 leaves too little detail per panel.

def character_prompt(style, c):
    return (f"Style: {style}\n"
            f"Character design sheet: Name: {c['name']}. {c['appearance']}\n"
            "Format: 16:9 landscape, four-panel layout. Left panel (largest, ~40% width): "
            "chest-up close-up portrait, high detail, clearly showing face, hairstyle, "
            "accessories and upper outfit. Right side (3 panels, ~20% width each): three "
            "full-body views — front, three-quarter, and back. Full-body panels use a static "
            "A-pose; show the complete figure head to toe with shoes fully visible and uncropped.\n"
            "BACKGROUND: pure white (#FFFFFF), completely empty, no background shadows. "
            "Do NOT include any environmental context — no scenery, no furniture, no floor pattern. "
            "Ignore any setting the clothing might suggest.\n"
            "The character must look identical across all four panels — same face, hairstyle, "
            "outfit and accessories. No action pose. No handheld objects unless permanently "
            "part of the character's identity.\n"
            "NO text, NO labels, NO captions, NO logos, NO watermarks, NO arrows, NO annotations.")


def location_prompt(style, a):
    return (f"Style: {style}\n"
            f"Location concept design sheet: Name: {a['name']}. {a['description']}.\n"
            "Format: 16:9 landscape, multi-angle layout. At least 4 panels showing the "
            "SAME location from different camera angles: wide establishing shot, reverse "
            "angle, overhead/bird-eye view, and a low-angle or detail close-up. Panels may "
            "vary lighting or time of day. No written descriptions, labels or floor plans.\n"
            "Rules: No characters or people — environment only. The location must look "
            "consistent and recognizable across all panels, with the same buildings, props "
            "and layout. Do not include any text, letters, numbers, annotations, captions, "
            "dimension lines, arrows, labels, legends or watermarks.")


def prop_prompt(style, a):
    return (f"Style: {style}\n"
            f"Prop design sheet: Name: {a['name']}. {a['description']}.\n"
            "Format: 4:3 landscape. Show only four views of the same prop: one main view "
            "that best presents its visual features, plus front, side and back views. The "
            "main view must be the largest and clearest. Pure white background.\n"
            "Rules: Do not include any text, letters, numbers, annotations, captions, "
            "material swatches, dimension lines, arrows, close-up detail panels or exploded "
            "views. The prop must remain completely consistent across all views. No "
            "environmental elements, no characters, no watermark.")


def keyframe_prompt(style, story, k):
    p = k["p"]
    # Name + short visual tag ("Bà Sáu (the elderly housekeeper in the white apron)"): a bare foreign
    # name tends to get drawn as text, and the tag ties the name to the right reference sheet.
    for ck in k.get("chars", []):
        c = story["characters"][ck]
        if c.get("tag"):
            p = p.replace(c["name"], f"{c['name']} ({c['tag']})", 1)
    return (p + f" Art style: {style}. Render the entire image in this style consistently."
            "\nTEXT POLICY — STRICT. Render text ONLY when this prompt names the exact wording in quotes. "
            "Otherwise the image must contain NO visible text: no caption, subtitle, title, speech bubble, "
            "UI text, watermark, logo or decorative lettering. A book, sign, screen or label with no specified "
            "wording must be blank or show non-readable markings. NEVER generate random letters or gibberish."
            "\nCOMPOSITION. Output ONE single continuous frame: one camera, one moment in time, no dividing "
            "lines, borders, black bars or stacked variations, unless the prompt explicitly asks for a split screen.\n"
            "The reference images may be character or location sheets showing several angles in a grid — they "
            "are reference material for identity and appearance only. Do NOT copy their panel layout.")


# ── main ────────────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    if len(args) < 2 or args[1] not in ("sheets", "keyframes"):
        sys.exit(__doc__)
    P = project_paths(args[0]); stage = args[1]; only = set(args[2:])
    story = read_json(P["story"]); style = story["visualStyle"]
    mpath = P["assets"] / "manifest.json"; manifest = read_json(mpath, {})
    tasks = []

    def save():                       # write via a temp file so a crash mid-write never corrupts the manifest
        tmp = mpath.with_suffix(".tmp"); write_json(tmp, manifest); tmp.replace(mpath)

    def on_update(key, entry):        # called by the provider the moment a job is paid for / an image is saved
        if entry is None: manifest.pop(key, None)
        else: manifest[key] = entry
        save()

    def has_image(key):
        e = manifest.get(key) or {}
        if e.get("path"):
            return Path(e["path"]).exists()
        return bool(e.get("url"))     # URL-only entry = a sheet reused from an earlier episode

    def want(key):
        if only and key not in only: return False
        return force or not has_image(key)

    def resume_job(key):              # a job created by an earlier run that never got collected: wait for it, don't pay again
        return None if force else (manifest.get(key) or {}).get("pending")

    if stage == "sheets":
        for k, c in story["characters"].items():
            key = f"ch_{k}"
            if c.get("sheet"):        # series: reuse a sheet from an earlier episode (local path or URL)
                src = c["sheet"]
                manifest[key] = {"path": src if not src.startswith("http") else "", "url": src if src.startswith("http") else None}
                continue
            if want(key): tasks.append({"key": key, "prompt": character_prompt(style, c), "aspect": "16:9"})
        for k, a in story.get("locations", {}).items():
            if want(f"lo_{k}"): tasks.append({"key": f"lo_{k}", "prompt": location_prompt(style, a), "aspect": "16:9"})
        for k, a in story.get("props", {}).items():
            if want(f"pr_{k}"): tasks.append({"key": f"pr_{k}", "prompt": prop_prompt(style, a), "aspect": "4:3"})
    else:
        aspect = story.get("aspectRatio", "9:16")
        for key, k in story["keyframes"].items():
            if not want(key): continue
            refs = []
            for kind, ids in (("ch", k.get("chars", [])), ("lo", k.get("loc", [])), ("pr", k.get("props", []))):
                for i in ids:
                    if not has_image(f"{kind}_{i}"):
                        sys.exit(f"{key}: sheet {kind}_{i} is missing or still generating — run the 'sheets' stage (again) first.")
                    refs.append(manifest[f"{kind}_{i}"])
            tasks.append({"key": key, "prompt": keyframe_prompt(style, story, k), "aspect": aspect, "refs": refs})

    for t in tasks:
        t["out"] = P["assets"] / f"{t['key']}.png"
        t["job"] = resume_job(t["key"])
    save()
    resumed = sum(1 for t in tasks if t["job"])
    print(f"{len(tasks)} image(s) to generate" + (f" ({resumed} resumed from an earlier run, no new charge)" if resumed else ""), flush=True)
    if not tasks:
        return
    try:
        done, failed = get_provider().generate_many(tasks, on_update)
    except KeyboardInterrupt:
        save()
        sys.exit("\nStopped. Finished images and jobs already paid for are saved — re-run the same command to continue.")
    save()
    if failed:
        print(f"\n{len(failed)} not finished:", *[f"{k}: {v}" for k, v in failed.items()], sep="\n  ")
        print("Re-run the same command: unfinished jobs are resumed (no new charge); jobs that ended without an image are retried.")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
