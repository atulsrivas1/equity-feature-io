# Contract catalogue (schema `ef-contract-catalogue1`)

Internal, synthetic, pre-release. Authority: core frozen contract; on conflict core wins and the gate fails.

The catalogue is a generated, read-only view of what each producer takes in (input view) and gives out (output view), taken from the core contract files. It states what an adapter supplies and what a consumer receives. It never says who supplies the data, and it computes nothing. This is catalogue story S1: EF3, EF4 and EF5 (8 core contract files, 21 producers, 126 feature ids). EF1 and EF2 are not present yet; `index.json` lists the families that are.

## Where it is

- Repository: [docs/contracts/catalogue/](catalogue/INDEX.md), start at `INDEX.md`.
- Installed: the same bytes as data files in the `equity-feature-io-contracts` wheel, under `equity_feature_io_contracts/catalogue/`. The catalogue version is the package version. No Python lookup module ships in this version (planned as a later story), so read the files directly, for example with `importlib.resources.files("equity_feature_io_contracts") / "catalogue" / "index.json"`.

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

`FeatureHeader` is in `equity_feature_io_contracts`; its `dtype` is a `ValueType`, which comes from core `equity_feature_contracts` (install it, it is already a dependency). Example (reads data only; no lookup module yet):

    import json
    from importlib.resources import files
    from equity_feature_contracts import ValueType
    from equity_feature_io_contracts import FeatureHeader

    root = files("equity_feature_io_contracts") / "catalogue"
    index = json.loads((root / "index.json").read_text("utf-8"))
    producer = index["by_feature_id"]["tape.window.count"]            # a result column to its producer
    output = json.loads((root / producer / "output.json").read_text("utf-8"))
    h = next(x for x in output["headers"] if x["feature_id"] == "tape.window.count")["feature_header_value"]
    header = FeatureHeader(h["feature_id"], h["algorithm_version"], ValueType(h["dtype"]), h["unit"], h["schema_version"])
    print(producer, header)

`catalogue.producers()`, `catalogue.by_feature_id()` as functions, `check_input` and `check_output` are not part of S1; they come in later stories (S6 and S8), and the structural checks will never compute or judge values.

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
