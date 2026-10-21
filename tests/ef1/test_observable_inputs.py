"""Lossless observable source conversion; no event or proof inference."""
from dataclasses import FrozenInstanceError, replace
import unittest
from equity_feature_contracts import Column, ContractError, Coverage, DataKind
from equity_feature_duckdb.ef1 import (
    OpeningTradeInputs, StatusHistoryInputs, make_observable_batch,
    synthetic_opening_trade_fixture, synthetic_opening_trade_context,
    synthetic_status_history_fixture, synthetic_status_history_missing_capability_fixture,
)

class ObservableInputTests(unittest.TestCase):
    def test_fixed_roles_and_original_object_identity(self):
        for inputs, roles in ((synthetic_opening_trade_fixture(), ('calendar_provenance','market_prefix','source_capability','trades')),
                (synthetic_status_history_fixture(), ('calendar_provenance','history_events','history_prefix','history_seed','source_capability'))):
            self.assertEqual(inputs.roles, roles)
            self.assertTrue(all(a is b for a,b in zip(inputs.batches, (b for b in inputs.slots if b is not None))))

    def test_each_missing_role_keeps_its_exact_slot(self):
        for inputs in (synthetic_opening_trade_fixture(), synthetic_status_history_fixture()):
            for i, role in enumerate(inputs.roles):
                origins=tuple('unavailable' if n==i or b is None else 'synthetic' for n,b in enumerate(inputs.slots))
                changed=replace(inputs, **{role:None, 'provenance':origins})
                self.assertIsNone(changed.slots[i])
                self.assertEqual(len(changed.slots),len(inputs.roles))
                self.assertEqual(changed.batches,tuple(b for n,b in enumerate(inputs.slots) if b is not None and n!=i))

    def test_all_none_and_frozen(self):
        for inputs in (OpeningTradeInputs(), StatusHistoryInputs()):
            self.assertEqual(inputs.slots,(None,)*len(inputs.roles))
            self.assertEqual(inputs.batches,())
            with self.assertRaises(FrozenInstanceError):
                inputs.calendar_provenance=None

    def test_provenance_shape_and_missingness_are_real(self):
        inputs=synthetic_opening_trade_fixture()
        for origins in (('synthetic',), ['synthetic']*4, ('guessed',)*4, ('unavailable',)*4):
            with self.assertRaises(ContractError): replace(inputs,provenance=origins)
        observed=replace(inputs,provenance=('duckdb_backed_observed',)*4)
        self.assertEqual(observed.batches,inputs.batches)
        self.assertEqual(observed.provenance,('duckdb_backed_observed',)*4)

    def test_wrong_role_kind_is_refused(self):
        inputs=synthetic_opening_trade_fixture()
        for role,batch in (('trades',inputs.market_prefix),('source_capability',inputs.trades)):
            with self.assertRaises(ContractError): replace(inputs,**{role:batch})

    def test_empty_batch_retains_columns_metadata_and_slot(self):
        inputs=synthetic_opening_trade_fixture(); original=inputs.source_capability
        empty=replace(original, columns=tuple(Column(c.name,()) for c in original.columns),
            metadata=replace(original.metadata,coverage=Coverage(0,0,True)))
        other=replace(inputs,source_capability=empty)
        self.assertIs(other.slots[2],empty)
        self.assertIn(empty,other.batches)
        self.assertEqual(tuple(c.name for c in empty.columns),tuple(c.name for c in original.columns))

    def test_unknown_and_future_original_clocks_unchanged(self):
        inputs=synthetic_opening_trade_fixture()
        for known in (None,999):
            original=inputs.trades
            batch=replace(original,columns=tuple(Column(c.name,(known,)) if c.name=='known_at_ns' else c for c in original.columns))
            self.assertIs(replace(inputs,trades=batch).trades,batch)

    def test_rectangular_conversion_no_sort_filter_or_column_loss(self):
        for inputs in (synthetic_opening_trade_fixture(),synthetic_status_history_fixture()):
            for batch in inputs.batches:
                names=tuple(c.name for c in batch.columns)
                rows=tuple(zip(*(c.values for c in batch.columns)))
                self.assertEqual(make_observable_batch(batch.kind,names,rows,metadata=batch.metadata),batch)
                for bad_names,bad_rows in ((list(names),rows),(names,list(rows)),(names,(rows[0][:-1],))):
                    with self.assertRaises(ContractError): make_observable_batch(batch.kind,bad_names,bad_rows,metadata=batch.metadata)
        with self.assertRaises(ContractError):
            make_observable_batch(DataKind.BAR,(),(),metadata=synthetic_opening_trade_fixture().trades.metadata)

    def test_original_namespace_and_duplicate_source_ids_refused(self):
        inputs=synthetic_opening_trade_fixture(); batch=inputs.market_prefix
        for meta in (replace(batch.metadata,namespace='other'),replace(batch.metadata,source=inputs.source_capability.metadata.source)):
            with self.assertRaises(ContractError): replace(inputs,market_prefix=replace(batch,metadata=meta))

    def test_literal_missing_identity_capability_is_not_fabricated_event(self):
        inputs=synthetic_status_history_missing_capability_fixture()
        self.assertIsNone(inputs.history_events)
        self.assertIsNone(inputs.history_seed)
        self.assertEqual(inputs.source_capability.column('text').values,('missing_identity',))

    def test_contexts_are_detached(self):
        first=synthetic_opening_trade_context(); second=synthetic_opening_trade_context()
        first['selection']['publisher']='changed'
        self.assertEqual(second['selection']['publisher'],'P')

if __name__=='__main__': unittest.main()
