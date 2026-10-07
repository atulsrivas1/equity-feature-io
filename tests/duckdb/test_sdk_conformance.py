"""Actual DuckDB SDK integration and strict installed-location enforcement."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

EXAMPLE=Path(__file__).resolve().parents[2]/'examples/duckdb_conformance.py'
spec=importlib.util.spec_from_file_location('duckdb_conformance_fixture',EXAMPLE)
assert spec is not None and spec.loader is not None
example=importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class SDKTests(unittest.TestCase):
    def test_actual_thirty_cases_and_independent_values_units_quality(self):
        report=example.run_suite()
        self.assertEqual(report['schema'],'duckdb-conformance1')
        self.assertEqual(len(report['cases']),30)
        self.assertEqual(len({c['case_id'] for c in report['cases']}),30)
        self.assertTrue(all(c['passed'] and c['expected']==c['observed'] for c in report['cases']))
        cases={c['case_id']:c for c in report['cases']}
        self.assertEqual(cases['pin-stale']['observed'],'schema_mismatch')
        self.assertEqual(cases['hash-limit']['observed'],'resource_limit')
        self.assertIn('mutated actual delivery',cases['sdk-reject-coverage']['stage'])
        self.assertEqual(len(report['numerical']),16)
        self.assertTrue(all(c['source_binding_parity'] and c['expected_unit']==c['unit'] and c['expected_status']==c['observed_status'] for c in report['numerical']))
        values={(c['case'],c['feature']):c['observed'] for c in report['numerical']}
        self.assertEqual(values['trades-valid','session.trade.notional'],81200)
        self.assertEqual(values['minute-whole','session.bar.close_weighted_price'],11.625)
        self.assertEqual(values['daily-whole','history.sma'],20.0)
        self.assertIsNone(values['unknown-knowledge','session.trade.count'])
        self.assertIsNone(values['future-knowledge','session.trade.count'])

    def test_repository_import_cannot_pass_installed_requirement(self):
        with patch.object(example.adapter_package,'__file__',str(EXAMPLE.parent/'repository-source.py')):
            with self.assertRaisesRegex(RuntimeError,'installed public package locations'):
                example.run_suite(require_installed=True)


if __name__=='__main__':unittest.main()
