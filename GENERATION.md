# Generation

MobilityAPI-Python is a tier over MEOS, so what it knows about MEOS is
generated from the MEOS-API catalog rather than kept by hand. The generator
lives in `tools/codegen.py`, its output is committed, and CI derives the catalog
from MobilityDB master, regenerates against it, and refuses a difference. This
is the arrangement of MobilityAPI's Go tier, whose generator is
`tools/codegen/main.go`.

## What is generated

`mobilityapi/catalog_gen.py` holds `FUNCTIONS`, one entry per MEOS function the
catalog states as exposable, ordered by name. Each entry is the catalog's own
entry restricted to the keys the dispatcher reads: `name`, `category`,
`params`, `returnType`, `network`, `wire` and `doc`.
`FunctionSignature.from_catalog_entry` reads an entry of the table exactly as it
reads one of the catalog, and the `Dispatcher` serves every function of the
table: `GET /catalog` lists them and `POST /functions/{name}` invokes one.

Run it against a catalog:

```bash
python3 tools/codegen.py -catalog <meos-idl.json> -o mobilityapi/catalog_gen.py
```

A catalog entry without one of the keys the dispatcher reads, or a catalog
stating no function as exposable, stops the generator.

## Where the facts come from

`meos-idl.json` is the machine-readable description of the MEOS C library that
[MEOS-API](https://github.com/MobilityDB/MEOS-API) derives from the MEOS headers
and sources, and that every binding in the ecosystem generates from. Whether a
function is exposable, and how each parameter and the result travel over the
wire, is the catalog's `network` and `wire` projection, which MEOS-API derives
from each function's types, SQL name and group.

The catalog is a derived artifact of one MobilityDB commit, so it is never
committed. CI derives it with
`MobilityDB/MEOS-API/.github/actions/provision-meos@master`, the action every
binding uses, and the `generated-table` job of `.github/workflows/python.yml`
regenerates the table against it. A function MEOS gains, loses or changes on
master arrives there as a difference to regenerate.

To derive the catalog by hand, run MEOS-API's `tools/provision-meos.sh` over a
MobilityDB checkout:

```bash
<MEOS-API>/tools/provision-meos.sh --mdb-src <MobilityDB> --catalog-out meos-idl.json
```
