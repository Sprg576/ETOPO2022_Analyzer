# ETOPO2022 Analyzer

基于 QGIS 的全球地形与海底地形分析桌面系统。支持地图浏览、单点查询、矩形裁剪、地形渲染、坡度/坡向、等值线、剖面、区域统计、多边形统计、A/B 区域对比、导出和工作状态保存。

## Windows 离线交付

发行包面向 Windows 10/11 x64，内置经过测试的 QGIS/Python 运行环境，不依赖目标设备的开发环境。

- `Start.cmd`：启动系统。
- `StartDemo.cmd`：打开合成示例地形。
- `Check.cmd`：执行实际分析与导出的环境自检，输出 JSON 报告。
- `Install.cmd`：安装到当前用户目录并创建桌面快捷方式，不覆盖已有版本。
- 同版本再次运行原始包的 `Install.cmd`：修复安装；安装失败后可以直接重试。
- 安装目录的 `Uninstall.cmd` 或 Windows“已安装的应用”：确认后卸载程序，保留用户输出和额外文件。

程序需完整解压后运行。全球 DEM 独立交付，通过“文件→打开栅格”加载。用户输出默认位于 `%LOCALAPPDATA%\ETOPO2022Analyzer\outputs`。

## 构建发行包

当前统一版本为 **1.0.0-rc2**。版本号只在 `src/etopo_analyzer/version.py` 中维护，构建读取此值并生成程序标题、启动器产品版本、发行目录与 `release.json`。构建参数 `-Version` 若与源码不一致会拒绝执行。当前交付入口见 `dist/release/CURRENT.txt`；旧 rc1 包保留作历史版本。

同版本安装默认使用 `%LOCALAPPDATA%\Programs\ETOPO2022Analyzer\1.0.0-rc2`，无需管理员权限。修复前关闭程序，从原始解压包运行安装；不接管无安装清单的目录。旧 rc1 便携目录需关闭后手动移除，不会被新版自动卸载。

在项目根目录使用 PowerShell：

```powershell
.\packaging\Build-Release.ps1 -RuntimeRoot D:\QGIS
```

`RuntimeRoot` 指向已验证的 QGIS LTR（Qt5/Python312）完整目录，不是通用的任意 QGIS 版本。构建会复制应用和运行环境、生成合成示例、执行独立路径自检及真实 Windows 窗口检查，最后生成 ZIP 与 SHA-256 文件。检查期间会短暂打开普通/示例窗口并自动关闭；后台隐藏启动器使用 Launcher.exe，主程序窗口正常显示。发布目录已存在时停止，避免覆盖交付成果。

`packaging/README.txt` 为运行包快速说明，`packaging/THIRD_PARTY.txt` 记录第三方组件来源。许可证、运行环境组件清单随包保留。

## 验证范围

退出系统或打开另一份工作状态时，若图层、参数、多边形或成果尚未保存，系统会提供“保存 / 不保存 / 取消”。取消选取保存路径或保存失败时保留当前工作。仅平移缩放地图、选择图层或切换结果页签不会触发提醒。工作状态保存数据引用，不会把源 DEM 复制进状态文件。

地图导出默认包含当前启用且已完成绘制的统计区、A/B 多边形，可在导出窗口取消勾选。PNG 保留半透明填充、边界、区域名称及图例；成果 `manifest.json` 保存 WGS84 多边形坐标与配色。预览与正式导出使用同一版式，未完成绘制或未启用的多边形不导出。

```powershell
.\tests\run_qgis_tests.ps1
```

本机独立路径测试不能替代跨设备验收。交付前应在无开发环境的目标电脑上运行 `Check.cmd`，保留成功报告，并人工检查地图交互、分析结果和文件导出。最终使用说明书、安装配置手册另行制作。
