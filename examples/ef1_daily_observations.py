"""Run an original synthetic supplied daily packet through the actual pure API."""
from equity_feature_contracts import EntityKey
from equity_feature_duckdb.ef1 import (
    synthetic_daily_observations_config, synthetic_daily_observations_fixture,
)
from equity_feature_io_sdk import encode_result
from equity_features.ef1 import compute_ef1


def main() -> None:
    config = synthetic_daily_observations_config()
    inputs = synthetic_daily_observations_fixture()
    result = compute_ef1(inputs.slots, config, entity=EntityKey('X', config.session.session_id))
    print(encode_result(result).decode('utf-8'))


if __name__ == '__main__':
    main()
