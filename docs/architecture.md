# 代码结构与交互工作流

## 入口与核心包

- 根目录 `__init__.py`：传统 KiCad ActionPlugin 注册。
- 根目录 `ipc_plugin.py`：KiCad IPC Python 入口。
- 根目录 `kicad_spiral_plugin.py`：兼容导出薄封装。
- `coilforge/legacy_plugin.py`：传统运行时实现。
- `coilforge/ipc_ui.py` + `coilforge/ipc_backend.py`：IPC UI 与后端。
- `coilforge/geometry.py`：无 KiCad 依赖的几何和尺寸求解。
- `coilforge/electrical.py`：电气估算与目标搜索。
- `coilforge/workflow.py`：双界面共享的参数显隐和步骤快照锁定。

## 安装包与运行时边界

默认发布包为 PCM IPC ZIP：根目录 `metadata.json` 负责安装和版本信息，`plugins/plugin.json`
负责 IPC 运行配置。PCM 自动插入包标识符目录，入口的相对导入和图标路径保持不变。

`coilforge/metadata.py` 集中维护品牌、版本、统一的 PCM / IPC 标识符和旧设置标识符。
`package_plugin.py` 从 `pcm/metadata.template.json` 生成安装元数据，并使用
`pcm/schemas/` 的官方快照验证两份清单。构建工具及 Schema 不进入默认运行包。

源码根目录的传统注册入口不进入 IPC ZIP；核心包中保留的传统模块不会自动注册。
IPC 设置优先通过 `get_plugin_settings_path()` 获取路径；对 KiCad 10.0 的特定上游错误做
窄范围兼容，并保留旧设置原位读取能力，不写入 PCM 安装目录。
完整布局与发布边界见[打包规范](packaging.md)。

## 场景化步骤锁定

`WorkflowLocks` 为当前场景实际保留的步骤定义字段集合。向后进入新步骤时保存已完成步骤快照；自动推荐和电机求解读取 `fixed_values()`，不得覆盖这些字段。返回较早步骤时，`unlock_from()` 清除该步及其后的快照。

## 动态显隐

`parameter_visibility()` 根据应用、线圈形状、设计模式、层数和高级开关返回可见字段集合。wx 与 tkinter 两套界面只负责显示/隐藏控件，不各自复制规则。

## 预览布局

`ui_layout.py` 统一规定左侧 65、右侧 35 的宽度比例。wx 使用无可拖动分隔条并在尺寸事件中重新设置位置；tkinter 使用同一 uniform grid 组的 65/35 权重。`fit_preview_scene()` 对完整场景包络执行等比缩放和视觉居中。
