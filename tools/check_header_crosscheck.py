"""Cross-check the catalogue output headers against the headers the io and workers code declare (catalogue story S5).

Internal, synthetic, pre-release. Authority: the catalogue output views (generated from the core contract; core wins). This tool
reads the packaged catalogue and the Python source of this repository (``packages/*/src`` and ``examples``) and, with
``--workers-root``, of the workers repository. It reads source text only (``ast``); it imports and runs nothing and writes nothing.

For every catalogue producer and each layer (io, workers) it compares what the code declares as string literals:

* ``algorithm_version``: in a tuple, list or dict that holds the producer's config identity, every version-like literal
  (``...-v<N>``) must equal the catalogue ``algorithm_version``; any other one is a MISMATCH;
* a constant whose name contains ALGORITHM and whose value is version-like must be an algorithm_version some catalogue producer
  states; otherwise it is a MISMATCH;
* otherwise the producer is OK (identity and algorithm_version both declared in one container and equal) or NOT_DECLARED (the code
  does not state both as literals together, so nothing can be compared; counted and shown, never reported as OK).

Every MISMATCH is printed with file and line. Exit status 1 when any MISMATCH exists, else 0. Feature ids, dtype, unit and
schema_version are not stated as literals next to the identities in the code, so they are not compared (stated in the output).

    python tools/check_header_crosscheck.py [--workers-root PATH_TO_WORKERS_CHECKOUT]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_LIKE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-v\d+$")


def sources(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        out += [p for p in sorted(root.rglob("*.py")) if "build" not in p.parts and "tests" not in p.parts]
    return out


def const_strs(nodes: list[ast.AST]) -> list[tuple[str, int]]:
    return [(n.value, n.lineno) for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def containers(tree: ast.AST) -> list[list[tuple[str, int]]]:
    """String literals that sit directly in one tuple, list or dict (a declaration of an identity next to its version)."""
    found = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Tuple, ast.List)):
            found.append(const_strs(list(n.elts)))
        elif isinstance(n, ast.Dict):
            found.append(const_strs([*n.keys, *n.values]))  # type: ignore[list-item]
    return found


def scan(paths: list[Path], base: Path, producers: list[dict[str, object]], versions: set[str]) -> tuple[dict[str, dict[str, object]], list[str], int]:
    result: dict[str, dict[str, object]] = {str(p["producer_id"]): {"identity": False, "algorithm": False, "findings": []} for p in producers}
    stray: list[str] = []
    constants = 0
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # never silent
            print(f"unparsable: {path}: {exc}", file=sys.stderr)
            continue
        rel = str(path.relative_to(base)).replace("\\", "/")
        for group in containers(tree):
            values = {v for v, _ in group}
            for p in producers:
                pid, algo = str(p["producer_id"]), str(p["algorithm_version"])
                if pid not in values:
                    continue
                r = result[pid]
                r["identity"] = True
                for v, line in group:
                    if VERSION_LIKE.match(v):
                        if v == algo:
                            r["algorithm"] = True
                        else:
                            r["findings"].append(f"MISMATCH {pid}: {rel}:{line} declares algorithm_version {v!r} next to the identity, catalogue states {algo!r}")  # type: ignore[attr-defined]
        for node in ast.walk(tree):  # rule C: a named ALGORITHM constant must be a version some catalogue producer states
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and VERSION_LIKE.match(node.value.value):
                if any(isinstance(t, ast.Name) and "ALGORITHM" in t.id.upper() for t in node.targets):
                    constants += 1
                    if node.value.value not in versions:
                        stray.append(f"MISMATCH constant: {rel}:{node.lineno} declares algorithm version {node.value.value!r}, which no catalogue producer states")
    return result, stray, constants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers-root", type=Path, default=None)
    args = parser.parse_args()
    index = json.loads((ROOT / "docs/contracts/catalogue/index.json").read_text(encoding="utf-8"))
    producers = []
    for p in index["producers"]:
        out = json.loads((ROOT / "docs/contracts/catalogue" / p["paths"]["output_json"]).read_text(encoding="utf-8"))
        producers.append({"producer_id": p["producer_id"], "algorithm_version": out["algorithm_version"]})
    versions = {str(p["algorithm_version"]) for p in producers}
    layers = {"io": scan(sources([ROOT / "packages", ROOT / "examples"]), ROOT, producers, versions)}
    if args.workers_root is not None:
        layers["workers"] = scan(sources([args.workers_root / "packages"]), args.workers_root, producers, versions)
    bad = 0
    print(f"catalogue {index['catalogue_version']}: {len(producers)} producers, {len(index['by_feature_id'])} feature ids; layers: {', '.join(layers)}")
    print(f"{'producer':34} " + " ".join(f"{name:>13}" for name in layers))
    for p in producers:
        pid = str(p["producer_id"])
        cells = []
        for res, _, _ in layers.values():
            r = res[pid]
            state = "FINDINGS" if r["findings"] else ("OK" if r["identity"] and r["algorithm"] else "NOT_DECLARED")
            cells.append(f"{state:>13}")
        print(f"{pid:34} " + " ".join(cells))
    for name, (res, stray, _) in layers.items():
        for pid, r in res.items():
            for line in r["findings"]:  # type: ignore[attr-defined]
                print(f"[{name}] {line}")
                bad += 1
        for line in stray:
            print(f"[{name}] {line}")
            bad += 1
    for name, (res, stray, constants) in layers.items():
        ok = sum(1 for r in res.values() if r["identity"] and r["algorithm"] and not r["findings"])
        nd = sum(1 for r in res.values() if not r["findings"] and not (r["identity"] and r["algorithm"]))
        print(f"[{name}] OK {ok}, NOT_DECLARED {nd} (identity and algorithm_version not both stated as literals in one tuple, list or dict, so nothing to compare), ALGORITHM constants checked {constants}")
    print("not compared: feature ids, dtype, unit, schema_version (the code does not state them as literals next to the identity)")
    print(f"header cross-check: {'FAILED, ' + str(bad) + ' finding(s)' if bad else 'no mismatch among the declarations that exist'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
