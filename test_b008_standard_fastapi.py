from typing import Annotated

class Depends:
    def __init__(self, dependency=None):
        pass

def get_db():
    pass

DbSession = Annotated[int, Depends(get_db)]

# This is what I want to use
def test_func_ok(db: DbSession = Depends()):
    pass

# This is what Ruff should flag
def test_func_bad(db: int = Depends(get_db)):
    pass
