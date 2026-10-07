"""Actual synthetic DuckDB/Parquet SDK qualification; no private source access."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import TypedDict, Unpack, cast

import duckdb
import numpy
import equity_feature_contracts as contracts_package
import equity_feature_duckdb as adapter_package
import equity_features as features_package
from equity_feature_contracts import (
    AvailabilitySpec, CanonicalBatch, ConfigSpec, Coverage, DataKind, EntityKey, FeatureResult,
    InputScope, Parameter, PriceUnit, SessionSpec, SourceBinding, Status, WindowSpec,
)
from equity_feature_contracts.adapter_kit import ConformanceCase, run_conformance
from equity_feature_contracts.adapters import AcquisitionRequest, AdapterBatch, SourceError, SourceErrorCode
from equity_feature_duckdb import (
    CatalogConfig, CoverageAssertion, DuckDBHistoricalAdapter, FilePin, GovernedCalendar,
    MappingPolicy, ReadConfig, SourceSelection, VerificationPolicy, make_history_context, resolve_source,
)
from equity_features.history import compute_history
from equity_features.session import compute_bars, compute_trades

ROOT = Path(__file__).resolve().parents[1]
UNIT = PriceUnit(2, "USD")
MINUTE = 60 * 10**9
DAY = 86400 * 10**9


class RequestChanges(TypedDict, total=False):
    start_ns: int
    end_ns: int
    max_rows: int
    max_batches: int
    snapshot_id: str
    namespace: str
    price_unit: PriceUnit
    instruments: tuple[str, ...]
    sessions: tuple[str, ...]
    sampling: str


def values(batch: CanonicalBatch, name: str) -> tuple[object, ...]:
    column = batch.column(name)
    assert column is not None
    return column.values


class Cancel:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


class Fixture:
    """Hand-authored source populations, separate from expected calculations."""
    def __init__(self, root: Path, schema: str = "trades", *, known: str = "1",
                 eligible: bool = True, layer: str = "prepared", price: int = 100) -> None:
        root.mkdir(parents=True)
        self.root, self.schema, self.layer = root, schema, layer
        self.db = root / "catalog.duckdb"
        self.snapshot = "synthetic-" + layer + "1"
        count = 3 if schema == "ohlcv-1d" else 1
        duration = DAY if count == 3 else 2*MINUTE if schema == "ohlcv-1m" else 4
        self.sessions = tuple(SessionSpec("sdk", f"S{i+1}", i*duration, (i+1)*duration, "UTC") for i in range(count))
        self.dates = tuple((date(1970, 1, 1)+timedelta(days=i)).isoformat() for i in range(count))
        self.files: list[Path] = []
        with duckdb.connect(str(self.db)) as con:
            con.execute("CREATE SCHEMA catalog")
            con.execute("CREATE TABLE catalog.catalog.datasets(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,view_schema VARCHAR,view_name VARCHAR)")
            con.execute("CREATE TABLE catalog.catalog.files(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,session_date DATE,path VARCHAR,bytes BIGINT,rows BIGINT,provenance VARCHAR,original_dataset VARCHAR,substituted_dataset VARCHAR,column_signature VARCHAR,optimized_path VARCHAR,optimized_bytes BIGINT,view_schema VARCHAR,view_name VARCHAR)")
            con.execute("INSERT INTO catalog.catalog.datasets VALUES (?,?, 'FICTION',?,'synthetic1','source1')", [layer,self.snapshot,schema])
            for i, session_date in enumerate(self.dates):
                if schema == "trades":
                    projection = ",true eligible" if eligible else ""
                    query = ("SELECT instrument_id,ts_utc,price::DOUBLE price,size,"+known+"::BIGINT known_at_ns"+projection+
                        " FROM (VALUES (7,'1970-01-01T00:00:00.000000001Z',"+str(price)+",2),"
                        "(7,'1970-01-01T00:00:00.000000002Z',"+str(price+2)+",3),"
                        "(7,'1970-01-01T00:00:00.000000002Z',"+str(price+2)+",3)) t(instrument_id,ts_utc,price,size)")
                    rows = 3
                elif schema == "tbbo":
                    query = "SELECT 7 instrument_id,'1970-01-01T00:00:00.000000001Z' ts_utc,10.0::DOUBLE bid,12.0::DOUBLE ask,2 bid_size,3 ask_size,1::BIGINT known_at_ns"
                    rows = 1
                elif schema == "ohlcv-1m":
                    query = ("SELECT 7 instrument_id,ts_utc,o::DOUBLE open,h::DOUBLE high,l::DOUBLE low,c::DOUBLE \"close\",v::UBIGINT volume,1::BIGINT known_at_ns "
                        "FROM (VALUES ('1970-01-01T00:00:00Z',10,12,9,11,3),('1970-01-01T00:01:00Z',11,14,10,12,5)) t(ts_utc,o,h,l,c,v)")
                    rows = 2
                else:
                    value = 10*(i+1)
                    query = (f"SELECT 7 instrument_id,'{session_date}T00:00:00Z' ts_utc,{value}.0::DOUBLE open,{value}.0::DOUBLE high,"
                        f"{value}.0::DOUBLE low,{value}.0::DOUBLE \"close\",5::UBIGINT volume,1::BIGINT known_at_ns")
                    rows = 1
                original, optimized = root/f"original-{i}.parquet", root/f"optimized-{i}.parquet"
                con.execute("COPY ("+query+") TO ? (FORMAT PARQUET)",[str(original)])
                shutil.copyfile(original, optimized)
                con.execute("INSERT INTO catalog.catalog.files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",[
                    layer,self.snapshot,"FICTION",schema,session_date,str(original),original.stat().st_size,rows,
                    "synthetic_caller_assertion","FICTION",None,"synthetic-schema1",str(optimized),optimized.stat().st_size,"synthetic1","source1"])
                self.files.append(original)

    def request(self, **kwargs: Unpack[RequestChanges]) -> AcquisitionRequest:
        kind = {"trades":DataKind.TRADE,"tbbo":DataKind.QUOTE,"ohlcv-1m":DataKind.BAR,"ohlcv-1d":DataKind.DAILY}[self.schema]
        end = self.sessions[-1].close_ns
        request = AcquisitionRequest("synthetic",kind,"sdk",("A",),tuple(s.session_id for s in self.sessions),0,end,
            self.snapshot,UNIT,AvailabilitySpec(end,end,end),sampling="trade_snapshot" if kind == DataKind.QUOTE else "none",
            max_batch_rows=2,max_rows=10,max_batches=10,selection="completed_intervals" if kind in (DataKind.BAR,DataKind.DAILY) else "event_half_open")
        return replace(request, **kwargs)

    def adapter(self, *, complete: int | None = None, pins: tuple[FilePin, ...] = (),
                verification: VerificationPolicy = VerificationPolicy()) -> DuckDBHistoricalAdapter:
        resolved = resolve_source(CatalogConfig(self.db),SourceSelection(self.layer,self.snapshot,"FICTION",self.schema,self.dates),pins=pins)
        is_trade = self.schema == "trades"
        mapping = MappingPolicy(self.schema,UNIT,"binary64_exact","exact",((7,"A"),),
            "event" if self.schema in ("trades","tbbo") else "receive_aggregation","synthetic1" if is_trade else None)
        end = self.sessions[-1].close_ns
        claim = CoverageAssertion(("A",),tuple(s.session_id for s in self.sessions),0,end,complete,"fictional-count1") if complete is not None else None
        return DuckDBHistoricalAdapter(ReadConfig(self.db,resolved,mapping,"sdk","synthetic","supplied-grid1",self.sessions,
            tuple(zip(self.dates,(s.session_id for s in self.sessions))),InputScope(0,end,"synthetic1"),claim,verification=verification))


def _numeric(result: FeatureResult, expected: dict[str, tuple[object, Status]],
             source: SourceBinding, label: str) -> list[dict[str, object]]:
    columns = {c.feature_id:c for c in result.values}
    quality = {q.feature_id:q for q in result.quality}
    assert any(binding.metadata.source == source for binding in result.metadata.inputs)
    assert all(binding.metadata.price_unit == UNIT for binding in result.metadata.inputs if binding.metadata.source == source)
    units = {
        "session.trade.count":"trades", "session.trade.volume":"shares",
        "session.trade.notional":"currency coefficient / 10^price_scale",
        "session.trade.vwap":"currency/share", "session.trade.mean_size":"shares/trade",
        "session.bar.open":"currency/share", "session.bar.high":"currency/share",
        "session.bar.low":"currency/share", "session.bar.close":"currency/share",
        "session.bar.volume":"shares", "session.bar.close_weighted_price":"currency/share; proxy",
        "session.bar.notional":"currency coefficient / 10^price_scale",
        "history.sma":"USD/share", "history.ema":"USD/share",
    }
    output: list[dict[str, object]] = []
    for name,(value,status) in expected.items():
        observed = columns[name].values[0]
        if type(value) is float:
            assert type(observed) is float and math.isclose(observed,value,rel_tol=1e-12,abs_tol=1e-12)
        else:
            assert observed == value
        assert quality[name].status == status
        assert columns[name].unit == units[name]
        output.append(dict(case=label,feature=name,expected=value,observed=observed,unit=columns[name].unit,
            expected_unit=units[name],expected_status=status.value,observed_status=quality[name].status.value,source_binding_parity=True))
    return output


def run_suite(*, require_installed: bool = False) -> dict[str, object]:
    installed = all("site-packages" in Path(cast(str,m.__file__)).parts for m in
        (contracts_package,features_package,adapter_package,duckdb,numpy))
    if require_installed and not installed:
        raise RuntimeError("Actual installed public package locations required")
    cases: list[ConformanceCase] = []
    stages: dict[str,str] = {}
    numerical: list[dict[str,object]] = []
    def collect(name: str, adapter: DuckDBHistoricalAdapter, request: AcquisitionRequest,
                expected: SourceErrorCode | None = None, cancel: Cancel | None = None) -> tuple[AdapterBatch,...]:
        captured = None
        try:
            batches = tuple(adapter.iter_batches(request,cancel or Cancel()))
        except SourceError as error:
            captured, batches = error.code, ()
        cases.append(ConformanceCase(name,request,adapter.capabilities(),batches,expected,captured))
        stages[name] = "actual acquisition"
        return batches
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        trades = Fixture(root/"trades");adapter=trades.adapter(complete=3);request=trades.request()
        delivered=collect("trades-valid",adapter,request)
        actual=adapter.read(request);assert actual.canonical is not None and actual.receipt is not None
        assert tuple(v for e in delivered if e.batch is not None for v in values(e.batch,"event_id")) == values(actual.canonical,"event_id")
        assert values(actual.canonical,"price") == (10000,10200,10200)
        assert len(set(values(actual.canonical,"event_id"))) == 3
        cfg=ConfigSpec("synthetic-trades","v1",(Parameter("eligibility_policy","synthetic1"),),trades.sessions[0],
            WindowSpec(1,"S1",("S1",)),request.availability,price_unit=UNIT)
        numerical += _numeric(compute_trades(actual.canonical,cfg,entity=EntityKey("A","S1")),{
            "session.trade.count":(3,Status.AVAILABLE),"session.trade.volume":(8,Status.AVAILABLE),
            "session.trade.notional":(81200,Status.AVAILABLE),"session.trade.vwap":(101.5,Status.AVAILABLE),
            "session.trade.mean_size":(8/3,Status.AVAILABLE)},actual.canonical.metadata.source,"trades-valid")
        unclaimed=trades.adapter()
        ties=collect("one-ns-tied-occurrences",unclaimed,trades.request(start_ns=2,end_ns=3))
        assert sum(e.batch.row_count for e in ties if e.batch is not None) == 2
        empty=collect("observed-empty",unclaimed,trades.request(start_ns=3,end_ns=4))
        assert empty[0].batch is not None and empty[0].batch.row_count == 0
        for label,known in (("unknown-knowledge","NULL"),("future-knowledge","9")):
            f=Fixture(root/label,known=known);a=f.adapter(complete=3);req=f.request();collect(label,a,req)
            b=a.read(req).canonical;assert b is not None
            assert values(b,"known_at_ns") == ((None,)*3 if known=="NULL" else (9,)*3)
            numerical += _numeric(compute_trades(b,cfg,entity=EntityKey("A","S1")),
                {"session.trade.count":(None,Status.MISSING_INPUT)},b.metadata.source,label)
        variants: tuple[tuple[str,RequestChanges,SourceErrorCode],...] = (
            ("snapshot-mismatch",dict(snapshot_id="other"),SourceErrorCode.UNSUPPORTED),
            ("namespace-mismatch",dict(namespace="other"),SourceErrorCode.UNSUPPORTED),
            ("unit-mismatch",dict(price_unit=PriceUnit(0,"USD")),SourceErrorCode.UNSUPPORTED),
            ("instrument-unavailable",dict(instruments=("UNKNOWN",)),SourceErrorCode.UNAVAILABLE),
            ("session-unavailable",dict(sessions=("UNKNOWN",)),SourceErrorCode.UNAVAILABLE),
            ("row-limit",dict(max_rows=2),SourceErrorCode.LIMIT),
            ("chunk-limit",dict(max_batches=1),SourceErrorCode.LIMIT))
        for label,change,code in variants:
            collect(label,unclaimed,replace(request,**change),code)
        collect("hash-limit",trades.adapter(verification=VerificationPolicy(max_hash_bytes=1)),request,SourceErrorCode.LIMIT)
        collect("cancelled",unclaimed,request,SourceErrorCode.CANCELLED,Cancel(True))
        absent=Fixture(root/"eligibility",eligible=False)
        collect("eligibility-unavailable",absent.adapter(),absent.request(),SourceErrorCode.UNAVAILABLE)
        missing=Fixture(root/"missing")
        with duckdb.connect(str(missing.db)) as con:con.execute("DELETE FROM catalog.catalog.files")
        absent_batches=collect("partition-missing",missing.adapter(),missing.request())
        assert absent_batches[0].disposition=="missing" and absent_batches[0].batch is None
        vanished=Fixture(root/"vanished");a=vanished.adapter();vanished.files[0].unlink()
        collect("file-missing",a,vanished.request(),SourceErrorCode.UNAVAILABLE)
        stale=Fixture(root/"stale");a=stale.adapter()
        with duckdb.connect(str(stale.db)) as con:con.execute("UPDATE catalog.catalog.files SET provenance='changed'")
        collect("catalog-stale",a,stale.request(),SourceErrorCode.SCHEMA)
        pinned=Fixture(root/"pinned");file=pinned.files[0]
        a=pinned.adapter(pins=(FilePin(str(file),hashlib.sha256(file.read_bytes()).hexdigest()),))
        data=file.read_bytes();file.write_bytes(b"X"+data[1:])
        collect("pin-stale",a,pinned.request(),SourceErrorCode.SCHEMA)
        quote=Fixture(root/"quotes","tbbo");a=quote.adapter();req=quote.request()
        q=collect("tbbo-trade-snapshot",a,req);assert q[0].batch is not None
        assert values(q[0].batch,"bid")== (1000,) and values(q[0].batch,"ask")== (1200,)
        collect("tbbo-continuous-unsupported",a,replace(req,sampling="continuous"),SourceErrorCode.UNSUPPORTED)
        bars=Fixture(root/"bars","ohlcv-1m");a=bars.adapter(complete=2);req=bars.request()
        collect("minute-whole",a,req);b=a.read(req).canonical;assert b is not None
        barcfg=replace(cfg,session=bars.sessions[0],availability=req.availability)
        numerical += _numeric(compute_bars(b,barcfg,entity=EntityKey("A","S1")),{
            "session.bar.open":(10.0,Status.AVAILABLE),"session.bar.high":(14.0,Status.AVAILABLE),
            "session.bar.low":(9.0,Status.AVAILABLE),"session.bar.close":(12.0,Status.AVAILABLE),
            "session.bar.volume":(8,Status.AVAILABLE),"session.bar.close_weighted_price":(11.625,Status.AVAILABLE),
            "session.bar.notional":(None,Status.MISSING_INPUT)},b.metadata.source,"minute-whole")
        partial=collect("minute-partial-cutoff",bars.adapter(),bars.request(end_ns=2*MINUTE-1))
        assert sum(e.batch.row_count for e in partial if e.batch is not None)==1
        daily=Fixture(root/"daily","ohlcv-1d");a=daily.adapter(complete=3);req=daily.request()
        collect("daily-whole",a,req);b=a.read(req).canonical;assert b is not None
        cal=GovernedCalendar("sdk","supplied-grid1","synthetic-calendar1",tuple(zip(daily.dates,daily.sessions)),grid_kind="utc_daily_intervals")
        ctx=make_history_context(cal,EntityKey("A","S3"),b,(Coverage(1,1,True),)*3,"S1")
        hcfg=ConfigSpec("synthetic-history","v1",(Parameter("period",3),),daily.sessions[-1],
            WindowSpec(3,"S3",("S1","S2","S3"),"completed_eod"),req.availability,price_unit=UNIT)
        numerical += _numeric(compute_history(b,hcfg,context=ctx,feature_ids=("history.sma","history.ema")),
            {"history.sma":(20.0,Status.AVAILABLE),"history.ema":(20.0,Status.AVAILABLE)},b.metadata.source,"daily-whole")
        partial=collect("daily-partial-cutoff",daily.adapter(),daily.request(end_ns=3*DAY-1))
        assert sum(e.batch.row_count for e in partial if e.batch is not None)==2
        # Two overlapping routes in one actual catalog; never union them.
        overlap=Fixture(root/"overlap",price=200)
        with duckdb.connect(str(overlap.db)) as con:
            con.execute("INSERT INTO catalog.catalog.datasets SELECT 'curated','synthetic-curated1',dataset,source_schema,view_schema,view_name FROM catalog.catalog.datasets")
            con.execute("INSERT INTO catalog.catalog.files SELECT 'curated','synthetic-curated1',dataset,source_schema,session_date,path,bytes,rows,provenance,original_dataset,substituted_dataset,column_signature,optimized_path,optimized_bytes,view_schema,view_name FROM catalog.catalog.files")
        prepared=collect("overlap-explicit-prepared",overlap.adapter(),overlap.request())
        overlap.layer,overlap.snapshot="curated","synthetic-curated1"
        curated=collect("overlap-explicit-curated",overlap.adapter(),overlap.request())
        assert sum(e.batch.row_count for e in prepared if e.batch is not None)==3
        assert sum(e.batch.row_count for e in curated if e.batch is not None)==3
        assert prepared[0].source.snapshot_id != curated[0].source.snapshot_id
        bad_coverage=Coverage(4,4,True)
        first=delivered[0]
        changed_coverage=(replace(first,source_coverage=bad_coverage,
            batch=replace(cast(CanonicalBatch,first.batch),metadata=replace(cast(CanonicalBatch,first.batch).metadata,coverage=bad_coverage))),*delivered[1:])
        for name,batches in (
            ("sdk-reject-ordinal",(replace(delivered[0],ordinal=1),*delivered[1:])),
            ("sdk-reject-final",(*delivered[:-1],replace(delivered[-1],final=False))),
            ("sdk-reject-coverage",changed_coverage)):
            cases.append(ConformanceCase(name,request,adapter.capabilities(),batches,SourceErrorCode.SCHEMA))
            stages[name]="intentionally mutated actual delivery / SDK validation"
    assert len(cases)==30
    report=run_conformance(tuple(cases))
    assert report.passed, [(o.case_id,o.expected_error,o.observed_error) for o in report.outcomes if not o.passed]
    return dict(schema="duckdb-conformance1",fixture="synthetic-sdk1",installed_public_execution=installed,
        cases=[dict(case_id=o.case_id,expected=o.expected_error,observed=o.observed_error,passed=o.passed,stage=stages[o.case_id]) for o in report.outcomes],
        numerical=numerical,independent_numerical_unit_quality_binding_parity=True,
        runtime=dict(system=platform.system(),python=platform.python_version(),duckdb=duckdb.__version__,numpy=numpy.__version__,
            adapter=adapter_package.__version__,contracts=contracts_package.__version__,features=features_package.__version__),
        limits="Actual bounded synthetic Parquet only; caller coverage/calendar/knowledge/eligibility assertions, no provider/PIT/rights/private numerical/full-corpus/atomic snapshot certification")


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed",action="store_true")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=run_suite(require_installed=args.installed)
    report["source_commit"]=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    report["source_dirty"]=bool(subprocess.check_output(["git","status","--porcelain","--","packages/duckdb","tests/duckdb","tools/build_duckdb.py","examples/duckdb_conformance.py"],cwd=ROOT,text=True).strip())
    report["harness_sha256"]=hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest()
    report["harness_hash_encoding"]="UTF8 with normalized LF"
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes((json.dumps(report,sort_keys=True,indent=2)+"\n").encode("utf-8"))
    print("Actual DuckDB thirtycase SDK / independent numerical conformance passed")


if __name__=="__main__":main()
