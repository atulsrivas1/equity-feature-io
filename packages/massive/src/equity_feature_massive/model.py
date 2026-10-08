"""Immutable exact population; no acquisition during construction."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import NoReturn

from equity_feature_contracts import Coverage, InputScope, PriceUnit, SourceBinding
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_contracts.inputs import I64_MAX, I64_MIN

MINUTE=60_000_000_000


def fail(code: SourceErrorCode=SourceErrorCode.SCHEMA) -> NoReturn:
    raise SourceError(code,'Massive operation stopped: '+code.value)


def text(value: object) -> None:
    if type(value) is not str or not value.strip() or len(value.encode('utf-8'))>4096:
        fail()


def stamp(value: object) -> None:
    if type(value) is not int or not I64_MIN<=value<=I64_MAX:
        fail()


@dataclass(frozen=True,repr=False)
class MassiveProfile:
    ticker: str
    instrument_id: str
    session_id: str
    namespace: str
    source: SourceBinding
    price_unit: PriceUnit
    scope: InputScope
    coverage: Coverage | None=None
    coverage_policy: str | None=None
    known_at_ns: int | None=None
    record_known_at_ns: tuple[int | None,...] | None=None

    def __post_init__(self) -> None:
        if type(self.ticker) is not str or re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,31}',self.ticker) is None:
            fail()
        for value in (self.instrument_id,self.session_id,self.namespace): text(value)
        if (type(self.source) is not SourceBinding or type(self.price_unit) is not PriceUnit
                or type(self.scope) is not InputScope): fail()
        if (self.price_unit.scale!=9 or self.price_unit.currency!='USD' or self.scope.start_ns%MINUTE or self.scope.end_ns%MINUTE
                or self.scope.include_opening_auction or self.scope.include_closing_auction):
            fail(SourceErrorCode.UNSUPPORTED)
        if self.coverage is not None:
            if type(self.coverage) is not Coverage or self.coverage.complete and self.coverage_policy is None: fail()
        if self.coverage_policy is not None: text(self.coverage_policy)
        if self.known_at_ns is not None: stamp(self.known_at_ns)
        if self.record_known_at_ns is not None:
            if type(self.record_known_at_ns) is not tuple: fail()
            for known in self.record_known_at_ns:
                if known is not None: stamp(known)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True)
class DownloadPolicy:
    max_rows: int=10
    max_bytes: int=524288
    read_chunk_bytes: int=16384
    max_batch_rows: int=1024
    max_elapsed_ns: int=30_000_000_000
    max_depth: int=8
    max_numeric_chars: int=128

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if type(value) is not int or not 1<=value<=I64_MAX: fail()
        if (self.read_chunk_bytes>self.max_bytes or self.max_rows>50000
                or self.max_numeric_chars>128 or self.max_depth>8): fail()
