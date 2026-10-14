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
    print(f"合计：{info['modules']} 个模块 / {info['points']} 个知识点 / {info['questions']} 道可作答题")
    by_type = info.get("by_type") or {}
    if by_type:
        # 真卷是「单选 25 + 判断 5 + 填空 5 + 综合题」，所以题型分布值得单独报一行。
        # 注意这里 case 恒为 0：综合题自己不占答题位，已经摊平到它的小题上计数了。
        labels = {"choice": "单选", "judge": "判断", "fill": "填空", "case": "综合题"}
        print("      按题型：" + " / ".join(
            f"{labels.get(name, name)} {count}" for name, count in by_type.items()
        ))
    if info.get("cases"):
        print(f"      另有综合题 {info['cases']} 道（各含若干小题，已计入上面的题型统计）")
    print("-" * 56)
    for module in modules:
        print(f"[{module['id']}] {module['name']}  color={module['color']}")
        for point in module.get("points", []):
            code_lines = len(point.get("code_example", "").splitlines())
            hints = len(point.get("hints") or {})
            questions = point.get("questions", [])
            # 用摊平后的口径统计，和上面的总计保持一致；
            # 否则「练习 6 道」会和总题数对不上（综合题的小题没算进去）。
            answerable = store.answerable_questions(questions)
            cases = sum(1 for item in questions if store.question_type(item) == "case")
            kinds = {}
            for item in answerable:
                key = store.question_type(item)
                kinds[key] = kinds.get(key, 0) + 1
            kinds_text = "".join(
                f"{labels.get(name, name)}{count} " for name, count in sorted(kinds.items())
            ).strip()
            tail = f"，含综合题 {cases} 道" if cases else ""
            print(
                f"    - {point['id']} {point['title']}"
                f"  |  代码 {code_lines} 行 / 提示 {hints} 条 / 练习 {len(answerable)} 道"
                + (f"（{kinds_text}）" if kinds_text else "")
                + tail
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
