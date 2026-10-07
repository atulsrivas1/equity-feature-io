"""Actual original Parquet reads with independent occurrence/time/population goldens."""
from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

import duckdb
from equity_feature_contracts import AvailabilitySpec, Coverage, DataKind, InputScope, PriceUnit, SessionSpec
from equity_feature_contracts.adapters import AcquisitionRequest, SourceError, SourceErrorCode, validate_delivery
from equity_feature_duckdb import (
    CatalogConfig, CoverageAssertion, DuckDBHistoricalAdapter, MappingPolicy, ReadConfig,
    SourceSelection, resolve_source,
)


class Cancel:
    def __init__(self): self.cancelled = False
    def is_cancelled(self): return self.cancelled


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root/'catalog.duckdb'
        self.parts = []
        self.init_catalog('trades')
        self.add_file("SELECT instrument_id,ts_utc,price::DOUBLE price,size FROM (VALUES (7,'1970-01-01T00:00:00.000000020Z',10.0,2),(7,'1970-01-01T00:00:00.000000010Z',10.125,3),(8,'1970-01-01T00:00:00.000000012Z',9.0,4)) t(instrument_id,ts_utc,price,size)",3)
        self.add_file("SELECT instrument_id,ts_utc,price::DOUBLE price,size FROM (VALUES (7,'1970-01-01T00:00:00.000000010Z',10.125,3),(7,'1970-01-01T00:00:00.000000015Z',10.375,5),(7,'1970-01-01T00:00:00.000000021Z',12.0,1)) t(instrument_id,ts_utc,price,size)",3)

    def init_catalog(self, schema):
        with duckdb.connect(str(self.db)) as c:
            c.execute('CREATE SCHEMA IF NOT EXISTS catalog')
            c.execute('CREATE OR REPLACE TABLE catalog.catalog.datasets(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,view_schema VARCHAR,view_name VARCHAR)')
            c.execute('CREATE OR REPLACE TABLE catalog.catalog.files(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,session_date DATE,path VARCHAR,bytes BIGINT,rows BIGINT,provenance VARCHAR,original_dataset VARCHAR,substituted_dataset VARCHAR,column_signature VARCHAR,optimized_path VARCHAR,optimized_bytes BIGINT,view_schema VARCHAR,view_name VARCHAR)')
            c.execute("INSERT INTO catalog.catalog.datasets VALUES ('prepared','frozen1','FICTION',?,'prepared1','source1')",[schema])
        self.schema = schema
        self.parts = []

    def add_file(self, query, rows):
        original = self.root/f'original-{len(self.parts)}.parquet'
        optimized = self.root/f'optimized-{len(self.parts)}.parquet'
        with duckdb.connect(str(self.db)) as c:
            c.execute('COPY ('+query+') TO ? (FORMAT PARQUET)',[str(original)])
            shutil.copyfile(original,optimized)
            c.execute('INSERT INTO catalog.catalog.files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[
                'prepared','frozen1','FICTION',self.schema,'1970-01-01',str(original),original.stat().st_size,
                rows,'unverified_legacy','FICTION',None,'fictional-signature1',str(optimized),optimized.stat().st_size,'prepared1','source1'])
        self.parts.append(original)

    def adapter(self, **kw):
        resolution=resolve_source(CatalogConfig(self.db),SourceSelection('prepared','frozen1','FICTION',self.schema,('1970-01-01',)))
        is_trade=self.schema=='trades'
        clock='event' if self.schema in ('trades','tbbo') else 'receive_aggregation'
        mapping=MappingPolicy(self.schema,PriceUnit(2,'USD'),'decimal_repr','half_even',((7,'A'),(8,'B')),clock,
            'fixture-v1' if is_trade else None,True if is_trade else None)
        close=30 if self.schema in ('trades','tbbo') else 3*60*10**9 if self.schema=='ohlcv-1m' else 86400*10**9
        defaults=dict(catalog_path=self.db,resolved=resolution,mapping=mapping,namespace='fiction:v1',source_id='synthetic',calendar_version='session-fixture-v1',
            sessions=(SessionSpec('fiction:v1','S1',0,close,'UTC'),),partition_sessions=(('1970-01-01','S1'),),scope=InputScope(0,close,'fixture-v1'))
        defaults.update(kw)
        return DuckDBHistoricalAdapter(ReadConfig(**defaults))

    def request(self, **kw):
        kind={'trades':DataKind.TRADE,'tbbo':DataKind.QUOTE,'ohlcv-1m':DataKind.BAR,'ohlcv-1d':DataKind.DAILY}[self.schema]
        defaults=dict(request_id='r1',kind=kind,namespace='fiction:v1',instruments=('A',),sessions=('S1',),start_ns=10,end_ns=20,
            snapshot_id='frozen1',price_unit=PriceUnit(2,'USD'),availability=AvailabilitySpec(20,20,20),max_batch_rows=2,max_rows=10,max_batches=10,
            sampling='trade_snapshot' if kind==DataKind.QUOTE else 'none',selection='completed_intervals' if kind in (DataKind.BAR,DataKind.DAILY) else 'event_half_open')
        defaults.update(kw)
        return AcquisitionRequest(**defaults)

    def error(self, code, fn):
        with self.assertRaises(SourceError) as caught: fn()
        self.assertEqual(caught.exception.code,code)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn(str(self.root),str(caught.exception))

    def test_original_order_occurrence_and_bounds(self):
        adapter=self.adapter();request=self.request();before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        result=adapter.read(request)
        self.assertEqual(result.canonical.column('event_ns').values,(10,10,15))
        self.assertEqual(result.canonical.column('price').values,(1012,1012,1038))
        self.assertEqual(result.canonical.column('size').values,(3,3,5))
        self.assertEqual(result.canonical.column('order_key').values,(0,1,2))
        self.assertEqual(len(set(result.canonical.column('event_id').values)),3)
        self.assertIsNone(result.canonical.column('known_at_ns'))
        self.assertEqual(result.canonical.metadata.coverage,Coverage(None,3,False))
        self.assertEqual([e.batch.row_count for e in result.batches],[2,1])
        self.assertEqual([e.final for e in result.batches],[False,True])
        self.assertEqual(result.batches[0].source.mapping_version,result.batches[1].source.mapping_version)
        self.assertNotEqual(result.batches[0].source.input_id,result.batches[1].source.input_id)
        validate_delivery(request,adapter.capabilities(),result.batches)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),before)
        self.assertEqual(result.metrics.delivered_rows,3)
        self.assertEqual(result.metrics.files,2)
        self.assertEqual(result.metrics.selected_file_bytes,sum(p.stat().st_size for p in self.parts))
        self.assertGreater(result.metrics.sql_fetch_ns,0)
        self.assertGreater(result.metrics.mapping_ns,0)

    def test_original_physical_row_identity_preserved(self):
        adapter=self.adapter()
        first=adapter.read(self.request(end_ns=11)).canonical
        wider=adapter.read(self.request()).canonical
        self.assertEqual(first.column('event_id').values,wider.column('event_id').values[:2])
        # Different request identity cannot replace original occurrence identity.
        self.assertNotEqual(first.metadata.source.input_id,wider.metadata.source.input_id)

    def test_optimized_not_mistaken_for_original(self):
        # Valid equal-size optimized content is intentionally replaced; source reads stay original.
        p=self.root/'optimized-0.parquet';p.write_bytes(b'X'*p.stat().st_size)
        self.assertEqual(self.adapter().read(self.request()).canonical.column('event_ns').values,(10,10,15))

    def test_one_nanosecond_half_open(self):
        result=self.adapter().read(self.request(start_ns=15,end_ns=16))
        self.assertEqual(result.canonical.column('event_ns').values,(15,))
        self.assertEqual(self.adapter().read(self.request(start_ns=16,end_ns=20)).canonical.row_count,0)

    def test_instrument_and_session_predicates(self):
        self.assertEqual(self.adapter().read(self.request(instruments=('B',))).canonical.column('size').values,(4,))
        restricted=self.adapter(sessions=(SessionSpec('fiction:v1','S1',11,20,'UTC'),),scope=InputScope(0,30,'fixture-v1'))
        self.assertEqual(restricted.read(self.request()).canonical.column('event_ns').values,(15,))

    def test_complete_only_matching_assertion(self):
        claim=CoverageAssertion(('A',),('S1',),10,20,3,'population-count1')
        adapter=self.adapter(coverage_assertion=claim);result=adapter.read(self.request())
        self.assertEqual(result.canonical.metadata.coverage,Coverage(3,3,True))
        validate_delivery(self.request(),adapter.capabilities(),result.batches)
        self.error(SourceErrorCode.SCHEMA,lambda:adapter.read(self.request(end_ns=16)))
        self.error(SourceErrorCode.SCHEMA,lambda:self.adapter(coverage_assertion=replace(claim,expected_rows=4)).read(self.request()))

    def test_empty_distinct_from_missing(self):
        adapter=self.adapter();r=adapter.read(self.request(start_ns=16,end_ns=20))
        self.assertIsNotNone(r.canonical);self.assertEqual(r.canonical.row_count,0)
        self.assertEqual(r.batches[0].disposition,'observed');self.assertTrue(r.batches[0].final)
        with duckdb.connect(str(self.db)) as c: c.execute('DELETE FROM catalog.catalog.files')
        adapter=self.adapter();r=adapter.read(self.request())
        self.assertIsNone(r.canonical);self.assertEqual(r.batches[0].disposition,'missing')
        validate_delivery(self.request(),adapter.capabilities(),r.batches)

    def test_bounds_before_yield(self):
        for kwargs in [dict(max_rows=2,max_batch_rows=2),dict(max_batches=1,max_batch_rows=2)]:
            self.error(SourceErrorCode.LIMIT,lambda:list(self.adapter().iter_batches(self.request(**kwargs),Cancel())))
        self.error(SourceErrorCode.LIMIT,lambda:self.adapter(max_files=1).read(self.request()))

    def test_pre_and_between_chunk_cancel(self):
        cancel=Cancel();cancel.cancelled=True
        self.error(SourceErrorCode.CANCELLED,lambda:self.adapter().read(self.request(),cancel))
        cancel=Cancel();iterator=self.adapter().iter_batches(self.request(),cancel)
        first=next(iterator);self.assertFalse(first.final)
        cancel.cancelled=True;self.error(SourceErrorCode.CANCELLED,lambda:next(iterator))

    def test_snapshot_unit_kind_namespace_scope(self):
        for kwargs in [dict(snapshot_id='other'),dict(price_unit=PriceUnit(4,'USD')),dict(namespace='other'),dict(kind=DataKind.QUOTE,sampling='continuous'),dict(start_ns=-1)]:
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.adapter().read(self.request(**kwargs)))
        self.error(SourceErrorCode.UNAVAILABLE,lambda:self.adapter().read(self.request(instruments=('UNKNOWN',))))
        self.error(SourceErrorCode.UNAVAILABLE,lambda:self.adapter().read(self.request(sessions=('UNKNOWN',))))

    def test_stale_count_schema_and_missing_file(self):
        with duckdb.connect(str(self.db)) as c:c.execute('UPDATE catalog.catalog.files SET rows=4')
        self.error(SourceErrorCode.SCHEMA,lambda:self.adapter().read(self.request()))
        with duckdb.connect(str(self.db)) as c:c.execute('UPDATE catalog.catalog.files SET rows=3')
        adapter=self.adapter();self.parts[0].unlink()
        self.error(SourceErrorCode.UNAVAILABLE,lambda:adapter.read(self.request()))

    def test_invalid_utc_source_suppresses_private_context(self):
        self.init_catalog('trades')
        self.add_file("SELECT 7 instrument_id,'invalid-secret' ts_utc,10.0::DOUBLE price,1 size",1)
        self.error(SourceErrorCode.SCHEMA,lambda:self.adapter().read(self.request()))

    def test_null_time_cannot_qualify_observed_empty(self):
        self.init_catalog('trades')
        self.add_file("SELECT 7 instrument_id,NULL::VARCHAR ts_utc,10.0::DOUBLE price,1 size",1)
        self.error(SourceErrorCode.SCHEMA,lambda:self.adapter().read(self.request()))
        claim=CoverageAssertion(('A',),('S1',),10,20,0,'declared-empty1')
        self.error(SourceErrorCode.SCHEMA,lambda:self.adapter(coverage_assertion=claim).read(self.request()))

    def test_minute_and_daily_whole_intervals(self):
        for schema,duration in [('ohlcv-1m',60*10**9),('ohlcv-1d',86400*10**9)]:
            self.init_catalog(schema)
            self.add_file('SELECT 7 instrument_id,\'1970-01-01T00:00:00Z\' ts_utc,10.0::DOUBLE open,12.0::DOUBLE high,9.0::DOUBLE low,11.0::DOUBLE "close",123::UBIGINT volume',1)
            adapter=self.adapter();request=self.request(start_ns=0,end_ns=duration)
            r=adapter.read(request)
            self.assertEqual(r.canonical.column('end_ns').values,(duration,))
            self.assertEqual(r.canonical.column('volume').values,(123,))
            validate_delivery(request,adapter.capabilities(),r.batches)
            self.assertEqual(adapter.read(self.request(start_ns=0,end_ns=duration-1)).canonical.row_count,0)

    def test_trade_snapshot_known_at_preserved(self):
        self.init_catalog('tbbo')
        self.add_file("SELECT 7 instrument_id,'1970-01-01T00:00:00.000000015Z' ts_utc,10.0::DOUBLE bid,11.0::DOUBLE ask,2 bid_size,3 ask_size,NULL::BIGINT known_at_ns",1)
        r=self.adapter().read(self.request());self.assertEqual(r.canonical.metadata.sampling,'trade_snapshot')
        self.assertEqual(r.canonical.column('known_at_ns').values,(None,))
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.adapter().read(self.request(sampling='continuous')))

    def test_invalid_governed_config(self):
        for kwargs in [dict(threads=True),dict(partition_sessions=()),dict(calendar_version=''),dict(scope=InputScope(0,30,'other'))]:
            self.error(SourceErrorCode.SCHEMA,lambda:self.adapter(**kwargs))
        self.error(SourceErrorCode.SCHEMA,lambda:CoverageAssertion(('A',),('S1',),'10','20',3,'p'))


if __name__=='__main__':unittest.main()
