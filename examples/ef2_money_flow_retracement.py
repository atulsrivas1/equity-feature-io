"""Explicit synthetic money-flow and retracement requests as supplied inputs; no acquisition."""
from equity_feature_duckdb.money_flow import (
    synthetic_money_flow_config, synthetic_money_flow_features, synthetic_money_flow_fixture,
)
from equity_feature_duckdb.retracement import synthetic_retracement_config, synthetic_retracement_fixture


def main() -> None:
    for case_id in ('M01', 'M24', 'M36'):
        inputs = synthetic_money_flow_fixture(case_id)
        config = synthetic_money_flow_config(case_id)
        print(case_id, inputs.roles, len(inputs.batches), synthetic_money_flow_features(case_id), config.identity)
    for case_id in ('T01', 'T20', 'T23'):
        inputs = synthetic_retracement_fixture(case_id)
        config = synthetic_retracement_config(case_id)
        print(case_id, inputs.roles, [b is not None for b in inputs.slots], config.identity)
    # The EF2 producers are computed by the pure library layer, with the bars chunks
    # `inputs.bars` (money flow) or the two roles `inputs.slots` (retracement); this module only maps.


if __name__ == '__main__':
    main()
