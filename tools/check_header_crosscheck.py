"""Cross-check the catalogue output headers against the headers the io and workers code declare (catalogue story S5, v2 RL-01-22).

Internal, synthetic, pre-release. Authority: the catalogue output views (generated from the core contract; core wins). This tool
reads the packaged catalogue and the Python source of this repository (``packages/*/src`` and ``examples``) and, with
``--workers-root``, of the workers repository. It reads source text only (``ast``); it imports and runs nothing and writes nothing.

For every catalogue producer and each layer (io, workers) it compares what the code declares as string literals:

* ``algorithm_version``: in a tuple, list or dict that holds the producer's config identity, every version-like literal
  (``...-v<N>``) must equal the catalogue ``algorithm_version``; any other one is a MISMATCH;
* a constant whose name contains ALGORITHM and whose value is version-like must be an algorithm_version some catalogue producer
  states; otherwise it is a MISMATCH;
* feature ids (v2): in a container that holds the producer's identity, a literal shaped like a feature id (dotted lower-case, first
  segment a catalogue feature-id namespace) must be one of that producer's catalogue feature ids; otherwise MISMATCH. Every
  literal equal to a catalogue feature id is counted as a declared id;
* dtype and unit (v2): in a dict that maps a catalogue feature id directly to a literal, or in a tuple or list that holds exactly
  one catalogue feature id, a literal that is a catalogue dtype value or a common dtype name such as int8 (or a catalogue unit value) must equal that feature id's catalogue dtype
  (or unit); otherwise MISMATCH;
* schema_version (v2): a ``schema_version`` dict key or keyword whose literal is a digit string, in a container that holds a
  producer identity or catalogue feature id, must equal the catalogue schema_version; otherwise MISMATCH;
* otherwise the producer is OK (identity and algorithm_version both declared in one container and equal) or NOT_DECLARED (the code
  does not state both as literals together, so nothing can be compared; counted and shown, never reported as OK). Every
  NOT_DECLARED pair (producer, layer) must be recorded as accepted, with a reason, in ``tools/header_crosscheck_accepted.json``;
  a pair not recorded is a finding, and a record whose pair is now OK, or no longer exists, is a stale record (also a finding).
  No pair is dropped.

Every finding is printed with file and line where one exists. Exit status 1 when any finding exists, else 0.

    python tools/check_header_crosscheck.py [--workers-root PATH_TO_WORKERS_CHECKOUT]

Exit codes: 0 no finding (every declared header value equals the catalogue, every NOT_DECLARED pair recorded); 1 at least one
finding; 2 usage or input error (fail closed: a ``--workers-root`` that is not an existing directory with a ``packages``
directory, a layer with no Python source to scan, or an unreadable accepted-pairs file). Without ``--workers-root`` the workers
layer is not read and its records are not checked.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = Path(__file__).resolve().parent / "header_crosscheck_accepted.json"
VERSION_LIKE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-v\d+$")
FEATURE_LIKE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
DIGITS = re.compile(r"^\d+$")
DTYPE_NAMES = {f"{k}{n}" for k in ("int", "uint") for n in (8, 16, 32, 64)} | {"float16", "float32", "float64", "bool", "string", "object"} | {f"decimal{n}" for n in (32, 64, 128, 256)}
DTYPE_NAMES = {f"{k}{n}" for k in ("int", "uint") for n in (8, 16, 32, 64)} | {"float16", "float32", "float64", "bool", "string", "object"} | {f"decimal{n}" for n in (32, 64, 128, 256)}


def sources(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        out += [p for p in sorted(root.rglob("*.py")) if "build" not in p.parts and "tests" not in p.parts]
    return out


def const_strs(nodes: list[ast.AST]) -> list[tuple[str, int]]:
    return [(n.value, n.lineno) for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def containers(tree: ast.AST) -> list[tuple[ast.AST, list[tuple[str, int]]]]:
    """String literals that sit directly in one tuple, list or dict (a declaration of an identity next to its version)."""
    found: list[tuple[ast.AST, list[tuple[str, int]]]] = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Tuple, ast.List)):
            found.append((n, const_strs(list(n.elts))))
        elif isinstance(n, ast.Dict):
            found.append((n, const_strs([*n.keys, *n.values])))  # type: ignore[list-item]
    return found


def mapped(node: ast.AST, key: str) -> list[tuple[str, int]]:
    """Literals a dict maps the literal ``key`` directly to (a feature id to its dtype or unit)."""
    if not isinstance(node, ast.Dict):
        return []
    return [(v.value, v.lineno) for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Constant) and isinstance(v.value, str)]


def schema_literals(node: ast.AST) -> list[tuple[str, int]]:
    """Digit-string literals bound to ``schema_version`` as a dict key or a keyword argument."""
    pairs: list[tuple[str, ast.AST]] = []
    if isinstance(node, ast.Dict):
        pairs = [(k.value, v) for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    elif isinstance(node, ast.Call):
        pairs = [(k.arg, k.value) for k in node.keywords if k.arg]
    return [(v.value, v.lineno) for k, v in pairs if k == "schema_version" and isinstance(v, ast.Constant) and isinstance(v.value, str) and DIGITS.match(v.value)]


def scan(paths: list[Path], base: Path, producers: list[dict[str, object]], versions: set[str], cat: dict[str, object]) -> tuple[dict[str, dict[str, object]], list[str], int]:
    result: dict[str, dict[str, object]] = {str(p["producer_id"]): {"identity": False, "algorithm": False, "findings": [], "ids": set()} for p in producers}
    fmeta: dict[str, dict[str, str]] = cat["features"]  # type: ignore[assignment]
    namespaces: set[str] = cat["namespaces"]  # type: ignore[assignment]
    dtypes: set[str] = cat["dtypes"]  # type: ignore[assignment]
    units: set[str] = cat["units"]  # type: ignore[assignment]
    schema = {str(p["producer_id"]): str(p["schema_version"]) for p in producers}
    stray: list[str] = []
    constants = 0

    def find(pid: str, text: str) -> None:
        result[pid]["findings"].append(text)  # type: ignore[attr-defined]

    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # never silent
            print(f"unparsable: {path}: {exc}", file=sys.stderr)
            continue
        rel = str(path.relative_to(base)).replace("\\", "/")
        for node, group in containers(tree):
            values = {v for v, _ in group}
            ids = [v for v, _ in group if v in fmeta]
            for fid in ids:
                result[fmeta[fid]["producer_id"]]["ids"].add(fid)  # type: ignore[attr-defined]
            for p in producers:
                pid, algo = str(p["producer_id"]), str(p["algorithm_version"])
                if pid not in values:
                    continue
                r = result[pid]
                r["identity"] = True
                own = {f for f, m in fmeta.items() if m["producer_id"] == pid}
                for v, line in group:
                    if VERSION_LIKE.match(v):
                        if v == algo:
                            r["algorithm"] = True
                        else:
                            find(pid, f"MISMATCH {pid}: {rel}:{line} declares algorithm_version {v!r} next to the identity, catalogue states {algo!r}")
                    elif FEATURE_LIKE.match(v) and v.split(".")[0] in namespaces and v not in own and v not in schema:
                        find(pid, f"MISMATCH {pid}: {rel}:{line} declares feature id {v!r} next to the identity, not a catalogue feature id of this producer")
            if isinstance(node, ast.Dict):
                pairs = [(fid, v, line) for fid in set(ids) for v, line in mapped(node, fid)]
            else:
                pairs = [(ids[0], v, line) for v, line in group if len(set(ids)) == 1 and v != ids[0]]
            for fid, v, line in pairs:
                m = fmeta[fid]
                if v in dtypes and v != m["dtype"]:
                    find(m["producer_id"], f"MISMATCH {m['producer_id']}: {rel}:{line} declares dtype {v!r} for {fid!r}, catalogue states {m['dtype']!r}")
                if v in units and v != m["unit"]:
                    find(m["producer_id"], f"MISMATCH {m['producer_id']}: {rel}:{line} declares unit {v!r} for {fid!r}, catalogue states {m['unit']!r}")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Dict, ast.Call)):
                near = {v for _, group in containers(node) for v, _ in group} if isinstance(node, ast.Dict) else set()
                for v, line in schema_literals(node):
                    for pid in schema:
                        if pid in near and v != schema[pid]:
                            find(pid, f"MISMATCH {pid}: {rel}:{line} declares schema_version {v!r}, catalogue states {schema[pid]!r}")
                    for fid in near & set(fmeta):
                        if v != fmeta[fid]["schema_version"]:
                            find(fmeta[fid]["producer_id"], f"MISMATCH {fmeta[fid]['producer_id']}: {rel}:{line} declares schema_version {v!r} next to {fid!r}, catalogue states {fmeta[fid]['schema_version']!r}")
            # rule C: a named ALGORITHM constant must be a version some catalogue producer states
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and VERSION_LIKE.match(node.value.value):
                if any(isinstance(t, ast.Name) and "ALGORITHM" in t.id.upper() for t in node.targets):
                    constants += 1
                    if node.value.value not in versions:
                        stray.append(f"MISMATCH constant: {rel}:{node.lineno} declares algorithm version {node.value.value!r}, which no catalogue producer states")
    return result, stray, constants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers-root", type=Path, default=None)
    args = parser.parse_args()
    if args.workers_root is not None and not (args.workers_root / "packages").is_dir():
        print(f"error: --workers-root {args.workers_root} is not a workers checkout (no 'packages' directory); refusing to report NOT_DECLARED for a layer that was not read", file=sys.stderr)
        return 2
    try:
        accepted_doc = json.loads(ACCEPTED.read_text(encoding="utf-8"))
        accepted = {(str(a["producer_id"]), str(a["layer"])): str(a["reason"]) for a in accepted_doc["accepted"]}
        if not all(accepted.values()):
            raise ValueError("a record has an empty reason")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: cannot read {ACCEPTED.name}: {exc}", file=sys.stderr)
        return 2
    index = json.loads((ROOT / "docs/contracts/catalogue/index.json").read_text(encoding="utf-8"))
    producers = []
    features: dict[str, dict[str, str]] = {}
    for p in index["producers"]:
        out = json.loads((ROOT / "docs/contracts/catalogue" / p["paths"]["output_json"]).read_text(encoding="utf-8"))
        producers.append({"producer_id": p["producer_id"], "algorithm_version": out["algorithm_version"], "schema_version": out["schema_version"]})
        for h in out["headers"]:
            features[h["feature_id"]] = {"producer_id": p["producer_id"], "dtype": h["dtype"], "unit": h["unit"], "schema_version": out["schema_version"]}
    cat: dict[str, object] = {"features": features, "namespaces": {f.split(".")[0] for f in features},
                              "dtypes": {m["dtype"] for m in features.values()} | DTYPE_NAMES, "units": {m["unit"] for m in features.values()}}
    versions = {str(p["algorithm_version"]) for p in producers}
    layers = {"io": scan(sources([ROOT / "packages", ROOT / "examples"]), ROOT, producers, versions, cat)}
    if args.workers_root is not None:
        workers_sources = sources([args.workers_root / "packages"])
        if not workers_sources:
            print(f"error: no Python source found under {args.workers_root / 'packages'}", file=sys.stderr)
            return 2
        layers["workers"] = scan(workers_sources, args.workers_root, producers, versions, cat)
    bad = 0
    print(f"catalogue {index['catalogue_version']}: {len(producers)} producers, {len(index['by_feature_id'])} feature ids; layers: {', '.join(layers)}")
    print(f"{'producer':34} " + " ".join(f"{name:>13}" for name in layers) + "   feature ids declared (io, workers)")
    pairs: dict[tuple[str, str], str] = {}
    for p in producers:
        pid = str(p["producer_id"])
        cells = []
        for name, (res, _, _) in layers.items():
            r = res[pid]
            state = "FINDINGS" if r["findings"] else ("OK" if r["identity"] and r["algorithm"] else "NOT_DECLARED")
            pairs[(pid, name)] = state
            cells.append(f"{state:>13}")
        total = sum(1 for m in features.values() if m["producer_id"] == pid)
        counts = ", ".join(f"{len(res[pid]['ids'])}/{total}" for res, _, _ in layers.values())  # type: ignore[arg-type]
        print(f"{pid:34} " + " ".join(cells) + f"   {counts}")
    for name, (res, stray, _) in layers.items():
        for r in res.values():
            for line in r["findings"]:  # type: ignore[attr-defined]
                print(f"[{name}] {line}")
                bad += 1
        for line in stray:
            print(f"[{name}] {line}")
            bad += 1
    for (pid, name), state in sorted(pairs.items()):
        if state == "NOT_DECLARED" and (pid, name) not in accepted:
            print(f"[{name}] NOT_DECLARED {pid}: not recorded in {ACCEPTED.name}; declare it in code or record it as accepted with a reason")
            bad += 1
    for (pid, name) in sorted(accepted):
        if name in layers and pairs.get((pid, name)) != "NOT_DECLARED":
            print(f"[{name}] STALE {pid}: recorded as accepted in {ACCEPTED.name} but the pair is {pairs.get((pid, name), 'not a catalogue producer')}; remove the record")
            bad += 1
    for name, (res, stray, constants) in layers.items():
        ok = sum(1 for r in res.values() if r["identity"] and r["algorithm"] and not r["findings"])
        nd = [pid for pid, r in res.items() if not r["findings"] and not (r["identity"] and r["algorithm"])]
        rec = sum(1 for pid in nd if (pid, name) in accepted)
        print(f"[{name}] OK {ok}, NOT_DECLARED {len(nd)} (recorded as accepted {rec}, unrecorded {len(nd) - rec}), ALGORITHM constants checked {constants}")
    if args.workers_root is None:
        print("workers layer not read (no --workers-root): its records are not checked")
    print("compared where declared as literals: algorithm_version, feature ids, dtype, unit, schema_version; a header value the code builds or computes is not a literal and cannot be compared")
    print(f"header cross-check: {'FAILED, ' + str(bad) + ' finding(s)' if bad else 'no finding; every NOT_DECLARED pair is recorded'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
