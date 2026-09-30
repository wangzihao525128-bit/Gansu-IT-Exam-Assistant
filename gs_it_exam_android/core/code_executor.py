r"""代码执行引擎（需求文档 Step 2）。

对外只有一个入口：

    result = run_code("a = 1 + 1\nprint(a)")
    print(result.as_dict())
    # {'success': True, 'output': '2\n', 'error': '', 'error_type': '', ...}

三种后端：

* local   —— 桌面端（本机有 Python）：写进独立子进程执行，
             启动参数 `-I -S` 让它读不到任何第三方库，超时强制结束；
* embedded —— Android / iOS：SeriousPython 把 CPython 嵌在 App 进程里，
             没有 python.exe 可以开子进程，只能同进程 exec（带行数预算防死循环）；
* pyodide —— 网页端兜底：build_pyodide_script() 生成 JS 交给 WebView 里的 Pyodide。

无论哪种后端，运行前都会先过 security.check_code()，给出统一的中文提示。
三种后端的学生环境都由这里统一装配：独立 globals + 受限 builtins +
security.safe_getattr（不是真 getattr）+ 包装过的 print + 输出上限
（`MAX_OUTPUT_CHARS`）。这几样是**配套的**，少哪一样都能被学生三行代码废掉，
详见 security.py 的模块说明。
"""

from __future__ import annotations

import builtins
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import security

DEFAULT_TIMEOUT = 5.0  # 需求文档 8.1：超时 5 秒，防死循环
PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.25.0/full/"

# 单次运行的输出上限。学生写 `while True: print("x")` 时，实测 print 进 StringIO
# 约 269 万次/秒，5 秒超时内能产出约 27 MB —— 不设上限的话：先把内存吃满、
# 再写一个几十 MB 的 result.json、最后把一个长字符串塞进界面里的**一个 Text 控件**。
MAX_OUTPUT_CHARS = 200_000
OUTPUT_TRUNCATED_NOTE = "\n…（输出太长，后面的内容没有显示）"


class _LimitedBuffer(io.StringIO):
    """带上限的字符串缓冲：超过上限就不再攒，只记一个 truncated 标记。

    子进程 runner 里有一份等价实现（那份脚本必须自包含），两边一起改。
    """

    def __init__(self, limit: int = MAX_OUTPUT_CHARS) -> None:
        super().__init__()
        self.limit = limit
        self.truncated = False

    def write(self, text) -> int:  # type: ignore[override]
        text = str(text)
        used = self.tell()
        if used >= self.limit:
            if text:
                self.truncated = True
            return len(text)
        room = self.limit - used
        if len(text) > room:
            self.truncated = True
            text = text[:room]
        super().write(text)
        return len(text)

# 运行学生代码的子进程脚本：只用标准库，不读用户文件。
# 它会被写到临时目录里，用 python -I -S 执行；-S 表示不加载 site，
# 所以即使沙箱被绕过，也 import 不到任何第三方库。
_RUNNER_SOURCE = r"""
import builtins as _builtins
import contextlib
import io
import json
import sys
import traceback


class _LimitedBuffer(io.StringIO):
    # 写到上限就不再攒了（原因见 code_executor.MAX_OUTPUT_CHARS）。
    def __init__(self, limit):
        io.StringIO.__init__(self)
        self.limit = limit
        self.truncated = False

    def write(self, text):
        text = str(text)
        used = self.tell()
        if used >= self.limit:
            if text:
                self.truncated = True
            return len(text)
        room = self.limit - used
        if len(text) > room:
            self.truncated = True
            text = text[:room]
        io.StringIO.write(self, text)
        return len(text)


def main():
    payload = json.loads(sys.stdin.read())
    code = payload["code"]
    inputs = list(payload.get("inputs") or [])
    allowed = payload.get("builtins") or []
    safe_modules = set(payload.get("modules") or [])
    blocked = set(payload.get("blocked") or [])
    limit = int(payload.get("output_limit") or 200000)

    stdout_buffer = _LimitedBuffer(limit)
    stderr_buffer = _LimitedBuffer(limit)

    def fake_input(prompt=""):
        if prompt:
            stdout_buffer.write(str(prompt))
        return inputs.pop(0) if inputs else ""

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0 or name.split(".")[0] not in safe_modules:
            raise ImportError("安全限制：不允许导入 " + str(name))
        return _builtins.__import__(name, globals, locals, fromlist, level)

    def safe_getattr(obj, name, *default):
        # 与 core/security.py 的 safe_getattr 等价（这份脚本必须自包含，
        # 不能 import 项目模块；两边由 test_sandbox.py 的逃逸用例一起盯着）。
        # 别看它短：把真 getattr 交出去，学生三行就能从
        # getattr(print, "__self__") 反查到 builtins 里的 open / __import__。
        if not isinstance(name, str):
            raise TypeError("getattr 的属性名必须是字符串")
        if name.startswith("_") or name in blocked:
            raise AttributeError("安全限制：不允许访问 " + name)
        if default:
            return getattr(obj, name, *default)
        return getattr(obj, name)

    def safe_print(*args, **kwargs):
        # 不把真的 print 对象交给学生代码：它身上的 __self__ 指向 builtins 模块。
        _builtins.print(*args, **kwargs)

    safe_builtins = {name: getattr(_builtins, name) for name in allowed if hasattr(_builtins, name)}
    safe_builtins["print"] = safe_print
    safe_builtins["input"] = fake_input
    safe_builtins["getattr"] = safe_getattr
    safe_builtins["__import__"] = safe_import

    result = {"success": True, "output": "", "stderr": "", "error": "", "error_type": "", "line": 0}
    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            exec(compile(code, "<学生代码>", "exec"), {"__name__": "__main__", "__builtins__": safe_builtins})
    except BaseException as exc:
        result["success"] = False
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        line = 0
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename == "<学生代码>":
                line = frame.lineno
        result["line"] = line

    result["output"] = stdout_buffer.getvalue()
    result["stderr"] = stderr_buffer.getvalue()
    result["truncated"] = stdout_buffer.truncated or stderr_buffer.truncated
    with open(payload["result_file"], "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False)


main()
"""

PYODIDE_PRELUDE = """import builtins
_lines = iter(__stdin_lines)


def _input(prompt=""):
    if prompt:
        print(prompt, end="")
    return next(_lines, "")


builtins.input = _input
"""

PYODIDE_TEMPLATE = """/* 手机端（Android / iOS / Web）用 Pyodide 运行学生代码。
   放进 WebView 页面后调用 runStudentCode() 即可。
   注意：先用 security.check_code() 过一次静态检查，中文提示才统一。 */
const PAYLOAD = __PAYLOAD__;
const INDEX_URL = "__URL__";
let engine = null;

async function getEngine() {
  if (engine === null) {
    engine = await loadPyodide({ indexURL: INDEX_URL });
  }
  return engine;
}

async function runStudentCode() {
  const result = { success: false, output: "", stderr: "", error: "", error_type: "", line: 0 };
  const out = [];
  const err = [];
  try {
    const pyodide = await getEngine();
    pyodide.setStdout({ batched: function (text) { out.push(text); } });
    pyodide.setStderr({ batched: function (text) { err.push(text); } });
    pyodide.globals.set("__stdin_lines", PAYLOAD.inputs);
    await pyodide.runPythonAsync(__PRELUDE__);
    await pyodide.runPythonAsync(PAYLOAD.code);
    result.success = true;
  } catch (error) {
    result.error_type = "runtime";
    result.error = (error && error.message) ? error.message : String(error);
  }
  result.output = out.join("");
  result.stderr = err.join("");
  return result;
}
"""
# 面向高中生的中文错误提示
RUNTIME_TIPS: dict[str, tuple[str, str]] = {
    "NameError": ("这里用到了一个还不存在的名字", "先给它赋值，或者检查有没有拼错（数字 1 和小写字母 l 很容易看混）。"),
    "TypeError": ("两个数据的类型对不上", "比如数字和文字不能直接相加，可以先用 int() / str() / float() 转换。"),
    "ValueError": ("这个值不合法", "比如 int('abc') 无法把文字转成数字。"),
    "IndexError": ("越界了", "列表下标从 0 开始，最后一个元素的下标是「长度 - 1」。"),
    "KeyError": ("字典里没有这个键", "可以先用 字典.get(键名, 默认值) 兜底。"),
    "ZeroDivisionError": ("除数不能是 0", "检查一下除号后面的数。"),
    "IndentationError": ("缩进不一致", "同一层的代码要对齐，建议整个文件统一用 4 个空格。"),
    "TabError": ("Tab 和空格混用了", "全选代码后统一改成 4 个空格。"),
    "AttributeError": ("这个对象上没有这个属性或方法", "检查对象的类型，以及名字有没有拼错。"),
    "SyntaxError": ("语法有问题", "检查括号、冒号、引号是否成对。"),
    "RecursionError": ("递归层数太深了", "函数里要有一个能停下来（走到出口）的分支。"),
    "MemoryError": ("内存不够了", "别一次创建特别大的列表或字符串。"),
    "OverflowError": ("数值太大溢出了", "检查一下是不是算式写错了。"),
    "UnboundLocalError": ("变量还没赋值就拿来用了", "先给它赋值，再参与运算。"),
    "ModuleNotFoundError": ("没有这个模块", "只能用安全模块清单里的模块，试试 math、random。"),
    "ImportError": ("这个模块不允许导入", "沙箱只开放了安全模块清单，比如 math、random、datetime、string。"),
    "StopIteration": ("迭代提前结束了", "一般是循环条件没考虑周全。"),
    "SystemExit": ("程序自己退出了", "检查有没有写 exit() / quit()。"),
}
DEFAULT_RUNTIME_TIP = ("运行时出错了", "把出错的那一行和提示对着代码示例看看，多半是少了个引号或括号。")


@dataclass
class RunResult:
    """一次运行的结果；as_dict() 给 UI 用。"""

    success: bool
    output: str = ""
    stderr: str = ""
    error: str = ""
    error_type: str = ""
    line: int = 0
    duration: float = 0.0
    backend: str = "local"

    @property
    def text(self) -> str:
        """屏幕上要显示的全部输出。"""
        parts = [self.output]
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(part for part in parts if part)

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "stdout": self.output,
            "stderr": self.stderr,
            "error": self.error,
            "error_type": self.error_type,
            "line": self.line,
            "duration": round(self.duration, 3),
            "backend": self.backend,
        }


def friendly_error(error_type: str, message: str, line: int = 0) -> str:
    """把 Python 报错翻译成高中生看得懂的中文提示。"""
    head, tip = RUNTIME_TIPS.get(error_type, DEFAULT_RUNTIME_TIP)
    where = f"第 {line} 行：" if line else ""
    raw = f"（Python 原始信息：{error_type}: {message}）" if message else ""
    return f"{where}{head}。{tip}{raw}"


MIN_PYTHON = (3, 8)  # 需求：内置的 Python 至少要是 3.8
RUNTIME_DIR_NAME = "runtime"
_RUNTIME: dict[str, Any] | None = None


def app_dir() -> Path:
    """程序所在目录：打包后是 exe 旁边，源码运行时是项目根目录。

    这是「用户能写、能换题库、能丢插件」的那个目录，不是只读的内置资源目录。
    单文件版请配合 :func:`bundle_dir` 用。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path | None:
    """PyInstaller 单文件版解包出来的只读目录（``%TEMP%\\_MEIxxxxxx``），其他模式没有。

    **单文件版必须认这个目录**：题库、图标、插件、内置 Python 全被封进 exe 里，
    启动时解到 ``sys._MEIPASS`` 下。``app_dir()`` 指的是 exe 所在目录（用户的
    下载目录），那里什么都没有——只认 app_dir 的话单文件版就会报
    「没找到可用的 Python 解释器，代码运行功能不可用」，
    而文件夹绿色版一切正常。文件夹版（onedir）没有 ``_MEIPASS``，返回 None。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    return Path(meipass)


def _runtime_candidates() -> list[Path]:
    """按优先级列出可能可用的 Python 解释器。

    1. ``GS_EXAM_PYTHON`` 环境变量（测试和绿色版可以指定用哪个解释器）；
    2. 程序目录下的 ``runtime/python.exe``——文件夹绿色版的内置 Python；
    3. 单文件版解包目录下的 ``runtime/python.exe``（``sys._MEIPASS``）；
    4. 没打包时的 ``sys.executable``（直接 ``python main.py`` 跑的开发环境）。
    """
    found: list[Path] = []
    override = os.environ.get("GS_EXAM_PYTHON", "").strip()
    if override:
        found.append(Path(override))
    found.append(app_dir() / RUNTIME_DIR_NAME / "python.exe")
    bundled = bundle_dir()
    if bundled is not None:
        found.append(bundled / RUNTIME_DIR_NAME / "python.exe")
    if not getattr(sys, "frozen", False) and sys.executable:
        found.append(Path(sys.executable))
    return found


def _probe_version(python: Path) -> tuple[int, ...]:
    """问解释器自己的版本号；起不来就返回空元组。"""
    extra: dict[str, Any] = {}
    if os.name == "nt":  # 别闪黑框
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(
            [str(python), "-I", "-S", "-c", "import sys;print('.'.join(map(str, sys.version_info[:3])))"],
            capture_output=True,
            text=True,
            timeout=10,
            **extra,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if done.returncode != 0:
        return ()
    try:
        return tuple(int(part) for part in done.stdout.strip().split("."))
    except ValueError:
        return ()


def runtime_info(refresh: bool = False) -> dict[str, Any]:
    """探测「代码运行窗口」实际会用哪个 Python，结果缓存，只查一次。

    返回 ``{"ok", "path", "version", "bundled", "error"}``；
    ``bundled`` 为 True 表示用的是随程序一起发出去的内置解释器。
    """
    global _RUNTIME
    if _RUNTIME is not None and not refresh:
        return _RUNTIME
    info: dict[str, Any] = {"ok": False, "path": "", "version": "", "bundled": False, "error": ""}
    # 「算不算内置」要同时认两个根：文件夹版的 exe 旁边，和单文件版的解包目录。
    bundled_roots = [(app_dir() / RUNTIME_DIR_NAME).resolve()]
    _bundle = bundle_dir()
    if _bundle is not None:
        bundled_roots.append((_bundle / RUNTIME_DIR_NAME).resolve())
    for candidate in _runtime_candidates():
        if not candidate.is_file():
            continue
        version = _probe_version(candidate)
        if not version:
            continue
        if version[:2] < MIN_PYTHON:
            info["error"] = f"找到的 Python 是 {'.'.join(map(str, version))}，低于要求的 3.8，已跳过。"
            continue
        try:
            inside = any(root in candidate.resolve().parents for root in bundled_roots)
        except OSError:
            inside = False
        info.update(ok=True, path=str(candidate), version=".".join(map(str, version)), bundled=inside)
        break
    if not info["ok"] and not info["error"]:
        info["error"] = "没找到可用的 Python 解释器，代码运行功能不可用。"
    _RUNTIME = info
    return info


def has_local_python() -> bool:
    """当前环境能不能用子进程跑代码（打包后靠内置 runtime，不再直接返回 False）。"""
    return bool(runtime_info()["ok"])


def runtime_label(backend: str = "local") -> str:
    """给界面显示的一行字，例如「内置 Python 3.11.7」。

    ``backend`` 传 "embedded"（安卓 / iOS）时不能说「没找到解释器」——
    解释器就在这个进程里（SeriousPython），只是没有 python.exe 可以起子进程。
    """
    if backend == "embedded":
        version = ".".join(str(part) for part in sys.version_info[:3])
        return f"内置 Python {version}（随 App 打包）"
    if backend == "pyodide":
        return "Pyodide（页面内运行）"
    info = runtime_info()
    if not info["ok"]:
        return info["error"] or "未找到 Python 运行时"
    return f"{'内置' if info['bundled'] else '本机'} Python {info['version']}"


def platform_key(platform: Any) -> str:
    """把 ``page.platform`` 归一成小写字符串，比如 ``"android"``。

    这个坑非常隐蔽：flet 0.23 的 ``Page.platform`` 是 ``PagePlatform`` 枚举，
    ``str(它)`` 得到的是 ``"PagePlatform.ANDROID"``，``.lower()`` 之后是
    ``"pageplatform.android"``，**永远不等于** ``"android"``。

    后果是安卓静默走了桌面的 ``local`` 后端：界面上写着「没找到可用的 Python
    解释器，代码运行功能不可用」，点「运行代码」毫无反应，而且单测全绿——
    因为单测传的是普通字符串，只有真机/模拟器才暴露。
    之前 mobile_runner（Pyodide）那条路也是同样的原因，一直是死代码。

    这里统一取枚举的 ``.value``；传普通字符串就原样用（单测里就是这么传的）。
    """
    if platform is None:
        return ""
    value = getattr(platform, "value", None)
    if isinstance(value, str) and value:
        return value.lower()
    text = str(platform).lower()
    if text.startswith("pageplatform."):
        text = text.split(".", 1)[1]
    return text


def backend_for_platform(platform: str, web: bool = False) -> str:
    """安卓 / iOS 用 Pyodide，其余用本地子进程。

    **为什么 web 端不走 Pyodide**（实测踩过的坑，别改回去）：
    flet 0.23 虽然有 ``ft.WebView``，但它只在 Android / iOS 上是真 WebView，
    在 web 渲染器下是个**空的平台视图**——页面里连 ``<iframe>`` 都不生成。
    于是 ``mobile_runner`` 起的桥页面永远收不到 WebView 的轮询，
    点「运行代码」只会一路等到超时。

    所以网页端老老实实走 local 后端：``flet run --web`` 时 Python 服务就跑在
    跑服务的那台电脑上，手机浏览器访问时由那台电脑执行代码——实测可用。

    ``web`` 参数保留，是为了让调用方能显式表达「这是网页端」，
    也提醒后来人：flet 0.23 的 PagePlatform 枚举里**没有 WEB 项**，
    ``flet run --web`` 时 ``page.platform`` 报的是宿主系统，别按它瞎猜。
    """
    if platform_key(platform) in {"android", "ios"}:
        return "embedded"
    return "local"


def _limited_text(buffer: _LimitedBuffer) -> str:
    """取缓冲区里的文本；被截断过就补一句给学生看得懂的中文说明。"""
    text = buffer.getvalue()
    if buffer.truncated:
        text += OUTPUT_TRUNCATED_NOTE
    return text


def _cap_output(result: RunResult) -> RunResult:
    """最后一道保险：任何后端回来的输出都不能无限长。

    真正的截断发生在各自的缓冲里（runner / embedded / pyodide），
    这里兜的是「将来有人新加一个后端忘了设上限」这种情况——
    UI 端把输出塞进**一个 Text 控件**，几十 MB 会直接把界面卡死。
    """
    for field in ("output", "stderr"):
        text = getattr(result, field)
        if not isinstance(text, str):
            continue
        if len(text) > MAX_OUTPUT_CHARS + len(OUTPUT_TRUNCATED_NOTE):
            setattr(result, field, text[:MAX_OUTPUT_CHARS] + OUTPUT_TRUNCATED_NOTE)
    return result


def run_code(
    code: str,
    test_inputs: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    backend: str = "local",
) -> RunResult:
    """运行一段学生代码，返回 RunResult。

    :param code: 学生写的 Python 代码
    :param test_inputs: 注入给 input() 的测试数据，按顺序取用
    :param timeout: 秒数上限，超时强制结束（默认 5 秒）
    :param backend: 'local'（桌面）或 'pyodide'（手机 / 网页）
    """
    code = code or ""
    try:
        security.check_code(code)
    except security.SecurityError as exc:
        return RunResult(False, error=str(exc), error_type="security", backend=backend)

    if backend == "local":
        result = _run_local(code, test_inputs, timeout)
    elif backend == "embedded":
        result = _run_embedded(code, test_inputs, timeout)
    elif backend == "pyodide":
        # 手机 / 网页端没有本地解释器，交给 core.mobile_runner 的
        # 「本地 HTTP 桥 + WebView 里的 Pyodide」执行。
        from core import mobile_runner

        result = mobile_runner.run(code, test_inputs, timeout=max(timeout, 30.0))
    else:
        return RunResult(False, error=f"未知的运行后端：{backend}", error_type="backend", backend=backend)
    return _cap_output(result)


def _cleanup(*paths: Path, workdir: Path) -> None:
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass
    try:
        workdir.rmdir()
    except OSError:
        pass


class _EmbeddedTimeout(BaseException):
    """行数预算或墙钟到了。

    故意继承 BaseException 而不是 Exception：万一学生代码里写了
    ``except Exception: pass``，不能让它把我们的超时信号顺手吃掉。
    """


_EMBEDDED_STEP_BUDGET_PER_SEC = 1_000_000


def _run_embedded(code: str, test_inputs: list[str] | None, timeout: float) -> RunResult:
    """在当前进程里执行学生代码（安卓 / iOS 的 SeriousPython 就是这么跑的）。

    为什么不能用桌面那套子进程：手机系统里没有 python.exe，SeriousPython 是把
    CPython 直接嵌在 App 进程里的，没法 fork出一个干净进程。所以只能同进程跑，
    隔离靠四件事一起兜：

      1. run_code() 里的 security.check_code() 静态白名单（AST 级，先跑过了）；
      2. 独立的 globals 和受限 builtins（和子进程 runner 完全一致）；
      3. sys.settrace 行数预算 + 墙钟看门狗——死循环跑不满预算就被打断，
         这一条是关键：同进程跑最怕的就是 while True 把整个 App 卡死；
      4. 守护线程，界面线程 join 超时后直接返回，不会被学生代码按死。

    之前安卓上这条路是断的：backend 走的是 pyodide，要一个 WebView 里的
    Pyodide，而打包出来的 flet 客户端根本没有 WebView，于是每次点「运行代码」
    都是干等 30 秒超时，界面上什么反馈都没有（实测截图见 完善/screenshots/安卓）。
    """
    inputs = list(test_inputs or [])
    out_buf = _LimitedBuffer()
    err_buf = _LimitedBuffer()
    state: dict[str, Any] = {"success": True, "error_type": "", "error": "", "line": 0}

    def fake_input(prompt=""):
        if prompt:
            out_buf.write(str(prompt))
        return inputs.pop(0) if inputs else ""

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0 or name.split(".")[0] not in security.SAFE_MODULES:
            raise ImportError("安全限制：不允许导入 " + str(name))
        return builtins.__import__(name, globals, locals, fromlist, level)

    def safe_print(*args, **kwargs):
        """包一层再交给学生代码：真的 print 对象身上挂着 __self__，
        学生能用它反查回 builtins 模块（那个漏洞实测过）。"""
        builtins.print(*args, **kwargs)

    safe_builtins = {
        name: getattr(builtins, name)
        for name in security.SAFE_BUILTIN_NAMES
        if hasattr(builtins, name)
    }
    safe_builtins["print"] = safe_print
    safe_builtins["input"] = fake_input
    safe_builtins["getattr"] = security.safe_getattr
    safe_builtins["__import__"] = safe_import

    deadline = time.perf_counter() + timeout
    budget = max(200_000, int(timeout * _EMBEDDED_STEP_BUDGET_PER_SEC))
    steps = 0

    def tracer(frame, event, arg):  # noqa: ARG001 - 签名是 sys.settrace 定的
        nonlocal steps
        steps += 1
        if steps > budget or time.perf_counter() > deadline:
            raise _EmbeddedTimeout()
        return tracer

    def body() -> None:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out_buf, err_buf
        sys.settrace(tracer)
        try:
            exec(
                compile(code, "<学生代码>", "exec"),
                {"__name__": "__main__", "__builtins__": safe_builtins},
            )
        except _EmbeddedTimeout:
            state.update(
                success=False,
                error_type="timeout",
                error=f"运行超过 {timeout:g} 秒还没结束，已经停下来了。"
                       "检查一下是不是写了个停不下来的循环。",
            )
        except BaseException as exc:  # 学生代码自己的错
            state.update(success=False, error_type=type(exc).__name__, error=str(exc))
            for frame_info in traceback.extract_tb(exc.__traceback__):
                if frame_info.filename == "<学生代码>":
                    state["line"] = frame_info.lineno
        finally:
            sys.settrace(None)
            sys.stdout, sys.stderr = old_out, old_err

    worker = threading.Thread(target=body, name="gs-exam-run", daemon=True)
    started = time.perf_counter()
    worker.start()
    worker.join(timeout + 2.0)
    duration = time.perf_counter() - started

    if worker.is_alive():
        # 学生代码卡在 C 层（trace 回调进不去），线程收不回来，只能如实说超时。
        return RunResult(
            False,
            error=f"运行超过 {timeout:g} 秒还没结束，已经停下来了。",
            error_type="timeout",
            duration=duration,
            backend="embedded",
        )

    return RunResult(
        bool(state["success"]),
        output=_limited_text(out_buf),
        stderr=_limited_text(err_buf),
        error=str(state["error"]),
        error_type=str(state["error_type"]),
        line=int(state["line"]),
        duration=duration,
        backend="embedded",
    )


def _run_local(code: str, test_inputs: list[str] | None, timeout: float) -> RunResult:
    runtime = runtime_info()
    if not runtime["ok"]:
        return RunResult(
            False,
            error=(runtime["error"] or "没有可用的 Python 解释器。") + " 桌面端请重新安装完整版，或改用网页版。",
            error_type="backend",
        )
    python_exe = runtime["path"]

    workdir = Path(tempfile.mkdtemp(prefix="gs_exam_"))
    runner = workdir / "runner.py"
    result_file = workdir / "result.json"
    started = time.perf_counter()

    # 整段包在 try/finally 里：不管是超时、解释器被人删了、结果文件坏了，
    # 临时目录都必须收回去（之前只有两条路径会清理，OSError 会漏一个目录）。
    try:
        runner.write_text(_RUNNER_SOURCE, encoding="utf-8")

        payload = json.dumps(
            {
                "code": code,
                "inputs": list(test_inputs or []),
                "builtins": sorted(security.SAFE_BUILTIN_NAMES),
                "modules": sorted(security.SAFE_MODULES),
                "blocked": sorted(security.FORBIDDEN_NAMES),
                "output_limit": MAX_OUTPUT_CHARS,
                "result_file": str(result_file),
            },
            # 子进程用 -I 启动，会忽略 PYTHONIOENCODING / PYTHONUTF8，
            # 所以这里必须转成纯 ASCII，中文才不会在管道里变成乱码。
            ensure_ascii=True,
        )
        # 运行时可能被换到别的目录（内置 runtime），所以按解释器位置重算一下工作目录
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        kwargs: dict[str, Any] = {}
        if os.name == "nt":  # 别闪黑框
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            completed = subprocess.run(
                [python_exe, "-I", "-S", "-B", str(runner)],
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(workdir),
                env=env,
                **kwargs,
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                False,
                error=f"代码运行超过 {timeout:g} 秒，多半是死循环（比如 while True 忘了写 break），已帮你强制停止。",
                error_type="timeout",
                duration=time.perf_counter() - started,
            )
        except (OSError, subprocess.SubprocessError) as error:
            # 解释器文件被删了、没有执行权限、临时目录被清理器收走……
            # 以前这里会直接把异常抛到界面上，现在给一句学生看得懂的话。
            return RunResult(
                False,
                error=f"沙箱启动失败：{error}",
                error_type="sandbox",
                duration=time.perf_counter() - started,
            )

        duration = time.perf_counter() - started
        if not result_file.exists():
            detail = (completed.stderr or "").strip()[-300:]
            return RunResult(
                False,
                error="沙箱没能正常返回结果。" + (f"\n（排查信息：{detail}）" if detail else ""),
                error_type="sandbox",
                duration=duration,
            )

        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            # 结果文件写坏了/读不出来：报「沙箱异常」，不要让原始异常冒到界面上。
            return RunResult(
                False,
                error=f"沙箱返回的结果读不出来：{error}",
                error_type="sandbox",
                duration=duration,
            )

        output = str(data.get("output", "") or "")
        stderr = str(data.get("stderr", "") or "")
        if data.get("truncated"):
            output += OUTPUT_TRUNCATED_NOTE

        if data.get("success"):
            return RunResult(True, output=output, stderr=stderr, duration=duration)

        error_type = data.get("error_type", "runtime")
        return RunResult(
            False,
            output=output,
            stderr=stderr,
            error=friendly_error(error_type, data.get("error", ""), int(data.get("line") or 0)),
            error_type=error_type,
            line=int(data.get("line") or 0),
            duration=duration,
        )
    finally:
        _cleanup(runner, result_file, workdir=workdir)


def build_pyodide_script(code: str, test_inputs: list[str] | None = None, pyodide_url: str = PYODIDE_URL) -> str:
    """生成手机 / 网页端用的 JS 脚本（Pyodide 0.25.0）。

    用法：把返回值写进 WebView 的 HTML 页面，页面里调用 runStudentCode()，
    再把结果 JSON 交回 Python 端，用 parse_pyodide_result() 解析。
    课堂若要离线使用，可把 Pyodide 下载到本地并传入 pyodide_url。
    """
    payload = json.dumps({"code": code or "", "inputs": list(test_inputs or [])}, ensure_ascii=False)
    return (
        PYODIDE_TEMPLATE.replace("__PAYLOAD__", payload)
        .replace("__URL__", pyodide_url)
        .replace("__PRELUDE__", json.dumps(PYODIDE_PRELUDE, ensure_ascii=False))
    )


def parse_pyodide_result(raw: str) -> RunResult:
    """把 WebView 回传的 JSON 解析成 RunResult，并翻译错误。"""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return RunResult(False, error="Pyodide 返回的内容看不懂，请重试一次。", error_type="pyodide", backend="pyodide")

    if data.get("success"):
        return _cap_output(
            RunResult(True, output=data.get("output", ""), stderr=data.get("stderr", ""), backend="pyodide")
        )

    error_type = data.get("error_type") or "runtime"
    return _cap_output(
        RunResult(
            False,
            output=data.get("output", ""),
            stderr=data.get("stderr", ""),
            error=friendly_error(error_type, data.get("error", ""), int(data.get("line") or 0)),
            error_type=error_type,
            line=int(data.get("line") or 0),
            backend="pyodide",
        )
    )
