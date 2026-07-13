#!/bin/bash
# Monthly epi-report MONITOR (launchd: com.rjeeda.pharma-epi-monthly, 5th @ 08:00 local).
#
# Model (pragmatic fallback — no unattended Box upload):
#   discovery (headless Claude, discovery-only) -> fetch.py (download + sha256 dedup,
#   staged locally, NO Box upload) -> coverage.py -> commit ledger + coverage to git
#   -> notify (macOS notification + NEW-REPORTS.md) if anything new.
# Box upload is a separate one-command attended step: scheduler/upload_pending.sh
# (uses a short-lived Box Developer Token, which uploads as you).

set -uo pipefail
REPO="$HOME/pharma-epi"
FETCHER="$REPO/skills/pharma-epi-fetcher"
INBOX="$REPO/.sources"           # transient local staging (gitignored)
LOGDIR="$REPO/logs"              # gitignored
CLAUDE_BIN="$HOME/.npm-global/bin/claude"
PY="/usr/bin/python3"            # stdlib-only scripts; avoids the pyenv shim (which hangs)
SLACK_CHANNEL="C0BGKMJE607"      # #epidash-testing (private) — posts via the Slack MCP connector

mkdir -p "$INBOX" "$LOGDIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/run-$STAMP.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== pharma-epi monthly monitor $STAMP ==="

cd "$REPO" || { echo "FATAL: $REPO missing"; exit 1; }
git pull --ff-only 2>&1 | tail -2

CAND="$(mktemp -t epi_cand.XXXXXX).json"
PROMPT="You are an automated discovery step (no human watching). Do ONLY this, then stop:
1. Read $FETCHER/SKILL.md ('Discovery ladder') and $FETCHER/watchlist.yaml.
2. For every source, resolve the report URL(s) currently published (WebFetch/WebSearch). Recurring sources: list every period available. one_off sources: use report_url. Do NOT filter against any ledger.
3. Write a JSON array to $CAND, elements: {\"source_id\",\"company\",\"period\",\"url\",\"expected_format\":\"pdf|xlsx\",\"adapter_hint\"}.
Write ONLY that file. No downloads, no scripts, no git. Omit any source you can't resolve."

echo "-- discovery --"
"$CLAUDE_BIN" -p "$PROMPT" --model claude-sonnet-5 --add-dir "$REPO" \
  --allowedTools "Read" "Write" "WebFetch" "WebSearch" --permission-mode acceptEdits \
  >/dev/null 2>>"$LOG" || echo "WARN: discovery exited non-zero"

if [ ! -s "$CAND" ] || ! "$PY" -I -c "import json,sys;a=json.load(open(sys.argv[1]));sys.exit(0 if isinstance(a,list) and a else 1)" "$CAND" 2>/dev/null; then
  echo "no candidates resolved — nothing to do"; rm -f "$CAND"; exit 0
fi

echo "-- fetch (local staging, no Box) --"
"$PY" "$FETCHER/fetch.py" --candidates "$CAND" --ledger "$FETCHER/ledger.json" --inbox "$INBOX" --manifest "$INBOX/manifest.json"
rm -f "$CAND"

echo "-- coverage --"
"$PY" "$FETCHER/coverage.py" --ledger "$FETCHER/ledger.json" --out "$REPO/coverage.md" || true

NEW=$("$PY" -I -c "import json;print(json.load(open('$INBOX/manifest.json'))['counts']['new'])" 2>/dev/null || echo 0)
echo "-- new this run: $NEW --"

git add "$FETCHER/ledger.json" "$REPO/coverage.md" 2>/dev/null
if git diff --cached --quiet; then
  echo "no ledger/coverage change"
else
  git commit -q -m "monitor: monthly pull $STAMP ($NEW new)" && git push -q origin main && echo "committed + pushed"
fi

# --- notify: Slack (primary) + macOS + NEW-REPORTS.md ---
DETAILS=$("$PY" -I -c "import json;m=json.load(open('$INBOX/manifest.json'));ns=m.get('new',[]);print('; '.join((str(n.get('company'))+' '+str(n.get('period'))) for n in ns))" 2>/dev/null)
if [ "${NEW:-0}" -gt 0 ] 2>/dev/null; then
  MSG=":large_green_circle: *pharma-epi monitor* ($STAMP): *$NEW new* report(s) staged — $DETAILS. Run \`upload_pending.sh\` to archive to Box. Ledger + coverage committed to rjeeda-ra/pharma-epi."
  printf '%s  —  %s new report(s) staged in %s (run scheduler/upload_pending.sh to push to Box): %s\n' "$STAMP" "$NEW" "$INBOX" "$DETAILS" >> "$REPO/NEW-REPORTS.md"
  /usr/bin/osascript -e "display notification \"$NEW new epi report(s) staged — run upload_pending.sh\" with title \"pharma-epi monitor\"" 2>/dev/null || true
else
  MSG=":white_circle: *pharma-epi monitor* ($STAMP): ran OK — no new reports this month."
fi

# Post to Slack via headless claude + the Slack MCP connector (message passed by file to avoid quoting issues)
MSGFILE="$(mktemp -t epi_slack.XXXXXX)"
printf '%s\n' "$MSG" > "$MSGFILE"
echo "-- slack notify --"
"$CLAUDE_BIN" -p "Read the file $MSGFILE and post its exact contents as a message to Slack channel $SLACK_CHANNEL using the slack_send_message tool. Post nothing else, then stop." \
  --model claude-sonnet-5 --allowedTools "Read" "mcp__claude_ai_Slack__slack_send_message" --permission-mode acceptEdits \
  >/dev/null 2>>"$LOG" && echo "slack posted" || echo "WARN: slack notify failed (see log)"
rm -f "$MSGFILE"
echo "=== done $STAMP (log: $LOG) ==="
