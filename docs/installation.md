# 安装、兼容性与故障排查

[English](installation.en.md) · [文档索引](README.md) · [打包与在线发布](packaging.md)

## 一个安装包，兼容 KiCad 6–10.99

所有版本使用同一文件：**`kicad_CoilForge_plugin-v0.2.8-PCM.zip`**。
保留 v0.2.6 已有的 ActionPlugin/wxPython 和 IPC/Tk 界面、线圈算法以及手动安装入口。
本次调整 PCM 布局、元数据和启动选择，不再要求用户下载两个运行时安装包。

| KiCad | 启动路径 | 环境要求 |
|---|---|---|
| 6、7、8 | 原 ActionPlugin / wxPython | KiCad 内置 pcbnew、wxPython；不需要 IPC 或 Tk |
| 9、10.0，API 关闭 | 原 ActionPlugin / wxPython | 同上 |
| 9、10.0，API 开启 | 原 IPC / Tk | API 可用，所选 Python 满足下面的 IPC 要求 |
| 10.99 | 原 IPC / Tk | 必须启用 API，并使用具备 `_tkinter` 的 Python |

PCM 专用注册入口根据 KiCad 版本和 API 设置选择运行方式，避免同时注册两套入口。
**更改 API 设置后必须重启 PCB 编辑器。** API 已开启但 Python 环境不完整时，应修复
该环境；不能期待自动切换到另一套界面。KiCad 4/5 和未来 KiCad 11 不在声明范围。

## 从文件安装

1. 关闭 PCB 编辑器。若之前安装过拆分包或 v0.2.7 包，先在 PCM 卸载旧包；
   移走可加载的手动副本以避免重复注册，不要删除用户设置。
2. 打开 KiCad 项目管理器 → **插件与内容管理器（PCM）** → **从文件安装…**。
3. 直接选择 `kicad_CoilForge_plugin-v0.2.8-PCM.zip`，不要解压、重新压缩或增加外层目录。
4. 重新打开 PCB 编辑器和一块 PCB，点击 CoilForge 工具栏图标。
   ActionPlugin 路径也提供 **工具 → 外部插件** 菜单，名称因版本/语言而异。
5. 老版若隐藏工具栏图标，可在 Action Plugin 管理中启用/刷新。

不要安装 GitHub 自动生成的 **Source code (zip)**，也不要把文件复制到 KiCad 的
`site-packages`。PCM 负责安装、更新和卸载目录。

## 在线仓库与更新

项目提供标准 PCM 仓库文件 `pcm/repository/repository.json` 与 `packages.json`。
**这些文件和 ZIP 必须先发布到对应地址，在线服务才可用；本次仅生成本地文件，未上传。**
发布后的仓库地址为：

```text
https://raw.githubusercontent.com/AskStr/kicad_CoilForge_plugin/main/pcm/repository/repository.json
```

1. 在 PCM 的 **管理仓库 / Manage** 中添加上述地址，然后刷新仓库。
2. 从该仓库安装 CoilForge，使安装记录与仓库关联。
3. 在提供此选项的 KiCad 版本中启用 PCM 更新检查；也可以手动打开 PCM 并点击 **刷新**。
4. **KiCad 7–10.99**：有更高且兼容、稳定性等级符合要求的版本时，PCM 提供更新操作。
5. **KiCad 6.0.11**：可以刷新仓库、取得新的版本列表，但原生 PCM 没有新版的更新状态/
   一键更新按钮。升级时关闭编辑器，在 PCM 卸载旧版本并从同一仓库安装新版；先备份用户设置。

“从文件安装”产生本地安装记录，不应假设它自动关联在线仓库。需要在线跟踪时，关闭编辑器，
在 PCM 卸载本地包后从该仓库重新安装。仅替换同名 ZIP 或同一个 `0.2.8` 版本的内容不会触发
版本更新；发布者必须增加版本号并刷新仓库索引。发布命令见[打包文档](packaging.md)。

## IPC Python 环境：包括 KiCad 10.99 的 `_tkinter`

保留原来已经正常工作的解释器。在提供相关选项的 **首选项 → 插件** 中启用 API，选择
Python 3.10+，它必须包含 `tkinter`、`_tkinter`、Tcl/Tk、venv 和 pip。
KiCad 还需要在管理的插件环境中准备 `kicad-python>=0.7.1,<0.9`，首次准备需要可用的
包索引、镜像或缓存。`_tkinter` 是 Python 的原生扩展，不是可以用 `pip install tkinter`
补上的普通依赖；不要混用不同 Python 版本的 DLL。

用 KiCad 所选解释器执行完整检查，而不仅测试 import：

```text
python -c "import tkinter as tk, _tkinter, venv, pip; r=tk.Tk(); r.withdraw(); print('Tk OK', r.tk.call('info', 'patchlevel')); r.destroy()"
```

如果设置的是 `pythonw.exe`，检查时使用同目录的 `python.exe`。切换解释器后重启编辑器，
确认 KiCad 已使用新解释器准备插件环境，然后再点击图标。

此前检查发现本机 KiCad 10.0.4 的内置 Python 缺少 `_tkinter`；旧 IPC 界面及其错误弹窗
都依赖 Tk，配合无控制台的 pythonw 就表现为“没有反应”。现在保留 Tk 界面，但启动失败时
提供本地化诊断和 Windows 原生错误提示，并显示实际解释器路径，不再依赖 Tk 报告 Tk 缺失。
KiCad 9.0.7/10.0.4 拒绝合法插件设置标识符的特定 API 错误也有定向兼容，其他错误仍上报。

## 已验证范围（2026-09-06）

使用 `D:\KiCad` 中的真实 Windows 程序、临时 PCB 和独立配置测试，未修改生产 PCB。
在线测试使用本机 HTTP 仓库，**不是已发布的 GitHub 服务**。

| 实际版本 | 同一 ZIP 的原生 PCM 在线安装 | PCB 工具栏启动 | 在线新版本检查 |
|---|---|---|---|
| 6.0.11 | 通过 | ActionPlugin 通过 | 新版本索引刷新通过；宿主无一键更新 |
| 7.0.11 | 通过 | ActionPlugin 通过 | 原生更新按钮通过 |
| 8.0.9 | 通过 | ActionPlugin 通过 | 原生更新按钮通过 |
| 9.0.7 | 通过 | API 关：ActionPlugin；API 开：IPC，均通过 | 原生更新按钮通过 |
| 10.0.4 | 通过 | API 关：ActionPlugin；API 开：IPC，均通过 | 原生更新按钮通过 |
| 10.99.0-2335-g1899bad41c | 通过 | IPC/Tk 通过 | 原生更新按钮通过 |

- 6.0.11、10.99 另通过原生 **从文件安装**、正常退出后安装记录保留、工具栏启动检查。
- 安装后的运行文件逐一与 ZIP 字节比对；在线安装记录保留仓库标识。
- 更新测试仅使用临时 `0.2.9` 夹具验证发现新版本；没有安装、上传或发布该测试版本。
- IPC 使用 Python 3.13.2、`_tkinter` 和 Tk 8.6.15；API 开启时未重复注册传统入口。
- KiCad 6–10.0 的内置 Python/pcbnew/wxPython 另有注册请求、窗口初始化及重复点击复用检查。
  独立 Python 测试拦截注册请求；真正 C++ 注册与工具栏启动由上表的原生编辑器验证。
- 单元测试覆盖双 Schema、布局、启动选择、失败诊断、设置兼容、仓库历史/哈希/时间戳等。
- `legacy_plugin.py`、`interface.py`、`ipc_ui.py`、`geometry.py`、`electrical.py`
  与 v0.2.6 保持一致。

以上是各版本系列的代表性 Windows 构建，不是每个补丁版本或 macOS/Linux 的实机承诺。
尚未完成各平台实际更新应用、卸载后数据保留、所有生成/撤销/重做操作的完整验收。
元数据继续使用 `testing`，不因安装测试通过就宣称全部功能已验证。

## 故障排查

- PCM 拒绝 ZIP：确认选择的是 `-PCM.zip`，根目录必须有 `metadata.json` 和 `plugins/`。
- 图标缺失/重复：重启编辑器，检查旧手动副本、API 设置和插件启用状态。
- IPC 图标尚不可用：等待环境准备完成，检查所选解释器、pip 网络及 API 状态。
- Tk 启动失败：运行上述完整 Tk 检查，并查看错误提示中的实际解释器路径。
- 在线仓库加载失败：确认发布已完成、URL 可访问、索引和 ZIP 哈希一致。
- 未提示更新：检查仓库关联、更高版本号、兼容范围及稳定性；KiCad 6 使用手动升级流程。

报告问题时提供完整 KiCad 版本、操作系统、安装方式、API 状态、解释器路径和错误信息。
