from __future__ import annotations

import json
from typing import Any

from deepdiff import DeepDiff


def diff_snapshots(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    return json.loads(DeepDiff(old, new, ignore_order=True).to_json())


def summarize_diff_rule_based(
    university: str,
    dept: str,
    year: int | None,
    diff: dict[str, Any],
) -> str:
    if not diff:
        return f"{university} {dept} {year or ''}年度: 変更は検出されませんでした。".strip()
    lines = [f"{university} {dept} {year or ''}年度 募集要項更新"]
    for key in (
        "dictionary_item_added",
        "dictionary_item_removed",
        "values_changed",
        "iterable_item_added",
        "iterable_item_removed",
    ):
        if key in diff:
            lines.append(f"- {key}: {len(diff[key])}件")
    return "\n".join(lines)
