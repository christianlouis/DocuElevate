from typing import Annotated

def Query(default, **kwargs):
    return default

def test_func(action: Annotated[str | None, Query(None, description="test")] = None):
    pass
