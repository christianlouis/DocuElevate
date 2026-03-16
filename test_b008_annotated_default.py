from typing import Annotated
def Query(default=None, **kwargs): return default
def test_func(limit: Annotated[int, Query(50, ge=1)] = 50):
    pass
