# Security policy

## Data boundary

This repository contains **no real data**. The catalog carries only public
repository metadata (names, URLs, descriptions verified against the GitHub API,
licenses, languages). The demo portfolio is fabricated; names like "Bluebonnet
Ridge" are fiction, not redactions. If any real deal, tenant, owner, or
portfolio data appears in a contribution, the contribution will be rejected.

## Attack surface

- The MCP server, CLI, and landing-page generator are **read-only** over the
  packaged catalog. They make no network calls, read no files outside their
  declared output paths, and execute no external input.
- The demo spawns one local subprocess (the MCP stdio server) using the same
  interpreter that runs the demo; the child command is a fixed string, not
  caller-controlled.
- Generated HTML escapes all catalog text (html.escape); catalog strings cannot
  inject markup. The landing page loads no scripts and no external assets.

## Typed refusals, not crashes

MCP tools never leak internal exception text: unknown components, unknown
categories, and missing arguments are returned as typed payload refusals
(`{"error": {"type": ..., "message": ...}}`) with actionable messages. A
crash-free contract means clients can rely on the shape of every response.

## Reporting a vulnerability

Open a private security advisory on the affected repository, or a regular issue
in this one for umbrella-level concerns. Do not open public issues for anything
involving real-data exposure.

## Scope and honesty

This package has been tested on Linux aarch64 with Python 3.11 and `mcp` 2.x.
No claim is made about other platforms. The synthetic demo proves the MCP
wiring, not any property of real data pipelines.