"""Explicit trusted replay of one fixed installed calculator.

The five-second limit is checked AFTER return. This synchronous API does not
interrupt an active call, authenticate the original environment, or retry.
"""
from __future__ import annotations
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from time import monotonic_ns as _now
from equity_feature_contracts import CanonicalBatch, ContractError, FeatureResult, validate_batch
from equity_feature_evidence import EvidenceError, canonical_content, fingerprint_result, verify_receipt_content
from ._binding import pairs, validate_bundle
from ._errors import BundleError, require, sanitized
from ._model import BundleInput, I64_MAX, MAX_CALCULATION_ACCEPT_NS, ReplayReport, ReproductionBundle


def _installed_calculator() -> Callable[..., FeatureResult] | None:
    # All names are literals in trusted code; no bundle-selected import or install.
    try:
        if (version('equity-feature-contracts'), version('equity-feature-evidence'), version('equity-features')) != ('0.0.4a4', '0.1.0a2', '0.0.4a4'):
            return None
        from equity_features.session import compute_trades
    except (PackageNotFoundError, ImportError):
        return None
    return compute_trades


def _report(status: str, elapsed: int | None = None, result: FeatureResult | None = None,
        match: bool | None = None) -> ReplayReport:
    states = {
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
    execution, content, compatibility, count = states[status]
    return ReplayReport(status, execution, content, compatibility, match, elapsed, count,
        fingerprint_result(result) if result is not None else None, False)


def _sample(value: object) -> bool:
    return type(value) is int and 0 <= value <= I64_MAX


def replay_bundle(bundle: ReproductionBundle, supplied_inputs: tuple[tuple[str, CanonicalBatch], ...] = (),
        *, cancel_before_start: bool = False) -> ReplayReport:
    require(type(bundle) is ReproductionBundle and type(cancel_before_start) is bool)
    pairs(supplied_inputs)
    if cancel_before_start:
        return _report('cancelled_before_start')
    with sanitized():
        validate_bundle(bundle)
        supplied = dict(supplied_inputs)
        missing = {x.role for x in bundle.inputs if x.batch is None}
        require(set(supplied) <= missing, 'integrity_mismatch')
        resolved = tuple(BundleInput(x.role, x.input_id, x.content,
            supplied.get(x.role) if x.batch is None else x.batch) for x in bundle.inputs)
        # Validate supplied facts even when some other reference is still missing.
        complete = ReproductionBundle(bundle.manifest, bundle.receipt, bundle.configuration, bundle.result, resolved)
        config = complete.configuration
        require(len(config.session.intervals) <= 64 and len(config.window.governed_sessions) <= 256, 'limit_exceeded')
        require(all(x.batch is None or x.batch.row_count <= 10000 for x in resolved), 'limit_exceeded')
        if any(x.batch is None for x in resolved):
            return _report('unavailable')
        actual = tuple((x.role, x.batch) for x in resolved if x.batch is not None)
        require(verify_receipt_content(complete.receipt, config, actual, complete.result), 'integrity_mismatch')
        require(config.price_unit is not None and config.session.open_ns < config.availability.market_cutoff_ns <= config.session.close_ns)
        for _, batch in actual:
            meta = batch.metadata
            scope = meta.scope
            require(meta.namespace == config.session.namespace and meta.price_unit == config.price_unit
                and meta.adjustment == config.adjustment and meta.coverage.observed == batch.row_count, 'integrity_mismatch')
            require(scope is not None, 'integrity_mismatch')
            assert scope is not None
            require((scope.start_ns, scope.end_ns, scope.eligibility_policy, scope.include_opening_auction, scope.include_closing_auction)
                == (config.session.open_ns, config.availability.market_cutoff_ns, config.parameters[0].value,
                    config.session.include_opening_auction, config.session.include_closing_auction), 'integrity_mismatch')
            validate_batch(batch, session=config.session, availability=config.availability, required_fields=())
            columns = {c.name: c.values for c in batch.columns}
            require(all(x == complete.manifest.entity.instrument_id for x in columns['instrument_id'])
                and all(x == complete.manifest.entity.session_id for x in columns['session_id']), 'integrity_mismatch')
    calculator = _installed_calculator()
    if calculator is None:
        return _report('incompatible')
    start = _now()
    if not _sample(start):
        return _report('control_failed_before_start')
    try:
        output = calculator(actual[0][1] if actual else None, config, entity=bundle.manifest.entity)
    except ContractError:
        return _report('calculation_rejected')
    end = _now()
    if not _sample(end) or end < start:
        return _report('control_failed_after_return')
    elapsed = end - start
    if elapsed > MAX_CALCULATION_ACCEPT_NS:
        return _report('budget_exceeded_after_return', elapsed)
    try:
        require(type(output) is FeatureResult)
        observed = canonical_content(output)
    except (BundleError, EvidenceError, ContractError, ValueError, TypeError, AttributeError, OverflowError):
        return _report('result_rejected', elapsed)
    equal = observed == canonical_content(bundle.result)
    return _report('matched' if equal else 'mismatch', elapsed, output, equal)
