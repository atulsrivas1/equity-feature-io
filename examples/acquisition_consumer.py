"""Owned synthetic external client; no provider or network access."""
from equity_feature_contracts import AvailabilitySpec, DataKind, PriceUnit
from equity_feature_contracts.adapters import AcquisitionRequest
from equity_feature_acquisition import (
    AcquisitionController, AcquisitionLimits, AcquisitionScope, AttemptBudget,
    DownloadApproval, Page, Transport,
)


class SuppliedFixture:
    def __call__(self, credential: str | None, budget: AttemptBudget) -> Page:
        assert credential is None and budget.remaining_bytes >= 8
        return Page(b"supplied", 1)


def run() -> None:
    stamp = 1700000000000000001
    request = AcquisitionRequest("owned-request", DataKind.TRADE, "synthetic", ("A",),
        ("S",), stamp, stamp + 10, "owned-revision", PriceUnit(6, "USD"),
        AvailabilitySpec(stamp + 10, stamp + 10, stamp + 10), max_batch_rows=1,max_rows=1)
    scope = AcquisitionScope(request,"owned-fixture","synthetic","supplied","historical","s1","m1")
    # A test-local authorization, not consent for any actual provider operation.
    approval = DownloadApproval(scope,"synthetic-permission",100,AcquisitionLimits(1,1,8,100,0))
    controller = AcquisitionController(approval,clock_ns=lambda:0,sleep_ns=lambda ns:None,cancelled=lambda:False)
    fixture: Transport = SuppliedFixture()
    page = controller.execute(scope,fixture,cost_upper_micro_usd=0)
    assert page == Page(b"supplied",1) and controller.ledger.calls == 1
    assert scope.request.start_ns == 1700000000000000001
    print("Synthetic third-party transport/public exact-scope proof PASS")


if __name__ == "__main__":
    run()
