"""Owned local CSV -> existing factory Protocol -> pure trades; no provider access."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import time

from equity_feature_acquisition import AcquisitionLimits, AcquisitionScope, DownloadApproval
from equity_feature_contracts import (AvailabilitySpec, ConfigSpec, Coverage, DataKind, EntityKey,
    InputScope, Parameter, PriceUnit, SessionSpec, SourceBinding, WindowSpec)
from equity_feature_contracts.adapters import AcquisitionRequest, HistoricalAdapter, validate_delivery
from equity_feature_files import FileProfile, LocalFileFactory
from equity_feature_io_contracts import ComponentFactory
from equity_feature_io_sdk.factories import SourceRegistry
from equity_features.session import compute_trades

BASE = 1700000000000000000
OWNED_CSV = ("instrument_id,session_id,event_ns,order_key,event_id,eligible,price,size,known_at_ns\n"
    "A,S,1700000000000000001,1,owned-e1,1,1000000000,2,1700000000000000001\n"
    "A,S,1700000000000000001,2,owned-e2,1,2000000000,1,\n"
    "A,S,1700000000000000003,3,owned-e3,1,3000000000,3,1700000000000000999\n").encode()


class NeverCancelled:
    def is_cancelled(self) -> bool:
        return False


class NoCredentials:
    def get(self, name: str) -> str | None:
        raise AssertionError("Local files never consult credentials")


def owned_approval(scope: AcquisitionScope) -> DownloadApproval:
    # Application consent for this generated synthetic file only; not provider consent.
    return DownloadApproval(scope, "example-owned-local-use", time.monotonic_ns()+1_000_000_000,
        AcquisitionLimits(1, scope.request.max_rows, 10_000, 1_000_000_000))


def configuration(*, reconstruction: bool) -> ConfigSpec:
    availability = AvailabilitySpec(BASE+10, BASE+10, BASE+10)
    if reconstruction:
        availability = replace(availability, mode="reconstruction", reconstruction_reason="owned-replay")
    return ConfigSpec("owned-files-example", "v1", (Parameter("eligibility_policy", "owned-file-v1"),),
        SessionSpec("owned-fixture", "S", BASE, BASE+10, "supplied"), WindowSpec(1, "S", ("S",)),
        availability, price_unit=PriceUnit(9, "USD"))


def main() -> None:
    profile = FileProfile("csv", "owned-fixture", SourceBinding("owned-local", "immutable-owned-v1", "mapping-v1", "fixture"),
        PriceUnit(9,"USD"), Coverage(3,3,True), InputScope(BASE,BASE+10,"owned-file-v1"),
        hashlib.sha256(OWNED_CSV).hexdigest())
    request = AcquisitionRequest("owned-request", DataKind.TRADE, "owned-fixture", ("A",), ("S",),
        BASE, BASE+10, "immutable-owned-v1", PriceUnit(9,"USD"), AvailabilitySpec(BASE+10,BASE+10,BASE+10), max_batch_rows=3)
    factory: ComponentFactory[HistoricalAdapter] = LocalFileFactory(profile, approve=owned_approval)
    registry: SourceRegistry[HistoricalAdapter] = SourceRegistry()
    registry.register("owned-files", factory)
    with tempfile.TemporaryDirectory(prefix="owned-file-example-") as temporary:
        path = Path(temporary)/"owned.csv"
        path.write_bytes(OWNED_CSV)
        adapter = registry.resolve("owned-files", {"path": str(path)}, NoCredentials(), request)
        delivery = tuple(adapter.iter_batches(request, NeverCancelled()))
        validate_delivery(request, adapter.capabilities(), delivery)
    batch = delivery[0].batch
    assert batch is not None
    replay = compute_trades(batch, configuration(reconstruction=True), entity=EntityKey("A","S"))
    values = {c.feature_id.rsplit(".",1)[1]: c.values[0] for c in replay.values}
    assert values["count"] == 3 and values["volume"] == 6 and values["notional"] == 13_000_000_000
    vwap = values["vwap"]
    assert type(vwap) is float and abs(vwap-13/6) < 1e-12
    assert values["mean_size"] == 2
    causal = compute_trades(batch, configuration(reconstruction=False), entity=EntityKey("A","S"))
    assert all(c.values[0] is None for c in causal.values)
    print("Owned CSV/factory/exact pure reconstruction and retained unknown/future causal evidence PASS")


if __name__ == "__main__":
    main()
