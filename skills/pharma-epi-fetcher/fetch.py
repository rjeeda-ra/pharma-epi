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
import subprocess
import sys
import tempfile
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


def _curl_env():
    """Env for curl calls: drop a stale CURL_CA_BUNDLE pointing at a missing file
    (Netskope rotates that download periodically). With it unset, Apple's
    /usr/bin/curl falls back to the system keychain, which trusts the corporate CA."""
    env = os.environ.copy()
    ca = env.get("CURL_CA_BUNDLE")
    if ca and not os.path.isfile(ca):
        env.pop("CURL_CA_BUNDLE", None)
    return env


def box_upload(data, filename, folder_id, token, as_user_id=None, timeout=180):
    """Upload a binary to Box via the content API, using curl.

    We shell out to curl deliberately: on corporate-proxied machines (Netskope
    TLS inspection) Python's OpenSSL 3.x rejects the injected CA ("CA cert does
    not include key usage extension"), while curl uses the system trust store /
    the CA bundle in $CURL_CA_BUNDLE and validates fine. The auth header is fed
    via a curl config on stdin so the token never appears in the process args."""
    attributes = json.dumps({"name": filename, "parent": {"id": str(folder_id)}})
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    try:
        cmd = [
            "curl", "-sS", "--fail-with-body", "-X", "POST", BOX_UPLOAD_URL,
            "-F", f"attributes={attributes}",
            "-F", f"file=@{tmp};filename={filename}",
            "-K", "-",  # read the Authorization (and As-User) header from stdin
        ]
        config = f'header = "Authorization: Bearer {token}"\n'
        if as_user_id:
            config += f'header = "As-User: {as_user_id}"\n'
        proc = subprocess.run(cmd, input=config, capture_output=True, text=True,
                              timeout=timeout, env=_curl_env())
    finally:
        os.unlink(tmp)
    if proc.returncode != 0:
        raise RuntimeError(f"curl upload failed (rc={proc.returncode}): "
                           f"{(proc.stdout or proc.stderr).strip()[:300]}")
    try:
        resp = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"unexpected Box response: {proc.stdout[:300]}")
    if "entries" not in resp:
        raise RuntimeError(f"Box upload error: {proc.stdout[:300]}")
    return resp["entries"][0]["id"]


def box_get_token_ccg(client_id, client_secret, subject_id, subject_type="enterprise", timeout=60):
    """Client Credentials Grant: exchange app creds for a ~60-min access token.
    subject_type is 'enterprise' (default) or 'user'. Via curl for the same
    Netskope reason as box_upload; secrets go through a stdin config so they
    never appear in the process args."""
    config = (
        'data-urlencode = "grant_type=client_credentials"\n'
        f'data-urlencode = "box_subject_type={subject_type}"\n'
        f'data-urlencode = "box_subject_id={subject_id}"\n'
        f'data-urlencode = "client_id={client_id}"\n'
        f'data-urlencode = "client_secret={client_secret}"\n'
    )
    proc = subprocess.run(
        ["curl", "-sS", "--fail-with-body", "-X", "POST",
         "https://api.box.com/oauth2/token", "-K", "-"],
        input=config, capture_output=True, text=True, timeout=timeout, env=_curl_env())
    if proc.returncode != 0:
        raise RuntimeError(f"Box CCG token request failed (rc={proc.returncode}): "
                           f"{(proc.stdout or proc.stderr).strip()[:300]}")
    try:
        return json.loads(proc.stdout)["access_token"]
    except Exception:
        raise RuntimeError(f"unexpected Box token response: {proc.stdout[:200]}")


def resolve_box_token(token_env):
    """Return (access_token, as_user_id). Prefer a ready token in $token_env (e.g. a
    Box Developer Token for manual runs); otherwise mint one via CCG from
    BOX_CLIENT_ID / BOX_CLIENT_SECRET / BOX_ENTERPRISE_ID (the automated path).
    Optional BOX_AS_USER_ID makes a CCG enterprise token act as that user."""
    as_user = os.environ.get("BOX_AS_USER_ID")
    tok = os.environ.get(token_env)
    if tok:
        return tok, as_user
    cid, csec = os.environ.get("BOX_CLIENT_ID"), os.environ.get("BOX_CLIENT_SECRET")
    subj_type = os.environ.get("BOX_SUBJECT_TYPE", "enterprise")
    subj_id = os.environ.get("BOX_SUBJECT_ID") or os.environ.get("BOX_ENTERPRISE_ID")
    if cid and csec and subj_id:
        return box_get_token_ccg(cid, csec, subj_id, subj_type), as_user
    return None, as_user


def run_backfill(ledger, args, token, as_user=None):
    """Upload already-staged local files (ledger entries lacking box_file_id) to Box."""
    uploaded, skipped, failed = [], [], []
    for url, e in sorted(ledger.items()):
        if e.get("box_file_id"):
            skipped.append((e.get("slug"), "already has box_file_id"))
            continue
        lp = e.get("local_path")
        if not lp or not os.path.isfile(lp):
            failed.append((e.get("slug"), f"local file missing: {lp}"))
            continue
        try:
            with open(lp, "rb") as fh:
                data = fh.read()
            fid = box_upload(data, os.path.basename(lp), args.box_folder_id, token, as_user_id=as_user)
            e["box_file_id"] = fid
            uploaded.append((e.get("slug"), fid))
        except Exception as ex:  # noqa: BLE001 - fail loud, keep going
            failed.append((e.get("slug"), str(ex)))

    with open(args.ledger, "w") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)

    print(f"\n=== Box backfill ===")
    print(f"uploaded: {len(uploaded)}   skipped: {len(skipped)}   failed: {len(failed)}")
    for slug, fid in uploaded:
        print(f"  uploaded {slug} -> box file {fid}")
    if failed:
        print("FAILED:")
        for slug, err in failed:
            print(f"  {slug}: {err}")
    sys.exit(1 if failed else 0)


def main():
    ap = argparse.ArgumentParser(description="Download/dedup/manifest core for pharma-epi-fetcher.")
    ap.add_argument("--candidates", default=None, help="JSON list of resolved report candidates.")
    ap.add_argument("--ledger", required=True, help="JSON dedup ledger (created if missing).")
    ap.add_argument("--backfill-box", action="store_true",
                    help="Upload already-staged local files (from the ledger) to Box and record box_file_id; "
                         "no downloads. Requires --box-folder-id and the token env var.")
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

    ledger = {}
    if os.path.isfile(args.ledger):
        try:
            ledger = json.load(open(args.ledger))
        except json.JSONDecodeError as e:
            die(f"ledger is not valid JSON: {e}")

    # Backfill mode: upload already-staged local files to Box, record box_file_id. No downloads.
    if args.backfill_box:
        if not args.box_folder_id:
            die("--backfill-box requires --box-folder-id")
        token, as_user = resolve_box_token(args.box_token_env)
        if not token:
            die(f"--backfill-box needs Box auth: set {args.box_token_env}, or "
                f"BOX_CLIENT_ID / BOX_CLIENT_SECRET / BOX_ENTERPRISE_ID for CCG.")
        run_backfill(ledger, args, token, as_user)
        return

    if not args.candidates or not os.path.isfile(args.candidates):
        die(f"candidates file not found: {args.candidates}")
    try:
        candidates = json.load(open(args.candidates))
    except json.JSONDecodeError as e:
        die(f"candidates file is not valid JSON: {e}")
    if not isinstance(candidates, list) or not candidates:
        die("candidates file must be a non-empty JSON list")

    seen_sha = {v.get("sha256") for v in ledger.values() if v.get("sha256")}

    box_token = box_as_user = None
    if args.box_folder_id and not args.dry_run:
        box_token, box_as_user = resolve_box_token(args.box_token_env)
        if not box_token:
            die(f"--box-folder-id given but no Box auth found. Set {args.box_token_env}, or "
                f"BOX_CLIENT_ID / BOX_CLIENT_SECRET / BOX_ENTERPRISE_ID for CCG; "
                f"or omit --box-folder-id to stage locally.")

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
                box_file_id = box_upload(data, fname, args.box_folder_id, box_token, as_user_id=box_as_user)
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
