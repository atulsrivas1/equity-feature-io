"""Explicit synthetic momentum and trend requests as supplied inputs; no acquisition."""
from equity_feature_duckdb.momentum import (
    synthetic_momentum_config, synthetic_momentum_features, synthetic_momentum_fixture,
)


def main() -> None:
    for case_id in ('M01', 'D22', 'T23', 'P01'):
        inputs = synthetic_momentum_fixture(case_id)
        config = synthetic_momentum_config(case_id)
        print(case_id, inputs.roles, len(inputs.batches), synthetic_momentum_features(case_id), config.identity)
    # The momentum producer is computed by the pure library layer, with the bars chunks
    # `inputs.bars`; this module only maps. The prefix fixtures P01 to P03 take series= and length=.


if __name__ == '__main__':
    main()
