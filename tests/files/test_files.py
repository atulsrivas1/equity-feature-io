"""Owned literal vectors, genuine formats and independent admission adversaries."""
from dataclasses import replace
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from equity_feature_acquisition import (AcquisitionLimits, CachePolicy, DownloadApproval,
                                       ImmutableCache, RetentionApproval)
from equity_feature_contracts import (AvailabilitySpec, Coverage, DataKind, InputScope,
                                     PriceUnit, SourceBinding)
from equity_feature_contracts.adapters import AcquisitionRequest, SourceError, SourceErrorCode, validate_delivery
from equity_feature_files import DBNAnnotation, DBNIdentity, FileProfile, LocalFileFactory, LocalFileTradeAdapter, ReadPolicy
from equity_feature_io_contracts import FactoryError
from equity_feature_io_sdk.factories import SourceRegistry

BASE = 1700000000000000000
FIELDS = ("instrument_id", "session_id", "event_ns", "order_key", "event_id", "eligible", "price", "size", "known_at_ns")
GOLD = json.loads((Path(__file__).resolve().parents[1]/"file_goldens.json").read_text())
ROWS = list(zip(*(GOLD[name] for name in FIELDS), strict=True))


def encoded(format, rows=ROWS, *, compression="NONE", schema="trades", ts_out=False):
    if format == "csv":
        output = io.StringIO(newline=""); writer = csv.writer(output)
        writer.writerow(FIELDS)
        for row in rows:
            writer.writerow([int(value) if type(value) is bool else value for value in row])
        return output.getvalue().encode()
    if format == "parquet":
        import pyarrow as pa
        import pyarrow.parquet as pq
        types = [pa.string(), pa.string(), pa.int64(), pa.int64(), pa.string(), pa.bool_(), pa.int64(), pa.int64(), pa.int64()]
        table = pa.Table.from_arrays([pa.array([r[i] for r in rows], type=t) for i,t in enumerate(types)], names=FIELDS)
        output = io.BytesIO(); pq.write_table(table, output, compression=compression, row_group_size=2)
        return output.getvalue()
    import databento_dbn as d
    meta = d.Metadata("SYNTH", BASE, d.SType.INSTRUMENT_ID, d.SType.INSTRUMENT_ID,
                      d.Schema.TRADES if schema == "trades" else d.Schema.MBP_1,
                      symbols=["1"], end=BASE+10, version=3, ts_out=ts_out)
    data = bytes(meta)
    for i,row in enumerate(rows):
        data += bytes(d.TradeMsg(1, 1, row[2], row[6], row[7], d.Action.TRADE, d.Side.BID,
                                0, row[2]+5, sequence=7+i))
    return data


class Cancel:
    def __init__(self): self.value=False
    def is_cancelled(self): return self.value


class Credentials:
    def get(self, name): raise AssertionError("Credential lookup forbidden")


class Files(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.clock = 10; self.cancel = Cancel(); self.approvals = 0

    def tearDown(self): self.temp.cleanup()

    def request(self, **changes):
        return replace(AcquisitionRequest("owned-request", DataKind.TRADE, "owned-fixture", ("A",), ("S",),
                        BASE, BASE+10, "immutable-owned-v1", PriceUnit(9,"USD"),
                        AvailabilitySpec(BASE+10, BASE+10, BASE+10), max_batch_rows=3), **changes)

    def profile(self, format, data, rows=ROWS):
        return FileProfile(format, "owned-fixture", SourceBinding("owned-local", "immutable-owned-v1", "mapping-v1", "fixture"),
            PriceUnit(9,"USD"), Coverage(len(rows),len(rows),True), InputScope(BASE,BASE+10,"owned-file-v1"),
            hashlib.sha256(data).hexdigest(), schema="dbn3-trades" if format=="dbn" else "normalized-trade-v1",
            dbn_dataset="SYNTH" if format=="dbn" else None,
            dbn_identities=(DBNIdentity(1,1,"A"),) if format=="dbn" else (),
            dbn_annotations=tuple(DBNAnnotation(r[1],r[5],r[8]) for r in rows) if format=="dbn" else ())

    def approve(self, scope):
        self.approvals += 1
        return DownloadApproval(scope, "owned-local-use", 1000000,
                    AcquisitionLimits(1,scope.request.max_rows,1000000,1000000))

    def adapter(self, format="csv", rows=ROWS, *, data=None, profile=None, **kwargs):
        data = encoded(format,rows) if data is None else data
        file = self.root/(format+"-private-sentinel")
        file.write_bytes(data)
        profile = self.profile(format,data,rows) if profile is None else profile
        return LocalFileTradeAdapter(str(file),profile,approve=kwargs.pop("approve",self.approve),
                                     clock_ns=lambda:self.clock,**kwargs)

    def deliver(self, adapter, request=None):
        request = request or self.request()
        result = tuple(adapter.iter_batches(request,self.cancel))
        validate_delivery(request,adapter.capabilities(),result)
        return result

    def error(self, code, callback):
        with self.assertRaises(SourceError) as caught: callback()
        error=caught.exception
        self.assertEqual(error.code,code)
        self.assertNotIn("private-sentinel",str(error))
        self.assertIsNone(error.__cause__); self.assertIsNone(error.__context__)

    def test_all_formats_exact_literal_projection(self):
        for format in ("csv","parquet","dbn"):
            with self.subTest(format=format):
                adapter=self.adapter(format); result=self.deliver(adapter); batch=result[0].batch
                for name in FIELDS:
                    expected=tuple(GOLD[name])
                    if format=="dbn" and name=="event_id":
                        expected=tuple("dbn:"+hashlib.sha256(encoded("dbn")).hexdigest()+":"+str(i) for i in (1,2,3))
                    self.assertEqual(batch.column(name).values,expected)
                self.assertEqual(result[0].source_coverage,Coverage(3,3,True))
                self.assertEqual(batch.metadata.price_unit,PriceUnit(9,"USD"))
                self.assertEqual(batch.metadata.scope,InputScope(BASE,BASE+10,"owned-file-v1"))

    def test_physical_dbn_metadata_independent(self):
        import databento_dbn as d
        raw=encoded("dbn"); decoder=d.DBNDecoder(upgrade_policy=d.VersionUpgradePolicy.AS_IS)
        decoder.write(raw); actual=decoder.decode()
        self.assertEqual((actual[0].version,actual[0].dataset,actual[0].schema),(3,"SYNTH","trades"))
        self.assertEqual([v.sequence for v in actual[1:]],[7,8,9])
        self.assertEqual([v.ts_event for v in actual[1:]],GOLD["event_ns"])
        self.assertEqual([v.price for v in actual[1:]],GOLD["price"])

    def test_physical_parquet_cells_independent(self):
        import pyarrow.parquet as pq
        table=pq.read_table(io.BytesIO(encoded("parquet")))
        self.assertEqual(table.to_pydict(),{name:GOLD[name] for name in FIELDS})

    def test_chunks_preserve_source_and_knowledge(self):
        batches=self.deliver(self.adapter(),self.request(max_batch_rows=2))
        self.assertEqual([b.batch.row_count for b in batches],[2,1])
        self.assertEqual([b.final for b in batches],[False,True])
        self.assertEqual([b.source_coverage.observed for b in batches],[3,3])
        self.assertEqual(batches[0].batch.column("known_at_ns").values,(BASE+1,None))
        self.assertEqual(batches[1].batch.column("known_at_ns").values,(BASE+999,))
        self.assertNotEqual(batches[0].source.input_id,batches[1].source.input_id)

    def test_half_open_selection(self):
        batch=self.deliver(self.adapter(),self.request(end_ns=BASE+3))[0]
        self.assertEqual(batch.batch.column("event_id").values,("owned-e1","owned-e2"))
        self.assertEqual(batch.source_coverage,Coverage(3,3,True))
        self.assertEqual(batch.delivery_coverage,Coverage(2,2,True))

    def test_unselected_invalid_rows_still_rejected(self):
        rows=ROWS.copy(); rows[2]=(*rows[2][:6],0,*rows[2][7:])
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(rows=rows),self.request(end_ns=BASE+3)))

    def test_empty_observed_all_formats(self):
        for format in ("csv","parquet","dbn"):
            batch=self.deliver(self.adapter(format,[]))[0]
            self.assertEqual(batch.disposition,"observed"); self.assertEqual(batch.batch.row_count,0)
            self.assertEqual(batch.source_coverage,Coverage(0,0,True))

    def test_missing_unavailable(self):
        data=encoded("csv"); profile=self.profile("csv",data)
        adapter=LocalFileTradeAdapter(str(self.root/"absent-private-sentinel"),profile,approve=self.approve,clock_ns=lambda:self.clock)
        self.error(SourceErrorCode.UNAVAILABLE,lambda:self.deliver(adapter))

    def test_malformed_csv_not_empty(self):
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter(data=b"")))
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(data=b"\xff")))

    def test_fractional_or_scientific_size(self):
        for value in ("1.5","1e2","+1"," 1"):
            rows=ROWS.copy(); rows[1]=(*rows[1][:7],value,rows[1][8])
            self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(rows=rows)))

    def test_signed_overflow(self):
        rows=ROWS.copy(); rows[1]=(*rows[1][:2],2**63,*rows[1][3:])
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(rows=rows)))

    def test_order_duplicate_and_scope(self):
        for index,value in ((2,BASE),(4,"owned-e1"),(2,BASE+10)):
            rows=ROWS.copy(); row=list(rows[1]); row[index]=value; rows[1]=tuple(row)
            self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(rows=rows)))

    def test_total_tie_order_required(self):
        rows=ROWS.copy(); row=list(rows[1]); row[3]=1; rows[1]=tuple(row)
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(rows=rows)))

    def test_schema_columns(self):
        raw=encoded("csv").replace(b"event_id",b"other_id")
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter(data=raw)))

    def test_revision_mismatch(self):
        raw=encoded("csv"); profile=self.profile("csv",raw)
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(data=raw+b"x",profile=profile)))

    def test_source_count_mismatch(self):
        raw=encoded("csv"); profile=replace(self.profile("csv",raw),coverage=Coverage(4,4,True))
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(profile=profile)))

    def test_incomplete_coverage_not_repaired(self):
        raw=encoded("csv"); profile=replace(self.profile("csv",raw),coverage=Coverage(None,3,False))
        self.assertEqual(self.deliver(self.adapter(profile=profile))[0].source_coverage,Coverage(None,3,False))

    def test_unsupported_before_open(self):
        adapter=self.adapter()
        with patch.object(Path,"open",side_effect=AssertionError("must not open")):
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(adapter,self.request(snapshot_id="different")))
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(adapter,self.request(kind=DataKind.QUOTE,sampling="continuous")))

    def test_denied_before_open(self):
        adapter=self.adapter(approve=lambda _:None)
        with patch.object(Path,"open",side_effect=AssertionError("must not open")):
            self.error(SourceErrorCode.ENTITLEMENT,lambda:self.deliver(adapter))

    def test_approval_exact_scope(self):
        adapter=self.adapter(approve=lambda s:self.approve(replace(s,mapping_revision="other")))
        self.error(SourceErrorCode.ENTITLEMENT,lambda:self.deliver(adapter))

    def test_bad_callback_secret_redacted(self):
        def broken(scope): raise ValueError("private-sentinel")
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter(approve=broken)))

    def test_raw_byte_limit(self):
        policy=ReadPolicy(max_bytes=100,max_metadata_bytes=80,read_chunk_bytes=10)
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=policy)))

    def test_input_row_limit(self):
        self.error(SourceErrorCode.LIMIT,lambda:self.adapter(policy=ReadPolicy(max_input_rows=2)))

    def test_decoded_byte_limit(self):
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=ReadPolicy(max_decoded_bytes=20))))

    def test_output_limits(self):
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(),self.request(max_rows=2,max_batch_rows=2)))
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(),self.request(max_batch_rows=1,max_batches=2)))

    def test_cancel_before_open_and_after_prefix(self):
        adapter=self.adapter(); self.cancel.value=True
        self.error(SourceErrorCode.CANCELLED,lambda:self.deliver(adapter))
        self.cancel.value=False; iterator=adapter.iter_batches(self.request(max_batch_rows=2),self.cancel)
        first=next(iterator); self.assertFalse(first.final); self.cancel.value=True
        self.error(SourceErrorCode.CANCELLED,lambda:next(iterator))

    def test_elapsed_expiry_during_read(self):
        def approve(scope):
            result=self.approve(scope); self.clock=1000001; return result
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(approve=approve)))

    def test_uri_and_unc_rejected(self):
        raw=encoded("csv"); profile=self.profile("csv",raw)
        for path in ("https://host/a","s3://bucket/a","//host/a",chr(92)*2+"host/a"):
            self.error(SourceErrorCode.UNSUPPORTED,lambda:LocalFileTradeAdapter(path,profile,approve=self.approve))

    def test_factory_existing_registry_no_credentials(self):
        raw=encoded("csv"); profile=self.profile("csv",raw); path=self.root/"factory.csv";path.write_bytes(raw)
        registry=SourceRegistry(); factory=LocalFileFactory(profile,approve=self.approve,clock_ns=lambda:self.clock)
        registry.register("owned-files",factory)
        adapter=registry.resolve("owned-files",{"path":str(path)},Credentials(),self.request())
        self.assertEqual(self.deliver(adapter)[0].batch.row_count,3)
        with self.assertRaises(FactoryError): factory.validate_config({"path":str(path),"other":True})
        self.assertNotIn(str(path),repr(factory)); self.assertNotIn(str(path),repr(adapter))

    def test_cache_hit_requires_retention_not_new_read(self):
        cache=ImmutableCache(clock_ns=lambda:self.clock,policy=CachePolicy(2,10000,1000))
        retain=lambda s:RetentionApproval(s,"owned-retention",10000,True)
        adapter=self.adapter(cache=cache,retain=retain); first=self.deliver(adapter)
        with patch.object(Path,"open",side_effect=AssertionError("cache must avoid file read")):
            second=self.deliver(adapter)
        self.assertEqual(first,second); self.assertEqual(self.approvals,1)

    def test_cache_profile_changed_annotations(self):
        cache=ImmutableCache(clock_ns=lambda:self.clock,policy=CachePolicy(2,10000,1000))
        retain=lambda s:RetentionApproval(s,"owned-retention",10000,True)
        raw=encoded("dbn"); profile=self.profile("dbn",raw)
        first=self.deliver(self.adapter("dbn",cache=cache,retain=retain))
        changed=replace(profile,dbn_annotations=(DBNAnnotation("S",True,BASE+1),)*3)
        second=self.deliver(self.adapter("dbn",profile=changed,cache=cache,retain=retain))
        self.assertNotEqual(first[0].source,second[0].source); self.assertEqual(self.approvals,2)

    def test_cache_expired_permission(self):
        cache=ImmutableCache(clock_ns=lambda:self.clock,policy=CachePolicy(2,10000,1000))
        retain=lambda s:RetentionApproval(s,"owned-retention",20,True)
        adapter=self.adapter(cache=cache,retain=retain); self.deliver(adapter); self.clock=21
        self.error(SourceErrorCode.ENTITLEMENT,lambda:self.deliver(adapter)); self.assertEqual(cache.entry_count,0)

    def test_dbn_mapping_missing(self):
        raw=encoded("dbn"); profile=replace(self.profile("dbn",raw),dbn_identities=())
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter("dbn",profile=profile)))

    def test_dbn_wrong_schema_and_truncated(self):
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter("dbn",data=encoded("dbn",schema="mbp"))))
        self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter("dbn",data=encoded("dbn")[:-1])))

    def test_dbn_unsigned_and_undefined(self):
        for index,value in ((2,2**63),(6,2**63-1),(7,2**32-1)):
            rows=ROWS.copy(); row=list(rows[0]);row[index]=value;rows[0]=tuple(row)
            self.error(SourceErrorCode.SCHEMA,lambda:self.deliver(self.adapter("dbn",rows=rows)))

    def test_csv_header_metadata_bound(self):
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter(policy=ReadPolicy(max_metadata_bytes=20))))

    def test_dbn_metadata_bound(self):
        policy=ReadPolicy(max_metadata_bytes=20)
        self.error(SourceErrorCode.LIMIT,lambda:self.deliver(self.adapter("dbn",policy=policy)))

    def test_parquet_compression_unsupported(self):
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter("parquet",data=encoded("parquet",compression="snappy"))))

    def test_parquet_wrong_type(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        table=pq.read_table(io.BytesIO(encoded("parquet")));table=table.set_column(7,"size",pa.array([2.0,1.0,3.0]))
        buffer=io.BytesIO();pq.write_table(table,buffer,compression="NONE")
        self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(self.adapter("parquet",data=buffer.getvalue())))

    def test_default_no_optional_import(self):
        with patch("equity_feature_files.codecs.import_module",side_effect=AssertionError("no optional import")):
            self.assertEqual(self.deliver(self.adapter())[0].batch.row_count,3)

    def test_missing_codec_before_open(self):
        adapter=self.adapter("parquet")
        with patch("equity_feature_files.codecs.version",side_effect=ModuleNotFoundError()), patch.object(Path,"open",side_effect=AssertionError("no read")):
            self.error(SourceErrorCode.UNSUPPORTED,lambda:self.deliver(adapter))

    def test_actual_pure_consumer_all_formats(self):
        from equity_feature_contracts import ConfigSpec, EntityKey, Parameter, SessionSpec, WindowSpec
        from equity_features.session import compute_trades
        config=ConfigSpec("owned-files-golden","v1",(Parameter("eligibility_policy","owned-file-v1"),),
            SessionSpec("owned-fixture","S",BASE,BASE+10,"supplied"),WindowSpec(1,"S",("S",)),
            AvailabilitySpec(BASE+10,BASE+10,BASE+10,mode="reconstruction",reconstruction_reason="owned-replay"),
            price_unit=PriceUnit(9,"USD"))
        for format in ("csv","parquet","dbn"):
            batch=self.deliver(self.adapter(format))[0].batch
            result=compute_trades(batch,config,entity=EntityKey("A","S"))
            values={c.feature_id.rsplit(".",1)[1]:c.values[0] for c in result.values}
            self.assertEqual(values["count"],3);self.assertEqual(values["volume"],6)
            self.assertEqual(values["notional"],13000000000);self.assertEqual(values["mean_size"],2)
            self.assertAlmostEqual(values["vwap"],13/6,delta=1e-12)
            causal=compute_trades(batch,replace(config,availability=AvailabilitySpec(BASE+10,BASE+10,BASE+10)),entity=EntityKey("A","S"))
            self.assertTrue(all(c.values[0] is None for c in causal.values))

    def test_profile_identity_same_bytes_changed_coverage(self):
        raw=encoded("csv"); profile=self.profile("csv",raw)
        original=self.deliver(self.adapter(profile=profile))[0].source
        changed=self.deliver(self.adapter(profile=replace(profile,coverage=Coverage(None,3,False))))[0].source
        self.assertNotEqual(original.mapping_version,changed.mapping_version)
        self.assertNotEqual(original.input_id,changed.input_id)


if __name__ == "__main__": unittest.main()
