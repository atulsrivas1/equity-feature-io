"""Lossless daily observation transport and provenance boundaries."""
from dataclasses import FrozenInstanceError, asdict, replace
import json
import unittest
from equity_feature_contracts import Column, ContractError, Coverage, DataKind
from equity_feature_duckdb.ef1 import (
    DailyObservationsInputs, make_daily_observations_batch,
    synthetic_daily_observations_config, synthetic_daily_observations_fixture,
)
from daily_observations_support import packets, packet_inputs


class DailyObservationsInputTests(unittest.TestCase):
    def test_91_literal_input_packets_preserve_every_supplied_cell_and_metadata(self):
        cases = [p for p in packets() if p.get('expected_result') is not None]
        self.assertEqual(len(cases), 91)
        for packet in cases:
            with self.subTest(case=packet['id']):
                inputs = packet_inputs(packet)
                for batch, slot in zip(inputs.slots, packet['role_slots'], strict=True):
                    self.assertEqual(None if batch is None else json.loads(json.dumps(asdict(batch))), slot['batch'])
                self.assertEqual(inputs.batches, tuple(b for b in inputs.slots if b is not None))

    def test_duplicate_canonical_reference_guard_is_retained(self):
        packet=next(p for p in packets() if p['id']=='X212-duplicate-record')
        with self.assertRaises(ContractError) as caught:
            packet_inputs(packet)
        self.assertEqual(caught.exception.code.value,'duplicate')

    def test_six_slots_frozen_and_all_absent(self):
        inputs = DailyObservationsInputs()
        self.assertEqual(inputs.roles, ('calendar_manifest','calendar_slots','observation_coverage',
            'raw_observations','common_observations','basis_provenance'))
        self.assertEqual(inputs.slots, (None,)*6)
        self.assertEqual(inputs.batches, ())
        with self.assertRaises(FrozenInstanceError): inputs.raw_observations = None

    def test_original_synthetic_examples_match_whitelisted_literals(self):
        selected = {p['id']: p for p in packets()}
        for case in ('V235-literal-last252','V201-observed-not-scheduled','V223-prior-skips-invalid-populated-period'):
            self.assertEqual(synthetic_daily_observations_fixture(case), packet_inputs(selected[case]))
            self.assertEqual(json.loads(synthetic_daily_observations_config(case).to_json()),selected[case]['config'])
        with self.assertRaises(ContractError): synthetic_daily_observations_fixture('not-a-fixture')

    def test_each_missing_slot_and_present_empty_are_distinct(self):
        inputs = synthetic_daily_observations_fixture('V201-observed-not-scheduled')
        for i, role in enumerate(inputs.roles):
            original = inputs.slots[i]
            empty = replace(original, columns=tuple(Column(c.name, ()) for c in original.columns),
                metadata=replace(original.metadata, coverage=Coverage(0,0,True)))
            changed = replace(inputs, **{role: empty})
            self.assertIs(changed.slots[i], empty)
            self.assertIn(empty, changed.batches)
            missing = replace(inputs, **{role: None, 'provenance': tuple('unavailable' if n==i else 'synthetic' for n in range(6))})
            self.assertIsNone(missing.slots[i])
            self.assertEqual(len(missing.batches), 5)

    def test_provenance_is_explicit_and_has_exact_shape(self):
        inputs = synthetic_daily_observations_fixture('V201-observed-not-scheduled')
        for origin in (('synthetic',), ['synthetic']*6, ('guessed',)*6, ('unavailable',)*6):
            with self.assertRaises(ContractError): replace(inputs, provenance=origin)
        observed = replace(inputs, provenance=('duckdb_backed_observed',)*6)
        self.assertEqual(observed.slots, inputs.slots)

    def test_namespace_instrument_input_identity_and_kind_refuse(self):
        inputs = synthetic_daily_observations_fixture('V201-observed-not-scheduled')
        batch = inputs.raw_observations
        with self.assertRaises(ContractError): replace(batch, kind=DataKind.TRADE)
        for changed in (
                        replace(batch, metadata=replace(batch.metadata, namespace='other')),
                        replace(batch, metadata=replace(batch.metadata, source=inputs.common_observations.metadata.source)),
                        replace(batch, columns=tuple(Column(c.name,('other',)*len(c.values)) if c.name=='instrument_id' else c for c in batch.columns))):
            with self.assertRaises(ContractError): replace(inputs, raw_observations=changed)

    def test_rectangular_schema_and_original_row_column_order(self):
        batch = synthetic_daily_observations_fixture('V201-observed-not-scheduled').raw_observations
        names = tuple(c.name for c in batch.columns)
        rows = tuple(zip(*(c.values for c in batch.columns)))
        reversed_batch = make_daily_observations_batch(names[::-1],tuple(row[::-1] for row in rows[::-1]),metadata=batch.metadata)
        self.assertEqual(tuple(c.name for c in reversed_batch.columns), names[::-1])
        self.assertEqual(reversed_batch.column('reference_id').values,batch.column('reference_id').values[::-1])
        self.assertIs(reversed_batch.metadata,batch.metadata)
        for n,r in ((list(names),rows),(names,list(rows)),(names,(rows[0][:-1],)),(names[:-1],())):
            with self.assertRaises(ContractError): make_daily_observations_batch(n,r,metadata=batch.metadata)

    def test_unknown_future_knowledge_and_zero_volume_are_unchanged_text(self):
        inputs = synthetic_daily_observations_fixture('V201-observed-not-scheduled')
        raw = inputs.raw_observations
        for known in (None,999999):
            changed = replace(raw,columns=tuple(Column(c.name,(known,)*len(c.values)) if c.name=='known_at_ns' else c for c in raw.columns))
            self.assertIs(replace(inputs,raw_observations=changed).raw_observations,changed)
        self.assertTrue(any(json.loads(v)['volume']==0 for v in raw.column('text').values))


if __name__ == '__main__': unittest.main()
