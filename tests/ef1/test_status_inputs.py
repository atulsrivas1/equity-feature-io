"""Original status conversion fixtures; source authored, not locally executed."""
from dataclasses import replace
import unittest

from equity_feature_contracts import BatchMetadata, Column, ContractError, Coverage, ErrorCode, SourceBinding
from equity_feature_duckdb.ef1 import (
    StatusCertificate, StatusInputs, StatusState, make_status_proof, make_status_states,
    synthetic_status_context, synthetic_status_fixture,
)


def metadata(input_id="st", coverage=Coverage(1, 1, True)):
    return BatchMetadata("SYN", SourceBinding("F", "R1", "ef1-reference-map1", input_id), coverage, None)


def states(rows=None, **changes):
    args = dict(dimension="ssr", epoch="e", metadata=metadata(), instrument_id="X", session_id="S")
    args.update(changes)
    return make_status_states((StatusState(0, "seed", 5, None, "on", 5),) if rows is None else rows, **args)


def mutate(batch, name, values):
    return replace(batch, columns=tuple(Column(c.name, values) if c.name == name else c for c in batch.columns))


class StatusInputTests(unittest.TestCase):
    def test_literal_reference_grammar_and_original_source_facts(self):
        packet = synthetic_status_fixture(case="S01")
        self.assertEqual(packet.status_states.column("reference_id").values, (
            "s1:t:ZQ:0000000000000000000:c2VlZA",
            "s1:t:ZQ:0000000000000000001:aGFsdA",
            "s1:t:ZQ:0000000000000000002:cmVzdW1l"))
        self.assertEqual(packet.status_states.column("effective_start_ns").values, (8, 12, 16))
        self.assertEqual(packet.status_states.column("known_at_ns").values, (8, 12, 16))
        self.assertEqual(packet.status_states.column("text").values, ("active", "halted", "active"))
        self.assertEqual(packet.status_prefix.column("reference_id").values, ("p1:t:ZQ:c3Q:cHJlZg",))
        self.assertEqual(packet.status_validity.column("reference_id").values, ("p1:t:ZQ:c3Q:dmFsaWQ",))
        self.assertEqual(packet.status_prefix.column("effective_end_ns").values, (20,))
        self.assertEqual(packet.status_validity.column("effective_end_ns").values, (21,))
        self.assertEqual(packet.status_states.metadata.source.input_id, "st")
        self.assertEqual(packet.status_states.metadata.source.mapping_version, "ef1-reference-map1")
        self.assertEqual(packet.roles, ("calendar_provenance", "status_states", "status_prefix", "status_validity"))
        self.assertTrue(all(a is b for a, b in zip(packet.slots, packet.batches)))

    def test_s02_s03_literal_rows_and_explicit_seed_not_generated_from_first_row(self):
        two, three = synthetic_status_fixture(case="S02"), synthetic_status_fixture(case="S03")
        self.assertEqual(two.status_states.column("reference_id").values, ("s1:s:ZQ:0000000000000000000:c2VlZA",))
        self.assertEqual(two.status_prefix.column("effective_end_ns").values, (16,))
        self.assertEqual(two.status_validity.column("effective_end_ns").values, (17,))
        self.assertEqual(three.status_states.column("reference_id").values,
            ("s1:s:ZQ:0000000000000000000:YQ", "s1:s:ZQ:0000000000000000001:Yg"))
        self.assertEqual(three.status_states.column("effective_start_ns").values, (5, 5))
        self.assertEqual(three.status_states.column("text").values, ("on", "off"))
        self.assertEqual(synthetic_status_context(case="S03")["selection"], {
            "dimension": "ssr", "epoch": "e", "seed_reference_id": "s1:s:ZQ:0000000000000000000:YQ", "max_age_ns": None})
        first = synthetic_status_context()
        first["selection"]["seed_reference_id"] = None
        self.assertEqual(synthetic_status_context()["selection"]["seed_reference_id"],
                         "s1:t:ZQ:0000000000000000000:c2VlZA")

    def test_missing_each_and_all_preserves_four_slots_and_original_present_bindings(self):
        packet = synthetic_status_fixture()
        for missing in range(4):
            slots = list(packet.slots)
            slots[missing] = None
            modes = tuple("unavailable" if i == missing else "duckdb_backed_observed" for i in range(4))
            actual = StatusInputs(*slots, provenance=modes)
            self.assertEqual(len(actual.slots), 4)
            self.assertIsNone(actual.slots[missing])
            self.assertEqual(actual.roles, packet.roles)
            self.assertEqual(actual.batches, tuple(batch for batch in slots if batch is not None))
            self.assertTrue(all(a is b for a, b in zip(actual.batches, (batch for batch in slots if batch is not None))))
        absent = StatusInputs(None, None, None, None, ("unavailable",) * 4)
        self.assertEqual(absent.slots, (None,) * 4)
        self.assertEqual(absent.batches, ())
        with self.assertRaises(ContractError):
            replace(packet, provenance=("unavailable",) * 4)

    def test_present_empty_and_unknown_population_are_never_missing_or_completed(self):
        packet = synthetic_status_fixture(case="S02")
        for coverage in (Coverage(0, 0, True), Coverage(None, 0, False)):
            empty = states((), metadata=metadata(coverage=coverage))
            actual = replace(packet, status_states=empty)
            self.assertIs(actual.slots[1], empty)
            self.assertEqual(len(actual.batches), 4)
            self.assertEqual(actual.status_states.metadata.coverage, coverage)
        incomplete = states(metadata=metadata(coverage=Coverage(None, 1, False)))
        self.assertEqual(incomplete.metadata.coverage, Coverage(None, 1, False))

    def test_unknown_future_precise_known_at_and_sequence_gaps_preserved(self):
        for known in (None, 99, 9007199254740993):
            batch = states((StatusState(42, "event", 5, None, "on", known),))
            self.assertEqual(batch.column("known_at_ns").values, (known,))
            self.assertEqual(batch.column("reference_id").values, ("s1:s:ZQ:0000000000000000042:ZXZlbnQ",))
        proof = make_status_proof((StatusCertificate("p", 5, 20, None),), role="status_prefix",
            dimension="ssr", epoch="e", target_input_id="st", metadata=metadata("p"), instrument_id="X", session_id="S")
        self.assertEqual(proof.column("known_at_ns").values, (None,))

    def test_no_order_repair_sequence_generation_or_unsafe_identity(self):
        invalid = (
            (StatusState(True, "x", 5, None, "on", 5),),
            (StatusState(-1, "x", 5, None, "on", 5),),
            (StatusState(2**63, "x", 5, None, "on", 5),),
            (StatusState(0, "x\n", 5, None, "on", 5),),
            (StatusState(0, "x" * 100, 5, None, "on", 5),),
            (StatusState(1, "x", 5, None, "on", 5), StatusState(0, "y", 6, None, "off", 6)),
            (StatusState(0, "x", 5, None, "on", 5), StatusState(0, "y", 5, None, "off", 5)),
        )
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ContractError):
                states(rows, metadata=metadata(coverage=Coverage(len(rows), len(rows), True)))

    def test_original_identity_and_wrong_role_negative_controls(self):
        packet = synthetic_status_fixture(case="S02")
        for invalid in ("s1:s:ZQ==:0000000000000000000:c2VlZA",  # padding
                        "s1:s:ZR:0000000000000000000:c2VlZA",  # noncanonical pad bits
                        "s1:s:_w:0000000000000000000:c2VlZA",  # invalid UTF8
                        "s1:s:ZQ:0:c2VlZA", "s1:s:ZQ:9223372036854775808:c2VlZA"):
            with self.assertRaises(ContractError):
                replace(packet, status_states=mutate(packet.status_states, "reference_id", (invalid,)))
        for field, value in (("reference_id", "p1:s:ZQ:d3Jvbmc:cHJlZg"),
                             ("fact_kind", "ef1.status.validity")):
            with self.assertRaises(ContractError):
                replace(packet, status_prefix=mutate(packet.status_prefix, field, (value,)))
        wrong_source = replace(packet.status_prefix, metadata=replace(packet.status_prefix.metadata,
            source=replace(packet.status_prefix.metadata.source, snapshot_id="R2")))
        with self.assertRaises(ContractError):
            replace(packet, status_prefix=wrong_source)
        missing_states = replace(packet, status_states=None, provenance=("synthetic", "unavailable", "synthetic", "synthetic"))
        with self.assertRaises(ContractError):
            replace(missing_states, status_prefix=wrong_source)
        with self.assertRaises(ContractError):
            replace(packet, status_prefix=packet.status_validity)


    def test_matching_status_origin_and_source_with_independent_calendar(self):
        packet = synthetic_status_fixture(case="S02")
        observed = replace(packet, provenance=("synthetic", "duckdb_backed_observed",
                                              "duckdb_backed_observed", "duckdb_backed_observed"))
        self.assertIs(observed.status_states, packet.status_states)
        with self.assertRaises(ContractError):
            replace(packet, provenance=("synthetic", "duckdb_backed_observed", "synthetic", "synthetic"))
        empty_proof = replace(packet.status_prefix,
            columns=tuple(Column(c.name, ()) for c in packet.status_prefix.columns),
            metadata=replace(packet.status_prefix.metadata, coverage=Coverage(0, 0, True),
                source=replace(packet.status_prefix.metadata.source, source_id="another-publisher")))
        with self.assertRaises(ContractError):
            replace(packet, status_prefix=empty_proof)

    def test_count_and_aggregate_bound_no_population_invention(self):
        with self.assertRaises(ContractError):
            states(metadata=metadata(coverage=Coverage(0, 0, True)))
        packet = synthetic_status_fixture(case="S02")
        for count in (4093, 4094):
            population = states(tuple(StatusState(i, str(i), 5, None, "on", 5) for i in range(count)),
                                metadata=metadata(coverage=Coverage(count, count, True)))
            if count == 4093:
                self.assertEqual(sum(b.row_count for b in replace(packet, status_states=population).batches), 4096)
            else:
                with self.assertRaises(ContractError) as caught:
                    replace(packet, status_states=population)
                self.assertEqual(caught.exception.code, ErrorCode.BOUNDS)

    def test_quoting_unicode_reversible_and_maximum_sequence(self):
        actual = states((StatusState(9223372036854775807, "é", 5, None, "enabled", 5),), dimension="quoting")
        self.assertEqual(actual.column("reference_id").values,
                         ("s1:q:ZQ:9223372036854775807:w6k",))
        self.assertEqual(actual.column("fact_kind").values, ("ef1.status.quoting",))
        self.assertEqual(actual.column("text").values, ("enabled",))

if __name__ == "__main__":
    unittest.main()
