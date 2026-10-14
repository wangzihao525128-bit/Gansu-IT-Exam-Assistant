# 插件目录（`plugins\`）

这个目录是**需求文档 8.4「预留插件化扩展接口」**的落点。

> 8.4 原文大意：知识点数据做成 JSON，方便只改数据就更新内容；
> 同时预留插件化扩展接口，后续要加工具、换交互，不用改主程序代码就能加进来。

**现在这个目录是空的（只有本说明文件），所以软件的行为和没这个接口时一模一样。**
一个插件都没装时，主程序不会往界面上加任何东西。

---

## 一、怎么加一个插件

1. 在这个目录下新建一个**子目录**，名字随便取（建议用英文，目录名会成为插件的默认 id）：

   ```
   plugins\
     README.md              <- 本文件
     my_tool\
       plugin.py            <- 入口文件，名字必须叫这个
   ```

2. `plugin.py` 里按需要写下面几样东西，**写一样算一样，全都可以不写**：

```python
# 可选：插件名片。不写就用目录名当名字、版本 0
PLUGIN = {
    "id": "my_tool",              # 留空则用目录名
    "name": "我的扩展工具",        # 显示在界面上的名字
    "version": "1.0",
    "description": "一句话说明这个插件干什么",
}

# 可选1：往题库里追加模块 / 知识点。
#        返回的结构和 data\knowledge_points.json 里的一模一样：
#        [{"id": "...", "name": "...", "color": "#4A90E2", "points": [ ... ]}]
def modules():
    return []

# 可选2：在知识点详情页「代码解释」下面追加一块自定义面板。
#        返回一个 flet 控件（ft.Container / ft.Text / ft.Column ... 都行）
def detail_panel(point, colors):
    import flet as ft
    return ft.Text("这里是我的面板")

# 可选3：主界面建好之后调用一次，可以做初始化、埋点等。
def startup(page):
    pass
```

3. **重启软件**（或调 `core.plugins.discover(force=True)`）即可生效。

打包成 exe 之后，把整个 `plugins\` 文件夹拷到 `GansuITExam.exe` 旁边就行，不用重新打包。

---

## 二、三条硬约定（接口里已经写死了，不是口头说说）

1. **插件只能「加」，不能「改」**
   `modules()` 追加的模块，如果 id 和官方 JSON 里的模块重名，会被**直接丢掉**并记一条日志。
   学生看到的教材内容永远以 `data\knowledge_points.json` 为准，插件顶不掉它。

2. **插件坏了不会带崩软件**
   加载失败、`modules()` 抛异常、`detail_panel()` 抛异常……每一步都单独 try，
   出问题就跳过那一个插件，其余功能和界面照常。
   被跳过的原因记在 `core.plugins.warnings()` 里。

3. **插件不在学生代码沙箱里**
   插件跑在**主程序进程**中，和 `knowledge_points.json` 是同一个信任级别：**只放老师自己信得过的代码**。
   反过来，学生在代码编辑器里写的任何东西都碰不到这里。

---

## 三、模块 / 知识点字段速查

写 `modules()` 时字段要和 `data\knowledge_points.json` 完全一致，字段表见
`tools\check_data.py` 的校验逻辑，简要如下：

| 层级 | 必填字段 |
| --- | --- |
| 模块 | `id` `name` `color` `points` |
| 知识点 | `id` `title` `content` `code_example` `code_explanation` `hints` `questions` |
| 练习题（公共） | `type` `question` `answer` `explanation` |
| 练习题（单选） | 另需 `options`；`answer` 是选项字母 |
| 练习题（判断） | **不用写 `options`**（程序补成「A. 正确 / B. 错误」）；`answer` 是 `"A"`（正确）或 `"B"`（错误） |
| 练习题（填空） | **不能有 `options`**；`answer` 是标准答案字符串，可选 `accept` 数组列其它等价写法 |

三种题型的例子：

```python
# 单选
{"type": "choice", "question": "……（ ）",
 "options": ["A. 甲", "B. 乙"], "answer": "B", "explanation": "解析"}

# 判断：A = 正确，B = 错误
{"type": "judge", "question": "……（ ）",
 "answer": "A", "explanation": "解析"}

# 填空：accept 里的写法判分时都算对
{"type": "fill", "question": "…… 是 ____ 。",
 "answer": "int", "accept": ["int()"], "explanation": "解析"}
```

补充说明：

* **不写 `type` 的题一律按单选处理** —— 历史题库里只有选择题，不用改；
* 单选 / 判断的 `answer` 填**选项字母**（`"B"`），不是下标；
* `options` 每一项要**自带序号前缀**，写成 `"B. 数据是……"`；
* **填空题的判分前会做归一化**（`core.knowledge_store.normalize_fill`）：
  全角转半角、去掉所有空格、转小写。所以 `ＩＮＴ（）`、`int ()`、`INT` 都算对。
  这是有意的取舍 —— 填空题考「知不知道填什么」，不是「记不记得大小写」。
  确实要区分大小写的题，请改用单选；
* 知识点里代码用到了 `input()` 的话，额外给一个 `sample_input`，
  编辑器才会多出「标准输入」那一行，否则学生在界面上没法喂数据。
  **多行输入用换行符 `\n` 分隔**（JSON 里写成 `"85\n8\n2024"`）。

字段缺了会被 `store.validate()` 抓出来，主界面会弹提示告诉老师是哪个插件的哪个知识点。

---

## 四、自测

`tools\check_plugins.py` 会在临时目录里造一个「好插件」和一个「故意报错的坏插件」，
断言好插件能被发现、能追加模块、坏插件被跳过且主程序不炸：

```powershell
cd gs_it_exam_windows
python tools\check_plugins.py
```