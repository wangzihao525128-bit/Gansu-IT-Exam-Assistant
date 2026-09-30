# assets 说明

打包时 flet 会自动收集本目录里的图片。

- `icon.png`：应用图标（1024×1024，PNG）。
  - Windows：`flet pack` 用它作为 exe 的图标；
  - Android：`flet build apk` 用它生成各分辨率的启动图标；
  - iOS：`flet build ipa` 用它生成 AppIcon 集合。
- 后续知识点讲解中的插图也放在这里，配合懒加载使用（需求文档 8.3）。
