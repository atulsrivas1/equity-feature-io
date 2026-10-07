# equity-feature-io

I/O contracts and SDK foundations; source/sink/factory implementations are pending their canonical stories.

Canonical scope: [EQ-121](https://github.com/atulsrivas1/equity-features/issues/278), [R4.1 handoff](https://github.com/atulsrivas1/equity-features/blob/main/docs/R4_1_AUTONOMOUS_HANDOFF.md) and [architecture](https://github.com/atulsrivas1/equity-features/blob/main/docs/IO_WORKER_ARCHITECTURE.md). This companion owns component implementation/evidence. Planning, lifecycle, epics and milestones stay in equity-features. Pure calculations and existing acquisition protocols retain their original repository/imports.

CPython3.12 x64 Windows/Linux only. Experimental version0.1.0a0 foundations expose version markers; no unimplemented operation is advertised. See [build/install](docs/BUILD_DELIVERY.md), [compatibility](docs/COMPATIBILITY.md) and [continuity](docs/SESSION_HANDOFF.md). Code is Apache-2.0; data rights are separate. No registry release or stable tag.

[Foundation source delivery evidence](docs/EQ121_DELIVERY.md) records reviewed heads/native artifact hashes; canonical issue278 records actual acceptance after main publication/readback.

EQ122 extracts the compatible [DuckDB source adapter](docs/DUCKDB_MIGRATION.md), independently packaged without I/O SDK/workers; its current API/docs live here and canonical279 records actual delivery acceptance.
