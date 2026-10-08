"""Immutable caller mapping; construction never acquires data."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import NoReturn

from equity_feature_contracts import Coverage, InputScope, PriceUnit, SourceBinding
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_contracts.inputs import I64_MAX, I64_MIN


def fail(code: SourceErrorCode = SourceErrorCode.SCHEMA) -> NoReturn:
    raise SourceError(code, "Databento operation stopped: " + code.value)


def text(value: object) -> None:
    if type(value) is not str or not value.strip() or len(value.encode('utf-8')) > 4096:
        fail()


def stamp(value: object) -> None:
    if type(value) is not int or not I64_MIN <= value <= I64_MAX:
        fail()


@dataclass(frozen=True, repr=False)
class InstrumentBinding:
    publisher_id: int
    instrument_id: int
    canonical_id: str
    session_id: str
    eligible: bool
    known_at_ns: int | None = None

    def __post_init__(self) -> None:
        if type(self.publisher_id) is not int or not 0 <= self.publisher_id <= 65535:
            fail()
        if type(self.instrument_id) is not int or not 0 <= self.instrument_id < 4294967295:
            fail()
        text(self.canonical_id); text(self.session_id)
        if type(self.eligible) is not bool:
            fail()
        if self.known_at_ns is not None:
            stamp(self.known_at_ns)


@dataclass(frozen=True, repr=False)
class DatabentoProfile:
    dataset: str
    schema: str
    namespace: str
    source: SourceBinding
    price_unit: PriceUnit
    event_scope: InputScope
    capture_start_ns: int
    capture_end_ns: int
    bindings: tuple[InstrumentBinding, ...]
    coverage: Coverage | None = None
    coverage_policy: str | None = None
    known_at_ns: tuple[int | None, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.dataset) is not str or re.fullmatch(r'[A-Z0-9]{2,16}\.[A-Z0-9_-]{1,16}', self.dataset) is None:
            fail()
        if self.schema not in ('trades', 'ohlcv-1m'):
            fail(SourceErrorCode.UNSUPPORTED)
        text(self.namespace)
        if (type(self.source) is not SourceBinding or type(self.price_unit) is not PriceUnit
                or type(self.event_scope) is not InputScope):
            fail()
        if self.price_unit.scale != 9 or self.event_scope.include_opening_auction or self.event_scope.include_closing_auction:
            fail(SourceErrorCode.UNSUPPORTED)
        stamp(self.capture_start_ns); stamp(self.capture_end_ns)
        if self.capture_start_ns >= self.capture_end_ns:
            fail()
        if type(self.bindings) is not tuple or not 1 <= len(self.bindings) <= 512 or any(type(b) is not InstrumentBinding for b in self.bindings):
            fail()
        keys = tuple((b.publisher_id,b.instrument_id) for b in self.bindings)
        if len(set(keys)) != len(keys):
            fail()
        if self.coverage is not None:
            if type(self.coverage) is not Coverage:
                fail()
            if self.coverage.complete and self.coverage_policy is None:
                fail()
        if self.coverage_policy is not None:
            text(self.coverage_policy)
        if self.known_at_ns is not None:
            if type(self.known_at_ns) is not tuple:
                fail()
            for value in self.known_at_ns:
                if value is not None:
                    stamp(value)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True)
class DownloadPolicy:
    max_rows: int = 10
    max_bytes: int = 524288
    max_metadata_bytes: int = 65536
    read_chunk_bytes: int = 16384
    max_batch_rows: int = 1024
    max_elapsed_ns: int = 30_000_000_000

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if type(value) is not int or not 1 <= value <= I64_MAX:
                fail()
        if self.max_metadata_bytes > self.max_bytes or self.read_chunk_bytes > self.max_bytes:
            fail()
