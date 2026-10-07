"""Compare a7/a8 installed readers against the very same synthetic files."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/duckdb'))
from test_reader import ReaderTests
import equity_feature_duckdb
from equity_feature_contracts.adapters import SourceError


def probe(root):
    assert 'site-packages' in Path(equity_feature_duckdb.__file__).parts
    fixture = ReaderTests()
    fixture.root = root
    fixture.db = root / 'catalog.duckdb'
    fixture.parts = sorted(root.glob('original-*.parquet'))
    fixture.schema = 'trades'
    adapter = fixture.adapter()
    result = adapter.read(fixture.request())
    metrics = {key: value for key, value in asdict(result.metrics).items() if not key.endswith('_ns')}
    errors = []
    for request in (fixture.request(max_rows=2), fixture.request(max_batches=1)):
        try:
            adapter.read(request)
        except SourceError as error:
            errors.append(dict(code=error.code.value, message=str(error)))
        else:
            raise AssertionError('Bounded acquisition unexpectedly succeeded')
    return dict(version=equity_feature_duckdb.__version__, canonical=asdict(result.canonical), batches=[asdict(b) for b in result.batches],
                mapping=asdict(result.mapping_report), receipt=asdict(result.receipt), receipt_digest=result.receipt.identity_digest,
                metrics=metrics, errors=errors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', type=Path)
    parser.add_argument('--old-python', type=Path)
    parser.add_argument('--new-python', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(probe(args.probe), sort_keys=True))
        return
    assert args.old_python and args.new_python and args.output
    fixture = ReaderTests()
    fixture.setUp()
    try:
        observed = []
        for python in (args.old_python, args.new_python):
            observed.append(json.loads(subprocess.check_output([str(python), '-I', str(Path(__file__).resolve()), '--probe', str(fixture.root)], text=True)))
        old, new = observed
        assert (old.pop('version'), new.pop('version')) == ('0.1.0a7', '0.1.0a8')
        assert (old['receipt'].pop('adapter_version'), new['receipt'].pop('adapter_version')) == ('0.1.0a7', '0.1.0a8')
        assert old.pop('receipt_digest') != new.pop('receipt_digest')
        assert old == new, 'Undeclared canonical/provenance/error difference'
        payload = json.dumps(new, sort_keys=True).encode()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(schema='extraction-compatibility1', old='0.1.0a7', new='0.1.0a8',
            same_files=True, canonical_batches_mapping_receipt_fields_metrics_errors_equal=True,
            declared_exclusions=['package_version', 'receipt.adapter_version', 'receipt.identity_digest'],
            common_observation_sha256=hashlib.sha256(payload).hexdigest(), synthetic=True), sort_keys=True, indent=2) + '\n')
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
