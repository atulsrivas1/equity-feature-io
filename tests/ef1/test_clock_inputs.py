"""Original clock source conversion fixtures; authored without local execution."""
from dataclasses import replace
import hashlib
import unittest

from equity_feature_contracts import ContractError, DataKind, ErrorCode
from equity_feature_duckdb.ef1 import (
    ClockInputs, calendar_definition_bytes, make_calendar_provenance,
    synthetic_clock_calendar, synthetic_clock_fixture,
)

CALENDAR_ASCII = (
    b'{"calendar_id":"C01","early_close":true,"revision":"R1","scheduled_close_ns":40,'
    b'"segments":[["premarket",0,10],["regular",10,30],["postmarket",30,40]],'
    b'"sessions":[["S","2026-01-02",10,30]],"target_date":"2026-01-02","timezone":"UTC"}'
)


def proof(calendar=None, **changes):
    args = dict(namespace="SYN", instrument_id="X", session_id="S", source_id="F",
                input_id="calendar-test", known_at_ns=5, start_ns=0, end_ns=40)
    args.update(changes)
    return make_calendar_provenance(synthetic_clock_calendar() if calendar is None else calendar, **args)


class ClockInputTests(unittest.TestCase):
    def test_c01_exact_canonical_ascii_and_real_reference_shape(self):
        self.assertEqual(calendar_definition_bytes(synthetic_clock_calendar()), CALENDAR_ASCII)
        packet = synthetic_clock_fixture()
        batch = packet.calendar_provenance
        self.assertEqual(batch.kind, DataKind.REFERENCE)
        self.assertEqual(packet.roles, ("calendar_provenance",))
        self.assertEqual(packet.batches, (batch,))
        self.assertEqual(batch.column("reference_id").values,
                         ("c1:" + hashlib.sha256(CALENDAR_ASCII).hexdigest(),))
        self.assertEqual(batch.column("fact_kind").values, ("ef1.calendar.provenance",))
        self.assertEqual(batch.column("text").values, ("supplied_schedule",))
        self.assertEqual(batch.column("effective_start_ns").values, (0,))
        self.assertEqual(batch.column("effective_end_ns").values, (40,))
        self.assertEqual(batch.metadata.source.snapshot_id, "R1")
        self.assertEqual(batch.metadata.source.mapping_version, "ef1-reference-map1")
        self.assertIsNone(batch.column("price"))
        self.assertIsNone(batch.column("factor_num"))
        self.assertIsNone(batch.column("factor_den"))

    def test_original_unknown_future_and_exact_nanosecond_knowledge_preserved(self):
        for known in (None, 5, 41, 9007199254740993):
            self.assertEqual(proof(known_at_ns=known).column("known_at_ns").values, (known,))
        with self.assertRaises(ContractError):
            proof(known_at_ns=True)

    def test_hash_binds_scheduled_close_early_flag_and_revision(self):
        original = calendar_definition_bytes(synthetic_clock_calendar())
        changed_schedule = synthetic_clock_calendar()
        changed_schedule["scheduled_close_ns"] = 30
        changed_schedule["early_close"] = False
        self.assertNotEqual(calendar_definition_bytes(changed_schedule), original)
        changed_revision = synthetic_clock_calendar()
        changed_revision["revision"] = "R2"
        self.assertNotEqual(proof(changed_revision).column("reference_id"), proof().column("reference_id"))
        self.assertEqual(proof(changed_revision).metadata.source.snapshot_id, "R2")
        invalid = synthetic_clock_calendar()
        invalid["early_close"] = False
        with self.assertRaises(ContractError):
            calendar_definition_bytes(invalid)

    def test_proof_covers_all_sessions_and_segments_not_only_regular(self):
        for changes in (dict(start_ns=1), dict(end_ns=39), dict(start_ns=40, end_ns=40)):
            with self.assertRaises(ContractError) as caught:
                proof(**changes)
            self.assertEqual(caught.exception.code, ErrorCode.BOUNDS)
        history = synthetic_clock_calendar()
        history["sessions"] = [["P", "2026-01-01", -20, -10], ["S", "2026-01-02", 10, 30]]
        with self.assertRaises(ContractError):
            proof(history)
        self.assertEqual(proof(history, start_ns=-20).column("effective_start_ns").values, (-20,))

    def test_reject_unknown_fields_wrong_target_and_noncanonical_rows(self):
        invalid = synthetic_clock_calendar()
        invalid["known_at_ns"] = 5
        with self.assertRaises(ContractError):
            calendar_definition_bytes(invalid)
        with self.assertRaises(ContractError) as caught:
            proof(session_id="OTHER")
        self.assertEqual(caught.exception.code, ErrorCode.INCONSISTENT_IDENTITY)
        invalid = synthetic_clock_calendar()
        invalid["segments"] = [["regular", 10, 30], ["premarket", 30, 40]]
        with self.assertRaises(ContractError):
            calendar_definition_bytes(invalid)
        invalid = synthetic_clock_calendar()
        invalid["sessions"] = [["S", "2026-01-02", True, 30]]
        with self.assertRaises(ContractError):
            calendar_definition_bytes(invalid)

    def test_descending_civil_dates_refused_despite_ascending_utc_bounds(self):
        invalid = synthetic_clock_calendar()
        invalid["sessions"] = [["P", "2026-01-03", -20, -10], ["S", "2026-01-02", 10, 30]]
        for convert in (calendar_definition_bytes, lambda calendar: proof(calendar, start_ns=-20)):
            with self.assertRaises(ContractError) as caught:
                convert(invalid)
            self.assertEqual(caught.exception.code, ErrorCode.INVALID_ORDER)
        equal_prior_dates = synthetic_clock_calendar()
        equal_prior_dates["sessions"] = [["P", "2026-01-01", -40, -30],
                                         ["Q", "2026-01-01", -20, -10],
                                         ["S", "2026-01-02", 10, 30]]
        # The shared library rejects descending dates, not equal civil labels
        # on distinct ordered sessions; preserve that exact comparison.
        self.assertEqual(proof(equal_prior_dates, start_ns=-40).column("effective_start_ns").values, (-40,))

    def test_owned_fixture_and_explicit_observed_synthetic_missing_modes(self):
        first = synthetic_clock_calendar()
        first["segments"] = []
        self.assertEqual(calendar_definition_bytes(synthetic_clock_calendar()), CALENDAR_ASCII)
        packet = synthetic_clock_fixture()
        observed = ClockInputs(packet.calendar_provenance, "duckdb_backed_observed")
        self.assertIs(observed.calendar_provenance, packet.calendar_provenance)
        self.assertEqual(observed.provenance, "duckdb_backed_observed")
        missing = ClockInputs(None, "unavailable")
        self.assertEqual(missing.batches, ())
        self.assertEqual(missing.roles, ("calendar_provenance",))
        for batch, mode in ((None, "synthetic"), (packet.calendar_provenance, "unavailable")):
            with self.assertRaises(ContractError):
                ClockInputs(batch, mode)
        partial = replace(packet.calendar_provenance,
                          metadata=replace(packet.calendar_provenance.metadata, source=replace(
                              packet.calendar_provenance.metadata.source, input_id="separate-actual-binding")))
        self.assertIs(ClockInputs(partial, "duckdb_backed_observed").calendar_provenance, partial)


if __name__ == "__main__":
    unittest.main()
