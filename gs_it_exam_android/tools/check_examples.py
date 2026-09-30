r"""把 JSON 里所有知识点的示例代码都跑一遍（Step 2 验收脚本）。

    python tools\check_examples.py

用途：确认沙箱既能安全运行真实教材代码，又没有被安全规则误伤。

结果分三类：
    OK    跑通了
    SKIP  依赖第三方库（如 pandas），沙箱有意不支持，跳过并说明原因
    ERR   真出错了，需要排查
退出码 0 表示没有 ERR。
"""

from __future__ import annotations

import ast
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


def main() -> int:
    passed = skipped = 0
    failed: list[str] = []

    for module in store.get_modules():
        print(f"[{module['id']}] {module['name']}")
        for point in module.get("points", []):
            code = point.get("code_example", "")
            title = point.get("title", "")
            modules, uses_input = analyse(code)
            outside = [name for name in modules if name not in security.SAFE_MODULES]

            if outside:
                skipped += 1
                print(f"    SKIP {point['id']} {title}  |  依赖 {'/'.join(outside)}，沙箱不支持")
                continue

            inputs = SAMPLE_INPUTS if uses_input else None
            result = executor.run_code(code, test_inputs=inputs, timeout=10.0)
            if result.success:
                passed += 1
                lines = result.output.strip().splitlines()[:1]
                preview = lines[0][:36] if lines else "(无输出)"
                tag = "已喂样例输入" if uses_input else "直接运行"
                print(f"    OK   {point['id']} {title}  |  {result.duration:.2f}s  |  {tag}  |  {preview}")
            else:
                failed.append(f"{point['id']} {title}")
                print(f"    ERR  {point['id']} {title}  |  {result.error_type}")
                print(f"         {result.error[:150]}")
    print("-" * 60)
    print(f"共 {passed + skipped + len(failed)} 段示例代码：跑通 {passed}，跳过 {skipped}，失败 {len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
