"""Various utilities for functional programming and piping"""

from typing import TypeVar, Callable, Iterable, Any, Union

T = TypeVar('T')
S = TypeVar('S')

def foreach(f: Callable[T, S], iter: Iterable[T]) -> None:
    """Consumes an iterable. Applies `f` to each element of `iter` and returns nothing"""
    for item in iter:
        f(item)

# Predicates

def is_none(item) -> bool:
    return item is None

def is_not_none(item) -> bool:
    return item is not None

def is_even(n) -> bool:
    return n % 2 == 0

def is_odd(n) -> bool:
    return n % 2 != 0

is_truthy = bool

def is_falsy(item) -> bool:
    return not item

# Operations

def square(x):
    return x*x

def cube(x):
    return x*x*x

