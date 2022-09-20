"""Extension: add a %_% and |_| pipe that can do everything but handling funcs() with parantheses while not requiring @ pipe function blocks"""

from functools import partial
from .superpipe import pipes

@pipes
class Infix(object):
    def __init__(self, func):
        self.func = func
    def __or__(self, other):
        return self.func(other)
    def __ror__(self, other):
        return Infix(partial(self.func, other))
    def __mod__(self, other):
        return self.func(other)
    def __rmod__(self, other):
        return Infix(partial(self.func, other))
    def __call__(self, v1, v2):
        return v1 >> v2


@Infix
@pipes
def _(x, f):
    return x >> f
