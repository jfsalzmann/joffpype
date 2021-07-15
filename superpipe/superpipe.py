"""Implements an @pipes operator that transforms the >> operator to act similarly to Elixir pipes"""


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
    Lambda,
    dump
)
from inspect import getsource, isclass, isfunction, stack
from itertools import takewhile
from textwrap import dedent

SUB_IDENT: str = "_"



class _PipeTransformer(NodeTransformer):
    def handle_atom(self, left: AST, atom: AST) -> typing.Tuple[AST, bool]:
        """
        Handle an "atom".
        Recursively replaces all instances of `_` / `*_` / `**_`
        Will call into `self.handle_node` if necessary
        """
        if isinstance(atom, Name):
            if atom.id == SUB_IDENT:
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

        # We have to explicitly handle the case
        # Where the right side is "_"
        # In that case we just return `left`
        # So that it is substituted
        if isinstance(right, Name):
            if right.id == SUB_IDENT:
                return left

        # _.attr or _[x]
        if isinstance(right, (Attribute, Subscript)):
            right.value, mod = self.handle_atom(left, right.value)

            # If we modified the attribute (this doesn't really apply to subscripts)
            # Then we can return the right side, however if we didn't it may need to be
            # Transformed into a function call
            # e.g. 5 >> Class.method
            if mod:
                return right

        # _ + x
        # x + _
        if isinstance(right, BinOp):
            if isinstance(right.op, RShift):
                return self.visit_BinOp(right)
            right.left, _ = self.handle_atom(left, right.left)
            right.right, _ = self.handle_atom(left, right.right)
            return right

        # if isinstance(right, Lambda):
        #     right.body = self.handle_atom(left, right.body)
        #     return right

        if isinstance(right, Call):

            # _.func
            if isinstance(right.func, Attribute):
                right.func.value, mod = self.handle_atom(left, right.func.value)

                # Only exit if we substituted the value of the call
                # Otherwise, we need to process the arguments
                if mod:
                    return right

            modified = False

            for i, arg in enumerate(right.args):
                right.args[i], mod = self.handle_atom(left, arg)
                modified |= mod

            for i, arg in enumerate(right.keywords):
                right.keywords[i].value, mod = self.handle_atom(left, arg.value)
                modified |= mod

            # If we didn't modify any arguments
            # Then we need to insert the left side
            # Into the arguments
            if not modified:
                right.args.append(left)

            return right

        # Lists, Tuples, and Sets
        if isinstance(right, (List, Tuple, Set)):
            for i, el in enumerate(right.elts):
                right.elts[i], _ = self.handle_atom(left, el)
            return right

        # Dictionaries
        if isinstance(right, Dict):
            for col in [right.keys, right.values]:
                for i, item in enumerate(col):
                    col[i], _ = self.handle_atom(left, item)
            return right

        # f-strings
        if isinstance(right, JoinedStr):
            for i, fvalue in enumerate(right.values):
                if isinstance(fvalue, FormattedValue):
                    right.values[i].value, _ = self.handle_atom(left, fvalue.value)
            return right

        # Comprehensions and Generators
        # [x for x in _]
        if isinstance(right, (ListComp, SetComp, DictComp, GeneratorExp)):
            for i, gen in enumerate(right.generators):
                gen.iter, _ = self.handle_atom(left, gen.iter)
            return right

        # If nothing else, we assume that we need to convert the right side into a function call
        # e.g. 5 >> print
        # This will break if the symbol is not callable, as is expected
        return Call(
            func=right,
            args=[left],
            keywords=[],
            starargs=None,
            kwargs=None,
            lineno=right.lineno,
            col_offset=right.col_offset,
        )

    def visit_BinOp(self, node: BinOp) -> AST:
        """
        Visitor method for BinOps. Returns the AST that takes the place of the input expression.
        """
        left, op, right = self.visit(node.left), node.op, node.right
        if isinstance(op, RShift):
            return self.handle_node(left, right)
        return node


def is_pipes_decorator(dec: AST) -> bool:
    """
    Determines if `dec` is one of our decorators.
    The check is fairly primitive and relies upon things being named as we expect them.
    If someone were to do a `from superpipe import pipes as ..` this function would break.
    :param dec: An AST node to check
    """
    if isinstance(dec, Name):
        return dec.id == "pipes"
    if isinstance(dec, Attribute):
        if isinstance(dec.value, Name):
            return dec.value.id == "superpipe" and dec.attr == "pipes"
    if isinstance(dec, Call):
        return is_pipes_decorator(dec.func)
    return False


# pylint: disable=exec-used
def pipes(func_or_class):
    """
    Enables the pipe operator in the decorated function, method, or class
    """
    if isclass(func_or_class):
        decorator_frame = stack()[1]
        ctx = decorator_frame[0].f_locals
        first_line_number = decorator_frame[2]
    elif isfunction(func_or_class):
        ctx = func_or_class.__globals__
        first_line_number = func_or_class.__code__.co_firstlineno
    else:
        raise ValueError(f"@pipes: Expected function or class. Got: {type(func_or_class)}")

    source = getsource(func_or_class)

    # AST data structure representing parsed function code
    tree = parse(dedent(source))

    print(dump(tree, indent=4))

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
    tree.body[0].decorator_list = [
        dec for dec in tree.body[0].decorator_list if not is_pipes_decorator(dec)
    ]

    # Apply the visit_BinOp transformation
    tree = _PipeTransformer().visit(tree)

    print(dump(tree, indent=4))

    # now compile the AST into an altered function or class definition
    code = compile(tree, filename=(ctx["__file__"] if "__file__" in ctx else "repl"), mode="exec")

    # and execute the definition in the original context so that the
    # decorated function can access the same scopes as the original
    exec(code, ctx)

    # return the modified function or class - original is never called
    return ctx[tree.body[0].name]
