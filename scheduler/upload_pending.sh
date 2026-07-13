#!/bin/bash
# One-command attended Box upload of any staged-but-not-yet-uploaded reports.
# Uses a short-lived Box Developer Token (which uploads AS you), so it needs no
# CCG / as-user / collaboration setup.
#
# Usage:
#   1. Box Developer Console -> your app -> Configuration -> generate a Developer Token
#   2. BOX_API_TOKEN='<that token>' ~/pharma-epi/scheduler/upload_pending.sh
#
# It uploads every ledger entry that still has box_file_id: null, records the ids,
# and commits the ledger.

set -uo pipefail
REPO="$HOME/pharma-epi"
FETCHER="$REPO/skills/pharma-epi-fetcher"
FOLDER="${BOX_FOLDER_ID:-397983244341}"   # Epidemiology_Test_Pull

if [ -z "${BOX_API_TOKEN:-}" ]; then
  echo "Set BOX_API_TOKEN to a fresh Box Developer Token first, e.g.:"
  echo "  BOX_API_TOKEN='xxxx' $0"
  exit 1
fi
[ -n "${CURL_CA_BUNDLE:-}" ] && [ ! -f "${CURL_CA_BUNDLE}" ] && unset CURL_CA_BUNDLE

cd "$REPO"
git pull --ff-only 2>&1 | tail -2

# BOX_AS_USER_ID intentionally unset here: a Developer Token is already your identity.
env -u BOX_AS_USER_ID -u BOX_CLIENT_ID -u BOX_CLIENT_SECRET -u BOX_ENTERPRISE_ID \
  BOX_API_TOKEN="$BOX_API_TOKEN" \
  /usr/bin/python3 "$FETCHER/fetch.py" --backfill-box --box-folder-id "$FOLDER" --ledger "$FETCHER/ledger.json"
rc=$?

git add "$FETCHER/ledger.json" 2>/dev/null
if git diff --cached --quiet; then
  echo "no ledger change (nothing pending, or upload failed)"
else
  git commit -q -m "upload: box_file_ids $(date +%Y%m%d-%H%M)" && git push -q origin main && echo "committed + pushed"
fi
exit $rc
