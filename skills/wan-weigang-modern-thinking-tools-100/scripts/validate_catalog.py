#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


EXPECTED = {
    "01-worldview.md": 6,
    "02-growth-strategy.md": 15,
    "03-decisions-judgment.md": 16,
    "04-learning-education.md": 10,
    "05-business-money.md": 10,
    "06-society-economy.md": 14,
    "07-organization-leadership.md": 10,
    "08-complexity.md": 8,
    "09-reflection-values.md": 10,
    "10-exploration-generativity.md": 1,
}
REQUIRED_BLOCKS = ("**何时调用**", "**核心模型**", "**Agent 程序**", "**诊断问题**", "**边界与输出**")
HEADING_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)


def validate(root: Path) -> dict:
    references = root / "references"
    errors: list[str] = []
    counts: dict[str, int] = {}
    headings: list[str] = []

    for filename, expected_count in EXPECTED.items():
        path = references / filename
        if not path.is_file():
            errors.append(f"missing reference: references/{filename}")
            continue
        text = path.read_text(encoding="utf-8")
        matches = list(HEADING_RE.finditer(text))
        counts[filename] = len(matches)
        if len(matches) != expected_count:
            errors.append(f"{filename}: expected {expected_count} tools, found {len(matches)}")
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            entry = text[match.start() : end]
            heading = match.group(1).strip()
            headings.append(heading)
            for block in REQUIRED_BLOCKS:
                if block not in entry:
                    errors.append(f"{filename}: {heading!r} is missing {block}")

    duplicates = sorted({heading for heading in headings if headings.count(heading) > 1})
    if duplicates:
        errors.append("duplicate tool headings: " + ", ".join(duplicates))

    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    for required in ("references/catalog-index.md", "references/operating-guide.md", "references/provenance.md"):
        if required not in skill_text:
            errors.append(f"SKILL.md does not reference {required}")

    total = sum(counts.values())
    if total != 100:
        errors.append(f"expected 100 tools in total, found {total}")

    return {
        "ok": not errors,
        "total_tools": total,
        "category_counts": counts,
        "duplicate_headings": duplicates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the 100-tool catalog structure.")
    parser.add_argument("skill_dir", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.skill_dir).resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"catalog validation passed: {result['total_tools']} tools")
    else:
        for error in result["errors"]:
            print(f"error: {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
