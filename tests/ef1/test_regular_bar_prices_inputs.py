"""Actual adapter/constructor stages, separate from pure producer execution."""
from dataclasses import replace
import json
import unittest
from equity_feature_contracts import Column, ContractError, Coverage, DataKind, validate_batch
from equity_feature_duckdb.regular_bar_prices import (
    RegularBarPriceInputs, make_regular_bar_price_batch, make_regular_bar_population_proof,
    synthetic_regular_bar_price_config, synthetic_regular_bar_price_fixture,
)
from regular_bar_prices_support import packets, packet_inputs, original_batch


class RegularBarPriceInputTests(unittest.TestCase):
    def test_all_100_literal_conversions_with_actual_early_stages(self):
        accepted = refused = full = 0
        stage_counts = {}
        for packet in packets():
            with self.subTest(case=packet["id"]):
                expected = packet.get("expected_error")
                stage = None if expected is None else expected["expected_earliest_stage"]
                if stage in ("Coverage_constructor", "CanonicalBatch_constructor"):
                    with self.assertRaises(ContractError) as caught:
                        tuple(original_batch(s["batch"], convert=False) for s in packet["role_slots"])
                    self.assertEqual(caught.exception.code.value, expected["code"])
                    # Independently verify the actual public conversion pipeline
                    # reaches and preserves this original early refusal as well.
                    with self.assertRaises(ContractError) as adapter_caught:
                        packet_inputs(packet)
                    self.assertEqual(adapter_caught.exception.code.value, expected["code"])
                    stage_counts[stage] = stage_counts.get(stage, 0) + 1
                    refused += 1
                elif stage == "canonical_validate_batch":
                    slots = tuple(original_batch(s["batch"], convert=False) for s in packet["role_slots"])
                    with self.assertRaises(ContractError) as caught:
                        for batch in slots:
                            if batch is not None: validate_batch(batch, required_fields=())
                    self.assertEqual(caught.exception.code.value, expected["code"])
                    # Independently verify the actual public conversion pipeline
                    # reaches and preserves this original early refusal as well.
                    with self.assertRaises(ContractError) as adapter_caught:
                        packet_inputs(packet)
                    self.assertEqual(adapter_caught.exception.code.value, expected["code"])
                    stage_counts[stage] = stage_counts.get(stage, 0) + 1
                    refused += 1
                elif packet["id"] in ("N14_wrong_slot_count", "N16_duplicate_actual_input_id"):
                    with self.assertRaises(ContractError) as caught: packet_inputs(packet)
                    self.assertEqual(caught.exception.code.value, expected["code"])
                    refused += 1
                    stage_counts["adapter_role_shape_or_container"] = stage_counts.get("adapter_role_shape_or_container", 0) + 1
                else:
                    actual = packet_inputs(packet)
                    accepted += 1
                    full += packet.get("expected_result") is not None
                    self.assertEqual(actual.roles, ("calendar_provenance", "bars", "population_proof"))
                    self.assertEqual(actual.slots, tuple(original_batch(s["batch"], convert=False) for s in packet["role_slots"]))
                    self.assertEqual(actual.batches, tuple(b for b in actual.slots if b is not None))
        self.assertEqual((accepted, refused, full), (84, 16, 46))
        self.assertEqual(stage_counts, {"canonical_validate_batch": 10, "Coverage_constructor": 1,
            "CanonicalBatch_constructor": 3, "adapter_role_shape_or_container": 2})

    def test_literal_helpers_equal_original_inputs_and_configs(self):
        selected = {p["id"]: p for p in packets()}
        for case in ("R01_two_independent_endpoints", "R08_unknown_before_first"):
            self.assertEqual(synthetic_regular_bar_price_fixture(case), packet_inputs(selected[case]))
            self.assertEqual(json.loads(synthetic_regular_bar_price_config(case).to_json()), selected[case]["config"])
        self.assertEqual(synthetic_regular_bar_price_fixture(), packet_inputs(selected["R01_two_independent_endpoints"]))
        for factory in (synthetic_regular_bar_price_config, synthetic_regular_bar_price_fixture):
            with self.assertRaises(ContractError): factory("unknown")

    def test_absence_empty_and_fixed_reference_roles(self):
        original = synthetic_regular_bar_price_fixture()
        for i, role in enumerate(original.roles):
            missing = replace(original, **{role: None, "provenance": tuple("unavailable" if j == i else "synthetic" for j in range(3))})
            self.assertIsNone(missing.slots[i])
            self.assertEqual(len(missing.batches), 2)
            batch = original.slots[i]
            empty = replace(batch, columns=tuple(Column(c.name, ()) for c in batch.columns),
                metadata=replace(batch.metadata, coverage=Coverage(0, 0, True)))
            present = replace(original, **{role: empty})
            self.assertIs(present.slots[i], empty)
            self.assertEqual(len(present.batches), 3)
        self.assertEqual(RegularBarPriceInputs().slots, (None,) * 3)
        self.assertEqual(RegularBarPriceInputs().batches, ())

    def test_proof_preserves_supplied_text_clocks_and_metadata(self):
        original = synthetic_regular_bar_price_fixture().population_proof
        row = {c.name: c.values[0] for c in original.columns}
        for known in (None, -100, 1000):
            supplied = {**row, "known_at_ns": known, "text": "not rewritten or repaired"}
            actual = make_regular_bar_population_proof(supplied, metadata=original.metadata)
            self.assertIs(actual.metadata, original.metadata)
            self.assertEqual(tuple(c.name for c in actual.columns), tuple(row))
            for c in actual.columns: self.assertEqual(c.values, (supplied[c.name],))
        for name in row:
            with self.assertRaises(ContractError):
                make_regular_bar_population_proof({k: v for k, v in row.items() if k != name}, metadata=original.metadata)

    def test_provenance_must_match_each_actual_delivery(self):
        original = synthetic_regular_bar_price_fixture()
        for modes in (("synthetic",), ["synthetic"] * 3, ("unknown",) * 3, ("unavailable",) * 3):
            with self.assertRaises(ContractError): replace(original, provenance=modes)
        observed = replace(original, provenance=("duckdb_backed_observed",) * 3)
        self.assertTrue(all(a is b for a, b in zip(observed.slots, original.slots)))
        with self.assertRaises(ContractError): replace(original, bars=original.calendar_provenance)
        with self.assertRaises(ContractError): replace(original, calendar_provenance=original.bars)

    def test_exact_rectangle_and_metadata_are_retained(self):
        batch = synthetic_regular_bar_price_fixture().bars
        names = tuple(c.name for c in batch.columns)
        rows = tuple(zip(*(c.values for c in batch.columns)))
        actual = make_regular_bar_price_batch(DataKind.BAR, names, rows, metadata=batch.metadata)
        self.assertEqual(actual, batch)
        self.assertIs(actual.metadata, batch.metadata)
        for names, rows in ((["instrument_id"], ()), (("instrument_id",), [["X"]]),
                            (("instrument_id",), (("X", "extra"),))):
            with self.assertRaises(ContractError):
                make_regular_bar_price_batch(DataKind.BAR, names, rows, metadata=batch.metadata)
        with self.assertRaises(ContractError):
            make_regular_bar_price_batch(DataKind.TRADE, (), (), metadata=batch.metadata)

    def test_absent_numeric_and_null_volume_survive_without_filling(self):
        cases = {p["id"]: p for p in packets()}
        for case in ("R08_unknown_before_first", "R12_absent_volume_column", "R18_absent_numeric_clock",
                     "R19_absent_open_final_ready", "R20_absent_close_first_ready"):
            actual = packet_inputs(cases[case]).bars
            raw = cases[case]["role_slots"][1]["batch"]
            self.assertEqual(tuple(c.name for c in actual.columns), tuple(c["name"] for c in raw["columns"]))
            self.assertEqual(tuple(c.values for c in actual.columns), tuple(tuple(c["values"]) for c in raw["columns"]))

    def test_semantic_negative_proofs_are_not_rewritten(self):
        cases = {p["id"]: p for p in packets()}
        for case in ("N38_malformed_json", "N39_noncanonical_json", "N40_duplicate_json_key",
                     "N41_proof_text_oversize", "N42_nonascii_proof"):
            actual = packet_inputs(cases[case]).population_proof
            raw = cases[case]["role_slots"][2]["batch"]
            self.assertEqual(actual.column("text").values, tuple(raw["columns"][6]["values"]))


if __name__ == "__main__": unittest.main()
