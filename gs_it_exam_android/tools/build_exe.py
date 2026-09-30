r"""把应用打包成 Windows 桌面程序（dist\GansuITExam\GansuITExam.exe）。

为什么不直接用 `flet pack`：
    flet 0.23 的 `flet pack` 在生成 exe 版本资源（--version-file）时，用的是
    系统默认编码写文件。中文 Windows 上写出来是 GBK，而 PyInstaller 固定按
    UTF-8 读，于是报 UnicodeDecodeError 直接失败——中文产品名根本打不出来。
    这里自己写一份 UTF-8 的版本资源，再直接调 PyInstaller，绕开这个 bug。

用法（一般在 build_windows.ps1 里被调用，也可单独跑）：
    python tools\build_exe.py --dist dist
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_NAME = "GansuITExam"
PRODUCT_NAME = "甘肃省信息技术会考学习软件"
FILE_DESC = "甘肃省信息技术学业水平考试备考学习软件"
# 作者信息直接写进 exe 的版本资源：Windows「文件属性 → 详细信息」里
# 公司/版权/备注三处都能看到，改名字就得改 exe 资源或重新打包。
COMPANY = "王子豪"
COPYRIGHT = "Copyright (C) 2026 王子豪 · 保留所有权利"
COMMENTS = "作者：王子豪 · 本软件由 AI 协助制作 · MIT 开源（衍生作品需保留署名）"
PRODUCT_VERSION = "1.0.0"
FILE_VERSION = "1.0.0.0"

VERSION_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({f[0]}, {f[1]}, {f[2]}, {f[3]}),
    prodvers=({f[0]}, {f[1]}, {f[2]}, {f[3]}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [StringStruct('CompanyName', {company!r}),
         StringStruct('FileDescription', {desc!r}),
         StringStruct('FileVersion', {file_version!r}),
         StringStruct('InternalName', {internal!r}),
         StringStruct('LegalCopyright', {copyright!r}),
         StringStruct('OriginalFilename', {internal!r}.encode('ascii', 'replace').decode('ascii') + '.exe'),
         StringStruct('ProductName', {product!r}),
         StringStruct('ProductVersion', {product_version!r}),
         StringStruct('Comments', {comments!r})])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def write_version_file(dest: Path) -> Path:
    """写一份 UTF-8 的 exe 版本资源，中文产品名不会把 PyInstaller 撑爆。"""
    major, minor, build, patch = (int(part) for part in FILE_VERSION.split("."))
    text = VERSION_TEMPLATE.format(
        f=(major, minor, build, patch),
        company=COMPANY,
        desc=FILE_DESC,
        file_version=FILE_VERSION,
        internal=APP_NAME,
        copyright=COPYRIGHT,
        product=PRODUCT_NAME,
        product_version=PRODUCT_VERSION,
        comments=COMMENTS,
    )
    path = dest / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def find_powershell() -> str:
    """找一个可用的 PowerShell 来跑 bundle_python.ps1。

    原来这里写死 ``"pwsh"``：只装了 Windows PowerShell（5.1）的机器上会直接
    抛 ``FileNotFoundError: [WinError 2]``，而且是在**单文件版打包的最后一步**
    才炸——dist_onefile 里已经有个旧的 exe 躺在那里，很容易被误判成「打成功了」。
    所以优先 pwsh（7.x），没有就退回 powershell（5.1）。
    """
    for candidate in ("pwsh", "powershell"):
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError("找不到 PowerShell（pwsh / powershell 都没有），无法内置 Python 运行时")


def stage_bundle(here: Path, stage: Path) -> Path:
    """把 data / assets / plugins / runtime 摆到一个暂存目录里。

    单文件版必须在 PyInstaller 打包时就把内置 Python 塞进去（``--add-data``），
    因为 exe 旁边不会有 ``runtime/`` 这一层。所以先摆好，再交给 PyInstaller。
    """
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)

    data = here / "data" / "knowledge_points.json"
    if data.is_file():
        (stage / "data").mkdir(exist_ok=True)
        shutil.copy2(data, stage / "data" / "knowledge_points.json")
    icon = here / "assets" / "icon.png"
    if icon.is_file():
        (stage / "assets").mkdir(exist_ok=True)
        shutil.copy2(icon, stage / "assets" / "icon.png")
    plugins = here / "plugins"
    if plugins.is_dir():
        shutil.copytree(plugins, stage / "plugins")

    script = here / "tools" / "bundle_python.ps1"
    subprocess.run(
        [find_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Dest", str(stage)],
        check=True,
    )
    return stage


def build(distpath: Path, workpath: Path, skip_clean: bool, onefile: bool = False) -> int:
    import PyInstaller.__main__

    from flet.__pyinstaller import config as hook_config
    from flet.__pyinstaller.utils import copy_flet_bin

    here = Path(__file__).resolve().parent.parent
    os.chdir(here)

    for folder in (distpath, workpath):
        if folder.exists() and not skip_clean:
            shutil.rmtree(folder, ignore_errors=True)

    icon = here / "assets" / "icon.ico"
    if not icon.exists():
        from PIL import Image

        Image.open(here / "assets" / "icon.png").convert("RGBA").save(
            icon, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        )

    with tempfile.TemporaryDirectory(prefix="gsexam_pyi_") as tmp_raw:
        tmp = Path(tmp_raw)
        version_file = write_version_file(tmp)

        add_data: list[tuple[Path, str]] = []
        if onefile:
            # 单文件版：题库、图标、插件、内置 Python 全部进 exe
            stage = stage_bundle(here, tmp / "stage")
            for name in ("data", "assets", "plugins", "runtime"):
                src = stage / name
                if src.is_dir():
                    add_data.append((src, name))
        else:
            add_data.append((here / "data" / "knowledge_points.json", "data"))
            add_data.append((here / "assets" / "icon.png", "assets"))

        # 让 flet 的 PyInstaller hook 把预编译的 Flutter 客户端塞进 flet/bin
        hook_config.temp_bin_dir = copy_flet_bin()
        try:
            args = [
                "main.py",
                "--noconfirm",
                "--noconsole",
                "--name",
                APP_NAME,
                "--distpath",
                str(distpath),
                "--workpath",
                str(workpath),
                "--specpath",
                str(workpath),
                "--icon",
                str(icon),
                "--onefile" if onefile else "--onedir",
                "--version-file",
                str(version_file),
            ]
            for src, dest in add_data:
                args += ["--add-data", f"{src}{os.pathsep}{dest}"]
            print("PyInstaller 参数：", " ".join(args), flush=True)
            PyInstaller.__main__.run(args)
        finally:
            if hook_config.temp_bin_dir and os.path.isdir(hook_config.temp_bin_dir):
                shutil.rmtree(hook_config.temp_bin_dir, ignore_errors=True)
            hook_config.temp_bin_dir = None
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 Windows 桌面程序")
    parser.add_argument("--dist", default="dist", help="输出目录（默认 dist）")
    parser.add_argument("--work", default="build", help="中间目录（默认 build）")
    parser.add_argument("--keep", action="store_true", help="保留上次的中间产物")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="打成单文件 exe（题库/插件/内置 Python 全部塞进 exe，双击即用，不用带文件夹）",
    )
    options = parser.parse_args()
    here = Path(__file__).resolve().parent.parent
    return build(
        (here / options.dist).resolve(),
        (here / options.work).resolve(),
        options.keep,
        options.onefile,
    )


if __name__ == "__main__":
    sys.exit(main())
