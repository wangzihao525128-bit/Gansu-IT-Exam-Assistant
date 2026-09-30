r"""署名与水印：左上角作者名 + 右下角 AI 协助声明。

**为什么两处用了两种做法**（都不是随便选的）：

* **左上角署名**做成小徽章，**直接放进每一页的顶栏里**，不用浮层——
  详情页左上角就是「← 返回」按钮，浮层压在上面会把返回点掉；
  放进顶栏还能跟着模块配色一起走，看着是界面的一部分，不是贴上去的膏药。
* **右下角 AI 声明**用 ``page.overlay`` 浮在最上层。两个原因：
  ``Page.clean()`` 只清 ``controls``、不清 ``overlay``，所以切页时不必每页都加一次；
  更关键的是浮层**不占布局高度**——右栏的高度预算是按像素算出来的，
  底下多占一行就会把「运行结果」框挤出卡片（这个坑真踩过）。

署名只在这一个文件里定义，改名字/改措辞只需要动下面三个常量。
"""

from __future__ import annotations

import flet as ft

AUTHOR = "王子豪"                    # 左上角署名
AI_NOTE = "本软件由 AI 协助制作"       # 右下角水印
VERSION = "v1.0"

# 装过水印的 page 上会打这个标记，避免同一页重复添加
_OVERLAY_FLAG = "_gs_watermark_installed"

# 水印字色：比正文的次要色（colors["sub"]）再淡一点，亮色/暗色主题下都看得见但不抢眼
WATERMARK_COLOR = "#8A8F98"


def author_chip() -> ft.Container:
    """顶栏里的署名徽章：白字 + 半透明白底，放在标题旁边（左上角一侧）。

    底色写 ``#33FFFFFF``（ARGB，白色 20% 透明），这样在首页蓝色顶栏和
    各模块自己的配色顶栏上都压得住，不用为每个模块单独调颜色。
    """
    return ft.Container(
        content=ft.Text(f"✍ {AUTHOR}", size=11, color="#FFFFFF", no_wrap=True),
        bgcolor="#33FFFFFF",
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
    )


def watermark() -> ft.Container:
    """右下角水印：半透明小字，靠 right/bottom 定位（overlay 里的坐标是相对窗口的）。"""
    return ft.Container(
        content=ft.Text(
            f"{AI_NOTE} · {VERSION}",
            size=11,
            color=WATERMARK_COLOR,
            opacity=0.55,
            no_wrap=True,
        ),
        right=12,
        bottom=8,
        padding=ft.padding.symmetric(horizontal=6, vertical=2),
    )


def install(page) -> bool:
    """把右下角水印挂到 ``page.overlay``；同一个页面只挂一次。

    **要在建页之前调用**：页面自己在构建过程中就会 ``page.update()``
    （首页的 refresh、详情页的进度卡），挂晚了得等下一次刷新才出现——
    和左栏进度卡那次「改完没刷」是同一类问题。

    冒烟测试用的假 Page 没有 ``overlay``，这里安静跳过，不影响建页。
    """
    if getattr(page, _OVERLAY_FLAG, False):
        return False
    overlay = getattr(page, "overlay", None)
    if overlay is None:
        return False
    try:
        overlay.append(watermark())
    except Exception:  # overlay 不是 list 之类的怪情况：不影响主流程
        return False
    try:
        setattr(page, _OVERLAY_FLAG, True)
    except Exception:  # 某些代理对象不让写属性
        pass
    return True
