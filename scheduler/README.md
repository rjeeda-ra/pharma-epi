# Monthly monitor (local launchd) + Slack notify

Runs `pharma-epi-fetcher` on the **5th of each month at 08:00 local** on this Mac.
(Claude Tag isn't available yet, so this stays local for now.) Lives in `~/pharma-epi`
(home — `~/Documents` is TCC-blocked for automated jobs).

## What the monthly run does (`run_monthly.sh`)
headless `claude -p` discovery (resolve current report URLs) → `fetch.py` (download +
sha256 dedup, staged in `.sources/`) → `coverage.py` → commit ledger + coverage to git →
**post a completion summary to Slack #epidash-testing** (🟢 new reports / ⚪ quiet month /
⚠️ discovery empty). Discovery retries once with a 600s per-attempt timeout.

Slack posts go through the claude.ai Slack MCP connector via a headless `claude -p` call
(verified working headless).

## Box upload (separate step — Box write now works)
The monthly run stages reports locally and records them in the ledger; it does **not**
auto-upload to Box yet. Two ways to archive to Box (both working now that the CCG service
account `Epi_Dashboard` is an Editor collaborator on the folder):
- **On-demand / cloud:** the `epi-box-sync` GitHub Action (`gh workflow run epi-box-sync`).
- **Local one-liner:** `BOX_API_TOKEN='<dev token>' ~/pharma-epi/scheduler/upload_pending.sh`.

## Manage the monthly job
```bash
launchctl bootout   gui/$(id -u)/com.rjeeda.pharma-epi-monthly            # disable
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rjeeda.pharma-epi-monthly.plist
launchctl kickstart -k gui/$(id -u)/com.rjeeda.pharma-epi-monthly         # run now
```
Logs: `~/pharma-epi/logs/`. Runs only when the Mac is awake (missed runs fire on next wake).
