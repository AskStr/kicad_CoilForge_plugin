# 统一 PCM 包与在线发布规范

[English](packaging.en.md) · [安装说明](installation.md) · [文档索引](README.md)

## 构建

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python package_plugin.py
```

默认产物：**`dist/kicad_CoilForge_plugin-v0.2.8-PCM.zip`**，一个文件用于 KiCad 6–10.99。
`jsonschema` 只用于开发/打包校验，不是插件的运行时依赖。
`--runtime swig` 和 `--runtime ipc` 仅保留为运行时专用诊断构建选项，不是面向用户的默认发布方案。
`--include-tests` 可带入诊断测试源码，但不构成独立测试环境。

## 安装布局与运行时

```text
metadata.json                         PCM 根元数据，不解包到插件目录
plugins/
  __init__.py                         由 pcm/entrypoint.py 注入的 PCM 注册入口
  kicad_spiral_plugin.py               原 ActionPlugin 薄封装
  plugin.json                         IPC 自动发现清单
  ipc_plugin.py                       原 IPC 启动入口
  requirements.txt                    IPC 依赖
  coilforge/                          完整核心模块（保留两套界面和算法）
  assets/                             原工具栏资源
  LICENSE                             许可证
```

PCM 将 `plugins/` 下的文件放入其管理的 `plugins/com_github_askstr_kicad-coilforge-plugin/`。
归档不含额外包名外层目录，不在插件下再次嵌套 `plugins/`。开发缓存、测试默认不入包。
手动安装的源码 `__init__.py` 不变；PCM 构建时才注入自动选择入口：

- KiCad 6–8：注册原 ActionPlugin。
- KiCad 9/10.0：API 关闭时注册 ActionPlugin；开启时留给原 IPC 发现，不重复注册。
- IPC-only 主机（10.99）：没有 pcbnew 时安全跳过传统入口，由 `plugin.json` 发现。
- 更改 API 设置后重启 PCB 编辑器；IPC 仍要求带 `_tkinter` 的解释器，不修改原 Tk UI。

### 同一元数据兼容旧 PCM 和 IPC-only 主机

统一包使用 PCM v1 根 Schema，并在版本项包含 `runtime: ipc`、`kicad_version: 6.0` 和
`kicad_version_max: 10.99`。KiCad 6–8 的 v1 读取器允许并忽略扩展字段；9/10 支持 IPC；
10.99 要求 IPC 运行时。该字段不意味着 KiCad 6 要运行 IPC，实际传统入口仍保留。
构建同时通过官方 PCM v1 和 v2 校验，不通过放宽 Schema 规避错误。

为兼容 KiCad 6 的旧许可证词表，PCM 显示值使用 `GPL-3.0`；实际 `LICENSE` 不变。
`resources/icon.png` 是可选 PCM 展示资源，本包未提供；原工具栏图标不变。

## 版本、标识符与可重复构建

`coilforge/metadata.py` 是版本及标识符的单一来源：

- `PLUGIN_VERSION`：当前 `0.2.8`，影响界面、包名和 PCM 版本。
- `PCM_ARCHIVE_BASENAME`：含 `-PCM` 的统一文件名。
- `PCM_PACKAGE_IDENTIFIER` / `IPC_PLUGIN_IDENTIFIER`：固定为
  `com.github.askstr.kicad-coilforge-plugin`，升级时不能改变。
- `MIN_LEGACY_KICAD_VERSION` / `MAX_PCM_KICAD_VERSION`：统一范围 `6.0`–`10.99`。
- 原运行时专用的最低/最高版本常量继续服务诊断构建，不决定统一包范围。
- `LEGACY_IPC_PLUGIN_IDENTIFIER` 仅用于原有设置兼容，不写入新运行清单。

`plugin.json` 必须与标识符常量一致，构建遇到不一致直接失败，不静默修正。
模板维护作者、说明、许可证和链接，构建器填写版本及实际 `install_size`（不含不解包的根元数据）。
当前状态为 `testing`，未声明所有平台实机验证。未指定 `platforms` 仅表示不做平台过滤。

构建检查必需文件、官方 PCM/IPC Schema、reverse-DNS 标识符、动作唯一性及资源路径。
条目排序、ZIP 时间戳、属性、路径和压缩参数固定；全部成功后才原子替换输出。
相同源码字节与 Python/zlib 工具链可生成相同字节；不承诺不同压缩工具链或源码换行产生同一哈希。
官方快照、来源和哈希见 [pcm/schemas/README.md](../pcm/schemas/README.md)。

## 在线仓库生成

先完成 ZIP，再生成外部索引，避免把 ZIP 自身哈希写回 ZIP 造成自引用。
下面命令在仓库根目录运行，PowerShell 可合并成一行：

```text
python package_repository.py --archive dist/kicad_CoilForge_plugin-v0.2.8-PCM.zip --output pcm/repository --base-url https://raw.githubusercontent.com/AskStr/kicad_CoilForge_plugin/main/pcm/repository --download-url https://github.com/AskStr/kicad_CoilForge_plugin/releases/download/V0.2.8/kicad_CoilForge_plugin-v0.2.8-PCM.zip
```

生成器只写本地文件，不上传、不联网、不改变 KiCad 配置：

| 文件 | 内容 |
|---|---|
| `packages.json` | 插件信息、版本历史及各版本的直接下载 URL、准确大小、SHA-256 |
| `repository.json` | 仓库名称、维护者、packages URL/SHA-256、UTC 更新时间及时间戳 |

- 两个索引都按官方 PCM v1/v2 校验，HTTP(S) 地址不能包含账户密码或片段。
- 默认合并输出目录已有 `packages.json`；可用 `--previous-packages` 指定原索引。
- 按数值版本与 epoch 排序并保留历史，不用字符串比较 `0.2.9` 与 `0.2.10`。
- 已发布同版本的 ZIP 字节不可改变；哈希不同时拒绝覆盖，并要求增加 `PLUGIN_VERSION`。
- 内容未变时保留时间戳；内容改变时递增，即使系统时钟回拨也不隐藏更新。
- `--timestamp` 可固定 Unix 时间戳以复现输出；改变内容时拒绝不递增的时间戳。
- 完整校验后分别原子写入索引，最后写根索引。两个文件不是跨文件事务；发布期间
  临时不一致应重试刷新，不应关闭哈希检查。

### 发布与后续更新

1. 首次发布当前版本：构建最终 ZIP 并完成测试。不要用旧的拆分包替代 `-PCM.zip`。
2. 将该 ZIP 作为 GitHub Release `V0.2.8` 的附件上传，确保直接下载地址与索引一致。
3. 生成/核对索引，将两个 JSON 一起发布到 `main` 分支的 `pcm/repository/`。
4. 用户在 PCM 添加 `repository.json` 地址并从该仓库安装。
5. 后续发布增加 `PLUGIN_VERSION`，更新文档示例，构建新 ZIP，并使用新 tag/下载 URL
   重新运行生成器，保留原索引作为历史；不要重复使用旧版本号。
6. 发布新的 ZIP 后再更新索引，以免 PCM 找到暂不可下载的更新。

当前生成文件中的 URL 是发布目标，不表示远程文件已经存在。本次工作未创建远程 Release、
未上传附件、未推送仓库。不要将 `.tmp` 中的 `0.2.9` QA 夹具当作正式版本发布。

PCM 按版本、兼容范围和稳定性选择更新。当前 `testing` 安装的后续版本可以保持 `testing`
或提升稳定性；不要指望已安装 `stable` 的用户收到稳定性较低的版本。
本地 ZIP 安装不自动等同于在线仓库安装；关联步骤和 KiCad 6 的手动升级限制见[安装说明](installation.md)。

## 发布验收

```text
python -m unittest discover -s tests -v
python package_plugin.py --output dist/verify-a.zip
python package_plugin.py --output dist/verify-b.zip
python -c "import hashlib,pathlib; a=pathlib.Path('dist/verify-a.zip').read_bytes(); b=pathlib.Path('dist/verify-b.zip').read_bytes(); assert a==b; print(hashlib.sha256(a).hexdigest())"
```

回归覆盖布局、所有核心模块保留、双运行时选择、旧版无 Tk/IPC 依赖、UTF-8、坏清单拒绝、
写入失败保护、哈希大小、仓库历史、数值版本、不可变版本和更新时间戳。
实际安装、工具栏启动与在线更新的版本矩阵及未完成项见[安装文档](installation.md#已验证范围2026-09-06)。

发布为 `stable` 前还应覆盖各平台真实更新应用、设置保留、卸载、临时 PCB 生成和撤销/重做。
不能把单元测试或发现更新通过等同于整个更新应用流程已经验收。

## 规范依据

- [KiCad Add-on Packages / PCM](https://dev-docs.kicad.org/en/addons/)
- [KiCad IPC 插件开发说明](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [PCM v1 Schema](https://go.kicad.org/pcm/schemas/v1) / [PCM v2 Schema](https://go.kicad.org/pcm/schemas/v2)
- [IPC v1 Schema](https://go.kicad.org/api/schemas/v1)
- [KiCad 6.0.11 PCM 状态与仓库缓存](https://github.com/KiCad/kicad-source-mirror/blob/6.0.11/kicad/pcm/pcm.cpp)
- [KiCad 10.0.4 PCM 安装实现](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/kicad/pcm/pcm_task_manager.cpp)
