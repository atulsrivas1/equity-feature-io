"""Source-authored supplied reference conversion controls; not executed locally."""
from dataclasses import FrozenInstanceError, replace
import unittest

from equity_feature_contracts import (
    CanonicalBatch, Column, ContractError, Coverage, DataKind, ErrorCode, InputScope,
)
from equity_feature_duckdb.ef1 import (
    ReferenceActionInputs, ReferenceClassificationInputs, ReferenceCertificate,
    make_reference_proof, make_reference_rows, synthetic_reference_action_context,
    synthetic_reference_action_fixture, synthetic_reference_classification_context,
    synthetic_reference_classification_fixture,
)


def change(batch, name, cells):
    return replace(batch, columns=tuple(Column(c.name, cells) if c.name == name else c for c in batch.columns))


class ReferenceInputTests(unittest.TestCase):
    def test_original_r01_half_open_boundaries_proof_ids_and_known_at(self):
        p = synthetic_reference_classification_fixture()
        self.assertEqual(p.classification_facts.column("effective_start_ns").values, (0, 20))
        self.assertEqual(p.classification_facts.column("effective_end_ns").values, (20, 40))
        self.assertEqual(p.classification_history.column("reference_id").values, ("h1:s:VQ:Y2w:aA",))
        self.assertEqual(p.classification_projection.column("reference_id").values, ("r1:Y2w:cA",))
        self.assertEqual(p.classification_facts.column("known_at_ns").values, (5, 5))
        self.assertEqual(p.provenance, ("synthetic",) * 3)

    def test_all_three_classification_kinds_have_explicit_bound_history(self):
        for kind, code in (("sector_membership", "s"), ("industry_membership", "i"), ("universe_membership", "u")):
            p = synthetic_reference_classification_fixture(fact_kind=kind)
            self.assertEqual(p.classification_facts.column("fact_kind").values, (kind, kind))
            self.assertEqual(p.classification_history.column("reference_id").values, (f"h1:{code}:VQ:Y2w:aA",))
            self.assertEqual(synthetic_reference_classification_context(fact_kind=kind)["selection"]["fact_kind"], kind)

    def test_complete_empty_is_present_and_missing_is_none(self):
        p = synthetic_reference_classification_fixture("R02")
        self.assertEqual(p.classification_facts.row_count, 0)
        self.assertEqual(p.classification_facts.metadata.coverage, Coverage(0, 0, True))
        missing = replace(p, classification_facts=None, provenance=("unavailable", "synthetic", "synthetic"))
        self.assertEqual(len(missing.slots), 3)
        self.assertIsNone(missing.slots[0])
        self.assertEqual(missing.batches, p.batches[1:])

    def test_exact_six_action_slots_original_factors_and_distinct_sources(self):
        p = synthetic_reference_action_fixture()
        self.assertEqual(p.roles, ("market", "action_facts", "action_history", "action_projection",
                                   "source_representation", "source_quantity_basis"))
        self.assertEqual(p.action_facts.column("factor_num").values, (1,))
        self.assertEqual(p.action_facts.column("factor_den").values, (2,))
        self.assertEqual(p.market.column("price").values, (100,))
        self.assertEqual(p.market.column("size").values, (10,))
        self.assertEqual(p.source_quantity_basis.column("text").values, ("raw_shares",))
        self.assertEqual(len({b.metadata.source.input_id for b in p.batches}), 6)

    def test_each_missing_role_preserves_position_and_present_objects(self):
        for p in (synthetic_reference_classification_fixture(), synthetic_reference_action_fixture()):
            for i, role in enumerate(p.roles):
                modes = tuple("unavailable" if j == i else "synthetic" for j in range(len(p.slots)))
                other = replace(p, **{role: None, "provenance": modes})
                self.assertIsNone(other.slots[i])
                self.assertTrue(all(a is b for a, b in zip(other.batches, (x for j, x in enumerate(p.slots) if j != i))))

    def test_all_missing_and_immutable_owned_tuples(self):
        for p in (ReferenceClassificationInputs(), ReferenceActionInputs()):
            self.assertEqual(p.batches, ())
            self.assertTrue(all(b is None for b in p.slots))
            with self.assertRaises(FrozenInstanceError):
                p.provenance = ()

    def test_observed_provenance_is_explicit_and_not_relabelled_synthetic(self):
        p = synthetic_reference_action_fixture()
        observed = replace(p, provenance=("duckdb_backed_observed",) * 6)
        self.assertEqual(observed.batches, p.batches)
        self.assertEqual(observed.provenance, ("duckdb_backed_observed",) * 6)
        mixed = replace(p, provenance=("duckdb_backed_observed",) + ("synthetic",) * 5)
        self.assertEqual(mixed.provenance[0], "duckdb_backed_observed")

    def test_provenance_missingness_kind_and_tuple_shape_refusals(self):
        p = synthetic_reference_classification_fixture()
        for modes in (("synthetic",), ["synthetic"] * 3, ("unavailable", "synthetic", "synthetic"), ("guessed",) * 3):
            with self.assertRaises(ContractError):
                replace(p, provenance=modes)
        with self.assertRaises(ContractError):
            replace(p, classification_facts=synthetic_reference_action_fixture().market)

    def test_target_source_snapshot_namespace_entity_and_self_proof_refuse(self):
        p = synthetic_reference_classification_fixture()
        proof = p.classification_history
        mutations = (
            change(proof, "reference_id", ("h1:s:VQ:b3RoZXI:aA",)),
            change(proof, "reference_id", ("h1:s:VQ:Y2g:aA",)),
            replace(proof, metadata=replace(proof.metadata, source=replace(proof.metadata.source, source_id="other"))),
            replace(proof, metadata=replace(proof.metadata, source=replace(proof.metadata.source, snapshot_id="R2"))),
            replace(proof, metadata=replace(proof.metadata, namespace="other")),
            change(proof, "instrument_id", ("Y",)),
        )
        for changed in mutations:
            with self.assertRaises(ContractError):
                replace(p, classification_history=changed)

    def test_missing_target_does_not_permit_incoherent_proofs(self):
        p = synthetic_reference_classification_fixture()
        with self.assertRaises(ContractError):
            ReferenceClassificationInputs(None, p.classification_history,
                change(p.classification_projection, "reference_id", ("r1:b3RoZXI:cA",)),
                ("unavailable", "synthetic", "synthetic"))

    def test_empty_proof_wrong_source_refuses_for_each_actual_target_group(self):
        for p in (synthetic_reference_classification_fixture(), synthetic_reference_action_fixture()):
            for role in p.roles:
                if role in ("market", "classification_facts", "action_facts"):
                    continue
                proof = getattr(p, role)
                empty = replace(proof, columns=tuple(Column(c.name, ()) for c in proof.columns),
                    metadata=replace(proof.metadata, coverage=Coverage(0, 0, True),
                        source=replace(proof.metadata.source, source_id="other-publisher")))
                with self.subTest(role=role), self.assertRaises(ContractError) as caught:
                    replace(p, **{role: empty})
                self.assertEqual(caught.exception.code, ErrorCode.INCONSISTENT_IDENTITY)

    def test_empty_proof_wrong_revision_refuses_for_each_actual_target_group(self):
        for p in (synthetic_reference_classification_fixture(), synthetic_reference_action_fixture()):
            for role in p.roles:
                if role in ("market", "classification_facts", "action_facts"):
                    continue
                proof = getattr(p, role)
                empty = replace(proof, columns=tuple(Column(c.name, ()) for c in proof.columns),
                    metadata=replace(proof.metadata, coverage=Coverage(0, 0, True),
                        source=replace(proof.metadata.source, snapshot_id="R2")))
                with self.subTest(role=role), self.assertRaises(ContractError) as caught:
                    replace(p, **{role: empty})
                self.assertEqual(caught.exception.code, ErrorCode.INCONSISTENT_IDENTITY)

    def test_missing_targets_empty_proofs_still_require_coherent_source_metadata(self):
        for p, absent, pair in (
            (synthetic_reference_classification_fixture(), ("classification_facts",),
                ("classification_history", "classification_projection")),
            (synthetic_reference_action_fixture(), ("market", "action_facts"),
                ("action_history", "action_projection")),
            (synthetic_reference_action_fixture(), ("market", "action_facts"),
                ("source_representation", "source_quantity_basis"))):
            modes = tuple("unavailable" if role in absent else "synthetic" for role in p.roles)
            changes = {role: None for role in absent}
            for role in pair:
                proof = getattr(p, role)
                changes[role] = replace(proof, columns=tuple(Column(c.name, ()) for c in proof.columns),
                    metadata=replace(proof.metadata, coverage=Coverage(0, 0, True)))
            coherent = replace(p, **changes, provenance=modes)
            self.assertTrue(all(getattr(coherent, role) is None for role in absent))
            for field, value in (("source_id", "other-publisher"), ("snapshot_id", "R2")):
                proof = getattr(coherent, pair[1])
                conflict = replace(proof, metadata=replace(proof.metadata,
                    source=replace(proof.metadata.source, **{field: value})))
                with self.subTest(pair=pair, field=field), self.assertRaises(ContractError) as caught:
                    replace(coherent, **{pair[1]: conflict})
                self.assertEqual(caught.exception.code, ErrorCode.INCONSISTENT_IDENTITY)

    def test_malformed_base64_closed_vocabulary_and_finite_proof_refuse(self):
        p = synthetic_reference_classification_fixture()
        for name, value in (("reference_id", "h1:s:VQ=:Y2w:aA"), ("text", "assumed"),
                            ("effective_end_ns", None)):
            with self.assertRaises(ContractError):
                replace(p, classification_history=change(p.classification_history, name, (value,)))

    def test_original_unknown_late_and_incomplete_are_preserved_not_repaired(self):
        p = synthetic_reference_classification_fixture()
        for known in (None, 99):
            facts = change(p.classification_facts, "known_at_ns", (known, known))
            facts = replace(facts, metadata=replace(facts.metadata, coverage=Coverage(None, 2, False)))
            packet = replace(p, classification_facts=facts)
            self.assertIs(packet.classification_facts, facts)
            self.assertEqual(packet.classification_facts.column("known_at_ns").values, (known, known))
            self.assertEqual(packet.classification_facts.metadata.coverage.expected, None)

    def test_blank_null_and_spaced_body_text_is_preserved(self):
        p = synthetic_reference_classification_fixture()
        for text in (None, "", "  ", " B "):
            packet = replace(p, classification_facts=change(p.classification_facts, "text", ("A", text)))
            self.assertEqual(packet.classification_facts.column("text").values[-1], text)
        for text in ("a\x00", "a\x7f", "a\ud800", "a" * 129):
            with self.assertRaises(ContractError):
                replace(p, classification_facts=change(p.classification_facts, "text", ("A", text)))

    def test_no_field_dropping_or_population_repair_in_converter(self):
        p = synthetic_reference_classification_fixture()
        row = {"reference_id": "x", "fact_kind": "industry_membership", "effective_start_ns": 0,
               "effective_end_ns": None, "text": "  original  ", "known_at_ns": None}
        actual = make_reference_rows((row,), role="classification_facts",
            metadata=replace(p.classification_history.metadata, coverage=Coverage(None, 1, False)),
            instrument_id="X", session_id="S")
        self.assertEqual(actual.column("text").values, ("  original  ",))
        self.assertEqual(actual.column("known_at_ns").values, (None,))
        self.assertIsNone(actual.metadata.coverage.expected)
        with self.assertRaises(ContractError):
            make_reference_rows(({**row, "unknown_private_field": 1},), role="classification_facts",
                metadata=actual.metadata, instrument_id="X", session_id="S")

    def test_null_unused_columns_preserved_but_populated_payload_refuses(self):
        p = synthetic_reference_classification_fixture()
        for role in p.roles:
            batch = getattr(p, role)
            nulls = replace(batch, columns=batch.columns + (Column("factor_num", (None,) * batch.row_count),))
            self.assertIs(getattr(replace(p, **{role: nulls}), role), nulls)
            with self.assertRaises(ContractError):
                replace(p, **{role: replace(batch, columns=batch.columns + (Column("factor_num", (1,) * batch.row_count),))})
        a = synthetic_reference_action_fixture()
        nulltext = replace(a.action_facts, columns=a.action_facts.columns + (Column("text", (None,)),))
        self.assertIs(replace(a, action_facts=nulltext).action_facts, nulltext)
        with self.assertRaises(ContractError):
            replace(a, action_facts=replace(a.action_facts, columns=a.action_facts.columns + (Column("text", ("payload",)),)))

    def test_complete_empty_action_factory_is_actual_zero_population(self):
        p = synthetic_reference_action_fixture()
        empty = make_reference_rows((), role="action_facts",
            metadata=replace(p.action_facts.metadata, coverage=Coverage(0, 0, True)),
            instrument_id="X", session_id="S")
        packet = replace(p, action_facts=empty)
        self.assertIs(packet.slots[1], empty)
        self.assertEqual(empty.metadata.coverage, Coverage(0, 0, True))
        self.assertEqual(empty.row_count, 0)
        self.assertIn(empty, packet.batches)

    def test_conversion_does_not_sort_deduplicate_or_truncate(self):
        p = synthetic_reference_classification_fixture()
        facts = p.classification_facts
        for columns in (tuple(Column(c.name, tuple(reversed(c.values))) for c in facts.columns),
                        tuple(Column(c.name, (c.values[0], c.values[0])) for c in facts.columns)):
            with self.assertRaises(ContractError):
                replace(p, classification_facts=replace(facts, columns=columns))
        with self.assertRaises(ContractError):
            make_reference_proof((ReferenceCertificate("x" * 128, 0, 40, "complete", 5),),
                role="classification_projection", target_input_id="cl", metadata=p.classification_projection.metadata,
                instrument_id="X", session_id="S")

    def test_market_kind_union_retains_original_trade_bar_daily(self):
        p = synthetic_reference_action_fixture()
        for kind in (DataKind.BAR, DataKind.DAILY):
            batch = CanonicalBatch(kind, tuple(Column(name, (value,)) for name, value in (
                ("instrument_id", "X"), ("session_id", "S"), ("start_ns", 10), ("end_ns", 20),
                ("open", 100), ("high", 100), ("low", 100), ("close", 100), ("volume", 10),
                ("actual_notional", 1000), ("known_at_ns", 20))), p.market.metadata)
            other = replace(p, market=batch)
            self.assertIs(other.market, batch)
            self.assertEqual(other.market.kind, kind)

    def test_contexts_are_fresh_selection_only_not_acquired_facts(self):
        a, b = synthetic_reference_action_context(), synthetic_reference_action_context()
        a["selection"]["policy"]["quantity_basis"] = "mutated"
        self.assertEqual(b["selection"]["policy"]["quantity_basis"], "split_shares")
        self.assertIsNone(b["calendar"])
        for factory in (synthetic_reference_action_fixture, synthetic_reference_classification_fixture):
            with self.assertRaises(ContractError):
                factory("unknown")


if __name__ == "__main__":
    unittest.main()
