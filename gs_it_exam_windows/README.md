# 甘肃省信息技术会考学习 · Windows 桌面版

甘肃省普通高中「信息技术学业水平考试」备考软件，本目录是 **Windows 桌面端** 工程，
同时也是整套代码的**主仓库（唯一真源）**：
`main.py`、`core/`、`ui/`、`data/` 与 `gs_it_exam_android/` 里保持完全一致，改完这里再同步到手机端。

## 当前完成度

| 需求文档步骤 | 状态 |
| --- | --- |
| Step 1 初始化项目（目录结构 / 依赖 / 知识点数据） | ✅ 已完成 |
| Step 2 安全代码执行引擎（AST 检查 + 沙箱 + 中文报错） | ✅ 已完成，25 项单测全绿 |
| Step 3 首页（导航、5 个模块卡片、备考建议、响应式） | ✅ 已完成骨架 |
| Step 4 模块浏览页（URL 参数加载 + 卡片跳转） | ✅ 已完成，路由链路已验证 |
| Step 5 知识点详情页（电脑三栏 25/45/30、手机堆叠 40/30/30） | ✅ 已完成骨架 |
| Step 6~8 代码编辑器 / 练习题卡片 / 代码提示面板 | ⏳ 未开始 |
| Step 9 整合测试、Step 10 部署发布 | ⏳ 未开始 |

## 目录结构

```
gs_it_exam_windows/
├── main.py                  程序入口（Flet 启动）
├── requirements.txt         依赖清单
├── build_windows.ps1        打包成 exe 的脚本
├── data/
│   └── knowledge_points.json  知识点数据（5 模块 / 11 知识点 / 15 题）
├── core/
│   ├── knowledge_store.py   数据读取、内存缓存、搜索、判分工具
│   ├── security.py          AST 安全沙箱检查（放行 / 拦截规则）
│   └── code_executor.py     代码执行引擎（子进程沙箱 + Pyodide 脚本）
├── ui/
│   ├── theme.py             配色与样式（亮色 / 暗色切换）
│   ├── home_page.py         首页
│   ├── module_page.py       模块浏览页（Step 4）
│   ├── detail_page.py       知识点详情页（Step 5，三栏 / 堆叠布局）
│   └── components/          【Step 6-8】代码编辑器 / 练习题卡片 / 提示面板
├── tools/
│   ├── check_data.py        数据自检脚本
│   ├── test_sandbox.py      沙箱单元测试（25 项）
│   ├── check_examples.py    把 11 段教材示例代码全跑一遍
│   └── ui_smoke_test.py     界面冒烟测试（不用开窗口）
└── assets/                  图标与插图
```

## 知识点数据

- 源文件：`..\资料\甘肃省信息技术会考学习软件-知识点数据.json`（原样拷贝到 `data/`，请以 `资料` 为准）
- 改写前的原始版本备份在 `..\资料\甘肃省信息技术会考学习软件-知识点数据.原始备份.json`
- 真实结构（`core/knowledge_store.py` 完全按此编写）：

```
{"modules": [{"id": "module1", "name": "模块一：数据与信息", "color": "#4A90E2",
  "points": [{"id": "1_1", "title": "...", "content": "Markdown 讲解",
              "code_example": "Python 代码", "code_explanation": "代码解释",
              "hints": {"print": "说明"},
              "questions": [{"type": "choice", "question": "...",
                             "options": ["A. ...", "B. ..."],
                             "answer": "B", "explanation": "..."}]}]}]}
```

- 注意两点：`answer` 存的是**选项字母**而不是下标；`options` 已自带 `A. ` 这类序号前缀。
- 更新知识点只需替换 `data/knowledge_points.json`，代码不用动（数据与代码分离）。

## Step 4：路由与模块浏览页

`main.py` 是唯一的页面分发入口（对应需求文档「根据 URL 参数加载」）：

| 路由 | 页面 |
| --- | --- |
| `/` | 首页（5 个模块卡片） |
| `/module/<module_id>` | 模块浏览页，例如 `/module/module1` |
| `/point/<module_id>/<point_id>` | 知识点详情页（Step 5） |

```python
page.on_route_change = lambda event: route_change(page, event.route)
page.go("/module/module1")      # 从首页卡片跳到模块页
page.go("/")                    # 返回首页
```

模块页显示该模块的每个知识点：编号、标题、题数、代码行数、提示条数、讲解首句预览，
点任意一条进入详情页路由；模块 id 传错时显示友好提示而不是报错。
顶部导航栏用模块自带的主色，和首页卡片颜色对应。

## Step 5：知识点详情页（核心页面）

布局按需求文档 4.1 / 4.2，宽度 < 900px 自动从三栏切成上下堆叠：

* **电脑端三栏**：左 25%（搜索框 + 模块导航 + 本模块知识点列表）、
  中 45%（标题 + 理论讲解 + 代码示例 + 练习题区）、
  右 30%（代码编辑器 + 运行按钮 + 运行结果，代码解释区占底部 1/3）；
* **手机端堆叠**：40% 讲解区 → 30% 编辑器区 → 30% 代码解释区。

理论讲解直接用 Flet 自带的 `ft.Markdown` 渲染知识点里的 Markdown 正文，
代码示例和代码解释分别取 `code_example`、`code_explanation` 字段。
本步骤已留好代码编辑器（Step 6）、练习题（Step 7）、代码提示（Step 8）三个位置。

```python
page.data = {"detail_mode": narrow}   # 记住当前布局模式，宽度变化时才重建
```

## Step 2：代码执行引擎

```python
from core import code_executor as executor

result = executor.run_code("a = int(input())\nprint(a * 2)", test_inputs=["21"])
print(result.success, result.output)      # True 42
print(result.as_dict()["error_type"])     # 失败时是 security / timeout / ZeroDivisionError
```

四道防线，从外到里：

1. **AST 静态检查**（`core/security.py`）——危险模块（os / sys / subprocess / socket / requests / shutil / ctypes）、
   文件读写（`open`）、动态执行（`eval` / `exec` / `compile` / `__import__`）、
   内部属性（`__globals__`、`__class__` 等）一律拦下，并说明中文原因；
2. **子进程沙箱**——代码写进临时目录，用 `python -I -S` 启动：
   `-I` 隔离环境变量与脚本目录，`-S` 不加载 site，所以**第三方库一个都读不到**；
3. **内置函数白名单 + import 闸门**——只给 40 来个纯计算函数，`print` / `input` 由沙箱接管，
   白名单之外的模块直接拒绝；
4. **5 秒超时**——死循环会被强制结束，并提示「多半是 while True 忘了写 break」。

报错全部翻译成中文，例如 `ZeroDivisionError` → 「除数不能是 0，检查一下除号后面的数。」，
同时保留 Python 原始信息方便对照。

**手机端不一样**：Android / Web 没有 Python 解释器，也开不了子进程，
所以用 `build_pyodide_script()` 生成一段 JS，在 WebView 里交给 Pyodide 0.25 运行，
再用 `parse_pyodide_result()` 解析回传结果：

```python
from core import code_executor as executor

backend = executor.backend_for_platform(page.platform)   # 手机 / 网页 -> pyodide
script = executor.build_pyodide_script(code, ["21"])     # 写进 WebView 的 HTML
result = executor.parse_pyodide_result(json_from_webview)
```

### 自测命令

```powershell
python tools\check_data.py        # 数据结构
python tools\test_sandbox.py     # 沙箱单测：危险操作、死循环、中文报错
python tools\check_examples.py   # 11 段教材示例代码实跑
python tools\ui_smoke_test.py    # 首页构建 + 响应式 + 主题切换
```

## 快速开始

```powershell
# 1. 建虚拟环境
python -m venv venv
.\venv\Scripts\activate

# 2. 装依赖
pip install -r requirements.txt

# 3. 先自检数据（不需要 flet）
python tools\check_data.py

# 4. 启动程序
python main.py
```

## 打包成 exe

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

产物在 `dist\GansuITExam.exe`（单文件，知识点数据已内置，发给别人直接双击即可运行）。

## 同步代码到手机端

改完本目录后，在工作区根目录执行：

```powershell
foreach ($target in 'gs_it_exam_android') {
    Copy-Item -Recurse -Force .\gs_it_exam_windows\core, .\gs_it_exam_windows\ui, .\gs_it_exam_windows\data, .\gs_it_exam_windows\tools $target\
    Copy-Item -Force .\gs_it_exam_windows\main.py, .\gs_it_exam_windows\requirements.txt $target\
}
```

## 后续路线（对应需求文档）

- Step 2：`core/security.py` + `core/code_executor.py`，AST 白名单 + 5 秒超时 + 中文错误提示；
  Windows 端用 `subprocess` 隔离执行，手机端必须用 **Pyodide**（手机里没有 Python 解释器）。
- Step 4 / 5：模块浏览页、知识点详情页（电脑端 25% / 45% / 30% 三栏，
  手机端改成**整页滚动 + 区块按内容自然高度**——原先按 40/30/30 硬压会把运行结果挤没）。
- Step 6~8：代码编辑器、练习题卡片、代码提示面板。
- Step 9 / 10：整合测试、Web 部署、Windows 打包、Android 发布。

## 常见问题

- **提示 `ModuleNotFoundError: flet`** → 虚拟环境没装依赖，执行 `pip install -r requirements.txt`。
- **中文显示成乱码** → 终端编码问题，不影响程序；数据文件本身是 UTF-8。
- **卡片点了没反应** → 不会了。Step 1~10 全部做完了，首页/模块页/详情页都能正常跳转。
- **示例代码提示「这个模块不允许导入」** → 沙箱只开放 math / random / datetime 这类安全模块。
  教材的 11 段示例已全部改写成纯 Python、且不依赖随机数，`check_examples.py` 稳定 11/11 跑通。
- **打包成 exe 后点「运行」报错** → 不会了。`tools\bundle_python.ps1` 已把
  CPython 3.11.7 打进 `dist\GansuITExam\runtime\`，`code_executor` 按
  「exe 同级 runtime\ → 系统 PATH」的顺序找解释器，**目标机不用装 Python**。

---

## 完善阶段（2026-09-30）

Step 1~10 全部完成后，又做了一轮真机走查式的完善。
**这一轮的详细报告（可行性报告 / UI 评价 / 使用说明 / 自检记录 / 构建踩坑记录等）留在作者本机，未随仓库发布。**

### 交付状态

| 目标 | 状态 |
|---|---|
| Windows EXE（内置 Python 3.11.7） | ✅ 已打包并实测跑通代码 |
| 手机端跑代码（Web + Pyodide） | ✅ 真浏览器验证，4 类任务全过 |
| Android APK | ⚠️ 工具链已备齐，见 仓库提交历史 第四节 |
| iOS IPA | ❌ Windows 上不可能，必须 macOS + Xcode（iOS 工程不随本仓库发布） |

### 这一轮新增的东西

- `tools/build_exe.py` —— 绕开 `flet pack` 中文产品名的编码 bug（GBK vs UTF-8，
  PyInstaller 会 `UnicodeDecodeError` 直接崩）
- `core/mobile_runner.py` —— 手机端 Pyodide 的「本地 HTTP 桥」。
  flet 0.23 没有 `page.run_js`，只能靠 127.0.0.1 小服务把代码送进 WebView
- `assets/pyodide/package/`（12.2 MB）—— 离线 Pyodide，
  jsdelivr 在国内不通，改从 npm 下，**断网也能跑代码**
- 作者本机的 `完善/` —— 可行性报告、UI 评价、使用说明、13+ 张真机截图（未随仓库发布）

### `requirements.txt` 里为什么没有注释

**别往里加 `#` 注释行。** flet 0.23 的 `flet build apk` 会把
requirements.txt 的**每一行当命令行参数**传给 `pip install`，**不过滤 `#` 注释**，
于是中文注释会变成一个叫「甘肃省信息技术会考学习软件」的包名，报错：

```
ERROR: Invalid requirement: '# 甘肃省信息技术会考学习软件 —— Python 依赖清单'
```

依赖清单的说明文字写在 README 这一节。依赖本身只有两条：

| 依赖 | 版本 | 用途 |
|---|---|---|
| `flet` | `==0.23.0` | 界面框架。**版本必须钉死**——曾被 `pip install flet-desktop` 意外升到 1.0.2，API 全变，回滚才恢复 |
| `pyinstaller` | `>=6.6` | Windows 端打包 exe 用，只做调试可以不装 |

### 这一轮修掉的 6 个 UI bug

全是**真机点按钮 + 看截图**才发现的，单元测试抓不到：

1. `_sync()` 按行数重算代码区高度，把「运行状态 + 运行结果」挤出卡片
   → **学生点「运行代码」看上去一点反应都没有**（最严重）
2. 高度预算 `INNER_CHROME_PX` 漏算按钮换行（按 1 排算、实际 2 排），
   运行结果框被顶出卡片
3. 结果框没设 `STRETCH`，宽度只有约 100px
4. 窄屏下标题「示例代码 · 2_4.py」竖着一个字一行
5. `ft.Container` 用了 flet 0.23 不存在的 `scroll` 参数
6. 窄屏按 40/30/30 硬压高度，运行结果区被挤没

已补 3 条回归断言钉住高度预算（`tools\ui_smoke_test.py`），
并把一个过期的单测改成适配新的 Pyodide 桥架构（27 项全过）。

### 质量现状

作者本机的 `完善\check_all.ps1`：每棵树 × 4 项检查 = **全绿，失败 0**（脚本留在本机，未随仓库发布）。
