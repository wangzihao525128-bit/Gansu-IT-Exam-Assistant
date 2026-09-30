r"""代码提示面板（需求文档 Step 8）。

知识点 JSON 里的 ``hints`` 是一个字典，键是关键词、值是解释：

    {"print": "print()函数用于在屏幕上输出显示内容",
     "f-string": "f\\"...{变量}\\" 是格式化字符串，可以嵌入变量值"}

面板按「关键词徽章 + 解释」两列展示，默认折叠以免抢讲解区的篇幅。
把编辑器里的当前代码传进来时，代码里真实出现过的关键词会标一个
「代码里用到了」，学生可以对照着看自己改动的部分。
"""

from __future__ import annotations

from typing import Any, Mapping

import flet as ft

from ui import motion, theme

TITLE = "代码提示"


class HintPanel:
    """可折叠的提示面板；外部只碰 :attr:`control`。"""

    def __init__(
        self,
        hints: Mapping[str, str] | None,
        colors: dict[str, str] | None = None,
        code: str = "",
        title: str = TITLE,
        default_open: bool = False,
        page: Any = None,
    ) -> None:
        self.page = page
        self.colors = colors or theme.colors()
        self.title = title
        self.code = code or ""
        self.items = [(str(k), str(v)) for k, v in (hints or {}).items()]
        self._open = default_open
        self._build()

    # ------------------------------------------------------------------ 对外
    @property
    def control(self) -> ft.Container:
        return self.root

    def used_keywords(self) -> list[str]:
        """当前代码里真实出现过的关键词。"""
        return [kw for kw, _ in self.items if kw and kw in self.code]

    def set_code(self, code: str) -> None:
        """代码改了之后刷新「代码里用到了」的标记。"""
        self.code = code or ""
        if self._open:
            self._render_body()
            self._safe_update()

    def toggle(self, _event: Any = None) -> None:
        self._open = not self._open
        self.body.visible = self._open
        if self._open:
            self._render_body()
        # 换一个新的文字对象给弹稿，才会淡入换掉旧的箭头
        self._arrow_text = ft.Text("▾" if self._open else "▸", size=13, color=self.colors["sub"])
        self.arrow_slot.content = self._arrow_text
        self._safe_update()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        c = self.colors
        # 箭头用弹稿跟展开/折叠：指针点开时能看见一下变化，
        # 而不是靠屏幕重绘。body 自己仍然用 visible 切换，契约不变。
        self._arrow_text = ft.Text("▸", size=13, color=c["sub"])
        self.arrow_slot = motion.feedback_switcher(self._arrow_text)
        self.body = ft.Column(spacing=8, tight=True, visible=self._open)
        self.root = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("💡", size=13),
                            ft.Text(
                                self.title if not self.items else f"{self.title} · {len(self.items)} 条",
                                size=13,
                                weight=ft.FontWeight.BOLD,
                                color=c["text"],
                                expand=True,
                            ),
                            self.arrow_slot,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    self.body,
                ],
                spacing=8,
                tight=True,
            ),
            bgcolor=c["card"],
            border=ft.border.all(1, c["border"]),
            border_radius=theme.RADIUS,
            padding=12,
            ink=bool(self.items),
            on_click=self.toggle if self.items else None,
        )
        self._render_body()

    def _render_body(self) -> None:
        c = self.colors
        if not self.items:
            self.body.controls = [ft.Text("这个知识点还没有整理提示。", size=12, color=c["sub"])]
            return
        used = set(self.used_keywords())
        self.body.controls = [
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(keyword, size=12, color="#FFFFFF"),
                        bgcolor=theme.WARNING if keyword in used else theme.PRIMARY,
                        border_radius=6,
                        padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    ),
                    # 同 quiz_card：面板整体可点击，文字再设 selectable=True 会把 tap 吃掉，
                    # 学生点提示文字就展不开面板了。
                    ft.Text(explain, size=12, color=c["sub"], expand=True),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
            for keyword, explain in self.items
        ]

    def _safe_update(self) -> None:
        update = getattr(self.page, "update", None)
        if callable(update):
            try:
                update()
            except Exception:
                pass
