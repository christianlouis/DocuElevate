"""CI-friendly extraction evaluation metrics and report generation."""

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_examples(examples: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute field exact-match accuracy and example completeness."""
    expected_fields = 0
    matching_fields = 0
    complete_examples = 0
    rows: list[dict[str, Any]] = []
    for example in examples:
        expected = example.get("expected", {})
        actual = example.get("actual", {})
        matches = {
            key: str(actual.get(key, "")).strip().casefold() == str(value).strip().casefold()
            for key, value in expected.items()
        }
        expected_fields += len(matches)
        matching_fields += sum(matches.values())
        complete = bool(matches) and all(matches.values())
        complete_examples += int(complete)
        rows.append({"id": example.get("id"), "matches": matches, "complete": complete})
    count = len(examples)
    return {
        "examples": count,
        "field_exact_match": matching_fields / expected_fields if expected_fields else 0.0,
        "complete_example_rate": complete_examples / count if count else 0.0,
        "details": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate DocuElevate extraction fixtures")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    examples = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = evaluate_examples(examples)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
