# EF4-I1 path efficiency and choppiness I/O source checkpoint - October 23, 2026

Status: source authored against the frozen path-efficiency contract (`ef4.path_efficiency`, `ef4-path-efficiency-v1`,
`ef4-path1`, EQ-161) by the EF4 I/O layer. See the [supplied-input API](api/EF4_PATH_EFFICIENCY_INPUTS.md). No
path mathematics, no sink/SDK/version change, no package version bump.

Executed (Python 3.12, core main `bbb39cd` with the merged library PR #708, io branch `ef4i1-io`): a manual scratch
driver (not committed; no unit tests added, per owner policy) expanded the contract fixtures to supplied rows, built
the batch, context and config with this adapter, computed through `compute_path_efficiency`, published each result to
a new scratch DuckDB sink and read it back.

- 31/31 result fixtures (203 outputs): every status, reason, expected and observed count, witness list and value
  matched the contract under its acceptance rule (`exact_float64` bit-exact, `exact_plus_zero` bit-exact `+0.0`,
  `tolerance` per the R17 envelope). The DuckDB readback equals the library output (canonical encoding equality).
- 31/31 configuration envelopes are identical (parameters, identity and algorithm) to the library
  `build_path_efficiency_config` for the same context.
- 39/39 refusal recipes raise the recorded error code. Raised at I/O: 23 (adapter configuration checks 9, which are
  PR18 to PR25, PR34; canonical validation or contract constructors used by the adapter 14, which are PR01, PR02,
  PR04, PR06 to PR15, PR35). Raised by the library: 16 (identity PR03, PR05, PR16, PR17; configuration and version
  PR26 to PR33; features and capability PR36 to PR39).

Not executed: the worker, mypy, an independent oracle beyond the contract expected values, and the observed-source
rights and release gates.

Remaining gates: worker and sink readback in the shared runner, source-evolution declaration review, independent
review, observed-source rights and release.
