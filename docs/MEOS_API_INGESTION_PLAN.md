# Plan — MobilityAPI ingestion of MEOS-API output

**Status:** authored as a parallel-session task; reads MEOS-API's published artefacts as inputs, ships changes here.

This document plans how MobilityAPI consumes the catalog and projections published by [`MobilityDB/MEOS-API`](https://github.com/MobilityDB/MEOS-API), and how it integrates with the **missing-work items** named in MEOS-API PR #5 (OpenAPI projection).

## Context

| Repo | Role |
|---|---|
| [MEOS-API](https://github.com/MobilityDB/MEOS-API) | Single source of truth: `meos-idl.json` catalog + machine-readable projections (OpenAPI, MCP, runtime server). PRs #4 (catalog enrichment), #5 (OpenAPI 3.1), #6 (MCP tool manifest), #7 (runtime HTTP server), #8 (portable-aliases), #9 (cross-repo handoff), #10 (object model), #11 (integration train). |
| **MobilityAPI** (this repo) | OGC API – Moving Features (OGC 22-003r3) Python HTTP server. Hand-written REST endpoints over PyMEOS-backed temporal data. The bridge: same MEOS surface, OGC-conformant shape. |

The MEOS-API README lists MobilityAPI as a downstream binding. PR #5's **"natural follow-ups"** explicitly names *"an OGC API – Moving Features resource projection"* as the next OpenAPI work — that projection is the contract MobilityAPI consumes.

## Per-task split (parallel sessions)

Each session owns exactly one repo (per the [cross-repo-handoff brief](https://github.com/MobilityDB/MEOS-API/pull/9)). The split:

| Session | Repo | Task | Status |
|---|---|---|---|
| **MEOS-API session** | `MEOS-API` | (a) Conformance validation of `meos-openapi.json` in CI (spectral / openapi-validator); (b) `generator/movfeat.py` projecting the enriched catalog onto an OGC API – Moving Features OpenAPI subset (`movfeat-openapi.json`). PR #5's natural follow-ups, separate PRs. | **MISSING** — to be opened by MEOS-API's session, not this one |
| **MobilityAPI session** (this plan) | `MobilityAPI` | (1) Vendor the MEOS-API artefacts MobilityAPI consumes as a versioned dependency. (2) Endpoint-by-endpoint gap analysis: each existing hand-written `resource/*` vs the generated equivalent. (3) Migration plan: replace hand-written endpoints with thin dispatchers over the generated contract, keep OGC-specific business logic (validation, content-negotiation, link relations) in this repo. (4) CI gate: regenerate-and-diff against the upstream `movfeat-openapi.json` so drift is detected. | THIS PR is the assessment + plan; subsequent PRs execute step-by-step |

The two sessions **do not block each other**. MobilityAPI's session can:

- Vendor the **current** `meos-idl.json` + `meos-openapi.json` artefacts NOW (catalog and generic OpenAPI exist on MEOS-API `master` already).
- Author the gap analysis NOW.
- Stand up the regenerate-and-diff CI gate NOW against the live MEOS-API artefacts.
- Replace hand-written endpoints with thin dispatchers as the `movfeat-openapi.json` projection becomes available (consume the open MEOS-API PR's branch, per the [never-wait-for-PR-merge](https://github.com/MobilityDB/MEOS-API/blob/master/docs/cross-repo-handoff.md) rule).

## Missing OpenAPI work (from MEOS-API PR #5's "natural follow-ups")

| Item | What | Where it lives | Status |
|---|---|---|---|
| MCP tool-manifest generator | Project catalog → MCP manifest for AI agents | MEOS-API | **DONE** — PR #6 (OPEN) |
| **OpenAPI conformance validation in CI** | spectral / openapi-validator over `meos-openapi.json` on every catalog regen | MEOS-API | **MISSING** — needs a new MEOS-API PR |
| **OGC API – Moving Features resource projection** | A second projector alongside `generate_openapi.py`, emitting `movfeat-openapi.json` with OGC paths (`/collections/{id}/items` etc.) and `application/geo+json` / `application/json` content types matching OGC 22-003r3 | MEOS-API | **MISSING** — needs a new MEOS-API PR; **this is the immediate dependency for MobilityAPI** |

Both missing items belong to the **MEOS-API session**. This plan calls them out so the parallel session knows the priority.

## Endpoint-by-endpoint gap analysis (this repo's surface vs the projected contract)

Today MobilityAPI's [`resource/`](../resource) directory contains ~10 hand-written endpoint modules. The mapping to the MEOS-API generated contract:

| MobilityAPI module | OGC 22-003r3 resource | MEOS-API generic OpenAPI mapping | MovFeat projection mapping | Migration step |
|---|---|---|---|---|
| `collections/` (Create, Retrieve) | `/collections`, `/collections/{collectionId}` | n/a (collection management is catalog-side, not MEOS-side) | `/collections` — OGC standard CRUD | KEEP — collection metadata is not in `meos-idl.json` |
| `collection/` (Delete, Retrieve, Replace) | `/collections/{collectionId}` | n/a | `/collections/{id}` | KEEP — same reason |
| `moving_features/` (Create, Retrieve) | `/collections/{cid}/items` | `POST /temporal_from_*` (catalog) + persistence | `/collections/{cid}/items` — MovFeat standard | Wrap: generated dispatcher for MEOS calls, hand-written for persistence + GeoJSON envelope |
| `moving_feature/` (Delete, Retrieve) | `/collections/{cid}/items/{fid}` | n/a (item identity is catalog-side) | `/collections/{cid}/items/{fid}` | KEEP — item-id is a MovFeat concept |
| `temporal_geom_seq/` (Create, Retrieve) | `/.../tgsequence` (full traj geom) | `POST /temporal_as_mfjson` for export; `POST /temporal_from_mfjson` for ingest | `/collections/{cid}/items/{fid}/tgsequence` | **REPLACE with dispatcher** — pure MEOS round-trip |
| `temporal_geom_query/` (acceleration, distance, velocity) | `/.../tgsequence/{velocity,acceleration,distance}` | `POST /tpoint_speed`, `POST /tpoint_cumulative_length`, etc. | `/.../tgsequence/{velocity,acceleration,distance}` | **REPLACE with dispatcher** — direct MEOS function calls |
| `temporal_prim_geom/` (Delete) | `/.../tgsequence/{...}` slot | n/a (atomic deletes are persistence-layer) | OGC-defined slot | KEEP — persistence-layer |
| `temporal_prim_value/` (Delete) | `/.../tproperty/{name}/{idx}` | n/a | OGC-defined slot | KEEP — persistence-layer |
| `temporal_properties/` | `/.../tproperty/{name}` | `POST /temporal_as_mfjson` for export | `/.../tproperty/{name}` | **REPLACE with dispatcher** — round-trip through MEOS |

**Replace candidates** (5 modules) are pure MEOS-function dispatchers: their hand-written code can be lifted from the generated OpenAPI's `operationId` once the MovFeat projection lands. **Keep** (5 modules) implement OGC-specific concerns (collection lifecycle, GeoJSON envelope construction, persistence indexing) that have no MEOS equivalent.

## Sequencing — what this MobilityAPI session does, in order

Following the [never-wait-for-merge rule](https://github.com/MobilityDB/MEOS-API/blob/master/docs/cross-repo-handoff.md):

1. **THIS PR** — ship this plan as `docs/MEOS_API_INGESTION_PLAN.md`. Get reviewer concurrence on the per-task split.
2. **PR #N+1** — vendor `meos-idl.json` + `meos-openapi.json` from MEOS-API master (or its open PR branches) into `vendor/meos-api/`. Add a `make vendor-meos-api` target that re-fetches.
3. **PR #N+2** — CI gate that regenerates the vendored artefacts and fails the PR if they drift. Surfaces upstream changes as PR-able diffs.
4. **PR #N+3** — replace the 5 "REPLACE" modules with thin dispatchers driven by `meos-openapi.json`'s `x-meos-{category,decode,encode}` extensions. Each dispatcher reads its function name, decodes the JSON body, calls the MEOS function (via PyMEOS, which itself reads the same catalog via PyMEOS-CFFI), encodes the result.
5. **PR #N+4** — *gated on MEOS-API session shipping `movfeat-openapi.json`* — replace the dispatchers with the OGC-shaped paths from the MovFeat projection. The 5 "REPLACE" modules then become 5 path-routing rules + the generic dispatcher.
6. **PR #N+5** — Spectral / OpenAPI-validator CI gate on MobilityAPI's *own* OpenAPI surface, asserting it's a superset of the OGC MovFeat projection.

Steps 1-3 + 4 unblock today against MEOS-API master. Step 5 unblocks once the MEOS-API session opens the MovFeat-projection PR (consume its branch immediately — don't wait for merge).

## Invariants this plan carries forward

- **Single source of truth.** Hand-written shapes that overlap the catalog must be replaceable from `meos-idl.json` without losing semantics. Drift means upstream changed; surface it as a PR, don't paper over it.
- **OGC standards compliance is MobilityAPI's value-add.** The generic OpenAPI from MEOS-API is correct but not OGC-shaped; that's the MovFeat projection's job. MobilityAPI's tests already exercise OGC paths against real AIS data — those tests stay.
- **PyMEOS in the middle.** MobilityAPI's runtime still calls PyMEOS; the catalog is for *contract* and *codegen*, not for direct MEOS dlopen. The CtypesEngine in MEOS-API PR #7 is a separate concern (a different deployment topology — generic MEOS-over-HTTP, not OGC).
- **No regressions on the AIS test suite** (`tests/test_mobility_api.py`). Replacement modules must pass the same fixture.
- **No AI co-author attribution** anywhere ([`no-ai-coauthor-public`](https://github.com/MobilityDB/MobilityDB/wiki) standing rule).

## Open questions for the maintainer

1. **Where does `movfeat-openapi.json` live as published artefact?** Embedded in `MobilityDB/MEOS-API/output/`? Or a release asset on MEOS-API tags? (Affects how MobilityAPI vendors it.)
2. **Does the regenerate-and-diff CI gate require a built MEOS, or only the headers?** The catalog regen needs libclang + headers; the OpenAPI projector needs only the catalog JSON. Choosing "only catalog JSON" keeps MobilityAPI's CI lightweight.
3. **Are there OGC-specific schemas (MovingFeaturesJSON, content-negotiation) that the MovFeat projection should reuse from an external OGC schema registry, or inline them?** Inlining matches PR #5's "self-describing OpenAPI" stance; external `$ref` matches the OGC schema registry convention.

## Provenance

Authored by the MobilityAPI session as a planning artefact, reading the live state of MEOS-API PRs #4 / #5 / #6 / #7 / #8 / #9 / #10 / #11. No code change in this PR — pure docs. Subsequent PRs execute the steps above one at a time.
