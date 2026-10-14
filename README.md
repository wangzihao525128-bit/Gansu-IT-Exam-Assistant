# 甘肃省信息技术会考学习软件

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **仓库简介**：教中国学生信息技术的学考软件（**仅限甘肃**）。
> 代码与文档以 MIT 公开，**是为了给作者的创作过程留下公开、可复核的时间戳保护作者的版权**；
> 教材内容的版权在原出版方手里，本项目无权再授权（见第十三节）。

> 给甘肃高中生复习信息技术会考（学考）用的桌面 / 手机学习软件：**读讲解 → 改代码 → 真跑一遍 → 做题看解析**。
> 一套 Python 代码（flet 0.23 + Python 3.11）同时出两种安装包：**Windows 桌面 exe** 与 **Android APK**
> （同一套代码也能用 `flet run --web` 当网页版跑）。
> 软件自带内置 Python，**目标电脑和手机都不用装 Python、不用联网**。

---

## 一、这是什么，为什么做

会考复习材料大多是「PDF + 死题」，学生看得懂语法却不敢改代码——一改就报错，一报错就放弃。
这个软件把每一个知识点做成三段：**Markdown 讲解 → 可以直接改、可以真跑的示例代码 → 带解析的练习题**。
代码在一个**教学沙箱**里执行，报错被翻译成高中生动得了的中文；做题进度存在本机，答完当场刷新。
内容（知识点、题库）全部放在一个 JSON 文件里，老师用记事本就能换题库，**不用重新打包**。

- 定位：**教学辅助工具**，不是考试系统，也不联网、不留学生数据到服务器。
- 内容规模：**6 个模块 / 23 个知识点 / 92 道练习题**（含 **2023 年真题操作题精讲 12 道**，明细见第二节）。
- 作者：**王子豪**；开发方式：**AI 协助制作**。

---

## 二、功能一览

| 模块 | 做了什么 |
|---|---|
| 理论页 | Markdown 讲解，支持标题、列表、代码块、表格 |
| 代码示例 | 每知识点一段可运行示例，编辑器带语法高亮、行号、回车自动缩进 |
| 代码运行 | 内置 Python 真跑；桌面走独立子进程（`python -I -S`），Android 走进程内 embedded 后端 |
| 中文报错 | 把 Python 异常翻译成「第几行 + 哪里写错了 + 怎么改」，并附原始报错 |
| 标准输入 | 示例用到 `input()` 时，界面直接给一行「标准输入」，预填样例数据 |
| 练习题 | 单选题 + 即时判分 + 解析；答对答错都有明确反馈 |
| 学习进度 | 首页与详情页展示「答了几道 / 正确率 / 练过几个知识点」，答完当场刷新 |
| 主题 | 深色 / 浅色一键切换 |
| 插件接口 | 把一个文件夹丢在 exe 旁边即可追加模块或面板，不用重新打包（见 `plugins/README.md`） |
| 署名水印 | 左上角作者名 `✍ 王子豪`，右下角 `本软件由 AI 协助制作 · v1.0` |
| 数据与代码分离 | `data/knowledge_points.json` 换题库，`plugins/` 加插件，都不用重新打包 |

### 题库内容（6 个模块 / 23 个知识点 / 92 道练习题）

| 模块 | 知识点 | 练习题 |
|---|---|---|
| 一、数据与信息 | 3 | 16 |
| 二、算法与程序实现 | 5 | 24 |
| 三、数据处理与应用 | 1 | 4 |
| 四、信息技术与社会 | 1 | 4 |
| 五、信息安全与信息社会责任 | 1 | 6 |
| **六、2023 年操作题真题精讲** | **12** | **38** |

**模块六是本次新增的重点**：把 `资料\2023考试python操作题\` 里那 12 道真题
（P1 交通信号灯、P2 遥控灯光、P3 汽车档位、P4 考核评价、P5 判断偶数、
P6 收银程序、P7 身高统计、P8 成绩合格人数、P9 用水次数、P10 剪纸游戏、
P11 存款程序、P12 生产总值）逐题拆成一个知识点，每题包含：

- **原题原文**（含 ①②③ 填空标记，照抄试卷）；
- **图解**：这段程序的执行路线、每个空考什么、变量每一轮怎么变；
- **可运行的完整答案代码**（能直接在编辑器里点「运行代码」验证）；
- **3~4 道选择题**，其中包含「①处应填什么」这种**与原考试完全同构**的题型。

> 原题 `.py` 文件顶部残留的速记（如 P12 那行 `#P12 2022 >= n`）
> 与代码语义**对不上**的地方，在知识点里都专门作了说明，并以代码语义为准。

### 关于「图解」的实现方式（含一条硬约束）

知识点里的图解用两种写法，**其一是 Markdown 表格，其二是箭头链式流程**：

```
开始 ──▶ 判断条件 ──是──▶ 执行语句块1 ──▶ 结束
              │
              └──否──▶ 执行语句块2 ──────▶ 结束
```

**为什么不在代码块里画 `┌─┐│└┘` 把中文框起来**：
应用用 `ft.Markdown` + `font_family="Consolas"` 渲染代码块，而 **Consolas 没有中文字形**，
中文只能回退到系统 CJK 字体。Consolas 的字符宽约 **0.55em**、CJK 全角字形 **1.0em**，
即 **1 个中文 ≈ 1.82 个 Consolas 字符，而不是 2** —— 差那 0.18 会累积，
中文画在方框里**必然错位**。Markdown 表格的边框由渲染器绘制，完全不受这个影响，所以优先用它。

> 真正的**图片**插图目前没做：`build_exe.py`（两处）与 `build_windows.ps1` 都**只把 `assets/icon.png` 打进包**，
> 其他资源不会随安装包分发。要上真图片，得同时改打包脚本、`page.assets_dir` 配置和两个平台的工程树，
> 属于独立的一次功能改动，不在本次范围内。

---

## 三、截图

> 界面截图**暂未随仓库发布**（作者整理好后再补，图片会放在这里或 Releases 的发布说明里）。
> 想先看效果：按第七节自行构建，或从 Releases 取打包好的安装包运行。

界面概览（文字版）：

| 页面 | 内容 |
|---|---|
| 首页 | 模块卡片（每张显示知识点数与练习题数）+ 搜索框 + 备考建议卡 + 学习进度卡 |
| 模块页 | 本模块知识点卡片列表（含代码行数、提示条数、练习题数）+「下一个模块」引导 |
| 详情页 | 三栏：左＝模块导航 + 本模块知识点 + 学习进度卡；中＝讲解 + 代码示例 + 练习题；右＝代码编辑器（行号 / 语法高亮 / 标准输入 / 运行结果）+ 代码解释与提示面板 |
| 运行结果 | 成功显示绿色「✅ 运行成功 · 用时 x.xx 秒」+ 真实 stdout；出错显示中文提示（含出错行号与 Python 原始信息） |
| 手机端 | 竖屏整页滚动堆叠；横屏三栏，代码区占满右栏，运行结果不用滚动就能看到 |

---

## 四、下载与使用（发给学生用哪个）

> 仓库**不含**构建产物（`.gitignore` 排除了 `dist/`、`dist_onefile/`），
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

任何一条非零退出即视为失败。

**两棵树都要跑**：把上面的 `cd gs_it_exam_windows` 换成 `cd gs_it_exam_android` 再跑一遍，
两棵树各五项 = 10 项全绿才算过。

> 单测全绿**不代表界面没问题**——这个项目四次严重的界面问题都不是单测抓到的。
> 作者的验收习惯是：打包后**启动真实 exe 点一遍**（首页 → 模块 → 知识点 → 运行代码），
> 每个窗口尺寸都确认两件事：**A** 结果区真的跑通（扫像素，绿多红少）、**B** 结果框没被卡片切掉（≥55px）。
> 这套走查脚本留在作者本机，未随仓库发布。

---

## 七、构建

```powershell
# Windows：文件夹版 + 单文件版（约 50 秒）
powershell -ExecutionPolicy Bypass -File .\gs_it_exam_windows\build_windows.ps1
powershell -ExecutionPolicy Bypass -File .\gs_it_exam_windows\build_windows.ps1 -OneFile

# Android APK（约 2 分钟，需要 Flutter + JDK 17 + Android SDK）
powershell -ExecutionPolicy Bypass -File .\gs_it_exam_android\build_android.ps1
```

- 改完代码**只改 `gs_it_exam_windows\`**（主仓库），再把共享文件同步到 `gs_it_exam_android\`
  （44 个共享文件是逐字节复制的两份副本；作者的同步脚本留在本机，未随仓库发布）。
- 改完界面必须**驱动打包好的 exe 点一遍**，别只看单测。

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
- 示例代码用到 `input()` 的知识点，额外给 `sample_input`，编辑器才会出现「标准输入」那一行。
  **多行输入直接用换行符 `\n` 分隔**（在 JSON 里写成 `"85\n8\n2024"`），不是别的分隔符。
  注意：`ui_smoke_test.py` 有一条断言会检查**每个用到 `input()` 的知识点都配了非空 `sample_input`**，漏一个就会失败。
- `content` 里的**图解**用两种写法，可靠性由高到低：
  **① Markdown 表格**（边框由渲染器画，中文宽度不影响对齐）→
  **② 箭头链式流程**（每行独立，不依赖跨行列表对齐）。
  **不要在代码块里用 `┌─┐│└┘` 把中文框起来** —— 应用用 `font_family="Consolas"` 渲染代码块，
  Consolas 没有中文字形，中文会回退到系统字体；Consolas 字符宽约 0.55em、CJK 全角 1.0em，
  **1 个中文 ≈ 1.82 个 Consolas 字符而不是 2**，方框必然错位。
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
├─ gs_it_exam_windows/                 ← 主仓库（唯一真源，打 Windows exe）
│  ├─ main.py                          ← 入口，flet 路由与启动自检
│  ├─ core/                            ← 代码执行器 / 沙箱安全 / 题库 / 本机存档 / 插件
│  ├─ ui/                              ← flet 页面与组件（首页、模块页、详情页、编辑器、进度卡、署名）
│  ├─ data/knowledge_points.json       ← 题库（改这个就换内容）
│  ├─ plugins/README.md                ← 插件接口说明
│  ├─ tools/                           ← 五项校验脚本 + 打包脚本 + 期望输出快照
│  ├─ assets/                          ← 图标与运行资源
│  ├─ build_windows.ps1 / build_android.ps1
│  └─ requirements.txt
├─ gs_it_exam_android/                 ← 与主仓库同构的安卓工程（打 APK）
├─ LICENSE / 署名与授权声明.md
└─ README.md
```

两棵树是**逐字节复制**出来的两份副本，共享文件从 Windows 单方向同步到安卓那棵；
`.gitattributes` 里写了 `* -text`，**禁止 git 改行尾**——被改一次行尾，两棵树的逐字节一致性就没了。

> 仓库里**只放能打出 exe / apk 的源码**。作者的校验/同步/走查脚本、内部工作文档、
> 界面截图与教材素材都不入库（见 `.gitignore` 末尾），它们仍在作者本机。

---

## 十一、沙箱：它是教学沙箱，不是安全边界

学生代码要能被拦住，也要能给出人话的报错。现在的做法分几层：

| 层 | 位置 | 做了什么 |
|---|---|---|
| 静态白名单 | `core/security.py` | AST 扫描：`import os`、`open`、`eval`、`exec`、`__import__`、`subprocess` 等一律拒绝，`getattr(x, "__self__")` 这类字符串形式也拦 |
| 运行时限制 | `core/security.py` + `core/code_executor.py` | 受限 builtins、`safe_getattr()`（只放行公开属性）、包一层的 `print`，**不把真的内置对象交给学生** |
| 进程隔离 | 桌面 | 学生代码在独立子进程里跑（`python -I -S`），带超时与输出上限 `MAX_OUTPUT_CHARS = 200_000` |
| 进程内预算 | Android | SeriousPython 的 embedded CPython 在进程内执行，用 `sys.settrace` 行数预算 + 墙钟看门狗打断死循环 |

**必须说清楚的一句**：这是**教学沙箱**，目标是「拦住学生手滑、并告诉他为什么」，**不是安全边界**。
静态白名单 + 受限 builtins 的组合拦得住课堂上的误用，拦不住铁了心的攻击者；
它在设计上就没有、也不该被当作隔离不可信代码的机制。

同理，**插件不在沙箱里**（跑在主程序进程），只放自己信得过的代码。
界面上的提示因此写的是「（教学沙箱，请勿运行陌生代码）」，而不是「读不到你的文件」这类做不到的承诺。

---

## 十二、已知限制（不粉饰）

| 限制 | 说明 |
|---|---|
| Android 只在模拟器验过 | MuMu 模拟器（Android 15）实测竖屏 / 横屏跑通代码、答题、进度刷新；**实体手机与厂商定制系统没验过** |
| 题库规模仍有限 | 现有 23 个知识点 / 92 道题，其中模块六是 **2023 年**那一次的 12 道操作题；**其他年份的真题还没录进来**，覆盖面仍然不够 |
| 没有图示 | 「理论 + 图示 + 代码示例」里，图示还是空的 |
| 没有错题本 | 只看得到正确率，看不到「具体哪几道错了」（数据已存，缺页面） |
| Web 版代码窗口跑不了 Python | flet 0.23 的 `ft.WebView` 在 web 渲染器下是空平台视图；网页版是「浏览器当显示器、Python 在服务器跑」 |
| 手机端行号不跟随滚动 | flet 0.23 的布局限制，不是逻辑 bug |
| 两棵树复制粘贴架构 | 44 个共享文件是两份副本 + 人工同步，改一处必须记得同步 |

---

## 十三、内容版权（重要）

- **代码**（本仓库所有 `.py` / `.ps1` / 文档）由 **王子豪** 编写，采用 **MIT 许可**，见 [`LICENSE`](LICENSE)。
- **教学内容**（知识点的讲解文字、题库）**不是原创**：它整理自第三方公开出版物 **《甘肃省信息技术学考指导》**，
  **该部分内容的版权属于原出版方**，本项目**没有**、也无权把它重新授权给你。
- 教学内容放在仓库里是**为了学习与教学用途**（也是为了让老师能直接替换成自己的题库）。
  如果你要再分发、商用或做成公开产品，请**自行确认并处理教材内容的授权**，必要时替换成自己编写的内容
  （只需改 `data/knowledge_points.json`，不用动代码）。
- **教材原件与素材不入库**：`资料\`（题库 JSON 素材、教材 PDF）已整体排除，见 `.gitignore` 末尾。
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

第三方组件：内置 CPython（PSF License）、flet / Flutter（Apache-2.0）、PyInstaller、
SeriousPython、Pyodide（MPL-2.0，相关代码保留但当前安装包内不可达）——均按其自身许可使用。
内容：版权归《甘肃省信息技术学考指导》原出版方所有，本项目不重新授权
```

MIT 只覆盖本仓库的**代码**。它要求的「保留版权声明」指的是 `LICENSE` 与源码中的版权与作者署名，
应用内的署名水印请在衍生版本中一并保留（这是礼貌要求，也是作者对作品来源的唯一标识）。

---

## English summary

**Gansu IT Exam Study App** — a study/revision app for the Gansu province high-school IT
proficiency exam (会考). One Python 3.11 + flet 0.23 codebase ships to Windows desktop (exe)
and Android (APK), and can also run as a web app. Students read Markdown theory, edit and actually run Python
examples in a built-in editor, and answer multiple-choice questions with instant grading
and explanations; progress is stored locally. Content lives in a single JSON file
(`gs_it_exam_windows/data/knowledge_points.json`) so teachers can swap the question bank
without rebuilding, and plugins can be dropped next to the executable.

- Tests: `tools/check_data.py`, `tools/test_sandbox.py` (56 cases), `tools/check_examples.py`,
  `tools/ui_smoke_test.py` (111 checks), `tools/check_plugins.py` — 5 tools × 2 platform trees = 10/10.
- Sandbox: an AST whitelist plus restricted builtins plus a `python -I -S` subprocess (desktop)
  or in-process tracing (Android). **It is a teaching sandbox, explicitly not a security boundary.**
- Known limits: Android is verified on an emulator only; only 11 knowledge points / 15 questions today.
- **Licensing**: the *code* is MIT by 王子豪 (Wang Zihao). The *teaching content* was derived from
  《甘肃省信息技术学考指导》, a third-party published study guide whose copyright belongs to its
  publisher — it is included for study purposes and is **not** relicensed by this project.
