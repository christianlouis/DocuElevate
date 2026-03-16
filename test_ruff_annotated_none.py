from typing import Annotated
def Depends(x): return x
def get_db(): return "db"
DbSession = Annotated[str, Depends(get_db)]
def test_func(db: DbSession = None):
    pass
