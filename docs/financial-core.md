# Financial core candidate: B2/B3

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

Build the reviewed operating producer and set these host environment variables:

```bash
export PLAT_BOXSCORE_EXACT_BIN=/absolute/path/to/boxscore-exact
# Optional deployment integrity pin:
export PLAT_BOXSCORE_EXACT_SHA256=SHA256_OF_THAT_BINARY
```

Pass the binary setting in your MCP launcher's `env` configuration too; clients
may sanitize inherited environment variables. The umbrella response includes
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

These changes implement financial-core behavior. They do not constitute the
complete v0.1 release. MCP 1 versus MCP 2 alignment, analysis extras, platform
binary distribution, clean installations, original-file review and human
approval flows, library/host acceptance, pilots, and publication remain.
The Rust repository's root/Cargo license mismatch also needs resolution before
publishing a package. General legacy `boxscore` features remain excluded from
the exact-cent workflow.
