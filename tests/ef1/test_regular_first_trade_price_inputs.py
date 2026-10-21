"""Original cells and real constructor/canonical stages; no feature mathematics."""
from collections import Counter
from dataclasses import replace
import json
import unittest
from equity_feature_contracts import Column, ContractError, Coverage, DataKind, validate_batch
from equity_feature_duckdb.regular_first_trade_price import (
    RegularFirstTradePriceInputs, make_regular_first_trade_price_batch,
    make_regular_trade_population_proof, synthetic_regular_first_trade_price_config,
    synthetic_regular_first_trade_price_fixture,
)
from regular_first_trade_price_support import packets, packet_inputs, original_batch


class RegularFirstTradePriceInputTests(unittest.TestCase):
    def test_all_281_original_requests_lossless_or_actual_early_refusal(self):
        cases = packets()
        self.assertEqual(len(cases), 281)
        constructor_stages = {'BatchMetadata_constructor', 'CanonicalBatch_constructor',
            'Coverage_constructor', 'PriceUnit_constructor', 'transport_schema_admission'}
        stages = Counter()
        accepted = 0
        for packet in cases:
            with self.subTest(case=packet['id']):
                error = packet.get('expected_error')
                stage = None if error is None else error['earliest_stage']
                trace = []
                if stage in constructor_stages:
                    with self.assertRaises(ContractError) as caught:
                        tuple(original_batch(s['batch'], convert=False, trace=trace)
                              for s in packet['request']['role_slots'])
                    self.assertEqual(trace[-1], stage)
                    self.assertEqual(caught.exception.code.value, error['code'])
                    with self.assertRaises(ContractError) as converted:
                        packet_inputs(packet)
                    self.assertEqual(converted.exception.code.value, error['code'])
                    stages[stage] += 1
                    continue
                slots = tuple(original_batch(s['batch'], convert=False)
                              for s in packet['request']['role_slots'])
                if stage == 'canonical_validate_batch':
                    with self.assertRaises(ContractError) as caught:
                        for batch in slots:
                            if batch is not None: validate_batch(batch, required_fields=())
                    self.assertEqual(caught.exception.code.value, error['code'])
                    with self.assertRaises(ContractError) as converted: packet_inputs(packet)
                    self.assertEqual(converted.exception.code.value, error['code'])
                    stages[stage] += 1
                    continue
                try:
                    actual = packet_inputs(packet)
                except ContractError as caught:
                    self.assertIsNotNone(error)
                    self.assertEqual(caught.code.value, error['code'])
                    stages['adapter_role_shape_or_container'] += 1
                else:
                    accepted += 1
                    self.assertEqual(actual.roles, ('calendar_provenance', 'trades', 'population_proof'))
                    self.assertEqual(actual.slots, slots)
                    self.assertEqual(actual.batches, tuple(b for b in slots if b is not None))
                    for actual_batch, source_batch in zip(actual.slots, slots):
                        if actual_batch is not None:
                            self.assertEqual(actual_batch.columns, source_batch.columns)
                            self.assertEqual(actual_batch.metadata, source_batch.metadata)
        self.assertEqual({k:v for k,v in stages.items() if k != 'adapter_role_shape_or_container'}, {
            'BatchMetadata_constructor':1, 'CanonicalBatch_constructor':23, 'Coverage_constructor':4,
            'PriceUnit_constructor':3, 'transport_schema_admission':1, 'canonical_validate_batch':20})
        self.assertEqual((accepted, stages['adapter_role_shape_or_container']), (225, 4))
        print('FIRST_TRADE_CONVERSION_CENSUS', accepted, dict(stages), flush=True)

    def test_all_122_success_requests_preserve_every_cell_and_binding(self):
        count = 0
        for packet in packets():
            if packet.get('expected_result') is None: continue
            with self.subTest(case=packet['id']):
                actual = packet_inputs(packet)
                for batch, raw in zip(actual.slots, packet['request']['role_slots']):
                    if batch is None:
                        self.assertIsNone(raw['batch'])
                    else:
                        self.assertEqual(tuple((c.name, c.values) for c in batch.columns),
                            tuple((c['name'], tuple(c['values'])) for c in raw['batch']['columns']))
                        self.assertEqual(batch.metadata.source.input_id, raw['batch']['metadata']['source']['input_id'])
                count += 1
        self.assertEqual(count, 122)

    def test_literal_helpers_equal_original_inputs_and_configs(self):
        selected = {p['id']:p for p in packets()}
        for case in ('R001', 'R019'):
            self.assertEqual(synthetic_regular_first_trade_price_fixture(case), packet_inputs(selected[case]))
            self.assertEqual(json.loads(synthetic_regular_first_trade_price_config(case).to_json()), selected[case]['request']['config'])
        for factory in (synthetic_regular_first_trade_price_config, synthetic_regular_first_trade_price_fixture):
            with self.assertRaises(ContractError): factory('unknown')

    def test_absence_empty_and_present_only_subsequence(self):
        original = synthetic_regular_first_trade_price_fixture()
        for i, role in enumerate(original.roles):
            missing = replace(original, **{role:None, 'provenance':tuple('unavailable' if j == i else 'synthetic' for j in range(3))})
            self.assertIsNone(missing.slots[i])
            self.assertEqual(missing.batches, tuple(b for j,b in enumerate(original.slots) if j != i))
            batch = original.slots[i]
            empty = replace(batch, columns=tuple(Column(c.name, ()) for c in batch.columns),
                metadata=replace(batch.metadata, coverage=Coverage(0,0,True)))
            present = replace(original, **{role:empty})
            self.assertIs(present.slots[i], empty)
            self.assertEqual(len(present.batches),3)
        self.assertEqual(RegularFirstTradePriceInputs().slots,(None,)*3)
        self.assertEqual(RegularFirstTradePriceInputs().batches,())

    def test_supplied_proof_is_not_hashed_or_repaired(self):
        original = synthetic_regular_first_trade_price_fixture().population_proof
        row = {c.name:c.values[0] for c in original.columns}
        for clock in (None,-100,1000):
            supplied = {**row,'known_at_ns':clock,'text':'not parsed, rewritten or repaired'}
            actual = make_regular_trade_population_proof(supplied,metadata=original.metadata)
            self.assertIs(actual.metadata,original.metadata)
            self.assertEqual(tuple(c.name for c in actual.columns),tuple(row))
            for c in actual.columns: self.assertEqual(c.values,(supplied[c.name],))
        for name in row:
            with self.assertRaises(ContractError):
                make_regular_trade_population_proof({k:v for k,v in row.items() if k != name},metadata=original.metadata)

    def test_exact_rectangle_metadata_and_column_order(self):
        batch = synthetic_regular_first_trade_price_fixture().trades
        columns = tuple(reversed(batch.columns))
        actual = make_regular_first_trade_price_batch(DataKind.TRADE,tuple(c.name for c in columns),
            tuple(zip(*(c.values for c in columns))),metadata=batch.metadata)
        self.assertEqual(actual.columns,columns)
        self.assertIs(actual.metadata,batch.metadata)
        for names, rows in ((['instrument_id'],()),(('instrument_id',),[['X']]),(('instrument_id',),(('X','extra'),))):
            with self.assertRaises(ContractError): make_regular_first_trade_price_batch(DataKind.TRADE,names,rows,metadata=batch.metadata)
        with self.assertRaises(ContractError): make_regular_first_trade_price_batch(DataKind.BAR,(),(),metadata=batch.metadata)

    def test_provenance_role_and_actual_source_identity_guards(self):
        original = synthetic_regular_first_trade_price_fixture()
        for modes in (('synthetic',),['synthetic']*3,('unknown',)*3,('unavailable',)*3):
            with self.assertRaises(ContractError): replace(original,provenance=modes)
        observed = replace(original,provenance=('duckdb_backed_observed',)*3)
        self.assertTrue(all(a is b for a,b in zip(observed.slots,original.slots)))
        with self.assertRaises(ContractError): replace(original,trades=original.calendar_provenance)
        with self.assertRaises(ContractError): replace(original,calendar_provenance=original.trades)
        duplicate = replace(original.trades,metadata=replace(original.trades.metadata,source=original.calendar_provenance.metadata.source))
        with self.assertRaises(ContractError) as caught: replace(original,trades=duplicate)
        self.assertEqual(caught.exception.code.value,'duplicate')

    def test_supplied_invalid_unused_numeric_refuses_with_peer_proofs_absent(self):
        packet = next(p for p in packets() if p['id']=='N043')
        with self.assertRaises(ContractError) as caught: packet_inputs(packet)
        self.assertEqual(caught.exception.code.value,'invalid_schema')

    def test_no_sorting_from_event_ids_and_no_64_trade_cap(self):
        selected = {p['id']:p for p in packets()}
        for case in ('R009','R033','R043','R093','R095','R105'):
            batch = packet_inputs(selected[case]).trades
            raw = selected[case]['request']['role_slots'][1]['batch']
            self.assertEqual(tuple(c.values for c in batch.columns),tuple(tuple(c['values']) for c in raw['columns']))
        self.assertEqual(packet_inputs(selected['R105']).trades.row_count,65)


if __name__ == '__main__': unittest.main()
