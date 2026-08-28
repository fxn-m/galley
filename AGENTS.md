## Repository guidance

- Galley uses the standard Python `src` layout. Product code lives in `src/galley/`; keep that
  package boundary intact.
- Preserve the installed `galley` command, `python -m galley`, report and record schemas, and
  existing user-visible behaviour unless a change explicitly says otherwise.
- Add or update behavioural tests for observable changes. Tests should exercise stable module
  interfaces or the installed command rather than implementation details.
- Run `uv run --locked python scripts/check.py` before considering a change complete.
- Keep repository documentation public and self-contained. Never add personal paths, private
  project records, or references that only resolve on one contributor's machine.
