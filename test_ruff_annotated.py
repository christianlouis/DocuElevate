from typing import Annotated

def Query(default=None, **kwargs):
    return default

def Depends(dependency=None):
    return dependency

def get_db():
    return None

def test_func(
    db: Annotated[int, Depends(get_db)] = Depends(),
    action: Annotated[str | None, Query(None, description="test")] = None
):
    pass
