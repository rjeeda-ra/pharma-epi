# Monthly cloud routine — setup spec

This wires `pharma-epi-fetcher` to run **unattended monthly** as a cloud routine
(a headless CCR session), via the `schedule` skill / `RemoteTrigger` tool.

## Cron

`cron_expression: "0 8 5 * *"` → 08:00 on the 5th of every month. Monthly (not
quarterly) because the sources publish on different clocks — GSK quarterly, Roche
~September, Novartis annual, Sanofi ad-hoc — so a monthly re-scan never misses a
window by more than a few weeks. Runs are cheap idempotent no-ops when nothing is new.

## RemoteTrigger create body (shape)

```jsonc
{
  "name": "Monthly epi-report pull",
  "enabled": true,
  "cron_expression": "0 8 5 * *",
  "job_config": {
    "ccr": {
      "environment_id": "<CCR environment id>",
      "session_context": {
        "model": "claude-sonnet-5",
        "sources": [
          { "git_repository": { "url": "<repo holding the pharma-epi-* skills bundle>" } }
        ],
        "allowed_tools": ["Bash", "Read", "Write", "WebFetch", "WebSearch", "Slack"]
      },
      "events": [
        { "message": "Run the pharma-epi-fetcher skill in unattended mode: read watchlist.yaml, resolve and fetch every new epi report per the discovery ladder, upload binaries to Box, auto-extract each to the human checkpoint (leave the checkpoint UNCHECKED, defer all decisions into the review note), then post the Slack summary. Do not cross the sign-off gate." }
      ]
    }
  },
  "mcp_connections": [
    { "connector_uuid": "<slack connector uuid>", "name": "Slack", "url": "<slack connector url>" }
  ]
}
```

## Prerequisites (all required before creating the routine)

1. **Skills bundle in a git repo** — the CCR checks out `session_context.sources[].git_repository`.
   The routine will NOT see `~/.claude/skills/`; move/push the `pharma-epi-*` bundle to a repo. *(deferred)*
2. **Slack connector** pre-connected at `claude.ai/customize/connectors`; reference it in `mcp_connections`.
3. **Runtime**: `python3` + `pdfplumber` + `openpyxl` available in the CCR image (extraction needs them).
4. **Box app token as a managed CCR secret**, exposed as `BOX_API_TOKEN` (never in the repo).
   - The Box **Custom App must be enterprise-admin-authorized** (Admin Console → Apps → Custom
     Apps Manager → authorize by Client ID) BEFORE any token works — otherwise every call 401s with
     `"Cannot authorize with this service"` (this gates even developer tokens). Confirmed 2026-07-08.
   - **Box uploads must go through `curl`**, not Python: on RAC's Netskope-proxied network, Python's
     OpenSSL 3.x rejects the injected CA (`CA cert does not include key usage extension`), while curl
     uses the system CA bundle (`$CURL_CA_BUNDLE`). `fetch.py`'s `box_upload()` already shells out to curl.
5. **Taxonomy as text** — the extractor reads the master's `Indication Aliases` / `Metric Type Aliases`
   tabs live; in the sandbox (no local `.xlsx`) provide them as a committed text/CSV export or via Box.

## Hard constraints (why the routine cannot be fully autonomous)

- **No interactive prompts** in a headless CCR — the fetcher's unattended mode defers every decision to
  the review note and leaves the checkpoint unchecked. Export + QC remain a human/local step after the
  routine notifies. This is required by RAC compliance: AI-extracted data may not enter the master sheet
  without human sign-off, and `export.py`'s gate has no override.
- Scope `allowed_tools` to exactly what the run needs; a missing permission stalls a headless run on
  `requires_action` with no client to answer.

## Validation before creating

- `RemoteTrigger {action: "list"}` to confirm access.
- Do a manual local run of the skill first (the on-demand path) and confirm the Slack summary + staging output.
- Only then `RemoteTrigger {action: "create", body: <above>}`. Manage/delete at `claude.ai/code/routines`.
