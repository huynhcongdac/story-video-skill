"""sangtao.ai image API (default provider).

Docs: https://sangtao.ai/vi/api-docs/chatgpt-image
- POST {base}/agents/jobs/create   header X-Api-Key, body {model, prompt, aspectRatio, referenceImages[], idempotencyKey}
- GET  {base}/jobs/{jobId}          -> status "complete" + resultUrl
Up to 20 reference image URLs per job, which is what keeps characters consistent across scenes.
"""
import json
import time
import urllib.error
import urllib.request
import uuid

from common import env

BASE = (env("SANGTAO_API_BASE", "https://sangtao.ai/api/v2") or "").rstrip("/")
MODEL = env("SANGTAO_IMAGE_MODEL", "chatgpt-image-sangtao")
RESOLUTION = env("SANGTAO_RESOLUTION", "")          # "", "1K" or "2K"
TIMEOUT_MIN = env("SANGTAO_TIMEOUT_MIN", "30")      # give up waiting after this many minutes
PRICING = "https://sangtao.ai/vi/imagine?tab=pricing"
FAILED = {"error", "failed", "cancelled", "canceled"}


def _headers():
    return {"X-Api-Key": env("SANGTAO_API_KEY", required=True), "Content-Type": "application/json",
            "User-Agent": "story-video-skill"}


def _call(method, url, body=None, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _create(task):
    refs = [r["url"] for r in task.get("refs", []) if r.get("url")]
    missing = [r for r in task.get("refs", []) if not r.get("url")]
    if missing:
        raise SystemExit(f"{task['key']}: sangtao needs reference images as public URLs. "
                         "Generate the sheets with sangtao too, or host them somewhere public.")
    body = {"model": MODEL, "prompt": task["prompt"], "aspectRatio": task["aspect"], "visibility": "private",
            "idempotencyKey": f"story-{task['key']}-{uuid.uuid4().hex[:8]}"}
    if refs:
        body["referenceImages"] = refs[:20]
    if RESOLUTION:
        body["resolution"] = RESOLUTION
    net_errors = 0
    for _ in range(120):                          # 429 = your queue is full → wait for it to drain
        try:
            return _call("POST", f"{BASE}/agents/jobs/create", body)["data"]["jobId"]
        except urllib.error.HTTPError as e:       # (HTTPError is a URLError subclass — keep this branch first)
            if e.code == 429:
                print(f"  {task['key']}: queue full, waiting 30s…", flush=True); time.sleep(30); continue
            msg = e.read()[:300].decode(errors="replace")
            if e.code == 402:
                raise SystemExit("Not enough credit on your sangtao.ai account (402). API calls need a plan or credit: " + PRICING)
            if e.code in (401, 403):
                raise SystemExit(f"API key rejected (HTTP {e.code}). Check SANGTAO_API_KEY in .env.")
            raise SystemExit(f"{task['key']}: HTTP {e.code} {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:   # network hiccup → retry a few times
            net_errors += 1
            if net_errors > 5:
                raise SystemExit(f"{task['key']}: cannot reach {BASE} ({e}). Check your connection and re-run.")
            print(f"  {task['key']}: network error, retrying in {10 * net_errors}s…", flush=True); time.sleep(10 * net_errors)
    raise SystemExit(f"{task['key']}: queue stayed full for too long")


def _download(url, out):
    """True on success. Retries a few times; a failed download never loses the job (it is still recorded as pending)."""
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            tmp = out.with_suffix(".part"); tmp.write_bytes(data); tmp.replace(out)
            return True
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(5 * (attempt + 1))
    return False


def generate_many(tasks, on_update=lambda key, entry: None):
    """Submit every task first (sangtao runs them in parallel), then poll until all finish.

    Billing safety: every job id is reported through on_update(key, {"pending": jobId}) the moment it is
    created, and on_update(key, {"path", "url"}) the moment its image is saved — so an interrupted run
    (Ctrl+C, network drop, timeout) never pays twice. A task carrying "job" resumes that job instead of
    creating a new one.
    """
    jobs = {}
    for t in tasks:
        if t.get("job"):
            jobs[t["key"]] = t["job"]
            print(f"  resuming {t['key']} (job already paid for)", flush=True)
            continue
        jobs[t["key"]] = _create(t)
        on_update(t["key"], {"pending": jobs[t["key"]]})
        print(f"  submitted {t['key']}", flush=True)
    done, failed = {}, {}
    pending = dict(jobs)
    deadline = time.time() + 60 * float(TIMEOUT_MIN)
    while pending:
        if time.time() > deadline:
            for key in pending: failed[key] = f"no result after {TIMEOUT_MIN} min"
            print(f"  stopped waiting on {len(pending)} image(s). They keep running on the server — re-run the same "
                  "command later to collect them (no new jobs are created for them).", flush=True)
            break
        time.sleep(15)
        for key, jid in list(pending.items()):
            try:
                d = _call("GET", f"{BASE}/jobs/{jid}")["data"]
            except urllib.error.HTTPError as e:   # 401/403/404 will not fix themselves — stop instead of polling forever
                if e.code in (401, 403):
                    raise SystemExit(f"API key rejected while checking results (HTTP {e.code}). Check SANGTAO_API_KEY.")
                if e.code == 404:
                    failed[key] = f"job {jid} not found"; del pending[key]
                    on_update(key, None)                   # forget the dead job so a re-run creates a fresh one
                    continue
                continue                           # 5xx: transient, try again next round
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                continue                           # network hiccup: try again next round
            st = (d.get("status") or "").lower()
            if st == "complete":
                url = d.get("resultUrl") or (d.get("resultImages") or [None])[0]
                task = next(t for t in tasks if t["key"] == key)
                del pending[key]
                if url and _download(url, task["out"]):
                    done[key] = {"path": str(task["out"]), "url": url}
                    on_update(key, done[key]); print(f"  done {key}", flush=True)
                else:                                      # keep {"pending": jobId} → a re-run downloads it again, no new charge
                    failed[key] = "image ready but download failed"; print(f"  DOWNLOAD FAILED {key} (re-run to fetch it)", flush=True)
            elif st in FAILED:
                failed[key] = d.get("error") or st
                del pending[key]; print(f"  FAILED {key}: {failed[key]}", flush=True)
                on_update(key, None)                       # the job ended without an image: a re-run may create a new one
        if pending:
            print(f"  waiting for {len(pending)} image(s)…", flush=True)
    return done, failed
