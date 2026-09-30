r"""数据自检脚本：不需要安装 flet，直接运行即可。

    python tools/check_data.py

它会打印模块 / 知识点 / 练习题统计，并校验 JSON 结构是否完整。
退出码 0 表示数据没问题，1 表示有问题。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import knowledge_store as store  # noqa: E402


def main() -> int:
    print("=" * 56)
    print("知识点数据自检")
    print("=" * 56)
    modules = store.load(force=True)
    info = store.stats()
    print(f"数据文件：{store.DATA_FILE}")
    print(f"合计：{info['modules']} 个模块 / {info['points']} 个知识点 / {info['questions']} 道练习题")
    print("-" * 56)
    for module in modules:
        print(f"[{module['id']}] {module['name']}  color={module['color']}")
        for point in module.get("points", []):
            code_lines = len(point.get("code_example", "").splitlines())
            hints = len(point.get("hints") or {})
            questions = len(point.get("questions", []))
            print(
                f"    - {point['id']} {point['title']}"
                f"  |  代码 {code_lines} 行 / 提示 {hints} 条 / 练习 {questions} 道"
            )
    print("-" * 56)
    problems = store.validate()
    if problems:
        print(f"发现 {len(problems)} 处数据问题：")
        for problem in problems:
            print("  !", problem)
        return 1
    print("数据结构检查通过，没有发现问题。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
