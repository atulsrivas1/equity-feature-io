"""Path packet/conversion source controls; runtime execution remains pending."""
from dataclasses import replace
import unittest

from equity_feature_contracts import CanonicalBatch, Column, ContractError, Coverage, DataKind, ErrorCode
from equity_feature_duckdb.ef1 import (
    PathGapInputs, PathDriveInputs, make_path_prior_close,
    synthetic_path_gap_fixture, synthetic_path_gap_context,
    synthetic_path_drive_fixture, synthetic_path_drive_context,
)


class PathInputTests(unittest.TestCase):
    def test_literal_gap_source_populations_and_distinct_sources(self):
        one, two, three = (synthetic_path_gap_fixture(case=c) for c in ("G01", "G02", "G03"))
        self.assertEqual(one.path.column("price").values, (12, 11, 9))
        self.assertEqual(two.path.column("low").values, (9,))
        self.assertEqual(two.path.column("close").values, (11,))
        self.assertEqual(three.path.column("price").values, (10, 11, 12))
        self.assertEqual(three.prior_close.column("close").values, (12,))
        self.assertEqual(one.prior_close.column("session_id").values, ("P",))
        self.assertEqual(one.path.metadata.source.source_id, "SYN-PATH")
        self.assertEqual(one.prior_close.metadata.source.source_id, "SYN-DAILY")
        self.assertEqual(one.provenance, ("synthetic",) * 3)

    def test_literal_drive_source_population_scope_and_calendar(self):
        packet = synthetic_path_drive_fixture()
        self.assertEqual(packet.path.column("event_ns").values, (10, 12, 14))
        self.assertEqual(packet.path.column("price").values, (10, 12, 11))
        self.assertEqual((packet.path.metadata.scope.start_ns, packet.path.metadata.scope.end_ns), (10, 15))
        context = synthetic_path_drive_context()
        self.assertEqual(context["selection"], {"sampling": "eligible_trade", "duration_ns": 5})
        self.assertEqual(context["calendar"]["sessions"], [["S", "2026-10-20", 10, 30]])

    def test_exact_explicit_column_orders_and_original_knowledge(self):
        packet = synthetic_path_gap_fixture()
        self.assertEqual(tuple(c.name for c in packet.prior_close.columns),
            ("instrument_id", "session_id", "start_ns", "end_ns", "close", "known_at_ns"))
        self.assertEqual(tuple(c.name for c in packet.calendar_provenance.columns),
            ("instrument_id", "session_id", "reference_id", "fact_kind", "effective_start_ns",
             "effective_end_ns", "text", "known_at_ns"))
        self.assertEqual(packet.calendar_provenance.column("known_at_ns").values, (-10,))
        self.assertEqual(packet.path.column("known_at_ns").values, (10, 11, 12))
        self.assertEqual(packet.prior_close.column("known_at_ns").values, (0,))

    def test_each_absent_gap_role_preserves_present_object_order(self):
        packet = synthetic_path_gap_fixture()
        self.assertEqual(packet.roles, ("calendar_provenance", "path", "prior_close"))
        for index, role in enumerate(packet.roles):
            modes = tuple("unavailable" if i == index else "synthetic" for i in range(3))
            changed = replace(packet, **{role: None, "provenance": modes})
            expected = tuple(b for i, b in enumerate(packet.batches) if i != index)
            self.assertEqual(changed.batches, expected)
            self.assertTrue(all(a is b for a, b in zip(changed.batches, expected)))
        self.assertEqual(PathGapInputs().batches, ())

    def test_each_absent_drive_role_and_empty_packet(self):
        packet = synthetic_path_drive_fixture()
        self.assertEqual(packet.roles, ("calendar_provenance", "path"))
        for index, role in enumerate(packet.roles):
            modes = tuple("unavailable" if i == index else "synthetic" for i in range(2))
            changed = replace(packet, **{role: None, "provenance": modes})
            self.assertEqual(changed.batches, (packet.batches[1 - index],))
        self.assertEqual(PathDriveInputs().batches, ())

    def test_truthful_independent_origin_modes(self):
        packet = synthetic_path_gap_fixture()
        mixed = replace(packet, provenance=("synthetic", "synthetic", "duckdb_backed_observed"))
        self.assertIs(mixed.prior_close, packet.prior_close)
        for modes in (("unavailable",) * 3, ("synthetic",), ["synthetic"] * 3,
                      ("synthetic", "observed", "synthetic")):
            with self.assertRaises(ContractError):
                replace(packet, provenance=modes)

    def test_wrong_role_kind_duplicate_ids_and_namespace_reject(self):
        packet = synthetic_path_gap_fixture()
        duplicate = replace(packet.prior_close, metadata=replace(packet.prior_close.metadata,
            source=replace(packet.prior_close.metadata.source, input_id="path")))
        other_namespace = replace(packet.prior_close, metadata=replace(packet.prior_close.metadata, namespace="OTHER"))
        for changes in ({"path": packet.prior_close}, {"prior_close": packet.path},
                        {"calendar_provenance": packet.path}, {"prior_close": duplicate},
                        {"prior_close": other_namespace}):
            with self.assertRaises(ContractError):
                replace(packet, **changes)

    def test_present_empty_unknown_coverage_retains_original_metadata(self):
        packet = synthetic_path_gap_fixture()
        empty = replace(packet.path, columns=tuple(Column(c.name, ()) for c in packet.path.columns),
            metadata=replace(packet.path.metadata, coverage=Coverage(None, 0, False)))
        actual = replace(packet, path=empty)
        self.assertIs(actual.batches[1], empty)
        self.assertEqual(actual.path.metadata.coverage, Coverage(None, 0, False))
        self.assertEqual(len(actual.batches), 3)

    def test_explicit_prior_converter_preserves_all_supplied_cells(self):
        meta = synthetic_path_gap_fixture().prior_close.metadata
        row = {"start_ns": -10, "end_ns": 0, "open": 10, "high": 12, "low": 9,
               "close": 11, "volume": 2, "actual_notional": 22, "known_at_ns": None}
        batch = make_path_prior_close(row, metadata=meta, instrument_id="X", session_id="P")
        self.assertEqual(batch.kind, DataKind.DAILY)
        self.assertIs(batch.metadata, meta)
        for field, value in row.items():
            self.assertEqual(batch.column(field).values, (value,))
        row["close"] = 99
        self.assertEqual(batch.column("close").values, (11,))

    def test_no_optional_close_volume_or_known_column_inference(self):
        meta = synthetic_path_gap_fixture().prior_close.metadata
        batch = make_path_prior_close({"start_ns": -10, "end_ns": 0},
            metadata=meta, instrument_id="X", session_id="P")
        self.assertIsNone(batch.column("close"))
        self.assertIsNone(batch.column("volume"))
        self.assertIsNone(batch.column("known_at_ns"))

    def test_prior_invalid_present_volume_and_ohlc_are_never_dropped(self):
        meta = synthetic_path_gap_fixture().prior_close.metadata
        for payload in ({"close": 10, "volume": 0}, {"close": None, "volume": 1},
                        {"close": 10, "open": 11, "high": 9, "low": 8, "volume": 1}):
            with self.assertRaises(ContractError) as caught:
                make_path_prior_close({"start_ns": -10, "end_ns": 0, **payload},
                    metadata=meta, instrument_id="X", session_id="P")
            self.assertEqual(caught.exception.code, ErrorCode.INVALID_SCHEMA)
        zero = make_path_prior_close({"start_ns": -10, "end_ns": 0, "close": None, "volume": 0},
            metadata=meta, instrument_id="X", session_id="P")
        self.assertEqual(zero.column("volume").values, (0,))

    def test_no_prior_time_or_unknown_field_defaults(self):
        meta = synthetic_path_gap_fixture().prior_close.metadata
        for row in ({"close": 10}, {"start_ns": -10, "end_ns": 0, "unrecognized": 1}):
            with self.assertRaises(ContractError):
                make_path_prior_close(row, metadata=meta, instrument_id="X", session_id="P")

    def test_path_structural_validation_before_readiness(self):
        packet = synthetic_path_gap_fixture()
        invalid = replace(packet.path, columns=tuple(
            Column(c.name, (None, 11, 9)) if c.name == "price" else c for c in packet.path.columns))
        with self.assertRaises(ContractError) as caught:
            PathGapInputs(path=invalid, provenance=("unavailable", "synthetic", "unavailable"))
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_SCHEMA)

    def test_no_trade_sorting_or_duplicate_identity_repair(self):
        packet = synthetic_path_gap_fixture()
        for columns in (tuple(Column(c.name, tuple(reversed(c.values))) for c in packet.path.columns),
                        tuple(Column(c.name, ("a", "a", "c")) if c.name == "event_id" else c for c in packet.path.columns)):
            with self.assertRaises(ContractError):
                replace(packet, path=CanonicalBatch(DataKind.TRADE, columns, packet.path.metadata))

    def test_contexts_are_owned_and_unknown_cases_reject(self):
        context = synthetic_path_gap_context()
        context["calendar"]["sessions"].clear()
        self.assertEqual(len(synthetic_path_gap_context()["calendar"]["sessions"]), 2)
        for factory in (synthetic_path_gap_context, synthetic_path_gap_fixture,
                        synthetic_path_drive_context, synthetic_path_drive_fixture):
            with self.assertRaises(ContractError):
                factory(case="UNKNOWN")


if __name__ == "__main__":
    unittest.main()
