"""Original EF1 I/O conformance authoring; execution requires resource admission."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from equity_feature_contracts import ContractError, ErrorCode
from equity_feature_duckdb.ef1 import (
    AnchorInputs, anchor_definition_bytes, make_anchor_provenance,
    separate_output_path, synthetic_anchor_fixture,
)

DEFINITION = {"anchor_id": "A", "reset_id": "R", "start_ns": 10,
              "selection_policy_id": "supplied-v1", "revision": "R1"}
LITERAL_DEFINITION = b'{"anchor_id":"A","reset_id":"R","revision":"R1","selection_policy_id":"supplied-v1","start_ns":10}'


class AnchorInputTests(unittest.TestCase):
    def test_a01_exact_original_trade_and_bar_columns(self):
        trades = synthetic_anchor_fixture()
        self.assertEqual(trades.roles, ("trades", "anchor_provenance"))
        self.assertEqual(trades.market.column("price").values, (1000, 1300))
        self.assertEqual(trades.market.column("size").values, (2, 1))
        self.assertEqual(trades.market.column("known_at_ns").values, (10, 15))
        self.assertEqual(trades.market.metadata.price_unit.scale, 2)
        self.assertEqual(trades.market.metadata.source.snapshot_id, "R1")
        self.assertEqual(trades.market.metadata.source.source_id, "F")
        self.assertEqual(trades.anchor_provenance.metadata.source.mapping_version, "ef1-reference-map1")
        bars = synthetic_anchor_fixture(mode="bars_actual_notional")
        self.assertEqual(bars.roles, ("bars", "anchor_provenance"))
        self.assertEqual(bars.market.column("actual_notional").values, (3300,))
        self.assertEqual(bars.market.column("volume").values, (3,))
        self.assertEqual(bars.market.column("start_ns").values, (10,))
        self.assertEqual(bars.market.column("end_ns").values, (20,))
        self.assertEqual(bars.market_provenance, "synthetic")

    def test_hash_is_exact_canonical_definition_and_original_knowledge(self):
        self.assertEqual(anchor_definition_bytes(DEFINITION), LITERAL_DEFINITION)
        for known in (None, 10, 21):
            proof = make_anchor_provenance(DEFINITION, namespace="SYN", instrument_id="X",
                                           session_id="S", source_id="F", input_id="P", known_at_ns=known)
            self.assertEqual(proof.column("reference_id").values,
                             ("a1:" + hashlib.sha256(LITERAL_DEFINITION).hexdigest(),))
            self.assertEqual(proof.column("fact_kind").values, ("ef1.anchor.provenance",))
            self.assertEqual(proof.column("text").values, ("supplied_anchor",))
            self.assertEqual(proof.column("known_at_ns").values, (known,))
            self.assertEqual(proof.column("effective_start_ns").values, (10,))
            self.assertEqual(proof.metadata.source.snapshot_id, "R1")
            self.assertIsNone(proof.column("factor_num"))

    def test_a02_missing_empty_and_null_notional_distinct(self):
        for mode in ("trades", "bars_actual_notional"):
            empty = synthetic_anchor_fixture("A02", mode=mode)
            self.assertEqual(empty.market.row_count, 0)
            self.assertTrue(empty.market.metadata.coverage.complete)
            self.assertEqual((empty.market.metadata.scope.start_ns, empty.market.metadata.scope.end_ns), (10, 20))
            missing = AnchorInputs(mode, None, empty.anchor_provenance, "unavailable", "synthetic")
            self.assertEqual(missing.batches, (empty.anchor_provenance,))
        null = synthetic_anchor_fixture("A01-missing-notional", mode="bars_actual_notional")
        self.assertEqual(null.market.column("actual_notional").values, (None,))
        self.assertEqual(null.market.column("volume").values, (3,))

    def test_a03_does_not_manufacture_positive_scope(self):
        with self.assertRaises(ContractError) as caught:
            synthetic_anchor_fixture("A03")
        self.assertEqual(caught.exception.code, ErrorCode.BOUNDS)

    def test_b01_shape_precision_and_explicit_provenance(self):
        for definition in (dict(DEFINITION, extra="bad"), dict(DEFINITION, start_ns=True),
                           dict(DEFINITION, start_ns=2**63)):
            with self.assertRaises(ContractError):
                anchor_definition_bytes(definition)
        packet = synthetic_anchor_fixture()
        with self.assertRaises(ContractError):
            AnchorInputs("trades", packet.market, packet.anchor_provenance, "unavailable", "synthetic")
        # Real supplied canonical observations remain labelled observed, even in a
        # mixed development packet. No fallback or invented availability occurs.
        mixed = AnchorInputs("trades", packet.market, packet.anchor_provenance,
                             "duckdb_backed_observed", "synthetic")
        self.assertEqual(mixed.market_provenance, "duckdb_backed_observed")
        foreign = replace(packet.anchor_provenance, metadata=replace(packet.anchor_provenance.metadata, namespace="OTHER"))
        with self.assertRaises(ContractError):
            AnchorInputs("trades", packet.market, foreign, "synthetic", "synthetic")

    def test_source_output_separation_before_sink_creation(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source.duckdb"
            with self.assertRaises(ContractError):
                separate_output_path(source, (source,))
            with self.assertRaises(ContractError):
                separate_output_path(Path("relative.duckdb"), (source,))
            output = separate_output_path(Path(temp) / "new-results.duckdb", (source,))
            self.assertFalse(output.exists())
            self.assertFalse(source.exists())

    def test_existing_hardlink_alias_refused_without_modifying_source(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source-placeholder"
            alias = Path(temp) / "output-alias"
            source.write_bytes(b"synthetic non-database placeholder")
            try:
                os.link(source, alias)
            except OSError:
                self.skipTest("Owned temporary filesystem does not support hardlinks")
            before = source.read_bytes()
            with self.assertRaises(ContractError) as caught:
                separate_output_path(alias, (source,))
            self.assertEqual(caught.exception.code, ErrorCode.INCONSISTENT_IDENTITY)
            self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
