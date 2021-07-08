
from ast import Call, parse, Name, NodeTransformer, LShift, RShift, \
    increment_lineno, walk, Attribute, BinOp, dump, List, Tuple, Starred, JoinedStr, Subscript, ListComp, DictComp, GeneratorExp, Set, SetComp
from inspect import getsource, isclass, stack
from itertools import takewhile
from textwrap import dedent

def check_name(item):
    if isinstance(item, Name):
        if item.id == '_':
            return True
    return False

def check_starred(item):
    if isinstance(item, Starred):
        return check_name(item.value)

def handle_atom(col, i, repl):
    if check_name(col[i]):
        col[i] = repl
    elif check_starred(col[i]):
        col[i].value = repl

def handle_atomm(left, atom):
    if isinstance(atom, Name):
        return left
    if isinstance(atom, Starred):
        atom.value = left
    
    return atom

class MyTransform(NodeTransformer):
    def handle_node(self, left, right):

        # _.attr
        if isinstance(right, Attribute):
            if check_name(right.value):
                right.value = left
            return True

        # _[x]
        if isinstance(right, Subscript):
            if check_name(right.value):
                right.value = left
            else:
                self.handle_node(left, right.value)
            return True

        # _ + x
        # x + _
        if isinstance(right, BinOp):
            if check_name(right.left):
                right.left = left
            elif check_starred(right.left):
                right.left.value = left
            else:
                self.handle_node(left, right.left)
            if check_name(right.right):
                right.right = left
            elif check_starred(right.right):
                right.right.value = left
            else:
                self.handle_node(left, right.right)
            return True

        if isinstance(right, Call):

            # _.func
            if isinstance(right.func, Attribute):
                if check_name(right.func.value):
                    right.func.value = left
                    return True
                else:
                    return self.handle_node(left, right.func.value)

            once = False

            # func(x, y, _, z)
            for i, arg in enumerate(right.args):
                if check_name(arg):
                    right.args[i] = left
                    once = True
                elif check_starred(arg):
                    right.args[i].value = left
                    once = True
                else:
                    if self.handle_node(left, arg):
                        once = True

            # func(a=x, b=y, c=_, d=z)
            for i, arg in enumerate(right.keywords):
                if check_name(arg.value):
                    right.keywords[i].value = left
                    once = True
                elif check_starred(arg.value):
                    right.keywords[i].value.value = left
                    once = True
                else:
                    if self.handle_node(left, arg):
                        once = True

            # True if we modified something
            # Otherwise the enclosing scope
            # Needs to add the arg, depending on >> or <<
            return once

        # Lists, Tuples, and Sets
        if isinstance(right, (List, Tuple, Set)):
            for i, el in enumerate(right.elts):

                # 5 >> [x, y, _, z]
                if check_name(el):
                    right.elts[i] = left

                # (1, 2) >> [x, y, *_, z]
                elif check_starred(el):
                    right.elts[i].value = left

                else:
                    self.handle_node(left, el)
            return True

        # f-strings
        if isinstance(right, JoinedStr):
            for i, fvalue in enumerate(right.values):
                if check_name(fvalue.value):
                    right.values[i].value = left
                elif check_starred(fvalue.value):
                    right.values[i].value.value = left
                else:
                    self.handle_node(left, fvalue.value)
            return True

        # Comprehensions and Generators
        # [x for x in _]
        if isinstance(right, (ListComp, SetComp, DictComp, GeneratorExp)):
            for i, gen in enumerate(right.generators):
                if check_name(gen.iter):
                    gen.iter = left
                else:
                    self.handle_node(left, gen.iter)

            return True

        return False

    def visit_BinOp(self, node):
        left, op, right = self.visit(node.left), node.op, node.right
        if isinstance(op, (LShift, RShift)):

            if self.handle_node(left, right):
                return right

            # Convert function name / lambda etc without braces into call
            if isinstance(right, Call):

                # Rewrite a >> b(...) as b(a, ...)
                right.args.insert(
                    0 if isinstance(op, RShift) else len(right.args),
                    left)
                return right

            # Rewrite a >> f as f(a)
            return Call(
                func=right,
                args=[left],
                keywords=[],
                starargs=None,
                kwargs=None,
                lineno=right.lineno,
                col_offset=right.col_offset
            )
                
        else:
            return node

def pipes(func_or_class):
    if isclass(func_or_class):
        decorator_frame = stack()[1]
        ctx = decorator_frame[0].f_locals
        first_line_number = decorator_frame[2]

    else:
        ctx = func_or_class.__globals__
        first_line_number = func_or_class.__code__.co_firstlineno

    source = getsource(func_or_class)

    # AST data structure representing parsed function code
    tree = parse(dedent(source))

    # Fix line and column numbers so that debuggers still work
    increment_lineno(tree, first_line_number - 1)
    source_indent = sum([1 for _ in takewhile(str.isspace, source)]) + 1

    for node in walk(tree):
        if hasattr(node, "col_offset"):
            node.col_offset += source_indent

    # remove the pipe decorator so that we don't recursively
    # call it again. The AST node for the decorator will be a
    # Call if it had braces, and a Name if it had no braces.
    # The location of the decorator function name in these
    # nodes is slightly different.
    tree.body[0].decorator_list = \
        [d for d in tree.body[0].decorator_list
         if isinstance(d, Call) and d.func.id != 'pipes'
         or isinstance(d, Name) and d.id != 'pipes']

    # Apply the visit_BinOp transformation
    tree = MyTransform().visit(tree)

    # now compile the AST into an altered function or class definition
    code = compile(
        tree,
        filename=(ctx['__file__'] if '__file__' in ctx else "repl"),
        mode="exec")

    # and execute the definition in the original context so that the
    # decorated function can access the same scopes as the original
    exec(code, ctx)

    # return the modified function or class - original is never called
    return ctx[tree.body[0].name]

@pipes
def foo():
    return [1,2,3,4,5] << filter(lambda x: x%2==0) >> list >> _.index(4)

print(foo())

@pipes
def baz():
    return 5 >> _.__mul__(2) >> _.bit_length()

print(baz())

@pipes
def bar():
    return 1 >> (_, 5)

@pipes
def ff():
    1 >> _+10 >> _*6 >> print(55, _, 77)

ff()

@pipes
def qq():
    [1, 2, 3] >> [1, *_] >> print(1, *_, 5)

qq()

@pipes
def tt():
    10 >> _**3>> [_] >> print

tt()

@pipes
def ee():
    10 >> [1, _, 100] >> f"the list: {_}" >> print

ee()

#pylint: disable=undefined-variable
@pipes
def cc():
    range(-5, 5) \
    << map(lambda x: x + 1) \
    << map(abs) \
    >> [-10, *_] \
    >> f"thing: {_}" \
    >> print

# cc()

square = lambda x: x * x

@pipes
def pogchamp():
    for x in range(10) << map(square):
        print(x) # Alternatively: x >> print

# pogchamp()

# @pipes
# def pp():
#     5 >> [_, _, 7, _] >> print(_, _)

# pp()

@pipes
def xx():
    range(10) >> sorted >> reversed >> list >> _[2] >> print

xx()

from random import random

@pipes
def rando():
    range(10) << map(lambda x: random()) >> sum >> print

rando()

@pipes
def slices():
    {"a": 3, "b": 9} >> _["a"] >> print

slices()

@pipes
def swap():
    [1, 2] >> [_[1], _[0]] >> print

swap()

@pipes
def recurse():
    [1, 2] >> [_[0], [_[1], _[0] + 3]] >> print

recurse()


@pipes
def kwargs_():
    range(10) >> {str(x) : x for x in _} >> print

kwargs_()

@pipes
def extra_args():
    range(3) >> list >> print([[_]], [_[1]], _[0] + 2)

extra_args()

@pipes
def fstring_complex():
    range(-5, 10) >> list >> dict(a=9, b="xyz", c=_) >> {k : v for k, v in _.items() if k in ['a', 'c']} >> f"num: {_['c'][3]}" >> print

fstring_complex()

@pipes
def fstring_in_print():
    5 >> print(f"{_}")

fstring_in_print()

@pipes
def aaa():
    {'a': 5} >> _['a'].bit_length() >> print

aaa()

# @pipes
# def get_user(user_id) -> User:
#     return {'user_id': user_id} >> database.get >> UserSchema.load

@pipes
def list_to_list():
    [0, 10] >> range(*_) >> list >> print

list_to_list()

square = lambda x: x * x
even = lambda x: x % 2 == 0

@pipes
def forloop():
    return range(100) << filter(even) << map(square) >> list

def forloop_standard():
    return list(map(square, filter(even, range(100))))

from functools import reduce

@pipes
def factorial(n):
    return range(1, n + 1) >> reduce(lambda a,b: a*b, _, 1)

@pipes
def main():
    forloop() >> print
    factorial(0) >> f"0! = {_}" >> print
    factorial(3) >> f"3! = {_}" >> print
    factorial(5) >> f"5! = {_}" >> print

main()

@pipes
def gen():
    return range(10) >> (y for y in _)

print(list(gen()))

@pipes
def slicing():
    "abcdef" >> _[1:-1] >> print

slicing()

@pipes
def sets():
    5 >> {1, _, 7} >> print

sets()

@pipes
def setcomp():
    range(5) >> {x for x in _} >> {-1, *_} >> print

setcomp()

square = lambda x: x * x
even = lambda x: x % 2 == 0

@pipes
def nice():
    range(-5, 10) << map(square) << filter(even) >> list >> (_[3], _[1], _[2]) >> print

nice()

ident = lambda x: x

@pipes
def x():
    range(20) << map(ident) >> list >> (_,_) >> print

x()