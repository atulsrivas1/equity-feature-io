"""Round trip of notional-ranked `tape.top_k_notional` cells through the bundles typed decoder, the io-sdk codec and the
core Arrow result conversion (PO ruling E1, C3/L2), plus the refusals the rank-aware shared check requires.

Requires the core library (`equity_features`) and the io packages on the interpreter path. Run: `python tools/verify_ef4_notional_cells.py`;
exit status 0 only if every check holds. This is a regression driver, not a unit test.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from typing import Any

from equity_feature_bundles import _json as lexer, _typed as typed
from equity_feature_contracts import (
    AdjustmentSpec, AvailabilitySpec, BatchMetadata, CanonicalBatch, Column, Coverage, DataKind, EntityKey, InputScope,
    PriceUnit, SessionSpec, SourceBinding,
)
from equity_feature_contracts.columnar import to_arrow_result
from equity_feature_evidence import canonical_content
from equity_feature_io_sdk.codec import decode_result, encode_result
from equity_features.ef4 import build_notional_top_k_config, compute_trade_top_k_notional

FEATURE = "tape.top_k_notional"


def notional_result() -> Any:
    """Prints a (1 x 10), b (2 x 3), c (1 x 1): the size order is b, a, c and the notional order is a, b, c."""
    session = SessionSpec("SYN", "S", 0, 100, "UTC")
    adjustment, unit = AdjustmentSpec(), PriceUnit(0, "USD")
    config = build_notional_top_k_config(policy_version="ef4-notional1", top_k=3, evidence_limit=3,
                                         eligibility_policy="regular", session=session,
                                         availability=AvailabilitySpec(100, 100, 100), adjustment=adjustment,
                                         price_unit=unit)
    data = [("I", "S", 1, 1, "a", True, 10, 1, 10), ("I", "S", 2, 2, "b", True, 3, 2, 10),
            ("I", "S", 3, 3, "c", True, 1, 1, 10)]
    names = ("instrument_id", "session_id", "event_ns", "order_key", "event_id", "eligible", "price", "size",
             "known_at_ns")
    columns = tuple(Column(name, tuple(row[i] for row in data)) for i, name in enumerate(names))
    meta = BatchMetadata("SYN", SourceBinding("SYN-SRC", "snap", "map1", "trades"), Coverage(3, 3, True), unit,
                         adjustment, "none", "shares", "declared", "reject", InputScope(0, 100, "regular"), ())
    return compute_trade_top_k_notional((CanonicalBatch(DataKind.TRADE, columns, meta),), config,
                                        entity=EntityKey("I", "S"), features=(FEATURE,))


def renamed(result: Any, feature_id: str) -> Any:
    def swap(x: Any) -> Any:
        return dataclasses.replace(x, feature_id=feature_id)
    return dataclasses.replace(result, values=tuple(swap(x) for x in result.values),
                               quality=tuple(swap(x) for x in result.quality),
                               evidence=tuple(swap(x) for x in result.evidence))


def refused(call: Any) -> bool:
    try:
        call()
    except Exception:
        return True
    return False


def main() -> int:
    problems: list[str] = []
    result = notional_result()
    cell = result.values[0].values[0]
    if [row.event_id for row in cell.rows] != ["a", "b", "c"]:
        problems.append("fixture is not notional ordered")
    raw = canonical_content(result)
    lexer.preflight(raw, "typed")
    if canonical_content(typed.typed_content(raw, "feature_result")) != raw:
        problems.append("bundles typed decoder does not round trip the notional cell")
    if decode_result(encode_result(result)) != result:
        problems.append("io-sdk codec does not round trip the notional cell")
    if FEATURE not in to_arrow_result(result)["values"]:
        problems.append("Arrow conversion lost the notional column")
    # The same stored cell under a size-ranked feature id is refused by the shared check (constructor and decoder).
    if not refused(lambda: renamed(result, "session.trade.top_k")):
        problems.append("notional cell under a size-ranked feature id was accepted")
    other = canonical_content(result).replace(b"tape.top_k_notional", b"session.trade.top_k")
    if not refused(lambda: typed.typed_content(other, "feature_result")):
        problems.append("bundles decoder accepted a notional cell under a size-ranked feature id")
    # A size-ordered cell under the notional feature id is refused.
    obj = json.loads(raw)
    cells = []

    def find(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "results.TopKTrades":
                cells.append(node["fields"]["rows"])
            for child in node.values():
                find(child)
        elif isinstance(node, list):
            for child in node:
                find(child)

    find(obj)
    dump = lambda: json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("ascii")  # noqa: E731
    if len(cells) != 1 or typed.typed_content(dump(), "feature_result") is None:  # type: ignore[no-untyped-call]
        problems.append("control: re-serialized notional result is not accepted")
    else:
        cells[0][0], cells[0][1] = cells[0][1], cells[0][0]
        if not refused(lambda: typed.typed_content(dump(), "feature_result")):  # type: ignore[no-untyped-call]
            problems.append("bundles decoder accepted rows not in notional order")
    for line in problems:
        print("FAIL", line)
    if not problems:
        print("OK: notional top-K cell round trips (bundles typed decoder, io-sdk codec, Arrow) and the rank refusals hold")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
