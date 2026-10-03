# Candidate installation and verification

This change prepares packages for publication. Candidate versions are not yet
available on PyPI. No tag or upload is part of the build.

| Distribution | Candidate |
| --- | --- |
| platworks | 0.1.4 |
| plat-multifamily-underwriting | 0.1.2 |
| plat-costmodel | 0.1.1 |
| plat-harness | 0.1.1 |
| plat-operations | 0.1.1 |

## Two install profiles

`platworks` provides the catalog and MCP stdio server. `platworks[analysis]`
adds the exact producer versions above, packaged synthetic examples, ingestion
and PDF dependencies, and the native operating executable. The agent remains a
separate optional application with its own tested lock and producer identities.

Use Python 3.11 or 3.12. CI verifies Linux x86-64 (glibc 2.28+), macOS Intel,
macOS Apple Silicon, and Windows x64. Other architectures and Python versions
are outside this candidate's acceptance matrix. Source installation of
`plat-operations` requires a Rust toolchain and C build tools.

Acquire reviewed wheels from the candidate CI artifacts. The umbrella workflow
uploads `python-wheels`, one `native-<os>` artifact for each platform, and
`install-evidence-<os>-<python>` with hashes and probe results. Keep one compatible
native wheel and the four pure Python wheels in `wheelhouse/`.

For an ordinary candidate install in an activated fresh environment:

```bash
python -m pip install --only-binary=:all: --find-links wheelhouse 'platworks[analysis]==0.1.4'
python -m pip check
platworks doctor --analysis --json
python -I -m platworks.verify_install
```

For the exact tested dependency set, install the matching lock before local wheels:

```bash
python -m pip install --require-hashes --only-binary=:all: -r requirements-analysis.lock
python -m pip install --no-deps wheelhouse/*.whl
python -m pip check
```

The shell must expand `*.whl`; on PowerShell, pass the paths from
`Get-ChildItem wheelhouse/*.whl` instead. For a catalog-only environment use
`requirements-catalog.lock` and only the `platworks` wheel. Both locks contain
third-party registry hashes. Candidate wheel hashes are recorded separately in
each platform's installation evidence. Never mix artifacts from different runs.

## Doctor and workflow check

`platworks doctor` checks the catalog's versions, dependency graph, and MCP import.
`--analysis` also checks packaged schemas/examples, both standalone MCP adapters,
producer identity, the `plat.ops/1` contract, and a one-cent variance. `--json`
emits `plat.doctor/1`; exit 0 means ready, exit 2 means incomplete. Diagnostics
avoid private paths, environment values, and raw exceptions.

`python -I -m platworks.verify_install` uses only synthetic inputs. It calls real
stdio servers, compares public API/wrapper/MCP backsolve output, and checks
canonical operating import, integer cents, report issuance, a one-cent correction,
preservation of the original report, and harness review. Temporary files are
removed. It does not establish real-file acceptance or assistant-host support.

No producer path override is needed. Explicit `PLAT_BOXSCORE_EXACT_BIN` and
`PLAT_BOXSCORE_EXACT_SHA256` remain host configuration for reviewed deployments.
A broken installed producer refuses; it does not silently switch to another
PATH binary. The temporary directory must allow executable files.

## Reproduce CI

`release-sources.json` records immutable source commits for component builds.
With Python build tools installed, `python scripts/build_components.py` builds
pure Python components from those pins. Build the matching native wheel with
Maturin 1.15.0 from the recorded operations commit or use its CI artifact.

```bash
python scripts/clean_install.py --profile catalog --wheelhouse wheelhouse --output catalog-check.json
python scripts/clean_install.py --profile analysis --wheelhouse wheelhouse --output analysis-check.json
```

Each command creates a new environment and an empty working directory, clears
source overrides, installs hashed dependencies and exact wheel paths, checks
requirements, and records artifact hashes plus installed versions. The analysis
probe contains no source-tree fallback. CI runs both profiles on all eight
platform/Python combinations and the full umbrella suite on Linux.

To refresh locks after reviewing dependency changes, use `uv pip compile
pyproject.toml --python-version 3.11 --universal --only-binary :all:
--generate-hashes --no-header` for the catalog. Add
`--extra analysis --find-links wheelhouse` and `--no-emit-package` for each of
`platworks`, `plat-multifamily-underwriting`, `plat-costmodel`, `plat-harness`, and
`plat-operations` for the analysis lock. The Python floor is required: universal platform resolution alone does not
set the minimum Python version. Package metadata bounds cryptography to the compatible wheel line on Intel
macOS, so ordinary installs also avoid a local Rust build. Re-run the full clean-install matrix.

A release tag must equal the metadata version, use an unused PyPI version, and
pass CI before the workflow can upload the same tested artifacts. The umbrella
release additionally requires all exact analysis dependencies to be published on
PyPI with non-yanked wheels for every supported target. Publish the four producer
packages first; `python scripts/check_published_dependencies.py` verifies this
prerequisite and blocks the umbrella upload while it is incomplete. Publication
also needs the repository's configured PyPI trusted publisher/environment. After
publication, repeat the checks using registry downloads and compare hashes to
the reviewed evidence before announcing the release.
