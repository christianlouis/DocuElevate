"""Tests for extraction quality metrics."""

from app.utils.extraction_evaluation import evaluate_examples


def test_evaluation_reports_field_and_complete_example_metrics():
    report = evaluate_examples(
        [
            {
                "id": "one",
                "expected": {"type": "Invoice", "sender": "ACME"},
                "actual": {"type": "invoice", "sender": "ACME"},
            },
            {
                "id": "two",
                "expected": {"type": "Contract", "sender": "Beta"},
                "actual": {"type": "Invoice", "sender": "Beta"},
            },
        ]
    )

    assert report["field_exact_match"] == 0.75
    assert report["complete_example_rate"] == 0.5
