"""Explicit immutable input governance; constructing profiles performs no I/O."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import NoReturn

from equity_feature_contracts import Coverage, InputScope, PriceUnit, SourceBinding
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_contracts.inputs import I64_MAX, I64_MIN

FIELDS = ("instrument_id", "session_id", "event_ns", "order_key", "event_id",
          "eligible", "price", "size", "known_at_ns")


def fail(code: SourceErrorCode = SourceErrorCode.SCHEMA) -> NoReturn:
    raise SourceError(code, "Local file operation stopped: " + code.value)


def text(value: object) -> None:
    if type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 4096:
        fail()


def stamp(value: object) -> None:
    if type(value) is not int or not I64_MIN <= value <= I64_MAX:
        fail()


def positive(value: int) -> None:
    if type(value) is not int or not 1 <= value <= I64_MAX:
        fail()


@dataclass(frozen=True, repr=False)
class DBNIdentity:
    publisher_id: int
    instrument_id: int
    canonical_id: str

    def __post_init__(self) -> None:
        if type(self.publisher_id) is not int or not 0 <= self.publisher_id <= 65535:
            fail()
        if type(self.instrument_id) is not int or not 0 <= self.instrument_id <= 4294967295:
            fail()
        text(self.canonical_id)


@dataclass(frozen=True, repr=False)
class DBNAnnotation:
    session_id: str
    eligible: bool
    known_at_ns: int | None

    def __post_init__(self) -> None:
        text(self.session_id)
        if type(self.eligible) is not bool:
            fail()
        if self.known_at_ns is not None:
            stamp(self.known_at_ns)


@dataclass(frozen=True, repr=False)
class FileProfile:
    format: str
    namespace: str
    source: SourceBinding
    price_unit: PriceUnit
    coverage: Coverage
    scope: InputScope
    sha256: str
    schema: str = "normalized-trade-v1"
    dbn_dataset: str | None = None
    dbn_identities: tuple[DBNIdentity, ...] = ()
    dbn_annotations: tuple[DBNAnnotation, ...] = ()

    def __post_init__(self) -> None:
        text(self.namespace)
        if (type(self.source) is not SourceBinding or type(self.price_unit) is not PriceUnit
                or type(self.coverage) is not Coverage or type(self.scope) is not InputScope):
            fail()
        if type(self.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            fail()
        if self.format not in ("csv", "parquet", "dbn"):
            fail(SourceErrorCode.UNSUPPORTED)
        if self.scope.include_opening_auction or self.scope.include_closing_auction:
            fail(SourceErrorCode.UNSUPPORTED)
        for name, values, expected in (("dbn_identities", self.dbn_identities, DBNIdentity),
                                       ("dbn_annotations", self.dbn_annotations, DBNAnnotation)):
            if type(values) is not tuple or any(type(v) is not expected for v in values):
                fail()
        keys = tuple((v.publisher_id, v.instrument_id) for v in self.dbn_identities)
        if len(set(keys)) != len(keys):
            fail()
        if self.format == "dbn":
            if self.schema != "dbn3-trades" or self.price_unit.scale != 9:
                fail(SourceErrorCode.UNSUPPORTED)
            if self.dbn_dataset is None:
                fail()
            text(self.dbn_dataset)
            if len(self.dbn_annotations) != self.coverage.observed:
                fail()
        elif (self.schema != "normalized-trade-v1" or self.dbn_dataset is not None
              or self.dbn_identities or self.dbn_annotations):
            fail(SourceErrorCode.UNSUPPORTED)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True,
                              separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ReadPolicy:
    max_bytes: int = 16_777_216
    max_input_rows: int = 100_000
    max_metadata_bytes: int = 1_048_576
    max_decoded_bytes: int = 33_554_432
    read_chunk_bytes: int = 65_536
    decode_batch_rows: int = 1024
    max_batch_rows: int = 1024
    max_elapsed_ns: int = 10_000_000_000

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            positive(value)
        if self.read_chunk_bytes > self.max_bytes or self.max_metadata_bytes > self.max_bytes:
            fail()
