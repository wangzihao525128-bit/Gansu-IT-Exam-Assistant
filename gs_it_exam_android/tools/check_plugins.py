r"""插件接口自检（需求文档 8.4）。不需要 flet，直接运行即可：

    python tools/check_plugins.py

它在**临时目录**里现造三种插件，验完就删，不会碰项目里的 plugins\ 目录：

* ``good``     —— 三个钩子都写了的正常插件，应该被发现、能追加模块；
* ``broken``   —— 一 import 就抛异常的坏插件，应该被跳过、软件不炸；
* ``noisy``    —— 能加载但 ``modules()`` / ``detail_panel()`` 抛异常，应该被忽略；
* ``collide``  —— 模块 id 撞了官方 module1，应该被丢掉，官方内容不受影响。

退出码 0 表示插件接口一切正常，1 表示有问题。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import knowledge_store as store  # noqa: E402
from core import plugins  # noqa: E402

failed = 0


def check(label, got, want) -> None:
    global failed
    if got == want:
        print(f"  [ok]   {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label}\n         期望: {want!r}\n         实际: {got!r}")


# ---------------------------------------------------------------- 插件样本
GOOD = '''
PLUGIN = {"id": "good", "name": "示例扩展", "version": "2.1", "description": "自检用"}

PANEL = "这是插件追加的面板"
STARTED = []  # 供测试回读 startup(page) 到底传进去了什么

def modules():
    return [{
        "id": "plug1", "name": "插件模块", "color": "#7A5AF8",
        "points": [{
            "id": "plug_1_1", "title": "插件知识点", "content": "正文",
            "code_example": "print(1)", "code_explanation": "解释", "hints": {},
            "questions": [{
                "type": "choice", "question": "对吗", "options": ["A. 对", "B. 错"],
                "answer": "A", "explanation": "解析",
            }],
        }],
    }]

def detail_panel(point, colors):
    return PANEL

def startup(page):
    STARTED.append(page)
'''

BROKEN = '''
raise RuntimeError("这个插件故意写坏了")
'''

NOISY = '''
PLUGIN = {"id": "noisy", "name": "坏钩子插件"}

def modules():
    raise ValueError("modules() 故意报错")

def detail_panel(point, colors):
    raise ValueError("detail_panel() 故意报错")

def startup(page):
    raise ValueError("startup() 故意报错")
'''

COLLIDE = '''
PLUGIN = {"id": "collide", "name": "撞车插件"}

def modules():
    # id 撞了官方 module1，核心层必须把它丢掉
    return [{"id": "module1", "name": "假的模块一", "color": "#000000", "points": []}]
'''


def write_plugin(root: Path, name: str, source: str) -> None:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plugin.py").write_text(source, encoding="utf-8")


def main() -> int:
    print("=" * 60)
    print("插件接口自检（需求文档 8.4）")
    print("=" * 60)

    # STARTED 活在 good 插件自己的命名空间里，测 startup 时靠它取回来
    original_dir = plugins.plugin_dir
    base_count = len(store.load(force=True))
    print(f"项目自带插件目录：{plugins.plugin_dir()}")
    print(f"未装插件时模块数  ：{base_count}")
    print("-" * 60)

    with tempfile.TemporaryDirectory(prefix="gs_plugins_") as tmp:
        root = Path(tmp)
        write_plugin(root, "good", GOOD)
        write_plugin(root, "broken", BROKEN)
        write_plugin(root, "noisy", NOISY)
        write_plugin(root, "collide", COLLIDE)

        # 临时把插件目录指到 tmp，后面再还原
        plugins.plugin_dir = lambda: root  # type: ignore[assignment]
        try:
            plugins.discover(force=True)
            found = plugins.discover()
            ids = sorted(p["info"]["id"] for p in found)
            print(f"临时插件目录：{root}")
            print(f"发现插件      ：{ids}")
            print("-" * 60)

            # 1) 发现：坏的被跳过，好的都在
            check("好插件被发现", "good" in ids, True)
            check("撞车插件也能发现（加载没问题）", "collide" in ids, True)
            check("import 就报错的插件被跳过", "broken" in ids, False)
            check("被跳过的插件留下了原因", any("broken" in w for w in plugins.warnings()), True)

            # 2) 钩子识别
            hooks = {p["info"]["id"]: sorted(p["hooks"]) for p in found}
            check(
                "三个可选钩子都被认出来",
                hooks.get("good"),
                ["detail_panel", "modules", "startup"],
            )
            check("只写 modules 的插件不会被误认出别的钩子", hooks.get("collide"), ["modules"])

            # 3) 名片元信息
            good_info = next(p["info"] for p in found if p["info"]["id"] == "good")
            check("PLUGIN 名片里的名字/版本读得到", (good_info["name"], good_info["version"]), ("示例扩展", "2.1"))

            # 4) modules() 追加进题库
            modules = store.load(force=True)
            check("模块总数 = 官方 + 1（撞车的和报错的都不算）", len(modules), base_count + 1)
            check("追加的模块排在官方后面", modules[-1]["id"], "plug1")
            check(
                "官方模块一个都没少、顺序没变",
                [m["id"] for m in modules[:-1]],
                [m["id"] for m in store._modules_cache],
            )
            check(
                "官方模块没被插件污染到缓存里",
                "plug1" in [m["id"] for m in store._modules_cache],
                False,
            )
            check("插件模块的知识点能按 id 查到", store.get_point("plug_1_1") is not None, True)
            check("插件模块的模块能按 id 查到", store.get_module("plug1") is not None, True)
            check(
                "stats() 把插件模块也算进去",
                store.stats()["modules"],
                base_count + 1,
            )

            # 5) id 撞车：插件顶不掉官方内容
            check("撞车的模块 id 被丢掉", [m["name"] for m in modules].count("假的模块一"), 0)
            check("撞车有记录", any("module1" in n for n in store.plugin_notes()), True)
            official = store.get_module("module1")
            check("官方模块一还在、名字没被改", official.get("name") if official else None, "模块一：数据与信息")

            # 6) 坏钩子：报错被吞掉，不影响题库
            check("modules() 报错的插件不贡献模块", "noisy" in [m["id"] for m in modules], False)
            check(
                "坏钩子有记录",
                any("noisy" in w for w in plugins.warnings()),
                True,
            )

            # 7) validate() 连插件模块一起查
            problems = store.validate()
            check("合法插件模块不产生校验问题", [p for p in problems if "插件" in p], [])

            # 8) detail_panel() 把控件原样透传
            point = store.get_point("1_1")[1]
            panels = plugins.detail_panels(point, {"card": "#fff", "text": "#000", "sub": "#888", "border": "#ddd"})
            check("好插件的面板透传出来", panels, [("示例扩展", "这是插件追加的面板")])
            check("面板出错 / 没写钩子的插件不贡献面板", len(panels), 1)

            # 9) startup(page) 真的被调用
            page = object()
            done = plugins.startup(page)
            check("startup() 成功执行并返回插件名", done, ["示例扩展"])
            started = getattr(sys.modules.get("gs_it_exam_plugin_good"), "STARTED", [])
            check("startup() 收到了 page", started, [page])
            check("startup() 报错的插件不算成功", "坏钩子插件" in done, False)
        finally:
            plugins.plugin_dir = original_dir  # type: ignore[assignment]
            plugins.discover(force=True)
            store.load(force=True)

    # 10) 还原之后必须回到「一个插件都没有」的状态
    print("-" * 60)
    check("还原后插件清单为空", plugins.summary()["loaded"], [])
    check("还原后模块数回到官方数量", len(store.load(force=True)), base_count)
    check("还原后数据校验依然干净", store.validate(), [])

    print("-" * 60)
    if failed:
        print(f"插件接口自检未通过：{failed} 项失败")
        return 1
    print("插件接口检查通过，没有发现问题。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())