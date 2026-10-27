"""Evidence probe for the typed adapter-build refusal guard (no unittest; run with the duckdb venv and core on PYTHONPATH)."""
from equity_feature_contracts import ContractError, ErrorCode
from equity_feature_duckdb._typed import typed_refusal

SECRET = "SUPPLIED-SECRET-VALUE"


def raiser(exc):
    @typed_refusal
    def f():
        raise exc
    return f


def check(name, exc, code):
    try:
        raiser(exc)()
    except ContractError as e:
        assert e is exc if isinstance(exc, ContractError) else True
        assert e.code is code, (name, e.code)
        assert SECRET not in str(e), name
        if not isinstance(exc, ContractError):
            assert e.__cause__ is exc, name
        print("ok", name, e.code.name)


original = ContractError(ErrorCode.DUPLICATE, "dup")
check("ContractError passthrough", original, ErrorCode.DUPLICATE)
for exc in (KeyError(SECRET), IndexError(SECRET), TypeError(SECRET), ValueError(SECRET)):
    check(type(exc).__name__, exc, ErrorCode.INVALID_SCHEMA)
check("OverflowError", OverflowError(SECRET), ErrorCode.OVERFLOW)
