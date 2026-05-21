MobilityAPI
===========

[![License: PostgreSQL](https://img.shields.io/badge/License-PostgreSQL-blue.svg)](LICENSE.txt)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![OGC API – Moving Features](https://img.shields.io/badge/OGC%20API-Moving%20Features-green.svg)](https://docs.ogc.org/is/22-003r3/22-003r3.html)

An open-source implementation of the [OGC API – Moving Features Standard](https://docs.ogc.org/is/22-003r3/22-003r3.html), built on top of [MobilityDB](https://github.com/MobilityDB/MobilityDB/).

<img src="doc/images/mobilitydb-logo.svg" width="200" alt="MobilityDB Logo" />

MobilityDB is developed by the Computer & Decision Engineering Department of the [Université libre de Bruxelles (ULB)](https://www.ulb.be/) under the direction of [Prof. Esteban Zimányi](http://cs.ulb.ac.be/members/esteban/). ULB is an OGC Associate Member and member of the OGC Moving Feature Standard Working Group ([MF-SWG](https://www.ogc.org/projects/groups/movfeatswg)).

<img src="doc/images/OGC_Associate_Member_3DR.png" width="100" alt="OGC Associate Member Logo" />

More information about MobilityDB and the broader MEOS ecosystem can be found at:

- **MobilityDB website** — https://mobilitydb.com
- **MEOS / libmeos.org** — https://libmeos.org/ (the canonical C library underlying MobilityDB and MobilityDuck; MobilityAPI is one of its [bindings](https://libmeos.org/bindings/mobilityapi/))
- **OGC API – Moving Features Standard** — https://docs.ogc.org/is/22-003r3/22-003r3.html

## Introduction

MobilityAPI is a Python API server that exposes MEOS-stored mobility data through the OGC API – Moving Features standard. It provides REST endpoints (GET / POST / PUT / DELETE) over collections of moving features, suitable for HTTP-driven clients that don't speak SQL or the PostgreSQL wire protocol — browser applications, mobile clients, microservices, ETL pipelines.

The reference implementation runs on top of MobilityDB and consumes [PyMEOS](https://github.com/MobilityDB/PyMEOS) for the temporal-data conversion layer.

## Status

This project is under active development. Existing endpoints implement the core OGC API – Moving Features Standard; coverage of the standard is being progressively extended. See [open issues](https://github.com/MobilityDB/MobilityAPI/issues) for the current roadmap and [discussions](https://github.com/MobilityDB/MobilityAPI/discussions) for design conversations.

## Features

- HTTP endpoints implementing the [OGC API – Moving Features Standard](https://docs.ogc.org/is/22-003r3/22-003r3.html): GET / POST / PUT / DELETE on collections, items, temporal geometries, and temporal properties.
- Built on [PyMEOS](https://github.com/MobilityDB/PyMEOS) for seamless interaction with MobilityDB temporal types.
- Validation of MovingFeaturesJSON payloads on insert.
- Test suite ingesting real-world AIS (Automatic Identification System) ship-trajectory data.

## Prerequisites

- Linux (Ubuntu recommended)
- Python 3.10 or later
- PostgreSQL with the [MobilityDB](https://github.com/MobilityDB/MobilityDB) extension installed

## Install

```bash
pip install -r requirements.txt
```

## Run the server

```bash
chmod +x run.sh
./run.sh
```

The server listens on `localhost:8080` by default. Connection parameters live in `config.json`.

## Run with the test suite

```bash
./run.sh --with-tests
```

The test runner ingests an AIS dataset before running the integration tests:

- ~23 minutes on first run if the JSON data file is not yet cached.
- ~21 seconds on subsequent runs.

If you need the AIS dataset, download `aisdk_2024-08-07.zip` from the [Danish Maritime Authority feed](http://aisdata.ais.dk/?prefix=2024/) into the `data/` folder. Manual GET request examples are in [`demo.txt`](demo.txt).

## Usage

Send HTTP requests to the API using any HTTP client. As an example, the `ais.sql` script will create `ships` and `ship2` tables containing ships data — change the CSV path in the script to point at your downloaded dataset.

For a guided walk-through of the OGC API – Moving Features endpoints against the Danish AIS dataset, open the [`tutorial.ipynb`](tutorial.ipynb) notebook (start the server with `./run.sh` first).

## Where MobilityAPI fits

MobilityAPI is the HTTP / OGC layer of the MEOS ecosystem. The other layers are:

- **MEOS** (canonical C library) — the underlying type system and computations.
- **MobilityDB** and **MobilityDuck** — peer SQL layers (PostgreSQL extension and DuckDB extension respectively) that expose MEOS as first-class database types.
- **Language bindings** — [PyMEOS](https://github.com/MobilityDB/PyMEOS), [JMEOS](https://github.com/MobilityDB/JMEOS), [meos-rs](https://github.com/MobilityDB/meos-rs), [GoMEOS](https://github.com/MobilityDB/GoMEOS), [MEOS.NET](https://github.com/MobilityDB/MEOS.NET), [MEOS.js](https://github.com/MobilityDB/MEOS.js).

A [longer overview](https://libmeos.org/) is available on libmeos.org.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup, test instructions, code style, and PR conventions. Issues and pull requests are welcome.

## History and Acknowledgements

MobilityAPI builds on the foundation laid by **[pg_mfserv](https://github.com/MobilityDB/pg_mfserv)**, an OGC API – Moving Features prototype authored at ULB in early 2024. The pg_mfserv initial implementation provided the Python-server skeleton, the OGC endpoint shape, and the PyMEOS-based MobilityDB integration pattern that MobilityAPI extends with a structured resource layout, comprehensive test coverage, and OGC-conformant request/response handling.

**pg_mfserv** is preserved in archived form at [`MobilityDB/pg_mfserv`](https://github.com/MobilityDB/pg_mfserv) for historical reference and scholarly attribution; active development continues in this repository.

Contributors to the lineage, in chronological order:

- **Maxime Schoemans** ([@mschoema](https://github.com/mschoema)) — pg_mfserv founding author (initial commit, OGC-API endpoint design).
- **Victor Morabito** ([@MrMaxime1er](https://github.com/MrMaxime1er)) — pg_mfserv main developer (column-discovery, request handling, exception handling, route refactors — March 2024).
- **Sirine Meraoui** ([@sirimeraoui](https://github.com/sirimeraoui)) — current MobilityAPI maintainer (structured resource layout, test infrastructure, OGC conformance, documentation).

See [`AUTHORS.md`](AUTHORS.md) for the complete contributor list.

## License

MobilityAPI is released under [The PostgreSQL License](LICENSE.txt). If you use MobilityAPI in academic or technical work, please cite it using the metadata in [`CITATION.cff`](CITATION.cff).
