"""Synthetic installed reader costs, owned copies and native lifetime memory."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]


def helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'benchmarks'/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_case(rows, repetitions):
    import duckdb
    import numpy
    import equity_feature_duckdb as adapter_package
    import equity_feature_contracts as contracts_package
    from equity_feature_contracts import AvailabilitySpec, DataKind, InputScope, PriceUnit, SessionSpec
    from equity_feature_contracts.adapters import AcquisitionRequest, validate_delivery
    from equity_feature_duckdb import (CatalogConfig, CoverageAssertion, DuckDBHistoricalAdapter,
        MappingPolicy, ReadConfig, SourceSelection, resolve_source)
    assert all('site-packages' in Path(m.__file__).parts for m in (adapter_package,contracts_package)), 'actual installed packages required'
    native = helper('reader_native_peak', 'run_baseline.py')
    owned = helper('reader_owned_graph', 'resource_behavior.py')
    initial, method = native.peak_bytes()
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);db=root/'fictional.duckdb';original=root/'original.parquet';optimized=root/'optimized.parquet'
        start=perf_counter_ns()
        with duckdb.connect(str(db)) as c:
            c.execute("CREATE TEMP TABLE fixture AS SELECT 7 instrument_id,'1970-01-01T00:00:00.' || lpad(CAST(i+1 AS VARCHAR),9,'0') || 'Z' ts_utc,(100.0+i%7)::DOUBLE price,((i%5)+1)::INTEGER size FROM range(?) t(i)",[rows])
            c.execute("COPY fixture TO ? (FORMAT PARQUET)",[str(original)])
            shutil.copyfile(original,optimized)
            c.execute('CREATE SCHEMA catalog')
            c.execute('CREATE TABLE catalog.datasets(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,view_schema VARCHAR,view_name VARCHAR)')
            c.execute('CREATE TABLE catalog.files(layer VARCHAR,snapshot VARCHAR,dataset VARCHAR,source_schema VARCHAR,session_date DATE,path VARCHAR,bytes BIGINT,rows BIGINT,provenance VARCHAR,original_dataset VARCHAR,substituted_dataset VARCHAR,column_signature VARCHAR,optimized_path VARCHAR,optimized_bytes BIGINT,view_schema VARCHAR,view_name VARCHAR)')
            c.execute("INSERT INTO catalog.datasets VALUES ('prepared','frozen1','FICTION','trades','prepared1','trades1')")
            c.execute('INSERT INTO catalog.files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[
                'prepared','frozen1','FICTION','trades','1970-01-01',str(original),original.stat().st_size,rows,
                'synthetic','FICTION',None,'benchmark-source-v1',str(optimized),optimized.stat().st_size,'prepared1','trades1'])
        unit=PriceUnit(2,'USD');end=rows+1
        resolved=resolve_source(CatalogConfig(db),SourceSelection('prepared','frozen1','FICTION','trades',('1970-01-01',)))
        mapping=MappingPolicy('trades',unit,'binary64_exact','exact',((7,'A'),),'event','fixture-v1',True,max_rows=rows)
        config=ReadConfig(db,resolved,mapping,'read-benchmark','synthetic','supplied-session-v1',
            (SessionSpec('read-benchmark','S1',0,end,'UTC'),),(('1970-01-01','S1'),),InputScope(0,end,'fixture-v1'),
            CoverageAssertion(('A',),('S1',),0,end,rows,'synthetic-exact-population-v1'))
        adapter=DuckDBHistoricalAdapter(config)
        request=AcquisitionRequest('r1',DataKind.TRADE,'read-benchmark',('A',),('S1',),0,end,'frozen1',unit,
            AvailabilitySpec(end,end,end),max_batch_rows=min(256,rows),max_rows=rows,max_batches=128)
        setup_ns=perf_counter_ns()-start
        after_setup=native.peak_bytes()[0]
        expected_times=tuple(range(1,rows+1))
        expected_prices=tuple(10000+100*(i%7) for i in range(rows))
        expected_sizes=tuple((i%5)+1 for i in range(rows))
        samples=[];phase_samples=[]
        for _ in range(repetitions):
            start=perf_counter_ns();result=adapter.read(request);samples.append(perf_counter_ns()-start)
            assert result.canonical.column('event_ns').values==expected_times
            assert result.canonical.column('price').values==expected_prices
            assert result.canonical.column('size').values==expected_sizes
            assert len(set(result.canonical.column('event_id').values))==rows
            assert result.canonical.column('known_at_ns') is None
            assert result.mapping_report.price_conversions[0].rounded_cells==0
            assert result.receipt is not None and result.receipt.rows==rows
            assert result.receipt.hash_bytes==result.metrics.verification_hash_bytes>0
            assert result.metrics.verification_ns>0
            validate_delivery(request,adapter.capabilities(),result.batches)
            phase_samples.append(asdict(result.metrics))
        peak=native.peak_bytes()[0]
        logical_fixture=hashlib.sha256(json.dumps([expected_times,expected_prices,expected_sizes]).encode()).hexdigest()
        return dict(rows=rows,logical_fixture_sha256=logical_fixture,independent_population_unit_identity_parity=True,
            fixture_resolver_setup_ns=setup_ns,read_total_samples_ns=samples,read_total_median_ns=statistics.median(samples),
            phases=phase_samples,owned_canonical_and_envelopes=owned.reachable((result.canonical,result.batches)),
            native_process=dict(initial_bytes=initial,after_setup_peak_bytes=after_setup,peak_bytes=peak,method=method,
                scope='process lifetime high-water including imports/fixture/resolver/SQL/Python/canonical/chunks; not exclusive read allocations or hard cap'),
            controls=dict(threads=config.threads,memory_setting_mb=config.memory_limit_mb,batch_rows=request.max_batch_rows,
                max_rows=request.max_rows,max_batches=request.max_batches),
            runtime=dict(system=platform.system(),machine=platform.machine(),python=platform.python_version(),
                duckdb=duckdb.__version__,numpy=numpy.__version__,adapter=adapter_package.__version__,contracts=contracts_package.__version__),
            limits='supplied synthetic single-process workload, no warm/cold storage distinction; file bytes are selected lengths, not measured I/O; owned graph excludes config/wrapper/native/global code; no throughput or zero-copy target')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quick',action='store_true');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    cases=[run_case(rows,1 if args.quick else 3) for rows in ((64,) if args.quick else (512,4096))]
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain','--','packages/duckdb','tests/duckdb','tools/build_duckdb.py','benchmarks/duckdb_read.py'],cwd=ROOT,text=True).strip())
    report=dict(schema='duckdb-read-cost1',source_commit=source,measurement_source_dirty=dirty,
        harness_sha256=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        harness_hash_encoding='UTF8 with normalized LF',cases=cases,
        timing_scope='whole public read plus separate source verification, SQL-fetch, owned mapping/materialization and delivery-copy phases; setup reported separately; hashed user-space bytes are not physical storage I/O')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('Installed synthetic reader parity/cost/native-memory report recorded')


if __name__=='__main__':main()
