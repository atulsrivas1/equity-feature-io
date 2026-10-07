"""Independent actual file identities, mutation/pin/budget and receipt checks."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import duckdb
import test_reader as source_fixture
from equity_feature_contracts import AvailabilitySpec, Coverage
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_duckdb import (
    CatalogConfig, DuckDBHistoricalAdapter, FilePin, VerificationPolicy, resolve_source,
)
from equity_feature_duckdb.resolver import _HashBudget


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.f = source_fixture.ReaderTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def adapter(self, **kwargs): return self.f.adapter(**kwargs)

    def pinned(self, *, optimized=True):
        config = self.adapter().config
        pins = tuple(FilePin(p.original_path, sha(p.original_path),
            sha(p.optimized_path) if optimized else None, 'fixture-receipt1') for p in config.resolved.partitions)
        resolved = resolve_source(CatalogConfig(self.f.db), config.resolved.selection, pins=pins)
        return DuckDBHistoricalAdapter(replace(config, resolved=resolved))

    def error(self, code, fn):
        with self.assertRaises(SourceError) as caught: fn()
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn(str(self.f.root), str(caught.exception))

    def test_observed_identity_normalization_coverage_and_byte_budget(self):
        request=self.f.request(); result=self.adapter().read(request); r=result.receipt
        expected=3*self.f.db.stat().st_size+2*sum(p.stat().st_size for p in self.f.parts)
        self.assertEqual(r.hash_bytes,expected)
        self.assertEqual(result.metrics.verification_hash_bytes,expected)
        self.assertGreater(result.metrics.verification_ns,0)
        self.assertEqual([e.observed_original_sha256 for e in r.files],[sha(p) for p in self.f.parts])
        self.assertTrue(all(e.verified_optimized_sha256 is None for e in r.files))
        self.assertEqual(r.pin_strength,'observed_without_all_original_pins')
        self.assertEqual(r.normalization.version,'retained-map1')
        self.assertEqual(r.normalization.digest,result.mapping_report.digest)
        self.assertEqual(r.source,result.canonical.metadata.source)
        self.assertIn('original-read2:'+r.input_evidence_digest,r.source.mapping_version)
        self.assertEqual(r.availability,request.availability)
        self.assertEqual(r.coverage,Coverage(None,3,False))
        self.assertEqual((r.schema,r.canonical_schema,r.adapter_version),('acquisition1',1,'0.1.0a8'))
        self.assertEqual(r.identity_digest,hashlib.sha256(json.dumps(asdict(r),sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertTrue(all(e.partition.admission=='unverified_legacy' for e in r.files))
        files=list(r.files);owned=replace(r,files=files);files.clear()
        self.assertEqual(len(owned.files),2)
        self.error(SourceErrorCode.SCHEMA,lambda:replace(r,availability='invented'))

    def test_all_pins_and_receipt_ids_preserved(self):
        adapter=self.pinned();r=adapter.read(self.f.request()).receipt
        expected=3*self.f.db.stat().st_size+4*sum(p.stat().st_size for p in self.f.parts)
        self.assertEqual(r.hash_bytes,expected)
        self.assertEqual(r.pin_strength,'all_selected_originals_pinned')
        self.assertTrue(all(e.partition.receipt_id=='fixture-receipt1' and e.verified_optimized_sha256==sha(e.partition.optimized_path) for e in r.files))
        self.assertEqual(r.files[0].observed_original_sha256,r.files[0].partition.original_sha256)

    def test_strict_missing_original_pins_and_invalid_policy(self):
        self.error(SourceErrorCode.UNAVAILABLE,lambda:self.adapter(verification=VerificationPolicy(require_original_pins=True)).read(self.f.request()))
        a=self.pinned(optimized=False)
        a=DuckDBHistoricalAdapter(replace(a.config,verification=VerificationPolicy(require_original_pins=True)))
        self.assertEqual(a.read(self.f.request()).receipt.pin_strength,'all_selected_originals_pinned')
        for kw in ({'max_hash_bytes':True},{'max_files':0},{'require_original_pins':1}):
            self.error(SourceErrorCode.SCHEMA,lambda:VerificationPolicy(**kw))
        self.error(SourceErrorCode.SCHEMA,lambda:self.adapter(verification='size-only'))

    def test_exact_hash_budget_and_file_bound(self):
        exact=3*self.f.db.stat().st_size+2*sum(p.stat().st_size for p in self.f.parts)
        self.assertEqual(self.adapter(verification=VerificationPolicy(max_hash_bytes=exact)).read(self.f.request()).receipt.hash_bytes,exact)
        self.error(SourceErrorCode.LIMIT,lambda:self.adapter(verification=VerificationPolicy(max_hash_bytes=exact-1)).read(self.f.request()))
        self.error(SourceErrorCode.LIMIT,lambda:self.adapter(verification=VerificationPolicy(max_files=1)).read(self.f.request()))

    def test_transient_catalog_size_cannot_undercharge_shared_budget(self):
        # Independent review probe: restore the accepted larger catalog after
        # preflight stat, before the first actual resolver hash.
        catalog=self.f.db.read_bytes();limit=2*len(catalog)
        a=self.adapter(verification=VerificationPolicy(max_hash_bytes=limit))
        self.f.db.write_bytes(b'xx');read=_HashBudget.read;hashed=0
        class Restore:
            calls=0
            def is_cancelled(inner):
                inner.calls+=1
                if inner.calls==2:self.f.db.write_bytes(catalog)
                return False
        def charged(budget,path,expected_size=None):
            nonlocal hashed
            result=read(budget,path,expected_size)
            hashed+=Path(path).stat().st_size
            return result
        with patch.object(_HashBudget,'read',charged):
            self.error(SourceErrorCode.LIMIT,lambda:a.read(self.f.request(),Restore()))
        self.assertEqual(hashed,limit)
        self.assertEqual(self.f.db.read_bytes(),catalog)

    def test_same_size_catalog_change_is_stale(self):
        adapter=self.adapter();size=self.f.db.stat().st_size
        with duckdb.connect(str(self.f.db)) as con:
            con.execute("UPDATE catalog.catalog.files SET provenance='unverified_other'")
        self.assertEqual(self.f.db.stat().st_size,size)
        self.error(SourceErrorCode.SCHEMA,lambda:adapter.read(self.f.request()))

    def test_resolution_digest_and_consistent_metadata_forgery(self):
        a=self.adapter();resolved=a.config.resolved
        broken=replace(resolved,identity_digest='0'*64)
        self.error(SourceErrorCode.SCHEMA,lambda:DuckDBHistoricalAdapter(replace(a.config,resolved=broken)).read(self.f.request()))
        p=replace(resolved.partitions[0],admission='fabricated')
        forged=replace(resolved,partitions=(p,*resolved.partitions[1:]))
        payload=dict(selection=asdict(forged.selection),catalog_sha256=forged.catalog_sha256,view_schema=forged.view_schema,
            view_name=forged.view_name,partitions=[asdict(x) for x in forged.partitions],missing_sessions=forged.missing_sessions)
        forged=replace(forged,identity_digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.error(SourceErrorCode.SCHEMA,lambda:DuckDBHistoricalAdapter(replace(a.config,resolved=forged)).read(self.f.request()))

    def test_original_pin_detects_same_size_change_before_read(self):
        a=self.pinned();p=self.f.parts[0];data=p.read_bytes();p.write_bytes(b'X'+data[1:])
        self.assertEqual(p.stat().st_size,len(data))
        self.error(SourceErrorCode.SCHEMA,lambda:a.read(self.f.request()))

    def test_optimized_unpinned_and_pinned_remain_distinct(self):
        pinned=self.pinned();unpinned=self.adapter();p=self.f.root/'optimized-0.parquet'
        data=p.read_bytes();p.write_bytes(b'X'+data[1:])
        r=unpinned.read(self.f.request());self.assertEqual(r.canonical.column('price').values,(1012,1012,1038))
        self.assertIsNone(r.receipt.files[0].verified_optimized_sha256)
        self.error(SourceErrorCode.SCHEMA,lambda:pinned.read(self.f.request()))

    def test_change_during_read_withholds_all_envelopes(self):
        a=self.adapter();p=self.f.parts[0];original=p.read_bytes();read=_HashBudget.read;calls=0
        def changed(budget,path,expected_size=None):
            nonlocal calls
            if Path(path)==p:
                calls+=1
                if calls==2:
                    data=p.read_bytes();p.write_bytes(b'X'+data[1:])
            return read(budget,path,expected_size)
        with patch.object(_HashBudget,'read',changed):
            self.error(SourceErrorCode.SCHEMA,lambda:next(a.iter_batches(self.f.request(),source_fixture.Cancel())))
        self.assertEqual(calls,2)
        p.write_bytes(original);pinned=self.pinned();opt=self.f.root/'optimized-0.parquet';calls=0
        def optimized_changed(budget,path,expected_size=None):
            nonlocal calls
            if Path(path)==opt:
                calls+=1
                if calls==2:
                    data=opt.read_bytes();opt.write_bytes(b'X'+data[1:])
            return read(budget,path,expected_size)
        with patch.object(_HashBudget,'read',optimized_changed):
            self.error(SourceErrorCode.SCHEMA,lambda:pinned.read(self.f.request()))
        self.assertEqual(calls,2)

    def test_cancellation_during_actual_hashing(self):
        class CancelOnHash:
            def is_cancelled(inner): return inner.cancelled
            cancelled=False
        cancel=CancelOnHash();read=_HashBudget.read
        def cancelled(budget,path,expected_size=None):
            if str(path)==str(self.f.parts[0]):cancel.cancelled=True
            return read(budget,path,expected_size)
        with patch.object(_HashBudget,'read',cancelled):
            self.error(SourceErrorCode.CANCELLED,lambda:self.adapter().read(self.f.request(),cancel))

    def test_missing_empty_and_missing_file(self):
        r=self.adapter().read(self.f.request(start_ns=16,end_ns=20)).receipt
        self.assertEqual((r.disposition,r.rows),('data',0));self.assertEqual(r.normalization.rows,0)
        a=self.adapter();self.f.parts[0].unlink()
        self.error(SourceErrorCode.UNAVAILABLE,lambda:a.read(self.f.request()))
        with duckdb.connect(str(self.f.db)) as con:con.execute('DELETE FROM catalog.catalog.files')
        missing=self.adapter().read(self.f.request()).receipt
        self.assertEqual((missing.disposition,missing.rows,missing.files,missing.missing_sessions),('missing',0,(),('1970-01-01',)))
        self.assertIsNone(missing.normalization);self.assertEqual(missing.coverage,Coverage(None,0,False))
        self.assertEqual(missing.hash_bytes,3*self.f.db.stat().st_size)

    def test_repeat_subset_chunk_and_availability_identity(self):
        a=self.adapter();req=self.f.request();r=a.read(req);again=a.read(req)
        self.assertEqual(r.receipt.identity_digest,again.receipt.identity_digest)
        smaller=a.read(self.f.request(end_ns=11));chunk=a.read(self.f.request(max_batch_rows=1))
        self.assertEqual(r.canonical.column('event_id').values[:2],smaller.canonical.column('event_id').values)
        self.assertEqual(r.canonical.column('event_id').values,chunk.canonical.column('event_id').values)
        self.assertNotEqual(r.receipt.identity_digest,chunk.receipt.identity_digest)
        later=a.read(replace(req,availability=AvailabilitySpec(20,21,21)))
        self.assertNotEqual(r.receipt.identity_digest,later.receipt.identity_digest)
        self.assertEqual(later.receipt.availability.knowledge_cutoff_ns,21)

    def test_valid_unpinned_pre_read_change_binds_observed_occurrence(self):
        self.f.init_catalog('trades')
        query="SELECT 7 instrument_id,'1970-01-01T00:00:00.000000010Z' ts_utc,10.0::DOUBLE price,1 size"
        self.f.add_file(query,1);a=self.adapter();first=a.read(self.f.request());p=self.f.parts[0];size=p.stat().st_size
        replacement=self.f.root/'replacement.parquet'
        with duckdb.connect() as con:con.execute('COPY ('+query.replace('10.0::DOUBLE','11.0::DOUBLE')+') TO ? (FORMAT PARQUET)',[str(replacement)])
        self.assertEqual(replacement.stat().st_size,size);shutil.copyfile(replacement,p)
        second=a.read(self.f.request())
        self.assertEqual(second.canonical.column('price').values,(1100,))
        self.assertNotEqual(first.receipt.identity_digest,second.receipt.identity_digest)
        self.assertNotEqual(first.canonical.column('event_id').values,second.canonical.column('event_id').values)
        self.assertEqual(second.receipt.pin_strength,'observed_without_all_original_pins')

    def test_substitution_and_normalization_policy_binding(self):
        with duckdb.connect(str(self.f.db)) as con:
            con.execute("UPDATE catalog.catalog.files SET original_dataset='SUMMARY',substituted_dataset='MINI'")
        a=self.adapter();r=a.read(self.f.request()).receipt
        self.assertTrue(all(e.partition.original_dataset=='SUMMARY' and e.partition.substituted_dataset=='MINI' for e in r.files))
        other=DuckDBHistoricalAdapter(replace(a.config,mapping=replace(a.config.mapping,interpretation='binary64_exact'))).read(self.f.request()).receipt
        self.assertNotEqual(r.configuration_digest,other.configuration_digest)
        self.assertNotEqual(r.normalization.digest,other.normalization.digest)
        self.assertNotEqual(r.identity_digest,other.identity_digest)


if __name__=='__main__':unittest.main()
