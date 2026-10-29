"""Single source of the experimental package versions for this repository's tools and tests.

A pre-release bump edits this table, the matching ``pyproject.toml`` files and ``__version__`` constants, the
canonical-package constant of ``equity_feature_io_contracts.factories`` and ``packages/bundles/.../_versions.py``
(installed packages cannot import this file). ``tools/verify_versions.py`` fails if any of them disagree.
Historical receipts, release records and frozen archive baselines keep the versions they were produced with.
"""
from __future__ import annotations

# Core distributions this repository is built and tested against (their sibling repository owns them).
CORE = {"equity-feature-contracts": "0.0.4a5", "equity-features": "0.0.4a6", "equity-feature-evidence": "0.1.0a3"}

# Distributions owned by this repository (examples included).
OWN = {
    "equity-feature-io-contracts": "0.1.0a3",
    "equity-feature-io-sdk": "0.1.0a3",
    "equity-feature-acquisition": "0.1.0a0",
    "equity-feature-files": "0.1.0a0",
    "equity-feature-duckdb": "0.1.0a11",
    "equity-feature-duckdb-sink": "0.1.0a1",
    "equity-feature-parquet": "0.1.0a2",
    "equity-feature-bundles": "0.1.0a2",
    "equity-feature-example-extensions": "0.1.0a1",
    "equity-feature-factory-fixture": "0.1.0a2",
}
VERSIONS = {**CORE, **OWN}
CONTRACTS = CORE["equity-feature-contracts"]
FEATURES = CORE["equity-features"]
EVIDENCE = CORE["equity-feature-evidence"]
IO_CONTRACTS = OWN["equity-feature-io-contracts"]
IO_SDK = OWN["equity-feature-io-sdk"]
