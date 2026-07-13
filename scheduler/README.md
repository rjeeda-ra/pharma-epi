# Monthly monitor (local launchd) + Slack notify

Runs `pharma-epi-fetcher` on the **5th of each month at 08:00 local** on this Mac.
(Claude Tag isn't available yet, so this stays local for now.) Lives in `~/pharma-epi`
(home — `~/Documents` is TCC-blocked for automated jobs).

## What the monthly run does (`run_monthly.sh`)
headless `claude -p` discovery (resolve current report URLs) → `fetch.py` (download +
sha256 dedup → **upload new reports to Box**) → `coverage.py` → commit ledger + coverage
to git → **post a completion summary to Slack #epidash-testing** (🟢 new / ⚪ quiet /
⚠️ discovery empty). Discovery retries once with a 600s per-attempt timeout.

Box upload runs automatically when `~/.config/pharma-epi/box.env` has the CCG creds
(`BOX_CLIENT_ID/SECRET/ENTERPRISE_ID` + `BOX_FOLDER_ID`); uploads use the service account,
which is an Editor collaborator on the folder. Without box.env it stages locally only.

Slack posts go through the claude.ai Slack MCP connector via a headless `claude -p` call
(verified working headless).

## Box upload — automatic, with fallbacks
The monthly run now uploads new reports to Box itself (see above). Fallbacks if ever needed:
- **On-demand / cloud:** the `epi-box-sync` GitHub Action (`gh workflow run epi-box-sync`).
- **Local one-liner:** `BOX_API_TOKEN='<dev token>' ~/pharma-epi/scheduler/upload_pending.sh`.

## Manage the monthly job
```bash
launchctl bootout   gui/$(id -u)/com.rjeeda.pharma-epi-monthly            # disable
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rjeeda.pharma-epi-monthly.plist
launchctl kickstart -k gui/$(id -u)/com.rjeeda.pharma-epi-monthly         # run now
```
Logs: `~/pharma-epi/logs/`. Runs only when the Mac is awake (missed runs fire on next wake).
