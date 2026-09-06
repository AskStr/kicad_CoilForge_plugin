# Unified PCM packaging and online release contract

[简体中文](packaging.md) · [Installation](installation.en.md) · [Documentation index](README.md)

## Build

```text
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python package_plugin.py
```

Default output: **`dist/kicad_CoilForge_plugin-v0.2.8-PCM.zip`**, one archive for KiCad 6–10.99.
`jsonschema` is a development/build dependency, not a plugin runtime dependency.
`--runtime swig` and `--runtime ipc` remain runtime-specific diagnostic builds, not the default user
release workflow. `--include-tests` includes diagnostic sources, not a standalone test environment.

## Installed layout and runtime

```text
metadata.json                         PCM root metadata; not extracted into the plugin
plugins/
  __init__.py                         PCM shim injected from pcm/entrypoint.py
  kicad_spiral_plugin.py               Existing ActionPlugin wrapper
  plugin.json                         IPC discovery manifest
  ipc_plugin.py                       Existing IPC startup entrypoint
  requirements.txt                    IPC dependencies
  coilforge/                          All core modules, both UIs and algorithms
  assets/                             Existing toolbar resources
  LICENSE                             License
```

PCM places the contents of `plugins/` in its managed `plugins/com_github_askstr_kicad-coilforge-plugin/`.
There is no extra package-name wrapper or nested `plugins/`. Development caches and tests are excluded
by default. The manual-install source `__init__.py` is unchanged; only PCM builds inject runtime selection:

- KiCad 6–8: register the original ActionPlugin.
- KiCad 9/10.0: register ActionPlugin with the API disabled; otherwise leave discovery to IPC.
- IPC-only hosts (10.99): safely skip legacy registration when pcbnew is unavailable; use `plugin.json`.
- Restart the editor after API changes. IPC still requires `_tkinter`; its Tk UI is not replaced.

### Metadata accepted by old PCM and IPC-only hosts

The unified package uses the PCM v1 root schema with `runtime: ipc`, `kicad_version: 6.0` and
`kicad_version_max: 10.99` in the version entry. KiCad 6–8 v1 readers permit and ignore the extension;
9/10 support IPC; 10.99 requires the IPC runtime. This metadata does not make KiCad 6 execute IPC:
the traditional discovery files remain. Builds validate against both official PCM v1 and v2 schemas
without weakening either schema.

PCM uses the older `GPL-3.0` license label accepted by KiCad 6; the actual `LICENSE` is unchanged.
The optional PCM `resources/icon.png` is not included; the existing toolbar icon is preserved.

## Versions, identifiers and reproducibility

`coilforge/metadata.py` is the source of truth:

- `PLUGIN_VERSION`: currently `0.2.8`, used in the UI, filename and PCM version.
- `PCM_ARCHIVE_BASENAME`: unified filename including `-PCM`.
- `PCM_PACKAGE_IDENTIFIER` / `IPC_PLUGIN_IDENTIFIER`: the stable
  `com.github.askstr.kicad-coilforge-plugin`; do not change it for updates.
- `MIN_LEGACY_KICAD_VERSION` / `MAX_PCM_KICAD_VERSION`: unified range `6.0`–`10.99`.
- Older runtime-specific minimum/maximum constants serve diagnostic builds, not the unified range.
- `LEGACY_IPC_PLUGIN_IDENTIFIER`: existing settings compatibility only, never the new manifest identity.

`plugin.json` must agree with the identifier constants; mismatches fail rather than being silently fixed.
The template owns author, description, license and links; the builder adds versions and actual
`install_size`, excluding root metadata that PCM does not extract. Status remains `testing`.
Omitting `platforms` disables platform filtering; it is not a claim of testing all platforms.

Builds check required files, official PCM/IPC schemas, reverse-DNS identifiers, action uniqueness and
resource paths. Entry order, ZIP timestamps, attributes, paths and compression settings are fixed;
the output is atomically replaced only after success. Identical source bytes and Python/zlib tools
produce identical bytes; different compression tools or source line endings may change the hash.
See [schema snapshots, sources and hashes](../pcm/schemas/README.md).

## Generate the online repository

Build the ZIP first, then generate external indexes. Never insert the ZIP's own hash into that ZIP.
Run this command from the repository root:

```text
python package_repository.py --archive dist/kicad_CoilForge_plugin-v0.2.8-PCM.zip --output pcm/repository --base-url https://raw.githubusercontent.com/AskStr/kicad_CoilForge_plugin/main/pcm/repository --download-url https://github.com/AskStr/kicad_CoilForge_plugin/releases/download/V0.2.8/kicad_CoilForge_plugin-v0.2.8-PCM.zip
```

This tool only writes local files; it does not upload, contact the network or modify KiCad settings.

| File | Contents |
|---|---|
| `packages.json` | Package metadata, release history, direct download URLs, exact sizes and SHA-256 hashes |
| `repository.json` | Repository name, maintainer, packages URL/hash and UTC update time/timestamp |

- Both indexes validate against PCM v1/v2. HTTP(S) URLs must not contain credentials or fragments.
- Existing output `packages.json` is merged by default; `--previous-packages` supplies explicit history.
- Versions sort numerically with epoch and retain history, not lexicographically (`0.2.9` vs `0.2.10`).
- Previously listed version bytes are immutable. A changed ZIP hash is rejected with a request to bump `PLUGIN_VERSION`.
- Unchanged content retains its timestamp. Changed content advances it even if the clock moves backward.
- `--timestamp` fixes a Unix timestamp for reproducibility; changed content rejects a non-increasing value.
- All validation precedes writes. Each index is atomically replaced, the root index last. This is not a
  cross-file transaction: refresh again after a transient publication mismatch; never disable hash checking.

### Publish and release subsequent updates

1. For this first unified release, build and test the final ZIP; do not substitute an older split archive.
2. Upload it as an asset of GitHub Release `V0.2.8`, matching the direct download URL in the index.
3. Generate/verify both indexes and publish them together under `pcm/repository/` on `main`.
4. Users add the `repository.json` URL to PCM and install from that repository.
5. For later releases, increment `PLUGIN_VERSION`, update documentation examples, build the new ZIP,
   and regenerate using the new tag/download URL while retaining index history. Never reuse a version.
6. Publish the ZIP before updating indexes, so clients do not discover an unavailable download.

URLs in generated files are publication targets, not proof that remote files already exist. This change
does not create a remote release, upload assets or push the repository. Never publish the QA-only
`0.2.9` fixtures under `.tmp` as real releases.

PCM selects updates by version, compatibility and stability. Existing `testing` installations can follow
subsequent `testing` or more stable releases; do not expect `stable` users to receive a less-stable release.
A local-file install is not automatically an online-repository install. See [installation](installation.en.md)
for repository association and KiCad 6's manual upgrade limitation.

## Release acceptance

```text
python -m unittest discover -s tests -v
python package_plugin.py --output dist/verify-a.zip
python package_plugin.py --output dist/verify-b.zip
python -c "import hashlib,pathlib; a=pathlib.Path('dist/verify-a.zip').read_bytes(); b=pathlib.Path('dist/verify-b.zip').read_bytes(); assert a==b; print(hashlib.sha256(a).hexdigest())"
```

Regressions cover layout, preservation of all core modules, runtime selection, no IPC/Tk dependency
on the legacy path, UTF-8, invalid manifests, write-failure protection, hashes/sizes, history, numeric
versions, immutable releases and update timestamps. See the [native version matrix and remaining work](installation.en.md#verification-boundary-september-6-2026).

Before marking releases `stable`, also verify real update application, settings retention, uninstall,
board generation and undo/redo across target platforms. Passing unit tests or update discovery does
not imply the entire update application workflow was tested.

## Primary specifications

- [KiCad Add-on Packages / PCM](https://dev-docs.kicad.org/en/addons/)
- [KiCad IPC add-on development](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [PCM v1 schema](https://go.kicad.org/pcm/schemas/v1) / [PCM v2 schema](https://go.kicad.org/pcm/schemas/v2)
- [IPC v1 schema](https://go.kicad.org/api/schemas/v1)
- [KiCad 6.0.11 PCM state and repository caching](https://github.com/KiCad/kicad-source-mirror/blob/6.0.11/kicad/pcm/pcm.cpp)
- [KiCad 10.0.4 PCM installation](https://github.com/KiCad/kicad-source-mirror/blob/10.0.4/kicad/pcm/pcm_task_manager.cpp)
