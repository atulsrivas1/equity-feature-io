"""Read-only lookups over the packaged contract catalogue (internal, synthetic, pre-release).

The data are the generated files under ``equity_feature_io_contracts/catalogue/`` (schema ``ef-contract-catalogue1``).
This module reads them and returns them; it validates nothing, computes nothing and imports no core or workers code.
Authority: core frozen contract; on conflict core wins and the drift gate fails.

    from equity_feature_io_contracts import catalogue
    catalogue.producers()                                   # every producer, in catalogue order
    catalogue.by_feature_id("tape.window.count")            # the producer whose output carries that feature id
    catalogue.version()                                     # catalogue version plus per-producer contract_version
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from types import MappingProxyType
from typing import Any, Mapping

__all__ = ["CatalogueVersion", "Producer", "UnknownFeatureId", "by_feature_id", "producers", "version"]


class UnknownFeatureId(KeyError):
    """The feature id is not an output of any producer in this catalogue version."""


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
