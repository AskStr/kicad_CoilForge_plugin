# 调研发现

- 旧 v0.2.6 ZIP 缺根目录 metadata.json，所有条目位于自定义顶层目录，PCM 无法安装。
- 官方 PCM 解包将 plugins/$contents 映射到第三方目录/plugins/$clean_package_id/$contents，包 ID 的点替换为下划线。
- PCM runtime 位于版本项，必须为 ipc；plugin.json runtime.type 仍为 python。
- PCM v2 与 IPC v1 的 identifier 规则不同，旧设置路径需保留兼容；清单 ID 不能只依赖 Schema 的宽松规则。
- 本机 KiCad 10.0.4、10.99.0 的两份 Schema 字节相同。官方 Schema 含根 $ref，可直接完整校验。
- 官方文档：dev-docs.kicad.org/en/addons/ 和 en/apis-and-binding/ipc-api/for-addon-developers/，2026-09-06 核对。
- PCM icon.png 是可选 64x64 图；现有工具栏图标 32x32，不冒充 PCM 图标。
- 官方要求归档内不含 download_*；离线安装 ZIP 不代表首次 Python 依赖安装无需网络。
- kicad-python 0.7.1 已在本机安装；后端使用 enabled layers、commit、create items、settings path API。

## 实机补充发现
- 10.0.4 common/api/api_handler_common.cpp 在合法 ID 条件分支错误地返回 invalid；master 已修正。
- master common/api/api_plugin.cpp 的严格 reverse-DNS 规则禁止下划线，比 IPC v1 Schema 严格。
- Windows 10.0.4 与 10.99.0-2335-g1899bad41c 均成功连接 IPC；发布包代码完成设置路径、8 arcs/group、8 bounding boxes、69 多层对象真实写板。
- 首次 10.99 隔离启动被新配置向导阻塞，补齐隔离 design-block-lib-table 后恢复。
- 首次多层 QA 参数内半径不足；仅修正测试输入至 5mm 后通过，未修改几何校验。
- 10.0.4 原生 PCM 从文件安装成功，21 个实际运行文件与 ZIP 字节一致；完整重启发现、升级卸载和端到端 UI 不宣称全部验收。
