"""知识点数据层：读取、内存缓存、检索与题目工具。

数据文件：data/knowledge_points.json
它是「资料」文件夹中《甘肃省信息技术会考学习软件-知识点数据.json》的原样拷贝，
本模块所有字段都按该文件的真实结构编写，不臆造字段。

真实结构（已核对：5 个模块 / 11 个知识点 / 15 道练习题）::

    {
      "modules": [
        {
          "id": "module1",
          "name": "模块一：数据与信息",
          "color": "#4A90E2",
          "points": [
            {
              "id": "1_1",
              "title": "数据、信息和知识的概念",
              "content": "Markdown 格式的讲解正文",
              "code_example": "Python 示例代码",
              "code_explanation": "代码解释文本",
              "hints": {"print": "print() 用于输出内容"},
              "questions": [
                {
                  "type": "choice",
                  "question": "下列关于数据的说法正确的是（ ）",
                  "options": ["A. 数据就是信息", "B. 数据是记录下来的可以被鉴别的符号"],
                  "answer": "B",
                  "explanation": "答案解析"
                }
              ]
            }
          ]
        }
      ]
    }

两个容易踩坑的地方：
1. questions[].answer 存的是选项字母（"B"），不是选项下标；
2. options 里的每一项已经自带 "A. " 这样的序号前缀。
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path
from typing import Any

BUNDLED_DATA = Path(__file__).resolve().parent.parent / "data" / "knowledge_points.json"


def data_file() -> Path:
    """找知识点数据文件，优先用程序旁边的 data\ 目录（老师可直接改 JSON 换题库）。

    1. ``<程序目录>/data/knowledge_points.json`` —— 打包后 exe 旁边那份，可编辑；
    2. PyInstaller 打进包里的 ``_MEIPASS/data/...`` —— 只读的兜底副本。

    这样既满足「未来只改 JSON 就能更新知识点」，又不会因为删了旁边的
    data 目录就整个软件读不到数据。
    """
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).resolve().parent / "data" / "knowledge_points.json"
        if portable.exists():
            return portable
        return BUNDLED_DATA
    return BUNDLED_DATA


DATA_FILE = data_file()

POINT_KEYS = ("id", "title", "content", "code_example", "code_explanation", "hints", "questions")
QUESTION_KEYS = ("type", "question", "options", "answer", "explanation")

_lock = threading.Lock()
# _modules_cache 只放官方 JSON 里的模块，永远不被插件污染；
# _merged_cache 才是「对外看到的那份」= 官方 + 插件追加。
_modules_cache: list[dict[str, Any]] = []
_merged_cache: list[dict[str, Any]] | None = None
_loaded_mtime: float | None = None
_plugin_notes: list[str] = []


def _plugin_modules() -> list[dict[str, Any]]:
    """问插件要「追加的模块」。插件没装、或者 core.plugins 不可用时安静返回空表。"""
    try:
        from core import plugins
    except Exception:  # pragma: no cover - 极端情况下才走
        return []
    try:
        return plugins.extra_modules()
    except Exception as exc:  # pragma: no cover - extra_modules 内部已兜底
        _plugin_notes.append(f"插件模块读取失败，已忽略：{exc}")
        return []


def _merge_plugin_modules(base: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把插件提供的模块接在官方模块后面。

    一条硬规则：**插件只能加，不能改**。id 和官方模块撞车的插件模块直接丢掉，
    免得第三方插件把教材原题顶掉。学生看到的内容永远以 data\knowledge_points.json 为准。
    """
    _plugin_notes.clear()
    extras = _plugin_modules()
    if not extras:
        return base
    known = {str(module.get("id", "")) for module in base}
    merged = list(base)
    for module in extras:
        mid = str(module.get("id", ""))
        if mid in known:
            _plugin_notes.append(f"插件模块 id {mid!r} 与已有模块重名，已忽略该插件模块")
            continue
        known.add(mid)
        merged.append(module)
    return merged


def plugin_notes() -> list[str]:
    """上一次合并时对插件做出的处置记录（重名忽略之类），给测试和排查用。"""
    load()
    return list(_plugin_notes)


def _read_raw() -> dict[str, Any]:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"找不到知识点数据文件：{DATA_FILE}")
    with DATA_FILE.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def split_option(option: str) -> tuple[str, str]:
    """把 'B. 数据是记录下来的可以被鉴别的符号' 拆成 ('B', '数据是记录下来的可以被鉴别的符号')。"""
    text = str(option).strip()
    head, separator, tail = text.partition(".")
    letter = head.strip()
    if separator and len(letter) == 1 and letter.isalpha():
        return letter.upper(), tail.strip()
    return "", text


def _check_modules(modules: list[dict[str, Any]], problems: list[str], tag: str = "") -> None:
    """逐个模块检查结构，把发现的问题追加进 problems。

    :param tag: 非空时给每条问题加前缀——插件模块的报错要能一眼看出是谁带来的。
    """
    head = f"{tag} " if tag else ""
    for module in modules:
        mid = module.get("id", "?")
        for key in ("id", "name", "color", "points"):
            if key not in module:
                problems.append(f"{head}模块 {mid} 缺少字段 {key}")
        for point in module.get("points", []):
            pid = point.get("id", "?")
            for key in POINT_KEYS:
                if key not in point:
                    problems.append(f"{head}知识点 {pid} 缺少字段 {key}")
            for index, question in enumerate(point.get("questions", []), start=1):
                label = f"{head}知识点 {pid} 第 {index} 题"
                for key in QUESTION_KEYS:
                    if key not in question:
                        problems.append(f"{label} 缺少字段 {key}")
                letters = [split_option(option)[0] for option in question.get("options", [])]
                answer = str(question.get("answer", "")).strip().upper()
                if letters and answer not in letters:
                    problems.append(f"{label} 的答案 {answer!r} 不在选项字母 {letters} 中")


def validate(data: dict[str, Any] | None = None) -> list[str]:
    """检查数据结构，返回问题列表；空列表代表数据完全正常。

    传 data 就只查那一份；不传就查「官方 JSON + 插件追加的模块」，
    这样老师装了插件之后，主界面那条数据校验提示也会把插件的问题一起算进去。
    """
    if data is not None:
        if "modules" not in data:
            return ['顶层缺少 "modules" 字段']
        problems: list[str] = []
        _check_modules(data["modules"], problems)
        return problems

    raw = _read_raw()
    if "modules" not in raw:
        return ['顶层缺少 "modules" 字段']
    problems = []
    _check_modules(raw["modules"], problems)
    for extra in _plugin_modules():
        _check_modules([extra], problems, tag=f"[插件模块 {extra.get('id', '?')}] ")
    return problems


def load(force: bool = False) -> list[dict[str, Any]]:
    """读取全部模块（官方 JSON + 插件追加）；走内存缓存，数据文件被改动后会自动重载。"""
    global _loaded_mtime, _merged_cache
    mtime = DATA_FILE.stat().st_mtime if DATA_FILE.exists() else None
    with _lock:
        if not force and _modules_cache and mtime is not None and mtime == _loaded_mtime:
            if _merged_cache is not None:
                return _merged_cache
    modules = _read_raw()["modules"]
    with _lock:
        _modules_cache[:] = modules
        _loaded_mtime = mtime
    merged = _merge_plugin_modules(modules)
    with _lock:
        _merged_cache = merged
    return merged


def get_modules() -> list[dict[str, Any]]:
    """全部模块 = 官方 5 个 + 插件追加的；一个插件都没装时就是官方那 5 个。"""
    return load()


def get_module(module_id: str) -> dict[str, Any] | None:
    for module in load():
        if module.get("id") == module_id:
            return module
    return None


def get_points(module_id: str) -> list[dict[str, Any]]:
    module = get_module(module_id)
    return module.get("points", []) if module else []


def get_point(point_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """按知识点 id 查找，返回 (所属模块, 知识点)；找不到返回 None。"""
    for module in load():
        for point in module.get("points", []):
            if point.get("id") == point_id:
                return module, point
    return None


def search(keyword: str) -> list[dict[str, Any]]:
    """在标题、正文、代码、提示里搜索，返回 [{"module": 模块, "point": 知识点}]。"""
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return []
    hits: list[dict[str, Any]] = []
    for module in load():
        for point in module.get("points", []):
            haystack = "\n".join(
                [
                    str(point.get("title", "")),
                    str(point.get("content", "")),
                    str(point.get("code_example", "")),
                    str(point.get("code_explanation", "")),
                    " ".join(f"{key} {value}" for key, value in (point.get("hints") or {}).items()),
                ]
            ).lower()
            if keyword in haystack:
                hits.append({"module": module, "point": point})
    return hits


def answer_text(question: dict[str, Any]) -> str:
    """返回正确答案对应的选项文本（去掉 'B. ' 这类前缀）。"""
    answer = str(question.get("answer", "")).strip().upper()
    for option in question.get("options", []):
        letter, text = split_option(option)
        if letter == answer:
            return text
    return answer


def check_answer(question: dict[str, Any], user_answer: str) -> bool:
    """判分；用户传字母或整段选项文本都可以。"""
    answer = str(question.get("answer", "")).strip().upper()
    user = str(user_answer or "").strip()
    if not user:
        return False
    letter, text = split_option(user)
    if letter and letter.upper() == answer:
        return True
    if user.upper() == answer:  # 只传了选项字母，例如 "b"
        return True
    return text == answer_text(question)


def question_key(question: dict[str, Any], index: int = 0) -> str:
    """给一道练习题生成**稳定**的存档 key（答题进度就存在这个 key 上）。

    **为什么不能用题号（下标）当 key**：题库是 data\\knowledge_points.json，
    老师最常干的事就是改题——插一道、删一道、调一下顺序。存下标的话，学生的
    旧记录会在题序一变之后安到**另一道题**头上：卡片徽章写着「上次答对」，
    可题目早就不是那道了；多出来的旧 key 还会被算进统计里，印出「已答 5 / 2 题」
    这种不可能的数字。用题目自身的身份当 key 就没这个问题。

    生成规则（从稳到不稳，逐级退化）：

    1. 题目自带非空 ``id`` —— 用 ``str(id)``，老师改题干也不影响（推荐数据里配上 id）；
    2. 没有 id —— 用题干文本的 sha1 前 8 位，前缀 ``q``：题干一样就算同一道题，
       只有「题干被改写」才会当成新题（那本来就该重新答一遍）；
    3. 连题干都没有 —— 只能退回 ``i{index}``，这种题按内容区分不了。
    """
    raw_id = question.get("id")
    if raw_id is not None and str(raw_id).strip():
        return str(raw_id).strip()
    text = str(question.get("question", "") or "").strip()
    if text:
        return "q" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"i{index}"


def stats() -> dict[str, Any]:
    modules = load()
    points = [point for module in modules for point in module.get("points", [])]
    questions = [question for point in points for question in point.get("questions", [])]
    return {
        "modules": len(modules),
        "points": len(points),
        "questions": len(questions),
        "detail": [
            {
                "id": module.get("id"),
                "name": module.get("name"),
                "color": module.get("color"),
                "points": len(module.get("points", [])),
            }
            for module in modules
        ],
    }
