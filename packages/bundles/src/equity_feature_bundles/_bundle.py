"""Verified byte archives and immutable unavailable references; no calculator."""
from __future__ import annotations
import hashlib
from typing import Any
from equity_feature_contracts import CanonicalBatch, ConfigSpec, EntityKey, FeatureResult
from equity_feature_evidence import (
    ContentFingerprint, ExecutionReceipt, canonical_content, decode_receipt, encode_receipt,
)
from . import _versions as V
from ._archive import read_stored, write_stored
from ._binding import aggregate, pairs, shape
from ._errors import require, sanitized
from ._json import Budget, dump, fields, load, preflight
from ._model import BundleInput, BundleManifest, BundleVersions, PublicationDeclaration, ReproductionBundle
from ._typed import typed_content


def fp_wire(value: ContentFingerprint) -> dict[str, object]:
    return {'domain': value.domain, 'digest': value.digest, 'byte_length': value.byte_length,
        'schema_version': value.schema_version, 'canonicalization': value.canonicalization, 'algorithm': value.algorithm}


def fp_read(value: Any, domain: str) -> ContentFingerprint:
    f = fields(value, ('domain', 'digest', 'byte_length', 'schema_version', 'canonicalization', 'algorithm'))
    result = ContentFingerprint(f['domain'], f['digest'], f['byte_length'], f['schema_version'], f['canonicalization'], f['algorithm'])
    require(result.domain == domain)
    require(0 < result.byte_length <= 33554432, 'limit_exceeded')
    return result


def check_data(raw: bytes, fp: ContentFingerprint) -> None:
    require(len(raw) == fp.byte_length and hashlib.sha256(raw).hexdigest() == fp.digest, 'integrity_mismatch')


def write_bundle(receipt: ExecutionReceipt, configuration: ConfigSpec, result: FeatureResult,
        inputs: tuple[tuple[str, CanonicalBatch], ...], publication: PublicationDeclaration) -> bytes:
    """Export supplied content; omitted actual batches remain unavailable refs."""
    with sanitized():
        pairs(inputs)
        require(type(receipt) is ExecutionReceipt and type(publication) is PublicationDeclaration)
        require({x[0] for x in inputs} <= {x.role for x in receipt.inputs}, 'integrity_mismatch')
        aggregate((configuration, result) + tuple(x[1] for x in inputs))
        supplied = dict(inputs)
        manifest = BundleManifest('session.compute_trades.v1', shape(configuration, result),
            BundleVersions(V.BUNDLE, V.CONTRACTS, V.EVIDENCE, V.FEATURES), publication)
        bundle = ReproductionBundle(manifest, receipt, configuration, result,
            tuple(BundleInput(x.role, x.input_id, x.content, supplied.get(x.role)) for x in receipt.inputs))
        return _encode(bundle)


def _encode(bundle: ReproductionBundle) -> bytes:
    receipt = encode_receipt(bundle.receipt)
    entries = {'receipt.json': receipt, 'configuration.json': canonical_content(bundle.configuration),
        'result.json': canonical_content(bundle.result)}
    inputs = []
    embedded = 0
    for item in bundle.inputs:
        entry = None
        if item.batch is not None:
            entry = f'inputs/{embedded:03d}.json'; embedded += 1
            entries[entry] = canonical_content(item.batch)
        inputs.append({'role': item.role, 'input_id': item.input_id, 'content': fp_wire(item.content),
            'storage': 'reference' if entry is None else 'embedded', 'entry': entry})
    m = bundle.manifest
    wire = {'project': 'equity-features', 'schema_version': '1', 'canonicalization': 'bundle-json-v1',
        'registry': m.registry, 'entity': {'instrument_id': m.entity.instrument_id, 'session_id': m.entity.session_id},
        'versions': {'bundle': m.versions.bundle, 'contracts': m.versions.contracts, 'evidence': m.versions.evidence, 'features': m.versions.features},
        'publication': {'data_class': m.publication.data_class, 'rights_statement': m.publication.rights_statement, 'retention': m.publication.retention},
        'receipt': {'entry': 'receipt.json', 'byte_length': len(receipt), 'digest': hashlib.sha256(receipt).hexdigest()},
        'configuration': {'entry': 'configuration.json', 'content': fp_wire(bundle.receipt.configuration)},
        'result': {'entry': 'result.json', 'content': fp_wire(bundle.receipt.output)}, 'inputs': inputs}
    entries['manifest.json'] = dump(wire)
    preflight(entries['manifest.json'], 'manifest')
    preflight(receipt, 'receipt')
    return write_stored(entries)


def read_bundle(raw: bytes) -> ReproductionBundle:
    """No extraction, path selection, acquisition or code resolution occurs."""
    with sanitized():
        entries = read_stored(raw)
        preflight(entries['manifest.json'], 'manifest')
        preflight(entries['receipt.json'], 'receipt')
        shared = Budget()
        for name, data in entries.items():
            if name not in ('manifest.json', 'receipt.json'):
                preflight(data, 'typed', shared)
        wire = fields(load(entries['manifest.json']), ('project', 'schema_version', 'canonicalization',
            'registry', 'entity', 'versions', 'publication', 'receipt', 'configuration', 'result', 'inputs'))
        require(dump(wire) == entries['manifest.json'], 'integrity_mismatch')
        require(wire['project'] == 'equity-features')
        require(wire['schema_version'] == '1' and wire['canonicalization'] == 'bundle-json-v1', 'unsupported_version')
        v = fields(wire['versions'], ('bundle', 'contracts', 'evidence', 'features'))
        p = fields(wire['publication'], ('data_class', 'rights_statement', 'retention'))
        e = fields(wire['entity'], ('instrument_id', 'session_id'))
        manifest = BundleManifest(wire['registry'], EntityKey(e['instrument_id'], e['session_id']),
            BundleVersions(v['bundle'], v['contracts'], v['evidence'], v['features']),
            PublicationDeclaration(p['data_class'], p['rights_statement'], p['retention']))
        desc = fields(wire['receipt'], ('entry', 'byte_length', 'digest'))
        receipt_raw = entries['receipt.json']
        require(desc['entry'] == 'receipt.json' and type(desc['byte_length']) is int and desc['byte_length'] <= 1048576)
        require(desc['byte_length'] == len(receipt_raw) and desc['digest'] == hashlib.sha256(receipt_raw).hexdigest(), 'integrity_mismatch')
        descriptors = []
        for key, domain in (('configuration', 'configuration'), ('result', 'feature_result')):
            d = fields(wire[key], ('entry', 'content'))
            require(d['entry'] == key + '.json')
            fp = fp_read(d['content'], domain)
            check_data(entries[key + '.json'], fp)
            descriptors.append(fp)
        require(type(wire['inputs']) is list and len(wire['inputs']) <= 64, 'limit_exceeded')
        used = {'manifest.json', 'receipt.json', 'configuration.json', 'result.json'}
        pending = []
        embedded = 0
        previous = None
        for item in wire['inputs']:
            d = fields(item, ('role', 'input_id', 'content', 'storage', 'entry'))
            from ._errors import label
            label(d['role']); label(d['input_id'])
            require(previous is None or d['role'] > previous)
            previous = d['role']
            fp = fp_read(d['content'], 'canonical_batch')
            if d['storage'] == 'embedded':
                entry = f'inputs/{embedded:03d}.json'; embedded += 1
                require(d['entry'] == entry and entry in entries, 'integrity_mismatch')
                check_data(entries[entry], fp); used.add(entry)
            else:
                require(d['storage'] == 'reference' and d['entry'] is None)
                entry = None
            pending.append((d['role'], d['input_id'], fp, entry))
        require(used == set(entries), 'invalid_archive')
        # Every header/entry CRC/hash and shared lexical limit passed before typed construction.
        receipt = decode_receipt(receipt_raw)
        require(descriptors == [receipt.configuration, receipt.output], 'integrity_mismatch')
        configuration = typed_content(entries['configuration.json'], 'configuration')
        result = typed_content(entries['result.json'], 'feature_result')
        inputs = tuple(BundleInput(role, input_id, fp,
            None if entry is None else typed_content(entries[entry], 'canonical_batch'))
            for role, input_id, fp, entry in pending)
        return ReproductionBundle(manifest, receipt, configuration, result, inputs)
