"""Fixed public errors; parsing never exposes supplied payloads."""
from contextlib import contextmanager
from collections.abc import Iterator
from equity_feature_contracts.errors import ContractError
from equity_feature_evidence import EvidenceError


class BundleError(ValueError):
    def __init__(self, code: str = 'invalid_schema') -> None:
        if type(code) is not str or code not in (
            'invalid_schema', 'invalid_archive', 'limit_exceeded',
            'integrity_mismatch', 'unsupported_version',
        ):
            code = 'invalid_schema'
        self.code = code
        super().__init__('Bundle rejected: ' + code)


def require(condition: bool, code: str = 'invalid_schema') -> None:
    if not condition:
        raise BundleError(code)


@contextmanager
def sanitized() -> Iterator[None]:
    try:
        yield
    except BundleError:
        raise
    except EvidenceError as error:
        code = error.code if error.code in ('limit_exceeded', 'unsupported_version') else 'integrity_mismatch'
        raise BundleError(code) from None
    except (ContractError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise BundleError() from None


def label(value: object) -> None:
    require(type(value) is str)
    assert isinstance(value, str)
    require(bool(value.strip()))
    require(len(value) <= 256, 'limit_exceeded')
    require(not any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value))
    require(len(value.encode('utf-8')) <= 1024, 'limit_exceeded')
