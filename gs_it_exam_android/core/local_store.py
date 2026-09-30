r"""本地存档：代码草稿 + 练习题进度（需求文档 8.3 性能优化）。

全部塞进一个 JSON 文件，随手写、随手读；任何一步出错都不该影响主流程。

「不影响主流程」不等于「可以悄悄把存档弄丢」——这个文件里装的是学生**全部**的
草稿和答题记录，所以：

* 落盘走 :func:`_flush` 的原子写（同目录临时文件 + ``os.replace``），中途死掉
  最坏只丢这一次修改，不会留下半截 JSON；
* 读到坏文件先试 ``.bak``，实在救不回来就把坏文件改名成 ``.corrupt`` 留档，
  并把原因记进 :func:`last_error`。以前这里是「读不到就当没有存档」，
  而下次保存又会把文件覆盖掉，一次半截 JSON 就能让所有进度无声清零。
* 数据目录的「主目录能不能写」只探一次（模块级缓存）。以前每次调用都要往用户
  主目录写一个探针文件再删掉，而编辑器是逐键保存的，等于每敲一个字都多两次
  文件系统操作。

草稿的作用是：学生改了半截代码、切去别的知识点再回来，代码还在。
逐键保存走 :func:`save_draft_soon`：内存立刻改（读的永远是最新的），
磁盘最多 0.8 秒写一次；切页 / 运行 / 退出前用 :func:`flush_pending` 补上最后一笔。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

APP_DIR_NAME = ".gs_it_exam"
FILE_NAME = "userdata.json"
BACKUP_SUFFIX = ".bak"        # 上一份写成功的存档，坏文件时靠它救场
CORRUPT_SUFFIX = ".corrupt"   # 坏文件的留档后缀；绝不覆盖它，留着才能查原因
SAVE_DELAY_SECONDS = 0.8      # 逐键保存的合并窗口（需求文档 8.3：别每键都写盘）

_drafts: dict[str, str] | None = None
_progress: dict[str, Any] | None = None
_data_dir_cache: Path | None = None  # 探过一次就记住，别再每键都探
_pending_since: float | None = None  # 有改动还没落盘时，记下第一次改动的时间
_load_error = ""   # 读存档时出的问题（人话说明，留给 last_error）
_write_error = ""  # 写存档时出的问题


def _data_dir() -> Path:
    """优先放用户主目录；主目录不可写时退回临时目录，保证功能可用。

    ``GS_EXAM_DATA_DIR`` 每次都现读（一次字典查找，不碰磁盘），所以测试脚本
    在 import 之前甚至之后设它都算数。

    「主目录能不能写」的结果才缓存到模块级：这里原本每次调用都要在用户主目录
    写一个探针文件再删掉，而保存草稿是逐键触发的，等于每敲一个字都摊上两次
    多余的文件系统操作。缓存之后代价从「每键一次」降到「每次启动一次」。
    """
    global _data_dir_cache
    override = os.environ.get("GS_EXAM_DATA_DIR")  # 测试和绿色版可以用它指到临时目录
    if override:
        return Path(override)
    if _data_dir_cache is not None:
        return _data_dir_cache
    try:
        home = Path.home()
        probe = home / ".gs_it_exam_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        _data_dir_cache = home / APP_DIR_NAME
    except Exception:
        _data_dir_cache = Path(tempfile.gettempdir()) / APP_DIR_NAME
    return _data_dir_cache


def _data_path() -> Path:
    return _data_dir() / FILE_NAME


def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + BACKUP_SUFFIX)


def _read_json(path: Path) -> tuple[str, Any]:
    """读一个 JSON 存档，返回 ``("ok", 数据)`` / ``("missing", None)`` / ``("broken", None)``。

    三种情况必须分开：文件不存在是「第一次用」，坏文件却是「学生的进度有危险」，
    以前两者都被 ``except Exception`` 混成空字典，坏文件就这么被当成没存档了。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "broken", None
    try:
        return "ok", json.loads(text)
    except Exception:
        return "broken", None


def _keep_corrupt(path: Path) -> str:
    """把坏文件改名留档（``userdata.json.corrupt``），返回留档后的文件名。

    关键是**不能**让它留在原地：下次 :func:`_flush` 的 ``os.replace`` 会把它顶掉，
    那唯一的现场就没了，学生的数据再也救不回来。
    """
    target = path.with_name(path.name + CORRUPT_SUFFIX)
    if target.exists():  # 已经留过一次档了，别把上一份盖掉
        target = path.with_name(f"{path.name}{CORRUPT_SUFFIX}.{int(time.time())}")
    try:
        os.replace(path, target)
    except OSError:
        return path.name  # 改名也失败（文件被占等）：至少别抛出去影响主流程
    return target.name


def _atomic_write(path: Path, text: str) -> None:
    """同目录临时文件 + ``os.replace``：目标文件要么是旧的、要么是新的。

    ``os.replace`` 在同一分区上是原子的，所以中途断电 / 被杀进程只会丢掉这一次
    修改，不会像 ``Path.write_text`` 那样先把文件截断、留下半截 JSON。
    """
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent), prefix=path.name + ".", suffix=".tmp", delete=False
    )
    tmp = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())  # 先落盘再替换，掉电也不会拿半截文件去顶掉好的
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _note_load_error(message: str) -> None:
    global _load_error
    _load_error = message


def _note_write_error(message: str) -> None:
    global _write_error
    _write_error = message


def last_error() -> str:
    """上一次存档出问题时的人话说明；一切正常时返回空串。

    给界面用的：写失败不再是「只当没发生」，而是能显示给学生看。
    读存档时的告警（比如从备份恢复）会一直留着，直到 :func:`reset_all`。
    """
    return _write_error or _load_error


def _load() -> None:
    """读一次就缓存在内存里，之后直接用内存的那份（8.3：避免频繁 IO）。

    读到坏文件时不再「当没有存档」：先试 ``.bak``，救不回来就把坏文件改名
    留档，并把原因记进 :func:`last_error`，绝不静默清零学生的进度。
    """
    global _drafts, _progress
    if _drafts is not None and _progress is not None:
        return
    path = _data_path()
    state, data = _read_json(path)
    if state == "broken":
        kept = _keep_corrupt(path)
        backup = _backup_path(path)
        backup_state, backup_data = _read_json(backup)
        if backup_state == "ok" and isinstance(backup_data, dict):
            data = backup_data
            _note_load_error(f"存档文件损坏，已从备份 {backup.name} 恢复；坏文件留档为 {kept}。")
        else:
            data = {}
            _note_load_error(f"存档文件损坏且备份不可用，坏文件已留档为 {kept}，这次草稿和答题记录从空开始。")
    elif state == "missing":
        data = {}  # 第一次用，正常情况
    if not isinstance(data, dict):
        data = {}
    drafts = data.get("drafts")
    progress = data.get("progress")
    _drafts = drafts if isinstance(drafts, dict) else {}
    _progress = progress if isinstance(progress, dict) else {}


def _flush() -> bool:
    """把内存里的存档整体落盘；返回是否写成功，失败原因记进 :func:`last_error`。

    写盘分两步：先写同目录的临时文件，再 ``os.replace`` 顶掉真文件；
    写新的之前先把上一份好文件复制成 ``.bak``，坏文件才有得救。
    失败不再 ``except: pass`` —— 学生的进度没保存成功，界面有权知道。
    """
    global _pending_since, _write_error
    _load()
    if _drafts is None or _progress is None:
        # 这里原来是 assert：python -O 会把整条断言去掉，变成 AttributeError，
        # 所以必须写成显式判断（下面几个函数同理）。
        _note_write_error("存档内存状态没有初始化，这次没有写入。")
        return False
    try:
        directory = _data_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / FILE_NAME
        payload = json.dumps({"drafts": _drafts, "progress": _progress}, ensure_ascii=False, indent=2)
        if path.exists():
            _atomic_write(_backup_path(path), path.read_text(encoding="utf-8"))
        _atomic_write(path, payload)
    except Exception as error:
        # 存档写不了不该影响使用，但要说出来：保留 _pending_since，
        # 下一次 save_draft_soon / flush_pending 还会再试一次。
        _note_write_error(f"存档写入失败（{error.__class__.__name__}: {error}），这次改动可能没保存。")
        return False
    _write_error = ""
    _pending_since = None
    return True


def save_draft(point_id: str, code: str) -> None:
    """记下这个知识点当前编辑器里的代码（立刻落盘，直接调用方用它）。"""
    if not point_id:
        return
    _load()
    if _drafts is None:
        _note_write_error("草稿内存状态没有初始化，这次修改没有保存。")
        return
    _drafts[point_id] = code
    _flush()


def save_draft_soon(point_id: str, code: str) -> None:
    """编辑器逐键保存用的版本：内存立刻改，磁盘最多每 0.8 秒写一次。

    编辑器每敲一个键都会调它。以前每键都要把全部草稿重新序列化写盘
    （400 行草稿约 13KB），再加上主目录探针，一句代码就能触发几百次 IO。
    内存是立刻更新的（:func:`load_draft` 读到的永远是最新的），
    磁盘延后一点；切页（main.route_change）、运行代码、还原示例、退出前
    都会调 :func:`flush_pending` 把最后一笔补上。
    """
    global _pending_since
    if not point_id:
        return
    _load()
    if _drafts is None:
        _note_write_error("草稿内存状态没有初始化，这次修改没有保存。")
        return
    _drafts[point_id] = code
    now = time.monotonic()
    if _pending_since is None:
        _pending_since = now
        return
    if now - _pending_since >= SAVE_DELAY_SECONDS:
        _flush()  # 成功会清掉 _pending_since，失败留着，下次接着试


def flush_pending() -> bool:
    """把还没落盘的改动立刻写下去；本来就没有待写内容时返回 True。

    页面切走、点运行、退出之前都该调一次，否则最后不到 0.8 秒的敲键会丢。
    """
    if _pending_since is None:
        return True
    return _flush()


def has_pending() -> bool:
    """有没有改动还没落盘。

    留给自检 / 排查用：逐键保存是延后写盘的，怀疑「草稿怎么没保存」时
    先看这里，就能区分「还没到写盘时机」和「写了但失败」（后者看 last_error）。
    """
    return _pending_since is not None


def load_draft(point_id: str, default: str = "") -> str:
    """取回草稿；没有就用 default（一般是知识点自带的 code_example）。"""
    _load()
    if _drafts is None:  # 原来是 assert，-O 下会被去掉
        return default
    value = _drafts.get(point_id)
    return value if isinstance(value, str) else default


def clear_draft(point_id: str) -> None:
    _load()
    if _drafts is None:
        _note_write_error("草稿内存状态没有初始化，这次修改没有保存。")
        return
    _drafts.pop(point_id, None)
    _flush()


def record_answer(point_id: str, question_key: str, chosen: str, correct: bool) -> None:
    """记一道题的作答情况（需求文档 8.3：答题进度本地存储）。

    :param question_key: 这道题的**稳定身份**，由
        :func:`core.knowledge_store.question_key` 算出来。
        以前这里传的是题目在列表里的下标（``question_index``），
        结果题库一改顺序/删一道题，旧记录就错位或虚高（界面会出现「已答 5 / 2 题」）。
        题库扩写就是这个项目的下一步计划，所以必须按内容取键，不能按位置。
        学生机器上已经存着的旧下标键不用迁移：那些题重答一次就会被新键覆盖。
    """
    if not point_id:
        return
    _load()
    if _progress is None:
        _note_write_error("答题记录内存状态没有初始化，这次修改没有保存。")
        return
    answers = _progress.setdefault(point_id, {})
    if not isinstance(answers, dict):
        answers = {}
        _progress[point_id] = answers
    answers[str(question_key)] = {"chosen": chosen, "correct": bool(correct)}
    _flush()


def load_answers(point_id: str) -> dict[str, Any]:
    _load()
    if _progress is None:  # 原来是 assert，-O 下会被去掉
        return {}
    answers = _progress.get(point_id)
    return dict(answers) if isinstance(answers, dict) else {}


def quiz_stat(point_id: str) -> dict[str, int]:
    """这个知识点答过几道、对了几道，用于详情页顶部的进度提示。"""
    answers = load_answers(point_id)
    return {
        "answered": len(answers),
        "correct": sum(1 for item in answers.values() if isinstance(item, dict) and item.get("correct")),
    }




def module_stat(module: dict) -> dict[str, int]:
    """一个模块的答题汇总：总题数 / 已答 / 答对 / 练过的知识点数。

    给 :mod:`ui.progress_panel` 用。``module`` 直接传 knowledge_store 里的模块 dict，
    这里不去 import knowledge_store，是为了不跟数据层互相依赖。
    """
    points = module.get("points", []) if isinstance(module, dict) else []
    total = answered = correct = touched = 0
    for point in points:
        questions = point.get("questions", []) or []
        total += len(questions)
        stat = quiz_stat(str(point.get("id", "")))
        answered += stat["answered"]
        correct += stat["correct"]
        if stat["answered"]:
            touched += 1
    return {
        "points": len(points),
        "total": total,
        "answered": answered,
        "correct": correct,
        "touched": touched,
    }


def overall_stat(modules: list[dict]) -> dict[str, int]:
    """全部模块加在一起的汇总，首页那张总进度卡用。"""
    total = answered = correct = touched = points = 0
    for module in modules or []:
        stat = module_stat(module)
        total += stat["total"]
        answered += stat["answered"]
        correct += stat["correct"]
        touched += stat["touched"]
        points += stat["points"]
    return {
        "points": points,
        "total": total,
        "answered": answered,
        "correct": correct,
        "touched": touched,
    }



def clear_progress(point_id: str) -> None:
    _load()
    if _progress is None:
        _note_write_error("答题记录内存状态没有初始化，这次修改没有保存。")
        return
    _progress.pop(point_id, None)
    _flush()


def reset_all() -> None:
    """清空草稿与答题记录（设置页的「清除学习记录」会用到）。"""
    global _drafts, _progress, _load_error
    _drafts, _progress = {}, {}
    _load_error = ""  # 数据都是新的了，之前「从备份恢复」的告警不再相关
    _flush()
