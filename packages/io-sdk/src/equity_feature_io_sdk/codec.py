"""Closed efio-json1 codec and exact logical identity; no executable decoding."""
from __future__ import annotations

from dataclasses import fields
from enum import StrEnum
from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any, TypeAlias
from types import MappingProxyType

from equity_feature_contracts import inputs as i, results as r, specs as s
from equity_feature_io_contracts.publication import (
    ArtifactReference, CompletionReceipt, FeatureHeader, PublicationEnvelope, PublicationIdentity,
    ResultDescriptor, SinkError, SinkErrorCode,
)

Wire: TypeAlias = None | bool | str | list["Wire"] | dict[str, "Wire"]
# These labels are constants, not import paths supplied by callers.
RECORDS: Mapping[str, type[Any]] = MappingProxyType({
    "results.EntityKey": r.EntityKey, "results.BreadthCounts": r.BreadthCounts,
    "results.BreadthFraction": r.BreadthFraction, "results.IntervalOHLCVRow": r.IntervalOHLCVRow,
    "results.IntervalVolumeShareRow": r.IntervalVolumeShareRow, "results.IntervalOHLCV": r.IntervalOHLCV,
    "results.IntervalVolumeShares": r.IntervalVolumeShares, "results.TopKTradeRow": r.TopKTradeRow,
    "results.TopKTrades": r.TopKTrades, "results.QuoteStateCounts": r.QuoteStateCounts,
    "results.QuoteObservation": r.QuoteObservation, "results.SampledSpread": r.SampledSpread,
    "results.QuoteDurations": r.QuoteDurations, "results.TimeWeightedSpread": r.TimeWeightedSpread,
    "results.FeatureColumn": r.FeatureColumn, "results.QualityRow": r.QualityRow,
    "results.InputBinding": r.InputBinding, "results.ResultMetadata": r.ResultMetadata,
    "results.EvidenceRow": r.EvidenceRow, "results.FeatureResult": r.FeatureResult,
    "inputs.BatchMetadata": i.BatchMetadata, "inputs.SourceBinding": i.SourceBinding,
    "inputs.Coverage": i.Coverage, "inputs.PriceUnit": i.PriceUnit,
    "inputs.AdjustmentSpec": i.AdjustmentSpec, "inputs.InputScope": i.InputScope,
    "inputs.IntervalCoverage": i.IntervalCoverage,
    "specs.AvailabilitySpec": s.AvailabilitySpec, "specs.IntervalSpec": s.IntervalSpec,
})
ENUMS: Mapping[str, type[StrEnum]] = MappingProxyType({
    "results.Status": r.Status, "results.Reason": r.Reason,
    "results.ValueType": r.ValueType, "inputs.DataKind": i.DataKind,
})
_RECORD_NAMES = {value: name for name, value in RECORDS.items()}
_ENUM_NAMES: Mapping[type[Any], str] = {value: name for name, value in ENUMS.items()}


def _string(value: str) -> str:
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    return value


def to_wire(value: object) -> Wire:
    """Encode only canonical closed records and exact inert scalar/sequence types."""
    cls = type(value)
    if cls in _ENUM_NAMES:
        assert isinstance(value, StrEnum)
        return {"enum": _ENUM_NAMES[cls], "value": value.value}
    if value is None or cls is bool:
        assert value is None or isinstance(value, bool)
        return value
    if cls is str:
        assert isinstance(value, str)
        return _string(value)
    if cls is int:
        return {"int": str(value)}
    if cls is float:
        assert isinstance(value, float)
        if not math.isfinite(value):
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        return {"float64": value.hex()}
    if cls in (tuple, list):
        assert isinstance(value, (tuple, list))
        return [to_wire(v) for v in value]
    if cls in _RECORD_NAMES:
        return {"record": _RECORD_NAMES[cls], "fields": {f.name: to_wire(getattr(value, f.name)) for f in fields(value)}}  # type: ignore[arg-type]
    raise SinkError(SinkErrorCode.INVALID_CONTENT)


def canonical_json(value: Wire) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _decode(value: Wire) -> object:
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        assert isinstance(value, str)
        return _string(value)
    if type(value) is list:
        assert isinstance(value, list)
        return tuple(_decode(v) for v in value)
    if type(value) is not dict:
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    assert isinstance(value, dict)
    if set(value) == {"int"}:
        text = value["int"]
        if type(text) is not str or re.fullmatch(r"0|-[1-9][0-9]*|[1-9][0-9]*", text) is None:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        return int(text)
    if set(value) == {"float64"}:
        text = value["float64"]
        if type(text) is not str:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        number = float.fromhex(text)
        if not math.isfinite(number) or number.hex() != text:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        return number
    if set(value) == {"enum", "value"}:
        name, member = value["enum"], value["value"]
        if type(name) is not str or name not in ENUMS or type(member) is not str:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        return ENUMS[name](member)
    if set(value) == {"record", "fields"}:
        name, data = value["record"], value["fields"]
        if type(name) is not str or name not in RECORDS or type(data) is not dict:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(data, dict)
        cls = RECORDS[name]
        if set(data) != {f.name for f in fields(cls)}:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        return cls(**{key: _decode(v) for key, v in data.items()})
    raise SinkError(SinkErrorCode.INVALID_CONTENT)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        result[key] = value
    return result


def encode_result(result: r.FeatureResult) -> bytes:
    try:
        if type(result) is not r.FeatureResult:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        data = canonical_json(to_wire(result))
        # Reconstruction applies canonical constructors even to forged/mutated records.
        reconstructed = _decode(json.loads(data, object_pairs_hook=_pairs))
        if type(reconstructed) is not r.FeatureResult or canonical_json(to_wire(reconstructed)) != data:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        return data
    except Exception:
        raise SinkError(SinkErrorCode.INVALID_CONTENT) from None


def decode_result(data: bytes) -> r.FeatureResult:
    try:
        if type(data) is not bytes:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        value = json.loads(data.decode("ascii"), object_pairs_hook=_pairs)
        result = _decode(value)
        if type(result) is not r.FeatureResult or encode_result(result) != data:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(result, r.FeatureResult)
        return result
    except Exception:
        raise SinkError(SinkErrorCode.INVALID_CONTENT) from None


def descriptor(result: r.FeatureResult) -> ResultDescriptor:
    return ResultDescriptor(result.metadata, tuple(FeatureHeader(c.feature_id, c.algorithm_version, c.dtype, c.unit, c.schema_version) for c in result.values))


def descriptor_wire(value: ResultDescriptor) -> Wire:
    return {"metadata": to_wire(value.metadata), "features": [{f.name: to_wire(getattr(h, f.name)) for f in fields(FeatureHeader)} for h in value.features]}


def identity_wire(identity: PublicationIdentity) -> Wire:
    return {f.name: [descriptor_wire(d) for d in identity.result_descriptors] if f.name == "result_descriptors" else to_wire(getattr(identity, f.name)) for f in fields(PublicationIdentity)}


def idempotency_key(identity: PublicationIdentity) -> str:
    return hashlib.sha256(b"efio-key1\0" + canonical_json(identity_wire(identity))).hexdigest()


def content_digest(results: tuple[r.FeatureResult, ...]) -> str:
    hasher = hashlib.sha256(b"efio-content1\0")
    for result in results:
        data = encode_result(result)
        hasher.update(len(data).to_bytes(8, "big"))
        hasher.update(data)
    return hasher.hexdigest()


_PUBLICATION_RECORDS = (FeatureHeader, ResultDescriptor, PublicationIdentity, PublicationEnvelope, ArtifactReference, CompletionReceipt)


def _publication_wire(value: object) -> Wire:
    if type(value) in _PUBLICATION_RECORDS:
        return {f.name: _publication_wire(getattr(value, f.name)) for f in fields(value)}  # type: ignore[arg-type]
    if type(value) is tuple:
        assert isinstance(value, tuple)
        return [_publication_wire(v) for v in value]
    return to_wire(value)


def _publication_decode(value: Wire, cls: type[Any]) -> Any:
    if type(value) is not dict:
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    assert isinstance(value, dict)
    if set(value) != {f.name for f in fields(cls)}:
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    result: dict[str, Any] = {}
    for key, wire in value.items():
        if key in ("result_descriptors", "features", "artifacts"):
            if type(wire) is not list:
                raise SinkError(SinkErrorCode.INVALID_CONTENT)
            assert isinstance(wire, list)
            child = {"result_descriptors": ResultDescriptor, "features": FeatureHeader, "artifacts": ArtifactReference}[key]
            result[key] = tuple(_publication_decode(v, child) for v in wire)
        elif key == "identity":
            result[key] = _publication_decode(wire, PublicationIdentity)
        else:
            result[key] = _decode(wire)
    return cls(**result)


def encode_envelope(value: PublicationEnvelope) -> bytes:
    if type(value) is not PublicationEnvelope:
        raise SinkError(SinkErrorCode.INVALID_CONFIG)
    wire = _publication_wire(value)
    _wire_versions(wire)
    return canonical_json(wire)


def encode_receipt(value: CompletionReceipt) -> bytes:
    if type(value) is not CompletionReceipt:
        raise SinkError(SinkErrorCode.INVALID_CONFIG)
    wire = _publication_wire(value)
    _wire_versions(wire, receipt=True)
    return canonical_json(wire)


def _wire_versions(value: Wire, *, receipt: bool = False) -> None:
    """Reject unsupported schema declarations BEFORE constructing current records."""
    if type(value) is not dict:
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    assert isinstance(value, dict)
    identity = value.get("identity") if receipt else value
    if type(identity) is not dict:
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    assert isinstance(identity, dict)
    versions = {"protocol_version": "1", "codec_version": "efio-json1", "identity_version": "efio-key1",
                "digest_version": "efio-content1", "canonical_package_version": "0.0.4a4",
                "canonical_schema_version": "1", "math_policy_version": "v1"}
    for field, expected in versions.items():
        if field not in identity or type(identity[field]) is not str:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        if identity[field] != expected:
            raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)
    descriptors = identity.get("result_descriptors")
    if type(descriptors) is not list:
        raise SinkError(SinkErrorCode.INVALID_CONTENT)
    assert isinstance(descriptors, list)
    for descriptor_value in descriptors:
        if type(descriptor_value) is not dict:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(descriptor_value, dict)
        metadata = descriptor_value.get("metadata")
        if type(metadata) is not dict:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(metadata, dict)
        data = metadata.get("fields")
        if type(data) is not dict:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(data, dict)
        for field, expected in (("schema_version", "1"), ("math_policy_version", "v1")):
            if field not in data or type(data[field]) is not str:
                raise SinkError(SinkErrorCode.INVALID_CONTENT)
            if data[field] != expected:
                raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)
        headers = descriptor_value.get("features")
        if type(headers) is not list:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(headers, list)
        for header in headers:
            if type(header) is not dict:
                raise SinkError(SinkErrorCode.INVALID_CONTENT)
            assert isinstance(header, dict)
            if "schema_version" not in header or type(header["schema_version"]) is not str:
                raise SinkError(SinkErrorCode.INVALID_CONTENT)
            if header["schema_version"] != "1":
                raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION)


def decode_envelope(data: bytes) -> PublicationEnvelope:
    try:
        if type(data) is not bytes:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        wire = json.loads(data.decode("ascii"), object_pairs_hook=_pairs)
        _wire_versions(wire)
        value = _publication_decode(wire, PublicationEnvelope)
        if type(value) is not PublicationEnvelope or encode_envelope(value) != data:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(value, PublicationEnvelope)
        return value
    except SinkError as error:
        raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION if error.code is SinkErrorCode.INCOMPATIBLE_VERSION else SinkErrorCode.INVALID_CONTENT) from None
    except Exception:
        raise SinkError(SinkErrorCode.INVALID_CONTENT) from None


def decode_receipt(data: bytes) -> CompletionReceipt:
    try:
        if type(data) is not bytes:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        wire = json.loads(data.decode("ascii"), object_pairs_hook=_pairs)
        _wire_versions(wire, receipt=True)
        value = _publication_decode(wire, CompletionReceipt)
        if type(value) is not CompletionReceipt or encode_receipt(value) != data:
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        assert isinstance(value, CompletionReceipt)
        if value.idempotency_key != idempotency_key(value.identity):
            raise SinkError(SinkErrorCode.INVALID_CONTENT)
        return value
    except SinkError as error:
        raise SinkError(SinkErrorCode.INCOMPATIBLE_VERSION if error.code is SinkErrorCode.INCOMPATIBLE_VERSION else SinkErrorCode.INVALID_CONTENT) from None
    except Exception:
        raise SinkError(SinkErrorCode.INVALID_CONTENT) from None
