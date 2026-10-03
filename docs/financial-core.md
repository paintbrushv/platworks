# Financial core candidate

The price-search calculation now comes from `engine.backsolve.backsolve_price`.
The engine CLI, engine MCP, agent, and umbrella use that one public API.
`underwrite_backsolve` requires a versioned policy and a benchmark with rate,
as-of date, and source. No Treasury rate is assumed. Example tool arguments:

```json
{"target_coc_pct":7,"policy":{"version":"plat.backsolve-policy/1","strategy":"cashflow"},"benchmark":{"rate":"0.04","as_of":"2026-10-03","source":"synthetic:example"}}
```

Also provide `inputs`, a canonical deal with an explicit property-tax policy.
The example rate is synthetic. Use reviewed assumptions for a real deal.
Responses distinguish `converged`, `ceiling_feasible`, `infeasible`, and
`iteration_limit`, with the actual bracket and effective assumptions.
`iteration_limit` contains a feasible candidate, not a solved maximum.
See the producer's [API contract](https://github.com/paintbrushv/plat-multifamily-underwriting/blob/main/docs/BACKSOLVE_API.md).

## Operating calculations

The former independent Python implementation has been removed.
`platworks.ops_oracle` now invokes `boxscore-exact protocol` with a 60-second
timeout. Each output pipe is limited to 16 MiB while reading; excess stdout
or stderr terminates the child without buffering further output. It validates
`plat.ops/1`, decimal money, the input hash, and producer
identity. Missing binaries, timeouts, invalid precision, overflow, and
unsupported contracts produce typed failures. The host controls the executable;
MCP clients cannot supply executable paths or arguments.

Each call hashes and executes a private temporary copy of the producer, then
removes it. A concurrent replacement of the configured binary cannot change
the bytes executed after the integrity check. The host's temporary directory
must permit local executable files.

The analysis extra installs the native producer wheel. The bridge locates its
executable through installed distribution metadata, even when the scripts directory
is outside PATH. A host may explicitly override it for a reviewed source build:

```bash
export PLAT_BOXSCORE_EXACT_BIN=/absolute/path/to/boxscore-exact
# Optional deployment integrity pin:
export PLAT_BOXSCORE_EXACT_SHA256=SHA256_OF_THAT_BINARY
```

When using an override, pass it in your MCP launcher's `env` configuration too.
Installed analysis wheels need no override. The umbrella response includes
binary SHA-256, protocol version, input SHA-256, and `checked_i64_cents` provenance.

The exact CLI supports canonical CSV/JSON imports, occupancy reconciliation,
immutable reports, linked corrections, and reviewed migration into a new
SQLite copy. See [exact workflow and migration](https://github.com/paintbrushv/plat-operations/blob/main/docs/EXACT_CENTS.md).

`ops_review` now uses harness contract `ops-review/2.0.0`. Python hosts may bind
an exact database with `db_path`; MCP's default remains the packaged synthetic
snapshot. The harness verifies exact revision hashes and does not infer mapping
approval. Legacy REAL databases remain a read-only compatibility path. The Rust
bridge refuses subcent legacy money and sign ambiguities that the older result
shape cannot disclose. Run reviewed migration to resolve those cases.

## Remaining release gates

The packaging candidate aligns MCP 2, provides an exact analysis dependency set,
ships native producer wheels, and runs doctor plus installed-workflow checks.
See [installation and verification](installation.md) for the platform matrix,
locks, and source pins. Cargo metadata now matches the Apache-2.0 root license.

Original-file review and human approval flows, library and assistant-host
acceptance, pilots, and package publication remain release work. General legacy
`boxscore` features remain excluded from the exact-cent workflow.
