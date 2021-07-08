
from ast import Call, parse, Name, NodeTransformer, LShift, RShift, \
    increment_lineno, walk, Attribute, BinOp, dump, List, Tuple, Starred, JoinedStr
from inspect import getsource, isclass, stack
from itertools import takewhile
from textwrap import dedent

SUB_IDENT = '_'

def check_name(item):
    if isinstance(item, Name):
        if item.id == SUB_IDENT:
            return True
    return False

def check_starred(item):
    if isinstance(item, Starred):
        return check_name(item.value)


class MyTransform(NodeTransformer):
    
    def handle_tuple_list(self, L, replace):
        if isinstance(L, (Tuple, List)):
            for i, el in enumerate(L.elts):
                if check_name(el):
                    L.elts[i] = self.visit(replace)
                    return True
                if check_starred(el):
                    L.elts[i].value = self.visit(replace)
                    return True
        return False

    def visit_BinOp(self, node):
        # print(dump(node, indent=4))
        # print('---')
        if isinstance(node.op, (LShift, RShift)):
            # if isinstance(node.right, Attribute):
            #     if isinstance(node.right.value, Name):
            #         if node.right.value.id == PLACEHOLDER:
            #             node.right.value = node.left
            #             return self.visit(node.right)
            if isinstance(node.right, BinOp):
                if isinstance(node.right.left, Name):
                    if node.right.left.id == SUB_IDENT:
                        node.right.left = self.visit(node.left)
                        return node.right
                if isinstance(node.right.right, Name):
                    if node.right.right.id == SUB_IDENT:
                        node.right.right = self.visit(node.left)
                        return node.right
            if isinstance(node.right, Call):

                # _.func
                if isinstance(node.right.func, Attribute):
                    if isinstance(node.right.func.value, Name):
                        if node.right.func.value.id == SUB_IDENT:
                            node.right.func.value = self.visit(node.left)
                            return node.right

                once = False

                # func(x, y, _, z)
                for i, arg in enumerate(node.right.args):
                    if check_name(arg):
                        node.right.args[i] = self.visit(node.left)
                        once = True
                    
                    if check_starred(arg):
                        node.right.args[i].value = self.visit(node.left)
                        once = True

                if once:
                    return node.right

            # Lists and Tuples
            if isinstance(node.right, (List, Tuple)):
                once = False
                for i, el in enumerate(node.right.elts):

                    # 5 >> [x, y, _, z]
                    if check_name(el):
                        node.right.elts[i] = self.visit(node.left)
                        once = True

                    # (1, 2) >> [x, y, *_, z]
                    if check_starred(el):
                        node.right.elts[i].value = self.visit(node.left)
                        once = True

                    # if isinstance(el, BinOp):
                    #     self.visit(el)

                if once:
                    return node.right

            if isinstance(node.right, JoinedStr):
                for i, fvalue in enumerate(node.right.values):
                    if check_name(fvalue.value):
                        node.right.values[i].value = self.visit(node.left)
                        return node.right
                    if check_starred(fvalue.value):
                        node.right.values[i].value.value = self.visit(node.left)
                        return node.right

            # Convert function name / lambda etc without braces into call
            if not isinstance(node.right, Call):
                return self.visit(Call(
                    func=node.right,
                    args=[node.left],
                    keywords=[],
                    starargs=None,
                    kwargs=None,
                    lineno=node.right.lineno,
                    col_offset=node.right.col_offset
                ))
            
            # Rewrite a >> b(...) as b(a, ...)
            node.right.args.insert(
                0 if isinstance(node.op, RShift) else len(node.right.args),
                node.left)
            return self.visit(node.right)
        else:
            return node


# from pipeop import pipes

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

    # Update name of function or class to compile
    #tree.body[0].name = decorated_name

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

    # print(dump(tree))

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

# @pipes
# def foo():
#     return [1,2,3,4,5] << filter(lambda x: x%2==0) >> list >> _.index(4)

# print(foo())

# @pipes
# def baz():
#     return 5 >> _.__mul__(2) >> _.bit_length()

# print(baz())

# @pipes
# def bar():
#     return 1 >> (_, 5)

# @pipes
# def ff():
#     1 >> _+10 >> _*6 >> print(55, _, 77)

# ff()

# @pipes
# def qq():
#     [1, 2, 3] >> [1, *_] >> print(1, *_, 5)

# qq()

# @pipes
# def tt():
#     10 >> _**3>> [_] >> print

# tt()

# @pipes
# def ee():
#     10 >> [1, _, 100] >> f"the list: {_}" >> print

# ee()

# pylint: disable=undefined-variable
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

pogchamp()

@pipes
def pp():
    5 >> [_, _, 7, _ + 7] >> print

pp()