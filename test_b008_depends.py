def Depends(arg=None):
    return arg
def get_db():
    pass
def test_func(db=Depends(get_db)):
    pass
