"""OpenAI Images API (alternative provider).

Uses /v1/images/edits when there are reference images (sent as files), else /v1/images/generations.
Set OPENAI_API_KEY; model via OPENAI_IMAGE_MODEL (default gpt-image-1).
Billed per image; accepts fewer reference images per call (OPENAI_MAX_REFS, default 10).
"""
import base64
import json
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import env

MODEL = env("OPENAI_IMAGE_MODEL", "gpt-image-1")
SIZES = {"1:1": "1024x1024", "9:16": "1024x1536", "16:9": "1536x1024", "4:3": "1536x1024", "3:4": "1024x1536"}
MAX_REFS = int(env("OPENAI_MAX_REFS", "10"))


def _multipart(fields, files):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, path in files:
        data = open(path, "rb").read()
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="ref.png"\r\n'
                     f"Content-Type: image/png\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _one(task):
    key = env("OPENAI_API_KEY", required=True)
    size = SIZES.get(task["aspect"], "1024x1024")
    refs = [r["path"] for r in task.get("refs", []) if r.get("path")][:MAX_REFS]
    for attempt in range(5):
        try:
            if refs:
                body, ctype = _multipart({"model": MODEL, "prompt": task["prompt"], "size": size},
                                         [("image[]", p) for p in refs])
                req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=body, method="POST",
                                             headers={"Authorization": f"Bearer {key}", "Content-Type": ctype})
            else:
                req = urllib.request.Request("https://api.openai.com/v1/images/generations", method="POST",
                                             data=json.dumps({"model": MODEL, "prompt": task["prompt"], "size": size}).encode(),
                                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                b64 = json.loads(r.read())["data"][0]["b64_json"]
            task["out"].write_bytes(base64.b64decode(b64))
            print(f"  done {task['key']}", flush=True)
            return task["key"], {"path": str(task["out"]), "url": None}, None
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(20 * (attempt + 1)); continue
            return task["key"], None, f"HTTP {e.code} {e.read()[:200].decode(errors='replace')}"
    return task["key"], None, "too many retries"


def generate_many(tasks, on_update=lambda key, entry: None):
    """Synchronous API: each image is saved and reported via on_update the moment it finishes."""
    done, failed = {}, {}
    with ThreadPoolExecutor(max_workers=int(env("OPENAI_CONCURRENCY", "4"))) as ex:
        for fut in as_completed([ex.submit(_one, t) for t in tasks]):
            key, ok, err = fut.result()
            if ok:
                done[key] = ok; on_update(key, ok)
            else:
                failed[key] = err; print(f"  FAILED {key}: {err}", flush=True)
    return done, failed
