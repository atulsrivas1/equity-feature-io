"""Explicit synthetic multi-venue status requests through the public pure API; no acquisition."""
from equity_feature_contracts import EntityKey
from equity_feature_duckdb.venue_status import (
    synthetic_venue_status_config, synthetic_venue_status_fixture,
)
from equity_features.ef1 import compute_ef1


def main() -> None:
    for case_id in ('MV05', 'MV06', 'MV15', 'MV02'):
        config = synthetic_venue_status_config(case_id)
        inputs = synthetic_venue_status_fixture(case_id)
        result = compute_ef1(inputs.slots, config, entity=EntityKey('X', config.session.session_id))
        print(case_id, result)


if __name__ == '__main__':
    main()
