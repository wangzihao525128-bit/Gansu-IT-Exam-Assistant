r"""把 JSON 里所有知识点的示例代码都跑一遍（Step 2 验收脚本）。

    python tools\check_examples.py             # 跑 + 比对期望输出
    python tools\check_examples.py --update     # 重新记录期望输出（人工确认后再用）

用途：确认沙箱既能安全运行真实教材代码、没有被安全规则误伤，
**而且算出来的结果是对的**——只判「跑通了」是不够的：
示例代码把 `a + b` 写成 `a - b` 照样能跑通，学生照着学会的东西就是错的。

结果分五类：
    OK      跑通且输出与期望一致
    OUT-x   跑通了但输出和期望不一致（这才是真问题，会算作失败）
    NOEXP   跑通了但快照里还没有它的期望输出（提示用 --update 记录）
    SKIP    依赖第三方库（如 pandas），沙箱有意不支持，跳过并说明原因
    ERR     真出错了，需要排查
退出码 0 表示没有 ERR / OUT-x / NOEXP。

期望输出存在同目录的 ``expected_example_outputs.json``：
键是知识点 id，值是运行时的标准输出（已 strip）。用 ``random`` / ``time`` /
``datetime`` 的示例输出不确定，脚本会跳过它们的比对（只判跑通），
不会把它们写进快照，免得每次运行都「失败」。
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import code_executor as executor  # noqa: E402
from core import knowledge_store as store  # noqa: E402
from core import security  # noqa: E402

# 教材里用到 input() 的示例，喂它一串通用样例数据（顺带验证 input 注入功能）。
# 开头先给 1~20：像 2_4「猜数字游戏」那种 random + while 的示例，
# 只有猜到 1~10 之间的数才会结束，缺一个数就会一直读到输入耗尽。
SAMPLE_INPUTS = [str(n) for n in range(1, 21)] + [
    "85", "92", "78", "88", "60", "45", "70", "95", "55", "0",
    "100", "65", "abc", "hello", "3.5", "2024",
]

# 输出不确定的模块：用了它们的示例只判「跑通」，不比对内容
NONDETERMINISTIC_MODULES = {"random", "time", "datetime"}

EXPECTED_FILE = Path(__file__).resolve().parent / "expected_example_outputs.json"


def analyse(code: str) -> tuple[list[str], bool]:
    """看这段代码用了哪些模块、要不要 input。"""
    tree = ast.parse(code)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    uses_input = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input"
        for node in ast.walk(tree)
    )
    return sorted(modules), uses_input


def load_expected() -> dict[str, str]:
    if not EXPECTED_FILE.exists():
        return {}
    try:
        data = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    except Exception as error:  # 快照本身坏了要说清楚，不能当没有
        print(f"! 期望输出快照读不出来（{error}），本次只判跑通。用 --update 重建。")
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_expected(records: dict[str, str]) -> None:
    EXPECTED_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def show_diff(expected: str, got: str, limit: int = 6) -> None:
    """把不一致的地方按行打出来，最多 limit 行——比「不一致」三个字有用得多。"""
    exp_lines, got_lines = expected.splitlines(), got.splitlines()
    for index in range(max(len(exp_lines), len(got_lines))):
        want = exp_lines[index] if index < len(exp_lines) else "<无此行>"
        have = got_lines[index] if index < len(got_lines) else "<无此行>"
        if want != have:
            print(f"         第 {index + 1} 行  期望: {want}")
            print(f"         第 {index + 1} 行  实际: {have}")
            limit -= 1
            if limit <= 0:
                print("         ……（后面还有）")
                break


def main() -> int:
    update = "--update" in sys.argv
    expected = load_expected()
    recorded: dict[str, str] = {}

    passed = skipped = nondet = 0
    mismatched: list[str] = []
    missing: list[str] = []
    failed: list[str] = []

    for module in store.get_modules():
        print(f"[{module['id']}] {module['name']}")
        for point in module.get("points", []):
            code = point.get("code_example", "")
            title = point.get("title", "")
            point_id = str(point.get("id", ""))
            modules, uses_input = analyse(code)
            outside = [name for name in modules if name not in security.SAFE_MODULES]

            if outside:
                skipped += 1
                print(f"    SKIP {point_id} {title}  |  依赖 {'/'.join(outside)}，沙箱不支持")
                continue

            inputs = SAMPLE_INPUTS if uses_input else None
            result = executor.run_code(code, test_inputs=inputs, timeout=10.0)
            if not result.success:
                failed.append(f"{point_id} {title}")
                print(f"    ERR  {point_id} {title}  |  {result.error_type}")
                print(f"         {result.error[:150]}")
                continue

            got = result.output.strip()
            tag = "已喂样例输入" if uses_input else "直接运行"
            nondeterministic = bool(set(modules) & NONDETERMINISTIC_MODULES)

            if nondeterministic:
                nondet += 1
                first = got.splitlines()[0][:36] if got else "(无输出)"
                print(f"    OK   {point_id} {title}  |  {result.duration:.2f}s  |  {tag}"
                      f"  |  输出含随机/时间，只判跑通  |  {first}")
                continue

            recorded[point_id] = got
            if point_id not in expected:
                missing.append(f"{point_id} {title}")
                print(f"    NOEXP {point_id} {title}  |  跑通了，但快照里还没有它的期望输出")
                continue

            if expected[point_id] != got:
                mismatched.append(f"{point_id} {title}")
                print(f"    OUT-x {point_id} {title}  |  跑通了，但输出和期望不一致：")
                show_diff(expected[point_id], got)
                continue

            passed += 1
            first = got.splitlines()[0][:36] if got else "(无输出)"
            print(f"    OK   {point_id} {title}  |  {result.duration:.2f}s  |  {tag}"
                  f"  |  输出与期望一致  |  {first}")

    if update:
        save_expected(recorded)
        print("-" * 60)
        print(f"已重新记录期望输出：{len(recorded)} 段 → {EXPECTED_FILE.name}")
        print("（请人眼确认这些输出是对的，再提交；否则等于把错误答案钉成标准答案）")
        return 0

    print("-" * 60)
    total = passed + nondet + skipped + len(failed) + len(mismatched) + len(missing)
    print(
        f"共 {total} 段示例代码：输出一致 {passed}，随机/时间 {nondet}，"
        f"跳过 {skipped}，输出不一致 {len(mismatched)}，未记录 {len(missing)}，出错 {len(failed)}"
    )
    if mismatched or missing or failed:
        print("处理办法：确认示例代码是对的，就用 --update 重新记录；"
              "示例算错了，就改 data\\knowledge_points.json。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
