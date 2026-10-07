"""EQ123 design-fixture checks; no production codec or sink implementation."""
import argparse
import dataclasses
import enum
import hashlib
import importlib
import json
from pathlib import Path
import sys
import typing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-root", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.core_root / "packages/contracts/src"))
    modules = {name: importlib.import_module("equity_feature_contracts." + name)
               for name in ("results", "inputs", "specs")}
    root = Path(__file__).resolve().parents[1]
    spec = (root / "docs/contracts/IO_V1.md").read_text(encoding="utf-8")
    vectors = (root / "docs/contracts/IO_V1_VECTORS.md").read_text(encoding="utf-8")
    golden = json.loads((root / "docs/contracts/IO_V1_GOLDENS.json").read_text(encoding="utf-8"))
    records = {getattr(modules[module], name) for module, names in golden["registry_records"].items() for name in names}
    enums = {getattr(modules[module], name) for module, names in golden["registry_enums"].items() for name in names}
    observed_records, observed_enums = set(), set()

    def visit(value):
        if isinstance(value, type) and dataclasses.is_dataclass(value):
            if value in observed_records:
                return
            observed_records.add(value)
            for field_type in typing.get_type_hints(value).values():
                visit(field_type)
        elif isinstance(value, type) and issubclass(value, enum.Enum):
            observed_enums.add(value)
        else:
            for arg in typing.get_args(value):
                visit(arg)

    visit(modules["results"].FeatureResult)
    assert observed_records == records, (observed_records ^ records)
    assert observed_enums == enums, (observed_enums ^ enums)
    assert len(records) == 29 and len(enums) == 4
    for cls in records | enums:
        assert cls.__name__ in spec

    # Exact manually authored byte vector, with SHA computed by the standard
    # primitive, independent of the later EQ125 serializer implementation.
    data = golden["empty_feature_result_ascii"].encode("ascii")
    wire = json.loads(data)
    assert json.dumps(wire, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") == data
    assert len(data) == golden["empty_feature_result_bytes"] == 607
    prefix = b"efio-content1\0"
    assert len(prefix) == 14
    assert hashlib.sha256(prefix).hexdigest() == golden["zero_results_content_sha256"]
    assert hashlib.sha256(prefix + len(data).to_bytes(8, "big") + data).hexdigest() == golden["one_empty_result_content_sha256"]
    assert hashlib.sha256(prefix + (4).to_bytes(8, "big") + b"null").hexdigest() == golden["framed_null_example_sha256"]
    assert golden["zero_results_content_sha256"] != golden["one_empty_result_content_sha256"]
    # Field names are canonical authority, not copied schema definitions.
    registry = {module + "." + name: getattr(modules[module], name)
                for module, names in golden["registry_records"].items() for name in names}

    def inspect(node):
        if isinstance(node, dict):
            if "record" in node:
                assert set(node) == {"record", "fields"}
                assert set(node["fields"]) == {field.name for field in dataclasses.fields(registry[node["record"]])}
            for child in node.values():
                inspect(child)
        elif isinstance(node, list):
            for child in node:
                inspect(child)
    inspect(wire)

    R, S = modules["results"], modules["specs"]
    metadata = R.ResultMetadata("synthetic", "S", S.AvailabilitySpec(10, 10, 10), "0" * 64, (), "synthetic", "1")
    empty = R.FeatureResult((), (), metadata)
    assert not empty.values and not empty.quality and not empty.evidence
    entity = R.EntityKey("I", "S")
    count = R.FeatureColumn("synthetic.count", "1", R.ValueType.INT64, "count", (entity,), (0,))
    observed_empty = R.FeatureResult((count,), (R.QualityRow(entity, count.feature_id, R.Status.AVAILABLE, 0, 0),), metadata)
    missing = R.FeatureResult((dataclasses.replace(count, values=(None,)),),
                             (R.QualityRow(entity, count.feature_id, R.Status.MISSING_INPUT, None, 0, (R.Reason.ABSENT_INPUT,)),), metadata)
    assert observed_empty.values[0].values == (0,) and missing.values[0].values == (None,)
    breadth = R.FeatureColumn("synthetic.breadth", "1", R.ValueType.BREADTH_COUNTS, "count", (entity,), (R.BreadthCounts(1, 0, 0, 2),))
    partial = R.FeatureResult((breadth,), (R.QualityRow(entity, breadth.feature_id, R.Status.INCOMPLETE_COVERAGE, 2, 1, (R.Reason.PARTIAL_UNIVERSE,)),), metadata)
    assert partial.values[0].values[0].coverage.numerator == 1
    assert partial.values[0].values[0].coverage.denominator == 2
    assert (0.0).hex() == "0x0.0p+0" and (-0.0).hex() == "-0x0.0p+0"
    assert (1.25).hex() == "0x1.4000000000000p+0"
    assert '"float64":"-0x0.0p+0"' in vectors
    assert "COMMIT_UNKNOWN" in vectors and "CONFLICT" in vectors
    print("EQ123 canonical closure29/4, manual607-byte golden/three SHA frames, canonical empty/missing/partial and signed-zero fixtures pass. No runtime sink executed.")


if __name__ == "__main__":
    main()
