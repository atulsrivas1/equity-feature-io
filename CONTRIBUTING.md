# Contributing

Use the canonical [roadmap](https://github.com/users/atulsrivas1/projects/2) and [EQ-121](https://github.com/atulsrivas1/equity-features/issues/278). Link canonical full issue URLs from component PRs; do not auto-close stories before actual release/readback. Apache-2.0 code licensing does not grant data rights. Public examples are synthetic or explicitly licensed. Follow AGENTS.md, same-story documentation, actual separate final-head review, independent expected checks and installed publication evidence. Use short-lived codex/ branches and Atul Srivastava author/local committer attribution without Codex trailers.

## Editing tracked source files

Any change to a file tracked in `docs/EF1_SOURCE_EVOLUTION.json` (for example the `packages/duckdb/src/equity_feature_duckdb/*.py` modules) must refresh that file in the same PR: update the declared `sha256` (computed over the Git blob bytes, LF endings) and keep the `reason` accurate. Then run `python tools/check_extraction.py --core-root <core checkout>` and confirm it passes; a stale digest fails it as an undeclared additive source change.
