# 安装、兼容性与故障排查

[English](installation.en.md) · [文档索引](README.md) · [打包规范](packaging.md)

## 选择正确的文件

- **v0.2.7 及以后发布附件** `kicad_CoilForge_plugin-v<version>.zip`：PCM IPC 安装包。
- **v0.2.6 的旧 ZIP**：手动解压目录包，缺少 PCM 元数据，不能用于“从文件安装”。
- **GitHub Source code (zip)**：源码归档，也不是 PCM 安装包。需要解压后自行构建。
- **传统 ActionPlugin**：使用完整源码目录；不使用新的 IPC 安装包替代传统源码目录。

## 环境要求

| 项目 | 要求 |
|---|---|
| KiCad | 目标 10.0+；当前包状态为 `testing` |
| API | 在偏好设置的插件页面启用 IPC API 服务器 |
| Python | 3.10+，具备可用的 tkinter、venv 和 pip |
| Python 依赖 | `kicad-python>=0.7.1,<0.9`，由 KiCad 的插件环境管理 |
| 当前编辑器 | 打开 PCB 后启动；动作 scope 为 `pcb` |
| 首次依赖准备 | 可访问 Python 包源，或已有可用镜像/缓存 |

`plugin.json` 中的 Python `min_version` 不能替代实际环境检查。KiCad 的官方 Schema
说明该字段尚不用于强制检查，因此仍须选择合适的解释器。

### 已验证范围（2026-09-06）

- Windows：KiCad **10.0.4** 和 **10.99.0-2335-g1899bad41c** 随附的 PCM v2 / IPC v1
  Schema 均已校验；构建器使用的两份官方快照与这些文件字节相同。
- KiCad **10.0.4**：在隔离配置中，通过原生 PCM“从文件安装”安装新 ZIP，已逐字节核对
  全部 21 个运行文件的实际安装结果；正常关闭管理器后，`installed_packages.json`
  正确记录版本 `0.2.7`、`runtime: ipc` 和“本地文件”来源。
- 两个版本均使用发布 ZIP 解包后的代码完成真实 IPC 后端验证：连接、设置路径、网络、
  铜层、选择、8 段圆弧及分组、8 个边界框，以及含走线和过孔的 69 个双层对象。
- 完整工具栏启动到全部 UI 操作、升级/卸载完整流程，以及 macOS/Linux 实机尚未全部验收。
  不将以上测试解释为所有系统和所有 KiCad 版本均已通过。
- KiCad 8/9 不在本 IPC 包的兼容声明中。传统 ActionPlugin 的兼容性与 PCM IPC 分开判断。

## 通过 PCM 安装

1. 下载正确的版本化发布附件，或按[打包文档](packaging.md)构建。
2. 打开 **KiCad 项目管理器**，进入 **扩展内容管理器 / 插件与内容管理器（PCM）**。
3. 点击 **从文件安装…（Install from File…）**，直接选择 ZIP。不要提前解压或重新压缩。
4. 在 **偏好设置 → 插件** 中启用 API 服务器，并检查 Python 解释器。
5. 关闭并重新打开 PCB 编辑器，打开测试 PCB，等待插件环境准备完成。
6. 从 IPC 插件入口或工具栏启动 **CoilForge**。菜单名称可能随语言和 KiCad 版本变化。

安装器自行决定第三方安装目录。不要再手动添加一层包名称目录，也不要把包复制进
KiCad 自带 Python 的 `site-packages`。

### Python 环境

KiCad 根据 `plugins/requirements.txt` 管理 IPC 插件的虚拟环境。普通用户不需要安装
`requirements-dev.txt`，也不需要把 `jsonschema` 安装到插件环境中。

使用偏好设置中同一套 Python 的控制台解释器检查：

```text
python --version
python -c "import tkinter, venv, pip; print('Python prerequisites OK')"
```

Windows 上若偏好设置选择的是 `pythonw.exe`，检查命令应使用同目录的 `python.exe`。
Linux 上某些 Python 发行包不自带 Tk，需要用系统包管理器补齐；**不要运行
`pip install tkinter`**。依赖安装失败时，应先检查插件环境日志、解释器和网络，而不是反复重装 ZIP。

## 升级与设置

### 从旧的手动安装包升级

1. 关闭所有相关 PCB 编辑器，备份已有设置和用户方案。
2. 将以前手动安装的插件目录移出 KiCad 的插件搜索路径，避免两个 CoilForge 同时加载。
3. 用 PCM 安装新发布 ZIP；不要将新 ZIP 覆盖解压到旧插件目录。

### 标识符调整与旧设置

新 PCM 和 IPC 标识符统一为：

```text
com.github.askstr.kicad-coilforge-plugin
```

旧 IPC 标识符 `org.coilforge.kicad_spiral_plugin` 含下划线，虽然能通过旧 Schema，
却不符合更新后的 KiCad 运行时严格检查，因此不再用于新清单。

设置兼容行为：

- 正常使用 KiCad API 返回的新标识符设置目录。
- 若新目录下尚无 `coilforge-settings.json`，但同级旧标识符目录下存在该文件，则继续
  **原位读写旧文件**，不复制、不移动、不删除。
- 新旧文件同时存在时优先新文件；不会覆盖旧文件。
- 用户方案仍使用原有共享方案存储逻辑，不随本次标识符调整搬迁。
- 设置不保存在 PCM 安装目录中；不要为修复 ZIP 安装而清空配置目录。

KiCad 10.0 的设置路径 API 存在合法标识符校验反向的问题，本机 10.0.4 已复现。
插件仅在 **10.0 系列返回这一特定错误** 时，按 KiCad 官方目录规则解析设置目录，
包括 `KICAD_CONFIG_HOME`。其他 API 错误和连接错误继续上报，不会被静默掩盖。

### 卸载

通过 PCM 卸载新包，避免手动删除其记录。对旧手动副本的清理应单独进行。
设置与运行文件分离；若需要彻底清除个人数据，应先确认路径并备份，再由用户自行处理。

## 常见故障

| 现象 | 检查方法 |
|---|---|
| 提示缺少有效 `metadata.json` | 是否选了旧 v0.2.6 ZIP 或 GitHub 源码 ZIP；使用新发布附件 |
| 安装后找不到入口 | 确认 API 已启用、PCB 已打开、编辑器已重启；检查插件环境准备状态 |
| 提示 KiCad 版本不兼容 | 本包声明 10.0+；不要修改 ZIP 的版本字段绕过检查 |
| `No module named kipy` | KiCad 管理的插件环境依赖未装好；检查包源、代理和解释器 |
| `No module named tkinter` | 所选 Python 缺少 Tk；更换/补齐 Python 发行环境 |
| 连接拒绝或超时 | API 服务是否启用；从 KiCad 启动插件以取得正确的 socket/token |
| 合法标识符被拒绝 | 使用 v0.2.7+ 的兼容处理；若仍发生，记录 KiCad 完整版本及错误日志 |
| 同时出现两个 CoilForge | 检查旧手动 IPC/ActionPlugin 副本，而非反复安装新包 |
| 本地 ZIP 已安装，但依赖失败 | ZIP 不含 Python 或第三方 wheel；首次依赖准备不保证离线 |

报告问题请附：操作系统、KiCad 完整版本、ZIP 文件名、所选 Python 版本、错误文本，以及
问题发生在“PCM 安装”“插件发现”“依赖准备”还是“插件运行”阶段。不要公开 token 等敏感信息。
