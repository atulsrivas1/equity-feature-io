"""Fixed-host bounded HTTPS; no redirects, retries or credential discovery."""
from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
import http.client
import ssl
from typing import Protocol
from urllib.parse import urlencode

from equity_feature_acquisition import AttemptBudget, AttemptFailure, Page
from equity_feature_contracts.adapters import SourceError, SourceErrorCode
from .codec import layout
from .model import DownloadPolicy, fail


class DatabentoTransport(Protocol):
    def __call__(self, parameters: Mapping[str,str], credential: str | None,
                 budget: AttemptBudget, check: Callable[[],None]) -> Page: ...


class HTTPSDatabentoTransport:
    def __init__(self, policy: DownloadPolicy, clock_ns: Callable[[],int]) -> None:
        self._policy, self._clock = policy, clock_ns

    def __repr__(self) -> str:
        return 'HTTPSDatabentoTransport(<opaque>)'

    def __call__(self, parameters: Mapping[str,str], credential: str | None,
                 budget: AttemptBudget, check: Callable[[],None]) -> Page:
        raw = bytearray(); connection: http.client.HTTPSConnection | None = None
        code = SourceErrorCode.TRANSPORT; page: Page | None = None
        try:
            check()
            if type(credential) is not str or not credential:
                fail(SourceErrorCode.AUTHENTICATION)
            remaining = budget.deadline_ns-self._clock()
            if remaining <= 0:
                fail(SourceErrorCode.LIMIT)
            connection = http.client.HTTPSConnection('hist.databento.com', timeout=remaining/1e9,
                                                     context=ssl.create_default_context())
            connection.connect()
            # Retain the socket: HTTPResponse can own its file after Connection: close.
            socket = connection.sock

            def refresh() -> None:
                check()
                remaining = budget.deadline_ns-self._clock()
                if remaining <= 0:
                    fail(SourceErrorCode.LIMIT)
                connection.timeout = remaining/1e9
                if socket is not None:
                    socket.settimeout(remaining/1e9)

            body = urlencode(parameters).encode('ascii')
            auth = 'Basic '+base64.b64encode((credential+':').encode()).decode('ascii')
            refresh()
            connection.request('POST','/v0/timeseries.get_range',body,
                               {'Authorization':auth,'Content-Type':'application/x-www-form-urlencoded',
                                'Accept-Encoding':'identity'})
            refresh(); response = connection.getresponse()
            status = response.status
            if 300 <= status < 400:
                fail(SourceErrorCode.UNSUPPORTED)
            if status == 401: fail(SourceErrorCode.AUTHENTICATION)
            if status == 403: fail(SourceErrorCode.ENTITLEMENT)
            if status == 404: fail(SourceErrorCode.UNAVAILABLE)
            if status == 429: fail(SourceErrorCode.RATE_LIMIT)
            if status != 200: fail(SourceErrorCode.TRANSPORT)
            if response.getheader('Content-Encoding','identity') not in ('identity','none',''):
                fail(SourceErrorCode.UNSUPPORTED)
            limit = min(budget.remaining_bytes,self._policy.max_bytes)
            declared = response.getheader('Content-Length')
            if declared is not None and (not declared.isdecimal() or int(declared)>limit):
                fail(SourceErrorCode.LIMIT)
            while True:
                refresh()
                chunk=response.read(min(self._policy.read_chunk_bytes,limit-len(raw)+1))
                if not chunk: break
                raw.extend(chunk)
                if len(raw)>limit: fail(SourceErrorCode.LIMIT)
            check()
            if declared is not None and len(raw) != int(declared):
                fail(SourceErrorCode.SCHEMA)
            _,_,count=layout(bytes(raw),parameters['schema'])
            page=Page(bytes(raw),count)
        except SourceError as caught:
            code=caught.code
        except http.client.IncompleteRead as caught:
            raw.extend(caught.partial)
            if len(raw) > min(budget.remaining_bytes,self._policy.max_bytes):
                code=SourceErrorCode.LIMIT
        except Exception:
            pass
        finally:
            if connection is not None:
                try: connection.close()
                except Exception: pass
        if page is None:
            raise AttemptFailure(code,received_bytes=len(raw))
        return page
