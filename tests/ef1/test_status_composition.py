"""Hand-authored independent status goldens and real sink composition; unexecuted."""
from dataclasses import replace
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ContractError,
    Coverage, DataKind, EntityKey, ErrorCode, SessionSpec, SourceBinding, WindowSpec,
)
from equity_feature_duckdb.ef1 import StatusInputs, synthetic_status_fixture, synthetic_status_context
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_sdk import encode_result, prepare_publication, publish
from equity_features.ef1 import build_ef1_config, compute_ef1


CALENDAR = {"calendar_id": "C01", "revision": "R1", "timezone": "UTC", "target_date": "2026-01-02",
    "sessions": [["S", "2026-01-02", 10, 30]],
    "segments": [["premarket", 0, 10], ["regular", 10, 30], ["postmarket", 30, 40]],
    "scheduled_close_ns": 40, "early_close": True}
CALENDAR_BYTES = (b'{"calendar_id":"C01","early_close":true,"revision":"R1","scheduled_close_ns":40,'
    b'"segments":[["premarket",0,10],["regular",10,30],["postmarket",30,40]],'
    b'"sessions":[["S","2026-01-02",10,30]],"target_date":"2026-01-02","timezone":"UTC"}')
STATE_ROWS = {
    "S01": (("s1:t:ZQ:0000000000000000000:c2VlZA", "ef1.status.trading", 8, None, "active", 8),
            ("s1:t:ZQ:0000000000000000001:aGFsdA", "ef1.status.trading", 12, None, "halted", 12),
            ("s1:t:ZQ:0000000000000000002:cmVzdW1l", "ef1.status.trading", 16, None, "active", 16)),
    "S02": (("s1:s:ZQ:0000000000000000000:c2VlZA", "ef1.status.ssr", 5, None, "on", 5),),
    "S03": (("s1:s:ZQ:0000000000000000000:YQ", "ef1.status.ssr", 5, None, "on", 5),
            ("s1:s:ZQ:0000000000000000001:Yg", "ef1.status.ssr", 5, None, "off", 5)),
}


def reference(input_id, rows, coverage=None):
    names = ("reference_id", "fact_kind", "effective_start_ns", "effective_end_ns", "text", "known_at_ns")
    columns = (Column("instrument_id", ("X",) * len(rows)), Column("session_id", ("S",) * len(rows))) + tuple(
        Column(name, tuple(row[i] for row in rows)) for i, name in enumerate(names))
    return CanonicalBatch(DataKind.REFERENCE, columns, BatchMetadata("SYN",
        SourceBinding("F", "R1", "ef1-reference-map1", input_id),
        Coverage(len(rows), len(rows), True) if coverage is None else coverage, None))


def independent_packet(case="S01"):
    """Raw original source declarations; no production conversion or result oracle."""
    code = "t" if case == "S01" else "s"
    start = 8 if case == "S01" else 5
    prefix_end, validity_end = (16, 17) if case == "S02" else (20, 21)
    calendar = reference("calendar", (("c1:" + hashlib.sha256(CALENDAR_BYTES).hexdigest(),
        "ef1.calendar.provenance", 0, 40, "supplied_schedule", 5),))
    prefix = reference("prefix", ((f"p1:{code}:ZQ:c3Q:cHJlZg", "ef1.status.prefix_complete",
        start, prefix_end, code, start),))
    validity = reference("validity", ((f"p1:{code}:ZQ:c3Q:dmFsaWQ", "ef1.status.validity",
        start, validity_end, code, start),))
    return StatusInputs(calendar, reference("st", STATE_ROWS[case]), prefix, validity, ("synthetic",) * 4)


def config(case="S01", cutoff=17, knowledge=None, max_age=None, seed="original", availability_mode="known_at"):
    code, dimension = ("t", "trading") if case == "S01" else ("s", "ssr")
    original = f"s1:{code}:ZQ:0000000000000000000:" + ("YQ" if case == "S03" else "c2VlZA")
    context = {"version": "ef1-context1", "producer": "status", "calendar": CALENDAR,
        "selection": {"dimension": dimension, "epoch": "e", "seed_reference_id": original if seed == "original" else seed,
                      "max_age_ns": max_age}}
    availability = AvailabilitySpec(cutoff, cutoff if knowledge is None else knowledge, 20)
    if availability_mode == "reconstruction":
        availability = replace(availability, mode="reconstruction", reconstruction_reason="synthetic replay")
    return build_ef1_config(context,
        session=SessionSpec("SYN", "S", 10, 30, "UTC", scheduled_close_ns=40, early_close=True),
        window=WindowSpec(1, "S", ("S",), "completed_eod"), availability=availability,
        price_unit=None, adjustment=AdjustmentSpec())


def result(packet=None, case="S01", **query):
    return compute_ef1((independent_packet(case) if packet is None else packet).slots,
                       config(case, **query), entity=EntityKey("X", "S"))


def cells(actual):
    return {column.feature_id.rsplit(".", 1)[1]: column.values[0] for column in actual.values}


def factual_quality(actual):
    return {row.feature_id.rsplit(".", 1)[1]: (row.status.value, tuple(r.value for r in row.reasons))
            for row in actual.quality if ".admission_" not in row.feature_id}


def change(batch, name, values):
    return replace(batch, columns=tuple(Column(c.name, values) if c.name == name else c for c in batch.columns))


class StatusCompositionTests(unittest.TestCase):
    def test_s01_literal_boundaries_and_required_transition_knowledge(self):
        for cutoff, knowledge, state, age, reason in (
                (16, 16, "halted", 4, "none"), (17, 17, "active", 1, "none"),
                (17, 15, None, None, "future_knowledge")):
            actual = result(cutoff=cutoff, knowledge=knowledge)
            self.assertEqual(cells(actual), {"trading_state": state, "trading_age_ns": age,
                "admission_state": "ready" if reason == "none" else "unavailable", "admission_reason": reason})
            quality = ("available", ()) if reason == "none" else ("missing_input", ("future_knowledge",))
            self.assertEqual(factual_quality(actual), {"trading_state": quality, "trading_age_ns": quality})
            self.assertEqual(len(actual.evidence), 2 if reason == "none" else 0)
            self.assertTrue(all(row.status.value == "available" for row in actual.quality if ".admission_" in row.feature_id))

    def test_s02_no_default_expiry_explicit_max_and_prefix_precedence(self):
        for cutoff, max_age, state, age, reason, state_q, age_q in (
            (16, None, "on", 11, "none", ("available", ()), ("available", ())),
            (16, 10, None, 11, "stale_state", ("missing_input", ("ineligible",)), ("available", ())),
            (15, 10, "on", 10, "none", ("available", ()), ("available", ())),
            (17, None, None, None, "incomplete_status_prefix", ("incomplete_coverage", ("governed_gap",)),
                                                      ("incomplete_coverage", ("governed_gap",)))):
            actual = result(case="S02", cutoff=cutoff, max_age=max_age)
            self.assertEqual(cells(actual), {"ssr_state": state, "ssr_age_ns": age,
                "admission_state": "ready" if reason == "none" else "unavailable", "admission_reason": reason})
            self.assertEqual(factual_quality(actual), {"ssr_state": state_q, "ssr_age_ns": age_q})
        packet = independent_packet("S02")
        packet = replace(packet, status_prefix=change(packet.status_prefix, "effective_end_ns", (20,)))
        expired = result(packet, case="S02", cutoff=17)
        self.assertEqual(cells(expired)["admission_reason"], "outside_effective_interval")
        self.assertEqual(factual_quality(expired)["ssr_age_ns"], ("missing_input", ("ineligible",)))
        self.assertEqual(expired.evidence, ())

    def test_s03_equal_time_original_publisher_tie_and_exact_witness(self):
        packet = independent_packet("S03")
        actual = result(packet, case="S03", cutoff=6)
        self.assertEqual(cells(actual)["ssr_state"], "off")
        self.assertEqual(cells(actual)["ssr_age_ns"], 1)
        for witness in actual.evidence:
            self.assertEqual((witness.input_id, witness.row_id, witness.event_ns, witness.known_at_ns,
                              witness.effective_start_ns, witness.effective_end_ns, witness.use),
                             ("st", "s1:s:ZQ:0000000000000000001:Yg", 5, 5, 5, None, "consumed"))
        stale = result(case="S02", cutoff=16, max_age=10)
        witnesses = {row.feature_id.rsplit(".", 1)[1]: row for row in stale.evidence}
        self.assertEqual(witnesses["ssr_state"].use, "excluded")
        self.assertEqual(witnesses["ssr_state"].exclusion_reason.value, "ineligible")
        self.assertEqual(witnesses["ssr_age_ns"].use, "consumed")
        self.assertEqual(witnesses["ssr_age_ns"].row_id, "s1:s:ZQ:0000000000000000000:c2VlZA")

    def test_each_missing_role_all_missing_and_present_empty_keep_bindings(self):
        packet = independent_packet()
        cases = []
        for i in range(4):
            slots = list(packet.slots)
            slots[i] = None
            cases.append(StatusInputs(*slots, provenance=tuple("unavailable" if n == i else "synthetic" for n in range(4))))
        cases.append(StatusInputs(None, None, None, None, ("unavailable",) * 4))
        cases.append(replace(packet, status_states=reference("st", ())))
        for inputs in cases:
            actual = result(inputs)
            self.assertIsNone(cells(actual)["trading_state"])
            self.assertIsNone(cells(actual)["trading_age_ns"])
            self.assertEqual(cells(actual)["admission_reason"], "absent_input")
            self.assertEqual(actual.evidence, ())
            expected = {role: batch.metadata for role, batch in zip(inputs.roles, inputs.slots) if batch is not None}
            self.assertEqual({binding.role: binding.metadata for binding in actual.metadata.inputs}, expected)
            self.assertEqual(tuple(binding.role for binding in actual.metadata.inputs), tuple(sorted(expected)))
        for slots in (packet.slots[:3], packet.slots + (None,), packet.batches[1:]):
            with self.assertRaises(ContractError):
                compute_ef1(slots, config(), entity=EntityKey("X", "S"))
        with self.assertRaises(ContractError):
            compute_ef1((packet.calendar_provenance, packet.status_states, packet.status_validity, packet.status_prefix),
                        config(), entity=EntityKey("X", "S"))

    def test_original_unknown_future_knowledge_remains_causal_in_both_modes(self):
        packet = independent_packet()
        for mode in ("known_at", "reconstruction"):
            for known, reason in ((None, "unknown_availability"), (18, "future_knowledge")):
                modified = replace(packet, status_states=change(packet.status_states, "known_at_ns", (8, 12, known)))
                actual = result(modified, availability_mode=mode)
                self.assertIsNone(cells(actual)["trading_state"])
                self.assertIsNone(cells(actual)["trading_age_ns"])
                self.assertEqual(cells(actual)["admission_reason"], reason)
                self.assertEqual(actual.evidence, ())
        no_seed = result(seed=None)
        self.assertEqual(cells(no_seed)["admission_reason"], "absent_input")
        self.assertEqual(no_seed.evidence, ())

    def test_no_certificate_stitching_or_overlapping_proof_arbitration(self):
        packet = independent_packet("S02")
        fragments = reference("prefix", (
            ("p1:s:ZQ:c3Q:YQ", "ef1.status.prefix_complete", 5, 10, "s", 5),
            ("p1:s:ZQ:c3Q:Yg", "ef1.status.prefix_complete", 10, 20, "s", 5)))
        actual = result(replace(packet, status_prefix=fragments), case="S02", cutoff=16)
        self.assertEqual(cells(actual)["admission_reason"], "incomplete_status_prefix")
        overlapping = reference("prefix", (
            ("p1:s:ZQ:c3Q:YQ", "ef1.status.prefix_complete", 5, 20, "s", 5),
            ("p1:s:ZQ:c3Q:Yg", "ef1.status.prefix_complete", 5, 21, "s", 99)))
        with self.assertRaises(ContractError) as caught:
            result(replace(packet, status_prefix=overlapping), case="S02", cutoff=16)
        self.assertEqual(caught.exception.code, ErrorCode.DUPLICATE)
        nonapplicable = reference("prefix", (
            ("p1:s:ZQ:c3Q:YQ", "ef1.status.prefix_complete", 0, 4, "s", 1),
            ("p1:s:ZQ:c3Q:Yg", "ef1.status.prefix_complete", 5, 20, "s", 5)))
        self.assertEqual(cells(result(replace(packet, status_prefix=nonapplicable), case="S02", cutoff=16))["ssr_state"], "on")

    def test_actual_demo_helpers_compose_using_slots(self):
        for case, cutoff, state, age in (("S01", 17, "active", 1), ("S02", 16, "on", 11), ("S03", 6, "off", 1)):
            context = synthetic_status_context(case=case)
            independent = config(case, cutoff=cutoff)
            configured = build_ef1_config(context, session=independent.session, window=independent.window,
                availability=independent.availability, price_unit=None, adjustment=independent.adjustment)
            actual = compute_ef1(synthetic_status_fixture(case=case).slots, configured, entity=EntityKey("X", "S"))
            dimension = "trading" if case == "S01" else "ssr"
            self.assertEqual(cells(actual)[dimension + "_state"], state)
            self.assertEqual(cells(actual)[dimension + "_age_ns"], age)

    def test_actual_sink_full_canonical_readback_replay_and_sequential_reopen(self):
        limits = SinkRequirements(max_results=1, max_chunk_bytes=1048576, max_total_bytes=1048576,
                                  max_result_cells=4, max_evidence_rows=128)
        packet = independent_packet()
        unavailable = StatusInputs(None, None, None, None, ("unavailable",) * 4)
        partial = replace(packet, status_prefix=None, provenance=("synthetic", "synthetic", "unavailable", "synthetic"))
        for actual in (result(packet), result(unavailable), result(partial), result(case="S02", cutoff=16, max_age=10)):
            with TemporaryDirectory() as temp:
                envelope = prepare_publication((actual,), destination_scope="synthetic-status",
                    generation_id="status-original", job_id="status", partition_id="X-S", limits=limits)
                output = Path(temp) / "new-status-results.duckdb"
                with DuckDBSink(output, "synthetic-status", limits=limits) as sink:
                    receipt = publish(sink, envelope, (actual,))
                    self.assertEqual(encode_result(sink.read(receipt)[0]), encode_result(actual))
                    self.assertEqual(publish(sink, envelope, (actual,)), receipt)
                with DuckDBSink(output, "synthetic-status", limits=limits) as reader:
                    self.assertEqual(reader.lookup(receipt.idempotency_key).receipt, receipt)
                    self.assertEqual(encode_result(reader.read(receipt)[0]), encode_result(actual))


if __name__ == "__main__":
    unittest.main()
