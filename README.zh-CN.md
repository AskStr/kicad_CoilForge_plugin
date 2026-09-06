# CoilForge v0.2.6

KiCad PCB 线圈与平面电机绕组生成插件，作者 **askstar / 问星**。

CoilForge 同时支持传统 KiCad `pcbnew` ActionPlugin 和 KiCad IPC 插件入口，可生成普通平面螺旋线圈、多层串联线圈、磁极线圈以及环形扇区 PCB 电机定子绕组。

## 主要能力

- **固定 65% / 35% 工作区**：左侧参数区保持 65%，右侧示意图区保持 35%；参数刷新不会挤压预览区，图形始终按完整可见包络居中缩放。
- **场景化引导流程**：根据应用动态保留必要步骤；设计目标、工艺、尺寸、排列、层叠与输出不会强制固定为七步。
- **分步锁定**：进入下一步后，前一步参数成为硬约束。后续自动求解只能调整未锁定参数；返回前一步后才会解除该步及后续步骤的锁定。
- **动态显隐**：根据普通线圈/电机线圈、设计依据、层数和“显示高级参数”状态，只显示当前真正相关的配置项。
- **防干涉电机阵列**：椭圆、跑道形和梯形阵列按相邻线圈旋转后的支撑包络、铜箔宽度、净距及连接过孔/端子外伸量计算安全中心距，避免相邻磁极铜箔或连接端短接。
- **环形扇区电机绕组**：根据 PCB 外径、中心开孔、极对数/槽数、边缘退让、槽间隔和制板最小线宽/净距，自动计算扇区可用角度、节距、圈数与阵列半径，并尽量均匀铺满环形 PCB。
- **旋转/直线电机目标求解**：旋转电机使用母线电压、RPM 与转矩；直线电机使用母线电压、推力与直线速度。两者同时检查最大相电流、允许温升、星形/三角形接法及制造约束。
- **电气估算**：提供铜箔直流电阻、压降、铜损、相电阻、相电感、反电动势、所需相电流、所需线电压和初步温升载流能力估算。
- **用户常用方案**：可自定义名称保存、覆盖、加载和删除参数组合，且所有 KiCad 版本共享。
- **安全配置处理**：当前插件配置文件名为 `coilforge-settings.json`；文件不存在、损坏或内容非法时直接使用内置默认参数，不报错，也**不迁移旧插件配置**。
- **制造约束检查**：解析后的实际线宽、净距、过孔直径、钻孔与过孔退让均会再次校验。
- **多层与多后端**：支持 1–12 层、自动串联换层、过孔扇出、圆弧/线段图元，以及中英文界面。

> 电机、电感、温升和载流能力结果用于 PCB 前期方案比较，不替代磁场有限元、热仿真、样机测试和制造商 DFM/DRC。

## 快速使用

1. 选择应用类型。环形 PCB 电机请选择“电机 · PCB 环形扇区定子”。
2. 选择设计依据。旋转电机使用“电压／转速／转矩”，直线电机输入“推力／直线速度”。
3. 输入母线电压、目标转速、目标转矩、最大相电流和允许温升。
4. 选择 PCB 制造能力，确认最小线宽、最小净距、铜厚和过孔规则。
5. 输入 PCB 最大外径、中心开孔直径、极对数/槽数。插件会自动计算扇区线圈并尽量铺满。
6. 逐步检查右侧结果和警告；需要专业调参时再启用“显示高级参数”。
7. 设置铜层、网络和输出质量后创建，并在 KiCad 中运行 DRC。

## 配置与用户方案

- 当前设置文件：`<KiCad 配置目录>/plugins/CoilForge/coilforge-settings.json`
- 跨版本用户方案：`<KiCad 配置根目录>/plugins/CoilForge/coilforge-profiles.json`
- 配置缺失或损坏：回退到默认值，不弹出异常。
- 旧 `kicad_spiral_plugin/settings.json`：不会读取、复制或迁移。
- 用户方案采用安全 JSON 和原子替换写入；名称不区分大小写，避免重复。

详见 [配置说明](docs/configuration.md)。

## 项目目录

```text
assets/                 插件图标等发布资源
coilforge/               核心实现
  geometry.py            通用与环形扇区几何
  electrical.py          电阻、电感、反电动势与电机目标求解
  workflow.py            七步参数锁定和动态显隐
  preview.py             预览场景与居中缩放
  settings.py            设置与用户方案存储
  interface.py           wxPython 界面
  ipc_ui.py              tkinter/ttk IPC 界面
  ipc_backend.py         KiCad IPC 后端
docs/                    用户、设计和开发文档
tests/                   单元与回归测试
__init__.py              传统 ActionPlugin 注册入口
ipc_plugin.py            IPC 插件入口
kicad_spiral_plugin.py   传统入口兼容薄封装
package_plugin.py        PCM IPC 安装包构建与校验
plugin.json              KiCad IPC 插件清单
pcm/                     PCM 元数据模板与官方 Schema 快照
```

更多设计说明：

- [环形扇区线圈与电机求解](docs/motor-sector-design.md)
- [代码结构与工作流](docs/architecture.md)

## 安装

### KiCad IPC 插件（推荐）

**v0.2.7 起的发布 ZIP 是 PCM 安装包，不是源码压缩包。** 目标环境为 **KiCad 10.0+**、
已启用的 IPC API，以及带 **tkinter 的 Python 3.10+**。当前发布状态为 `testing`；
已验证范围及限制见[安装与兼容性说明](docs/installation.md)。

1. 下载发布附件 `kicad_CoilForge_plugin-v<version>.zip`，不要选择 GitHub 自动生成的 **Source code (zip)**。
2. 打开 KiCad 项目管理器 → **插件与内容管理器（PCM）** → **从文件安装…**，直接选择 ZIP，无需解压。
3. 在 **偏好设置 → 插件** 中启用 API 服务器，并选择可用的 Python 解释器。
4. 重启 PCB 编辑器、打开 PCB，从 IPC 插件入口或工具栏启动 **CoilForge**。

KiCad 管理插件的 Python 环境并安装 `requirements.txt`。首次准备依赖需要网络或预先配置的
包镜像；**从本地 ZIP 安装不等于依赖也可以完全离线安装**。`tkinter` 必须由所选 Python 提供，
不要尝试通过 `pip install tkinter` 安装。

### 传统 ActionPlugin

保留源码级兼容入口：将**完整源码目录**放入对应 KiCad 版本的 Python scripting 插件目录。
不要把新的 PCM ZIP 按传统目录包解压安装，也不要同时保留两份可加载的插件副本。
从旧包升级、设置保留和故障排查见[详细安装文档](docs/installation.md)。

## 开发与测试

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python package_plugin.py
```

当前输出为 `dist/kicad_CoilForge_plugin-v0.2.7.zip`。构建器先使用仓库内的 KiCad 官方 Schema
离线校验 PCM 元数据与 IPC 清单，再原子替换发布 ZIP；采用固定时间戳、排序和 POSIX 路径。
`jsonschema` 仅供构建和测试，不会加入 IPC 插件的运行时依赖。

包结构、标识符、可重复构建、发布验收和诊断参数见[打包与发布规范](docs/packaging.md)。

## License

见 [LICENSE](LICENSE)。


## Languages

- English: [README.md](README.md)
- 简体中文：本文件
- 双语文档索引：[docs/README.md](docs/README.md)
