# pylint: disable=undefined-variable, import-error

from os import path, sys

# Fix import location
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

import unittest
from unittest import TestCase

import superpipe


@superpipe.pipes
class Test(TestCase):
    def test(self):
        assert 5 >> _ == 5


if __name__ == "__main__":
    unittest.main()
