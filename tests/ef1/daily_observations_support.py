"""Original synthetic frozen daily packets; no source discovery or feature math."""
import hashlib
import json
from pathlib import Path
from equity_feature_contracts import (
    AdjustmentSpec, BatchMetadata, CanonicalBatch, Column, Coverage, DataKind, InputScope, IntervalCoverage,
    PriceUnit, SourceBinding,
)
from equity_feature_duckdb.ef1 import DailyObservationsInputs, make_daily_observations_batch

PACKETS = Path(__file__).with_name('daily_observations_contract_packets.json')
PACKET_SHA = '479948037cd6d2fca3901cdb9cf3fcbba6256acbbcb9440bcd68e0362d7688c5'


def packets():
    raw = PACKETS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PACKET_SHA
    return json.loads(raw)['packets']


def original_batch(raw, *, convert=True):
    if raw is None:
        return None
    assert raw['kind'] == 'reference'
    m = dict(raw['metadata'])
    for key, cls in (('source', SourceBinding), ('coverage', Coverage),
                     ('adjustment', AdjustmentSpec), ('price_unit', PriceUnit), ('scope', InputScope)):
        m[key] = None if m[key] is None else cls(**m[key])
    m['interval_coverage'] = tuple(IntervalCoverage(**{**v, 'coverage': Coverage(**v['coverage'])})
                                 for v in m['interval_coverage'])
    columns = raw['columns']
    if not convert:
        return CanonicalBatch(DataKind.REFERENCE,tuple(Column(c['name'],tuple(c['values'])) for c in columns),BatchMetadata(**m))
    return make_daily_observations_batch(tuple(c['name'] for c in columns),
        tuple(zip(*(c['values'] for c in columns))), metadata=BatchMetadata(**m))


def packet_inputs(packet):
    # Preserve actual supplied positional order, including the wrong-slot control.
    slots = tuple(original_batch(slot['batch']) for slot in packet['role_slots'])
    return DailyObservationsInputs(*slots, tuple('unavailable' if b is None else 'synthetic' for b in slots))
