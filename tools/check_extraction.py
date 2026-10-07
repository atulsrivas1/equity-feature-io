"""Verify extraction against the accepted public Git source, without imports."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--core-root', type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads((ROOT / 'docs/EQ122_EXTRACTION_INVENTORY.json').read_text())
    checked = {}
    for name, expected_hash in inventory['source_sha256_utf8_git_bytes'].items():
        original = subprocess.check_output(['git', 'show', inventory['canonical_baseline'] + ':' + name], cwd=args.core_root)
        assert hashlib.sha256(original).hexdigest() == expected_hash, name
        current = (ROOT / name).read_bytes()
        if name.startswith('packages/duckdb/src/') or name.startswith('tests/duckdb/') or name.startswith(('examples/', 'benchmarks/')):
            expected = original
            if name in inventory['allowed_runtime_differences'] or name == 'tests/duckdb/test_evidence.py':
                expected = expected.replace(b'0.1.0a7', b'0.1.0a8')
            assert current == expected, 'Undeclared source/fixture change: ' + name
            checked[name] = hashlib.sha256(current).hexdigest()
    assert len(checked) == 19, len(checked)
    print(json.dumps(dict(schema='extraction-source-check1', baseline=inventory['canonical_baseline'], checked=checked, mathematical_changes=False), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
