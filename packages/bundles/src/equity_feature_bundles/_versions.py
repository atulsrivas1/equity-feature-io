"""Single source of truth for the exact versions this bundle format admits.

Bundles deliberately refuse unknown versions, so these are literals rather than
values read from the installed packages. Keep FEATURES equal to the current
`equity-features` release (and the `replay` extra in pyproject.toml).
"""
BUNDLE = '0.1.0a1'
CONTRACTS = '0.0.4a4'
EVIDENCE = '0.1.0a2'
FEATURES = '0.0.4a5'
