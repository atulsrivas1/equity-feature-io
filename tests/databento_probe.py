"""Fresh installed provider consumer; owned fixtures only, never a real request."""
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

root=Path(sys.argv[1]).resolve(); report_path=Path(sys.argv[2])
versions={}
for name,expected in (('equity-feature-databento','0.1.0a0'),('equity-feature-acquisition','0.1.0a0'),
    ('equity-feature-io-sdk','0.1.0a2'),('equity-feature-io-contracts','0.1.0a2'),
    ('equity-feature-contracts','0.0.4a4'),('equity-features','0.0.4a4'),('databento-dbn','0.70.0')):
    dist=importlib.metadata.distribution(name); assert dist.version==expected; versions[name]=expected
    for relative in dist.files:
        assert 'site-packages' in Path(dist.locate_file(relative)).resolve().parts
        assert '__editable__' not in str(relative)
assert importlib.util.find_spec('databento') is None
assert importlib.util.find_spec('pyarrow') is None
subprocess.run([sys.executable,'-I',str(root/'examples/databento_consumer.py')],check=True)
suite=unittest.defaultTestLoader.discover(str(root/'tests/databento'))
count=suite.countTestCases(); assert count==24
result=unittest.TextTestRunner(verbosity=1).run(suite)
assert result.wasSuccessful() and not result.skipped and result.testsRun==count
subprocess.run([sys.executable,'-I','-m','mypy','--strict','-p','equity_feature_databento'],check=True)
subprocess.run([sys.executable,'-I','-m','mypy','--strict',str(root/'examples/databento_consumer.py')],check=True)
invalid=root/'invalid.py'
invalid.write_text('from equity_feature_databento import DownloadPolicy, InstrumentBinding\nDownloadPolicy(max_bytes="infinite")\nInstrumentBinding(1, 1, "A", "S", "yes")\n',encoding='utf-8')
rejected=subprocess.run([sys.executable,'-I','-m','mypy','--strict',str(invalid)],text=True,capture_output=True)
assert rejected.returncode==1 and rejected.stdout.count('error:')==2
hashes={str(p.relative_to(root)).replace(chr(92),'/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root/'tests/databento/test_databento.py',root/'tests/databento_oracle.json',root/'examples/databento_consumer.py')}
report_path.write_text(json.dumps({'installed_public_execution':True,'actual_provider_proof':False,
    'versions':versions,'tests_run':count,'failures':0,'skips':0,'strict_typing':True,
    'rejected_invalid_calls':2,'source_sha256':hashes},indent=2)+'\n',encoding='utf-8',newline='\n')
