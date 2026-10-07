"""Bounded acquisition observations; hashes never confer source admission."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
from pathlib import Path

from equity_feature_contracts import AvailabilitySpec, Coverage, SourceBinding
from equity_feature_contracts.adapters import Cancellation, SourceErrorCode
from .mapping import MappingReport
from .resolver import (CatalogConfig, FilePin, ResolvedPartition, ResolvedSource,
                       _HashBudget, _absolute, _count, _date, _fail, _hash, _identifier, _text, _resolve_source)


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        _fail("Serializable acquisition identity required")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class VerificationPolicy:
    max_hash_bytes: int = 1073741824
    max_files: int = 4096
    require_original_pins: bool = False

    def __post_init__(self) -> None:
        _count(self.max_hash_bytes, positive=True)
        _count(self.max_files, positive=True)
        if type(self.require_original_pins) is not bool:
            _fail("Boolean original pin policy required")


@dataclass(frozen=True)
class FileEvidence:
    partition: ResolvedPartition
    observed_original_sha256: str
    verified_optimized_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.partition) is not ResolvedPartition or _hash(self.observed_original_sha256) is None:
            _fail("Typed observed original file evidence required")
        _hash(self.verified_optimized_sha256)
        if (self.partition.original_sha256 is not None and self.partition.original_sha256 != self.observed_original_sha256
                or self.verified_optimized_sha256 is not None and self.partition.optimized_sha256 != self.verified_optimized_sha256):
            _fail("File evidence conflicts with supplied pins")


@dataclass(frozen=True)
class AcquisitionReceipt:
    request_digest: str
    configuration_digest: str
    resolved_digest: str
    input_evidence_digest: str
    catalog_sha256: str
    files: tuple[FileEvidence, ...]
    missing_sessions: tuple[str, ...]
    source: SourceBinding
    normalization: MappingReport | None
    coverage: Coverage
    availability: AvailabilitySpec
    calendar_version: str
    disposition: str
    rows: int
    pin_strength: str
    hash_bytes: int
    schema: str = field(default="acquisition1", init=False)
    adapter_version: str = field(default="0.1.0a8", init=False)
    canonical_schema: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        for digest in (self.request_digest, self.configuration_digest, self.resolved_digest,
                       self.input_evidence_digest, self.catalog_sha256):
            if _hash(digest) is None:
                _fail("Acquisition identity digest required")
        if type(self.files) not in (tuple, list) or any(type(x) is not FileEvidence for x in self.files):
            _fail("Owned file evidence required")
        object.__setattr__(self, "files", tuple(self.files))
        if type(self.missing_sessions) not in (tuple, list):
            _fail("Owned missing partition dates required")
        for session in self.missing_sessions:
            _date(session)
        object.__setattr__(self, "missing_sessions", tuple(self.missing_sessions))
        if (type(self.source) is not SourceBinding or type(self.coverage) is not Coverage
                or type(self.availability) is not AvailabilitySpec
                or self.normalization is not None and type(self.normalization) is not MappingReport):
            _fail("Typed acquisition metadata required")
        _text(self.calendar_version)
        _count(self.rows)
        _count(self.hash_bytes)
        if self.disposition not in ("data", "missing"):
            _fail("Supported acquisition disposition required")
        if (self.pin_strength not in ("no_selected_files", "all_selected_originals_pinned", "observed_without_all_original_pins")
                or self.disposition == "missing" and (self.rows != 0 or self.normalization is not None)
                or self.disposition == "data" and (self.normalization is None or self.normalization.rows != self.rows)):
            _fail("Acquisition receipt scope conflict")

    @property
    def identity_digest(self) -> str:
        return _digest(asdict(self))


@dataclass
class _Observation:
    catalog_path: Path
    catalog_sha256: str
    catalog_bytes: int
    files: tuple[FileEvidence, ...]
    policy: VerificationPolicy
    budget: _HashBudget

    def finish(self) -> None:
        # Matching observations are not an atomic snapshot or an ABA guarantee.
        for evidence in self.files:
            p = evidence.partition
            if self.budget.read(Path(p.original_path), p.original_bytes) != evidence.observed_original_sha256:
                _fail("Original source changed during acquisition")
            if evidence.verified_optimized_sha256 is not None:
                if self.budget.read(Path(p.optimized_path), p.optimized_bytes) != evidence.verified_optimized_sha256:
                    _fail("Pinned optimized source changed during acquisition")
        if self.budget.read(self.catalog_path, self.catalog_bytes) != self.catalog_sha256:
            _fail("Catalog changed during acquisition")

    @property
    def hash_bytes(self) -> int:
        return self.policy.max_hash_bytes - self.budget.remaining

    @property
    def pin_strength(self) -> str:
        if not self.files:
            return "no_selected_files"
        return ("all_selected_originals_pinned" if all(x.partition.original_sha256 is not None for x in self.files)
                else "observed_without_all_original_pins")


def _begin_observation(catalog_path: Path, resolved: ResolvedSource,
                       selected: tuple[ResolvedPartition, ...], policy: VerificationPolicy,
                       cancellation: Cancellation | None) -> _Observation:
    if len(resolved.partitions) > policy.max_files or len(selected) > policy.max_files:
        _fail("Verification file bound exceeded", SourceErrorCode.LIMIT)
    if _hash(resolved.catalog_sha256) is None:
        _fail("Resolved catalog hash required")
    _identifier(resolved.view_schema)
    _identifier(resolved.view_name)
    for p in resolved.partitions:
        _absolute(p.optimized_path)
        _count(p.optimized_bytes)
        if _hash(p.schema_sha256) is None:
            _fail("Resolved schema digest required")
        _hash(p.original_sha256)
        _hash(p.optimized_sha256)
        _text(p.admission)
        _text(p.original_dataset)
        for optional in (p.substituted_dataset, p.receipt_id):
            if optional is not None:
                _text(optional)
    payload = dict(selection=asdict(resolved.selection), catalog_sha256=resolved.catalog_sha256,
                   view_schema=resolved.view_schema, view_name=resolved.view_name,
                   partitions=[asdict(p) for p in resolved.partitions], missing_sessions=resolved.missing_sessions)
    if _digest(payload) != resolved.identity_digest:
        _fail("Resolved source identity mismatch")
    try:
        catalog_bytes = catalog_path.stat().st_size
    except OSError:
        _fail("Source catalog unavailable", SourceErrorCode.UNAVAILABLE)
    budget = _HashBudget(policy.max_hash_bytes, cancellation)
    # Reuse the accepted route/schema/metadata resolver, preserving receipt IDs.
    # Share the actual counter: a prior stat cannot charge concurrent file reads.
    fresh = _resolve_source(CatalogConfig(catalog_path, resolved.catalog_sha256,
        max_sessions=len(resolved.selection.sessions), max_files=policy.max_files,
        max_hash_bytes=budget.remaining), resolved.selection,
        pins=tuple(FilePin(p.original_path, receipt_id=p.receipt_id) for p in resolved.partitions),
        cancellation=cancellation, budget=budget)
    expected = tuple(replace(p, original_sha256=None, optimized_sha256=None) for p in resolved.partitions)
    if (fresh.partitions != expected or fresh.missing_sessions != resolved.missing_sessions
            or (fresh.view_schema, fresh.view_name) != (resolved.view_schema, resolved.view_name)):
        _fail("Resolved source metadata changed")
    files: list[FileEvidence] = []
    for p in selected:
        if policy.require_original_pins and p.original_sha256 is None:
            _fail("Required original hash pin unavailable", SourceErrorCode.UNAVAILABLE)
        original = budget.read(Path(p.original_path), p.original_bytes)
        if p.original_sha256 is not None and original != p.original_sha256:
            _fail("Original source hash pin mismatch")
        optimized = None
        if p.optimized_sha256 is not None:
            optimized = budget.read(Path(p.optimized_path), p.optimized_bytes)
            if optimized != p.optimized_sha256:
                _fail("Optimized source hash pin mismatch")
        files.append(FileEvidence(p, original, optimized))
    return _Observation(catalog_path, resolved.catalog_sha256, catalog_bytes, tuple(files), policy, budget)
