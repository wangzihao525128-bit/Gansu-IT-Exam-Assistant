r"""去掉 APK 里已有的签名文件，好让 apksigner 用作者自己的密钥重新签。

    python tools\strip_apk_signature.py 输入.apk 输出.apk

为什么需要它：``flet build apk`` 打出来的包已经带 **Android Debug 签名**
（META-INF 里的 .RSA / .SF / MANIFEST.MF）。Debug 证书谁都能生成，
等于这个包没有身份，也上不了应用商店。要用作者自己的密钥重签，
就得先把旧的签名条目清掉，否则两套签名文件会打架（apksigner 会报错）。

只重写 zip 结构，不动任何内容；条目的压缩方式按原样保留，
所以之后 zipalign + apksigner 的结果和正常发布流程一致。
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

# v1 签名（JAR 签名）会在 META-INF 下留这些文件
_SIG_NAMES = ("MANIFEST.MF",)
_SIG_SUFFIXES = (".RSA", ".DSA", ".EC", ".SF")


def is_signature_entry(name: str) -> bool:
    top, _, rest = name.partition("/")
    if top != "META-INF" or not rest:
        return False
    upper = rest.upper()
    return upper in _SIG_NAMES or upper.endswith(_SIG_SUFFIXES)


def main() -> int:
    if len(sys.argv) != 3:
        print("用法：python tools\\strip_apk_signature.py 输入.apk 输出.apk")
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        print(f"找不到输入 APK：{src}")
        return 1

    removed = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if is_signature_entry(item.filename):
                removed += 1
                continue
            zout.writestr(item, zin.read(item.filename))
    print(f"去掉 {removed} 个旧签名条目 -> {dst.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
