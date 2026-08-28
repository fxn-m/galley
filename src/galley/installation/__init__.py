"""Install and remove Galley's own Agent Skills in a discoverable target.

This package is about somebody else's directory. Everything else Galley writes is a file it
named itself inside a Workspace it resolved; a skill installation reaches into a target that may
already hold skills from other products, and the whole subject is knowing which files Galley may
speak for. That is what the Galley-managed manifest is: the record of exactly which relative
paths and hashes one installation put there, so a later run can tell its own work from a local
edit and from a stranger's file, and can refuse rather than guess.
"""
