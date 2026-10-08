"""Verified fixed-host GET; one call, finite body/time, no automatic operations."""
import http.client
import ssl
from collections.abc import Callable
from typing import Protocol

from equity_feature_acquisition import AttemptBudget, AttemptFailure
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from .model import DownloadPolicy, fail


class MassiveTransport(Protocol):
    def __call__(self, path: str, credential: str | None, budget: AttemptBudget,
                 check: Callable[[],None]) -> bytes: ...


class HTTPSMassiveTransport:
    def __init__(self,policy: DownloadPolicy,clock_ns: Callable[[],int]) -> None:
        self._policy,self._clock=policy,clock_ns

    def __repr__(self) -> str: return 'HTTPSMassiveTransport(<opaque>)'

    def __call__(self,path: str,credential: str | None,budget: AttemptBudget,
                 check: Callable[[],None]) -> bytes:
        raw=bytearray(); connection: http.client.HTTPSConnection | None=None
        code=SourceErrorCode.TRANSPORT; success=False
        try:
            check()
            if type(credential) is not str or not credential: fail(SourceErrorCode.AUTHENTICATION)
            remaining=budget.deadline_ns-self._clock()
            if remaining<=0: fail(SourceErrorCode.LIMIT)
            connection=http.client.HTTPSConnection('api.massive.com',timeout=remaining/1e9,
                                                  context=ssl.create_default_context())
            connection.connect(); socket=connection.sock

            def refresh() -> None:
                check(); remaining=budget.deadline_ns-self._clock()
                if remaining<=0: fail(SourceErrorCode.LIMIT)
                connection.timeout=remaining/1e9
                if socket is not None: socket.settimeout(remaining/1e9)

            refresh(); connection.request('GET',path,headers={'Authorization':'Bearer '+credential,
                                                             'Accept-Encoding':'identity'})
            refresh(); response=connection.getresponse(); status=response.status
            if 300<=status<400: fail(SourceErrorCode.UNSUPPORTED)
            if status==401: fail(SourceErrorCode.AUTHENTICATION)
            if status==403: fail(SourceErrorCode.ENTITLEMENT)
            if status==404: fail(SourceErrorCode.UNAVAILABLE)
            if status==429: fail(SourceErrorCode.RATE_LIMIT)
            if status!=200: fail(SourceErrorCode.TRANSPORT)
            if response.getheader('Content-Encoding','identity') not in ('identity','none',''):
                fail(SourceErrorCode.UNSUPPORTED)
            cap=min(self._policy.max_bytes,budget.remaining_bytes)
            declared=response.getheader('Content-Length')
            if declared is not None and (not declared.isdecimal() or int(declared)>cap):
                fail(SourceErrorCode.LIMIT)
            while True:
                refresh(); chunk=response.read(min(self._policy.read_chunk_bytes,cap-len(raw)+1))
                if not chunk: break
                raw.extend(chunk)
                if len(raw)>cap: fail(SourceErrorCode.LIMIT)
            refresh()
            if declared is not None and len(raw)!=int(declared): fail()
            success=True
        except SourceError as caught: code=caught.code
        except http.client.IncompleteRead as caught:
            raw.extend(caught.partial)
            if len(raw)>min(self._policy.max_bytes,budget.remaining_bytes): code=SourceErrorCode.LIMIT
        except Exception: pass
        finally:
            if connection is not None:
                try: connection.close()
                except Exception: pass
        if not success: raise AttemptFailure(code,received_bytes=len(raw))
        return bytes(raw)
