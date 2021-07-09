"""Implements an @pipes operator that transforms the >> and << to act similarly to Elixir pipes"""


import typing
from ast import (
    AST,
    Attribute,
    BinOp,
    Call,
    Dict,
    DictComp,
    FormattedValue,
    GeneratorExp,
    JoinedStr,
    List,
    ListComp,
    LShift,
    Name,
    NodeTransformer,
    RShift,
    Set,
    SetComp,
    Starred,
    Subscript,
    Tuple,
    increment_lineno,
    parse,
    walk,
)
from inspect import getsource, isclass, stack
from itertools import takewhile
from textwrap import dedent


class _PipeTransformer(NodeTransformer):
    def handle_atom(self, left: AST, atom: AST) -> typing.Tuple[AST, bool]:
        """
        Handle an "atom".
        Recursively replaces all instances of `_` and `*_`
        """
        if isinstance(atom, Name):
            if atom.id == "_":
                return left, True
            else:
                return atom, False
        elif isinstance(atom, Starred):
            atom.value, mod = self.handle_atom(left, atom.value)
            return atom, mod

        self.handle_node(left, atom)
        return atom, False

    # pylint: disable=too-many-branches, too-many-return-statements, invalid-name
    def handle_node(self, left: AST, right: AST) -> AST:
        """
        Recursively handles AST substitutions
        :param left: Nominally the left side of a BinOp. This is substitued into `right`
        :param right: Nominally the right side of a BinOp. Target of substitutions.
        :returns: The transformed AST
        """

        # _.attr or _[x]
        if isinstance(right, (Attribute, Subscript)):
            right.value, mod = self.handle_atom(left, right.value)
            return mod

        # _ + x
        # x + _
        if isinstance(right, BinOp):
            right.left, _ = self.handle_atom(left, right.left)
            right.right, _ = self.handle_atom(left, right.right)
            return True

        if isinstance(right, Call):

            # _.func
            if isinstance(right.func, Attribute):
                right.func.value, mod = self.handle_atom(left, right.func.value)

                # Only exit if we substituted the value of the call
                # Otherwise, we need to process the arguments
                if mod:
                    return True

            once = False

            for i, arg in enumerate(right.args):
                right.args[i], mod = self.handle_atom(left, arg)
                once |= mod

            for i, arg in enumerate(right.keywords):
                right.keywords[i].value, mod = self.handle_atom(left, arg.value)
                once |= mod

            # True if we modified something
            # Otherwise the enclosing scope
            # Needs to add the arg, depending on >> or <<
            return once

        # Lists, Tuples, and Sets
        if isinstance(right, (List, Tuple, Set)):
            for i, el in enumerate(right.elts):
                right.elts[i], _ = self.handle_atom(left, el)
            return True

        # Dictionaries
        if isinstance(right, Dict):
            for col in [right.keys, right.values]:
                for i, item in enumerate(col):
                    col[i], _ = self.handle_atom(left, item)
            return True

        # f-strings
        if isinstance(right, JoinedStr):
            for i, fvalue in enumerate(right.values):
                if isinstance(fvalue, FormattedValue):
                    right.values[i].value, _ = self.handle_atom(left, fvalue.value)
            return True

        # Comprehensions and Generators
        # [x for x in _]
        if isinstance(right, (ListComp, SetComp, DictComp, GeneratorExp)):
            for i, gen in enumerate(right.generators):
                gen.iter, _ = self.handle_atom(left, gen.iter)
            return True

        return False

    def visit_BinOp(self, node: BinOp) -> AST:
        """
        Visitor method for BinOps. Returns the AST that takes the place of the input expression.
        """
        left, op, right = self.visit(node.left), node.op, node.right
        if isinstance(op, RShift):

            if self.handle_node(left, right):
                return right

            # Convert function name / lambda etc without braces into call
            if isinstance(right, Call):

                # Rewrite a >> f(...) as f(..., a)
                right.args.append(left)
                return right

            # Rewrite a >> f as f(a)
            return Call(
                func=right,
                args=[left],
                keywords=[],
                starargs=None,
                kwargs=None,
                lineno=right.lineno,
                col_offset=right.col_offset,
            )

        return node


# pylint: disable=exec-used
def pipes(func_or_class):
    """
    Enables the pipe operator in the decorated function or method
    """
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

    # Update name of function or class to compile
    # tree.body[0].name = decorated_name

    # remove the pipe decorator so that we don't recursively
    # call it again. The AST node for the decorator will be a
    # Call if it had braces, and a Name if it had no braces.
    # The location of the decorator function name in these
    # nodes is slightly different.
    tree.body[0].decorator_list = [
        dec
        for dec in tree.body[0].decorator_list
        if isinstance(dec, Call)
        and dec.func.id != "pipes"
        or isinstance(dec, Name)
        and dec.id != "pipes"
    ]

    # Apply the visit_BinOp transformation
    tree = _PipeTransformer().visit(tree)

    # now compile the AST into an altered function or class definition
    code = compile(tree, filename=(ctx["__file__"] if "__file__" in ctx else "repl"), mode="exec")

    # and execute the definition in the original context so that the
    # decorated function can access the same scopes as the original
    exec(code, ctx)

    # return the modified function or class - original is never called
    return ctx[tree.body[0].name]
