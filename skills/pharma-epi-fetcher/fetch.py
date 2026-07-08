#!/usr/bin/env python3
"""
fetch.py — deterministic download / dedup / manifest core for pharma-epi-fetcher.

The judgment part (deciding WHICH URL is the current report for each watchlist
source) is done by the skill via WebFetch/WebSearch. This script does only the
deterministic, fail-loud part:

  resolved candidate URLs  ->  download binary  ->  sha256 dedup vs ledger
                           ->  (optional) upload to Box via API
                           ->  update ledger.json + write manifest.json

Stdlib only (urllib, json, hashlib) so it runs anywhere without pip installs.
The watchlist itself is YAML the skill reads; this script consumes the skill's
resolved `--candidates` JSON, so it never needs pyyaml.

Candidates JSON: a list of objects, each:
  {
    "source_id": "gsk",
    "company":   "GSK",
    "period":    "Q1 2026",
    "url":       "https://www.gsk.com/media/2wgpnet2/q1-2026-epidemiology-report.xlsx",
    "expected_format": "xlsx",          # or "pdf"
    "adapter_hint":    "gsk-epidemiology-report"
  }

Exit codes: 0 = all candidates fetched or already-ingested; 1 = at least one
candidate failed (loud, so a scheduled run cannot silently miss a source);
2 = hard config error (bad args / bad candidates file / missing Box token).
"""

import argparse
import datetime
import hashlib
import json
import mimetypes
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

BOX_UPLOAD_URL = "https://upload.box.com/api/2.0/files/content"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def die(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(source_id, period):
    s = f"{source_id}-{period}".lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def ext_for(cand, final_url, content_type):
    fmt = (cand.get("expected_format") or "").lower().lstrip(".")
    if fmt in ("xlsx", "pdf", "csv"):
        return fmt
    # fall back to URL suffix, then content-type
    m = re.search(r"\.(xlsx|pdf|csv)(?:$|\?)", final_url.lower())
    if m:
        return m.group(1)
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    return (guessed or ".bin").lstrip(".")


def download(url, timeout=60):
    """GET a URL, following redirects. On DNS failure for a media.* host, retry
    the www.* host (GSK serves /media/ paths from www.gsk.com; media.gsk.com may
    not resolve in every environment). Returns (bytes, final_url, content_type)."""
    tried = [url]
    if "://media." in url:
        tried.append(url.replace("://media.", "://www.", 1))
    last = None
    for u in tried:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": USER_AGENT})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
                if not data:
                    raise ValueError("empty response body")
                return data, r.geturl(), r.headers.get("Content-Type", "")
        except (urllib.error.URLError, ValueError, OSError) as e:
            last = e
            continue
    raise RuntimeError(f"download failed for {url}: {type(last).__name__}: {last}")


def box_upload(data, filename, folder_id, token, timeout=120):
    """Upload a binary to Box via the content API (multipart/form-data)."""
    boundary = "----pharmaepifetcher7f3a2b"
    attributes = json.dumps({"name": filename, "parent": {"id": str(folder_id)}})
    pre = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="attributes"\r\n\r\n'
        f"{attributes}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    post = f"\r\n--{boundary}--\r\n".encode()
    body = pre + data + post
    req = urllib.request.Request(
        BOX_UPLOAD_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode())
    return resp["entries"][0]["id"]


def main():
    ap = argparse.ArgumentParser(description="Download/dedup/manifest core for pharma-epi-fetcher.")
    ap.add_argument("--candidates", required=True, help="JSON list of resolved report candidates.")
    ap.add_argument("--ledger", required=True, help="JSON dedup ledger (created if missing).")
    ap.add_argument("--inbox", default=os.path.expanduser("~/Documents/Epi Source Inbox"),
                    help="Local staging dir for downloaded binaries.")
    ap.add_argument("--manifest", default=None, help="Where to write this run's manifest.json.")
    ap.add_argument("--project", default="epi-master",
                    help="Project tag recorded on each ledger entry (per-candidate 'project' overrides).")
    ap.add_argument("--box-folder-id", default=None, help="Box folder id to upload binaries into.")
    ap.add_argument("--box-token-env", default="BOX_API_TOKEN",
                    help="Env var holding the Box API token (never pass the token itself).")
    ap.add_argument("--dry-run", action="store_true", help="Resolve + dedup only; no download/upload.")
    args = ap.parse_args()

    if not os.path.isfile(args.candidates):
        die(f"candidates file not found: {args.candidates}")
    try:
        candidates = json.load(open(args.candidates))
    except json.JSONDecodeError as e:
        die(f"candidates file is not valid JSON: {e}")
    if not isinstance(candidates, list) or not candidates:
        die("candidates file must be a non-empty JSON list")

    ledger = {}
    if os.path.isfile(args.ledger):
        try:
            ledger = json.load(open(args.ledger))
        except json.JSONDecodeError as e:
            die(f"ledger is not valid JSON: {e}")
    seen_sha = {v.get("sha256") for v in ledger.values() if v.get("sha256")}

    box_token = None
    if args.box_folder_id and not args.dry_run:
        box_token = os.environ.get(args.box_token_env)
        if not box_token:
            die(f"--box-folder-id given but env var {args.box_token_env} is empty. "
                f"Set it (never hardcode the token) or omit --box-folder-id to stage locally.")

    os.makedirs(args.inbox, exist_ok=True)
    new, skipped, failed = [], [], []

    for cand in candidates:
        url = cand.get("url")
        sid = cand.get("source_id", "src")
        period = cand.get("period", "")
        if not url:
            failed.append({**cand, "error": "candidate missing 'url'"})
            continue
        slug = slugify(sid, period)

        # URL-level dedup (already ingested this exact report)
        if url in ledger:
            skipped.append({"slug": slug, "url": url, "reason": "url already in ledger"})
            continue

        if args.dry_run:
            new.append({"slug": slug, "url": url, "status": "would-fetch"})
            continue

        try:
            data, final_url, ctype = download(url)
        except Exception as e:  # noqa: BLE001 - fail loud, keep going
            failed.append({"slug": slug, "url": url, "error": str(e)})
            continue

        sha = hashlib.sha256(data).hexdigest()
        if sha in seen_sha:
            skipped.append({"slug": slug, "url": url, "reason": f"content sha256 already ingested ({sha[:12]})"})
            continue

        ext = ext_for(cand, final_url, ctype)
        company_dir = os.path.join(args.inbox, re.sub(r"[^A-Za-z0-9]+", "_", cand.get("company", sid)))
        os.makedirs(company_dir, exist_ok=True)
        fname = f"{slug}.{ext}"
        local_path = os.path.join(company_dir, fname)
        with open(local_path, "wb") as fh:
            fh.write(data)

        box_file_id = None
        if box_token:
            try:
                box_file_id = box_upload(data, fname, args.box_folder_id, box_token)
            except Exception as e:  # noqa: BLE001
                failed.append({"slug": slug, "url": url, "error": f"downloaded OK but Box upload failed: {e}",
                               "local_path": local_path})
                continue

        entry = {
            "source_id": sid, "company": cand.get("company"), "period": period,
            "project": cand.get("project") or args.project,
            "slug": slug, "adapter_hint": cand.get("adapter_hint"),
            "sha256": sha, "bytes": len(data), "content_type": ctype,
            "final_url": final_url, "local_path": local_path,
            "box_file_id": box_file_id, "fetched_at": now_iso(),
        }
        ledger[url] = entry
        seen_sha.add(sha)
        new.append(entry)

    if not args.dry_run:
        with open(args.ledger, "w") as fh:
            json.dump(ledger, fh, indent=2, sort_keys=True)

    manifest = {
        "run_at": now_iso(),
        "dry_run": args.dry_run,
        "counts": {"new": len(new), "skipped": len(skipped), "failed": len(failed)},
        "new": new, "skipped": skipped, "failed": failed,
    }
    manifest_path = args.manifest or os.path.join(args.inbox, "manifest.json")
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\n=== pharma-epi-fetcher run {'(DRY RUN) ' if args.dry_run else ''}===")
    print(f"new: {len(new)}   skipped: {len(skipped)}   failed: {len(failed)}")
    print(f"manifest: {manifest_path}")
    print(f"ledger:   {args.ledger}")
    if new and not args.dry_run:
        print("\nStaged files (ready to drag into Box):")
        for n in new:
            print(f"  [{n.get('company')}] {n.get('period')}  ->  {n.get('local_path')}  "
                  f"({n.get('bytes'):,} bytes, {(n.get('content_type') or '').split(';')[0]})")
    if failed:
        print("\nFAILED (needs manual pull / investigation):")
        for f in failed:
            print(f"  {f.get('slug')}  {f.get('url')}\n     -> {f.get('error')}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
