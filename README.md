# 甘肃省信息技术会考学习软件

[![CI](https://github.com/wangzihao525128-bit/Gansu-IT-Exam-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/wangzihao525128-bit/Gansu-IT-Exam-Assistant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **仓库简介**：教中国学生信息技术的学考软件（**仅限甘肃**）。
> 代码与文档以 MIT 公开，**是为了给作者的创作过程留下公开、可复核的时间戳保护作者的版权**；
> 教材内容的版权在原出版方手里，本项目无权再授权（见第十三节）。

> 给甘肃高中生复习信息技术会考（学考）用的桌面 / 手机学习软件：**读讲解 → 改代码 → 真跑一遍 → 做题看解析**。
> 一套 Python 代码（flet 0.23 + Python 3.11）同时出四个平台的包：Windows 桌面、Android APK、iOS、Web。
> 软件自带内置 Python，**目标电脑和手机都不用装 Python、不用联网**。

---

## 一、这是什么，为什么做

会考复习材料大多是「PDF + 死题」，学生看得懂语法却不敢改代码——一改就报错，一报错就放弃。
这个软件把每一个知识点做成三段：**Markdown 讲解 → 可以直接改、可以真跑的示例代码 → 带解析的练习题**。
代码在一个**教学沙箱**里执行，报错被翻译成高中生动得了的中文；做题进度存在本机，答完当场刷新。
内容（知识点、题库）全部放在一个 JSON 文件里，老师用记事本就能换题库，**不用重新打包**。

- 定位：**教学辅助工具**，不是考试系统，也不联网、不留学生数据到服务器。
- 内容规模：5 个模块 / 11 个知识点 / 15 道练习题（**这是目前最大的短板**，见「已知限制」）。
- 作者：**王子豪**；开发方式：**AI 协助制作**。

---

## 二、功能一览

| 模块 | 做了什么 |
|---|---|
| 理论页 | Markdown 讲解，支持标题、列表、代码块、表格 |
| 代码示例 | 每知识点一段可运行示例，编辑器带语法高亮、行号、回车自动缩进 |
| 代码运行 | 内置 Python 真跑；桌面走独立子进程（`python -I -S`），Android/iOS 走进程内 embedded 后端 |
| 中文报错 | 把 Python 异常翻译成「第几行 + 哪里写错了 + 怎么改」，并附原始报错 |
| 标准输入 | 示例用到 `input()` 时，界面直接给一行「标准输入」，预填样例数据 |
| 练习题 | 单选题 + 即时判分 + 解析；答对答错都有明确反馈 |
| 学习进度 | 首页与详情页展示「答了几道 / 正确率 / 练过几个知识点」，答完当场刷新 |
| 主题 | 深色 / 浅色一键切换 |
| 插件接口 | 把一个文件夹丢在 exe 旁边即可追加模块或面板，不用重新打包（见 `plugins/README.md`） |
| 署名水印 | 左上角作者名 `✍ 王子豪`，右下角 `本软件由 AI 协助制作 · v1.0` |
| 数据与代码分离 | `data/knowledge_points.json` 换题库，`plugins/` 加插件，都不用重新打包 |

---

## 三、截图

图片都在仓库里（`完善/screenshots/`），不需要外部图床。

| Windows 绿色版 | Windows 单文件版 |
|---|---|
| ![首页](完善/screenshots/exe_win/走查_01_首页.png) | ![首页](完善/screenshots/exe_one/走查_01_首页.png) |
| `完善/screenshots/exe_win/走查_01_首页.png` —— 首页：5 个模块卡片 + 学习进度卡 | `完善/screenshots/exe_one/走查_01_首页.png` —— 121.2 MB 单文件版启动后的首页 |

| Android（MuMu 模拟器实测） | Android 横屏运行结果 |
|---|---|
| ![竖屏运行结果](完善/screenshots/安卓/46_竖屏运行结果.png) | ![横屏运行结果](完善/screenshots/安卓/36_横屏运行结果_修复后.png) |
| `完善/screenshots/安卓/46_竖屏运行结果.png` —— 竖屏点「运行代码」，输出是真实 stdout | `完善/screenshots/安卓/36_横屏运行结果_修复后.png` —— 横屏三栏，结果不用滚动就能看见 |

更多截图：

| 路径 | 说明 |
|---|---|
| `完善/screenshots/exe_win/走查_02_模块页.png` | 模块页知识点卡片 |
| `完善/screenshots/exe_win/走查_03_详情页.png` | 知识点详情页：左栏导航 + 中栏讲解 + 右栏编辑器 |
| `完善/screenshots/exe_win/走查_04_运行结果.png` | 点「运行代码」的结果区（布局体检：结果框可见 64px，PASS） |
| `完善/screenshots/exe_one/走查_02_模块页.png` ~ `_04_运行结果.png` | 同上四步，对象是单文件版 exe |
| `完善/screenshots/安卓/` | 模拟器实测整组：竖屏 / 横屏、首页 / 模块 / 详情 / 运行结果 / 答题 |

---

## 四、下载与使用（发给学生用哪个）

> 仓库**不含**构建产物（`.gitignore` 排除了 `dist/`、`dist_onefile/`、`完善/成品/`），
> 需要自己按第七节构建，或从 Releases 页面取打包好的文件。

| 产物 | 体积 | 适合谁 | 怎么用 |
|---|---|---|---|
| **Windows 绿色版**（整个文件夹） | 214.4 MB | 机房 / 教室电脑，**推荐** | 解压后双击 `GansuITExam.exe`；**必须整个文件夹一起拷**，不能只拷 exe |
| **Windows 绿色版 zip** | 93.7 MB | 用微信 / U 盘传给学生 | 解压即用，同上 |
| **Windows 单文件版**（单个 exe） | 121.2 MB | 图省事、只发一个文件 | 双击即用。每次启动要解包到 `%TEMP%`，启动约 3.3 秒（绿色版约 0.8 秒） |
| **Android APK** | 61.9 MB | 学生手机 | 传到手机点安装，需允许「未知来源应用」；要求 Android 7.0+。**签名换过，装过更早版本的请先卸载** |

三种 Windows 产物都**内置 CPython 3.11**，目标电脑**不用装 Python、不用联网**。
APK 内置 CPython 3.11.6，跑代码完全在本机，同样不用联网。

注意事项：

- v1.0 的 APK 用**作者本人的密钥签名**（`apksigner verify --print-certs` 可见 `CN=王子豪`），
  已经是可以上架的正规签名；换签名后装过旧包的设备要先卸载再装。
- 应用内有三处署名（左上角 `✍ 王子豪`、右下角 AI 协助声明、窗口标题），
  并有签名自检：署名被改动会显示「本软件已被修改」并回退到原作者名。详见 `署名与授权声明.md`。
- 学习进度存在本机（Windows：`%USERPROFILE%\.gs_it_exam\userdata.json`），**换设备不会同步**，这是本机记录。
- 想清空进度：删掉上面那个文件即可。

---

## 五、从源码运行

```powershell
cd gs_it_exam_windows
python -m pip install -r requirements.txt      # flet==0.23.0（+ 打包用的 pyinstaller / Pillow）
python main.py
```

- Python **3.11** 已验证（代码里的最低要求是 3.8，见 `core/code_executor.py` 的 `MIN_PYTHON`）。
- `requirements.txt` 里 `flet` 是运行必需，`pyinstaller` 与 `Pillow` 只在**重新打包 exe** 时用到
  （`tools/build_exe.py` 用 Pillow 生成图标）。只跑源码不需要后两个。

- 网页版（老师在服务端跑，学生手机浏览器当显示器）：

  ```powershell
  flet run --web --port 8551
  ```

---

## 六、跑测试

五项校验，全部在 `gs_it_exam_windows\` 下执行（当前 56 / 111 等数字为实测值）：

```powershell
cd gs_it_exam_windows
python tools\check_data.py        # 题库 JSON 结构与字段校验
python tools\test_sandbox.py      # 沙箱注入与逃逸回归，56 个用例
python tools\check_examples.py    # 每段示例真跑一遍，并比对录制的期望输出
python tools\ui_smoke_test.py     # 界面冒烟，111 项检查
python tools\check_plugins.py     # 插件接口 28 条断言（含故意写坏的插件）
```

任何一条非零退出即视为失败；CI（`.github/workflows/ci.yml`）就是这么判的。

三棵树（Windows / Android / iOS）一起跑 + 真机走查：

```powershell
cd D:\桌面\工作区\学考
powershell -ExecutionPolicy Bypass -File .\完善\check_all.ps1                     # 3 平台 × 5 项 = 15 项，上次完整校验 15/15
powershell -ExecutionPolicy Bypass -File .\完善\走查.ps1                          # 驱动真实 EXE 点一遍 + 布局体检（需先打包）
powershell -ExecutionPolicy Bypass -File .\完善\走查.ps1 -WinW 1600 -WinH 1000    # 换个大窗口再走一遍
```

> `check_all.ps1` 开头有两道预检：`python` 是否在 PATH（缺失 exit 99）、所有 `.ps1` 是否带
> **UTF-8 BOM**（缺失 exit 98）。BOM 那道不是形式主义——被剥掉 BOM 的脚本会被 PowerShell 5.1
> 按 ANSI 读，中文注释变乱码且报错行号指向无关处。用编辑器改过 `.ps1` 之后请确认它还是「UTF-8 带 BOM」。

`走查.ps1` 会启动**打包好的 EXE**，点击首页 → 模块 → 知识点 → 运行代码，每步比对截图哈希，
最后做两项体检：**A** 扫结果区像素确认代码真的跑通（绿多红少），**B** 确认结果框没被卡片切掉（≥55px）。
单测全绿时它仍可能报红——这个项目四次严重的界面问题都不是单测抓到的。

---

## 七、构建

```powershell
# Windows：文件夹版 + 单文件版（约 50 秒）
powershell -ExecutionPolicy Bypass -File .\gs_it_exam_windows\build_windows.ps1
powershell -ExecutionPolicy Bypass -File .\gs_it_exam_windows\build_windows.ps1 -OneFile

# Android APK（约 2 分钟，需要 Flutter + JDK 17 + Android SDK）
powershell -ExecutionPolicy Bypass -File .\gs_it_exam_android\build_android.ps1
```

- 改完代码**只改 `gs_it_exam_windows\`**（主仓库），再用 `完善\sync_platforms.ps1` 同步到另外两棵树。
- 改完界面必须跑一次 `完善\走查.ps1`。
- iOS 需要 macOS + Xcode，`gs_it_exam_ios\build_ios.sh` 已备好，见「已知限制」。

---

## 八、换题库（老师用，不用会编程）

题库就是一个 JSON 文件，记事本就能改：

```
开发时：      gs_it_exam_windows\data\knowledge_points.json
打包后：      GansuITExam\data\knowledge_points.json     （exe 旁边那份优先读）
```

字段表：

| 层级 | 必填字段 |
|---|---|
| 模块 | `id` `name` `color` `points` |
| 知识点 | `id` `title` `content` `code_example` `code_explanation` `hints` `questions` |
| 练习题 | `question` `options` `answer` `explanation` |

要点：

- `answer` 填**选项字母**（`"B"`），不是下标；`options` 每项**自带序号前缀**（`"B. 数据是……"`）。
- 示例代码用到 `input()` 的知识点，额外给 `sample_input`（多行用 `·` 分隔），编辑器才会出现「标准输入」那一行。
- 答题记录按**内容键**（题目 `id` → 题干 sha1 前 8 位 → 下标）存，改题库不会把旧记录错位。
- **改完必须跑这两条**：

  ```powershell
  cd gs_it_exam_windows
  python tools\check_data.py
  python tools\check_examples.py
  ```

  后者会告诉你哪段示例的输出变了（示例输出比对当初就抓出过一个算错的凯撒加密示例）。

---

## 九、写插件（老师用）

`plugins\` 目录是插件接口的落点。把一个子目录丢到 exe 旁边，里面放 `plugin.py`，
可以选写 `modules()` / `detail_panel()` / `startup()` 三样，**写一样算一样**：

- 插件只能「加」不能「改」——id 撞教材模块会被丢弃，学生看到的教材永远以 JSON 为准；
- 插件报错只跳过该插件，不会带崩软件；
- 插件跑在主程序进程里，**不在学生代码沙箱中**，只放自己信得过的代码。

模板、字段速查与自测命令：**[`plugins/README.md`](gs_it_exam_windows/plugins/README.md)**。

---

## 十、项目结构

```
学考/                                  ← 仓库根（本目录）
├─ gs_it_exam_windows/                 ← 主仓库（唯一真源）
│  ├─ main.py                          ← 入口，flet 路由与启动自检
│  ├─ core/                            ← 代码执行器 / 沙箱安全 / 题库 / 本机存档 / 插件
│  ├─ ui/                              ← flet 页面与组件（首页、模块页、详情页、编辑器、进度卡、署名）
│  ├─ data/knowledge_points.json       ← 题库（改这个就换内容）
│  ├─ plugins/README.md                ← 插件接口说明
│  ├─ tools/                           ← 五项校验脚本 + 打包脚本 + 期望输出快照
│  ├─ assets/                          ← 图标等资源
│  ├─ build_windows.ps1 / build_android.ps1
│  └─ requirements.txt
├─ gs_it_exam_android/                 ← 与主仓库同构的安卓工程（由同步脚本生成）
├─ gs_it_exam_ios/                     ← 与主仓库同构的 iOS 工程（同上）
├─ 完善/                                ← 交接文档 + 走查脚本 + 截图
│  ├─ 交接文档.md / 可行性报告.md / 本轮修复记录.md / 自检记录.md …
│  ├─ check_all.ps1 / sync_platforms.ps1 / 走查.ps1
│  └─ screenshots/
├─ 资料/                                ← 知识点 JSON 素材（**教材 PDF 不在仓库里**，见第十三节）
├─ .github/workflows/ci.yml            ← CI（Windows）
├─ CONTRIBUTING.md / CHANGELOG.md / 署名与授权声明.md / LICENSE
└─ README.md
```

三棵树是**逐字节复制**出来的三份副本，共享文件由 `完善\sync_platforms.ps1` 从 Windows 单方向同步到另外两棵；
`.gitattributes` 里写了 `* -text`，**禁止 git 改行尾**——被改一次行尾，三棵树的逐字节一致性就没了。

---

## 十一、沙箱：它是教学沙箱，不是安全边界

学生代码要能被拦住，也要能给出人话的报错。现在的做法分几层：

| 层 | 位置 | 做了什么 |
|---|---|---|
| 静态白名单 | `core/security.py` | AST 扫描：`import os`、`open`、`eval`、`exec`、`__import__`、`subprocess` 等一律拒绝，`getattr(x, "__self__")` 这类字符串形式也拦 |
| 运行时限制 | `core/security.py` + `core/code_executor.py` | 受限 builtins、`safe_getattr()`（只放行公开属性）、包一层的 `print`，**不把真的内置对象交给学生** |
| 进程隔离 | 桌面 | 学生代码在独立子进程里跑（`python -I -S`），带超时与输出上限 `MAX_OUTPUT_CHARS = 200_000` |
| 进程内预算 | Android / iOS | SeriousPython 的 embedded CPython 在进程内执行，用 `sys.settrace` 行数预算 + 墙钟看门狗打断死循环 |

**必须说清楚的一句**：这是**教学沙箱**，目标是「拦住学生手滑、并告诉他为什么」，**不是安全边界**。
静态白名单 + 受限 builtins 的组合拦得住课堂上的误用，拦不住铁了心的攻击者；
它在设计上就没有、也不该被当作隔离不可信代码的机制。

同理，**插件不在沙箱里**（跑在主程序进程），只放自己信得过的代码。
界面上的提示因此写的是「（教学沙箱，请勿运行陌生代码）」，而不是「读不到你的文件」这类做不到的承诺。

---

## 十二、已知限制（不粉饰）

| 限制 | 说明 |
|---|---|
| iOS 未出包 | 需要 macOS + Xcode + 付费开发者账号，Windows 上做不了；`gs_it_exam_ios\build_ios.sh` 已备好但**没构建过** |
| Android 只在模拟器验过 | MuMu 模拟器（Android 15）实测竖屏 / 横屏跑通代码、答题、进度刷新；**实体手机与厂商定制系统没验过** |
| 题库规模小 | 只有 11 个知识点 / 15 道题，覆盖不了整个会考大纲——**第一短板** |
| 没有图示 | 「理论 + 图示 + 代码示例」里，图示还是空的 |
| 没有错题本 | 只看得到正确率，看不到「具体哪几道错了」（数据已存，缺页面） |
| Web 版代码窗口跑不了 Python | flet 0.23 的 `ft.WebView` 在 web 渲染器下是空平台视图；网页版是「浏览器当显示器、Python 在服务器跑」 |
| 手机端行号不跟随滚动 | flet 0.23 的布局限制，不是逻辑 bug |
| 三平台复制粘贴架构 | 44 个共享文件是三份副本 + 人工同步脚本，改一处必须记得同步 |

---

## 十三、内容版权（重要）

- **代码**（本仓库所有 `.py` / `.ps1` / 文档）由 **王子豪** 编写，采用 **MIT 许可**，见 [`LICENSE`](LICENSE)。
- **教学内容**（知识点的讲解文字、题库）**不是原创**：它整理自第三方公开出版物 **《甘肃省信息技术学考指导》**，
  **该部分内容的版权属于原出版方**，本项目**没有**、也无权把它重新授权给你。
- 教学内容放在仓库里是**为了学习与教学用途**（也是为了让老师能直接替换成自己的题库）。
  如果你要再分发、商用或做成公开产品，请**自行确认并处理教材内容的授权**，必要时替换成自己编写的内容
  （只需改 `data/knowledge_points.json`，不用动代码）。
- **教材原件（`资料\甘肃省信息技术学考指导.pdf`）不入库**：`.gitignore` 已排除 `资料/*.pdf`。
  它是出版社公开出版物的扫描件，把它放进公开仓库等于替原出版方做了一次未授权分发，
  这个风险不该由本项目承担。文件仍保留在作者本机，只是不被 git 跟踪。
- 以上是**如实说明事实**，不是法律意见；有疑问请咨询专业人士。

---

## 十四、作者与致谢

- **作者**：王子豪
- **开发方式**：**AI 协助制作**（软件内右下角也有同样的声明）
- **致谢**：[flet](https://flet.dev/)（Flutter for Python，界面）、PyInstaller（Windows 打包）、
  SeriousPython（Android 上的 embedded CPython）、Pyodide（WebAssembly 版 Python，
  相关代码保留但当前安装包内不可达），以及 Python 官方文档与社区问答。

署名与水印是作者身份标识，衍生作品请保留；详见 [`署名与授权声明.md`](署名与授权声明.md)。

---

## 十五、License

```
代码：MIT License, Copyright (c) 2026 王子豪（Wang Zihao）  → 见 LICENSE

第三方组件（Pyodide 等）与教材内容的授权说明：见 [NOTICE.md](NOTICE.md)。
内容：版权归《甘肃省信息技术学考指导》原出版方所有，本项目不重新授权
```

MIT 只覆盖本仓库的**代码**。它要求的「保留版权声明」指的是 `LICENSE` 与源码中的版权与作者署名，
应用内的署名水印请在衍生版本中一并保留（这是礼貌要求，也是作者对作品来源的唯一标识）。

---

## English summary

**Gansu IT Exam Study App** — a study/revision app for the Gansu province high-school IT
proficiency exam (会考). One Python 3.11 + flet 0.23 codebase ships to Windows desktop,
Android APK, iOS and Web. Students read Markdown theory, edit and actually run Python
examples in a built-in editor, and answer multiple-choice questions with instant grading
and explanations; progress is stored locally. Content lives in a single JSON file
(`gs_it_exam_windows/data/knowledge_points.json`) so teachers can swap the question bank
without rebuilding, and plugins can be dropped next to the executable.

- Tests: `tools/check_data.py`, `tools/test_sandbox.py` (56 cases), `tools/check_examples.py`,
  `tools/ui_smoke_test.py` (111 checks), `tools/check_plugins.py` — 5 tools × 3 platform trees = 15/15.
- Sandbox: an AST whitelist plus restricted builtins plus a `python -I -S` subprocess (desktop)
  or in-process tracing (Android/iOS). **It is a teaching sandbox, explicitly not a security boundary.**
- Known limits: iOS requires macOS + Xcode (script ready, never built); Android is verified on an
  emulator only; only 11 knowledge points / 15 questions today.
- **Licensing**: the *code* is MIT by 王子豪 (Wang Zihao). The *teaching content* was derived from
  《甘肃省信息技术学考指导》, a third-party published study guide whose copyright belongs to its
  publisher — it is included for study purposes and is **not** relicensed by this project.
