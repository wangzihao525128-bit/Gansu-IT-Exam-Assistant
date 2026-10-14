"""首页：顶部导航 + 欢迎语 + 模块卡片 + 备考建议（需求文档 Step 3）。

模块卡片直接读取 data/knowledge_points.json 的真实数据，
点击卡片通过 page.go() 跳到模块浏览页（Step 4 已接入）。
"""

from __future__ import annotations

import flet as ft

from core import knowledge_store
from ui import branding, page_compat, theme
from ui.module_page import module_route
from ui.progress_panel import overall_panel

GREETING = "把会考知识点，装进每天十分钟"
SUBTITLE = "甘肃省信息技术学业水平考试 · 教材七个模块同步精讲"
TIPS = [
    "每天挑 1 个知识点：先读讲解，再改一遍示例代码，最后做练习题。",
    "代码一定要亲手改一行再运行，看到输出变了才算学会。",
    "错题当天看解析，第二天再刷一遍同类题。",
]


def _open_module(page: ft.Page, module: dict) -> None:
    """点击模块卡片：按 URL 参数跳到模块浏览页。"""
    page.go(module_route(module.get("id", "")))


def _filter_modules(keyword: str) -> list[dict]:
    keyword = (keyword or "").strip()
    if not keyword:
        return knowledge_store.get_modules()
    hit_ids = {hit["module"].get("id") for hit in knowledge_store.search(keyword)}
    return [module for module in knowledge_store.get_modules() if module.get("id") in hit_ids]


def _module_card(page: ft.Page, module: dict, wide: bool) -> ft.Container:
    c = theme.colors()
    points = module.get("points", [])
    # 综合题自己不占答题位，摊平到小题上再数，否则卡片上的题数会少算。
    question_count = sum(
        len(knowledge_store.answerable_questions(point.get("questions", []))) for point in points
    )
    titles = "、".join(point.get("title", "") for point in points[:3])
    if len(points) > 3:
        titles += " 等"
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(height=6, bgcolor=module.get("color", theme.PRIMARY), border_radius=3),
                ft.Text(module.get("name", ""), size=17, weight=ft.FontWeight.BOLD, color=c["text"]),
                ft.Text(f"{len(points)} 个知识点 · {question_count} 道练习题", size=12, color=c["sub"]),
                ft.Text(titles, size=12, color=c["sub"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=8,
            tight=True,
        ),
        bgcolor=c["card"],
        border=ft.border.all(1, c["border"]),
        border_radius=theme.RADIUS,
        padding=18,
        width=320 if wide else None,
        ink=True,
        on_click=lambda event, module=module: _open_module(page, module),
    )


def _tips_card(expand: int | None = None) -> ft.Container:
    c = theme.colors()
    rows = [
        ft.Row(
            [
                ft.Text("·", color=theme.WARNING, size=16),
                ft.Text(tip, size=13, color=c["sub"], expand=True),
            ],
            spacing=8,
        )
        for tip in TIPS
    ]
    return ft.Container(
        content=ft.Column(
            [ft.Text("备考建议", size=15, weight=ft.FontWeight.BOLD, color=theme.WARNING), *rows],
            spacing=8,
            tight=True,
        ),
        bgcolor=c["card"],
        border=ft.border.all(1, c["border"]),
        border_radius=theme.RADIUS,
        padding=18,
        expand=expand,
    )


def _toggle_theme(page: ft.Page) -> None:
    theme.toggle()
    page.clean()
    build_home(page)


def build_home(page: ft.Page) -> None:
    c = theme.colors()
    page.bgcolor = c["bg"]
    page.padding = 0
    info = knowledge_store.stats()

    # 窗口尺寸只在「本次启动的第一次进首页」时定一次。
    #
    # 【真 bug，之前偷懒当已知取舍放过了】原来是无条件每次都设 1180x800，
    # 于是学生把窗口拖大、甚至最大化之后，点一下「返回首页」窗口就被强行缩回去——
    # 正在看的代码、正在写的题全被挤掉。之前在文档里写成"已知取舍"，那是不对的，
    # 这就是 bug，修掉。
    window = getattr(page, "window", None)
    if window is not None and not getattr(page, "_gs_window_sized", False):
        try:
            window.width, window.height = 1180, 800
            window.min_width, window.min_height = 680, 560
            page._gs_window_sized = True
        except Exception:  # 手机端没有桌面窗口概念，忽略
            pass

    cards_column = ft.Column(spacing=theme.GAP, tight=True)
    # 底部两张卡：备考建议 + 学习进度。放一起是因为首页下半屏原本空掉约 250px，
    # 而学习进度的数据从 Step 7 起就一直存着、只是没在首页露过面。
    bottom = ft.Column(spacing=theme.GAP, tight=True)

    def refresh(_event=None) -> None:
        keyword = search.value or ""
        modules = _filter_modules(keyword)
        wide = (page.width or 0) >= 720
        tips = _tips_card(1 if wide else None)
        progress = overall_panel(knowledge_store.get_modules(), c, 1 if wide else None)
        # 窄屏（手机）上下堆叠，宽屏左右各占一半
        bottom.controls = (
            [ft.Row([tips, progress], spacing=theme.GAP)]
            if wide
            else [ft.Column([tips, progress], spacing=theme.GAP)]
        )
        if not modules:
            cards_column.controls = [
                ft.Text(f"没有找到和「{keyword}」相关的知识点，换个关键词试试～", color=c["sub"], size=14)
            ]
        elif wide:
            cards_column.controls = [
                ft.Row(
                    [_module_card(page, module, True) for module in modules],
                    wrap=True,
                    spacing=theme.GAP,
                    run_spacing=theme.GAP,
                )
            ]
        else:
            cards_column.controls = [_module_card(page, module, False) for module in modules]
        page.update()

    search = ft.TextField(
        hint_text="搜索知识点…",
        # hint_text 不给 hint_style 时跟着主题走，实测在这套配色下会淡到看不见，
        # 搜索框就成了一个光秃秃的空框。颜色写死才稳。
        hint_style=ft.TextStyle(color=c["sub"], size=13),
        prefix_icon=ft.icons.SEARCH,
        on_change=refresh,
        border_color=c["border"],
        bgcolor=c["card"],
        dense=True,
    )

    theme_button = ft.Container(
        content=ft.Text("深色模式" if theme.mode() == "light" else "浅色模式", color="#FFFFFF", size=13),
        on_click=lambda _event: _toggle_theme(page),
        ink=True,
        padding=ft.padding.symmetric(horizontal=12, vertical=6),
    )

    header = ft.Container(
        content=ft.Row(
            [
                ft.Text("🎓  甘肃省信息技术会考学习", size=18, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                branding.author_chip(),
                ft.Container(expand=True),
                theme_button,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=theme.PRIMARY,
        padding=ft.padding.symmetric(horizontal=20, vertical=14),
    )

    body = ft.Container(
        content=ft.Column(
            [
                ft.Text(GREETING, size=24, weight=ft.FontWeight.BOLD, color=c["text"]),
                ft.Text(SUBTITLE, size=13, color=c["sub"]),
                ft.Text(
                    f"已收录 {info['modules']} 个模块 · {info['points']} 个知识点 · {info['questions']} 道练习题",
                    size=13,
                    color=c["sub"],
                ),
                search,
                cards_column,
                bottom,
            ],
            spacing=theme.GAP,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        padding=ft.padding.all(20),
        expand=True,
    )

    page_compat.set_resize_handler(page, lambda event: refresh())
    page.add(header, body)
    refresh()
