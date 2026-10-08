"""Exact DBN3 records; no network, timestamps or population inference."""
from __future__ import annotations

from collections.abc import Callable
import importlib
from importlib.metadata import version
from typing import Protocol, cast

from equity_feature_contracts.inputs import Cell, I64_MAX
from equity_feature_contracts import BatchMetadata, CanonicalBatch, Column, Coverage, DataKind
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_contracts.validation import validate_batch
from .model import DatabentoProfile, DownloadPolicy, fail, stamp

TRADE_FIELDS = ('instrument_id','session_id','event_ns','order_key','event_id','eligible','price','size','known_at_ns')
BAR_FIELDS = ('instrument_id','session_id','start_ns','end_ns','open','high','low','close','volume','trade_count','actual_notional','known_at_ns')


class _Decoder(Protocol):
    def write(self, data: bytes) -> None: ...
    def decode(self) -> list[object]: ...
    def buffer(self) -> bytes: ...


class _Metadata(Protocol):
    version: int
    dataset: str
    schema: str | None
    ts_out: bool
    start: int
    end: int | None
    partial: list[str]
    not_found: list[str]
    stype_in: str | None
    stype_out: str | None


class _Record(Protocol):
    publisher_id: int
    instrument_id: int
    ts_event: int


class _Trade(_Record, Protocol):
    ts_recv: int
    price: int
    size: int
    sequence: int
    action: str


class _Bar(_Record, Protocol):
    rtype: object
    open: int
    high: int
    low: int
    close: int
    volume: int


def layout(raw: bytes, schema: str) -> tuple[int, int, int]:
    if len(raw) < 8 or raw[:4] != b'DBN\x03':
        fail(SourceErrorCode.UNSUPPORTED)
    metadata = 8 + int.from_bytes(raw[4:8], 'little')
    size = 48 if schema == 'trades' else 56
    if metadata > len(raw) or metadata < 8 or (len(raw)-metadata) % size:
        fail()
    return metadata, size, (len(raw)-metadata)//size


def decode(raw: bytes, profile: DatabentoProfile, policy: DownloadPolicy,
           check: Callable[[], None]) -> tuple[tuple[Cell, ...], ...]:
    metadata_bytes, size, count = layout(raw, profile.schema)
    if len(raw) > policy.max_bytes or metadata_bytes > policy.max_metadata_bytes or count > policy.max_rows:
        fail(SourceErrorCode.LIMIT)
    if profile.known_at_ns is not None and len(profile.known_at_ns) != count:
        fail()
    module: object | None = None
    try:
        if version('databento-dbn') == '0.70.0':
            module = importlib.import_module('databento_dbn')
    except Exception:
        pass
    if module is None:
        fail(SourceErrorCode.UNSUPPORTED)
    constructor = cast(Callable[..., _Decoder], getattr(module,'DBNDecoder'))
    decoder = constructor(upgrade_policy=getattr(getattr(module,'VersionUpgradePolicy'),'AS_IS'))
    decoder.write(raw[:metadata_bytes]); values = decoder.decode()
    if len(values) != 1 or not isinstance(values[0], cast(type[object],getattr(module,'Metadata'))) or decoder.buffer():
        fail()
    meta = cast(_Metadata, values[0])
    if (meta.version != 3 or meta.schema != profile.schema or meta.dataset != profile.dataset
            or meta.ts_out or str(meta.stype_in) != 'instrument_id' or str(meta.stype_out) != 'instrument_id'
            or meta.start != profile.capture_start_ns or meta.end != profile.capture_end_ns):
        fail(SourceErrorCode.UNSUPPORTED)
    if meta.partial or meta.not_found:
        fail(SourceErrorCode.UNAVAILABLE)
    mappings = {(b.publisher_id,b.instrument_id):b for b in profile.bindings}
    result: list[tuple[Cell, ...]] = []
    indices: list[int] = []
    record_type = cast(type[object], getattr(module,'TradeMsg' if profile.schema == 'trades' else 'OHLCVMsg'))
    for ordinal in range(count):
        check(); offset = metadata_bytes+ordinal*size
        if raw[offset]*4 != size:
            fail(SourceErrorCode.UNSUPPORTED)
        decoder.write(raw[offset:offset+size]); values = decoder.decode()
        if len(values) != 1 or not isinstance(values[0],record_type) or decoder.buffer():
            fail(SourceErrorCode.UNSUPPORTED)
        item = cast(_Record,values[0]); binding = mappings.get((item.publisher_id,item.instrument_id))
        if binding is None:
            fail()
        stamp(item.ts_event)
        known = binding.known_at_ns if profile.known_at_ns is None else profile.known_at_ns[ordinal]
        if profile.schema == 'trades':
            trade = cast(_Trade,item)
            stamp(trade.ts_recv); stamp(trade.sequence); stamp(trade.price); stamp(trade.size)
            if (not profile.capture_start_ns <= trade.ts_recv < profile.capture_end_ns
                    or trade.action != 'T' or trade.price == I64_MAX or trade.size == 4294967295):
                fail()
            event_id = f'databento:{item.publisher_id}:{item.instrument_id}:{item.ts_event}:{trade.sequence}'
            row: tuple[Cell,...] = (binding.canonical_id,binding.session_id,item.ts_event,trade.sequence,event_id,
                                    binding.eligible,trade.price,trade.size,known)
            selected = profile.event_scope.start_ns <= item.ts_event < profile.event_scope.end_ns
        else:
            bar = cast(_Bar,item); end = item.ts_event+60_000_000_000; stamp(end); stamp(bar.volume)
            if str(bar.rtype) != 'ohlcv-1m':
                fail(SourceErrorCode.UNSUPPORTED)
            if not profile.capture_start_ns <= item.ts_event < profile.capture_end_ns:
                fail()
            prices: list[int | None] = []
            for value in (bar.open,bar.high,bar.low,bar.close):
                stamp(value); prices.append(None if value == I64_MAX else value)
            row = (binding.canonical_id,binding.session_id,item.ts_event,end,*prices,bar.volume,None,None,known)
            selected = profile.event_scope.start_ns <= item.ts_event < end <= profile.event_scope.end_ns
        if selected:
            indices.append(ordinal)
        result.append(row)
    kind = DataKind.TRADE if profile.schema == 'trades' else DataKind.BAR
    fields = TRADE_FIELDS if kind == DataKind.TRADE else BAR_FIELDS
    received = CanonicalBatch(kind, tuple(Column(name, tuple(r[i] for r in result))
        for i,name in enumerate(fields)), BatchMetadata(profile.namespace,profile.source,
            Coverage(None,len(result),False),profile.price_unit))
    validate_batch(received,required_fields=())
    check()
    return tuple(result[i] for i in indices)


def safe_decode(raw: bytes, profile: DatabentoProfile, policy: DownloadPolicy,
                check: Callable[[], None]) -> tuple[tuple[Cell, ...], ...]:
    rows: tuple[tuple[Cell,...],...] | None = None
    error = SourceErrorCode.SCHEMA
    try:
        rows = decode(raw,profile,policy,check)
    except SourceError as caught:
        error = caught.code
    except Exception:
        pass
    if rows is None:
        fail(error)
    return rows
