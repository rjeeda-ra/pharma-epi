# Quarterly cloud routine — setup spec (DEFERRED, not yet stood up)

This wires `pharma-epi-fetcher` to run **unattended every quarter** as a cloud
routine (a headless CCR session), via the `schedule` skill / `RemoteTrigger`
tool. It is documented here and intentionally **not created yet** — activate it
only after the prerequisites below are met.

## Cron

`cron_expression: "0 9 1 */3 *"` → 09:00 on the 1st of Jan/Apr/Jul/Oct.
(Pin explicit months `1,4,7,10` if you prefer calendar quarters exactly.)

## RemoteTrigger create body (shape)

```jsonc
{
  "name": "Quarterly epi-report pull",
  "enabled": true,
  "cron_expression": "0 9 1 */3 *",
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
