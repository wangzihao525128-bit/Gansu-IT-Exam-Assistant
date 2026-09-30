# 甘肃省信息技术会考学习 · Android 版

与 Windows 版共用同一套 Python 代码（`main.py` / `core/` / `ui/` / `data/` 完全一致），
差别只在**打包方式**和**代码执行引擎**。

## 与 Windows 版的关键差异

| 项目 | Windows 桌面版 | Android 版 |
| --- | --- | --- |
| 打包 | `flet pack`（PyInstaller） | `flet build apk`（Flutter + Gradle） |
| 运行 Python 代码 | `subprocess` 子进程沙箱 | **Pyodide**（WebView 里的 CPython/WASM） |
| 布局 | 25% / 45% / 30% 三栏 | **整页滚动 + 区块按内容自然高度**（原先 40/30/30 硬压会把运行结果挤没） |
| 构建机器 | 任意 Windows | 任意系统（含 Windows） |

手机系统里没有 Python 解释器，也开不了子进程，所以 `core/code_executor.py` 在手机端走 Pyodide。

**实际实现和最初设想不一样**：最初想「生成 JS 丢给 WebView」，
但 **flet 0.23 没有 `page.run_js`**，拿不到直接执行 JS 的能力。
所以改成 `core/mobile_runner.py` 的**本地 HTTP 桥**：

```python
# Python 端起 127.0.0.1 小 HTTP 服务（后台线程 + 随机 token 路径）
# WebView 加载桥页面 → 页面轮询 /task 拿代码 → Pyodide 跑 → POST /result 回传
from core import mobile_runner
url = mobile_runner.start()          # 返回给 ft.WebView(url=...)
result = mobile_runner.run(code, ["21", "35"], timeout=30.0)
```

桌面端走 `subprocess` 沙箱（`python -I -S` + 5 秒超时），
两边返回的都是同一个 `RunResult`，UI 代码不用分平台写。
WebView 控件已用 flet 0.23 内置的 `ft.WebView` 实现（不需要 `flet-webview` 插件）。

**Pyodide 完全离线**：默认 CDN `cdn.jsdelivr.net` 国内不通，
改为把 `pyodide@0.25.0` 的核心 13 个文件（12.2 MB）放在
`assets\pyodide\package\`，**断网也能跑代码**（校机房场景）。

## 打包前置条件

1. Python 3.8+ 与本目录的依赖：`pip install -r requirements.txt`
2. [Flutter SDK](https://docs.flutter.dev/get-started/install)
3. Android SDK + 平台工具 + Android Studio（或纯命令行 SDK）
4. JDK 17

> **国内必须设镜像**，否则官方源 `storage.googleapis.com` 会卡死：

```powershell
$env:FLUTTER_STORAGE_BASE_URL = "https://storage.flutter-io.cn"
$env:PUB_HOSTED_URL = "https://pub.flutter-io.cn"
```

检查环境：

```powershell
flutter doctor
```

## 真机调试（最快看到效果）

```powershell
flet run -d android     # 需要手机开启「USB 调试」并连接电脑
```

## 打包 APK

```powershell
powershell -ExecutionPolicy Bypass -File .\build_android.ps1
```

产物在 `build\apk\`，`app-release.apk` 可直接安装到手机；
也可以用 `flet build appbundle` 产出上架 Google Play 用的 `.aab`。

> **当前状态：APK 已产出并验证完成。**
> 产物：`甘肃省信息技术会考学习软件-Android.apk`（61.9 MB，作者本机打包，成品不随仓库发布）。
> 已拆包核对：应用名、minSdk 24 / targetSdk 34、ABI 覆盖 arm64-v8a + armeabi-v7a、
> 内置 Python 3.11 运行时、2401 个 Python 依赖。
> 签名：**作者本人密钥**（`apksigner verify --print-certs` 可见 `CN=王子豪`），
> 构建时用 `tools\strip_apk_signature.py` 去掉 flet 默认的 debug 签名后再签。
> Dart 层已混淆（`--obfuscate`，符号表在 `D:\gs_it_exam_symbols`）。
> **已在 MuMu 模拟器（Android 15）实测**：横竖屏、跑代码、答题、进度卡刷新全部通过。
> 完整攻克过程见 `..\提交历史` 第四节。
>
> **为什么不能直接 `flet build apk`**：
> flet 默认从 GitHub 拉 `flet-build-template`，本机不通 github.com；
> 拉到后的模板又过旧（AGP 7.3 / Gradle 7.5），
> 且 `dependency_overrides` 会拉到要求 AGP 8.12 的新版插件。
> 本项目自建了离线模板 `D:\tools\flet-cc-template`，把这三个坑都补了：
> 钉死插件版本、升到 AGP 8.1 / Gradle 8.3 / Kotlin 1.8.22、加 `FLUTTER_ROOT` 兜底。
> `build_android.ps1` 已把镜像与环境变量全部写进去，本机已实测跑通。

## 发布到应用商店

1. 在 https://play.google.com/console 创建应用，拿到包名（如 `com.gansuexam.study`）；
2. 用 `build_android.ps1` 里的 `--org`、`--project-name` 替换成自己的包名；
3. 生成签名密钥：`keytool -genkey -v -keystore study.keystore -keyalg RSA -keysize 2048 -validity 10000 -alias study`；
4. 上传 `.aab` 并填写版本说明、隐私政策。
   注意：应用**不联网、不收集任何信息**，但会在本机开一个
   `127.0.0.1` 的临时 HTTP 端口给 WebView 跑 Pyodide 用（进程内自启自停）。

## 同步 Windows 端的最新代码

见 `..\gs_it_exam_windows\README.md` 的「同步代码到手机端」一节。
