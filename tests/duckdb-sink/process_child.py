"""Controlled real SQL boundaries in a test-owned child and synthetic output."""
import argparse
import dataclasses
import json
from pathlib import Path
import platform
import sys

from equity_feature_factory_fixture.publication_facts import synthetic_results
from equity_feature_io_contracts.publication import CompletionReceipt,SinkError
from equity_feature_io_sdk.codec import encode_receipt,idempotency_key
from equity_feature_io_sdk.publication import prepare_publication
from equity_feature_duckdb_sink import DuckDBSink
from equity_feature_duckdb_sink.sink import DEFAULT_LIMITS

parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=('reservation','partial','components','before_manifest','after_manifest','publish','source_wal'))
parser.add_argument('root',type=Path);parser.add_argument('checkpoint',type=Path)
parser.add_argument('--different',action='store_true');args=parser.parse_args()
facts=list(synthetic_results())
if args.different:
    facts[1]=dataclasses.replace(facts[1],values=(dataclasses.replace(facts[1].values[0],values=(-(2**63)+1,)),))
facts=tuple(facts)
envelope=prepare_publication(facts,destination_scope='synthetic-process',generation_id='generation',job_id='job',partition_id='partition',limits=DEFAULT_LIMITS)


def pause(session):
    args.checkpoint.write_text(json.dumps(dict(phase=args.phase,key=idempotency_key(envelope.identity),
        attempt_id=session.attempt_id,python=platform.python_version(),system=platform.system())),encoding='utf-8')
    sys.stdin.read(1)


class Observer:
    def __init__(self,connection,session):self.connection=connection;self.session=session
    def execute(self,query,*parameters):
        if query=='COMMIT' and args.phase=='before_manifest':pause(self.session)
        result=self.connection.execute(query,*parameters)
        if query.startswith('INSERT INTO efio_results') and args.phase=='partial':pause(self.session)
        if query=='COMMIT' and args.phase=='after_manifest':pause(self.session)
        return result
    def executemany(self,*arguments):return self.connection.executemany(*arguments)
    def fetchall(self):return self.connection.fetchall()
    def close(self):return self.connection.close()


try:
    if args.phase=='source_wal':
        from equity_feature_duckdb_sink.schema import connect
        connection=connect(str(args.root))
        connection.execute('CREATE TABLE source_data(id BIGINT)')
        connection.execute('INSERT INTO source_data VALUES (1)')
        args.checkpoint.write_text(json.dumps(dict(phase='source_wal')),encoding='utf-8')
        sys.stdin.read(1)
        connection.close()
        sys.exit(0)
    with DuckDBSink(args.root,'synthetic-process',caller_committed_at_ns=17) as sink:
        session=sink.begin(envelope)
        if isinstance(session,CompletionReceipt):
            print(json.dumps(dict(outcome='committed',receipt=encode_receipt(session).decode('ascii'))),flush=True)
            sys.exit(0)
        if args.phase=='reservation':pause(session)
        session.data=Observer(session.data,session)
        for ordinal,result in enumerate(facts):sink.write(session,ordinal,result)
        if args.phase=='components':pause(session)
        receipt=sink.commit(session)
        print(json.dumps(dict(outcome='committed',receipt=encode_receipt(receipt).decode('ascii'))),flush=True)
except SinkError as error:
    print(json.dumps(dict(outcome=error.code.value)),flush=True)
