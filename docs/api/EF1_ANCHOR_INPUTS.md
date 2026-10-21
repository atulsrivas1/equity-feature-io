# EF1 anchor source composition (EQ212)

[EQ212 #570](https://github.com/atulsrivas1/equity-features/issues/570),
epic569 / milestone34, implements the reviewed first EF1 slice. This is source
authoring in progress; no test, build, installed-artifact or release acceptance
is claimed. The canonical `ef1-contract1` ledger SHA256 is
`02940da0c4663bbced050ac551e7fbafe2a1da1534e4c6fa5c87eaf90d420076`.
The implementation grant explicitly permits this reviewed subset while the full
EQ164 inventory audit remains a release gate.

Import the additive module explicitly:

```python
from equity_feature_duckdb.ef1 import synthetic_anchor_fixture

packet = synthetic_anchor_fixture("A01", mode="trades")
# packet.roles == ("trades", "anchor_provenance")
# packet.batches contains the actual canonical market/proof batches in role order.
```

The corresponding mathematical selection is:

```python
selection = {
    "version": "ef1-context1", "producer": "anchor", "calendar": None,
    "selection": {
        "mode": "trades",
        "definition": {
            "anchor_id": "A", "reset_id": "R",
            "start_ns": 10, "selection_policy_id": "supplied-v1", "revision": "R1"
        }
    }
}
```

Use namespace SYN, instrument X, session S, explicit session bounds10..30, cutoff/
knowledge/evaluation20 and PriceUnit(2,"USD"). All times are fictional integer
nanoseconds. There is no exchange-calendar assertion. Actual builder/calculation
is `equity_features.ef1` in the separately qualified feature candidate; this I/O
module contains no feature mathematics or feature-package import.

`synthetic_anchor_fixture` supports A01, A02 and A01-missing-notional. Modes are
`trades` and `bars_actual_notional`; the missing-notional subcase is bars only.
A01 supplies trade coefficients1000*2+1300*1, or equivalent BAR actual_notional3300
and volume3. Independent expected VWAP is11currency/share, notional coefficient3300
at scale2 and volume3. A02 is a real complete0/0 population over positive scope
[10,20); expected totals are zero and VWAP unavailable/zero_denominator. A03
raises BOUNDS without constructing a fake InputScope(20,20).

`make_anchor_provenance(definition, *, namespace, instrument_id, session_id,
source_id, input_id, known_at_ns, end_ns=None)` maps explicitly supplied source
declaration evidence to canonical REFERENCE. The five exact definition keys are
anchor_id/reset_id/start_ns/selection_policy_id/revision. Its reference_id is
`a1:` plus SHA256 of exact sorted compact ASCII JSON of that definition;
fact_kind is `ef1.anchor.provenance`, text `supplied_anchor`, effective start
unchanged, known-at unchanged including null, source snapshot equal revision.
No JSON state cells, factor-field overload, new DataKind or wire codec is added.
The pure feature API owns cutoff-relative anchor/proof admission and readiness;
the source constructor does not transform late/unknown facts into eligible ones.

`AnchorInputs(mode, market, anchor_provenance, market_provenance,
anchor_provenance_mode)` composes caller-supplied canonical batches without
relabeling their metadata. Provenance is explicitly duckdb_backed_observed,
synthetic or unavailable per slot. A missing batch must say unavailable;
an observed-empty actual batch is present. Mixed observed/synthetic packets keep
both labels. This validates declared internal shape, not provenance truth or
dataset rights. No automatic synthetic fallback, source lookup, new table reader
or live provider is introduced. Reuse the accepted catalog/original-Parquet reader
only after separately qualified source selection and rights; arbitrary DuckDB
tables remain unsupported. No N: source database has been queried by this story.

`separate_output_path(output_path, source_paths)` requires caller-owned absolute
paths, resolves path aliases and rejects an exact/symlink/hardlink alias of any
declared source. It creates no files. Callers supply all actual input paths;
omitting a path cannot establish separation. Existing sink branding, lease,
local-filesystem qualification and transaction behavior remain unchanged.

The separately invoked example `examples/ef1/publish_result.py` reads one bounded
SDK canonical result file and uses the existing DuckDBSink/publication SDK,
explicit generation/job/partition IDs and a separate output path. It verifies
full canonical encoded readback, preserving quality, metadata, input identities
and evidence; it performs no calculations. Retry IDs remain caller-owned and
unchanged for identical requests. Conflict, uncertain commitment and corruption
remain typed SDK/sink outcomes; the example does not catch them as rollback.
No database exists until the caller explicitly executes the command.

Authored checks are `tests/ef1/test_anchor_inputs.py` (mapping/availability/
provenance/path controls) and `tests/ef1/test_anchor_composition.py` (independent
literal A01-A03/B01 expectations plus full feature-to-physical-sink bytes and
replay/readback). The latter requires the exact feature candidate and optional
sink dependency. They have not run while EQ142 has the reserved resource window.
They do not replace worker integration, independent final-head review, both-OS
installed artifacts, public source qualification or the browser demo.

Source package metadata and public version are0.1.0a9 under the reviewed packaging
amendment; canonical contracts stay0.0.4a4. SDK/contracts.a2, sink.a0 and historical
source acquisition behavior are unchanged. Existing a8 artifacts do not contain
this addition. The existing historical build pipeline is not EF1 coverage;
coordinator owns new cross-repository CI/source pins and compatible artifacts.
Follow-up required before release: updated build provenance, executed relevant
conformance, exact compatible artifacts and remaining EF1 source/reference families.

Current AcquisitionReceipt.adapter_version now reports0.1.0a9, with its current
evidence test and historical-source builder version assertions aligned explicitly.
This is expected adapter identity evolution; acquisition1/schema1, canonical
contracts0.0.4a4, declared evidence and source algorithms are unchanged. Historical
a8 receipts remain untouched; new receipt bytes are not asserted identical to a8.
The builder adjustment does not add EF1 tests or new feature-dependency coverage.

Review corrections IO-01/02 use explicit one-result limits:1MiB per-result and
total bytes,3 cells,128 evidence rows. The example admits those bounds before
sink construction. Authored example checks cover nonempty publication/readback
and oversized input refusal before sink creation. IO-03 asserts canonical
ResultMetadata role sorting independently of source packet transport order.
All checks remain unexecuted while the official R18 study owns its resource window.

Current qualification declarations use `docs/EF1_SOURCE_EVOLUTION.json` alongside
the unchanged original EQ122 inventory. The retained19 extraction comparisons
still verify original canonical Git hashes and exact current bytes, permitting
only three declared one-occurrence a7-to-a9 markers (package, receipt and its
current test). The new EF1 source module is separately hash-bound; the complete
package file-set check rejects undeclared additions. The source builder retains
both declaration digests and checks them before/after qualification. The matrix
expects exact a9 and records DuckDB as a changed distribution, retaining accepted
a8 archive hashes historically and exact accepted hash equality for unchanged
packages. All new archives still require repeat-build equality and actual installed
composition checks. These declarations do not establish that CI passed or that
the historical matrix covers new EF1 mathematics.
