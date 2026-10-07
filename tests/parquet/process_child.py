"""Owned synthetic process fault probe; observers pause real storage boundaries."""
import argparse
import dataclasses
import json
from pathlib import Path
import platform
import sys

from equity_feature_factory_fixture.publication_facts import synthetic_results
from equity_feature_io_contracts import SinkRequirements
from equity_feature_io_contracts.publication import CompletionReceipt, SinkError
from equity_feature_io_sdk.codec import encode_receipt, idempotency_key
from equity_feature_io_sdk.publication import prepare_publication
from equity_feature_parquet import ParquetSink
import equity_feature_parquet.sink as backend

parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=('reservation','partial','components','before_manifest','after_manifest','publish'))
parser.add_argument('root',type=Path);parser.add_argument('checkpoint',type=Path)
parser.add_argument('--different',action='store_true');args=parser.parse_args()
facts=list(synthetic_results())
if args.different:
    facts[1]=dataclasses.replace(facts[1],values=(dataclasses.replace(facts[1].values[0],values=(-(2**63)+1,)),))
facts=tuple(facts)
limits=SinkRequirements(max_results=100,max_chunk_bytes=1048576,max_total_bytes=10485760,max_result_cells=100000,max_evidence_rows=100000)
envelope=prepare_publication(facts,destination_scope='synthetic-process',generation_id='generation',job_id='job',partition_id='partition',limits=limits)


def pause(session):
    # Marker is test-owned, outside the backend namespace. No raw path goes in reports.
    args.checkpoint.write_text(json.dumps(dict(phase=args.phase,key=idempotency_key(envelope.identity),
        attempt_id=session.attempt_id,python=platform.python_version(),system=platform.system())),encoding='utf-8')
    sys.stdin.read(1)


try:
    with ParquetSink(args.root,'synthetic-process',caller_committed_at_ns=17) as sink:
        session=sink.begin(envelope)
        if isinstance(session,CompletionReceipt):
            print(json.dumps(dict(outcome='committed',receipt=encode_receipt(session).decode('ascii'))),flush=True)
            sys.exit(0)
        if args.phase=='reservation':pause(session)
        if args.phase=='partial':
            original=backend.write_projection
            def projection_observer(*a,**kwargs):
                pause(session)
                return original(*a,**kwargs)
            backend.write_projection=projection_observer
        if args.phase in ('before_manifest','after_manifest'):
            original_control=sink._control_write
            def control_observer(path,data):
                if path.name=='complete.json' and args.phase=='before_manifest':pause(session)
                original_control(path,data)
                if path.name=='complete.json' and args.phase=='after_manifest':pause(session)
            sink._control_write=control_observer
        for ordinal,result in enumerate(facts):sink.write(session,ordinal,result)
        if args.phase=='components':pause(session)
        receipt=sink.commit(session)
        print(json.dumps(dict(outcome='committed',receipt=encode_receipt(receipt).decode('ascii'))),flush=True)
except SinkError as error:
    print(json.dumps(dict(outcome=error.code.value)),flush=True)
