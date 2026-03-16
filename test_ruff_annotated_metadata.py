from typing import Annotated
def Query(x=None, **kwargs): return x
def test_func(x: Annotated[str, Query(None, description="test")] = None):
    pass
