"""Independent hand-authored source populations and canonical expectations."""
from dataclasses import replace
import unittest

from equity_feature_contracts import BatchMetadata, Coverage, PriceUnit, SourceBinding
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_duckdb import MappingPolicy, RowOccurrence, map_columns, parse_utc_ns


class MappingTests(unittest.TestCase):
    def policy(self, schema='trades', **kw):
        defaults = dict(source_schema=schema, price_unit=PriceUnit(2, 'USD'),
            interpretation='binary64_exact', rounding='half_even', instrument_ids=((7, 'FICTION'),),
            source_clock='event' if schema in ('trades', 'tbbo') else 'receive_aggregation',
            eligibility_policy='fictional-eligibility-v1' if schema == 'trades' else None,
            eligible_default=True if schema == 'trades' else None)
        defaults.update(kw)
        return MappingPolicy(**defaults)

    def rows(self):
        return dict(ts_utc=('2023-11-14T22:13:20.000000001Z',), instrument_id=(7,), price=(10.125,), size=(3,))

    def mapped(self, columns=None, policy=None, **kw):
        columns = self.rows() if columns is None else columns
        policy = self.policy() if policy is None else policy
        n = len(columns['ts_utc'])
        defaults = dict(metadata=BatchMetadata('fictional:v1', SourceBinding('synthetic', 'frozen1', 'map1', 'input1'),
                Coverage(n, n, True), policy.price_unit, sampling='trade_snapshot' if policy.source_schema == 'tbbo' else 'none'),
            occurrences=tuple(RowOccurrence('original-fixture1', i, i) for i in range(n)), sessions=('S1',)*n)
        defaults.update(kw)
        return map_columns(policy, columns, **defaults)

    def error(self, code, fn):
        with self.assertRaises(SourceError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn('secret-path', str(caught.exception))

    def test_exact_utc_ns(self):
        cases = {'1970-01-01T00:00:00Z': 0, '1969-12-31T23:59:59.999999999Z': -1,
            '2023-11-14T22:13:20.123456789+00:00': 1700000000123456789,
            '2000-02-29 00:00:00.1Z': 951782400100000000,
            '1677-09-21T00:12:43.145224192Z': -(2**63),
            '2262-04-11T23:47:16.854775807Z': 2**63-1}
        for stamp, golden in cases.items():
            with self.subTest(stamp=stamp): self.assertEqual(parse_utc_ns(stamp), golden)
        self.assertEqual(parse_utc_ns(1700000000000000001), 1700000000000000001)

    def test_invalid_time(self):
        for value in (True, 1.5, None, 2**63, -(2**63)-1, '2023-11-14T22:13:20',
            '2023-11-14T22:13:20+01:00', '2023-11-14T22:13:60Z', '2023-02-29T00:00:00Z',
            '2023-11-14T24:00:00Z', '2023-11-14T22:13:20.1234567891Z',
            '2262-04-11T23:47:16.854775808Z', 'secret-path'):
            with self.subTest(value=value): self.error(SourceErrorCode.SCHEMA, lambda: parse_utc_ns(value))

    def test_trade_expected(self):
        result = self.mapped()
        self.assertEqual(result.batch.column('event_ns').values, (1700000000000000001,))
        self.assertEqual(result.batch.column('price').values, (1012,))
        self.assertEqual(result.batch.column('size').values, (3,))
        self.assertEqual(result.batch.column('eligible').values, (True,))
        self.assertIsNone(result.batch.column('known_at_ns'))
        self.assertEqual(result.report.price_conversions[0].rounded_cells, 1)
        self.assertEqual(result.report.eligibility_source, 'caller_assertion')

    def test_half_even_independent_ties(self):
        d=self.rows(); d.update(ts_utc=(1,2,3,4), instrument_id=(7,)*4, price=(10.125,10.375,0.125,0.375),size=(1,)*4)
        self.assertEqual(self.mapped(d).batch.column('price').values, (1012,1038,12,38))

    def test_price_interpretation(self):
        d=self.rows();d['price']=(0.1,)
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,self.policy(rounding='exact')))
        result=self.mapped(d,self.policy(rounding='exact',interpretation='decimal_repr'))
        self.assertEqual(result.batch.column('price').values,(10,))
        self.assertEqual(result.report.price_conversions[0].interpretation,'decimal_repr')

    def test_invalid_price_and_shares(self):
        for price in (float('nan'),float('inf'),True,1,1e20):
            d=self.rows();d['price']=(price,)
            self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d))
        for size in (-1,True,1.0,2**63):
            d=self.rows();d['size']=(size,)
            self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d))

    def test_missing_null_zero(self):
        d=self.rows();d.pop('price');d['size']=(0,)
        result=self.mapped(d,self.policy(eligible_default=False))
        self.assertIsNone(result.batch.column('price'))
        self.assertEqual(result.batch.column('size').values,(0,))
        d['price']=(None,);d['size']=(None,)
        result=self.mapped(d,self.policy(eligible_default=False))
        self.assertEqual(result.batch.column('price').values,(None,))
        self.assertEqual(result.batch.column('size').values,(None,))

    def test_eligibility_required(self):
        self.error(SourceErrorCode.UNAVAILABLE,lambda:self.mapped(policy=self.policy(eligible_default=None)))
        self.error(SourceErrorCode.UNAVAILABLE,lambda:self.mapped(policy=self.policy(eligibility_policy=None,eligible_default=None)))
        d=self.rows();d['eligible']=(False,)
        r=self.mapped(d,self.policy(eligible_default=None));self.assertEqual(r.batch.column('eligible').values,(False,))
        self.assertEqual(r.report.eligibility_source,'column')
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d))
        d['eligible']=(None,);self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,self.policy(eligible_default=None)))

    def test_tied_equal_payload_occurrences(self):
        d={k:v*2 for k,v in self.rows().items()}
        r=self.mapped(d);self.assertEqual(r.batch.row_count,2)
        self.assertEqual(r.batch.column('order_key').values,(0,1))
        self.assertEqual(len(set(r.batch.column('event_id').values)),2)
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,occurrences=(RowOccurrence('file1',0,0),)*2))
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,occurrences=(RowOccurrence('file1',0,0),RowOccurrence('file1',1,0))))

    def test_occurrence_identity_independent_of_payload(self):
        a=self.mapped();d=self.rows();d['price']=(12.5,);b=self.mapped(d)
        self.assertEqual(a.batch.column('event_id').values,b.batch.column('event_id').values)
        self.assertNotEqual(a.report.digest,b.report.digest)
        self.assertNotEqual(a.batch.metadata.source.input_id,b.batch.metadata.source.input_id)
        c=self.mapped(occurrences=(RowOccurrence('other-original',0,0),))
        self.assertNotEqual(a.batch.column('event_id').values,c.batch.column('event_id').values)

    def test_known_at_preserved(self):
        d=self.rows();d['known_at_ns']=(None,)
        self.assertEqual(self.mapped(d).batch.column('known_at_ns').values,(None,))
        d['known_at_ns']=('2023-11-15T00:00:00Z',)
        self.assertEqual(self.mapped(d).batch.column('known_at_ns').values,(1700006400000000000,))

    def test_trade_snapshot_quote(self):
        d=dict(ts_utc=(1,2,3),instrument_id=(7,)*3,bid=(10.0,10.0,None),ask=(11.0,9.0,0.0),bid_size=(0,None,3),ask_size=(1,2,3))
        r=self.mapped(d,self.policy('tbbo'))
        self.assertEqual(r.batch.metadata.sampling,'trade_snapshot')
        self.assertEqual(r.batch.column('bid').values,(1000,1000,None))
        self.assertEqual(r.batch.column('ask').values,(1100,900,0))
        self.assertIsNone(r.batch.column('eligible'))
        bad=replace(r.batch.metadata,sampling='continuous')
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.mapped(d,self.policy('tbbo'),metadata=bad))

    def test_minute_bar_and_daily_intervals(self):
        d=dict(ts_utc=('2025-01-02T00:00:00Z',),instrument_id=(7,),open=(10.0,),high=(12.0,),low=(9.0,),close=(11.0,),volume=(123,))
        for schema,end in [('ohlcv-1m',1735776060000000000),('ohlcv-1d',1735862400000000000)]:
            r=self.mapped(d,self.policy(schema))
            self.assertEqual(r.batch.column('start_ns').values,(1735776000000000000,))
            self.assertEqual(r.batch.column('end_ns').values,(end,))
            self.assertEqual(r.batch.column('volume').values,(123,))
            self.assertIn('receive_aggregation_UTC',r.report.interval_clock)
            self.assertIsNone(r.batch.column('actual_notional'))
        d['ts_utc']=(1735776000000000001,)
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,self.policy('ohlcv-1m')))
        d['ts_utc']=(9223372020000000000,)
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,self.policy('ohlcv-1m')))

    def test_zero_volume_and_malformed_ohlc(self):
        d=dict(ts_utc=(0,),instrument_id=(7,),open=(10.0,),high=(12.0,),low=(9.0,),close=(11.0,),volume=(0,))
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,self.policy('ohlcv-1m')))
        for k in ('open','high','low','close'):d[k]=(None,)
        self.assertEqual(self.mapped(d,self.policy('ohlcv-1m')).batch.column('volume').values,(0,))
        d.update(open=(10.0,),high=(9.0,),low=(8.0,),close=(8.0,),volume=(1,))
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d,self.policy('ohlcv-1m')))

    def test_unmapped_not_inferred(self):
        d=self.rows();d['symbol']=('FICTION',);d['tick_rule_sign']=(1,)
        r=self.mapped(d)
        self.assertEqual(r.report.unmapped_fields,('symbol','tick_rule_sign'))
        d['instrument_id']=(99,)
        self.error(SourceErrorCode.UNAVAILABLE,lambda:self.mapped(d))

    def test_owned_and_policy_binding(self):
        d={k:list(v) for k,v in self.rows().items()};a=self.mapped(d);d['price'][0]=99.0
        self.assertEqual(a.batch.column('price').values,(1012,))
        b=self.mapped(policy=self.policy(interpretation='decimal_repr'))
        self.assertNotEqual(a.report.digest,b.report.digest)

    def test_bounds_and_shape(self):
        d={k:v*2 for k,v in self.rows().items()}
        self.error(SourceErrorCode.LIMIT,lambda:self.mapped(d,self.policy(max_rows=1)))
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(sessions=()))
        d=self.rows();d['size']=(1,2)
        self.error(SourceErrorCode.SCHEMA,lambda:self.mapped(d))
        d=self.rows();d.pop('ts_utc')
        meta=BatchMetadata('fiction',SourceBinding('s','p','m','i'),Coverage(1,1,True),PriceUnit(2,'USD'))
        self.error(SourceErrorCode.SCHEMA,lambda:map_columns(self.policy(),d,metadata=meta,occurrences=(RowOccurrence('f',0,0),),sessions=('s',)))

    def test_empty_population(self):
        r=self.mapped({k:() for k in self.rows()});self.assertEqual(r.batch.row_count,0)
        self.assertEqual(r.batch.metadata.coverage,Coverage(0,0,True))

    def test_invalid_configuration(self):
        for kw in [dict(source_clock='unknown'),dict(source_schema='definition'),dict(source_clock='receive_aggregation')]:
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.policy(**kw))
        for kw in [dict(max_rows=True),dict(instrument_ids=((7,'A'),(8,'A'))),dict(eligible_default='yes'),dict(rounding='implicit')]:
            self.error(SourceErrorCode.SCHEMA,lambda:self.policy(**kw))
        for args in [('file',True,0),('file',0,-1),('',0,0)]:
            self.error(SourceErrorCode.SCHEMA,lambda:RowOccurrence(*args))


if __name__ == '__main__': unittest.main()
