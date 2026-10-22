"""Explicit synthetic requests through the public pure API; no storage acquisition."""
from equity_feature_contracts import EntityKey
from equity_feature_duckdb.reference_close import (
    synthetic_reference_close_config, synthetic_reference_close_fixture,
)
from equity_features.ef1 import compute_ef1


def main() -> None:
    for case_id in ('C01_within_tolerance', 'C02_outside_tolerance', 'C03_absent_authoritative_close'):
        config = synthetic_reference_close_config(case_id)
        inputs = synthetic_reference_close_fixture(case_id)
        result = compute_ef1(inputs.slots, config, entity=EntityKey('X', config.session.session_id))
        print(case_id, result)


if __name__ == '__main__':
    main()
