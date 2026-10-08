"""Exact bounded JSON numbers; no float rounding or invented notional."""
from collections.abc import Callable
from decimal import Decimal
import json
from typing import cast

from equity_feature_contracts import BatchMetadata, CanonicalBatch, Column, Coverage, DataKind
from equity_feature_contracts.inputs import Cell
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from equity_feature_contracts.validation import validate_batch
from .model import MassiveProfile, DownloadPolicy, MINUTE, fail, stamp

FIELDS=('instrument_id','session_id','start_ns','end_ns','open','high','low','close','volume',
        'trade_count','actual_notional','known_at_ns')
Row=tuple[Cell,...]


def lexical(raw: bytes, policy: DownloadPolicy, check: Callable[[],None]) -> str:
    if len(raw)>policy.max_bytes: fail(SourceErrorCode.LIMIT)
    value=raw.decode('utf-8'); quoted=False; escaped=False; depth=0; structures=0; commas=0
    for ordinal,char in enumerate(value):
        if ordinal%4096==0: check()
        if quoted:
            if escaped: escaped=False
            elif char=='\\': escaped=True
            elif char=='"': quoted=False
        elif char=='"': quoted=True
        elif char in '[{':
            depth+=1; structures+=1
            if depth>policy.max_depth or structures>policy.max_rows+8: fail(SourceErrorCode.LIMIT)
        elif char in ']}': depth-=1
        elif char==',':
            commas+=1
            if commas>policy.max_rows*32+64: fail(SourceErrorCode.LIMIT)
    return value


def coefficient(value: object, scale: int=0) -> int:
    result: int
    if type(value) is int:
        result=value*10**scale
    elif type(value) is Decimal:
        number=value
        if not number.is_finite(): fail()
        sign,digits,exponent=number.as_tuple()
        if type(exponent) is not int or not -128<=exponent<=128 or len(digits)>128:
            fail(SourceErrorCode.LIMIT)
        integer=int(''.join(str(n) for n in digits))*(-1 if sign else 1)
        power=exponent+scale
        if power>=0: result=integer*10**power
        else:
            divisor=10**(-power)
            if integer%divisor: fail(SourceErrorCode.UNSUPPORTED)
            result=integer//divisor
    else: fail()
    stamp(result)
    return result


def decode(raw: bytes, profile: MassiveProfile, policy: DownloadPolicy,
           limit: int, check: Callable[[],None]) -> tuple[Row,...]:
    def decimal(value: str) -> Decimal:
        if len(value)>policy.max_numeric_chars: fail(SourceErrorCode.LIMIT)
        return Decimal(value)

    def integer(value: str) -> int:
        if len(value)>min(20,policy.max_numeric_chars): fail(SourceErrorCode.LIMIT)
        result=int(value); stamp(result); return result

    def pairs(values: list[tuple[str,object]]) -> dict[str,object]:
        if len(values)>32: fail(SourceErrorCode.LIMIT)
        result: dict[str,object]={}
        for key,value in values:
            if key in result: fail()
            result[key]=value
        return result

    def constant(_: str) -> object: fail()

    data: object=json.loads(lexical(raw,policy,check),parse_float=decimal,parse_int=integer,
                           parse_constant=constant,object_pairs_hook=pairs)
    if type(data) is not dict: fail()
    top=cast(dict[str,object],data)
    if (top.get('status')!='OK' or top.get('ticker')!=profile.ticker
            or top.get('adjusted') is not False): fail(SourceErrorCode.UNSUPPORTED)
    if top.get('next_url') is not None: fail(SourceErrorCode.LIMIT)
    records=top.get('results',[])
    if type(records) is not list: fail()
    entries=cast(list[object],records)
    if len(entries)>policy.max_rows: fail(SourceErrorCode.LIMIT)
    count,base=top.get('resultsCount'),top.get('queryCount')
    if type(count) is not int or type(base) is not int:
        fail()
    if base>=limit or count>=limit: fail(SourceErrorCode.LIMIT)
    # Base minute bars and multiplier1 involve no larger-interval regrouping.
    if count!=len(entries) or count!=base: fail()
    if profile.record_known_at_ns is not None and len(profile.record_known_at_ns)!=count: fail()
    rows: list[Row]=[]
    for ordinal,entry in enumerate(entries):
        check()
        if type(entry) is not dict: fail()
        item=cast(dict[str,object],entry); timestamp=item.get('t')
        if type(timestamp) is not int: fail()
        start=timestamp*1_000_000; end=start+MINUTE; stamp(start); stamp(end)
        if start%MINUTE or not profile.scope.start_ns<=start<end<=profile.scope.end_ns:
            fail(SourceErrorCode.UNSUPPORTED)
        prices=tuple(None if item.get(name) is None else coefficient(item[name],9) for name in ('o','h','l','c'))
        volume=coefficient(item.get('v')); trades=None if item.get('n') is None else coefficient(item['n'])
        known=profile.known_at_ns if profile.record_known_at_ns is None else profile.record_known_at_ns[ordinal]
        rows.append((profile.instrument_id,profile.session_id,start,end,*prices,volume,trades,None,known))
    batch=CanonicalBatch(DataKind.BAR,tuple(Column(name,tuple(row[i] for row in rows))
        for i,name in enumerate(FIELDS)),BatchMetadata(profile.namespace,profile.source,
            Coverage(None,len(rows),False),profile.price_unit,scope=profile.scope))
    validate_batch(batch,required_fields=()); check()
    return tuple(rows)


def safe_decode(raw: bytes, profile: MassiveProfile, policy: DownloadPolicy,
                limit: int, check: Callable[[],None]) -> tuple[Row,...]:
    result: tuple[Row,...] | None=None; error=SourceErrorCode.SCHEMA
    try: result=decode(raw,profile,policy,limit,check)
    except SourceError as caught: error=caught.code
    except Exception: pass
    if result is None: fail(error)
    return result
