# equity-feature-io

I/O contracts/SDK.a2 provide explicit per-run factories/direct admission and complete logical publication. Source extraction and Parquet sink are accepted through canonical EQ121–126; [EQ127 delivery](docs/EQ127_DELIVERY.md) records the transactional DuckDB sink's review, qualification and publication evidence. Live Project is the status authority for R4.1 acceptance.

Canonical scope: [EQ-121](https://github.com/atulsrivas1/equity-features/issues/278), [R4.1 handoff](https://github.com/atulsrivas1/equity-features/blob/main/docs/R4_1_AUTONOMOUS_HANDOFF.md) and [architecture](https://github.com/atulsrivas1/equity-features/blob/main/docs/IO_WORKER_ARCHITECTURE.md). This companion owns component implementation/evidence. Planning, lifecycle, epics and milestones stay in equity-features. Pure calculations and existing acquisition protocols retain their original repository/imports.

CPython3.12 x64 Windows/Linux only. Experimental io-contracts/SDK0.1.0a2 provides [factory composition](docs/api/FACTORIES.md) and [logical publication](docs/api/PUBLICATION.md); actual acceptance is recorded on canonical issues. See [build/install](docs/BUILD_DELIVERY.md), [compatibility](docs/COMPATIBILITY.md) and [continuity](docs/SESSION_HANDOFF.md). Code is Apache-2.0; data rights are separate. No registry release or stable tag.

[Foundation source delivery evidence](docs/EQ121_DELIVERY.md) records reviewed heads/native artifact hashes; canonical issue278 records actual acceptance after main publication/readback.

EQ122 extracts the compatible [DuckDB source adapter](docs/DUCKDB_MIGRATION.md), independently packaged without I/O SDK/workers; its current API/docs live here and canonical279 records actual delivery acceptance.

[Experimental I/O v1 specification](docs/contracts/IO_V1.md) and [independent expected vectors](docs/contracts/IO_V1_VECTORS.md) freeze EQ123 design. Runtime publication types/conformance remain EQ125; no installed sink operation is claimed by the specification.

EQ125 accepted logical publication: [typed API/extension kit](docs/api/PUBLICATION.md), [evidence](docs/EQ125_DELIVERY.md). EQ126 accepted [Parquet API](docs/api/PARQUET_SINK.md)/[delivery](docs/EQ126_DELIVERY.md). EQ127 [DuckDB sink API](docs/api/DUCKDB_SINK.md)/[delivery](docs/EQ127_DELIVERY.md) records implementation, resolved recovery findings and exact qualification/publication evidence; these backend guarantees do not certify worker execution or provider/private data.

[Independent public extension tutorial](examples/third_party/README.md) demonstrates synthetic source->pure calculation->in-memory sink/directfactory composition; [EQ128 delivery](docs/EQ128_DELIVERY.md) and canonical285 record actual qualification gates.

## R6 acquisition controls under qualification

[Shared acquisition](packages/acquisition/README.md) adds optional explicit request-scoped consent, safe credentials/errors, finite retry/cancellation/cost/byte ledgers and disabled-by-default authorized immutable cache. [EQ068 plan](docs/EQ068_PLAN.md), [canonical story77](https://github.com/atulsrivas1/equity-features/issues/77), componentPR12/canonicalPR343. Source implemented; separate final review/native fresh forms/publication readback still required before release. No provider access/data rights/integration qualified. Existing SDK/contracts.a2 and workers.a12 remain unchanged.
