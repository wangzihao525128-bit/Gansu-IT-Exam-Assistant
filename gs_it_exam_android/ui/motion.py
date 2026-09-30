r"""交互动效（需求文档 Step 9：“优化 UI 细节与交互动画”）。

为什么单独抽一个文件：动效参数散在各组件里，很容易成为“那里动一下、
那里动一下”的雖琐配置。集中在这里，方便统一调整。

**为什么用的是 `AnimatedSwitcher` 而不是 `animate_opacity`**：
flet 0.23 的动画 API 只有 `AnimatedSwitcher` / `Animation` / `AnimationCurve`，
`animate_opacity` 是新版 Flet（0.70+）才有的，写了就跑不起来。

**使用方式很关键**：弹窗自己必须保持同一个对象，只是换它的 `.content`，
然后调 `page.update()`。如果每次重新 `new` 一个弹窗对象，旧弹窗已经从控制树里消失了，
就没有“退出”的动画可播，只会弄得一下闪现。
"""

from __future__ import annotations

import flet as ft

# 时长统一在 120~260 毫秒之间。学生点了按钮就期待反馈，
# 很慢会让人怀疑点没点着；快到看不出动画才是真正的“响应”。
FAST_MS = 130   # 收起条（旧内容退出）——要快，不拖下一步
SHOW_MS = 220   # 新内容进场
CLEAR_MS = 160  # 「还原示例」这类重置操作


def result_switcher(content: ft.Control, height: int | None = None) -> ft.AnimatedSwitcher:
    """运行结果区的弹窗。

    结果出现时缩放闪现，学生的视线会自然落在绿色/红色那一行上。

    `height` 为 None 时按内容自然高度（手机端整页滚动用）；
    桌面端传固定高度，避免输出一长就把下方的代码解释区顶出台卡。
    """
    return ft.AnimatedSwitcher(
        content=content,
        duration=SHOW_MS,
        reverse_duration=FAST_MS,
        transition=ft.AnimatedSwitcherTransition.SCALE,
        switch_in_curve=ft.AnimationCurve.EASE_OUT_BACK,
        switch_out_curve=ft.AnimationCurve.EASE_IN,
        **({"height": height} if height else {}),
    )


def feedback_switcher(content: ft.Control) -> ft.AnimatedSwitcher:
    """答题判分结果条的弹窗。

    只用淡入：判分条里有「你选的」和「正确答案」两行字，
    缩放会让它在出现时瞬间大一下又缩回去，留下的印象比原设想更得压封。
    """
    return ft.AnimatedSwitcher(
        content=content,
        duration=SHOW_MS,
        reverse_duration=FAST_MS,
        transition=ft.AnimatedSwitcherTransition.FADE,
        switch_in_curve=ft.AnimationCurve.EASE_OUT,
        switch_out_curve=ft.AnimationCurve.EASE_IN,
    )


def page_transition_theme() -> ft.PageTransitionsTheme:
    """页面之间跳转的动效。

    flet 0.23 的路由切换默认是点击立刻换。改成「旧页面上移 + 淡出」，
    会人眼体感上提升一个级别——不想回去时不会误以为卡得没点。

    注意：flet 0.23 的 `PageTransitionTheme` 是**枚举**（不是带 transition 参数的类），
    可选值只有 NONE / FADE_UPWARDS / OPEN_UPWARDS / ZOOM / CUPERTINO。
    """
    return ft.PageTransitionsTheme(
        android=ft.PageTransitionTheme.FADE_UPWARDS,
        ios=ft.PageTransitionTheme.CUPERTINO,
        windows=ft.PageTransitionTheme.FADE_UPWARDS,
        macos=ft.PageTransitionTheme.FADE_UPWARDS,
        linux=ft.PageTransitionTheme.FADE_UPWARDS,
    )
