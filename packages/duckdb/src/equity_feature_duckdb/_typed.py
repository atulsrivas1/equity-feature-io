"""Typed adapter-build refusals for the supplied-input adapters.

A malformed supplied input must surface as a `ContractError` that carries the shared library `ErrorCode`, never as a bare
Python exception (`KeyError`, `IndexError`, `TypeError`, `ValueError`, `OverflowError`). `ContractError` subclasses
`ValueError`, so callers that already catch `ValueError` keep working. Fixed messages only: the original exception text
(which can echo supplied values) stays only as __cause__, never in the message."""
from __future__ import annotations

import functools
from collections.abc import Callable, MutableMapping
from types import FunctionType
from typing import Any, TypeVar

from equity_feature_contracts import ContractError, ErrorCode

F = TypeVar("F", bound=Callable[..., Any])


def typed_refusal(function: F) -> F:
    @functools.wraps(function)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except ContractError:
            raise
        except OverflowError as exc:
            raise ContractError(ErrorCode.OVERFLOW, "supplied value exceeds the representable range") from exc
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ContractError(ErrorCode.INVALID_SCHEMA, "malformed supplied input") from exc
    return guarded  # type: ignore[return-value]


def guard_public(namespace: MutableMapping[str, Any], module: str) -> None:
    """Wrap every public function defined in `module` so adapter-build failures are typed."""
    for name, value in list(namespace.items()):
        if not name.startswith("_") and type(value) is FunctionType and value.__module__ == module:
            namespace[name] = typed_refusal(value)
