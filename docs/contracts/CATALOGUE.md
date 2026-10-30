# Contract catalogue (schema `ef-contract-catalogue1`)

Internal, synthetic, pre-release. Authority: core frozen contract; on conflict core wins and the gate fails.

The catalogue is a generated, read-only view of what each producer takes in (input view) and gives out (output view), taken from the core contract files. It states what an adapter supplies and what a consumer receives. It never says who supplies the data, and it computes nothing. This is catalogue story S1: EF3, EF4 and EF5 (8 core contract files, 21 producers, 126 feature ids). EF1 and EF2 are not present yet; `index.json` lists the families that are.

## Where it is

- Repository: [docs/contracts/catalogue/](catalogue/INDEX.md), start at `INDEX.md`.
- Installed: the same bytes as data files in the `equity-feature-io-contracts` wheel, under `equity_feature_io_contracts/catalogue/`. The catalogue version is the package version. The module `equity_feature_io_contracts.catalogue` reads them (S6 part 2): `producers()` returns every producer, `by_feature_id(feature_id)` returns the producer whose output carries that feature id (raises `UnknownFeatureId`, a `KeyError`, for an unknown id), and `version()` returns the catalogue version, the families present and each producer's `contract_version`. Each `Producer` carries the producer id, family, contract key, contract_version, status, feature ids and the catalogue paths of its four pages. The module imports only the standard library and reads the packaged data; it imports no core or workers code, validates nothing and computes nothing. The files can still be read directly, for example with `importlib.resources.files("equity_feature_io_contracts") / "catalogue" / "index.json"`.

## Layout (paths follow from the producer id)

| Path | Content |
| --- | --- |
| `index.json` | schema, catalogue version, families present, per-contract provenance, per-producer entry (producer id, family, contract_version, status, adapter links, feature ids, paths), `by_feature_id` (feature id to producer id) |
| `INDEX.md` | the same index for reading, grouped by family |
| `<producer_id>/input.md`, `input.json` | input view for the producer |
| `<producer_id>/output.md`, `output.json` | output view for the producer |

`producer_id` is the core `config_identity`, for example `ef4.tape_window_sign`.

## Input view, fixed order

1. roles and slots in library order, with batch kind and nullability; 2. required columns and per-role rules (core states columns inside the role text; copied unchanged); 3. reference fact kinds and schemas; 4. config parameters (and any defaults position core states); 5. coverage, adjustment, scale, known_at and mode rules; 6. input-stage refusal order and codes; 7. adapter API link.

## Output view, fixed order

1. feature ids with dtype, unit, scale, availability rule and order; 2. quality vocabulary, readiness and evidence bounds; 3. reasons reached (fixture ids in core); then refused outcomes, known limits and unit additions where core states them; and the headers as `FeatureHeader` values (`feature_id`, `algorithm_version`, `dtype`, `unit`, `schema_version`; `dtype` is the `ValueType` string value).

## Reading a page from the installed package

`FeatureHeader` is in `equity_feature_io_contracts`; its `dtype` is a `ValueType`, which comes from core `equity_feature_contracts` (install it, it is already a dependency). Example (reads data only):

    import json
    from importlib.resources import files
    from equity_feature_contracts import ValueType
    from equity_feature_io_contracts import FeatureHeader, catalogue

    root = files("equity_feature_io_contracts") / "catalogue"
    producer = catalogue.by_feature_id("tape.window.count").producer_id   # a result column to its producer
    print(catalogue.version().catalogue_version, len(catalogue.producers()))
    output = json.loads((root / producer / "output.json").read_text("utf-8"))
    h = next(x for x in output["headers"] if x["feature_id"] == "tape.window.count")["feature_header_value"]
    header = FeatureHeader(h["feature_id"], h["algorithm_version"], ValueType(h["dtype"]), h["unit"], h["schema_version"])
    print(producer, header)

## Checking a sample input and a sample output (structural checks)

`check_input` and `check_output` are structural checks. They compare the shape of what you supply or receive with the catalogue page and cite the rule and page that failed. They do not look at values, compute nothing, and do not replace a library refusal: the library stays the authority, and a clean check does not say the values are right. They need only the installed `equity-feature-io-contracts` wheel (no workers code, and nothing you import yourself from core).

    from equity_feature_io_contracts import catalogue

    # Input: map each role to the batch kind you supply for it (None or left out = absent delivery).
    result = catalogue.check_input("ef4.tape_window_sign", {"trades": "trade", "seed": "reference"})
    print(result.ok)                                    # True
    result = catalogue.check_input("ef4.tape_window_sign", {"trades": "bar", "extra": "bar"})
    for f in result.findings:
        print(f.rule, f.subject, "-", f.detail, "-", f.page)
    # input.role.unknown extra - role 'extra' is not declared; declared roles: trades, seed - ef4.tape_window_sign/input.md
    # input.role.kind trades - role 'trades' expects kind 'trade', got 'bar' - ef4.tape_window_sign/input.md

    # Output: pass the result headers (mappings, or FeatureHeader objects), and optionally the reason names you saw.
    headers = [{"feature_id": "tape.window.count", "algorithm_version": "ef4-tape-window-v1",
                "dtype": "int64", "unit": "trades", "schema_version": "1"}]
    print(catalogue.check_output("ef4.tape_window_sign", headers).ok)    # a unit or dtype that differs is a finding
    bad = catalogue.check_output("ef4.tape_window_sign", [{**headers[0], "unit": "shares"}], reasons=["absent_input", "nope"])
    for f in bad.findings:
        print(f.rule, f.subject, "-", f.detail)

Rules cited (each is a part of the catalogue page named in `Finding.page`): `input.role.unknown`, `input.role.kind`, `input.role.required` (input view, roles: a role declared not nullable is absent; a nullable role that is absent is not a finding, the library reports `absent_input`); `output.header.field`, `output.feature_id.unknown`, `output.feature_id.duplicate`, `output.header.value` (output view, headers) and `output.quality.reason` (output view, quality vocabulary). Selecting only some of a producer's feature ids is fine. An unknown producer id raises `UnknownProducer`. The unit string in the example is the one the catalogue states for that feature id; read it from the page rather than assuming it.

## Provenance, on every page and every JSON

`contract_version` (core `policy_version`), `status`, source core path, core commit (the last core commit that touched the file, as of the ref used), sha256 of the LF bytes of the source, and the authority line. `status` is read only from the leading words of the core `coordinator_freeze` text: `Frozen as ...` gives `frozen`, `Proposed freeze ...` gives `proposed`. The core status text is kept verbatim as `source_status`. Amendment files named in `related_core_files_not_extracted` (the shared amendments of EF3, EF4 and EF5) are referenced with commit and sha256 but their rulings are not extracted in this version; read them in core.

Amendment rulings are not extracted in this version, and core marks those amendments as proposed; each page says so. Extracting them is a later story.

Four producers show `proposed` because core's freeze text still reads "Proposed freeze", although they are implemented and accepted: `ef4.tape_window_sign`, `ef4.trade_top_k_notional`, `ef4.quote_dynamics`, `ef4.vwap_path`. The catalogue shows core's text as is and adds no status map. Core wins on conflict; when core corrects its text, regeneration picks it up.

The adapter module on each page is labelled the reference storage module: the project's own storage package, never the supplier of data.

## What is not in the views

Every core top-level key is either parsed into a view, listed under `excluded_core_keys` in `index.json` with a reason (calculation semantics, decision record, test evidence, process, per-source matrix), or listed as unparsed. Unparsed keys are never dropped. The gate fails on any unparsed key, so a new core key forces an explicit decision in the extractor.

## Maintainers

    python tools/gen_contract_catalogue.py --core-root <core checkout> [--core-ref origin/main]   # writes both copies
    python tools/check_contract_catalogue.py --core-root <core checkout> [--core-ref origin/main] # drift gate: docs copy == package data == regeneration
    python tools/verify_contract_catalogue.py                                                    # wording, markers, provenance, no provider names

Generated files are never hand-edited. The generator reads core with `git show <ref>:<path>` so a dirty core working tree is not read. Adding a contract file means adding one entry (io module, API page, checkpoint) to `CONTRACTS` in the generator.
