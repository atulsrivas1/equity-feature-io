"""Authored cross-layer checks; deliberately unexecuted during EQ142 reservation.

Requires the reviewed EF1 feature candidate and existing optional physical sink.
The original literal expectations below are independent of the feature engine.
"""
from dataclasses import replace
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, Column, ContractError, EntityKey, ErrorCode,
    PriceUnit, SessionSpec, WindowSpec,
)
from equity_feature_duckdb.ef1 import separate_output_path, synthetic_anchor_fixture
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import build_ef1_config, compute_ef1


def config(mode="trades", start=10):
    context = {"version": "ef1-context1", "producer": "anchor", "calendar": None,
               "selection": {"mode": mode, "definition": {
                   "anchor_id": "A", "reset_id": "R", "start_ns": start,
                   "selection_policy_id": "supplied-v1", "revision": "R1"}}}
    return build_ef1_config(context, session=SessionSpec("SYN", "S", 10, 30, "UTC"),
                            window=WindowSpec(1, "S", ("S",), "completed_eod"),
                            availability=AvailabilitySpec(20, 20, 20),
                            price_unit=PriceUnit(2, "USD"), adjustment=AdjustmentSpec())


def calculate(packet, cfg=None):
    return compute_ef1(packet.batches, config(packet.mode) if cfg is None else cfg,
                       entity=EntityKey("X", "S"))


def cells(result):
    return {column.feature_id: column.values[0] for column in result.values}


class AnchorCompositionTests(unittest.TestCase):
    def test_a01_trade_and_actual_notional_bar_literal_values(self):
        for mode in ("trades", "bars_actual_notional"):
            with self.subTest(mode=mode):
                result = calculate(synthetic_anchor_fixture(mode=mode))
                self.assertEqual(cells(result), {"session.anchor.vwap": 11.0,
                                                "session.anchor.volume": 3,
                                                "session.anchor.notional": 3300})
                self.assertTrue(all(row.status.value == "available" for row in result.quality))
                self.assertEqual(tuple(binding.role for binding in result.metadata.inputs),
                                 tuple(sorted(("trades" if mode == "trades" else "bars", "anchor_provenance"))))
                # Source packet order is transport order; canonical result inputs
                # are independently sorted by role by ResultMetadata.

    def test_a01_missing_notional_does_not_invent_close_times_volume(self):
        result = calculate(synthetic_anchor_fixture("A01-missing-notional", mode="bars_actual_notional"))
        self.assertEqual(cells(result), {"session.anchor.vwap": None,
                                        "session.anchor.volume": 3, "session.anchor.notional": None})
        qualities = {row.feature_id: row for row in result.quality}
        self.assertEqual(qualities["session.anchor.volume"].status.value, "available")
        self.assertEqual(qualities["session.anchor.notional"].status.value, "missing_input")
        self.assertIn("null_field", tuple(reason.value for reason in qualities["session.anchor.notional"].reasons))

    def test_a02_positive_covered_empty_window_has_available_zero_totals(self):
        for mode in ("trades", "bars_actual_notional"):
            result = calculate(synthetic_anchor_fixture("A02", mode=mode))
            self.assertEqual(cells(result), {"session.anchor.vwap": None,
                                            "session.anchor.volume": 0, "session.anchor.notional": 0})
            qualities = {row.feature_id: row for row in result.quality}
            self.assertEqual(qualities["session.anchor.volume"].status.value, "available")
            self.assertEqual(qualities["session.anchor.vwap"].status.value, "not_applicable")
            self.assertIn("zero_denominator", tuple(reason.value for reason in qualities["session.anchor.vwap"].reasons))

    def test_a03_request_rejected_without_synthetic_scope(self):
        with self.assertRaises(ContractError) as caught:
            # Builder or calculation must reject this exact request.
            calculate(synthetic_anchor_fixture(), config(start=20))
        self.assertEqual(caught.exception.code, ErrorCode.BOUNDS)

    def test_b01_hash_and_revision_mismatch_refused(self):
        packet = synthetic_anchor_fixture()
        proof = packet.anchor_provenance
        wrong_hash = replace(proof, columns=tuple(
            Column(column.name, ("a1:" + "0" * 64,)) if column.name == "reference_id" else column
            for column in proof.columns))
        wrong_revision = replace(proof, metadata=replace(proof.metadata,
            source=replace(proof.metadata.source, snapshot_id="different-revision")))
        for malformed in (wrong_hash, wrong_revision):
            with self.assertRaises(ContractError) as caught:
                calculate(replace(packet, anchor_provenance=malformed))
            self.assertEqual(caught.exception.code, ErrorCode.INCONSISTENT_IDENTITY)

    def test_unknown_and_future_proof_remain_unavailable(self):
        packet = synthetic_anchor_fixture()
        for known, reason in ((None, "unknown_availability"), (21, "future_knowledge")):
            proof = replace(packet.anchor_provenance, columns=tuple(
                Column(c.name, (known,)) if c.name == "known_at_ns" else c
                for c in packet.anchor_provenance.columns))
            result = calculate(replace(packet, anchor_provenance=proof))
            self.assertTrue(all(value is None for value in cells(result).values()))
            self.assertTrue(all(reason in tuple(r.value for r in row.reasons) for row in result.quality))

    def test_unchanged_full_canonical_sink_bytes_readback_replay(self):
        for case, mode in (("A01", "trades"), ("A01", "bars_actual_notional"),
                           ("A02", "trades"), ("A01-missing-notional", "bars_actual_notional")):
            with self.subTest(case=case, mode=mode), TemporaryDirectory() as temp:
                result = calculate(synthetic_anchor_fixture(case, mode=mode))
                expected = encode_result(result)
                output = separate_output_path(Path(temp) / "new-results.duckdb", ())
                envelope = prepare_publication((result,), destination_scope="synthetic-ef1",
                    generation_id="gen-" + case + "-" + mode, job_id="anchor", partition_id="X-S",
                    limits=SinkRequirements(max_results=1, max_chunk_bytes=1048576,
                        max_total_bytes=1048576, max_result_cells=3, max_evidence_rows=128))
                with DuckDBSink(output, "synthetic-ef1") as sink:
                    receipt = publish(sink, envelope, (result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]), expected)
                    self.assertEqual(publish(sink, envelope, (result,)), receipt)
                # Sequential handoff only: no simultaneous native viewer reader.
                with DuckDBSink(output, "synthetic-ef1") as reader:
                    self.assertEqual(reader.lookup(receipt.idempotency_key).receipt, receipt)
                    self.assertEqual(encode_result(reader.read(receipt)[0]), expected)

    def test_publication_example_nonempty_result_and_readback(self):
        example = Path(__file__).resolve().parents[2] / "examples" / "ef1" / "publish_result.py"
        result = calculate(synthetic_anchor_fixture())
        with TemporaryDirectory() as temp:
            source = Path(temp) / "canonical-result.json"
            source.write_bytes(encode_result(result))
            output = Path(temp) / "new-output.duckdb"
            args = [str(example), str(source), str(output), "--destination-scope", "synthetic-ef1",
                    "--generation-id", "example-A01", "--job-id", "anchor", "--partition-id", "X-S"]
            with mock.patch.object(sys, "argv", args), mock.patch("builtins.print") as printed:
                runpy.run_path(str(example), run_name="__main__")
            printed.assert_called_once()
            envelope = prepare_publication((result,), destination_scope="synthetic-ef1",
                generation_id="example-A01", job_id="anchor", partition_id="X-S",
                limits=SinkRequirements(max_results=1, max_chunk_bytes=1048576,
                    max_total_bytes=1048576, max_result_cells=3, max_evidence_rows=128))
            from equity_feature_io_sdk import idempotency_key
            with DuckDBSink(output, "synthetic-ef1") as reader:
                receipt = reader.lookup(idempotency_key(envelope.identity)).receipt
                self.assertIsNotNone(receipt)
                self.assertEqual(encode_result(reader.read(receipt)[0]), encode_result(result))

    def test_publication_example_oversized_refused_before_sink_creation(self):
        example = Path(__file__).resolve().parents[2] / "examples" / "ef1" / "publish_result.py"
        with TemporaryDirectory() as temp:
            source = Path(temp) / "oversized.json"
            source.write_bytes(b"x" * 1048577)
            output = Path(temp) / "never-created.duckdb"
            args = [str(example), str(source), str(output), "--destination-scope", "synthetic-ef1",
                    "--generation-id", "oversized", "--job-id", "anchor", "--partition-id", "X-S"]
            with mock.patch.object(sys, "argv", args), mock.patch("equity_feature_duckdb_sink.DuckDBSink") as sink:
                with self.assertRaises(SystemExit) as caught:
                    runpy.run_path(str(example), run_name="__main__")
                self.assertEqual(caught.exception.code, 2)
                sink.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
