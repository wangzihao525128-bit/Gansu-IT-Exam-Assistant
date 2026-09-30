"""模块浏览页（需求文档 Step 4）：按 URL 参数加载模块的知识点列表。

路由约定：
    /                      首页
    /module/<module_id>    模块浏览页，例如 /module/module1
    /point/<module_id>/<point_id>   知识点详情页（Step 5）

首页模块卡片点击后 page.go(module_route(...))，由 main.py 的路由分发调用本模块。
"""

from __future__ import annotations

import flet as ft

from core import knowledge_store as store
from ui import branding, theme


def module_route(module_id: str) -> str:
    """模块页路由。"""
    return f"/module/{module_id}"


def point_route(module_id: str, point_id: str) -> str:
    """知识点详情页路由（Step 5 会用到）。"""
    return f"/point/{module_id}/{point_id}"


def _preview(content: str, limit: int = 46) -> str:
    """从 Markdown 讲解里取第一句正文当卡片预览。"""
    for line in str(content).splitlines():
        text = line.strip().lstrip("#").strip()
        if text and not text.startswith("**"):
            return text[:limit] + ("…" if len(text) > limit else "")
    return ""


def back_button(page: ft.Page, label: str = "返回首页") -> ft.Container:
    """顶部导航栏左侧的返回按钮。"""
    return ft.Container(
        content=ft.Text(f"← {label}", color="#FFFFFF", size=13),
        on_click=lambda _event: page.go("/"),
        ink=True,
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
    )


def _point_card(page: ft.Page, module: dict, point: dict) -> ft.Container:
    c = theme.colors()
    color = module.get("color", theme.PRIMARY)
    questions = len(point.get("questions", []))
    hints = len(point.get("hints") or {})
    code_lines = len(point.get("code_example", "").splitlines())
    preview = _preview(point.get("content", ""))
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(str(point.get("id", "")), color="#FFFFFF", size=12),
                            bgcolor=color,
                            border_radius=8,
                            padding=ft.padding.symmetric(horizontal=8, vertical=3),
                        ),
                        ft.Text(
                            point.get("title", ""),
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=c["text"],
                            expand=True,
                        ),
                        ft.Text("›", size=18, color=c["sub"]),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                ),
                ft.Text(
                    f"{questions} 道练习题 · 代码示例 {code_lines} 行 · {hints} 条提示",
                    size=12,
                    color=c["sub"],
                ),
                ft.Text(preview, size=12, color=c["sub"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=8,
            tight=True,
        ),
        bgcolor=c["card"],
        border=ft.border.all(1, c["border"]),
        border_radius=theme.RADIUS,
        padding=16,
        ink=True,
        on_click=lambda _event, m=module, p=point: page.go(point_route(m.get("id", ""), p.get("id", ""))),
    )


def _next_module_card(page: ft.Page, module: dict) -> ft.Container:
    """「下一个模块」引导卡。

    动机：模块一只有 3 个知识点、模块三到五只有 1 个，
    卡片只占上半屏，下半屏约 40% 是空的——视感上稍稀疏。
    不能用空白卡片来“撑高度”，那样只是把空白做成更好看的样子。
    改成真的有用引导：学完这个模块之后自然会想去下一个。
    它既填上了空白，又真的帮学生按顺序学完五个模块。
    """
    c = theme.colors()
    modules = store.get_modules()
    order = [m.get("id") for m in modules]
    try:
        here = order.index(module.get("id"))
    except ValueError:
        here = -1
    nxt = modules[here + 1] if 0 <= here < len(order) - 1 else None

    if nxt is None:  # 已经是最后一个模块
        head, sub, target = "✓ 五个模块已经遍完了", "回首页再看一遍模块卡片，或者直接进任何一个详情页练习", "/"
    else:
        head = f"下一个：{nxt.get('name', '')}"
        sub = f"{len(nxt.get('points', []))} 个知识点 · 点进去继续学"
        target = module_route(nxt.get("id", ""))
    return ft.Container(
        content=ft.Row(
            [
                ft.Column([ft.Text(head, size=14, weight=ft.FontWeight.BOLD, color=c["text"]), ft.Text(sub, size=12, color=c["sub"])], spacing=4, expand=True),
                ft.Text("›", size=20, color=c["sub"]),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=c["card"],
        border=ft.border.all(1, c["border"]),
        border_radius=theme.RADIUS,
        padding=16,
        ink=True,
        on_click=lambda _event, t=target: page.go(t),
    )


def _missing_module(page: ft.Page, module_id: str) -> None:
    c = theme.colors()
    page.add(
        ft.Container(
            content=ft.Row([back_button(page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=theme.PRIMARY,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
        ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"没有找到这个模块：{module_id}", size=17, weight=ft.FontWeight.BOLD, color=c["text"]),
                    ft.Text("可能是链接输错了，点左上角返回首页重新选一个模块。", size=13, color=c["sub"]),
                ],
                spacing=10,
            ),
            padding=24,
            expand=True,
        ),
    )


def build_module_page(page: ft.Page, module_id: str) -> None:
    """按 module_id 渲染模块浏览页。"""
    c = theme.colors()
    page.bgcolor = c["bg"]
    page.padding = 0

    module = store.get_module(module_id)
    if module is None:
        _missing_module(page, module_id)
        return

    points = module.get("points", [])
    question_count = sum(len(point.get("questions", [])) for point in points)
    color = module.get("color", theme.PRIMARY)

    header = ft.Container(
        content=ft.Row(
            [
                back_button(page),
                branding.author_chip(),
                ft.Text(module.get("name", ""), size=17, weight=ft.FontWeight.BOLD, color="#FFFFFF", expand=True),
                ft.Text(f"{len(points)} 知识点", size=12, color="#FFFFFF"),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        bgcolor=color,
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
    )

    body = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    f"共 {len(points)} 个知识点 · {question_count} 道练习题，点任意一条进入讲解与代码练习",
                    size=13,
                    color=c["sub"],
                ),
                *[_point_card(page, module, point) for point in points],
                _next_module_card(page, module),
            ],
            spacing=theme.GAP,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        padding=ft.padding.all(16),
        expand=True,
    )

    page.add(header, body)
