"""Adversarial archive gates for a new distribution beside the pure core."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from build_duckdb import inspect_adapter


class ArchiveTests(unittest.TestCase):
    def test_core_namespace_overwrite_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'equity_feature_duckdb-0.1.0a1-py3-none-any.whl'
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('equity_features/__init__.py','overwritten')
            with self.assertRaises(AssertionError):inspect_adapter(path)

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'equity_feature_duckdb-0.1.0a1-py3-none-any.whl'
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('../private.txt','escape')
            with self.assertRaises(AssertionError):inspect_adapter(path)


if __name__=='__main__':unittest.main()
