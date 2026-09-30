r"""代码编辑器组件（需求文档 Step 6）。

Flet 没有现成的代码控件，所以这个组件自己拼了三样东西：

* **语法高亮 + 行号**：用标准库 ``tokenize`` 定位源码里的关键字、字符串、数字、
  注释，再按字符偏移量切成一串带颜色的片段交给 ``ft.Text(spans=...)`` 渲染。
  这里有个坑：``tokenize`` 只吐词法单元，两个词之间的空格会被丢掉，
  所以必须用「绝对偏移量回切原文」的方式补齐，否则高亮区和行号会错位。
  切分满足一条硬约束——所有片段的文本拼起来必须和源码一字不差，
  tools\ui_smoke_test.py 里有这条断言。
* **自动缩进**：按回车时如果上一行以冒号结尾（if / for / def ...）就多缩进 4 格，
  否则沿用上一行的缩进宽度。
* **运行**：点「▶ 运行代码」把内容交给 Step 2 的 ``code_executor`` 沙箱。
  桌面端在本机子进程里跑，手机端生成 Pyodide 脚本；跑在后台线程里，
  最多等 5 秒（需求文档 8.1），结果区用绿 / 红两种颜色区分成功和失败。
  注意沙箱是**教学用途**的 AST 白名单，不是真正的安全边界（子进程里
  还有标准库可以绕），所以界面上不要向学生承诺「读不到你的文件」这种话，
  详情见 :meth:`CodeEditor._hint`。
"""

from __future__ import annotations

import builtins
import io
import keyword
import tokenize
from typing import Any, Callable

import flet as ft

from core import code_executor, local_store
from ui import motion, theme

INDENT = "    "  # 4 个空格，和沙箱给学生的中文提示保持一致
MONO = "Consolas"
MAX_LINES = 400  # 超过就只高亮前 400 行，防止粘贴超大文件把界面卡死
LINE_PX = 19        # 一行代码大约占多少像素（size=13 的等宽字体实测值）
CODE_MIN_PX = 150       # 代码区最少这么高（约 6 行，够看一个循环）
CODE_MIN_PX_INPUT = 130  # 示例代码用了 input() 时代码区让一点高度，
                           # 否则运行结果会被卡片底边切掉——之前踩过这个 bug。
CODE_MAX_PX = 560   # 再高就自己内部滚动，别把讲解区挤没
RESULT_BOX_PX = 88   # 运行结果区固定高度（内容超了自己内部滚动）
RESULT_BOX_PX_NARROW = 84  # 手机端上下堆叠时结果区矮一点，少一层嵌套滚动
RESULT_BOX_PX_MOBILE_WIDE = 88  # 手机横屏（宽布局）结果区定高。
                                # 必须定高：不定高时它按内容长高，输出一多就把代码区顶出卡片。
CODE_MIN_PX_MOBILE_WIDE = 84  # 手机横屏代码区下限（约 4 行，再矮就没法读代码了）
MOBILE_WIDE_CHROME_PX = 170  # 手机横屏右栏里，代码区以外固定占掉的高度：
                             # 「代码编辑器」标题 20 + 编辑器标题行 20 + 按钮两排 64
                             # + 运行状态行 18 + 6 个 8px 间距。
                             # 按钮在 277 逻辑像素宽的右栏里必然换行，按一排算会少 40。
MOBILE_WIDE_EDITOR_SHARE = 1.0  # 手机横屏时右栏整列都给编辑器（代码解释挪去了中栏）
NARROW_CODE_PX = 260  # 手机端代码区固定高度（整页滚动，不再和可用高度抢空间）
STDIN_EXTRA_PX = 14  # 「标准输入」和运行环境提示挤在同一行，这一行约 42px，
                     # 原来那行两行提示只占 28px，净多 14px。只在用到 input() 时计入。

# 代码区以外固定占掉的高度，分内外两层（fit_height 要先扣外层再乘 share）：
#   外层 = 顶部导航条 60 + 页面内边距 24 + 区域间距 12 + 卡片内边距 28
#   内层 = 「代码编辑器」标题 18 + 编辑器标题行 24 + 按钮行 76 + 运行状态行 28
#        + 编辑器内部 4 个 8px 间距
# 按钮行按最坏情况算 2 行：右栏内宽只有 270 上下，四个按钮放一行必然换行，
# 实测就是两排（每排约 34 + 6 间距）。按 1 行算会少 38px，结果区正好被顶出卡片，
# 学生点完「运行代码」只看得见绿色的「运行成功」，看不见输出。
OUTER_CHROME_PX = 60 + 24 + 12 + 28
INNER_CHROME_PX = 18 + 24 + 76 + 28 + 8 * 4

# 深色代码底上的配色：关键字 / 内置函数 / 字符串 / 数字 / 注释
SYNTAX = {
    "keyword": "#7FB3FF",
    "builtin": "#66D9C0",
    "string": "#FFD580",
    "number": "#C7A0FF",
    "comment": "#8A8F98",
    "name": "#9BE28B",
    "text": "#E6E6E6",
}

_BUILTIN_NAMES = frozenset(dir(builtins))


def _plain(code: str) -> list[ft.TextSpan]:
    """高亮失败时的兜底：整段用单色渲染，保证编辑器永远有内容。"""
    return [ft.TextSpan(text=code, style=ft.TextStyle(color=SYNTAX["text"]))]


def fit_height(page: ft.Page | None, lines: int, share: float, needs_input: bool = False) -> int:
    """算代码区该多高，既放得下代码，又给运行结果留出位置。

    只按行数算高度会出事：右栏里编辑器只占 2/3，代码一多就把下面
    「运行状态 + 运行结果」挤出卡片，学生点完「运行代码」什么都看不到。
    所以这里再拿窗口实际高度卡一道上限。
    """
    wanted = lines * LINE_PX + 30
    floor = CODE_MIN_PX_INPUT if needs_input else CODE_MIN_PX
    page_h = float(getattr(page, "height", 0) or 0)
    if page_h <= 0:
        return max(CODE_MIN_PX, min(CODE_MAX_PX, wanted))
    inner = INNER_CHROME_PX + (STDIN_EXTRA_PX if needs_input else 0)
    usable = (page_h - OUTER_CHROME_PX) * share - inner - fit_result_height(share)
    return int(max(floor, min(CODE_MAX_PX, wanted, usable)))


def fit_result_height(share: float) -> int:
    """结果区该多高：电脑端宽裕，手机端矮一点，避免两层嵌套滚动。"""
    return RESULT_BOX_PX if share > 0.5 else RESULT_BOX_PX_NARROW


def fit_mobile_wide(page_height: float, lines: int, needs_input: bool = False) -> int:
    """手机横屏（宽布局）专用：代码区该多高。

    为什么电脑端那套 fit_height 在手机横屏不管用——实测 MuMu 模拟器横屏
    1600x900，设备像素比 1.5，所以 flet 看到的 page.height 只有 600 逻辑像素。
    fit_height 算出 (600-124)*2/3-192-88 = 37px，比 CODE_MIN_PX_INPUT 还小，
    代码区于是直接掉到下限 130px。可右栏卡片整块只有约 320px 高，
    扣掉标题、标题行、两排按钮、标准输入、状态行之后只剩 19px 给运行结果——
    结果框被挤到卡片内部滚动区的外面，点完「运行代码」屏幕上一点反馈都没有，
    必须手动在卡片里上滑才看得见（真机截图见作者本机）。

    所以手机横屏单独算：右栏整列都归编辑器（代码解释区挪到中栏去了），
    卡片可视高度 = 页面高度扣掉外框，再扣掉固定开销和结果区，剩下的才是代码区。
    宁可代码区矮一点，也要保证运行结果一直摆在屏幕里。
    """
    if page_height <= 0:
        return CODE_MIN_PX_MOBILE_WIDE
    viewport = (page_height - OUTER_CHROME_PX) * MOBILE_WIDE_EDITOR_SHARE - 28
    # 中栏和右栏一样高，所以这里不用再按 2/3 之类的份额缩——右栏整列都是编辑器卡片。
    chrome = MOBILE_WIDE_CHROME_PX + (STDIN_EXTRA_PX if needs_input else 0)
    usable = viewport - chrome - RESULT_BOX_PX_MOBILE_WIDE
    wanted = lines * LINE_PX + 30
    return int(max(CODE_MIN_PX_MOBILE_WIDE, min(wanted, usable, CODE_MAX_PX)))


def fits(page_height: float, share: float, needs_input: bool = False) -> bool:
    """结果区放不放得下（冒烟测试用，防止以后改布局又把结果挤出卡片）。

    真实条件是「实际算出来的代码区高度 + 固定开销 ≤ 可用高度」；
    这里用最小代码区（CODE_MIN_PX）做最坏情况，如果最坏都放不下，
    说明窗口太矮，外层滚动条会兜住。
    """
    if page_height <= 0:
        return True
    floor = CODE_MIN_PX_INPUT if needs_input else CODE_MIN_PX
    need = floor + INNER_CHROME_PX + (STDIN_EXTRA_PX if needs_input else 0) + RESULT_BOX_PX
    return need <= (page_height - OUTER_CHROME_PX) * share


def _color_of(tok: tokenize.TokenInfo, prev_word: str) -> tuple[str, bool]:
    """一个词法单元该用哪种颜色；第二个返回值是是否用斜体（注释用）。"""
    if tok.type == tokenize.COMMENT:
        return SYNTAX["comment"], True
    if tok.type == tokenize.STRING:
        return SYNTAX["string"], False
    if tok.type == tokenize.NUMBER:
        return SYNTAX["number"], False
    if tok.type == tokenize.NAME:
        if keyword.iskeyword(tok.string):
            return SYNTAX["keyword"], False
        if tok.string in _BUILTIN_NAMES:
            return SYNTAX["builtin"], False
        if prev_word in {"def", "class"}:
            return SYNTAX["name"], False
    return SYNTAX["text"], False


def highlight(code: str) -> list[ft.TextSpan]:
    """把 Python 源码切成带颜色的片段。

    硬约束：把返回的片段文本依次拼接，结果必须等于传入的 ``code``。
    学生代码经常只写一半，``tokenize`` 会抛异常，这时退回单色纯文本。
    """
    if not code:
        return _plain("")
    try:
        tokens = [
            tok
            for tok in tokenize.generate_tokens(io.StringIO(code).readline)
            if tok.type != tokenize.ENDMARKER
        ]
    except Exception:
        return _plain(code)

    lines = code.split("\n")
    line_start: list[int] = []
    offset = 0
    for line in lines:
        line_start.append(offset)
        offset += len(line) + 1  # +1 是被 split 掉的换行符

    def at(row: int, col: int) -> int:
        """把 tokenize 的 (1 起算行号, 0 起算列号) 换成字符串里的绝对下标。"""
        index = row - 1
        if index < 0:
            return 0
        if index >= len(lines):
            return len(code)
        return max(line_start[index], min(line_start[index] + max(col, 0), line_start[index] + len(lines[index])))

    spans: list[ft.TextSpan] = []
    prev_word = ""  # 上一个单词，用来认出 def / class 后面那个名字
    cursor = 0

    def push(text: str, color: str, italic: bool = False) -> None:
        if text:
            spans.append(ft.TextSpan(text=text, style=ft.TextStyle(color=color, italic=italic)))

    for tok in tokens:
        start, end = at(*tok.start), at(*tok.end)
        if start < cursor:  # 理论上不会发生，兜底避免片段重叠
            start = cursor
        end = max(start, end)
        push(code[cursor:start], SYNTAX["text"])  # 补回 tokenize 丢掉的空格
        color, italic = _color_of(tok, prev_word)
        push(code[start:end], color, italic)
        if tok.type == tokenize.NAME:
            prev_word = tok.string
        elif tok.type not in (tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.NEWLINE):
            prev_word = ""
        cursor = end

    push(code[cursor:], SYNTAX["text"])
    return spans or _plain(code)


def join_spans(spans: list[ft.TextSpan]) -> str:
    """把片段拼回原文，供冒烟测试校验高亮没有丢字符。"""
    return "".join(span.text for span in spans)


def _chip(label: str, colors, on_click: Callable[..., None], active: bool = False) -> ft.Container:
    """编辑器顶部的小按钮（运行 / 还原 / 模式切换都用它）。"""
    return ft.Container(
        content=ft.Text(label, size=12, color="#FFFFFF" if active else colors["text"], no_wrap=True),
        bgcolor=theme.PRIMARY if active else colors["card"],
        border=ft.border.all(1, theme.PRIMARY if active else colors["border"]),
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        ink=True,
        on_click=on_click,
    )


class CodeEditor:
    """知识点详情页右栏的代码编辑器；外部只碰 :attr:`control`。"""

    def __init__(
        self,
        page: ft.Page,
        point: dict,
        colors: dict[str, str] | None = None,
        height: int = 250,
        result_height: int | None = RESULT_BOX_PX,
        on_result: Callable[[code_executor.RunResult], None] | None = None,
        on_code_change: Callable[[str], None] | None = None,
    ) -> None:
        self.page = page
        self.point = point
        self.point_id = str(point.get("id", "") or "")
        self.default_code = str(point.get("code_example", "") or "")
        self.colors = colors or theme.colors()
        self.on_result = on_result
        self.on_code_change = on_code_change
        self._mode = "edit"  # edit | highlight
        self._running = False
        self._last_code = ""
        self.engine_strip: ft.Container | None = None
        self._build(height, result_height)

    # ------------------------------------------------------------------ 对外
    @property
    def control(self) -> ft.Column:
        return self.root

    def code(self) -> str:
        """当前编辑器里的代码。"""
        return self.field.value or ""

    def _is_mobile(self) -> bool:
        """当前是不是安卓 / iOS 客户端。

        必须走 code_executor.platform_key()：page.platform 是枚举，
        str() 出来是 "PagePlatform.ANDROID"，直接比 "android" 永远为假。
        """
        return code_executor.platform_key(getattr(self.page, "platform", "")) in {"android", "ios"}

    def backend(self) -> str:
        """按运行平台选后端：安卓 / iOS 在 App 进程内跑，其余用本地子进程。"""
        platform = getattr(self.page, "platform", "") or ""
        # 注意：这里刻意**不**按 page.web 切到 Pyodide。flet 0.23 的
        # ft.WebView 只在 Android / iOS 上是真 WebView，在 web 渲染器下
        # 是个空平台视图（连 <iframe> 都不生成），切过去只会让运行一路超时。
        # 详细原因见 core.code_executor.backend_for_platform 的 docstring。
        return code_executor.backend_for_platform(
            platform, web=bool(getattr(self.page, "web", False))
        )
    def run(self) -> None:
        """对外的运行入口，测试里直接调它，不用模拟点击。"""
        self._run(None)

    # ------------------------------------------------------------------ 构建
    def _build(self, height: int, result_height: int | None = RESULT_BOX_PX) -> None:
        c = self.colors
        # 这个高度已经同时考虑了「代码多少行」和「窗口还剩多少空间」，
        # 存下来当作这次布局算出来的唯一标准：别的地方不要再按行数重算，
        # 否则会把「运行状态 + 运行结果」挤出卡片。
        # 注意 _sync() 并不读它——只有 tools\ui_smoke_test.py 会断言
        # code_area.height == fitted_height，防止以后改布局又把它按行数撑高。
        self.fitted_height = height
        # 移动端不能给结果区锁死高度。
        # 实测（MuMu 模拟器，横屏 1600x900）：锁了 88px 的结果区整个不渲染——
        # 界面上看不见，uiautomator 的可访问性树里也查不到。同一个控件在竖屏（narrow，
        # 默认就不锁高）下反而正常显示。所以这里直接改成按内容自然高度，
        # 外层 _editor_body 本来就带 scroll，不会把下方的代码解释区顶出去。
        # 竖屏（上下堆叠）时结果区不锁高，整页滚动、按内容自然高度最舒服，
        # 由 detail_page 传 None 进来。
        # 手机横屏是另一回事：右栏卡片定高，必须由 detail_page 传一个算好的定高值，
        # 否则结果框会被顶到卡片滚动区外面（原因见 fit_mobile_wide 的说明）。
        # flet 0.23 的多行 TextField 会忽略 height、照样按内容行数撑高，
        # 用 min_lines / max_lines 把它钉死在「看得见的那几行」才管用。
        visible_lines = max(4, int((height - 16 - 20) // LINE_PX))
        self.field = ft.TextField(
            value=local_store.load_draft(self.point_id, self.default_code),
            multiline=True,
            min_lines=visible_lines,
            max_lines=visible_lines,
            text_size=13,
            text_style=ft.TextStyle(font_family=MONO, color=SYNTAX["text"], size=13),
            color=SYNTAX["text"],
            bgcolor=theme.CODE_BG,
            border_color=theme.CODE_BG,
            focused_border_color=theme.PRIMARY,
            selection_color="#3A4A63",
            cursor_color=theme.PRIMARY,
            border_radius=10,
            content_padding=ft.padding.all(10),
            on_change=self._on_edit,
            expand=True,
            # 关键：光给外层 Container 设高度没用，TextField 会按内容行数自己撑高
            # （它自己带深色底），把下面「运行状态 + 运行结果」整个顶出卡片，
            # 学生点「运行代码」看不到任何反馈。这里必须给输入框本身限高。
            height=height - 16,
        )
        self.preview = ft.Text(
            "",
            font_family=MONO,
            size=13,
            color=SYNTAX["text"],
            no_wrap=True,
            selectable=True,
            expand=True,
            height=height - 16,
        )
        self.gutter = ft.Text("", font_family=MONO, size=13, color="#5A6270", no_wrap=True)
        self.run_button = _chip("▶ 运行代码", c, self._run, True)
        self.reset_button = _chip("↺ 还原示例", c, self._reset)
        self.edit_button = _chip("✎ 编辑", c, lambda _e: self._set_mode("edit"), True)
        self.preview_button = _chip("◉ 高亮", c, lambda _e: self._set_mode("highlight"))

        self.editor_box = ft.Container(
            # 行号列同样要限高裁剪，否则 35 行代码会把这一行撑到 500 多像素
            content=ft.Row(
                [
                    ft.Container(
                        content=self.gutter,
                        height=height - 16,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    ),
                    self.field,
                ],
                spacing=8,
                expand=True,
                height=height - 16,
            ),
            padding=ft.padding.all(8),
            height=height,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        self.preview_box = ft.Container(content=self.preview, padding=ft.padding.all(8), visible=False)
        self.code_area = ft.Container(
            content=ft.Stack([self.editor_box, self.preview_box], expand=True),
            bgcolor=theme.CODE_BG,
            border_radius=10,
            height=height,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        # 「标准输入」：教材示例里有 input()，光点「运行代码」必然报
        # ValueError / EOFError，而界面上原来根本没有地方敲数据——
        # 学生看到的是一段看不懂的报错。这里给一个预填了样例的单行框：
        # 不改代码就能跑出正确结果，想换数字直接改框里的内容。
        self.needs_input = "input(" in self.default_code
        self.stdin_field = ft.TextField(
            value=str(self.point.get("sample_input", "") or ""),
            dense=True,
            max_lines=1,
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=2),
            hint_text="标准输入：一行一个数据（这段示例用不到就留空）",
            hint_style=ft.TextStyle(color=c["sub"], size=12),
            border_color=c["border"],
            bgcolor=c["card"],
            color=c["text"],
        )
        # 和下面的运行环境提示并成一行：右栏高度就那么多，单独再占一行，
        # 运行结果会被卡片底边切掉（实测在 1180x800 下就是这么被切的）。
        # 只放「标签 + 输入框」：输入框默认会把整行宽度吃光，
        # 运行环境提示放在同一行会被挤成 0 宽，所以挪到卡片标题行右边。
        self.stdin_row = ft.Row(
            [
                ft.Text("标准输入", size=11, color=c["sub"], no_wrap=True),
                self.stdin_field,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            visible=self.needs_input,
        )
        self.status = ft.Text(
            self._hint(),
            size=11,
            color=c["sub"],
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
            visible=not self.needs_input,
        )
        # 结果区自己内部滚动：输出再长也不会把下面的代码解释区顶出屏幕
        # result_height 为 None = 按内容自然高度（手机端整页滚动用）
        self._result_height = result_height
        self._result_holder = self._new_result_column([])
        # 弹窗对象全程保持同一个，只换里面的 .content——才会播退场动画
        # 手机端（Android / iOS）别用 AnimatedSwitcher：实测打包出来的 flet 客户端
        # 上这个控件整个不渲染——结果框连「点上面的运行代码看结果」那行占位文字都看不见，
        # 学生点完「运行代码」界面上一点反馈都没有。
        # 动画只是锦上添花，可见性是底线，所以移动端换成最朴素的 Container。
        if self._is_mobile():
            self.result_box = ft.Container(
                content=self._result_holder,
                height=result_height,
                border_radius=8,
            )
        else:
            self.result_box = motion.result_switcher(self._result_holder, height=result_height)

        # 手机 / 网页端：系统里没有 Python 解释器，代码要在 WebView 里的
        # Pyodide 上跑。flet 0.23 没有 page.run_js，所以靠 core.mobile_runner
        # 起的本地 HTTP 桥把代码送进这个 WebView，再把结果取回来。
        # 桌面端不需要它，完全不创建，免得白起一个本地服务。
        if self.backend() == "pyodide":
            self.engine_strip = self._build_engine_strip()

        self.root = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            f"示例代码 · {self.point_id}.py" if self.point_id else "示例代码",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=c["text"],
                            expand=True,
                            # 窗口一窄，右栏只有 300 多像素，标题会被挤成
                            # 一个字一行竖着排（很丑）。这里锁一行、超出省略。
                            no_wrap=True,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            code_executor.runtime_label(self.backend()),
                            size=11,
                            color=c["sub"],
                            no_wrap=True,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            visible=self.needs_input,
                        ),
                    ],
                    spacing=6,
                ),
                # 按钮单独一行并允许换行：手机端一行放不下四个按钮，
                # 换行比横向滚动好——手机上不方便拖着横条滑。
                # （别用 Row(scroll=...)：那会让整行在窄容器里塌成 0 高度，按钮直接消失。）
                ft.Row(
                    [
                        self.edit_button,
                        self.preview_button,
                        self.run_button,
                        self.reset_button,
                    ],
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                self.code_area,
                self.stdin_row,
                self.status,
                self.result_box,
            ],
            spacing=8,
            tight=True,
        )
        if self.engine_strip is not None:
            self.root.controls.insert(1, self.engine_strip)
        self._sync()
        self._render_result(None)

    def _build_engine_strip(self) -> ft.Container:
        """手机端那条「Python 引擎」状态条，底下就是跑代码的 WebView。"""
        from core import mobile_runner

        try:
            url = mobile_runner.start()
        except OSError as error:
            self.status.value = f"手机端引擎启动失败：{error}"
            return ft.Container(visible=False)
        self.engine_webview = ft.WebView(url=url, expand=True)
        return ft.Container(
            content=self.engine_webview,
            height=76,
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def test_inputs(self) -> list[str] | None:
        """把「标准输入」框里的内容拆成一行一个的数据；没填就返回 None。"""
        raw = (self.stdin_field.value or "").strip()
        if not raw:
            return None
        return [line for line in raw.splitlines() if line.strip()]

    def _hint(self) -> str:
        if self.backend() == "embedded":
            return f"{code_executor.runtime_label('embedded')} · 同一进程内运行，最长等 5 秒。"
        if self.backend() == "pyodide":
            return "网页端用 Pyodide 在页面里运行，最长等 5 秒。"
        if getattr(self, "needs_input", False):
            # 这一行旁边已经占了「标准输入」，提示压成一句，右栏才放得下。
            return f"{code_executor.runtime_label()} · 独立子进程运行"
        # 这里原来写的是「读不到你的文件」——沙箱只是 AST 白名单 + 子进程，
        # 挡得住教材里那些危险写法，却不是真正的安全边界，向学生承诺这个不诚实。
        # 改成实话：说清它是教学沙箱、别拿它跑陌生代码。右栏窄，句子必须短。
        return f"{code_executor.runtime_label()} · 独立子进程运行，最长等 5 秒（教学沙箱，请勿运行陌生代码）"

    # ------------------------------------------------------------------ 编辑
    def _on_edit(self, _event: Any = None) -> None:
        """回车自动缩进 + 同步行号 / 高亮 / 草稿。"""
        new = self.field.value or ""
        old = self._last_code
        self._last_code = new
        if new == old + "\n":  # 只在光标正好在末尾敲回车时才补缩进，避免光标乱跳
            previous = new[:-1].split("\n")[-1]
            pad = previous[: len(previous) - len(previous.lstrip())]
            if previous.rstrip().endswith(":"):
                pad += INDENT
            if pad:
                self.field.value = new + pad
                self._last_code = self.field.value
        self._sync()
        self._safe_update()

    def _sync(self) -> None:
        code = self.field.value or ""
        self._last_code = code
        lines = code.split("\n")
        shown = min(len(lines), MAX_LINES)
        width = max(2, len(str(shown)))
        self.gutter.value = "\n".join(f"{i:>{width}}" for i in range(1, shown + 1))
        clipped = code if shown == len(lines) else "\n".join(lines[:MAX_LINES])
        self.preview.value = ""
        self.preview.spans = highlight(clipped)
        # 只在学生真的改过之后才留草稿：还原成示例就该清掉，
        # 否则以后更新了 JSON 里的示例，旧草稿会把新示例盖住。
        # 用 save_draft_soon：每敲一个键都调这里，逐键整份重写磁盘
        # 会把 400 行草稿（约 13KB）写几百遍，还会捎带一次主目录探针。
        # 内存立刻更新，磁盘最多 0.8 秒一次，切页 / 运行前由 flush_pending 补上。
        if code != self.default_code:
            local_store.save_draft_soon(self.point_id, code)
        else:
            local_store.clear_draft(self.point_id)
        # 学生自己加了 input()，就把「标准输入」这一行放出来（只进不退，
        # 免得改着改着代码区高度来回跳）。
        if "input(" in code:
            self.needs_input = True
        self.stdin_row.visible = self.needs_input
        self.status.visible = not self.needs_input
        if self.on_code_change:
            self.on_code_change(code)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self.editor_box.visible = mode == "edit"
        self.preview_box.visible = mode == "highlight"
        self.edit_button.bgcolor = theme.PRIMARY if mode == "edit" else self.colors["card"]
        self.edit_button.content.color = "#FFFFFF" if mode == "edit" else self.colors["text"]
        self.preview_button.bgcolor = theme.PRIMARY if mode == "highlight" else self.colors["card"]
        self.preview_button.content.color = "#FFFFFF" if mode == "highlight" else self.colors["text"]
        self._safe_update()

    def _reset(self, _event: Any = None) -> None:
        # 先把还没落盘的敲键写下去：下面 _sync() 会立刻 clear_draft，
        # 万一之后有改动让它不再立刻落盘，学生的草稿也不该就这么没了。
        local_store.flush_pending()
        self.field.value = self.default_code
        self.stdin_field.value = str(self.point.get("sample_input", "") or "")
        self._sync()
        local_store.clear_draft(self.point_id)
        self._render_result(None)
        self._safe_update()

    # ------------------------------------------------------------------ 运行
    def _run(self, _event: Any = None) -> None:
        if self._running:
            return
        # 运行前把草稿补写一次：学生常常是「敲完立刻点运行」就切走，
        # 那不到 0.8 秒的最后一笔不补上的话，回来代码就回到上一个状态了。
        local_store.flush_pending()
        code = self.code()
        if not code.strip():
            self._render_result(
                code_executor.RunResult(False, error="先写点代码再运行吧。", error_type="empty")
            )
            self._safe_update()
            return
        self._running = True
        self.run_button.content = ft.Text("运行中…", size=12, color="#FFFFFF")
        self._safe_update()

        def worker() -> None:
            try:
                result = code_executor.run_code(
                    code, test_inputs=self.test_inputs(), backend=self.backend()
                )
            except BaseException:  # 沙箱自己炸了：解释器不在、结果文件坏了、Pyodide 桥报错……
                # 以前这里没有兜底：异常直接冒到线程顶，self._running 永远是 True，
                # 按钮卡在「运行中…」，学生再也点不动「运行代码」，只能重启软件。
                result = code_executor.RunResult(
                    False, error="运行环境出了点问题，请重试一次。", error_type="runtime"
                )
            finally:
                # 必须放 finally：BaseException 连 SystemExit / KeyboardInterrupt 一起接住，
                # 只 except Exception 兜不住，按钮还是会锁死。
                self._running = False
                self.run_button.content = ft.Text("▶ 运行代码", size=12, color="#FFFFFF")
            self._render_result(result)
            self._safe_update()
            if self.on_result:
                self.on_result(result)

        run_thread = getattr(self.page, "run_thread", None)
        if callable(run_thread):  # 真页面：丢后台线程，界面不会卡住
            run_thread(worker)
        else:  # 冒烟测试的假 Page：直接同步跑，方便断言
            worker()

    # ------------------------------------------------------------------ 结果
    def _render_result(self, result: code_executor.RunResult | None) -> None:
        c = self.colors
        if result is None:
            self._set_result([ft.Text("点上面的「▶ 运行代码」看结果。", size=12, color=c["sub"])])
            return

        if result.success:
            self._set_result([
                ft.Text(f"✅ 运行成功 · 用时 {result.duration:.2f} 秒", size=12, color=theme.SUCCESS),
                self._console(result.text or "（程序跑完了，但没有输出任何内容）"),
            ])
            return

        where = f"，在第 {result.line} 行" if result.line else ""
        kind = {
            "timeout": "运行超时",
            "security": "安全检查没通过",
            "sandbox": "沙箱异常",
            "backend": "没有可用的运行环境",
            "empty": "代码是空的",
        }.get(result.error_type, "运行失败")
        controls = [
            ft.Text(f"❌ {kind}{where}", size=12, color=theme.DANGER),
            ft.Text(result.error or "出了点问题，再检查一下代码。", size=12, color=c["sub"], selectable=True),
        ]
        if result.output:
            controls.append(self._console(result.output))
        self._set_result(controls)

    def _new_result_column(self, controls: list[ft.Control]) -> ft.Column:
        """结果区那个 Column。每次换内容都重新建，让弹窗能识别到「变了」。"""
        common = dict(
            spacing=6,
            tight=True,
            controls=controls,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        if self._result_height is None:
            return ft.Column(**common)
        return ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=False,
            height=self._result_height,
            **common,
        )

    def _set_result(self, controls: list[ft.Control]) -> None:
        """替换结果区内容。

        关键是只换 `result_box.content`，而不是重建 `result_box`——弹窗对象必须是原那个，
        否则旧内容没了可播的退场目标，只会闪一下。
        """
        self._result_holder = self._new_result_column(controls)
        self.result_box.content = self._result_holder

    def _console(self, text: str) -> ft.Container:
        lines = text.count("\n") + 1
        return ft.Container(
            # flet 0.23 的 Container 没有 scroll 参数，滚动要挂在内层 Column 上
            content=ft.Column(
                [ft.Text(text, font_family=MONO, size=12, color=SYNTAX["text"], selectable=True)],
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
                tight=True,
            ),
            bgcolor=theme.CODE_BG,
            border_radius=8,
            padding=10,
            height=min(160, max(40, lines * 18 + 12)),
        )

    # ------------------------------------------------------------------ 小工具
    def _safe_update(self) -> None:
        update = getattr(self.page, "update", None)
        if callable(update):
            try:
                update()
            except Exception:  # 页面还没挂上时忽略
                pass
