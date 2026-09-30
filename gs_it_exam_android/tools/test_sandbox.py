r"""沙箱单元测试（需求文档 Step 2）。

    python tools\test_sandbox.py

覆盖六件事：
1. 正常代码能跑通、输出正确；
2. input() 能注入测试数据；
3. 危险操作全部被拦下（os.system / open / eval / __import__ / 沙箱逃逸）；
4. 死循环能超时强制停止；
5. 报错是中文提示，并且带行号；
6. 手机端 Pyodide 脚本能正确生成与解析。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import code_executor as executor  # noqa: E402
from core import security  # noqa: E402


class TestSecurityCheck(unittest.TestCase):
    def test_normal_code_passes(self):
        for code in [
            "a = 1 + 1\nprint(a)",
            "import math\nprint(math.pi)",
            "for i in range(3):\n    print(i)",
            "print([i * i for i in range(5)])",
            "name = input()\nprint('你好', name)",
            "print(f'{1 + 1} 等于 2')",
            "d = {'a': 1}\nfor k, v in d.items():\n    print(k, v)",
        ]:
            self.assertTrue(security.is_safe(code), f"不该拦：{code!r}")

    def test_dangerous_imports_blocked(self):
        for code in [
            "import os\nos.system('dir')",
            "import sys",
            "import subprocess",
            "import socket",
            "import requests",
            "import shutil",
            "import ctypes",
            "from os import system",
            "from subprocess import run",
            "import os.path",
        ]:
            with self.assertRaises(security.SecurityError, msg=code):
                security.check_code(code)

    def test_file_and_dynamic_blocked(self):
        for code in [
            "open('a.txt')",
            "f = open('a.txt', 'w')",
            "eval('1 + 1')",
            "exec('print(1)')",
            "compile('x = 1', '', 'exec')",
            "__import__('os').system('dir')",
            "print(globals())",
        ]:
            with self.assertRaises(security.SecurityError, msg=code):
                security.check_code(code)

    def test_sandbox_escape_blocked(self):
        for code in [
            "print((1).__class__)",
            "x = ().__class__.__bases__[0].__subclasses__()",
            "print(globals()['__builtins__'])",
        ]:
            with self.assertRaises(security.SecurityError, msg=code):
                security.check_code(code)

    def test_getattr_dunder_string_is_blocked(self):
        """回归用例：``getattr(x, "__self__")`` 曾经能一次性废掉整张白名单。

        真实漏洞（实测过）：白名单里的 ``print`` 是真的内置 print 对象，它身上的
        ``__self__`` 指向 builtins 模块，于是三行就能拿到 ``open`` / ``__import__``：

            b = getattr(print, "__self__")
            d = getattr(b, "__dict__")
            d["__import__"]("os").system(...)

        属性名是字符串常量，AST 上没有 Attribute 节点，早先那条「不能访问
        ``__xxx__``」的检查完全看不见它。
        """
        for code in [
            'print(getattr(print, "__self__"))',
            'print(getattr(print, "__dict__"))',
            'getattr(1, "__class__")',
            'getattr(type(1), "__subclasses__")()',
            'getattr(object, "open")',
            'getattr(print, name="__globals__")',
        ]:
            with self.assertRaises(security.SecurityError, msg=code):
                security.check_code(code)

    def test_normal_getattr_still_allowed(self):
        """堵漏洞不能把学生的正常用法一起堵掉。"""
        for code in [
            "d = {'a': 1}\nprint(getattr(d, 'get')('a'))",
            "print(getattr(d, 'x', 0))",
            "print(getattr('abc', 'upper')())",
        ]:
            self.assertTrue(security.is_safe(code), f"不该拦：{code!r}")

    def test_runtime_safe_getattr_blocks_private_names(self):
        """运行时那一层（security.safe_getattr）：静态检查看不到变量属性名，靠它兜。"""
        with self.assertRaises(AttributeError):
            security.safe_getattr(print, "__self__")
        with self.assertRaises(AttributeError):
            security.safe_getattr(print, "open")
        # 公开属性照常放行，第三个参数当默认值用
        self.assertEqual(security.safe_getattr({"a": 1}, "get", None)("a"), 1)
        self.assertEqual(security.safe_getattr({"a": 1}, "nope", 0), 0)


    def test_syntax_error_message_is_chinese(self):
        with self.assertRaises(security.SecurityError) as ctx:
            security.check_code("if True:\n    print(1)\n  print(2)")
        self.assertIn("缩进", str(ctx.exception))
        with self.assertRaises(security.SecurityError) as ctx:
            security.check_code("if True\n    print(1)")
        self.assertIn("冒号", str(ctx.exception))

    def test_message_points_to_line(self):
        with self.assertRaises(security.SecurityError) as ctx:
            security.check_code("import math\nimport os\n")
        self.assertIn("第 2 行", str(ctx.exception))

    def test_safe_modules_text(self):
        self.assertIn("math", security.safe_modules_text())


class TestLocalExecutor(unittest.TestCase):
    def test_hello(self):
        result = executor.run_code("print('你好，会考')")
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output.strip(), "你好，会考")
        self.assertEqual(result.error, "")

    def test_math_import_works(self):
        result = executor.run_code("import math\nprint(round(math.sqrt(16)))")
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output.strip(), "4")

    def test_input_injection(self):
        result = executor.run_code("a = input()\nb = input()\nprint(int(a) + int(b))", test_inputs=["3", "4"])
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output.strip(), "7")

    def test_chinese_output_round_trip(self):
        result = executor.run_code("print('甘肃省信息技术会考')")
        self.assertTrue(result.success, result.error)
        self.assertIn("甘肃省信息技术会考", result.output)

    def test_dangerous_code_blocked_before_running(self):
        result = executor.run_code("import os\nos.system('echo hacked')")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "security")
        self.assertIn("不能导入", result.error)
        self.assertEqual(result.output, "")

    def test_timeout_stops_infinite_loop(self):
        started = time.perf_counter()
        result = executor.run_code("while True:\n    pass", timeout=1.0)
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "timeout")
        self.assertIn("死循环", result.error)
        self.assertLess(time.perf_counter() - started, 8.0)

    def test_zero_division_is_friendly(self):
        result = executor.run_code("a = 1\nb = 0\nprint(a / b)")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "ZeroDivisionError")
        self.assertIn("除数不能是 0", result.error)
        self.assertEqual(result.line, 3)

    def test_name_error_is_friendly(self):
        result = executor.run_code("print(total)")
        self.assertFalse(result.success)
        self.assertIn("还不存在的名字", result.error)

    def test_output_before_error_is_kept(self):
        result = executor.run_code("print('第一行')\nprint(1 / 0)")
        self.assertFalse(result.success)
        self.assertIn("第一行", result.output)

    def test_import_gate_blocks_other_modules(self):
        # 绕过 AST 直接进沙箱，白名单之外的模块依然被 import 闸门挡住
        result = executor._run_local("import flet\nprint('imported')", None, 10.0)
        self.assertFalse(result.success)
        self.assertIn("安全限制", result.error)

    def test_pythonpath_cannot_hijack_module(self):
        # 把 PYTHONPATH 指向放了假 math.py 的目录，子进程也只会用标准库的 math
        hijack = Path(tempfile.mkdtemp(prefix="gs_hijack_"))
        (hijack / "math.py").write_text("print('HIJACKED')\n", encoding="utf-8")
        old = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = str(hijack)
        try:
            result = executor._run_local("import math\nprint('ok', round(math.sqrt(9)))", None, 10.0)
        finally:
            if old is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = old
            shutil.rmtree(hijack, ignore_errors=True)
        self.assertTrue(result.success, result.error)
        self.assertNotIn("HIJACKED", result.output)
        self.assertIn("ok 3", result.output)

    def test_result_dict_shape(self):
        data = executor.run_code("print(1)").as_dict()
        self.assertTrue(data["success"])
        # 这里原来写的是 assertEqual(data["stdout"], data["output"])：
        # 两个字段都由 RunResult.output 赋值，永远相等，等于什么都没测。
        self.assertEqual(data["output"], "1\n")
        self.assertEqual(data["stdout"], "1\n")
        self.assertIn("duration", data)
        self.assertIn("error_type", data)

    def test_getattr_escape_is_blocked_at_runtime(self):
        """回归用例：用变量拼出属性名，绕过静态检查后，子进程里也要拦住。

        静态检查只看字面量字符串，所以 ``"__" + "self__"`` 这种写法它能放行
        （这是刻意的：字面量查得准，变量查不到）。真正兜住它的是运行时把真
        getattr 换成了 security.safe_getattr——这条用例就是盯着那一层别被改回去。
        """
        code = (
            'name = "__" + "self__"\n'
            "b = getattr(print, name)\n"
            'print("ESCAPED", b)\n'
        )
        self.assertTrue(security.is_safe(code), "变量拼写法本来就该被静态检查放行")
        result = executor.run_code(code)
        self.assertFalse(result.success)
        self.assertNotIn("ESCAPED", result.output)
        self.assertIn("安全限制", result.error)

    def test_builtins_module_cannot_be_reached(self):
        """就算绕过了静态检查，也拿不到真正的 builtins 模块。"""
        code = (
            "g = getattr\n"
            'mod = g(print, "__" + "self__")\n'
            'print("LEAK", mod)\n'
        )
        result = executor.run_code(code)
        self.assertFalse(result.success)
        self.assertNotIn("LEAK", result.output)
        self.assertNotIn("builtins", result.output)

    def test_huge_output_is_capped(self):
        """输出必须有上限：5 秒的 while True: print() 实测能产出约 27 MB，
        而界面那边是把输出塞进**一个 Text 控件**——不截断就会把界面卡死。"""
        result = executor.run_code("for i in range(50000):\n    print('x' * 60)")
        self.assertTrue(result.success)
        self.assertIn("没有显示", result.output)
        self.assertLessEqual(
            len(result.output),
            executor.MAX_OUTPUT_CHARS + len(executor.OUTPUT_TRUNCATED_NOTE) + 8,
        )


class TestPyodideBackend(unittest.TestCase):
    def test_backend_selection(self):
        # 安卓 / iOS 走 embedded：SeriousPython 把 CPython 嵌在 App 进程里，
        # 没有 python.exe 可以开子进程；pyodide 那条路要一个 WebView，
        # 而打包出来的 flet 客户端没有 WebView，等 30 秒必然超时。
        for platform in ("android", "iOS"):
            self.assertEqual(executor.backend_for_platform(platform), "embedded")
        for platform in ("windows", "macos", "linux", "web"):
            self.assertEqual(executor.backend_for_platform(platform), "local")

    def test_web_does_not_use_pyodide(self):
        # ft.WebView in flet 0.23 web renderer is an EMPTY platform view -
        # no <iframe> is generated at all, so mobile_runner bridge page
        # never gets polled and every run times out. Web must stay local.
        for platform in ("windows", "macos", "linux"):
            self.assertEqual(executor.backend_for_platform(platform, web=True), "local")
        self.assertEqual(executor.backend_for_platform("android", web=True), "embedded")
        self.assertEqual(executor.backend_for_platform("ios", web=False), "embedded")

    def test_script_contains_payload(self):
        script = executor.build_pyodide_script("print('hi')", ["张三"])
        self.assertIn("print('hi')", script)
        self.assertIn("张三", script)
        self.assertIn("loadPyodide", script)
        self.assertIn("pyodide/v0.25.0", script)
        self.assertNotIn("__PAYLOAD__", script)
        self.assertNotIn("__PRELUDE__", script)

    def test_pyodide_delegates_to_mobile_runner(self):
        # 手机端不再靠「生成一段 JS 丢给 WebView」，而是委托给
        # core.mobile_runner 的本地 HTTP 桥。这里只验证委托关系，
        # 真正的执行结果由 mobile_runner 自己的单测覆盖。
        from core import mobile_runner

        seen = {}
        original = mobile_runner.run

        def fake_run(code, test_inputs=None, timeout=60.0):
            seen.update(code=code, inputs=test_inputs, timeout=timeout)
            return executor.RunResult(True, output="ok", backend="pyodide")

        mobile_runner.run = fake_run
        try:
            result = executor.run_code("print(1)", ["a"], backend="pyodide")
        finally:
            mobile_runner.run = original
        self.assertTrue(result.success)
        self.assertEqual(seen["code"], "print(1)")
        self.assertEqual(seen["inputs"], ["a"])
        self.assertGreaterEqual(seen["timeout"], 30.0)

    def test_pyodide_checks_security_before_dispatch(self):
        # 危险代码必须在派发给页面之前就拦下来，不能等 Pyodide 跑完再说。
        from core import mobile_runner

        called = []
        original = mobile_runner.run
        mobile_runner.run = lambda *a, **k: called.append(1)
        try:
            result = executor.run_code("import os", backend="pyodide")
        finally:
            mobile_runner.run = original
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "security")
        self.assertEqual(called, [], "危险代码不该被送到页面里执行")

    def test_pyodide_without_webview_says_engine_not_ready(self):
        # 没有 WebView 接任务时，要给学生一句人话，而不是干等或崩掉。
        from core import mobile_runner

        try:
            result = mobile_runner.run("print(1)", timeout=0.5)
        finally:
            # mobile_runner.run() 会真的起一个本地 HTTP 桥（127.0.0.1 + 一次性 token），
            # 以前这里不关：单测跑完会留下一个活着服务线程和占着端口不放。
            mobile_runner.stop()
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "timeout")
        self.assertEqual(result.backend, "pyodide")
        self.assertIn("运行代码", result.error)

    def test_parse_success(self):
        result = executor.parse_pyodide_result(json.dumps({"success": True, "output": "hi\n", "stderr": ""}))
        self.assertTrue(result.success)
        self.assertEqual(result.output, "hi\n")
        self.assertEqual(result.backend, "pyodide")

    def test_parse_error_is_translated(self):
        raw = json.dumps({"success": False, "error_type": "ZeroDivisionError", "error": "division by zero", "line": 2})
        result = executor.parse_pyodide_result(raw)
        self.assertFalse(result.success)
        self.assertIn("除数不能是 0", result.error)
        self.assertIn("第 2 行", result.error)

    def test_parse_garbage(self):
        result = executor.parse_pyodide_result("not json")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "pyodide")


class TestEmbeddedBackend(unittest.TestCase):
    """安卓 / iOS：同进程执行（SeriousPython）。"""

    def test_hello(self):
        result = executor.run_code('a = 1 + 1\nprint(a)\nprint("\u4f60\u597d")', backend="embedded")
        self.assertTrue(result.success)
        self.assertIn("2", result.output)
        self.assertIn("\u4f60\u597d", result.output)
        self.assertEqual(result.backend, "embedded")

    def test_input_injection(self):
        result = executor.run_code('x = input("\u540d\u5b57:")\nprint("\u4f60\u597d", x)',
                                   ["\u7518\u8083\u540c\u5b66"], backend="embedded")
        self.assertTrue(result.success)
        self.assertIn("\u7518\u8083\u540c\u5b66", result.output)

    def test_error_points_to_line(self):
        result = executor.run_code("print(1)\nprint(1 / 0)", backend="embedded")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "ZeroDivisionError")
        self.assertEqual(result.line, 2)
        self.assertIn("1", result.output)  # 出错前的输出要留住

    def test_dangerous_import_blocked(self):
        result = executor.run_code("import os", backend="embedded")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "security")

    def test_getattr_escape_is_blocked(self):
        """同进程后端也要堵住 getattr 逃逸（这条路以前是完全敞开的）。"""
        code = (
            'name = "__" + "self__"\n'
            "b = getattr(print, name)\n"
            'print("ESCAPED", b)\n'
        )
        result = executor.run_code(code, backend="embedded")
        self.assertFalse(result.success)
        self.assertNotIn("ESCAPED", result.output)
        self.assertIn("安全限制", result.error)

    def test_huge_output_is_capped(self):
        """同进程后端直接把输出留在内存里，上限更不能少。"""
        result = executor.run_code("for i in range(50000):\n    print('x' * 60)", backend="embedded")
        self.assertTrue(result.success)
        self.assertIn("没有显示", result.output)
        self.assertLessEqual(
            len(result.output),
            executor.MAX_OUTPUT_CHARS + len(executor.OUTPUT_TRUNCATED_NOTE) + 8,
        )

    def test_math_works(self):
        result = executor.run_code("import math\nprint(math.sqrt(16))", backend="embedded")
        self.assertTrue(result.success)
        self.assertIn("4.0", result.output)

    def test_infinite_loop_is_stopped(self):
        # 同进程跑最怕的就是 while True 把整个 App 卡死，这里确认行数预算兜得住。
        import time as _time
        started = _time.perf_counter()
        result = executor.run_code("while True:\n    pass\n", timeout=5.0, backend="embedded")
        spent = _time.perf_counter() - started
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "timeout")
        self.assertLess(spent, 4.0, "\u6b7b\u5faa\u73af\u8d85\u65f6\u540e\u6ca1\u80fd\u65ad\u6389")

    def test_main_thread_survives(self):
        executor.run_code("while True:\n    pass\n", timeout=5.0, backend="embedded")
        self.assertEqual(executor.run_code("print(1 + 1)", backend="embedded").output.strip(), "2")

    def test_platform_enum_is_normalised(self):
        # 回归测试：page.platform 是 PagePlatform 枚举，str() 出来是
        # "PagePlatform.ANDROID" 而不是 "android"。早先直接
        # str(platform).lower() == "android" 比较，永远为假，
        # 安卡静默走了桌面后端。
        from flet import PagePlatform

        for member, want in (
            (PagePlatform.ANDROID, "android"),
            (PagePlatform.IOS, "ios"),
            (PagePlatform.WINDOWS, "windows"),
        ):
            self.assertEqual(executor.platform_key(member), want)
        self.assertEqual(executor.backend_for_platform(PagePlatform.ANDROID), "embedded")
        self.assertEqual(executor.backend_for_platform(PagePlatform.WINDOWS), "local")

    def test_label_does_not_say_missing_interpreter(self):
        label = executor.runtime_label("embedded")
        self.assertNotIn("\u6ca1\u627e\u5230", label)
        self.assertIn("Python", label)


class TestOnefileRuntimePath(unittest.TestCase):
    """单文件版（PyInstaller --onefile）找内置 Python 的路径。

    背景：单文件版把题库、图标、插件、内置 Python 全封进 exe，启动时解到
    ``sys._MEIPASS``（%TEMP%\_MEIxxxxxx）。而 ``app_dir()`` 指的是 exe 所在目录
    ——用户的下载目录——那里什么都没有。只认 app_dir 的话，**文件夹绿色版一切正常，
    单文件版却报「没找到可用的 Python 解释器，代码运行功能不可用」**。
    这个 bug 真实发生过一次：走查脚本只量「结果框有没有被切掉」，
    框是在的（装的是错误提示），于是被判成 PASS。
    """

    # 源码直接跑时 sys 上根本没有 frozen / _MEIPASS 这两个属性，
    # 所以先记住「原来有没有」，测完原样还回去。
    _ATTRS = ("frozen", "_MEIPASS", "executable")

    def setUp(self) -> None:
        self._had = {name: hasattr(sys, name) for name in self._ATTRS}
        self._saved = {name: getattr(sys, name, None) for name in self._ATTRS}

    def tearDown(self) -> None:
        for name in self._ATTRS:
            if self._had[name]:
                setattr(sys, name, self._saved[name])
            elif hasattr(sys, name):
                delattr(sys, name)
        os.environ.pop("GS_EXAM_PYTHON", None)

    def test_bundle_dir_is_none_without_meipass(self) -> None:
        """文件夹版没有 _MEIPASS，bundle_dir() 必须是 None（不能瞎造一个目录）。"""
        sys.frozen = True
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
        self.assertIsNone(executor.bundle_dir())

    def test_onefile_finds_runtime_inside_meipass(self) -> None:
        r"""单文件版：sys._MEIPASS 里有 runtime\python.exe 就要被找到。"""
        sys.frozen = True
        sys._MEIPASS = r"C:\Users\me\AppData\Local\Temp\_MEI123456"
        self.assertEqual(
            executor.bundle_dir(), Path(r"C:\Users\me\AppData\Local\Temp\_MEI123456")
        )
        found = executor._runtime_candidates()
        self.assertIn(
            Path(r"C:\Users\me\AppData\Local\Temp\_MEI123456\runtime\python.exe"), found
        )

    def test_exe_dir_is_tried_before_meipass(self) -> None:
        r"""exe 旁边的 runtime\ 要排在解包目录前面——
        绿色版可以让用户自己往 exe 旁边放一套更新的 Python。"""
        sys.frozen = True
        sys.executable = r"D:\下载\甘肃省信息技术会考学习软件.exe"
        sys._MEIPASS = r"C:\Temp\_MEI999"
        found = executor._runtime_candidates()
        self.assertEqual(
            found[0], Path(r"D:\下载") / "runtime" / "python.exe"
        )
        self.assertEqual(found[1], Path(r"C:\Temp\_MEI999") / "runtime" / "python.exe")

    def test_gs_exam_python_override_still_wins(self) -> None:
        """环境变量优先级最高，绿色版 / 测试可以指定别的解释器。"""
        sys.frozen = True
        sys._MEIPASS = r"C:\Temp\_MEI999"
        os.environ["GS_EXAM_PYTHON"] = r"D:\Python312\python.exe"
        self.assertEqual(
            executor._runtime_candidates()[0], Path(r"D:\Python312\python.exe")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

