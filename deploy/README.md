# MCP deployment files

Prepared only. Hosting and DNS have not been chosen/configured. This template
serves the public reference library and scenario tools; it does not host the
operator community or accept memberships.

## Build an auditable Linux amd64 image

Build the exact candidate Python and Linux native wheels with the CI build/native
jobs (or `scripts/build_components.py` and the pinned Rust wheel build). Place one
wheel per candidate in `wheelhouse/`. Use Python 3.12 on Linux amd64:

```bash
python scripts/prepare_container.py --wheelhouse wheelhouse --output /tmp/plat-oci-context
# SOURCE_REVISION must be the source revision used to build the umbrella wheel.
docker build --network=none --build-arg SOURCE_REVISION=REVIEWED_COMMIT -t platworks:0.1.4 /tmp/plat-oci-context
python scripts/check_container.py --image platworks:0.1.4 --output container-check.json
```

Preparation downloads only the hashed dependency lock, records candidate wheel
hashes and copies a minimal context. Image installation is offline; the final image
contains installed packages, Rust and a build manifest. No source checkout,
credentials, source-alias configuration or user files enter the context. Base
images use immutable digests. Preserve the source tree, manifest, image ID/digest
and probe output together. A local image ID is not a registry publication.

## Hosting later

Choose a Docker-compatible Linux amd64 host with outbound access for the TLS
proxy. Publish the tested image to the chosen registry, pin `PLATWORKS_IMAGE` by
digest, point the chosen `MCP_DOMAIN` at the host, and use `compose.yaml` plus
`Caddyfile`. Intended domain: `mcp.platworks.org`. No commands here were deployed.

The MCP service has no published host port. It runs as UID 65532 with a read-only
root, 256 MiB temporary filesystem, 1 GiB memory, two CPUs, 64 PIDs and dropped
capabilities. The internal Docker network denies its external egress; the TLS
proxy is attached to both the edge and internal networks. Temporary storage needs
execute permission for the verified private copy of the Rust binary. Do not add
host file mounts, source aliases, credentials or an outbound network to the MCP
service. This template is one service process/replica; each replica adds two
calculation slots.

Application limits: 2 MiB JSON requests, depth 32 and 100,000 nodes for scenario
arguments, 10,000 rows per list, 600 analysis months, 1,000 cohorts, 80 backsolve
iterations, two concurrent calculation processes, 8 MiB result limit, 60-second
calculation deadline. A full service returns a typed busy refusal. Public endpoints
are `POST /mcp` and `GET /healthz`; no SSE subscription or session database is kept.
Configure exact allowed hosts. Origins are refused unless explicitly allowed;
server-to-server clients ordinarily send no Origin. Do not use wildcard origins.

The application and proxy configurations disable access/payload/error logging
and caching. Temporary inputs and SQLite previews are deleted after each call,
including timeout/cancellation; an abnormal container termination loses tmpfs.
The chosen platform must also disable request-body tracing, payload collection,
crash dumps and swap persistence if it provides them. Validate its own logging,
retention, TLS, domain, resource limits and external-egress behavior before using
private inputs. These are deployment checks, not claims about an unchosen provider.

There is no authentication or per-user quota in this public v0.1 template. The
service exposes only the shared library and transient scenario calculations.
Before opening the endpoint, choose provider-level abuse/rate controls and test
them without collecting request payloads. OAuth, tenant storage and organization
approval identity are outside this candidate. See [assistant setup and acceptance](../docs/assistant-integrations.md).
