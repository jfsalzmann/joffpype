"""Implements an @pipes operator that transforms the >> operator to act similarly to Elixir pipes. change by joff: first instead of last argument"""


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
    Lambda,
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
    dump,
    increment_lineno,
    parse,
    walk,
)
from inspect import getsource, isclass, isfunction, stack
from itertools import takewhile
from textwrap import dedent

SUB_IDENT: str = "__"


class _PipeTransformer(NodeTransformer):
    def handle_atom(self, left: AST, atom: AST) -> typing.Tuple[AST, bool]:
        """
        Handle an "atom".
        Recursively replaces all instances of `_` / `*_` / `**_`
        Will call into `self.handle_node` if necessary
        Returns the new AST and whether or not any modifications were made to the AST
        """
        if isinstance(atom, Name):
            if atom.id == SUB_IDENT:
                return left, True
            else:
                return atom, False
        elif isinstance(atom, Starred):
            atom.value, mod = self.handle_atom(left, atom.value)
            return atom, mod

        # We set implicit=False here so that no nested calls get implicit arguments
        return self.handle_node(left, atom, False)

    # pylint: disable=too-many-branches, too-many-return-statements, invalid-name
    def handle_node(self, left: AST, right: AST, implicit=True) -> typing.Tuple[AST, bool]:
        """
        Recursively handles AST substitutions
        :param left: Nominally the left side of a BinOp. This is substitued into `right`
        :param right: Nominally the right side of a BinOp. Target of substitutions.
        :param implicit: Determines if the transformer is allowed to append arguments implicitly to function calls, and convert attribute/names/lambdas into calls
        :returns: The transformed AST, and whether or not any modifications were made to the AST
        """

        # We have to explicitly handle the case
        # Where the right side is "_"
        # In that case we just return `left`
        # So that it is substituted
        if isinstance(right, Name):
            if right.id == SUB_IDENT:
                return left, True

        # _.attr or _[x]
        if isinstance(right, (Attribute, Subscript)):
            right.value, mod = self.handle_atom(left, right.value)

            # If we modified the attribute (this doesn't really apply to subscripts)
            # Then we can return the right side, however if we didn't it may need to be
            # Transformed into a function call
            # e.g. 5 >> Class.method
            if mod:
                return right, True

        if isinstance(right, Lambda):
            right.expr, mod = self.handle_atom(left, right.body)
            # return right, mod

        # _ + x
        # x + _
        if isinstance(right, BinOp):
            mod = False
            right.left, m = self.handle_atom(left, right.left)
            mod |= m
            right.right, m = self.handle_atom(left, right.right)
            mod |= m
            return right, mod

        if isinstance(right, Call):

            # _.func
            if isinstance(right.func, Attribute):

                # True if we substituted into _.func
                # This way we can sub arguments, for stuff like _.func(_)
                # But avoid adding the implicit argument
                right.func.value, modified = self.handle_atom(left, right.func.value)
            else:
                modified = False

            for i, arg in enumerate(right.args):
                right.args[i], mod = self.handle_atom(left, arg)
                modified |= mod

            for i, arg in enumerate(right.keywords):
                right.keywords[i].value, mod = self.handle_atom(left, arg.value)
                modified |= mod

            # If we didn't modify any arguments
            # Then we need to insert the left side
            # Into the arguments, if implicit is allowed
            if not modified and implicit:
                right.args.insert(0,left) ####### changed
                modified = True

            return right, modified

        # Lists, Tuples, and Sets
        if isinstance(right, (List, Tuple, Set)):
            mod = False
            for i, el in enumerate(right.elts):
                right.elts[i], m = self.handle_atom(left, el)
                mod |= m
            return right, mod

        # Dictionaries
        if isinstance(right, Dict):
            mod = False
            for col in [right.keys, right.values]:
                for i, item in enumerate(col):
                    col[i], m = self.handle_atom(left, item)
                    mod |= m
            return right, mod

        # f-strings
        if isinstance(right, JoinedStr):
            mod = False
            for i, fvalue in enumerate(right.values):
                if isinstance(fvalue, FormattedValue):
                    right.values[i].value, m = self.handle_atom(left, fvalue.value)
                    mod |= m
            return right, mod

        # Comprehensions and Generators
        # [x for x in _]
        if isinstance(right, (ListComp, SetComp, DictComp, GeneratorExp)):
            mod = False

            # handle [THIS for .. in ..] part of the comprehension
            # Special case for dictionaries because of {THESE : THESE for .. in ..}
            if isinstance(right, DictComp):
                right.key, m = self.handle_atom(left, right.key)
                mod |= m
                right.value, m = self.handle_atom(left, right.value)
                mod |= m
            else:
                right.elt, m = self.handle_atom(left, right.elt)
                mod |= m

            for i, gen in enumerate(right.generators):
                gen.iter, m = self.handle_atom(left, gen.iter)
                mod |= m

            return right, mod

        if isinstance(right, (Name, Attribute, Lambda)) and implicit:
            # If nothing else, we assume that we need to convert the right side into a function call
            # e.g. 5 >> print
            # This will break if the symbol is not callable, as is expected
            return (
                Call(
                    func=right,
                    args=[left],
                    keywords=[],
                    starargs=None,
                    kwargs=None,
                    lineno=right.lineno,
                    col_offset=right.col_offset,
                ),
                False,
            )

        return right, False

    def visit_BinOp(self, node: BinOp) -> AST:
        """
        Visitor method for BinOps. Returns the AST that takes the place of the input expression.
        """
        left, op, right = self.visit(node.left), node.op, node.right
        if isinstance(op, RShift):
            ast, _ = self.handle_node(left, right)
            return ast
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

    # now compile the AST into an altered function or class definition
    code = compile(tree, filename=(ctx["__file__"] if "__file__" in ctx else "repl"), mode="exec")

    # and execute the definition in the original context so that the
    # decorated function can access the same scopes as the original
    exec(code, ctx)

    # return the modified function or class - original is never called
    return ctx[tree.body[0].name]
