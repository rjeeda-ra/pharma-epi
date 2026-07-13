# Monthly monitor (local launchd) + one-step Box upload

Runs `pharma-epi-fetcher` on the **5th of each month at 08:00 local** on this Mac.
Lives in `~/pharma-epi` (home) — **not** `~/Documents`, which macOS TCC blocks for
automated processes.

## Model (why it's split)

Unattended Box upload isn't possible here: the cloud routine can't hold a secret,
and every CCG path (service-account collaboration, as-user impersonation) is
blocked by enterprise Box policy. So we split:

- **`run_monthly.sh` (automatic, monthly):** headless Claude does discovery only
  (resolve current report URLs → candidates JSON; no Bash/git), then `fetch.py`
  downloads + sha256-dedups new reports into `.sources/` (no Box), `coverage.py`
  refreshes `coverage.md`, and the ledger + coverage are committed to git. Every run
  posts a summary to **Slack #epidash-testing** (via the Slack MCP connector, using a
  headless `claude -p` call) — green when new reports are staged, white on a quiet
  month; new-report runs also append `NEW-REPORTS.md` and pop a macOS notification.
- **`upload_pending.sh` (attended, one command):** you paste a fresh Box Developer
  Token and it uploads any ledger entries still missing a `box_file_id`, then
  commits the ids. The Developer Token uploads *as you*, so no CCG/collaboration.

The ledger (git) is the state/audit trail; Box holds the PDFs once you run the upload.

## Enable / disable the monthly job
```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rjeeda.pharma-epi-monthly.plist
launchctl kickstart -k gui/$(id -u)/com.rjeeda.pharma-epi-monthly   # run once now (test)
launchctl bootout   gui/$(id -u)/com.rjeeda.pharma-epi-monthly       # disable
```

## Upload staged reports to Box (after a notification)
```bash
# Box Developer Console -> your app -> generate a Developer Token, then:
BOX_API_TOKEN='<token>' ~/pharma-epi/scheduler/upload_pending.sh
```

## Logs & notes
- Per-run logs: `~/pharma-epi/logs/run-<timestamp>.log`; new-report history: `NEW-REPORTS.md`.
- Runs only when the Mac is awake (launchd fires a missed calendar run on next wake).
- Uses `/usr/bin/python3` (scripts are stdlib-only) — the pyenv shim currently hangs.
- Does not run extractor/exporter/qc; extraction into the master sheet stays a
  separate human-checkpointed step.
