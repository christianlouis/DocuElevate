from typing import Annotated

class Depends:
    def __init__(self, dependency=None):
        pass

def get_db():
    pass

DbSession = Annotated[int, Depends(get_db)]

# Cleanest Annotated pattern
def test_func_clean(db: DbSession):
    pass
