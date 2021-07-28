# pylint: disable=undefined-variable, import-error, no-value-for-parameter

from os import path, sys

# Fix import location
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

import unittest
from unittest import TestCase

from superpipe import foreach, is_not_none, pipes, square


# pylint: disable=no-self-argument
class Utils:
    def add2(a, b):
        return a + b

    def add3(a, b, c):
        return a + b + c

    def div(a, b):
        return a / b

    def ident1(x):
        return x

    def ident2(x, y):
        return x, y

    def ident3(x, y, z):
        return x, y, z


class TestClasses(TestCase):
    class PipedMethods:
        @pipes
        def foo(self):
            return 5 >> _ * 5 >> [_, 2] >> sum

    def test_piped_methods(self):
        assert TestClasses.PipedMethods().foo() == 27

    @pipes
    class PipedClass:
        def foo(self):
            return [1, 2] >> sum >> _.bit_length()

    def test_piped_class(self):
        assert TestClasses.PipedClass().foo() == (3).bit_length()


@pipes
class TestMisc(TestCase):
    def test(self):
        assert 5 >> 2 ** _ >> _.bit_length() == 6
        assert [1, None, 3, 5, 84, 33] >> filter(is_not_none) >> map(square) >> sum == sum(map(square, [1, 3, 5, 84, 33]))

        from random import choice

        sample = range(5) >> [None, *_]
        sample >> [choice(_) for _x in range(10)]

    def test_idempotent(self):
        assert 1 >> _ >> _ >> _ == 1

    def test_loops(self):
        L = []
        for x in range(5) >> map(lambda x: x + 2):
            L.append(x)

        assert L == [2, 3, 4, 5, 6]

        x = 10
        count = 0
        while x >> _ > 0:
            count += 1
            x -= 1
        
        assert count == 10

    def test_foreach(self):
        L = []
        range(5) >> map(lambda x: x + 1) >> foreach(L.append)
        assert L == [1, 2, 3, 4, 5]

# fmt: off
    def test_complex(self):
        assert(
            3
            >> _ * 4
            >> (lambda x: x + 3)
            >> [1, _, 3, _]
            >> sorted
            >> filter(lambda x: x % 2 != 0)
            >> map(lambda x: x * x)
            >> list
            >> [77, 5, 6] + [_[2]]
            >> sum
            >> _ + 9
            >> {"a": 4 + _ + 5}
            >> _["a"]
            >> _.bit_length()
            >> pow(_, 2)
            == pow((331).bit_length(), 2)
        )
# fmt: on


class TestFunctionCalls(TestCase):
    @pipes
    def test(self):
        assert 5 >> Utils.add2(1) == 6
        assert 1 >> Utils.add2(1) >> Utils.add2(1) == 3
        assert 7 >> Utils.add3(1, 2) == 10

        assert 2 >> Utils.div(1) == 0.5

        assert [1, 2, 3] >> sum() == 6

    @pipes
    def test_implicit_call(self):
        assert [1, 2, 3] >> sum == 6
        assert range(5) >> sum == 10

        assert [1, [2, [3]]] >> Utils.ident1 == [1, [2, [3]]]
        assert "abcd" >> Utils.ident1 == "abcd"

        assert 4 >> range >> list == [0, 1, 2, 3]

    @pipes
    def test_substitution(self):
        assert 5 >> Utils.div(_, 1) == 5
        assert [1, 2] >> Utils.ident3(0, _, 3) == (0, [1, 2], 3)
        assert [1, 2] >> Utils.ident3(0, *_) == (0, 1, 2)

        def foo(bar, baz, qux):
            (baz + qux) * bar

        assert {"bar": 2, "baz": 9, "qux": 5} >> foo(**_) == foo(bar=2, baz=9, qux=5)

    @pipes
    def test_substitute_target(self):
        assert "a" >> _.upper() == "A"

        L = [1, 2, 3]
        L >> _.extend(L)
        assert L == [1, 2, 3, 1, 2, 3]

        def index(L):
            for i in L >> len >> range:
                assert L >> _.index(_[i]) == i

        index([1, 2, 3, 4, 5])


class TestComprehensions(TestCase):
    @pipes
    def test_list_comp(self):
        assert range(5) >> [x * x for x in _] == [x * x for x in range(5)]
        assert [1, 2, 3] >> [x for x in _ if x % 2 != 0] == [1, 3]

    @pipes
    def test_set_comp(self):
        assert range(5) >> {x for x in _} == set(range(5))
        assert {3, 3, 4} >> {x * x for x in _} == {9, 16}

    @pipes
    def test_dict_comp(self):
        assert {"a": 0, "b": 1, "c": 2} >> {k: v for k, v in _.items()} == {"a": 0, "b": 1, "c": 2}
        assert range(3) >> {str(x): x for x in _} == {"0": 0, "1": 1, "2": 2}

    @pipes
    def test_gen_expr(self):
        def gen_eq(a, b) -> bool:
            return all(x == y for x, y in zip(a, b))

        assert gen_eq(range(5) >> (x for x in _), range(5))
        assert gen_eq(range(3) >> (x * x for x in _), (x for x in [0, 1, 4]))

    @pipes
    def test_nested(self):
        assert [x+1 for x in range(3) >> map(lambda x: x + 1)] == [2, 3, 4]

class TestCollections(TestCase):
    @pipes
    def test_tuple(self):
        assert 3 >> (1, 2, _, 4, 5) == (1, 2, 3, 4, 5)
        assert (2, 3, 4) >> (1, *_, 5) == (1, 2, 3, 4, 5)
        assert (4, 5) >> (*_,) == (4, 5)

    @pipes
    def test_set(self):
        assert 3 >> {1, 2, _} == {1, 2, 3}
        assert {1, 2, 3} >> {*_, 4, 5} == {1, 2, 3, 4, 5}
        assert {3} >> {*_} == {3}

    @pipes
    def test_list(self):
        assert 0 >> [_, 1, 2] == [0, 1, 2]
        assert [5, 9] >> [1, *_, 22] == [1, 5, 9, 22]
        assert [7] >> [*_] == [7]

    @pipes
    def test_dict(self):
        assert 0 >> {"a": _} == {"a": 0}
        assert "a" >> {_: 0} == {"a": 0}
        assert {"b": 1} >> {"a": _} == {"a": {"b": 1}}

    @pipes
    def test_nesting(self):
        assert [2, 3] >> [[_]] == [[[2, 3]]]
        assert ([1, [7]], (77, {4})) >> [_, (2, _)] >> [[_], 7] == [
            [[([1, [7]], (77, {4})), (2, ([1, [7]], (77, {4})))]],
            7,
        ]
        assert 5 >> {_, _, 7, (8,)} >> [(_,), _] == [({5, 7, (8,)},), {5, 7, (8,)}]


if __name__ == "__main__":
    unittest.main()
