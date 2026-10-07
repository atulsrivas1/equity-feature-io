"""Actual synthetic DuckDB metadata; expectations originate in fixture bytes."""
from dataclasses import replace
from datetime import date
import hashlib
from pathlib import Path
import tempfile
import unittest

import duckdb
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_duckdb import CatalogConfig, FilePin, SourceSelection, resolve_source


class Cancel:
    def __init__(self, after=0):
        self.calls = 0
        self.after = after

    def is_cancelled(self):
        self.calls += 1
        return self.calls > self.after


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'fictional.duckdb'
        with duckdb.connect(str(self.db)) as con:
            con.execute('CREATE SCHEMA catalog')
            con.execute('CREATE TABLE catalog.datasets(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,view_schema VARCHAR,view_name VARCHAR)')
            con.execute('CREATE TABLE catalog.files(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,session_date DATE,path VARCHAR,bytes BIGINT,rows BIGINT,provenance VARCHAR,original_dataset VARCHAR,substituted_dataset VARCHAR,column_signature VARCHAR,optimized_path VARCHAR,optimized_bytes BIGINT,view_schema VARCHAR,view_name VARCHAR)')
            con.execute("INSERT INTO catalog.datasets VALUES ('prepared','frozen1','FICTION','ohlcv-1d','prepared1','daily')")
        self.original = self.root / 'original.fixture'
        self.optimized = self.root / 'optimized.fixture'
        self.original.write_bytes(b'original fictional independent bytes')
        self.optimized.write_bytes(b'optimized fictional independent bytes')
        self.insert_file()
        self.config = CatalogConfig(self.db)
        self.selection = SourceSelection('prepared','frozen1','FICTION','ohlcv-1d',('2025-03-03',))

    def mutate(self, sql, params=None):
        with duckdb.connect(str(self.db)) as con:
            con.execute(sql,params)

    def insert_file(self, session='2025-03-03', rows=2, original=None, optimized=None, layer='prepared', snapshot='frozen1'):
        original = original or self.original
        optimized = optimized or self.optimized
        self.mutate('INSERT INTO catalog.files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[
            layer,snapshot,'FICTION','ohlcv-1d',date.fromisoformat(session),str(original),original.stat().st_size,
            rows,'unverified_legacy','FICTION','FICTION.SUBSTITUTE','price:double;time:string',
            str(optimized),optimized.stat().st_size,'prepared1','daily'])

    def error(self, code, fn):
        with self.assertRaises(SourceError) as caught:
            fn()
        self.assertEqual(caught.exception.code,code)
        self.assertNotIn(str(self.root),str(caught.exception))

    def test_explicit_generation_excludes_curated_and_other_snapshot(self):
        self.insert_file(layer='curated')
        self.insert_file(snapshot='other')
        result=resolve_source(self.config,self.selection)
        self.assertEqual(len(result.partitions),1)
        row=result.partitions[0]
        self.assertEqual((row.original_path,row.optimized_path,row.declared_rows),(str(self.original),str(self.optimized),2))
        self.assertEqual(row.substituted_dataset,'FICTION.SUBSTITUTE')
        self.assertEqual(row.admission,'unverified_legacy')
        self.assertIsNone(row.original_sha256)
        self.assertIsNone(row.optimized_sha256)
        self.assertEqual(result.identity_digest,resolve_source(self.config,self.selection).identity_digest)

    def test_missing_date_and_declared_empty_are_distinct(self):
        self.mutate('UPDATE catalog.files SET rows=0')
        result=resolve_source(self.config,replace(self.selection,sessions=('2025-03-03','2025-03-04')))
        self.assertEqual(result.missing_sessions,('2025-03-04',))
        self.assertTrue(result.partitions[0].declared_empty)
        self.assertEqual(result.partitions[0].declared_rows,0)

    def test_all_missing_partitions_remain_explicit(self):
        result=resolve_source(self.config,replace(self.selection,sessions=('2025-03-04',)))
        self.assertEqual(result.partitions,())
        self.assertEqual(result.missing_sessions,('2025-03-04',))

    def test_no_route(self):
        self.error(SourceErrorCode.UNAVAILABLE,lambda: resolve_source(self.config,replace(self.selection,snapshot='absent')))

    def test_ambiguous_route(self):
        self.mutate('INSERT INTO catalog.datasets SELECT * FROM catalog.datasets')
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection))

    def test_shards_retained_and_duplicates_rejected(self):
        a=self.root/'a.fixture';b=self.root/'b.fixture';a.write_bytes(b'a');b.write_bytes(b'b')
        self.insert_file(original=a,optimized=b)
        result=resolve_source(self.config,self.selection)
        self.assertEqual({p.original_path for p in result.partitions},{str(a),str(self.original)})
        self.insert_file(original=a,optimized=b)
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection))

    def test_schema_conflict(self):
        self.insert_file(session='2025-03-04')
        self.mutate("UPDATE catalog.files SET column_signature='price:integer' WHERE session_date='2025-03-04'")
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,replace(self.selection,sessions=('2025-03-03','2025-03-04'))))

    def test_correct_schema_pin_and_stale_schema(self):
        sha=hashlib.sha256(b'price:double;time:string').hexdigest()
        self.assertEqual(resolve_source(self.config,replace(self.selection,expected_schema_sha256=sha)).partitions[0].schema_sha256,sha)
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,replace(self.selection,expected_schema_sha256='0'*64)))

    def test_route_conflict_is_not_silent_missing(self):
        self.mutate("UPDATE catalog.files SET view_name='foreign_view'")
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection))

    def test_hashes_bind_both_actual_files_and_receipt(self):
        original=hashlib.sha256(self.original.read_bytes()).hexdigest()
        optimized=hashlib.sha256(self.optimized.read_bytes()).hexdigest()
        pin=FilePin(str(self.original),original,optimized,'receipt-fiction1')
        row=resolve_source(self.config,self.selection,pins=(pin,)).partitions[0]
        self.assertEqual((row.original_sha256,row.optimized_sha256,row.receipt_id),(original,optimized,'receipt-fiction1'))
        self.optimized.write_bytes(b'x'*self.optimized.stat().st_size)
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection,pins=(pin,)))

    def test_wrong_original_hash(self):
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection,pins=(FilePin(str(self.original),'0'*64),)))

    def test_wrong_catalog_hash(self):
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(replace(self.config,expected_sha256='0'*64),self.selection))

    def test_actual_catalog_hash_and_read_only_database(self):
        sha=hashlib.sha256(self.db.read_bytes()).hexdigest()
        result=resolve_source(replace(self.config,expected_sha256=sha),self.selection)
        self.assertEqual(result.catalog_sha256,sha)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),sha)
        with duckdb.connect(str(self.db),read_only=True) as con:
            with self.assertRaises(duckdb.Error):con.execute('DELETE FROM catalog.files')

    def test_file_size_changed(self):
        self.original.write_bytes(b'changed')
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection))

    def test_file_missing(self):
        self.original.unlink()
        self.error(SourceErrorCode.UNAVAILABLE,lambda: resolve_source(self.config,self.selection))

    def test_catalog_missing(self):
        self.error(SourceErrorCode.UNAVAILABLE,lambda: resolve_source(replace(self.config,path=self.root/'absent.duckdb'),self.selection))
        self.assertFalse((self.root/'absent.duckdb').exists())

    def test_extra_and_duplicate_pins(self):
        pin=FilePin(str(self.original))
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection,pins=(pin,pin)))
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection,pins=(FilePin(str(self.root/'other')),)))

    def test_limits(self):
        self.error(SourceErrorCode.LIMIT,lambda: resolve_source(replace(self.config,max_hash_bytes=1),self.selection))
        self.error(SourceErrorCode.LIMIT,lambda: resolve_source(replace(self.config,max_sessions=1),replace(self.selection,sessions=('2025-03-03','2025-03-04'))))
        self.insert_file(session='2025-03-04')
        self.error(SourceErrorCode.LIMIT,lambda: resolve_source(replace(self.config,max_files=1),replace(self.selection,sessions=('2025-03-03','2025-03-04'))))

    def test_cancel_before_and_during_hash(self):
        self.error(SourceErrorCode.CANCELLED,lambda: resolve_source(self.config,self.selection,cancellation=Cancel()))
        self.error(SourceErrorCode.CANCELLED,lambda: resolve_source(self.config,self.selection,cancellation=Cancel(after=1)))

    def test_invalid_identity_and_metadata(self):
        for changes in ({'sessions':('20250303',)},{'sessions':('2025-03-03','2025-03-03')},{'snapshot':''}):
            with self.subTest(changes=changes):self.error(SourceErrorCode.SCHEMA,lambda: replace(self.selection,**changes))
        for value in (None,'unsafe; DROP TABLE catalog.files'):
            self.mutate('UPDATE catalog.datasets SET view_schema=?',[value])
            self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection))

    def test_negative_and_null_metadata(self):
        for statement in ('UPDATE catalog.files SET rows=-1','UPDATE catalog.files SET provenance=NULL'):
            self.mutate(statement)
            self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection))
            self.mutate("UPDATE catalog.files SET rows=2,provenance='unverified_legacy'")

    def test_invalid_config_pin_and_bound_types(self):
        for fn in (lambda: CatalogConfig(Path('relative')),lambda: replace(self.config,max_files=True),lambda: FilePin(str(self.original),'XYZ')):
            self.error(SourceErrorCode.SCHEMA,fn)

    def test_dataset_value_is_bound_not_sql(self):
        self.error(SourceErrorCode.UNAVAILABLE,lambda: resolve_source(self.config,replace(self.selection,dataset="FICTION' OR 1=1 --")))

    def test_actual_parquet_metadata_fixture(self):
        original=self.root/'fictional-original.parquet'
        optimized=self.root/'fictional-optimized.parquet'
        with duckdb.connect() as con:
            for path in (original,optimized):
                con.execute('COPY (SELECT 1800000000000000001::BIGINT AS event_ns, 101::BIGINT AS price, 2::BIGINT AS size) TO ? (FORMAT PARQUET)',[str(path)])
            self.assertEqual(con.execute('SELECT count(*) FROM read_parquet(?)',[str(original)]).fetchone()[0],1)
        self.mutate('DELETE FROM catalog.files')
        self.insert_file(rows=1,original=original,optimized=optimized)
        pin=FilePin(str(original),hashlib.sha256(original.read_bytes()).hexdigest(),hashlib.sha256(optimized.read_bytes()).hexdigest(),'fictional-parquet-receipt')
        row=resolve_source(self.config,self.selection,pins=(pin,)).partitions[0]
        self.assertEqual(row.declared_rows,1)
        self.assertEqual(row.original_bytes,original.stat().st_size)

    def test_catalog_mutation_during_resolution_rejected(self):
        owner=self
        class MutateOnce:
            calls=0
            def is_cancelled(self):
                self.calls+=1
                if self.calls==6:owner.mutate("UPDATE catalog.files SET provenance='changed_revision'")
                return False
        self.error(SourceErrorCode.SCHEMA,lambda: resolve_source(self.config,self.selection,cancellation=MutateOnce()))


if __name__ == '__main__':
    unittest.main()
