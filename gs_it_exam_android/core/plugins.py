"""插件化扩展接口（需求文档 8.4「预留插件化扩展接口」）。

**为什么要它**：8.4 要求「未来更新知识点只需修改 JSON」之外，
还要「预留插件化扩展接口」，好让后续功能不用改主程序就能加进来。
这个模块就是那个接口。

**怎么用**：在程序目录下的 ``plugins\\`` 里放一个子目录，
里面放一个 ``plugin.py``，程序启动时自动发现并加载。子目录可以任意命名。

``plugin.py`` 里可以写下面几样东西（**全是可选的**，写一样算一样）：

.. code-block:: python

    PLUGIN = {"name": "记忆卡片", "version": "1.0", "description": "按艾宾浩斯曲线安排复习"}

    def modules() -> list[dict]:
        \"\"\"往题库里追加模块 / 知识点。返回的结构和 data\\knowledge_points.json 一样。\"\"\"
        return [{"id": "m1", "name": "模块一：…", "color": "#4A90E2", "points": [...]}]

    def detail_panel(point: dict, colors: dict):
        \"\"\"在知识点详情页右栏底部追加一块自定义面板，返回 flet 控件；不需要就删掉。\"\"\"
        import flet as ft
        return ft.Text("插件面板")

    def startup(page) -> None:
        \"\"\"主界面建好之后调用一次，可以做埋点、初始化自己的状态等。\"\"\"

**三条安全约定**（写进接口本身，不是口头约定）：

1. 插件在**主程序进程**里跑，不在学生代码沙箱里跑；
   所以它和 ``knowledge_points.json`` 是同一个信任级别——老师自己放的。
2. 任何一个插件抛异常，只会被**跳过并记一条日志**，
   绝不会把整个软件带崩（``load_all`` 里逐个 try）。
3. 学生写的代码永远进不了这里；这里的插件也碰不到学生代码的执行环境。

8.3 要求的内存缓存精神也遵守：发现结果只在进程内算一次。
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

PLUGIN_SUBDIR = "plugins"
ENTRY_FILE = "plugin.py"

# 插件里约定的几个可选项，各自都能缺省
OPTIONAL_HOOKS = ("modules", "detail_panel", "startup")

_cache: list[dict[str, Any]] | None = None
_warnings: list[str] = []


def plugin_dir() -> Path:
    """插件目录：打包后在 exe 旁边，开发时在项目根目录。

    和 :func:`core.knowledge_store.data_file` 同一个思路——
    「程序旁边那份优先，打包内置那份兜底」，这样老师可以直接往文件夹里丢插件。
    """
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).resolve().parent / PLUGIN_SUBDIR
        if portable.exists():
            return portable
        return Path(__file__).resolve().parent.parent / PLUGIN_SUBDIR
    return Path(__file__).resolve().parent.parent / PLUGIN_SUBDIR


def _describe(module: Any, fallback: str) -> dict[str, str]:
    meta = getattr(module, "PLUGIN", None)
    meta = meta if isinstance(meta, dict) else {}
    return {
        "id": str(meta.get("id", fallback)),
        "name": str(meta.get("name", fallback)),
        "version": str(meta.get("version", "0")),
        "description": str(meta.get("description", "")),
    }


def _import_plugin(path: Path) -> Any:
    """按文件路径 import 一个模块，并给个唯一名字免得跟主程序撞名。"""
    unique = f"gs_it_exam_plugin_{path.parent.name}"
    spec = importlib.util.spec_from_file_location(unique, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 {path} 创建 import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique] = module
    spec.loader.exec_module(module)
    return module


def discover(force: bool = False) -> list[dict[str, Any]]:
    """找出并加载所有插件，返回 ``[{"info": {...}, "module": 模块对象}]``。

    :param force: True 时忽略缓存重新扫描（改了插件想立刻生效时用）
    """
    global _cache
    if _cache is not None and not force:
        return _cache

    found: list[dict[str, Any]] = []
    warnings: list[str] = []
    root = plugin_dir()
    if root.exists():
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            entry = folder / ENTRY_FILE
            if not entry.exists():
                continue
            try:
                module = _import_plugin(entry)
            except Exception as exc:  # 插件写错了不能带崩主程序
                warnings.append(f"插件 {folder.name} 加载失败，已跳过：{exc}")
                continue
            hooks: dict[str, Callable[..., Any]] = {}
            for name in OPTIONAL_HOOKS:
                hook = getattr(module, name, None)
                if callable(hook):
                    hooks[name] = hook
            found.append({"info": _describe(module, folder.name), "module": module, "hooks": hooks})

    _cache = found
    _warnings[:] = warnings
    return found


def warnings() -> list[str]:
    """上一次 :func:`discover` 里被跳过的插件和原因。"""
    discover()
    return list(_warnings)


def extra_modules() -> list[dict[str, Any]]:
    """所有插件提供的追加模块；插件出错就当它没提供，不影响题库。"""
    modules: list[dict[str, Any]] = []
    for plugin in discover():
        hook = plugin["hooks"].get("modules")
        if not hook:
            continue
        try:
            produced = hook() or []
        except Exception:
            _warnings.append(f"插件 {plugin['info']['id']} 的 modules() 报错，已忽略")
            continue
        for module in produced:
            if isinstance(module, dict) and module.get("id"):
                modules.append(module)
    return modules


def detail_panels(point: dict, colors: dict[str, str]) -> list[tuple[str, Any]]:
    """详情页要追加的自定义面板：``[(插件名, flet 控件), ...]``。"""
    panels: list[tuple[str, Any]] = []
    for plugin in discover():
        hook = plugin["hooks"].get("detail_panel")
        if not hook:
            continue
        try:
            control = hook(point, colors)
        except Exception:
            _warnings.append(f"插件 {plugin['info']['id']} 的 detail_panel() 报错，已忽略")
            continue
        if control is not None:
            panels.append((plugin["info"]["name"], control))
    return panels


def startup(page) -> list[str]:
    """跑一遍各插件的 ``startup(page)``，返回成功执行的插件名。"""
    done: list[str] = []
    for plugin in discover():
        hook = plugin["hooks"].get("startup")
        if not hook:
            continue
        try:
            hook(page)
            done.append(plugin["info"]["name"])
        except Exception:
            _warnings.append(f"插件 {plugin['info']['id']} 的 startup() 报错，已忽略")
    return done


def summary() -> dict[str, Any]:
    """给「关于」类界面 / 测试用的一份插件清单。"""
    plugins = discover()
    return {
        "dir": str(plugin_dir()),
        "loaded": [plugin["info"] for plugin in plugins],
        "hooks": {plugin["info"]["id"]: sorted(plugin["hooks"]) for plugin in plugins},
        "warnings": warnings(),
    }