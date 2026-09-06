# PCM IPC 打包与文档规范化

## 已确认目标
- 默认 ZIP 可由 KiCad PCM 从文件安装，符合 PCM v2 与 IPC v1 清单契约。
- 更新中英文安装、打包、升级、故障排查文档；保留原有 README 内容。
- 不改线圈算法和 UI；兼容旧 IPC 设置路径，传统入口仅供源码手动安装。

## 阶段
1. 官方契约核对：完成。
2. 构建器、元数据、Schema 与测试：完成。
3. 双语文档：完成。
4. 全量测试、产物与实机可行验证：完成（实际验证边界见 progress.md）。

## 决策
- 新版本 0.2.7；PCM ID 使用 com.github.askstr.kicad-coilforge-plugin。
- 目标 KiCad 10.0+，发布状态 testing；不宣称 KiCad 9 或所有系统实机通过。
- 构建时使用仓库内官方 Schema 离线校验；jsonschema 为开发依赖，不加入 IPC requirements.txt。
- 可选 PCM 展示图标暂不提供；原 IPC 工具栏图标不变。

## 实机验证后的调整
- KiCad 10.0.4 的 GetPluginSettingsPath 会拒绝合法标识符；仅对此系列及特定错误复用平台路径解析。
- 更新后的官方运行时严格检查不接受旧 IPC ID 的下划线，故统一新 PCM/IPC ID；不再坚持旧清单 ID。
- 旧设置按同级旧目录原位读取，新旧同时存在时新文件优先。不移动、删除或自动复制用户配置。
- 此为确保“可安装且能启动”必需的窄兼容修复，不改几何算法、UI 或共享方案格式。
