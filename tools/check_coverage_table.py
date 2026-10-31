"""Gate for the feature coverage table: rules R1 to R8, the D2 marker, wording, schema and regeneration (docs copy only).

Internal, synthetic, pre-release. Writes nothing.

    python tools/check_coverage_table.py --core-root PATH_TO_CORE [--core-ref origin/main] [--self-test]

Rules checked in this change (rules R5 to R8 and the DV1 marker expiry are a later change; this gate says so when it passes):

* R1 every cited output id resolves to exactly one of four contract states (frozen, proposed_not_frozen, core_registry,
  planned) with a link or a typed pointer; no blank link for a non-missing, non-out-of-scope row. R1b: no pointer-typed id may
  also have an io catalogue page (the pointer is stale, the page wins), and every pointer target must resolve and name the id.
* R2 every catalogue feature id is cited by an item or listed under ``extras`` (informational count).
* R3 design ids are unique; item count and per-family counts equal the declared design basis.
* R4 derived statuses equal the statuses pinned in the core map row by row, and equal the pinned counts below.
* R5 every record the map cites exists in core and is listed under ``sources.records``. R6 manifest cross-check: a cited
  output's release equals the manifest ``planned_delivery`` (or the catalogue family of its page); a manifest row that says
  ``implemented_by_this_packet`` must be in the catalogue unless the ``pending_catalogue`` marker lists it. R7 every evidence
  ref resolves to a file in core. R8 an assertion that carries ``asserted.contract_sha256`` (feature id to the sha256 of its
  catalogue source contract) fails once the contract moved; no row carries a stamp today, so R8 is exercised by its fixture only.
* D2 marker ``pending_catalogue`` (release DV1, expires_at CAT-DV1): its ids must equal the planned DV1 ids the map cites,
  the generated output must print the DV1 banner, and the gate FAILS if the catalogue already has the DV1 family.
* Wording: no provider names and no banned words in the generated text; schema: coverage.json validates against coverage.schema.json.
* R9 (docs part): the committed files equal a fresh regeneration from core. The packaged copy is not part of this change.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_coverage_table as gen  # noqa: E402

# Pinned counts after the Product Owner rulings of 2026-10-30 and 2026-10-31 (X7; P5 and P10 are partial, EF1 not frozen).
EXPECTED = {"implemented_confirmed": 31, "implemented_provisional": 7, "partial": 46, "missing": 59, "differs": 6, "out_of_library_scope": 17}
EXPECTED_MAP_EXTRA_GROUPS = 11
BANNED = re.compile(r"\b(databento|fmp|edgar|finra|massive|tempest|covered|fixed|production|releasable|speedup|faster)\b", re.I)


def validate(value: Any, schema: dict[str, Any], where: str, errors: list[str]) -> None:
    """Small stdlib JSON-Schema subset: const, enum, type, required, properties, items, oneOf."""
    if "oneOf" in schema:
        trial = [[] for _ in schema["oneOf"]]
        for sub, errs in zip(schema["oneOf"], trial):
            validate(value, sub, where, errs)
        if sum(1 for errs in trial if not errs) != 1:
            errors.append(f"{where}: does not match exactly one allowed shape")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{where}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")
    types = {"string": str, "object": dict, "array": list, "boolean": bool, "null": type(None)}
    if "type" in schema:
        wanted = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(isinstance(value, types[t]) for t in wanted):
            errors.append(f"{where}: expected type {wanted}")
            return
    if isinstance(value, str) and schema.get("type") == "string" and not value.strip():
        errors.append(f"{where}: blank string")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: missing key {key}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate(value[key], sub, f"{where}.{key}", errors)
    if isinstance(value, list) and "items" in schema:
        for n, one in enumerate(value):
            validate(one, schema["items"], f"{where}[{n}]", errors)


def check_document(doc: dict[str, Any], core: gen.Core, index: dict[str, Any], problems: list[str], pinned: dict[str, str] | None) -> list[str]:
    """R1 to R4 and wording on a built coverage document (``problems`` are the generator's unresolved-id findings)."""
    errors = list(problems)
    schema_errors: list[str] = []
    validate(doc, gen.SCHEMA_DOC, "coverage", schema_errors)
    errors += ["schema: " + e for e in schema_errors]
    seen_ids: set[str] = set()
    families: dict[str, int] = {}
    cited: set[str] = set()
    for item in doc["items"]:
        did = item["design_id"]
        if did in seen_ids:
            errors.append(f"R3: duplicate design_id {did}")
        seen_ids.add(did)
        families[item["family"]] = families.get(item["family"], 0) + 1
        if item["status"] in ("implemented", "differs") and not item["outputs"]:
            errors.append(f"R1: {did} has status {item['status']} and no output link")
        if item["status"] == "missing" and item["outputs"]:
            errors.append(f"R4: {did} is missing but cites outputs")
        if pinned is not None and pinned.get(did) != item["status"]:
            errors.append(f"R4: {did} derives {item['status']}, the core map pins {pinned.get(did)}")
        for o in item["outputs"]:
            cited.add(o["feature_id"])
            pointer_typed = o["contract_status"] in ("core_registry", "planned") or o["producer_id"] is None
            if pointer_typed and o["feature_id"] in index["by_feature_id"]:
                errors.append(f"R1b: {o['feature_id']} is typed {o['contract_status']} by pointer but has an io catalogue page; the pointer is stale, the page wins")
            for which in ("input_contract", "output_contract"):
                link = o[which]
                if link.get("kind") != "catalogue":
                    try:
                        text = core.text(link["core_path"])
                    except Exception:  # noqa: BLE001
                        errors.append(f"R1b: {o['feature_id']} {which} target {link['core_path']} does not resolve in core")
                        continue
                    if link["kind"] != "ownership_manifest" and o["feature_id"] not in text:
                        errors.append(f"R1b: {o['feature_id']} is not named in its pointer target {link['core_path']}")
                    if link["kind"] == "ownership_manifest" and f'"{o["feature_id"]}"' not in text:
                        errors.append(f"R1b: {o['feature_id']} has no row in {link['core_path']}")
    basis = doc["generated_from"]["design_basis"]
    if basis["item_count"] != len(doc["items"]):
        errors.append(f"R3: item_count {basis['item_count']} != {len(doc['items'])} items")
    if basis["family_counts"] != families:
        errors.append(f"R3: family_counts {basis['family_counts']} != actual {families}")
    for fid in index["by_feature_id"]:
        if fid not in cited and fid not in {e["feature_id"] for e in doc["extras"]}:
            errors.append(f"R2: catalogue id {fid} is neither cited nor listed as an extra")
    counts = doc["counts"]
    for key, want in EXPECTED.items():
        if counts[key] != want:
            errors.append(f"R4: count {key} is {counts[key]}, pinned {want}")
    if counts["map_extra_groups"] != EXPECTED_MAP_EXTRA_GROUPS:
        errors.append(f"R4: map extra groups {counts['map_extra_groups']}, pinned {EXPECTED_MAP_EXTRA_GROUPS}")
    return errors


def core_has(core: gen.Core, path: str) -> bool:
    return core.exists(path)


def rules_5_to_8(core: gen.Core, map_doc: dict[str, Any], doc: dict[str, Any], index: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    """R5 records, R6 manifest cross-check, R7 evidence refs, R8 asserted freshness, and the D2 marker (shape, coverage, expiry)."""
    errors: list[str] = []
    rows = gen.manifest_rows(manifest)
    listed = set(map_doc.get("sources", {}).get("records", {}).values())
    for rel in sorted(listed):
        if not core_has(core, rel):
            errors.append(f"R5: record {rel} listed in the map does not exist in core")
    producer_of = index["by_feature_id"]
    producers = {p["producer_id"]: p for p in index["producers"]}
    contract_sha = {c["contract_key"]: c["source"]["sha256_lf"] for c in index["contracts"]}
    planned_cited: set[str] = set()
    for item in map_doc["items"]:
        did = item["design_id"]
        asserted = item.get("asserted")
        if asserted:
            rec = asserted.get("record", "")
            if not core_has(core, rec):
                errors.append(f"R5: {did} cites record {rec}, which does not exist in core")
            elif rec not in listed:
                errors.append(f"R5: {did} cites record {rec}, which is not listed under sources.records")
            stamps = asserted.get("contract_sha256")
            if stamps is not None:
                for fid, stamped in sorted(stamps.items()):
                    pid = producer_of.get(fid)
                    if pid is None:
                        errors.append(f"R8: {did} stamps {fid}, which has no io catalogue page")
                    elif contract_sha[producers[pid]["contract_key"]] != stamped:
                        errors.append(f"R8: {did} assertion is stale: {fid} contract sha256 moved since the stamp; the Product Owner re-confirms")
        for e in item.get("evidence", []):
            if not core_has(core, e.get("ref", "")):
                errors.append(f"R7: {did} evidence {e.get('kind')} {e.get('ref')} does not resolve in core")
        for o in item["outputs"]:
            row = rows.get(o["id"])
            if row is not None and row["planned_delivery"] != o["release"]:
                errors.append(f"R6: {did} cites {o['id']} as {o['release']}, the ownership manifest says {row['planned_delivery']}")
            pid = producer_of.get(o["id"])
            if pid is not None and producers[pid]["family"] != o["release"]:
                errors.append(f"R6: {did} cites {o['id']} as {o['release']}, its catalogue page is family {producers[pid]['family']}")
            if o["release"] == "DV1" and pid is None:
                planned_cited.add(o["id"])
    marker = map_doc.get("pending_catalogue")
    for fid, row in sorted(rows.items()):
        if row["implemented"] and fid not in producer_of and not (marker and fid in marker.get("ids", [])):
            errors.append(f"R6: the manifest says {fid} is implemented, the catalogue lacks it (only the pending_catalogue marker is exempt)")
    if marker:
        if marker.get("release") != "DV1" or marker.get("expires_at") != "CAT-DV1":
            errors.append("D2: pending_catalogue must name release DV1 and expires_at CAT-DV1")
        if "DV1" in index["families_present"]:
            errors.append("D2: pending_catalogue marker is present but the catalogue already has the DV1 family; CAT-DV1's PR removes the marker")
        if set(marker.get("ids", [])) != planned_cited:
            only_marker = sorted(set(marker.get("ids", [])) - planned_cited)
            only_map = sorted(planned_cited - set(marker.get("ids", [])))
            errors.append(f"D2: marker ids differ from the planned DV1 ids the map cites: only in marker {only_marker}, only in map {only_map}")
        if gen.BANNER_DV1 not in doc.get("banners", []):
            errors.append("D2: marker present but the DV1 banner is not in the generated output")
    elif planned_cited:
        errors.append(f"D2: planned DV1 ids are cited with no pending_catalogue marker: {sorted(planned_cited)}")
    return errors


def wording_errors(files: dict[str, bytes]) -> list[str]:
    errors = []
    for name, data in files.items():
        for n, line in enumerate(data.decode("ascii", "replace").splitlines(), 1):
            for m in BANNED.finditer(line):
                errors.append(f"wording: {name}:{n}: banned word {m.group(0)!r}")
        if name == "COVERAGE.md" and "internal, synthetic, pre-release" not in data.decode("ascii", "replace"):
            errors.append("wording: COVERAGE.md lacks the scope wording")
        if re.search(r"\bEF1\b[^|\n]{0,40}\b(is|are) (delivered|frozen)\b", data.decode("ascii", "replace")):
            errors.append(f"wording: {name} claims EF1 is delivered or frozen")
    return errors


def run_checks(core_root: Path, ref: str, map_doc: dict[str, Any] | None = None, compare_committed: bool = True) -> list[str]:
    core = gen.Core(core_root, ref)
    raw_map, _ = core.read(gen.MAP_PATH)
    base = json.loads(raw_map.decode("utf-8"))
    use = map_doc if map_doc is not None else base
    doc, problems = gen.build(core_root, ref, map_doc)
    index = json.loads(gen.CATALOGUE_INDEX.read_text(encoding="utf-8"))
    pinned = {i["design_id"]: i["status"] for i in use["items"]}
    errors = check_document(doc, core, index, problems, pinned)
    manifest = json.loads(core.read(gen.MANIFEST_PATH)[0].decode("utf-8"))
    errors += rules_5_to_8(core, use, doc, index, manifest)
    if not problems:
        files = {"COVERAGE.md": gen.coverage_md(doc), "coverage.json": gen.cat.dumps(doc), "coverage.schema.json": gen.cat.dumps(gen.SCHEMA_DOC)}
        errors += wording_errors(files)
        if compare_committed:
            for name in sorted(set(files) | {p.name for p in gen.OUT_DIR.glob("*")}):
                path = gen.OUT_DIR / name
                if not path.is_file():
                    errors.append(f"R9: committed file {name} is missing")
                elif name not in files:
                    errors.append(f"R9: unexpected committed file {name}")
                elif path.read_bytes() != files[name]:
                    errors.append(f"R9: {name} differs from a regeneration from core")
    return errors


def self_test(core_root: Path, ref: str) -> list[str]:
    """Each rule has a bad scratch map (in memory, nothing written) that must fail with the expected message."""
    raw, _ = gen.Core(core_root, ref).read(gen.MAP_PATH)
    base = json.loads(raw.decode("utf-8"))
    failures: list[str] = []

    def expect(name: str, mutate: Any, needle: str) -> None:
        bad = copy.deepcopy(base)
        mutate(bad)
        try:
            errors = run_checks(core_root, ref, bad, compare_committed=False)
        except SystemExit as exc:
            errors = [str(exc)]
        except Exception as exc:  # noqa: BLE001
            errors = [repr(exc)]
        if not any(needle in e for e in errors):
            failures.append(f"self-test {name}: expected a finding containing {needle!r}, got {errors[:3]}")

    def item(doc: dict[str, Any], did: str) -> dict[str, Any]:
        return next(i for i in doc["items"] if i["design_id"] == did)

    expect("P5 restored to implemented", lambda d: item(d, "P5").update(status="implemented"), "R4: P5 derives partial, the core map pins implemented")
    expect("unknown output id", lambda d: item(d, "P3")["outputs"].append({"id": "nowhere.invented", "role": "operand", "release": "R1"}), "R1: R1 id nowhere.invented")
    expect("invented EF1 id", lambda d: item(d, "P3")["outputs"].append({"id": "session.invented.thing", "role": "operand", "release": "EF1"}), "R1: EF1 id session.invented.thing")
    expect("DV1 id with no manifest row", lambda d: item(d, "P3")["outputs"].append({"id": "history.invented_dv1", "role": "operand", "release": "DV1"}), "R1: history.invented_dv1 is cited as DV1")
    expect("outputs with no link (output list emptied)", lambda d: item(d, "P3").update(outputs=[], status="implemented"), "R4: P3 derives missing")
    expect("duplicate design id", lambda d: d["items"].append(copy.deepcopy(item(d, "P3"))), "R3: duplicate design_id P3")
    expect("item count", lambda d: d["design_basis"].update(item_count=165), "R3: item_count 165")
    expect("family counts", lambda d: d["design_basis"]["family_counts"].update({"presets": 99}), "R3: family_counts")
    live_index = json.loads(gen.CATALOGUE_INDEX.read_text(encoding="utf-8"))
    asserted_item = next(i for i in base["items"] if i.get("asserted"))["design_id"]
    expect("R5 unknown record", lambda d: item(d, asserted_item)["asserted"].update(record="docs/plans/records/nope.md"), "R5: " + asserted_item + " cites record")
    expect("R5 record not listed", lambda d: d["sources"]["records"].clear(), "R5: " + asserted_item + " cites record")
    paged = next((i["design_id"], n, o) for i in base["items"] for n, o in enumerate(i["outputs"]) if o["id"] in live_index["by_feature_id"])
    other = "EF2" if paged[2]["release"] != "EF2" else "EF3"
    expect("R6 release disagrees with the catalogue family", lambda d: item(d, paged[0])["outputs"].__setitem__(paged[1], {**paged[2], "release": other}), "R6: " + paged[0] + " cites " + paged[2]["id"])
    expect("R7 evidence does not resolve", lambda d: item(d, "P3")["evidence"].append({"kind": "gate", "ref": "tools/no_such_gate.py"}), "R7: P3 evidence")
    stamped = next((i for i in base["items"] if i.get("asserted") and any(o["id"] in live_index["by_feature_id"] for o in i["outputs"])), None)
    if stamped is not None:
        sid = next(o["id"] for o in stamped["outputs"] if o["id"] in live_index["by_feature_id"])
        expect("R8 stale stamp", lambda d: item(d, stamped["design_id"])["asserted"].update(contract_sha256={sid: "0" * 64}), "R8: " + stamped["design_id"] + " assertion is stale")
    else:
        failures.append("self-test R8: no asserted row cites a catalogue id to stamp")
    expect("D2 marker wrong expiry", lambda d: d["pending_catalogue"].update(expires_at="never"), "D2: pending_catalogue must name")
    expect("D2 marker id not planned", lambda d: d["pending_catalogue"]["ids"].append("candle.body_fraction"), "D2: marker ids differ")
    expect("D2 marker removed while DV1 ids planned", lambda d: d.pop("pending_catalogue"), "D2: planned DV1 ids are cited with no pending_catalogue marker")
    core_obj = gen.Core(core_root, ref)
    manifest = json.loads(core_obj.read(gen.MANIFEST_PATH)[0].decode("utf-8"))
    built, _ = gen.build(core_root, ref)
    flagged = copy.deepcopy(manifest)
    victim = next(r for r in flagged["outputs"] if r["canonical_name"] not in live_index["by_feature_id"])
    victim["implemented_by_this_packet"] = True
    if not any("R6: the manifest says" in e for e in rules_5_to_8(core_obj, base, built, live_index, flagged)):
        failures.append("self-test R6 manifest implemented without catalogue: no finding")
    with_dv1 = copy.deepcopy(live_index)
    with_dv1["families_present"] = sorted(with_dv1["families_present"] + ["DV1"])
    if not any("already has the DV1 family" in e for e in rules_5_to_8(core_obj, base, built, with_dv1, manifest)):
        failures.append("self-test D2 expiry (catalogue has DV1 while marker present): no finding")
    doc, problems = gen.build(core_root, ref)
    shadow = copy.deepcopy(doc)
    one = next(o for i in shadow["items"] for o in i["outputs"] if o["producer_id"] is not None)
    one["producer_id"] = None
    one["contract_status"] = "core_registry"
    errs = check_document(shadow, gen.Core(core_root, ref), json.loads(gen.CATALOGUE_INDEX.read_text(encoding="utf-8")), problems, None)
    if not any("R1b" in e and "stale" in e for e in errs):
        failures.append("self-test shadowed pointer: no R1b stale-pointer finding")
    broken = copy.deepcopy(doc)
    one = next(o for i in broken["items"] for o in i["outputs"] if o["contract_status"] == "core_registry")
    one["input_contract"] = one["output_contract"] = {**one["output_contract"], "core_path": "docs/does/not/exist.md"}
    errs = check_document(broken, gen.Core(core_root, ref), json.loads(gen.CATALOGUE_INDEX.read_text(encoding="utf-8")), problems, None)
    if not any("does not resolve" in e for e in errs):
        failures.append("self-test unresolved pointer: no finding")
    blank = copy.deepcopy(doc)
    next(o for i in blank["items"] for o in i["outputs"])["output_contract"] = {"kind": "core_registry", "core_path": "", "core_commit": "", "sha256_lf": "", "core_link": ""}
    errs = check_document(blank, gen.Core(core_root, ref), json.loads(gen.CATALOGUE_INDEX.read_text(encoding="utf-8")), problems, None)
    if not any("blank string" in e or "does not match" in e for e in errs):
        failures.append("self-test blank link: no finding")
    bad_status = copy.deepcopy(doc)
    next(o for i in bad_status["items"] for o in i["outputs"])["contract_status"] = "delivered"
    errs = check_document(bad_status, gen.Core(core_root, ref), json.loads(gen.CATALOGUE_INDEX.read_text(encoding="utf-8")), problems, None)
    if not any("is not one of" in e for e in errs):
        failures.append("self-test fifth contract_status: no finding")
    words = {"COVERAGE.md": b"internal, synthetic, pre-release. These items are covered and EF1 is frozen.\n"}
    if len(wording_errors(words)) < 2:
        failures.append("self-test wording: banned word and EF1 claim not both found")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--core-ref", default="origin/main")
    parser.add_argument("--self-test", action="store_true", help="also run the failing scratch-map fixtures (one per rule)")
    args = parser.parse_args()
    errors = run_checks(args.core_root, args.core_ref)
    if args.self_test:
        errors += self_test(args.core_root, args.core_ref)
    if errors:
        print("coverage table check FAILED:")
        for e in errors:
            print("  " + e)
        print("Fix the core map (core PR) or regenerate with: python tools/gen_coverage_table.py --core-root <core> --core-ref " + args.core_ref)
        return 1
    print(f"coverage table OK (R1-R8, R1b, D2 marker, wording, schema, docs copy == regeneration from core {args.core_ref}"
          + ("; self-test fixtures all failed as expected" if args.self_test else "") + ")")
    print("Not checked here: packaged copy (CV2), pre-merge wiring (CV3).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
