# pylint: disable=undefined-variable, import-error

from os import path, sys

# Fix import location
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

import unittest
from functools import cache as cache_
from unittest import TestCase

import superpipe


@superpipe.pipes
class Test(TestCase):
    def test(self):
        assert 5 >> _ == 5


@cache_
@superpipe.pipes
def foo():
    pass


try:

    @superpipe.pipes
    @cache_
    def bar():
        pass

except ValueError:
    pass
else:
    assert (
        False
    ), "@pipes should raise an error here because the result of functools.cache is a so-called 'method descriptor' and not a function"

if __name__ == "__main__":
    unittest.main()
