# Vendored MEOS-API artefacts

This directory contains snapshots of the published catalog and projections
from [`MobilityDB/MEOS-API`](https://github.com/MobilityDB/MEOS-API).
MobilityAPI's [`docs/MEOS_API_INGESTION_PLAN.md`](../../docs/MEOS_API_INGESTION_PLAN.md)
describes how these artefacts drive the ingestion pipeline; this file
documents which artefact is fresh from where.

## Refresh

```bash
# Current state — copies from MEOS-API master:
make vendor-meos-api

# Once the open PR branches land — pulls from PR #4 + PR #5 and regenerates:
make vendor-meos-api-from-prs
```

The `Makefile` targets are idempotent; commit the resulting JSON files
verbatim so a downstream contributor doesn't need libclang installed to
run MobilityAPI.

## What lives here today

| File | Source | Size | Describes |
|---|---|---:|---|
| `meos-idl.json` | MEOS-API master, `output/` | ~1.2 MB | Catalog: 2699 functions, 47 structs, 6 enums (**simple parse**; enrichment via PR #4 not yet on master) |
| `meos-coverage.json` | MEOS-API master, `output/` | ~37 KB | Worklist of non-exposable functions ranked by class |
| `meos-object-model-parity.json` | MEOS-API master, `output/` | ~13 KB | 29-pair portable-bare-name parity (object-model dispatch) |
| **`PROVENANCE.json`** | this file's companion | ~2 KB | Machine-readable source map + status of pending artefacts |

## What's NOT here yet (pending upstream)

| File | Pending | Why |
|---|---|---|
| `meos-idl.json` (enriched form, with `network` / `wire` / `api` fields) | MEOS-API PR #4 | The enrichment pass adds the projectability metadata MobilityAPI's dispatcher layer needs. Once #4's content reaches master, `make vendor-meos-api` picks it up automatically. |
| `meos-openapi.json` | MEOS-API PR #5 | OpenAPI 3.1 projection: 1790 operations + `x-meos-*` extensions. Consumed by MobilityAPI's dispatcher generator (step 4 of the ingestion plan). |
| `meos-movfeat-openapi.json` | MEOS-API session's natural-follow-up | OGC API – Moving Features resource projection. The immediate dependency for MobilityAPI step 5; until it lands, MobilityAPI's hand-written OGC endpoints stay. |

## Why we vendor instead of fetching at runtime

Three reasons:

1. **Reproducible builds** — a MobilityAPI checkout pinned to commit `X` always builds against the same MEOS-API artefact tree, not whatever MEOS-API's master happens to be at build time.
2. **No libclang dependency at install time** — running MEOS-API's `run.py` (the enrichment pass) requires libclang and a checked-out MEOS source tree. Most MobilityAPI users don't need that.
3. **Diff-able drift signal** — a `make vendor-meos-api` followed by `git status` immediately shows what changed upstream, surfacing breaking-changes as reviewable diffs.

See [`docs/MEOS_API_INGESTION_PLAN.md`](../../docs/MEOS_API_INGESTION_PLAN.md) for the full ingestion roadmap (steps 1–5).
