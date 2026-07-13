#!/bin/bash
# Monthly epi-report MONITOR (launchd: com.rjeeda.pharma-epi-monthly, 5th @ 08:00 local).
#
# Model (pragmatic fallback — no unattended Box upload):
#   discovery (headless Claude, discovery-only, retried) -> fetch.py (download + sha256
#   dedup, staged locally, NO Box) -> coverage.py -> commit ledger + coverage to git
#   -> ALWAYS post a summary to Slack (+ macOS notice / NEW-REPORTS.md when new).
# Box upload is a separate attended step: scheduler/upload_pending.sh (Developer Token).

set -uo pipefail
REPO="$HOME/pharma-epi"
FETCHER="$REPO/skills/pharma-epi-fetcher"
INBOX="$REPO/.sources"
LOGDIR="$REPO/logs"
CLAUDE_BIN="$HOME/.npm-global/bin/claude"
PY="/usr/bin/python3"
SLACK_CHANNEL="C0BGKMJE607"      # #epidash-testing

mkdir -p "$INBOX" "$LOGDIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/run-$STAMP.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== pharma-epi monthly monitor $STAMP ==="

# Hard timeout wrapper (macOS has no `timeout`): perl's alarm survives exec and
# SIGALRMs the child if it overruns, so a hung claude -p can never wedge the job.
with_timeout() { local s="$1"; shift; /usr/bin/perl -e 'alarm shift @ARGV; exec @ARGV' "$s" "$@"; }

# Post a message to Slack via headless claude + the Slack MCP tool (message passed by
# file to avoid quoting issues). Best-effort; never aborts the run.
slack_notify() {
  local msg="$1" mf
  mf="$(mktemp -t epi_slack.XXXXXX)"; printf '%s\n' "$msg" > "$mf"
  echo "-- slack notify --"
  with_timeout 180 "$CLAUDE_BIN" -p "Read the file $mf and post its exact contents as a message to Slack channel $SLACK_CHANNEL using the slack_send_message tool. Post nothing else, then stop." \
    --model claude-sonnet-5 --allowedTools "Read" "mcp__claude_ai_Slack__slack_send_message" \
    --permission-mode acceptEdits >>"$LOG" 2>&1 && echo "slack posted" || echo "WARN: slack notify failed"
  rm -f "$mf"
}

cd "$REPO" || { echo "FATAL: $REPO missing"; slack_notify ":red_circle: *pharma-epi monitor* ($STAMP): FATAL — repo $REPO missing."; exit 1; }
git pull --ff-only 2>&1 | tail -2

CAND="$(mktemp -t epi_cand.XXXXXX).json"
PROMPT="You are an automated discovery step (no human watching). Do ONLY this, then stop:
1. Read $FETCHER/SKILL.md ('Discovery ladder') and $FETCHER/watchlist.yaml.
2. For every source, resolve the report URL(s) currently published (WebFetch/WebSearch). Recurring sources: list every period available. one_off sources: use report_url. Do NOT filter against any ledger.
3. Write a JSON array to $CAND, elements: {\"source_id\",\"company\",\"period\",\"url\",\"expected_format\":\"pdf|xlsx\",\"adapter_hint\"}.
Write ONLY that file (a non-empty JSON array). No downloads, no scripts, no git."

valid_cand() { [ -s "$CAND" ] && "$PY" -I -c "import json,sys;a=json.load(open(sys.argv[1]));sys.exit(0 if isinstance(a,list) and a else 1)" "$CAND" 2>/dev/null; }

# Discovery with one retry (LLM discovery is nondeterministic).
for attempt in 1 2; do
  echo "-- discovery attempt $attempt --"
  with_timeout 600 "$CLAUDE_BIN" -p "$PROMPT" --model claude-sonnet-5 --add-dir "$REPO" \
    --allowedTools "Read" "Write" "WebFetch" "WebSearch" --permission-mode acceptEdits >>"$LOG" 2>&1 || echo "WARN: discovery attempt $attempt failed/timed out"
  valid_cand && break
  echo "attempt $attempt produced no valid candidates"
done

if ! valid_cand; then
  echo "discovery produced nothing after retries"
  rm -f "$CAND"
  slack_notify ":warning: *pharma-epi monitor* ($STAMP): discovery returned NO candidates after 2 tries — likely a scraper/site issue. Check the log ($LOG) and the watchlist; run manually if needed."
  echo "=== done $STAMP (log: $LOG) ==="
  exit 0
fi
echo "candidates: $("$PY" -I -c "import json,sys;print(len(json.load(open(sys.argv[1]))))" "$CAND")"

echo "-- fetch (local staging, no Box) --"
"$PY" "$FETCHER/fetch.py" --candidates "$CAND" --ledger "$FETCHER/ledger.json" --inbox "$INBOX" --manifest "$INBOX/manifest.json"
rm -f "$CAND"

echo "-- coverage --"
"$PY" "$FETCHER/coverage.py" --ledger "$FETCHER/ledger.json" --out "$REPO/coverage.md" || true

NEW=$("$PY" -I -c "import json;print(json.load(open('$INBOX/manifest.json'))['counts']['new'])" 2>/dev/null || echo 0)
FAILED=$("$PY" -I -c "import json;print(json.load(open('$INBOX/manifest.json'))['counts']['failed'])" 2>/dev/null || echo 0)
DETAILS=$("$PY" -I -c "import json;m=json.load(open('$INBOX/manifest.json'));ns=m.get('new',[]);print('; '.join((str(n.get('company'))+' '+str(n.get('period'))) for n in ns))" 2>/dev/null)
echo "-- new: $NEW  failed: $FAILED --"
FAILNOTE=""
[ "${FAILED:-0}" -gt 0 ] 2>/dev/null && FAILNOTE=" (:warning: $FAILED source(s) failed to fetch — check log.)"

git add "$FETCHER/ledger.json" "$REPO/coverage.md" 2>/dev/null
if git diff --cached --quiet; then echo "no ledger/coverage change"; else
  git commit -q -m "monitor: monthly pull $STAMP ($NEW new)" && git push -q origin main && echo "committed + pushed"; fi

if [ "${NEW:-0}" -gt 0 ] 2>/dev/null; then
  printf '%s  —  %s new: %s (run scheduler/upload_pending.sh)\n' "$STAMP" "$NEW" "$DETAILS" >> "$REPO/NEW-REPORTS.md"
  /usr/bin/osascript -e "display notification \"$NEW new epi report(s) staged — run upload_pending.sh\" with title \"pharma-epi monitor\"" 2>/dev/null || true
  slack_notify ":large_green_circle: *pharma-epi monitor* ($STAMP): *$NEW new* report(s) staged — $DETAILS. Run \`upload_pending.sh\` to archive to Box. Ledger + coverage committed to rjeeda-ra/pharma-epi.${FAILNOTE}"
else
  slack_notify ":white_circle: *pharma-epi monitor* ($STAMP): ran OK — no new reports this month.${FAILNOTE}"
fi
echo "=== done $STAMP (log: $LOG) ==="
