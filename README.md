# equity-feature-io

I/O contracts/SDK.a2 provide explicit per-run factories/direct admission and complete logical publication. Source extraction and Parquet sink are accepted through canonical EQ121–126; transactional DuckDB sink is in EQ127 rework, with later R4.1 acceptance pending. Live Project is the status authority.

Canonical scope: [EQ-121](https://github.com/atulsrivas1/equity-features/issues/278), [R4.1 handoff](https://github.com/atulsrivas1/equity-features/blob/main/docs/R4_1_AUTONOMOUS_HANDOFF.md) and [architecture](https://github.com/atulsrivas1/equity-features/blob/main/docs/IO_WORKER_ARCHITECTURE.md). This companion owns component implementation/evidence. Planning, lifecycle, epics and milestones stay in equity-features. Pure calculations and existing acquisition protocols retain their original repository/imports.

CPython3.12 x64 Windows/Linux only. Experimental io-contracts/SDK0.1.0a2 provides [factory composition](docs/api/FACTORIES.md) and [logical publication](docs/api/PUBLICATION.md); actual acceptance is recorded on canonical issues. See [build/install](docs/BUILD_DELIVERY.md), [compatibility](docs/COMPATIBILITY.md) and [continuity](docs/SESSION_HANDOFF.md). Code is Apache-2.0; data rights are separate. No registry release or stable tag.

[Foundation source delivery evidence](docs/EQ121_DELIVERY.md) records reviewed heads/native artifact hashes; canonical issue278 records actual acceptance after main publication/readback.

EQ122 extracts the compatible [DuckDB source adapter](docs/DUCKDB_MIGRATION.md), independently packaged without I/O SDK/workers; its current API/docs live here and canonical279 records actual delivery acceptance.

[Experimental I/O v1 specification](docs/contracts/IO_V1.md) and [independent expected vectors](docs/contracts/IO_V1_VECTORS.md) freeze EQ123 design. Runtime publication types/conformance remain EQ125; no installed sink operation is claimed by the specification.

EQ125 accepted logical publication: [typed API/extension kit](docs/api/PUBLICATION.md), [evidence](docs/EQ125_DELIVERY.md). EQ126 accepted [Parquet API](docs/api/PARQUET_SINK.md)/[delivery](docs/EQ126_DELIVERY.md). EQ127 [DuckDB sink API](docs/api/DUCKDB_SINK.md)/[delivery](docs/EQ127_DELIVERY.md) records implementation, recovery rework and pending final qualification; these backend guarantees do not certify worker execution or provider/private data.
