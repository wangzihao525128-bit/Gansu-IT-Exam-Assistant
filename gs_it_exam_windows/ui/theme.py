"""全局配色与样式（对应需求文档 4.3 配色方案），支持亮色 / 暗色切换。"""

from __future__ import annotations

PRIMARY = "#4A90E2"  # 导航栏、主按钮、高亮文本
DANGER = "#E74C3C"  # 错误提示、重要警告
SUCCESS = "#2ECC71"  # 运行成功、答案正确
WARNING = "#F39C12"  # 代码警告、注意事项
CODE_BG = "#2D2D2D"  # 代码编辑器深色背景

LIGHT: dict[str, str] = {
    "bg": "#F5F7FA",
    "card": "#FFFFFF",
    "text": "#2C3E50",
    "sub": "#7F8C8D",
    "border": "#E1E6EE",
}
DARK: dict[str, str] = {
    "bg": "#1E2229",
    "card": "#262B33",
    "text": "#ECF0F1",
    "sub": "#95A5A6",
    "border": "#333A45",
}

RADIUS = 14
GAP = 12

_mode = "light"


def colors() -> dict[str, str]:
    """当前配色；页面构建时取一次即可。"""
    return DARK if _mode == "dark" else LIGHT


def mode() -> str:
    return _mode


def set_mode(value: str) -> None:
    global _mode
    _mode = "dark" if value == "dark" else "light"


def toggle() -> str:
    """切换主题，返回切换后的模式名。"""
    set_mode("light" if _mode == "dark" else "dark")
    return _mode
