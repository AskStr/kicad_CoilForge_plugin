# PCM IPC 打包与发布规范

[English](packaging.en.md) · [安装说明](installation.md) · [文档索引](README.md)

## 构建

在完整源码目录执行（Python 3.10+）：

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python package_plugin.py
```

当前版本输出：`dist/kicad_CoilForge_plugin-v0.2.7.zip`。

```text
python package_plugin.py --output dist/custom-name.zip
python package_plugin.py --include-tests --output dist/coilforge-diagnostic.zip
```

- 默认包仅包含运行文件和许可证。
- `--include-tests` 保留为诊断选项，只附带测试源码供查看，**不是独立开发/测试环境**。
  运行测试应使用完整源码仓库；正式发布不使用该选项。
- 构建/测试依赖 `jsonschema`，运行时 `requirements.txt` 不依赖它。
- 开发依赖安装完成后，构建及 Schema 校验不请求网络，不自动跟随 `$schema` 下载文件。
- `pcm/metadata.template.json` 是模板，不是可直接安装的完整元数据。

## ZIP 契约

```text
kicad_CoilForge_plugin-v<version>.zip
├── metadata.json
└── plugins/
    ├── plugin.json
    ├── ipc_plugin.py
    ├── requirements.txt
    ├── LICENSE
    ├── assets/
    │   └── coilforge.png
    └── coilforge/
        ├── __init__.py
        ├── metadata.py
        ├── ipc_backend.py
        ├── ipc_ui.py
        └── 其他运行模块
```

- `metadata.json` 必须在 ZIP 根目录，包含且仅包含本次发布的一个版本。
- `versions[0].runtime` 必须为 `ipc`；`plugin.json` 的 `runtime.type` 为 `python`。
- 不再使用旧的 `kicad_CoilForge_plugin/` 顶层包装，也不预先插入包标识符子目录。
- PCM 将 `plugins/$contents` 安装到第三方目录的 `plugins/$clean_package_id/$contents`，
  其中包标识符中的点替换为下划线。
- `entrypoint` 和图标相对于安装后的插件根目录解析。构建器检查它们存在且不越界。
- 默认包排除根目录传统注册入口 `__init__.py`、`kicad_spiral_plugin.py`，避免双运行时注册。
  `coilforge/` 内保留的传统模块为被动模块，不会因 IPC 导入自动注册。
- 文档、构建器、Schema、开发依赖、缓存、虚拟环境和个人设置不进入默认 ZIP。
- PCM 的 `resources/icon.png` 为可选 64×64 展示图。本版不附带该资源；现有 32×32
  IPC 工具栏图标保持原样，不冒充 PCM 展示图标。

## 元数据与标识符

`coilforge/metadata.py` 是版本和标识符的单一来源：

| 常量 | 用途 |
|---|---|
| `PLUGIN_VERSION` | 插件版本、ZIP 文件名与 PCM 版本项 |
| `PACKAGE_IDENTIFIER` | 兼容保留的文件名/传统目录名称，不是 PCM 标识符 |
| `PCM_PACKAGE_IDENTIFIER` | `com.github.askstr.kicad-coilforge-plugin` |
| `IPC_PLUGIN_IDENTIFIER` | 与 PCM 标识符相同，满足严格 reverse-DNS 检查 |
| `LEGACY_IPC_PLUGIN_IDENTIFIER` | 仅用于寻找旧设置，不写入新运行清单 |
| `MIN_KICAD_VERSION` | 当前目标为 `10.0` |

源码 `plugin.json` 的标识符需要与常量一致，构建时不静默改写它；不一致直接报错。
更新版本仅修改 `PLUGIN_VERSION`，同时更新文档中的当前产物示例和兼容性记录。

模板维护说明、作者、许可证、资源链接和标签。构建器注入名称、标识符和版本信息，
并计算 `install_size` 为实际解包运行文件的未压缩字节数，**不计 PCM 不解包的根元数据**。

当前包状态为 `testing`，没有声称所有平台已经验证。未填写 `platforms` 不代表所有平台
实机通过；它表示没有人为进行平台过滤。具体测试矩阵见[安装文档](installation.md)。

归档内的版本项不包含 `download_url`、`download_size`、`download_sha256`。将来接入在线
仓库时，在 ZIP 构建完成后，为**外部仓库元数据**生成这些值；不要把 ZIP 自身的哈希回填
进 ZIP，否则会形成自引用。当前修复不创建在线仓库，也不发布到远程。

## 校验及失败行为

每次构建都会：

1. 检查必需运行文件并读取发布内容。
2. 按官方 IPC v1 Schema 校验 `plugin.json`。
3. 补充检查严格 reverse-DNS 标识符、Python 运行时、非空/不重复动作及引用文件。
4. 生成根元数据，按官方 PCM v2 Schema 校验。
5. 以排序条目、固定 ZIP 时间戳、Unix 文件属性、POSIX 路径和固定压缩级别构建临时 ZIP。
6. 全部成功后原子替换输出文件；验证失败或写入失败不破坏已有发布文件，并清理临时文件。

官方快照与来源记录位于 [pcm/schemas/README.md](../pcm/schemas/README.md)。升级 Schema
需要显式核对变化、更新来源/哈希，并运行正向与负向测试，不能用放宽规则来绕过失败。
在相同 Python/zlib 和相同输入字节下构建可重复；不同工具链压缩版本或源码换行可能导致
不同哈希，不能仅凭时间戳相同宣称跨任意工具链字节一致。

## 发布验收

### 自动检查

```text
python -m unittest discover -s tests -v
python package_plugin.py --output dist/verify-a.zip
python package_plugin.py --output dist/verify-b.zip
python -c "import hashlib,pathlib; a=pathlib.Path('dist/verify-a.zip').read_bytes(); b=pathlib.Path('dist/verify-b.zip').read_bytes(); assert a==b; print(hashlib.sha256(a).hexdigest())"
```

测试覆盖官方 Schema、元数据一致性、文件布局、隔离安装目录导入、UTF-8 描述、资源路径、
版本和设置兼容、确定性构建、坏清单拒绝，以及写入失败时保护旧产物。

### 实机检查

- [ ] 在干净或隔离配置中，使用 PCM 的“从文件安装”，不能仅手动解压后宣称安装通过。
- [ ] 确认已安装包信息及路径正确，重启后仍被发现。
- [ ] 让 KiCad 完成 Python 环境准备，并从真正的 IPC 入口打开界面。
- [ ] 在临时 PCB 上生成线圈，检查图形、分组、撤销/重做；不使用生产设计验收。
- [ ] 使用同标识符的新版本包验证升级，确认旧设置未丢失。
- [ ] 验证卸载清理运行文件，设置/方案保留策略符合预期。
- [ ] 按目标操作系统和完整 KiCad 版本记录结果，再决定是否改为 `stable`。

已完成与未完成项以[安装文档的验证记录](installation.md#已验证范围2026-09-06)为准。
不要因单元测试通过就把以上所有项目视为已完成。

## 规范依据

- [KiCad Add-on Packages / PCM](https://dev-docs.kicad.org/en/addons/)
- [KiCad IPC 插件开发说明](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [PCM v2 Schema](https://go.kicad.org/pcm/schemas/v2)
- [IPC v1 Schema](https://go.kicad.org/api/schemas/v1)
- [KiCad 10.0.4 PCM 安装实现](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/kicad/pcm/pcm_task_manager.cpp)
- [KiCad 10.0.4 设置路径处理器](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/common/api/api_handler_common.cpp)
