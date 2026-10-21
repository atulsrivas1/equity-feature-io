"""Explicit synthetic requests through the public pure API; no storage acquisition."""
from equity_feature_contracts import EntityKey
from equity_feature_duckdb.regular_first_trade_price import (
    synthetic_regular_first_trade_price_config, synthetic_regular_first_trade_price_fixture,
)
from equity_features.ef1 import compute_ef1


def main() -> None:
    for case_id in ('R001', 'R019'):
        config = synthetic_regular_first_trade_price_config(case_id)
        inputs = synthetic_regular_first_trade_price_fixture(case_id)
        result = compute_ef1(inputs.slots,config,entity=EntityKey('X',config.session.session_id))
        print(case_id,result)


if __name__ == '__main__':
    main()
