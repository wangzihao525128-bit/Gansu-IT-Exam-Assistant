r"""练习题组件（需求文档 Step 7）。

数据来自知识点 JSON 的 ``questions`` 字段。**三种题型**（见
:data:`core.knowledge_store.QUESTION_TYPES`）：

    {"type": "choice", "question": "题干（ ）",
     "options": ["A. …", "B. …"], "answer": "B", "explanation": "解析"}

    {"type": "judge", "question": "题干（ ）",
     "answer": "A", "explanation": "解析"}          # 选项由程序补「A. 正确 / B. 错误」

    {"type": "fill", "question": "题干", "answer": "input",
     "accept": ["input()"], "explanation": "解析"}   # 没有选项，直接在输入框里填

- ``choice`` / ``judge`` 走 :class:`QuizCard`：点选项 → 提交 → 展开解析；
- ``fill`` 走 :class:`FillCard`：输入框里打字 → 提交 → 展开解析；
- 不写 ``type`` 的题一律按 ``choice`` 处理（历史数据里只有选择题，不用改）。

交互统一是三步：作答 → 点「提交」判分 → 自动展开正确答案和解析。
每题结果写进 :mod:`core.local_store`（8.3：答题进度本地存储），
下次进这个知识点还会显示上次答对还是答错。

判分只有一条规则：一律走 :func:`core.knowledge_store.check_answer`，这里不再自己比一遍。
存档 key 也一律走 :func:`core.knowledge_store.question_key`——**不能拿题号当 key**，
题库 JSON 一改题序，旧记录就会挂到别的题上（详见 question_key 的说明）。

两个实现上的坑：
1. Flet 是按控件在树里的位置绑定点击回调的，**不要**在每次选中时把选项整排重建一遍——
   那样回调会错位，点「提交」会没反应。所以这里只在 :func:`QuizCard._build_options`
   里建一次控件，之后只改颜色和文字。
2. :class:`FillCard` 的对外接口**刻意和 QuizCard 对齐**（``control`` / ``chosen`` /
   ``submitted`` / ``submit()`` / ``retry()`` / ``correct()`` / ``feedback``），
   这样 :func:`build_quiz_list` 的调用方和测试不用区分题型。
   差别只有：填空用 :meth:`FillCard.fill` 而不是 ``select()``，且 ``letters()`` 返回空表。
"""

from __future__ import annotations

import re
from typing import Any, Callable

import flet as ft

from core import knowledge_store, local_store
from ui import motion, theme

LETTERS = "ABCDEFGH"
_PREFIX = re.compile(r"^\s*([A-Z])\s*[.、)）]\s*")  # 去掉选项自带的 "A. " 前缀，字母改用徽章显示

# 题型在界面上的名字。考试卷面就是这么分的（单选 25 题 / 判断 5 题 / 填空 5 题）。
TYPE_LABELS = {"choice": "单选题", "judge": "判断题", "fill": "填空题"}


def type_label(question: dict) -> str:
    return TYPE_LABELS.get(knowledge_store.question_type(question), "练习题")


def _type_chip(question: dict, colors) -> ft.Container:
    """左上角那个题型小标签。判断题给个醒目的颜色，学生一眼看出不用选字母。"""
    qtype = knowledge_store.question_type(question)
    color = theme.WARNING if qtype == "judge" else (theme.SUCCESS if qtype == "fill" else theme.PRIMARY)
    return ft.Container(
        content=ft.Text(type_label(question), size=10, color="#FFFFFF"),
        bgcolor=color,
        border_radius=4,
        padding=ft.padding.symmetric(horizontal=6, vertical=2),
    )


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
        # 判断题的数据里通常不写 options，由 question_options() 补成「A. 正确 / B. 错误」。
        self.options = knowledge_store.question_options(question)
        self.qtype = knowledge_store.question_type(question)
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
                            _type_chip(self.question, c),
                            ft.Container(expand=True),
                            self.badge,
                        ],
                        spacing=8,
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
        elif self.qtype == "judge":
            # 判断题显示「正确 / 错误」比显示字母 A / B 直观得多。
            text = knowledge_store.answer_text(self.question) or self.answer
            head = ft.Text(f"❌ 答错了，正确答案是 {text}（{self.answer}）", size=13, color=theme.DANGER)
        else:
            # 单选题保持原样：这里的形式被 ui_smoke_test 断言过（正确答案是 X）。
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
        chosen = str(record.get("chosen", "?") or "?")
        if self.qtype == "judge" and not record.get("correct"):
            # 判断题存档里存的是字母，显示成「你选了 正确 / 错误」更好读。
            for option in self.options:
                letter, text = knowledge_store.split_option(option)
                if letter == chosen.strip().upper()[:1]:
                    chosen = f"{text}（{chosen}）"
                    break
        self.badge.value = f"{mark}（你选了 {chosen}）"

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


class FillCard:
    """一道填空题：输入框里打字 → 提交 → 展开标准答案和解析。

    对外接口**刻意和 :class:`QuizCard` 对齐**（``control`` / ``chosen`` / ``submitted``
    / ``submit()`` / ``retry()`` / ``correct()`` / ``feedback`` / ``letters()``），
    这样 :func:`build_quiz_list` 的调用方和测试不用按题型写两套。

    唯一的差别是作答方式：这里用 :meth:`fill` 而不是 ``select()``。
    判分一律走 :func:`core.knowledge_store.check_answer`，
    归一化规则（全角转半角、去空格、转小写）也在那边，这里不重复实现。
    """

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
        self.qtype = knowledge_store.question_type(question)
        # chosen 存学生填的原文；判分靠 check_answer 归一化后再比。
        self.chosen = ""
        self.submitted = False
        self._build()

    # ------------------------------------------------------------------ 对外
    @property
    def control(self) -> ft.Container:
        return self.root

    def letters(self) -> list[str]:
        """填空题没有选项。返回空表，让调用方可以统一遍历而不用先判题型。"""
        return []

    def fill(self, text: str) -> None:
        """把作答写进输入框。UI 上由打字触发，测试里直接调它。"""
        if self.submitted:
            return
        self.chosen = str(text or "")
        self.field.value = self.chosen
        self._safe_update()

    def submit(self) -> None:
        """判分。输入框是空的就什么都不做（和选择题没选不能提交一致）。"""
        if self.submitted:
            return
        # 以输入框里的实际内容为准（学生是真打字的），退回 chosen 是为了
        # 某些测试替身不会回写 value 的情况。
        self.chosen = str(getattr(self.field, "value", "") or self.chosen or "")
        if not self.chosen.strip():
            return
        self.submitted = True
        correct = knowledge_store.check_answer(self.question, self.chosen)
        if self.point_id:
            local_store.record_answer(
                self.point_id,
                knowledge_store.question_key(self.question, self.index),
                self.chosen,
                correct,
            )
            self._render_badge()
        self.field.disabled = True
        self.submit_button.visible = False
        self.again_button.visible = True
        self._render_feedback(correct)
        self._safe_update()
        if self.on_progress:
            self.on_progress(correct)

    def retry(self) -> None:
        """再做一次：清空输入框和解析，回到未作答状态。"""
        self.chosen = ""
        self.submitted = False
        self.field.value = ""
        self.field.disabled = False
        self.submit_button.visible = True
        self.again_button.visible = False
        self._render_feedback(None)
        self._safe_update()

    def correct(self) -> bool:
        return self.submitted and knowledge_store.check_answer(self.question, self.chosen)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        c = self.colors
        self._feedback_holder = ft.Column(spacing=6, tight=True)
        self.feedback = motion.feedback_switcher(self._feedback_holder)
        self.badge = ft.Text("", size=11, color=c["sub"])

        # 标准答案可能有多个可接受写法，提示里把第一个列出来就够了（解析里会写全）。
        accepted = knowledge_store.accepted_fill_answers(self.question)
        hint = "在这里填写答案" + (f"，例如：{accepted[0]}" if accepted else "")
        self.field = ft.TextField(
            value="",
            hint_text=hint,
            text_size=13,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=10),
            border_color=c["border"],
            focused_border_color=theme.PRIMARY,
            on_submit=lambda _e: self.submit(),
        )
        self.submit_button = self._button("提交答案", theme.PRIMARY, "#FFFFFF", self._on_submit)
        self.again_button = self._button("再做一次", c["card"], c["text"], self._on_retry, visible=False)

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
                            _type_chip(self.question, c),
                            ft.Container(expand=True),
                            self.badge,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    _stem(str(self.question.get("question", ""))),
                    self.field,
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
        self._render_badge()

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
    def _render_feedback(self, correct: bool | None) -> None:
        c = self.colors
        if correct is None:
            self._feedback_holder = ft.Column(spacing=6, tight=True)
            self.feedback.content = self._feedback_holder
            return
        standard = knowledge_store.answer_text(self.question)
        if correct:
            head = ft.Text("✅ 答对了！", size=13, color=theme.SUCCESS)
        else:
            head = ft.Text(f"❌ 答错了，标准答案是 {standard}", size=13, color=theme.DANGER)
        controls = [
            head,
            ft.Divider(color=c["border"], height=8),
            ft.Text("解析", size=12, weight=ft.FontWeight.BOLD, color=c["sub"]),
            _explanation(str(self.question.get("explanation", "")), c),
        ]
        # 列出所有可接受写法——学生答错时最想知道的就是「我那样写行不行」。
        others = [item for item in knowledge_store.accepted_fill_answers(self.question)
                  if item != knowledge_store.normalize_fill(standard)]
        if others:
            controls.append(
                ft.Text("其它可接受的写法：" + "、".join(others), size=12, color=c["sub"])
            )
        self._feedback_holder = ft.Column(spacing=6, tight=True, controls=controls)
        self.feedback.content = self._feedback_holder

    def _render_badge(self) -> None:
        if not self.point_id:
            return
        key = knowledge_store.question_key(self.question, self.index)
        record = local_store.load_answers(self.point_id).get(key)
        if not isinstance(record, dict):
            return
        mark = "✅ 上次答对" if record.get("correct") else "❌ 上次答错"
        self.badge.value = f"{mark}（你填了 {record.get('chosen', '?')}）"

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


def make_card(
    page: ft.Page,
    question: dict,
    index: int,
    total: int,
    point_id: str,
    colors: dict[str, str],
    on_progress: Callable[[bool], None] | None = None,
):
    """按题型挑卡片类。填空题走 :class:`FillCard`，其余（单选 / 判断）走 :class:`QuizCard`。

    单独抽出来是因为测试也要按同一规则造卡片，规则只能有一处。
    """
    if knowledge_store.question_type(question) == "fill":
        return FillCard(page, question, index, total, point_id, colors, on_progress=on_progress)
    return QuizCard(page, question, index, total, point_id, colors, on_progress=on_progress)


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
        make_card(page, question, i, len(questions), point_id, c, refresh)
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
