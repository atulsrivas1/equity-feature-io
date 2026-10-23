"""Verify retained source plus explicitly declared EF1 additions, without imports."""
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
    evolution_path = ROOT / 'docs/EF1_SOURCE_EVOLUTION.json'
    evolution = json.loads(evolution_path.read_text(encoding='utf-8'))
    assert evolution['schema'] == 'ef1-source-evolution1'
    assert evolution['baseline_inventory'] == 'docs/EQ122_EXTRACTION_INVENTORY.json'
    assert evolution['canonical_baseline'] == inventory['canonical_baseline']
    substitutions = evolution['allowed_version_marker_substitutions']
    assert set(substitutions) == set(inventory['allowed_runtime_differences']) | {'tests/duckdb/test_evidence.py'}
    assert evolution['current_distribution_version'] == '0.1.0a9'
    checked = {}
    for name, expected_hash in inventory['source_sha256_utf8_git_bytes'].items():
        original = subprocess.check_output(['git', 'show', inventory['canonical_baseline'] + ':' + name], cwd=args.core_root)
        assert hashlib.sha256(original).hexdigest() == expected_hash, name
        current = (ROOT / name).read_bytes()
        if name.startswith('packages/duckdb/src/') or name.startswith('tests/duckdb/') or name.startswith(('examples/', 'benchmarks/')):
            expected = original
            if name in substitutions:
                change = substitutions[name]
                assert change['from'] == '0.1.0a7' and change['to'] == '0.1.0a9'
                assert type(change['occurrences']) is int and change['occurrences'] == 1
                previous, current_version = change['from'].encode('ascii'), change['to'].encode('ascii')
                assert expected.count(previous) == change['occurrences'], name
                expected = expected.replace(previous, current_version)
            assert current == expected, 'Undeclared source/fixture change: ' + name
            checked[name] = hashlib.sha256(current).hexdigest()
    assert len(checked) == evolution['baseline_compared_files'] == 19, len(checked)
    additions = evolution['additive_package_files']
    assert set(additions) == {
        'packages/duckdb/src/equity_feature_duckdb/ef1.py',
        'packages/duckdb/src/equity_feature_duckdb/gap_endpoint.py',
        'packages/duckdb/src/equity_feature_duckdb/regular_bar_prices.py',
        'packages/duckdb/src/equity_feature_duckdb/real_bars_reader.py',
        'packages/duckdb/src/equity_feature_duckdb/regular_first_trade_price.py',
        'packages/duckdb/src/equity_feature_duckdb/reference_close.py',
        'packages/duckdb/src/equity_feature_duckdb/venue_status.py',
        'packages/duckdb/src/equity_feature_duckdb/money_flow.py',
        'packages/duckdb/src/equity_feature_duckdb/retracement.py',
        'packages/duckdb/src/equity_feature_duckdb/momentum.py',
    }
    additive_checked = {}
    for name, declaration in additions.items():
        digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert digest == declaration['sha256'], 'Undeclared additive source change: ' + name
        additive_checked[name] = digest
    package_prefix = 'packages/duckdb/src/equity_feature_duckdb/'
    expected_package_files = {name for name in inventory['source_sha256_utf8_git_bytes'] if name.startswith(package_prefix)} | set(additions)
    actual_package_files = {path.relative_to(ROOT).as_posix() for path in (ROOT / package_prefix).rglob('*')
                            if path.is_file() and '__pycache__' not in path.parts}
    assert actual_package_files == expected_package_files, 'Undeclared package file set'
    print(json.dumps(dict(schema='extraction-source-check2', baseline=inventory['canonical_baseline'],
        checked=checked, additive_checked=additive_checked,
        evolution_sha256=hashlib.sha256(evolution_path.read_bytes()).hexdigest(),
        version_marker_substitutions=substitutions, mathematical_changes=False), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
