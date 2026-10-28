"""Gate for the EF5 supplied-input adapter (`equity_feature_duckdb.price_structures`) against the frozen EF5 contract.

Every result fixture (candle, structure, technical, known_at KA-set) of core `docs/ef5/PRICE_STRUCTURES_CONTRACT_PROPOSAL.json`
is expanded to supplied rows with the adapter (context, BAR chunks, closed configuration), computed through the pure library
(`equity_features_intraday.compute_ef5`) and compared with the contract literal (value by the contract acceptance rule, status,
reasons, counts, witnesses, echoed basis). The adapter configuration must equal the library builder's for the same context, and the
library result must survive the SDK codec round trip. Every refusal recipe is applied to its base fixture and must raise the
recorded error code, at the adapter or in the library. No mathematics here: the expectations are the contract literals that the
independent core expander recomputes.

    python tools/verify_ef5_io.py [--contract PATH_TO_CORE_docs_ef5_JSON]

The contract defaults to the sibling core checkout (`../equity-features/docs/ef5/...`) or the EF5_CONTRACT environment variable.
Exit status 0 only if everything holds.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, ContractError, Coverage, DataKind,
    InputScope, IntervalCoverage, PriceUnit, SessionSpec, SourceBinding,
)
from equity_feature_duckdb.price_structures import (
    CLOSE_COLUMNS, OHLCV_COLUMNS, make_ef5_batch, make_ef5_chunks, make_ef5_config, make_ef5_context,
)
from equity_feature_duckdb.relative_rv import IntradayRunSpec
from equity_feature_io_sdk import decode_result, encode_result
from equity_features_intraday import IntradayContext, IntradayRun, build_ef5_config, compute_ef5, require_ef5_capability

ROOT = Path(__file__).resolve().parents[1]
LISTS = ("candle_fixtures", "structure_fixtures", "technical_fixtures", "ka_fixtures")
T0 = 1_700_000_000_000_000_000
SEC = 10 ** 9
BAR = 60 * SEC
DAY = 86_400 * SEC
KA_DEFAULT = 50  # the compact notation's default known_at token, stated here and passed explicitly (fixture only)
LABEL_OF = {"raw": "unadjusted", "split": "split_adjusted"}
PARAMS = ("doji_body_max_fraction", "swing_strength", "lookback", "trend_window", "trend_count")
OWNER = {"doji_body_max_fraction": "candle", "swing_strength": "structure", "lookback": "structure",
         "trend_window": "technical", "trend_count": "technical"}


def contract_path(override: str | None) -> Path:
    if override:
        return Path(override)
    if os.environ.get("EF5_CONTRACT"):
        return Path(os.environ["EF5_CONTRACT"])
    return ROOT.parent / "equity-features" / "docs" / "ef5" / "PRICE_STRUCTURES_CONTRACT_PROPOSAL.json"


def grid(fx: dict[str, Any], n: int) -> tuple[list[int], list[int]]:
    daily = fx.get("grid") == "daily"
    offsets = fx.get("ends_s")
    ends = [T0 + ((offsets[i] if offsets else (i + 1) * 86400) * SEC if daily else (i + 1) * BAR) for i in range(n)]
    return [e - (DAY if daily else BAR) for e in ends], ends


def adjustment_spec(label: str | None, spec: dict[str, Any] | None) -> AdjustmentSpec:
    spec = spec or {}
    if label == "split_adjusted":
        return AdjustmentSpec(basis="split", **{k: spec[k] for k in ("policy_version", "action_snapshot", "anchor") if k in spec})
    return AdjustmentSpec(basis="raw", **({"policy_version": spec["policy_version"]} if "policy_version" in spec else {}))


def special(slot: Any) -> bool:
    return isinstance(slot, dict) and any(k in slot for k in ("wire", "versions", "no_coverage"))


def expand(fx: dict[str, Any]) -> tuple[Any, tuple[CanonicalBatch, ...], Any, Any, tuple[str, ...], str]:
    p = fx["params"]
    n = fx.get("target", len(fx["slots"]) - 1) + 1
    slots = fx["slots"][:n]
    daily = fx.get("grid") == "daily"
    starts, ends = grid(fx, n)
    forming = slots[-1] == "forming"
    cutoff = (ends[n - 2] if n >= 2 else starts[0]) if forming else ends[-1]
    knowledge = cutoff + 100 * SEC
    cols = OHLCV_COLUMNS if fx.get("columns", "ohlcv") == "ohlcv" else CLOSE_COLUMNS
    width = len(cols)
    label = fx.get("adjustment")
    declared = fx.get("coverage", "declared") == "declared"

    def known(ka: Any) -> Any:
        return ka if ka is None or isinstance(ka, float) else knowledge - (100 - ka) * SEC

    if daily:
        sessions = tuple(SessionSpec("SYN", f"D{i}", starts[i], ends[i], "UTC") for i in range(n))
        runs = tuple(IntradayRunSpec(f"D{i}", starts[i], DAY, 1) for i in range(n))
        lib_runs = tuple(IntradayRun(f"D{i}", starts[i], DAY, 1) for i in range(n))
    else:
        sessions = (SessionSpec("SYN", "S1", T0, T0 + n * BAR, "UTC"),)
        runs = (IntradayRunSpec("S1", T0, BAR, n),)
        lib_runs = (IntradayRun("S1", T0, BAR, n),)
    profile = p.get("epoch_profile")
    mode = {"session_reset": "reset", "governed_history": "carry"}.get(profile, "reset")
    spec_context = make_ef5_context("X", calendar_id="SYN-CAL", grid_id="SYN-GRID", revision="r1", sessions=sessions, runs=runs,
                                    anchor_index=0, target_index=n - 1,
                                    epoch_profile=profile if profile in ("session_reset", "governed_history") else "session_reset")
    library_context = IntradayContext("X", "SYN-CAL", "SYN-GRID", "r1", sessions, lib_runs, 0, n - 1, mode)
    unit = PriceUnit(fx["unit"]["scale"], fx["unit"]["currency"])
    basis = adjustment_spec(label, fx.get("adjustment_spec"))

    entries: list[Any] = []
    for slot in slots:
        if isinstance(slot, str) and slot != "null":
            entries.append(slot)
        elif slot == "null":
            entries.append({"values": (None,) * width, "known_at_ns": known(KA_DEFAULT)})
        elif isinstance(slot, dict) and "row" in slot and not special(slot):
            row = slot["row"]
            entries.append({"values": tuple(row) if row is not None else (None,) * width,
                            "known_at_ns": known(slot.get("ka", KA_DEFAULT))})
        elif isinstance(slot, list):
            entries.append({"values": tuple(slot), "known_at_ns": known(KA_DEFAULT)})
        else:
            entries.append(slot)
    if any(special(s) for s in slots) or any(isinstance(e, dict) and len(e.get("values", ())) not in (0, width) for e in entries):
        chunks = explicit_chunks(fx, slots, spec_context, cols, unit, basis, starts, ends, known, daily, declared)
    else:
        for e in entries:
            if isinstance(e, dict) and len(e["values"]) != width:
                raise ContractError(__import__("equity_feature_contracts").ErrorCode.INVALID_SCHEMA, "row width")
        chunks = make_ef5_chunks(spec_context, entries, input_id="bars", source_id="SYN-SRC", snapshot_id="snap1",
                                 namespace="SYN", price_unit=unit, adjustment=basis, columns=cols,
                                 eligibility_policy="ef5-regular", declare_coverage=declared)
    producer = fx["producer"]
    names = {k: p.get(k) for k in ("policy_version", "epoch_profile", "evidence_limit")}
    names.update({k: p.get(k) for k in PARAMS if OWNER[k] == producer})
    extra = {k: v for k, v in p.items() if k not in names}
    availability = AvailabilitySpec(cutoff, knowledge, knowledge)
    policy = (fx.get("adjustment_spec") or {}).get("policy_version")
    config = make_ef5_config(producer, spec_context, availability=availability, adjustment=basis, price_unit=unit,
                             adjustment_label=label, adjustment_policy_version=policy, **names, **extra)
    return library_context, chunks, config, (producer, availability, basis, unit, names, label, policy), \
        tuple(fx["outputs"]), fx.get("call", "compute")


def explicit_chunks(fx: dict[str, Any], slots: list[Any], context: Any, cols: tuple[str, ...], unit: PriceUnit,
                    basis: AdjustmentSpec, starts: list[int], ends: list[int], known: Any, daily: bool,
                    declared: bool) -> tuple[CanonicalBatch, ...]:
    """Identity-explicit rows for the wire-form recipes: the identity comes from the wire override or the grid."""
    from equity_feature_contracts import ErrorCode
    width = len(cols)
    names = ("instrument_id", "session_id", "start_ns", "end_ns", *cols, "known_at_ns")
    out: list[CanonicalBatch] = []
    row_basis = None
    for session in context.sessions:
        rows: list[tuple[Any, ...]] = []
        intervals: list[IntervalCoverage] = []
        for i, slot in enumerate(slots):
            if (f"D{i}" if daily else "S1") != session.session_id:
                continue
            if isinstance(slot, str) and slot not in ("null",):
                if slot == "gap":
                    intervals.append(IntervalCoverage(f"slot:{i}", starts[i], ends[i], Coverage(1, 0, False)))
                elif slot == "empty":
                    intervals.append(IntervalCoverage(f"slot:{i}", starts[i], ends[i], Coverage(0, 0, True)))
                continue
            wire = slot.get("wire", {}) if isinstance(slot, dict) else {}
            body = wire.get("row", slot.get("row") if isinstance(slot, dict) else slot)
            ka = wire.get("ka", slot.get("ka", KA_DEFAULT) if isinstance(slot, dict) else KA_DEFAULT)
            if slot == "null":
                body = [None] * width
            versions = slot.get("versions") if isinstance(slot, dict) else None
            for version in versions or [{"ka": ka}]:
                values = tuple(body) if body is not None else (None,) * width
                if len(values) != width:
                    raise ContractError(ErrorCode.INVALID_SCHEMA, "row width differs from the delivered columns")
                rows.append((wire.get("inst", "X"), wire.get("ss", session.session_id), wire.get("start", starts[i]),
                             wire.get("end", ends[i]), *values, known(version.get("ka", ka))))
            if wire.get("basis") is not None:
                row_basis = wire["basis"]
            if declared and not (isinstance(slot, dict) and slot.get("no_coverage")):
                intervals.append(IntervalCoverage(f"slot:{i}", starts[i], ends[i], Coverage(1, 1, True)))
        if row_basis is not None:
            adjustment = adjustment_spec(row_basis, {"policy_version": "split-factors-v1", "action_snapshot": "snap",
                                                     "anchor": "anchor"})
        else:
            adjustment = basis
        metadata = BatchMetadata("SYN", SourceBinding("SYN-SRC", "snap1", "ef5-map1", f"bars-{len(out):03}"),
                                 Coverage(None, len(rows), False), unit, adjustment, "none", "shares", "declared",
                                 "reject", InputScope(session.open_ns, session.close_ns, "ef5-regular"), tuple(intervals))
        out.append(make_ef5_batch(names, tuple(rows), metadata=metadata))
    return tuple(out)


def run(fx: dict[str, Any], features: tuple[str, ...] | None = None) -> tuple[Any, Any, Any]:
    context, chunks, config, parts, outputs, call = expand(fx)
    chosen = features or outputs
    if call != "compute":
        for feature in chosen:
            require_ef5_capability(feature, call)
    context_arg = None if ("context" in fx and fx["context"] is None) else context
    return compute_ef5(fx["producer"], chunks, context_arg, config, features=chosen), config, (context, parts)


def accepts(want: dict[str, Any] | None, value: Any) -> bool:
    if want is None or value is None:
        return want is None and value is None
    if "bool" in want:
        return bool(type(value) is bool and value is want["bool"])
    if "int" in want:
        return bool(type(value) is int and value == want["int"])
    r = float.fromhex(want["hex"])
    if want["acceptance"] in ("exact_float64", "exact_plus_zero"):
        return bool(value.hex() == r.hex() and math.copysign(1.0, value) == math.copysign(1.0, r))
    return bool(abs(value - r) <= max(8 * math.ulp(r), 1e-12 * abs(r)))


def compare(fx: dict[str, Any], result: Any, config: Any, features: tuple[str, ...]) -> list[str]:
    problems: list[str] = []
    expected = fx["expected"]
    if tuple(c.feature_id for c in result.values) != tuple(sorted(features)):
        return ["selected outputs differ"]
    found: dict[str, list[str]] = {f: [] for f in features}
    for row in result.evidence:
        found[row.feature_id].append(row.row_id)
    basis = LABEL_OF[config.adjustment.basis]
    echoed = {LABEL_OF[b.metadata.adjustment.basis] for b in result.metadata.inputs}
    for column in result.values:
        quality, = (q for q in result.quality if q.feature_id == column.feature_id)
        want = expected[column.feature_id]
        value, = column.values
        got = (quality.status.value, [r.value for r in quality.reasons], quality.expected, quality.observed)
        if not accepts(want["value"], value) or got != (want["status"], want["reasons"], want["expected"], want["observed"]):
            problems.append(f"{column.feature_id}: value {value!r} {got}")
        if want["basis"] != basis or echoed != {basis}:
            problems.append(f"{column.feature_id}: basis echo {basis} {echoed} != {want['basis']}")
        if len(features) == 1 and found[column.feature_id] != want["witnesses"]:
            problems.append(f"{column.feature_id}: witnesses {found[column.feature_id]} != {want['witnesses']}")
    if len(features) > 1:
        flat = [r.row_id for r in result.evidence]
        joint = [w for f in sorted(features) for w in expected[f]["witnesses"]][:fx["params"]["evidence_limit"]]
        if flat != joint:
            problems.append(f"joint evidence {flat} != {joint}")
    if decode_result(encode_result(result)) != result:
        problems.append("SDK codec round trip differs")
    return problems


def apply(base: dict[str, Any], mutations: list[dict[str, Any]]) -> dict[str, Any]:
    fx = copy.deepcopy(base)
    for step in mutations:
        keys = (step.get("delete") or step["set"]).split(".")[1:]
        cursor: Any = fx
        for key in keys[:-1]:
            cursor = cursor[int(key)] if isinstance(cursor, list) else cursor[key]
        last: Any = int(keys[-1]) if isinstance(cursor, list) else keys[-1]
        if "delete" in step:
            del cursor[last]
        else:
            cursor[last] = step["value"]
    return fx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract")
    doc = json.loads(contract_path(parser.parse_args().contract).read_text(encoding="utf-8"))
    by_id = {fx["id"]: fx for key in LISTS for fx in doc[key]}
    problems: list[str] = []
    runs = at_io = 0
    for fx in by_id.values():
        outputs = tuple(sorted(fx["expected"]))
        for features in [(f,) for f in outputs] + ([outputs] if len(outputs) > 1 else []):
            runs += 1
            try:
                result, config, (context, parts) = run(fx, features)
            except ContractError as error:
                problems.append(f"{fx['id']} {features}: refused {error.code.name}: {error}")
                continue
            problems += [f"{fx['id']}: {p}" for p in compare(fx, result, config, features)]
            producer, availability, basis, unit, names, label, policy = parts
            library = build_ef5_config(producer, context, availability=availability, adjustment=basis, price_unit=unit,
                                       adjustment_label=label, adjustment_policy_version=policy, **names)
            if library != config:
                problems.append(f"{fx['id']}: adapter configuration differs from the library builder")
    codes: set[str] = set()
    for rf in doc["refusal_fixtures"]:
        mutated = apply(by_id[rf["base"]], rf["mutation"])
        try:
            expand(mutated)
            run(mutated)
        except ContractError as error:
            codes.add(error.code.name)
            at_io += 1 if _raised_at_io(mutated) else 0
            if error.code.name != rf["error_code"]:
                problems.append(f"{rf['id']}: refused {error.code.name} expected {rf['error_code']} ({error})")
        else:
            problems.append(f"{rf['id']}: not refused (expected {rf['error_code']})")
    for line in problems:
        print("MISMATCH", line)
    if problems:
        print(f"{len(problems)} MISMATCH(ES)")
        return 1
    print(f"EF5 io: {len(by_id)} result fixtures ({runs} runs), adapter configurations equal the library builder, SDK round "
          f"trips equal; {len(doc['refusal_fixtures'])} refusals ({len(codes)} codes) raise the recorded code "
          f"({at_io} already at the adapter)")
    return 0


def _raised_at_io(fx: dict[str, Any]) -> bool:
    try:
        expand(fx)
    except ContractError:
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
