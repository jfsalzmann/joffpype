@Echo off
py -m build
py -m twine upload dist/*
pause
