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
#   GansuITExam.spec、requirements.txt、README.md
# —— 这些会跟着安装包一起发到学生手机上，没道理。
# assets\pyodide（12.8 MB）也排除了：安卓走 embedded（SeriousPython 内置
# CPython 3.11），backend_for_platform() 永远不会返回 pyodide，
# 代码仍然都在（core\mobile_runner.py、build_pyodide_script 没删），
# 只是不往安装包里塞这份跑不到的运行时（见 core\code_executor.py）。
$exclude = @(
    "tools", ".pytest_cache", "dist_onefile", "build_onefile",
    "GansuITExam.spec", "requirements.txt", "README.md",
    "assets/pyodide"
)
flet build apk --template $template --exclude @exclude
if ($LASTEXITCODE -ne 0) { throw "APK 构建失败" }

$apk = Join-Path $here "build\apk\app-release.apk"
Say "==> 完成" Green
Say "产物：$apk（$([math]::Round((Get-Item $apk).Length/1MB,1)) MB）" Yellow
Say "签名是 debug 证书，可直接安装，但不能上应用商店" Yellow
Say "上架前请把 android/app/build.gradle 里的 signingConfigs.debug 换成自己的 keystore" DarkGray

Pop-Location
