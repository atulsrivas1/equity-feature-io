"""Check that every live place that carries a package version agrees with tools/_versions.py (static, source based).

Covers: pyproject versions and exact pins of packages and examples, package ``__version__`` constants, the canonical
package constant of io-contracts, the admitted versions of the bundles format and the canonical-version literals of the
example extension and factory fixture. Historical receipts are deliberately not checked.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _versions import CONTRACTS, EVIDENCE, FEATURES, OWN, VERSIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def expect(label: str, actual: object, wanted: object) -> None:
    if actual != wanted:
        errors.append(f"{label}: {actual!r} != {wanted!r}")


def check_requirements(label: str, requirements: list[str]) -> None:
    for requirement in requirements:
        m = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[a-z,]+\])?==([0-9][^;\s]*)(?:\s*;.*)?", requirement)
        if m and m.group(1) in VERSIONS:
            expect(f"{label} pin {m.group(1)}", m.group(2), VERSIONS[m.group(1)])


def constant(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)  # type: ignore[no-any-return]
    errors.append(f"{path.relative_to(ROOT)}: {name} not found")
    return ""


_README = re.compile(r"(?<![\w-])(equity-features?(?:-[a-z0-9]+)*)`?(?:==)?\s?(0\.\d+\.\d+a\d+)")
_SHORT = re.compile(r"(?<![\w-])(contracts|features|evidence|diagnostics|conformance|continuous|intraday|explanations|labels|strategies)\s?(0\.\d+\.\d+a\d+)")


def check_readmes(directory: Path, known: dict[str, str], short: dict[str, str]) -> None:
    """Every version a package README states for a distribution must equal the table (gate against stale or altered pins)."""
    for readme in sorted(directory.glob("*/README.md")):
        label = str(readme.relative_to(ROOT))
        historical = False
        for line in readme.read_text(encoding="utf-8").split(chr(10)):
            found = [(n, v) for n, v in _README.findall(line) if n in known]
            if line.startswith("#"):
                # A heading that names an older version of a distribution opens a historical section: its text is a record, not a pin.
                historical = any(v != known[n] for n, v in found)
                continue
            if historical:
                continue
            for name, version in found:
                expect(f"{label} states {name}", version, known[name])
            for name, version in _SHORT.findall(line):
                if name in short:
                    expect(f"{label} states {name}", version, short[name])


for pyproject in sorted([*(ROOT / "packages").glob("*/pyproject.toml"), *(ROOT / "examples").glob("*/pyproject.toml")]):
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    label = str(pyproject.parent.relative_to(ROOT))
    if project["name"] in OWN:
        expect(f"{label} version", project["version"], OWN[project["name"]])
    check_requirements(label, project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        check_requirements(label, group)

for init, name in (("packages/io-contracts/src/equity_feature_io_contracts/__init__.py", "equity-feature-io-contracts"),
                   ("packages/io-sdk/src/equity_feature_io_sdk/__init__.py", "equity-feature-io-sdk"),
                   ("packages/duckdb/src/equity_feature_duckdb/__init__.py", "equity-feature-duckdb"),
                   ("packages/parquet/src/equity_feature_parquet/__init__.py", "equity-feature-parquet"),
                   ("examples/third_party/src/equity_feature_example_extensions/__init__.py", "equity-feature-example-extensions"),
                   ("examples/factory_consumer/src/equity_feature_factory_fixture/__init__.py", "equity-feature-factory-fixture")):
    expect(f"{init} __version__", constant(ROOT / init, "__version__"), OWN[name])
expect("duckdb adapter_version default", re.search(r'adapter_version: str = field\(default="([^"]+)"', (ROOT / "packages/duckdb/src/equity_feature_duckdb/evidence.py").read_text(encoding="utf-8")).group(1),  # type: ignore[union-attr]
       OWN["equity-feature-duckdb"])
expect("io-contracts CANONICAL_PACKAGE_VERSION", constant(ROOT / "packages/io-contracts/src/equity_feature_io_contracts/factories.py", "CANONICAL_PACKAGE_VERSION"), CONTRACTS)

bundles = ROOT / "packages/bundles/src/equity_feature_bundles/_versions.py"
expect("bundles BUNDLE", constant(bundles, "BUNDLE"), OWN["equity-feature-bundles"])
expect("bundles CONTRACTS", constant(bundles, "CONTRACTS"), CONTRACTS)
expect("bundles EVIDENCE", constant(bundles, "EVIDENCE"), EVIDENCE)
expect("bundles FEATURES", constant(bundles, "FEATURES"), FEATURES)

# Standalone example packages declare the canonical contracts version they support as a literal on purpose.
for path in ("examples/factory_consumer/src/equity_feature_factory_fixture/publication.py",
             "examples/factory_consumer/src/equity_feature_factory_fixture/__init__.py",
             "examples/third_party/src/equity_feature_example_extensions/sink.py"):
    found = set(re.findall(r"0\.0\.4a\d+", (ROOT / path).read_text(encoding="utf-8")))
    expect(f"{path} canonical literals", found, {CONTRACTS})

check_readmes(ROOT / "packages", dict(VERSIONS), {n.removeprefix("equity-feature-").removeprefix("equity-"): v for n, v in VERSIONS.items()} | {"intraday": VERSIONS.get("equity-features-intraday", "")})

if errors:
    raise SystemExit("version drift:\n" + "\n".join(errors))
print("Versions consistent across packages, examples, in-source constants and bundle admission.")
