#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["id", "title", "authors", "year", "venue", "team", "topic", "source", "first_seen", "last_checked", "status", "relevance_score"]


def main() -> int:
    papers = json.loads((ROOT / "data" / "papers.json").read_text(encoding="utf-8"))
    groups = json.loads((ROOT / "data" / "groups.json").read_text(encoding="utf-8"))
    group_ids = {g["id"] for g in groups} | {"unknown"}
    seen = {}
    errors = []
    for idx, paper in enumerate(papers):
        for key in REQUIRED:
            if key not in paper:
                errors.append(f"paper[{idx}] missing {key}")
        paper_id = paper.get("id")
        if paper_id in seen:
            errors.append(
                "duplicate id: "
                f"{paper_id} | first={seen[paper_id].get('title')} | second={paper.get('title')}"
            )
        seen[paper_id] = paper
        if paper.get("team") not in group_ids:
            errors.append(f"unknown team for {paper.get('id')}: {paper.get('team')}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"ok: {len(groups)} groups, {len(papers)} papers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
