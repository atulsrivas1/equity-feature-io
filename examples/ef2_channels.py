"""Explicit synthetic Ichimoku and price-channel requests as supplied inputs; no acquisition."""
from equity_feature_duckdb.channels import (
    synthetic_channels_config, synthetic_channels_features, synthetic_channels_fixture,
)


def main() -> None:
    for case_id in ('ICH-01', 'KEL-03', 'PIV-01', 'SQ-02'):
        inputs = synthetic_channels_fixture(case_id)
        config = synthetic_channels_config(case_id)
        print(case_id, inputs.roles, len(inputs.batches), synthetic_channels_features(case_id), config.identity)
    # The channels producers are computed by the pure library layer, with the bars chunks
    # `inputs.bars` (one per governed session); this module only maps.


if __name__ == '__main__':
    main()
