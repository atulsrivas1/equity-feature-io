"""Authored clock-to-existing-sink conformance, not executed qualification."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, Column, ContractError, EntityKey, ErrorCode,
    SessionSpec, WindowSpec,
)
from equity_feature_duckdb.ef1 import ClockInputs, synthetic_clock_calendar, synthetic_clock_fixture
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import build_ef1_config, compute_ef1


def config(cutoff=20, knowledge=None):
    return build_ef1_config({"version": "ef1-context1", "producer": "clock",
        "calendar": synthetic_clock_calendar(), "selection": {}},
        session=SessionSpec("SYN", "S", 10, 30, "UTC", scheduled_close_ns=40, early_close=True),
        window=WindowSpec(1, "S", ("S",), "completed_eod"),
        availability=AvailabilitySpec(cutoff, cutoff if knowledge is None else knowledge, 40),
        price_unit=None, adjustment=AdjustmentSpec())


def calculate(packet=None, cutoff=20, knowledge=None):
    inputs = synthetic_clock_fixture() if packet is None else packet
    return compute_ef1(inputs.batches, config(cutoff, knowledge), entity=EntityKey("X", "S"))


def cells(result):
    return {column.feature_id: column.values[0] for column in result.values}


class ClockCompositionTests(unittest.TestCase):
    def test_c01_literal_boundaries_including_proof_end_equality(self):
        expected = (
            (10, "regular", 0, 20, 0.0),
            (20, "regular", 10, 10, 0.5),
            (30, "postmarket", 20, 0, 1.0),
            (40, "closed", 20, 0, 1.0),
        )
        for cutoff, phase, elapsed, remaining, fraction in expected:
            with self.subTest(cutoff=cutoff):
                result = calculate(cutoff=cutoff)
                self.assertEqual(cells(result), {"session.clock.phase": phase,
                    "session.clock.regular_elapsed_ns": elapsed,
                    "session.clock.regular_remaining_ns": remaining,
                    "session.clock.regular_fraction": fraction, "session.clock.early_close": True})
                self.assertTrue(all(row.status.value == "available" for row in result.quality))
                self.assertEqual(tuple(binding.role for binding in result.metadata.inputs), ("calendar_provenance",))

    def test_clock_missing_unknown_future_original_schedule_proof(self):
        cases = ((ClockInputs(None, "unavailable"), "absent_input"),
                 (synthetic_clock_fixture(known_at_ns=None), "unknown_availability"),
                 (synthetic_clock_fixture(known_at_ns=21), "future_knowledge"))
        for packet, reason in cases:
            result = calculate(packet)
            self.assertTrue(all(value is None for value in cells(result).values()))
            self.assertTrue(all(row.status.value == "missing_input" for row in result.quality))
            self.assertTrue(all(reason in tuple(r.value for r in row.reasons) for row in result.quality))
            self.assertEqual(len(result.metadata.inputs), len(packet.batches))

    def test_known_at_equality_and_exact_actual_binding_preserved(self):
        packet = synthetic_clock_fixture(known_at_ns=20)
        result = calculate(packet)
        self.assertEqual(cells(result)["session.clock.regular_fraction"], 0.5)
        self.assertEqual(result.metadata.inputs[0].metadata, packet.calendar_provenance.metadata)

    def test_wrong_calendar_hash_or_revision_is_identity_error(self):
        packet = synthetic_clock_fixture()
        proof = packet.calendar_provenance
        invalid_hash = replace(proof, columns=tuple(
            Column(c.name, ("c1:" + "0" * 64,)) if c.name == "reference_id" else c for c in proof.columns))
        invalid_revision = replace(proof, metadata=replace(proof.metadata,
            source=replace(proof.metadata.source, snapshot_id="R2")))
        for invalid in (invalid_hash, invalid_revision):
            with self.assertRaises(ContractError) as caught:
                calculate(ClockInputs(invalid, "synthetic"))
            self.assertEqual(caught.exception.code, ErrorCode.INCONSISTENT_IDENTITY)

    def test_five_cell_result_full_sink_bytes_lookup_replay_and_sequential_reopen(self):
        limits = SinkRequirements(max_results=1, max_chunk_bytes=1048576, max_total_bytes=1048576,
                                  max_result_cells=5, max_evidence_rows=128)
        for packet in (synthetic_clock_fixture(), synthetic_clock_fixture(known_at_ns=None),
                       ClockInputs(None, "unavailable")):
            with self.subTest(provenance=packet.provenance), TemporaryDirectory() as temp:
                result = calculate(packet)
                envelope = prepare_publication((result,), destination_scope="synthetic-clock",
                    generation_id="C01", job_id="clock", partition_id="X-S", limits=limits)
                output = Path(temp) / "new-clock-results.duckdb"
                with DuckDBSink(output, "synthetic-clock", limits=limits) as sink:
                    receipt = publish(sink, envelope, (result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]), encode_result(result))
                    self.assertEqual(publish(sink, envelope, (result,)), receipt)
                with DuckDBSink(output, "synthetic-clock", limits=limits) as reader:
                    self.assertEqual(reader.lookup(receipt.idempotency_key).receipt, receipt)
                    self.assertEqual(encode_result(reader.read(receipt)[0]), encode_result(result))


if __name__ == "__main__":
    unittest.main()
