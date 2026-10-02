---
status: accepted
---

# Make cub-workenv the sole host environment authority

The partial transition left creation recipes requiring their output DB to exist
and then calling a legacy lifecycle that refused workenv storage. All active
selection and preparation now use `cub-workenv`; the legacy runtime engine is
retired while historical metadata and DBs remain preserved. This supersedes all
retained-legacy-path rules in ADR-0001.

Keep the existing coordinator name and lock namespace for its narrowed
build/install protection. Removing it outright would lose build serialization,
installation busy checks and persistent container lifetime ownership. Ordinary
native commands stay supported, and no DB lease, universal run wrapper or
host-wide daemon is introduced. Environment loading remains cheap and explicit
host initialization stays independent from build/ctest/container preparation.

The user selected automatic deletion/recreation only for known wholly internal
DBs. New CLI creation records provenance; reuse never fabricates it. The personal
helper checks storage boundaries and invokes native deletion with a private
registry, preserving unrelated entries, external targets and unknown leftovers.
Unreceipted or uncertain DBs require manual review; binary-independent deletion
and automatic preset takeover are retired. These checks do not promise atomic
protection against concurrent manual filesystem/registry edits.
