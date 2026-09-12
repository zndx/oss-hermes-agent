Vendored signals-protocol snapshot for the local Hermes lattice engine.

Canonical: git@github.com:zndx/signals-protocol.git @ ce14c87
(`Engine/Announce`, supervision.v1 Expectation/Supervise, scheduler.v1 Coordination Activities). Do not treat this
tree as the protocol SoR — bump from that repo. Hermes-only extras
(`oip_mandatory.md`, `deprecations.md`, OIP proto, `SERVER_QUERY_KIND_FMP=16`,
`SERVER_QUERY_KIND_AGENTS=17` + `zndx.agent.v1`) stay here until the
canonical repo absorbs them. A Metabase draft used AGENTS=16; that number is
live FMP on this lattice — AGENTS is 17.
