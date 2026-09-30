"""学习进度面板：把 8.3 存下来的答题进度显示出来（需求文档 8.4「组件高度模块化」）。

**为什么要有这块面板**：从 Step 7 起，每次答题都写进了 :mod:`core.local_store`，
但界面上只有练习题区那一行「已答 0 / 2 题」，还藏在详情页中栏很长内容的下面。
学生答完题只知道自己对了这一道，**不知道自己这个模块练到哪儿了、正确率如何**。

真机走查时还看到另外一件事：详情页左栏知识点列表只有 5 条，下半屏空掉约 350px；
首页「备考建议」下面也空掉约 250px。这块面板把**已经存好的数据**摆出来，
两个问题一起解决——不是为了填空白而加装饰，是数据本来就在那，只是没露出来。

**答题后会实时刷新**：容器上挂了 ``refresh_progress``，详情页把它挂到练习题的
进度回调上，学生点一下「提交答案」，左栏这张卡的数字就跟着变，不用翻页面。
（第一版就是漏在这里：``build_controls`` 闭包里把 answered/correct 在建卡时算死了，
结果只有「已练过 N 个知识点」那行会变，标题上的「0 / 5 题」永远不动。
是被 ``tools/ui_smoke_test.py`` 里那条「答题后左栏进度卡实时更新」断言逮住的。）

用法::

    from ui.progress_panel import module_panel, overall_panel
    box = module_panel(module, expand=1)      # 详情页左栏底部
    box.refresh_progress()                    # 数据变了就调它
    overall_panel(modules, expand=1)          # 首页右下
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from core import local_store
from ui import theme

StatFn = Callable[[], dict[str, int]]


def _bar(ratio: float, color: str, track: str) -> ft.Control:
    """一条进度条。优先用原生 ProgressBar，取不到就画两个叠起来的色块。"""
    ratio = max(0.0, min(1.0, float(ratio)))
    try:
        return ft.ProgressBar(value=ratio, color=color, bgcolor=track, height=6)
    except Exception:  # 不同 flet 版本字段不一样，退化成最朴素的两段色块
        return ft.Container(
            content=ft.Stack(
                [
                    ft.Container(bgcolor=track, border_radius=3, expand=True),
                    ft.Container(width=max(0.02, ratio) * 100, bgcolor=color, border_radius=3),
                ]
            ),
            height=6,
        )


def _make_panel(
    title: str,
    stat_fn: StatFn,
    extra_fn: Callable[[dict[str, int]], str],
    colors: dict[str, str],
    accent: str,
    expand: int | None,
    empty_hint: str,
) -> ft.Container:
    """进度卡的共用外壳。

    **每次重画都重新调一次 ``stat_fn``**——这是「答题后卡片会变」的关键。
    数字不能在建卡时算死，不然刷新只会刷出一张一模一样的卡。
    """
    color_of_title = colors["text"]
    sub = colors["sub"]
    border = colors["border"]

    def build_controls() -> list[ft.Control]:
        stat = stat_fn()
        total, answered, correct = stat["total"], stat["answered"], stat["correct"]
        # 夹住上限：老存档是按「题号」存 key 的（见 knowledge_store.question_key），
        # 题库改过题序之后那些对不上号的旧 key 还留在存档里，会被 module_stat /
        # overall_stat 照数不误。不夹就会印出「5 / 2 题」和超过 100% 的正确率——
        # 学生看到的是不可能的数字，只会以为软件坏了。total 为 0 时 answered
        # 一并归零，走下面「暂无题目」那条老路。
        answered = min(answered, total)
        correct = min(correct, answered)
        rate = f"{correct / answered * 100:.0f}%" if answered else "—"
        rows: list[ft.Control] = [
            ft.Row(
                [
                    ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=color_of_title, expand=True),
                    ft.Text(f"{answered} / {total} 题" if total else "暂无题目", size=12, color=sub),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ]
        rows.append(_bar(answered / total, accent, border) if total
                    else ft.Text(empty_hint, size=12, color=sub))
        rows.append(
            ft.Row(
                [
                    # 一题都还没答对时别用绿色：「答对 0 题」挂个成功色看着像在夸人。
                    ft.Text(f"答对 {correct} 题", size=12,
                            color=theme.SUCCESS if correct else sub),
                    ft.Text("·", size=12, color=sub),
                    ft.Text(f"正确率 {rate}", size=12, color=sub),
                ],
                spacing=6,
            )
        )
        hint = extra_fn(stat)
        if hint:
            rows.append(ft.Text(hint, size=12, color=sub))
        if not answered:
            rows.append(ft.Text("还没开始做练习题——先答一道，进度就会记在这儿。", size=12, color=sub))
        return rows

    column = ft.Column(build_controls(), spacing=8, tight=True)
    box = ft.Container(
        content=column,
        bgcolor=colors["card"],
        border=ft.border.all(1, colors["border"]),
        border_radius=theme.RADIUS,
        padding=18,
        expand=expand,
    )

    def refresh_progress() -> None:
        """重新读一遍 local_store 并重画卡面（数据是内存里的，几乎不耗时间）。"""
        column.controls = build_controls()

    box.refresh_progress = refresh_progress
    return box


def _touched_line(stat: dict[str, int]) -> str:
    return f"已练过 {stat['touched']} / {stat['points']} 个知识点"


def module_panel(module: dict, colors: dict[str, str] | None = None, expand: int | None = None) -> ft.Container:
    """详情页底部（宽屏在左栏、窄屏在整页最后）：当前模块的答题进度。"""
    c = colors or theme.colors()
    return _make_panel(
        title="本模块学习进度",
        stat_fn=lambda: local_store.module_stat(module),
        extra_fn=_touched_line,
        colors=c,
        accent=module.get("color", theme.PRIMARY),
        expand=expand,
        empty_hint="这个模块暂时没有练习题。",
    )


def overall_panel(modules: list[dict], colors: dict[str, str] | None = None, expand: int | None = None) -> ft.Container:
    """首页右下：五个模块合起来的总进度。"""
    c = colors or theme.colors()
    return _make_panel(
        title="学习进度",
        stat_fn=lambda: local_store.overall_stat(modules),
        extra_fn=_touched_line,
        colors=c,
        accent=theme.PRIMARY,
        expand=expand,
        empty_hint="题库里还没有练习题。",
    )