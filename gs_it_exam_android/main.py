r"""甘肃省信息技术会考学习软件 —— 统一程序入口。

同一套代码同时支持四个平台（需求文档「全平台支持」）：

    Windows 桌面端    python main.py
    浏览器 / Web 端   flet run --web --port 8550
    Android 安装包    flet build apk
    iOS 安装包        flet build ipa   （必须在 macOS + Xcode 上执行）

路由（需求文档 Step 4）：
    /                        首页
    /module/<module_id>      模块浏览页
    /point/<module_id>/<id>  知识点详情页
"""

from __future__ import annotations

import flet as ft

from core import knowledge_store
from core import local_store
from core import plugins
from ui import motion, theme
from ui.detail_page import build_detail_page
from ui.home_page import build_home
from ui.module_page import build_module_page, module_route

APP_TITLE = "甘肃省信息技术会考学习"


def route_change(page: ft.Page, route: str) -> None:
    """所有页面的分发入口。"""
    # 切页之前先把编辑器里还没落盘的敲键写下去：草稿是逐键合并保存的
    # （core.local_store.save_draft_soon，最多 0.8 秒写一次盘），
    # 不补这一笔，学生「敲两下就切走」时最后那几行代码就白写了。
    local_store.flush_pending()
    page.clean()
    parts = [part for part in (route or "/").strip("/").split("/") if part]

    if not parts:
        build_home(page)
    elif parts[0] == "module" and len(parts) >= 2:
        build_module_page(page, parts[1])
    elif parts[0] == "point" and len(parts) >= 3:
        build_detail_page(page, parts[1], parts[2])
    else:
        page.add(ft.Text(f"页面不存在：{route}", color=theme.DANGER))
        page.update()


def main(page: ft.Page) -> None:
    page.title = APP_TITLE
    # 需求文档 Step 9：从首页→模块页→详情页的切换动效，让学生知道自己到了哪里
    page.theme = ft.Theme(page_transitions=motion.page_transition_theme())
    try:
        problems = knowledge_store.validate()
    except Exception as error:  # 数据缺失或损坏时给中文提示，而不是抛栈
        page.add(ft.Text(f"知识点数据读取失败：{error}", color=theme.DANGER))
        return

    page.on_route_change = lambda event: route_change(page, event.route)
    # 关窗口（手机端是退到后台）时也补一次草稿：route_change 只在切页时补，
    # 学生「敲完直接关掉」那最后不到 0.8 秒的改动不然就随进程没了。
    page.on_disconnect = lambda _event: local_store.flush_pending()
    route_change(page, page.route)

    # 需求文档 8.4：界面建好之后给插件一次启动机会（可做初始化、埋点、自定义状态）。
    # 插件出错只会写进 plugins.warnings()，不会影响首页显示。
    plugins.startup(page)
    for note in plugins.warnings():
        print(f"[插件] {note}")

    if problems:
        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"数据校验发现 {len(problems)} 处问题，例如：{problems[0]}"),
            bgcolor=theme.WARNING,
        )
        page.snack_bar.open = True
        page.update()


if __name__ == "__main__":
    ft.app(target=main)
