"""Actual canonical conversion stages; endpoint pure computation is separate."""
from dataclasses import replace
import unittest
from equity_feature_contracts import Column, ContractError, Coverage, DataKind, ErrorCode
from equity_feature_duckdb.ef1 import GapEndpointInputs, make_gap_endpoint_batch, make_gap_population_proof
from gap_endpoint_support import packets, packet_inputs, original_batch


class GapEndpointInputTests(unittest.TestCase):
    def test_all_114_conversion_stages_and_71_full_result_input_shapes(self):
        accepted = refused = available = 0
        early = {"E18_duplicate_order_key", "E25_present_null_latest_price", "E30_unknown_expected",
                 "P16_reversed_actual_order", "Q06_supplied_null_size_invalid",
                 "Q07_supplied_zero_size_invalid", "Q15_empty_supplied_invalid_prior_price",
                 "Q18_duplicate_identical_reference_identity", "Q34_duplicate_actual_input_id"}
        for packet in packets():
            with self.subTest(case=packet["id"]):
                if packet["id"] in early:
                    with self.assertRaises(ContractError) as caught:
                        packet_inputs(packet)
                    self.assertEqual(caught.exception.code.value, packet["expected_error"]["code"])
                    refused += 1
                    continue
                actual = packet_inputs(packet)
                accepted += 1
                available += packet["expected_result"] is not None
                self.assertEqual(actual.roles, ("calendar_provenance", "path", "prior_close", "population_proof"))
                self.assertEqual(len(actual.slots), 4)
                for slot, source in zip(actual.slots, packet["role_slots"]):
                    self.assertEqual(slot, original_batch(source["batch"], convert=False))
                self.assertEqual(actual.batches, tuple(b for b in actual.slots if b is not None))
        self.assertEqual((accepted, refused, available), (105, 9, 71))

    def test_literal_synthetic_helpers_equal_frozen_inputs_and_config(self):
        import json
        from equity_feature_duckdb.ef1 import synthetic_gap_endpoint_config, synthetic_gap_endpoint_fixture
        selected = {p["id"]: p for p in packets()}
        for case in ("E01_up_reversal", "E26_bar_close_at_cutoff"):
            self.assertEqual(synthetic_gap_endpoint_fixture(case), packet_inputs(selected[case]))
            self.assertEqual(json.loads(synthetic_gap_endpoint_config(case).to_json()), selected[case]["config"])
        for factory in (synthetic_gap_endpoint_config, synthetic_gap_endpoint_fixture):
            with self.assertRaises(ContractError): factory("unknown")

    def test_missing_empty_and_reference_role_indices_remain_distinct(self):
        original = packet_inputs(packets()[0])
        for i, role in enumerate(original.roles):
            missing = replace(original, **{role: None, "provenance": tuple(
                "unavailable" if j == i else "synthetic" for j in range(4))})
            self.assertIsNone(missing.slots[i])
            self.assertEqual(len(missing.batches), 3)
            batch = original.slots[i]
            empty = replace(batch, columns=tuple(Column(c.name, ()) for c in batch.columns),
                            metadata=replace(batch.metadata, coverage=Coverage(0, 0, True)))
            present = replace(original, **{role: empty})
            self.assertIs(present.slots[i], empty)
            self.assertEqual(len(present.batches), 4)
        self.assertEqual(GapEndpointInputs().slots, (None,) * 4)
        self.assertEqual(GapEndpointInputs().batches, ())

    def test_supplied_population_row_preserves_original_text_time_and_metadata(self):
        original = packet_inputs(packets()[0]).population_proof
        row = {c.name: c.values[0] for c in original.columns}
        for known in (None, -100, 1000):
            supplied = {**row, "known_at_ns": known, "text": "not rewritten or repaired"}
            actual = make_gap_population_proof(supplied, metadata=original.metadata)
            self.assertIs(actual.metadata, original.metadata)
            self.assertEqual(tuple(c.name for c in actual.columns), tuple(row))
            for column in actual.columns:
                self.assertEqual(column.values, (supplied[column.name],))
        for name in row:
            with self.assertRaises(ContractError):
                make_gap_population_proof({k: v for k, v in row.items() if k != name}, metadata=original.metadata)

    def test_modes_shape_and_delivery_agreement(self):
        original = packet_inputs(packets()[0])
        for modes in (("synthetic",), ["synthetic"] * 4, ("unknown",) * 4, ("unavailable",) * 4):
            with self.assertRaises(ContractError): replace(original, provenance=modes)
        observed = replace(original, provenance=("duckdb_backed_observed",) * 4)
        self.assertEqual(observed.slots, original.slots)  # declaration is not capability admission
        self.assertTrue(all(a is b for a, b in zip(observed.slots, original.slots)))

    def test_rectangle_requires_original_cells_not_truncating_zip(self):
        original = packet_inputs(packets()[0]).path
        for names, rows in ((["instrument_id"], ()), (("instrument_id",), [["X"]]),
                            (("instrument_id",), (("X", "extra"),))):
            with self.assertRaises(ContractError):
                make_gap_endpoint_batch(DataKind.TRADE, names, rows, metadata=original.metadata)

    def test_negative_semantic_proofs_survive_conversion_for_actual_pure_admission(self):
        cases = {p["id"]: p for p in packets()}
        for case in ("Q23_duplicate_json_key", "Q24_malformed_json", "Q25_noncanonical_json",
                     "Q26_unknown_json_key", "Q27_bool_as_int", "Q28_oversized_proof_text"):
            packet = packet_inputs(cases[case])
            self.assertEqual(packet.population_proof.column("text").values,
                             tuple(cases[case]["role_slots"][3]["batch"]["columns"][6]["values"]))


if __name__ == "__main__":
    unittest.main()
