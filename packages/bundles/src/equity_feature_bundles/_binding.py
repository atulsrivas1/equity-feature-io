"""Full content binding and fixed registry shape; no calculator import."""
from __future__ import annotations
from equity_feature_contracts import CanonicalBatch, ConfigSpec, DataKind, EntityKey, FeatureResult, ValueType
from equity_feature_evidence import (
    ExecutionReceipt, canonical_content, content_chunks, encode_receipt,
    fingerprint_config, fingerprint_result, make_receipt,
)
from ._errors import require
from ._model import BundleInput, BundleManifest, ReproductionBundle


def aggregate(roots: tuple[CanonicalBatch | ConfigSpec | FeatureResult, ...]) -> None:
    """Count known canonical tokens across streamed roots before retaining their bytes."""
    size = nodes = 0
    for root in roots:
        quoted = escaped = atom = False
        for chunk in content_chunks(root):
            size += len(chunk)
            require(size <= 33554432, 'limit_exceeded')
            for c in chunk:
                if quoted:
                    if escaped: escaped = False
                    elif c == 92: escaped = True
                    elif c == 34: quoted = False
                elif c == 34:
                    nodes += 1; quoted = True; atom = False
                elif c in (123, 91):
                    nodes += 1; atom = False
                elif c in (125, 93, 44, 58):
                    atom = False
                elif not atom:
                    nodes += 1; atom = True
                require(nodes <= 1000000, 'limit_exceeded')


def shape(configuration: ConfigSpec, result: FeatureResult) -> EntityKey:
    require(type(configuration) is ConfigSpec and type(result) is FeatureResult)
    require(configuration.schema_version == '1' and configuration.algorithm_version == 'v1'
        and len(configuration.parameters) == 1 and configuration.parameters[0].name == 'eligibility_policy'
        and type(configuration.parameters[0].value) is str, 'unsupported_version')
    require(len(result.values) == 5 and not result.evidence and result.metadata.evidence_limit == 0
        and result.metadata.backend_id == 'python-exact' and result.metadata.backend_version == '0.0.4a4', 'unsupported_version')
    entity = result.values[0].entities
    require(type(entity) is tuple and len(entity) == 1 and type(entity[0]) is EntityKey, 'unsupported_version')
    specs = (('count', ValueType.INT64, 'trades'), ('volume', ValueType.INT64, 'shares'),
        ('notional', ValueType.DECIMAL128, 'currency coefficient / 10^price_scale'),
        ('vwap', ValueType.FLOAT64, 'currency/share'), ('mean_size', ValueType.FLOAT64, 'shares/trade'))
    for column, (suffix, dtype, unit) in zip(result.values, specs, strict=True):
        require(column.feature_id == 'session.trade.' + suffix and column.algorithm_version == 'v1'
            and column.schema_version == '1' and column.dtype is dtype and column.unit == unit
            and column.entities == entity, 'unsupported_version')
    require(entity[0].session_id == configuration.session.session_id, 'integrity_mismatch')
    require(len(result.metadata.inputs) <= 1, 'unsupported_version')
    for binding in result.metadata.inputs:
        require(binding.role == 'trades' and binding.kind is DataKind.TRADE, 'unsupported_version')
    return entity[0]


def pairs(value: tuple[tuple[str, CanonicalBatch], ...]) -> None:
    require(type(value) is tuple)
    require(len(value) <= 64, 'limit_exceeded')
    from ._errors import label
    for pair in value:
        require(type(pair) is tuple and len(pair) == 2)
        label(pair[0]); require(type(pair[1]) is CanonicalBatch)
    require(len({x[0] for x in value}) == len(value))


def validate_bundle(bundle: ReproductionBundle) -> None:
    require(type(bundle) is ReproductionBundle and type(bundle.manifest) is BundleManifest)
    bundle.manifest.__post_init__()
    require(type(bundle.receipt) is ExecutionReceipt and type(bundle.configuration) is ConfigSpec
        and type(bundle.result) is FeatureResult and type(bundle.inputs) is tuple)
    require(len(bundle.inputs) <= 64, 'limit_exceeded')
    require(all(type(x) is BundleInput for x in bundle.inputs))
    require(len({x.role for x in bundle.inputs}) == len(bundle.inputs)
        and len({x.input_id for x in bundle.inputs}) == len(bundle.inputs))
    # Whole aggregate prevalidation precedes fingerprints/materialized config digest.
    aggregate((bundle.configuration, bundle.result) + tuple(x.batch for x in bundle.inputs if x.batch is not None))
    for item in bundle.inputs: item.__post_init__()
    require(shape(bundle.configuration, bundle.result) == bundle.manifest.entity, 'integrity_mismatch')
    receipt = bundle.receipt
    receipt_bytes = encode_receipt(receipt)
    require(receipt.configuration == fingerprint_config(bundle.configuration)
        and receipt.output == fingerprint_result(bundle.result), 'integrity_mismatch')
    expected = make_receipt(bundle.result, configuration=receipt.configuration, inputs=receipt.inputs,
        output=receipt.output, formulas=receipt.formulas, environment=receipt.environment,
        execution=receipt.execution, evidence=receipt.evidence)
    require(encode_receipt(expected) == receipt_bytes, 'integrity_mismatch')
    meta, config = bundle.result.metadata, bundle.configuration
    require(meta.namespace == config.session.namespace and meta.session_id == config.session.session_id
        and meta.availability == config.availability and meta.config_digest == config.digest, 'integrity_mismatch')
    require(tuple(sorted((x.role, x.input_id, x.content) for x in bundle.inputs))
        == tuple((x.role, x.input_id, x.content) for x in receipt.inputs), 'integrity_mismatch')
    for item in bundle.inputs:
        if item.batch is not None:
            binding = next(x for x in meta.inputs if x.role == item.role)
            require(item.batch.kind is binding.kind and item.batch.metadata == binding.metadata, 'integrity_mismatch')
