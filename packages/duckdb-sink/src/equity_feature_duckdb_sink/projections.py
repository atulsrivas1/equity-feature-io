"""Independent SQL projections; complete canonical records remain authoritative."""
from __future__ import annotations

from decimal import Decimal
from typing import cast
from equity_feature_contracts.results import FeatureResult, ValueType
from equity_feature_io_sdk.codec import canonical_json, to_wire
from equity_feature_io_contracts.publication import SinkError, SinkErrorCode

Row = dict[str, object]


def rows(result: FeatureResult, ordinal: int) -> tuple[list[Row], list[Row]]:
    qualities = {(q.entity, q.feature_id): q for q in result.quality}
    cells: list[Row] = []
    for col_ordinal, column in enumerate(result.values):
        for entity_ordinal, (entity, value) in enumerate(zip(column.entities, column.values, strict=True)):
            q = qualities[entity, column.feature_id]
            item: Row = dict(result_ordinal=ordinal, column_ordinal=col_ordinal, entity_ordinal=entity_ordinal,
                             namespace=result.metadata.namespace, instrument_id=entity.instrument_id,
                             session_id=entity.session_id, feature_id=column.feature_id,
                             algorithm_version=column.algorithm_version, dtype=column.dtype.value,
                             unit=column.unit, schema_version=column.schema_version, is_null=value is None,
                             value_int64=None, value_decimal128=None, value_float64=None, value_bool=None,
                             value_utf8=None, value_wire=None, quality_status=q.status.value,
                             quality_expected=q.expected, quality_observed=q.observed,
                             quality_reasons=[reason.value for reason in q.reasons])
            if value is not None:
                if column.dtype is ValueType.INT64:
                    item["value_int64"] = value
                elif column.dtype is ValueType.DECIMAL128:
                    assert type(value) is int
                    item["value_decimal128"] = Decimal(value)
                elif column.dtype is ValueType.FLOAT64:
                    item["value_float64"] = value
                elif column.dtype is ValueType.BOOL:
                    item["value_bool"] = value
                elif column.dtype is ValueType.STRING:
                    item["value_utf8"] = value
                else:
                    item["value_wire"] = canonical_json(to_wire(value))
            cells.append(item)
    evidence: list[Row] = [dict(result_ordinal=ordinal, evidence_ordinal=index, feature_id=e.feature_id,
                                instrument_id=e.entity.instrument_id, session_id=e.entity.session_id,
                                input_id=e.input_id, row_id=e.row_id, event_ns=e.event_ns,
                                known_at_ns=e.known_at_ns, effective_start_ns=e.effective_start_ns,
                                effective_end_ns=e.effective_end_ns, use=e.use,
                                exclusion_reason=None if e.exclusion_reason is None else e.exclusion_reason.value,
                                boundary=e.boundary) for index, e in enumerate(result.evidence)]
    return cells, evidence


def _bound(value: object) -> int:
    if type(value) is str:
        return 6 * len(value.encode("utf-8")) + 64
    if type(value) is bytes:
        return 2 * len(value) + 64
    if type(value) in (tuple, list):
        return 64 + sum(_bound(v) for v in cast(list[object] | tuple[object, ...], value))
    return 128


def admit_projection(result: FeatureResult, remaining: int) -> None:
    # Calculate repetition before allocating the per-cell dictionaries or bundles.
    quality = {(q.entity, q.feature_id): q for q in result.quality}
    size = 256
    for column in result.values:
        header = (result.metadata.namespace, column.feature_id, column.algorithm_version,
                  column.dtype.value, column.unit, column.schema_version)
        for entity, value in zip(column.entities, column.values, strict=True):
            q = quality[entity, column.feature_id]
            size += 4096 + _bound(header) + _bound((entity.instrument_id, entity.session_id))
            size += _bound(tuple(reason.value for reason in q.reasons))
            if column.dtype in (ValueType.INT64, ValueType.DECIMAL128, ValueType.FLOAT64, ValueType.BOOL, ValueType.STRING):
                size += _bound(value)
            else:
                size += 2 * len(canonical_json(to_wire(value))) + 64
            if size > remaining:
                raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
    for e in result.evidence:
        size += 4096 + _bound((e.feature_id, e.entity.instrument_id, e.entity.session_id,
                             e.input_id, e.row_id, e.use, e.boundary))
        if size > remaining:
            raise SinkError(SinkErrorCode.RESOURCE_LIMIT)
    if size > remaining:
        raise SinkError(SinkErrorCode.RESOURCE_LIMIT)


def bundle(data: list[Row], fields: tuple[tuple[str, str], ...]) -> bytes:
    values = tuple(tuple(int(value) if isinstance(value, Decimal) else tuple(cast(list[object], value))
                         if type(value) is list else value.hex() if type(value) is bytes else value
                         for value in (row[name] for name, _ in fields)) for row in data)
    return canonical_json(to_wire(values))


def exact(value: object) -> object:
    if type(value) is float:
        return ("float", value.hex())
    if isinstance(value, Decimal):
        return ("decimal", str(value))
    if type(value) in (tuple, list):
        return tuple(exact(v) for v in cast(list[object] | tuple[object, ...], value))
    return (type(value).__name__, value)
