# Muse.ai integration brief — prepared, not submitted

Product: Platworks, an Apache-2.0 reference library and deterministic scenario
MCP service for multifamily owners and asset managers. The operator community
is a separate application-only service; community membership is not exposed here.

Prepared transport: stateless Streamable HTTP, intended
`https://mcp.platworks.org/mcp` after hosting is selected. Public profile: 22 tools,
including `search_library`, `get_reference`, `get_synthetic_example`, underwriting,
renovation and exact-cent operations previews. No approval, file-system or
retained-database tools. The current candidate uses no accounts or OAuth.

Files can stay in the assistant host while it extracts the required structured
fields. Values supplied to the public MCP service leave the host. Results are
unverified scenarios, with producer versions/hashes and no human approval.

Needed from Muse before implementation can be called compatible:

- Its supported MCP transport/protocol and custom-connector configuration format.
- Whether it supports tool use alongside user attachments, and required permissions.
- Authentication, distribution/submission requirements and a verified contact path.
- A test account/session for the common synthetic attachment acceptance checklist.

Public check on 2026-10-05: muse.ai redirected to authentication. No integration
specification or approval route was verified. Do not send this brief or claim
an approved integration without the owner's instruction and actual evidence.
