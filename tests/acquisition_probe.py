"""Run only installed public packages and copied synthetic tests from a clean cwd."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import unittest

root = Path(sys.argv[1]).resolve()
report_path = Path(sys.argv[2])
versions = {}
for name, version in (("equity-feature-acquisition","0.1.0a0"),
                      ("equity-feature-io-contracts","0.1.0a2"),
                      ("equity-feature-contracts","0.0.4a4"), ("equity-features","0.0.4a4")):
    dist = importlib.metadata.distribution(name)
    assert dist.version == version
    versions[name] = version
    for relative in dist.files:
        path = Path(dist.locate_file(relative)).resolve()
        assert 'site-packages' in path.parts and '__editable__' not in str(relative)
suite = unittest.defaultTestLoader.discover(str(root/'tests/acquisition'))
count = suite.countTestCases()
assert count == 29
result = unittest.TextTestRunner(verbosity=1).run(suite)
assert result.wasSuccessful() and not result.skipped and result.testsRun == count
subprocess.run([sys.executable,'-I',str(root/'examples/acquisition_consumer.py')],check=True)
subprocess.run([sys.executable,'-I','-m','mypy','--strict','-p','equity_feature_acquisition'],check=True)
subprocess.run([sys.executable,'-I','-m','mypy','--strict',str(root/'examples/acquisition_consumer.py')],check=True)
invalid = root/'invalid.py'
invalid.write_text('from equity_feature_acquisition import Page, AcquisitionLimits\nPage("mutable text", 1)\nAcquisitionLimits(1, 1, 1, 1, "unknown")\n',encoding='utf-8')
rejected = subprocess.run([sys.executable,'-I','-m','mypy','--strict',str(invalid)],text=True,capture_output=True)
assert rejected.returncode == 1 and rejected.stdout.count('error:') == 2
hashes = {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
    (root/'tests/acquisition/test_controls.py',root/'tests/acquisition_goldens.json',root/'examples/acquisition_consumer.py')}
report_path.write_text(json.dumps({'installed_public_execution':True,'versions':versions,
    'tests_run':count,'failures':0,'skips':0,'third_party_transport':True,'strict_typing':True,
    'rejected_invalid_calls':2,'source_sha256':hashes},indent=2)+'\n',encoding='utf-8',newline='\n')
