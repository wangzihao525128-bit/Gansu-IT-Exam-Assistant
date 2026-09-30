# Windows 桌面端一键打包脚本
#
#   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
#
# 产出：dist\GansuITExam\GansuITExam.exe
# 这个目录是「绿色版」——整个文件夹拷到任何一台没装 Python 的电脑上
# 双击就能用，代码运行窗口自带 CPython 3.11（>= 3.8）。
param(
    [string]$Python = "",
    [switch]$SkipRuntime,
    # 码掉重复 DLL 和用不到的库（libmpv / tcl / tk / pydoc_data），省约 61.7 MB。
    # 默认开启；万一将来用到了视频或 tkinter，用 -TrimDeadWeight:$false 关掉。
    [switch]$TrimDeadWeight = $true,
    # 单文件版：题库/图标/插件/内置 Python 全塞进一个 exe，双击即用。
    # 代价是每次启动都要先解包到 %%TEMP%%，会比文件夹版慢（实测数据见 完善\文档）。
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

# 控制台以 UTF-8 输出，否则重定向时中文会乱码
chcp 65001 > $null 2>&1
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8


$name = "GansuITExam"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }

Say "==> 1/5 清理上次的构建产物" Cyan
$cleanDirs = if ($OneFile) { @("build_onefile", "dist_onefile") } else { @("build", "dist") }
foreach ($d in $cleanDirs) {
    if (Test-Path $d) { Get-ChildItem $d -Recurse -File | Remove-Item -Force -ErrorAction SilentlyContinue }
}

Say "==> 2/5 自检（数据 / 沙箱 / 示例代码）" Cyan
$env:PYTHONIOENCODING = "utf-8"
python tools\check_data.py
if ($LASTEXITCODE -ne 0) { throw "数据自检没过，停止打包" }

Say "==> 3/5 用 PyInstaller 打包界面程序" Cyan
# 注意：这里没用 `flet pack`——它在中文 Windows 上写 exe 版本资源会用 GBK，
# PyInstaller 按 UTF-8 读会直接崩。tools\build_exe.py 自己写 UTF-8 版本资源绕开这个 bug。
# 单文件版输出到 dist_onefile\，和文件夹绿色版（dist\GansuITExam\）分开，
# 否则第 1 步「清理 dist」会把对方连同产物一起删掉。
if ($OneFile) {
    python tools\build_exe.py --dist dist_onefile --work build_onefile --onefile
} else {
    python tools\build_exe.py --dist dist --work build
}
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

$appDir = Join-Path $here "dist\$name"
if (-not (Test-Path $appDir)) { $appDir = Join-Path $here "dist\$name\dist" }

if ($OneFile) {
    # 单文件版：题库 / 图标 / 插件 / 内置 Python 已经在打包时进 exe 了，
    # 不能再往 dist\GansuITExam 旁边堆东西——那个文件夹里只有 exe 一个文件。
    Say "==> 4/5 单文件版：跳过数据搬运（题库/插件/内置 Python 都已封进 exe）" Cyan
    Pop-Location
    $oneExe = Join-Path $here "dist_onefile\GansuITExam.exe"
    if (-not (Test-Path $oneExe)) { throw "没找到 exe：$oneExe" }
    $oneSize = [math]::Round((Get-Item $oneExe).Length / 1MB, 1)
    Say "" ; Say "打包完成 ✓（单文件版）" Green
    Say "  程序    : $oneExe"
    Say "  大小    : $oneSize MB"
    Say "  使用    : 直接双击这一个 exe 就行，不用带别的文件" Cyan
    Say "  题库    : 解包后 data\knowledge_points.json（只读；换题库请用文件夹绿色版）" DarkGray
    Say "  注意    : 每次启动会先解包到 %%TEMP%%，比文件夹版慢几秒" DarkGray
    return
}

Say "==> 4/5 放置数据文件与插件目录（老师可直接改 JSON 换题库、往 plugins\ 丢插件）" Cyan
New-Item -ItemType Directory -Force -Path (Join-Path $appDir "data") | Out-Null
Copy-Item "data\knowledge_points.json" (Join-Path $appDir "data\knowledge_points.json") -Force
New-Item -ItemType Directory -Force -Path (Join-Path $appDir "assets") | Out-Null
Copy-Item "assets\icon.png" (Join-Path $appDir "assets\icon.png") -Force

# 需求文档 8.4：插件接口。目录里现在只有一份说明文件，等于「一个插件都没装」，
# 软件行为和没这个接口时一模一样；老师想加扩展，往 exe 旁边的 plugins\ 里丢子目录即可。
$pluginSrc = Join-Path $here "plugins"
if (Test-Path $pluginSrc) {
    $pluginDst = Join-Path $appDir "plugins"
    New-Item -ItemType Directory -Force -Path $pluginDst | Out-Null
    Get-ChildItem $pluginSrc -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($pluginSrc.Length + 1)
        $to = Join-Path $pluginDst $rel
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $to) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $to -Force
    }
    $pluginCount = (Get-ChildItem $pluginSrc -Recurse -Filter "plugin.py" -File).Count
    Say "        插件目录就位（其中 $pluginCount 个插件）" DarkGray
} else {
    Say "        没找到 plugins\ 源目录，跳过" Yellow
}

# --- 砍死重量 --------------------------------------------------------------
# 这里是实测出来的，不是拍脑袋。原始 dist 是 276.2 MB，其中两大块是纯重复：
#
#   _internal\ 顶层和 _internal\flet\bin\flet\ 里躺着一模一样的两套 DLL。
#   真正被加载的是 flet\bin\flet\ 那套——flet.exe 只存在于那一个目录，
#   而 Windows 加载 DLL 优先找 exe 所在目录。顶层那份是 PyInstaller 扫依赖时
#   顺手收进来的第二份副本，删掉不影响运行（实测走查全绿，见 完善\自检记录.md）。
#
#   libmpv-2.dll            28.4 MB  视频解码器，全项目 grep Video 零命中
#   flutter_windows.dll     17.3 MB  Flutter 引擎（副本）
#   libGLESv2.dll            7.1 MB  OpenGL（副本）
#   rive_common_plugin.dll   1.3 MB  Rive 动画运行时（副本）
#   ucrtbased.dll            2.1 MB  调试版 UCRT，发行版 Python 根本不加载
#   *_windows_plugin.dll     0.8 MB  11 个 Flutter 插件（副本）
#
#   刻意保留：ucrtbase / MSVCP140 / vcruntime140 / api-ms-win-* / libcrypto-3 /
#   libssl-3 —— 这些是 Python 那一侧要用的，不属于 Flutter 客户端，删了会起不来。
#
# 另砍内置 Python 里确定用不到的 Tcl/Tk 和 pydoc 帮助文本（约 4 MB）。
# 合计省 61.7 MB：276.2 MB -> 214.4 MB。
if ($TrimDeadWeight) {
    Say "==> 4.5/5 砍掉重复副本和用不到的库（约 57.8 MB）" Cyan
    $dead = @(
        @{ Path = "_internal\libmpv-2.dll";                          MB = 28.4 },
        @{ Path = "_internal\flutter_windows.dll";                   MB = 17.3 },
        @{ Path = "_internal\libGLESv2.dll";                         MB = 7.1 },
        @{ Path = "_internal\ucrtbased.dll";                         MB = 2.1 },
        @{ Path = "_internal\rive_common_plugin.dll";                MB = 1.3 },
        @{ Path = "_internal\libEGL.dll";                            MB = 0.5 },
        @{ Path = "_internal\audioplayers_windows_plugin.dll";        MB = 0.2 },
        @{ Path = "_internal\geolocator_windows_plugin.dll";          MB = 0.1 },
        @{ Path = "_internal\media_kit_libs_windows_video_plugin.dll"; MB = 0.0 },
        @{ Path = "_internal\media_kit_video_plugin.dll";             MB = 0.1 },
        @{ Path = "_internal\permission_handler_windows_plugin.dll";  MB = 0.1 },
        @{ Path = "_internal\record_windows_plugin.dll";              MB = 0.1 },
        @{ Path = "_internal\screen_brightness_windows_plugin.dll";   MB = 0.1 },
        @{ Path = "_internal\screen_retriever_plugin.dll";            MB = 0.1 },
        @{ Path = "_internal\url_launcher_windows_plugin.dll";        MB = 0.1 },
        @{ Path = "_internal\window_manager_plugin.dll";              MB = 0.1 },
        @{ Path = "_internal\window_to_front_plugin.dll";             MB = 0.1 }
    )
    $freed = 0.0
    $missed = 0
    foreach ($d in $dead) {
        $full = Join-Path $appDir $d.Path
        if (Test-Path -LiteralPath $full) {
            $item = Get-Item -LiteralPath $full
            if ($item.PSIsContainer) {
                $mb = ((Get-ChildItem -LiteralPath $full -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
                [System.IO.Directory]::Delete($full, $true)
            } else {
                $mb = $item.Length / 1MB
                Remove-Item -LiteralPath $full -Force
            }
            $freed += $mb
        } else {
            $missed++
        }
    }
    Say "        共省 $([math]::Round($freed,1)) MB" Green
    if ($missed -gt 0) { Say "        （$missed 项本轮构建里不存在，正常）" DarkGray }
} else {
    Say "==> 4.5/5 跳过裁剪（-TrimDeadWeight 没开）" Yellow
}

if (-not $SkipRuntime) {
    Say "==> 5/5 内置 Python 运行时（代码运行窗口要用）" Cyan
    # 用哪个 PowerShell 执行子脚本：优先 pwsh（7.x），没有就退回 powershell（5.1）。
    # 原来写死 `& pwsh ...`，在只装了 Windows PowerShell 的机器上会直接
    # 「无法将"pwsh"识别为 cmdlet」，而且是在打包的最后一步炸——
    # 前面 dist\ 已经生成好了，很容易被误当成「打成功了、只是少了个提示」。
    $psHost = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
    & $psHost -NoProfile -ExecutionPolicy Bypass -File "tools\bundle_python.ps1" -Dest $appDir
    if ($LASTEXITCODE -ne 0) { throw "内置 Python 打包失败" }
} else {
    Say "==> 5/5 跳过内置 Python（-SkipRuntime）" Yellow
}

# runtime 是第 5 步才放进来的，所以它里面用不到的东西必须排在第 5 步之后砍。
# 早一步跑的时候 runtime 目录还不存在，那几条会静默跳过（等于白写）。
if ($TrimDeadWeight -and -not $SkipRuntime) {
    Say "==> 5.5/5 砍掉内置 Python 里用不到的东西（约 4 MB）" Cyan
    $rtDead = @(
        @{ Path = "runtime\DLLs\tcl86t.dll"; MB = 1.8 },
        @{ Path = "runtime\DLLs\tk86t.dll";  MB = 1.5 },
        @{ Path = "runtime\Lib\pydoc_data";  MB = 0.7 }
    )
    $rtFreed = 0.0
    foreach ($d in $rtDead) {
        $full = Join-Path $appDir $d.Path
        if (-not (Test-Path -LiteralPath $full)) { continue }
        $item = Get-Item -LiteralPath $full
        if ($item.PSIsContainer) {
            $mb = ((Get-ChildItem -LiteralPath $full -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
            Remove-Item -LiteralPath $full -Recurse -Force
        } else {
            $mb = $item.Length / 1MB
            Remove-Item -LiteralPath $full -Force
        }
        $rtFreed += $mb
    }
    Say "        共省 $([math]::Round($rtFreed,1)) MB" Green
}
$exe = Join-Path $appDir "$name.exe"
if (-not (Test-Path $exe)) { throw "没找到 exe：$exe" }
$size = [math]::Round(((Get-ChildItem $appDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Say ""
Say "打包完成 ✓" Green
Say "  程序    : $exe"
Say "  总大小  : $size MB"
Say "  内置Py  : $(if (Test-Path (Join-Path $appDir 'runtime\python.exe')) { (Get-Content (Join-Path $appDir 'runtime\VERSION.txt')) } else { '未内置' })"
Say "  题库    : $(Join-Path $appDir 'data\knowledge_points.json')"
Say "  插件    : $(Join-Path $appDir 'plugins')  (丢子目录进去即可扩展，不用重打包)"
Say "  使用    : 把整个 $name 文件夹拷走，双击 exe 即可" Cyan
Pop-Location
