r"""Flet 版本兼容层。

Flet 0.23 起 ``Page.on_resize`` 被标记为过时（0.26 会删掉），官方推荐换成
``Page.window.on_resided``。但 ``page.window`` 是实例属性，手机端 / 网页端
不一定拿得到，所以这里做一层探测：

* 有 ``window.on_resided`` 就用新的；
* 没有才退回旧的 ``page.on_resize``，同时把这个弃用警告静音，
  免得控制台里刷一串黄色提示。

**每次挂新回调之前要把上一次的摘掉**：flet 0.23 的事件总线是
``self.__handlers[handler] = True``，按对象身份记账，``unsubscribe()`` 有实现
但没人调——而详情页每次都传一个新的 lambda 进来 subscribe，于是旧回调全留在
总线里。页面已经销毁了、回调里还在重建整棵控件树，学生每拖一下窗口就多一份
孤儿页面在跑。所以把当前生效的回调存在 ``page._gs_resize_handler`` 上，
下次挂之前先按它 unsubscribe。
"""

from __future__ import annotations

import warnings
from typing import Any, Callable

__all__ = ["set_resize_handler", "resize_backend"]

Handler = Callable[[Any], None]

_HANDLER_ATTR = "_gs_resize_handler"  # 记在 page 上：这个页面当前装着哪个回调


def resize_backend(page: Any) -> str:
    """当前 page 实际能用哪种缩放监听：``window`` / ``legacy`` / ``none``。"""
    event = getattr(getattr(page, "window", None), "on_resized", None)
    if event is not None and hasattr(event, "subscribe"):
        return "window"
    if hasattr(type(page), "on_resize"):
        return "legacy"
    return "none"


def _detach_previous(page: Any, backend: str) -> None:
    """摘掉这个 page 上一次挂上的缩放回调（没有就什么都不做）。

    假 Page（``tools/ui_smoke_test.py`` 里的 FakePage）不一定实现 ``unsubscribe``，
    所以这里全部按「有则调、没有就放过」处理，绝不抛异常。
    """
    previous = getattr(page, _HANDLER_ATTR, None)
    if previous is None:
        return
    try:
        if backend == "window":
            event = getattr(getattr(page, "window", None), "on_resized", None)
            unsubscribe = getattr(event, "unsubscribe", None)
            if callable(unsubscribe):
                unsubscribe(previous)
        elif backend == "legacy":
            # 旧 API 只是一个普通属性，置 None 就是取消订阅
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                page.on_resize = None
    except Exception:  # 兼容层的活是「能用就行」，别因为订阅总线版本差异把建页带崩
        pass
    try:
        setattr(page, _HANDLER_ATTR, None)
    except Exception:  # 某些代理对象不允许写属性
        pass


def set_resize_handler(page: Any, handler: Handler | None) -> str:
    """给页面挂上窗口缩放回调，返回实际生效的方式（见 :func:`resize_backend`）。

    同一个 page 反复调用（详情页每次切知识点都会重建并重挂）时，旧的先摘掉，
    不会在事件总线上越积越多。
    """
    backend = resize_backend(page)
    _detach_previous(page, backend)
    if backend == "window":
        if handler is not None:
            try:
                page.window.on_resized.subscribe(handler)
            except Exception:  # 订阅失败就当没挂上，页面照常构建
                return backend
            setattr(page, _HANDLER_ATTR, handler)
        return "window"
    if backend == "legacy":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            page.on_resize = handler
        if handler is not None:
            setattr(page, _HANDLER_ATTR, handler)
        return "legacy"
    return "none"
