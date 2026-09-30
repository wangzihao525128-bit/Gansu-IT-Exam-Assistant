r"""代码安全沙箱 —— AST 静态检查（需求文档 Step 2）。

放行「考试用得上」的东西：常用内置函数 + 安全模块；
拦下五类危险操作：

1. 危险模块：os / sys / subprocess / socket / requests / shutil / ctypes ...
2. 文件读写：open(...)
3. 动态执行：eval / exec / compile / __import__
4. 内部属性：__globals__、__class__ 等下划线开头的属性（防止绕过沙箱）
5. **用 getattr 的字符串参数绕开第 4 条**：``getattr(print, "__self__")`` 里的
   属性名是字符串常量，AST 上根本没有 Attribute 节点，第 4 条看不见它。

第 5 条是**真实存在过的漏洞，别再删掉这条检查**：白名单里的 ``print`` 是真的
内置 print 对象，它身上挂着 ``__self__``，指向真正的 builtins 模块。
学生只要三行：

    b = getattr(print, "__self__")
    d = getattr(b, "__dict__")
    d["__import__"]("os").system("...")

就能把整张白名单一次性废掉（实测过：``check_code`` 全绿，然后真的拿到了 os）。
所以现在这段的防线分两层，缺一不可：

* 静态检查拦下 ``getattr(x, "__xxx__")`` 这种**字符串写法**（本模块）；
* 运行时把真 getattr 换成 :func:`safe_getattr`（只放行公开属性），
  并且不再把真的 ``print`` 对象交给学生代码（code_executor 两个后端都换了）。

**定位要说清楚**：这是教学沙箱，不是安全隔离。它挡得住会考范围外的「手滑」
（删文件、连网络、写死循环），挡不住铁了心研究 Python 内省的人。
真要强隔离得上容器 / seccomp —— 见 完善\Step交付清单.md 里的同名说明。
"""

from __future__ import annotations

import ast

MAX_CODE_LENGTH = 100_000

# 允许导入的模块：全部是纯计算 / 纯文本，没有任何系统能力
SAFE_MODULES = frozenset(
    {
        "math",
        "random",
        "datetime",
        "string",
        "collections",
        "time",
        "statistics",
        "cmath",
        "fractions",
        "decimal",
        "itertools",
        "functools",
        "heapq",
        "bisect",
        "re",
    }
)

# 允许使用的内置函数名（子进程里按这张表真正构造受限环境）
SAFE_BUILTIN_NAMES = frozenset(
    {
        "print", "len", "range", "int", "float", "str", "bool", "list", "dict", "set", "tuple",
        "frozenset", "sum", "min", "max", "abs", "round", "sorted", "reversed", "enumerate",
        "zip", "map", "filter", "any", "all", "type", "isinstance", "issubclass", "divmod",
        "pow", "chr", "ord", "bin", "oct", "hex", "format", "iter", "next", "slice", "repr",
        "getattr", "callable", "input",
    }
)

# 直接禁用的内置函数
FORBIDDEN_NAMES = frozenset(
    {"open", "eval", "exec", "compile", "__import__", "globals", "locals", "vars", "breakpoint", "exit", "quit", "help"}
)

MODULE_TIPS = {
    "os": "它能删除文件、控制系统，题目里用不到",
    "sys": "它能修改解释器设置、退出程序",
    "subprocess": "它能调用系统命令，属于危险操作",
    "socket": "它能连接网络，属于危险操作",
    "requests": "它能连接网络，属于危险操作",
    "urllib": "它能连接网络，属于危险操作",
    "http": "它能连接网络，属于危险操作",
    "shutil": "它能复制、删除文件，属于危险操作",
    "ctypes": "它能直接调用系统函数，属于危险操作",
    "multiprocessing": "它能创建新进程，属于危险操作",
    "threading": "它能创建新线程，容易把程序卡死",
    "pathlib": "它能读写文件，属于危险操作",
    "pickle": "它能读写文件，属于危险操作",
    "builtins": "它能拿到 open、eval 等危险函数",
    "importlib": "它能动态加载任意模块，属于危险操作",
    "webbrowser": "它能打开网页或本地程序，属于危险操作",
}

NAME_TIPS = {
    "open": "：它能读取或删除你电脑上的文件",
    "eval": "：它能把你写的字符串当成代码执行",
    "exec": "：它能把你写的字符串当成代码执行",
    "compile": "：它和 eval / exec 一样危险",
    "__import__": "：它是 import 的底层写法，等于绕过了安全检查",
    "globals": "：它能拿到整个运行环境，属于危险操作",
    "locals": "：它能拿到整个运行环境，属于危险操作",
    "vars": "：它能拿到整个运行环境，属于危险操作",
    "breakpoint": "：调试用不到",
    "exit": "：会直接关掉程序",
    "quit": "：会直接关掉程序",
    "help": "：调试用不到",
}

SYNTAX_HINTS = (
    ("indent", "缩进要一致：同一层的代码前面空格数要一样，建议统一用 4 个空格。"),
    ("unterminated", "字符串或注释的引号没有成对闭合。"),
    ("never closed", "括号没有成对闭合，检查一下 ( [ { 是否都写全了。"),
    ("expected ':'", "if / for / while / def 那一行末尾要加冒号 :"),
    ("assignment", "等号左边必须是一个变量名，不能是常量、函数或表达式。"),
    ("invalid", "检查这一行的括号、冒号、引号是否成对。"),
)
DEFAULT_SYNTAX_HINT = "对照代码示例检查一下这一行的写法。"


class SecurityError(Exception):
    """代码没通过安全检查；str(exc) 就是可以直接展示给学生看的中文提示。"""


def _line_of(node) -> int:
    return getattr(node, "lineno", 0) or 0


def _syntax_hint(message: str) -> str:
    for keyword, hint in SYNTAX_HINTS:
        if keyword in message:
            return hint
    return DEFAULT_SYNTAX_HINT


def check_syntax(code: str) -> ast.Module:
    """解析代码；有语法错误就抛出中文提示。"""
    try:
        return ast.parse(code)
    except SyntaxError as exc:
        line = exc.lineno or 0
        detail = exc.msg or "写法不对"
        raise SecurityError(f"第 {line} 行语法有问题：{detail}。{_syntax_hint(detail)}") from exc
    except ValueError as exc:  # 例如源码里混进了空字符
        raise SecurityError(f"代码里有不能识别的字符：{exc}") from exc


def _check_module(node, full_name: str) -> None:
    root = full_name.split(".")[0]
    if root not in SAFE_MODULES:
        tip = MODULE_TIPS.get(root, "它不属于会考范围，可以换成 math、random 等安全模块。")
        raise SecurityError(f"第 {_line_of(node)} 行：安全提醒，不能导入 {full_name} 模块——{tip}。")


GETATTR_TIP = "getattr 的属性名不能以下划线开头，也不能是 open / eval 这类危险函数。"


def _getattr_target(node: ast.Call) -> ast.expr | None:
    """取出 ``getattr(obj, X)`` 的第二个参数（属性名）；写法不标准就返回 None。"""
    if len(node.args) >= 2:
        return node.args[1]
    for keyword in node.keywords:
        if keyword.arg == "name":
            return keyword.value
    return None


def _check_getattr_call(node: ast.Call) -> None:
    """拦下 ``getattr(obj, "__self__")`` 这种「用字符串绕开属性检查」的写法。

    只检查**字面量**字符串。变量形式的属性名（``getattr(o, name)``）静态查不出来，
    那种情况由运行时的 :func:`safe_getattr` 兜住——两层都要在。
    """
    target = _getattr_target(node)
    if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
        return
    name = target.value
    if name.startswith("_"):
        raise SecurityError(
            f"第 {_line_of(node)} 行：安全提醒，不能用 getattr 读取 {name!r} 这类内部属性。{GETATTR_TIP}"
        )
    if name in FORBIDDEN_NAMES:
        raise SecurityError(
            f"第 {_line_of(node)} 行：安全提醒，不能用 getattr 取到 {name}{NAME_TIPS.get(name, '')}。"
        )


def check_code(code: str) -> ast.Module:
    """完整的静态安全检查；通过则返回语法树，否则抛 SecurityError。"""
    if len(code) > MAX_CODE_LENGTH:
        raise SecurityError("代码太长了（超过 10 万个字符），请精简后再运行。")

    tree = check_syntax(code)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(node, alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 形如 from . import xxx
                raise SecurityError(f"第 {_line_of(node)} 行：不能使用相对导入，请直接写 import 模块名。")
            _check_module(node, node.module or "")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise SecurityError(f"第 {_line_of(node)} 行：安全提醒，不能使用 {node.id}{NAME_TIPS.get(node.id, '')}。")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            raise SecurityError(
                f"第 {_line_of(node)} 行：安全提醒，不能访问 {node.attr} 这类以下划线开头的内部属性。"
            )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            _check_getattr_call(node)
    return tree


def safe_getattr(obj, name, *default):
    """运行时版 getattr：只放行「公开」属性，堵掉 ``getattr(x, "__self__")`` 这条路。

    为什么必须有它、而且不能把真的 getattr 交给学生代码：
    真 getattr 会老老实实把 ``__self__`` / ``__globals__`` / ``__dict__`` 这类后门
    交出去，而内置对象上恰好挂着通往整个 builtins 的引用——白名单就废了。
    这里把「以下划线开头」和 FORBIDDEN_NAMES 里的名字直接拒掉，
    剩下的公开属性照常返回，所以学生的正常用法（``getattr(d, "get", None)``）不受影响。

    子进程 runner 里有一份等价实现（那个脚本必须自包含，不能 import 本模块），
    两边由 tools\test_sandbox.py 的逃逸回归用例同时盯着。
    """
    if not isinstance(name, str):
        raise TypeError("getattr 的属性名必须是字符串")
    if name.startswith("_") or name in FORBIDDEN_NAMES:
        raise AttributeError(f"安全限制：不允许访问 {name}")
    if default:
        return getattr(obj, name, *default)
    return getattr(obj, name)


def is_safe(code: str) -> bool:
    """只关心能不能通过检查时用它。"""
    try:
        check_code(code)
    except SecurityError:
        return False
    return True


def safe_modules_text() -> str:
    """给 UI 展示用：当前允许使用哪些模块。"""
    return "、".join(sorted(SAFE_MODULES))
