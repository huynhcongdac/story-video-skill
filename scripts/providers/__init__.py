"""Image providers. Each exposes generate_many(tasks, on_update) -> (done, failed).

A task is {"key", "prompt", "aspect", "refs": [{"path", "url"}], "out": Path, "job"?: resume id}.
on_update(key, entry) must be called as soon as something is paid for / saved, so the caller can persist it:
  {"pending": jobId}   job created (async providers) — resumed on the next run instead of paying again
  {"path", "url"}      image saved
  None                 job ended without an image — forget it
Pick one with IMAGE_PROVIDER in .env (default: sangtao).
"""
from common import env


def get_provider():
    name = (env("IMAGE_PROVIDER", "sangtao") or "sangtao").lower()
    if name == "sangtao":
        from providers import sangtao as p
    elif name == "openai":
        from providers import openai_images as p
    else:
        raise SystemExit(f"Unknown IMAGE_PROVIDER '{name}'. Use 'sangtao' or 'openai', or add a module in scripts/providers/.")
    return p
