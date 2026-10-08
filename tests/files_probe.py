"""Fresh installed default/light then full optional source consumer proof."""
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

root=Path(sys.argv[1]).resolve(); report_path=Path(sys.argv[2]); mode=sys.argv[3]
versions={}
for name, expected in (("equity-feature-files","0.1.0a0"),("equity-feature-acquisition","0.1.0a0"),
    ("equity-feature-io-sdk","0.1.0a2"),("equity-feature-io-contracts","0.1.0a2"),
    ("equity-feature-contracts","0.0.4a4"),("equity-features","0.0.4a4")):
    dist=importlib.metadata.distribution(name);assert dist.version==expected;versions[name]=expected
    for relative in dist.files:
        assert "site-packages" in Path(dist.locate_file(relative)).resolve().parts
        assert "__editable__" not in str(relative)
subprocess.run([sys.executable,"-I",str(root/"examples/files_consumer.py")],check=True)
if mode=="light":
    from equity_feature_contracts import AvailabilitySpec,Coverage,DataKind,InputScope,PriceUnit,SourceBinding
    from equity_feature_contracts.adapters import AcquisitionRequest,SourceError,SourceErrorCode
    from equity_feature_files import FileProfile,LocalFileTradeAdapter
    assert importlib.util.find_spec("pyarrow") is None and importlib.util.find_spec("databento_dbn") is None
    class NeverCancelled:
        def is_cancelled(self):return False
    request=AcquisitionRequest("light",DataKind.TRADE,"owned-fixture",("A",),("S",),1,2,"s",PriceUnit(9,"USD"),AvailabilitySpec(2,2,2),max_batch_rows=1)
    for format in ("parquet","dbn"):
        profile=FileProfile(format,"owned-fixture",SourceBinding("owned","s","m","i"),PriceUnit(9,"USD"),Coverage(0,0,True),InputScope(1,2,"owned"),"0"*64,
            schema="dbn3-trades" if format=="dbn" else "normalized-trade-v1",dbn_dataset="SYNTH" if format=="dbn" else None)
        adapter=LocalFileTradeAdapter(str(root/"nonexistent"),profile,approve=lambda _:None)
        try:tuple(adapter.iter_batches(request,NeverCancelled()))
        except SourceError as error:assert error.code==SourceErrorCode.UNSUPPORTED and error.__context__ is None
        else:raise AssertionError("Absent optional dependency must fail before consent/read")
    report_path.write_text(json.dumps({"light_isolation":True,"optional_installed":False,"csv_factory_pure_consumer":True,"safe_missing_codecs":2,"versions":versions},indent=2)+"\n",encoding="utf-8",newline="\n")
else:
    assert mode=="full"
    for name,expected in (("pyarrow","20.0.0"),("databento-dbn","0.70.0")):
        assert importlib.metadata.version(name)==expected;versions[name]=expected
    suite=unittest.defaultTestLoader.discover(str(root/"tests/files"));count=suite.countTestCases();assert count==43
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful() and not result.skipped and result.testsRun==count
    subprocess.run([sys.executable,"-I","-m","mypy","--strict","-p","equity_feature_files"],check=True)
    subprocess.run([sys.executable,"-I","-m","mypy","--strict",str(root/"examples/files_consumer.py")],check=True)
    invalid=root/"invalid.py"
    invalid.write_text('from equity_feature_files import DBNAnnotation, ReadPolicy\nDBNAnnotation("S", "yes", None)\nReadPolicy(max_bytes="infinite")\n',encoding="utf-8")
    rejected=subprocess.run([sys.executable,"-I","-m","mypy","--strict",str(invalid)],text=True,capture_output=True)
    assert rejected.returncode==1 and rejected.stdout.count("error:")==2
    hashes={str(p.relative_to(root)).replace(chr(92),"/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/"tests/files/test_files.py",root/"tests/file_goldens.json",root/"examples/files_consumer.py")}
    report_path.write_text(json.dumps({"installed_public_execution":True,"versions":versions,"tests_run":count,"failures":0,"skips":0,
        "genuine_owned_formats": ["csv","parquet","dbn3"],"pure_consumer_formats":3,"strict_typing":True,"rejected_invalid_calls":2,"source_sha256":hashes},indent=2)+"\n",encoding="utf-8",newline="\n")
