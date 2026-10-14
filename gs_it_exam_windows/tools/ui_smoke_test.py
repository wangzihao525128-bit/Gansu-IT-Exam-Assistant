r"""界面冒烟测试：不启动窗口，用假 Page 把首页真正构建一遍。

    python tools\ui_smoke_test.py

作用：
1. 校验 Flet 控件用法是否正确（参数名、控制台属性），改动 ui/ 后立刻能发现问题；
2. 校验响应式布局、搜索过滤、主题切换、卡片点击这些交互逻辑；
3. 不依赖显示器和网络，可以在任何机器、任何时候跑。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 草稿和答题进度写到临时目录，别污染学生真实的 ~/.gs_it_exam
os.environ.setdefault("GS_EXAM_DATA_DIR", tempfile.mkdtemp(prefix="gs_exam_smoke_"))

import flet as ft  # noqa: E402

import main as app  # noqa: E402
from core import knowledge_store as store  # noqa: E402
from core import local_store  # noqa: E402
from core import plugins  # noqa: E402
from ui import branding, page_compat, theme  # noqa: E402
from ui.components import code_editor as ce  # noqa: E402
from ui.components.code_editor import fits as ce_fits, join_spans  # noqa: E402


def fake_page_height(height: float):
    """造一个只带 height 的假 Page，给 fit_height / fits 用。"""
    return type("P", (), {"height": height})()

CHILD_ATTRS = ("controls", "content", "leading", "trailing", "actions")


class FakeEvent:
    """模拟 flet 的路由事件对象。"""

    def __init__(self, route: str) -> None:
        self.route = route


class FakeEventBus:
    """模拟 flet 的事件总线：subscribe 注册，fire 触发。"""

    def __init__(self) -> None:
        self.handlers: list = []

    def subscribe(self, handler) -> None:
        if handler is not None:
            self.handlers.append(handler)

    def fire(self, event=None) -> None:
        for handler in list(self.handlers):
            handler(event)


class FakeWindow:
    """假 window：ui/page_compat.py 只需要 on_resized 就能判定走新 API。"""

    def __init__(self) -> None:
        self.on_resized = FakeEventBus()
        self.width = 1180
        self.height = 800
        self.min_width = 0
        self.min_height = 0


class FakePage:
    """够用的假 Page：只实现首页、模块页与 main.py 真正用到的那几个接口。"""

    def __init__(self, width: float = 1180.0) -> None:
        self.width = width
        self.height = 800.0
        self.platform = ""
        self.title = ""
        self.bgcolor = None
        self.padding = None
        self.on_resize = None
        self.snack_bar = None
        self.window = FakeWindow()
        self.route = "/"
        self.on_route_change = None
        self.data = None
        self.history: list[str] = []
        self.controls: list[ft.Control] = []
        # page.overlay 是真的 flet Page 上做浮层的那个列表；右下角 AI 水印挂在它里面。
        # 注意：真的 Page.clean() 只清 controls、不清 overlay，这里保持一致。
        self.overlay: list[ft.Control] = []
        self.update_count = 0

    def go(self, route: str) -> None:
        """模拟 page.go()：切换路由并触发 on_route_change。"""
        self.route = route
        self.history.append(route)
        if self.on_route_change:
            self.on_route_change(FakeEvent(route))

    def add(self, *controls: ft.Control) -> None:
        self.controls.extend(controls)

    def clean(self) -> None:
        self.controls.clear()

    def update(self) -> None:
        self.update_count += 1

    def resize(self, width: float | None = None) -> None:
        """模拟拖动窗口：改宽度再触发 on_resized。"""
        if width is not None:
            self.width = width
        self.window.on_resized.fire(FakeEvent(self.route))


def walk(control, parent=None, seen=None):
    """遍历控件树，产出 (控件, 父控件)。"""
    if isinstance(control, (list, tuple)):
        for item in control:
            yield from walk(item, parent, seen)
        return
    if control is None or isinstance(control, (str, int, float, bool)):
        return
    seen = seen if seen is not None else set()
    if id(control) in seen:
        return
    seen.add(id(control))
    yield control, parent
    for attr in CHILD_ATTRS:
        child = getattr(control, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for item in child:
                yield from walk(item, control, seen)
        else:
            yield from walk(child, control, seen)


def find(page: FakePage, predicate):
    for control, parent in walk(page.controls):
        if predicate(control):
            return control, parent
    return None, None


def visible_modules(page: FakePage) -> list[str]:
    names = {module["name"] for module in store.get_modules()}
    return [c.value for c, _ in walk(page.controls) if isinstance(c, ft.Text) and c.value in names]


def is_back_button(control) -> bool:
    """顶部导航栏的返回按钮：内容是一个以「←」开头的文本。"""
    return (
        isinstance(control, ft.Container)
        and control.on_click is not None
        and isinstance(control.content, ft.Text)
        and str(control.content.value).startswith("←")
    )


def is_card(control) -> bool:
    """可点击的卡片：首页模块卡片、模块页知识点卡片都是这个形状。"""
    return isinstance(control, ft.Container) and control.on_click is not None and isinstance(control.content, ft.Column)


def point_rows(page: FakePage, ids) -> list:
    """左栏里对应各知识点的行控件，返回 [(知识点 id, 控件)]。"""
    found = []
    for control, _ in walk(page.controls):
        if not (isinstance(control, ft.Container) and control.on_click and isinstance(control.content, ft.Row)):
            continue
        texts = [str(c.value) for c, _ in walk(control) if isinstance(c, ft.Text)]
        matched = [t for t in texts if t in ids]
        if matched:
            found.append((matched[0], control))
    return found


def expand_ratios(control) -> list:
    return [getattr(child, "expand", None) for child in getattr(control, "controls", []) or []]


def any_text_contains_on(control, needle: str) -> bool:
    """某个控件的子树里有没有包含指定文字的文本控件。"""
    return any(needle in str(c.value) for c, _ in walk(control) if isinstance(c, ft.Text))


def any_text_contains(page: FakePage, needle: str) -> bool:
    return any_text_contains_on(page.controls, needle)


def console_text(control) -> str:
    """取运行结果里那块等宽控制台的内容（区别于标题、状态文字）。"""
    for item, _ in walk(control):
        if isinstance(item, ft.Text) and item.font_family == "Consolas" and item.selectable:
            return str(item.value or "")
    return ""


def first_matching(page: FakePage, predicate):
    for control, _ in walk(page.controls):
        if predicate(control):
            return control
    return None


def shown_titles(page: FakePage, titles) -> list[str]:
    wanted = set(titles)
    return [c.value for c, _ in walk(page.controls) if isinstance(c, ft.Text) and c.value in wanted]


def check(label: str, actual, expected) -> None:
    status = "PASS" if actual == expected else "FAIL"
    print(f"[{status}] {label}: {actual!r}" + ("" if status == "PASS" else f"  期望 {expected!r}"))
    if status == "FAIL":
        check.failed = True


check.failed = False


def main_test() -> int:
    modules = store.get_modules()
    all_names = [module["name"] for module in modules]

    # 1. 宽屏：三栏首页应渲染出全部模块卡片（网格）
    page = FakePage(width=1180.0)
    app.main(page)
    check("宽屏显示模块卡片", visible_modules(page), all_names)
    check("宽屏使用换行网格", any(isinstance(c, ft.Row) and c.wrap for c, _ in walk(page.controls)), True)
    # 底部两张卡：宽屏并排、窄屏上下堆叠。跟着 refresh() 走，所以拖窗口就会变。
    check("宽屏底部两张卡并排", any(
        isinstance(node, ft.Row) and not node.wrap
        and any_text_contains(node, "备考建议") and any_text_contains(node, "学习进度")
        for node, _ in walk(page.controls)), True)

    # 2. 窄屏（手机）：改成上下列表
    page.resize(400.0)
    check("窄屏仍显示全部模块", visible_modules(page), all_names)
    check("窄屏取消网格", any(isinstance(c, ft.Row) and c.wrap for c, _ in walk(page.controls)), False)
    check("窄屏底部两张卡改成上下堆叠", any(
        isinstance(node, ft.Column)
        and any_text_contains(node, "备考建议") and any_text_contains(node, "学习进度")
        for node, _ in walk(page.controls)), True)
    # 首页底部：备考建议 + 学习进度。数据从 Step 7 起就存在 local_store 里，
    # 但之前界面上从来没露过面（只有中栏练习题区那一行），顺手把下半屏空白也填了。
    check("首页有备考建议卡", any_text_contains(page, "备考建议"), True)
    check("首页有学习进度卡", any_text_contains(page, "学习进度"), True)
    check("学习进度卡显示总题数", any_text_contains(page, f"0 / {store.stats()['questions']} 题"), True)

    # 署名与水印（ui/branding.py）：
    #   左上角署名在顶栏里（不是浮层——浮层会压住详情页的「← 返回」按钮）；
    #   右下角 AI 声明走 page.overlay，不占布局高度。
    check("首页顶栏有作者署名", any_text_contains(page, f"✍ {branding.AUTHOR}"), True)
    check("右下角 AI 水印已挂到 overlay", any_text_contains_on(page.overlay, branding.AI_NOTE), True)
    check("水印在 overlay 里只挂一份", len(page.overlay), 1)
    # 切页后 Page.clean() 不清 overlay，不该越积越多
    page.go("/module/module1")
    page.go("/")
    check("切页后水印没有重复挂", len(page.overlay), 1)
    # 回归：点「返回首页」不该把用户调好的窗口拉回 1180x800。
    # 以前 home_page.py 无条件每次都设，于是学生把窗口最大化后点一下返回，
    # 窗口就被强行缩回去，正在看的代码被挤掉。之前在文档里当"已知取舍"写过——
    # 那不对，这是 bug。
    win_page = FakePage(width=1180.0)
    app.main(win_page)
    check("首启动把窗口定成 1180x800", (win_page.window.width, win_page.window.height), (1180, 800))
    check("最小尺寸守着 680x560", (win_page.window.min_width, win_page.window.min_height), (680, 560))
    win_page.window.width, win_page.window.height = 1920, 1080  # 学生自己最大化
    win_page.go("/module/module1")
    win_page.go("/")  # 点「返回首页」
    check("返回首页不会把窗口拉回去", (win_page.window.width, win_page.window.height), (1920, 1080))
    win_page.window.width, win_page.window.height = 900, 700
    win_page.go("/module/module2")
    win_page.go("/")
    check("用户把窗口改小也不被强行拉回", (win_page.window.width, win_page.window.height), (900, 700))

    page.resize(1180.0)  # 后面几步都按电脑端宽度继续

    # 3. 搜索过滤（期望值直接由数据层算出，避免写死）
    keyword = "加密"
    hit_ids = {hit["module"]["id"] for hit in store.search(keyword)}
    expected = [m["name"] for m in modules if m["id"] in hit_ids]
    field, _ = find(page, lambda c: isinstance(c, ft.TextField))
    field.value = keyword
    field.on_change(None)
    check(f"搜索「{keyword}」", visible_modules(page), expected)

    field.value = "绝对搜不到的词zzz"
    field.on_change(None)
    check("搜索无结果有提示", any("没有找到" in str(c.value) for c, _ in walk(page.controls) if isinstance(c, ft.Text)), True)

    # 4. 点击模块卡片 -> 按 URL 参数跳到模块浏览页
    field.value = ""
    field.on_change(None)
    first_matching(page, is_card).on_click(None)
    check("模块卡片跳转到模块页", page.route, "/module/module1")

    # 5. 模块页按路由参数加载出该模块的知识点列表
    check("模块页加载知识点列表", shown_titles(page, [p["title"] for p in store.get_points("module1")]),
          [p["title"] for p in store.get_points("module1")])
    check("模块页有返回按钮", first_matching(page, is_back_button) is not None, True)

    # 6. 点击知识点卡片 -> 详情页（Step 5 三栏布局）
    first_matching(page, is_card).on_click(None)
    check("知识点跳转到详情页", page.route, "/point/module1/1_1")
    check("详情页显示知识点标题", len(shown_titles(page, [store.get_point("1_1")[1]["title"]])) >= 1, True)
    check("讲解用 Markdown 渲染", any(isinstance(c, ft.Markdown) for c, _ in walk(page.controls)), True)
    check("含代码示例与代码解释区", any_text_contains(page, "代码示例") and any_text_contains(page, "代码解释"), True)
    wide = next((c for c, _ in walk(page.controls) if isinstance(c, ft.Row) and 25 in expand_ratios(c)), None)
    check("宽屏三栏 25/45/30", expand_ratios(wide) if wide else None, [25, 45, 30])
    point_ids = [p["id"] for p in store.get_points("module1")]
    rows = point_rows(page, point_ids)
    check("左栏知识点行数", len(rows), len(point_ids))
    # 6.3 Step 6：代码编辑器（语法高亮 / 行号 / 自动缩进 / 沙箱运行）
    check("缩放监听走新 API", page_compat.resize_backend(page), "window")
    editor = page.data["editor"]
    sample = store.get_point("1_1")[1]
    check("高亮拼回原文不丢空格", join_spans(editor.preview.spans), editor.code())
    check("行号数量与代码行数一致", len(editor.gutter.value.strip().split("\n")), len(editor.code().split("\n")))
    # 回归：以前 _sync() 会按行数把 code_area 重新撑高，把「运行状态 + 运行结果」
    # 挤出卡片——学生点「运行代码」看上去一点反应都没有。这条断言盯住高度。
    check("代码区高度不被行数覆盖", editor.code_area.height, editor.fitted_height)
    # 回归：右栏内宽只有 270 上下，四个按钮必然换行成两排。高度预算如果按
    # 一排按钮算，少 38px，「运行结果」正好被顶出卡片——学生点完「运行代码」
    # 只看得见绿色的「运行成功」，看不见输出。fits() 用最坏情况验这个预算。
    right_share = 2 / 3
    check("运行结果放得下（按钮按两排算）", ce_fits(761, right_share), True)
    check("最常见窗口高度也放得下", ce_fits(1040, right_share), True)
    check(
        "代码区 + 固定开销 = 右栏可用高度",
        ce.fit_height(fake_page_height(761), len(sample["code_example"].split("\n")), right_share)
        + ce.INNER_CHROME_PX
        + ce.fit_result_height(right_share),
        int((761 - ce.OUTER_CHROME_PX) * right_share),
    )

    # 回归：教材示例里有若干段用了 input()（早期是 2_2 / 2_3 / 2_5 三段，
    # 后来模块六的真题精讲又补了 7 段）。以前界面上根本没有地方敲数据，
    # 学生点「运行代码」只会拿到一段 ValueError 报错，看不出代码错在哪。
    # 现在：用到 input() 的知识点都配了 sample_input，编辑器多一行「标准输入」，
    # 并且这一行的高度算进了右栏预算，不会把运行结果挤出卡片。
    input_points = [
        p
        for m in store.get_modules()
        for p in m.get("points", [])
        if "input(" in str(p.get("code_example", ""))
    ]
    # 这里断言的是「**至少**有 3 个」而不是「恰好等于 3」。
    # 原来写死等于 3，题库一加内容（比如模块六那 7 道真题）就会误报失败——
    # 那属于测试自身太脆，不是数据错了。真正要守的是下面那条一致性检查：
    # **每个用到 input() 的知识点都必须配 sample_input**，少一个才算真问题。
    check("题库里有需要键盘输入的示例（≥3 个，保证标准输入这条路径有覆盖）",
          len(input_points) >= 3, True)
    check(
        "用到 input() 的示例都配了 sample_input",
        [p["id"] for p in input_points if not str(p.get("sample_input", "")).strip()],
        [],
    )
    check("不需要输入的示例不显示标准输入行", editor.stdin_row.visible, False)
    # 详情页沿用首页设的 1180x800 窗口：带「标准输入」时高度预算不能超支。
    # （窗口再矮到 760px 左右，右栏会自动改成内部滚动——见 _region 的 scroll，
    #   内容不会丢，只是要多滑一下。）
    check("默认窗口高度下带标准输入也放得下", ce_fits(800, right_share, True), True)
    check("常见窗口高度下带标准输入也放得下", ce_fits(1040, right_share, True), True)
    check(
        "带标准输入的高度预算不超支",
        ce.fit_height(fake_page_height(800), 6, right_share, True)
        + ce.INNER_CHROME_PX
        + ce.STDIN_EXTRA_PX
        + ce.fit_result_height(right_share)
        <= int((800 - ce.OUTER_CHROME_PX) * right_share),
        True,
    )

    # 回归（MuMu 模拟器横屏 1600x900 实测）：设备像素比 1.5，flet 看到的
    # page.height 只有 600 逻辑像素。电脑端那套 fit_height 在这里算出 37px，
    # 直接掉到 CODE_MIN_PX_INPUT 下限 130px，右栏卡片扣完固定开销只剩 19px 给
    # 运行结果——结果框被顶到卡片内部滚动区外面，点完「运行代码」看不见输出。
    # 手机横屏走 fit_mobile_wide：代码区 + 固定开销 + 结果区必须放得下。
    for label, page_h in (("手机横屏 1600x900(dpr1.5)", 600), ("平板横屏", 1000)):
        for needs_input in (False, True):
            need = (
                ce.fit_mobile_wide(page_h, 33, needs_input)
                + ce.MOBILE_WIDE_CHROME_PX
                + (ce.STDIN_EXTRA_PX if needs_input else 0)
                + ce.RESULT_BOX_PX_MOBILE_WIDE
            )
            have = int((page_h - ce.OUTER_CHROME_PX) * ce.MOBILE_WIDE_EDITOR_SHARE) - 28
            check(f"{label}{'带标准输入' if needs_input else ''}: 代码区+结果区放得下", need <= have, True)
    check("手机横屏代码区不低于下限", ce.fit_mobile_wide(400, 33, True) >= ce.CODE_MIN_PX_MOBILE_WIDE, True)
    check("手机横屏代码区不超上限", ce.fit_mobile_wide(4000, 200, False) <= ce.CODE_MAX_PX, True)

    # 回归（Win 走查实测）：**矮窗口**也必须走「右栏整列给编辑器」那套。
    # 614 逻辑像素 = 常见的 1366×768 笔记本开 125% 缩放（注意是逻辑像素，
    # 屏幕够大不等于放得下）。电脑端三栏的高度预算是
    # 「编辑器下限 150 + 固定开销 178 + 结果框 88 = 416」，右栏只占可用高度的
    # 2/3，反推需要逻辑高度 ≈ 748 以上；实测这在 1093x614 下走查失败——
    # 按钮点到了，但「运行状态那一行没渲染出来」（结果框被挤出卡片）。
    short_page = FakePage(width=1180.0)
    short_page.height = 614.0
    app.main(short_page)
    short_page.go("/point/module2/2_2")
    short_editor = short_page.data["editor"]
    short_sample = store.get_point("2_2")[1]["code_example"]
    short_lines = len(short_sample.splitlines())
    short_needs_input = "input(" in short_sample
    check(
        "矮窗口走手机横屏那套高度算法",
        short_editor.fitted_height,
        ce.fit_mobile_wide(614.0, short_lines, short_needs_input),
    )
    check(
        "矮窗口结果区定高（不会被挤出卡片）",
        short_editor._result_height,
        ce.RESULT_BOX_PX_MOBILE_WIDE,
    )
    # 矮窗口下把「代码解释」挪到中栏，右栏整列留给代码与运行结果
    short_row = next(
        (c for c, _ in walk(short_page.controls) if isinstance(c, ft.Row) and 25 in expand_ratios(c)), None
    )
    short_center = short_row.controls[1] if short_row is not None and len(short_row.controls) > 1 else None
    check(
        "矮窗口把代码解释挪到中栏",
        bool(short_center) and any_text_contains_on(short_center, "代码解释"),
        True,
    )
    check("矮窗口里代码区不低于手机横屏下限", short_editor.fitted_height >= ce.CODE_MIN_PX_MOBILE_WIDE, True)
    check(
        "矮窗口预算不溢出",
        short_editor.fitted_height + ce.MOBILE_WIDE_CHROME_PX
        + (ce.STDIN_EXTRA_PX if short_needs_input else 0)
        + ce.RESULT_BOX_PX_MOBILE_WIDE
        <= int((614 - ce.OUTER_CHROME_PX) * ce.MOBILE_WIDE_EDITOR_SHARE) - 28,
        True,
    )
    # 普通高度（768 及以上）仍然走原来的电脑端算法，别把好窗口一起改了
    tall_page = FakePage(width=1180.0)
    tall_page.height = 800.0
    app.main(tall_page)
    tall_page.go("/point/module2/2_2")
    check(
        "普通高度窗口仍用电脑端算法",
        tall_page.data["editor"].fitted_height,
        ce.fit_height(tall_page, short_lines, 2 / 3, short_needs_input),
    )

    # 真跑一遍带输入的示例：以前这一步是必失败的
    page.go("/point/module2/2_3")
    editor_in = page.data["editor"]
    check("用到 input() 时显示标准输入行", editor_in.stdin_row.visible, True)
    check("标准输入已预填样例", editor_in.stdin_field.value, store.get_point("2_3")[1]["sample_input"])
    editor_in.run()
    check("带输入的示例点运行就成功", any_text_contains_on(editor_in.result_box, "运行成功"), True)
    check("带输入的示例输出正确", "良好" in console_text(editor_in.result_box), True)
    # 学生自己加 input() 也要能放出来
    editor_in.field.value = "print(input())"
    editor_in.field.on_change(None)
    check("改代码加了 input() 会放出标准输入行", editor_in.stdin_row.visible, True)
    editor_in.stdin_field.value = "hello"
    editor_in.run()
    check("改后的代码用标准输入跑通", "hello" in console_text(editor_in.result_box), True)
    page.go("/point/module1/1_1")
    editor = page.data["editor"]

    editor.run()
    check("示例代码运行成功", any_text_contains_on(editor.result_box, "运行成功"), True)
    check("示例代码有输出", console_text(editor.result_box).strip() != "", True)

    editor.field.value = "if True:"
    editor.field.on_change(None)
    editor.field.value = "if True:\n"
    editor.field.on_change(None)  # 模拟按回车
    check("冒号结尾自动缩进", editor.code(), "if True:\n" + "    ")

    editor.field.value = "print(1 + 1)"
    editor.field.on_change(None)
    editor.run()
    check("简单代码运行成功", any_text_contains_on(editor.result_box, "运行成功"), True)
    check("运行输出正确", console_text(editor.result_box).strip(), "2")

    editor.field.value = "print(未定义的变量)"
    editor.field.on_change(None)
    editor.run()
    check("运行失败有提示", any_text_contains_on(editor.result_box, "运行失败"), True)
    check("错误提示是中文", any_text_contains_on(editor.result_box, "还不存在的名字"), True)

    editor.field.value = "import os\nos.system('echo hi')"
    editor.field.on_change(None)
    editor.run()
    check("危险代码被安全检查拦下", any_text_contains_on(editor.result_box, "安全检查没通过"), True)

    editor.field.value = "while True:\n    pass"
    editor.field.on_change(None)
    editor.run()
    check("死循环被超时掐断", any_text_contains_on(editor.result_box, "运行超时"), True)

    editor.field.value = ""
    editor.field.on_change(None)
    editor.run()
    check("空代码有友好提示", any_text_contains_on(editor.result_box, "先写点代码"), True)

    editor._reset()
    check("还原示例代码", editor.code(), sample["code_example"])

    # 6.4 Step 7：练习题（单选 + 即时判分 + 解析）
    cards = page.data["quiz"].cards
    check("练习题数量", len(cards), len(sample["questions"]))
    card = cards[0]
    card.submit()
    check("没选不能提交", card.submitted, False)
    card.select(card.answer)
    check("选中后有标记", card.chosen, card.answer)
    card.submit()
    check("答对判定", card.correct(), True)
    check("答对显示解析", any_text_contains_on(card.feedback, "解析"), True)
    check("答题进度已保存", any_text_contains_on(page.data["quiz"], "已答 1 /"), True)

    # 6.4.2 学习进度面板。详情页建页时卡上是「0 / N」（那时还没答题），
    # 这里答完第一题就断言它变成了 1 —— 也就是说 on_progress 那根线真的接通了。
    # 断了的话这里会一直是 0，测试就红。
    _mod1 = store.get_module("module1")
    _stat = local_store.module_stat(_mod1)
    check("左栏有本模块学习进度卡", any_text_contains(page, "本模块学习进度"), True)
    check("答题后左栏进度卡实时更新", any_text_contains(page, f"{_stat['answered']} / {_stat['total']} 题"), True)
    check("进度卡答对数与存档一致", any_text_contains(page, f"答对 {_stat['correct']} 题"), True)
    check("进度卡显示已练知识点数", any_text_contains(page, f"已练过 {_stat['touched']} / {_stat['points']} 个知识点"), True)
    check("正确率算得对", any_text_contains(page, f"正确率 {_stat['correct'] / _stat['answered'] * 100:.0f}%"), True)

    if len(cards) > 1:
        other_card = cards[1]
        wrong_letter = next(letter for letter in other_card.letters() if letter != other_card.answer)
        other_card.select(wrong_letter)
        other_card.submit()
        check("答错判定", other_card.correct(), False)
        check("答错显示正确答案", any_text_contains_on(other_card.feedback, f"正确答案是 {other_card.answer}"), True)
        other_card.retry()
        check("重做清空选择", (other_card.chosen, other_card.submitted), ("", False))

    # 6.4.1 回归：可点击容器里的文字不能设 selectable=True
    # Flutter 里可选文本会吞掉 tap 手势，点选项文字会没反应（踩过这个坑）。
    def selectable_under_clickable(node):
        """找出「可点击容器」子树里所有 selectable 的文字控件。"""
        bad = []
        for item, _ in walk(node):
            if not (isinstance(item, ft.Container) and item.on_click is not None):
                continue
            for child, _ in walk(item):
                if isinstance(child, ft.Text) and child.selectable:
                    bad.append(str(child.value)[:24])
        return bad

    check("选项文字没被 selectable 吞掉点击", selectable_under_clickable(page.controls), [])
    check("提示面板文字没被 selectable 吞掉点击",
          selectable_under_clickable(page.data["hints"].control), [])

    # 6.5 Step 8：代码提示面板
    hints = page.data["hints"]
    check("提示条数", len(hints.items), len(sample["hints"]))
    check("提示默认折叠", hints.body.visible, False)
    hints.toggle()
    check("提示可以展开", hints.body.visible, True)
    check("提示关键词来自 JSON", [k for k, _ in hints.items], list(sample["hints"]))
    check("标出代码里用到的关键词", len(hints.used_keywords()) <= len(hints.items), True)

    # 6.1 左栏切换知识点
    next(control for pid, control in rows if pid == "1_2").on_click(None)
    check("左栏切换知识点", page.route, "/point/module1/1_2")

    page.resize(400.0)
    # 手机端堆叠现在是 4 块：讲解 / 代码 / 解释 / 学习进度。
    # 手机端没有左栏，进度卡放整页最后，否则这个模块练到哪儿在手机上是看不见的。
    narrow = next(
        (
            c
            for c, _ in walk(page.controls)
            if isinstance(c, ft.Column) and c.scroll is not None and len(c.controls) == 4
        ),
        None,
    )
    check("窄屏整页可滚动", narrow is not None, True)
    check("窄屏区块按内容自然高度", [r.height for r in (narrow.controls if narrow else [])], [None, None, None, None])
    check("窄屏也有本模块学习进度卡", any_text_contains_on(narrow, "本模块学习进度") if narrow else False, True)
    page.resize(1180.0)
    check("切回宽屏三栏", any(isinstance(c, ft.Row) and expand_ratios(c) == [25, 45, 30] for c, _ in walk(page.controls)), True)
    # 回归：进度卡必须排在左栏的【最后】。之前它被 expand=True 的知识点列表
    # 顶到了可视区外——控件在树里、单测查得到，屏幕上却是空的，只有真机截图能看出来。
    wide_now = next((c for c, _ in walk(page.controls)
                     if isinstance(c, ft.Row) and expand_ratios(c) == [25, 45, 30]), None)
    left_region = wide_now.controls[0] if wide_now is not None and wide_now.controls else None
    left_body = getattr(left_region, "content", None)
    left_tail = left_body.controls[-1] if left_body is not None and getattr(left_body, "controls", None) else None
    check("宽屏左栏有本模块学习进度卡", any_text_contains(page, "本模块学习进度"), True)
    check("进度卡钉在左栏最后（没被列表顶出可视区）", any_text_contains_on(left_tail, "本模块学习进度") if left_tail else False, True)
    check("左栏上半部分单独滚动，进度卡不跟着滚",
          [getattr(x, "expand", None) for x in (left_body.controls if left_body is not None else [])],
          [True, None])

    # 6.5 需求文档 8.4 的插件接口：面板要真的画到详情页右栏，坏插件不能把页面画崩。
    # check_plugins.py 只验了数据层（模块能追加、坏插件被跳过），
    # 这里是验「界面这一层」——不然接口写了却接不上，测试也是全绿。
    _plugin_src = """
import flet as ft
PLUGIN = {"id": "ui_probe", "name": "界面探针插件"}

def detail_panel(point, colors):
    return ft.Text("插件面板测试标记")
"""

    def has_text(mark: str) -> bool:
        return any(isinstance(c, ft.Text) and mark in str(c.value) for c, _ in walk(page.controls))

    with tempfile.TemporaryDirectory(prefix="gs_ui_plugin_") as _tmp:
        _root = Path(_tmp)
        _dir = _root / "ui_probe"
        _dir.mkdir(parents=True)
        (_dir / "plugin.py").write_text(_plugin_src, encoding="utf-8")
        _saved = plugins.plugin_dir
        plugins.plugin_dir = lambda: _root  # type: ignore[assignment]
        try:
            plugins.discover(force=True)
            app.route_change(page, "/point/module1/1_1")
            check("插件面板画进了详情页", has_text("插件面板测试标记"), True)
            check("面板上有插件名", has_text("界面探针插件"), True)
            check("右栏出现「扩展功能」分区", has_text("扩展功能"), True)

            # 面板报错的插件：页面白照画，不该冒出异常
            (_dir / "plugin.py").write_text(
                "def detail_panel(point, colors):\n    raise RuntimeError('故意炸')\n", encoding="utf-8"
            )
            plugins.discover(force=True)
            try:
                app.route_change(page, "/point/module1/1_1")
                check("面板报错的插件不炸页面", has_text("扩展功能"), False)
                check("页面其它内容还在", has_text("代码编辑器"), True)
            except Exception as _error:  # noqa: BLE001
                check("面板报错的插件不炸页面", f"抛异常：{_error}", False)
        finally:
            plugins.plugin_dir = _saved  # type: ignore[assignment]
            plugins.discover(force=True)
            store.load(force=True)

    app.route_change(page, "/point/module1/1_1")
    check("还原后插件面板消失", has_text("插件面板测试标记"), False)
    check("还原后详情页仍然正常", has_text("代码编辑器"), True)

    # 7. 逐级返回：详情页 -> 模块页 -> 首页
    first_matching(page, is_back_button).on_click(None)
    check("详情页返回模块页", page.route, "/module/module1")

    # 模块页底部的「下一个模块」引导卡（提求文档 Step 3 的响应式布局）。
    # 模块一只有 3 个知识点，卡片只占上半屏，下半屏全空——这张卡把空白变成了引导。
    # 引导卡的 content 是 Row（左文字右箭头），所以不能用 is_card（那个只认 Column）。
    next_card = next(
        (c for c, _ in walk(page.controls)
         if isinstance(c, ft.Container) and c.on_click is not None
         and any_text_contains_on(c, "下一个：")),
        None,
    )
    check("模块页有下一模块引导卡", next_card is not None, True)
    if next_card is not None:
        next_card.on_click(None)
        check("引导卡能跳到下一模块", page.route, "/module/module2")
        # 模块页的返回按钮直接回首页（不是退上一个模块），这是既有设计
        first_matching(page, is_back_button).on_click(None)
        check("从下一模块能回首页", page.route, "/")
        # 回到本模块继续验证下一步的返回链路
        page.go("/module/module1")
        check("重新进入模块页", page.route, "/module/module1")
    first_matching(page, is_back_button).on_click(None)
    check("模块页返回首页", page.route, "/")
    check("回到首页模块卡片", visible_modules(page), all_names)

    # 5. 主题切换
    button, _ = find(page, lambda c: isinstance(c, ft.Container) and c.on_click and c.content is not None and isinstance(c.content, ft.Text) and str(c.content.value).endswith("模式"))
    before = page.bgcolor
    button.on_click(None)
    check("切换到暗色背景", page.bgcolor, theme.colors()["bg"])
    check("暗色与原背景不同", page.bgcolor != before, True)
    check("主题状态", theme.mode(), "dark")

    button, _ = find(page, lambda c: isinstance(c, ft.Container) and c.on_click and c.content is not None and isinstance(c.content, ft.Text) and str(c.content.value).endswith("模式"))
    button.on_click(None)
    check("切回亮色", theme.mode(), "light")

    print("-" * 56)
    if check.failed:
        print("界面冒烟测试未通过，请按上面的 FAIL 项排查。")
        return 1
    print("界面冒烟测试全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_test())
