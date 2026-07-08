#!/usr/bin/env python3
"""
coverage.py — render a human-readable coverage log from the fetcher ledger.

Answers "which quarters/years have we already grabbed, per company and project,
and where are the gaps?" — a scannable view over ledger.json (which is keyed by
URL and hard to read directly).

    python3 coverage.py --ledger ledger.json [--out coverage.md] [--project epi-master]

Stdlib only. Writes Markdown (and prints a short summary). Read-only over the ledger.
"""

import argparse
import json
import os
import re
import sys

QUARTERS = ["Q1", "Q2", "Q3", "Q4", "FY"]


def parse_period(period):
    """Return (year:int|None, bucket:str) where bucket is Q1..Q4, FY, or 'event'."""
    if not period:
        return None, "event"
    ym = re.search(r"(19|20)\d{2}", period)
    year = int(ym.group(0)) if ym else None
    q = re.search(r"\bQ([1-4])\b", period, re.I)
    if q:
        return year, f"Q{q.group(1)}"
    if re.search(r"\bFY\b|full[\s-]?year|annual", period, re.I):
        return year, "FY"
    # bare-year annual report (e.g. Novartis "2025")
    if year and period.strip() == str(year):
        return year, "FY"
    return year, "event"


def main():
    ap = argparse.ArgumentParser(description="Render coverage log from the fetcher ledger.")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", default=None, help="Markdown output path (default: alongside ledger as coverage.md).")
    ap.add_argument("--project", default=None, help="Limit to a single project tag.")
    args = ap.parse_args()

    if not os.path.isfile(args.ledger):
        print(f"ERROR: ledger not found: {args.ledger}", file=sys.stderr)
        sys.exit(2)
    ledger = json.load(open(args.ledger))
    entries = list(ledger.values())
    if args.project:
        entries = [e for e in entries if (e.get("project") or "epi-master") == args.project]

    # group: project -> company -> list of entries
    projects = {}
    for e in entries:
        proj = e.get("project") or "epi-master"
        projects.setdefault(proj, {}).setdefault(e.get("company") or e.get("source_id"), []).append(e)

    lines = ["# Epi source coverage log", ""]
    lines.append(f"Total documents held: **{len(entries)}**  ·  projects: {len(projects)}")
    lines.append("")
    lines.append("Legend: ✓ = held · · = gap (no report grabbed for that period). "
                 "Event/undated decks are listed separately per year.")
    lines.append("")

    summary = []
    for proj in sorted(projects):
        lines.append(f"## Project: `{proj}`")
        lines.append("")
        for company in sorted(projects[proj]):
            evs = projects[proj][company]
            grid = {}          # year -> bucket -> True
            events = {}        # year -> [period,...] for non-Q/FY items
            undated = []
            for e in evs:
                y, b = parse_period(e.get("period"))
                if y is None:
                    undated.append(e.get("period") or e.get("slug"))
                    continue
                if b == "event":
                    events.setdefault(y, []).append(e.get("period"))
                else:
                    grid.setdefault(y, {})[b] = True
            years = sorted(set(list(grid) + list(events)))
            held = sum(len(v) for v in grid.values()) + sum(len(v) for v in events.values()) + len(undated)
            lines.append(f"### {company}  ({held} held, {years[0] if years else '—'}–{years[-1] if years else '—'})")
            lines.append("")
            if grid:
                lines.append("| Year | " + " | ".join(QUARTERS) + " |")
                lines.append("|" + "---|" * (len(QUARTERS) + 1))
                for y in years:
                    row = grid.get(y, {})
                    cells = ["✓" if row.get(b) else "·" for b in QUARTERS]
                    lines.append(f"| {y} | " + " | ".join(cells) + " |")
                lines.append("")
            for y in sorted(events):
                lines.append(f"- **{y} events:** " + "; ".join(sorted(events[y])))
            if undated:
                lines.append(f"- **undated:** " + "; ".join(undated))
            lines.append("")
            # gap note for quarterly-style companies
            if grid:
                gaps = []
                for y in range(years[0], years[-1] + 1):
                    for b in ["Q1", "Q2", "Q3", "Q4"]:
                        if not grid.get(y, {}).get(b) and not grid.get(y, {}).get("FY"):
                            gaps.append(f"{y} {b}")
                if gaps:
                    lines.append(f"> Gaps (quarterly view): {', '.join(gaps)}")
                    lines.append("")
            summary.append((proj, company, held))

    out = args.out or os.path.join(os.path.dirname(args.ledger) or ".", "coverage.md")
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"coverage log -> {out}")
    for proj, company, held in summary:
        print(f"  [{proj}] {company}: {held} held")


if __name__ == "__main__":
    main()
