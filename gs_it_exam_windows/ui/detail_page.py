"""知识点详情页（需求文档 Step 5，核心页面）。

布局严格按需求文档 4.1 / 4.2：

* 电脑端三栏：左 25%（搜索 + 模块导航 + 知识点列表）、中 45%（标题 + 讲解 + 代码示例 + 练习题）、
  右 30%（代码编辑器 + 运行结果 + 代码解释区，解释区占底部 1/3）；
* 手机端上下堆叠：40% 讲解区、30% 编辑器区、30% 代码解释区。

Step 6~8 的三个组件已接入：右栏是代码编辑器（语法高亮 + 行号 + 自动缩进 + 沙箱运行），
中栏底部是练习题，右栏底部是代码解释 + 代码提示面板。
"""

from __future__ import annotations

import flet as ft

from core import code_executor
from core import knowledge_store as store
from core import plugins
from ui import branding, page_compat, theme
from ui.components.code_editor import (
    NARROW_CODE_PX,
    RESULT_BOX_PX_MOBILE_WIDE,
    CodeEditor,
    fit_height,
    fit_mobile_wide,
    fit_result_height,
)
from ui.components.hint_panel import HintPanel
from ui.components.quiz_card import build_quiz_list
from ui.module_page import module_route, point_route
from ui.progress_panel import module_panel

WIDE_BREAKPOINT = 900  # 窄于这个宽度就改成上下堆叠
WIDE_FLEX = (25, 45, 30)  # 电脑端三栏
NARROW_FLEX = (40, 30, 30)  # 手机端堆叠
# 逻辑高度低于这个值就当「矮窗口」，改用手机横屏那套按剩余高度算的布局。
#
# 780 是怎么来的：电脑端三栏的高度预算是「编辑器下限 150 + 固定开销 178 +
# 结果框 88 = 416」，右栏只占可用高度的 2/3，反推逻辑高度需要 ≈ 748 以上——
# tools\ui_smoke_test.py 里那条 `fits(761)` 就是把 761 当成刚好够用的边界。
# 但**实测比理论更紧**：窗口高 768（flet 逻辑高度 ≈ 754，要减掉约 14px 窗口边框）
# 走查就失败了（点得到「运行代码」，但结果框被挤出卡片，界面上什么都没有）。
# 所以留一点余量取 780：默认窗口 1180×800（逻辑高度 ≈ 786）仍然走原来的电脑端三栏，
# 而 1366×768 笔记本开 125% 缩放（逻辑高度 ≈ 600）这种就走矮窗口布局。
SHORT_WINDOW_BREAKPOINT = 780


def _is_narrow(page: ft.Page) -> bool:
    return (page.width or 0) < WIDE_BREAKPOINT


def _is_short(page: ft.Page) -> bool:
    """窗口逻辑高度太矮，电脑端三栏那套像素预算放不下。

    注意是**逻辑**高度：系统缩放 125% 时，1366×768 的屏幕只有 614 逻辑像素，
    所以「屏幕够大」不等于「放得下」。
    """
    height = float(getattr(page, "height", 0) or 0)
    return 0 < height < SHORT_WINDOW_BREAKPOINT


def _is_mobile(page: ft.Page) -> bool:
    """当前是不是安卓 / iOS 客户端。

    必须走 code_executor.platform_key：page.platform 是枚举，
    str() 出来是 "PagePlatform.ANDROID"，直接比 "android" 永远为假——
    这个坑让安卓端一度静默走桌面后端，手机上代码窗口点不动。
    """
    return code_executor.platform_key(getattr(page, "platform", "")) in {"android", "ios"}


def _apply_theme(page: ft.Page) -> None:
    """让 Markdown 这类原生控件也跟着亮/暗色切换。"""
    try:
        page.theme_mode = ft.ThemeMode.DARK if theme.mode() == "dark" else ft.ThemeMode.LIGHT
    except Exception:  # 不同 flet 版本字段可能不同，忽略即可
        pass


def _code_block(code: str, height=None, expand=None, size: int = 12) -> ft.Container:
    """深色等宽代码块。"""
    return ft.Container(
        content=ft.Text(
            code,
            font_family="Consolas",
            size=size,
            color="#E6E6E6",
            selectable=True,
        ),
        bgcolor=theme.CODE_BG,
        border_radius=10,
        padding=12,
        height=height,
        expand=expand,
    )


def _theory(point: dict, colors) -> ft.Control:
    """理论讲解：优先用 Flet 自带的 Markdown 控件。"""
    content = str(point.get("content", ""))
    try:
        return ft.Markdown(
            value=content,
            selectable=True,
            code_style=ft.TextStyle(font_family="Consolas", size=12),
        )
    except Exception:  # 极老版本没有 Markdown 控件时退回纯文本
        return ft.Text(content, size=13, color=colors["text"], selectable=True)


def _top_bar(page: ft.Page, module: dict, point: dict) -> ft.Container:
    color = module.get("color", theme.PRIMARY)
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Text(f"← 返回 {module.get('name', '')}", color="#FFFFFF", size=13),
                    on_click=lambda _event: page.go(module_route(module.get("id", ""))),
                    ink=True,
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                ),
                branding.author_chip(),
                ft.Text(
                    point.get("title", ""),
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color="#FFFFFF",
                    expand=True,
                ),
                ft.Text(str(point.get("id", "")), size=12, color="#FFFFFF"),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        bgcolor=color,
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
    )


def _point_row(page: ft.Page, module: dict, point: dict, active: bool, colors) -> ft.Container:
    color = module.get("color", theme.PRIMARY)
    return ft.Container(
        content=ft.Row(
            [
                ft.Text(str(point.get("id", "")), size=11, color=colors["sub"]),
                ft.Text(
                    point.get("title", ""),
                    size=13,
                    color=colors["text"],
                    expand=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            spacing=8,
        ),
        bgcolor=colors["card"],
        border=ft.border.all(2 if active else 1, color if active else colors["border"]),
        border_radius=8,
        padding=8,
        ink=True,
        on_click=lambda _event, p=point: page.go(point_route(module.get("id", ""), p.get("id", ""))),
    )


def _module_menu(page: ft.Page, module: dict, colors) -> ft.Column:
    """模块导航菜单：点任意模块跳到它的第一个知识点。"""
    items = [ft.Text("模块导航", size=12, weight=ft.FontWeight.BOLD, color=colors["sub"])]
    for each in store.get_modules():
        points = each.get("points", [])
        target = points[0].get("id") if points else None
        active = each.get("id") == module.get("id")
        items.append(
            ft.Container(
                content=ft.Text(
                    each.get("name", ""),
                    size=12,
                    color="#FFFFFF" if active else colors["sub"],
                ),
                bgcolor=each.get("color", theme.PRIMARY) if active else None,
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                ink=True,
                on_click=(
                    (lambda _event, mid=each.get("id", ""), pid=target: page.go(point_route(mid, pid)))
                    if target
                    else None
                ),
            )
        )
    return ft.Column(items, spacing=6, tight=True)


def _left_body(page: ft.Page, module: dict, point: dict, colors, panel_box: dict | None = None) -> ft.Column:
    """左栏：搜索框 + 模块导航 + 本模块知识点列表。"""
    points = module.get("points", [])
    list_column = ft.Column(spacing=6, tight=True, scroll=ft.ScrollMode.AUTO, expand=True)

    def refresh(_event=None) -> None:
        keyword = (search.value or "").strip().lower()
        shown = [p for p in points if not keyword or keyword in str(p.get("title", "")).lower()]
        if not shown:
            list_column.controls = [ft.Text("没有匹配的知识点", size=12, color=colors["sub"])]
        else:
            list_column.controls = [
                _point_row(page, module, p, p.get("id") == point.get("id"), colors) for p in shown
            ]
        page.update()

    search = ft.TextField(
        hint_text="在本模块内搜索知识点",
        prefix_icon=ft.icons.SEARCH,
        dense=True,
        on_change=refresh,
        border_color=colors["border"],
        bgcolor=colors["card"],
    )
    # 上面这一段自己滚动，下面这张进度卡固定在左栏最底。
    #
    # 这里踩过一个坑：一开始把进度卡直接排在 list_column 后面，
    # 而 list_column 是 expand=True 的（会吃掉全部剩余高度），
    # 结果卡片被顶到可视区外面去了——**控件在树里、冒烟测试查得到，
    # 屏幕上就是看不见**，只有对着真机截图才看得出来。
    # 所以拆成两层：滚动区和固定区各占一层，固定区永远露在最后。
    scrollable = ft.Column(
        [
            search,
            _module_menu(page, module, colors),
            ft.Text("知识点列表", size=12, weight=ft.FontWeight.BOLD, color=colors["sub"]),
            list_column,
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    body = ft.Column(
        [scrollable, _module_progress_box(module, colors, panel_box)],
        spacing=10,
        expand=True,
    )
    refresh()
    return body


def _center_body(
    page: ft.Page,
    module: dict,
    point: dict,
    colors,
    quiz: ft.Control,
    extra: list[ft.Control] | None = None,
) -> ft.Column:
    """中栏：标题 + 理论讲解 + 代码示例 + 练习题区。

    extra：手机横屏时把「代码解释 + 提示面板」塞进来。
    横屏右栏整列都要留给代码和运行结果，解释区再占 1/4 就把结果框挤没了。
    """
    controls: list[ft.Control] = [
            ft.Text(point.get("title", ""), size=20, weight=ft.FontWeight.BOLD, color=colors["text"]),
            ft.Text(
                f"知识点 {point.get('id', '')} · {module.get('name', '')}",
                size=12,
                color=colors["sub"],
            ),
            _theory(point, colors),
            ft.Text("代码示例", size=14, weight=ft.FontWeight.BOLD, color=colors["text"]),
            ft.Text(
                "右边「代码编辑器」里就是这一份，可以直接改一行再运行。",
                size=12,
                color=colors["sub"],
            ),
            _code_block(point.get("code_example", "")),
            quiz,
        ]
    controls.extend(extra or [])
    return ft.Column(
        controls,
        spacing=theme.GAP,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _editor_body(page: ft.Page, point: dict, colors, editor: CodeEditor) -> ft.Column:
    """代码区：Step 6 的编辑器组件（语法高亮 / 行号 / 自动缩进 / 沙箱运行）。"""
    return ft.Column(
        [
            ft.Text("代码编辑器", size=14, weight=ft.FontWeight.BOLD, color=colors["text"]),
            editor.control,
        ],
        spacing=theme.GAP,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


def _explanation_body(page: ft.Page, point: dict, colors, hints: HintPanel) -> ft.Column:
    """代码解释区：知识点自带的 code_explanation + Step 8 的代码提示面板。"""
    return ft.Column(
        [
            ft.Text("代码解释", size=14, weight=ft.FontWeight.BOLD, color=theme.WARNING),
            ft.Text(point.get("code_explanation", ""), size=12, color=colors["sub"], selectable=True),
            hints.control,
        ],
        spacing=theme.GAP,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
def _module_progress_box(module: dict, colors, panel_box: dict | None) -> ft.Container:
    """左栏底部的进度卡，同时把它登记到 panel_box，答题后好回头刷新。"""
    box = module_panel(module, colors)
    if panel_box is not None:
        panel_box["box"] = box
    return box


def _refresh_module_progress(panel_box: dict, page: ft.Page) -> None:
    """练习题判分后调它，左栏进度卡的数字立刻跟上，并且立刻推到屏幕上。

    **为什么这里还要 page.update()**：quiz_card.refresh() 的顺序是
    「先 page.update()，再回调 on_progress」，所以左栏进度卡的重画是整轮里
    **最后一次**控件树改动——改完没有刷新就发不出去。真机上左栏数字会一直停在
    旧值，要等到学生下次碰别的东西（切页、拖窗口）才蹦出来，看着像卡住了。
    冒烟测试只查内存里的控件树，看不见这一层，所以这里必须显式刷新。
    """
    box = panel_box.get("box")
    refresh = getattr(box, "refresh_progress", None) if box is not None else None
    if not callable(refresh):
        return
    try:
        refresh()
        update = getattr(page, "update", None)
        if callable(update):
            update()
    except Exception:  # 刷新进度失败不该把答题流程带崩
        pass


def _plugin_body(page: ft.Page, point: dict, colors) -> ft.Column | None:
    """需求文档 8.4 的落点：插件在详情页右栏底部追加的面板。

    一个插件都没装时返回 None，调用方就不插任何东西——**默认行为与没有这个接口时完全一致**。
    """
    panels = plugins.detail_panels(point, colors)
    if not panels:
        return None
    blocks: list[ft.Control] = [
        ft.Text("扩展功能", size=14, weight=ft.FontWeight.BOLD, color=colors["sub"])
    ]
    for name, control in panels:
        blocks.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(str(name), size=13, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        control,
                    ],
                    spacing=6,
                    tight=True,
                ),
                bgcolor=colors["bg"],
                border=ft.border.all(1, colors["border"]),
                border_radius=theme.RADIUS,
                padding=10,
            )
        )
    return ft.Column(blocks, spacing=theme.GAP, scroll=ft.ScrollMode.AUTO, expand=True)


def _region(body: ft.Column, colors, flex: int) -> ft.Container:
    """把一个内容区包成独立滚动、带圆角的卡片。"""
    return ft.Container(
        content=body,
        padding=ft.padding.all(14),
        # flex <= 0 表示「按内容自然高度」，手机端整页滚动时用这个，
        # 免得 30% 的屏幕高度把代码区和运行结果挤没。
        expand=flex if flex and flex > 0 else None,
        bgcolor=colors["card"],
        border_radius=theme.RADIUS,
    )


def _not_found(page: ft.Page, module_id: str, point_id: str) -> None:
    c = theme.colors()
    page.bgcolor = c["bg"]
    page.padding = 0
    page.add(
        ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text("← 返回模块", color="#FFFFFF", size=13),
                        on_click=lambda _event: page.go(module_route(module_id)),
                        ink=True,
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                    ),
                    branding.author_chip(),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=theme.PRIMARY,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
        ft.Container(
            content=ft.Column(
                [
                    ft.Text("没有找到这个知识点", size=17, weight=ft.FontWeight.BOLD, color=c["text"]),
                    ft.Text(
                        f"模块 {module_id} 下的 {point_id} 不存在，可能是链接输错了。",
                        size=13,
                        color=c["sub"],
                    ),
                ],
                spacing=10,
            ),
            padding=24,
            expand=True,
        ),
    )


def build_detail_page(page: ft.Page, module_id: str, point_id: str) -> None:
    """知识点详情页：宽屏三栏 25/45/30，窄屏上下堆叠 40/30/30。"""
    narrow = _is_narrow(page)
    short = _is_short(page)
    # 布局模式 = 宽窄 + 矮高，两者任一变化都要重建：
    # 只按宽度记缓存的话，学生把窗口拉矮跨过 700 这条线时页面不会重建，
    # 结果框就一直卡在被挤出去的位置。
    layout_mode = (narrow, short)
    cached = getattr(page, "data", None)
    if isinstance(cached, dict) and cached.get("detail_mode") == layout_mode and page.controls:
        return  # 布局模式没变，不必重建
    page.data = {"detail_mode": layout_mode}

    page.clean()
    _apply_theme(page)

    module = store.get_module(module_id)
    found = store.get_point(point_id)
    if module is None or found is None or found[0].get("id") != module_id:
        _not_found(page, module_id, point_id)
        return

    point = found[1]
    c = theme.colors()
    page.bgcolor = c["bg"]
    page.padding = 0

    # Step 6 编辑器与 Step 8 提示面板互相关联：代码一改，提示里
    # 「代码里用到了」的标记跟着更新。
    # panel_box 是左栏进度卡的「信箱」：卡片建好后把自己塞进来，
    # 练习题每次判分就通过它把左栏那张卡重画一遍。
    panel_box: dict = {}
    quiz = build_quiz_list(
        page,
        str(point.get("id", "")),
        list(point.get("questions") or []),
        c,
        on_progress=lambda: _refresh_module_progress(panel_box, page),
    )
    # 代码区高度要按窗口实际高度算：编辑器在右栏只占 2/3（手机端占 30%），
    # 高度给多了会把「运行状态 + 运行结果」挤出卡片，学生点运行看不到反馈。
    # 手机端是「整页滚动 + 区块按内容自然高度」，不再把编辑器按百分比压扁；
    # 电脑端右栏空间有限，才需要按窗口高度算代码区能有多高。
    share = 2 / 3
    editor_code = str(point.get("code_example", "") or "")
    editor_lines = len(editor_code.splitlines())
    # 示例代码里有 input() 时，编辑器里会多出「标准输入」一行，高度预算要算进去，
    # 否则那一行会把运行结果挤出卡片——正是之前踩过的那个坑。
    editor_needs_input = "input(" in editor_code
    # 「右栏整列给编辑器」是第三种情况（手机横屏，以及电脑上的矮窗口）：
    # 右栏卡片定高 + 内部滚动，代码区必须提前把运行结果的位置让出来，
    # 否则结果框会被顶到滚动区外面。
    # 竖屏不锁结果区高度（整页滚动），普通高度的电脑端用 fit_height 那套。
    #
    # 矮窗口（_is_short，例如 1366×768 笔记本开 125% 缩放 → 逻辑高度只有约 600）
    # 必须走这条路：实测那台尺寸下电脑端三栏放不下，
    # 结果框被挤到卡片滚动区外，学生点「运行代码」只看得见「运行中…」
    # （窗口高 768 这种逼近临界的情况也一样会失败）。
    # fit_mobile_wide 是按剩余高度倒推的，矮窗口也不会溢出。
    mobile_wide = (not narrow) and (_is_mobile(page) or short)
    if mobile_wide:
        editor_height = fit_mobile_wide(
            float(getattr(page, "height", 0) or 0), editor_lines, editor_needs_input
        )
        editor_result_height: int | None = RESULT_BOX_PX_MOBILE_WIDE
    elif narrow:
        editor_height = NARROW_CODE_PX
        editor_result_height = None
    else:
        editor_height = fit_height(page, editor_lines, share, editor_needs_input)
        editor_result_height = fit_result_height(share)
    editor = CodeEditor(
        page,
        point,
        c,
        height=editor_height,
        result_height=editor_result_height,
    )
    hints = HintPanel(point.get("hints"), c, code=editor.code(), page=page)
    editor.on_code_change = hints.set_code
    # 冒烟测试要模拟运行代码和答题，所以把三个组件挂在 page.data 上
    page.data = {"detail_mode": layout_mode, "editor": editor, "hints": hints, "quiz": quiz}

    # 8.4 插件面板：右栏最下面一块，高度按内容走（flex=0），不跟讲解区抢地方
    plugin_body = _plugin_body(page, point, c)
    plugin_region = _region(plugin_body, c, 0) if plugin_body is not None else None

    if narrow:
        stacked = [
            # 手机端：上下堆叠（讲解 → 代码 → 解释，需求文档 4.2），
            # 但高度按内容走、整页滚动，而不是死抠 40/30/30 的像素比例。
            _region(_center_body(page, module, point, c, quiz), c, 0),
            _region(_editor_body(page, point, c, editor), c, 0),
            _region(_explanation_body(page, point, c, hints), c, 0),
        ]
        # 手机端没有左栏（窄屏是讲解/代码/解释三段堆叠），进度卡放整页最后，
        # 否则这个模块的练习进度在手机上是彻底看不见的。
        stacked.append(_module_progress_box(module, c, panel_box))
        if plugin_region is not None:
            stacked.append(plugin_region)
        layout = ft.Column(
            stacked,
            spacing=theme.GAP,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    else:
        # 手机横屏（page.height 只有 600 逻辑像素上下）右栏卡片整块才 320px 高，
        # 再切一半给代码解释区，运行结果就露不出来了。所以横屏时右栏整列给编辑器，
        # 代码解释 + 提示面板挪到中栏（那里本来就在滚动阅读区，位置更自然）。
        if mobile_wide:
            right = [_region(_editor_body(page, point, c, editor), c, 1)]
            center_extra = [_region(_explanation_body(page, point, c, hints), c, 0)]
        else:
            center_extra = None
            right = [
                _region(_editor_body(page, point, c, editor), c, 2),
                _region(_explanation_body(page, point, c, hints), c, 1),
            ]
        if plugin_region is not None:
            right.append(plugin_region)
        layout = ft.Row(
            [
                _region(_left_body(page, module, point, c, panel_box), c, WIDE_FLEX[0]),
                _region(
                    _center_body(page, module, point, c, quiz, center_extra),
                    c,
                    WIDE_FLEX[1],
                ),
                ft.Column(
                    right,
                    spacing=theme.GAP,
                    expand=WIDE_FLEX[2],
                ),
            ],
            spacing=theme.GAP,
            expand=True,
        )

    page.add(
        _top_bar(page, module, point),
        ft.Container(content=layout, padding=ft.padding.all(12), expand=True),
    )
    page_compat.set_resize_handler(page, lambda event: build_detail_page(page, module_id, point_id))
