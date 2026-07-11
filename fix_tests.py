import sys

# Fix test_process_document.py
with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.replace(
    """    rule = PipelineRoutingRule(
        pipeline_id=pipeline.id,
        rule_type="regex",
        field="original_filename",
        value=r".*test\.pdf",
        is_active=True,
        order=10
    )""",
    """    rule = PipelineRoutingRule(
        name="Test Rule",
        target_pipeline_id=pipeline.id,
        operator="regex",
        field="original_filename",
        value=r".*test\.pdf",
        is_active=True,
        position=10
    )""",
)

with open("tests/test_process_document.py", "w") as f:
    f.write(content)
