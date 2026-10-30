"""Read-only lookups over the packaged contract catalogue (internal, synthetic, pre-release).

The data are the generated files under ``equity_feature_io_contracts/catalogue/`` (schema ``ef-contract-catalogue1``).
This module reads them and returns them; it validates nothing, computes nothing and imports no core or workers code.
Authority: core frozen contract; on conflict core wins and the drift gate fails.

    from equity_feature_io_contracts import catalogue
    catalogue.producers()                                   # every producer, in catalogue order
    catalogue.by_feature_id("tape.window.count")            # the producer whose output carries that feature id
    catalogue.version()                                     # catalogue version plus per-producer contract_version
    catalogue.check_input("ef4.tape_window_sign", {"trades": "trade"})      # structural check of the roles supplied
    catalogue.check_output("ef4.tape_window_sign", headers)                 # structural check of result headers

``check_input`` and ``check_output`` are structural checks only (roles, kinds, nullability, feature ids, header fields,
reason names). They never look at values, never compute and never replace a library refusal; the library stays the
authority. Each finding cites the catalogue rule that failed and the catalogue page that states it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from types import MappingProxyType
from typing import Any, Iterable, Mapping

__all__ = ["CatalogueVersion", "CheckResult", "Finding", "Producer", "UnknownFeatureId", "UnknownProducer", "by_feature_id",
           "check_input", "check_output", "producers", "version"]


class UnknownFeatureId(KeyError):
    """The feature id is not an output of any producer in this catalogue version."""


class UnknownProducer(KeyError):
    """The producer id is not in this catalogue version."""


@dataclass(frozen=True)
class Finding:
    """One structural finding: the catalogue rule that failed, what it is about, and the catalogue page that states it."""

    rule: str
    subject: str
    detail: str
    page: str


@dataclass(frozen=True)
class CheckResult:
    """Result of a structural check: ``ok`` is true exactly when there are no findings."""

    producer_id: str
    view: str
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings


@dataclass(frozen=True)
class Producer:
    """One catalogue entry: a producer, its contract version and status, and the catalogue paths of its pages."""

    producer_id: str
    family: str
    contract_key: str
    contract_version: str
    status: str
    feature_ids: tuple[str, ...]
    adapter_api_page: str
    input_json: str
    input_md: str
    output_json: str
    output_md: str


@dataclass(frozen=True)
class CatalogueVersion:
    """Catalogue version (the package version) plus the contract_version of each producer, keyed by producer id."""

    catalogue_version: str
    families_present: tuple[str, ...]
    contract_versions: Mapping[str, str]


@lru_cache(maxsize=1)
def _index() -> dict[str, Any]:
    text = (resources.files("equity_feature_io_contracts") / "catalogue" / "index.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def _producer(entry: Mapping[str, Any]) -> Producer:
    paths = entry["paths"]
    return Producer(
        producer_id=entry["producer_id"], family=entry["family"], contract_key=entry["contract_key"],
        contract_version=entry["contract_version"], status=entry["status"], feature_ids=tuple(entry["feature_ids"]),
        adapter_api_page=entry["adapter"]["api_page"], input_json=paths["input_json"], input_md=paths["input_md"],
        output_json=paths["output_json"], output_md=paths["output_md"],
    )


def producers() -> tuple[Producer, ...]:
    """Every producer in the catalogue, in the order of ``index.json``."""
    return tuple(_producer(e) for e in _index()["producers"])


def by_feature_id(feature_id: str) -> Producer:
    """The producer whose output carries ``feature_id``; raises ``UnknownFeatureId`` (a ``KeyError``) when none does."""
    producer_id = _index()["by_feature_id"].get(feature_id)
    if producer_id is None:
        raise UnknownFeatureId(feature_id)
    for entry in _index()["producers"]:
        if entry["producer_id"] == producer_id:
            return _producer(entry)
    raise UnknownFeatureId(feature_id)  # unreachable while the drift gate holds: index.json is self-consistent


def version() -> CatalogueVersion:
    """The catalogue version and the contract_version of every producer."""
    index = _index()
    return CatalogueVersion(
        catalogue_version=index["catalogue_version"], families_present=tuple(index["families_present"]),
        contract_versions=MappingProxyType({e["producer_id"]: e["contract_version"] for e in index["producers"]}),
    )


def _view(producer_id: str, name: str) -> tuple[dict[str, Any], str]:
    """The packaged ``input`` or ``output`` view of a producer and its catalogue page path (md)."""
    for entry in _index()["producers"]:
        if entry["producer_id"] == producer_id:
            path = entry["paths"][f"{name}_json"]
            text = (resources.files("equity_feature_io_contracts") / "catalogue" / path).read_text(encoding="utf-8")
            view: dict[str, Any] = json.loads(text)
            return view, entry["paths"][f"{name}_md"]
    raise UnknownProducer(producer_id)


def check_input(producer_id: str, roles: Mapping[str, str | None]) -> CheckResult:
    """Structural check of the roles an adapter supplies against the producer's input view.

    ``roles`` maps a role name to the batch kind supplied for it (for example ``"trade"``) or ``None`` for an absent
    delivery. A role left out of the mapping is an absent delivery. Rules (all from the input view, ``roles``):
    ``input.role.unknown`` (a role the producer does not declare), ``input.role.kind`` (a kind other than the one
    declared, compared without regard to case; a role with no declared kind is not checked), ``input.role.required`` (a role declared not nullable is
    absent). A producer whose core contract states no role table has no roles to judge, so only the other rules apply. A nullable role that is absent is not a finding: the library reports it as ``absent_input``. Columns, rows
    and values are not looked at. Raises ``UnknownProducer`` for an unknown producer id.
    """
    view, page = _view(producer_id, "input")
    declared = {r["role"]: r for r in view["roles"]}
    findings: list[Finding] = []
    for name in sorted(set(roles) - set(declared)) if declared else ():  # no role table in core: roles cannot be judged
        findings.append(Finding("input.role.unknown", name, f"role {name!r} is not declared; declared roles: {', '.join(declared)}", page))
    for name, role in declared.items():
        kind = roles.get(name)
        if kind is None:
            if role["nullable"] is False:
                findings.append(Finding("input.role.required", name, f"role {name!r} is declared not nullable and must be supplied", page))
        elif role["kind"] is not None and kind.lower() != role["kind"].lower():  # core spells some kinds in capitals
            findings.append(Finding("input.role.kind", name, f"role {name!r} expects kind {role['kind']!r}, got {kind!r}", page))
    return CheckResult(producer_id, "input", tuple(findings))


_HEADER_FIELDS = ("feature_id", "algorithm_version", "dtype", "unit", "schema_version")


def _field(header: Any, name: str) -> Any:
    value = header.get(name) if isinstance(header, Mapping) else getattr(header, name, None)
    return getattr(value, "value", value) if name == "dtype" else value  # a ValueType enum compares by its string value


def check_output(producer_id: str, headers: Iterable[Any], reasons: Iterable[str] = ()) -> CheckResult:
    """Structural check of result headers (and, optionally, reason names) against the producer's output view.

    Each header is a mapping or an object with ``feature_id``, ``algorithm_version``, ``dtype``, ``unit`` and
    ``schema_version`` (a ``FeatureHeader`` works). Rules (from the output view, ``headers`` and ``quality``):
    ``output.header.field`` (a field is absent), ``output.feature_id.unknown`` (not an output of the producer),
    ``output.feature_id.duplicate``, ``output.header.value`` (a field differs from the catalogue
    ``feature_header_value``), ``output.quality.reason`` (a reason name outside the quality vocabulary the output view states; a producer whose core file states none is not judged on reasons). Selecting only
    some of the producer's feature ids is fine. Values, dtypes of cells and readiness are not looked at. Raises
    ``UnknownProducer`` for an unknown producer id.
    """
    view, page = _view(producer_id, "output")
    expected = {h["feature_id"]: h["feature_header_value"] for h in view["headers"]}
    findings: list[Finding] = []
    seen: set[str] = set()
    for header in headers:
        fid = _field(header, "feature_id")
        for f in (f for f in _HEADER_FIELDS if _field(header, f) is None):
            findings.append(Finding("output.header.field", f if fid is None else f"{fid}.{f}", f"header field {f!r} is absent", page))
        if fid is None:
            continue
        if fid in seen:
            findings.append(Finding("output.feature_id.duplicate", str(fid), f"feature id {fid!r} appears more than once", page))
            continue
        seen.add(fid)
        want = expected.get(fid)
        if want is None:
            findings.append(Finding("output.feature_id.unknown", str(fid), f"feature id {fid!r} is not an output of {producer_id}", page))
            continue
        for f in _HEADER_FIELDS[1:]:
            got = _field(header, f)
            if got is not None and got != want[f]:
                findings.append(Finding("output.header.value", f"{fid}.{f}", f"{f} is {got!r}, catalogue states {want[f]!r}", page))
    quality = view.get("quality") or {}
    vocabulary: set[str] = set(quality["status_of_reason"]) if isinstance(quality.get("status_of_reason"), dict) else set()
    for key in ("precedence", "reason_precedence", "reasons", "reasons_used"):
        if isinstance(quality.get(key), list):
            vocabulary |= {str(r) for r in quality[key]}
    for reason in sorted({str(r) for r in reasons} - vocabulary) if vocabulary else ():  # no stated vocabulary: reasons are not judged
        findings.append(Finding("output.quality.reason", reason, f"reason {reason!r} is not in the quality vocabulary", page))
    return CheckResult(producer_id, "output", tuple(findings))
