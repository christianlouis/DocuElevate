from typing import Annotated

class Depends:
    def __init__(self, dependency=None):
        pass

def get_db():
    pass

def test_func(db: Annotated[int, Depends(get_db)] = Depends()):
    pass
