"""Exact immutable public records; construction never authenticates execution."""
from __future__ import annotations
from dataclasses import dataclass
from equity_feature_contracts import CanonicalBatch, ConfigSpec, EntityKey, FeatureResult
from equity_feature_evidence import ContentFingerprint, ExecutionReceipt, fingerprint_batch
from ._errors import label, require, sanitized

MAX_CALCULATION_ACCEPT_NS = 5000000000
I64_MAX = 2**63 - 1


@dataclass(frozen=True)
class PublicationDeclaration:
    data_class: str
    rights_statement: str
    retention: str

    def __post_init__(self) -> None:
        require(type(self.data_class) is str and self.data_class == 'synthetic')
        label(self.rights_statement)
        require(type(self.retention) is str and self.retention == 'caller_owned')


@dataclass(frozen=True)
class BundleVersions:
    bundle: str
    contracts: str
    evidence: str
    features: str

    def __post_init__(self) -> None:
        require(all(type(x) is str for x in (self.bundle, self.contracts, self.evidence, self.features)))
        require((self.bundle, self.contracts, self.evidence, self.features)
            == ('0.1.0a1', '0.0.4a4', '0.1.0a2', '0.0.4a4'), 'unsupported_version')


@dataclass(frozen=True)
class BundleManifest:
    registry: str
    entity: EntityKey
    versions: BundleVersions
    publication: PublicationDeclaration

    def __post_init__(self) -> None:
        require(type(self.registry) is str and self.registry == 'session.compute_trades.v1', 'unsupported_version')
        require(type(self.entity) is EntityKey and type(self.versions) is BundleVersions
            and type(self.publication) is PublicationDeclaration)
        label(self.entity.instrument_id); label(self.entity.session_id)
        self.versions.__post_init__(); self.publication.__post_init__()


@dataclass(frozen=True)
class BundleInput:
    role: str
    input_id: str
    content: ContentFingerprint
    batch: CanonicalBatch | None

    def __post_init__(self) -> None:
        with sanitized():
            label(self.role); label(self.input_id)
            require(type(self.content) is ContentFingerprint)
            self.content.__post_init__()
            require(self.content.domain == 'canonical_batch')
            require(0 < self.content.byte_length <= 33554432, 'limit_exceeded')
            require(self.batch is None or type(self.batch) is CanonicalBatch)
            if self.batch is not None:
                require(self.batch.metadata.source.input_id == self.input_id
                    and fingerprint_batch(self.batch) == self.content, 'integrity_mismatch')


@dataclass(frozen=True)
class ReproductionBundle:
    manifest: BundleManifest
    receipt: ExecutionReceipt
    configuration: ConfigSpec
    result: FeatureResult
    inputs: tuple[BundleInput, ...]

    def __post_init__(self) -> None:
        # Import is fixed internal code, never selected by data.
        from ._binding import validate_bundle
        with sanitized():
            validate_bundle(self)
            object.__setattr__(self, 'inputs', tuple(sorted(self.inputs, key=lambda x: x.role)))


@dataclass(frozen=True)
class ReplayReport:
    status: str
    execution_state: str
    content_state: str
    compatibility_state: str
    result_match: bool | None
    elapsed_ns: int | None
    calculation_count: int
    replayed_output: ContentFingerprint | None
    declared_environment_verified: bool

    def __post_init__(self) -> None:
        require(all(type(x) is str for x in (self.status, self.execution_state, self.content_state, self.compatibility_state)))
        require(type(self.calculation_count) is int and self.calculation_count in (0, 1))
        require(type(self.declared_environment_verified) is bool and self.declared_environment_verified is False)
        require(self.result_match is None or type(self.result_match) is bool)
        require(self.elapsed_ns is None or (type(self.elapsed_ns) is int and 0 <= self.elapsed_ns <= I64_MAX))
        with sanitized():
            if self.replayed_output is not None:
                require(type(self.replayed_output) is ContentFingerprint)
                self.replayed_output.__post_init__()
                require(self.replayed_output.domain == 'feature_result' and 0 < self.replayed_output.byte_length <= 33554432)
        rows = {
            'cancelled_before_start': ('not_started', 'not_checked', 'not_checked', 0),
            'unavailable': ('not_started', 'unavailable', 'not_checked', 0),
            'incompatible': ('not_started', 'verified', 'incompatible', 0),
            'control_failed_before_start': ('not_started', 'verified', 'verified', 0),
            'control_failed_after_return': ('returned', 'verified', 'verified', 1),
            'calculation_rejected': ('raised', 'verified', 'verified', 1),
            'budget_exceeded_after_return': ('returned', 'verified', 'verified', 1),
            'result_rejected': ('returned', 'verified', 'verified', 1),
            'mismatch': ('returned', 'verified', 'verified', 1),
            'matched': ('returned', 'verified', 'verified', 1),
        }
        require(self.status in rows)
        require((self.execution_state, self.content_state, self.compatibility_state, self.calculation_count) == rows[self.status])
        if self.status in ('matched', 'mismatch', 'result_rejected', 'budget_exceeded_after_return'):
            require(self.elapsed_ns is not None)
            assert self.elapsed_ns is not None
            require((self.elapsed_ns > MAX_CALCULATION_ACCEPT_NS) == (self.status == 'budget_exceeded_after_return'))
        else:
            require(self.elapsed_ns is None)
        if self.status in ('matched', 'mismatch'):
            require(self.result_match is (self.status == 'matched') and self.replayed_output is not None)
        else:
            require(self.result_match is None and self.replayed_output is None)
