"""Retrieve the remote images a Markdown source references, once, into a reviewable Repair Set.

`prepare` never fetches for a Markdown source, because a stable file on disk must build a stable
book. This package is the one explicit step that touches the network on its behalf: it reads the
source, retrieves each remote image under hardened public-network bounds, writes the bytes
and a rewritten Canonical Document into an evidence directory, and records what was pulled from
where in a `galley/localisation/1` document. What comes out is an ordinary agent-assisted repair,
which the ordinary repair path then prepares from local bytes.
"""
