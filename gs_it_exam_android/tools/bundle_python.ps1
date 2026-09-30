# 把一份干净的 CPython 3.8+ 标准库复制到 app 的 runtime\ 目录，
# 让打包出来的 exe 自带代码运行环境——不依赖学生电脑里装没装 Python。
#
#   powershell -ExecutionPolicy Bypass -File tools\bundle_python.ps1 -Dest dist\gs_it_exam_windows
#
# 复制内容：python.exe + 主 DLL + DLLs\ + 标准库 Lib\（去掉 site-packages / 测试 / tkinter）
param(
    [Parameter(Mandatory = $true)][string]$Dest,
    [string]$Source = ""
)

$ErrorActionPreference = "Stop"

if (-not $Source) {
    $Source = Split-Path -Parent (Get-Command python -ErrorAction Stop).Source
}
$exe = Join-Path $Source "python.exe"
if (-not (Test-Path $exe)) { throw "没找到源解释器：$exe" }

$ver = (& $exe -c "import sys;print('%d.%d' % sys.version_info[:2])").Trim()
$parts = $ver.Split(".")
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 8)) {
    throw "源解释器是 $ver，低于要求的 3.8"
}

$runtime = Join-Path $Dest "runtime"
if (Test-Path $runtime) { Remove-Item -Recurse -Force $runtime }
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

Write-Output "源解释器：$Source（Python $ver）"
Write-Output "目标目录：$runtime"

# 1) 解释器本体 + 主 DLL + vcruntime
Get-ChildItem $Source -File |
    Where-Object { $_.Extension -in ".exe", ".dll" -and $_.BaseName -match "^(python|vcruntime|sqlite3)" } |
    Where-Object { $_.Name -ne "pythonw.exe" } |
    ForEach-Object { Copy-Item $_.FullName -Destination $runtime -Force }

# 2) 扩展模块 DLLs\
$srcDlls = Join-Path $Source "DLLs"
if (Test-Path $srcDlls) {
    Copy-Item $srcDlls -Destination $runtime -Recurse -Force
    foreach ($junk in @("test", "tkinter", "tcl", "libffi", "turtledemo")) {
        $p = Join-Path $runtime "DLLs\$junk"
        if (Test-Path $p) { Remove-Item -Recurse -Force $p -ErrorAction SilentlyContinue }
    }
}

# 3) 标准库 Lib\（去掉 site-packages、测试套件、GUI 这些占地方又用不上的）
$srcLib = Join-Path $Source "Lib"
$skipTop = @("site-packages", "test", "idlelib", "tkinter", "turtledemo", "lib2to3",
    "ensurepip", "venv", "__pycache__", "distutils")
$libDst = Join-Path $runtime "Lib"
New-Item -ItemType Directory -Force -Path $libDst | Out-Null

$copied = 0
foreach ($f in Get-ChildItem $srcLib -Recurse -File -Filter *.py) {
    $rel = $f.FullName.Substring($srcLib.Length + 1)
    $top = ($rel -split "\\")[0]
    if (($skipTop | Where-Object { $top -like $_ }).Count -gt 0) { continue }
    if ($rel -like "config-*") { continue }
    $target = Join-Path $libDst $rel
    $dir = Split-Path -Parent $target
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Copy-Item $f.FullName -Destination $target -Force
    $copied++
}
Write-Output "标准库 .py：$copied 个"

# 4) 版本标记，方便排查
Set-Content -Path (Join-Path $runtime "VERSION.txt") -Value "CPython $ver" -Encoding utf8

# 5) 自检：真跑一段代码，确认这个 runtime 能用
$check = "import random,math,datetime,string,collections,statistics,json;print('RUNTIME_OK')"
$out = & (Join-Path $runtime "python.exe") -I -S -c $check 2>&1
if ("$out" -notmatch "RUNTIME_OK") { throw "内置 runtime 自检失败：$out" }
$size = [math]::Round(((Get-ChildItem $runtime -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Output "内置 runtime 自检通过，总大小 $size MB"