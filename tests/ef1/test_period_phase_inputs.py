"""Exact role conversion, no source discovery or feature mathematics."""
from dataclasses import FrozenInstanceError, replace
import unittest
from equity_feature_contracts import Column, ContractError, Coverage, DataKind
from equity_feature_duckdb.ef1 import (
    PeriodInputs, ExtendedInputs, make_period_batch, synthetic_period_fixture,
    synthetic_extended_fixture, synthetic_period_context, synthetic_extended_context,
)


class PeriodPhaseInputTests(unittest.TestCase):
    def test_exact_roles_kinds_and_original_objects(self):
        p, e = synthetic_period_fixture(), synthetic_extended_fixture()
        self.assertEqual(p.roles, ('calendar_provenance', 'daily_history', 'bars'))
        self.assertEqual(e.roles, ('calendar_provenance', 'bars', 'prior_close'))
        for inputs in (p, e):
            self.assertEqual(inputs.provenance, ('synthetic',) * 3)
            self.assertTrue(all(a is b for a, b in zip(inputs.slots, inputs.batches)))

    def test_each_missing_slot_preserves_position_and_other_objects(self):
        for inputs in (synthetic_period_fixture(), synthetic_extended_fixture()):
            for i, role in enumerate(inputs.roles):
                modes = tuple('unavailable' if n == i else 'synthetic' for n in range(3))
                missing = replace(inputs, **{role: None, 'provenance': modes})
                self.assertIsNone(missing.slots[i])
                self.assertEqual(missing.batches, tuple(b for n, b in enumerate(inputs.slots) if n != i))

    def test_all_missing_and_immutable(self):
        for inputs in (PeriodInputs(), ExtendedInputs()):
            self.assertEqual(inputs.slots, (None,) * 3)
            self.assertEqual(inputs.batches, ())
            with self.assertRaises(FrozenInstanceError):
                inputs.bars = None

    def test_observed_and_mixed_provenance_never_relabelled(self):
        for inputs in (synthetic_period_fixture(), synthetic_extended_fixture()):
            for origins in (('duckdb_backed_observed',) * 3, ('synthetic', 'duckdb_backed_observed', 'synthetic')):
                other = replace(inputs, provenance=origins)
                self.assertEqual(other.provenance, origins)
                self.assertEqual(other.batches, inputs.batches)

    def test_missingness_and_provenance_shape_refused(self):
        p = synthetic_period_fixture()
        for value in (('synthetic',), ['synthetic'] * 3, ('guessed',) * 3, ('unavailable',) * 3):
            with self.assertRaises(ContractError):
                replace(p, provenance=value)

    def test_wrong_role_kinds_and_unsupported_trade_phase_refused(self):
        p, e = synthetic_period_fixture(), synthetic_extended_fixture()
        for inputs, role, wrong in ((p, 'bars', p.daily_history), (p, 'daily_history', p.bars),
                                    (e, 'prior_close', e.bars), (e, 'calendar_provenance', e.bars)):
            with self.assertRaises(ContractError):
                replace(inputs, **{role: wrong})
        with self.assertRaises(ContractError):
            make_period_batch(DataKind.TRADE, (), (), metadata=e.bars.metadata)

    def test_prior_session_and_phase_timestamps_remain_original(self):
        e = synthetic_extended_fixture()
        self.assertEqual(e.prior_close.column('session_id').values, ('P',))
        self.assertEqual(e.prior_close.column('start_ns').values, (-10,))
        self.assertEqual(e.bars.column('start_ns').values, (0, 5))
        self.assertEqual(e.bars.column('end_ns').values, (5, 10))
        self.assertEqual(e.bars.column('known_at_ns').values, (5, 10))

    def test_unknown_and_future_original_availability_preserved(self):
        e = synthetic_extended_fixture()
        for known in ((None, 999), (999, 999)):
            bars = replace(e.bars, columns=tuple(Column(c.name, known) if c.name == 'known_at_ns' else c for c in e.bars.columns))
            self.assertIs(replace(e, bars=bars).bars, bars)

    def test_empty_delivery_stays_present_with_original_columns_and_coverage(self):
        p = synthetic_period_fixture()
        empty = replace(p.bars, columns=tuple(Column(c.name, ()) for c in p.bars.columns),
                        metadata=replace(p.bars.metadata, coverage=Coverage(1, 0, False),
                                         interval_coverage=()))
        kept = replace(p, bars=empty)
        self.assertIs(kept.slots[2], empty)
        self.assertEqual(kept.bars.metadata.coverage, Coverage(1, 0, False))
        self.assertEqual(tuple(c.name for c in kept.bars.columns), tuple(c.name for c in p.bars.columns))

    def test_unused_prior_columns_are_structurally_validated(self):
        e = synthetic_extended_fixture()
        broken = replace(e.prior_close, columns=tuple(Column(c.name, (-1,)) if c.name == 'volume' else c for c in e.prior_close.columns))
        with self.assertRaises(ContractError):
            replace(e, prior_close=broken)

    def test_duplicate_binding_and_cross_namespace_refused(self):
        p = synthetic_period_fixture()
        for meta in (replace(p.bars.metadata, namespace='other'),
                     replace(p.bars.metadata, source=replace(p.bars.metadata.source, input_id=p.daily_history.metadata.source.input_id))):
            with self.assertRaises(ContractError):
                replace(p, bars=replace(p.bars, metadata=meta))

    def test_rectangular_conversion_preserves_all_fields_and_empty_schema(self):
        p = synthetic_period_fixture()
        names = tuple(c.name for c in p.bars.columns)
        rows = tuple(zip(*(c.values for c in p.bars.columns)))
        self.assertEqual(make_period_batch(DataKind.BAR, names, rows, metadata=p.bars.metadata), p.bars)
        for order, values in ((names, (rows[0][:-1],)), (list(names), rows), (names, [rows[0]])):
            with self.assertRaises(ContractError):
                make_period_batch(DataKind.BAR, order, values, metadata=p.bars.metadata)

    def test_context_is_detached_each_call_and_synthetic(self):
        for constructor in (synthetic_period_context, synthetic_extended_context):
            first, second = constructor(), constructor()
            first['calendar']['sessions'][0][0] = 'changed'
            self.assertNotEqual(first, second)
            self.assertEqual(second['calendar']['sessions'][0][0], 'P')


if __name__ == '__main__':
    unittest.main()
