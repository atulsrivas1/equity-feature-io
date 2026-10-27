"""Closed typed-json-v1 projection. Data cannot name a Python constructor."""
from __future__ import annotations
import math
import re
from typing import Any
from equity_feature_contracts import inputs as i, results as r, specs as s
from equity_feature_evidence import canonical_content
from ._errors import require
from . import _versions as V
from ._json import fields, load


def _float(value: Any) -> float:
    require(type(value) is str)
    require(len(value) <= 24, 'limit_exceeded')
    require(value.isascii())
    if value not in ('0x0.0p+0', '-0x0.0p+0'):
        match = re.fullmatch(r'-?0x[01]\.[0-9a-f]{13}p([+-])(0|[1-9][0-9]{0,3})', value)
        require(match is not None)
        assert match is not None
        exponent = int(match[1] + match[2])
        require(-1022 <= exponent <= 1023)
    result = float.fromhex(value)
    require(math.isfinite(result) and result.hex() == value)
    return result


def decode(value: Any) -> Any:
    if type(value) in (str, int, bool) or value is None:
        return value
    if type(value) is list:
        return tuple(decode(x) for x in value)
    require(type(value) is dict)
    if set(value) == {'float64'}:
        return _float(value['float64'])
    envelope = fields(value, ('type', 'fields'))
    tag = envelope['type']
    require(type(tag) is str)
    raw = envelope['fields']
    if tag == 'inputs.CanonicalBatch':
        f = fields(raw, ('kind', 'columns', 'metadata'))
        require(type(f['columns']) is list and len(f['columns']) <= 64, 'limit_exceeded')
        return i.CanonicalBatch(
            kind=i.DataKind(f['kind']),
            columns=decode(f['columns']),
            metadata=decode(f['metadata']))
    if tag == 'inputs.Column':
        f = fields(raw, ('name', 'values'))
        return i.Column(
            name=decode(f['name']),
            values=decode(f['values']))
    if tag == 'inputs.BatchMetadata':
        f = fields(raw, ('namespace', 'source', 'coverage', 'price_unit', 'adjustment', 'sampling', 'quantity_unit', 'ordering', 'duplicate_policy', 'scope', 'interval_coverage'))
        return i.BatchMetadata(
            namespace=decode(f['namespace']),
            source=decode(f['source']),
            coverage=decode(f['coverage']),
            price_unit=decode(f['price_unit']),
            adjustment=decode(f['adjustment']),
            sampling=decode(f['sampling']),
            quantity_unit=decode(f['quantity_unit']),
            ordering=decode(f['ordering']),
            duplicate_policy=decode(f['duplicate_policy']),
            scope=decode(f['scope']),
            interval_coverage=decode(f['interval_coverage']))
    if tag == 'inputs.SourceBinding':
        f = fields(raw, ('source_id', 'snapshot_id', 'mapping_version', 'input_id'))
        return i.SourceBinding(
            source_id=decode(f['source_id']),
            snapshot_id=decode(f['snapshot_id']),
            mapping_version=decode(f['mapping_version']),
            input_id=decode(f['input_id']))
    if tag == 'inputs.Coverage':
        f = fields(raw, ('expected', 'observed', 'complete'))
        return i.Coverage(
            expected=decode(f['expected']),
            observed=decode(f['observed']),
            complete=decode(f['complete']))
    if tag == 'inputs.PriceUnit':
        f = fields(raw, ('scale', 'currency'))
        return i.PriceUnit(
            scale=decode(f['scale']),
            currency=decode(f['currency']))
    if tag == 'inputs.AdjustmentSpec':
        f = fields(raw, ('basis', 'policy_version', 'action_snapshot', 'anchor'))
        return i.AdjustmentSpec(
            basis=decode(f['basis']),
            policy_version=decode(f['policy_version']),
            action_snapshot=decode(f['action_snapshot']),
            anchor=decode(f['anchor']))
    if tag == 'inputs.InputScope':
        f = fields(raw, ('start_ns', 'end_ns', 'eligibility_policy', 'include_opening_auction', 'include_closing_auction'))
        return i.InputScope(
            start_ns=decode(f['start_ns']),
            end_ns=decode(f['end_ns']),
            eligibility_policy=decode(f['eligibility_policy']),
            include_opening_auction=decode(f['include_opening_auction']),
            include_closing_auction=decode(f['include_closing_auction']))
    if tag == 'inputs.IntervalCoverage':
        f = fields(raw, ('name', 'start_ns', 'end_ns', 'coverage'))
        return i.IntervalCoverage(
            name=decode(f['name']),
            start_ns=decode(f['start_ns']),
            end_ns=decode(f['end_ns']),
            coverage=decode(f['coverage']))
    if tag == 'specs.ConfigSpec':
        f = fields(raw, ('identity', 'algorithm_version', 'parameters', 'session', 'window', 'availability', 'adjustment', 'price_unit', 'schema_version'))
        return s.ConfigSpec(
            identity=decode(f['identity']),
            algorithm_version=decode(f['algorithm_version']),
            parameters=decode(f['parameters']),
            session=decode(f['session']),
            window=decode(f['window']),
            availability=decode(f['availability']),
            adjustment=decode(f['adjustment']),
            price_unit=decode(f['price_unit']),
            schema_version=decode(f['schema_version']))
    if tag == 'specs.Parameter':
        f = fields(raw, ('name', 'value'))
        return s.Parameter(
            name=decode(f['name']),
            value=decode(f['value']))
    if tag == 'specs.SessionSpec':
        f = fields(raw, ('namespace', 'session_id', 'open_ns', 'close_ns', 'timezone_label', 'intervals', 'scheduled_close_ns', 'early_close', 'include_opening_auction', 'include_closing_auction'))
        return s.SessionSpec(
            namespace=decode(f['namespace']),
            session_id=decode(f['session_id']),
            open_ns=decode(f['open_ns']),
            close_ns=decode(f['close_ns']),
            timezone_label=decode(f['timezone_label']),
            intervals=decode(f['intervals']),
            scheduled_close_ns=decode(f['scheduled_close_ns']),
            early_close=decode(f['early_close']),
            include_opening_auction=decode(f['include_opening_auction']),
            include_closing_auction=decode(f['include_closing_auction']))
    if tag == 'specs.IntervalSpec':
        f = fields(raw, ('name', 'start_ns', 'end_ns'))
        return s.IntervalSpec(
            name=decode(f['name']),
            start_ns=decode(f['start_ns']),
            end_ns=decode(f['end_ns']))
    if tag == 'specs.WindowSpec':
        f = fields(raw, ('count', 'target_session_id', 'governed_sessions', 'anchor'))
        return s.WindowSpec(
            count=decode(f['count']),
            target_session_id=decode(f['target_session_id']),
            governed_sessions=decode(f['governed_sessions']),
            anchor=decode(f['anchor']))
    if tag == 'specs.AvailabilitySpec':
        f = fields(raw, ('market_cutoff_ns', 'knowledge_cutoff_ns', 'evaluation_ns', 'mode', 'reconstruction_reason'))
        return s.AvailabilitySpec(
            market_cutoff_ns=decode(f['market_cutoff_ns']),
            knowledge_cutoff_ns=decode(f['knowledge_cutoff_ns']),
            evaluation_ns=decode(f['evaluation_ns']),
            mode=decode(f['mode']),
            reconstruction_reason=decode(f['reconstruction_reason']))
    if tag == 'results.FeatureResult':
        f = fields(raw, ('values', 'quality', 'metadata', 'evidence'))
        require(type(f['values']) is list and len(f['values']) <= 256, 'limit_exceeded')
        return r.FeatureResult(
            values=decode(f['values']),
            quality=decode(f['quality']),
            metadata=decode(f['metadata']),
            evidence=decode(f['evidence']))
    if tag == 'results.FeatureColumn':
        f = fields(raw, ('feature_id', 'algorithm_version', 'dtype', 'unit', 'entities', 'values', 'schema_version'))
        return r.FeatureColumn(
            feature_id=decode(f['feature_id']),
            algorithm_version=decode(f['algorithm_version']),
            dtype=r.ValueType(f['dtype']),
            unit=decode(f['unit']),
            entities=decode(f['entities']),
            values=decode(f['values']),
            schema_version=decode(f['schema_version']))
    if tag == 'results.EntityKey':
        f = fields(raw, ('instrument_id', 'session_id'))
        return r.EntityKey(
            instrument_id=decode(f['instrument_id']),
            session_id=decode(f['session_id']))
    if tag == 'results.QualityRow':
        f = fields(raw, ('entity', 'feature_id', 'status', 'expected', 'observed', 'reasons'))
        return r.QualityRow(
            entity=decode(f['entity']),
            feature_id=decode(f['feature_id']),
            status=r.Status(f['status']),
            expected=decode(f['expected']),
            observed=decode(f['observed']),
            reasons=tuple(r.Reason(x) for x in decode(f['reasons'])))
    if tag == 'results.ResultMetadata':
        f = fields(raw, ('namespace', 'session_id', 'availability', 'config_digest', 'inputs', 'backend_id', 'backend_version', 'evidence_limit', 'schema_version', 'math_policy_version'))
        return r.ResultMetadata(
            namespace=decode(f['namespace']),
            session_id=decode(f['session_id']),
            availability=decode(f['availability']),
            config_digest=decode(f['config_digest']),
            inputs=decode(f['inputs']),
            backend_id=decode(f['backend_id']),
            backend_version=decode(f['backend_version']),
            evidence_limit=decode(f['evidence_limit']),
            schema_version=decode(f['schema_version']),
            math_policy_version=decode(f['math_policy_version']))
    if tag == 'results.InputBinding':
        f = fields(raw, ('role', 'kind', 'metadata', 'schema_version'))
        return r.InputBinding(
            role=decode(f['role']),
            kind=i.DataKind(f['kind']),
            metadata=decode(f['metadata']),
            schema_version=decode(f['schema_version']))
    if tag == 'results.EvidenceRow':
        f = fields(raw, ('entity', 'feature_id', 'input_id', 'row_id', 'event_ns', 'known_at_ns', 'effective_start_ns', 'effective_end_ns', 'use', 'exclusion_reason', 'boundary'))
        return r.EvidenceRow(
            entity=decode(f['entity']),
            feature_id=decode(f['feature_id']),
            input_id=decode(f['input_id']),
            row_id=decode(f['row_id']),
            event_ns=decode(f['event_ns']),
            known_at_ns=decode(f['known_at_ns']),
            effective_start_ns=decode(f['effective_start_ns']),
            effective_end_ns=decode(f['effective_end_ns']),
            use=decode(f['use']),
            exclusion_reason=decode(f['exclusion_reason']),
            boundary=decode(f['boundary']))
    if tag == 'results.BreadthCounts':
        f = fields(raw, ('advancing', 'declining', 'unchanged', 'expected'))
        return r.BreadthCounts(
            advancing=decode(f['advancing']),
            declining=decode(f['declining']),
            unchanged=decode(f['unchanged']),
            expected=decode(f['expected']))
    if tag == 'results.BreadthFraction':
        f = fields(raw, ('above', 'eligible', 'expected'))
        return r.BreadthFraction(
            above=decode(f['above']),
            eligible=decode(f['eligible']),
            expected=decode(f['expected']))
    if tag == 'results.TopKTrades':
        f = fields(raw, ('k', 'rows'))
        return r.TopKTrades(
            k=decode(f['k']),
            rows=decode(f['rows']))
    if tag == 'results.TopKTradeRow':
        f = fields(raw, ('input_id', 'event_id', 'event_ns', 'order_key', 'known_at_ns', 'price', 'size'))
        return r.TopKTradeRow(
            input_id=decode(f['input_id']),
            event_id=decode(f['event_id']),
            event_ns=decode(f['event_ns']),
            order_key=decode(f['order_key']),
            known_at_ns=decode(f['known_at_ns']),
            price=decode(f['price']),
            size=decode(f['size']))
    if tag == 'results.QuoteStateCounts':
        f = fields(raw, ('normal', 'locked', 'crossed', 'invalid'))
        return r.QuoteStateCounts(
            normal=decode(f['normal']),
            locked=decode(f['locked']),
            crossed=decode(f['crossed']),
            invalid=decode(f['invalid']))
    if tag == 'results.QuoteObservation':
        f = fields(raw, ('input_id', 'event_id', 'event_ns', 'order_key', 'known_at_ns', 'bid', 'ask', 'state', 'spread', 'bps'))
        return r.QuoteObservation(
            input_id=decode(f['input_id']),
            event_id=decode(f['event_id']),
            event_ns=decode(f['event_ns']),
            order_key=decode(f['order_key']),
            known_at_ns=decode(f['known_at_ns']),
            bid=decode(f['bid']),
            ask=decode(f['ask']),
            state=decode(f['state']),
            spread=decode(f['spread']),
            bps=decode(f['bps']))
    if tag == 'results.SampledSpread':
        f = fields(raw, ('sampling', 'total', 'valid', 'mean_spread', 'mean_bps', 'observation_limit', 'rows'))
        return r.SampledSpread(
            sampling=decode(f['sampling']),
            total=decode(f['total']),
            valid=decode(f['valid']),
            mean_spread=decode(f['mean_spread']),
            mean_bps=decode(f['mean_bps']),
            observation_limit=decode(f['observation_limit']),
            rows=decode(f['rows']))
    if tag == 'results.QuoteDurations':
        f = fields(raw, ('normal', 'locked', 'crossed', 'invalid', 'expired', 'unknown'))
        return r.QuoteDurations(
            normal=decode(f['normal']),
            locked=decode(f['locked']),
            crossed=decode(f['crossed']),
            invalid=decode(f['invalid']),
            expired=decode(f['expired']),
            unknown=decode(f['unknown']))
    if tag == 'results.TimeWeightedSpread':
        f = fields(raw, ('durations', 'mean_spread', 'mean_bps', 'max_age_ns', 'initial_state'))
        return r.TimeWeightedSpread(
            durations=decode(f['durations']),
            mean_spread=decode(f['mean_spread']),
            mean_bps=decode(f['mean_bps']),
            max_age_ns=decode(f['max_age_ns']),
            initial_state=decode(f['initial_state']))
    if tag == 'results.IntervalOHLCV':
        f = fields(raw, ('rows',))
        return r.IntervalOHLCV(
            rows=decode(f['rows']))
    if tag == 'results.IntervalOHLCVRow':
        f = fields(raw, ('interval', 'open_price', 'high_price', 'low_price', 'close_price', 'volume', 'quality'))
        return r.IntervalOHLCVRow(
            interval=decode(f['interval']),
            open_price=decode(f['open_price']),
            high_price=decode(f['high_price']),
            low_price=decode(f['low_price']),
            close_price=decode(f['close_price']),
            volume=decode(f['volume']),
            quality=decode(f['quality']))
    if tag == 'results.IntervalVolumeShares':
        f = fields(raw, ('rows',))
        return r.IntervalVolumeShares(
            rows=decode(f['rows']))
    if tag == 'results.IntervalVolumeShareRow':
        f = fields(raw, ('interval', 'share', 'quality'))
        return r.IntervalVolumeShareRow(
            interval=decode(f['interval']),
            share=decode(f['share']),
            quality=decode(f['quality']))
    require(False)


def typed_content(raw: bytes, domain: str) -> Any:
    envelope = fields(load(raw), ('algorithm', 'canonicalization', 'contracts_version', 'domain', 'project', 'schema_version', 'value'))
    require(envelope['algorithm'] == 'sha256' and envelope['canonicalization'] == 'typed-json-v1'
        and envelope['contracts_version'] == V.CONTRACTS and envelope['schema_version'] == '1', 'unsupported_version')
    require(envelope['project'] == 'equity-features' and envelope['domain'] == domain)
    result = decode(envelope['value'])
    require((domain == 'canonical_batch' and type(result) is i.CanonicalBatch)
        or (domain == 'configuration' and type(result) is s.ConfigSpec)
        or (domain == 'feature_result' and type(result) is r.FeatureResult))
    require(canonical_content(result) == raw, 'integrity_mismatch')
    return result
