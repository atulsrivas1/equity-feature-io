"""Per-family extraction maps for the contract catalogue (EF1 and EF2 core contract files).

Internal, synthetic, pre-release. The EF3, EF4 and EF5 core files share one layout that ``gen_contract_catalogue.py`` reads
directly. The EF1 and EF2 files each use their own layout, so each gets one map here. A map only RENAMES and REGROUPS core keys
into that common layout (a producer table, a role table, a header list with a ``producer`` field, input rules, output
extras). It copies core text verbatim, computes nothing and invents no statement: a value that core does not state stays
``None`` and is shown as "not stated". Every core top-level key a map does not move is left in place, so the generator's
classification either excludes it with a reason (``extra_excluded`` below) or lists it as unparsed, which fails the gate.

Each map returns ``(contract_in_common_layout, extra_excluded_top_level_keys)``.
"""
from __future__ import annotations

import json
from typing import Any, Callable

Contract = dict[str, Any]

# Contract version (policy_version) per core file. It is asserted to occur in the core ``coordinator_freeze`` text, so it is read
# from core and not chosen here.
FREEZE_IDS = {
    "ef2.channels": "ef2-v1", "ef2.momentum": "ef2-conv1", "ef2.money_flow_retracement": "ef2-mf1 and ef2-retrace1",
    "ef1.close_reconciliation": "ef1-close-compare1", "ef1.multivenue_status": "ef1-multivenue-status1",
}

PROCESS = "process"
DECISION = "decision record"
CALC = "calculation semantics"
TESTS = "test evidence"


def _need_freeze(key: str, c: Contract) -> None:
    for part in FREEZE_IDS[key].split(" and "):
        if part not in c["coordinator_freeze"]:
            raise SystemExit(f"{key}: contract version {part!r} not found in core coordinator_freeze text; update the map")


def _take(c: Contract, *names: str) -> dict[str, Any]:
    return {n: c.pop(n) for n in names if n in c}


def _flatten_refusals(items: list[dict[str, Any]], producer: str | None = None) -> list[dict[str, Any]]:
    """Refusal fixtures with ``error_code`` at the top (core nests it under ``expected`` or names it ``code`` in some files)."""
    out = []
    for item in items:
        item = dict(item)
        expected = item.get("expected")
        if "error_code" not in item and isinstance(expected, dict) and "error_code" in expected:
            item["error_code"] = expected["error_code"]
        if "error_code" not in item and "code" in item:
            item["error_code"] = item["code"]
        if producer is not None:
            item["producer"] = producer
        out.append(item)
    return out


def _headers(items: list[dict[str, Any]], producer: str) -> list[dict[str, Any]]:
    return [{**h, "producer": producer} for h in items]


def map_channels(c: Contract) -> tuple[Contract, dict[str, str]]:
    """docs/ef2/ICHIMOKU_CHANNELS_CONTRACT_PROPOSAL.json: six producers, headers nested in each producer, no role table."""
    _need_freeze("ef2.channels", c)
    producers: dict[str, Any] = {}
    headers: list[dict[str, Any]] = []
    for p in c.pop("producers"):
        p = dict(p)
        name = p.pop("name")
        headers += _headers(p.pop("headers"), name)
        producers[name] = {**p, "policy_version": FREEZE_IDS["ef2.channels"]}
    c["producers"], c["headers"] = producers, headers
    c["quality"] = _take(c, "status_precedence", "reasons_used", "reasons_unreachable", "counts")
    c["refusal_fixtures"] = _flatten_refusals(c["refusal_fixtures"])
    return c, {"coordinator_decisions": DECISION, "operand_policy": CALC, "index_semantics": CALC, "conventions": DECISION, "coordinator_rulings": DECISION, "coordinator_decisions": DECISION,
               "ledger_to_be_applied": PROCESS, "invariant_pairs": TESTS}


def map_momentum(c: Contract) -> tuple[Contract, dict[str, str]]:
    """docs/ef2/MOMENTUM_TREND_CONTRACT_PROPOSAL.json: one producer identity covering macd, dmi and stochastic."""
    _need_freeze("ef2.momentum", c)
    config = c.pop("config")
    c.pop("frozen_version")
    shared = {k: v for k, v in config.items() if k not in ("identity", "algorithm_version", "status")}
    c["producers"] = {"momentum": {
        "config_identity": config["identity"], "algorithm_version": config["algorithm_version"], "schema_version": c["headers"][0]["schema_version"],
        "policy_version": FREEZE_IDS["ef2.momentum"], "parameters": shared, "config_status": config["status"]}}
    c["headers"] = _headers(c["headers"], "momentum")
    c["roles"] = {"momentum": c["roles"]}
    c["refusal_fixtures"] = _flatten_refusals(c["refusal_fixtures"])
    c["quality"] = {**c["quality"], "evidence_rule": c.pop("evidence_rule")}
    return c, {"shared_contract_followup": PROCESS, "builds_on": PROCESS, "r17_operands": CALC, "adx_expected_rule": CALC}


def map_money_flow_retracement(c: Contract) -> tuple[Contract, dict[str, str]]:
    """docs/ef2/MONEYFLOW_RETRACEMENT_CONTRACT_PROPOSAL.json: two producers, separate role tables and fixtures."""
    _need_freeze("ef2.money_flow_retracement", c)
    mf, rt = c.pop("money_flow_producer"), c.pop("retracement_producer")
    rt_params = list(rt.pop("parameters")) + [f"direction_values: {json.dumps(rt.pop('direction_values'))}", f"ratio_domain: {rt.pop('ratio_domain')}"]
    c["producers"] = {"money_flow": mf, "retracement_level": {**rt, "parameters": rt_params}}
    c["headers"] = c["headers"]  # already carries a producer field per header
    c["roles"] = {"money_flow": c.pop("money_flow_roles"), "retracement_level": c.pop("retracement_roles")}
    c["producers"]["retracement_level"]["roles_in_slot_order"] = c.pop("retracement_slot_order")
    c["reference_fact_schemas"] = {"extremum_reference_schema": c.pop("extremum_reference_schema")}
    c["refusal_fixtures"] = (_flatten_refusals(c.pop("money_flow_refusal_fixtures"), "money_flow")
                             + _flatten_refusals(c.pop("retracement_refusal_fixtures"), "retracement_level"))
    c["producers"]["money_flow"]["policy_version"] = "ef2-mf1"
    c["producers"]["retracement_level"]["policy_version"] = "ef2-retrace1"
    return c, {"decisions": DECISION, "rulings": DECISION, "amendment_note": PROCESS}


def map_close_reconciliation(c: Contract) -> tuple[Contract, dict[str, str]]:
    """docs/ef1/CLOSE_RECONCILIATION_CONTRACT_PROPOSAL.json: one producer, roles and slot order at the top."""
    _need_freeze("ef1.close_reconciliation", c)
    producer = dict(c.pop("producer"))
    name = producer.pop("name")
    c["producers"] = {name: {**producer, "policy_version": FREEZE_IDS["ef1.close_reconciliation"], "roles_in_slot_order": c.pop("slot_order")}}
    c["headers"] = c["headers"]
    c["roles"] = {name: c["roles"]}
    c["quality"] = {**c["quality"], **_take(c, "comparison_state_vocabulary", "comparison_state_precedence")}
    c["reference_fact_schemas"] = {"authoritative_close_schema": c.pop("authoritative_close_schema")}
    c["refusal_fixtures"] = _flatten_refusals(c["refusal_fixtures"])
    return c, {"coordinator_decisions": DECISION, "mathematics": CALC}


def map_multivenue_status(c: Contract) -> tuple[Contract, dict[str, str]]:
    """docs/ef1/MULTI_VENUE_STATUS_CONTRACT_PROPOSAL.json: one producer, five REFERENCE slots described field by field."""
    _need_freeze("ef1.multivenue_status", c)
    name = c.pop("producer")
    ident = dict(c.pop("config_identity"))
    entry = {"config_identity": ident.pop("identity"), "algorithm_version": ident.pop("algorithm_version"),
             "schema_version": ident.pop("schema_version"), "policy_version": FREEZE_IDS["ef1.multivenue_status"], "parameters": ident}
    roles = []
    for r in c.pop("roles"):
        rest = {k: v for k, v in r.items() if k not in ("slot", "role", "kind")}
        text = "; ".join(f"{k}: {v if isinstance(v, str) else json.dumps(v)}" for k, v in rest.items())
        roles.append({"role": r["role"], "kind": r["kind"], "nullable": None, "contract": text})
    c["producers"] = {name: {**entry, "roles_in_slot_order": [r["role"] for r in roles]}}
    c["roles"] = {name: roles}
    c["quality"] = _take(c, "reason_precedence", "available_aggregate_reasons", "scalar_to_legacy_reason", "quality_status_rule",
                         "dimension_codes", "mapping_version")
    c["refusal_model"] = c.pop("refusal_codes")
    c["selection"] = {"selection_schema": c.pop("selection_schema"), "policy_vocabulary": c.pop("policy_vocabulary")}
    return c, {"supporting": PROCESS, "frozen_contract": PROCESS, "frozen_contract_sha256": PROCESS, "coordinator_decisions": DECISION}


MAPS: dict[str, Callable[[Contract], tuple[Contract, dict[str, str]]]] = {
    "ef2.channels": map_channels, "ef2.momentum": map_momentum, "ef2.money_flow_retracement": map_money_flow_retracement,
    "ef1.close_reconciliation": map_close_reconciliation, "ef1.multivenue_status": map_multivenue_status,
}
