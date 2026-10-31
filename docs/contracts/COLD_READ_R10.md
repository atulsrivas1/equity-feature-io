# Cold-read test R10 for the feature coverage table

Internal, synthetic, pre-release. Rule R10 of the coverage table design (acceptance criterion 3, ruling X8): a fresh reader who has not seen this repository finds, for three named design features, the status, the producer, the input contract and the output contract in under 5 minutes each. Failure means the layout is fixed, not the test.

**Record status: RUN once on 2026-10-31 by a reader with no project knowledge; PASS with limits (see "Limits of this record").** The author of the coverage table was not the reader. This file holds the protocol and the record only; the expected answers are not in the repository.

## Protocol (give this section, and only this section, to the reader)

You may use only a browser or file viewer and two starting points: the repository file `docs/contracts/catalogue/INDEX.md` (and anything it links to). Do not use search engines, source code, git history or other people. Start a timer per feature. Stop at 5 minutes.

For each design feature below, write down: (1) its status, (2) the producer id or the statement that none exists, (3) the link to its input contract, (4) the link to its output contract. Say where you looked and where you got stuck.

| # | Design feature (id and title) |
| --- | --- |
| 1 | V4, Volume acceleration |
| 2 | P40, Beta to SPY/QQQ over N sessions |
| 3 | P16, Direction-change count; share of moves in session direction |

Also note, once, how many pages you opened before you found the coverage table, and any word you did not understand.

## Notes for the person running the read (do not give to the reader)

- The installed-package route (`catalogue.coverage_for_feature_id`, `design_items_for_producer`) does not exist yet: the packaged copy and API belong to CV2 (RL-01-16). Run the docs-copy route now and repeat the package route after CV2.
- The INDEX pointer to the coverage table is deferred to CV2 (changing `INDEX.md` changes packaged bytes). Until then the path from `INDEX.md` is: its link to `CATALOGUE.md`, then the section "Feature coverage table", then `coverage/COVERAGE.md`. Record the extra hop; if it is the reason for a miss, that is a layout finding for CV2, not a reason to change the protocol.
- Features were chosen per ruling X8: one implemented row on an EF3, EF4 or EF5 producer (V4), one `differs` row (P40), one `missing` row (P16). P5 and P10 are not used. Core-registry and planned-only features are not used for the timed test.

## Record (run of 2026-10-31, repository at PR 80 head 57ac19c, docs-copy route)

| Field | Value |
| --- | --- |
| Status | RUN, PASS with limits |
| Reader and their prior knowledge of the repository | A Claude sub-agent with no project knowledge. It opened this file, so it also saw the "Notes for the person running the read" section above, which names the hop INDEX.md, CATALOGUE.md, "Feature coverage table", coverage/COVERAGE.md. The read was therefore not fully blind. |
| Date, route | 2026-10-31, docs copy (installed-package route not run; it waits for CV2) |
| V4: time, answers, correct? | Under 5 minutes (not stopwatch-timed; three tool calls once COVERAGE.md was open). Status implemented; producer `ef3.adaptive_volume`; input and output pages under `catalogue/ef3.adaptive_volume/`. Consistent between the COVERAGE.md row and the producer output page "Design items served". |
| P40: time, answers, correct? | Under 5 minutes (not stopwatch-timed). Status differs; existing output on `ef3.relative_stats` with its input and output pages; the planned variant has no io page and links to a core ownership-manifest pointer. Consistent with the producer output page. |
| P16: time, answers, correct? | Under 5 minutes (not stopwatch-timed). Status missing; no producer; no contract links. Consistent with the status definition in CATALOGUE.md. |
| Pages opened before the coverage table | 2 (INDEX.md, CATALOGUE.md), then COVERAGE.md |
| Layout findings | INDEX.md links CATALOGUE.md only by an absolute GitHub URL, not a relative link. INDEX.md has no pointer to the coverage table (deferred to CV2). COVERAGE.md has no producer column; the producer is read from the link folder name or the output page. Also noted: INDEX.md alone cannot answer design-id questions (its lookup is by output feature id); CATALOGUE.md is long and the coverage section is near its end; the planned-variant link is a core JSON pointer, different in kind from the others; terms not understood on first read: EF3/EF4/EF5 family, core registry, DV1, ownership manifest, provisional. |
| Result (pass or fix the layout) | PASS on all three features against the criterion (status, producer or none, input and output links found within 5 minutes each), with the limits below. Layout fixes recommended for CV2: relative link from INDEX.md to the coverage table, and a producer column in COVERAGE.md. |

## Limits of this record

- Not fully blind: the reader followed the hop named in the notes section of this file. Without it, an INDEX.md-only reader would have had to follow the absolute web URL (the main branch, which may differ from the checkout) or guess.
- Not stopwatch-timed: "under 5 minutes" is the reader's account of the number of steps, not a measured time.
- No answer key was available to the reader: "correct" means the answers were consistent across COVERAGE.md and the producer pages, not that they were checked against an independent key.
- One reader, one run, docs-copy route only. The installed-package route is open until CV2.
