
from ast import Call, parse, Name, NodeTransformer, LShift, RShift, \
    increment_lineno, walk, Attribute, BinOp, dump, List, Tuple, Starred
from inspect import getsource, isclass, stack
from itertools import takewhile
from textwrap import dedent

PLACEHOLDER = '_'

# def all_left(node):



class MyTransform(NodeTransformer):
    def substitute(L, i, sub):
        item = L[i]

        if isinstance(item, Name):
            if item.id == PLACEHOLDER:
                L[i] = self.visit(sub)

        if isinstance(item, Starred):
            if isinstance(item.value, Name):
                if item.value.id == PLACEHOLDER:
                    item.value = self.visit(sub)

    def visit_BinOp(self, node):
        print(dump(node, indent=4))
        print('---')
        if isinstance(node.op, (LShift, RShift)):
            # if isinstance(node.right, Attribute):
            #     if isinstance(node.right.value, Name):
            #         if node.right.value.id == PLACEHOLDER:
            #             node.right.value = node.left
            #             return self.visit(node.right)
            if isinstance(node.right, BinOp):
                if isinstance(node.right.left, Name):
                    if node.right.left.id == PLACEHOLDER:
                        node.right.left = self.visit(node.left)
                        return node.right
                if isinstance(node.right.right, Name):
                    if node.right.right.id == PLACEHOLDER:
                        node.right.right = self.visit(node.left)
                        return node.right
            if isinstance(node.right, Call):

                # _.func
                if isinstance(node.right.func, Attribute):
                    if isinstance(node.right.func.value, Name):
                        if node.right.func.value.id == PLACEHOLDER:
                            node.right.func.value = self.visit(node.left)
                            return node.right

                # func(x, y, _, z)
                for i, arg in enumerate(node.right.args):
                    if isinstance(arg, Name):
                        if arg.id == PLACEHOLDER:
                            node.right.args[i] = self.visit(node.left)
                            return node.right

            if isinstance(node.right, (List, Tuple)):
                for i, el in enumerate(node.right.elts):
                    if isinstance(el, Name):
                        if el.id == PLACEHOLDER:
                            node.right.elts[i] = self.visit(node.left)
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

    print(dump(tree))

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

@pipes
def ff():
    1 >> _+10 >> _*6 >> print(55, _, 77)

ff()

@pipes
def qq():
    [1, 2, 3] >> [1, *_] >> print(1, _, 5)

qq()
