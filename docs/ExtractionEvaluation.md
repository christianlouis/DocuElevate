# Extraction evaluation

Extraction fixtures are JSON arrays. Each entry has a stable `id`, an
`expected` object containing the gold fields, and an `actual` object containing
the extractor output being evaluated.

```json
[
  {
    "id": "invoice-001",
    "expected": {"document_type": "Invoice", "sender": "Example GmbH"},
    "actual": {"document_type": "Invoice", "sender": "Example GmbH"}
  }
]
```

Run the evaluator with:

```bash
python -m app.utils.extraction_evaluation dataset.json --output report.json
```

The report includes two baseline metrics:

- `field_exact_match`: fraction of expected fields matched after trimming and case normalization.
- `complete_example_rate`: fraction of examples where every expected field matched.

Fixtures should contain synthetic or explicitly licensed documents and must not
include production document contents or personal information.
