r"""练习题组件（需求文档 Step 7）。

数据来自知识点 JSON 的 ``questions`` 字段：

    {"type": "choice", "question": "题干（ ）",
     "options": ["A. …", "B. …"], "answer": "B", "explanation": "解析"}

交互是三步：点一个选项选中 → 点「提交」判分 → 自动展开正确答案和解析。
每题结果写进 :mod:`core.local_store`（8.3：答题进度本地存储），
下次进这个知识点还会显示上次答对还是答错。

判分只有一条规则：一律走 :func:`core.knowledge_store.check_answer`，这里不再自己比一遍。
存档 key 也一律走 :func:`core.knowledge_store.question_key`——**不能拿题号当 key**，
题库 JSON 一改题序，旧记录就会挂到别的题上（详见 question_key 的说明）。

一个实现上的坑：Flet 是按控件在树里的位置绑定点击回调的，**不要**在每次选中时
把选项整排重建一遍——那样回调会错位，点「提交」会没反应。所以这里只在
:func:`QuizCard._build_options` 里建一次控件，之后只改颜色和文字。
"""

from __future__ import annotations

import re
from typing import Any, Callable

import flet as ft

from core import knowledge_store, local_store
from ui import motion, theme

LETTERS = "ABCDEFGH"
_PREFIX = re.compile(r"^\s*([A-Z])\s*[.、)）]\s*")  # 去掉选项自带的 "A. " 前缀，字母改用徽章显示


def letter_of(text: str, index: int) -> str:
    """选项字母：优先用 JSON 里自带的前缀，没有就按顺序补。"""
    match = _PREFIX.match(str(text or ""))
    if match and match.group(1) in LETTERS:
        return match.group(1)
    return LETTERS[index] if index < len(LETTERS) else "?"


def strip_prefix(text: str) -> str:
    return _PREFIX.sub("", str(text or "")).strip()


class QuizCard:
    """一道选择题；外部只碰 :attr:`control`，测试直接调 :meth:`select` / :meth:`submit`。"""

    def __init__(
        self,
        page: ft.Page,
        question: dict,
        index: int = 0,
        total: int = 1,
        point_id: str = "",
        colors: dict[str, str] | None = None,
        on_progress: Callable[[bool], None] | None = None,
    ) -> None:
        self.page = page
        self.question = question
        self.index = index
        self.total = total
        self.point_id = point_id
        self.colors = colors or theme.colors()
        self.on_progress = on_progress
        self.options = list(question.get("options") or [])
        self.answer = str(question.get("answer", "") or "").strip().upper()[:1]
        self.chosen = ""
        self.submitted = False
        self._rows: dict[str, dict[str, Any]] = {}  # letter -> {"box","badge","text","mark"}
        self._build()

    # ------------------------------------------------------------------ 对外
    @property
    def control(self) -> ft.Container:
        return self.root

    def letters(self) -> list[str]:
        return [letter_of(text, i) for i, text in enumerate(self.options)]

    def select(self, letter: str) -> None:
        """选中一个选项（再次点同一项不取消，保持单选语义简单可预期）。"""
        letter = str(letter or "").strip().upper()[:1]
        if self.submitted or letter not in self._rows:
            return
        self.chosen = letter
        self._paint()
        self._safe_update()

    def submit(self) -> None:
        """判分。没选选项时什么都不做；答完就把结果存进本地进度。"""
        if self.submitted or not self.chosen:
            return
        self.submitted = True
        # 判分规则只此一处（check_answer），别在这里再写一遍 self.chosen == self.answer：
        # 两套规则早晚会走岔，学生看到的结果就和存档里的记录对不上了。
        correct = knowledge_store.check_answer(self.question, self.chosen)
        if self.point_id:
            # key 用题目的稳定身份，不用题号——见 knowledge_store.question_key
            local_store.record_answer(
                self.point_id,
                knowledge_store.question_key(self.question, self.index),
                self.chosen,
                correct,
            )
            # 刚写进存档，顶部那行「上次答对/答错」必须立刻跟上来。
            # 以前只有 _build() 里调它，所以卡片中间刚说完「❌ 答错了」，
            # 上面的徽章还挂着上一次的结果，自相矛盾。
            self._render_badge()
        self._paint()
        self._render_feedback(correct)
        self.submit_button.visible = False
        self.again_button.visible = True
        self._safe_update()
        if self.on_progress:
            self.on_progress(correct)

    def retry(self) -> None:
        """再做一次：清空选择和解析，回到未作答状态。"""
        self.chosen = ""
        self.submitted = False
        self._paint()
        self._render_feedback(None)
        self.submit_button.visible = True
        self.again_button.visible = False
        self._safe_update()

    def correct(self) -> bool:
        """是否已答对（未作答算 False）。判分逻辑同样只走 check_answer。"""
        return self.submitted and knowledge_store.check_answer(self.question, self.chosen)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        c = self.colors
        self.options_column = ft.Column(spacing=6, tight=True)
        # 判分结果出现时淡入：弹窗对象全程同一个，只换 .content
        self._feedback_holder = ft.Column(spacing=6, tight=True)
        self.feedback = motion.feedback_switcher(self._feedback_holder)
        self.submit_button = self._button("提交答案", theme.PRIMARY, "#FFFFFF", self._on_submit)
        self.again_button = self._button("再做一次", c["card"], c["text"], self._on_retry, visible=False)
        self.badge = ft.Text("", size=11, color=c["sub"])

        self.root = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                f"第 {self.index + 1} / {self.total} 题",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=theme.WARNING,
                            ),
                            ft.Container(expand=True),
                            self.badge,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    _stem(str(self.question.get("question", ""))),
                    self.options_column,
                    ft.Row([self.submit_button, self.again_button], spacing=8),
                    self.feedback,
                ],
                spacing=8,
                tight=True,
            ),
            bgcolor=c["card"],
            border=ft.border.all(1, c["border"]),
            border_radius=theme.RADIUS,
            padding=14,
        )
        self._build_options()
        self._paint()
        self._render_badge()

    def _build_options(self) -> None:
        """建一次选项控件，之后只改属性，不再重建控件树。"""
        rows = []
        for text, letter in zip(self.options, self.letters()):
            badge = ft.Container(
                content=ft.Text(letter, size=12, color="#FFFFFF"),
                bgcolor=self.colors["sub"],
                border_radius=6,
                width=24,
                height=24,
                alignment=ft.alignment.center,
            )
            # 这里千万别加 selectable=True：Flutter 里可选文本会自己吞掉 tap 手势，
            # 外层容器的 on_click 就再也收不到 click，学生点选项文字会没反应。
            label = ft.Text(strip_prefix(text), size=13, color=self.colors["text"], expand=True)
            mark = ft.Text("", size=11, color=self.colors["sub"])
            box = ft.Container(
                content=ft.Row([badge, label, mark], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                border=ft.border.all(1, self.colors["border"]),
                border_radius=8,
                padding=10,
                ink=True,
                on_click=lambda _e, letter=letter: self.select(letter),
            )
            self._rows[letter] = {"box": box, "badge": badge, "text": label, "mark": mark}
            rows.append(box)
        self.options_column.controls = rows

    def _button(self, label: str, bg: str, fg: str, on_click: Callable[..., None], visible: bool = True) -> ft.Container:
        return ft.Container(
            content=ft.Text(label, size=12, color=fg),
            bgcolor=bg,
            border=ft.border.all(1, self.colors["border"]),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=12, vertical=7),
            ink=True,
            on_click=on_click,
            visible=visible,
        )

    # ------------------------------------------------------------------ 渲染
    def _paint(self) -> None:
        """按当前状态刷新每个选项的配色和标记。"""
        c = self.colors
        for letter, row in self._rows.items():
            picked = letter == self.chosen
            is_answer = self.submitted and letter == self.answer
            wrong_pick = self.submitted and picked and letter != self.answer
            if is_answer:
                border, text_color, mark = theme.SUCCESS, theme.SUCCESS, "✓ 正确答案"
            elif wrong_pick:
                border, text_color, mark = theme.DANGER, theme.DANGER, "✗ 你选的"
            elif picked:
                border, text_color, mark = theme.PRIMARY, c["text"], "已选择"
            else:
                border, text_color, mark = c["border"], c["text"], ""
            row["box"].border = ft.border.all(2 if (picked or is_answer) else 1, border)
            row["box"].bgcolor = c["card"] if not (picked or is_answer or wrong_pick) else None
            row["badge"].bgcolor = border if (picked or is_answer or wrong_pick) else c["sub"]
            row["text"].color = text_color
            row["mark"].value = mark
            row["mark"].color = text_color

    def _render_feedback(self, correct: bool | None) -> None:
        c = self.colors
        if correct is None:
            # 回到未作答状态：交给弹窗一个空 Column 就会淡出去
            self._feedback_holder = ft.Column(spacing=6, tight=True)
            self.feedback.content = self._feedback_holder
            return
        if correct:
            head = ft.Text("✅ 答对了！", size=13, color=theme.SUCCESS)
        else:
            head = ft.Text(f"❌ 答错了，正确答案是 {self.answer}", size=13, color=theme.DANGER)
        self._feedback_holder = ft.Column(
            spacing=6,
            tight=True,
            controls=[
                head,
                ft.Divider(color=c["border"], height=8),
                ft.Text("解析", size=12, weight=ft.FontWeight.BOLD, color=c["sub"]),
                _explanation(str(self.question.get("explanation", "")), c),
            ],
        )
        self.feedback.content = self._feedback_holder

    def _render_badge(self) -> None:
        if not self.point_id:
            return
        # 用 question_key 取存档（不是 str(self.index)：题号会被题库改动带走）。
        # 存档里残留的老数字 key 读不到就算了，当没答过，不会报错。
        key = knowledge_store.question_key(self.question, self.index)
        record = local_store.load_answers(self.point_id).get(key)
        if not isinstance(record, dict):
            return
        mark = "✅ 上次答对" if record.get("correct") else "❌ 上次答错"
        self.badge.value = f"{mark}（你选了 {record.get('chosen', '?')}）"

    # ------------------------------------------------------------------ 事件
    def _on_submit(self, _event: Any = None) -> None:
        self.submit()

    def _on_retry(self, _event: Any = None) -> None:
        self.retry()

    def _safe_update(self) -> None:
        update = getattr(self.page, "update", None)
        if callable(update):
            try:
                update()
            except Exception:
                pass


def _stem(text: str) -> ft.Control:
    try:
        return ft.Markdown(value=text, selectable=True)
    except Exception:  # 极老版本没有 Markdown 控件
        return ft.Text(text, size=13, selectable=True)


def _explanation(text: str, colors) -> ft.Control:
    if not text:
        return ft.Text("（这道题没有写解析）", size=12, color=colors["sub"])
    try:
        return ft.Markdown(value=text, selectable=True)
    except Exception:
        return ft.Text(text, size=12, color=colors["sub"], selectable=True)


def build_quiz_list(
    page: ft.Page,
    point_id: str,
    questions: list[dict],
    colors: dict[str, str] | None = None,
    on_progress: Callable[[], None] | None = None,
) -> ft.Control:
    """把一个知识点的所有练习题渲染成一列，顶部带答题进度。

    :param on_progress: 每次判分后额外回调一次。详情页用它刷新左栏那张
        「本模块学习进度」卡，学生点完「提交答案」左栏数字就跟着变。

    返回值统一带 ``.cards`` 属性（没有题时是空表），调用方不用先判空。
    """
    c = colors or theme.colors()
    if not questions:
        # 这里必须用 Container 包一层：flet 0.23 的 ft.Column **不收** bgcolor /
        # border / border_radius / padding（会直接 TypeError: unexpected keyword
        # argument），卡片样式只能挂在 Container 上。之前一直没炸，纯粹是因为
        # 题库里 11 个知识点都配了题；下一步要重写题库 JSON，一旦有知识点没题，
        # 详情页就会在构建时整个崩掉。
        empty = ft.Container(
            content=ft.Column(
                [ft.Text("这个知识点暂时没有练习题。", size=12, color=c["sub"])],
                spacing=6,
                tight=True,
            ),
            bgcolor=c["card"],
            border=ft.border.all(1, c["border"]),
            border_radius=theme.RADIUS,
            padding=14,
        )
        empty.cards = []  # 与下面那份保持一致，调用方不必先判空再取 .cards
        return empty

    holder = ft.Column(spacing=theme.GAP, tight=True)
    progress = ft.Text("", size=12, color=c["sub"])

    def refresh(_correct: bool | None = None) -> None:
        stat = local_store.quiz_stat(point_id)
        # 夹一道：老存档是按题号存 key 的（见 knowledge_store.question_key），
        # 题库改过题序之后存档里会剩下对不上号的旧 key，被统计算进来就会印出
        # 「已答 5 / 2 题」这种比题目总数还大的数字。旧 key 不影响使用，只是别让它露馅。
        answered = min(stat["answered"], len(questions))
        # 答对数也要夹：旧 key 可能比对得上的还多，只夹「已答」会印出
        # 「已答 2 / 2 题 · 答对 3 题」这种比题目总数还大的答对数。
        correct = min(stat["correct"], answered)
        progress.value = f"已答 {answered} / {len(questions)} 题 · 答对 {correct} 题"
        update = getattr(page, "update", None)  # 光改 value 不会重画，必须显式刷新
        if callable(update):
            try:
                update()
            except Exception:
                pass
        if on_progress is not None:  # 别的面板（比如左栏进度卡）也要跟着重画
            try:
                on_progress()
            except Exception:
                pass

    cards = [
        QuizCard(page, question, i, len(questions), point_id, c, on_progress=refresh)
        for i, question in enumerate(questions)
    ]
    refresh()
    holder.controls = [
        ft.Text("练习题", size=14, weight=ft.FontWeight.BOLD, color=c["text"]),
        progress,
        *[card.control for card in cards],
    ]
    holder.cards = cards  # 冒烟测试要拿到每一张卡片来模拟作答
    return holder
