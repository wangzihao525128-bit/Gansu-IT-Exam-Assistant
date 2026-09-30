r"""署名与水印 + 署名校验（作者身份标识，请勿移除）。

三处署名都从这里出：**顶栏徽章**（左上角）、**右下角水印**、**窗口标题**，
内容由下面的编码数据在运行时解出，源码里没有明文姓名。

**为什么要编码 + 签名自检**：不是为了"保密"，而是让「把名字改成自己的再发出去」
这件事变得不划算——
改名的人要么先把编码解开（得看懂这套东西），要么改了之后自检对不上，
**界面反而会弹出「本软件已被修改」并把作者名换回权威副本里的那位**，
他自己的"署名"就变成了篡改证据。权威副本（``_CREDIT_AUTHORITY``）里另存了一份
作者名，即使主署名被人改掉，界面上显示的仍然是原作者。

**能力边界要说清楚**（别把它当防弹衣）：这是 Python / Flutter 程序，理论上一定能被
拆包、反编译、改名重打包。所以这里做的是「提高门槛 + 留痕 + 可追溯」：

1. 源码里无明文署名，且署名/声明三处同源，改一处不生效；
2. 自检失败会显式提示，并把作者名回退到权威副本；
3. 分发包本身带作者信息：Windows 版 exe 的「文件属性 → 详细信息」里有作者与版权，
   Android APK 用**作者自己的签名密钥**签名（``apksigner verify --print-certs``
   能看到证书里的名字，没有私钥谁也伪造不了）；
4. 法律与时间线层面：仓库是 MIT 开源，衍生作品必须保留版权声明与作者署名
   （见仓库根目录 ``LICENSE`` 与 ``署名与授权声明.md``），提交历史即创作时间线。

这四条合起来才是完整的"归属"方案；单靠任何一条都挡不住有心人。
"""

from __future__ import annotations

import base64
import hashlib

import flet as ft

# 版本号：界面上跟着署名一起显示，改版本时**必须同步更新 _SIGNATURE**
VERSION = "v1.0"

# 解码用的密钥（编码只为了让明文不直接出现在源码里，不是加密）
_KEY = b"gs-it-exam-2026-gansu"

# ---- 以下四行是运行时解出来的署名数据，不要手改；改名字请找作者本人 ----
_CREDIT_ENCODED = "fc>V7*}aX)%K"
_CREDIT_AUTHORITY = "kHUwH*}a1H>JiGkyVsk&kI=*"
_NOTE_ENCODED = "f$xEV$%28y*NVA=5OaSGg6!dz|IU`B-;j{`"
_SIGNATURE = "d0bac5d0b2e662563e262f84c53d32f3"

# 水印字色：比正文次要色再淡一点，亮色/暗色主题下都看得见但不抢眼
WATERMARK_COLOR = "#8A8F98"

# 装过水印的 page 上会打这个标记，避免同一页重复添加
_OVERLAY_FLAG = "_gs_watermark_installed"


def _decode(blob: str) -> str:
    """把编码数据还原成字符串（异或 + base85）。"""
    raw = base64.b85decode(blob.encode("ascii"))
    return bytes(byte ^ _KEY[i % len(_KEY)] for i, byte in enumerate(raw)).decode("utf-8")


AUTHOR = _decode(_CREDIT_ENCODED)
AI_NOTE = _decode(_NOTE_ENCODED)
# 权威副本：格式是「作者名反写|作者名」，取后一段
_AUTHORITY = _decode(_CREDIT_AUTHORITY).split("|")[-1]


def _signature() -> str:
    return hashlib.sha256(f"{AUTHOR}|{AI_NOTE}|{VERSION}".encode("utf-8")).hexdigest()[:32]


def verify() -> tuple[bool, str]:
    """校验署名与 AI 声明有没有被动过。

    返回 ``(是否正常, 提示语)``；提示语可以直接显示给学生看，
    里面用的是**权威副本**里的作者名。
    """
    if AUTHOR != _AUTHORITY or _signature() != _SIGNATURE:
        return False, f"⚠ 本软件已被修改，原作者：{_AUTHORITY}。请从作者处获取正版。"
    return True, ""


def author_text() -> str:
    """界面上显示的作者名：自检不通过时回退到权威副本（也就是原作者）。"""
    ok, _ = verify()
    return AUTHOR if ok else _AUTHORITY


def note_text() -> str:
    return AI_NOTE


def author_chip() -> ft.Container:
    """顶栏里的署名徽章：白字 + 半透明白底，放在标题旁边（左上角一侧）。

    底色写 ``#33FFFFFF``（ARGB，白色 20% 透明），这样在首页蓝色顶栏和各模块
    自己的配色顶栏上都压得住，不用为每个模块单独调颜色。

    为什么放顶栏而不是浮层：详情页左上角就是「← 返回」按钮，
    浮层压上去会把返回点掉。
    """
    return ft.Container(
        content=ft.Text(f"✍ {author_text()}", size=11, color="#FFFFFF", no_wrap=True),
        bgcolor="#33FFFFFF",
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
    )


def watermark() -> ft.Container:
    """右下角水印：半透明小字，靠 right/bottom 定位（overlay 里的坐标相对窗口）。"""
    return ft.Container(
        content=ft.Text(
            f"{note_text()} · {VERSION} · {author_text()}",
            size=11,
            color=WATERMARK_COLOR,
            opacity=0.55,
            no_wrap=True,
        ),
        right=12,
        bottom=8,
        padding=ft.padding.symmetric(horizontal=6, vertical=2),
    )


def window_title(base: str) -> str:
    """窗口/任务栏标题：带上作者名，多一处跑不掉的署名。"""
    return f"{base} · {author_text()}"


def startup_banner() -> str:
    """启动时打一行到控制台（也是三棵树一致性检查用的身份标识）。"""
    return f"{note_text()} · 作者：{author_text()} · {VERSION}"


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
