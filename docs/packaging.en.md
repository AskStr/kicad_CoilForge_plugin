# PCM IPC packaging and release contract

[简体中文](packaging.md) · [Installation](installation.en.md) · [Documentation index](README.md)

## Build

From the complete source checkout, with Python 3.10+:

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python package_plugin.py
```

Current output: `dist/kicad_CoilForge_plugin-v0.2.7.zip`.

```text
python package_plugin.py --output dist/custom-name.zip
python package_plugin.py --include-tests --output dist/coilforge-diagnostic.zip
```

- The default archive contains runtime files and the license only.
- `--include-tests` retains the diagnostic option. It includes test sources for inspection, **not a
  standalone development/test environment**. Run tests from the complete checkout; do not publish this variant.
- `jsonschema` is a build/test dependency, absent from runtime `requirements.txt`.
- Once development dependencies are installed, builds and schema validation are offline; `$schema`
  does not trigger a download.
- `pcm/metadata.template.json` is a template, not complete installable metadata.

## Archive layout

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
        └── other runtime modules
```

- Root `metadata.json` contains exactly one version: this release.
- `versions[0].runtime` is `ipc`; the separate `plugin.json` runtime type remains `python`.
- Do not wrap everything in the old `kicad_CoilForge_plugin/` directory or pre-insert a package-id directory.
- PCM maps `plugins/$contents` to the third-party directory's `plugins/$clean_package_id/$contents`.
  Dots in the package identifier become underscores in the installation directory.
- Entrypoint and icon paths resolve relative to the installed plugin root; the builder checks their existence and safety.
- The source-root legacy registration files `__init__.py` and `kicad_spiral_plugin.py` are excluded.
  Passive legacy modules inside `coilforge/` do not register themselves on IPC import.
- Documentation, the builder, schemas, development dependencies, caches, virtual environments and
  personal settings are excluded from the default archive.
- PCM's 64×64 `resources/icon.png` is optional and is not included in this release. The existing
  32×32 IPC toolbar icon is retained unchanged, not repurposed as a PCM display icon.

## Metadata and identities

`coilforge/metadata.py` is the source of truth:

| Constant | Purpose |
|---|---|
| `PLUGIN_VERSION` | Runtime version, ZIP filename and PCM version entry |
| `PACKAGE_IDENTIFIER` | Historical filename/legacy directory name, not the PCM identity |
| `PCM_PACKAGE_IDENTIFIER` | `com.github.askstr.kicad-coilforge-plugin` |
| `IPC_PLUGIN_IDENTIFIER` | Same as PCM identity; satisfies strict reverse-DNS validation |
| `LEGACY_IPC_PLUGIN_IDENTIFIER` | Lookup of old settings only; absent from the new runtime manifest |
| `MIN_KICAD_VERSION` | Current target: `10.0` |

Source `plugin.json` must match the identity constant. The builder rejects drift rather than silently
rewriting the manifest. Change `PLUGIN_VERSION` for a release, then update current-output examples
and the compatibility record in documentation.

The template maintains descriptions, author, license, resource links and tags. The builder injects
name, identifier and version data. `install_size` counts uncompressed installed payload bytes,
excluding root metadata that PCM does not extract.

The release status is `testing`. Omitting `platforms` avoids artificial platform filtering; it does
not claim every platform has been tested. See the [verification matrix](installation.en.md).

Do not embed `download_url`, `download_size` or `download_sha256` in the archive's version entry.
For a future online repository, generate these in **external repository metadata after building**
the ZIP. Do not inject a ZIP's own hash back into that ZIP. This change does not create an online
repository or publish anything remotely.

## Validation and failure behavior

Each build:

1. Checks required runtime files and reads the release payload.
2. Validates `plugin.json` against the official IPC v1 schema.
3. Checks strict reverse-DNS identity, Python runtime, nonempty/unique actions, and referenced files.
4. Generates PCM metadata and validates it against the official PCM v2 schema.
5. Writes a temporary ZIP with sorted entries, fixed timestamps, Unix file attributes, POSIX paths
   and a fixed compression level.
6. Atomically replaces the output only after success. Validation/write failures preserve the previous
   release and clean up temporary archive files.

Pinned schemas and provenance are documented in [pcm/schemas/README.md](../pcm/schemas/README.md).
Review schema updates explicitly, update provenance/hashes, and run positive and negative tests.
Do not weaken validation to hide a failure.

Builds are reproducible for identical input bytes and the same Python/zlib toolchain. Different
compression-library versions or source line endings can change hashes; fixed timestamps alone do
not guarantee byte identity across arbitrary toolchains.

## Release checklist

### Automated checks

```text
python -m unittest discover -s tests -v
python package_plugin.py --output dist/verify-a.zip
python package_plugin.py --output dist/verify-b.zip
python -c "import hashlib,pathlib; a=pathlib.Path('dist/verify-a.zip').read_bytes(); b=pathlib.Path('dist/verify-b.zip').read_bytes(); assert a==b; print(hashlib.sha256(a).hexdigest())"
```

Tests cover official schemas, metadata consistency, installation layout, isolated imports, UTF-8
text, resources, version/settings compatibility, deterministic output, invalid manifests, and
preserving the previous artifact on write failure.

### Real KiCad checks

- [ ] Use native PCM **Install from File** in a clean/isolated configuration, not just manual extraction.
- [ ] Check installed package metadata/path and discovery after restarting.
- [ ] Allow managed Python setup to finish and open the UI through the actual IPC action.
- [ ] Generate on a disposable board; check geometry, grouping, undo and redo.
- [ ] Upgrade with the same identity and a newer version; retain existing settings.
- [ ] Uninstall and verify runtime removal and the intended settings/profile retention behavior.
- [ ] Record full KiCad and OS versions before deciding whether to mark the release `stable`.

See the [installation verification record](installation.en.md#verification-boundary-september-6-2026)
for completed checks and remaining gaps. Unit tests do not complete the whole checklist automatically.

## Official references

- [KiCad Add-on Packages / PCM](https://dev-docs.kicad.org/en/addons/)
- [KiCad IPC plugin development](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [PCM v2 schema](https://go.kicad.org/pcm/schemas/v2)
- [IPC v1 schema](https://go.kicad.org/api/schemas/v1)
- [KiCad 10.0.4 PCM installer](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/kicad/pcm/pcm_task_manager.cpp)
- [KiCad 10.0.4 settings-path handler](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/common/api/api_handler_common.cpp)
