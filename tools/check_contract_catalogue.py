"""Drift gate for the contract catalogue: docs copy == packaged data == fresh regeneration from core.

Internal, synthetic, pre-release. One command, three comparisons (exact file set and exact bytes):

    python tools/check_contract_catalogue.py --core-root PATH_TO_CORE [--core-ref origin/main]

Fails if ``docs/contracts/catalogue/`` differs from the packaged copy, or either differs from a regeneration from the core
contract files at the given ref, or any core top-level or producer key is unparsed. Core wins on conflict: the fix is to
regenerate (``tools/gen_contract_catalogue.py``), never to edit a generated file. Writes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_contract_catalogue as gen  # noqa: E402


def load(directory: Path) -> dict[str, bytes]:
    if not directory.is_dir():
        return {}
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(directory.rglob("*")) if p.is_file()}


def compare(label: str, found: dict[str, bytes], wanted: dict[str, bytes], errors: list[str]) -> None:
    for name in sorted(set(found) - set(wanted)):
        errors.append(f"{label}: unexpected file {name}")
    for name in sorted(set(wanted) - set(found)):
        errors.append(f"{label}: missing file {name}")
    for name in sorted(set(found) & set(wanted)):
        if found[name] != wanted[name]:
            errors.append(f"{label}: {name} differs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--core-ref", default="origin/main")
    args = parser.parse_args()
    fresh = gen.generate(args.core_root, args.core_ref)
    docs, package = load(gen.DOCS_DIR), load(gen.PACKAGE_DIR)
    errors: list[str] = []
    compare("docs copy vs package data", docs, package, errors)
    compare("docs copy vs regeneration from core", docs, fresh, errors)
    compare("package data vs regeneration from core", package, fresh, errors)
    index = json.loads(fresh["index.json"])
    for c in index["contracts"]:
        if c["unparsed_top_level_keys"] or c["unparsed_producer_keys"]:
            errors.append(f"unparsed core keys in {c['contract_key']}: {c['unparsed_top_level_keys']} {c['unparsed_producer_keys']}")
    listing = gen.git(args.core_root, "ls-tree", "-r", "--name-only", args.core_ref).decode("utf-8").split()
    known = {spec["path"] for spec in gen.CONTRACTS.values()}
    for path in sorted(p for p in listing if re.fullmatch(r"docs/[a-z0-9_]+/(?:[A-Z0-9_]+_CONTRACT_PROPOSAL|CONTRACT)\.json", p) and p not in known):
        print(f"not yet catalogued: {path} (core contract file with no catalogue entry; later story)")
    if errors:
        print("contract catalogue drift:")
        for e in errors:
            print("  " + e)
        print("Core wins. Regenerate with: python tools/gen_contract_catalogue.py --core-root <core> --core-ref " + args.core_ref)
        return 1
    print(f"contract catalogue OK: {len(fresh)} files, docs copy == package data == regeneration from core ({args.core_ref}); unparsed keys: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
