# Android 打包脚本（一键重建 APK）
#
#   powershell -ExecutionPolicy Bypass -File .\build_android.ps1
#
# 产物：build\apk\app-release.apk（约 89 MB，含内置 Python 3.11 运行时）
#
# 本机已验证可直接跑通。三个环境变量是关键，不能删：
#   FLUTTER_STORAGE_BASE_URL / PUB_HOSTED_URL  —— Flutter 官方源在国内不通，改用官方中国镜像
#   SERIOUS_PYTHON_BUILD_DIST                 —— 让 serious_python 用本地原生库，绕开 github.com
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# 控制台以 UTF-8 输出，否则重定向时中文会乱码
chcp 65001 > $null 2>&1
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8


$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }

# ---- 工具链路径（本机实测可用）----
$env:JAVA_HOME           = "D:\tools\jdk-17.0.13+11"
$env:FLUTTER_ROOT        = "D:\tools\flutter"
$env:ANDROID_SDK_ROOT    = "D:\tools\android-sdk"
$env:ANDROID_HOME        = "D:\tools\android-sdk"
$env:FLUTTER_STORAGE_BASE_URL = "https://storage.flutter-io.cn"
$env:PUB_HOSTED_URL           = "https://pub.flutter-io.cn"
$env:PYTHONIOENCODING    = "utf-8"
$env:PATH = "$env:FLUTTER_ROOT\bin;$env:JAVA_HOME\bin;" + $env:PATH

# ---- serious_python 的 Python Android 原生库（本地，不走 github.com）----
$spDist = "D:\tools\sp-python-android-dist"
if (Test-Path $spDist) {
    $env:SERIOUS_PYTHON_BUILD_DIST = $spDist
    Say "使用本地 Python 原生库：$spDist" DarkGray
} else {
    Say "未找到本地原生库，将尝试从 github.com 下载（本机不通，会失败）" Yellow
}

# ---- 离线 cookiecutter 模板（含钉死的插件版本 + FLUTTER_ROOT 兜底）----
$template = "D:\tools\flet-cc-template"
if (-not (Test-Path $template)) {
    throw "找不到离线模板 $template"
}

if ($Clean) {
    Say "==> 清理上次产物" Cyan
    foreach ($d in @("build", ".dart_tool")) {
        if (Test-Path $d) { [System.IO.Directory]::Delete((Join-Path $here $d), $true) }
    }
    # 不要把 __pycache__ / .pyc 打进包里
    Get-ChildItem $here -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { [System.IO.Directory]::Delete($_.FullName, $true) }
    Get-ChildItem $here -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
        ForEach-Object { [System.IO.File]::Delete($_.FullName) }
}

Say "==> 1/2 自检（数据 / 沙箱 / 示例代码）" Cyan
python tools\check_data.py;      if ($LASTEXITCODE -ne 0) { throw "数据自检没过" }
python tools\test_sandbox.py;    if ($LASTEXITCODE -ne 0) { throw "沙箱单测没过" }
python tools\check_examples.py;  if ($LASTEXITCODE -ne 0) { throw "示例代码自检没过" }

Say "==> 2/2 打 Gradle 包" Cyan
& "$env:FLUTTER_ROOT\bin\flutter.bat" --version | Select-Object -First 1

# 只把「应用本身」（core\ ui\ data\ assets\图标 main.py）打进 APK，开发用的东西一律排除。
# 之前是整个工程目录原样塞进 app.zip：实测成品 APK 的
# assets\flutter_assets\app\app.zip 里有 2467 个条目，其中带着
#   tools\（8 项，含 build_exe.pyc）、.pytest_cache\、dist_onefile\、
#   GansuITExam.spec、requirements.txt、README.md、build_android.ps1
# —— 这些会跟着安装包一起发到学生手机上，没道理。
# 加完这些之后 app.zip 从 26.9 MB 降到 19.2 MB。
$exclude = @(
    "tools", ".pytest_cache", "dist_onefile", "build_onefile",
    "GansuITExam.spec", "requirements.txt", "README.md",
    "build_android.ps1", "__pycache__"
)

# assets\pyodide（12.8 MB，已经压缩过的 wasm/zip，压缩不了多少）不用发到手机上：
# 安卓走 embedded（SeriousPython 内置 CPython 3.11），backend_for_platform()
# 永远不会返回 pyodide，代码仍然都在（core\mobile_runner.py、build_pyodide_script
# 没删），只是这份离线 Pyodide 在安卓端跑不到（见 core\code_executor.py）。
# **它不能靠 --exclude 排掉**：flet 的 --exclude 只认工程根目录下的名字，
# 写 "assets/pyodide" 这种嵌套路径实测不生效（打包结果里那 14 个条目还在）。
# 所以打包前先把它挪出工程目录，打完再挪回来；用 try/finally 保证一定还原，
# 中途失败也不会把源码弄丢。
$pyodideDir = Join-Path $here "assets\pyodide"
$pyodideStash = Join-Path $env:TEMP ("gs_pyodide_stash_" + [guid]::NewGuid().ToString("N"))

# 自愈：上一次构建如果被强杀（Ctrl+C / 工具超时 / 关机），源码里的 assets\pyodide
# 会被留在临时暂存目录里回不来。**本脚本真被这样坑过一次**：源码树悄悄少了 12.8 MB 资源，
# 直到下次打包才发现。所以开工前先找回来；找不到就明确报错，不许带着缺件打包。
if (-not (Test-Path -LiteralPath $pyodideDir)) {
    $leftover = Get-ChildItem $env:TEMP -Directory -Filter "gs_pyodide_stash_*" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($leftover) {
        Move-Item -LiteralPath $leftover.FullName -Destination $pyodideDir -Force
        Say "  上次构建被中断，已从临时目录找回 assets\pyodide" Yellow
    } else {
        throw "assets\pyodide 不见了，临时目录里也没有暂存。先恢复它：git checkout -- gs_it_exam_android/assets/pyodide"
    }
}
$pyodideMoved = $false
try {
    if (Test-Path -LiteralPath $pyodideDir) {
        Move-Item -LiteralPath $pyodideDir -Destination $pyodideStash -Force
        $pyodideMoved = $true
        Say "  已临时移出 assets\pyodide（12.8 MB，安卓端用不到）" DarkGray
    }
    # --company / --copyright：把作者信息写进包的应用信息里
    # --flutter-build-args：Dart 层混淆（--obfuscate 改名；--split-debug-info 把符号表另存）
    # 写法注意：必须用 `--flutter-build-args=--obfuscate` 这种**等号**形式。
    # flet 这个参数是 nargs="*"：用空格分隔时 argparse 会把 --obfuscate 当成
    # flet 自己的参数，直接报 "unrecognized arguments"（实测踩过）。
    # 符号表目录必须是**纯 ASCII 路径**：本工程在 D:\桌面\... 下，Dart 的快照生成器
    # 写中文路径会失败（"Unable to write file: ...\build\symbols\app.android-arm.symbols"，
    # 实测踩过），所以固定放 D:\gs_it_exam_symbols。这个目录要长期留着
    # （将来还原混淆后的崩溃堆栈靠它），但**不要随安装包发出去**。
    $symbolsDir = "D:\gs_it_exam_symbols"
    if (-not (Test-Path $symbolsDir)) { New-Item -ItemType Directory -Force -Path $symbolsDir | Out-Null }
    flet build apk --template $template --exclude @exclude `
        --company "王子豪" --copyright "Copyright (C) 2026 王子豪 · MIT 开源，衍生作品请保留署名" `
        "--flutter-build-args=--obfuscate" "--flutter-build-args=--split-debug-info=$symbolsDir"
    $buildExit = $LASTEXITCODE
} finally {
    if ($pyodideMoved -and (Test-Path -LiteralPath $pyodideStash)) {
        Move-Item -LiteralPath $pyodideStash -Destination $pyodideDir -Force
        Say "  已还原 assets\pyodide" DarkGray
    }
}
if ($buildExit -ne 0) { throw "APK 构建失败" }

# ---- 用作者自己的密钥重新签名（这是 APK 上最实质的一层身份）----
# flet 默认签的是 Android Debug 证书：谁都能生成、看不出作者是谁、也上不了应用商店。
# 换成作者本人的密钥之后：
#   * `apksigner verify --print-certs` 里能看到 CN=作者名，任何人都能核对；
#   * 没有这份私钥的人伪造不了签名，也不能给这个包名推"官方更新"；
#   * 密钥库在 签名密钥\ 目录（已加进 .gitignore，**绝不能提交到 GitHub**）。
$ks = Join-Path (Split-Path -Parent $PSScriptRoot) "签名密钥\gs_it_exam.jks"
if (-not (Test-Path -LiteralPath $ks)) { $ks = "D:\桌面\工作区\学考\签名密钥\gs_it_exam.jks" }
$apk = Join-Path $here "build\apk\app-release.apk"
if (Test-Path -LiteralPath $ks) {
    Say "==> 用作者密钥重新签名" Cyan
    $btRoot = "D:\tools\android-sdk\build-tools"
    $bt = Get-ChildItem $btRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $bt) { throw "找不到 Android build-tools（zipalign / apksigner）" }
    $zipalign = Join-Path $bt.FullName "zipalign.exe"
    $apksigner = Join-Path $bt.FullName "apksigner.bat"
    $stripped = Join-Path $here "build\apk\app-release-unsigned.apk"
    $aligned = Join-Path $here "build\apk\app-release-aligned.apk"
    $signed = Join-Path $here "build\apk\app-release-signed.apk"
    $storePass = "（口令已作废并移除，请用环境变量 GS_KS_PASS）"

    python tools\strip_apk_signature.py $apk $stripped; if ($LASTEXITCODE -ne 0) { throw "去掉旧签名失败" }
    & $zipalign -p -f 4 $stripped $aligned;           if ($LASTEXITCODE -ne 0) { throw "zipalign 失败" }
    & $apksigner sign --ks $ks --ks-key-alias gsitexam --ks-pass "pass:$storePass" --key-pass "pass:$storePass" `
        --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --out $signed $aligned
    if ($LASTEXITCODE -ne 0) { throw "签名失败" }
    Copy-Item -LiteralPath $signed -Destination $apk -Force
    Remove-Item -LiteralPath $stripped, $aligned, $signed -Force -ErrorAction SilentlyContinue
    Say "  签名证书：" DarkGray
    & $apksigner verify --print-certs $apk 2>&1 | Select-String -Pattern 'Signer #1 certificate DN|SHA-256 digest' | Select-Object -First 2 | ForEach-Object { Say ("    " + $_.Line.Trim()) DarkGray }
} else {
    Say "==> 没找到签名密钥，APK 仍是 debug 签名（不能上架，也体现不出作者身份）" Yellow
}

$apk = Join-Path $here "build\apk\app-release.apk"
Say "==> 完成" Green
Say "产物：$apk（$([math]::Round((Get-Item $apk).Length/1MB,1)) MB）" Yellow
if (Test-Path -LiteralPath $ks) {
    Say "签名：作者本人密钥（Certificate DN 里是作者名，见上面的 verify 输出）" Green
    Say "上架前可换成同一个密钥库的正式 alias；密钥库和口令必须自己备份好，丢了就再也发不了更新" DarkGray
} else {
    Say "签名：debug 证书（能装、不能上架，也体现不出作者身份）" Yellow
}

Pop-Location
