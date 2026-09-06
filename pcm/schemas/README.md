# Official KiCad schema snapshots / 官方 Schema 快照

These are unmodified, vendored JSON schemas from the installed **KiCad 10.0.4** distribution
(`share/kicad/schemas/`), captured on **2026-09-06**. They also match the files shipped with the
locally checked **10.99.0-2335-g1899bad41c** build byte-for-byte.

文件为 KiCad 官方发行版内的原始字节，不是手写的简化 Schema。构建器使用本地快照做
Draft 7 校验，不访问网络。快照仅用于源码构建/测试，不进入默认发布 ZIP。

| File | Official schema ID | SHA-256 |
|---|---|---|
| `pcm.v2.schema.json` | `https://go.kicad.org/pcm/schemas/v2` | `74bfb8fca2abdcf619afd152f57bcc768c855541587e21b81e2c6e8fd3b8abb2` |
| `api.v1.schema.json` | `https://go.kicad.org/api/schemas/v1` | `70e4d3911a4e1cd7afdf296fdf038b5f45ec613fe66c6d34c717bb27311c15b0` |

Upstream sources:

- [PCM schema v2 source](https://gitlab.com/kicad/addons/metadata/-/blob/main/schema-v2.json)
- [IPC schema source at KiCad 10.0.4](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/api/schemas/api.v1.schema.json)
- [KiCad source license](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/LICENSE)

KiCad upstream material remains under its upstream licensing terms; the repository's own code
and distributed plugin are covered by the root `LICENSE`. Do not strip provenance when updating.

## Updating / 更新

1. Obtain schemas from a specific official KiCad release and record that full release/build.
2. Review changes, including differences between Schema validation and actual KiCad runtime validation.
3. Replace snapshots without modification and update the hashes and verification date above.
4. Run `python -m unittest discover -s tests -v` and `python package_plugin.py`.
5. Recheck native PCM installation and IPC behavior on the supported KiCad versions.

Runtime path existence, strict reverse-DNS identity, duplicate actions and the exact archive layout
are checked separately: schema validation alone does not establish installability or execution.
