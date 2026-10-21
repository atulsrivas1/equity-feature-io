"""Independent literal path goldens and unchanged sink composition; unexecuted."""
from dataclasses import replace
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ContractError,
    Coverage, DataKind, EntityKey, ErrorCode, InputScope, PriceUnit, SessionSpec, SourceBinding, WindowSpec,
)
from equity_feature_duckdb.ef1 import (
    PathGapInputs, synthetic_path_gap_fixture, synthetic_path_gap_context,
    synthetic_path_drive_fixture, synthetic_path_drive_context,
)
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import build_ef1_config, compute_ef1

# Expectations are literal reviewed mathematics, never values from another run.
GAP = ("session.gap.fill_fraction", "session.gap.filled", "session.gap.first_fill_ns", "session.gap.remaining_fraction")
DRIVE = ("session.opening_drive.excursion_down", "session.opening_drive.excursion_up", "session.opening_drive.return")
GOLDENS = {"G01": ((1.0, True, 12, 0.0), 4, 7), "G02": ((0.5, False, None, 0.5), 2, 3),
           "G03": ((1.0, True, 12, 0.0), 4, 7), "D01": ((0.0, 0.2, 0.1), 3, 4)}


def config(case="G01", cutoff=None, mode="known_at"):
    drive = case == "D01"
    context = synthetic_path_drive_context() if drive else synthetic_path_gap_context(case=case)
    cutoff = (15 if drive else 12 if case == "G02" else 13) if cutoff is None else cutoff
    availability = AvailabilitySpec(cutoff, cutoff, cutoff)
    if mode == "reconstruction":
        availability = replace(availability, mode=mode, reconstruction_reason="synthetic replay")
    return build_ef1_config(context,
        session=SessionSpec("SYN", "S", 10, 30, "UTC", scheduled_close_ns=30, early_close=False),
        window=WindowSpec(1 if drive else 2, "S", ("S",) if drive else ("P", "S"), "completed_eod"),
        availability=availability, price_unit=PriceUnit(0, "USD"), adjustment=AdjustmentSpec())


def calculate(case="G01", packet=None, **kwargs):
    if packet is None:
        packet = synthetic_path_drive_fixture() if case == "D01" else synthetic_path_gap_fixture(case=case)
    return compute_ef1(packet.batches, config(case, **kwargs), entity=EntityKey("X", "S"))


def values(result):
    return {column.feature_id: column.values[0] for column in result.values}


def change_column(batch, name, cells):
    return replace(batch, columns=tuple(Column(c.name, cells) if c.name == name else c for c in batch.columns))


def independent_g01():
    """Raw independent source population: no production fixture/converter used."""
    calendar_bytes = (b'{"calendar_id":"SYN-CAL","early_close":false,"revision":"R1","scheduled_close_ns":30,'
        b'"segments":[["regular",10,30]],"sessions":[["P","2026-10-19",-10,0],["S","2026-10-20",10,30]],'
        b'"target_date":"2026-10-20","timezone":"UTC"}')
    def batch(kind, names, rows, source, input_id, scope=None):
        columns = tuple(Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
        return CanonicalBatch(kind, columns, BatchMetadata("SYN",
            SourceBinding(source, "R1", "ef1-reference-map1" if scope is None else "ef1-path-map1", input_id),
            Coverage(len(rows), len(rows), True), None if scope is None else PriceUnit(0, "USD"),
            AdjustmentSpec(), scope=scope))
    proof = batch(DataKind.REFERENCE, ("instrument_id", "session_id", "reference_id", "fact_kind",
        "effective_start_ns", "effective_end_ns", "text", "known_at_ns"),
        (("X", "S", "c1:" + hashlib.sha256(calendar_bytes).hexdigest(), "ef1.calendar.provenance",
          -10, 30, "supplied_schedule", -10),), "SYN-CALENDAR", "calendar")
    path = batch(DataKind.TRADE, ("instrument_id", "session_id", "event_ns", "order_key", "event_id",
        "eligible", "price", "size", "known_at_ns"),
        (("X", "S", 10, 0, "a", True, 12, 1, 10), ("X", "S", 11, 1, "b", True, 11, 1, 11),
         ("X", "S", 12, 2, "c", True, 9, 1, 12)), "SYN-PATH", "path", InputScope(10, 13, "supplied_path"))
    prior = batch(DataKind.DAILY, ("instrument_id", "session_id", "start_ns", "end_ns", "close", "known_at_ns"),
        (("X", "P", -10, 0, 10, 0),), "SYN-DAILY", "prior", InputScope(-10, 0, "supplied_path"))
    return PathGapInputs(proof, path, prior, ("synthetic",) * 3)


class PathCompositionTests(unittest.TestCase):
    def test_four_literal_independent_value_population_and_evidence_goldens(self):
        for case, (expected, count, evidence_count) in GOLDENS.items():
            with self.subTest(case=case):
                actual = calculate(case)
                headers = DRIVE if case == "D01" else GAP
                self.assertEqual(tuple(column.feature_id for column in actual.values), headers)
                for feature, value in zip(headers, expected):
                    if type(value) is float:
                        self.assertAlmostEqual(values(actual)[feature], value, delta=1e-12)
                    else:
                        self.assertEqual(values(actual)[feature], value)
                self.assertEqual(len(actual.evidence), evidence_count)
                for row in actual.quality:
                    self.assertEqual((row.expected, row.observed), (count, count))
                    status, reasons = (("not_applicable", ("no_eligible_observations",))
                        if case == "G02" and row.feature_id == GAP[2] else ("available", ()))
                    self.assertEqual((row.status.value, tuple(r.value for r in row.reasons)), (status, reasons))

    def test_independent_raw_source_and_adapter_full_result_identity(self):
        self.assertEqual(encode_result(calculate(packet=independent_g01())), encode_result(calculate()))

    def test_gap_prefix_no_hit_and_bar_low_crossing_do_not_invent_hits(self):
        packet = synthetic_path_gap_fixture()
        path = replace(packet.path, columns=tuple(Column(c.name, c.values[:2]) for c in packet.path.columns),
            metadata=replace(packet.path.metadata, coverage=Coverage(2, 2, True),
                scope=replace(packet.path.metadata.scope, end_ns=12)))
        actual = calculate(packet=replace(packet, path=path), cutoff=12)
        self.assertEqual(tuple(values(actual)[key] for key in GAP), (0.5, False, None, 0.5))
        self.assertEqual(len(actual.evidence), 5)
        self.assertEqual(tuple(values(calculate("G02"))[key] for key in GAP), (0.5, False, None, 0.5))

    def test_reversal_retains_maximum_fill_and_first_hit(self):
        packet = synthetic_path_gap_fixture()
        actual = calculate(packet=replace(packet, path=change_column(packet.path, "price", (12, 10, 11))))
        self.assertEqual(tuple(values(actual)[key] for key in GAP), (1.0, True, 11, 0.5))
        self.assertEqual({row.row_id for row in actual.evidence if row.feature_id == GAP[2]}, {"b"})

    def test_overshoot_remaining_has_no_upper_clamp(self):
        packet = synthetic_path_gap_fixture()
        actual = calculate(packet=replace(packet, path=change_column(packet.path, "price", (12, 9, 14))))
        self.assertEqual(tuple(values(actual)[key] for key in GAP), (1.0, True, 11, 2.0))

    def test_missing_each_role_never_fabricates_binding(self):
        packet = synthetic_path_gap_fixture()
        for index, role in enumerate(packet.roles):
            modes = tuple("unavailable" if i == index else "synthetic" for i in range(3))
            partial = replace(packet, **{role: None, "provenance": modes})
            actual = calculate(packet=partial)
            self.assertTrue(all(v is None for v in values(actual).values()))
            self.assertTrue(all(row.status.value == "missing_input" for row in actual.quality))
            self.assertEqual(len(actual.metadata.inputs), 2)
            self.assertEqual(actual.evidence, ())
            self.assertTrue(all("absent_input" in tuple(r.value for r in row.reasons) for row in actual.quality))

    def test_original_known_at_required_for_each_role_in_both_modes(self):
        packet = synthetic_path_gap_fixture()
        for mode in ("known_at", "reconstruction"):
            for role in packet.roles:
                batch = getattr(packet, role)
                for known, reason in ((None, "unknown_availability"), (14, "future_knowledge")):
                    changed = change_column(batch, "known_at_ns", (known,) * batch.row_count)
                    actual = calculate(packet=replace(packet, **{role: changed}), mode=mode)
                    self.assertTrue(all(v is None for v in values(actual).values()))
                    self.assertTrue(all(reason in tuple(r.value for r in row.reasons) for row in actual.quality))
                    self.assertEqual(actual.evidence, ())

    def test_incomplete_and_unknown_population_and_complete_empty(self):
        packet = synthetic_path_gap_fixture()
        incomplete = replace(packet.path, metadata=replace(packet.path.metadata, coverage=Coverage(None, 3, False)))
        actual = calculate(packet=replace(packet, path=incomplete))
        self.assertTrue(all((r.status.value, r.expected, r.observed) == ("incomplete_coverage", None, 4) for r in actual.quality))
        empty = replace(packet.path, columns=tuple(Column(c.name, ()) for c in packet.path.columns),
            metadata=replace(packet.path.metadata, coverage=Coverage(0, 0, True)))
        actual = calculate(packet=replace(packet, path=empty))
        self.assertTrue(all((r.status.value, r.expected, r.observed) == ("not_applicable", 1, 1) for r in actual.quality))
        self.assertEqual(actual.evidence, ())

    def test_unfinished_drive_prefix_is_incomplete(self):
        packet = synthetic_path_drive_fixture()
        path = replace(packet.path, columns=tuple(Column(c.name, c.values[:2]) for c in packet.path.columns),
            metadata=replace(packet.path.metadata, coverage=Coverage(2, 2, True),
                scope=replace(packet.path.metadata.scope, end_ns=14)))
        actual = calculate("D01", packet=replace(packet, path=path), cutoff=14)
        self.assertTrue(all(v is None for v in values(actual).values()))
        self.assertTrue(all(r.status.value == "incomplete_coverage" for r in actual.quality))
        self.assertEqual(actual.evidence, ())

    def test_wrong_prior_session_and_endpoint_trade_reject(self):
        packet = synthetic_path_gap_fixture()
        wrong = change_column(packet.prior_close, "session_id", ("S",))
        with self.assertRaises(ContractError):
            calculate(packet=replace(packet, prior_close=wrong))
        drive = synthetic_path_drive_fixture()
        endpoint = change_column(drive.path, "event_ns", (10, 12, 15))
        with self.assertRaises(ContractError) as caught:
            calculate("D01", packet=replace(drive, path=endpoint))
        self.assertEqual(caught.exception.code, ErrorCode.BOUNDS)

    def test_full_canonical_result_sink_bytes_idempotence_and_reopen(self):
        limits = SinkRequirements(max_results=1, max_chunk_bytes=1048576, max_total_bytes=1048576,
                                  max_result_cells=4, max_evidence_rows=128)
        for case in GOLDENS:
            with self.subTest(case=case), TemporaryDirectory() as temp:
                result = calculate(case)
                # Independent literal goldens above gate the source calculation;
                # this checks preservation of the entire result at the I/O boundary.
                envelope = prepare_publication((result,), destination_scope="synthetic-path",
                    generation_id=case, job_id="path-" + case, partition_id="X-S", limits=limits)
                output = Path(temp) / "new-path-results.duckdb"
                with DuckDBSink(output, "synthetic-path", limits=limits) as sink:
                    receipt = publish(sink, envelope, (result,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]), encode_result(result))
                    self.assertEqual(publish(sink, envelope, (result,)), receipt)
                with DuckDBSink(output, "synthetic-path", limits=limits) as reader:
                    self.assertEqual(reader.lookup(receipt.idempotency_key).receipt, receipt)
                    self.assertEqual(encode_result(reader.read(receipt)[0]), encode_result(result))


if __name__ == "__main__":
    unittest.main()
