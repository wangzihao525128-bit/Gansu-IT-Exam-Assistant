r"""手机端 / 网页端的 Python 执行桥（需求文档 5.1、Step 6）。

为什么需要这个文件
------------------
Flet 0.23 没有 ``page.run_js``，Python 端没法直接往 WebView 里塞代码让浏览器执行。
所以改走「本地 HTTP 桥」：

    Python 端（手机 App 进程内）
        └─ 起一个只监听 127.0.0.1 的小 HTTP 服务（后台线程）
        └─ 界面上放一个 ft.WebView 指向这个地址
    WebView 里的页面
        └─ 加载 Pyodide（assets/pyodide 目录，完全离线，不用联网）
        └─ 轮询 /task 拿代码 → 在 Pyodide 里跑 → POST /result 回传结果

这样「点运行代码」的按钮仍然是 Flet 原生按钮，编辑也还是原生输入框，
只有真正执行代码的那一步交给浏览器里的 Pyodide，和技术选型里写的一致。

安全
----
* 只绑定 127.0.0.1，手机上别的 App 连不上；
* 所有路径都带一次性随机 token，别的主机猜不到；
* 不发 CORS 头，别的网页也没法来读结果；
* 真正跑代码前照样过 core.security 的 AST 检查。
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core import code_executor, security

# 随程序发出去的离线 Pyodide（npm 包 pyodide@0.25.0 的核心文件，12MB）
_ASSET_DIRS = (
    Path(__file__).resolve().parent.parent / "assets" / "pyodide",
    Path(__file__).resolve().parent.parent / "assets" / "pyodide" / "package",
)
_ASSET_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".zip": "application/zip",
    ".html": "text/html; charset=utf-8",
}

RUNNER_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Python 引擎</title>
<style>
  html,body{margin:0;padding:0;background:#2D2D2D;color:#E6E6E6;
    font:13px/1.5 system-ui,"Microsoft YaHei",sans-serif;overflow:hidden}
  #bar{display:flex;align-items:center;gap:6px;padding:6px 10px;background:#242830}
  #dot{width:9px;height:9px;border-radius:50%;background:#F39C12;flex:none}
  #dot.ok{background:#2ECC71} #dot.bad{background:#E74C3C}
  #txt{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #last{padding:5px 10px;font:12px/1.45 Consolas,monospace;white-space:pre-wrap;
    max-height:64px;overflow:auto;border-top:1px solid #353B45;color:#C8CDD4}
  #last.bad{color:#F0A0A0}
</style></head><body>
<div id="bar"><span id="dot"></span><span id="txt">正在加载 Python 引擎…</span></div>
<div id="last"></div>
<script src="pyodide.js"></script>
<script>
const TOKEN = "__TOKEN__";
const dot = document.getElementById("dot");
const txt = document.getElementById("txt");
const last = document.getElementById("last");
let engine = null, busy = false;

function say(text, cls) {
  txt.textContent = text;
  dot.className = cls || "";
}

function showLast(text, bad) {
  last.textContent = text || "";
  last.className = bad ? "bad" : "";
}

async function boot() {
  try {
    engine = await loadPyodide({ indexURL: "./" });
    engine.setStdout({ batched: (s) => outStdout += s });
    engine.setStderr({ batched: (s) => outStderr += s });
    say("Python 引擎就绪", "ok");
    poll();
  } catch (err) {
    say("引擎加载失败：" + err, "bad");
  }
}

let outStdout = "", outStderr = "";

async function poll() {
  for (;;) {
    if (!busy) {
      let task = null;
      try { task = await (await fetch("task?t=" + Date.now())).json(); } catch (e) {}
      if (task && task.id != null) { busy = true; runOne(task).finally(() => { busy = false; }); }
    }
    await new Promise((r) => setTimeout(r, 250));
  }
}

async function runOne(task) {
  outStdout = ""; outStderr = "";
  let result = { id: task.id, success: true, output: "", stderr: "", error: "", error_type: "", line: 0 };
  try {
    const lines = (task.inputs || []).slice();
    engine.globals.set("__stdin_lines__", lines);
    engine.runPython(PY_PRELUDE);
    await engine.runPythonAsync(task.code);
    result.output = outStdout; result.stderr = outStderr;
    showLast((outStdout || outStderr || "(没有输出)").slice(0, 400), false);
  } catch (exc) {
    result.success = false;
    result.output = outStdout; result.stderr = outStderr;
    // 这里只负责把 Pyodide 的原始报错原样送回 Python 端，
    // 异常类型 / 中文提示的解析统一放在 Python 里做（core.mobile_runner._split_py_error），
    // 免得同一套正则要维护两份、还不好单测。
    const text = String(exc && exc.message ? exc.message : exc);
    const m = text.match(/File "<(?:学生代码|__main__)>", line (\\d+)/);
    result.line = m ? parseInt(m[1], 10) : 0;
    result.error_type = "";
    result.error = text;
    showLast((outStdout + outStderr).trim() + "\\n" + text.split("\\n").slice(-2).join("\\n"), true);
  }
  try {
    await fetch("result", { method: "POST", body: JSON.stringify(result) });
  } catch (e) {}
}

const PY_PRELUDE = `
import builtins
_lines = iter(__stdin_lines__)
def _fake_input(prompt=""):
    if prompt: print(prompt, end="")
    return next(_lines, "")
builtins.input = _fake_input
`;

boot();
</script></body></html>
"""


class _State:
    """Python 端和 HTTP 线程之间共享的状态。"""

    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(16)
        self.ready = threading.Event()
        self.task: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.result_ready = threading.Event()
        self.lock = threading.Lock()


_state: _State | None = None
_server: ThreadingHTTPServer | None = None


def asset_dir() -> Path | None:
    """找到随程序发出去的 Pyodide 文件夹。"""
    for candidate in _ASSET_DIRS:
        if (candidate / "pyodide.js").is_file():
            return candidate
    return None


_PY_ERROR_RE = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*(?:Error|Exception|Interrupt|Exit))\b\s*:?\s*(.*)$", re.S)
_STUDENT_LINE_RE = re.compile(r'File "<(?:学生代码|__main__)>", line (\d+)')


def split_py_error(raw: str) -> tuple[str, str, int]:
    """把 Pyodide 回传的 Python traceback 拆成 (异常类型, 异常消息, 学生代码行号)。

    Pyodide 抛出来的是 ``PythonError``，``.message`` 里是 Python 原始 traceback。
    界面上不该直接糊一整段 traceback 给高中生看，所以这里只留最后那行
    「异常类型: 消息」，剩下的交给 code_executor.friendly_error() 翻成中文。
    """
    text = str(raw or "").strip()
    line = 0
    found = _STUDENT_LINE_RE.search(text)
    if found:
        line = int(found.group(1))
    lines = [item.strip() for item in text.splitlines() if item.strip()]
    tail = lines[-1] if lines else ""
    if tail.startswith("PythonError") and len(lines) >= 2:
        tail = lines[-2]
    matched = _PY_ERROR_RE.match(tail)
    if matched:
        return matched.group(1), (matched.group(2).strip() or tail), line
    return "RuntimeError", (tail or "代码运行出错。"), line


def _make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args) -> None:  # 别刷屏
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # 故意不发 CORS 头：别的网页读不到这里的结果
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError):
                pass

        def _json(self, payload: Any, code: int = 200) -> None:
            self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _guard(self, tail: str) -> bool:
            return self.path.split("?")[0] == f"/{state.token}/{tail}"

        def do_GET(self) -> None:  # noqa: N802
            if self._guard("ready"):
                self._json({"ready": state.ready.is_set()})
                return
            if self._guard("task"):
                with state.lock:
                    task, state.task = state.task, None
                self._json(task)
                return
            if self._guard(""):
                root = asset_dir()
                if root is None:
                    self._send(500, "缺少 assets/pyodide 离线引擎".encode("utf-8"),
                               "text/plain; charset=utf-8")
                    return
                html = RUNNER_HTML.replace("__TOKEN__", state.token).encode("utf-8")
                self._send(200, html, "text/html; charset=utf-8")
                return
            # 静态资源：pyodide.js / pyodide.asm.js / pyodide.asm.wasm / python_stdlib.zip ...
            name = self.path.split("?")[0].rsplit("/", 1)[-1]
            if name and self.path.startswith(f"/{state.token}/"):
                root = asset_dir()
                target = (root / name) if root else None
                if target and target.is_file() and target.parent == root:
                    ctype = _ASSET_TYPES.get(target.suffix, "application/octet-stream")
                    self._send(200, target.read_bytes(), ctype)
                    return
            self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            if not self._guard("result"):
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            with state.lock:
                state.result = json.loads(raw.decode("utf-8", "replace") or "{}")
            state.result_ready.set()
            self._json({"ok": True})

    return Handler


def start() -> str:
    """启动本地引擎服务，返回 WebView 该加载的地址。"""
    global _state, _server
    if _server is not None and _state is not None:
        return url()
    _state = _State()
    _server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(_state))
    _server.daemon_threads = True
    threading.Thread(target=_server.serve_forever, name="pyodide-bridge", daemon=True).start()
    return url()


def url() -> str:
    """WebView 要加载的地址。"""
    if _state is None or _server is None:
        return ""
    host, port = _server.server_address[0], _server.server_address[1]
    return f"http://{host}:{port}/{_state.token}/"


def is_ready() -> bool:
    return bool(_state and _state.ready.is_set())


def mark_ready() -> None:
    """页面加载完 Pyodide 后回调（WebView 里用不到时留作扩展点）。"""
    if _state is not None:
        _state.ready.set()


def run(code: str, test_inputs: list[str] | None = None, timeout: float = 60.0) -> code_executor.RunResult:
    """把代码交给页面里的 Pyodide 执行并等结果。

    先过一遍 core.security 的 AST 检查——静态检查在 Python 端做，
    提示才能是统一的中文。页面里的 Pyodide 只负责执行，不做安全判断。
    """
    start()
    assert _state is not None
    try:
        security.check_code(code or "")
    except security.SecurityError as exc:
        return code_executor.RunResult(False, error=str(exc), error_type="security", backend="pyodide")

    with _state.lock:
        _state.result = None
        _state.task = {"id": secrets.randbelow(1 << 30), "code": code or "", "inputs": list(test_inputs or [])}
    _state.result_ready.clear()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _state.result_ready.wait(0.2):
            with _state.lock:
                raw = _state.result or {}
            if not raw.get("success") and not raw.get("error_type"):
                error_type, message, line = split_py_error(raw.get("error", ""))
                raw["error_type"] = error_type
                raw["error"] = message
                raw["line"] = raw.get("line") or line
            return code_executor.parse_pyodide_result(json.dumps(raw, ensure_ascii=False))
    return code_executor.RunResult(
        False,
        error="手机端引擎还没准备好，请稍等几秒再点一次「运行代码」。",
        error_type="timeout",
        backend="pyodide",
    )


def stop() -> None:
    """关掉本地服务（退出 App 或切回桌面端时调用）。"""
    global _server, _state
    if _server is not None:
        _server.shutdown()
        _server.server_close()
    _server = None
    _state = None
