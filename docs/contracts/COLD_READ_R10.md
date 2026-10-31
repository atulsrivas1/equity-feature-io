# Cold-read test R10 for the feature coverage table

Internal, synthetic, pre-release. Rule R10 of the coverage table design (acceptance criterion 3, ruling X8): a fresh reader who has not seen this repository finds, for three named design features, the status, the producer, the input contract and the output contract in under 5 minutes each. Failure means the layout is fixed, not the test.

**Record status: PENDING INDEPENDENT READER. No cold read has been run.** The author of the coverage table cannot be the reader. The tables below are the protocol and the sealed answer key; the record is appended by the person who runs the read.

## Protocol (give this section, and only this section, to the reader)

You may use only a browser or file viewer and two starting points: the repository file `docs/contracts/catalogue/INDEX.md` (and anything it links to). Do not use search engines, source code, git history or other people. Start a timer per feature. Stop at 5 minutes.

For each design feature below, write down: (1) its status, (2) the producer id or the statement that none exists, (3) the link to its input contract, (4) the link to its output contract. Say where you looked and where you got stuck.

| # | Design feature (id and title) |
| --- | --- |
| 1 | V4, Volume acceleration |
| 2 | P40, Beta to SPY/QQQ over N sessions |
| 3 | P16, Direction-change count; share of moves in session direction |

Also note, once, how many pages you opened before you found the coverage table, and any word you did not understand.

## Scope notes for the person running the read

- The installed-package route (`catalogue.coverage_for_feature_id`, `design_items_for_producer`) does not exist yet: the packaged copy and API belong to CV2 (RL-01-16). Run the docs-copy route now and repeat the package route after CV2.
- The INDEX pointer to the coverage table is deferred to CV2 (changing `INDEX.md` changes packaged bytes). Until then the path from `INDEX.md` is: its link to `CATALOGUE.md`, then the section "Feature coverage table", then `coverage/COVERAGE.md`. Record the extra hop; if it is the reason for a miss, that is a layout finding for CV2, not a reason to change the protocol.
- Features were chosen per ruling X8: one implemented row on an EF3, EF4 or EF5 producer (V4), one `differs` row (P40), one `missing` row (P16). P5 and P10 are not used. Core-registry and planned-only features are not used for the timed test; the reader may follow one afterwards and note the result (P40 also cites a planned output).

## Answer key (coordinator only, do not give to the reader; generated table as of catalogue 0.1.0a7, core 73848a9)

| # | Status | Producer | Input contract | Output contract |
| --- | --- | --- | --- | --- |
| V4 | implemented | `ef3.adaptive_volume` (output `adaptive.volume.peak_relative_acceleration`, frozen) | `catalogue/ef3.adaptive_volume/input.md` | `catalogue/ef3.adaptive_volume/output.md` |
| P40 | differs | existing output `relative.beta` on `ef3.relative_stats` (frozen); the variant `relative.log_return_beta` is planned (pointer to the ownership manifest row, DV1) | `catalogue/ef3.relative_stats/input.md` | `catalogue/ef3.relative_stats/output.md` |
| P16 | missing | none: no cited output | none | none |

## Record (appended by the reader's runner)

| Field | Value |
| --- | --- |
| Status | PENDING INDEPENDENT READER |
| Reader and their prior knowledge of the repository | |
| Date, route (docs copy or installed package) | |
| V4: time, answers, correct? | |
| P40: time, answers, correct? | |
| P16: time, answers, correct? | |
| Pages opened before the coverage table | |
| Layout findings | |
| Result (pass or fix the layout) | |
