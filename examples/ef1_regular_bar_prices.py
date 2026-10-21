"""Compute original synthetic completed-BAR endpoints with the actual pure API."""
from equity_feature_contracts import EntityKey
from equity_feature_duckdb.regular_bar_prices import (
    synthetic_regular_bar_price_config, synthetic_regular_bar_price_fixture,
)
from equity_feature_io_sdk import encode_result
from equity_features.ef1 import compute_ef1


def main() -> None:
    for case in ("R01_two_independent_endpoints", "R08_unknown_before_first"):
        config = synthetic_regular_bar_price_config(case)
        inputs = synthetic_regular_bar_price_fixture(case)
        result = compute_ef1(inputs.slots, config, entity=EntityKey("X", config.session.session_id))
        print(encode_result(result).decode("utf-8"))


if __name__ == "__main__": main()
