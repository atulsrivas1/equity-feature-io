"""Bounded original-Parquet historical acquisition outside calculations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from time import perf_counter_ns
from typing import Iterator, cast

import duckdb
from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, CanonicalBatch, Column, Coverage, DataKind, InputScope,
    SessionSpec, SourceBinding,
)
from equity_feature_contracts.adapters import (
    AcquisitionRequest, AdapterBatch, AdapterCapabilities, Cancellation,
    SourceError, SourceErrorCode, require_adapter_capability,
)
from .mapping import MappingPolicy, MappingReport, RowOccurrence, map_columns, parse_utc_ns
from .resolver import (ResolvedPartition, ResolvedSource, SourceSelection,
                       _absolute, _cancel, _count, _date, _fail, _hash, _text)
from .evidence import AcquisitionReceipt, VerificationPolicy, _begin_observation, _digest


def _create_utc_parser(con: duckdb.DuckDBPyConnection) -> None:
    """Connection-local exact ASCII UTCns arithmetic; no Python row callbacks."""
    con.execute(r"""
        CREATE TEMP MACRO canonical_utc_ns(v) AS
        CASE WHEN v IS NOT NULL
            AND regexp_full_match(v, '[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?(Z|\+00:00)')
            AND try_cast(substr(v, 1, 10) AS DATE) IS NOT NULL
            AND try_cast(substr(v, 1, 4) AS INTEGER) BETWEEN 1 AND 9999
            AND try_cast(substr(v, 12, 2) AS INTEGER) BETWEEN 0 AND 23
            AND try_cast(substr(v, 15, 2) AS INTEGER) BETWEEN 0 AND 59
            AND try_cast(substr(v, 18, 2) AS INTEGER) BETWEEN 0 AND 59
        THEN coalesce(try_cast(
            (cast(date_diff('day', DATE '1970-01-01', try_cast(substr(v, 1, 10) AS DATE)) AS HUGEINT) * 86400
             + cast(substr(v, 12, 2) AS HUGEINT) * 3600
             + cast(substr(v, 15, 2) AS HUGEINT) * 60
             + cast(substr(v, 18, 2) AS HUGEINT)) * 1000000000
             + cast(rpad(regexp_extract(v, '\.([0-9]{1,9})', 1), 9, '0') AS HUGEINT)
            AS BIGINT), error('Timestamp outside int64'))
        ELSE error('Exact UTC timestamp required') END
    """)


@dataclass(frozen=True)
class CoverageAssertion:
    instruments: tuple[str, ...]
    sessions: tuple[str, ...]
    start_ns: int
    end_ns: int
    expected_rows: int
    policy_id: str

    def __post_init__(self) -> None:
        for name in ("instruments", "sessions"):
            values = getattr(self, name)
            if type(values) not in (tuple, list) or not values:
                _fail("Unique concrete coverage identities required")
            for value in values:
                _text(value)
            if len(set(values)) != len(values):
                _fail("Unique coverage identities required")
            object.__setattr__(self, name, tuple(values))
        if type(self.start_ns) is not int or type(self.end_ns) is not int:
            _fail("Exact UTCns coverage bounds required")
        parse_utc_ns(self.start_ns)
        parse_utc_ns(self.end_ns)
        if self.start_ns >= self.end_ns:
            _fail("Positive coverage interval required")
        _count(self.expected_rows)
        _text(self.policy_id)


@dataclass(frozen=True)
class ReadConfig:
    catalog_path: Path
    resolved: ResolvedSource
    mapping: MappingPolicy
    namespace: str
    source_id: str
    calendar_version: str
    sessions: tuple[SessionSpec, ...]
    partition_sessions: tuple[tuple[str, str], ...]
    scope: InputScope
    coverage_assertion: CoverageAssertion | None = None
    max_files: int = 4096
    max_batch_rows: int = 1024
    threads: int = 1
    memory_limit_mb: int = 256
    verification: VerificationPolicy = VerificationPolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.catalog_path, Path) or not self.catalog_path.is_absolute():
            _fail("Explicit absolute catalog Path required")
        if type(self.resolved) is not ResolvedSource or type(self.mapping) is not MappingPolicy or type(self.scope) is not InputScope:
            _fail("Typed resolved source/mapping/scope required")
        if type(self.verification) is not VerificationPolicy:
            _fail("Typed verification policy required")
        for value in (self.namespace, self.source_id, self.calendar_version):
            _text(value)
        for bound in (self.max_files, self.max_batch_rows, self.threads, self.memory_limit_mb):
            _count(bound, positive=True)
        if type(self.resolved.selection) is not SourceSelection or type(self.resolved.partitions) not in (tuple, list) or type(self.resolved.missing_sessions) not in (tuple, list):
            _fail("Owned resolved records required")
        if _hash(self.resolved.identity_digest) is None:
            _fail("Resolved identity digest required")
        for partition in self.resolved.partitions:
            if type(partition) is not ResolvedPartition or _date(partition.session) not in self.resolved.selection.sessions:
                _fail("Typed selected partition required")
            _absolute(partition.original_path)
            _count(partition.original_bytes)
            _count(partition.declared_rows)
        for missing in self.resolved.missing_sessions:
            if _date(missing) not in self.resolved.selection.sessions:
                _fail("Selected missing partition required")
        object.__setattr__(self, "resolved", replace(self.resolved, partitions=tuple(self.resolved.partitions),
                                                     missing_sessions=tuple(self.resolved.missing_sessions)))
        if self.mapping.source_schema != self.resolved.selection.source_schema:
            _fail("Resolved mapping schema conflict")
        if self.mapping.eligibility_policy is not None and self.mapping.eligibility_policy != self.scope.eligibility_policy:
            _fail("Scope and mapping eligibility conflict")
        if self.scope.include_opening_auction or self.scope.include_closing_auction:
            _fail("Auction acquisition unsupported", SourceErrorCode.UNSUPPORTED)
        if type(self.sessions) not in (tuple, list) or not self.sessions or any(type(x) is not SessionSpec for x in self.sessions):
            _fail("Concrete governed sessions required")
        ordered = sorted(self.sessions, key=lambda s: s.open_ns)
        if len({x.session_id for x in ordered}) != len(ordered):
            _fail("Unique governed sessions required")
        for i, session in enumerate(ordered):
            if session.namespace != self.namespace or session.open_ns < self.scope.start_ns or session.close_ns > self.scope.end_ns:
                _fail("Session namespace/scope conflict")
            if session.include_opening_auction or session.include_closing_auction:
                _fail("Auction acquisition unsupported", SourceErrorCode.UNSUPPORTED)
            if i and ordered[i-1].close_ns > session.open_ns:
                _fail("Overlapping governed sessions")
        object.__setattr__(self, "sessions", tuple(ordered))
        if type(self.partition_sessions) not in (tuple, list):
            _fail("Concrete partition session mapping required")
        pairs: list[tuple[str, str]] = []
        for pair in self.partition_sessions:
            if type(pair) not in (tuple, list) or len(pair) != 2:
                _fail("Explicit partition session pair required")
            pairs.append((_date(pair[0]), _text(pair[1])))
        if len({p for p, _ in pairs}) != len(pairs) or set(p for p, _ in pairs) != set(self.resolved.selection.sessions):
            _fail("Exact selected partition session mapping required")
        if any(s not in {x.session_id for x in ordered} for _, s in pairs):
            _fail("Unknown governed partition session")
        object.__setattr__(self, "partition_sessions", tuple(pairs))
        if self.coverage_assertion is not None and type(self.coverage_assertion) is not CoverageAssertion:
            _fail("Typed coverage assertion required")


@dataclass(frozen=True)
class ReadMetrics:
    sql_fetch_ns: int
    mapping_ns: int
    delivery_copy_ns: int
    delivered_rows: int
    files: int
    selected_file_bytes: int
    canonical_cells: int
    batches: int
    verification_ns: int = 0
    verification_hash_bytes: int = 0


@dataclass(frozen=True)
class ReadResult:
    canonical: CanonicalBatch | None
    batches: tuple[AdapterBatch, ...]
    metrics: ReadMetrics
    mapping_report: MappingReport | None = None
    receipt: AcquisitionReceipt | None = None


class DuckDBHistoricalAdapter:
    def __init__(self, config: ReadConfig) -> None:
        if type(config) is not ReadConfig:
            _fail("Typed read config required")
        self.config = config

    def capabilities(self) -> AdapterCapabilities:
        config = self.config
        kind = {"trades": DataKind.TRADE, "tbbo": DataKind.QUOTE,
                "ohlcv-1m": DataKind.BAR, "ohlcv-1d": DataKind.DAILY}[config.mapping.source_schema]
        return AdapterCapabilities((kind,), (config.namespace,), (config.mapping.price_unit,),
            sampling=("trade_snapshot",) if kind == DataKind.QUOTE else ("none",),
            max_batch_rows=config.max_batch_rows)

    def read(self, request: AcquisitionRequest, cancellation: Cancellation | None = None) -> ReadResult:
        config = self.config
        _cancel(cancellation)
        try:
            require_adapter_capability(self.capabilities(), request)
        except SourceError as error:
            _fail("Request capability validation failed", error.code)
        if request.snapshot_id != config.resolved.selection.snapshot or request.adjustment != AdjustmentSpec():
            _fail("Unsupported source snapshot/adjustment", SourceErrorCode.UNSUPPORTED)
        sessions = {x.session_id: x for x in config.sessions}
        instruments = {canonical: original for original, canonical in config.mapping.instrument_ids}
        if any(x not in sessions for x in request.sessions) or any(x not in instruments for x in request.instruments):
            _fail("Requested identity unavailable", SourceErrorCode.UNAVAILABLE)
        if request.start_ns < config.scope.start_ns or request.end_ns > config.scope.end_ns:
            _fail("Request outside governed source scope", SourceErrorCode.UNSUPPORTED)
        if not config.catalog_path.is_file():
            _fail("Source catalog unavailable", SourceErrorCode.UNAVAILABLE)
        partition_sessions = dict(config.partition_sessions)
        selected = tuple(p for p in config.resolved.partitions if partition_sessions[p.session] in request.sessions)
        if len(selected) > config.max_files:
            _fail("Read file limit exceeded", SourceErrorCode.LIMIT)
        verification_start = perf_counter_ns()
        observation = _begin_observation(config.catalog_path, config.resolved, selected, config.verification, cancellation)
        verification_ns = perf_counter_ns()-verification_start
        request_digest = _digest(asdict(request))
        configuration = asdict(config)
        configuration["catalog_path"] = str(config.catalog_path)
        configuration_digest = _digest(configuration)
        identity = _digest(dict(version="original-read2", request=request_digest,
            configuration=configuration_digest, catalog=observation.catalog_sha256,
            files=[asdict(f) for f in observation.files]))
        source = SourceBinding(config.source_id, request.snapshot_id, "original-read2:"+identity, "request:"+identity)
        def receipt(binding: SourceBinding, coverage: Coverage, report: MappingReport | None,
                    disposition: str, rows: int) -> AcquisitionReceipt:
            return AcquisitionReceipt(request_digest, configuration_digest, config.resolved.identity_digest,
                identity, observation.catalog_sha256, observation.files, config.resolved.missing_sessions,
                binding, report, coverage, request.availability, config.calendar_version, disposition,
                rows, observation.pin_strength, observation.hash_bytes)
        if any(partition_sessions[d] in request.sessions for d in config.resolved.missing_sessions):
            verification_start = perf_counter_ns()
            observation.finish()
            verification_ns += perf_counter_ns()-verification_start
            envelope = AdapterBatch(request.request_id, 0, True, source, Coverage(None, 0, False),
                                    Coverage(None, 0, False), None, "missing", "Selected source partition missing")
            return ReadResult(None, (envelope,), ReadMetrics(0, 0, 0, 0, 0, 0, 0, 1,
                verification_ns, observation.hash_bytes), receipt=receipt(source, envelope.source_coverage, None, "missing", 0))
        start = perf_counter_ns()
        # All values are owned in this bounded collection before any envelope is exposed.
        acquired: list[tuple[int, int, int, str, tuple[object, ...]]] = []
        names: tuple[str, ...] | None = None
        file_bytes = 0
        maximum = min(request.max_rows, config.mapping.max_rows)
        prices = ("price",) if request.kind == DataKind.TRADE else ("bid", "ask") if request.kind == DataKind.QUOTE else ("open", "high", "low", "close")
        quantities = ("size",) if request.kind == DataKind.TRADE else ("bid_size", "ask_size") if request.kind == DataKind.QUOTE else ("volume",)
        permitted = ("instrument_id", "ts_utc", *prices, *quantities, "eligible", "condition", "known_at_ns", "symbol", "tick_rule_sign")
        interval = (60 if request.kind == DataKind.BAR else 86400) * 10**9 if request.kind in (DataKind.BAR, DataKind.DAILY) else 0
        try:
            with duckdb.connect(str(config.catalog_path), read_only=True,
                                config={"threads": config.threads, "memory_limit": f"{config.memory_limit_mb}MB"}) as con:
                _create_utc_parser(con)
                for file_index, partition in enumerate(selected):
                    _cancel(cancellation)
                    path = partition.original_path
                    if not Path(path).is_absolute() or any(c in path for c in "*?[]{}"):
                        _fail("Exact original local file required")
                    try:
                        size = Path(path).stat().st_size
                    except OSError:
                        _fail("Original source file unavailable", SourceErrorCode.UNAVAILABLE)
                    if size != partition.original_bytes:
                        _fail("Original source file size changed")
                    file_bytes += size
                    schema = con.execute("DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [path]).fetchall()
                    fields = {str(row[0]): str(row[1]) for row in schema}
                    if fields.get("ts_utc") != "VARCHAR" or "instrument_id" not in fields or "file_row_number" in fields:
                        _fail("Original retained source schema mismatch")
                    current_names = tuple(n for n in permitted if n in fields)
                    if names is None:
                        names = current_names
                    elif names != current_names:
                        _fail("Mixed original file columns unsupported")
                    count = con.execute("SELECT num_rows FROM parquet_file_metadata(?)", [path]).fetchone()
                    if count is None or _count(count[0]) != partition.declared_rows:
                        _fail("Original catalog row count mismatch")
                    session_id = partition_sessions[partition.session]
                    session = sessions[session_id]
                    lower = max(request.start_ns, session.open_ns)
                    upper = min(request.end_ns, session.close_ns)
                    if lower >= upper or (interval and upper-lower < interval):
                        continue
                    comparison = "<=?" if interval else "<?"
                    projection = ",".join('"'+n+'"' for n in current_names)
                    placeholders = ",".join("?" for _ in request.instruments)
                    sql = (f"SELECT {projection},file_row_number,canonical_utc_ns(ts_utc) FROM read_parquet(?,file_row_number=true,hive_partitioning=false) "
                           f"WHERE instrument_id IN ({placeholders}) AND canonical_utc_ns(ts_utc)>=? AND canonical_utc_ns(ts_utc){comparison} "
                           "ORDER BY canonical_utc_ns(ts_utc),file_row_number LIMIT ?")
                    values = [path, *(instruments[x] for x in request.instruments), lower, upper-interval if interval else upper, maximum-len(acquired)+1]
                    cursor = con.execute(sql, values)
                    while True:
                        _cancel(cancellation)
                        rows = cursor.fetchmany(min(request.max_batch_rows, maximum+1))
                        if not rows:
                            break
                        for row in rows:
                            acquired.append((cast(int, row[-1]), file_index, _count(row[-2]), session_id, tuple(row[:-2])))
                        if len(acquired) > maximum:
                            _fail("Read row limit exceeded", SourceErrorCode.LIMIT)
        except SourceError:
            raise
        except (duckdb.Error, OSError, ValueError, OverflowError):
            _fail("Original source read failed")
        query_ns = perf_counter_ns()-start
        _cancel(cancellation)
        verification_start = perf_counter_ns()
        observation.finish()
        verification_ns += perf_counter_ns()-verification_start
        start = perf_counter_ns()
        acquired.sort(key=lambda row: row[:3])
        count_rows = len(acquired)
        chunks = max(1, (count_rows+request.max_batch_rows-1)//request.max_batch_rows)
        if chunks > request.max_batches:
            _fail("Read batch limit exceeded", SourceErrorCode.LIMIT)
        coverage = Coverage(None, count_rows, False)
        claim = config.coverage_assertion
        if claim is not None:
            if (set(claim.instruments), set(claim.sessions), claim.start_ns, claim.end_ns) != (set(request.instruments), set(request.sessions), request.start_ns, request.end_ns):
                _fail("Coverage assertion request mismatch")
            if claim.expected_rows != count_rows:
                _fail("Coverage assertion observed count mismatch")
            coverage = Coverage(claim.expected_rows, count_rows, True)
        names = names or ("instrument_id", "ts_utc")
        columns: dict[str, tuple[object, ...] | list[object]] = {n: tuple(row[4][i] for row in acquired) for i, n in enumerate(names)}
        occurrences = tuple(RowOccurrence(hashlib.sha256(json.dumps([config.resolved.identity_digest, selected[row[1]].original_path, observation.files[row[1]].observed_original_sha256]).encode()).hexdigest(), row[2], i) for i, row in enumerate(acquired))
        scope = InputScope(request.start_ns, request.end_ns, config.scope.eligibility_policy)
        metadata = BatchMetadata(config.namespace, source, coverage, request.price_unit,
                                 adjustment=request.adjustment, sampling=request.sampling, scope=scope)
        mapped = map_columns(config.mapping, columns, metadata=metadata, occurrences=occurrences,
                             sessions=tuple(row[3] for row in acquired))
        mapping_ns = perf_counter_ns()-start
        _cancel(cancellation)
        start = perf_counter_ns()
        envelopes: list[AdapterBatch] = []
        for ordinal in range(chunks):
            _cancel(cancellation)
            begin = ordinal*request.max_batch_rows
            end = min(count_rows, begin+request.max_batch_rows)
            binding = replace(mapped.batch.metadata.source, input_id=mapped.batch.metadata.source.input_id+f":chunk:{ordinal}:{begin}:{end}")
            batch = CanonicalBatch(mapped.batch.kind, tuple(Column(c.name, c.values[begin:end]) for c in mapped.batch.columns), replace(mapped.batch.metadata, source=binding))
            envelopes.append(AdapterBatch(request.request_id, ordinal, ordinal == chunks-1, binding, coverage,
                                          Coverage(end-begin, end-begin, True), batch))
        copying_ns = perf_counter_ns()-start
        metrics = ReadMetrics(query_ns, mapping_ns, copying_ns, count_rows, len(selected), file_bytes,
                              len(mapped.batch.columns)*count_rows, chunks, verification_ns, observation.hash_bytes)
        return ReadResult(mapped.batch, tuple(envelopes), metrics, mapped.report,
                          receipt(mapped.batch.metadata.source, coverage, mapped.report, "data", count_rows))

    def iter_batches(self, request: AcquisitionRequest, cancellation: Cancellation) -> Iterator[AdapterBatch]:
        result = self.read(request, cancellation)
        for envelope in result.batches:
            _cancel(cancellation)
            yield envelope
